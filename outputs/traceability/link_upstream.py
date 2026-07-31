# -*- coding: utf-8 -*-
"""Link the upstream code in variable-lineage.html at COLUMN level.

The explorer already attaches the right upstream code blocks to each ADaM
variable, but it never says *why* they are there: every upstream step ships with
`hi: []`, so nothing is highlighted and the reader has to re-derive the join
themselves. For ADSL.HEIGHTBL that leaves two questions unanswered:

  * `rename(HEIGHTBL = HEIGHT)` is highlighted — but where does `HEIGHT` come
    from? It is not an SDTM variable. It is manufactured at line 58 by
    `pivot_wider(names_from = VSTESTCD, values_from = VSSTRESN)`, which turns
    each *value* of VSTESTCD into a column name.
  * `vsbl` is shown as an upstream step — but how does it reach `adsl`? Via the
    `left_join(vsbl, by = "USUBJID")` on line 59.

This script walks each variable's step chain backwards, carrying the set of
column names currently being tracked, and records per step:

  hi     — the lines that actually produce/carry a tracked column
  track  — the column names this step is being read for
  origin — how the tracked column comes into being here (pivot / rename / ...)
  note   — one plain sentence naming the mechanism
  via    — {line, code, how} : where this frame is consumed by the step below it

It rewrites the embedded DATA JSON in place and reports coverage. Nothing is
invented: a step that cannot be resolved keeps `hi: []` and gets no note, and
the tail of the run prints how many of those remain.
"""
import json, os, re, sys
from collections import OrderedDict

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "variable-lineage.html")

# dplyr/tidyr verbs and R builtins that are never column names
VERBS = set("""
if_else case_when ifelse mutate transmute filter select rename group_by ungroup
summarise summarize arrange distinct slice_max slice_min left_join inner_join
full_join right_join anti_join semi_join bind_rows bind_cols pivot_wider
pivot_longer coalesce na_if replace_na row_number n first last min max sum mean
sd median quantile round as Date as.Date as.numeric as.character as.integer
unname names c is.na paste paste0 sprintf nchar substr toupper tolower trimws
grepl gsub sub sort unique rev head tail seq rep which nrow length any all
across everything starts_with ends_with contains matches TRUE FALSE NA NULL
NA_character_ NA_real_ NA_integer_ Inf function return stopifnot vapply sapply
lapply do.call setNames rowwise cur_group_id desc read_sdtm read_adam by
with_ties names_from values_from values_fn n_distinct abs sqrt log exp floor
ceiling trunc pmax pmin cumsum tibble data frame rbind cbind list nesting
""".split())

IDENT = re.compile(r"\.?[A-Za-z._][A-Za-z0-9._]*")
JOINS = ("left_join", "inner_join", "full_join", "right_join",
         "anti_join", "semi_join", "bind_rows", "bind_cols")


def idents(expr):
    """Column-ish identifiers in an R expression.

    Leading-dot names are kept: `.dosed` and friends are real dplyr scratch
    columns and are exactly the link between a helper frame and the flag that
    reads it (ADSL.SAFFL reads `.dosed`).
    """
    expr = re.sub(r"%[a-zA-Z+*/]+%", " ", expr)   # %in%, %>% are operators, not columns
    expr = re.sub(r"\b\d+[Li]\b", " ", expr)      # 0L / 1i are literals, not the column `L`
    out = []
    for m in IDENT.finditer(re.sub(r'"[^"]*"', '""', expr)):
        t = m.group()
        if t in VERBS or t.isdigit() or t in (".", ".."):
            continue
        # drop function calls: NAME(
        if expr[m.end():m.end() + 1] == "(":
            continue
        out.append(t)
    return list(OrderedDict.fromkeys(out))


def strings(text):
    return set(re.findall(r'"([^"]+)"', text))


def rename_pairs(text):
    """rename(NEW = OLD, ...) -> {NEW: OLD}. Also covers transmute(NEW = OLD)."""
    out = {}
    for m in re.finditer(r"\brename\s*\(([^)]*)\)", text):
        for part in m.group(1).split(","):
            if "=" in part:
                new, old = part.split("=", 1)
                new, old = new.strip(), old.strip()
                if IDENT.fullmatch(new) and IDENT.fullmatch(old):
                    out[new] = old
    return out


