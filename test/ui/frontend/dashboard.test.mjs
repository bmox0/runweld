import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { renderDashboard } from "../../../ui/frontend/dashboard.mjs";
import { passiveHtmlImage, readerMarkup, renderDiff, renderMarkdown, renderTerminal } from "../../../ui/frontend/evidence.mjs";

const fixture = JSON.parse(readFileSync(new URL("project.json", import.meta.url), "utf8"));
const task = "pipeline-panel";

test("inventory preserves five recorded outcomes and their actual stages [dashboard#task-evidence]", () => {
  const view = renderDashboard(fixture);
  for (const [status, title, stage] of [
    ["Active", "Pipeline panel", "Build"], ["Plans", "Archive filters", "Plan"],
    ["Completed", "Prototype review", "Prototype"], ["Cancelled", "Audit trail", "Grill"],
    ["Merged", "Workflow progress", "Finish"],
  ]) {
    assert.match(view, new RegExp(`class="rx-inv-head">${status} · 1</div>.*?${title}.*?${stage}`, "s"));
  }
  assert.match(renderDashboard({ ...fixture, tasks: [] }), /No tasks yet/);
  const completed = renderDashboard(fixture, { task: "prototype-review" });
  assert.match(completed, /Approved prototype/);
  assert.doesNotMatch(completed, /Current: Prototype/);
  assert.match(completed, /Closed at: Prototype/);
});

test("selecting an earlier stage leaves the task's active stage intact [dashboard#task-evidence]", () => {
  const view = renderDashboard(fixture, { task, stage: "grill" });
  assert.match(view, /data-stage="grill" aria-pressed="true"/);
  assert.match(view, /data-stage="build" aria-pressed="false" aria-current="step"/);
  assert.match(view, /Current: Build/);
  assert.match(view, /No saved files for this stage/);
});

test("the workspace displays both saved executor profiles without phases [dashboard#task-evidence]", () => {
  const project = structuredClone(fixture);
  project.tasks.find((row) => row.id === "prototype-review").executors = {
    primary: { provider: "Main & Co", model: "Planner" },
    secondary: { provider: "Helper", model: "Worker", effort: "high" },
  };
  const view = renderDashboard(project, { task: "prototype-review", showProfiles: true });
  assert.match(view, /Primary executor[\s\S]*Main &amp; Co[\s\S]*Planner/);
  assert.match(view, /Secondary executor[\s\S]*Helper[\s\S]*Worker[\s\S]*high/);
});

test("an open evidence reference carries its latest revision [dashboard#phase-graph]", () => {
  const project = structuredClone(fixture);
  const item = project.tasks[0].phases[1].evidence[0];
  const selection = { task, phase: "2", evidence: item.id };
  item.revision = "version-a";
  assert.match(renderDashboard(project, selection), /data-revision="version-a"/);
  item.revision = "version-b";
  assert.match(renderDashboard(project, selection), /data-revision="version-b"/);
});

test("independent active phases share a column and only the recorded dependency draws an arrow [dashboard#phase-graph]", () => {
  const view = renderDashboard(fixture, { task, phase: "2", showGraph: true });
  const positions = [...view.matchAll(/data-phase="(\d)" aria-pressed="(true|false)" style="--x:(\d+);--y:(\d+)"/g)]
    .map(([, id, selected, x, y]) => [id, selected, Number(x), Number(y)]);
  assert.equal(positions.length, 3, "all three phase nodes are visible");
  const [first, second, third] = positions;
  assert.equal(first[2], second[2], "independent phases share a column");
  assert.notEqual(first[3], second[3], "independent phases occupy separate lanes");
  assert.ok(third[2] > second[2], "dependents are to the right");
  assert.equal(second[1], "true", "phase 2 is selected");
  const arrows = [...view.matchAll(/<path data-from="(\d)" data-to="(\d)"[^>]*marker-end/g)]
    .map(([, from, to]) => [from, to]);
  assert.deepEqual(arrows, [["2", "3"]]);
  assert.equal((view.match(/>In progress<\/span>/g) ?? []).length, 2);
  assert.match(view, /GPT.*gpt-6\.2-sol/s);
  assert.match(view, /Implementation brief/);
  assert.match(view, /Phase report/);
});

test("task and evidence titles display as text, not HTML [dashboard#task-evidence]", () => {
  const project = structuredClone(fixture);
  project.tasks[0].title = "<b>Untrusted task</b>";
  project.tasks[0].phases[1].evidence[0].title = "<img src=x>";
  const view = renderDashboard(project, { task, phase: "2" });
  assert.match(view, /&lt;b&gt;Untrusted task&lt;\/b&gt;/);
  assert.match(view, /&lt;img src=x&gt;/);
  assert.doesNotMatch(view, /<img src=x>/);
});

