import { icon } from "./icons.mjs";

export const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char]);

function inline(source) {
  let html = "", end = 0;
  for (const token of source.matchAll(/`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*|\[([^\]]+)\]\(([^()\s]+)\)/g)) {
    const [match, code, strong, em, label, url] = token;
    html += escapeHtml(source.slice(end, token.index));
    end = token.index + match.length;
    if (code) html += `<code>${escapeHtml(code)}</code>`;
    else if (strong) html += `<strong>${escapeHtml(strong)}</strong>`;
    else if (em) html += `<em>${escapeHtml(em)}</em>`;
    else html += /^https?:\/\//i.test(url)
      ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`
      : escapeHtml(match);
  }
  return html + escapeHtml(source.slice(end));
}

const heading = /^(#{1,6})\s+(.+)/;
const fence = /^\s{0,3}(`{3,}|~{3,})/;
const list = /^\s*(?:(\d+)[.)]|[-+*])\s+(.+)/;
const quote = /^>\s?/;
const rule = /^(?:-{3,}|\*{3,}|_{3,})\s*$/;
const tableRule = /^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$/;
const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((cell) => inline(cell.trim()));

// shortcut: Runweld documents use these Markdown blocks; adopt a full parser if richer Markdown becomes part of the evidence format.
export function renderMarkdown(source, firstLevel = 1) {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  for (let i = 0; i < lines.length;) {
    const line = lines[i++];
    if (!line.trim()) continue;
    const [marker, depth, body] = line.match(heading) ?? [];
    const boundary = line.match(fence)?.[1];
    const entry = line.match(list);
    if (boundary) {
      const code = [];
      const closes = new RegExp(`^\\s{0,3}${boundary[0]}{${boundary.length},}\\s*$`);
      while (i < lines.length && !closes.test(lines[i])) code.push(lines[i++]);
      i++;
      blocks.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
    } else if (marker) {
      const level = Math.min(6, depth.length + firstLevel - 1);
      blocks.push(`<h${level}>${inline(body)}</h${level}>`);
    } else if (rule.test(line)) {
      blocks.push("<hr>");
    } else if (entry) {
      const tag = entry[1] ? "ol" : "ul";
      const items = [entry[2]];
      for (let next; (next = lines[i]?.match(list)) && Boolean(next[1]) === Boolean(entry[1]); i++) items.push(next[2]);
      blocks.push(`<${tag}${entry[1] ? ` start="${entry[1]}"` : ""}>${items.map((item) => `<li>${inline(item)}</li>`).join("")}</${tag}>`);
    } else if (quote.test(line)) {
      const quoted = [line.replace(quote, "")];
      while (quote.test(lines[i] ?? "")) quoted.push(lines[i++].replace(quote, ""));
      blocks.push(`<blockquote><p>${inline(quoted.join(" "))}</p></blockquote>`);
    } else if (line.includes("|") && tableRule.test(lines[i] ?? "")) {
      const header = cells(line).map((cell) => `<th scope="col">${cell}</th>`).join("");
      const rows = [];
      i++;
      while (lines[i]?.includes("|")) rows.push(`<tr>${cells(lines[i++]).map((cell) => `<td>${cell}</td>`).join("")}</tr>`);
      blocks.push(`<div class="document-table"><table><thead><tr>${header}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`);
    } else {
      const paragraph = [line];
      while (lines[i]?.trim() && ![heading, fence, list, quote, rule].some((pattern) => pattern.test(lines[i]))) {
        paragraph.push(lines[i++]);
      }
      blocks.push(`<p>${inline(paragraph.join(" "))}</p>`);
    }
  }
  return blocks.join("\n");
}

export function renderDiff(source) {
  return source.replace(/\r\n?/g, "\n").replace(/\n$/, "").split("\n").map((line) => {
    const kind = /^(diff --git |index |@@|--- |\+\+\+ )/.test(line) ? "meta"
      : line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "ctx";
    return `<span class="${kind}">${escapeHtml(line)}</span>`;
  }).join("");
}

export function renderTerminal(source) {
  return source.replace(/\r\n?/g, "\n").split("\n").map((line) =>
    line.startsWith("$ ") ? `<span class="command">${escapeHtml(line)}</span>` : escapeHtml(line)).join("\n");
}

const captions = {
  image: "Saved image artifact.",
  html: "Rendered from saved HTML. Scripts and external resources are disabled.",
  text: "Saved text artifact.",
  diff: "Recorded source changes.",
};

export function readerMarkup(open, url) {
  const { kind, badge } = open;
  const fileIcon = kind === "image" ? "photo" : kind === "html" ? "code" : "file";
  const label = badge?.text ?? open.label ?? (open.role === "reference" ? "Guide"
    : kind === "diff" ? "Source" : kind === "markdown" ? "Document" : "Artifact");
  const tone = ["blue", "neutral", "orange", "green"].includes(badge?.tone) ? badge.tone
    : kind === "diff" ? "neutral" : "blue";
  return `<div class="rx-filebar">${icon(fileIcon, true)}<b tabindex="-1">${escapeHtml(open.sourceName ?? open.title)}</b><span class="rx-chip rx-${tone}">${escapeHtml(label)}</span></div><div data-evidence-reader="${escapeHtml(url)}" data-kind="${escapeHtml(kind)}" data-revision="${escapeHtml(open.revision)}" data-title="${escapeHtml(open.title)}" data-caption="${escapeHtml(open.caption ?? captions[kind])}" data-browser-address="${escapeHtml(open.browserAddress || "Rendered HTML")}" aria-busy="true"><p class="rx-note" role="status">Opening document…</p></div>`;
}

export function updateReader(reader, nextReader) {
  const oldBar = reader.previousElementSibling;
  const newBar = nextReader.previousElementSibling;
  if (oldBar.outerHTML !== newBar.outerHTML) {
    const focused = oldBar.contains(document.activeElement);
    oldBar.replaceWith(newBar);
    if (focused) newBar.querySelector("b").focus({ preventScroll: true });
  }
  const { title, caption, browserAddress } = nextReader.dataset;
  Object.assign(reader.dataset, { title, caption, browserAddress });
  const figure = reader.querySelector("figure");
  if (!figure) return;
  const text = figure.querySelector("figcaption");
  const address = figure.querySelector(".rx-browser span");
  const image = figure.querySelector("img");
  const frame = figure.querySelector("iframe");
  if (text.textContent !== caption) text.textContent = caption;
  if (address && address.textContent !== browserAddress) {
    address.textContent = browserAddress;
    address.closest("button")?.setAttribute("aria-label", browserAddress + " · Open original HTML preview");
  }
  if (image && image.dataset.recordedAlt === undefined && image.alt !== title) image.alt = title;
  if (frame && frame.title !== title) frame.title = title;
}

function preview(reader, content) {
  const figure = document.createElement("figure");
  figure.className = "rx-preview";
  if (typeof content === "string") figure.innerHTML = content;
  else figure.append(content);
  const caption = document.createElement("figcaption");
  caption.textContent = reader.dataset.caption;
  figure.append(caption);
  return figure;
}

// Only an unstyled single-image document can be shown unchanged outside the HTML sandbox.
export function passiveHtmlImage(source) {
  const doc = /^\s*(?:<!doctype html>\s*)?<html>\s*<head>([\s\S]*?)<\/head>\s*<body\s+style=(["'])\s*margin:\s*0\s*;?\s*\2>\s*<img([^<>]+)>\s*<\/body>\s*<\/html>\s*$/i.exec(source);
  const metadata = /<title>[^<]*<\/title>|<meta\s+(?:charset="utf-8"|name="viewport"\s+content="width=device-width")\s*\/?>/gi;
  if (!doc || doc[1].replace(metadata, "").trim()) return;
  const attributes = new Map();
  const extra = doc[3].replace(/\s+(src|alt|style)\s*=\s*(?:"([^"]*)"|'([^']*)')/gi, (match, name, double, single) => {
    name = name.toLowerCase();
    if (attributes.has(name)) return match;
    attributes.set(name, double ?? single);
    return "";
  });
  const alt = attributes.get("alt") ?? "";
  const style = attributes.get("style")?.replace(/\s/g, "").replace(/;$/, "").split(";").sort().join(";");
  if (!/^\s*\/?$/.test(extra) || alt.includes("&") || style !== "display:block;width:100%") return;
  const src = attributes.get("src");
  const encoded = /^data:image\/(png|jpeg|gif|webp);base64,([A-Za-z0-9+/]+={0,2})$/.exec(src ?? "");
  if (!encoded || encoded[2].length % 4 !== 0) return;
  const signatures = { png: /^\x89PNG\r\n\x1a\n/, jpeg: /^\xff\xd8\xff/, gif: /^GIF8[79]a/, webp: /^RIFF....WEBP/s };
  if (signatures[encoded[1]].test(atob(encoded[2].slice(0, 16)))) return { src, alt };
}

function browserBar(address, interactive) {
  const contents = icon("code", true) + `<span>${escapeHtml(address)}</span>`;
  return interactive
    ? `<button type="button" class="rx-browser" title="Open original HTML preview" aria-label="${escapeHtml(address)} · Open original HTML preview">${contents}</button>`
    : `<div class="rx-browser">${contents}</div>`;
}

const previewPolicy = "<!doctype html><meta charset=utf-8>" +
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; form-action \'none\'; base-uri \'none\'">';

export async function loadEvidence(reader, signal, preservePosition) {
  const { evidenceReader: url, kind, revision } = reader.dataset;
  delete reader.dataset.evidenceReady;
  reader.setAttribute("aria-busy", "true");
  function ready(status) {
    reader.dataset.evidenceReady = status;
    reader.removeAttribute("aria-busy");
  }
  function replace(content) {
    if (signal.aborted) return;
    const [x, y] = [window.scrollX, window.scrollY];
    const before = reader.querySelector("pre");
    const scrollLeft = before?.scrollLeft;
    const scrollTop = before?.scrollTop;
    const focused = before === document.activeElement;
    if (typeof content === "string") reader.innerHTML = content;
    else reader.replaceChildren(content);
    if (preservePosition) {
      const pre = reader.querySelector("pre");
      if (pre && scrollLeft !== undefined) {
        if (focused) pre.focus({ preventScroll: true });
        pre.scrollLeft = scrollLeft;
        pre.scrollTop = scrollTop;
      }
      window.scrollTo(x, y);
    }
  }
  function unavailable() {
    replace('<p class="rx-note" role="status">This document is unavailable.</p>');
    if (!signal.aborted) ready("error");
  }

  async function showHtml(source, focus = false) {
    if (signal.aborted) return;
    let frame = reader.querySelector("iframe");
    if (!frame) {
      const controller = await fetch("./preview-controller.js", { signal });
      if (!controller.ok) throw new Error("Preview unavailable");
      const script = await controller.text();
      frame = document.createElement("iframe");
      frame.title = reader.dataset.title;
      // A data document shares its opaque origin with the script-disabled artifact, not the dashboard.
      frame.setAttribute("sandbox", "allow-scripts allow-same-origin");
      frame.src = "data:text/html;charset=utf-8," + encodeURIComponent(`<!doctype html><style>
        html,body,iframe{width:100%;height:100%;margin:0;border:0;display:block;overflow:hidden}
        </style><iframe sandbox="allow-same-origin" title="HTML artifact"></iframe><script>${script}</script>`);
      frame.addEventListener("load", () => { frame.dataset.ready = ""; }, { once: true });
      const figure = preview(reader, frame);
      figure.insertAdjacentHTML("afterbegin", browserBar(reader.dataset.browserAddress, false));
      replace(figure);
      if (focus && !signal.aborted) frame.focus({ preventScroll: true });
    }
    const send = () => frame.contentWindow.postMessage({ revision, html: previewPolicy + source }, "*");
    if (!signal.aborted) {
      window.addEventListener("message", (event) => {
        if (event.source !== frame.contentWindow || event.data?.revision !== revision) return;
        const { height } = event.data;
        if (Number.isFinite(height) && height > 0) {
          const size = `${Math.min(height, 880)}px`;
          if (frame.style.height !== size) {
            const [x, y] = [window.scrollX, window.scrollY];
            frame.style.height = size;
            if (preservePosition) window.scrollTo(x, y);
          }
        }
        ready("loaded");
      }, { signal });
      if (frame.dataset.ready !== undefined) send();
      else frame.addEventListener("load", send, { once: true, signal });
    }
  }

  async function showPassive(photo, source) {
    const image = document.createElement("img");
    image.src = photo.src;
    image.alt = photo.alt || reader.dataset.title;
    if (photo.alt) image.dataset.recordedAlt = "";
    try {
      await image.decode();
    } catch {
      return false;
    }
    if (signal.aborted) return true;
    const figure = preview(reader, image);
    figure.insertAdjacentHTML("afterbegin", browserBar(reader.dataset.browserAddress, true));
    figure.firstElementChild.addEventListener("click", () => {
      reader.dataset.previewMode = "html";
      delete reader.dataset.evidenceReady;
      reader.setAttribute("aria-busy", "true");
      showHtml(source, true).catch(unavailable);
    }, { once: true });
    replace(figure);
    ready("loaded");
    return true;
  }

  try {
    const response = await fetch(url, { signal });
    if (!response.ok) throw new Error("Evidence unavailable");
    if (kind === "image") {
      const image = document.createElement("img");
      const blob = URL.createObjectURL(await response.blob());
      if (signal.aborted) {
        URL.revokeObjectURL(blob);
        return;
      }
      signal.addEventListener("abort", () => URL.revokeObjectURL(blob), { once: true });
      image.src = blob;
      await image.decode();
      if (signal.aborted) return;
      image.alt = reader.dataset.title;
      replace(preview(reader, image));
      ready("loaded");
      return;
    }
    const source = await response.text();
    if (kind === "html") {
      const photo = reader.dataset.previewMode !== "html" && passiveHtmlImage(source);
      if (!photo || !await showPassive(photo, source)) await showHtml(source);
    } else if (kind === "markdown") {
      replace(`<article class="rx-reader">${renderMarkdown(source, 4)}</article>`);
      if (!signal.aborted) ready("loaded");
    } else {
      const markup = kind === "diff"
        ? `<pre class="rx-diff" tabindex="0">${renderDiff(source)}</pre>`
        : `<pre class="rx-terminal" tabindex="0">${renderTerminal(source)}</pre>`;
      replace(preview(reader, markup));
      if (!signal.aborted) ready("loaded");
    }
  } catch {
    unavailable();
  }
}
