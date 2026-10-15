// MODELO de gravação de tela com cursor visível (Playwright + Chromium). Não é um tutorial: é o esqueleto
// que provou, em 14/10/2026, que dá a gravar 1920x1080 com cliques reais no app de demonstração.
//
//   node gravar_exemplo.mjs            (lê usuário/senha de $DEMO_DIR/cred.txt; DEMO_DIR padrão /tmp/cowdata-demo)
//
// Pré-requisitos já resolvidos aqui (ver REGISTRO_PREPARACAO.md §6):
//  - LANGUAGE/LC_ALL/LANG = pt_BR no ambiente do Chromium → datas em dd/mm/aaaa (sem isso saem mm/dd/yyyy);
//  - login FORA da gravação (storageState) → o vídeo já começa dentro do sistema (a tela de login e a Capa
//    citam a fazenda real, não podem aparecer);
//  - cursor desenhado por script (o Chromium headless não desenha cursor no vídeo);
//  - build de PRODUÇÃO do front (next start), senão o selo "N"/"Compiling" do modo dev aparece no canto.
// O Playwright grava a 25 fps em WebM (VP8); converta com ffmpeg (-r 30 -c:v libx264 -pix_fmt yuv420p).
import { createRequire } from "module";
import fs from "fs";
import path from "path";
const require = createRequire(process.env.PW_NODE_MODULES || "/opt/node-tools/node_modules/");
const { chromium } = require("playwright");

const DEMO = process.env.DEMO_DIR || "/tmp/cowdata-demo";
const FRONT = process.env.FRONT || "http://localhost:3000";
const cred = fs.readFileSync(`${DEMO}/cred.txt`, "utf8");
const usuario = cred.match(/usuario:\s+(\S+)/)[1];
const senha = cred.match(/senha:\s+(\S+)/)[1];
const SAIDA = path.join(DEMO, "gravacoes");
fs.mkdirSync(SAIDA, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium",
  args: ["--no-sandbox", "--lang=pt-BR", "--accept-lang=pt-BR"],
  env: { ...process.env, LANGUAGE: "pt_BR:pt", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" },
});
const base = { viewport: { width: 1920, height: 1080 }, locale: "pt-BR", timezoneId: "America/Sao_Paulo" };

// 1) login fora da gravação
const c0 = await browser.newContext(base);
const p0 = await c0.newPage();
await p0.goto(`${FRONT}/login`, { waitUntil: "networkidle" });
await p0.fill("#login-usuario", usuario);
await p0.fill("#login-senha", senha);
await p0.keyboard.press("Enter");
await p0.waitForTimeout(3000);
await c0.storageState({ path: `${DEMO}/estado.json` });
await c0.close();

// 2) contexto gravado, já logado
const ctx = await browser.newContext({ ...base, storageState: `${DEMO}/estado.json`, recordVideo: { dir: SAIDA, size: { width: 1920, height: 1080 } } });
const page = await ctx.newPage();
await page.addInitScript(() => {
  const mk = () => {
    const d = document.createElement("div");
    d.style.cssText = "position:fixed;z-index:2147483647;width:22px;height:22px;border-radius:50%;background:rgba(201,164,76,.55);border:2px solid #8A6D2F;pointer-events:none;transform:translate(-50%,-50%);left:-50px;top:-50px";
    document.documentElement.appendChild(d);
    document.addEventListener("mousemove", (e) => { d.style.left = e.clientX + "px"; d.style.top = e.clientY + "px"; }, true);
  };
  if (document.readyState !== "loading") mk(); else document.addEventListener("DOMContentLoaded", mk);
});

// Move o cursor até o elemento (com passos, para ficar legível no vídeo) e clica.
async function clicar(locator, passos = 25) {
  const b = await locator.boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: passos });
  await page.waitForTimeout(250);
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
}

await page.goto(`${FRONT}/financeiro?sub=resumo`, { waitUntil: "networkidle" });
await page.waitForTimeout(1200);
await page.mouse.move(300, 300);
await clicar(page.getByText("Contas", { exact: true }).first()); // o DOM tem "Contas"; a caixa-alta é CSS
await page.waitForTimeout(2000);

await ctx.close(); // fecha o vídeo
await browser.close();
console.log("gravado em", SAIDA);
