#!/usr/bin/env bash
# Install the CDISC TLF pipeline skills into the user's GLOBAL Claude Code skills
# directory (~/.claude/skills/), sourced from the canonical cdisc-case-3 copy.
# Global personal skills are available in every Claude Code session, any directory.
# Re-run any time to refresh after editing the canonical skills.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
C3_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$C3_ROOT/plugins/cdisc-case-3/skills"
DEST="$HOME/.claude/skills"

# The runnable pipeline skills (propose-skill-lesson is workflow-internal, not installed).
SKILLS=(tlf-planner tlf-plan-critic tlf-analysis-spec sdtm-to-adam tlf-generator traceability-builder)

[ -d "$SRC" ] || { echo "ERROR: canonical skills dir not found: $SRC" >&2; exit 1; }
mkdir -p "$DEST"

for s in "${SKILLS[@]}"; do
  [ -d "$SRC/$s" ] || { echo "WARN: canonical skill missing, skipping: $s" >&2; continue; }
  rm -rf "${DEST:?}/$s"
  cp -r "$SRC/$s" "$DEST/$s"
  echo "installed: $s -> $DEST/$s"
done

echo "Done — ${#SKILLS[@]} pipeline skills installed globally in $DEST"
echo "Restart Claude Code (or start a new session) to pick them up."
