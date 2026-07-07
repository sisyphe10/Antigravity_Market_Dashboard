# Architecture Renderer

`execution/create_architecture.py` turns the architecture registry
(`architecture/registry.json`) into two artifacts:

1. **`architecture.html`** (repo root) — a single, self-contained interactive page
   (no external CDN; all CSS/JS inlined) with a layered system diagram, a schedule
   timeline, and a searchable wiki.
2. **`architecture/wiki/<id>.md`** (+ `INDEX.md`) — one self-contained markdown file
   per component, meant to read independently as an LLM/RAG search corpus.

> **These outputs are generated — do not hand-edit them.**
> `architecture.html` and everything under `architecture/wiki/` are overwritten on
> every run. Edit the **registry** (or the generator) and re-run. The wiki directory
> is generator-owned: `.md` files for components that no longer exist are pruned
> automatically.

The generator is **stdlib-only** (`json` / `html` / `re` / `os` / `sys` /
`datetime` / `argparse`) — no third-party dependencies, no network access.

---

## Usage

```bash
# generate architecture.html + wiki/*.md
python execution/create_architecture.py

# validate the registry only (referential integrity), no files written
python execution/create_architecture.py --check
```

Run from the repo root (paths are resolved relative to the script location, so it
also works from anywhere). On success it prints a summary:

```
source          : registry.json            # or "SAMPLE_REGISTRY (registry.json absent)"
components      : 42
cross-layer edges: 61
architecture.html: .../architecture.html (parsed ok (900 tags))
wiki files       : 43 written to .../architecture/wiki
warnings         : 0 (see stderr)
```

Exit codes: `0` OK · `2` generated HTML failed its integrity self-check.
`--check` returns `1` if any validation warnings were found (CI-friendly).

### Regeneration procedure (when the registry changes)

1. Edit `architecture/registry.json` (add/modify components).
2. `python execution/create_architecture.py --check` — confirm `warnings: 0`
   (broken id references and unknown enum values print to stderr).
3. `python execution/create_architecture.py` — regenerate.
4. Open `architecture.html` and eyeball the diagram/timeline/wiki (see *Local preview*).
5. Commit `architecture.html`, `architecture/wiki/**`, and `registry.json` together.

### Local preview

`file://` URLs are blocked by the Chrome automation extension and some browsers
restrict `fetch`; serve over a local HTTP server instead:

```bash
python -m http.server 8899 --bind 127.0.0.1
# then open http://127.0.0.1:8899/architecture.html
```

(The page needs no `fetch` — all data is inlined — so opening the file directly in a
normal browser window works too. The HTTP server is only needed for tooling.)

---

## Input contract — `architecture/registry.json`

```jsonc
{
  "meta": { "updated": "YYYY-MM-DD HH:MM:SS KST", "projects": ["..."], "version": "1" },
  "components": [
    {
      "id": "fetch_featured",              // unique slug; also the wiki filename (<id>.md)
      "project": "Antigravity",
      "domain": "market-kr",               // wiki grouping; see Domains below (optional)
      "type": "gha_workflow",              // see Types below
      "name": "Featured 수집",
      "runs_on": "gha",                    // vm_macmini | gha | laptop | github | external
      "schedule_kst": "매일 16:20 / 18:30", // free text; times parsed for the timeline
      "status": "active",                  // active | frozen | retired | planned
      "desc_md": "markdown body…",         // headings / bold / lists / code rendered
      "code": ["execution/fetch_featured_data_kis.py"],
      "reads":  ["krx_api"],               // component ids this reads FROM
      "writes": ["dataset_csv"],           // component ids this writes TO
      "depends_on": ["vm_infra"],          // upstream component ids
      "alerts": "…gotcha text…",           // optional; rendered as a warning box
      "links": [{ "label": "KRX", "url": "https://…" }]
    }
  ]
}
```

