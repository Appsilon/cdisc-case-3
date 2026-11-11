"""Reconcile every displayed number with the ARD, and build the TLF viewer.

Deterministic. For each table and listing, every body cell that shows numbers
names their ARD rows (data-ard="i,j", 0-based) and each number must equal its
row's stat rounded half away from zero at the shown precision (proportions may
be shown x100). Matching against exactly the named row - not any ARD value - is
what makes the check bite on large ARDs, where a wrong number usually equals
some other statistic. A number without its row was computed or typed in the
renderer - the failure the numbers-then-display discipline exists to prevent -
and goes back to the agent while attempts remain.

On pass writes tlf-viewer.html: one self-contained page with, per output, the
rendered display (hovering a cell shows the ARD rows it was rendered from), its
ARD, the program that made both, and the trace - ARS analysis, analysis set, record subset, methods, and each ADaM variable the
program reads with the derivation program lines from the ADaM lineage.

Result: { needsFix, retry, attempt, problems, checked, unmatched, summary }
"""

from __future__ import annotations

import base64
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, STEP_OUTPUTS_DIR, run_main, write_result  # noqa: E402
from tfllib import (  # noqa: E402
    ARD_INDEX, INPUTS_DIR, LOOP, MAX_PROBLEMS_PER_OUTPUT, PROGRAMS_DIR, RUN_DIR, SELF_CHECK, describe_ard_row, planned_outputs, read_json,
    reconcile_output,
)

STYLE = """
:root { color-scheme: light dark; --fg:#1d2433; --muted:#5b6475; --line:#d9dee7; --bg:#fff; --panel:#f6f8fb; --chip:#eef2f8; --accent:#2f5fd0; }
html.dark { --fg:#e6e9ef; --muted:#9aa3b2; --line:#333a47; --bg:#14171d; --panel:#1b1f27; --chip:#222834; --accent:#86a8ff; }
body { font: 14px/1.45 system-ui, sans-serif; color: var(--fg); background: var(--bg); margin: 0; display: flex; }
nav { width: 230px; flex: none; border-right: 1px solid var(--line); height: 100vh; overflow-y: auto; position: sticky; top: 0; padding: 12px 0; }
nav a { display: block; padding: 3px 14px; color: var(--fg); text-decoration: none; font-size: 13px; } nav a:hover { color: var(--accent); }
main { flex: 1; min-width: 0; padding: 16px 20px; } section { border-bottom: 1px solid var(--line); padding: 8px 0 20px; }
h1 { font-size: 18px; margin: 0 0 4px; } h2 { font-size: 16px; margin: 12px 0 4px; } p.meta { color: var(--muted); margin: 0 0 8px; }
.chip { background: var(--chip); border-radius: 4px; padding: 0 5px; font-size: 12px; margin-right: 4px; display: inline-block; }
iframe { width: 100%; height: 420px; border: 1px solid var(--line); background: #fff; } img { max-width: 100%; border: 1px solid var(--line); }
details { margin-top: 8px; } summary { cursor: pointer; color: var(--accent); }
table.ard { border-collapse: collapse; font-size: 12px; } table.ard td, table.ard th { border-bottom: 1px solid var(--line); padding: 2px 8px; text-align: left; }
pre { background: var(--panel); padding: 8px; overflow-x: auto; font-size: 12px; } dl { margin: 4px 0; } dt { color: var(--muted); float: left; width: 130px; } dd { margin: 0 0 2px 130px; }
@media (max-width: 700px) { body { display: block; } nav { display: none; } }
"""
ARD_ROWS_SHOWN = 300
CELL_REFS = re.compile(r"<t[dh]\b[^>]*?\sdata-ard\s*=\s*(?:(?P<quote>[\"'])(?P<quoted>[^\"']*)(?P=quote)|(?P<bare>[^\s>]+))", re.IGNORECASE)
HEAD_END = re.compile(r"</head>", re.IGNORECASE)
CELL_HOVER_STYLE = "<style>[data-ard]:hover{outline:2px solid #2f5fd0;cursor:help}</style>"


