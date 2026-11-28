"""Read-only dashboard projections of local Runweld records."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tomllib

from workflow.build import pipeline
from workflow.build import runweld_release as release
from .presentation import badge, overview, task_display
from .route import observe

PACKAGE = Path(__file__).resolve().parents[2]
PLANS = Path(pipeline.WORKFLOW_DIR) / "plans"
LIMIT = 16 * 1024 * 1024
SHA = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})")
ARTIFACTS = {
    ".md": "markdown", ".txt": "text", ".diff": "diff", ".patch": "diff",
    ".htm": "html", ".html": "html", ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".webp": "image",
}
PRIVATE = re.compile(r"(?:^|\.)(?:judge|notes|brief-[^.]+)\.md$", re.IGNORECASE)
PLAN_STATUSES = frozenset(pipeline.PLAN_STATUSES)
STAGE_GUIDES = {
    "grill": "workflow/grill/GUIDE.md", "prototype": "workflow/prototype/GUIDE.md",
    "reproduce": "workflow/bug/GUIDE.md", "plan": "workflow/plan/GUIDE.md",
    "build": "workflow/build/GUIDE.md", "build-verification": "workflow/build/references/gate.md",
    "judge": "workflow/build/references/judge.md", "human-review": "workflow/build/references/human-guide.md",
    "finish": "workflow/finish/GUIDE.md",
}
STAGE_LABELS = {"grill": "Grill", "prototype": "Prototype", "reproduce": "Bug reproduction",
                "build-verification": "Verification"}
STAGE_IDS = frozenset(("grill", "prototype", "plan", "build", "build-verification", "judge", "human-review", "finish"))


@contextmanager
def open_record(root, path, *, directory=False):
    # Walk from the trusted root without following links, including parent directories.
    path = Path(path)
    if path.is_absolute() or ".." in path.parts:
        raise OSError("outside the evidence root")
    folders = path.parts if directory else path.parts[:-1]
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY
    fd = os.open(root, flags)
    try:
        for part in folders:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        if directory:
            yield fd
        else:
            file = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(file, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > LIMIT:
                    raise OSError("not an evidence file")
                yield stream
    finally:
        os.close(fd)


def children(root, path, *, strict=False):
    try:
        with open_record(root, path, directory=True) as fd:
            return sorted(os.listdir(fd))
    except FileNotFoundError:
        return []
    except OSError:
        if strict:
            raise
        return []


def file_bytes(root, path):
    try:
        with open_record(root, path) as file:
            data = file.read(LIMIT + 1)
            return data if len(data) <= LIMIT else None
    except OSError:
        return None


def text_file(root, path):
    data = file_bytes(root, path)
    try:
        return data.decode() if data is not None else None
    except UnicodeError:
        return None


def mapping(value):
    return value if isinstance(value, dict) else {}


def records(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def value_of(row, key):
    value = row.get(key)
    if isinstance(value, str) and value.strip():
        return value.encode("utf-8", "replace").decode()
    return None


def content(root, path, parse):
    text = text_file(root, path)
    try:
        return mapping(parse(text)) if text is not None else {}
    except (ValueError, RecursionError):
        return {}


def checksum_key(value):
    return hashlib.sha256(os.fsencode(value)).hexdigest()[:24]


class Evidence:
    def __init__(self):
        self.items = {}

    def ref(self, items, key, title, kind, getter, *, revision, reference=False):
        if key not in self.items:
            self.items[key] = kind, getter
            items.append({"id": key, "title": title.encode("utf-8", "replace").decode(), "kind": kind, "revision": revision,
                          **({"role": "reference"} if reference else {})})

    def document(self, items, key, title, text, kind="markdown"):
        if text and text.strip():
            data = text.encode("utf-8", "replace")
            self.ref(items, key, title, kind, lambda: data, revision=hashlib.sha256(data).hexdigest())

    def file(self, items, key, title, kind, root, path, *, reference=False, checksum=None):
        try:
            with open_record(root, path) as file:
                info = os.fstat(file.fileno())
        except OSError:
            return False

        def get():
            data = file_bytes(root, path)
            if data is None or checksum and hashlib.sha256(data).hexdigest() != checksum:
                return None
            if kind != "image":
                try:
                    data.decode()
                except UnicodeError:
                    return None
            return data

        revision = checksum_key(f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}")
        self.ref(items, key, title, kind, get, revision=revision, reference=reference)
        return True

    def read(self, key):
        if key in self.items:
            kind, get = self.items[key]
            if (data := get()) is not None:
                return kind, data
        return None


def catalog(pin):
    if pin is None:
        return release.read_workflow(PACKAGE), PACKAGE, {}
    if not release.valid_release(pin):
        raise release.ReleaseError("invalid release pin")
    if PACKAGE.parent.name == "releases" and release.valid_release(PACKAGE.name):
        package = PACKAGE.parent / pin
    elif launcher := shutil.which("runweld"):
        package = Path(launcher).resolve().parents[1] / "lib" / "runweld" / "releases" / pin
    else:
        raise release.ReleaseError("release store unavailable")
    manifest = release.release_manifest(package, pin)["files"]
    data = file_bytes(package, release.WORKFLOW)
    if data is None or hashlib.sha256(data).hexdigest() != manifest.get(release.WORKFLOW, [None])[0]:
        raise release.ReleaseError("stage definitions unavailable")
    definitions = tomllib.loads(data.decode())
    order, stages = definitions["order"], definitions["stages"]
    if (not isinstance(order, list) or set(order) != STAGE_IDS or len(order) != len(STAGE_IDS)
            or any(not value_of(mapping(stages[key]), "label") for key in order)):
        raise release.ReleaseError("invalid stage definitions")
    return definitions, package, manifest


def available_catalog(pin, cache):
    if pin not in cache:
        try:
            cache[pin] = (*catalog(pin), True)
        except (release.ReleaseError, OSError, ValueError, TypeError, KeyError, IndexError):
            cache[pin] = (*catalog(None), False)
    return cache[pin]


def inventory(project):
    plans = {}
    for name in children(project, PLANS, strict=True):
        if match := release.DATED_TASK.fullmatch(name):
            task_id = match[1]
            folder = PLANS / name
            if task_id + ".task.json" not in children(project, folder):
                continue
            plan = folder / (task_id + ".md")
        elif name.endswith(".md") and release.TASK_ID.fullmatch(task_id := name[:-3]):
            plan = PLANS / name
        else:
            continue
        plans[task_id] = None if task_id in plans else plan
    return plans


def git_diff(project, *revisions):
    if not all(SHA.fullmatch(r) for r in revisions):
        return None
    command = ["diff"] if len(revisions) == 2 else ["show", "--format="]
    try:
        diff = subprocess.run(["git", "--no-replace-objects", *command, "--no-ext-diff", "--no-textconv", "--no-color",
                               *revisions, "--", ".", ":(exclude).runweld"], cwd=project, capture_output=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return diff.stdout if diff.returncode == 0 and 0 < len(diff.stdout) <= LIMIT else None


def add_artifact(evidence, items, key, project, artifacts, path, title):
    if artifacts is None or not path or "\x00" in path:
        return False
    path = Path(path)
    if path.is_absolute():
        if not path.is_relative_to(project / artifacts):
            return False
        path = path.relative_to(project)
    elif not path.is_relative_to(artifacts):
        path = artifacts / path
    if ".." in path.parts or not path.is_relative_to(artifacts):
        return False
    kind = ARTIFACTS.get(path.suffix.lower())
    if not kind or any(part.startswith(".") for part in path.relative_to(artifacts).parts) or PRIVATE.search(path.name):
        return False
    if evidence.file(items, key, title, kind, project, path):
        items[-1]["sourceName"] = str(path.relative_to(artifacts))
        return True
    return False


def capture_path(value):
    # shortcut: reserve explicit paths and artifact extensions until captures record a type.
    path = Path(value)
    return not any(char in value for char in "\r\n") and (
        path.is_absolute() or value.startswith(("./", "../")) or path.suffix.lower() in ARTIFACTS)


def add_capture(evidence, items, key, project, artifacts, capture, title):
    if add_artifact(evidence, items, key, project, artifacts, capture, title):
        return True
    if capture and add_artifact(evidence, items, key, project, artifacts, str(Path(capture) / "index.html"), title):
        return True
    return False


def phase_rows(state):
    seen = set()
    for row in records(state.get("phases")):
        n = row.get("n")
        if type(n) is int and n > 0 and n not in seen:
            seen.add(n)
            yield row


def text_lines(row, fields):
    return [f"**{title}** — {value}" for key, title in fields if (value := value_of(row, key))]



def compiled_route(project, plan, bundle, pin, engines):
    if pin not in engines:
        try:
            engines[pin] = release.verify_release(bundle.parents[1], pin) if pin else bundle
        except release.ReleaseError:
            engines[pin] = None
    engine = engines[pin]
    if engine and (row := observe(project, project / plan, engine)):
        stage = row.get("stage")
        if stage in STAGE_IDS:
            return row
    return {}


def phase_evidence(evidence, project, artifacts, plan, state, head):
    phases = []
    for row in phase_rows(state):
        n = row["n"]
        items = []
        report = mapping(row.get("report"))
        lines = text_lines(report, (("became", "Result"), ("skills", "Skills"), ("interfaces", "Interfaces"),
                                    ("checks", "Checks"), ("at", "Recorded (UTC)")))
        lines += [f"- {command} — {outcome}" for command, outcome in mapping(report.get("check_outcomes")).items()
                  if isinstance(outcome, str)]
        commits = report.get("commits")
        if isinstance(commits, list):
            lines += [f"- Commit `{commit}`" for commit in commits if isinstance(commit, str) and SHA.fullmatch(commit)]
        evidence.document(items, f"report-{n}", "Phase report", "\n\n".join(lines))

        brief = plan.with_name(f"{plan.stem}.brief-implementer-{n}.md")
        if text_file(project, brief) and (section := pipeline.phase_brief_text(head, n)):
            evidence.document(items, f"brief-{n}", "Implementation brief", "\n".join(section))

        if artifacts is not None:
            area = artifacts / f"phase-{n}"
            for name in children(project, area):
                add_artifact(evidence, items, f"phase-{n}-artifact-{checksum_key(name)}", project, artifacts,
                             str(project / area / name), name)
        executor = mapping(row.get("executor"))
        assignment = ({"role": "Implementer", "provider": value_of(executor, "provider"), "model": value_of(executor, "model"),
                       "effort": value_of(executor, "effort"), "profile": value_of(executor, "tier")} if executor else None)
        waits = row.get("waits")
        phases.append({"id": str(n), "title": value_of(row, "title") or f"Phase {n}",
                       "status": value_of(row, "status") or "unknown",
                       "prerequisites": [str(i) for i in waits if type(i) is int and i > 0] if isinstance(waits, list) else [],
                       "assignment": assignment, "evidence": items,
                       "territory": [item for item in row.get("territory", []) if isinstance(item, str)]
                                    if isinstance(row.get("territory"), list) else [],
                       "report": {"became": value_of(report, "became"), "at": value_of(report, "at"),
                                  "checkOutcomes": {k: v for k, v in mapping(report.get("check_outcomes")).items()
                                                    if isinstance(v, str)}} if report else None})
    return phases


def verification_evidence(evidence, project, artifacts, state, verification, human):
    checks, results = [], []
    for index, cycle in enumerate(records(state.get("cycles")), 1):
        label = "Gate" if cycle.get("kind") == "gate" else f"Round {cycle.get('n', index)}"
        for n, run in enumerate(records(cycle.get("runs")), 1):
            head = value_of(run, "head")
            checks.append(f"## {label} — run {n}" + (f" at `{head[:7]}`" if head else "")
                          + ("" if run.get("done") else " (incomplete)"))
            for command in records(run.get("commands")):
                if name := value_of(command, "command"):
                    exit_code = command.get("exit")
                    result = f"failed (exit {exit_code})" if command.get("red") or exit_code else "passed" if exit_code == 0 else "unknown"
                    checks.append(f"- {name} — {result}")
        latest = {r["case"]: r for r in records(cycle.get("results")) if type(r.get("case")) is int}
        for case, result in latest.items():
            title = f"{label} · case {case}"
            capture = value_of(result, "capture")
            details = text_lines(result, (("outcome", "Outcome"), ("do", "Action"), ("see", "Expected"), ("detail", "Observed"), ("width", "Width")))
            if capture:
                key = f"capture-{index}-{case}"
                if add_artifact(evidence, verification, key, project, artifacts, capture, title):
                    if human is not None:
                        add_artifact(evidence, human, f"human-{key}", project, artifacts, capture, title)
                elif capture_path(capture):
                    details.append("Recorded capture unavailable.")
                else:
                    evidence.document(verification, key, title, capture, kind="text")
                    if human is not None:
                        evidence.document(human, f"human-{key}", title, capture, kind="text")
            results.extend([f"## {title}", *details])
    evidence.document(verification, "checks", "Check outcomes", "\n\n".join(checks))
    evidence.document(verification, "verification", "Verification results", "\n\n".join(results))


def handoffs(evidence, project, state, artifacts, base, stages):
    for row in records(state.get("verdicts")):
        n = row.get("n")
        if type(n) is not int:
            continue
        lines = text_lines(row, (("kind", "Verdict"), ("report", "Report"), ("cycle", "Cycle"),
                                 ("head", "Commit"), ("evidence_note", "Evidence exception"), ("owed", "Evidence owed by"),
                                 ("question", "Question"), ("answer", "Answer")))
        for decision in records(row.get("decisions")):
            lines += [" — ".join(line for key in ("id", "action", "reason") if (line := value_of(decision, key)))]
        evidence.document(stages["judge"], f"verdict-{n}", f"Verdict {n}", "\n\n".join(lines))

    human = stages["human-review"]
    page = mapping(state.get("page"))
    evidence.document(human, "human-guide", "Human review guide", value_of(page, "note"))
    lands = records(state.get("lands"))
    if lands:
        land = lands[-1]
        tip = value_of(land, "tip")
        if base and tip and SHA.fullmatch(base) and SHA.fullmatch(tip):
            evidence.ref(human, "land-diff", "Landed changes", "diff", lambda: git_diff(project, base, tip),
                         revision=f"{base}-{tip}")
        for commit in records(land.get("shape")):
            if (sha := value_of(commit, "sha")) and SHA.fullmatch(sha):
                message = (value_of(commit, "message") or sha[:7]).splitlines()[0]
                evidence.ref(human, f"commit-{sha}", f"Commit: {message}", "diff", lambda sha=sha: git_diff(project, sha),
                             revision=sha)
    verification_evidence(evidence, project, artifacts, state, stages["build-verification"], human if page or lands else None)


def public_companions(evidence, project, plan, proposal, state, stage_items):
    sections = []
    for key, names in (("route", ("grill", "prototype")), ("finish", ("how", "target")),
                       ("executors", ("primary", "secondary"))):
        section = mapping(proposal.get(key))
        lines = []
        for name in names:
            if key == "executors":
                lines += text_lines(mapping(section.get(name)), (("provider", f"{name} provider"),
                                                                 ("model", f"{name} model"), ("effort", f"{name} effort")))
            elif value := value_of(section, name):
                lines.append(f"- {name}: {value}")
        if lines:
            sections += [f"## {key.capitalize()}", *lines]
    evidence.document(stage_items["plan"], "run-configuration", "Run configuration", "\n\n".join(sections))
    cycles = records(state.get("cycles"))
    if not cycles:
        return
    fixed = {
        "reviewer": "build-verification", "verify": "build-verification", "fix": "build-verification",
        "judge": "judge", "round": "build",
    }
    pattern = re.compile(rf"{re.escape(plan.stem)}\.brief-(reviewer|verify|fix|judge|round)-([a-z0-9-]+)\.md")
    scopes = {role: set() for role in fixed}
    for cycle in cycles:
        n = cycle.get("n")
        label = "gate" if cycle.get("kind") == "gate" else f"round-{n}" if type(n) is int else None
        if label is None:
            continue
        for role in ("reviewer", "verify", "judge"):
            scopes[role].add(label)
        scopes["reviewer"].add(f"{label}-baseline")
        for fix in records(cycle.get("fixes")):
            if type(number := fix.get("n")) is int:
                for role in ("reviewer", "verify"):
                    scopes[role].add(f"{label}-fix-{number}")
                scopes["fix"].add(f"{label}-{number}")
    scopes["round"].update(str(row["n"]) for row in records(state.get("rounds")) if type(row.get("n")) is int)
    for name in children(project, plan.parent):
        if not (match := pattern.fullmatch(name)):
            continue
        role, assignment = match.groups()
        if assignment not in scopes[role] and (role not in ("reviewer", "verify")
                or not assignment.rpartition("-")[2].isdigit() or assignment.rpartition("-")[0] not in scopes[role]):
            continue
        body = text_file(project, plan.with_name(name))
        if not body or not body.startswith(f"# Brief: {role} — ") or not re.search(r"(?m)^Assignment binding: [a-f0-9]{64}$", body):
            continue
        description = "Saved assignment instructions. A brief does not confirm dispatch."
        evidence.document(stage_items[fixed[role]], f"public-brief-{checksum_key(name)}", name,
                          f"## {role.capitalize()} assignment\n\nScope: {assignment}\n\n{description}")


def task_view(project, task_id, plan, trees, catalogs, engines=None):
    evidence = Evidence()
    task = {"id": task_id, "title": task_id, "status": "planned", "stage": None, "branch": None,
            "worktree": None, "stages": [], "phases": []}
    if plan is None:
        return {**task, "summary": "Multiple registrations claim this task ID. Restore one registration."}, evidence

    record = content(project, plan.with_suffix(".task.json"), json.loads)
    state_path = plan.with_suffix(".json")
    state = content(project, state_path, json.loads)
    status = value_of(state, "status") or ""
    if (state.get("version") != 1 or state.get("plan") != plan.name or not list(phase_rows(state))
            or status not in PLAN_STATUSES and not status.startswith("http")):
        state = {}
        status = None
    outcome = content(project, plan.with_suffix(release.TASK_OUTCOME_SUFFIX), json.loads)
    outcome_name, outcome_stage = value_of(outcome, "outcome"), value_of(outcome, "stage")
    outcome_missing = False
    if (outcome_name not in release.TASK_OUTCOMES.values() or outcome_stage not in STAGE_IDS | {"reproduce"}
            or not all(value_of(outcome, key) for key in ("by", "reason", "at"))):
        outcome_missing = plan.with_suffix(release.TASK_OUTCOME_SUFFIX).name in children(project, plan.parent)
        outcome, outcome_name, outcome_stage = {}, None, None
    discovery = mapping(content(project, plan.with_suffix(".discovery.json"), json.loads).get("stages"))
    proposal = content(project, plan.with_suffix(".run.toml"), tomllib.loads)
    run = mapping(state.get("run")) or proposal
    executors = {}
    for tier in ("primary", "secondary"):
        profile = mapping(mapping(run.get("executors")).get(tier))
        if profile:
            executors[tier] = {field: value_of(profile, field) for field in ("provider", "model", "effort")}

    plan_source = text_file(project, plan)
    head, _ = pipeline.split_gate(pipeline.markdown_newlines(plan_source or "").split("\n"))
    header = pipeline.header_of(head)
    status_match = next((match for line, hidden in zip(header, pipeline.fenced(header))
                         if not hidden and (match := pipeline.STATUS_LINE.match(line))), None)
    heading = (pipeline.plan_title(head) or "").strip()
    branch = value_of(record, "branch") or value_of(state, "branch") or (status_match[2] if status_match else None)
    base = value_of(record, "base") or value_of(state, "base") or (status_match[3] if status_match else None)
    problems = []

    pin = value_of(record, "release")
    if pin is None:
        try:
            pin = release.release_pin(run, plan)
        except release.ReleaseError:
            pin = ""
    definition, bundle, manifest, pinned = available_catalog(pin, catalogs)
    if not pinned:
        problems.append("Pinned stage definitions are unavailable. Stage labels use the installed viewer's definitions.")
    if branch and branch not in trees and status != "merged":
        problems.append("The recorded branch has no available worktree.")
    if plan_source is None and state:
        problems.append("Plan Markdown is unavailable.")

    stopped = not state and (pipeline.was_compiled(head) or state_path.name in children(project, plan.parent))
    if stopped:
        problems.append(f"Compiled state is unavailable. Restore {state_path.name} from a known-good copy.")
    route = {**dict.fromkeys(release.ROUTE_STAGES, "ask"), **mapping(definition.get("route")), **mapping(run.get("route"))}
    optional = {k: value_of(mapping(discovery.get(k)), "status") or ("skipped by route" if route[k] == "skip" else None)
                for k in release.ROUTE_STAGES}
    history = pipeline.optional_workflow_history(head)
    optional = {k: v or (history[k] if state else None) for k, v in optional.items()}
    is_bug = record.get("bug") is True or outcome_stage == "reproduce"
    if is_bug:
        optional = dict.fromkeys(release.ROUTE_STAGES, "not applicable")
        optional["reproduce"] = value_of(mapping(discovery.get("reproduce")), "status")
    optional.update({k: v for k, v in mapping(outcome.get("optional_stages")).items()
                     if k in release.ROUTE_STAGES and isinstance(v, str)})
    workflow = {}
    if outcome_name:
        target, current = outcome_name, outcome_stage
        if reason := value_of(outcome, "reason"):
            problems.insert(0, reason)
    elif outcome_missing:
        target, current = "active", None
        problems.append("Task outcome is unavailable. Restore the saved outcome before relying on the current stage.")
    elif status == "merged":
        target, current = "merged", "finish"
    elif stopped:
        target, current = "active", None
    elif status:
        target, current = ("planned" if status in ("draft", "approved") else "active"), None
        if engines is not None:
            if pinned and plan_source is not None:
                workflow = compiled_route(project, plan, bundle, pin, engines)
                current = workflow.get("stage")
            if current is None:
                problems.append("Current stage is unavailable. Check the pinned release, plan records and task worktree.")
    else:
        candidates = ("reproduce",) if is_bug else tuple(k for k in definition["order"] if k in release.ROUTE_STAGES)
        current = ("plan" if state else next((k for k in candidates if optional[k] not in ("done", "skipped", "skipped by route")), "plan"))
        target = "active" if any(value_of(row, "status") == "active" for row in discovery.values() if isinstance(row, dict)) else "planned"
    if not pinned and target in ("active", "planned"):
        current = None

    order = list(definition["order"])
    if is_bug:
        order.insert(order.index("plan"), "reproduce")
    stage_items = {key: [] for key in order}
    summaries = {}
    # A flat plan has no task-owned artifact directory.
    artifacts = plan.parent / "artifacts" if plan.parent != PLANS and record else None
    for name in ("grill", "prototype", "reproduce"):
        if name not in stage_items or not (data := mapping(discovery.get(name))):
            continue
        lines = text_lines(data, (("status", "Status"), ("result", "Result"), ("reason", "Reason"),
                                  ("command", "Reproduction command"), ("entered", "Entered (UTC)"), ("closed", "Closed (UTC)")))
        questions = data.get("questions")
        if isinstance(questions, list):
            lines.extend(f"- Open question: {q}" for q in questions if isinstance(q, str))
        evidence.document(stage_items[name], f"discovery-{name}", "Discovery decisions", "\n\n".join(lines))
        if artifact := value_of(data, "artifact"):
            if not add_capture(evidence, stage_items[name], f"capture-{name}", project, artifacts, artifact, "Recorded capture"):
                summaries[name] = "The recorded capture is unavailable."
    evidence.document(stage_items["plan"], "plan", "Plan", "\n".join(head))
    handoffs(evidence, project, state, artifacts, base, stage_items)
    notes = [n for n in records(state.get("notes")) if n.get("by") in ("human", "user") and n.get("cause") != "task"]
    if notes:
        lines = [f"## Note {n['n']}\n\n{value_of(n, 'text')}" for n in notes
                 if type(n.get("n")) is int and value_of(n, "text")]
        evidence.document(stage_items["human-review"], "human-notes", "Recorded human notes", "\n\n".join(lines))
    if lands := records(state.get("lands")):
        landed = lands[-1]
        shape = [f"- {value_of(commit, 'message')} — {value_of(commit, 'walkthrough') or 'No walkthrough recorded'}"
                 for commit in records(landed.get("shape")) if value_of(commit, "message")]
        evidence.document(stage_items["judge"], "land-shape", "Recorded land shape", "\n\n".join(shape))
        stage_items["judge"].extend(ref for ref in stage_items["plan"] if ref["id"] == "plan")
    public_companions(evidence, project, plan, proposal, state, stage_items)
    phases = phase_evidence(evidence, project, artifacts, plan, state, head)
    for phase in phases:
        stage_items["build"].extend(phase["evidence"])
    cleanup = target == "merged" and bool(state.get("cleanup_pending"))
    if decisions := records(state.get("decisions")):
        text = "\n\n".join("\n".join(text_lines(row, (("question", "Question"), ("answer", "Decision"),
                         ("why", "Reason"), ("cost", "Cost if wrong")))) for row in decisions)
        evidence.document(stage_items["build"], "build-decisions", "Build decisions", text)

    closed = target in ("completed", "cancelled", "merged")
    current_index = order.index(current) if current in order else None
    stages = []
    for index, key in enumerate(order):
        stage = definition["stages"].get(key, {"label": "Reproduce", "purpose": "Record a failing reproduction of the bug."})
        status = ("unknown" if current_index is None else "current" if index == current_index
                  else "complete" if index < current_index else "upcoming")
        status = optional.get(key) or status
        if current_index == index and closed and not cleanup and status in ("current", "active", "upcoming", "unknown"):
            status = "complete" if target == "merged" else "closed"
        if closed and status in ("active", "current") and not (cleanup and key == "finish"):
            status = "closed"
        if pinned:
            label = STAGE_LABELS.get(key, stage["label"])
            guides = {STAGE_GUIDES[key]: f"{label} guide"} if key in STAGE_GUIDES else {}
            for link, title in {**guides, **mapping(stage.get("references"))}.items():
                path = Path(link)
                if path.suffix not in (".md", ".toml") or manifest and link not in manifest or not isinstance(title, str):
                    continue
                evidence.file(stage_items[key], f"reference-{key}-{checksum_key(link)}", title,
                              "markdown" if path.suffix == ".md" else "text",
                              bundle, path, reference=True, checksum=manifest.get(link, [None])[0])
        summary = summaries.get(key) or value_of(stage, "purpose")
        display_label = STAGE_LABELS.get(key, stage["label"]) if stage["label"] in (
            "Grill (optional)", "Prototype (optional)", "Reproduce", "Build verification") else stage["label"]
        display = badge(status)
        for item in stage_items[key]:
            label = ("Workflow reference" if item.get("role") == "reference" else
                     "Run configuration" if item["id"] == "run-configuration" else
                     "Record" if item["id"].startswith("discovery-") else
                     "Brief" if "brief" in item["id"] else
                     "Plan" if item["id"] == "plan" else "Guide" if item["id"] == "human-guide" else
                     "Source" if item["kind"] == "diff" else "Artifact")
            item.update(label=label, badge=badge("record" if label == "Record" else "reference", label))
            if item["id"] == "plan":
                item["sourceName"] = plan.name
            elif item["id"] == "human-guide":
                item["sourceName"] = f"{plan.name}#human-gate"
            elif item["id"] == "run-configuration":
                item["sourceName"] = plan.with_suffix(".run.toml").name
            elif item["id"].startswith("discovery-"):
                item["sourceName"] = plan.with_suffix(".discovery.json").name
            elif "sourceName" in item and item["kind"] in ("image", "html"):
                item["caption"] = "Saved artifact" if key == "prototype" else "Recorded capture"
        stages.append({"id": key, "label": display_label, "status": status, "statusLabel": display["text"],
                       "statusTone": display["tone"], "displayStatus": display,
                       "evidence": stage_items[key], **({"summary": summary} if summary else {})})

    task.update(title=(value_of(state, "title") or heading or value_of(record, "goal") or task_id).removeprefix("Plan: "),
                status=target, stage=current, branch=branch, worktree=trees.get(branch), stages=stages,
                phases=phases, executors=executors)
    task.update(task_display(task, project, record, state, stopped))
    for stage in stages:
        stage["overview"] = overview(stage["id"], stage, task, state, discovery, proposal, run, workflow,
                                     {item["id"] for item in stage["evidence"]})
    if problems:
        task["summary"] = " ".join(problems)
    return task, evidence


def worktrees(project):
    try:
        return {branch: str(path) for path, branch in release.worktrees(project) if branch and path.is_dir()}
    except release.ReleaseError:
        return {}


def project_snapshot(project: Path) -> dict:
    """Return the browser-visible project inventory and associated evidence references."""
    project = Path(project).resolve()
    trees, catalogs, engines = worktrees(project), {}, {}
    tasks = [task_view(project, task_id, plan, trees, catalogs, engines)[0] for task_id, plan in sorted(inventory(project).items())]
    return {"project": {"name": project.name, "path": str(project)}, "tasks": tasks}


def read_evidence(project: Path, task: str, evidence_id: str) -> tuple[str, bytes] | None:
    """Resolve an opaque evidence ID from its own task's current records."""
    if not release.TASK_ID.fullmatch(task):
        return None
    project = Path(project).resolve()
    if plan := inventory(project).get(task):
        return task_view(project, task, plan, {}, {})[1].read(evidence_id)
    return None
