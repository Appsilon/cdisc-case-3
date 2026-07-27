"""Intermediate CDISC CORE conformance validation for the derived ADaM.

Runs as the `validate-core` script step, between `derive-adam`/`generate-define`
and `generate-tlfs`. It runs the CDISC Open Rules Engine (`cdisc-rules-engine`,
exposed as `core`) over the derived ADaM datasets and writes a conformance
report to /output for the reviewer to inspect at the TLF review gate.

Same proven pattern as cdisc-case-1: the engine is a shallow clone of a release
tag that ships an OFFLINE rules cache, so CORE runs with NO CDISC Library API
key and no network. CORE is ADVISORY here (like case 1) — findings are reported,
never a hard gate: the step always proceeds to TLF generation, and a human
resolves or justifies any findings at `review-tlfs`. The whole engine call is
wrapped so a CORE failure never fails the step.

CORE ingests XPT (or Dataset-JSON); the derive step may emit .csv / Dataset-JSON
/ .xpt, so this step first normalises whatever is in /workspace/adam into XPT v5
via R (haven), then points CORE at that directory.

Env knobs (set on the step; all have working defaults):
  CORE_BIN        engine command (default "core")
  CORE_STANDARD   standard slug (default "adamig")
  CORE_VERSION    version, hyphen form (default "1-3")
  CORE_CT         controlled-terminology package (default "" -> omit -ct)
  CORE_CACHE      cache dir passed to -ca (default "resources/cache", relative
                  to the engine dir the `core` wrapper cd's into)

Inputs:  /workspace/adam/*  (derived ADaM datasets)
Outputs: /output/core_report/*.json  (raw CORE report)
         /output/core-report.md       (human summary, read at review-tlfs)
         /output/result.json          { coreRan, standard, version, datasets,
                                         errorCount, warningNoticeCount, summary }
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/workspace"))
OUTPUT = Path(os.environ.get("OUTPUT_DIR", "/output"))
ADAM_DIR = WORKSPACE / "adam"
XPT_DIR = WORKSPACE / "adam_xpt"
CORE_DIR = OUTPUT / "core_report"

CORE_BIN = os.environ.get("CORE_BIN", "core")
STANDARD = os.environ.get("CORE_STANDARD", "adamig")
VERSION = os.environ.get("CORE_VERSION", "1-3")
CT_PACKAGE = os.environ.get("CORE_CT", "").strip()
CORE_CACHE = os.environ.get("CORE_CACHE", "resources/cache")

ERROR_TOKENS = ("error", "reject", "critical")

# R one-liner-ish converter: read every dataset in ADAM_DIR (csv / Dataset-JSON /
# xpt) and write it as XPT v5 (dataset name = lowercased, <=8 chars) so CORE can
# ingest it. Best-effort per file; a bad file is skipped, not fatal.
R_CONVERT = r"""
args <- commandArgs(trailingOnly = TRUE)
indir <- args[1]; outdir <- args[2]
dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
for (f in list.files(indir, full.names = TRUE)) {
  ext  <- tolower(tools::file_ext(f))
  name <- tolower(tools::file_path_sans_ext(basename(f)))
  if (!nzchar(name) || nchar(name) > 8) next
  df <- tryCatch({
    if (ext == "xpt")  haven::read_xpt(f)
    else if (ext == "csv")  utils::read.csv(f, stringsAsFactors = FALSE, check.names = FALSE)
    else if (ext == "json") datasetjson::read_dataset_json(f)
    else NULL
  }, error = function(e) NULL)
  if (is.null(df) || !is.data.frame(df) || ncol(df) == 0) next
  tryCatch(
    haven::write_xpt(df, file.path(outdir, paste0(name, ".xpt")), version = 5, name = name),
    error = function(e) message("skip ", name, ": ", conditionMessage(e))
  )
}
cat(length(list.files(outdir)))
"""


def normalise_to_xpt() -> int:
    """Convert the derived ADaM into a clean dir of XPT v5 datasets. Returns the
    number of XPT files produced (0 if none / conversion unavailable)."""
    if not ADAM_DIR.is_dir() or not any(ADAM_DIR.iterdir()):
        return 0
    if XPT_DIR.exists():
        shutil.rmtree(XPT_DIR, ignore_errors=True)
    XPT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["Rscript", "-e", R_CONVERT, str(ADAM_DIR), str(XPT_DIR)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            sys.stderr.write(f"[validate_core] R conversion stderr:\n{proc.stderr[-1000:]}\n")
    except (OSError, subprocess.SubprocessError) as exc:
        sys.stderr.write(f"[validate_core] R conversion failed: {exc}\n")
    return len(list(XPT_DIR.glob("*.xpt")))


def run_core() -> tuple[bool, str]:
    """Invoke CORE (advisory). Returns (ran_without_raising, combined_output)."""
    CORE_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [CORE_BIN, "validate", "-s", STANDARD, "-v", VERSION,
           "-d", str(XPT_DIR), "-ca", CORE_CACHE,
           "-o", str(CORE_DIR / "core"), "-of", "JSON", "-l", "error"]
    if CT_PACKAGE:
        cmd[6:6] = ["-ct", CT_PACKAGE]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        return True, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return False, f"'{CORE_BIN}' not found on PATH"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"core invocation failed: {exc}"


def digest_report() -> tuple[int, int, list[dict]]:
    """Best-effort count of ERROR vs WARNING/NOTICE findings from the CORE JSON
    report, tolerant to the report shape. Returns (errors, warn_notice, sample)."""
    reports = sorted(CORE_DIR.glob("*.json"))
    if not reports:
        return 0, 0, []
    try:
        data = json.loads(reports[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0, 0, []
    errors = warn_notice = 0
    sample: list[dict] = []

    def walk(obj):
        nonlocal errors, warn_notice
        if isinstance(obj, dict):
            sev = obj.get("severity") or obj.get("Severity") or obj.get("status")
            if sev is not None and any(k in obj for k in ("message", "description", "rule_id", "core_id", "Message")):
                s = str(sev).lower()
                if any(tok in s for tok in ERROR_TOKENS):
                    errors += 1
                else:
                    warn_notice += 1
                if len(sample) < 25:
                    sample.append({
                        "severity": s or "unknown",
                        "rule": obj.get("rule_id") or obj.get("core_id") or obj.get("id") or "",
                        "message": obj.get("message") or obj.get("description") or obj.get("Message") or "",
                    })
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return errors, warn_notice, sample


def render_report(core_ran, n_datasets, errors, warn_notice, sample, note="") -> str:
    lines = ["# CDISC CORE conformance report", ""]
    lines.append(f"- Engine: `cdisc-rules-engine` · standard `{STANDARD}` v`{VERSION}`"
                 + (f" · CT `{CT_PACKAGE}`" if CT_PACKAGE else " · no CT package"))
    lines.append(f"- ADaM datasets validated: {n_datasets}")
    lines.append(f"- CORE ran: {'yes' if core_ran else 'no'}")
    lines.append(f"- ERROR-severity findings: {errors}")
    lines.append(f"- WARNING/NOTICE findings: {warn_notice}")
    lines.append("")
    lines.append("_Advisory: CORE conformance is reported here for review; the pipeline "
                 "proceeds to TLF generation. Resolve or justify ERROR-severity findings "
                 "at the TLF review gate._")
    if note:
        lines.append("")
        lines.append("```")
        lines.append(note[-1500:])
        lines.append("```")
    if sample:
        lines.append("")
        lines.append("## Findings (sample)")
        for f in sample:
            rule = f" `{f['rule']}`" if f["rule"] else ""
            lines.append(f"- **{f['severity']}**{rule} — {f['message']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    n_datasets = normalise_to_xpt()
    core_ran = False
    errors = warn_notice = 0
    sample: list[dict] = []
    note = ""

    if n_datasets == 0:
        note = f"No ingestible ADaM datasets found/convertible under {ADAM_DIR}."
    else:
        ran, output = run_core()
        (CORE_DIR).mkdir(parents=True, exist_ok=True)
        (CORE_DIR / "core.log").write_text(output, encoding="utf-8")
        errors, warn_notice, sample = digest_report()
        core_ran = ran and bool(sorted(CORE_DIR.glob("*.json")))
        if not core_ran:
            note = output

    report_md = render_report(core_ran, n_datasets, errors, warn_notice, sample, note)
    for base in (OUTPUT, WORKSPACE):
        base.mkdir(parents=True, exist_ok=True)
        (base / "core-report.md").write_text(report_md, encoding="utf-8")

    summary = (f"CORE {'ran' if core_ran else 'did not run'}: {errors} error(s), "
               f"{warn_notice} warning/notice over {n_datasets} dataset(s)")
    result = {
        "coreRan": core_ran,
        "standard": STANDARD,
        "version": VERSION,
        "ctPackage": CT_PACKAGE or None,
        "datasets": n_datasets,
        "errorCount": errors,
        "warningNoticeCount": warn_notice,
        "summary": summary,
        "reportPath": "/output/core-report.md",
    }
    (OUTPUT / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"validate_core: {summary}", file=sys.stderr)
    # Advisory — always exit 0 so the pipeline proceeds regardless of findings.
    sys.exit(0)


if __name__ == "__main__":
    main()
