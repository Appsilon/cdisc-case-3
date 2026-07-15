# CLAUDE.md — cdisc-case-3

## The TLF pipeline skills are canonical HERE (single source of truth)

`plugins/cdisc-case-3/skills/` is the **one authoritative copy** of the pipeline skills:

- `sdtm-to-adam`, `tlf-analysis-spec`, `tlf-generator`, `tlf-plan-critic`, `tlf-planner`,
  `traceability-builder` (the 6 shared with `protocol-to-tfl`) **+** `propose-skill-lesson` (the
  self-learning loop skill).

**Always edit these here**, then propagate to the mirror:

```bash
bash scripts/sync-skills-to-protocol-to-tfl.sh
```

That copies the 7 skills into `../protocol-to-tfl/plugins/protocol-to-tfl/skills/` byte-for-byte.
There must be exactly ONE version of each pipeline skill across every repo. After any skill change,
run the mirror and confirm `diff -rq` reports no differences on the 7 skills.

## Out of scope — do NOT edit or sync these
- `protocol-to-tfl` also owns 4 older, superseded skills that do **not** exist here and are **not**
  mirrored: `adam-to-tlg`, `mock-tlg-generator`, `trial-metadata-extractor`, `adam-to-teal`.
- `.claude/skills/` (`ard-authoring`, `tlf-build`, `usdm-endpoints`, `traceability-report`,
  `tlf-planner`) + `engine/` + `mcp/` are a **dead alternate implementation** — ignore them.
- The `mediforce*/apps/protocol-to-tfl` copies are an older 5-skill generation — unrelated.

## Deployment note
`src/cdisc-case-3.wd.json` fetches skills at runtime from THIS repo (`externalSkillsRepo` +
`skillsDir: plugins/cdisc-case-3/skills`), pinned by commit. After changing a skill, follow the
release pin dance (content commit → bump the `commit` pins to that SHA → commit) before registering a
new workflow version.
