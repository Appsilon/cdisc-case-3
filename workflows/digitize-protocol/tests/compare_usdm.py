"""Compare an extracted USDM with a ground-truth USDM of the same study, per entity type.

Entities are paired greedily by similarity - the best over each entity's
name / label / description / text of: difflib ratio, containment (one string
inside the other: "ADAS-Cog" in "... Cognitive Subscale (ADAS-Cog)"), and word
overlap (shared words over the shorter side's words, numbers kept so "Week 2" is
not "Week 20"); pairs below THRESHOLD stay unmatched - then reported as
matched / missing (in the truth only) / extra (in the extraction only). The
schedule of activities is compared through those pairs: an (activity, encounter)
cell of the extraction counts when both ends matched a truth entity that is
scheduled together on the truth's main timeline.

  python3 tests/compare_usdm.py <extracted usdm.json> <truth usdm.json> [--json]
"""

from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

THRESHOLD = 0.6
CONTAINED = 0.9
PLACEHOLDER = re.compile(r"to be determined", re.IGNORECASE)


def clean(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9][a-z0-9+\-]*", text) if len(word) >= 3 or word.isdigit()}


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    shorter, longer = sorted((left, right), key=len)
    contained = CONTAINED if len(shorter) >= 3 and shorter in longer else 0.0
    left_words, right_words = words(left), words(right)
    overlap = len(left_words & right_words) / min(len(left_words), len(right_words)) if left_words and right_words else 0.0
    return max(SequenceMatcher(None, left, right).ratio(), contained, overlap)


def texts(item: dict, *fields: str) -> tuple[str, ...]:
    return tuple(clean(item.get(field)) for field in fields if clean(item.get(field)))


def design_of(document: dict) -> tuple[dict, dict]:
    version = document["study"]["versions"][0]
    return version, version["studyDesigns"][0]


def entities(document: dict) -> dict[str, list[tuple[str, tuple[str, ...]]]]:
    """Entity type -> [(id, texts compared)]."""
    version, design = design_of(document)
    items = {item["id"]: item for item in version.get("eligibilityCriterionItems") or []}
    objectives = design.get("objectives") or []
    names = ("name", "label", "description")

    def criteria(code: str) -> list[tuple[str, tuple[str, ...]]]:
        return [(criterion["id"], texts(items.get(criterion.get("criterionItemId")) or {}, "text"))
                for criterion in design.get("eligibilityCriteria") or [] if (criterion.get("category") or {}).get("code") == code]

    return {
        "objectives": [(item["id"], texts(item, "text")) for item in objectives],
        "endpoints": [(endpoint["id"], texts(endpoint, "text", "name")) for item in objectives for endpoint in item.get("endpoints") or []
                      if PLACEHOLDER.search(str(endpoint.get("text") or "")) is None],
        "estimands": [(item["id"], texts(item, "populationSummary", "name")) for item in design.get("estimands") or []],
        "arms": [(item["id"], texts(item, "name", "label")) for item in design.get("arms") or []],
        "epochs": [(item["id"], texts(item, *names)) for item in design.get("epochs") or []],
        "inclusion": criteria("C25532"),
        "exclusion": criteria("C25370"),
        "encounters": [(item["id"], texts(item, *names)) for item in design.get("encounters") or []],
        "activities": [(item["id"], texts(item, "name", "label")) for item in design.get("activities") or []],
    }


def schedule(document: dict) -> set[tuple[str, str]]:
    _version, design = design_of(document)
    main = next((timeline for timeline in design.get("scheduleTimelines") or [] if timeline.get("mainTimeline") is True), {})
    return {(activity, instance.get("encounterId")) for instance in main.get("instances") or [] for activity in instance.get("activityIds") or []}


def pair(extracted: list[tuple[str, tuple[str, ...]]], truth: list[tuple[str, tuple[str, ...]]]) -> dict[str, str]:
    """Greedy best-first pairing: extracted id -> truth id."""
    scored = sorted(((max((similarity(left_text, right_text) for left_text in left_texts for right_text in right_texts), default=0.0), left, right)
                     for left, left_texts in extracted for right, right_texts in truth), reverse=True)
    pairs: dict[str, str] = {}
    used: set[str] = set()
    for score, left, right in scored:
        if score < THRESHOLD:
            break
        if left not in pairs and right not in used:
            pairs[left] = right
            used.add(right)
    return pairs


def compare(extracted_document: dict, truth_document: dict) -> dict:
    extracted, truth = entities(extracted_document), entities(truth_document)
    report: dict[str, dict] = {}
    mapping: dict[str, str] = {}
    for kind in truth:
        pairs = pair(extracted[kind], truth[kind])
        mapping.update(pairs)
        report[kind] = {"truth": len(truth[kind]), "extracted": len(extracted[kind]), "matched": len(pairs),
                        "missing": len(truth[kind]) - len(pairs), "extra": len(extracted[kind]) - len(pairs)}
    truth_cells = schedule(truth_document)
    mapped = {(mapping.get(activity), mapping.get(encounter)) for activity, encounter in schedule(extracted_document)}
    comparable = {cell for cell in mapped if None not in cell}
    correct = comparable & truth_cells
    report["schedule"] = {"truth": len(truth_cells), "extracted": len(schedule(extracted_document)), "matched": len(correct),
                          "precision": round(len(correct) / len(comparable), 3) if comparable else None,
                          "recall": round(len(correct) / len(truth_cells), 3) if truth_cells else None}
    return report


def main() -> None:
    arguments = [argument for argument in sys.argv[1:] if argument != "--json"]
    if len(arguments) != 2:
        sys.exit(__doc__)
    report = compare(*(json.loads(Path(argument).read_text(encoding="utf-8")) for argument in arguments))
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
        return
    print(f"{'entity':<12} {'truth':>6} {'extracted':>9} {'matched':>8} {'missing':>8} {'extra':>6}")
    for kind, row in report.items():
        if kind == "schedule":
            print(f"{'schedule':<12} {row['truth']:>6} {row['extracted']:>9} {row['matched']:>8}   precision {row['precision']}  recall {row['recall']}")
        else:
            print(f"{kind:<12} {row['truth']:>6} {row['extracted']:>9} {row['matched']:>8} {row['missing']:>8} {row['extra']:>6}")


if __name__ == "__main__":
    main()
