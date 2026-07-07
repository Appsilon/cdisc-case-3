#!/usr/bin/env python3
"""Derive the trace-graph model (nodes + edges) rendered by the visualization.

Six CDISC layers, left->right from intent to provenance:

    Objective (USDM) -> Endpoint (USDM) -> Output/TFL (ARS)
      -> Analysis (ARS) -> Method (ARS) -> ADaM dataset

The ARS half (Output -> Analysis -> Method -> dataset) is extracted verbatim from
the Reporting Event. The USDM half (Objective -> Endpoint) comes from the study
definition; Endpoint -> Output is a curated semantic mapping, because this ARS
instance (Common Safety Displays) carries no USDM endpoint ids. Endpoints with no
matching output surface as traceability gaps.

`graph()` is the shared builder used by both this standalone script and the
container's build_trace.py (which passes run status to annotate each output).

Usage (standalone, regenerate trace_graph.json from source):
    python build_graph.py --usdm /path/to/CDISC_Pilot_Study.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Curated endpoint -> ARS output links for the bundled CDISCPILOT01 reference.
EP2OUT = {
    "Endpoint_1": ["Out14-3-01"],                                  # ADAS-Cog Wk24 -> ANCOVA
    "Endpoint_3": ["Out14-3-1-1", "Out14-3-2-1", "Out14-KM-01"],   # AE -> overall, SOC/PT, TTE
    "Endpoint_4": ["Out14-3-3-1a", "Out14-3-3-1b"],                # Vital signs
}
POP_CONTEXT = {"Endpoint_3": "Out14-1-1"}  # demographics = population context for the AE endpoint
STANDARD = {"Out14-1-1", "Out14-3-1-1", "Out14-3-2-1", "Out14-3-3-1a", "Out14-3-3-1b"}
DSLABEL = {"ADSL": "Subject-Level Analysis", "ADAE": "Adverse Events Analysis",
           "ADVS": "Vital Signs Analysis", "ADQSADAS": "ADAS-Cog Questionnaire",
           "ADTTE": "Time-to-Event Analysis"}
SDTM = {"ADSL": "DM", "ADAE": "AE", "ADVS": "VS", "ADQSADAS": "QS", "ADTTE": "AE / DS (derived)"}
def _txt(o):
    # normalise the U+FFFD replacement char that the source USDM uses for apostrophes
    return (o.get("text") or o.get("description") or o.get("name") or "").replace("�", "’")


def _walk(node, cur, acc):
    if isinstance(node, dict):
        if "outputId" in node:
            cur = node["outputId"]
        if "analysisId" in node and cur:
            acc.setdefault(cur, []).append(node["analysisId"])
        for v in node.values():
            _walk(v, cur, acc)
    elif isinstance(node, list):
        for v in node:
            _walk(v, cur, acc)


def objectives_from_usdm(usdm):
    """Flatten a full USDM study into the simplified objective/endpoint shape."""
    dd = usdm["study"]["versions"][0]["studyDesigns"][0]
    objs = []
    for o in dd.get("objectives", []):
        eps = [{"id": e["id"], "level": e.get("level", {}).get("decode", ""), "text": _txt(e)}
               for e in o.get("endpoints", [])]
        objs.append({"id": o["id"], "level": o.get("level", {}).get("decode", ""),
                     "text": _txt(o), "endpoints": eps})
    return objs


def graph(ars, objectives=None, ep2out=None, pop_context=None, run=None):
    """Build {nodes, edges, meta}.

    objectives  simplified [{id, level, text, endpoints:[{id, level, text}]}] (USDM half; may be [])
    ep2out      {endpointId: [outputId, ...]} curated links
    run         optional {outputId: {mode, rendered, ardRows, repairs}} run annotations
    """
    objectives = objectives or []
    ep2out = ep2out or {}
    pop_context = pop_context or {}
    run = run or {}

    methods = {m["id"]: m for m in ars.get("methods", [])}
    sets = {s["id"]: s for s in ars.get("analysisSets", [])}
    subsets = {s["id"]: s for s in ars.get("dataSubsets", [])}
    groups = {g["id"]: g for g in ars.get("analysisGroupings", [])}
    analyses = {a["id"]: a for a in ars.get("analyses", [])}
    outputs = {o["id"]: o for o in ars.get("outputs", [])}

    out2an = {}
    _walk(ars.get("mainListOfContents", {}), None, out2an)
    for k in out2an:
        seen = set()
        out2an[k] = [x for x in out2an[k] if not (x in seen or seen.add(x))]
    # efficacy outputs are not in the LOPA tree; link them to their authored analyses
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

    for o in objectives:
        add(o["id"], layer=0, kind="objective", label=o.get("level", ""), sublabel=o.get("text", "")[:150],
            meta={"USDM id": o["id"], "Level": o.get("level", ""), "Text": o.get("text", "")})
        for e in o.get("endpoints", []):
            et = e.get("text", "")
            tbd = "To be determined" in et or "*** To be" in et
            add(e["id"], layer=1, kind="endpoint", label=e.get("level", ""),
                sublabel=("endpoint not defined in protocol" if tbd else et[:150]),
                mode=("gap" if tbd else None),
                meta={"USDM id": e["id"], "Level": e.get("level", ""), "Text": et, "Objective": o["id"]})
            link(o["id"], e["id"], "has endpoint")

    for oid, ans in out2an.items():
        o = outputs.get(oid, {})
        r = run.get(oid, {})
        mode = r.get("mode") or ("standard" if oid in STANDARD else "custom")
        dsset = sorted({analyses[a]["dataset"] for a in ans if a in analyses})
        meta = {"ARS Output id": oid, "Title": o.get("name", ""),
                "Mode": ("Standard - validated recipe" if mode == "standard"
                         else "Custom - AI-drafted program, human-reviewed"),
                "Analyses": len(ans), "Datasets": ", ".join(dsset)}
        if r:
            meta["Run status"] = "rendered" if r.get("rendered") else "not rendered"
            if r.get("ardRows") is not None:
                meta["ARD result rows"] = r["ardRows"]
            if r.get("repairs"):
                meta["Repairs"] = "; ".join(r["repairs"]) if isinstance(r["repairs"], list) else str(r["repairs"])
        add(oid, layer=2, kind="output", label=oid, sublabel=(o.get("name") or oid), mode=mode, meta=meta)

    for ep, outs in ep2out.items():
        for oid in outs:
            if oid in seen and ep in seen:
                link(ep, oid, "evaluated by")
    for ep, oid in pop_context.items():
        if oid in seen and ep in seen:
            link(ep, oid, "population context")

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
                add(mid, layer=4, kind="method", label=mid,
                    sublabel=(m.get("label") or m.get("name", ""))[:80],
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
    g = graph(ars, objectives_from_usdm(usdm), EP2OUT, POP_CONTEXT)
    Path(a.out).write_text(json.dumps(g, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {a.out}: {len(g['nodes'])} nodes, {len(g['edges'])} edges")


if __name__ == "__main__":
    main()