def step_lines(st):
    """[(absolute_line_no, text), ...] for a step."""
    return [(st["s"] + k, L) for k, L in enumerate(st["code"].split("\n"))]


def assigns_on(line, names):
    """Does this line assign to any of `names`?  NAME = ... / NAME <- ..."""
    hit = []
    for nm in names:
        if re.search(r"(?<![A-Za-z0-9._])%s\s*(?:=(?!=)|<-)" % re.escape(nm), line):
            hit.append(nm)
    return hit


def mentions(line, names):
    return [nm for nm in names
            if re.search(r"(?<![A-Za-z0-9._])%s(?![A-Za-z0-9._])" % re.escape(nm), line)]


def rhs_of(line, name):
    """Right-hand side of `name = expr` / `name <- expr` on this line."""
    m = re.search(r"(?<![A-Za-z0-9._])%s\s*(?:=(?!=)|<-)\s*(.*)$" % re.escape(name), line)
    return m.group(1) if m else ""


def plural(names):
    """(joined, is/are, column/columns) for a set of names."""
    j = "`" + "`, `".join(sorted(names)) + "`"
    return (j, "are" if len(names) > 1 else "is", "columns" if len(names) > 1 else "a column")


def resolve_step(st, track, downstream, frames=(), known=None, const=None):
    """Annotate one upstream step. Returns the track set for the next hop.

    Only the tracked names this step actually accounts for are carried onward.
    Threading the whole speculative set made ADSL.SAFFL claim that `.dosed` and
    `ITTFL` come from SDTM EX — `.dosed` is invented one frame later and `ITTFL`
    is derived elsewhere in the program entirely. A name this step does not
    touch is dropped from the chain rather than repeated as fact.
    """
    lines = step_lines(st)
    body = st["code"]
    hi, note, origin, nxt = [], None, None, None
    matched = set()

    # ── 1. pivot_wider manufactures the column from a *value* of names_from ──
    piv = [(no, L) for no, L in lines if "pivot_wider" in L]
    if piv and (track & strings(body)):
        made = sorted(track & strings(body))
        pno, pline = piv[0]
        m = re.search(r"names_from\s*=\s*([A-Za-z._][A-Za-z0-9._]*)", body)
        v = re.search(r"values_from\s*=\s*([A-Za-z._][A-Za-z0-9._]*)", body)
        k_col, v_col = (m.group(1) if m else None), (v.group(1) if v else None)
        hi = [pno] + [no for no, L in lines if strings(L) & set(made)]
        origin, matched = "pivot", set(made)
        j, isare, coln = plural(made)
        note = ("%s %s not %s in the source data — %s %s created here: pivot_wider() "
                "turns each value of %s into a column of its own, with %s as the "
                "value." % (j, isare, coln, "they" if len(made) > 1 else "it", isare,
                            k_col or "names_from", v_col or "values_from"))
        nxt = {c for c in (k_col, v_col) if c}
        # the filter that names the literal is part of the story
        nxt |= set(idents(" ".join(L for no, L in lines if "filter" in L)))

    # ── 2. plain assignment / rename of a tracked column ────────────────────
    if not hi:
        ren = rename_pairs(body)
        carried = {ren[n] for n in track if n in ren}
        for no, L in lines:
            got = assigns_on(L, track) or (mentions(L, set(ren)) if carried else [])
            if got:
                hi.append(no)
                matched |= set(got)
        if hi:
            origin = "rename" if carried else "assign"
            nxt = set(carried)
            for no, L in lines:
                if no in hi:
                    for nm in assigns_on(L, track):
                        nxt |= set(idents(rhs_of(L, nm)))
            nxt -= matched
            if not nxt:
                # assigned from a constant (`.dosed = TRUE`): what this frame
                # really contributes upstream are the keys it is built on.
                keys = set()
                for no, L in lines:
                    keys |= set(idents(re.sub(r"(?:=(?!=)|<-)[^,)]*", "", L)))
                nxt = {k for k in keys if k not in matched and k not in frames}
            if carried:
                j, _, _ = plural(carried)
                note = "carried in under its source name %s." % j

    # ── 3. the column is merely selected / passed through ───────────────────
    if not hi:
        for no, L in lines:
            got = mentions(L, track)
            if got:
                hi.append(no)
                matched |= set(got)
        if hi:
            origin = "carry"
            nxt = set(matched)

    # ── 4. the frame is read straight from SDTM / a prior ADaM here ─────────
    dom = st.get("srcDomain") or ""
    where = ("the already-built ADaM dataset %s" % dom.lstrip("@")
             if dom.startswith("@") else "SDTM %s" % dom)
    if not hi and dom:
        rd = [no for no, L in lines if "read_sdtm" in L or "read_adam" in L]
        if rd:
            hi, origin = rd[:1], "adam" if dom.startswith("@") else "sdtm"
            # Only claim the names this source actually contains. Without the
            # check, ADFTAVLT.PARAMCD — a constant "AVLATOT" — was reported as
            # coming from SDTM FT, which has no PARAMCD at all.
            if known is not None:
                track = {t for t in track if t in known}
            if track:
                j, isare, _ = plural(track)
                note = ("`%s` is read straight from %s here, so %s %s not derived "
                        "in this program — %s arrive%s already built."
                        % (st.get("frame") or "the frame", where, j, isare,
                           "they" if len(track) > 1 else "it",
                           "" if len(track) > 1 else "s"))
            else:
                note = ("`%s` is read from %s here. It supplies the rows this frame "
                        "is built on, not a named column of its own."
                        % (st.get("frame") or "the frame", where))
    elif dom and origin in ("carry", "assign") and matched:
        j, isare, _ = plural(matched)
        note = "%s %s read from %s here." % (j, isare, where)

    # ── 5. the frame contributes rows, not this column's value ──────────────
    if not hi and st.get("frame"):
        hi, origin = [st["s"]], "rows"
        if const:
            note = ("`%s` is a constant assigned at line %s. `%s` supplies the rows "
                    "it is attached to, not its value."
                    % (const[0], const[1], st["frame"]))
        else:
            j, _, _ = plural(track) if track else ("this variable", "", "")
            note = ("No column of `%s` resolves to %s — it feeds the step above "
                    "(grouping, filtering or parameters) rather than carrying this "
                    "variable's value." % (st["frame"], j))

    st["hi"] = sorted(set(hi))
    # report only what this step actually accounts for
    st["track"] = sorted(matched or (track if origin in ("sdtm", "adam") else set()))
    if origin:
        st["origin"] = origin
    if note:
        st["note"] = note

    # ── how this frame reaches the step below it ────────────────────────────
    frame = st.get("frame")
    if frame and downstream is not None and downstream is not st:
        for no, L in step_lines(downstream):
            # a line inside this step's own range is not a handoff, it is the
            # step talking about itself (duplicate steps made `prev` overlap)
            if st["s"] <= no <= st["e"]:
                continue
            if re.search(r"(?<![A-Za-z0-9._])%s(?![A-Za-z0-9._])" % re.escape(frame), L):
                how = next((j for j in JOINS if j + "(" in L.replace(" ", "")
                            or j in L), None)
                st["via"] = {"line": no, "code": L.strip(),
                             "how": how or ("piped into `%s`" % (
                                 downstream.get("frame") or downstream["region"]))}
                break

    return (nxt or track)


