// node render_todas.mjs roteiro.json quadros/ [ids...]  → quadros/cN/qNNNN.png (0..(dur+transição)*fps)
import { createRequire } from "module"; import fs from "fs"; import path from "path";
const require = createRequire("/opt/node-tools/node_modules/"); const { chromium } = require("playwright");
const [, , rot, out, ...ids] = process.argv; const R = JSON.parse(fs.readFileSync(rot, "utf8"));
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--disable-gpu", "--disable-partial-raster", "--force-color-profile=srgb"] });
for (const c of R.cenas) {
  if (ids.length && !ids.includes(String(c.id))) continue;
  const dir = path.join(out, "c" + c.id); fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  const p = await b.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  await p.goto("file://" + path.resolve(path.dirname(rot), c.html));
  await p.evaluate(cfg => window.montar(cfg), c.cfg);
  const n = Math.round((c.dur + R.transicao) * R.fps);
  for (let i = 0; i < n; i++) { await p.evaluate(t => window.seek(t), i / R.fps); await p.screenshot({ path: `${dir}/q${String(i).padStart(4, "0")}.png` }); }
  await p.close(); console.log("cena", c.id, n, "quadros");
}
await b.close();
