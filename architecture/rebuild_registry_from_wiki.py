#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rebuild_registry_from_wiki.py — reconstruct architecture/registry.json from the
wiki corpus that create_architecture.py emits.

The registry is the single source of truth for the architecture page, but it is a
``.json`` file and was once dropped from a push by a global ``*.json`` .gitignore
rule (while the generated ``architecture/wiki/*.md`` — which embed every field in
their frontmatter + body — survived). This script is the inverse of
``create_architecture.build_wiki_files``: it parses each ``<id>.md`` back into a
component and rewrites ``registry.json``. Keep it around: as long as the wiki
survives, the registry can always be rebuilt.

Field recovery per component:
  * frontmatter (YAML block the generator wrote): id, name, domain, project, type,
    runs_on, schedule_kst, status, code[], reads[], writes[], depends_on[], alerts
  * body: desc_md (between the overview line and "## Reads"), links[] ("## Links")
  * meta{updated, projects, version}: parsed from INDEX.md (CLI-overridable)

Component ORDER only affects the JS EDGES array's byte sequence in the generated
html (everything else sorts by name/domain independently). ``--order-from-html``
reproduces a surviving html's exact component order — recovered from its EDGES
sequence via the edge "owner" rule — so the regenerated page is byte-identical.
Without it, components are ordered by id (fine for a from-scratch regeneration).

Stdlib only. Usage:
    python architecture/rebuild_registry_from_wiki.py
    python architecture/rebuild_registry_from_wiki.py --order-from-html architecture.html
    python architecture/rebuild_registry_from_wiki.py --wiki-dir DIR --out FILE \
        --meta-updated 2026-07-07 --meta-version 1 --meta-projects antigravity
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WIKI_DIR = os.path.join(ROOT, "architecture", "wiki")
DEFAULT_OUT = os.path.join(ROOT, "architecture", "registry.json")

# Frontmatter keys that the generator emits as YAML block lists (vs scalars).
LIST_KEYS = {"code", "reads", "writes", "depends_on"}
# Output field order (readability; json preserves insertion order).
FIELD_ORDER = ["id", "project", "domain", "type", "name", "runs_on", "schedule_kst",
               "status", "desc_md", "code", "reads", "writes", "depends_on",
               "alerts", "links"]


def _unquote(s):
    """Reverse _yaml_scalar / _yaml_list quoting: strip wrapping quotes, unescape \\"."""
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1].replace('\\"', '"')
    return s


def parse_frontmatter(fm_text):
    """Parse the YAML frontmatter block (the exact subset create_architecture emits)."""
    data = {}
    lines = fm_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest == "":
            # non-empty block list: following "  - \"item\"" lines
            items = []
            j = i + 1
            while j < len(lines) and lines[j].startswith("  - "):
                items.append(_unquote(lines[j][4:]))
                j += 1
            data[key] = items
            i = j
            continue
        if rest == "[]":
            data[key] = []
            i += 1
            continue
        data[key] = _unquote(rest)
        i += 1
    return data


def parse_body(body_text):
    """Extract (desc_md, links) from the markdown body. desc_md is everything
    between the overview line and the first '## Reads' section; links come from
    the '## Links' section."""
    lines = body_text.split("\n")

    def find(pred, default=None):
        for i, l in enumerate(lines):
            if pred(l):
                return i
        return default

    reads_idx = find(lambda l: l.strip() == "## Reads", len(lines))
    title_idx = find(lambda l: l.startswith("# "), -1)

    ov_idx = None
    for i in range(title_idx + 1, reads_idx):
        if lines[i].strip():
            ov_idx = i
            break
    if ov_idx is not None and lines[ov_idx].lstrip().startswith("**"):
        desc_start = ov_idx + 1
    elif ov_idx is not None:
        desc_start = ov_idx
    else:
        desc_start = title_idx + 1
    desc_md = "\n".join(lines[desc_start:reads_idx]).strip()

    links = []
    li = find(lambda l: l.strip() == "## Links")
    if li is not None:
        for l in lines[li + 1:]:
            if l.strip().startswith("## "):
                break
            m = re.match(r"^- \[(.*?)\]\((.*)\)\s*$", l.strip())
            if m:
                links.append({"label": m.group(1), "url": m.group(2)})
    return desc_md, links


def parse_component(md_text):
    """Parse one <id>.md into a component dict (only non-empty fields kept)."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", md_text, re.S)
    if not m:
        raise ValueError("no frontmatter block found")
    fm = parse_frontmatter(m.group(1))
    desc_md, links = parse_body(m.group(2))

    comp = {}
    comp["id"] = fm.get("id")
    for k in ("project", "domain"):
        if fm.get(k):
            comp[k] = fm[k]
    comp["type"] = fm.get("type")
    comp["name"] = fm.get("name")
    for k in ("runs_on", "schedule_kst"):
        if fm.get(k):
            comp[k] = fm[k]
    comp["status"] = fm.get("status")
    if desc_md:
        comp["desc_md"] = desc_md
    for k in ("code", "reads", "writes", "depends_on"):
        if fm.get(k):
            comp[k] = fm[k]
    if fm.get("alerts"):
        comp["alerts"] = fm["alerts"]
    if links:
        comp["links"] = links

    # normalise to canonical field order
    return {k: comp[k] for k in FIELD_ORDER if k in comp}


def parse_meta_from_index(wiki_dir):
    """Recover meta{updated, projects, version} from INDEX.md when present."""
    meta = {}
    path = os.path.join(wiki_dir, "INDEX.md")
    if not os.path.exists(path):
        return meta
    text = open(path, "r", encoding="utf-8").read()
    m = re.search(r"^Updated:\s*(.+)$", text, re.M)
    if m:
        meta["updated"] = m.group(1).strip()
    m = re.search(r"projects:\s*(.+?)\s*·\s*v(\d+)", text)
    if m:
        meta["projects"] = [p.strip() for p in m.group(1).split(",") if p.strip()]
        meta["version"] = int(m.group(2))
    return meta


def order_from_html(comps, html_path):
    """Reorder components to reproduce a surviving html's EDGES byte sequence.

    In create_architecture.build_edges, each edge is appended while processing
    exactly one component (its "owner"): read/dep edges -> destination `b`,
    write edges -> source `a`. Each owner's edges form a consecutive block, so the
    original component order == order of first-owned-edge index. Components that
    own no edges don't affect the array and fall to the end (by id)."""
    data = open(html_path, "r", encoding="utf-8").read()
    m = re.search(r"var EDGES = (\[[\s\S]*?\]);", data)
    if not m:
        sys.stderr.write("WARN: no EDGES array in %s; ordering by id.\n" % html_path)
        return sorted(comps, key=lambda c: c["id"])
    target = json.loads(m.group(1))
    rank = {}
    for idx, e in enumerate(target):
        owner = e["b"] if e["k"] in ("read", "dep") else e["a"]
        rank.setdefault(owner, idx)
    big = len(target) + 1
    return sorted(comps, key=lambda c: (rank.get(c["id"], big), c["id"]))


def rebuild(wiki_dir, order_html=None, meta_overrides=None):
    comps = []
    for fn in sorted(os.listdir(wiki_dir)):
        if not fn.endswith(".md") or fn == "INDEX.md":
            continue
        text = open(os.path.join(wiki_dir, fn), "r", encoding="utf-8").read()
        try:
            comp = parse_component(text)
        except ValueError as exc:
            sys.stderr.write("WARN: %s: %s\n" % (fn, exc))
            continue
        if comp.get("id") and comp["id"] != fn[:-3]:
            sys.stderr.write("WARN: %s id '%s' != filename\n" % (fn, comp["id"]))
        comps.append(comp)

    if order_html:
        comps = order_from_html(comps, order_html)
    else:
        comps = sorted(comps, key=lambda c: c["id"])

    meta = parse_meta_from_index(wiki_dir)
    if meta_overrides:
        meta.update({k: v for k, v in meta_overrides.items() if v is not None})
    meta.setdefault("updated", "")
    meta.setdefault("projects", ["antigravity"])
    meta.setdefault("version", 1)
    # canonical meta key order
    meta = {k: meta[k] for k in ("updated", "projects", "version") if k in meta}

    return {"meta": meta, "components": comps}


def main():
    ap = argparse.ArgumentParser(description="Rebuild registry.json from wiki/*.md")
    ap.add_argument("--wiki-dir", default=DEFAULT_WIKI_DIR)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--order-from-html", default=None,
                    help="reproduce this html's component order (byte-identity)")
    ap.add_argument("--meta-updated", default=None)
    ap.add_argument("--meta-version", type=int, default=None)
    ap.add_argument("--meta-projects", default=None, help="comma-separated")
    ap.add_argument("--stdout", action="store_true", help="print to stdout, don't write")
    args = ap.parse_args()

    overrides = {}
    if args.meta_updated is not None:
        overrides["updated"] = args.meta_updated
    if args.meta_version is not None:
        overrides["version"] = args.meta_version
    if args.meta_projects is not None:
        overrides["projects"] = [p.strip() for p in args.meta_projects.split(",") if p.strip()]

    reg = rebuild(args.wiki_dir, order_html=args.order_from_html, meta_overrides=overrides)
    out = json.dumps(reg, ensure_ascii=False, indent=1)

    if args.stdout:
        sys.stdout.write(out + "\n")
    else:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
        print("wrote %s" % args.out)
    print("components: %d" % len(reg["components"]))
    print("meta: %s" % json.dumps(reg["meta"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
