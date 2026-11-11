# protocol-to-tfl-modular

The master: take a study from its USDM study definition and SDTM to validated
ADaM, ARD and rendered TLFs by running the team-owned sub-workflows in order.
Each child is its own run with its own reviewers and runs standalone too, so a
sponsor can adopt any single piece. (The name `protocol-to-tfl` is taken on
staging `vedha` by the old monolithic v6.)

```
plan (tlf-planning) ─► specify (analysis-specification) ─► validate-sdtm (cdisc-core-validation, sdtmig, onReject=reupload)
   ─► derive-adam (adam-core-loop: adam-derivation ⇄ CORE adamig) ─► generate (ard-tfl-generation) ─► finish ─► done
each child: run failed ─► child-failed · ended without its result (failed / not accepted) ─► stopped
generate: outcome upstream_change ─► specs-change-requested
```

| Step | Child (pinned version, staging `vedha`) | Hand-off |
|---|---|---|
| `plan` | `tlf-planning` v4 | `${triggerPayload.package}`; empty → the statistician uploads USDM, SDTM, define.xml (+ SAP) in the child |
| `specify` | `analysis-specification` v2 | `${steps.plan.output.package}` |
| `validate-sdtm` | `cdisc-core-validation` v2 | `${steps.specify.output.package}`, `standard=sdtmig`, `onReject=reupload` (corrected SDTM is uploaded inside the child) |
| `derive-adam` | `adam-core-loop` v2 | `${steps.validate-sdtm.output.package}`, `start=derive` |
| `generate` | `ard-tfl-generation` v1 | `${steps.derive-adam.output.package}` |
| `finish` | script | `manifest.json`: every deliverable with the run that produced it, and the package history |

A run-workflow step's output is `{instanceId, definitionName, status, error,
output}`, where `output` is the chosen child step's result; every child returns
`{outcome, summary, files, package}`. Versions are per namespace — bump the pins
in `workflow.json` when a child is re-registered.

## Not yet

- `upstream_change` from the TLF review stops the run (`specs-change-requested`); re-running
  `analysis-specification` with the reviewer's request is the next step.
- Protocol PDF → USDM (`protocol-digitization`); today the USDM is required.

## Test

```bash
python3 tests/test_finish.py
```