def close_within(st, names, depth=6):
    """Resolve tracked names against assignments *inside the same step*.

    A step is a pipeline, not one line: ADFTAVLT.AVAL reads `.sum` and `NTRIALS`
    on line 84, but both are manufactured by the summarise() on line 80 out of
    FTSTRESN. Without walking that hop the chain hands `.sum` to the upstream
    frame, which has never heard of it, and the step resolves to nothing.

    Returns (resolved_names, extra_hi_lines).
    """
    lines = step_lines(st)
    cur, extra = set(names), set()
    for _ in range(depth):
        nxt, moved = set(), False
        for nm in cur:
            src = set()
            for no, L in lines:
                if assigns_on(L, [nm]):
                    src |= set(idents(rhs_of(L, nm)))
                    extra.add(no)
            if src:
                nxt |= {s for s in src if s != nm}
                moved = True
            else:
                nxt.add(nm)
        cur = nxt
        if not moved:
            break
    return cur, extra


def seed_track(v, prim):
    """Columns the primary step reads in order to produce this variable.

    Two hops matter here, and missing the second is what left ADSL.BMIBL
    unlinked: line 61 reads `WEIGHTBL`/`HEIGHTBL`, but those names only exist
    *after* the rename on line 60. Upstream the columns are `WEIGHT`/`HEIGHT`,
    so the seed has to be pushed back through the step's own rename() before
    the frame chain is walked.
    """
    if prim is None:
        return {v["name"]}
    body, name = prim["code"], v["name"]
    ren = rename_pairs(body)
    if name in ren:                       # rename(HEIGHTBL = HEIGHT)
        return {ren[name]}
    got = set()
    for no, L in step_lines(prim):
        if no in (prim.get("hi") or []) or assigns_on(L, [name]):
            got |= set(idents(rhs_of(L, name)))
    got = got or {name}
    # push the seed back through any rename in the same step, then resolve any
    # name that the step itself manufactures a few lines earlier
    got = {ren.get(c, c) for c in got}
    got, extra = close_within(prim, got)
    if extra:
        prim["hi"] = sorted(set(prim.get("hi") or []) | extra)
    return {ren.get(c, c) for c in got}



