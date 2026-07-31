# -*- coding: utf-8 -*-
"""Assemble the traceability graph model from the pipeline artifacts on disk."""
import json, os, re

ROOT = "/Users/vedha/Repo/FULL_WORKFLOW"
P    = os.path.join(ROOT, "outputs", "tlf-plan")
TLF  = os.path.join(ROOT, "outputs", "tlf")
SDTM = os.path.join(ROOT, "inputs", "sdtm")
OUT  = os.path.join(ROOT, "outputs", "traceability")
os.makedirs(OUT, exist_ok=True)

SM   = json.load(open(os.path.join(P, "study-model.json")))
PLAN = json.load(open(os.path.join(P, "tlf-plan.json")))
ASPEC= json.load(open(os.path.join(P, "analysis-spec.json")))
ADSP = json.load(open(os.path.join(P, "adam-spec.json")))
aspec_by_tid = {}
for e in ASPEC:
    key = e["id"][3:] if e["id"].startswith(("AN-L-", "AN-F-")) else "T-" + e["table_id"]
    aspec_by_tid[key] = e

sdtm_present = sorted({f[:-4].upper() for f in os.listdir(SDTM) if f.endswith(".xpt")})
SDTM_LABELS = {
 "AE":"Adverse Events","CM":"Concomitant Medications","DD":"Death Details","DI":"Device Identifiers",
 "DM":"Demographics","DS":"Disposition","EC":"Exposure as Collected","EX":"Exposure",
 "FA":"Findings About (injection-site reactions)","FT":"Functional Tests (AVLT-REY)",
 "IE":"Inclusion/Exclusion Exceptions","LB":"Laboratory Test Results","MH":"Medical History",
 "OE":"Ophthalmic Examinations","QS":"Questionnaires","QSPH":"Questionnaires — PHQ-9",
 "QSSL":"Questionnaires — SWLS","RELREC":"Related Records","RS":"Disease Response (HAMD 17)",
 "SE":"Subject Elements","SUPPDM":"Supplemental DM","SUPPEC":"Supplemental EC","SV":"Subject Visits",
 "TA":"Trial Arms","TE":"Trial Elements","TI":"Trial Inclusion/Exclusion","TS":"Trial Summary",
 "TV":"Trial Visits","VS":"Vital Signs","DV":"Protocol Deviations",
}
CATLAB = {"disposition":"Disposition / Populations","demographics":"Demographics & Baseline",
 "efficacy":"Efficacy","exposure":"Drug Exposure","safety-ae":"Adverse Events",
 "safety-lab":"Laboratory","safety-vs":"Vital Signs","conmeds":"Concomitant Medications",
 "pro":"Patient-Reported","pk":"Pharmacokinetics","other":"Other"}

def short_tp(tps):
    if not tps: return None
    f = lambda t: re.sub(r"^Week\s*", "Wk", str(t))
    return " / ".join(f(t) for t in tps)
def trunc(s, n=64):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n-1].rstrip() + "…"

nodes, edges, issues = [], [], []
def N(**kw): nodes.append(kw); return kw
def E(s, t, kind, dashed=False, rule=None):
    edges.append({"source": s, "target": t, "kind": kind, "dashed": dashed, "rule": rule})

# ---------------- tier 0/1: objectives + endpoints -------------------------
ep_by_id = {e["id"]: e for e in SM["endpoints"]}
for o in SM["objectives"]:
    measures = [ep_by_id[i]["parsed"].get("measure") for i in o["endpoint_ids"]
                if i in ep_by_id and ep_by_id[i].get("parsed")]
    measures = [m for m in measures if m]
    sub = " & ".join(dict.fromkeys(measures)) if measures else trunc(o.get("text"), 46)
    N(id="obj:"+o["id"], type="Objective", tier=0, label=o["name"],
      sublabel=trunc(sub, 30) or o["level"], title=o.get("text") or o["name"],
      status=None, unresolved=False, absent=False, isFigure=False,
      meta={"level": o["level"], "source": o.get("source", "USDM"),
            "description": o.get("description"), "text": o.get("text"),
            "endpoints": o["endpoint_ids"]})
