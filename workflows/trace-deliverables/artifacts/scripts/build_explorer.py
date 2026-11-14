"""Build traceability.json and traceability-explorer.html from a study package folder.

    python3 build_explorer.py <package dir> <output dir>

<package dir> holds the files as <kind>/<name> (tools/fetch_package.py layout;
build_step.py stages a run's package the same way). The ADaM datasets are
profiled with R haven (profile_adam.R); without Rscript or ADaM the explorer is
built without data profiles. The HTML is one self-contained page: the model as
JSON in <script id="DATA">, explorer.js and the styles inline, no external requests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracemodel import build_model  # noqa: E402

HERE = Path(__file__).resolve().parent


def profile_adam(package_dir: Path) -> tuple[dict, str | None]:
    datasets = sorted((package_dir / "adam").glob("*.xpt")) if (package_dir / "adam").is_dir() else []
    if len(datasets) == 0:
        return {}, "no ADaM datasets in the package"
    if shutil.which("Rscript") is None:
        return {}, "Rscript is not available"
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "profiles.json"
        completed = subprocess.run(["Rscript", "--vanilla", str(HERE / "profile_adam.R"), str(target), *map(str, datasets)],
                                   capture_output=True, text=True, timeout=1800)
        if completed.returncode != 0 or target.is_file() is False:
            return {}, "profile_adam.R failed: " + (completed.stderr.strip().splitlines() or ["no output"])[-1]
        return json.loads(target.read_text(encoding="utf-8")), None


def render(model: dict) -> str:
    template = (HERE / "explorer.html").read_text(encoding="utf-8")
    script = (HERE / "explorer.js").read_text(encoding="utf-8")
    data = json.dumps(model, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    return template.replace("<script>/*__SCRIPT__*/</script>", "<script>" + script.replace("</script", "<\\/script") + "</script>") \
                   .replace("/*__DATA__*/", data, 1)


def build(package_dir: Path, output_dir: Path) -> dict:
    profiles, profile_problem = profile_adam(package_dir)
    model = build_model(package_dir, profiles)
    if profile_problem is not None:
        model["gaps"].append({"kind": "data", "ref": "ADaM", "message": f"No data profiles: {profile_problem}."})
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "traceability.json").write_text(json.dumps(model, indent=1, ensure_ascii=False), encoding="utf-8")
    (output_dir / "traceability-explorer.html").write_text(render(model), encoding="utf-8")
    return model


def summary(model: dict) -> str:
    outputs, variables = model["outputs"], model["vars"]
    cells = sum(1 for output in outputs.values() if output.get("html") and "data-ard" in output["html"])
    reaching = sum(1 for finding in model["core"]["findings"] if finding["impact"]["outputs"])
    return (f"Traced {len(outputs)} output(s) ({cells} with number-level links), {len(variables)} ADaM variable(s), "
            f"{len(model['sdtm'])} SDTM column(s), {len(model['objectives'])} objective(s), {len(model['core']['findings'])} CORE finding(s) "
            f"({reaching} reach an output); {len(model['gaps'])} gap(s).")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    model = build(Path(sys.argv[1]), Path(sys.argv[2]))
    print(summary(model))
    for gap in model["gaps"][:20]:
        print(f"  gap [{gap['kind']}] {gap['ref']}: {gap['message']}")


if __name__ == "__main__":
    main()
