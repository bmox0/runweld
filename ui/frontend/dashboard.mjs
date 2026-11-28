import { escapeHtml, loadEvidence, readerMarkup, updateReader } from "./evidence.mjs";
import { icon, sprite } from "./icons.mjs";

const stageStatus = { complete: "Finished", done: "Finished", unknown: "Not recorded" };
const tones = {
  active: "orange", current: "orange", "in progress": "orange", ready: "blue",
  complete: "green", completed: "green", merged: "green", done: "green",
  cancelled: "red", blocked: "red", waiting: "amber", planned: "orange", unknown: "amber",
};
const kinds = { image: "photo", html: "code" };
const groupNames = { active: "Active", completed: "Completed", planned: "Plans", cancelled: "Cancelled", merged: "Merged", plans: "Plans" };
const sentence = (value) => value ? value[0].toUpperCase() + value.slice(1) : "Not recorded";
const stageLabel = (task) => task.stages.find((stage) => stage.id === task.stage)?.label ?? task.stage;
const closed = (task) => ["completed", "cancelled", "merged"].includes(task.status);
const text = (value) => escapeHtml(value ?? "Not recorded");
const toneClass = (value) => `rx-${Object.values(tones).includes(value) ? value : "neutral"}`;

function mark(tone, status) {
  const shape = status === "skipped" ? " dash" : ["upcoming", "not applicable"].includes(status) ? " off" : "";
  return `<span class="rx-mark ${toneClass(tone)}${shape}" aria-hidden="true"></span>`;
}
function chip(badge, status, button = false) {
  if (!badge?.text) return "";
  const attrs = `class="rx-chip ${toneClass(badge.tone)}"`;
  const label = (status ? mark(badge.tone, status) : "") + text(badge.text);
  return button ? `<button type="button" ${attrs} data-toggle="profiles" title="Executor profiles" aria-label="${text(badge.text)} · Executor profiles" aria-expanded="${button.show}">${label}</button>` :
    `<span ${attrs}>${label}</span>`;
}

function stageButton(task, stage, selected, mobile = false) {
  const label = stage.statusLabel ?? stageStatus[stage.status] ?? sentence(stage.status);
  const selectedClass = stage.id === selected?.id ? " sel" : "";
  const state = mark(stage.statusTone ?? tones[stage.status], stage.status);
  const current = stage.id === task.stage && (!closed(task) || stage.status === "current");
  return `<button type="button" class="${mobile ? "rx-mstop" : "rx-stage"}${selectedClass}" data-stage="${text(stage.id)}" aria-pressed="${Boolean(selectedClass)}"${current ? ' aria-current="step"' : ""}>${
    mobile ? `${text(stage.label)}<small>${state}${text(label)}</small>` : `${state}<span>${text(stage.label)}</span><small>${text(label)}</small>`
  }</button>`;
}

function sidebar(tasks, task, selectedStage) {
  const stages = task?.stages ?? [];
  const runs = tasks.length ? `<div class="rx-sidelabel">Runs</div>${tasks.map((run) => {
    const selected = run.id === task?.id;
    const detail = run.sidebar?.detail ?? [groupNames[run.status] ?? sentence(run.status), stageLabel(run)].filter(Boolean).join(" · ");
    return `<button type="button" class="rx-nav rx-mini${selected ? " on" : ""}" data-task="${text(run.id)}"${selected ? ' aria-current="page"' : ""}>${
      mark(run.sidebar?.tone ?? tones[run.status])
    }<span><strong>${text(run.title)}</strong><small>${text(detail)}</small></span></button>`;
  }).join("")}` : "";
  return `<aside class="rx-side" aria-label="Project navigation">
    <div class="rx-brand"><span class="rx-logo">${icon("flow")}</span>Runweld</div>
    <button class="rx-nav${task ? "" : " on"}" type="button" data-home${task ? "" : ' aria-current="page"'}>${icon("folder")}Tasks</button>
    ${stages.length ? `<div class="rx-sidelabel">Stages</div><nav class="rx-stages" aria-label="Stages">${stages.map((stage) => stageButton(task, stage, selectedStage)).join("")}</nav>` : ""}
    ${task && runs ? `<div class="rx-sidebar-bottom">${runs}</div>` : runs}
  </aside>`;
}