for e in SM["endpoints"]:
    pa = e.get("parsed") or {}
    if e["resolved"] and pa.get("measure"):
        sub = pa["measure"] + (" · " + short_tp(pa.get("timepoints")) if pa.get("timepoints") else "")
    elif not e["resolved"]:
        sub = "unresolved — to be determined"
    else:
        sub = trunc(e.get("text"), 40)
    N(id="end:"+e["id"], type="Endpoint", tier=1, label=e["name"],
      sublabel=trunc(sub, 30), title=e.get("text") or e["name"], status=None,
      unresolved=not e["resolved"], absent=False, isFigure=False,
      meta={"level": e["level"], "source": e.get("source", "USDM"), "text": e.get("text"),
            "objective": e.get("objective_id"), "resolved": e["resolved"],
            "measure": pa.get("measure"), "measure_type": pa.get("measure_type"),
            "timepoints": pa.get("timepoints") or [], "domain_hint": pa.get("domain_hint")})
    E("obj:"+e["objective_id"], "end:"+e["id"], "obj-end")
    if not e["resolved"]:
        issues.append({"severity": "clarification", "nodeId": "end:"+e["id"],
            "relatedNodeIds": ["obj:"+e["objective_id"]],
            "message": "Endpoint %s (%s) is unresolved: its protocol text is the placeholder \"%s\". "
                       "No output can be planned until it is defined."
                       % (e["name"], e["id"], (e.get("text") or "").strip())})

N(id="reg:ICHE3", type="Regulatory", tier=1, label="ICH E3", sublabel="ICH E3",
  title="ICH E3 — Structure and Content of Clinical Study Reports", status=None,
  unresolved=False, absent=False, isFigure=False,
  meta={"standard": "ICH E3",
        "note": "Objective-independent regulatory scaffolding: displays mandated by reporting "
                "convention rather than by any study objective."})

# ---------------- tier 4: SDTM ---------------------------------------------
needed = set()
for ds in ADSP["datasets"]: needed |= set(ds["sdtm_source"])
for c in PLAN: needed |= set(c["data_requirements"]["sdtm_source"])
for d in sorted(needed | set(sdtm_present)):
    absent = d not in sdtm_present and d != "QS"
    if d == "QS": continue
    N(id="sdtm:"+d, type="SDTM", tier=4, label=d,
      sublabel=trunc(SDTM_LABELS.get(d, d), 30), title=SDTM_LABELS.get(d, d), status=None,
      unresolved=False, absent=absent, isFigure=False,
      meta={"domain": d, "label": SDTM_LABELS.get(d, d), "absent": absent,
            "present_in_inventory": d in sdtm_present})

# ---------------- tier 3: ADaM ---------------------------------------------
adam_names = set()
for ds in ADSP["datasets"]:
    nm = ds["name"]; adam_names.add(nm)
    vars_ = []
    for v in ds["variables"]:
        src = v.get("source", "") or ""
        doms = [d for d in ds["sdtm_source"] if re.search(r"\b%s\b" % re.escape(d), src)]
        if not doms and src.startswith("ADSL"): doms = ["*ADSL*"]
        if not doms: doms = ds["sdtm_source"] if src and not src.startswith("derived") else []
        vars_.append({"name": v["name"], "role": v.get("role", ""),
                      "source": src, "source_domains": doms})
    N(id="adam:"+nm, type="ADaM", tier=3, label=nm, sublabel=ds["class"],
      title="%s — %s (%s)" % (nm, ds["class"], ", ".join(ds["sdtm_source"])), status=None,
      unresolved=False, absent=False, isFigure=False,
      meta={"klass": ds["class"], "sdtm_source": ds["sdtm_source"],
            "used_by_tables": ds.get("used_by_tables", []),
            "derivation_requirements": [r["name"] for r in ds.get("derivation_requirements", [])],
            "parameters": [{"paramcd": p.get("paramcd"), "param": p.get("param"),
                            "note": p.get("note")} for p in ds.get("parameters", [])],
            "variables": vars_, "notes": ds.get("notes", [])})
    for d in ds["sdtm_source"]:
        if any(n["id"] == "sdtm:"+d for n in nodes): E("adam:"+nm, "sdtm:"+d, "adam-sdtm")

# used_by_tables -> tlf id map (authoritative TLF->ADaM edges)
adam_for_tid = {}
for ds in ADSP["datasets"]:
    for t in ds.get("used_by_tables", []):
        adam_for_tid.setdefault(t, set()).add(ds["name"])

# ---------------- tier 2: TLF ----------------------------------------------
def dir_id(c):
    f = c.get("final_id")
    return f if f else None
