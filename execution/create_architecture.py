#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""create_architecture.py — architecture registry -> interactive diagram page + wiki corpus.

Reads ``architecture/registry.json`` and generates two things:

  1. ``architecture.html`` (repo root)  — a single self-contained page (no external
     CDN; all CSS/JS inlined) with three stacked sections:
       * a 5-layer top-down diagram (input/notebooks -> GitHub -> compute VM/macmini
         -> data stores -> live pages) with clickable boxes and hover-highlighted
         cross-layer connection lines drawn as an SVG overlay,
       * a 00-24 KST schedule timeline,
       * a searchable, type-grouped wiki with rendered ``desc_md`` cards.
  2. ``architecture/wiki/<id>.md`` (+ ``INDEX.md``) — one self-contained markdown
     file per component, intended to read independently as an LLM/RAG corpus.

Stdlib only (json / html / re / os / sys / datetime / argparse).

Usage:
    python execution/create_architecture.py           # generate html + wiki
    python execution/create_architecture.py --check    # validate registry only, no output

If ``architecture/registry.json`` is absent, a built-in SAMPLE_REGISTRY (covering
every component type) is used so the renderer is developable/testable on its own.
See architecture/RENDERER_README.md for the full contract.
"""

import argparse
import datetime
import html
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG_PATH = os.path.join(ROOT, "architecture", "registry.json")
OUT_HTML = os.path.join(ROOT, "architecture.html")
WIKI_DIR = os.path.join(ROOT, "architecture", "wiki")

# ---------------------------------------------------------------------------
# Vocabulary: types, statuses, layers
# ---------------------------------------------------------------------------
# Type -> {label, light background tint, solid border/legend color}. Text is
# ALWAYS black (#000) per the dashboard style rule; only backgrounds/borders/lines
# carry colour.
TYPE_META = {
    "bot":             {"label": "Bot",        "bg": "#e3f2fd", "line": "#1565c0"},
    "timer":           {"label": "Timer",      "bg": "#e8f5e9", "line": "#2e7d32"},
    "gha_workflow":    {"label": "GHA",        "bg": "#f3e5f5", "line": "#7b1fa2"},
    "page":            {"label": "Page",       "bg": "#fff8e1", "line": "#f9a825"},
    "dataset":         {"label": "Dataset",    "bg": "#e0f7fa", "line": "#00838f"},
    "store":           {"label": "Store",      "bg": "#eceff1", "line": "#546e7a"},
    "infra":           {"label": "Infra",      "bg": "#fce4ec", "line": "#ad1457"},
    "external":        {"label": "External",   "bg": "#fff3e0", "line": "#ef6c00"},
    "pipeline_source": {"label": "Source",     "bg": "#f1f8e9", "line": "#558b2f"},
    "watcher":         {"label": "Watcher",    "bg": "#ede7f6", "line": "#5e35b1"},
}
DEFAULT_TYPE = {"label": "Other", "bg": "#f5f5f5", "line": "#757575"}

STATUS_META = {
    "active":  {"label": "active",  "css": "st-active"},
    "frozen":  {"label": "frozen",  "css": "st-frozen"},
    "retired": {"label": "retired", "css": "st-retired"},
    "planned": {"label": "planned", "css": "st-planned"},
}

# Domain groups for the wiki (7 fixed). Korean label + order. Registry adds a
# `domain` field per component; when absent (transition period), the wiki falls
# back to grouping by `type`.
DOMAIN_META = {
    "market-kr":      {"label": "국내 시장"},
    "market-global":  {"label": "해외 · 매크로"},
    "tech-semis":     {"label": "반도체 · 테크"},
    "portfolio-wrap": {"label": "포트폴리오 · WRAP"},
    "news-research":  {"label": "뉴스 · 리서치"},
    "personal":       {"label": "개인 · 가족"},
    "ops-infra":      {"label": "운영 · 인프라"},
}


def domain_label(d):
    if not d:
        return "(미분류)"
    return DOMAIN_META.get(d, {"label": d})["label"]

# 5 layers, top -> bottom on the page.
LAYERS = [
    (1, "입력 · 노트북", "Input & notebooks — manual inputs, laptop scripts, external sources"),
    (2, "GitHub — 정본 · Pages · GHA", "Source of truth, GitHub Pages, GitHub Actions workflows"),
    (3, "컴퓨트 — VM → 맥미니", "Always-on compute: bots, timers, watchers (Oracle VM, migrating to Mac mini)"),
    (4, "데이터 저장", "Data stores — datasets, JSON stores, databases"),
    (5, "라이브 페이지", "Live pages served to the browser"),
]
LAYER_IDS = [n for (n, _t, _d) in LAYERS]

# Kinds of cross-layer connection edges and their line colour.
EDGE_KIND = {
    "read":  {"label": "reads",      "color": "#2d7a3a"},
    "write": {"label": "writes",     "color": "#c0392b"},
    "dep":   {"label": "depends on", "color": "#8a8a8a"},
}


def layer_of(comp):
    """Assign a component to one of the 5 layers (top->bottom)."""
    t = (comp.get("type") or "").strip()
    r = (comp.get("runs_on") or "").strip()
    if t == "page":
        return 5
    if t in ("dataset", "store"):
        return 4
    if t in ("bot", "timer", "watcher") or r == "vm_macmini":
        return 3
    if t == "gha_workflow" or r in ("gha", "github"):
        return 2
    return 1  # external, pipeline_source, infra, laptop inputs, unknown


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def esc(s):
    return html.escape("" if s is None else str(s))


def type_meta(t):
    return TYPE_META.get(t, DEFAULT_TYPE)


def status_css(s):
    return STATUS_META.get(s, {"css": "st-active"})["css"]


def now_kst_str():
    """Current time formatted as the dashboards do: 'YYYY-MM-DD HH:MM:SS KST'."""
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S KST")


def truncate(s, n):
    """Ellipsize a display string to at most n characters."""
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def first_sentence(md, maxlen=90):
    """Extract a one-line plain-text summary from a desc_md body: the first
    meaningful (non-heading) line, stripped of markdown tokens, cut at the first
    sentence end or maxlen."""
    if not md:
        return ""
    line = ""
    for raw in str(md).replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("```"):
            continue
        s = re.sub(r"^#{1,6}\s*", "", s)          # heading markers
        s = re.sub(r"^[-*]\s+", "", s)            # list bullets
        s = re.sub(r"[*`]+", "", s)               # bold/inline-code marks
        s = s.strip()
        if s:
            line = s
            break
    if not line:
        return ""
    # cut at first sentence terminator (keep the period)
    m = re.search(r"[.。!?](\s|$)", line)
    if m and m.start() + 1 <= maxlen:
        line = line[: m.start() + 1]
    return truncate(line, maxlen)


def tip_attrs(c):
    """Build the data-* attributes that feed the shared custom tooltip
    (reused by diagram boxes and timeline labels)."""
    dom = c.get("domain")
    return (
        'data-tip="1" data-tip-name="%s" data-tip-sched="%s" '
        'data-tip-runs="%s" data-tip-domain="%s" data-tip-desc="%s"'
        % (esc(c.get("name") or c.get("id") or ""),
           esc(c.get("schedule_kst") or ""),
           esc(c.get("runs_on") or ""),
           esc(domain_label(dom) if dom else ""),
           esc(first_sentence(c.get("desc_md"), 110)))
    )


# ---------------------------------------------------------------------------
# Minimal markdown -> html (headings, bold, lists, inline+fenced code)
# ---------------------------------------------------------------------------
def _inline_md(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", lambda m: "<code>" + m.group(1) + "</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", lambda m: "<strong>" + m.group(1) + "</strong>", s)
    return s


def md_to_html(text):
    """Render a small markdown subset: #/##/### headings, **bold**, - lists,
    `inline code`, and ``` fenced code blocks. Everything else becomes <p>."""
    if not text:
        return ""
    lines = str(text).replace("\r\n", "\n").split("\n")
    out = []
    in_list = False
    i = 0

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            close_list()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(html.escape(lines[i]))
                i += 1
            i += 1  # consume closing fence (if present)
            out.append("<pre><code>" + "\n".join(buf) + "</code></pre>")
            continue
        stripped = line.strip()
        if not stripped:
            close_list()
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            close_list()
            tag = {1: "h4", 2: "h5", 3: "h6"}[len(m.group(1))]
            out.append("<%s>%s</%s>" % (tag, _inline_md(m.group(2)), tag))
            i += 1
            continue
        m = re.match(r"^[-*]\s+(.*)$", stripped)
        if m:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + _inline_md(m.group(1)) + "</li>")
            i += 1
            continue
        close_list()
        out.append("<p>" + _inline_md(stripped) + "</p>")
        i += 1
    close_list()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Schedule parsing (for the timeline)
# ---------------------------------------------------------------------------
def parse_schedule(text, ctype):
    """Return (times, full_bar, freq_label).

    times      -- list of minutes-past-midnight for discrete firings
    full_bar   -- True for always-on processes (bots/watchers) -> full-width bar
    freq_label -- one of '매일' / '주중' / '주1회' / '상시' / ''
    """
    t = "" if text is None else str(text)
    times = []
    for hh, mm in re.findall(r"(\d{1,2}):(\d{2})", t):
        h, m = int(hh), int(mm)
        if 0 <= h <= 24 and 0 <= m < 60:
            times.append(min(h * 60 + m, 1439))
    times = sorted(set(times))

    always = bool(re.search(r"상시|실시간|always|24/7|continuous", t, re.I))
    full_bar = always or (ctype in ("bot", "watcher") and not times)

    if re.search(r"주중|평일|월\s*[~\-]\s*금|화\s*[~\-]\s*토|mon\s*-\s*fri|weekday", t, re.I):
        freq = "주중"
    elif re.search(r"매주|주1|주간|매월|월1|weekly|monthly|토\s*요일|일\s*요일|토\s*0?9", t, re.I):
        freq = "주1회"
    elif always:
        freq = "상시"
    elif times:
        freq = "매일"
    else:
        freq = ""
    return times, full_bar, freq


# ---------------------------------------------------------------------------
# Registry loading & validation
# ---------------------------------------------------------------------------
def load_registry():
    """Return (registry_dict, is_real). Falls back to SAMPLE_REGISTRY if the
    on-disk registry.json is missing or unreadable."""
    if os.path.exists(REG_PATH):
        try:
            with open(REG_PATH, "r", encoding="utf-8") as fh:
                return json.load(fh), True
        except (ValueError, OSError) as exc:
            sys.stderr.write("WARN: could not read %s (%s); using sample.\n" % (REG_PATH, exc))
    return SAMPLE_REGISTRY, False


def validate(reg):
    """Check referential integrity. Returns a list of warning strings and also
    writes each to stderr. Broken id references in depends_on/reads/writes and
    duplicate ids are reported; generation continues regardless."""
    warnings = []
    comps = reg.get("components", [])
    ids = {}
    for c in comps:
        cid = c.get("id")
        if not cid:
            warnings.append("component missing 'id': %r" % (c.get("name") or c))
            continue
        if cid in ids:
            warnings.append("duplicate id '%s'" % cid)
        ids[cid] = c

    known = set(ids)
    known_types = set(TYPE_META)
    known_status = set(STATUS_META)
    known_domains = set(DOMAIN_META)
    for c in comps:
        cid = c.get("id", "?")
        if c.get("type") not in known_types:
            warnings.append("component '%s' has unknown type '%s'" % (cid, c.get("type")))
        if c.get("status") not in known_status:
            warnings.append("component '%s' has unknown status '%s'" % (cid, c.get("status")))
        if c.get("domain") and c.get("domain") not in known_domains:
            warnings.append("component '%s' has unknown domain '%s'" % (cid, c.get("domain")))
        for field in ("depends_on", "reads", "writes"):
            for ref in c.get(field, []) or []:
                if ref not in known:
                    warnings.append("component '%s' %s -> unknown id '%s'" % (cid, field, ref))
        for lk in c.get("links", []) or []:
            if not isinstance(lk, dict) or "url" not in lk:
                warnings.append("component '%s' has malformed link entry %r" % (cid, lk))

    for w in warnings:
        sys.stderr.write("WARN: " + w + "\n")
    return warnings


def build_edges(reg):
    """Build cross-layer connection edges. Each edge is {a, b, k} meaning an
    arrow a -> b (flow direction). Only edges whose endpoints resolve to known
    components AND sit on different layers are returned (same-layer deps are
    shown as card text instead, to keep the diagram readable)."""
    comps = reg.get("components", [])
    by_id = {c["id"]: c for c in comps if c.get("id")}
    layer = {cid: layer_of(c) for cid, c in by_id.items()}
    edges = []
    seen = set()

    def add(a, b, k):
        if a not in by_id or b not in by_id or a == b:
            return
        if layer[a] == layer[b]:
            return
        key = (a, b, k)
        if key in seen:
            return
        seen.add(key)
        edges.append({"a": a, "b": b, "k": k})

    for c in comps:
        cid = c.get("id")
        if not cid:
            continue
        for ref in c.get("reads", []) or []:      # comp reads ref: ref -> comp
            add(ref, cid, "read")
        for ref in c.get("writes", []) or []:     # comp writes ref: comp -> ref
            add(cid, ref, "write")
        for ref in c.get("depends_on", []) or []:  # comp depends on ref: ref -> comp
            add(ref, cid, "dep")
    return edges


# ===========================================================================
# HTML generation
# ===========================================================================
PAGE_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Pretendard Variable', Pretendard, system-ui, -apple-system, sans-serif;
       background: #f8f9fa; color: #000; line-height: 1.6; }
a { color: #000; }

/* ---- top nav (matches index.html / market.html) ---- */
.topnav { background: #fff; border-bottom: 1px solid #e5e7eb; position: sticky; top: 0; z-index: 100; }
.topnav-inner { max-width: 1400px; margin: 0 auto; padding: 0 28px; display: flex; align-items: center; height: 72px; gap: 32px; }
.topnav-brand { font-size: 1.3rem; font-weight: 800; letter-spacing: 1.5px; color: #111; white-space: nowrap; text-decoration: none; }
.topnav-brand:hover { color: #2d7a3a; }
.topnav-tabs { display: flex; gap: 12px; flex: 1; align-items: center; }
.topnav-item { position: relative; }
.topnav-tab { box-sizing: border-box; min-width: 180px; justify-content: center; padding: 10px 24px; display: inline-flex; align-items: center; gap: 6px; color: #444; text-decoration: none; font-size: 1rem; font-weight: 600; border: 1.5px solid #d1d5db; border-radius: 999px; white-space: nowrap; background: #fff; transition: all 0.15s; cursor: pointer; }
.topnav-tab:hover { color: #111; border-color: #2d7a3a; background: #f0f7f2; }
.topnav-tab.active { color: #fff; border-color: #2d7a3a; background: #2d7a3a; }
.topnav-dropdown { box-sizing: border-box; position: absolute; top: calc(100% + 8px); left: 0; min-width: 180px; width: 100%; background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.10); padding: 6px; opacity: 0; visibility: hidden; transform: translateY(-4px); transition: opacity 0.15s, transform 0.15s, visibility 0.15s; z-index: 200; }
.topnav-item:hover .topnav-dropdown, .topnav-item:focus-within .topnav-dropdown { opacity: 1; visibility: visible; transform: translateY(0); }
.topnav-sub { display: block; padding: 9px 14px; color: #333; text-decoration: none; font-size: 0.9rem; font-weight: 500; border-radius: 8px; white-space: nowrap; text-align: center; }
.topnav-sub:hover { background: #f3f4f6; color: #111; }
@media (max-width: 800px) {
  .topnav-inner { padding: 0 12px; gap: 12px; height: 52px; }
  .topnav-brand { font-size: 0.95rem; }
  .topnav-tab { padding: 6px 14px; font-size: 0.85rem; min-width: 0; }
  .topnav-tabs { gap: 6px; }
}

/* ---- page shell ---- */
.wrap { max-width: 1400px; margin: 0 auto; padding: 28px 28px 80px; }
header.page-head { text-align: center; padding: 18px 0 8px; border-bottom: 1px solid #e5e7eb; margin-bottom: 24px; position: relative; }
header.page-head h1 { font-size: 33px; color: #111; font-weight: 800; }
.last-updated { margin-top: 8px; color: #6c757d; font-size: 15px; font-style: italic; }
.meta-line { margin-top: 4px; color: #6c757d; font-size: 13px; }
.sample-banner { margin: 12px auto 0; max-width: 760px; background: #fff3e0; border: 1.5px solid #ef6c00; color: #000; border-radius: 10px; padding: 8px 14px; font-size: 14px; text-align: center; }

section.block { margin: 34px 0; }
h2.block-title { font-size: 1.4rem; color: #111; font-weight: 800; margin-bottom: 6px; }
.block-sub { color: #555; font-size: 14px; margin-bottom: 16px; }

/* ---- legend ---- */
.legend { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; margin: 10px 0 18px; font-size: 13px; }
.legend .lg-item { display: inline-flex; align-items: center; gap: 6px; }
.legend .sw { width: 16px; height: 16px; border-radius: 4px; border: 1.5px solid #999; display: inline-block; }
.legend .sw-line { width: 22px; height: 0; border-top-width: 3px; border-top-style: solid; display: inline-block; }
.legend .sep { width: 1px; height: 16px; background: #ddd; }

/* ---- diagram ---- */
.diagram { position: relative; }
.edge-svg { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; overflow: visible; }
.layers { position: relative; z-index: 2; display: flex; flex-direction: column; gap: 14px; }
.layer { border: 1px solid #e5e7eb; border-radius: 12px; background: #fff; padding: 12px 14px; }
.layer-head { font-size: 0.82rem; font-weight: 700; color: #111; letter-spacing: 0.3px; margin-bottom: 4px; }
.layer-desc { font-size: 12px; color: #777; margin-bottom: 10px; }
.layer-nodes { display: flex; flex-wrap: wrap; gap: 10px; }
.node { position: relative; min-width: 150px; max-width: 230px; border: 1.5px solid #bbb; border-radius: 9px; padding: 8px 11px; cursor: pointer; background: #fff; transition: box-shadow 0.12s, transform 0.12s; color: #000; }
.node:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.12); transform: translateY(-1px); }
.node:focus { outline: 2px solid #2d7a3a; outline-offset: 2px; }
.node .node-type { display: inline-block; font-size: 0.62rem; font-weight: 700; letter-spacing: 0.4px; text-transform: uppercase; padding: 1px 7px; border-radius: 999px; border: 1px solid; background: #fff; margin-bottom: 4px; color: #000; }
.node .node-name { display: block; font-size: 0.9rem; font-weight: 700; color: #000; max-width: 205px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.node .node-sched { display: block; font-size: 0.72rem; color: #333; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 205px; }
.node.st-frozen { border-style: dotted; }
.node.st-planned { border-style: dashed; }
.node.st-retired { opacity: 0.55; filter: grayscale(0.6); }
.node.node-dim { opacity: 0.28; }
.node.node-hl { box-shadow: 0 0 0 2.5px #2d7a3a; }
.edge-line { stroke-width: 1.6; fill: none; opacity: 0.5; transition: opacity 0.12s, stroke-width 0.12s; }
.edge-line.edge-hl { opacity: 1; stroke-width: 3; }
.edge-line.edge-dim { opacity: 0.06; }

/* ---- timeline ---- */
.timeline { border: 1px solid #e5e7eb; border-radius: 12px; background: #fff; padding: 14px 16px; overflow-x: auto; }
.tl-inner { min-width: 720px; }
.tl-axis { position: relative; height: 20px; margin-left: 210px; border-bottom: 1px solid #ddd; }
.tl-tick { position: absolute; top: 0; font-size: 11px; color: #777; transform: translateX(-50%); }
.tl-tick::after { content: ""; position: absolute; left: 50%; top: 16px; width: 1px; height: 6px; background: #ddd; }
.tl-row { display: flex; align-items: center; height: 30px; }
.tl-label { width: 210px; flex: 0 0 210px; font-size: 12.5px; color: #000; padding-right: 12px; text-align: right; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
.tl-label:hover .tl-name { color: #2d7a3a; text-decoration: underline; }
.tl-name { color: #000; }
.tl-freq { font-size: 10px; color: #fff; background: #9aa0a6; border-radius: 999px; padding: 0 6px; margin-left: 6px; }
.tl-freq.f매주 { background: #7b1fa2; }
.tl-track { position: relative; flex: 1 1 auto; height: 100%; background: repeating-linear-gradient(90deg, #f4f5f7 0, #f4f5f7 1px, transparent 1px, transparent 12.5%); border-radius: 4px; }
.tl-mark { position: absolute; top: 50%; width: 11px; height: 11px; border-radius: 50%; transform: translate(-50%, -50%); border: 1.5px solid #fff; cursor: default; }
.tl-bar { position: absolute; top: 50%; left: 0; right: 0; height: 8px; transform: translateY(-50%); border-radius: 4px; opacity: 0.5; }
.tl-trigger { position: absolute; top: 50%; left: 0; transform: translateY(-50%); font-size: 11px; color: #555; background: #eef0f2; border: 1px dashed #c2c6cc; border-radius: 999px; padding: 0 8px; white-space: nowrap; }
.tl-band { display: flex; align-items: center; gap: 9px; margin: 12px 0 4px; padding: 5px 10px; background: #eef2f1; border-left: 4px solid #2d7a3a; border-radius: 6px; }
.tl-band:first-of-type { margin-top: 8px; }
.tl-band-name { font-size: 0.95rem; font-weight: 800; color: #111; }
.tl-band-sub { font-size: 12px; color: #666; }
.tl-band-count { font-size: 0.78rem; font-weight: 700; color: #444; background: #fff; border-radius: 999px; padding: 1px 8px; margin-left: auto; }

/* ---- custom tooltip (shared by diagram boxes + timeline labels) ---- */
.arch-tip { position: fixed; z-index: 500; max-width: 320px; background: #fffdf5; border: 1.5px solid #c9ccd1; border-radius: 8px; padding: 8px 11px; font-size: 12.5px; color: #000; line-height: 1.45; box-shadow: 0 6px 20px rgba(0,0,0,0.16); pointer-events: none; display: none; }
.arch-tip .tip-name { font-weight: 800; margin-bottom: 3px; color: #000; }
.arch-tip .tip-meta { color: #333; }
.arch-tip .tip-desc { color: #333; margin-top: 4px; }

/* ---- wiki (compact collapsible list) ---- */
.wiki-tools { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.wiki-search { flex: 1 1 260px; max-width: 420px; padding: 9px 14px; font-size: 15px; border: 1.5px solid #d1d5db; border-radius: 999px; font-family: inherit; color: #000; }
.wiki-search:focus { outline: none; border-color: #2d7a3a; }
.wiki-count { color: #666; font-size: 13px; }
.wiki-group { margin-bottom: 22px; }
.wg-head { display: flex; align-items: center; gap: 10px; padding: 0 2px 8px; border-bottom: 2.5px solid #111; margin-bottom: 4px; }
.wg-head .g-sw { width: 15px; height: 15px; border-radius: 4px; border: 1.5px solid #999; }
.wg-head .wg-title { font-size: 1.06rem; font-weight: 800; color: #111; }
.wg-head .g-count { font-size: 0.82rem; font-weight: 700; color: #444; background: #eceff1; border-radius: 999px; padding: 1px 9px; }
.wiki-list { }
.witem { border-bottom: 1px solid #ececec; scroll-margin-top: 90px; }
.witem.wi-flash { animation: wiflash 1.6s ease-out; }
@keyframes wiflash { 0% { background: #e7f3ea; } 100% { background: transparent; } }
.witem-row { display: flex; align-items: baseline; gap: 9px; padding: 9px 6px; cursor: pointer; }
.witem-row:hover { background: #f6f8f7; }
.witem-row:focus { outline: 2px solid #2d7a3a; outline-offset: -2px; }
.wi-caret { flex: 0 0 auto; font-size: 0.7rem; color: #888; transition: transform 0.12s; transform: translateY(-1px); }
.witem.open .wi-caret { transform: rotate(90deg) translateX(-1px); }
.wi-name { flex: 0 0 auto; min-width: 130px; font-weight: 700; font-size: 0.95rem; color: #000; }
.wi-sched { flex: 0 0 auto; color: #555; font-size: 12px; white-space: nowrap; }
.wi-summary { flex: 1 1 auto; color: #333; font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.badge { flex: 0 0 auto; font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; padding: 1px 7px; border-radius: 999px; border: 1px solid; color: #000; background: #fff; align-self: center; }
.badge-status { border-color: #999; color: #000; background: #f3f4f6; }
.badge-status.st-active { background: #e8f5e9; border-color: #2e7d32; }
.badge-status.st-frozen { background: #e3f2fd; border-color: #1565c0; }
.badge-status.st-retired { background: #eceff1; border-color: #90a4ae; }
.badge-status.st-planned { background: #fff8e1; border-color: #f9a825; }
.witem-detail { display: none; padding: 2px 8px 14px 26px; }
.witem.open .witem-detail { display: block; }
.card-meta { font-size: 12px; color: #555; margin: 4px 0 8px; }
.card-desc { font-size: 13.5px; color: #000; }
.card-desc h4 { font-size: 0.98rem; margin: 8px 0 4px; }
.card-desc h5 { font-size: 0.9rem; margin: 8px 0 4px; }
.card-desc h6 { font-size: 0.84rem; margin: 6px 0 4px; color: #333; }
.card-desc ul { margin: 4px 0 8px 18px; }
.card-desc p { margin: 4px 0; }
.card-desc code { font-family: 'Consolas', 'Courier New', monospace; font-size: 0.85em; background: #f3f4f6; padding: 1px 5px; border-radius: 4px; color: #000; }
.card-desc pre { background: #f6f8fa; border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px; overflow-x: auto; margin: 6px 0; }
.card-desc pre code { background: none; padding: 0; }
.chips { margin-top: 10px; font-size: 12.5px; }
.chip-row { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; margin: 5px 0; }
.chip-row .chip-k { flex: 0 0 auto; min-width: 74px; font-weight: 700; color: #333; }
.chip { display: inline-block; font-size: 12px; padding: 2px 9px; border-radius: 999px; border: 1px solid #d1d5db; background: #f7f8fa; color: #000; text-decoration: none; }
.chip-ref { border-color: #9ec5a6; background: #eef6f0; color: #14532d; }
.chip-ref:hover { background: #ddeede; }
.chip-code { font-family: 'Consolas', 'Courier New', monospace; font-size: 11.5px; background: #f3f4f6; color: #000; }
.chip-ext { border-color: #f0b878; background: #fff3e0; color: #8a4b00; }
.chip-ext:hover { background: #ffe9cc; }
.card-alerts { margin-top: 8px; font-size: 12.5px; color: #000; background: #fff8e1; border: 1px solid #f9a825; border-radius: 6px; padding: 6px 10px; }
.no-match { color: #777; font-size: 14px; padding: 20px; text-align: center; }
@media (max-width: 640px) {
  .wi-summary { display: none; }
  .wi-name { min-width: 0; }
}
"""

TOP_NAV_HTML = (
    '<nav class="topnav"><div class="topnav-inner">'
    # 브랜드 텍스트 없음 — 다른 페이지(랜딩·마켓 계열)와 상단바 모습 통일 (2026-07-12 사용자)
    '<div class="topnav-tabs">'
    '<div class="topnav-item"><a href="wrap.html" class="topnav-tab">WRAP</a>'
    '<div class="topnav-dropdown">'
    '<a href="wrap.html#dashboard" class="topnav-sub">Dashboard</a>'
    '<a href="wrap.html#order" class="topnav-sub">Order</a>'
    '<a href="wrap.html#disclosures" class="topnav-sub">공시</a>'
    '<a href="wrap.html#contribution" class="topnav-sub">기여도</a>'
    '<a href="wrap.html#fee" class="topnav-sub">수수료</a></div></div>'
    '<div class="topnav-item"><a href="market.html" class="topnav-tab">Market</a>'
    '<div class="topnav-dropdown">'
    '<a href="market.html" class="topnav-sub">Data</a>'
    '<a href="universe.html" class="topnav-sub">Universe</a>'
    '<a href="universe_lab.html" class="topnav-sub">Universe Lab</a>'
    '<a href="featured.html" class="topnav-sub">Featured</a>'
    '<a href="market_alert.html" class="topnav-sub">투자유의종목</a>'
    '<a href="etf.html" class="topnav-sub">ETF</a>'
    '<a href="seibro.html" class="topnav-sub">SEIBro</a></div></div>'
    '<div class="topnav-item"><a href="architecture.html" class="topnav-tab active">Architecture</a></div>'
    '</div></div></nav>'
)


def _rel_links(refs, by_id):
    """Render a reads/writes/depends_on ref list as inline anchors to wiki cards.
    Unresolved refs (not a known component id) render as plain code text."""
    parts = []
    for ref in refs:
        c = by_id.get(ref)
        if c:
            parts.append('<a href="#wiki-%s" data-jump="%s">%s</a>'
                         % (esc(ref), esc(ref), esc(c.get("name") or ref)))
        else:
            parts.append('<code>%s</code>' % esc(ref))
    return ", ".join(parts)


def build_diagram(comps, by_id):
    """Return HTML for the 5-layer diagram (boxes only; edges drawn at runtime)."""
    buckets = {n: [] for n in LAYER_IDS}
    for c in comps:
        buckets[layer_of(c)].append(c)
    for n in buckets:
        buckets[n].sort(key=lambda c: (c.get("name") or "").lower())

    parts = ['<div class="diagram"><svg class="edge-svg" id="edgeSvg"></svg>',
             '<div class="layers" id="layers">']
    for (n, title, desc) in LAYERS:
        parts.append('<div class="layer" data-layer="%d">' % n)
        parts.append('<div class="layer-head">%s</div>' % esc(title))
        parts.append('<div class="layer-desc">%s</div>' % esc(desc))
        parts.append('<div class="layer-nodes">')
        if not buckets[n]:
            parts.append('<div class="layer-desc" style="opacity:.6">— (none)</div>')
        for c in buckets[n]:
            tm = type_meta(c.get("type"))
            cid = c.get("id", "")
            sched = c.get("schedule_kst") or ""
            parts.append(
                '<div class="node %s" data-id="%s" tabindex="0" role="button" '
                '%s style="background:%s">'
                % (status_css(c.get("status")), esc(cid), tip_attrs(c), tm["bg"]))
            parts.append('<span class="node-type" style="border-color:%s">%s</span>'
                         % (tm["line"], esc(tm["label"])))
            parts.append('<span class="node-name">%s</span>' % esc(c.get("name") or cid))
            if sched:
                parts.append('<span class="node-sched">%s</span>' % esc(truncate(sched, 22)))
            parts.append('</div>')
        parts.append('</div></div>')  # layer-nodes, layer
    parts.append('</div></div>')  # layers, diagram
    return "".join(parts)


# Time-of-day bands (top -> bottom). "always" holds always-on full bars,
# "weekly" holds weekly + event/push-triggered rows.
TIMELINE_BANDS = [
    ("always",   "⏱ 상시",                      "봇 · 워처 (상시 실행)"),
    ("morning",  "🌅 아침 브리핑 (05:00~08:59)", ""),
    ("intraday", "📈 장중 (09:00~15:49)",        ""),
    ("close",    "🏁 장마감 처리 (15:50~18:59)", ""),
    ("night",    "🌙 야간 (19:00~24:00)",        ""),
    ("weekly",   "📅 주간 · 이벤트",              "주1회 · 트리거 실행"),
]


def timeline_band(times, full_bar, freq):
    """Assign a scheduled component to a timeline band id."""
    if full_bar:
        return "always"
    if freq == "주1회" or not times:
        return "weekly"          # weekly cadence, or event/push (no fixed time)
    t0 = times[0]
    if 5 * 60 <= t0 < 9 * 60:
        return "morning"
    if 9 * 60 <= t0 < 15 * 60 + 50:
        return "intraday"
    if 15 * 60 + 50 <= t0 < 19 * 60:
        return "close"
    return "night"               # 19:00~24:00 and 00:00~04:59


def build_timeline(comps):
    """Return HTML for the 00-24 KST schedule timeline, grouped into named
    time-of-day bands."""
    buckets = {bid: [] for (bid, _l, _s) in TIMELINE_BANDS}
    for c in comps:
        times, full_bar, freq = parse_schedule(c.get("schedule_kst"), c.get("type"))
        # include anything always-on, timed, or carrying a schedule label
        if not times and not full_bar and not (c.get("schedule_kst") or "").strip():
            continue
        buckets[timeline_band(times, full_bar, freq)].append((c, times, full_bar, freq))

    for bid in buckets:
        buckets[bid].sort(key=lambda r: (r[1][0] if r[1] else 9999, (r[0].get("name") or "").lower()))

    parts = ['<div class="timeline"><div class="tl-inner">']
    # axis
    parts.append('<div class="tl-axis">')
    for h in range(0, 25, 3):
        parts.append('<span class="tl-tick" style="left:%.4f%%">%02d</span>' % (h / 24.0 * 100, h))
    parts.append('</div>')

    if not any(buckets.values()):
        parts.append('<div class="layer-desc" style="opacity:.6;padding:8px">— no scheduled components —</div>')

    for (bid, label, subtitle) in TIMELINE_BANDS:
        rows = buckets[bid]
        if not rows:
            continue
        sub = ('<span class="tl-band-sub">%s</span>' % esc(subtitle)) if subtitle else ""
        parts.append('<div class="tl-band"><span class="tl-band-name">%s</span>%s'
                     '<span class="tl-band-count">%d</span></div>' % (esc(label), sub, len(rows)))
        for (c, times, full_bar, freq) in rows:
            tm = type_meta(c.get("type"))
            cid = c.get("id", "")
            freq_cls = "f매주" if freq == "주1회" else ""
            parts.append('<div class="tl-row">')
            freq_tag = ('<span class="tl-freq %s">%s</span>' % (freq_cls, esc(freq))) if freq else ""
            parts.append('<div class="tl-label" data-jump="%s" %s><span class="tl-name">%s</span>%s</div>'
                         % (esc(cid), tip_attrs(c), esc(truncate(c.get("name") or cid, 13)), freq_tag))
            parts.append('<div class="tl-track">')
            if full_bar:
                parts.append('<span class="tl-bar" style="background:%s"></span>' % tm["line"])
            for mins in times:
                left = mins / 1440.0 * 100
                hh, mm = divmod(mins, 60)
                parts.append('<span class="tl-mark" style="left:%.4f%%;background:%s" title="%02d:%02d — %s"></span>'
                             % (left, tm["line"], hh, mm, esc(c.get("name") or cid)))
            if not times and not full_bar:  # event/push trigger, no fixed time
                parts.append('<span class="tl-trigger">%s</span>' % esc(truncate(c.get("schedule_kst") or "트리거", 26)))
            parts.append('</div></div>')
    parts.append('</div></div>')
    return "".join(parts)


def _wiki_grouping(comps):
    """Decide how to group the wiki. Returns (mode, ordered_groups) where each
    group is (key, header_html, items). Groups by `domain` if any component
    carries one; otherwise falls back to grouping by `type`."""
    has_domain = any(c.get("domain") for c in comps)
    if has_domain:
        groups = {}
        for c in comps:
            groups.setdefault(c.get("domain") or "", []).append(c)
        order = list(DOMAIN_META.keys())
        keys = [d for d in order if d in groups] + [d for d in sorted(groups) if d not in order]
        ordered = []
        for d in keys:
            items = sorted(groups[d], key=lambda c: (c.get("name") or "").lower())
            header = ('<div class="wg-head"><span class="wg-title">%s</span>'
                      '<span class="g-count">%d</span></div>'
                      % (esc(domain_label(d)), len(items)))
            ordered.append((d or "unassigned", header, items))
        return "domain", ordered

    groups = {}
    for c in comps:
        groups.setdefault(c.get("type"), []).append(c)
    order = list(TYPE_META.keys())
    keys = [t for t in order if t in groups] + [t for t in groups if t not in order]
    ordered = []
    for t in keys:
        tm = type_meta(t)
        items = sorted(groups[t], key=lambda c: (c.get("name") or "").lower())
        header = ('<div class="wg-head"><span class="g-sw" style="background:%s;border-color:%s"></span>'
                  '<span class="wg-title">%s</span><span class="g-count">%d</span></div>'
                  % (tm["bg"], tm["line"], esc(tm["label"]), len(items)))
        ordered.append((t or "other", header, items))
    return "type", ordered


def build_wiki_section(comps, by_id):
    """Return HTML for the searchable wiki. Grouped by domain (Korean section
    headers) when the registry supplies `domain`, else by type. Each component is
    a collapsed one-line row; clicking expands its full detail."""
    mode, groups = _wiki_grouping(comps)

    parts = ['<div class="wiki-tools">',
             '<input type="text" class="wiki-search" id="wikiSearch" placeholder="이름·설명 검색…" aria-label="search components">',
             '<span class="wiki-count" id="wikiCount"></span></div>',
             '<div id="wikiGroups" data-group-mode="%s">' % mode]
    for (key, header, items) in groups:
        parts.append('<section class="wiki-group" data-group="%s">' % esc(key))
        parts.append(header)
        parts.append('<div class="wiki-list">')
        for c in items:
            parts.append(build_witem(c, by_id))
        parts.append('</div></section>')
    parts.append('</div>')
    parts.append('<div class="no-match" id="noMatch" style="display:none">검색 결과가 없습니다.</div>')
    return "".join(parts)


def build_witem(c, by_id):
    """One collapsible wiki row: collapsed = [name · badges · schedule · one-line
    summary]; expanded = full desc_md + code/reads/writes/depends_on chips +
    links + alerts. Collapsed by default."""
    cid = c.get("id", "")
    tm = type_meta(c.get("type"))
    st = c.get("status") or "active"
    name = c.get("name") or cid
    summary = first_sentence(c.get("desc_md"), 60)
    sched = c.get("schedule_kst") or ""
    search_text = " ".join([
        name, cid, c.get("type") or "", c.get("project") or "",
        c.get("domain") or "", domain_label(c.get("domain")) if c.get("domain") else "",
        c.get("desc_md") or "", sched, " ".join(c.get("code", []) or []),
    ]).lower()

    p = ['<div class="witem" id="wiki-%s" data-id="%s" data-search="%s">'
         % (esc(cid), esc(cid), esc(search_text))]

    # --- collapsed row ---
    p.append('<div class="witem-row" role="button" tabindex="0" aria-expanded="false">')
    p.append('<span class="wi-caret">▸</span>')
    p.append('<span class="wi-name">%s</span>' % esc(name))
    p.append('<span class="badge" style="background:%s;border-color:%s">%s</span>'
             % (tm["bg"], tm["line"], esc(tm["label"])))
    p.append('<span class="badge badge-status %s">%s</span>' % (status_css(st), esc(st)))
    if sched:
        p.append('<span class="wi-sched">%s</span>' % esc(sched))
    if summary:
        p.append('<span class="wi-summary">%s</span>' % esc(summary))
    p.append('</div>')  # witem-row

    # --- expanded detail ---
    d = ['<div class="witem-detail">']
    meta_bits = []
    if c.get("domain"):
        meta_bits.append("Domain: " + esc(domain_label(c["domain"])))
    if c.get("project"):
        meta_bits.append("Project: " + esc(c["project"]))
    if c.get("runs_on"):
        meta_bits.append("Runs on: " + esc(c["runs_on"]))
    if c.get("schedule_kst"):
        meta_bits.append("Schedule: " + esc(c["schedule_kst"]))
    if meta_bits:
        d.append('<div class="card-meta">%s</div>' % " · ".join(meta_bits))
    if c.get("desc_md"):
        d.append('<div class="card-desc">%s</div>' % md_to_html(c["desc_md"]))

    chips = []
    for label, field in (("reads", "reads"), ("writes", "writes"), ("depends on", "depends_on")):
        refs = c.get(field, []) or []
        if refs:
            chip_html = "".join(_ref_chip(r, by_id) for r in refs)
            chips.append('<div class="chip-row"><span class="chip-k">%s</span>%s</div>' % (label, chip_html))
    if c.get("code"):
        code_html = "".join('<span class="chip chip-code">%s</span>' % esc(x) for x in c["code"])
        chips.append('<div class="chip-row"><span class="chip-k">code</span>%s</div>' % code_html)
    for lk in c.get("links", []) or []:
        if isinstance(lk, dict) and lk.get("url"):
            chips.append('<div class="chip-row"><span class="chip-k">link</span>'
                         '<a class="chip chip-ext" href="%s" target="_blank" rel="noopener">%s ↗</a></div>'
                         % (esc(lk["url"]), esc(lk.get("label") or lk["url"])))
    if chips:
        d.append('<div class="chips">' + "".join(chips) + '</div>')
    if c.get("alerts"):
        d.append('<div class="card-alerts">⚠ %s</div>' % esc(c["alerts"]))
    d.append('</div>')  # witem-detail

    p.append("".join(d))
    p.append('</div>')  # witem
    return "".join(p)


def _ref_chip(ref, by_id):
    tgt = by_id.get(ref)
    if tgt:
        return ('<a class="chip chip-ref" href="#wiki-%s" data-jump="%s">%s</a>'
                % (esc(ref), esc(ref), esc(tgt.get("name") or ref)))
    return '<span class="chip chip-code">%s</span>' % esc(ref)


def build_legend():
    parts = ['<div class="legend">']
    for t, m in TYPE_META.items():
        parts.append('<span class="lg-item"><span class="sw" style="background:%s;border-color:%s"></span>%s</span>'
                     % (m["bg"], m["line"], esc(m["label"])))
    parts.append('<span class="sep"></span>')
    parts.append('<span class="lg-item"><span class="sw" style="border-style:dotted"></span>frozen</span>')
    parts.append('<span class="lg-item"><span class="sw" style="border-style:dashed"></span>planned</span>')
    parts.append('<span class="lg-item"><span class="sw" style="opacity:.5;filter:grayscale(.6)"></span>retired</span>')
    parts.append('<span class="sep"></span>')
    for k, m in EDGE_KIND.items():
        parts.append('<span class="lg-item"><span class="sw-line" style="border-top-color:%s"></span>%s</span>'
                     % (m["color"], esc(m["label"])))
    parts.append('</div>')
    return "".join(parts)


PAGE_JS = """
(function () {
  var EDGES = __EDGES__;
  var KIND_COLOR = __KIND_COLOR__;
  var SVGNS = "http://www.w3.org/2000/svg";
  var diagram = document.querySelector(".diagram");
  var svg = document.getElementById("edgeSvg");
  var lineEls = [];

  function nodeEl(id) { return diagram.querySelector('.node[data-id="' + cssEsc(id) + '"]'); }
  function cssEsc(s) { return String(s).replace(/["\\\\]/g, "\\\\$&"); }

  function ensureDefs() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var defs = document.createElementNS(SVGNS, "defs");
    for (var k in KIND_COLOR) {
      var mk = document.createElementNS(SVGNS, "marker");
      mk.setAttribute("id", "arrow-" + k);
      mk.setAttribute("viewBox", "0 0 10 10");
      mk.setAttribute("refX", "9"); mk.setAttribute("refY", "5");
      mk.setAttribute("markerWidth", "6"); mk.setAttribute("markerHeight", "6");
      mk.setAttribute("orient", "auto-start-reverse");
      var pa = document.createElementNS(SVGNS, "path");
      pa.setAttribute("d", "M0,0 L10,5 L0,10 z");
      pa.setAttribute("fill", KIND_COLOR[k]);
      mk.appendChild(pa); defs.appendChild(mk);
    }
    svg.appendChild(defs);
  }

  function drawEdges() {
    ensureDefs();
    lineEls = [];
    var cb = diagram.getBoundingClientRect();
    svg.setAttribute("width", diagram.scrollWidth);
    svg.setAttribute("height", diagram.scrollHeight);
    svg.setAttribute("viewBox", "0 0 " + diagram.scrollWidth + " " + diagram.scrollHeight);
    EDGES.forEach(function (e) {
      var ea = nodeEl(e.a), eb = nodeEl(e.b);
      if (!ea || !eb) return;
      var ra = ea.getBoundingClientRect(), rb = eb.getBoundingClientRect();
      var ax = ra.left - cb.left + ra.width / 2, ay = ra.top - cb.top + ra.height / 2;
      var bx = rb.left - cb.left + rb.width / 2, by = rb.top - cb.top + rb.height / 2;
      // attach at the box edges facing each other
      if (ay <= by) { ay = ra.bottom - cb.top; by = rb.top - cb.top; }
      else { ay = ra.top - cb.top; by = rb.bottom - cb.top; }
      var color = KIND_COLOR[e.k] || "#888";
      var mx = (ax + bx) / 2;
      var d = "M" + ax + "," + ay + " C" + ax + "," + (ay + by) / 2 + " " + bx + "," + (ay + by) / 2 + " " + bx + "," + by;
      var ln = document.createElementNS(SVGNS, "path");
      ln.setAttribute("d", d);
      ln.setAttribute("class", "edge-line");
      ln.setAttribute("stroke", color);
      ln.setAttribute("marker-end", "url(#arrow-" + e.k + ")");
      ln.dataset.a = e.a; ln.dataset.b = e.b;
      svg.appendChild(ln);
      lineEls.push(ln);
    });
  }

  function highlight(id) {
    var connected = {};
    lineEls.forEach(function (ln) {
      if (ln.dataset.a === id || ln.dataset.b === id) {
        ln.classList.add("edge-hl"); ln.classList.remove("edge-dim");
        connected[ln.dataset.a] = 1; connected[ln.dataset.b] = 1;
      } else { ln.classList.add("edge-dim"); ln.classList.remove("edge-hl"); }
    });
    diagram.querySelectorAll(".node").forEach(function (n) {
      var nid = n.dataset.id;
      if (nid === id || connected[nid]) { n.classList.add("node-hl"); n.classList.remove("node-dim"); }
      else { n.classList.add("node-dim"); n.classList.remove("node-hl"); }
    });
  }
  function clearHighlight() {
    lineEls.forEach(function (ln) { ln.classList.remove("edge-hl", "edge-dim"); });
    diagram.querySelectorAll(".node").forEach(function (n) { n.classList.remove("node-hl", "node-dim"); });
  }

  // ---- shared custom tooltip (diagram boxes + timeline labels) ----
  var tip = document.createElement("div");
  tip.className = "arch-tip";
  document.body.appendChild(tip);
  function showTip(el) {
    tip.innerHTML = "";
    var n = document.createElement("div"); n.className = "tip-name";
    n.textContent = el.getAttribute("data-tip-name") || ""; tip.appendChild(n);
    var sched = el.getAttribute("data-tip-sched");
    var runs = el.getAttribute("data-tip-runs");
    var dom = el.getAttribute("data-tip-domain");
    if (sched) { var s = document.createElement("div"); s.className = "tip-meta"; s.textContent = "⏱ " + sched; tip.appendChild(s); }
    if (runs) { var r = document.createElement("div"); r.className = "tip-meta"; r.textContent = "▶ " + runs; tip.appendChild(r); }
    if (dom) { var g = document.createElement("div"); g.className = "tip-meta"; g.textContent = "🗂 " + dom; tip.appendChild(g); }
    var desc = el.getAttribute("data-tip-desc");
    if (desc) { var d = document.createElement("div"); d.className = "tip-desc"; d.textContent = desc; tip.appendChild(d); }
    tip.style.display = "block";
  }
  function moveTip(ev) {
    var pad = 14, tw = tip.offsetWidth, th = tip.offsetHeight;
    var x = ev.clientX + pad, y = ev.clientY + pad;
    if (x + tw > window.innerWidth - 8) x = ev.clientX - tw - pad;
    if (y + th > window.innerHeight - 8) y = ev.clientY - th - pad;
    tip.style.left = Math.max(6, x) + "px";
    tip.style.top = Math.max(6, y) + "px";
  }
  function hideTip() { tip.style.display = "none"; }
  document.querySelectorAll("[data-tip]").forEach(function (el) {
    el.addEventListener("mouseenter", function () { showTip(el); });
    el.addEventListener("mousemove", moveTip);
    el.addEventListener("mouseleave", hideTip);
  });

  function jumpTo(id) {
    var item = document.getElementById("wiki-" + id);
    if (!item) return;
    item.classList.add("open");
    var row = item.querySelector(".witem-row");
    if (row) row.setAttribute("aria-expanded", "true");
    item.scrollIntoView({ behavior: "smooth", block: "center" });
    item.classList.remove("wi-flash"); void item.offsetWidth; item.classList.add("wi-flash");
  }

  // node interactions
  diagram.querySelectorAll(".node").forEach(function (n) {
    var id = n.dataset.id;
    n.addEventListener("mouseenter", function () { highlight(id); });
    n.addEventListener("mouseleave", clearHighlight);
    n.addEventListener("focus", function () { highlight(id); });
    n.addEventListener("blur", clearHighlight);
    n.addEventListener("click", function () { jumpTo(id); });
    n.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); jumpTo(id); }
    });
  });

  // wiki row expand / collapse
  document.querySelectorAll(".witem-row").forEach(function (row) {
    function toggle() {
      var item = row.parentNode;
      var open = item.classList.toggle("open");
      row.setAttribute("aria-expanded", open ? "true" : "false");
    }
    row.addEventListener("click", toggle);
    row.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggle(); }
    });
  });

  // timeline label + in-detail ref jumps
  document.querySelectorAll("[data-jump]").forEach(function (el) {
    el.addEventListener("click", function (ev) {
      if (el.tagName === "A") ev.preventDefault();
      jumpTo(el.dataset.jump);
    });
  });

  // wiki search (operates on the collapsed summary rows)
  var search = document.getElementById("wikiSearch");
  var countEl = document.getElementById("wikiCount");
  var items = Array.prototype.slice.call(document.querySelectorAll(".witem"));
  var noMatch = document.getElementById("noMatch");
  function runFilter() {
    var q = (search.value || "").trim().toLowerCase();
    var shown = 0;
    items.forEach(function (c) {
      var ok = !q || c.dataset.search.indexOf(q) !== -1;
      c.style.display = ok ? "" : "none";
      if (ok) shown++;
    });
    document.querySelectorAll(".wiki-group").forEach(function (g) {
      var any = g.querySelectorAll('.witem:not([style*="display: none"])').length > 0;
      g.style.display = any ? "" : "none";
    });
    if (countEl) countEl.textContent = shown + " / " + items.length + " components";
    if (noMatch) noMatch.style.display = shown ? "none" : "block";
  }
  if (search) { search.addEventListener("input", runFilter); }
  if (countEl) countEl.textContent = items.length + " components";

  // deep link (#wiki-<id>) on load
  function initHash() {
    if (location.hash && location.hash.indexOf("#wiki-") === 0) {
      jumpTo(location.hash.slice(6));
    }
  }

  var raf = 0;
  function scheduleDraw() { cancelAnimationFrame(raf); raf = requestAnimationFrame(drawEdges); }
  window.addEventListener("resize", scheduleDraw);
  window.addEventListener("load", function () { drawEdges(); initHash(); });
  drawEdges();
})();
"""


def build_html(reg, is_real):
    comps = reg.get("components", [])
    by_id = {c["id"]: c for c in comps if c.get("id")}
    meta = reg.get("meta", {})
    edges = build_edges(reg)

    updated = meta.get("updated") or now_kst_str()
    projects = meta.get("projects")
    version = meta.get("version")

    kind_color = {k: v["color"] for k, v in EDGE_KIND.items()}
    js = (PAGE_JS
          .replace("__EDGES__", json.dumps(edges, ensure_ascii=False))
          .replace("__KIND_COLOR__", json.dumps(kind_color, ensure_ascii=False)))

    meta_line = []
    if projects:
        if isinstance(projects, (list, tuple)):
            meta_line.append("Projects: " + ", ".join(str(x) for x in projects))
        else:
            meta_line.append("Projects: " + str(projects))
    meta_line.append("Components: %d" % len(comps))
    if version:
        meta_line.append("registry v" + str(version))

    banner = ""
    if not is_real:
        banner = ('<div class="sample-banner">샘플 레지스트리로 렌더링됨 — '
                  'architecture/registry.json 을 기다리는 중입니다.</div>')

    out = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="ko"><head>')
    out.append('<meta charset="UTF-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    out.append("<title>System Architecture — Age of Emergence</title>")
    out.append("<style>" + PAGE_CSS + "</style>")
    out.append("</head><body>")
    out.append(TOP_NAV_HTML)
    out.append('<div class="wrap">')
    out.append('<header class="page-head"><h1>System Architecture</h1>')
    out.append('<div class="last-updated">Updated: %s</div>' % esc(updated))
    out.append('<div class="meta-line">%s</div>' % esc(" · ".join(meta_line)))
    out.append(banner)
    out.append('</header>')

    # Section 1: diagram
    out.append('<section class="block">')
    out.append('<h2 class="block-title">계층 도식도</h2>')
    out.append('<div class="block-sub">박스를 클릭하면 아래 위키 카드로 이동합니다. 박스에 마우스를 올리면 연결선(reads/writes/depends_on)이 강조됩니다. 같은 레이어 내부 의존은 카드 텍스트로만 표시됩니다.</div>')
    out.append(build_legend())
    out.append(build_diagram(comps, by_id))
    out.append('</section>')

    # Section 2: timeline
    out.append('<section class="block">')
    out.append('<h2 class="block-title">스케줄 타임라인 (KST)</h2>')
    out.append('<div class="block-sub">00–24시 KST. 상시 실행(봇·워처)은 풀바, 예약 실행은 발화 시각 마커로 표시합니다.</div>')
    out.append(build_timeline(comps))
    out.append('</section>')

    # Section 3: wiki
    out.append('<section class="block">')
    out.append('<h2 class="block-title">위키</h2>')
    out.append('<div class="block-sub">도메인별 그룹(도메인 미지정 시 타입별). 행을 클릭하면 상세가 펼쳐집니다. 이름·설명으로 실시간 검색됩니다.</div>')
    out.append(build_wiki_section(comps, by_id))
    out.append('</section>')

    out.append('</div>')  # wrap
    out.append("<script>" + js + "</script>")
    out.append("</body></html>")

    html_str = "\n".join(out)
    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(html_str)
    return html_str, edges


# ===========================================================================
# Wiki markdown generation
# ===========================================================================
def _yaml_list(key, items):
    items = items or []
    if not items:
        return "%s: []" % key
    lines = ["%s:" % key]
    for it in items:
        lines.append('  - "%s"' % str(it).replace('"', '\\"'))
    return "\n".join(lines)


def _yaml_scalar(key, val):
    if val is None or val == "":
        return '%s: ""' % key
    return '%s: "%s"' % (key, str(val).replace('"', '\\"'))


def build_wiki_files(reg):
    """Write architecture/wiki/<id>.md for every component + INDEX.md. Returns
    the list of file paths written."""
    if not os.path.isdir(WIKI_DIR):
        os.makedirs(WIKI_DIR, exist_ok=True)

    comps = reg.get("components", [])
    by_id = {c["id"]: c for c in comps if c.get("id")}
    written = []

    def ref_lines(field):
        refs = c.get(field, []) or []
        if not refs:
            return "- (none)"
        rows = []
        for ref in refs:
            tgt = by_id.get(ref)
            if tgt:
                rows.append("- [[%s]] — %s" % (ref, tgt.get("name") or ref))
            else:
                rows.append("- `%s`" % ref)
        return "\n".join(rows)

    for c in comps:
        cid = c.get("id")
        if not cid:
            continue
        fm = ["---"]
        fm.append(_yaml_scalar("id", cid))
        fm.append(_yaml_scalar("name", c.get("name")))
        fm.append(_yaml_scalar("domain", c.get("domain")))
        fm.append(_yaml_scalar("project", c.get("project")))
        fm.append(_yaml_scalar("type", c.get("type")))
        fm.append(_yaml_scalar("runs_on", c.get("runs_on")))
        fm.append(_yaml_scalar("schedule_kst", c.get("schedule_kst")))
        fm.append(_yaml_scalar("status", c.get("status")))
        fm.append(_yaml_list("code", c.get("code")))
        fm.append(_yaml_list("reads", c.get("reads")))
        fm.append(_yaml_list("writes", c.get("writes")))
        fm.append(_yaml_list("depends_on", c.get("depends_on")))
        fm.append(_yaml_scalar("alerts", c.get("alerts")))
        fm.append("---")

        body = []
        body.append("# %s" % (c.get("name") or cid))
        body.append("")
        overview = []
        if c.get("domain"):
            overview.append("**Domain:** %s" % domain_label(c.get("domain")))
        if c.get("type"):
            overview.append("**Type:** %s" % type_meta(c.get("type"))["label"])
        if c.get("runs_on"):
            overview.append("**Runs on:** %s" % c["runs_on"])
        if c.get("schedule_kst"):
            overview.append("**Schedule (KST):** %s" % c["schedule_kst"])
        if c.get("status"):
            overview.append("**Status:** %s" % c["status"])
        if c.get("project"):
            overview.append("**Project:** %s" % c["project"])
        if overview:
            body.append(" · ".join(overview))
            body.append("")
        if c.get("desc_md"):
            body.append(str(c["desc_md"]).strip())
            body.append("")
        body.append("## Reads")
        body.append(ref_lines("reads"))
        body.append("")
        body.append("## Writes")
        body.append(ref_lines("writes"))
        body.append("")
        body.append("## Depends on")
        body.append(ref_lines("depends_on"))
        body.append("")
        body.append("## Code")
        if c.get("code"):
            body.extend("- `%s`" % x for x in c["code"])
        else:
            body.append("- (none)")
        body.append("")
        if c.get("alerts"):
            body.append("## Alerts")
            body.append("⚠ " + str(c["alerts"]).strip())
            body.append("")
        if c.get("links"):
            body.append("## Links")
            for lk in c["links"]:
                if isinstance(lk, dict) and lk.get("url"):
                    body.append("- [%s](%s)" % (lk.get("label") or lk["url"], lk["url"]))
            body.append("")

        path = os.path.join(WIKI_DIR, "%s.md" % cid)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(fm) + "\n\n" + "\n".join(body).rstrip() + "\n")
        written.append(path)

    # INDEX.md
    meta = reg.get("meta", {})
    idx = ["# Architecture Wiki Index", ""]
    proj = meta.get("projects")
    proj_str = ", ".join(str(x) for x in proj) if isinstance(proj, (list, tuple)) else (str(proj) if proj else "")
    idx.append("_Generated from `architecture/registry.json`%s%s — %d components._" % (
        (" · projects: " + proj_str) if proj_str else "",
        (" · v" + str(meta["version"])) if meta.get("version") else "",
        len(comps)))
    idx.append("")
    if meta.get("updated"):
        idx.append("Updated: %s" % meta["updated"])
        idx.append("")

    # By domain (only when the registry supplies domains)
    if any(c.get("domain") for c in comps):
        idx.append("## By domain")
        idx.append("")
        by_dom = {}
        for c in comps:
            by_dom.setdefault(c.get("domain") or "", []).append(c)
        dorder = list(DOMAIN_META.keys())
        for d in [x for x in dorder if x in by_dom] + [x for x in sorted(by_dom) if x not in dorder]:
            items = sorted(by_dom[d], key=lambda c: (c.get("name") or "").lower())
            idx.append("### %s (%d)" % (domain_label(d), len(items)))
            for c in items:
                cid = c.get("id", "")
                idx.append("- [%s](%s.md) — %s" % (c.get("name") or cid, cid, type_meta(c.get("type"))["label"]))
            idx.append("")

    idx.append("## By type")
    idx.append("")
    order = list(TYPE_META.keys())
    by_type = {}
    for c in comps:
        by_type.setdefault(c.get("type"), []).append(c)
    for t in [x for x in order if x in by_type] + [x for x in by_type if x not in order]:
        items = sorted(by_type[t], key=lambda c: (c.get("name") or "").lower())
        idx.append("### %s (%d)" % (type_meta(t)["label"], len(items)))
        for c in items:
            cid = c.get("id", "")
            desc = []
            if c.get("schedule_kst"):
                desc.append(c["schedule_kst"])
            if c.get("status"):
                desc.append(c["status"])
            tail = (" — " + ", ".join(desc)) if desc else ""
            idx.append("- [%s](%s.md)%s" % (c.get("name") or cid, cid, tail))
        idx.append("")

    idx.append("## By project")
    idx.append("")
    by_proj = {}
    for c in comps:
        by_proj.setdefault(c.get("project") or "(unassigned)", []).append(c)
    for pname in sorted(by_proj):
        items = sorted(by_proj[pname], key=lambda c: (c.get("name") or "").lower())
        idx.append("### %s (%d)" % (pname, len(items)))
        for c in items:
            cid = c.get("id", "")
            idx.append("- [%s](%s.md) — %s" % (c.get("name") or cid, cid, type_meta(c.get("type"))["label"]))
        idx.append("")

    idx_path = os.path.join(WIKI_DIR, "INDEX.md")
    with open(idx_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(idx).rstrip() + "\n")
    written.append(idx_path)

    # Prune stale .md files: the wiki dir is exclusively generator-owned, so any
    # .md not written this run belongs to a component that was removed/renamed.
    keep = {os.path.basename(p) for p in written}
    for fn in os.listdir(WIKI_DIR):
        if fn.endswith(".md") and fn not in keep:
            try:
                os.remove(os.path.join(WIKI_DIR, fn))
            except OSError:
                pass

    return written


# ===========================================================================
# HTML integrity self-check (stdlib html.parser)
# ===========================================================================
def verify_html(path):
    """Parse the generated HTML with html.parser and check void-aware tag
    balance. Returns (ok, message)."""
    from html.parser import HTMLParser

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr"}

    class Checker(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.tags = 0
            self.errors = []

        def handle_starttag(self, tag, attrs):
            self.tags += 1
            if tag not in VOID:
                self.stack.append(tag)

        def handle_startendtag(self, tag, attrs):
            self.tags += 1

        def handle_endtag(self, tag):
            if tag in VOID:
                return
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            else:
                self.errors.append("stray </%s>" % tag)

    with open(path, "r", encoding="utf-8") as fh:
        data = fh.read()
    ck = Checker()
    try:
        ck.feed(data)
    except Exception as exc:  # noqa: BLE001 - parser robustness check
        return False, "parse error: %s" % exc
    if ck.stack:
        ck.errors.append("unclosed: " + ", ".join(ck.stack[:8]))
    if ck.errors:
        return False, "; ".join(ck.errors[:8])
    return True, "parsed ok (%d tags)" % ck.tags


# ===========================================================================
# Sample registry (used when architecture/registry.json is absent) — covers
# every component type and both cross-layer + same-layer references.
# ===========================================================================
SAMPLE_REGISTRY = {
    "meta": {"updated": "2026-07-07 12:00:00 KST (sample)", "projects": ["Antigravity"], "version": "sample-1"},
    "components": [
        {
            "id": "krx_api", "project": "Antigravity", "type": "external", "name": "KRX Open API",
            "runs_on": "external", "status": "active",
            "desc_md": "한국거래소 공개 API. **Featured / 규모별 지수 / 밸류에이션** 수집의 원천.\n\n- 18:10 KST 일별 배포\n- 로그인 세션 필요(일부 엔드포인트)",
            "code": [], "reads": [], "writes": [], "depends_on": [],
            "links": [{"label": "KRX", "url": "https://data.krx.co.kr"}],
        },
        {
            "id": "manual_aum", "project": "Antigravity", "type": "pipeline_source", "name": "AUM 수기 입력",
            "runs_on": "laptop", "status": "active",
            "desc_md": "매일 `날짜/증권사/유형/원` 5줄 텍스트를 `/aum` 커맨드로 입력.",
            "code": ["add_aum.py"], "reads": [], "writes": ["wrap_nav_xlsx"], "depends_on": [],
        },
        {
            "id": "fetch_featured", "project": "Antigravity", "type": "gha_workflow", "name": "Featured 수집",
            "runs_on": "gha", "status": "active", "schedule_kst": "매일 16:20 / 18:30",
            "desc_md": "KRX 거래대금·시총·상승률 TOP 수집 → dataset.\n\n### 스케줄\n- 16:20 1차\n- 18:30 2차(KRX 18:10 배포 후)",
            "code": ["execution/fetch_featured_data_kis.py"],
            "reads": ["krx_api"], "writes": ["dataset_csv"], "depends_on": [],
        },
        {
            "id": "fetch_ecos", "project": "Antigravity", "type": "gha_workflow", "name": "ECOS 매크로 수집",
            "runs_on": "gha", "status": "active", "schedule_kst": "매일 17:40",
            "desc_md": "한국은행 ECOS 매크로 33종을 DATA 섹션에 통합.",
            "code": ["execution/fetch_ecos_data.py"],
            "reads": ["krx_api"], "writes": ["dataset_csv"], "depends_on": [], "alerts": "M2=161Y006 함정 주의",
        },
        {
            "id": "dataset_csv", "project": "Antigravity", "type": "dataset", "name": "dataset.csv",
            "runs_on": "github", "status": "active",
            "desc_md": "모든 매크로/커모디티/지수 시계열의 통합 정본 CSV. append-only.",
            "code": ["dataset.csv"], "reads": [], "writes": [], "depends_on": [],
        },
        {
            "id": "wrap_nav_xlsx", "project": "Antigravity", "type": "store", "name": "Wrap_NAV.xlsx",
            "runs_on": "github", "status": "active",
            "desc_md": "WRAP 상품별 NAV/기준가/수익률/AUM 시트. 대시보드 파생의 원천.",
            "code": ["Wrap_NAV.xlsx"], "reads": [], "writes": [], "depends_on": [],
        },
        {
            "id": "sisyphe_bot", "project": "Antigravity", "type": "bot", "name": "Sisyphe-Bot",
            "runs_on": "vm_macmini", "status": "active", "schedule_kst": "상시 (05:00 날씨·16:00 리포트 등)",
            "desc_md": "펀드/일상 텔레그램 봇. 포트폴리오 자동 업데이트·리포트·Featured 트리거.",
            "code": ["execution/sisyphe_bot.py"],
            "reads": ["wrap_nav_xlsx"], "writes": ["market_html"], "depends_on": ["vm_infra"],
        },
        {
            "id": "watch_wrap_nav", "project": "Antigravity", "type": "watcher", "name": "WatchWrapNav",
            "runs_on": "laptop", "status": "active", "schedule_kst": "상시 (5분 자가복구)",
            "desc_md": "로컬 Wrap_NAV.xlsx 변경 감지 → 재계산·push 파이프라인.",
            "code": ["watch_wrap_nav.py"],
            "reads": ["wrap_nav_xlsx"], "writes": ["wrap_nav_xlsx"], "depends_on": [],
        },
        {
            "id": "etf_collect_timer", "project": "Antigravity", "type": "timer", "name": "etf-collect.timer",
            "runs_on": "vm_macmini", "status": "active", "schedule_kst": "매일 16:30 / 18:00 재시도",
            "desc_md": "systemd 타이머로 ETF 구성종목 수집. 봇 재시작이 수집을 죽이던 문제 해결.",
            "code": ["scripts/run_etf_collect.sh"],
            "reads": [], "writes": ["etf_html"], "depends_on": ["vm_infra"],
        },
        {
            "id": "vm_infra", "project": "Antigravity", "type": "infra", "name": "Oracle VM (144.24.70.224)",
            "runs_on": "vm_macmini", "status": "frozen",
            "desc_md": "Ubuntu VM. 봇·타이머 호스트. **맥미니(arm64)로 이전 중** (목표 2026-06).",
            "code": ["scripts/deploy.sh"], "reads": [], "writes": [], "depends_on": [],
            "links": [{"label": "migration status", "url": "https://example.invalid/macmini"}],
        },
        {
            "id": "hotel_adr_timer", "project": "Antigravity", "type": "timer", "name": "HotelADRDaily (retired)",
            "runs_on": "vm_macmini", "status": "retired", "schedule_kst": "매일 12:00",
            "desc_md": "호텔 ADR 수집. 2026-07-06 전면 은퇴(크롬 행이 /update 잡을 굶겨 죽인 사고).",
            "code": ["execution/fetch_hotel_adr.py"], "reads": [], "writes": ["hotels_html"], "depends_on": ["vm_infra"],
        },
        {
            "id": "market_html", "project": "Antigravity", "type": "page", "name": "market.html",
            "runs_on": "github", "status": "active",
            "desc_md": "마켓 대시보드 — Monthly Returns 표 + Indices/MARKET 동적 차트.",
            "code": ["market.html"], "reads": ["dataset_csv"], "writes": [], "depends_on": [],
        },
        {
            "id": "etf_html", "project": "Antigravity", "type": "page", "name": "etf.html",
            "runs_on": "github", "status": "active",
            "desc_md": "ETF 구성종목 페이지. 액티브 ETF 서브탭 포함.",
            "code": ["etf.html"], "reads": [], "writes": [], "depends_on": [],
        },
        {
            "id": "hotels_html", "project": "Antigravity", "type": "page", "name": "hotels.html",
            "runs_on": "github", "status": "frozen",
            "desc_md": "호텔 ADR 페이지. 데이터 동결(수집 은퇴).",
            "code": ["hotels.html"], "reads": [], "writes": [], "depends_on": [],
        },
    ],
}


# ===========================================================================
# main
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(description="Generate architecture.html + wiki from registry.json")
    ap.add_argument("--check", action="store_true", help="validate registry only, no output")
    args = ap.parse_args()

    reg, is_real = load_registry()
    src = "registry.json" if is_real else "SAMPLE_REGISTRY (registry.json absent)"
    warnings = validate(reg)
    ncomp = len(reg.get("components", []))
    edges = build_edges(reg)

    if args.check:
        print("source: %s" % src)
        print("components: %d, cross-layer edges: %d" % (ncomp, len(edges)))
        print("warnings: %d" % len(warnings))
        return 1 if warnings else 0

    _, _ = build_html(reg, is_real)
    files = build_wiki_files(reg)
    ok, msg = verify_html(OUT_HTML)

    print("source          : %s" % src)
    print("components      : %d" % ncomp)
    print("cross-layer edges: %d" % len(edges))
    print("architecture.html: %s (%s)" % (OUT_HTML, msg))
    print("wiki files       : %d written to %s" % (len(files), WIKI_DIR))
    print("warnings         : %d (see stderr)" % len(warnings))
    if not ok:
        sys.stderr.write("ERROR: generated HTML failed integrity check: %s\n" % msg)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