**`reads` / `writes` / `depends_on` are arrays of component `id`s** (not file paths).
They become the connection lines in the diagram and the cross-links in the wiki.
A ref that doesn't resolve to a known `id` is reported as a warning and, in the wiki,
rendered as plain `code` text rather than a link.

If `registry.json` is **absent or unreadable**, the generator falls back to a built-in
`SAMPLE_REGISTRY` (14 components covering every type) and stamps a "sample" banner on
the page, so the renderer is fully developable/testable on its own.

### Types (`type`)

`bot` · `timer` · `gha_workflow` · `page` · `dataset` · `store` · `infra` ·
`external` · `pipeline_source` · `watcher`

Each type has a light background tint and a border/legend colour (text is always
black, per the dashboard style rule). Unknown types render in a neutral grey and
raise a warning.

### Domains (`domain`) — wiki grouping

Optional field with 7 fixed values (Korean section label in parentheses):
`market-kr` (국내 시장) · `market-global` (해외 · 매크로) · `tech-semis` (반도체 · 테크) ·
`portfolio-wrap` (포트폴리오 · WRAP) · `news-research` (뉴스 · 리서치) ·
`personal` (개인 · 가족) · `ops-infra` (운영 · 인프라).

The wiki groups components by `domain` (Korean section headers, type shown only as a
per-row badge) **when any component carries one**; otherwise it falls back to grouping
by `type`. Domain is not drawn on the diagram boxes — it appears only in their hover
tooltip. Unknown domain values raise a warning and render under their raw label.

### Layer assignment (top → bottom, 5 layers)

Computed by `layer_of()` from `type` + `runs_on`:

| Layer | Name | Members |
|---|---|---|
| 1 | 입력 · 노트북 | `external`, `pipeline_source`, `infra`, `laptop` inputs, unknown |
| 2 | GitHub — 정본 · Pages · GHA | `gha_workflow`, or `runs_on` = `gha`/`github` |
| 3 | 컴퓨트 — VM → 맥미니 | `bot`, `timer`, `watcher`, or `runs_on` = `vm_macmini` |
| 4 | 데이터 저장 | `dataset`, `store` |
| 5 | 라이브 페이지 | `page` |

Only **cross-layer** edges are drawn as SVG lines (same-layer dependencies would
overcrowd the diagram, so they appear as text inside the wiki cards instead).

### Status (`status`)

`active` (solid border) · `frozen` (dotted border) · `planned` (dashed border) ·
`retired` (greyed + desaturated). Unknown values raise a warning and default to
`active` styling.

### `schedule_kst` parsing (timeline)

Free text. The generator extracts every `HH:MM` for the 00–24 KST timeline markers,
and derives a frequency label:

- `주중` — text matches 주중 / 평일 / 월~금 / 화~토 / weekday
- `주1회` — 매주 / 주1 / 매월 / weekly / monthly / 토·일요일
- `상시` — 상시 / 실시간 / always / 24/7 → drawn as a **full-width bar**
- `매일` — has times but none of the above

`bot` and `watcher` components render as full bars regardless (always-on processes),
with markers overlaid for any discrete times they also fire at.

Timeline rows are grouped into named **time-of-day bands** (`timeline_band()`), each
with a header strip and count, in this order: `⏱ 상시` (always-on full bars) ·
`🌅 아침 브리핑 (05:00~08:59)` · `📈 장중 (09:00~15:49)` · `🏁 장마감 처리 (15:50~18:59)` ·
`🌙 야간 (19:00~24:00)` · `📅 주간 · 이벤트` (weekly cadence + event/push-triggered rows
with no fixed time — these show a dashed "trigger" chip instead of a marker). Timed
rows land in a band by their first firing time; empty bands are omitted.

### `desc_md` — supported markdown subset