status_tally = {"generated": 0, "blocked": 0, "needs-clarification": 0}
for c in PLAN:
    did = dir_id(c)
    d = os.path.join(TLF, did) if did else None
    md = ard = gr = None; grpath = None
    if d and os.path.isdir(d):
        mdf = os.path.join(d, "%s.generated.md" % did)
        if os.path.exists(mdf): md = open(mdf).read()
        af = os.path.join(d, "ard.json")
        if os.path.exists(af): ard = open(af).read()
        rf = os.path.join(d, "generate.R")
        if os.path.exists(rf):
            gr = open(rf).read(); grpath = "outputs/tlf/%s/generate.R" % did
    st = "generated" if md else c["status"]
    if st == "planned": st = "blocked"
    status_tally[st] = status_tally.get(st, 0) + 1
    tid = "tlf:" + c["candidate_id"]
    sp = aspec_by_tid.get(did) if did else None
    a = c["analysis"]
    N(id=tid, type="TLF", tier=2, label=did or "—",
      sublabel=trunc(c["title"], 30), title=c["title"], status=st,
      unresolved=(st == "needs-clarification"), absent=False,
      isFigure=(c["type"] == "Figure"),
      meta={"candidate_id": c["candidate_id"], "final_id": c.get("final_id"), "dir_id": did,
            "type": c["type"], "category": c["category"],
            "cat_label": CATLAB.get(c["category"], c["category"]),
            "title": c["title"], "status": st, "status_reason": c.get("status_reason"),
            "priority": c["priority"], "produced_by": c["produced_by"], "notes": c.get("notes", []),
            "method": a["method"], "population": a["population"], "timepoint": a["timepoint"],
            "imputation": a["imputation"], "subgroup": a["subgroup"], "comparison": a["comparison"],
            "objectives": c["traces_to"]["objective_ids"], "endpoints": c["traces_to"]["endpoint_ids"],
            "regulatory_rule": c["traces_to"]["regulatory_rule"],
            "adam": c["data_requirements"]["adam"], "sdtm": c["data_requirements"]["sdtm_source"],
            "analysisSet": sp["analysisSet"]["label"] if sp else None,
            "analysisSetCond": sp["analysisSet"]["condition"] if sp else None,
            "dataSubset": sp["dataSubset"]["condition"] if sp else None,
            "purpose": sp["purpose"] if sp else None,
            "generatedMd": md, "ardJson": ard, "generateR": gr, "generateRPath": grpath,
            "isFigure": c["type"] == "Figure",
            "figurePng": ("outputs/tlf/%s/%s.png" % (did, did))
                         if did and os.path.exists(os.path.join(TLF, did, "%s.png" % did)) else None})
    for oid in c["traces_to"]["objective_ids"]:
        if any(n["id"] == "obj:"+oid for n in nodes): E("obj:"+oid, tid, "obj-tlf")
    for eid in c["traces_to"]["endpoint_ids"]:
        if any(n["id"] == "end:"+eid for n in nodes): E("end:"+eid, tid, "end-tlf")
    if c["traces_to"]["regulatory_rule"]:
        E("reg:ICHE3", tid, "reg-tlf", rule=c["traces_to"]["regulatory_rule"])
    # TLF -> ADaM: adam-spec used_by_tables is authoritative; fall back to the plan
    linked = adam_for_tid.get(did, set()) if did else set()
    if not linked: linked = {x for x in c["data_requirements"]["adam"] if x in adam_names}
    for nm in sorted(linked): E(tid, "adam:"+nm, "tlf-adam")
    # dashed TLF -> SDTM for domains declared but not bridged by a derived ADaM
    bridged = set()
    for nm in linked:
        bridged |= set(next(x for x in ADSP["datasets"] if x["name"] == nm)["sdtm_source"])
    for dm in c["data_requirements"]["sdtm_source"]:
        if dm not in bridged and any(n["id"] == "sdtm:"+dm for n in nodes):
            E(tid, "sdtm:"+dm, "tlf-sdtm", dashed=True)
    # issues
    if st == "blocked":
        rel = ["sdtm:"+dm for dm in c["data_requirements"]["sdtm_source"]
               if any(n["id"] == "sdtm:"+dm and n["absent"] for n in nodes)]
        issues.append({"severity": "blocked", "nodeId": tid, "relatedNodeIds": rel,
                       "message": c.get("status_reason") or "Blocked; no reason recorded."})
    elif st == "needs-clarification":
        issues.append({"severity": "clarification", "nodeId": tid, "relatedNodeIds": [],
                       "message": c.get("status_reason") or "Needs clarification."})

# Drop SDTM domains that no ADaM dataset and no TLF actually consumes: they are in
# the delivered inventory but feed nothing, and 11 unconnected nodes would just be
# clutter. Record them as an info issue so the omission is visible, not silent.
deg = {n["id"]: 0 for n in nodes}
for e in edges: deg[e["source"]] += 1; deg[e["target"]] += 1
unused = [n for n in nodes if n["type"] == "SDTM" and deg[n["id"]] == 0 and not n["absent"]]
if unused:
    nodes[:] = [n for n in nodes if n not in unused]
    issues.append({"severity": "info", "nodeId": None, "relatedNodeIds": [],
        "message": "%d SDTM domain(s) present in inputs/sdtm/ feed no ADaM dataset and no planned "
                   "display, so they are omitted from the graph: %s. Trial-design and "
                   "administrative domains are expected here; OE (ophthalmic examinations, 285 "
                   "records) is real collected data with no planned output."
                   % (len(unused), ", ".join(sorted(n["label"] for n in unused)))})

