# protocol-to-tfl-modular

The master: take a study from its USDM study definition and SDTM to validated
ADaM, ARD and rendered TLFs by running the team-owned sub-workflows in order.
Each child is its own run with its own reviewers and runs standalone too, so a
sponsor can adopt any single piece. (The name `protocol-to-tfl` is taken on
staging `vedha` by the old monolithic v6.)

```
plan (tlf-planning) ─► validate-sdtm (cdisc-core-validation, sdtmig, onReject=reupload) ─► route-spec ─► specify (analysis-specification)
   ─► derive-adam (adam-core-loop: adam-derivation ⇄ CORE adamig) ─► generate (ard-tfl-generation) ─► finish ─► done
generate: outcome upstream_change ─► route-spec ─► specify (with the reviewer's request) ─► derive-adam ─► generate   (≤ 2 rounds)
route-spec: a third spec-change request ─► specs-change-requested
each child: run failed ─► child-failed · ended without its result (failed / not accepted) ─► stopped
```

The SDTM is validated before specification, so a spec-change round does not
repeat CORE SDTMIG validation (nor its human dispositions): the SDTM has not
changed. Replacing the specs drops the ADaM, ARD and TLFs derived from them
from the package (`mfpkg.DOWNSTREAM`), so the round re-derives and re-validates
the ADaM, then regenerates the TLFs.

| Step | Child (pinned version, staging `vedha`) | Hand-off |
|---|---|---|
| `plan` | `tlf-planning` v4 | `${triggerPayload.package}`; empty → the statistician uploads USDM, SDTM, define.xml (+ SAP) in the child |
| `validate-sdtm` | `cdisc-core-validation` v3 | `${steps.plan.output.package}`, `standard=sdtmig`, `onReject=reupload` (corrected SDTM is uploaded inside the child) |
| `route-spec` | script | First pass: validate-sdtm's package, no request. After `upstream_change`: generate's package and its `request`; a third request → `specs-change-requested`. |
| `specify` | `analysis-specification` v4 | `${steps.route-spec.package}`, `request` = `${steps.route-spec.request}` (the child revises its previous specs when set) |
| `derive-adam` | `adam-core-loop` v3 | `${steps.specify.output.package}`, `start=derive` |
| `generate` | `ard-tfl-generation` v4 | `${steps.derive-adam.output.package}` |
| `finish` | script | `manifest.json`: every deliverable with the run that produced it, and the package history |

A run-workflow step's output is `{instanceId, definitionName, status, error,
output}`, where `output` is the chosen child step's result; every child returns
`{outcome, summary, files, package}`. Versions are per namespace — bump the pins
in `workflow.json` when a child is re-registered.

## Not yet

- Protocol PDF → USDM (`protocol-digitization`); today the USDM is required.

## Test

```bash
python3 tests/test_finish.py
python3 tests/test_route_spec.py
```