def chips(values) -> str:
    return "".join(f"<span class='chip'>{html.escape(str(value))}</span>" for value in values if value)


def lineage_index() -> dict[str, dict]:
    path = INPUTS_DIR / "lineage.json"
    if path.is_file() is False:
        return {}
    return {f"{item.get('dataset')}.{item.get('variable')}": item for item in read_json(path).get("variables") or []}


def ard_table(rows: list[dict]) -> str:
    columns = ["group1", "group1_level", "variable", "variable_level", "context", "stat_name", "stat"]
    body = "".join(f"<tr><td>{index}</td>" + "".join(f"<td>{html.escape(str(row.get(column, '')))}</td>" for column in columns) + "</tr>"
                   for index, row in enumerate(rows[:ARD_ROWS_SHOWN]))
    more = f"<p class='meta'>{len(rows) - ARD_ROWS_SHOWN} more rows in the ARD file.</p>" if len(rows) > ARD_ROWS_SHOWN else ""
    return f"<table class='ard'><tr><th>#</th>{''.join(f'<th>{column}</th>' for column in columns)}</tr>{body}</table>{more}"


def linked_display(display_html: str, rows: list[dict]) -> str:
    """The display with a tooltip on every data-ard cell naming the ARD rows it was rendered from."""
    def titled(match: re.Match) -> str:
        lines = [f"ARD #{index}: {describe_ard_row(rows[int(index)])}, stat={rows[int(index)].get('stat')}"
                 for index in (reference.strip() for reference in (match.group("quoted") or match.group("bare") or "").split(","))
                 if ARD_INDEX.fullmatch(index) is not None and int(index) < len(rows)]
        return match.group(0) + f' title="{html.escape(chr(10).join(lines))}"'
    linked = CELL_REFS.sub(titled, display_html)
    return HEAD_END.sub(lambda end: CELL_HOVER_STYLE + end.group(0), linked, count=1) if HEAD_END.search(linked) else linked + CELL_HOVER_STYLE


def section(final_id: str, meta: dict, spec: dict, tag: dict, lineage: dict, folder: Path, check: dict) -> str:
    html_path, png_path = folder / "tfl" / f"{final_id}.html", folder / "tfl" / f"{final_id}.png"
    display = ""
    if png_path.is_file():
        display += f"<img alt='{html.escape(final_id)}' src='data:image/png;base64,{base64.b64encode(png_path.read_bytes()).decode()}'>"
    ard_rows = read_json(folder / "ard" / f"{final_id}.json")
    if html_path.is_file():
        linked = linked_display(html_path.read_text(encoding="utf-8", errors="replace"), ard_rows)
        display += f"<iframe sandbox title='{html.escape(final_id)}' srcdoc=\"{html.escape(linked)}\"></iframe>"
    trace_rows = []
    for variable in tag.get("uses") or []:
        entry = lineage.get(variable)
        where = f"{entry.get('program')} lines {entry.get('lines')}" if entry else "no ADaM lineage supplied"
        sources = ", ".join(entry.get("sources") or []) if entry else ""
        trace_rows.append(f"<dd>{chips([variable])} ← {html.escape(where)}{(' ← ' + html.escape(sources)) if sources else ''}</dd>")
    methods = [method.get("type") or method.get("id") for method in spec.get("methods") or [] if isinstance(method, dict)]
    program = PROGRAMS_DIR / f"{final_id}.R"
    code = program.read_text(encoding="utf-8") if program.is_file() else ""
    checked = f"{check['checked']} displayed numbers reconciled with the ARD" if check.get("skipped") is None else check["skipped"]
    return f"""<section id="{html.escape(final_id)}"><h2>{html.escape(final_id)} {html.escape(str(meta.get('title') or ''))}</h2>
<p class="meta">{html.escape(checked)} · {len(ard_rows)} ARD rows</p>
<dl><dt>ARS analysis</dt><dd>{chips([tag.get('analysis')])}</dd>
<dt>Analysis set</dt><dd>{html.escape(str((spec.get('analysisSet') or {}).get('condition', '')))}</dd>
<dt>Records</dt><dd>{chips([(spec.get('dataSubset') or {}).get('dataset')])}{html.escape(str((spec.get('dataSubset') or {}).get('condition', '')))}</dd>
<dt>Methods</dt><dd>{chips(methods)}</dd><dt>ADaM → code</dt>{''.join(trace_rows) or '<dd>-</dd>'}</dl>
{display}
<details><summary>ARD (the numbers)</summary>{ard_table(ard_rows)}</details>
<details><summary>Program {html.escape(program.name)}</summary><pre>{html.escape(code)}</pre></details></section>"""


