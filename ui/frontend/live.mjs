import { mountDashboard } from "./dashboard.mjs";

const root = document.querySelector("#dashboard");
const connection = document.querySelector("#connection");
const dashboard = mountDashboard(root, { project: { name: root.dataset.project }, tasks: [] }, "loading");
let loaded = false;
let timer;

async function refresh() {
  try {
    const response = await fetch("./api/project", { signal: AbortSignal.timeout(5000) });
    if (!response.ok) throw new Error("Snapshot unavailable");
    const snapshot = await response.json();
    dashboard.update(snapshot);
    loaded = true;
    connection.hidden = true;
  } catch {
    if (loaded) {
      connection.textContent = "Live updates are unavailable. Showing the last saved view.";
      connection.hidden = false;
    } else {
      dashboard.startup("error");
    }
  } finally {
    if (loaded) timer = setTimeout(refresh, 1500);
  }
}

root.addEventListener("click", (event) => {
  if (!event.target.closest("[data-retry]")) return;
  clearTimeout(timer);
  dashboard.startup("loading");
  refresh();
});

refresh();
