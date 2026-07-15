# cdisc-case-3 — USDM → traceable TFLs (full pipeline)

A Mediforce workflow for the CDISC AI Innovation Challenge, **Use Case 3:
AI-Driven Tables, Figures, and Listings (TFL) Generation** — now the **full
protocol-to-TFL pipeline**. Given a study's **USDM** metadata (and its **SDTM**
datasets) it plans the required TFLs, builds the analysis + ADaM specs, derives
ADaM, generates the **ARD** (numbers) and rendered **TFLs** (display), and
assembles an interactive **objective → endpoint → SDTM → ADaM → TFL**
traceability explorer.

**Thesis:** *plan from the objectives, generate from the spec, prove with the
numbers.* Accuracy is measured cell-by-cell against known-good CSR outputs; every
TFL traces back through the ARD to the ADaM, SDTM, endpoint, and objective that
justify it. Three human review gates (plan, specs, TFLs) each feed a
**self-learning skill-refinement loop**: reviewer feedback is distilled into
durable, per-skill lessons and opened as a PR, so the skills improve over time.

## Pipeline (14 steps)

| # | Step | Executor | Skill / script | Output |
|---|------|----------|----------------|--------|
| 1 | upload-usdm | human | — | upload the study's USDM JSON (→ `/data/` for plan-tlfs) |
| 2 | plan-tlfs | agent | `tlf-planner` | study-model.json, tlf-plan.json, tlf-index.md |
| 3 | audit-plan | agent | `tlf-plan-critic` | coverage-report.md + verdict |
| 4 | **review-plan** | human review | — | approve → specs · revise → plan |
| 5 | build-specs | agent | `tlf-analysis-spec` | analysis-spec.json, adam-spec.json |
| 6 | **review-specs** | human review | — | approve → SDTM upload · revise → specs |
| 7 | upload-sdtm | human | — | upload the study's SDTM datasets (→ `/data/` for derive-adam) |
| 8 | derive-adam | agent | `sdtm-to-adam` | `/workspace/adam/*` + conformance report |
| 9 | generate-tlfs | agent | `tlf-generator` | ARD + rendered TFLs |
| 10 | **review-tlfs** | human review | — | approve → trace · revise → generate |
| 11 | build-traceability | agent | `traceability-builder` | traceability.html, trace_graph.json, manifest.json |
| 12 | propose-skill-update | agent | `propose-skill-lesson` | per-skill lesson blocks |
| 13 | open-skill-pr | script | `open_skill_pr.py` | PR against main (or clean no-op) |
| 14 | done | human (terminal) | — | — |

Inputs are uploaded via two `file-upload` human steps — the **USDM** up front
(step 1) and the **SDTM** datasets later (step 7, once the specs are approved).
Each upload is made available read-only under `/data/` to the agent step that
immediately follows it; no separate staging step is needed.

Transitions include three revise loops (each review gate can send the run back
to its producing agent step).

### The self-learning skill-refinement loop (retained + generalized)

On each **Request Changes**, the producing agent step (`plan-tlfs`,
`build-specs`, `generate-tlfs`) appends the reviewer comment to
`/workspace/review_feedback.jsonl`, **tagged with its skill**. After approval,
`propose-skill-update` groups that feedback by skill and distils durable,
skill-general lessons; `open-skill-pr` appends each to the target skill's
`references/lessons-learned.md` and opens one PR against `main`. A human merges;
the next run reads the improved skills. First-pass approvals (no revisions)
produce no PR.

## Skills (in `plugins/cdisc-case-3/skills`, read at run time via `externalSkillsRepo` + `skillsDir`)

`tlf-planner`, `tlf-plan-critic`, `tlf-analysis-spec`, `sdtm-to-adam`,
`tlf-generator`, `traceability-builder`, `propose-skill-lesson`. The six pipeline
skills are ported from the `protocol-to-tfl` design; the revisable ones
(`tlf-planner`, `tlf-analysis-spec`, `tlf-generator`) each carry a
`references/lessons-learned.md` that the loop appends to.

## Environment variables & secrets

| Name | Secret | Scope | Used by | Meaning | How to set | Example |
|------|--------|-------|---------|---------|------------|---------|
| `GITHUB_TOKEN` | ✅ | workflow | all script/agent steps (Docker build context + skills fetch) and `open-skill-pr` | Token with repo read for the pinned build/skills context, plus `contents:write` + `pull-requests:write` for the skill-lesson PR | namespace/workflow secret | `ghp_…` |
| `OPENROUTER_API_KEY` | ✅ | workflow | every agent step (mapped to `ANTHROPIC_AUTH_TOKEN`, base URL `https://openrouter.ai/api`) | LLM credential for the Claude-Code agents | namespace/workflow secret | `sk-or-…` |
| `SKILL_REPO` | — | `open-skill-pr` step env | `open_skill_pr.py` | `<owner>/<repo>` the skills live in | step `env` | `vedhav/cdisc-case-3` |

Secrets are referenced via `{{SECRET_NAME}}` templates and are never committed or
baked into the image.

## Docker image

`mediforce-agent:cdisc-case-3`, built from `Dockerfile` (`FROM
mediforce-golden-image`). Adds the pinned R stack — admiral/admiraldev/metacore/
metatools (ADaM); cards/cardx/emmeans/mmrm/survival/broom.helpers (ARD + models);
gtsummary/gt/tfrmt/rtables/rlistings/ggsurvfit/ggplot2 (display); dplyr/tidyr/
haven/jsonlite — plus Python `pyyaml`, the step scripts (`container/`), and the
bundled CDISCPILOT01 reference (`fixtures/`). Skills are **not** baked in. Build:
`docker build -t mediforce-agent:cdisc-case-3 .`.

## Output contract (`/output`)

`study-model.json`, `tlf-plan.json`, `tlf-index.md`, `coverage-report.md`,
`analysis-spec.json`, `adam-spec.json`, the ARD + rendered TFLs,
`traceability.html`, `trace_graph.json`, `manifest.json`, and each
step's `result.json`.

## Inputs (uploaded per run — nothing bundled)

Two upload steps, each feeding the agent step that follows it (read-only `/data/`):
- **`upload-usdm`** (step 1) — the study's **USDM** study-definition JSON (required).
- **`upload-sdtm`** (step 7, after the specs are approved) — the study's **SDTM**
  datasets (required; `.xpt` / Dataset-JSON / `.csv` / `.sas7bdat`).

The pipeline runs against any new study's USDM + SDTM. A known-good reference for
smoke-testing is the **CDISCPILOT01** (H2Q-MC-LZZT Alzheimer's) USDM + SDTM,
produced/held upstream (Case 1/Case 2 and the `protocol-to-tfl` source).

## Runtime source pinning

`externalSkillsRepo.commit` and every step's `script.commit` / `agent.commit`
are pinned to a single repo commit (updated on each release via the two-step pin
dance: push, read HEAD, rewrite the pins to that SHA, push again). The four repo
fields are kept distinct: `source` (import provenance, n/a here), `externalSkillsRepo`
(runtime skills), step `agent.repo`/`script.repo` (Docker build context), and
`workspace.remote` (unused).

## Registration

Import/register a new workflow version for every released change
(`mediforce workflow validate` then register). See `src/cdisc-case-3.wd.json`.
