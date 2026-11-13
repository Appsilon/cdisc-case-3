"""Normalise the inputs and run the CDISC CORE rules engine over them.

Every dataset is staged as SAS V5 transport named after the dataset in lower
case (`dm.xpt`, `adsl.xpt`): CORE reads the domain from the file name, and one
file type keeps the run uniform. A dataset that cannot be written as V5 (name
over 8 characters, say) is reported, never truncated.

CORE runs up to twice, because `-lr` replaces the published rules rather than
adding to them:
  1. the published rules of the standard (none exist for ADaMIG);
  2. the local rules — carried in /artifacts/rules/<standard>/ plus any the
     sponsor supplied — when there are any.
The two JSON reports are merged into core-report.json; each pass keeps its XLSX.
A local rule whose Core Id is a published CORE-* id replaces that published rule
(excluded from pass 1 with -er): the carried sdtmig/CORE-000206.yml is CDISC's
corrected definition of a rule CORE v1.0.0 publishes with a per-subject cross
join (false issues; >14 GB on the CDISC pilot's SUPPLB).
Issue rows are capped at MAX_ISSUE_ROWS per rule and dataset (CORE `-me <n> true`):
real studies raise hundreds of thousands of rows for one rule (EPOCH missing on
every QS/LB record of the CDISC pilot - 293k rows, a 113 MB report, an XLSX that
did not finish in an hour). CORE's Issue_Summary keeps the true counts.
The platform runs this step in an 8 GB, 2-CPU container. CORE sizes its caches
and picks pandas or Dask from psutil's available memory, which inside a container
is the host's; core_memory/sitecustomize.py makes every CORE process see half the
container's usable memory instead (CORE_MEMORY_BUDGET_BYTES). CORE always runs on
pandas: its Dask path was 3x slower on the pilot and reported different findings
(163k vs 293k issues) - the report must not depend on the machine. Workers: one
per available CPU (cgroup quota), bounded by the memory the caches leave at
WORKER_MEMORY_BYTES each (one worker plus caches peaked at 6.7 GB on the pilot,
CORE-002123 on QS; when the kernel kills a worker CORE's pool hangs for good);
CORE_POOL_SIZE overrides it. The staging folders are emptied first, so a retried
step never sees the previous attempt's datasets.

Result: { config, coreVersion, environment, datasets, ruleStatusCounts,
          issueCount, notes, notChecked, inputFiles, reports }
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import OUTPUT_DIR, StepFailure, read_input, run_main, sha256_of, step_output, verify_files, write_result  # noqa: E402

CORE_HOME = Path(os.environ.get("CORE_HOME", "/opt/cdisc-core/core"))
CARRIED_RULES = Path(os.environ.get("CORE_LOCAL_RULES", "/artifacts/rules"))
DATASETS_DIR = OUTPUT_DIR / "datasets"
INPUTS_DIR = OUTPUT_DIR / "inputs"
WORK_DIR = Path(os.environ.get("CORE_WORK_DIR", "/tmp/core-work"))
DATASET_NAME = re.compile(r"^[a-z][a-z0-9]{1,7}$")
NO_RULES_MESSAGE = "No rules were selected"
MAX_ISSUE_ROWS = 1000
WORKER_MEMORY_BYTES = 4 * 1024 ** 3
PANDAS_THRESHOLD_BYTES = str(10 ** 15)
CORE_MEMORY_DIR = Path(__file__).resolve().parent / "core_memory"
CACHE_SHARE_OF_BUDGET = 0.75
DATA_KINDS = {"sdtm", "send", "adam", "usdm"}
DEFINE_SUFFIX = "-define"


def classify(entry: dict) -> str:
    """The role of one input: dataset, define, usdm, rule, lineage, program, history or ignored."""
    kind = str(entry.get("kind") or "")
    if kind in DATA_KINDS:
        return "usdm" if kind == "usdm" else "dataset"
    if kind.endswith(DEFINE_SUFFIX):
        return "define"
    if kind == "core-rules":
        return "rule"
    if kind == "lineage":
        return "lineage"
    if kind == "adam-program":
        return "program"
    if kind.startswith("core-dispositions") or kind.startswith("core-issue-index") or kind == "core-policy":
        return "history"
    name = entry["name"].lower()
    suffix = Path(name).suffix
    if suffix in (".xpt", ".sas7bdat", ".csv"):
        return "dataset"
    if suffix == ".xml":
        return "define"
    if suffix in (".yml", ".yaml"):
        return "rule"
    if suffix in (".r", ".sas"):
        return "program"
    if suffix == ".json":
        if name.startswith("lineage"):
            return "lineage"
        if name.startswith(("core-dispositions", "core-issue-index", "core-policy")):
            return "history"
        return sniff_json(Path(entry["localPath"]))
    return "ignored"


def sniff_json(path: Path) -> str:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "ignored"
    if isinstance(document, dict) and ("datasetJSONVersion" in document or "clinicalData" in document or "referenceData" in document):
        return "dataset"
    if isinstance(document, dict) and ("usdmVersion" in document or "study" in document):
        return "usdm"
    return "ignored"


def dataset_json_frame(path: Path):
    """Dataset-JSON 1.1 (top-level columns/rows) or 1.0 (clinicalData itemGroupData)."""
    import pandas

    document = json.loads(path.read_text(encoding="utf-8"))
    if "columns" in document:
        columns = document["columns"]
        rows = document.get("rows") or []
        label = document.get("label") or ""
    else:
        container = document.get("clinicalData") or document.get("referenceData") or {}
        group = next(iter((container.get("itemGroupData") or {}).values()))
        columns = group["items"]
        rows = group.get("itemData") or []
        label = group.get("label") or ""
    names = [column["name"] for column in columns]
    frame = pandas.DataFrame(rows, columns=names)
    labels = [column.get("label") or "" for column in columns]
    if names and names[0] == "ITEMGROUPDATASEQ":
        frame = frame.drop(columns=names[0])
        labels = labels[1:]
    return frame, labels, label


def stage_dataset(entry: dict, findings: list[dict]) -> dict | None:
    """Write one dataset to DATASETS_DIR/<name>.xpt. Returns its summary, or None when it cannot be validated."""
    import pandas
    import pyreadstat

    source = Path(entry["localPath"])
    stem = Path(entry["name"]).stem.lower()
    if DATASET_NAME.match(stem) is None:
        findings.append({"dataset": entry["name"], "problem": "File name is not a dataset name (1-8 letters/digits, starting with a letter); CORE reads the domain from it.", "fatal": True})
        return None
    target = DATASETS_DIR / f"{stem}.xpt"
    if target.exists():
        raise StepFailure(f"Two inputs map to dataset {stem.upper()} (e.g. ae.xpt and ae.sas7bdat). Supply one file per dataset.")
    suffix = source.suffix.lower()
    if suffix == ".xpt":
        shutil.copyfile(source, target)
        _, meta = pyreadstat.read_xport(str(target), metadataonly=True)
        return {"name": stem, "source": entry["name"], "records": meta.number_rows, "variables": len(meta.column_names)}

    if suffix == ".sas7bdat":
        frame, meta = pyreadstat.read_sas7bdat(str(source))
        labels, table_label = list(meta.column_labels or [None] * len(frame.columns)), meta.file_label or ""
    elif suffix == ".csv":
        frame = pandas.read_csv(source, keep_default_na=False, na_values=[""])
        labels, table_label = [None] * len(frame.columns), ""
        findings.append({"dataset": stem.upper(), "problem": "CSV carries no labels or types; types were inferred.", "fatal": False})
    else:
        frame, labels, table_label = dataset_json_frame(source)

    too_long = [str(column) for column in frame.columns if len(str(column)) > 8]
    if too_long:
        findings.append({"dataset": stem.upper(), "problem": f"Variable names longer than 8 characters cannot be written as SAS V5: {', '.join(too_long)}", "fatal": True})
        return None
    long_labels = [str(column) for column, label in zip(frame.columns, labels) if label and len(label) > 40]
    if long_labels:
        findings.append({"dataset": stem.upper(), "problem": f"Labels over 40 characters were shortened for SAS V5: {', '.join(long_labels)}", "fatal": False})
    labels = [(label or "")[:40] for label in labels]
    pyreadstat.write_xport(frame, str(target), table_name=stem.upper(), file_label=(table_label or "")[:40],
                           column_labels=labels, file_format_version=5)
    return {"name": stem, "source": entry["name"], "records": len(frame), "variables": len(frame.columns)}


def read_cgroup(name: str) -> str:
    try:
        return Path("/sys/fs/cgroup", name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def available_cpus() -> float:
    cpus = float(len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1))
    quota = read_cgroup("cpu.max").split() or [read_cgroup("cpu/cpu.cfs_quota_us"), read_cgroup("cpu/cpu.cfs_period_us")]
    if len(quota) == 2 and quota[0].isdigit() and quota[1].isdigit():
        cpus = min(cpus, int(quota[0]) / int(quota[1]))
    return cpus


def runtime_environment(largest_dataset_bytes: int) -> dict:
    """CPUs, memory and the CORE worker count for this container."""
    import psutil

    memory = psutil.virtual_memory()
    limit_text = read_cgroup("memory.max") or read_cgroup("memory/memory.limit_in_bytes")
    usage_text = read_cgroup("memory.current") or read_cgroup("memory/memory.usage_in_bytes")
    memory_limit = min(int(limit_text), memory.total) if limit_text.isdigit() else memory.total
    usable_memory = min(memory.available, memory_limit - int(usage_text) if usage_text.isdigit() else memory_limit)
    cpus = available_cpus()
    core_budget = usable_memory // 2
    worker_memory = usable_memory - int(core_budget * CACHE_SHARE_OF_BUDGET)
    pool_size = int(os.environ.get("CORE_POOL_SIZE") or max(1, min(int(cpus), worker_memory // WORKER_MEMORY_BYTES)))
    return {
        "cpus": round(cpus, 2),
        "memoryTotal": memory.total,
        "memoryLimit": memory_limit,
        "memoryUsable": usable_memory,
        "coreMemoryBudget": core_budget,
        "largestDatasetBytes": largest_dataset_bytes,
        "datasetImplementation": "pandas",
        "poolSize": pool_size,
        "passSeconds": {},
    }


def core_environment(environment: dict) -> dict:
    python_path = os.pathsep.join(part for part in (str(CORE_MEMORY_DIR), os.environ.get("PYTHONPATH", "")) if part)
    return {
        **os.environ,
        "PYTHONPATH": python_path,
        "CORE_MEMORY_BUDGET_BYTES": str(environment["coreMemoryBudget"]),
        "DATASET_SIZE_THRESHOLD": PANDAS_THRESHOLD_BYTES,
    }


def core_version() -> str:
    completed = subprocess.run(["./core", "version"], cwd=CORE_HOME, capture_output=True, text=True)
    return (completed.stdout or completed.stderr).strip().splitlines()[-1] if completed.returncode == 0 else "unknown"


def run_engine(arguments: list[str], label: str, notes: list[str], environment: dict) -> dict | None:
    """One CORE pass. Returns its parsed JSON report, or None when the pass selected no rules."""
    stem = WORK_DIR / f"report-{label}"
    command = ["./core", "validate", *arguments, "-o", str(stem), "-of", "JSON", "-of", "XLSX", "-p", "disabled",
               "-me", str(MAX_ISSUE_ROWS), "true", "-ps", str(environment["poolSize"])]
    print(f"[{label}] {' '.join(command)}", flush=True)
    started = time.monotonic()
    completed = subprocess.run(command, cwd=CORE_HOME, capture_output=True, text=True,
                               env=core_environment(environment))
    environment["passSeconds"][label] = round(time.monotonic() - started)
    print(f"[{label}] finished in {environment['passSeconds'][label]} s, exit code {completed.returncode}", flush=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    for line in output.splitlines()[-25:]:
        print(f"[{label}] {line}")
    if NO_RULES_MESSAGE in output:
        notes.append(f"{label} rules: CORE selected no rules for this standard/version.")
        return None
    report_path = stem.with_suffix(".json")
    if report_path.exists() is False:
        raise StepFailure(f"CORE ({label} rules) produced no report, exit code {completed.returncode}: {output.strip()[-600:]}")
    xlsx = stem.with_suffix(".xlsx")
    if xlsx.exists():
        shutil.copyfile(xlsx, OUTPUT_DIR / ("core-report.xlsx" if label == "published" else f"core-report-{label}.xlsx"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for rule in report.get("Rules_Report") or []:
        rule["source"] = label
    return report


def merge_reports(reports: list[dict]) -> dict:
    merged = {"Conformance_Details": {}, "Dataset_Details": [], "Issue_Summary": [], "Issue_Details": [], "Rules_Report": []}
    for report in reports:
        if merged["Conformance_Details"] == {}:
            merged["Conformance_Details"] = report.get("Conformance_Details") or {}
        if merged["Dataset_Details"] == []:
            merged["Dataset_Details"] = report.get("Dataset_Details") or []
        for section in ("Issue_Summary", "Issue_Details", "Rules_Report"):
            merged[section].extend(report.get(section) or [])
    return merged


def collect_rules(standard: str, uploaded: list[Path]) -> Path | None:
    rules_dir = WORK_DIR / "local-rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    carried = CARRIED_RULES / standard
    sources = sorted(carried.glob("*.y*ml")) if carried.is_dir() else []
    for source in [*sources, *uploaded]:
        shutil.copyfile(source, rules_dir / source.name)
    return rules_dir if any(rules_dir.iterdir()) else None


def replaced_published_rules(rules_dir: Path | None) -> list[str]:
    """Published CORE ids that a local rule redefines."""
    import yaml

    if rules_dir is None:
        return []
    core_ids = set()
    for rule_file in rules_dir.iterdir():
        core_id = str(((yaml.safe_load(rule_file.read_text(encoding="utf-8")) or {}).get("Core") or {}).get("Id") or "")
        if core_id.startswith("CORE-"):
            core_ids.add(core_id)
    return sorted(core_ids)


def main() -> None:
    step_input = read_input()
    config = step_output(step_input, "resolve-inputs").get("config") or {}
    if not config:
        raise StepFailure("resolve-inputs produced no config")
    files = step_input.get("files") or []
    if not files:
        raise StepFailure("No files reached this step: the upload or the study package was empty.")
    verify_files(files)

    for folder in (DATASETS_DIR, INPUTS_DIR, WORK_DIR):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)

    roles = {entry["name"]: classify(entry) for entry in files}
    notes = [f"Ignored {name}: not a dataset, define, rule, lineage or program." for name, role in roles.items() if role == "ignored"]
    findings: list[dict] = []
    datasets: list[dict] = []
    define_path: Path | None = None
    usdm_path: Path | None = None
    uploaded_rules: list[Path] = []

    for entry in files:
        role = roles[entry["name"]]
        local = Path(entry["localPath"])
        if role == "dataset":
            staged = stage_dataset(entry, findings)
            if staged is not None:
                datasets.append(staged)
        elif role == "define":
            if define_path is not None:
                raise StepFailure("More than one define.xml was supplied; supply exactly one.")
            define_path = WORK_DIR / "define.xml"
            shutil.copyfile(local, define_path)
            text = define_path.read_text(encoding="utf-8", errors="replace")
            if "def/v2.0" not in text and "def/v2.1" not in text:
                notes.append(f"{entry['name']} is not Define-XML 2.0/2.1; CORE cannot use it, so it was left out.")
                define_path = None
        elif role == "usdm":
            usdm_path = WORK_DIR / local.name
            shutil.copyfile(local, usdm_path)
        elif role == "rule":
            uploaded_rules.append(local)
        elif role in ("lineage", "program", "history"):
            target = INPUTS_DIR / ("programs" if role == "program" else "") / local.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local, target)

    standard, version = config["standard"], config["version"]
    if standard == "usdm":
        if usdm_path is None:
            raise StepFailure("Standard usdm needs a USDM study-definition JSON; none was supplied.")
        base_arguments = ["-s", "usdm", "-v", version, "-dp", str(usdm_path)]
    else:
        if not datasets:
            raise StepFailure("No dataset could be staged for CORE: " + "; ".join(f"{item['dataset']}: {item['problem']}" for item in findings))
        base_arguments = ["-s", standard, "-v", version, "-d", str(DATASETS_DIR)]
        if define_path is not None:
            base_arguments += ["-dxp", str(define_path)]
        if config.get("ct"):
            base_arguments += ["-ct", config["ct"]]

    inputs_validated = [usdm_path] if standard == "usdm" else list(DATASETS_DIR.glob("*.xpt"))
    environment = runtime_environment(max(staged.stat().st_size for staged in inputs_validated))
    print(f"environment: {json.dumps(environment)}", flush=True)

    rules_dir = collect_rules(standard, uploaded_rules)
    replaced = replaced_published_rules(rules_dir)
    for core_id in replaced:
        notes.append(f"{core_id}: the published CORE v1.0.0 rule was replaced by the local rule of the same id.")

    passes: dict[str, dict] = {}
    published = run_engine(base_arguments + [argument for core_id in replaced for argument in ("-er", core_id)], "published", notes, environment)
    if published is not None:
        passes["published"] = published
    if rules_dir is not None:
        local = run_engine(base_arguments + ["-lr", str(rules_dir)], "local", notes, environment)
        if local is not None:
            passes["local"] = local
    reports = list(passes.values())
    if not reports:
        raise StepFailure(f"No CORE rules exist for {standard} {version}, published or local — nothing was validated.")

    merged = merge_reports(reports)
    merged["Conformance_Details"]["Mediforce"] = {
        "passes": list(passes),
        "defineXml": define_path is not None,
        "ct": config.get("ct") or "",
    }
    (OUTPUT_DIR / "core-report.json").write_text(json.dumps(merged), encoding="utf-8")

    statuses = Counter(rule.get("status") for rule in merged["Rules_Report"])
    issue_count = sum(int(item.get("issues") or 0) for item in merged["Issue_Summary"]) or len(merged["Issue_Details"])
    input_files = [
        {"name": entry["name"], "downloadUrl": entry["downloadUrl"], "sha256": sha256_of(Path(entry["localPath"])), "role": roles[entry["name"]]}
        for entry in files
        if roles[entry["name"]] in ("dataset", "define", "usdm")
    ]
    write_result({
        "config": config,
        "coreVersion": core_version(),
        "environment": environment,
        "datasets": datasets,
        "ruleStatusCounts": dict(statuses),
        "issueCount": issue_count,
        "rulesWithIssues": len({(issue.get("core_id"), issue.get("dataset")) for issue in merged["Issue_Details"]}),
        "notes": notes,
        "intakeFindings": findings,
        "inputFiles": input_files,
        "summary": (
            f"CORE {standard} {version}: {issue_count} issue(s) across "
            f"{statuses.get('ISSUE REPORTED', 0)} rule(s); {statuses.get('EXECUTION ERROR', 0)} rule(s) could not execute. "
            f"{sum(environment['passSeconds'].values())} s on {environment['poolSize']} worker(s), {environment['cpus']} CPU(s)."
        ),
    })


if __name__ == "__main__":
    run_main(main)
