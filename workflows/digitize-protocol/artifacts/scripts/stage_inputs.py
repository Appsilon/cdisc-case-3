"""Verify the protocol (and SAP) and stage their text, page by page, where the agent reads it.

Files arrive as top-level `files` (from the study package or the upload),
already downloaded with `localPath`. Each is sha256-verified; the PDF text layer
is extracted with pypdf, one file per physical page (1-based, the page number a
citation names - not the page number printed in the footer), plus the whole
document in one file with "=== Page N ===" markers. The USDM 4.0 schema baked
into the image is copied next to them, so the gate and the agent's self-check
(which runs in another image) validate against the same file. Uploads carry no
kind: "sap" or "statistical" in the name = SAP, otherwise protocol.

Result: { inputFiles: [{name, downloadUrl, sha256, kind}], documents: {kind: pages}, summary }
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mfpkg import StepFailure, read_input, run_main, sha256_of, verify_files, write_result  # noqa: E402
from usdmlib import INPUTS_DIR, SCHEMA_PATH, WORK_DIR, page_path  # noqa: E402

SCHEMA_SOURCE = Path(os.environ.get("USDM_API_SOURCE", "/opt/usdm/USDM_API.json"))
MIN_AVERAGE_TEXT_PER_PAGE = 50


def classify(entry: dict) -> str:
    if entry.get("kind"):
        return str(entry["kind"])
    name = str(entry.get("name", "")).lower()
    return "sap" if re.search(r"(^|[^a-z])sap([^a-z]|$)", name) or "statistical" in name else "protocol"


def stage_pdf(source: Path, document: str) -> int:
    from pypdf import PdfReader

    try:
        pages = [page.extract_text() or "" for page in PdfReader(source).pages]
    except Exception as error:  # pypdf raises many types for a damaged or non-PDF file
        raise StepFailure(f"{source.name}: cannot read it as a PDF ({error}).") from error
    if not pages or sum(len(text.strip()) for text in pages) / len(pages) < MIN_AVERAGE_TEXT_PER_PAGE:
        raise StepFailure(f"{source.name}: the PDF has almost no text layer (a scan?). OCR is not supported; upload a text PDF.")
    page_path(document, 1).parent.mkdir(parents=True)
    for number, text in enumerate(pages, start=1):
        page_path(document, number).write_text(text, encoding="utf-8")
    combined = "".join(f"=== Page {number} ===\n{text}\n" for number, text in enumerate(pages, start=1))
    (INPUTS_DIR / document / f"{document}.txt").write_text(combined, encoding="utf-8")
    return len(pages)


def main() -> None:
    step_input = read_input()
    files = verify_files(step_input.get("files") or [])
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    INPUTS_DIR.mkdir(parents=True)

    kinds = [(entry, classify(entry)) for entry in files]
    for document in ("protocol", "sap"):
        named = [entry["name"] for entry, kind in kinds if kind == document]
        if len(named) > 1 or (document == "protocol" and not named):
            raise StepFailure(f"Expected {'exactly' if document == 'protocol' else 'at most'} one {document} PDF, got {len(named)}: "
                              + (", ".join(named) or "none"))
    not_pdf = [entry["name"] for entry, _kind in kinds if str(entry["name"]).lower().endswith(".pdf") is False]
    if not_pdf:
        raise StepFailure(f"Only PDF documents are supported, got: {', '.join(not_pdf)}")

    documents = {kind: stage_pdf(Path(entry["localPath"]), kind) for entry, kind in kinds}
    if SCHEMA_SOURCE.is_file() is False:
        raise StepFailure(f"The USDM 4.0 schema is missing from the image ({SCHEMA_SOURCE}).")
    SCHEMA_PATH.parent.mkdir(parents=True)
    shutil.copyfile(SCHEMA_SOURCE, SCHEMA_PATH)

    write_result({
        "inputFiles": [{"name": entry["name"], "downloadUrl": entry["downloadUrl"], "sha256": entry.get("sha256") or sha256_of(Path(entry["localPath"])),
                        "kind": kind} for entry, kind in kinds],
        "documents": documents,
        "summary": "Staged " + ", ".join(f"the {kind} ({pages} pages)" for kind, pages in documents.items()) + " and the USDM 4.0 schema.",
    })


if __name__ == "__main__":
    run_main(main)