function mobileStages(task, selected) {
  if (!selected) return "";
  const index = task.stages.indexOf(selected);
  const start = Math.max(0, Math.min(index - 1, task.stages.length - 3));
  return `<nav class="rx-mobile-rail" aria-label="Stages">
    <div class="rx-railhead"><span>Stages</span><span>${index + 1} of ${task.stages.length}</span></div>
    <div class="rx-railrow">${task.stages.slice(start, start + 3).map((stage) => stageButton(task, stage, selected, true)).join(icon("arrow", true))}</div>
  </nav>`;
}

function inventory(tasks, mode) {
  let content;
  if (mode === "loading") {
    content = `<div class="rx-skeleton" aria-label="Loading tasks"><p class="rx-note" role="status">Reading project tasks…</p>${
      [157, 142, 127, 112].map((width, i) => `<div class="rx-taskrow"><span class="rx-skel" style="width:${width}px"></span><span class="rx-skel" style="width:${91 + i * 5}px"></span><span class="rx-skel" style="width:76px"></span><span></span></div>`).join("")
    }</div>`;
  } else if (mode === "error") {
    content = `<section class="rx-empty">${icon("alert")}<h4>Couldn’t load project tasks</h4><p>The project is open, but its task records could not be read. Try again to refresh the list.</p><button class="rx-button" type="button" data-retry>Try again</button></section>`;
  } else if (!tasks.length) {
    content = `<section class="rx-empty">${icon("folder")}<h4>No tasks yet</h4><p>Start a task with Runweld to see its stage, worktree and artifacts here.</p><p style="margin-top:10px"><code>runweld task start ID --goal TEXT</code></p></section>`;
  } else {
    const groups = Map.groupBy(tasks, (task) => task.inventory?.group ?? task.status);
    const order = [...new Set([...Object.keys(groupNames), ...groups.keys()])];
    content = order.filter((group) => groups.has(group)).map((group) => {
      const rows = groups.get(group);
      return `<section class="rx-inv-group"><div class="rx-inv-head">${text(groupNames[group] ?? sentence(group))} · ${rows.length}</div>${
        rows.map((task) => {
          const item = task.inventory;
          const badge = item?.status ?? { tone: tones[task.status], text: [sentence(task.status), stageLabel(task)].filter(Boolean).join(" · ") };
          return `<button class="rx-taskrow" type="button" data-task="${text(task.id)}"><span><b>${text(task.title)}</b><span class="rx-sub mono">${text(item?.subtitle ?? task.id)}</span></span><span>${chip(badge, task.status)}<span class="rx-sub">${text(item?.detail ?? (closed(task) ? "Archived task" : "Local task"))}</span></span><span class="rx-note">${text(item?.execution ?? (task.worktree ? "Worktree" : task.branch ? "Branch only" : "Not assigned"))}</span>${icon("arrow", true)}</button>`;
        }).join("")
      }</section>`;
    }).join("");
  }
  return `<section class="rx-listbody"><div class="rx-listhead"><h3>Tasks</h3>${mode === "ready" && tasks.length ? `<span class="rx-note">${tasks.length} ${tasks.length === 1 ? "task" : "tasks"} · Local and archived</span>` : ""}</div>${content}</section>`;
}

const graphBox = { nodeWidth: 168, nodeHeight: 84, stepX: 224, stepY: 102, pad: 13 };

function graphLayout(phases) {
  const ids = new Set(phases.map((phase) => phase.id));
  const nodes = new Map();
  const occupied = new Map();
  let pending = phases;
  while (pending.length) {
    const next = [];
    for (const phase of pending) {
      const needs = phase.prerequisites.filter((id) => ids.has(id));
      if (needs.some((id) => !nodes.has(id))) {
        next.push(phase);
        continue;
      }
      const depth = Math.max(0, ...needs.map((id) => nodes.get(id).depth + 1));
      const lanes = occupied.get(depth) ?? new Set();
      let lane = needs.length ? nodes.get(needs[0]).lane : 0;
      while (lanes.has(lane)) lane++;
      lanes.add(lane);
      occupied.set(depth, lanes);
      nodes.set(phase.id, { depth, lane });
    }
    if (next.length === pending.length) {
      for (const phase of next) nodes.set(phase.id, { depth: 0, lane: nodes.size });
      break;
    }
    pending = next;
  }
  const { stepX, stepY, pad } = graphBox;
  for (const point of nodes.values()) {
    point.x = pad + point.depth * stepX;
    point.y = pad + point.lane * stepY;
  }
  return nodes;
}

