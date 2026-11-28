This is history; the rules that hold now are in `docs/spec/`.

# Plan: Inspect the Runweld project pipeline in a local dashboard

## Result

Open one project in a browser to see its planned, active and completed Runweld tasks. Select a task to see its branch, worktree, current stage, phase dependencies and recorded results. Read the evidence where the decision was made while the rest of the dashboard continues to update.

## Approach

Ship the viewer and its local server with the installed CLI. Launch from the project checkout or one of its task worktrees. Follow the accepted storyboard for the project inventory, stage sidebar and full-width workspace.

- `runweld ui up` runs in the foreground, opens the default browser and prints the loopback URL and server PID once ready. Preserve the printed URL if opening a browser fails. Ctrl+C or `runweld ui down PID` from any directory stops that instance. Verify instance identity to handle stale PIDs and concurrent projects. From any directory, `runweld ui list` lists this user’s running local panels with project path, URL and PID, and reports when none are open.
- Read the project's registered pipeline in `.runweld/`. Use each task's pinned stage definitions and records. Keep a task visible if its checkout, release or individual artifact is unavailable, and identify what could not be read.
- Refresh statuses, graph nodes and evidence as records change. Preserve the selected task, stage, phase, document and scroll position. Keep navigation in the sidebar and graph.
- In Build Overview, draw a horizontal directed graph from the plan's actual prerequisites. Independent phases occupy parallel lanes. An arrow points from each prerequisite to its dependent. Each node shows the recorded phase status. Selecting one reveals its assignment, provider, model, executor profile, brief and evidence when available.
- Use phase artifacts for the first release's detail. Give stage results priority over guides. Scope document and preview access to intended evidence and isolate HTML previews from the dashboard.
- Use the launcher’s task outcome and actual closing stage for completed and cancelled tasks, including those pinned to an earlier release. Show the retained evidence, the run’s own stage route and its recorded executor profiles. A task stopped because its compiled state is missing reports the recovery reason.

## Out of scope

Cross-project supervision, dashboard mutations, terminal transcripts, and new intra-phase activity instrumentation.

## Done and Spec

```text
## Done

1. Start from a checkout or its task worktree → the panel opens for that project and prints a usable local address and PID. Stop it from another directory by PID → the other project's panel stays up, and retrying with a stale PID leaves unrelated processes untouched.
2. Open a project with planned, active, explicitly completed, cancelled and merged runs → the inventory shows each recorded state and actual stage, keeps early closure distinct from integration, and preserves access to available evidence after cleanup. An empty project has its own view.
3. Open Build with phases 1 and 2 running and phase 3 depending only on phase 2 → two parallel active nodes appear and exactly one incoming arrow connects phase 2 to phase 3. Select phase 2 → its executor, brief and reported artifacts are visible.
4. Keep a phase 2 document open and scroll, then advance the fixture to phase 3 → the graph updates automatically while phase 2, its document and its reading position stay selected.
5. Inspect discovery, plan, judge and human review → read the saved decisions, preview a prototype, read plan Markdown, inspect the public verdict, screenshot and code diff. Missing evidence has an explicit empty state. Unrelated files and private judge material stay outside the viewer.
6. Compare the running local dashboard with the approved storyboard at desktop and mobile widths → the task inventory, stage navigation, graph and evidence readers are legible and use the available workspace — you check.
7. Start panels for two projects and invoke `runweld ui list` outside a checkout → both rows identify the project path, URL and PID. Stop one and then the other → the list shows the remaining panel and then the empty state, excluding stale entries.
8. Read `runweld help ui` or `runweld ui --help`, then open help for up, list and down using either form → the CLI explains how to launch, find and stop a panel with examples, without starting a server.

## Spec

+ dashboard — Project dashboard
  About: The local browser view of a project's Runweld pipeline.
+ dashboard#project-instance — Users can discover, launch, list and stop their local project panels with built-in command help and verified instance identities
  Why: independent project processes need controllable lifetimes
  Done: 1, 7, 8
+ dashboard#task-evidence — The project inventory preserves recorded task state and exposes the evidence belonging to the selected task and stage
  Why: the user follows handoffs and outcomes across the pipeline
  Done: 2, 5, 6
+ dashboard#phase-graph — The Build overview draws directed prerequisite edges and shows recorded phase status while preserving the selected phase and document during updates
  Why: the user needs to see parallel progress while reading earlier work
  Done: 3, 4
```
