const artifact = document.querySelector("iframe");
let position, revision;

function reportSize() {
  const doc = artifact.contentDocument;
  if (doc?.URL !== "about:srcdoc" || !doc.body) return;
  const body = doc.body;
  const win = artifact.contentWindow;
  const bottom = body.getBoundingClientRect().bottom + win.scrollY + (parseFloat(win.getComputedStyle(body).marginBottom) || 0);
  const overflow = doc.documentElement.scrollHeight;
  const height = overflow > Math.max(artifact.clientHeight, Math.ceil(bottom)) ? overflow : bottom;
  parent.postMessage({ revision, height }, "*");
}
const resize = new ResizeObserver(reportSize);

addEventListener("message", ({ source, data }) => {
  if (source !== parent || typeof data?.html !== "string") return;
  if (!position && artifact.contentDocument?.URL === "about:srcdoc") {
    position = { left: artifact.contentWindow.scrollX, top: artifact.contentWindow.scrollY, behavior: "instant" };
  }
  resize.disconnect();
  revision = data.revision;
  artifact.srcdoc = data.html;
});

artifact.addEventListener("load", () => {
  const doc = artifact.contentDocument;
  if (doc?.URL !== "about:srcdoc" || !doc.body) return;
  if (position) {
    artifact.contentWindow.scrollTo(position);
    position = undefined;
  }
  reportSize();
  resize.observe(doc.body);
});