function graph(phases, selected) {
  if (!phases.length) return '<p class="rx-note">No phases recorded for this task.</p>';
  const layout = graphLayout(phases);
  const { nodeWidth, nodeHeight, pad } = graphBox;
  const width = Math.max(...Array.from(layout.values(), ({ x }) => x)) + nodeWidth + pad;
  const height = Math.max(...Array.from(layout.values(), ({ y }) => y)) + nodeHeight + pad;
  const links = phases.flatMap((phase) => phase.prerequisites.map((id) => {
    const from = layout.get(id), to = layout.get(phase.id);
    if (!from || from.depth >= to.depth) return "";
    const x1 = from.x + nodeWidth, y1 = from.y + nodeHeight / 2;
    const x2 = to.x - 3, y2 = to.y + nodeHeight / 2;
    const route = to.depth - from.depth > 1
      ? `H${x1 + 16} V${pad / 2} H${x2 - 18} V${y2}`
      : `H${(x1 + x2) / 2} V${y2}`;
    return `<path data-from="${escapeHtml(id)}" data-to="${escapeHtml(phase.id)}" d="M${x1} ${y1} ${route} H${x2}" marker-end="url(#phase-arrow)"/>`;
  })).join("");
  return `<section class="phase-graph" aria-labelledby="phase-graph-title">
    <h3 id="phase-graph-title">Phase graph</h3>
    <div class="graph-scroll">
      <div class="graph-canvas" style="--width:${width};--height:${height};--node-width:${nodeWidth};--node-height:${nodeHeight}">
        <svg class="graph-edges" viewBox="0 0 ${width} ${height}" aria-hidden="true">
          <defs><marker id="phase-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto">
            <path d="M0 0 8 4 0 8z"/>
          </marker></defs>${links}
        </svg>
        ${phases.map((phase) => {
          const { x, y } = layout.get(phase.id);
          return `<button type="button" class="graph-node" data-phase="${escapeHtml(phase.id)}" aria-pressed="${selected?.id === phase.id}" style="--x:${x};--y:${y}">
            <small>Phase ${escapeHtml(phase.id)}</small><strong title="${escapeHtml(phase.title)}">${escapeHtml(phase.title)}</strong>${chip({ text: sentence(phase.status), tone: tones[phase.status] })}
            ${phase.prerequisites.length ? `<span class="sr-only">Requires ${escapeHtml(phase.prerequisites.join(", "))}</span>` : ""}
          </button>`;
        }).join("")}
      </div>
    </div>
  </section>`;
}

function facts(rows) {
  return rows.length ? `<dl class="rx-facts">${rows.map(({ label, value }) =>
    `<div><dt>${text(label)}</dt><dd>${text(value)}</dd></div>`).join("")}</dl>` : "";
}

function phaseDetail(phase) {
  const assignment = phase.assignment;
  return `<section class="rx-rows"><h4>Phase ${text(phase.id)} · ${text(phase.title)}</h4>
    ${facts([
      ["Prerequisites", phase.prerequisites.length ? phase.prerequisites.map((id) => `Phase ${id}`).join(", ") : "None"],
      ["Assignment", assignment?.role], ["Provider", assignment?.provider],
      ["Model", assignment?.model], ["Executor profile", assignment?.profile],
      ...(assignment?.effort ? [["Effort", assignment.effort]] : []),
    ].map(([label, value]) => ({ label, value })))}
  </section>`;
}

function profileDetails(task) {
  return `<div class="rx-pane-extra">${facts(["primary", "secondary"].filter((tier) => task.executors?.[tier]).map((tier) => {
    const { provider, model, effort } = task.executors[tier];
    return { label: sentence(tier) + " executor", value: [provider, model, effort].filter(Boolean).join(" / ") };
  }))}</div>`;
}

