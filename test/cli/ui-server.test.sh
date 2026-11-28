#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 - "$repo_root" <<'PY'
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

source = Path(sys.argv[1])
with tempfile.TemporaryDirectory() as tmp:
    outside = Path(tmp).resolve()
    prefix = outside / "install with spaces"
    cli = prefix / "bin/runweld"
    cache = outside / "cache"
    env = dict({k: v for k, v in os.environ.items() if not k.startswith("RUNWELD_")},
               HOME=str(outside), XDG_CONFIG_HOME=str(outside / "config"), XDG_CACHE_HOME=str(cache),
               PATH=f"{outside}:{os.environ['PATH']}", DISPLAY="", WAYLAND_DISPLAY="", TERM="",
               GIT_AUTHOR_NAME="Tester", GIT_AUTHOR_EMAIL="test@example.org",
               GIT_COMMITTER_NAME="Tester", GIT_COMMITTER_EMAIL="test@example.org")
    browser = outside / "browser"
    browser.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$HOME/browser.log"\nexit "${BROWSER_EXIT:-0}"\n')
    browser.chmod(0o755)
    osascript = outside / "osascript"
    osascript.write_text("#!/bin/sh\ncat >/dev/null\nexit 1\n")
    osascript.chmod(0o755)
    env["BROWSER"] = str(browser)

    def run(*args, cwd=outside, code=0):
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == code, (args, result.returncode, result.stdout, result.stderr)
        return result.stdout if code == 0 else result.stderr

    candidate = outside / "source"
    candidate.mkdir()
    for name in ("workflow", "agents", "references", "adapters", "scripts", "docs", "bin"):
        shutil.copytree(source / name, candidate / name)
    for name in ("README.md", "LICENSE", "install.sh", "VERSION"):
        shutil.copy2(source / name, candidate / name)

    projects = (outside / 'first "project" & docs', outside / "other project")
    # The earlier pin has no UI payload, but the installer expects the directory.
    (candidate / "ui").mkdir()
    help_path = candidate / "workflow/build/cli_help.py"
    current_help = help_path.read_text()
    help_path.write_text("".join(line for line in current_help.splitlines(keepends=True) if not line.startswith("  ui ")))
    run(candidate / "scripts/install-runweld", "--prefix", prefix)
    earlier = (prefix / "lib/runweld/default").read_text().strip()
    for project in projects:
        project.mkdir()
        run("git", "init", "-qb", "main", cwd=project)
        run("git", "commit", "--allow-empty", "-qm", "base", cwd=project)
        run(cli, "onboard", "--apply", "--primary-provider", "Test", "--primary-model", "primary",
            "--secondary-provider", "Test", "--secondary-model", "secondary", "--no-setup", cwd=project)
    task = json.loads(run(cli, "task", "start", "example", "--json", cwd=projects[0]))
    tree = Path(task["tree"])
    pinned = [(project / "runweld.lock").read_bytes() for project in projects]

    for name in ("frontend", "server"):
        shutil.copytree(source / "ui" / name, candidate / "ui" / name)
    help_path.write_text(current_help)
    frontend = candidate / "ui/frontend"
    reader = candidate / "ui/reader"
    reader.mkdir()
    (reader / "__init__.py").write_text("""
def project_snapshot(project):
    return {"project": {"name": project.name, "path": str(project)}, "tasks": []}

def read_evidence(project, task, evidence_id):
    if (task, evidence_id) == ("example", "prototype"):
        return "html", b"<script>parent.document.body.textContent = 'unsafe'</script>"
    if task == "example" and evidence_id in {"png", "jpeg", "gif", "webp", "invalid"}:
        return "image", {"png": bytes.fromhex("89504e470d0a1a0a"), "jpeg": bytes.fromhex("ffd8ff"),
                         "gif": b"GIF89a", "webp": b"RIFF1234WEBP", "invalid": b"<svg>"}[evidence_id]
    return None
""")
    run(candidate / "scripts/install-runweld", "--prefix", prefix)

    # dashboard#project-instance: dashboard help is independent of the checkout pin.
    assert "\n  ui " in run(cli, "--help"), "dashboard#project-instance: root help lists the dashboard"
    pinned_help = run(cli, "--release", earlier, "--help", cwd=tree)
    assert "\n  ui " not in pinned_help
    assert run(cli, "--help", cwd=tree) == run(cli, "help", cwd=tree) == pinned_help
    assert "No running" in run(cli, "ui", "list")
    for subcommand in ((), ("up",), ("list",), ("down",)):
        card = run(cli, "help", "ui", *subcommand)
        assert "Examples" in card and card == run(cli, "ui", *subcommand, "--help")
        assert card == run(cli, "ui", *subcommand, "--help", cwd=tree)
    assert "URL" in run(cli, "help", "ui", "up") and "PID" in run(cli, "help", "ui", "up")
    assert "checkout" in run(cli, "ui", "up", code=1)
    assert "No running" in run(cli, "ui", "list")

    processes = []

    def launch(cwd, browser_exit="0"):
        process = subprocess.Popen([cli, "ui", "up"], cwd=cwd, env=dict(env, BROWSER_EXIT=browser_exit),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes.append(process)
        ready = b""
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            for _ in range(2):
                if b"\nPID: " in ready and ready.endswith(b"\n"):
                    break
                assert selector.select(5), ("dashboard startup did not report readiness", ready)
                chunk = os.read(process.stdout.fileno(), 4096)
                assert chunk, (ready, process.stderr.read().decode())
                ready += chunk
        url_line, pid_line = ready.decode().splitlines()
        assert pid_line == f"PID: {process.pid}" and url_line.startswith("URL: ")
        url = url_line.removeprefix("URL: ")
        assert urlsplit(url).hostname == "127.0.0.1"
        return process, url

    def http(url, route, *, headers=None, method="GET"):
        address = urlsplit(url)
        connection = HTTPConnection(address.hostname, address.port, timeout=3)
        try:
            connection.request(method, route, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    try:
        # dashboard#project-instance: task worktree and second checkout run independently on their older project pins.
        a, first = launch(tree)
        b, second = launch(projects[1], browser_exit="1")
        assert first != second
        entries = run(cli, "ui", "list")
        for process, url, project in zip((a, b), (first, second), projects):
            assert f"{process.pid}\t{url}\t{project}" in entries.splitlines()
            assert json.loads(http(url, "/api/project")[2]) == {
                "project": {"name": project.name, "path": str(project)}, "tasks": []}
        assert run(cli, "ui", "list", cwd=tree) == entries
        assert [(project / "runweld.lock").read_bytes() for project in projects] == pinned

        status, headers, content = http(first, "/")
        expected = (frontend / "index.html").read_bytes().replace(
            b"__RUNWELD_PROJECT__", b"first &quot;project&quot; &amp; docs")
        assert status == 200 and content == expected
        assert "font-src data:" in headers["Content-Security-Policy"]
        assert headers["Cache-Control"] == "no-store"
        assert http(first, "/styles.css")[0] == 200 and http(first, "/dashboard.mjs")[0] == 200
        status, headers, content = http(first, "/api/evidence?task=example&id=prototype")
        assert status == 200 and headers["Content-Type"].startswith("text/html") and b"unsafe" in content
        assert "sandbox" in headers["Content-Security-Policy"]
        assert headers["X-Content-Type-Options"] == "nosniff"
        for image in ("png", "jpeg", "gif", "webp"):
            status, headers, _ = http(first, f"/api/evidence?task=example&id={image}")
            assert status == 200 and headers["Content-Type"] == f"image/{image}"
        for route in ("/CONTRACT.txt", "/api/evidence?task=example&id=unknown", "/../runweld.lock", "/.git/config",
                      "/api/evidence?task=example&id=invalid"):
            assert http(first, route)[0] == 404, route
        for route in ("/api/evidence?task=example&id=prototype&id=prototype",
                      "/api/evidence?task=example&id=..%2F..%2Frunweld.lock"):
            assert http(first, route)[0] == 400, route
        for headers in ({"Host": "external.example"}, {"Origin": "http://external.example"},
                        {"Sec-Fetch-Site": "cross-site"}):
            assert http(first, "/api/project", headers=headers)[0] == 403
        assert http(first, "/api/project", method="POST")[0] == 404

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            log = outside / "browser.log"
            if log.exists() and {first, second} <= set(log.read_text().splitlines()):
                break
            time.sleep(0.02)
        else:
            raise AssertionError("dashboard never passed both printed URLs to the default browser")

        registry = cache / "runweld/ui"
        record = registry / f"{a.pid}.json"
        assert stat.S_IMODE(registry.stat().st_mode) == 0o700
        assert stat.S_IMODE(record.stat().st_mode) == 0o600
        old = record.read_bytes()

        # dashboard#project-instance: a copied identity with another PID cannot stop either process.
        unrelated = subprocess.Popen(["sleep", "30"], cwd=outside, env=env)
        processes.append(unrelated)
        impostor = registry / f"{unrelated.pid}.json"
        impostor.write_text(json.dumps(dict(json.loads(old), pid=unrelated.pid)))
        impostor.chmod(0o600)
        assert "No running" in run(cli, "ui", "down", str(unrelated.pid), code=1)
        assert unrelated.poll() is None and a.poll() is None and b.poll() is None
        assert run(cli, "ui", "list") == entries

        assert str(a.pid) in run(cli, "ui", "down", str(a.pid), cwd=projects[1])
        assert a.wait(timeout=5) == 0 and not record.exists()
        record.write_bytes(old)
        record.chmod(0o600)
        assert "No running" in run(cli, "ui", "down", str(a.pid), code=1)
        assert http(second, "/")[0] == 200
        assert run(cli, "ui", "list").splitlines() == [f"{b.pid}\t{second}\t{projects[1]}"]

        b.send_signal(signal.SIGINT)
        assert b.wait(timeout=5) == 0 and not (registry / f"{b.pid}.json").exists()
        assert "No running" in run(cli, "ui", "list")
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=5)
PY
