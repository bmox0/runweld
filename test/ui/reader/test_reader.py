"""dashboard#task-evidence and dashboard#phase-graph — project snapshots and scoped evidence."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SOURCE))
from workflow.build.runweld_release import manifest_bytes, release_id


class ReaderTest(unittest.TestCase):

    def test_registered_pipeline_and_evidence(self):
        """Project recorded task outcomes and phases [dashboard#task-evidence] [dashboard#phase-graph]."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project = root / "fixture project"
            project.mkdir()
            prefix = root / "install"
            cli = prefix / "bin/runweld"
            env = dict({k: v for k, v in os.environ.items() if not k.startswith("RUNWELD_")},
                       GIT_AUTHOR_NAME="Tester", GIT_AUTHOR_EMAIL="test@example.org",
                       GIT_COMMITTER_NAME="Tester", GIT_COMMITTER_EMAIL="test@example.org")

            def run(*args, cwd=project):
                result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout.strip()

            def cli_json(*args, cwd=project):
                return json.loads(run(cli, *args, "--json", cwd=cwd))

            run(SOURCE / "scripts/install-runweld", "--prefix", prefix)
            store = prefix / "lib/runweld/releases"
            release = (store.parent / "default").read_text().strip()
            run("git", "init", "-qb", "main")
            run("git", "commit", "--allow-empty", "-qm", "base")
            run(cli, "onboard", "--apply", "--primary-provider", "Fixture", "--secondary-provider", "Fixture",
                "--primary-model", "Test-Main", "--secondary-model", "Test-Helper", "--secondary-effort", "high", "--no-setup")

            # Exercise the bundled reader and its sibling release store without relying on PATH.
            def read(*args, checkout=project):
                code = (
                    "from pathlib import Path\nimport json, sys\n"
                    "from ui import reader\n"
                    "project = Path(sys.argv[1])\n"
                    "if len(sys.argv) == 2:\n"
                    "    print(json.dumps(reader.project_snapshot(project)))\n"
                    "else:\n"
                    "    result = reader.read_evidence(project, *sys.argv[2:])\n"
                    "    print(json.dumps([result[0], result[1].decode()] if result else None))\n"
                )
                return json.loads(run(sys.executable, "-B", "-c", code, checkout, *args, cwd=store / release))

            self.assertEqual(read()["tasks"], [])

            def start(name):
                return cli_json("task", "start", name, "--goal", f"Goal for {name}",
                                "--finish-how", "ff-only", "--finish-target", "main")

            def rows():
                return {task["id"]: task for task in read()["tasks"]}

            def stage(task, stage_id):
                return next(s for s in task["stages"] if s["id"] == stage_id)

            def docs(task, items):
                return {e["title"]: read(task["id"], e["id"]) for e in items if e.get("role") != "reference"}

            start("planned")
            prototype = start("early")
            early = Path(prototype["plan"])
            run(cli, "grill", "start", early)
            run(cli, "grill", "done", early, "--result", "Keep the directed graph.")
            run(cli, "prototype", "start", early)
            capture = Path(prototype["artifacts"]) / "prototype.html"
            capture.write_text("<h1>Approved prototype</h1>")
            run(cli, "prototype", "done", early, "--result", "Approve the design.", "--artifact", capture)
            cancelled = start("cancelled")
            run(cli, "task", "complete", "early", "--by", "Owner", "--reason", "Goal reached early")
            run(cli, "task", "cancel", "cancelled", "--by", "Owner", "--reason", "Stopped intentionally")
            run("git", "worktree", "remove", prototype["tree"])
            snapshot = rows()
            self.assertEqual({i: (t["status"], t["stage"]) for i, t in snapshot.items()},
                             {"early": ("completed", "plan"), "cancelled": ("cancelled", "grill"),
                              "planned": ("planned", "grill")})
            self.assertIsNone(snapshot["early"]["worktree"])
            self.assertEqual(snapshot["early"]["inventory"]["status"]["text"], "Completed · Plan")
            self.assertEqual(snapshot["cancelled"]["inventory"]["status"]["text"], "Cancelled · Grill")
            with self.subTest("discovery closure retains executor profiles [dashboard#task-evidence]"):
                self.assertEqual(snapshot["early"].get("executors"), {
                    "primary": {"provider": "Fixture", "model": "Test-Main", "effort": None},
                    "secondary": {"provider": "Fixture", "model": "Test-Helper", "effort": "high"},
                })
            self.assertNotIn(stage(snapshot["cancelled"], "grill")["status"], ("current", "active"))
            self.assertIn("Keep the directed graph.", docs(snapshot["early"], stage(snapshot["early"], "grill")["evidence"])["Discovery decisions"][1])
            evidence = stage(snapshot["early"], "prototype")["evidence"]
            html = next(e for e in evidence if e["kind"] == "html")
            self.assertEqual(read("early", html["id"]), ["html", "<h1>Approved prototype</h1>"])
            self.assertIsNone(read("planned", html["id"]))

            previous = root / "previous-payload"
            shutil.copytree(store / release, previous)
            definitions = previous / "references/workflow.toml"
            definitions.write_text(definitions.read_text().replace('label = "Plan"', 'label = "Previous plan"'))
            manifest = manifest_bytes(previous, "7.2.0")
            (previous / "release.json").write_bytes(manifest)
            older = store / release_id("7.2.0", manifest)
            previous.rename(older)
            registration = early.with_suffix(".task.json")
            registration.write_text(json.dumps({**json.loads(registration.read_bytes()), "release": older.name}))
            self.assertEqual(stage(rows()["early"], "plan")["label"], "Previous plan")
            older.rename(previous)
            unavailable = rows()["early"]
            self.assertEqual((unavailable["status"], unavailable["stage"]), ("completed", "plan"))
            self.assertIn("Pinned stage definitions are unavailable", unavailable["summary"])
            self.assertEqual(read("early", html["id"]), ["html", "<h1>Approved prototype</h1>"])

            cli_json("task", "start", "bug", "--bug", "--goal", "Reproduce a bug")
            route = rows()["bug"]["stages"]
            self.assertEqual([item["id"] for item in route[:4]], ["grill", "prototype", "reproduce", "plan"])
            active = start("compiled")
            plan = Path(active["plan"])
            for optional in ("grill", "prototype"):
                run(cli, optional, "skip", plan, "--reason", "Not needed")
            plan.write_text(f"""# Plan: Compiled fixture

Status: draft · branch `runweld/compiled` · base `{active['base']}`

## Result

A dashboard fixture.

## Approach

Implement the fixture.

## Out of scope

- Other changes.

## Phases

### 1. First — `waiting`
Territory: `first.txt`
Skills: none
Spec: none
Waits for: nothing

### 2. Second — `waiting`
Territory: `second.txt`
Skills: none
Spec: none
Waits for: nothing

### 3. Third — `waiting`
Territory: `third.txt`
Skills: none
Spec: none
Waits for: 2 — Second

## Checks

- Gate: normal — fixture

## Done

1. Open the fixture → it shows the result.

## Spec

none
""")
            draft_source = plan.read_text()
            run(cli, "approve", plan)
            plan.with_suffix(".summary.md").write_bytes((SOURCE / "test/lib/summary.md").read_bytes())
            revision = cli_json("plan", "review", plan)["revision"]
            run(cli, "plan", "approve", plan, "--revision", revision, "--by", "Owner", "--words", "Approve")
            run(cli, "build", "start", plan)
            run(cli, "phase", "start", plan, "1")
            run(cli, "phase", "start", plan, "2")
            run(cli, "brief", "implementer", plan, "2")
            tree = Path(active["tree"])
            (tree / "second.txt").write_text("phase two content\n")
            run("git", "add", "second.txt", cwd=tree)
            run("git", "commit", "-qm", "Write phase two", cwd=tree)
            head = run("git", "rev-parse", "HEAD", cwd=tree)
            run(cli, "phase", "report", plan, "2", "--became", "Phase detail",
                "--skills", "none", "--interfaces", "none", "--checks", "test result", "--commit", head)
            task = rows()["compiled"]
            self.assertEqual((task["status"], task["stage"]), ("active", "build"))
            self.assertEqual([p["status"] for p in task["phases"]], ["in progress", "in progress", "waiting"])
            self.assertEqual(task["phases"][2]["prerequisites"], ["2"])
            phase = task["phases"][1]
            self.assertEqual(phase["assignment"], {"role": "Implementer", "provider": "Fixture",
                             "model": "Test-Helper", "effort": "high", "profile": "secondary"})
            self.assertIn("Phase detail", docs(task, phase["evidence"])["Phase report"][1])
            brief = plan.with_name("compiled.brief-implementer-2.md")
            brief.write_text(brief.read_text() + "\nPRIVATE RUN METADATA\n")
            shown = docs(task, phase["evidence"])["Implementation brief"][1]
            self.assertIn("Second", shown)
            self.assertNotIn("PRIVATE RUN METADATA", shown)
            self.assertIn("## Result", docs(task, stage(task, "plan")["evidence"])["Plan"][1])

            def item(task, stage_id, evidence_id):
                return next(e for e in stage(task, stage_id)["evidence"] if e["id"] == evidence_id)

            source = plan.read_text()
            self.assertEqual(task["inventory"]["group"], "active")
            self.assertEqual(task["inventory"]["status"]["text"], "Current · Build")
            self.assertEqual({f["label"]: f["value"] for f in stage(task, "build")["overview"]["facts"]},
                             {"Active phases": "2", "Blocked by dependencies": "1"})
            self.assertTrue(any(row.get("phaseId") == "2" for group in stage(task, "build")["overview"]["groups"]
                                for row in group["rows"]))
            self.assertTrue(any(ref["id"] == "run-configuration" for ref in stage(task, "plan")["evidence"]))

            before = item(task, "plan", "plan")
            plan.write_text(source.replace("A dashboard fixture.", "An updated fixture."))
            after = item(rows()["compiled"], "plan", "plan")
            plan.write_text(source)
            with self.subTest("same document ID exposes its updated revision [dashboard#phase-graph]"):
                self.assertNotEqual(before.get("revision"), after.get("revision"))
                self.assertEqual(before, item(rows()["compiled"], "plan", "plan"))

            state_path = plan.with_suffix(".json")
            state = json.loads(state_path.read_bytes())
            state_path.unlink()
            stopped = rows()["compiled"]
            self.assertIsNone(stopped["stage"])
            self.assertIn("Restore compiled.json", stopped["summary"])
            state_path.write_text(json.dumps(state))

            def agreement(expected):
                self.assertEqual(cli_json("status", plan)["workflow"]["stage"], expected)
                self.assertEqual(rows()["compiled"]["stage"], expected)

            run(cli, "gate", "start", plan, "--note", "Open this fixture gate early.")
            run(cli, "review", "complete", plan, "--assignment", "gate", "--range", f"{active['base']}..{head}")
            run(cli, "result", plan, "--case", "1", "--outcome", "failed", "--detail", "Needs a fix",
                "--capture", "1 task listed")
            with self.subTest("failed verification without reviewer findings needs a fix [dashboard#task-evidence]"):
                agreement("build-verification")
            run(cli, "result", plan, "--case", "1", "--outcome", "passed", "--capture", "2 tasks listed")
            run(cli, "finding", plan, "--kind", "observation", "--where", "second.txt:1", "--text", "Observation only")
            run(cli, "review", "complete", plan, "--assignment", "gate", "--range", f"{active['base']}..{head}")
            with self.subTest("observations do not block the judge [dashboard#task-evidence]"):
                agreement("judge")
            with self.subTest("literal command output is available as text [dashboard#task-evidence]"):
                for capture in ("2 tasks listed", "7/7"):
                    run(cli, "result", plan, "--case", "1", "--outcome", "passed", "--capture", capture)
                    task = rows()["compiled"]
                    result_docs = docs(task, stage(task, "build-verification")["evidence"])
                    self.assertEqual(result_docs.get("Gate · case 1"), ["text", capture])
                    self.assertNotIn("Recorded capture unavailable.", result_docs["Verification results"][1])

            run(cli, "verdict", "pass", plan, "--report", "The fixture is ready.", "--predicted", "pass", "--engine", "Fixture")
            with self.subTest("a current pass stays at Judge [dashboard#task-evidence]"):
                agreement("judge")

            run(cli, "result", plan, "--case", "1", "--outcome", "failed", "--capture", "6/7", "--detail", "One check failed")
            with self.subTest("a prior pass does not mask newly failed evidence [dashboard#task-evidence]"):
                agreement("build-verification")
            run(cli, "result", plan, "--case", "1", "--outcome", "passed", "--capture", "7/7")
            run(cli, "verdict", "pass", plan, "--report", "The fixture is ready again.")

            (tree / "second.txt").write_text("phase two content\nChanged after evidence\n")
            run("git", "commit", "-qam", "Change checked tree", cwd=tree)
            with self.subTest("a prior pass does not mask stale checks [dashboard#task-evidence]"):
                agreement("build-verification")
            run(cli, "gate", "start", plan, "--note", "Refresh checks on the changed tree.")
            new_head = run("git", "rev-parse", "HEAD", cwd=tree)
            run(cli, "review", "complete", plan, "--assignment", "gate", "--range", f"{active['base']}..{new_head}")
            with self.subTest("results at an earlier tree do not open Judge [dashboard#task-evidence]"):
                agreement("build-verification")

            run(cli, "result", plan, "--case", "1", "--outcome", "passed", "--capture", "7/7")
            run(cli, "verdict", "pass", plan, "--report", "Ready for land.")
            with self.subTest("Judge next action does not reveal unrelated worktree paths [dashboard#task-evidence]"):
                unrelated = tree / "unrelated-private-fixture.txt"
                unrelated.write_text("Not task evidence")
                try:
                    workflow = cli_json("status", plan)["workflow"]
                    task = rows()["compiled"]
                    self.assertEqual(task["stage"], workflow["stage"])
                    self.assertEqual(task["stage"], "judge")
                    self.assertIn(unrelated.name, workflow["actions"][0]["action"])
                    next_ = stage(task, "judge")["overview"]["next"]
                    self.assertEqual(next_["owner"], "Coordinator")
                    self.assertNotIn(unrelated.name, str(task))
                    self.assertIn("runweld next", next_["text"])
                finally:
                    unrelated.unlink()
            shape = Path(run(cli, "land", "draft", plan).removeprefix("land draft: "))
            shape.write_text(shape.read_text().replace('message = ""', 'message = "feat: shape the fixture"')
                             .replace('walkthrough = ""', 'walkthrough = "Review the fixture."'))
            hook = project / ".git/hooks/pre-commit"
            hook.parent.mkdir(exist_ok=True)
            run("git", "config", "core.hooksPath", hook.parent)
            hook.write_text("#!/bin/sh\nprintf 'formatter line\\n' >> second.txt\ngit add second.txt\n")
            hook.chmod(0o755)
            run(cli, "land", plan)
            with self.subTest("pending land difference remains at Judge [dashboard#task-evidence]"):
                agreement("judge")
                workflow = cli_json("status", plan)["workflow"]
                self.assertEqual(workflow["actions"][0]["input"], "land-difference")
                overview = stage(rows()["compiled"], "judge")["overview"]
                self.assertIn("accept or revert", overview["summary"])
            hook.unlink()
            run(cli, "land", "revert", plan)

            # Replay historical evidence separately from the validated current route.
            artifacts = Path(active["artifacts"])
            image = artifacts / "human-review.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nfixture image")
            plan.with_suffix(".judge.md").write_text("## Prediction\nPRIVATE JUDGE")
            plan.with_suffix(".notes.md").write_text("PRIVATE NOTES")
            (artifacts / "unrelated.txt").write_text("UNRELATED")
            phase_dir = artifacts / "phase-2"
            phase_dir.mkdir()
            (phase_dir / "fixture.txt").write_text("Phase artifact")
            (phase_dir / "leak.md").symlink_to(plan.with_suffix(".judge.md"))
            (phase_dir / "hardlink.md").hardlink_to(plan.with_suffix(".judge.md"))
            (artifacts / "escape.png").symlink_to(image)
            result = {"case": 1, "capture": str(image), "outcome": "passed", "do": "Open the fixture",
                      "see": "The result appears", "detail": None, "commit": head}
            state.update(
                status="at the human gate", page={"note": "Human guide fixture."},
                cycles=[{"kind": "gate", "n": 1, "results": [result, {**result, "case": 2, "capture": str(artifacts / "escape.png")}],
                         "runs": [{"head": head, "done": True, "commands": [
                             {"command": "scripts/check", "exit": 0, "red": False, "tail": "PRIVATE LOG"}]}]}],
                verdicts=[{"n": 1, "kind": "question", "cycle": "gate", "head": head, "report": "Public verdict.",
                           "question": "Keep the graph?", "answer": "Keep it directed.", "prediction": "PRIVATE PREDICTION"}],
                lands=[{"n": 1, "judge": 1, "tip": head, "shape": [{"sha": head, "message": "Write phase two",
                         "walkthrough": "Add the fixture", "paths": ["second.txt"]}]}],
            )
            state_path.write_text(json.dumps(state))
            task = rows()["compiled"]
            self.assertIsNone(task["stage"])
            self.assertIn("Current stage is unavailable", task["summary"])
            verify = docs(task, [e for e in stage(task, "build-verification")["evidence"] if e["kind"] != "image"])
            self.assertIn("scripts/check — passed", verify["Check outcomes"][1])
            self.assertNotIn("PRIVATE LOG", str(verify))
            self.assertIn("Recorded capture unavailable.", verify["Verification results"][1])
            self.assertNotIn("Gate · case 2", verify)
            judge = docs(task, stage(task, "judge")["evidence"])
            self.assertIn("Public verdict.", judge["Verdict 1"][1])
            self.assertNotIn("PRIVATE", str(judge))
            with self.subTest("the verdict contains the public question and answer [dashboard#task-evidence]"):
                self.assertIn("Keep the graph?", judge["Verdict 1"][1])
                self.assertIn("Keep it directed.", judge["Verdict 1"][1])
            with self.subTest("Judge distinguishes current cycle facts from historical verdict and land [dashboard#task-evidence]"):
                def judge_overview():
                    return stage(rows()["compiled"], "judge")["overview"]

                def facts(overview):
                    return {fact["label"]: fact["value"] for fact in overview["facts"]}

                current = facts(judge_overview())
                self.assertEqual((current["Cycle"], current["Verdict"], current["Landed tip"]), ("gate", "question", head[:7]))
                state["cycles"].append({"kind": "round", "n": 2, "runs": [{"head": new_head}]})
                state_path.write_text(json.dumps(state))
                overview = judge_overview()
                current = facts(overview)
                self.assertEqual((current["Cycle"], current["Checked HEAD"]), ("round-2", new_head[:7]))
                self.assertNotIn("Verdict", current)
                self.assertNotIn("Landed tip", current)
                self.assertNotIn("Public verdict.", overview["summary"])
                self.assertTrue(any("Historical land 1" in row["title"] and head[:7] in row.get("detail", "")
                                    for group in overview["groups"] for row in group["rows"]))
                self.assertEqual(read("compiled", "verdict-1"), judge["Verdict 1"])
                state["verdicts"].append({"n": 2, "kind": "pass", "cycle": "round-2", "head": new_head, "report": "Round passed."})
                state_path.write_text(json.dumps(state))
                overview = judge_overview()
                self.assertEqual(facts(overview)["Verdict"], "pass")
                self.assertNotIn("Landed tip", facts(overview))
                self.assertEqual(overview["summary"], "Round passed.")
                state["cycles"].pop()
                state["verdicts"].pop()
                state_path.write_text(json.dumps(state))
            self.assertEqual(sum(e["kind"] == "image" for e in stage(task, "human-review")["evidence"]), 1)
            review = docs(task, [e for e in stage(task, "human-review")["evidence"] if e["kind"] != "image"])
            self.assertIn("Human guide fixture.", review["Human review guide"][1])
            self.assertIn("+phase two content", review["Commit: Write phase two"][1])
            phase_items = task["phases"][1]["evidence"]
            self.assertIn("fixture.txt", {e["title"] for e in phase_items})
            self.assertNotIn("leak.md", {e["title"] for e in phase_items})
            self.assertNotIn("hardlink.md", {e["title"] for e in phase_items})
            with self.subTest("flat plans do not claim shared artifacts [dashboard#task-evidence]"):
                flat_artifacts = plan.parent.parent / "artifacts" / "phase-2"
                flat_artifacts.mkdir(parents=True)
                (flat_artifacts / "shared.txt").write_text("Ambiguous ownership")
                for slug in ("legacy-one", "legacy-two"):
                    flat_plan = plan.parent.parent / f"{slug}.md"
                    flat_plan.write_text(source)
                    flat_plan.with_suffix(".json").write_text(json.dumps({**state, "plan": flat_plan.name}))
                for slug in ("legacy-one", "legacy-two"):
                    self.assertNotIn("shared.txt", {e["title"] for e in rows()[slug]["phases"][1]["evidence"]})
            capture_id = next(e["id"] for e in stage(task, "human-review")["evidence"] if e["kind"] == "image")
            image.unlink()
            image.symlink_to(plan.with_suffix(".judge.md"))
            self.assertIsNone(read("compiled", capture_id))
            for forbidden in ("../compiled.judge.md", ".runweld/config.toml", "unrelated.txt", str(image), "escape.png"):
                self.assertIsNone(read("compiled", forbidden), forbidden)

            run("git", "worktree", "remove", tree)
            run("git", "merge", "--ff-only", "runweld/compiled")
            run("git", "branch", "-d", "runweld/compiled")
            state.update(status="merged", integration={"commit": head, "landed": head})
            state_path.write_text(json.dumps(state))
            task = rows()["compiled"]
            self.assertEqual((task["status"], task["stage"], task["worktree"]), ("merged", "finish", None))
            self.assertEqual(task["branch"], "runweld/compiled")
            diffs = [e for e in stage(task, "human-review")["evidence"] if e["kind"] == "diff"]
            self.assertIn("+phase two content", docs(task, diffs)["Commit: Write phase two"][1])

            with self.subTest("use the registered older engine and keep historical evidence when unavailable"):
                previous.rename(older)
                older_project = root / "old project"
                older_project.mkdir()
                run("git", "init", "-qb", "main", cwd=older_project)
                run("git", "commit", "--allow-empty", "-qm", "base", cwd=older_project)
                run(cli, "--release", older.name, "onboard", "--apply", "--primary-provider", "Fixture",
                    "--secondary-provider", "Fixture", "--primary-model", "Test-Main",
                    "--secondary-model", "Test-Helper", "--no-setup", cwd=older_project)
                old_task = cli_json("task", "start", "older", "--goal", "Use the old engine",
                                    "--finish-how", "ff-only", "--finish-target", "main", cwd=older_project)
                old_plan = Path(old_task["plan"])
                for optional in ("grill", "prototype"):
                    run(cli, optional, "skip", old_plan, "--reason", "Fixture", cwd=older_project)
                old_plan.write_text(draft_source.replace("runweld/compiled", "runweld/older").replace(active["base"], old_task["base"]))
                run(cli, "approve", old_plan, cwd=older_project)
                row, = read(checkout=older_project)["tasks"]
                self.assertEqual(row["stage"], "plan")
                self.assertEqual(stage(row, "plan")["label"], "Previous plan")
                engine = older / "workflow/build/pipeline.py"
                engine.write_bytes(engine.read_bytes() + b"\n")
                row, = read(checkout=older_project)["tasks"]
                self.assertIsNone(row["stage"])
                self.assertIn("Current stage is unavailable", row["summary"])
                self.assertIn("## Result", read("older", "plan", checkout=older_project)[1])
                older.rename(previous)
                row, = read(checkout=older_project)["tasks"]
                self.assertIsNone(row["stage"])
                self.assertIn("Pinned stage definitions are unavailable", row["summary"])


if __name__ == "__main__":
    unittest.main()