function phaseRows(phases) {
  return phases.length ? [{ title: "Build phases", rows: phases.map((phase) => ({
    phaseId: phase.id, title: phase.id + " · " + phase.title, detail: phase.territory?.join(", ") || phase.assignment?.role,
    status: { text: phase.status === "in progress" ? "Running" : stageStatus[phase.status] ?? sentence(phase.status), tone: tones[phase.status] },
  })) }] : [];
}

function overviewMarkup(task, stage, phase, page) {
  const overview = stage?.overview;
  const groups = overview?.groups ?? (stage?.id === "build" ? phaseRows(task.phases) : []);
  return `<h4>${text(overview?.heading || "Stage overview")}</h4>
    <p class="rx-summary">${text(overview?.summary || stage?.summary || "No overview recorded for this stage.")}</p>
    ${facts(overview?.facts ?? [])}
    ${groups.map((group) => `<section class="rx-rows"><h4>${text(group.title)}</h4>${
      group.rows.map((row) => {
        const title = text(row.title);
        const namedPhase = task.phases.find((item) => item.id === row.phaseId);
        const trigger = namedPhase ? `<button type="button" data-phase="${text(namedPhase.id)}" aria-pressed="${phase?.id === namedPhase.id}" title="Inspect phase">${title}</button>`
          : row.evidenceId ? `<button type="button" data-evidence="${text(row.evidenceId)}">${title}</button>` : title;
        return `<div class="rx-log"><strong>${trigger}</strong>${chip(row.status)}${row.detail ? `<p>${text(row.detail)}</p>` : ""}</div>`;
      }).join("")
    }</section>`).join("")}
    ${overview?.next ? `<div class="rx-next">${icon("clock", true)}<div><b>Next action</b>${overview.next.owner && overview.next.owner !== "Next action" ? text(overview.next.owner) + " · " : ""}${text(overview.next.text)}</div></div>` : ""}
    ${phase && page ? phaseDetail(phase) : ""}`;
}

function evidenceList(items, selected, view) {
  function group(title, role, empty) {
    const files = items.filter((item) => (item.role ?? "result") === role);
    return `<h4>${title}</h4>${files.length ? files.map((item) => `<button type="button" class="rx-file${selected === item.id ? " on" : ""}" data-evidence="${text(item.id)}" aria-pressed="${selected === item.id}"${selected === item.id ? ' title="Close document"' : ""}>${icon(item.icon ?? kinds[item.kind] ?? "file", true)}<span><b>${text(item.title)}</b><small>${text(item.label ?? sentence(item.kind))}</small></span></button>`).join("") :
      `<div class="rx-file"><small>${empty}</small></div>`}`;
  }
  return `<aside class="rx-aux" aria-label="Evidence">${view !== "guide" || selected ? group("Stage files", "result", "No saved files for this stage.") : ""}${view === "guide" || ((view !== "artifacts" || selected) && items.some((item) => item.role === "reference")) ? group("Reference", "reference", "No saved guide for this stage.") : ""}</aside>`;
}