def viewer(outputs: dict, tags: dict, folder: Path, checks: dict) -> str:
    specs = {str(entry.get("table_id")): entry for entry in read_json(INPUTS_DIR / "analysis-spec.json") if isinstance(entry, dict)}
    lineage = lineage_index()
    ordered = sorted(tags)
    nav = "".join(f"<a href='#{html.escape(final_id)}'>{html.escape(final_id)}</a>" for final_id in ordered)
    body = "".join(section(final_id, outputs[final_id], specs.get(final_id, {}), tags[final_id], lineage, folder,
                           checks[final_id]) for final_id in ordered)
    numbers = sum(item["checked"] for item in checks.values())
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>TLF viewer</title><style>{STYLE}</style></head><body>
<nav>{nav}</nav><main><h1>Tables, listings and figures</h1>
<p class="meta">{len(ordered)} outputs · {numbers} displayed numbers, each matched to the ARD row its cell names (hover a cell) · every ARD computed by the program shown, from ADaM traced to its derivation lines</p>
{body}</main></body></html>"""


def main() -> None:
    folder = RUN_DIR if SELF_CHECK is True else STEP_OUTPUTS_DIR / "execute-programs"
    outputs = planned_outputs()
    tags = read_json(folder / "tags.json") if (folder / "tags.json").is_file() else {
        path.stem: {"id": path.stem} for path in (folder / "ard").glob("*.json")}
    checks, problems = {}, []
    for final_id in sorted(tags):
        listing = str(outputs.get(final_id, {}).get("type") or "").lower().startswith("listing")
        check = reconcile_output(final_id, folder / "tfl" / f"{final_id}.html", folder / "ard" / f"{final_id}.json", listing)
        checks[final_id] = check
        for item in check["unmatched"][:MAX_PROBLEMS_PER_OUTPUT]:
            problems.append(f"{final_id}: {item['where']}: {item['problem']} - compute it into the ARD, render from there "
                            "and name its row in data-ard")
        if len(check["unmatched"]) > MAX_PROBLEMS_PER_OUTPUT:
            problems.append(f"{final_id}: {len(check['unmatched']) - MAX_PROBLEMS_PER_OUTPUT} more unmatched value(s)")

    routing = LOOP.route("reconcile", problems)
    checked = sum(item["checked"] for item in checks.values())
    unmatched = sum(len(item["unmatched"]) for item in checks.values())
    if SELF_CHECK is False:
        (OUTPUT_DIR / "reconciliation.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
        if not problems:
            (OUTPUT_DIR / "tlf-viewer.html").write_text(viewer(outputs, tags, folder, checks), encoding="utf-8")
    summary = (f"ARD reconciliation FAILED (attempt {routing['attempt']}): {unmatched} problem(s) in {checked} displayed number(s) - each must match the ARD row its cell names."
               if problems else f"ARD reconciliation passed: {checked} displayed number(s) in {len(checks)} output(s) each match the ARD row their cell names.")
    write_result({**routing, "checked": checked, "unmatched": unmatched, "summary": summary})


if __name__ == "__main__":
    run_main(main)
