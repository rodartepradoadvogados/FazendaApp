// T3 · Ep.1 (teste 3D) — Menu (Reprodução aberta) e Agenda Reprodutiva, telas REAIS do app em produção contra o stub (EP=t3e1). DPR 3.
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const OUT = "shots_t3/"; fs.mkdirSync(OUT, { recursive: true });
const API = "http://localhost:8000";
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const ctx = await novoContexto(br, 844, 3);
await ctx.addInitScript(() => {
  const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
  new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache")) localStorage.removeItem(k); } catch {}
});
const p = await pagina(ctx);
const esp = (ms = 700) => p.waitForTimeout(ms);
const meta = {};
await fetch(API + "/__reset");
// 1) Menu com todas as seções recolhidas (placas) e 2) Reprodução aberta
await p.goto("http://localhost:3000/app/menu", { waitUntil: "networkidle" }); await esp(1500);
await p.evaluate(() => localStorage.setItem("mob_menu_secoes_colapsadas", JSON.stringify(["protocolos-restrito","reproducao","sanidade","alimentacao","producao","gestao","financeiro","modulos","administracao","app"])));
await p.reload({ waitUntil: "networkidle" }); await esp(1500);
await p.screenshot({ path: OUT + "menu_fechado.png" });
const heads = await p.$$eval("button[aria-expanded]", (bs) => bs.map((b) => { const r = b.getBoundingClientRect(); const c = b.closest("div")?.parentElement; const rr = (b.parentElement || b).getBoundingClientRect(); return { txt: b.innerText.replace(/\s+/g, " ").trim(), x: r.x, y: r.y, w: r.width, h: r.height, px: rr.x, py: rr.y, pw: rr.width, ph: rr.height }; }));
meta.heads = heads;
const nomes = ["reproducao","sanidade","alimentacao","producao","gestao","financeiro"];
for (let i = 0; i < 6; i++) { const h = heads[i]; await p.screenshot({ path: OUT + `placa_${nomes[i]}.png`, clip: { x: h.px, y: h.py, width: h.pw, height: h.ph } }); } console.log(heads.map((h) => h.txt + " " + Math.round(h.y) + " " + Math.round(h.h)).join("\n"));
// abre Reprodução
await p.locator('button[aria-expanded]', { hasText: "Reprodução" }).first().click(); await esp(900);
await p.screenshot({ path: OUT + "menu_repro.png" });
{ const hh = await p.locator('button[aria-expanded]', { hasText: "Reprodução" }).first().evaluate((b) => { const r = b.parentElement.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); meta.reproCard = hh; await p.screenshot({ path: OUT + "placa_reproducao_aberta.png", clip: { x: hh.x, y: hh.y, width: hh.w, height: hh.h } }); }
meta.reproItem = await p.evaluate(() => { const b = [...document.querySelectorAll("button")].find((x) => x.innerText.includes("Agenda Reprodutiva")); const r = b.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
// 3) Agenda Reprodutiva
await p.locator("button", { hasText: "Agenda Reprodutiva" }).first().click(); await esp(2200);
await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); });
await esp(400);
await p.screenshot({ path: OUT + "agenda.png" });
// abre o card "Inseminadas 30–59"
const det = p.locator("details", { hasText: "Inseminadas 30–59" }).first();
const topo = async () => { await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); }); await esp(400); };
await det.locator("summary").click(); await esp(1200); await topo();
await p.screenshot({ path: OUT + "agenda_aberta.png" });
meta.card = await det.boundingBox(); meta.cardResumo = await det.locator("summary").boundingBox();
meta.cabecalho = await p.evaluate(() => { const h = document.querySelector("header"); const r = h.getBoundingClientRect(); const n = document.querySelector("nav.mob-nav").getBoundingClientRect(); return { hdrBottom: r.bottom, navTop: n.top }; });
await p.addStyleTag({ content: "nav.mob-nav,header{visibility:hidden!important}" }); await esp(200);
await p.setViewportSize({ width: 390, height: 1500 }); await esp(700); await topo();
{ const bb = await det.boundingBox(); meta.cardAlto = bb; await p.screenshot({ path: OUT + "card_insem.png", clip: { x: bb.x, y: bb.y, width: bb.width, height: bb.height } }); }
await p.setViewportSize({ width: 390, height: 844 }); await esp(700); await topo();
await det.evaluate((e) => (e.style.visibility = "hidden")); await esp(300);
await p.screenshot({ path: OUT + "agenda_vazio_sem_moldura.png" });
await p.addStyleTag({ content: "nav.mob-nav,header{visibility:visible!important}" }); await esp(300); await topo();
await p.screenshot({ path: OUT + "agenda_vazio.png" });
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(meta, null, 1));
await br.close();
