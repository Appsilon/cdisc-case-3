"""The retry and review plumbing shared by the AI-writes / script-checks workflows.

A gate step counts its runs in <work-dir>/attempts.json and writes what it
rejected to <work-dir>/feedback.json for the agent; a reviewer's change request
is appended to <work-dir>/review-feedback.jsonl and gives the gate a fresh set
of attempts. The agent's own self-check must not use an attempt.

    loop = GateLoop(WORK_DIR)
    attempt = loop.count()                 # in the gate step
    result = loop.route("check-x", problems)   # {needsFix, retry, attempt, problems}
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from mfpkg import OUTPUT_DIR, StepFailure, now_iso, published_file, step_output

MAX_ATTEMPTS = 3


class GateLoop:
    def __init__(self, work_dir: Path, self_check: bool = False):
        self.work_dir = work_dir
        self.self_check = self_check
        self.attempts_path = work_dir / "attempts.json"
        self.feedback_path = work_dir / "feedback.json"
        self.review_feedback_path = work_dir / "review-feedback.jsonl"

    def attempts(self) -> int:
        if self.attempts_path.is_file() is False:
            return 0
        return int(json.loads(self.attempts_path.read_text(encoding="utf-8")).get("attempts", 0))

    def count(self) -> int:
        if self.self_check is True:
            return self.attempts()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        attempt = self.attempts() + 1
        self.attempts_path.write_text(json.dumps({"attempts": attempt}), encoding="utf-8")
        return attempt

    def reset(self) -> None:
        self.attempts_path.unlink(missing_ok=True)
        self.feedback_path.unlink(missing_ok=True)

    def route(self, step: str, problems: list[str]) -> dict:
        """Record the gate's verdict and say whether the work goes back to the agent."""
        attempt = self.attempts()
        if self.self_check is False and problems:
            self.feedback_path.write_text(json.dumps({"step": step, "attempt": attempt, "problems": problems}, indent=2), encoding="utf-8")
        elif self.self_check is False:
            self.feedback_path.unlink(missing_ok=True)
        return {"needsFix": bool(problems), "retry": bool(problems) and attempt < MAX_ATTEMPTS, "attempt": attempt, "problems": problems}

    def record_review(self, step_input: dict, review_step: str, skill: str) -> dict:
        """Append a 'revise' comment for the agent (and skill learning); fresh attempts for the revision."""
        review = step_output(step_input, review_step)
        comment = str(review.get("reviewerComment") or review.get("comment") or "").strip()
        if not comment:
            raise StepFailure("The work was sent back without a comment; the agent needs to know what to change.")
        return self.append_request(comment, skill)

    def append_request(self, comment: str, skill: str, source: str = "review") -> dict:
        """Append a change request (a reviewer's, or one a script composed) and give the agent fresh attempts."""
        previous = self.review_feedback_path.read_text(encoding="utf-8").splitlines() if self.review_feedback_path.is_file() else []
        iteration = len(previous) + 1
        line = {"skill": skill, "iteration": iteration, "comment": comment, "at": now_iso()}
        if source != "review":
            line["source"] = source
        with open(self.review_feedback_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")
        self.reset()
        return {"iteration": iteration, "comment": comment, "summary": f"Revision {iteration} requested: {comment[:200]}"}


def publish_copy(source: Path, kind: str, workflow: str) -> dict | None:
    """Copy a workspace file into this step's /output and describe it as a package FileEntry."""
    if source.is_file() is False:
        return None
    target = OUTPUT_DIR / source.name
    shutil.copyfile(source, target)
    return published_file(target, kind, workflow)
