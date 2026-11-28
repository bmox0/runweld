"""Observe a compiled task through the CLI's pinned workflow resolver."""
from functools import cache
import json
import os
from pathlib import Path
import subprocess
import sys

ENGINE = Path("workflow/build/pipeline.py")
VIEWER = Path(__file__).resolve().parents[2]


def observe(project, plan, bundle):
    try:
        reply = subprocess.run(
            [sys.executable, "-I", "-B", __file__, str(bundle), str(project), str(plan)],
            capture_output=True, timeout=4, check=True,
        )
        return json.loads(reply.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main(bundle, project, plan):
    sys.path[:0] = [str((bundle / ENGINE).parent), str(VIEWER)]
    import pipeline
    import runweld_release as release
    from ui.reader import file_bytes, open_record

    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_EXTERNAL_DIFF"):
        os.environ.pop(name, None)
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"
    os.environ["GIT_NO_LAZY_FETCH"] = "1"
    index = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    for key, value in (("core.fsmonitor", "false"), ("diff.external", "")):
        os.environ[f"GIT_CONFIG_KEY_{index}"] = key
        os.environ[f"GIT_CONFIG_VALUE_{index}"] = value
        index += 1
    os.environ["GIT_CONFIG_COUNT"] = str(index)

    folder = plan.parent
    allowed_files = {plan.with_suffix(suffix) for suffix in
                     (".md", ".json", ".run.toml", ".task.json", ".summary.md", ".shape.toml")}
    check_lock = folder / (plan.stem + ".json.checks.lock")

    def scoped_bytes(path):
        path = Path(path)
        if path in allowed_files:
            return file_bytes(project, path.relative_to(project))
        if path == bundle / release.WORKFLOW:
            return file_bytes(bundle, Path(release.WORKFLOW))
        return None

    def regular_bytes(path):
        if (data := scoped_bytes(path)) is None:
            raise FileNotFoundError(path)
        return data

    def read_required(path, code, fix, *, optional=False, newline=None):
        if (data := scoped_bytes(path)) is None:
            if optional and not os.path.lexists(path):
                return None
            raise pipeline.Refuse(code, "Recorded input is unavailable", fix)
        try:
            result = data.decode()
        except UnicodeError:
            raise pipeline.Refuse(code, "Recorded input is not UTF-8", fix) from None
        if not result.strip() or "\0" in result:
            raise pipeline.Refuse(code, "Recorded input is empty or invalid", fix)
        return pipeline.markdown_newlines(result) if newline is None else result

    release.regular_bytes = regular_bytes
    pipeline.read_required = read_required

    def open_lock(path, mode):
        if Path(path) != check_lock or mode != "rb":
            raise OSError("Unexpected workflow file")
        return open_record(project, check_lock.relative_to(project))

    pipeline.open = open_lock
    listed_worktrees = release.worktrees(project)
    roots = {tree.resolve() for tree, _ in listed_worktrees if tree.is_dir()}

    @cache
    def scoped_git(*args, check=True, cwd=None):
        here = Path(cwd or project).resolve()
        if here not in roots and here != folder and here != project:
            if check:
                raise pipeline.Refuse("tree", "Recorded worktree is unavailable", "restore the task worktree")
            return subprocess.CompletedProcess(["git", *args], 128, "", "Recorded worktree is unavailable")
        result = subprocess.run(["git", *args], cwd=here, capture_output=True, text=True, timeout=2)
        if check and result.returncode:
            raise pipeline.Fail(result.stderr.strip() or "Git inspection failed")
        return result

    def scoped_worktrees(location):
        here = Path(location).resolve()
        return listed_worktrees if here == folder or here in roots or here == project else []

    pipeline.git = scoped_git
    release.worktrees = scoped_worktrees

    def prepared(plan, st, kind, executor, args):
        phase = args[0] if kind == "implementer" else None
        cases = list(map(int, args[1].split(","))) if kind == "verify" and args else []
        marker = "Assignment binding: " + pipeline.brief_binding(plan, st, kind, executor, phase=phase, cases=cases)
        for name in sorted(os.listdir(folder), reverse=True):
            if not name.startswith(f"{Path(plan).stem}.brief-{kind}-") or not name.endswith(".md"):
                continue
            candidate = folder / name
            body = file_bytes(project, candidate.relative_to(project))
            if body and marker.encode() in body.splitlines():
                return str(candidate)
        return None

    pipeline.prepared_brief = prepared
    st = pipeline.load_state(plan, required=True)
    head, tail = pipeline.read_plan(plan)
    tree = pipeline.tree_fact(plan, st)
    stage, actions = pipeline.workflow_next(
        str(plan), st, tree, pipeline.ready_phases(st),
        pipeline.drift_diags(plan, st, head, tail), pipeline.consent_diags(plan, st, head=head),
    )
    safe = []
    for row in actions:
        item = {key: row[key] for key in ("kind", "owner", "action", "input", "waiting_for") if key in row}
        assignment = row.get("assignment") or {}
        if row.get("waiting_for") == "merge" and "--merged" in row.get("command", {}).get("argv", []):
            item["action"] += " After observing the merge, confirm with runweld finish --merged PLAN."
        if row.get("check"):
            item["action"] = "Wait for full checks." if row["kind"] == "wait" else "Read the current check recovery instructions."
        if row.get("role") == "coordinator" and assignment.get("kind") == "land":
            item["action"] = "Resolve uncommitted worktree changes before landing. Run `runweld next` in the task worktree for details."
        if assignment:
            item["assignment"] = {key: assignment[key] for key in ("id", "cycle", "head", "range", "cases", "phase") if key in assignment}
            if path := assignment.get("brief", {}).get("path"):
                item["assignment"]["brief"] = Path(path).name
        if executor := row.get("executor"):
            item["executor"] = {key: executor[key] for key in ("provider", "model", "tier", "effort") if key in executor}
        safe.append(item)
    verification = {}
    if st.get("cycles") and stage in ("build-verification", "judge", "human-review"):
        try:
            tree = pipeline.tree_of(plan, st)
            pipeline.on_branch(st, tree)
            cycle = pipeline.cycle_of(st)
            head = pipeline.head_sha(None, tree)
            verification = {
                "checksCurrent": pipeline.checks_current(st, cycle, tree),
                "reviewCurrent": pipeline.review_is_current(cycle, pipeline.review_target(st, cycle, tree, head)),
                "pendingCases": pipeline.pending_results(st, cycle, tree),
            }
        except pipeline.Refuse:
            pass
    print(json.dumps({"stage": stage, "actions": safe, "verification": verification}))


if __name__ == "__main__":
    main(*(Path(value) for value in sys.argv[1:]))
