#!/usr/bin/env bash
# Mirror the canonical CDISC Case 3 pipeline skills into the protocol-to-tfl repo.
#
# SINGLE SOURCE OF TRUTH: cdisc-case-3/plugins/cdisc-case-3/skills/
# The protocol-to-tfl copies are a byte-identical MIRROR — never edit them directly.
# Edit the canonical skill here, then run this script to propagate.
#
# Assumes cdisc-case-3 and protocol-to-tfl are sibling repos (…/repos/cdisc-case-3,
# …/repos/protocol-to-tfl). Runs on git-bash (Windows), macOS, or Linux.
#
# PowerShell equivalent (one shared skill):
#   Remove-Item -Recurse -Force <P2T>\plugins\protocol-to-tfl\skills\<skill>
#   Copy-Item -Recurse <C3>\plugins\cdisc-case-3\skills\<skill> <P2T>\plugins\protocol-to-tfl\skills\
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
C3_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
P2T_ROOT="$(cd "$C3_ROOT/../protocol-to-tfl" && pwd)"

SRC="$C3_ROOT/plugins/cdisc-case-3/skills"
DEST="$P2T_ROOT/plugins/protocol-to-tfl/skills"

# The pipeline skills kept in sync across both repos (6 shared + the loop skill).
# NOT touched: protocol-to-tfl's older, superseded skills
#   (adam-to-tlg, mock-tlg-generator, trial-metadata-extractor, adam-to-teal).
SKILLS=(sdtm-to-adam tlf-analysis-spec tlf-generator tlf-plan-critic tlf-planner traceability-builder propose-skill-lesson)

[ -d "$SRC" ]  || { echo "ERROR: canonical skills dir not found: $SRC" >&2; exit 1; }
[ -d "$DEST" ] || { echo "ERROR: mirror skills dir not found: $DEST" >&2; exit 1; }

for s in "${SKILLS[@]}"; do
  if [ ! -d "$SRC/$s" ]; then echo "WARN: canonical skill missing, skipping: $s" >&2; continue; fi
  rm -rf "${DEST:?}/$s"
  cp -r "$SRC/$s" "$DEST/$s"
  echo "mirrored: $s"
done

echo "Done — mirrored ${#SKILLS[@]} skills into $DEST"
echo "Untouched P2T-only skills: adam-to-tlg, mock-tlg-generator, trial-metadata-extractor, adam-to-teal"
