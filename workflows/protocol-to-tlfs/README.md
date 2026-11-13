# protocol-to-tlfs

The master: take a study from its protocol (or its USDM study definition) and
SDTM to validated ADaM, ARD and rendered TLFs by running the team-owned
sub-workflows in order.
Each child is its own run with its own reviewers and runs standalone too, so a
sponsor can adopt any single piece. Registered in prod namespace `clinical-workflows` (pins in `pins/prod-clinical-workflows.json`); first end-to-end run on the real CDISC pilot: `a48c3201` (2026-11-13, under the pre-rename step ids).

Each step that runs a sub-workflow has that sub-workflow's name as its id and its title as its label.

```
route-input ─protocol, no usdm─► digitize-protocol ─► route-input ─► plan-tlfs
            ─usdm, or empty─► plan-tlfs
plan-tlfs ─► validate-with-core (sdtmig, onReject=reupload) ─► route-spec ─► specify-analyses
   ─► derive-and-validate-adam (derive-adam ⇄ validate-with-core adamig) ─► generate-ard-tlfs ─► collect-deliverables ─► finish ─► done
generate-ard-tlfs: outcome upstream_change ─► route-spec ─► specify-analyses (with the reviewer's request) ─► derive-and-validate-adam ─► generate-ard-tlfs   (≤ 2 rounds)
route-spec: a third spec-change request ─► specs-change-requested
each child: run failed ─► child-failed · ended without its result (failed / not accepted) ─► stopped
plan-tlfs: outcome data-mismatch (the SDTM is not the USDM's study, or cannot answer any primary endpoint of an objective) ─► data-mismatch
```

The SDTM is validated before specification, so a spec-change round does not
repeat CORE SDTMIG validation (nor its human dispositions): the SDTM has not
changed. Replacing the specs drops the ADaM, ARD and TLFs derived from them
from the package (`mfpkg.DOWNSTREAM`), so the round re-derives and re-validates
the ADaM, then regenerates the TLFs.

| Step | Child (pinned version: staging `vedha` / prod `appsilon`) | Hand-off |
|---|---|---|
| `route-input` | script | Package with a `usdm` → `plan-tlfs`; with a `protocol` but no `usdm` → `digitize-protocol`, then back here with digitize-protocol's package → `plan-tlfs`; empty → `plan-tlfs` (uploads happen there). |
| `digitize-protocol` | `digitize-protocol` v3 / v1 | `${steps.route-input.package}`; protocol PDF → USDM 4.0 with page citations, gated, CORE-validated (usdm 4-0), approved by the clinical scientist |
| `plan-tlfs` | `plan-tlfs` v4 / v1 | `${steps.route-input.package}`; empty → the statistician uploads USDM, SDTM, define.xml (+ SAP) in the child |
| `validate-with-core` | `validate-with-core` v3 / v3 | `${steps.plan-tlfs.output.package}`, `standard=sdtmig`, `onReject=reupload` (corrected SDTM is uploaded inside the child) |
| `route-spec` | script | First pass: validate-with-core's package, no request. After `upstream_change`: generate-ard-tlfs's package and its `request`; a third request → `specs-change-requested`. |
| `specify-analyses` | `specify-analyses` v4 / v1 | `${steps.route-spec.package}`, `request` = `${steps.route-spec.request}` (the child revises its previous specs when set) |
| `derive-and-validate-adam` | `derive-and-validate-adam` v3 / v1 | `${steps.specify-analyses.output.package}`, `start=derive` |
| `generate-ard-tlfs` | `generate-ard-tlfs` v4 / v1 | `${steps.derive-and-validate-adam.output.package}` |
| `collect-deliverables` | script | Lifts the files worth opening out of generate-ard-tlfs's package into top-level `files` (the runtime downloads only those), each tagged `showAs`: `tlf-viewer.html`, `reconciliation.json`, `accuracy.json` (big-N and recompute gates), `data-check-sdtm-vs-protocol.html` (plan-tlfs's `study-check.html`), `usdm-review.html`, `tlf-plan.html`, `specs.html`, `core-report-<usdm\|sdtmig\|adamig>.html`, `adam-define.xml` |
| `finish` | script | Copies those files, sha256-verified, into its `/output` — the master run shows the TLF viewer and review pages directly; `manifest.json`: every file of the package with the run that produced it, and the package history |

A run-workflow step's output is `{instanceId, definitionName, status, error,
output}`, where `output` is the chosen child step's result; every child returns
`{outcome, summary, files, package}`. Versions are per namespace — bump the pins
in `workflow.json` when a child is re-registered.

## Not yet

- Parallel branches; QC double programming.

## Test

```bash
python3 tests/test_finish.py
python3 tests/test_route_input.py
python3 tests/test_route_spec.py
```