# ── ref provenance ──────────────────────────────────────────────────────────
# `refs` mixes two very different claims under one look: a column the CODE
# actually reads, and a column the SPEC declared that the code never touches.
# ADSL.TRTEDT showed EX.EXENDTC (spec) and DM.RFXENDTC (code) side by side as
# equals, so the reader could not tell that the program ignores the spec's
# source. Worse, some "code" refs come only from a cat()/sprintf() progress
# line, which reads nothing at all.
DIAG = re.compile(r"\b(?:cat|sprintf|message|print|warning|stopifnot|paste0?)\s*\(")


def code_lines_for(prog, col):
    """(real_reads, diagnostic_only_mentions) line counts for a column."""
    real = diag = 0
    pat = re.compile(r"(?<![A-Za-z0-9._])%s(?![A-Za-z0-9._])" % re.escape(col))
    for L in (prog or "").split("\n"):
        if not pat.search(L):
            continue
        stripped = L.strip()
        if stripped.startswith("#"):
            continue
        if DIAG.search(L):
            diag += 1
        else:
            real += 1
    return real, diag


def classify_refs(D):
    """Tag every ref with how we actually know about it, and flag real
    spec-vs-code divergence. Returns (dropped, mismatches)."""
    dropped, mism = [], []
    for v in D["vars"]:
        prog = D["programs"].get(D["dsProgram"].get(v["ds"], ""), "")
        keep = []
        for r in (v.get("refs") or []):
            col = r["ref"].split(".", 1)[-1]
            real, diag = code_lines_for(prog, col)
            r.pop("diagOnly", None)
            if r.get("src") == "code" and real == 0 and diag > 0:
                # Mentioned only in a progress/reconciliation line, so the code
                # does not read it. Marked rather than deleted: dropping it made
                # the count vanish on the next run and lost the audit trail.
                r["diagOnly"] = True
                dropped.append((v["id"], r["ref"]))
            if r.get("src") == "spec" and real > 0:
                # the spec's column IS read; the extractor just missed it
                # (ADAE.AEDECOD is recoded from itself on one line)
                r["src"], r["n"] = "code", max(r.get("n") or 0, real)
            r["reads"] = real
            keep.append(r)
        v["refs"] = keep
        spec = {r["ref"] for r in keep if r.get("src") == "spec" and not r.get("diagOnly")}
        code = {r["ref"] for r in keep if r.get("src") == "code" and not r.get("diagOnly")}
        if spec and code:
            v["specMismatch"] = {"spec": sorted(spec), "code": sorted(code),
                                 "specSource": v.get("specSource")}
            mism.append((v["id"], sorted(spec), sorted(code)))
        else:
            v.pop("specMismatch", None)
    return dropped, mism


