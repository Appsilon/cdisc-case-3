#!/usr/bin/env python3
"""Derive trace_graph.json from the ARS Reporting Event + the study USDM.

Produces the node/edge model the visualization renders, across six CDISC layers:

    Objective (USDM) -> Endpoint (USDM) -> Output/TFL (ARS)
      -> Analysis (ARS) -> Method (ARS) -> ADaM dataset

The ARS half (Output -> Analysis -> Method -> dataset) is extracted verbatim from
the Reporting Event. The USDM half (Objective -> Endpoint) comes from the study
definition; Endpoint -> Output is a curated semantic mapping (EP2OUT below),
because this ARS instance is the Common Safety Displays subset and does not carry
USDM endpoint ids. Endpoints with no matching output surface as traceability gaps.

Usage:
    python build_graph.py \
        --ars ../fixtures/reporting_event.json \
        --usdm /path/to/CDISC_Pilot_Study.json \
        --out trace_graph.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Curated endpoint -> ARS output links (semantic; see module docstring).
EP2OUT = {
    "Endpoint_1": ["Out14-3-01"],                                  # ADAS-Cog Wk24 -> ANCOVA
    "Endpoint_3": ["Out14-3-1-1", "Out14-3-2-1", "Out14-KM-01"],   # AE -> overall, SOC/PT, TTE
    "Endpoint_4": ["Out14-3-3-1a", "Out14-3-3-1b"],                # Vital signs
}
POP_CONTEXT_OUT = "Out14-1-1"  # demographics = population context for the AE endpoint
STANDARD = {"Out14-1-1", "Out14-3-1-1", "Out14-3-2-1", "Out14-3-3-1a", "Out14-3-3-1b"}
DSLABEL = {"ADSL": "Subject-Level Analysis", "ADAE": "Adverse Events Analysis",
           "ADVS": "Vital Signs Analysis", "ADQSADAS": "ADAS-Cog Questionnaire",
           "ADTTE": "Time-to-Event Analysis"}
SDTM = {"ADSL": "DM", "ADAE": "AE", "ADVS": "VS", "ADQSADAS": "QS", "ADTTE": "AE / DS (derived)"}
BAD, APOS = "�", "’"


def txt(o):
    return (o.get("text") or o.get("description") or o.get("name") or "").replace(BAD, APOS)


def walk(node, cur, acc):
    if isinstance(node, dict):
        if "outputId" in node:
            cur = node["outputId"]
        if "analysisId" in node and cur:
            acc.setdefault(cur, []).append(node["analysisId"])
        for v in node.values():
            walk(v, cur, acc)
    elif isinstance(node, list):
        for v in node:
            walk(v, cur, acc)


def build(ars, usdm):
    dd = usdm["study"]["versions"][0]["studyDesigns"][0]
    methods = {m["id"]: m for m in ars.get("methods", [])}
    sets = {s["id"]: s for s in ars.get("analysisSets", [])}
    subsets = {s["id"]: s for s in ars.get("dataSubsets", [])}
    groups = {g["id"]: g for g in ars.get("analysisGroupings", [])}
    analyses = {a["id"]: a for a in ars.get("analyses", [])}
    outputs = {o["id"]: o for o in ars.get("outputs", [])}

    out2an = {}
    walk(ars["mainListOfContents"], None, out2an)
    for k in out2an:
        seen = set()
        out2an[k] = [x for x in out2an[k] if not (x in seen or seen.add(x))]
    out2an.setdefault("Out14-3-01", ["AnEff01_ADAS_Wk24_ANCOVA"])
    out2an.setdefault("Out14-KM-01", ["AnEff02_TTE_KM"])

    nodes, edges, seen = [], [], set()

    def add(nid, **kw):
        if nid in seen:
            return
        seen.add(nid)
        kw["id"] = nid
        nodes.append(kw)

    def link(a, b, rel):
        edges.append({"from": a, "to": b, "rel": rel})

    for o in dd.get("objectives", []):
        oid = o["id"]
        lvl = o.get("level", {}).get("decode", "")
        add(oid, layer=0, kind="objective", label=lvl, sublabel=txt(o)[:150],
            meta={"USDM id": oid, "Level": lvl, "Text": txt(o)})
        for e in o.get("endpoints", []):
            eid = e["id"]
            et = txt(e)
            tbd = "To be determined" in et or "*** To be" in et
            add(eid, layer=1, kind="endpoint", label=e.get("level", {}).get("decode", ""),
                sublabel=("endpoint not defined in protocol" if tbd else et[:150]),
                mode=("gap" if tbd else None),
                meta={"USDM id": eid, "Level": e.get("level", {}).get("decode", ""),
                      "Text": et, "Objective": oid})
            link(oid, eid, "has endpoint")

    for oid, ans in out2an.items():
        o = outputs.get(oid, {})
        mode = "standard" if oid in STANDARD else "custom"
        dsset = sorted({analyses[a]["dataset"] for a in ans if a in analyses})
        add(oid, layer=2, kind="output", label=oid, sublabel=(o.get("name") or oid), mode=mode,
            meta={"ARS Output id": oid, "Title": o.get("name", ""),
                  "Mode": ("Standard - validated recipe" if mode == "standard"
                           else "Custom - AI-drafted program, human-reviewed"),
                  "Analyses": len(ans), "Datasets": ", ".join(dsset)})

    for ep, outs in EP2OUT.items():
        for oid in outs:
            if oid in seen:
                link(ep, oid, "evaluated by")
    if POP_CONTEXT_OUT in seen:
        link("Endpoint_3", POP_CONTEXT_OUT, "population context")

    for oid, ans in out2an.items():
        for aid in ans:
            a = analyses.get(aid)
            if not a:
                continue
            m = methods.get(a["methodId"], {})
            aset = sets.get(a.get("analysisSetId"), {})
            sub = subsets.get(a.get("dataSubsetId"), {}) if a.get("dataSubsetId") else {}
            grp = [groups.get(g["groupingId"], {}).get("name") for g in a.get("orderedGroupings", [])]
            add(aid, layer=3, kind="analysis", label=aid, sublabel=a["name"][:90],
                mode=("custom" if aid.startswith("AnEff") else "standard"),
                meta={"ARS Analysis id": aid, "Name": a["name"],
                      "Purpose": a.get("purpose", {}).get("controlledTerm", ""),
                      "Reason": a.get("reason", {}).get("controlledTerm", ""),
                      "Analysis set": aset.get("name", ""),
                      "Grouping": ", ".join([g for g in grp if g]),
                      "Data subset": sub.get("name", ""),
                      "Operates on": a["dataset"] + "." + a["variable"]})
            link(oid, aid, "comprises")
            mid = a["methodId"]
            if mid not in seen:
                ops = [op["label"] + " (" + op["name"] + ")" for op in m.get("operations", [])]
                add(mid, layer=4, kind="method", label=mid, sublabel=(m.get("label") or m.get("name", ""))[:80],
                    meta={"ARS Method id": mid, "Name": m.get("name", ""),
                          "Operations": "; ".join(ops) or "-",
                          "Has SAS codeTemplate": "yes" if m.get("codeTemplate") else "no"})
            link(aid, mid, "uses method")
            did = a["dataset"]
            if did not in seen:
                add(did, layer=5, kind="dataset", label=did, sublabel=DSLABEL.get(did, did),
                    meta={"ADaM dataset": did, "Label": DSLABEL.get(did, did),
                          "SDTM predecessor": SDTM.get(did, "")})
            link(mid, did, "reads")

    return {"nodes": nodes, "edges": edges,
            "meta": {"study": "CDISCPILOT01", "ars": ars.get("name"), "arms": 3,
                     "layers": ["Objective", "Endpoint", "Output / TFL", "Analysis",
                                "Method", "ADaM dataset"]}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ars", default=str(HERE.parent / "fixtures" / "reporting_event.json"))
    ap.add_argument("--usdm", required=True, help="path to the study USDM JSON (CDISC_Pilot_Study.json)")
    ap.add_argument("--out", default=str(HERE / "trace_graph.json"))
    a = ap.parse_args()
    ars = json.loads(Path(a.ars).read_text(encoding="utf-8"))
    usdm = json.loads(Path(a.usdm).read_text(encoding="utf-8"))
    graph = build(ars, usdm)
    Path(a.out).write_text(json.dumps(graph, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {a.out}: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")


if __name__ == "__main__":
    main()
