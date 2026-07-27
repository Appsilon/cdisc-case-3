# =============================================================================
# CDISC Case 3 agent image  (full USDM -> TLF pipeline)
#
# Extends mediforce-golden-image (R + tidyverse + Python + Claude Code) with the
# R stack the six pipeline skills need at run time:
#   - ADaM derivation:   admiral, admiraldev, metacore, metatools
#   - ARD (numbers):      cards, cardx  (+ emmeans, mmrm, survival, broom.helpers)
#   - display:            gtsummary, gt, tfrmt, rtables, rlistings, ggsurvfit, ggplot2
#   - data plumbing:      dplyr, tidyr, haven, jsonlite
#   - Python:             pyyaml (skills + step scripts)
# plus the deterministic step script (open_skill_pr.py). No study data is bundled —
# the USDM + SDTM datasets are uploaded together at the Upload inputs step each run.
#
# NOTE: `siera` is deliberately NOT installed. The ARS-native CRAN package's back
# end is not production-grade; the tlf-generator skill drafts analysis R directly
# on cards/cardx + emmeans instead (see its generation-idioms reference).
#
# Skills are NOT baked in — they are read at run time from the repo via the
# workflow's externalSkillsRepo + skillsDir. Only the R/Python packages, the
# step scripts, and the fixtures need to be in the image.
#
# Build by hand (needs mediforce-golden-image):
#   docker build -t mediforce-agent:cdisc-case-3 .
#
# Build commands are kept QUIET on purpose: the platform builds with
# execSync(stdio:'pipe') and Node's 1MB maxBuffer; a chatty build overflows it
# and the build is killed.
# =============================================================================

FROM mediforce-golden-image

# --- ADaM derivation stack ---
RUN install2.r --error --skipinstalled \
      admiral admiraldev metacore metatools > /dev/null 2>&1

# --- ARD (numbers) + models ---
RUN install2.r --error --skipinstalled \
      cards cardx emmeans mmrm survival broom broom.helpers > /dev/null 2>&1

# --- Display / rendering ---
RUN install2.r --error --skipinstalled \
      gtsummary gt tfrmt rtables rlistings ggsurvfit ggplot2 > /dev/null 2>&1

# --- Data plumbing (+ dataset IO for CORE: datasetjson reads Dataset-JSON,
#     xportr/haven write XPT v5 that CDISC CORE ingests) ---
RUN install2.r --error --skipinstalled \
      dplyr tidyr haven jsonlite datasetjson xportr > /dev/null 2>&1

# --- Python deps for the step scripts / skills ---
#   pyyaml       skills + step scripts
#   jsonschema   validate_ars.py — ARS LDM schema gate
RUN pip install --no-cache-dir --break-system-packages \
      pyyaml jsonschema > /dev/null 2>&1

# --- CDISC CORE: cdisc-rules-engine (same proven pattern as cdisc-case-1) ---
# Shallow clone of a release tag (history-free) so the build completes on a cold
# builder; the tag ships the OFFLINE resources/cache, so CORE runs with NO CDISC
# Library API key and no network at run time. Exposed as the `core` command; the
# wrapper cd's into the engine dir so `-ca resources/cache` (relative) resolves.
ARG CORE_ENGINE_REF=v0.16.0
RUN git clone --depth 1 --branch "${CORE_ENGINE_REF}" --quiet https://github.com/cdisc-org/cdisc-rules-engine.git /app/cdisc-rules-engine \
 && pip install --quiet --no-input --no-cache-dir --break-system-packages -r /app/cdisc-rules-engine/requirements.txt > /dev/null 2>&1
RUN printf '#!/bin/bash\ncd /app/cdisc-rules-engine && exec python3 core.py "$@"\n' > /usr/local/bin/core \
 && chmod +x /usr/local/bin/core

# --- Deterministic step scripts + baked-in schemas ---
#   container/ carries build_traceability.py, open_skill_pr.py, validate_ars.py,
#   generate_define.py, validate_core.py, and schemas/ars_ldm.schema.json.
COPY container/ /app/container/

WORKDIR /workspace