function workspace(task, stage, selection) {
  const { view = "overview", showGraph, showProfiles } = selection;
  const phase = task.phases.find((item) => item.id === selection.phase);
  const build = stage?.id === "build";
  const profile = task.executors && Object.keys(task.executors).length;
  const stageFiles = stage?.evidence ?? [];
  const phaseFiles = build ? task.phases.flatMap((item) => item.evidence) : [];
  const allFiles = [...new Map([...stageFiles, ...phaseFiles].map((item) => [item.id, item])).values()];
  const otherFiles = new Set(build && phase ? task.phases.filter((item) => item !== phase)
    .flatMap((item) => item.evidence.map((file) => file.id)) : []);
  const files = allFiles.filter((item) => !otherFiles.has(item.id));
  const listed = build && phase ? files.map((item) => phase.evidence.some((file) => file.id === item.id)
    ? { ...item, label: `Phase ${phase.id} · ${item.label ?? sentence(item.kind)}` } : item) : files;
  const open = files.find((item) => item.id === selection.evidence);
  const evidenceUrl = open && "./api/evidence?" + new URLSearchParams({ task: task.id, id: open.id });
  const context = stage?.contextLabel ?? (closed(task) && stageLabel(task) ? "Closed at: " + stageLabel(task) :
    stage?.id !== task.stage && stageLabel(task) ? "Current: " + stageLabel(task) : "");
  const state = task.displayStatus ?? { text: closed(task) ? sentence(task.status) : stageLabel(task) ?? sentence(task.status), tone: tones[task.status] };
  const execution = task.execution;
  return `<div class="rx-taskhead">
    <div class="rx-titleline"><h3>${text(task.workspaceTitle ?? task.id)}</h3>${chip(state, task.status, profile ? { show: Boolean(showProfiles) } : false)}</div>
    <div class="rx-meta">
      <span>${icon("branch", true)}Branch <code>${text(task.branch ?? "Not assigned")}</code></span>
      <span>${icon("tree", true)}${text(execution?.label ?? (task.worktree || !task.branch ? "Worktree" : "Execution"))} <code>${text(execution?.value ?? task.worktree ?? (task.branch ? "Branch only" : "Not assigned"))}</code></span>
      ${execution?.detail ? `<span>${text(execution.detail)}</span>` : ""}
    </div>
    ${task.summary ? `<p class="rx-note">${text(task.summary)}</p>` : ""}
  </div>
  ${showProfiles && profile ? profileDetails(task) : ""}
  ${mobileStages(task, stage)}
  <div class="rx-stagebar">
    <h4>${build && task.phases.length ? `<button type="button" data-toggle="graph" title="Phase graph" aria-label="Build · Phase graph" aria-expanded="${Boolean(showGraph)}">${text(stage.label)}</button>` : text(stage?.label)}${
      stage ? chip(stage.displayStatus ?? { text: stage.statusLabel ?? stageStatus[stage.status] ?? sentence(stage.status), tone: stage.statusTone ?? tones[stage.status] }, stage.status) : ""
    }${context ? `<span class="rx-now">${text(context)}</span>` : ""}</h4>
    <nav class="rx-views" aria-label="Stage views">${["overview", "artifacts", "guide"].map((name) =>
      `<button class="rx-tab${name === view ? " on" : ""}" data-view="${name}" type="button" aria-pressed="${name === view}">${sentence(name)}</button>`).join("")}</nav>
  </div>
  ${showGraph && build ? graph(task.phases, phase) : ""}
  <div class="rx-layout">
    <section class="rx-pane">${open ? readerMarkup(open, evidenceUrl) :
      view === "overview" ? overviewMarkup(task, stage, phase, build) :
        `<h4>${sentence(view)}</h4><p class="rx-summary">${files.some((item) => (item.role === "reference") === (view === "guide")) ? "Select a document to open it here." : "No document to open."}</p>`}</section>
    ${evidenceList(listed, open?.id, view)}
  </div>`;
}

function resolve(data, selection) {
  const task = data.tasks.find((item) => item.id === selection.task);
  const stage = task?.stages.find((item) => item.id === selection.stage)
    ?? task?.stages.find((item) => item.id === task.stage) ?? task?.stages[0];
  return { task, stage };
}

export function renderDashboard(data, selection = {}, mode = "ready") {
  const { project, tasks } = data;
  const { task, stage } = resolve(data, selection);
  return `${sprite}<div class="rw">${sidebar(tasks, task, stage)}
    <main id="workspace" class="rx-main" tabindex="-1">
      <header class="rx-top">
        ${icon(task ? "left" : "folder")}
        <strong>${task ? '<button type="button" data-home>Tasks</button>' : text(project.name)}</strong>
        <span class="crumb" title="${text(project.path)}">${task ? text(project.name) : "Project"}</span><span class="sp"></span>
      </header>
      ${task ? workspace(task, stage, selection) : inventory(tasks, mode)}
    </main></div>`;
}

