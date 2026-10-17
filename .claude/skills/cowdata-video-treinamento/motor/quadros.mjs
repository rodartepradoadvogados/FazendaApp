// node render/quadros.mjs <saida> <t0> <t1> [fps]   ou   node render/quadros.mjs <saida> lista 1.0,2.5,...
import { createRequire } from "module"; import fs from "fs"; import path from "path";
const require = createRequire("/opt/node-tools/node_modules/"); const { chromium } = require("playwright");
const [, , out, a, b, fpsArg] = process.argv; fs.mkdirSync(out, { recursive: true });
let tempos = [];
if (a === "lista") tempos = b.split(",").map(Number);
else { const f0 = Math.round(Number(a) * 30), f1 = Math.round(Number(b) * 30); for (let i = f0; i < f1; i++) tempos.push(i / 30); }
const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--disable-gpu", "--force-color-profile=srgb", "--allow-file-access-from-files"] });
const p = await br.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
p.on("pageerror", e => console.error("ERRO", e.message)); p.on("console", m => { if (m.type() === "error") console.error("console", m.text()); });
await p.goto("file://" + path.resolve(process.env.HTML || "cena.html")); await p.evaluate(() => window.__ready);
let i = 0;
for (const t of tempos) {
  await p.evaluate(t => window.seek(t), t);
  const nome = a === "lista" ? `t${t.toFixed(2).padStart(6, "0")}.png` : `q${String(Math.round(t * 30)).padStart(5, "0")}.png`;
  await p.screenshot({ path: path.join(out, nome) }); i++;
}
await br.close(); console.log("quadros", i);
