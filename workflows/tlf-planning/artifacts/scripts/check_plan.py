"""Deterministic gate over the planner's output, and the reviewable rendering of it.

Runs the planlib checks (schema, traces, numbering, endpoint coverage). On
failure the problems go to /workspace/tlf-planning/feedback.json and the plan
returns to the agent while attempts remain (three per review round). On pass
it publishes the plan files and tlf-plan.html - the plan as a table a
statistician can review, with the trace of every output and the flagged items
- for the critic and the human review.

Result: { needsFix, retry, attempt, problems, counts, summary }
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, run_main, write_result  # noqa: E402
from gate import MAX_ATTEMPTS  # noqa: E402
from planlib import LOOP, PLAN_CHECK_PATH, PLAN_DIR, PLAN_FILES, STUDY_MODEL, TLF_PLAN, check_plan  # noqa: E402

STYLE = """
:root { color-scheme: light dark; --fg:#1d2433; --muted:#5b6475; --line:#d9dee7; --bg:#fff; --chip:#eef2f8; --warn:#9a5b00; }
html.dark { --fg:#e6e9ef; --muted:#9aa3b2; --line:#333a47; --bg:#14171d; --chip:#222834; --warn:#e0a24a; }
body { font: 14px/1.45 system-ui, sans-serif; color: var(--fg); background: var(--bg); margin: 16px; }
h1 { font-size: 18px; margin: 0 0 4px; } h2 { font-size: 15px; margin: 20px 0 6px; }
p.meta { color: var(--muted); margin: 0 0 12px; }
table { border-collapse: collapse; width: 100%; } th, td { border-bottom: 1px solid var(--line); padding: 5px 8px; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; } code, .chip { background: var(--chip); border-radius: 4px; padding: 0 4px; font-size: 12px; }
td.reason { color: var(--warn); }
"""


def trace_text(candidate: dict) -> str:
    traces = candidate.get("traces_to") or {}
    parts = list(traces.get("objective_ids") or []) + list(traces.get("endpoint_ids") or [])
    if traces.get("regulatory_rule"):
        parts.append(str(traces["regulatory_rule"]))
    return " ".join(f"<span class='chip'>{html.escape(str(part))}</span>" for part in parts)


def analysis_text(candidate: dict) -> str:
    analysis = candidate.get("analysis") or {}
    fields = [analysis.get(key) for key in ("method", "population", "timepoint", "imputation", "subgroup")]
    return html.escape(" · ".join(str(value) for value in fields if value not in (None, "", "none")))


def render(model: dict, plan: list[dict], counts: dict) -> str:
    planned = sorted((item for item in plan if item.get("status") == "planned"), key=lambda item: str(item.get("final_id")))
    flagged = [item for item in plan if item.get("status") != "planned"]
    endpoints = {str(item.get("id")): item for item in model.get("endpoints") or []}
    rows = "".join(
        f"<tr><td><code>{html.escape(str(item.get('final_id')))}</code></td><td>{html.escape(str(item.get('title')))}</td>"
        f"<td>{html.escape(str(item.get('priority')))}</td><td>{analysis_text(item)}</td><td>{trace_text(item)}</td></tr>"
        for item in planned
    )
    flagged_rows = "".join(
        f"<tr><td>{html.escape(str(item.get('candidate_id')))}</td><td>{html.escape(str(item.get('title')))}</td>"
        f"<td>{html.escape(str(item.get('status')))}</td><td class='reason'>{html.escape(str(item.get('status_reason')))}</td>"
        f"<td>{trace_text(item)}</td></tr>"
        for item in flagged
    )
    blocked = "".join(
        f"<li><code>{html.escape(key)}</code> {html.escape(str(endpoints.get(key, {}).get('text', ''))[:160])}</li>"
        for key in counts.get("blockedEndpoints") or []
    )
    title = html.escape(f"{model.get('study_id', '')} TLF plan")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>{STYLE}</style></head><body>
<h1>{title}</h1>
<p class="meta">{counts.get('tables', 0)} tables · {counts.get('listings', 0)} listings · {counts.get('figures', 0)} figures planned ·
{counts.get('flagged', 0)} flagged · {counts.get('objectives', 0)} objectives / {counts.get('endpoints', 0)} endpoints
({counts.get('unresolvedEndpoints', 0)} unresolved)</p>
{f'<h2>Resolved endpoints with no producible output</h2><ul>{blocked}</ul>' if blocked else ''}
<h2>Planned outputs</h2>
<table><tr><th>ID</th><th>Title</th><th>Priority</th><th>Analysis</th><th>Traces to</th></tr>{rows}</table>
<h2>Flagged / not currently producible</h2>
<table><tr><th>Candidate</th><th>Title</th><th>Status</th><th>Reason</th><th>Traces to</th></tr>{flagged_rows}</table>
</body></html>"""


def main() -> None:
    attempt = LOOP.count()
    result = check_plan()
    problems = result["problems"]
    PLAN_CHECK_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    routing = LOOP.route("check-plan", problems)
    if problems:
        write_result({**routing, "counts": result["counts"],
                      "summary": f"Plan gate FAILED (attempt {attempt}/{MAX_ATTEMPTS}): {len(problems)} problem(s), first: {problems[0]}"})
        return

    for name in PLAN_FILES:
        shutil.copyfile(PLAN_DIR / name, OUTPUT_DIR / name)
    model = json.loads((PLAN_DIR / STUDY_MODEL).read_text(encoding="utf-8"))
    plan = json.loads((PLAN_DIR / TLF_PLAN).read_text(encoding="utf-8"))
    counts = result["counts"]
    (OUTPUT_DIR / "tlf-plan.html").write_text(render(model, plan, counts), encoding="utf-8")
    write_result({
        **routing, "counts": counts,
        "summary": f"Plan gate passed: {counts['tables']} tables, {counts['listings']} listings, {counts['figures']} figures planned, "
                   f"{counts['flagged']} flagged; every resolved endpoint traced"
                   + (f" ({len(counts['blockedEndpoints'])} with no producible output: {', '.join(counts['blockedEndpoints'])})."
                      if counts["blockedEndpoints"] else "."),
    })


if __name__ == "__main__":
    run_main(main)
