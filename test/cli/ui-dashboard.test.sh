#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 - "$repo_root" <<'PY'
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlencode
from urllib.request import urlopen

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp).resolve()
    checkout = root / "project"
    checkout.mkdir()
    cli = root / "install/bin/runweld"
    env = dict({k: v for k, v in os.environ.items() if not k.startswith("RUNWELD_")},
               XDG_CACHE_HOME=str(root / "cache"), BROWSER="true",
               GIT_AUTHOR_NAME="Tester", GIT_AUTHOR_EMAIL="test@example.org",
               GIT_COMMITTER_NAME="Tester", GIT_COMMITTER_EMAIL="test@example.org")

    def run(*args, cwd=checkout):
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    def get(url, path):
        with urlopen(url + path, timeout=5) as response:
            return response.read()

    run(Path(sys.argv[1]) / "scripts/install-runweld", "--prefix", cli.parents[1])
    store = cli.parents[1] / "lib/runweld"
    release = (store / "default").read_text().strip()
    files = json.loads((store / "releases" / release / "release.json").read_bytes())["files"]
    assert {"ui/__init__.py", "ui/frontend/index.html", "ui/frontend/styles.css",
            "ui/reader/route.py", "ui/server/__init__.py"} <= files.keys(), (
        "distribution#shared-resources: the installed manifest records the UI at the release root")
    assert not any(path.startswith("workflow/ui/") for path in files), (
        "distribution#shared-resources: the installed manifest has no duplicate UI under workflow")
    run("git", "init", "-qb", "main")
    run("git", "commit", "--allow-empty", "-qm", "base")
    run(cli, "onboard", "--apply", "--primary-provider", "Fixture", "--primary-model", "primary",
        "--secondary-provider", "Fixture", "--secondary-model", "secondary", "--no-setup")
    lock = tomllib.loads((checkout / "runweld.lock").read_text())
    assert "ui" not in lock["cli"] and "ui" not in lock["guides"], (
        "distribution#project-lock: dashboard files belong to the release manifest, not v3 lock components")
    task = json.loads(run(cli, "task", "start", "dashboard", "--goal", "Exercise the dashboard", "--json"))
    plan = Path(task["plan"])
    run(cli, "grill", "start", plan)
    run(cli, "grill", "done", plan, "--result", "Follow the recorded phase dependencies.")

    with subprocess.Popen([cli, "ui", "up"], cwd=task["tree"], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        try:
            assert select.select([process.stdout], [], [], 5)[0], "panel did not report readiness"
            address = process.stdout.readline().decode().strip()
            assert address.startswith("URL: "), address
            url = address.removeprefix("URL: ")
            assert process.stdout.readline().decode().strip() == f"PID: {process.pid}"

            # dashboard#task-evidence: the installed page starts the live view and reads evidence from the checkout.
            page = get(url, "/")
            entry = re.search(rb'<script type="module" src="\./([\w.-]+)"', page)
            assert entry, "installed page does not start the dashboard"
            assert get(url, "/" + entry[1].decode()), "installed dashboard entry module is empty"
            snapshot = json.loads(get(url, "/api/project"))
            assert snapshot["project"]["path"] == str(checkout)
            (row,) = snapshot["tasks"]
            assert (row["id"], row["stage"]) == ("dashboard", "prototype")
            decisions = next(item for stage in row["stages"] if stage["id"] == "grill"
                             for item in stage["evidence"] if item["title"] == "Discovery decisions")
            query = urlencode({"task": row["id"], "id": decisions["id"]})
            assert b"Follow the recorded phase dependencies." in get(url, "/api/evidence?" + query)

            prototype = Path(task["artifacts"]) / "prototype.html"
            prototype.write_text("<h1>Accepted example</h1>")
            run(cli, "prototype", "start", plan)
            run(cli, "prototype", "done", plan, "--result", "Reviewed", "--artifact", prototype)
            (updated,) = json.loads(get(url, "/api/project"))["tasks"]
            assert updated["stage"] == "plan"
            capture = next(item for stage in updated["stages"] if stage["id"] == "prototype"
                           for item in stage["evidence"] if item["kind"] == "html")
            query = urlencode({"task": row["id"], "id": capture["id"]})
            assert get(url, "/api/evidence?" + query) == b"<h1>Accepted example</h1>"
        finally:
            try:
                run(cli, "ui", "down", str(process.pid), cwd=root)
                assert process.wait(timeout=5) == 0
            finally:
                if process.poll() is None:
                    process.kill()
PY
