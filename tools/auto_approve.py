"""Approve every human task of a prod master run and its descendant runs, until the master ends.

For automated end-to-end runs Vedha asks for (first used 2026-11-13, run a48c3201):
CORE dispositions are recorded "justified" with a note saying they were not
individually reviewed; review verdicts get their approve option. Any other task
(upload, unknown form) stops the loop and is printed - nothing is guessed.
Only for runs where Vedha explicitly asked for automatic approval.

  python3 tools/auto_approve.py <master-run-id> [run-id-prefix-to-ignore ...]
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

BASE_URL = "https://prod.mediforce.ai"
KEY = (Path.home() / ".config/mediforce/phuse-key").read_text().strip()
CHECKOUT = Path.home() / "Repo" / "mediforce"
NOTE = "Auto-approved via the mediforce CLI for the automated end-to-end run Vedha requested (2026-11-13); not individually reviewed."


def cli(*arguments: str) -> str:
    completed = subprocess.run(["pnpm", "-s", "exec", "mediforce", *arguments, f"--base-url={BASE_URL}"], cwd=CHECKOUT,
                               env={**os.environ, "MEDIFORCE_API_KEY": KEY}, capture_output=True, text=True)
    return completed.stdout + (completed.stderr if completed.returncode != 0 else "")


def paused_descendants(run_id: str) -> list[str]:
    """Paused runs anywhere below run_id (children, grandchildren, ...) - never another run's tasks."""
    found: list[str] = []
    for line in cli("run", "list", f"--parent={run_id}").splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[1] not in ("running", "paused"):
            continue
        child = fields[2]
        if fields[1] == "paused":
            found.append(child)
        found.extend(paused_descendants(child))
    return found


def open_tasks(run_id: str) -> list[dict]:
    output = cli("task", "list", f"--instance-id={run_id}", "--json")
    try:
        tasks = json.loads(output)
    except json.JSONDecodeError:
        return []
    tasks = tasks if isinstance(tasks, list) else tasks.get("tasks", [])
    return [task for task in tasks if task.get("status") not in ("completed", "cancelled")]


def approve_verdict(task: dict) -> dict | None:
    config = (task.get("ui") or {}).get("config") or {}
    verdicts = task.get("verdicts") or config.get("verdicts") or config.get("options") or []
    names = [verdict.get("key") or verdict.get("id") or verdict.get("value") if isinstance(verdict, dict) else verdict
             for verdict in verdicts]
    chosen = next((name for name in names if isinstance(name, str) and ("approv" in name or "accept" in name)), None)
    if chosen is None:
        return None
    return {"kind": "verdict-with-params", "verdict": chosen, "paramValues": {"comment": NOTE}, "comment": NOTE}


def payload_for(task: dict) -> dict | None:
    component = (task.get("ui") or {}).get("component")
    if component == "table-editor":
        rows = [{"itemId": option["id"], "values": {"disposition": "justified", "justification": NOTE}}
                for option in task.get("options") or []]
        return {"kind": "rows", "rows": rows}
    return approve_verdict(task)


def main() -> None:
    master, ignored = sys.argv[1], set(sys.argv[2:])
    handled: set[str] = set()
    while True:
        state = cli("run", "get", master)
        if "status:       completed" in state or "status:       failed" in state:
            print(state, flush=True)
            return
        if "status:       running" not in state and "status:       paused" not in state:
            print(f"{time.strftime('%H:%M:%S')} master status unreadable, retrying: {state.strip()[:200]}", flush=True)
            time.sleep(30)
            continue
        for run_id in [master, *paused_descendants(master)]:
            if any(run_id.startswith(prefix) for prefix in ignored):
                continue
            for summary in open_tasks(run_id):
                if summary["id"] in handled:
                    continue
                try:
                    task = json.loads(cli("task", "get", summary["id"], "--json"))
                except json.JSONDecodeError:
                    continue
                payload = payload_for(task)
                if payload is None:
                    print(f"STOP: no automatic answer for task {task['id']} (run {run_id}, step {task.get('stepId')}):", flush=True)
                    print(json.dumps({key: task.get(key) for key in ("stepId", "ui", "options")}, default=str)[:3000], flush=True)
                    return
                result = cli("task", "complete", task["id"], f"--payload={json.dumps(payload)}")
                handled.add(task["id"])
                print(f"{time.strftime('%H:%M:%S')} completed {task.get('stepId')} on run {run_id[:8]} "
                      f"({payload['kind']}, {len(payload.get('rows', [])) or payload.get('verdict')}): {result.strip()[:200]}", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