Headings (`#`/`##`/`###`), `**bold**`, `` `inline code` ``, fenced ```` ``` ````
code blocks, and `-`/`*` bullet lists. Everything else becomes a paragraph. HTML in
the source is escaped. (This subset is shared by the HTML cards and the raw `.md`
files — keep `desc_md` within it.)

---

## Output

### `architecture.html`

Three stacked sections, under the shared top nav (`AoE` brand → `index.html`;
WRAP / Market / **Architecture** tabs matching the other dashboards):

1. **계층 도식도** — the 5-layer diagram. Boxes are colored by type, bordered by
   status. Long box labels are truncated with an ellipsis; hovering a box shows a
   styled tooltip (full name / schedule / runs_on / domain / first sentence of `desc_md`)
   and highlights its incident cross-layer edges + connected boxes (dimming the
   rest); clicking a box scrolls to and flashes its wiki row. Edges are drawn at
   runtime as an SVG overlay (`reads` = green, `writes` = red, `depends_on` = grey)
   and redrawn on resize.
2. **스케줄 타임라인 (KST)** — 00–24 axis; rows grouped into named time-of-day bands
   (상시 / 아침 / 장중 / 장마감 / 야간 / 주간·이벤트, each with a header strip + count);
   full bars for always-on processes, dot markers at firing times, dashed trigger
   chips for event/push rows. Row labels are truncated with the same hover tooltip as
   the diagram boxes. Clicking a label jumps to the wiki row.
3. **위키** — **domain-grouped compact list** (falls back to type grouping when no
   component has a `domain`). Each component is a collapsed one-line row [name · type
   + status badges · schedule · one-line summary (first sentence of `desc_md`,
   ~60 chars)]; clicking the row expands the full `desc_md` plus code / reads / writes
   / depends_on chips (refs cross-link to other rows), links, and alerts. Everything is
   collapsed by default — no code/ref lists or long text show until expanded. Section
   headers are the Korean domain label (bold + rule + count); type appears only as a
   per-row badge. A search box filters the rows live by name/description/domain; empty
   groups hide. Deep-linkable: `architecture.html#wiki-<id>` expands and scrolls to a row.

Fully self-contained (no CDN/fetch), theme is the light dashboard palette with
black text throughout, and the wiki collapses to a single column on narrow screens.

### `architecture/wiki/<id>.md` + `INDEX.md`

Each component file has YAML frontmatter (`id`, `name`, `project`, `type`, `runs_on`,
`schedule_kst`, `status`, `code`, `reads`, `writes`, `depends_on`, `alerts`) followed
by an overview line, the `desc_md` body, and Reads / Writes / Depends-on / Code /
Alerts / Links sections. Cross-references use `[[id]] — name` so each file is
self-describing yet linkable. `INDEX.md` lists every component grouped **by type** and
**by project**. This directory is the intended corpus for future LLM/RAG search.

---

## Extending

- **Add a component type** — add an entry to `TYPE_META` (label + `bg` tint + `line`
  colour), and, if it belongs on a specific layer, extend `layer_of()`. It flows
  through the legend, diagram, timeline, and wiki automatically.
- **Add a status** — add to `STATUS_META` and give it a `.node.st-*` / `.badge-status.st-*`
  rule in `PAGE_CSS`.
- **Add an edge kind** — extend `EDGE_KIND` (label + colour) and emit it in
  `build_edges()`; the SVG arrow markers and legend pick it up.
- **Richer markdown** — extend `md_to_html()` / `_inline_md()` (keep the HTML and `.md`
  outputs consistent).
- **Layout/theme tweaks** — edit `PAGE_CSS`. The top nav (`TOP_NAV_HTML` / the
  `.topnav*` CSS) mirrors `index.html`; if the shared dashboard nav changes, update it
  here too (this page is not produced by `create_dashboard.py`).

### Integrity checks built in

- `validate()` reports duplicate ids, unknown types/statuses, malformed links, and
  broken `reads`/`writes`/`depends_on` id references to stderr (generation continues).
- After writing, `verify_html()` re-parses `architecture.html` with `html.parser` and
  checks void-aware tag balance; a failure exits non-zero.
- `python -m py_compile execution/create_architecture.py` should pass before committing.
