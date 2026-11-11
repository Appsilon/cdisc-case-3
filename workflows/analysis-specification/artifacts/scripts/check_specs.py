"""Deterministic gate over the three spec files, and the reviewable rendering of them.

Runs the speclib checks (ARS schema + references, one analysis per planned
output, variables present in the ADaM spec, the ADaM spec contract). On failure
the problems go to /workspace/analysis-specification/feedback.json and the
specs return to the agent while attempts remain (three per review round). On
pass it publishes the specs and specs.html - per output the population, record
subset, variables and methods, and per ADaM dataset what feeds it and who
consumes it - for the statistician's review.

Result: { needsFix, retry, attempt, problems, counts, summary }
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, StepFailure, run_main, write_result  # noqa: E402
from gate import MAX_ATTEMPTS  # noqa: E402
from speclib import ADAM_SPEC, ANALYSIS_SPEC, LOOP, SPEC_FILES, SPECS_DIR, check_specs  # noqa: E402

STYLE = """
:root { color-scheme: light dark; --fg:#1d2433; --muted:#5b6475; --line:#d9dee7; --bg:#fff; --chip:#eef2f8; }
html.dark { --fg:#e6e9ef; --muted:#9aa3b2; --line:#333a47; --bg:#14171d; --chip:#222834; }
body { font: 14px/1.45 system-ui, sans-serif; color: var(--fg); background: var(--bg); margin: 16px; }
h1 { font-size: 18px; margin: 0 0 4px; } h2 { font-size: 15px; margin: 20px 0 6px; } p.meta { color: var(--muted); margin: 0 0 12px; }
table { border-collapse: collapse; width: 100%; } th, td { border-bottom: 1px solid var(--line); padding: 5px 8px; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; } code, .chip { background: var(--chip); border-radius: 4px; padding: 0 4px; font-size: 12px; }
"""


def chips(values) -> str:
    return " ".join(f"<span class='chip'>{html.escape(str(value))}</span>" for value in values if value)


def render(entries: list[dict], spec: dict, counts: dict) -> str:
    rows = "".join(
        f"<tr><td><code>{html.escape(str(entry.get('table_id')))}</code></td><td>{html.escape(str(entry.get('title', '')))}</td>"
        f"<td>{html.escape(str((entry.get('analysisSet') or {}).get('condition', '')))}</td>"
        f"<td><code>{html.escape(str((entry.get('dataSubset') or {}).get('dataset', '')))}</code> "
        f"{html.escape(str((entry.get('dataSubset') or {}).get('condition', '')))}</td>"
        f"<td>{chips((role or {}).get('variable') if isinstance(role, dict) else role for role in (entry.get('analysisVariables') or {}).values())}</td>"
        f"<td>{chips(method.get('type') or method.get('id') for method in entry.get('methods') or [] if isinstance(method, dict))}</td></tr>"
        for entry in sorted(entries, key=lambda item: str(item.get("table_id")))
    )
    datasets = "".join(
        f"<tr><td><code>{html.escape(str(item.get('name')))}</code></td><td>{html.escape(str(item.get('class')))}</td>"
        f"<td>{chips(item.get('sdtm_source') or [])}</td>"
        f"<td>{chips(parameter.get('paramcd') for parameter in item.get('parameters') or [] if isinstance(parameter, dict))}</td>"
        f"<td>{len(item.get('variables') or [])}</td><td>{chips(item.get('used_by_tables') or [])}</td></tr>"
        for item in spec.get("datasets") or []
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Analysis specification</title><style>{STYLE}</style></head><body>
<h1>Analysis specification</h1>
<p class="meta">{counts['analyses']} analyses for {counts['plannedOutputs']} planned outputs · {len(counts['datasets'])} ADaM datasets ·
{counts['variables']} variables · ARS ReportingEvent schema-valid with {counts['arsAnalyses']} analyses</p>
<h2>Analyses</h2>
<table><tr><th>Output</th><th>Title</th><th>Analysis set</th><th>Records</th><th>Variables</th><th>Methods</th></tr>{rows}</table>
<h2>ADaM datasets</h2>
<table><tr><th>Dataset</th><th>Class</th><th>SDTM source</th><th>Parameters</th><th>Variables</th><th>Used by</th></tr>{datasets}</table>
</body></html>"""


def main() -> None:
    attempt = LOOP.count()
    try:
        result = check_specs()
    except RuntimeError as error:
        raise StepFailure(str(error)) from error
    problems = result["problems"]
    routing = LOOP.route("check-specs", problems)
    if problems:
        write_result({**routing, "counts": result["counts"],
                      "summary": f"Spec gate FAILED (attempt {attempt}/{MAX_ATTEMPTS}): {len(problems)} problem(s), first: {problems[0]}"})
        return

    for name in SPEC_FILES:
        shutil.copyfile(SPECS_DIR / name, OUTPUT_DIR / name)
    entries = json.loads((SPECS_DIR / ANALYSIS_SPEC).read_text(encoding="utf-8"))
    spec = json.loads((SPECS_DIR / ADAM_SPEC).read_text(encoding="utf-8"))
    counts = result["counts"]
    (OUTPUT_DIR / "specs.html").write_text(render(entries, spec, counts), encoding="utf-8")
    write_result({
        **routing, "counts": counts,
        "summary": f"Spec gate passed: {counts['analyses']} analyses, ADaM spec of {', '.join(counts['datasets'])} "
                   f"({counts['variables']} variables), ARS ReportingEvent schema-valid.",
    })


if __name__ == "__main__":
    run_main(main)