test("Markdown and diff readers format saved text without running embedded markup [dashboard#task-evidence]", () => {
  const markdown = renderMarkdown([
    "# Result",
    "Read **recorded** decisions from `a < b`, not <img src=x onerror=evil()>.",
    "[Reference](https://example.org/guide?a=1&b=2) and [Unsafe](javascript:evil).",
    "",
    "5. Confirm the choices",
    "6. Close",
    "",
    "| Phase | Status |",
    "| --- | --- |",
    "| 2 | In progress |",
    "",
    "```html",
    "<script>evil()</script>",
    "```",
  ].join("\n"));
  assert.match(markdown, /<h1>Result<\/h1>/);
  assert.equal(renderMarkdown("# Result\n\n## Checks", 4), "<h4>Result</h4>\n<h5>Checks</h5>");
  assert.match(markdown, /<strong>recorded<\/strong>.*<code>a &lt; b<\/code>/);
  assert.match(markdown, /href="https:\/\/example.org\/guide\?a=1&amp;b=2"/);
  assert.match(markdown, /<ol start="5"><li>Confirm the choices<\/li><li>Close<\/li><\/ol>/);
  assert.match(markdown, /<th scope="col">Phase<\/th>.*<td>In progress<\/td>/);
  assert.match(markdown, /<pre><code>&lt;script&gt;evil\(\)&lt;\/script&gt;<\/code><\/pre>/);
  assert.doesNotMatch(markdown, /<img|<script|href="javascript:/);

  const diff = renderDiff("@@ -1 +1 @@\n-<old>\n+<new>");
  assert.match(diff, /class="meta">@@ -1 \+1 @@/);
  assert.match(diff, /class="del">-&lt;old&gt;/);
  assert.match(diff, /class="add">\+&lt;new&gt;/);
  assert.equal(renderDiff(" context\n+line\n"), '<span class="ctx"> context</span><span class="add">+line</span>');
  assert.equal(renderTerminal("$ echo <tag>\n output"), '<span class="command">$ echo &lt;tag&gt;</span>\n output');
});

test("the artifact filebar and caption expose plain text and the selected revision [dashboard#task-evidence]", () => {
  const markup = readerMarkup({
    title: "<Prototype>",
    kind: "html",
    revision: 'rev"1',
    badge: { text: "<Artifact>", tone: 'blue" onclick="bad()' },
    caption: "<Earlier version>",
  }, "./api/evidence?task=a&id=b");
  assert.match(markup, /<div class="rx-filebar"><svg [^>]*><use href="#r-code"\/><\/svg><b tabindex="-1">&lt;Prototype&gt;<\/b>/);
  assert.match(markup, /class="rx-chip rx-blue">&lt;Artifact&gt;/);
  assert.match(markup, /data-evidence-reader="\.\/api\/evidence\?task=a&amp;id=b"/);
  assert.match(markup, /data-revision="rev&quot;1"/);
  assert.match(markup, /data-caption="&lt;Earlier version&gt;"/);
  assert.doesNotMatch(markup, /onclick|<Prototype>|<Artifact>|<Earlier version>/);
});

test("startup failure and a successful empty project are different states [dashboard#task-evidence]", () => {
  const empty = { ...fixture, tasks: [] };
  assert.match(renderDashboard(empty, {}, "loading"), /Reading project tasks/);
  assert.match(renderDashboard(empty, {}, "error"), /data-retry[^>]*>Try again/);
  assert.match(renderDashboard(empty), /No tasks yet/);
});

test("Build opens the compact phase list with an explicit graph action [dashboard#phase-graph]", () => {
  const view = renderDashboard(fixture, { task });
  assert.match(view, /data-toggle="graph"/);
  assert.doesNotMatch(view, /class="graph-node"/);
  assert.match(view, /Running/);
});

test("a selected phase identifies its own files even when reports share a title [dashboard#phase-graph]", () => {
  const project = structuredClone(fixture);
  const [first, second, third] = project.tasks[0].phases;
  first.evidence = [{ ...second.evidence[1], id: "report-1" }];
  const build = project.tasks[0].stages.find(({ id }) => id === "build");
  build.evidence = [...first.evidence, ...second.evidence, { id: "decisions", title: "Build decisions", kind: "markdown" }];
  const unselected = renderDashboard(project, { task });
  assert.match(unselected, /data-evidence="report-1"/);
  assert.match(unselected, /data-evidence="report-2"/);
  const selected = renderDashboard(project, { task, phase: second.id });
  assert.match(selected, /data-evidence="brief-2"[^>]*>[^]*?<b>Implementation brief<\/b><small>Phase 2/);
  assert.match(selected, /data-evidence="report-2"[^>]*>[^]*?<b>Phase report<\/b><small>Phase 2/);
  assert.match(selected, /data-evidence="decisions"/);
  assert.doesNotMatch(selected, /data-evidence="report-1"/);
  const earlier = renderDashboard(project, { task, phase: first.id });
  assert.match(earlier, /data-evidence="report-1"[^>]*>[^]*?<b>Phase report<\/b><small>Phase 1/);
  assert.doesNotMatch(earlier, /data-evidence="(brief|report)-2"/);
  assert.doesNotMatch(renderDashboard(project, { task, phase: third.id }), /data-evidence="report-/);
});

test("an image-only HTML artifact can be displayed without relaxing the HTML sandbox [dashboard#task-evidence]", () => {
  const src = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABAQMAAAAl21bKAAAAA1BMVEUAAACnej3aAAAACklEQVQI12NgAAAAAgAB4iG8MwAAAABJRU5ErkJggg==";
  const image = `<img alt="Captured graph" style="width:100%;display:block" src="${src}">`;
  const document = (body, head = "") => `<!doctype html><html><head>${head}</head><body style="margin:0">${body}</body></html>`;
  const result = passiveHtmlImage(document(image, '<title>Prototype</title><meta charset="utf-8">'));
  assert.deepEqual(result, { src, alt: "Captured graph" });
  for (const source of [
    document(image + "<p>Important context</p>"),
    document(image, "<style>img { opacity:.5 }</style>"),
    document(image.replace("<img", '<img onload="alert(1)"')),
    document(image.replace(src, "data:image/png;base64,PGh0bWw+")),
    document(image.replace(src, "/unrecorded.png")),
    document(image.replace(src, "data:image/svg+xml;base64,PHN2Zz4=")),
    document(image.replace("width:100%", "width:80%")),
  ]) assert.equal(passiveHtmlImage(source), undefined);
});
