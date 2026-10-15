// Captura telas reais da demo (1920x1080, pt-BR), login fora. Uso: node capturar.mjs <saida_dir> <nome>=<caminho> ...
import { createRequire } from "module";
import fs from "fs";
const require = createRequire("/opt/node-tools/node_modules/");
const { chromium } = require("playwright");
const [, , OUT, ...alvos] = process.argv;
fs.mkdirSync(OUT, { recursive: true });
const cred = fs.readFileSync("/tmp/cowdata-demo/cred.txt", "utf8");
const usuario = cred.match(/usuario:\s+(\S+)/)[1], senha = cred.match(/senha:\s+(\S+)/)[1];
const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium", args: ["--no-sandbox", "--lang=pt-BR"],
  env: { ...process.env, LANGUAGE: "pt_BR:pt", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" },
});
const base = { viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2, locale: "pt-BR", timezoneId: "America/Sao_Paulo" };
const c0 = await browser.newContext(base); const p0 = await c0.newPage();
await p0.goto("http://localhost:3000/login", { waitUntil: "networkidle" });
await p0.fill("#login-usuario", usuario); await p0.fill("#login-senha", senha); await p0.keyboard.press("Enter");
await p0.waitForTimeout(3000); const st = await c0.storageState(); await c0.close();
const ctx = await browser.newContext({ ...base, storageState: st }); const page = await ctx.newPage();
for (const a of alvos) {
  const [nome, resto] = a.split("=");
  const [caminho, ...cliques] = resto.split("|");
  await page.goto("http://localhost:3000" + caminho, { waitUntil: "networkidle" });
  await page.waitForTimeout(2000);
  for (const t of cliques) { await page.getByText(t, { exact: true }).first().click(); await page.waitForTimeout(2500); }
  await page.screenshot({ path: `${OUT}/${nome}.png` });
  console.log("ok", nome);
}
await browser.close();
