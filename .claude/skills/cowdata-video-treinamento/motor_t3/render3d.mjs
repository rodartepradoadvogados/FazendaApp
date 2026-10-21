// node render3d.mjs <saida> <t0> <t1>   |   node render3d.mjs <saida> lista 1.0,2.5
// Env: PAGE (cena/<arquivo>.html, padrão index.html) · PORT (8123) · FMT=jpg|png (padrão png; jpg q95 para o episódio) · DEDUP=1 (quadros com a mesma window.sig(t) viram hardlink do anterior)
import { createRequire } from "module"; import fs from "fs"; import path from "path"; import http from "node:http";
const require = createRequire("/opt/node-tools/node_modules/"); const { chromium } = require("playwright");
const [, , out, a, b] = process.argv; fs.mkdirSync(out, { recursive: true });
const FMT = process.env.FMT === "jpg" ? "jpg" : "png";
let tempos = [];
if (a === "lista") tempos = b.split(",").map(Number); else { const f0 = Math.round(Number(a) * 30), f1 = Math.round(Number(b) * 30); for (let i = f0; i < f1; i++) tempos.push(i / 30); }
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "cena");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".png": "image/png", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".json": "application/json" };
const srv = http.createServer((q, r) => { const f = path.join(ROOT, decodeURIComponent(q.url.split("?")[0]).replace(/^\/$/, "/" + (process.env.PAGE || "index.html"))); fs.readFile(f, (e, d) => { if (e) { r.statusCode = 404; return r.end(); } r.setHeader("Content-Type", MIME[path.extname(f)] || "application/octet-stream"); r.end(d); }); });
await new Promise((ok) => srv.listen(Number(process.env.PORT || 8123), ok));
const br = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--force-color-profile=srgb"] });
const p = await br.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
p.on("pageerror", (e) => console.error("ERRO", e.message)); p.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !/404/.test(m.text())) console.error("console", m.text().slice(0, 300)); });
await p.goto(`http://localhost:${process.env.PORT || 8123}/`); await p.waitForFunction(() => window.__ready, null, { timeout: 120000 });
let i = 0, dup = 0; const t0 = Date.now(); let prev = null;
const nomeDe = (t) => (a === "lista" ? `t${t.toFixed(2).padStart(6, "0")}.${FMT}` : `q${String(Math.round(t * 30)).padStart(5, "0")}.${FMT}`);
for (const t of tempos) {
  const nm = path.join(out, nomeDe(t)); const sig = process.env.DEDUP ? await p.evaluate((t) => (window.sig ? window.sig(t) : "u" + t), t) : "u" + t;
  if (fs.existsSync(nm) && fs.statSync(nm).size > 5000) { prev = { sig, nm }; continue; }
  if (process.env.DEDUP && prev && prev.sig === sig && !sig.startsWith("u") && fs.existsSync(prev.nm)) { fs.linkSync(prev.nm, nm); dup++; prev = { sig, nm }; continue; }
  await p.evaluate((t) => window.seek(t), t);
  await p.screenshot(FMT === "jpg" ? { path: nm, type: "jpeg", quality: 95 } : { path: nm }); i++; prev = { sig, nm };
}
await br.close(); srv.close(); console.log("quadros", i, "copiados", dup, (i ? (Date.now() - t0) / i / 1000 : 0).toFixed(2), "s/quadro");