def main():
    src = open(HTML, encoding="utf-8").read()
    m = re.search(r'(<script id="DATA" type="application/json">)(.*?)(</script>)', src, re.S)
    D = json.loads(m.group(2))

    # Idempotence: stash each step's original `hi` on first run and reset every
    # derived key, so re-running never compounds a previous pass's output.
    for v in D["vars"]:
        for st in (v.get("steps") or []):
            if "hi0" not in st:
                st["hi0"] = list(st.get("hi") or [])
            st["hi"] = list(st["hi0"])
            for k in ("track", "origin", "note", "via"):
                st.pop(k, None)

    FRAMES = {st.get("frame") for v in D["vars"] for st in (v.get("steps") or [])
              if st.get("frame")}
    DOMVARS = {k: {x["name"] for x in (d.get("vars") or [])} for k, d in D["domains"].items()}

    def known_for(st):
        dm = (st.get("srcDomain") or "").lstrip("@")
        return DOMVARS.get(dm)

    def const_for(v, prims):
        """(name, line) if the variable is assigned a bare literal."""
        for pz in prims:
            for no, L in step_lines(pz):
                r = rhs_of(L, v["name"])
                if r and re.match(r'^\s*(?:"[^"]*"|-?\d+(?:\.\d+)?[Li]?)\s*[,)]?\s*$', r):
                    return (v["name"], no)
        return None
    stat = {"vars": 0, "steps": 0, "hi": 0, "via": 0, "note": 0, "unresolved": []}
    for v in D["vars"]:
        steps = v.get("steps") or []
        if not steps:
            continue
        rank = {"primary": 0, "copy": 1, "reshape": 1, "helper": 2, "upstream": 3}
        chain = sorted(steps, key=lambda s: rank.get(s["kind"], 4))
        prims = [s for s in chain if s["kind"] in ("primary", "copy", "reshape")]
        prim = prims[0] if prims else None
        ups = [s for s in chain if s["kind"] not in ("primary", "copy", "reshape")]
        if not ups:
            continue
        stat["vars"] += 1
        seed = set()
        for pz in (prims or [None]):
            got = seed_track(v, pz)
            seed |= got
            if pz is not None:
                pz["track"] = sorted(got)

        # Only frame-bearing steps form a real chain (adsl <- vsbl <- vs), so the
        # tracked columns are threaded through those. Helper functions are
        # *alternative producers* of the same column, not hops in one chain —
        # threading through them made add_locf() look for window_by_day()'s
        # locals and resolve nothing. Each helper is matched against the seed.
        track, prev = set(seed), prim
        for st in ups:
            stat["steps"] += 1
            chained = bool(st.get("frame"))
            use = set(track) if chained else set(seed)
            nxt = resolve_step(st, use, prev if chained else prim, FRAMES,
                               known_for(st), const_for(v, prims))
            if not st["hi"] and chained and use != seed:
                # the frame may be a sibling rather than a hop: retry on the seed
                nxt2 = resolve_step(st, set(seed), prev, FRAMES,
                                    known_for(st), const_for(v, prims))
                if st["hi"]:
                    nxt = nxt2
            if chained:
                track, prev = nxt, st
            if st["hi"]:
                stat["hi"] += 1
            else:
                stat["unresolved"].append("%s @ %s:%s" % (v["id"], st["file"], st["s"]))
            if st.get("via"):
                stat["via"] += 1
            if st.get("note"):
                stat["note"] += 1

    dropped, mism = classify_refs(D)

    out = m.group(1) + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + m.group(3)
    open(HTML, "w", encoding="utf-8").write(src[:m.start()] + out + src[m.end():])

    print("variables with an upstream chain : %d" % stat["vars"])
    print("upstream steps                   : %d" % stat["steps"])
    print("  with a highlighted line        : %d" % stat["hi"])
    print("  with a handoff (via)           : %d" % stat["via"])
    print("  with a mechanism note          : %d" % stat["note"])
    print("  UNRESOLVED (left blank)        : %d" % len(stat["unresolved"]))
    for u in stat["unresolved"][:12]:
        print("      -", u)
    if len(stat["unresolved"]) > 12:
        print("      ... and %d more" % (len(stat["unresolved"]) - 12))

    print()
    print("refs flagged as log-line-only, hidden from \"comes from\": %d" % len(dropped))
    for vid, rf in dropped[:10]:
        print("      -", vid, rf)
    if len(dropped) > 10:
        print("      ... and %d more" % (len(dropped) - 10))
    print("SPEC vs CODE divergence (spec names a source the code never reads): %d" % len(mism))
    for vid, sp, cd in mism:
        print("      - %-18s spec %s  vs  code %s" % (vid, sp, cd))


if __name__ == "__main__":
    main()
