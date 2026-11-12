"""Block until a run ends or it (a sub-workflow run) or one of its children waits at a human step.

  python3 tools/wait_human.py [--prod] <master-run-id> [run-id-to-ignore ...]

Polls every 30 s through the mediforce CLI (run from ~/Repo/mediforce): staging with
~/.config/mediforce/staging-key, or with --prod prod.mediforce.ai with
~/.config/mediforce/phuse-key. Prints the paused child runs, or the master's final
state. Ignore runs you already handled or parked.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

INSTANCES = {"staging": ("https://staging.mediforce.ai", "staging-key"), "prod": ("https://prod.mediforce.ai", "phuse-key")}
INSTANCE = "staging"
CHILD_WORKFLOWS = ("protocol-digitization", "tlf-planning", "analysis-specification", "cdisc-core-validation", "adam-derivation", "ard-tfl-generation")
MEDIFORCE_CHECKOUT = Path.home() / "Repo" / "mediforce"


def cli(*arguments: str) -> str:
    base_url, key_file = INSTANCES[INSTANCE]
    environment = {**os.environ, "MEDIFORCE_API_KEY": (Path.home() / ".config/mediforce" / key_file).read_text().strip()}
    return subprocess.run(["pnpm", "exec", "mediforce", *arguments, f"--base-url={base_url}"], cwd=MEDIFORCE_CHECKOUT, env=environment,
                          capture_output=True, text=True).stdout


def has_open_task(run_id: str) -> bool:
    """A paused run waits for a person only with an open task; a parent waiting on its child run is paused too."""
    output = cli("task", "list", f"--instance-id={run_id}", "--json")
    tasks = json.loads(output) if output.strip() else []
    tasks = tasks if isinstance(tasks, list) else tasks.get("tasks", [])
    return any(task.get("status") not in ("completed", "cancelled") for task in tasks)


def main() -> None:
    global INSTANCE
    arguments = sys.argv[1:]
    if arguments[0] == "--prod":
        INSTANCE, arguments = "prod", arguments[1:]
    master, ignored = arguments[0], set(arguments[1:])
    while True:
        state = cli("run", "get", master)
        if "status:       running" not in state and "status:       paused" not in state:
            print(state)
            return
        waiting = [line for line in cli("run", "list").splitlines()
                   if "paused" in line and any(name in line for name in CHILD_WORKFLOWS)
                   and not any(run_id in line for run_id in ignored) and has_open_task(line.split()[2])]
        if waiting:
            print("\n".join(waiting))
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
