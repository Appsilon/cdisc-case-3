"""Render the reviewable page of the USDM that passed the gate and CORE, right before the human review.

The review step shows the output of the step just before it, so the page is
built here and not in check-usdm (two steps back, behind the CORE child run).
It renders exactly the copy check-usdm published: every extracted entity with
the page and quote it came from, the arm x epoch element matrix, the criteria,
the schedule of activities as a grid, and CORE's verdict on top.

Result: { summary, counts }
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, STEP_OUTPUTS_DIR, read_input, run_main, step_output, write_result  # noqa: E402
from usdmlib import CITATIONS, USDM, code_of  # noqa: E402

STYLE = """
:root { color-scheme: light dark; --fg:#1d2433; --muted:#5b6475; --line:#d9dee7; --bg:#fff; --chip:#eef2f8; --on:#1f7a4d; }
html.dark { --fg:#e6e9ef; --muted:#9aa3b2; --line:#333a47; --bg:#14171d; --chip:#222834; --on:#5cc28f; }
body { font: 14px/1.45 system-ui, sans-serif; color: var(--fg); background: var(--bg); margin: 16px; }
h1 { font-size: 18px; margin: 0 0 4px; } h2 { font-size: 15px; margin: 22px 0 6px; }
p.meta { color: var(--muted); margin: 0 0 12px; }
table { border-collapse: collapse; width: 100%; } th, td { border-bottom: 1px solid var(--line); padding: 5px 8px; text-align: left; vertical-align: top; }
th { color: var(--muted); font-weight: 600; } .chip { background: var(--chip); border-radius: 4px; padding: 0 4px; font-size: 12px; white-space: nowrap; }
.cite { color: var(--muted); font-size: 12px; } .soa td, .soa th { text-align: center; padding: 3px 5px; } .soa td:first-child, .soa th:first-child { text-align: left; }
.on { color: var(--on); font-weight: 700; } .scroll { overflow-x: auto; }
"""


def text(value) -> str:
    return html.escape(str(value if value is not None else ""))


def decode(code) -> str:
    return text(code_of(code, "decode"))


class Page:
    def __init__(self, citations: dict):
        self.citations = citations

    def cite(self, identifier) -> str:
        citation = self.citations.get(identifier) or {}
        if not citation:
            return ""
        document = citation.get("document") or "protocol"
        label = f"p. {citation.get('page')}" if document == "protocol" else f"{document} p. {citation.get('page')}"
        return f"<span class='chip' title='{text(citation.get('quote'))}'>{text(label)}</span>"

    def table(self, header: list[str], rows: list[list[str]]) -> str:
        head = "".join(f"<th>{text(cell)}</th>" for cell in header)
        body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
        return f"<table><tr>{head}</tr>{body}</table>"


def render(document: dict, citations: dict, counts: dict, core_summary: str) -> str:
    page = Page(citations)
    version = document["study"]["versions"][0]
    design = version["studyDesigns"][0]
    titles = {decode(title.get("type")): title.get("text") for title in version.get("titles") or []}
    name = titles.get("Official Study Title") or document["study"].get("name") or "Study"

    objectives = []
    for objective in design.get("objectives") or []:
        objectives.append([text(objective.get("name")), decode(objective.get("level")), text(objective.get("text")), page.cite(objective.get("id"))])
        for endpoint in objective.get("endpoints") or []:
            objectives.append([f"&nbsp;&nbsp;↳ {text(endpoint.get('name'))}", decode(endpoint.get("level")), text(endpoint.get("text")), page.cite(endpoint.get("id"))])
    estimands = [[text(item.get("name")), text(item.get("populationSummary")), text(item.get("variableOfInterestId")),
                  "; ".join(f"{text(event.get('text'))}: {text(event.get('strategy'))}" for event in item.get("intercurrentEvents") or []),
                  page.cite(item.get("id"))] for item in design.get("estimands") or []]
    arms = [[text(arm.get("name")), decode(arm.get("type")), text(arm.get("description")), page.cite(arm.get("id"))] for arm in design.get("arms") or []]
    epochs = design.get("epochs") or []
    elements = {element.get("id"): element for element in design.get("elements") or []}
    cells = {(cell.get("armId"), cell.get("epochId")): cell for cell in design.get("studyCells") or []}
    matrix = [[text(arm.get("name"))] + [", ".join(text(elements.get(element, {}).get("name", element))
                                                  for element in (cells.get((arm.get("id"), epoch.get("id"))) or {}).get("elementIds") or [])
                                        for epoch in epochs] for arm in design.get("arms") or []]
    items = {item.get("id"): item for item in version.get("eligibilityCriterionItems") or []}
    criteria = [[text(criterion.get("identifier")), decode(criterion.get("category")),
                 text(items.get(criterion.get("criterionItemId"), {}).get("text")), page.cite(criterion.get("id"))]
                for criterion in design.get("eligibilityCriteria") or []]

    encounters = design.get("encounters") or []
    main = next((timeline for timeline in design.get("scheduleTimelines") or [] if timeline.get("mainTimeline") is True), {})
    scheduled = {}
    for instance in main.get("instances") or []:
        for activity in instance.get("activityIds") or []:
            scheduled.setdefault(activity, {})[instance.get("encounterId")] = instance.get("id")
    soa = [[f"{text(activity.get('label') or activity.get('name'))} {page.cite(activity.get('id'))}"]
           + [(f"<span class='on'>✓</span>" if encounter.get("id") in scheduled.get(activity.get("id"), {}) else "") for encounter in encounters]
           for activity in design.get("activities") or []]
    soa_header = "".join(f"<th>{text(encounter.get('label') or encounter.get('name'))}<br>{page.cite(encounter.get('id'))}</th>" for encounter in encounters)
    soa_body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in soa)

    population = design.get("population") or {}
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{text(name)}</title><style>{STYLE}</style></head><body>
<h1>{text(name)}</h1>
<p class="meta">{text(core_summary)}</p>
<p class="meta">USDM {text(document.get('usdmVersion'))} · {counts.get('objectives', 0)} objectives · {counts.get('endpoints', 0)} endpoints ·
{counts.get('estimands', 0)} estimands · {counts.get('arms', 0)} arms × {counts.get('epochs', 0)} epochs · {counts.get('inclusion', 0)} inclusion /
{counts.get('exclusion', 0)} exclusion criteria · {counts.get('encounters', 0)} encounters × {counts.get('activities', 0)} activities ·
{counts.get('citations', 0)} citations on {counts.get('citedPages', 0)} pages. Hover a page chip to read the quote.</p>
<h2>Objectives and endpoints</h2>{page.table(['Name', 'Level', 'Text', 'Source'], objectives)}
<h2>Estimands</h2>{page.table(['Name', 'Population', 'Variable of interest', 'Intercurrent events', 'Source'], estimands) if estimands else '<p class="meta">None extracted.</p>'}
<h2>Arms</h2>{page.table(['Arm', 'Type', 'Description', 'Source'], arms)}
<h2>Design: elements per arm and epoch</h2><div class="scroll">{page.table(['Arm'] + [f"{text(epoch.get('name'))} {page.cite(epoch.get('id'))}" for epoch in epochs], matrix)}</div>
<h2>Population</h2><p>{text(population.get('description') or population.get('name'))} {page.cite(population.get('id'))}</p>
{page.table(['#', 'Category', 'Criterion', 'Source'], criteria)}
<h2>Schedule of activities (main timeline)</h2>
<div class="scroll"><table class="soa"><tr><th>Activity</th>{soa_header}</tr>{soa_body}</table></div>
</body></html>"""


def main() -> None:
    step_input = read_input()
    counts = step_output(step_input, "check-usdm").get("counts") or {}
    core_summary = str((step_output(step_input, "validate-with-core").get("output") or {}).get("summary") or "")
    checked = STEP_OUTPUTS_DIR / "check-usdm"
    document = json.loads((checked / USDM).read_text(encoding="utf-8"))
    citations = json.loads((checked / CITATIONS).read_text(encoding="utf-8"))
    (OUTPUT_DIR / "usdm-review.html").write_text(render(document, citations, counts, core_summary), encoding="utf-8")
    write_result({"counts": counts, "summary": f"Review page ready: open usdm-review.html. {core_summary}"})


if __name__ == "__main__":
    run_main(main)
