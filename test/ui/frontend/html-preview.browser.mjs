import { writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

export default async ({ page, step, expect, shot, size }) => {
  const artifact = process.env.RUNWELD_PREVIEW_FIXTURE;
  const outer = page.locator("[data-evidence-reader] iframe");
  const preview = async () => {
    const frame = outer.contentFrame();
    return await outer.getAttribute("src") ? frame.locator("iframe") : outer;
  };
  const body = async () => (await preview()).contentFrame().locator("body");
  await size(1280, 800);
  await step("a revised HTML artifact preserves its reading position [dashboard#phase-graph]", async () => {
    await page.getByRole("main").getByRole("button", { name: /reader update/i }).click();
    await page.getByRole("navigation", { name: "Stages", exact: true }).getByRole("button", { name: /prototype/i }).click();
    await page.getByRole("button", { name: "Recorded capture" }).click();
    const heading = async () => (await body()).locator("h1").textContent({ timeout: 500 });
    const position = async () => (await body()).evaluate(() => window.scrollY);
    await expect(heading, "Original preview", "initial artifact heading");
    await (await body()).evaluate(() => window.scrollTo(0, 800));
    await expect(position, 800, "initial preview scroll position");
    writeFileSync(artifact, `<h1>Revised preview</h1><div style="height:1900px"></div><p>Lower content</p>`);
    await expect(heading, "Revised preview", "refreshed artifact heading");
    await expect(position, 800, "refreshed preview scroll position");
  });
  await step("HTML evidence remains opaque to the dashboard and script-disabled [dashboard#task-evidence]", async () => {
    await expect(() => outer.evaluate((frame) => frame.contentDocument === null), true,
      "dashboard cannot read the preview frame");
    await expect(async () => (await body()).evaluate(() => window.origin), "null", "opaque artifact origin");
    const owner = await preview();
    await expect(() => owner.evaluate((node) => node.hasAttribute("sandbox") && !node.sandbox.contains("allow-scripts")), true,
      "artifact sandbox disables scripts");
  });
  async function pixel(png, offset) {
    return page.evaluate(async ({ data, offset }) => {
      const image = new Image();
      image.src = `data:image/png;base64,${data}`;
      await image.decode();
      const ctx = document.createElement("canvas").getContext("2d");
      ctx.drawImage(image, -offset, -offset);
      return [...ctx.getImageData(0, 0, 1, 1).data].join(",");
    }, { data: png.toString("base64"), offset });
  }
  const canvasPixel = async () => pixel(await outer.screenshot({ scale: "css" }), 4);
  async function standalonePixel() {
    const direct = await page.context().newPage();
    try {
      await direct.goto(pathToFileURL(artifact).href);
      return await pixel(await direct.screenshot({ clip: { x: 4, y: 4, width: 1, height: 1 }, scale: "css" }), 0);
    } finally {
      await direct.close();
    }
  }
  await step("transparent HTML uses the standalone document canvas on desktop and mobile [dashboard#task-evidence]", async () => {
    await (await body()).evaluate(() => window.scrollTo(0, 0));
    const pixels = [];
    for (const width of [1280, 390]) {
      await size(width, 800);
      pixels.push(await canvasPixel());
      await shot(`html-transparent-${width}`);
    }
    const standalone = await standalonePixel();
    await expect(pixels.join(" / "), [standalone, standalone].join(" / "), "painted document canvas");
  });
  await step("HTML preview preserves an explicit artifact background [dashboard#task-evidence]", async () => {
    writeFileSync(artifact, '<style>body { background: #25354a; color: white }</style><h1>Styled preview</h1>');
    await expect(async () => (await body()).locator("h1").textContent({ timeout: 500 }), "Styled preview", "styled artifact heading");
    await expect(canvasPixel, await standalonePixel(), "painted artifact background");
    return shot("html-styled-390");
  });
};
