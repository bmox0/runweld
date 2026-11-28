# Project dashboard

The local browser view of a project's Runweld pipeline.

### project-instance — Users can discover, launch, list and stop their local project panels with built-in command help and verified instance identities

Why: independent project processes need controllable lifetimes

- Start from a checkout or its task worktree → the panel opens for that project and prints a usable local address and PID. Stop it from another directory by PID → the other project's panel stays up, and retrying with a stale PID leaves unrelated processes untouched.
- Start panels for two projects and invoke `runweld ui list` outside a checkout → both rows identify the project path, URL and PID. Stop one and then the other → the list shows the remaining panel and then the empty state, excluding stale entries.
- Read `runweld help ui` or `runweld ui --help`, then open help for up, list and down using either form → the CLI explains how to launch, find and stop a panel with examples, without starting a server.

### task-evidence — The project inventory preserves recorded task state and exposes the evidence belonging to the selected task and stage

Why: the user follows handoffs and outcomes across the pipeline

- Open a project with planned, active, explicitly completed, cancelled and merged runs → the inventory shows each recorded state and actual stage, keeps early closure distinct from integration, and preserves access to available evidence after cleanup. An empty project has its own view.
- Inspect discovery, plan, judge and human review → read the saved decisions, preview a prototype, read plan Markdown, inspect the public verdict, screenshot and code diff. Missing evidence has an explicit empty state. Unrelated files and private judge material stay outside the viewer.
- Compare the running local dashboard with the approved storyboard at desktop and mobile widths → the task inventory, stage navigation, graph and evidence readers are legible and use the available workspace

### phase-graph — The Build overview draws directed prerequisite edges and shows recorded phase status while preserving the selected phase and document during updates

Why: the user needs to see parallel progress while reading earlier work

- Open Build with phases 1 and 2 running and phase 3 depending only on phase 2 → two parallel active nodes appear and exactly one incoming arrow connects phase 2 to phase 3. Select phase 2 → its executor, brief and reported artifacts are visible.
- Keep a phase 2 document open and scroll, then advance the fixture to phase 3 → the graph updates automatically while phase 2, its document and its reading position stay selected.