export function mountDashboard(root, initial, mode = "ready") {
  let data = initial;
  let selection = {};
  let previous = "";
  let pending;
  function read(reader, preservePosition) {
    pending?.abort();
    pending = new AbortController();
    loadEvidence(reader, pending.signal, preservePosition);
  }

  function paint(hint) {
    const { task, stage } = resolve(data, selection);
    selection.stage = stage?.id;
    if (!task?.phases.some((phase) => phase.id === selection.phase)) selection.phase = undefined;
    const markup = renderDashboard(data, selection, mode);
    if (markup === previous) return;
    previous = markup;
    const focused = root.contains(document.activeElement) ? document.activeElement : null;
    const [x, y] = [window.scrollX, window.scrollY];
    const graphScroll = root.querySelector(".graph-scroll")?.scrollLeft ?? 0;
    const template = document.createElement("template");
    template.innerHTML = markup;
    const reader = root.querySelector("[data-evidence-reader]");
    const nextReader = template.content.querySelector("[data-evidence-reader]");
    const keep = reader && nextReader && reader.dataset.evidenceReader === nextReader.dataset.evidenceReader
      && reader.dataset.kind === nextReader.dataset.kind;
    const rect = keep && reader.getBoundingClientRect();
    const top = rect && rect.bottom > 0 && rect.top < window.innerHeight ? rect.top : null;

    if (keep) {
      // A connected reader keeps its iframe, text selection and scroll during refresh.
      const layout = reader.closest(".rx-layout");
      const nextLayout = nextReader.closest(".rx-layout");
      root.querySelector(".rx-side").replaceWith(template.content.querySelector(".rx-side"));
      for (const child of [...layout.parentElement.children]) if (child !== layout) child.remove();
      layout.before(...[...nextLayout.parentElement.children].filter((child) => child !== nextLayout));
      layout.lastElementChild.replaceWith(nextLayout.lastElementChild);
      updateReader(reader, nextReader);
      if (reader.dataset.revision !== nextReader.dataset.revision) {
        reader.dataset.revision = nextReader.dataset.revision;
        read(reader, true);
      }
    } else {
      pending?.abort();
      root.replaceChildren(template.content);
      if (nextReader) read(nextReader, false);
    }

    const graphScrollElement = root.querySelector(".graph-scroll");
    if (graphScrollElement) graphScrollElement.scrollLeft = graphScroll;
    if (hint === "heading") {
      root.querySelector("main")?.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    } else {
      if (focused && !focused.isConnected) {
        const buttons = [...root.querySelectorAll("button")].filter((button) => button.getClientRects().length);
        const replacement = buttons.find((button) => button.outerHTML === focused.outerHTML)
          ?? buttons.find((button) => ["task", "stage", "phase", "view", "evidence", "toggle"].some((key) =>
            focused.dataset[key] !== undefined && focused.dataset[key] === button.dataset[key]));
        replacement?.focus({ preventScroll: true });
      }
      if (hint === "refresh") window.scrollTo(x, top === null ? y : y + reader.getBoundingClientRect().top - top);
    }
  }
  root.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || !root.contains(button)) return;
    const { task, stage, phase, view, evidence, toggle } = button.dataset;
    let hint;
    const oldEvidence = selection.evidence;
    if (button.hasAttribute("data-home")) {
      selection = {};
      hint = "heading";
    } else if (task !== undefined) {
      selection = { task };
      hint = "heading";
    } else if (stage !== undefined) {
      selection = { task: selection.task, stage, showProfiles: selection.showProfiles };
    } else if (toggle === "graph") {
      selection.showGraph = !selection.showGraph;
    } else if (toggle === "profiles") {
      selection.showProfiles = !selection.showProfiles;
    } else if (phase !== undefined) {
      selection = { ...selection, phase, evidence: undefined, view: "overview" };
    } else if (view !== undefined) {
      selection = { ...selection, view, evidence: undefined };
    } else if (evidence !== undefined || button.hasAttribute("data-close-evidence")) {
      selection.evidence = evidence === oldEvidence ? undefined : evidence;
    } else return;
    paint(hint);
    if (selection.evidence && selection.evidence !== oldEvidence) {
      const heading = root.querySelector(".rx-filebar b");
      heading?.focus({ preventScroll: true });
      heading?.scrollIntoView({ block: "nearest" });
    } else if (oldEvidence && (evidence !== undefined || button.hasAttribute("data-close-evidence"))) {
      [...root.querySelectorAll("[data-evidence]")].find((file) => file.dataset.evidence === oldEvidence)?.focus();
    }
  });
  paint();
  return {
    update(snapshot) { data = snapshot; mode = "ready"; paint("refresh"); },
    startup(state) { mode = state; paint(); },
  };
}