# absent-domain issues
for n in nodes:
    if n["type"] == "SDTM" and n["absent"]:
        blocked_by = [c["title"] for c in PLAN if n["meta"]["domain"] in c["data_requirements"]["sdtm_source"]]
        issues.append({"severity": "blocked", "nodeId": n["id"], "relatedNodeIds": [],
            "message": "SDTM domain %s (%s) is absent from the delivered inventory. It blocks: %s."
                       % (n["meta"]["domain"], n["meta"]["label"],
                          "; ".join(blocked_by) if blocked_by else "no planned output")})

# coverage gaps
has_generated = set()
for e in edges:
    if e["kind"] in ("end-tlf", "obj-tlf"):
        t = next(n for n in nodes if n["id"] == e["target"])
        if t["status"] == "generated": has_generated.add(e["source"])
for n in nodes:
    if n["type"] == "Endpoint" and not n["unresolved"] and n["id"] not in has_generated:
        issues.append({"severity": "gap", "nodeId": n["id"], "relatedNodeIds": [],
            "message": "Resolved endpoint %s (%s) has no generated output — every display tracing to "
                       "it is blocked. Coverage gap." % (n["label"], n["meta"].get("measure") or "—")})
    if n["type"] == "Objective":
        eps = ["end:"+i for i in n["meta"]["endpoints"]]
        if n["id"] not in has_generated and not any(x in has_generated for x in eps):
            allun = all(next(m for m in nodes if m["id"] == x)["unresolved"] for x in eps) if eps else False
            issues.append({"severity": "clarification" if allun else "gap", "nodeId": n["id"],
                "relatedNodeIds": eps,
                "message": "Objective %s has no generated output. %s"
                           % (n["label"], "All of its endpoints are unresolved."
                              if allun else "Its endpoints resolve, but every downstream display is blocked.")})

# map a display id (T-14-3.01) back to its node id so info lines are clickable
did2node = {n["meta"]["dir_id"]: n["id"] for n in nodes
            if n["type"] == "TLF" and n["meta"].get("dir_id")}

# info issues from the generator + ADaM runs
for src, tag in ((os.path.join(TLF, "issues.md"), "TLF generation"),
                 (os.path.join(ROOT, "outputs", "adam", "issues.md"), "ADaM derivation")):
    if os.path.exists(src):
        for ln in open(src):
            m = re.match(r"^\|\s*(?:#\s*\|\s*)?", ln)
            if ln.startswith("| ") and ln.count("|") >= 4 and "---" not in ln and "Severity" not in ln \
               and "Issue |" not in ln and "Flag |" not in ln and "Correction |" not in ln \
               and "Assumption |" not in ln and "Gap |" not in ln:
                cells = [c.strip() for c in ln.strip().strip("|").split("|")]
                if len(cells) >= 2 and cells[0] and not cells[0].startswith("**"):
                    nid = did2node.get(cells[0])
                    issues.append({"severity": "info", "nodeId": nid, "relatedNodeIds": [],
                        "message": "[%s] %s" % (tag, " — ".join(c for c in cells if c)[:400])})

sev_rank = {"blocked": 0, "clarification": 1, "gap": 2, "info": 3}
issues.sort(key=lambda i: (sev_rank.get(i["severity"], 9), i.get("nodeId") or "zz"))

G = {
 "study": {"id": SM["study_id"], "name": SM["study_name"], "title": SM["title"], "phase": SM["phase"]},
 "counts": {
   "objectives": sum(1 for n in nodes if n["type"] == "Objective"),
   "endpoints": sum(1 for n in nodes if n["type"] == "Endpoint"),
   "endpoints_unresolved": sum(1 for n in nodes if n["type"] == "Endpoint" and n["unresolved"]),
   "sdtm": sum(1 for n in nodes if n["type"] == "SDTM"),
   "sdtm_absent": sum(1 for n in nodes if n["type"] == "SDTM" and n["absent"]),
   "adam": sum(1 for n in nodes if n["type"] == "ADaM"),
   "tlf": sum(1 for n in nodes if n["type"] == "TLF"),
   "tlf_producible": status_tally.get("generated", 0)},
 "status": status_tally,
 "issues": issues, "nodes": nodes, "edges": edges,
}
json.dump(G, open(os.path.join(OUT, "graph.json"), "w"), indent=1, ensure_ascii=False)
print("nodes", len(nodes), "edges", len(edges), "issues", len(issues))
print("counts", G["counts"]); print("status", status_tally)
print("by type", {t: sum(1 for n in nodes if n["type"] == t)
                  for t in ["Objective","Endpoint","Regulatory","TLF","ADaM","SDTM"]})
