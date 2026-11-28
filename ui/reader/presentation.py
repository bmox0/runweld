"""Public display facts derived from a task's records."""
from datetime import datetime
from pathlib import Path


TONES = {
    "current": "orange", "active": "orange", "in progress": "orange", "open": "orange",
    "complete": "green", "done": "green", "passed": "green", "merged": "green",
    "failed": "red", "cancelled": "red", "blocked": "amber", "waiting": "amber", "stale": "amber",
    "unknown": "amber", "pending": "amber", "upcoming": "neutral", "record": "blue",
    "accepted": "green", "prepared": "orange", "ready": "orange",
}
LABELS = {"complete": "Finished", "done": "Finished", "unknown": "Not recorded"}


def mapping(value):
    return value if isinstance(value, dict) else {}


def records(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def text(record, key):
    value = record.get(key)
    return value.encode("utf-8", "replace").decode() if isinstance(value, str) and value.strip() else None


def badge(status, label=None):
    return {"text": label or LABELS.get(status) or status.capitalize(), "tone": TONES.get(status, "neutral")}


def row(title, state=None, detail=None, **links):
    return {"title": str(title), **({"status": badge(state)} if state else {}),
            **({"detail": detail} if detail else {}), **links}


def utc(stamp):
    try:
        date = datetime.fromisoformat(stamp)
        return f"{date.day} {date:%b %Y · %H:%M:%S}"
    except (TypeError, ValueError):
        return stamp


def short(value):
    return value[:7] if isinstance(value, str) else None


def profile(run, tier):
    return " / ".join(value for key in ("provider", "model", "effort") if (value := text(mapping(run.get(tier)), key))) or None


def task_display(task, project, record, state, stopped):
    status = task["status"]
    raw = text(state, "status")
    stage = next((item["label"] for item in task["stages"] if item["id"] == task["stage"]), None)
    label = "Stopped" if stopped else {
        "merged": "Merged", "completed": "Completed", "cancelled": "Cancelled",
    }.get(status) or ("Merge request open" if raw and raw.startswith("http")
                     else raw.capitalize() if raw else stage or "Not recorded")
    tone = status if status not in ("active", "planned") else "active" if raw != "passed" else "passed"
    group = {"planned": "plans", "merged": "completed"}.get(status, status)
    inventory_status = f"Current · {stage}" if stage and status == "active" else f"{label} · {stage}" if stage and stage != label else label
    sidebar_status = stage if stage and status in ("completed", "cancelled") else label
    where = task["worktree"]
    registered = bool(record)
    if where and (registered or where != str(project)):
        mode, location, value = "worktree", "Worktree", where
        try:
            value = str(Path(where).relative_to(project))
        except ValueError:
            pass
    elif not registered and (where == str(project) or text(state, "tree") == str(project)):
        mode, location, value = "branch-only", "Execution", "Branch only (legacy)"
    elif status == "merged" and registered and not state.get("cleanup_pending"):
        mode, location, value = "cleaned", "Worktree", "Cleaned up"
    elif task["branch"]:
        mode, location, value = "missing", "Worktree", "Unavailable"
    else:
        mode, location, value = "unassigned", "Worktree", "Not assigned"
    return {
        "workspaceTitle": task["id"],
        "displayStatus": badge(tone, label),
        "sidebar": {"detail": f"{group.capitalize()} · {sidebar_status}", "tone": badge(tone)["tone"]},
        "inventory": {"group": group, "subtitle": task["id"], "detail": "Local task" if registered else "Legacy plan",
                      "execution": value if mode != "worktree" else location, "status": badge(tone, inventory_status)},
        "execution": {"mode": mode, "label": location, "value": value},
    }


def overview(key, stage, task, state, discovery, proposal, run, work, files):
    facts, groups = [], []
    heading, summary, action = "Stage overview", None, None

    def fact(label, value):
        if value is not None:
            facts.append({"label": label, "value": str(value)})

    def group(title, rows):
        if rows:
            groups.append({"title": title, "rows": rows})

    assigned = records(work.get("actions"))
    live = task["stage"] == key and task["status"] not in ("completed", "cancelled", "merged")
    if live and assigned and (body := text(assigned[0], "action")):
        action = {"text": body, "owner": text(assigned[0], "owner")}
    current = mapping(records(state.get("cycles"))[-1]) if records(state.get("cycles")) else {}
    label = "gate" if current.get("kind") == "gate" else f"round-{current['n']}" if type(current.get("n")) is int else None
    runs = records(current.get("runs"))
    selected = current.get("current_run", -1)
    checked = runs[selected] if runs and type(selected) is int and -1 <= selected < len(runs) else {}
    result_map = {r.get("case"): r for r in records(current.get("results")) if type(r.get("case")) is int}
    reviews = records(current.get("reviews"))
    verdicts = records(state.get("verdicts"))
    verdict = verdicts[-1] if verdicts else {}
    lands = records(state.get("lands"))
    land = lands[-1] if lands else {}
    rounds = records(state.get("rounds"))
    round_ = rounds[-1] if rounds else {}
    acceptance = mapping(state.get("acceptance"))
    page = mapping(state.get("page"))
    integration = mapping(state.get("integration"))
    finish = mapping(run.get("finish"))
    verification = mapping(work.get("verification"))

    if key in ("grill", "prototype", "reproduce"):
        saved = mapping(discovery.get(key))
        questions = [q for q in saved.get("questions", []) if isinstance(q, str) and q.strip()] if isinstance(saved.get("questions"), list) else []
        summary = text(saved, "reason") or text(saved, "result")
        if not summary:
            summary = {"grill": "No discussion has been recorded.", "prototype": "No prototype has been requested or saved.",
                       "reproduce": "No red reproduction has been recorded."}[key]
            if stage["status"] == "active":
                summary = f"{stage['label']} has been entered. No result is saved yet."
        if saved.get("status") == "skipped" and not saved.get("entered"):
            fact("Participation", "Skipped before entry")
        fact("Questions saved", len(questions) if questions else "None")
        fact("Entered (UTC)", utc(text(saved, "entered")))
        fact("Closed (UTC)", utc(text(saved, "closed")))
        if key == "prototype" and any(item["kind"] in ("html", "image") for item in stage["evidence"]):
            fact("Output", "HTML" if any(item["kind"] == "html" for item in stage["evidence"]) else "Image")
        group("Saved questions", [row(q, "waiting", "Awaiting human answer") for q in questions])
        if command := text(saved, "command"):
            capture = next((ref["id"] for ref in stage["evidence"] if ref["id"].startswith("capture-")), None)
            group("Reproduction evidence", [row("Reproduction command", "failed", command, **({"evidenceId": capture} if capture else {}))])
        if live and not action and (questions or not saved or stage["status"] == "active"):
            action = {"owner": "Human" if questions else "Planner",
                      "text": "Resolve the saved questions." if questions
                      else f"Record the result with runweld {'bug' if key == 'reproduce' else key} done PLAN." if saved
                      else f"Enter this stage with runweld {'bug' if key == 'reproduce' else key} start PLAN."}
    elif key == "plan":
        approval = mapping(mapping(state.get("approvals")).get("plan"))
        if state.get("status") == "approved":
            summary = "The plan was approved. The build still needs a separate start instruction."
        elif approval:
            summary = "The plan and its approved run configuration are recorded."
        elif state:
            summary = "The plan and run configuration can be reviewed for approval."
        else:
            summary = "No reviewed plan has been recorded."
        fact("Plan", "Compiled" if state else "Draft" if "plan" in files else "Not recorded")
        fact("Run configuration", "Recorded" if proposal else "Not recorded")
        fact("Approval", "Recorded" if approval else "Not recorded")
        group("Recorded work", [row("Plan and run configuration", "complete" if approval else "waiting",
                                   "Review the revision together before approval.", **({"evidenceId": "plan"} if "plan" in files else {}))])
        if live and not action and "plan" in files:
            action = {"owner": "Planner", "text": "Validate the draft before requesting approval."}
    elif key == "build":
        phases = task["phases"]
        done = {p["id"] for p in phases if p["status"] == "done"}
        ready = {p["id"] for p in phases if p["status"] == "waiting" and set(p["prerequisites"]) <= done}
        active = [p for p in phases if p["status"] == "in progress"]
        summary = ("The current build work is recorded below." if phases else "No phases are recorded for this task.")
        if live and active:
            fact("Active phases", len(active))
            fact("Blocked by dependencies", sum(p["status"] == "waiting" and p["id"] not in ready for p in phases))
        else:
            fact("Coordinator", profile(task["executors"], "primary"))
            fact("Ready", len(ready) if live else None)
            fact("Reported", f"{len(done)} of {len(phases)}" if phases else None)
        phase_rows = []
        for p in phases:
            needed = [n for n in p["prerequisites"] if n not in done]
            report = mapping(p.get("report"))
            outcomes = mapping(report.get("checkOutcomes"))
            failed = next((v for v in outcomes.values() if isinstance(v, str) and v.startswith("failed")), None)
            detail = failed or text(report, "became")
            if not detail and needed:
                detail = "Waits for phases " + ", ".join(needed) + "."
            if not detail and p.get("territory"):
                detail = ", ".join(p["territory"])
            phase_rows.append(row(f"{p['id']} · {p['title']}", "blocked" if failed and p["status"] == "in progress"
                                  else "ready" if live and p["id"] in ready else p["status"], detail, phaseId=p["id"]))
        group("Build phases", phase_rows)
        if round_ and not round_.get("done"):
            fact("Round", round_.get("n"))
    elif key == "build-verification":
        summary = ("The current check cycle records reviews, checks and verification results."
                   if current else "No check cycle has been recorded.")
        fact("Gate", text(current, "level") or text(state, "level"))
        fact("Cycle", label)
        fact("HEAD", short(text(checked, "head")))
        command_rows = []
        recorded_commands = records(checked.get("commands"))
        for index, command in enumerate(checked.get("full", [])) if isinstance(checked.get("full"), list) else []:
            result = recorded_commands[index] if index < len(recorded_commands) else {}
            exit_code = result.get("exit")
            command_rows.append(row(command, "failed" if result.get("red") or exit_code else
                                    "passed" if exit_code == 0 else "pending",
                                    f"Exit {exit_code}" if type(exit_code) is int else None))
        if reviews or current:
            latest = reviews[-1] if reviews else {}
            command_rows.append(row("Reviewer", "complete" if verification.get("reviewCurrent") else
                                    "stale" if live and reviews and verification else "pending" if live else "recorded",
                                    text(latest, "range")))
        required = {n for n in verification.get("pendingCases", []) if type(n) is int}
        for done in records(state.get("done")) if current else []:
            case = done.get("n")
            result = result_map.get(case, {})
            if current.get("level") == "small" or done.get("you_check"):
                status = "you check"
            elif case in required:
                status = "stale" if result else "pending"
            else:
                status = text(result, "outcome") or "pending"
            command_rows.append(row(f"Done {case} · {text(done, 'text') or 'Verification'}", status, text(result, "detail")))
        for step in assigned if live else []:
            owner = text(step, "owner")
            assignment = mapping(step.get("assignment"))
            if owner == "Verify" and (assignment or step.get("kind") == "work"):
                command_rows.append(row(owner, "prepared" if assignment.get("brief") else "pending",
                                        text(assignment, "range") or ", ".join(map(str, assignment.get("cases", [])))))
                break
        group("Recorded work", command_rows)
        fixes = records(current.get("fixes"))
        fix = fixes[-1] if fixes else {}
        items = set(i for i in fix.get("items", []) if isinstance(i, str)) if isinstance(fix.get("items"), list) else set()
        if fix:
            fact("Assignment", f"{label}-fix-{fix.get('n')}")
            fact("From", short(text(fix, "from")))
        work_list = [row(f"check-{i} · {text(check, 'command') or 'Check'}", "failed",
                         "Taken by the fix" if f"check-{i}" in items else None)
                     for i, check in enumerate(recorded_commands, 1) if check.get("red") or check.get("exit")]
        for finding in records(current.get("findings")):
            id_ = text(finding, "id")
            kind = text(finding, "kind")
            work_list.append(row(f"{id_ or 'Finding'} · {text(finding, 'text') or kind or 'Recorded'}",
                                 "in fix" if id_ in items else "for judge" if kind == "convention" else kind,
                                 text(finding, "where")))
        group("Fix and review findings", work_list)
    elif key == "judge":
        current_verdict = verdict if label and verdict.get("cycle") == label else {}
        land_cycle = next((text(v, "cycle") for v in verdicts if v.get("n") == land.get("judge")), None) if land.get("judge") is not None else None
        current_land = bool(label and land_cycle == label)
        fact("Cycle", label)
        fact("Checked HEAD", short(text(current_verdict, "head") or text(checked, "head")))
        fact("Executor", profile(task["executors"], "primary"))
        fact("Verdict", text(current_verdict, "kind"))
        fact("Landed tip", short(text(land, "tip")) if current_land else None)
        summary = text(current_verdict, "report") or ("A current review and verification handoff can open Judge."
                                                      if current else "No verdict has been recorded.")
        if current_verdict.get("kind") == "question" and not current_verdict.get("answer") and live:
            heading = text(current_verdict, "question") or "A decision is needed"
        if live and any(step.get("input") == "land-difference" for step in assigned):
            heading = "Land differs from the checked tree"
            summary = "The Judge must accept or revert the recorded land difference before human review."
        work_rows = []
        if checked:
            work_rows.append(row("Check run", "passed" if verification.get("checksCurrent") and not any(c.get("red") for c in records(checked.get("commands"))) else "recorded"))
        if reviews:
            work_rows.append(row("Reviewer", "complete" if verification.get("reviewCurrent") else "recorded", text(reviews[-1], "range")))
        if result_map:
            work_rows.append(row("Verify", "recorded", ", ".join(f"Done {n}" for n in sorted(result_map))))
        if round_:
            work_rows.append(row(f"Round {round_.get('n')}", "complete" if round_.get("done") else "pending",
                                 text(mapping(round_.get("report")), "became")))
        if land:
            backup = text(land, "backup")
            if current_land:
                work_rows.append(row(f"Land {land.get('n')}", "waiting" if land.get("difference") and not land.get("accepted") else "complete", backup))
            else:
                work_rows.append(row(f"Historical land {land.get('n')}", "recorded",
                                     " · ".join(filter(None, (land_cycle, short(text(land, "tip")), backup)))))
        group("Recorded work", work_rows)
    elif key == "human-review":
        summary = "The guide records how to review the landed result." if page else "No human review page has been recorded."
        if round_ and not round_.get("done"):
            fact("Round", round_.get("n"))
        fact("Accepted by", text(acceptance, "by"))
        fact("Recorded (UTC)", utc(text(acceptance, "at")))
        ending = mapping(page.get("ending"))
        if text(ending, "how") and text(ending, "target"):
            fact("Ending", f"{ending['how']} into {ending['target']}")
        notes = [n for n in records(state.get("notes")) if n.get("by") in ("human", "user") and n.get("cause") != "task"]
        if any(n.get("round") is None for n in notes):
            heading = "Start a round?"
            summary = "Feedback can be recorded without authorizing a new round."
        rows = [row(f"Note {n.get('n')}", "open" if n.get("round") is None else "recorded", text(n, "text")) for n in notes]
        scoped = set(n for n in round_.get("notes", []) if type(n) is int) if isinstance(round_.get("notes"), list) else set()
        if scoped and any(n.get("n") in scoped for n in notes):
            rows.append(row(f"Round {round_.get('n')}", "complete" if round_.get("done") else "recorded", "Human-authorized scope"))
        if page:
            accepted = bool(acceptance) and task["stage"] == "finish"
            rows.append(row("Current page" if accepted else "Review guide", "accepted" if accepted else "recorded",
                            **({"evidenceId": "human-guide"} if "human-guide" in files else {})))
        group("Recorded work", rows)
    elif key == "finish":
        reason = text(state, "cleanup_pending")
        request = text(state, "status")
        link = request if request and request.startswith("http") else text(integration, "request")
        integrated = task["status"] == "merged"
        fact("Strategy", text(integration, "how") or text(finish, "how"))
        fact("Target", text(integration, "target") or text(finish, "target"))
        fact("Integrated commit" if integrated else "Accepted tip", short(text(integration, "commit") or text(land, "tip")))
        summary = ("Integration succeeded. Cleanup is still pending." if integrated and reason else
                   "The recorded integration has no pending cleanup." if integrated else
                   "The linked request is pending confirmation." if link else
                   "The accepted result is ready for the approved finish." if live and acceptance else
                   "No integration has been recorded.")
        if integrated and reason:
            heading = "Safe cleanup retry"
            action = {"owner": "Coordinator", "text": "Resolve the cleanup hold and retry with runweld finish --json PLAN."}
        work_rows = [row("Integration", "complete" if integrated else "pending")]
        if link:
            work_rows.insert(0, row("Request", "complete" if integrated else "open", link))
        if reason or integrated or link:
            work_rows.append(row("Cleanup", "blocked" if reason else "complete" if integrated else "waiting", reason))
        if integrated and task["branch"]:
            work_rows.append(row("Task branch", "retained", task["branch"]))
        group("Recorded work", work_rows)
    return {"heading": heading, "summary": summary or stage.get("summary") or "No overview recorded for this stage.",
            "facts": facts, "groups": groups, **({"next": action} if action and text(action, "text") else {})}
