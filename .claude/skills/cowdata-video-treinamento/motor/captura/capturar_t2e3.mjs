// Temporada 2 · Ep. 3 — Reprodutivo › Diagnóstico de gestação. Captura as telas REAIS do app (produção) contra o stub (EP=t2e3).
// Rodar:  EP=t2e3 node stub-api.mjs &   (frontend: next start)   node capturar_t2e3.mjs
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const OUT = "shots/"; fs.mkdirSync(OUT, { recursive: true }); const mapa = {};
const API = "http://localhost:8000";
const cfg = (o) => fetch(API + "/__cfg", { method: "POST", body: JSON.stringify(o) });
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });

async function sessao() {
  await fetch(API + "/__reset");
  const ctx = await novoContexto(br);
  // o cabeçalho do app tem o nome de uma fazenda real escrito direto no layout; no vídeo só vale o nome fictício
  await ctx.addInitScript(() => {
    const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
    new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
  });
  return { ctx, p: await pagina(ctx) };
}
let p;
const esp = (ms = 650) => p.waitForTimeout(ms);
async function caixas(sel) {
  const o = {};
  for (const [k, s] of Object.entries(sel)) {
    const l = p.locator(s).first();
    if (!(await l.count())) { o[k] = null; continue; }
    const b = await l.boundingBox(); o[k] = b && { x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1), h: +b.height.toFixed(1) };
  }
  return o;
}
const scrollar = (y) => p.evaluate((y) => { document.activeElement?.blur?.(); window.scrollTo(0, y); document.body.scrollTo(0, y); document.scrollingElement.scrollTo(0, y); }, y);
// A barra de ação do Diagnóstico não tem classe (é uma div sticky com botões .mob-btn): marcamos com data-vbarra para medir e esconder.
const marcarBarra = () => p.evaluate(() => { document.querySelectorAll("[data-vbarra]").forEach((e) => e.removeAttribute("data-vbarra")); const d = [...document.querySelectorAll("div")].find((e) => getComputedStyle(e).position === "sticky" && e.querySelector(":scope > button.mob-btn")); if (d) d.setAttribute("data-vbarra", "1"); return !!d; });
// tall = captura alta (barra escondida) para o motor rolar a imagem; scroll = posição da página na captura normal
async function snap(nome, { tall = false, alvos = {}, scroll = 0, tallMax = 3000 } = {}) {
  await esp(); await scrollar(scroll); await esp(250);
  const temBarra = await marcarBarra();
  const navTop = await p.evaluate(() => document.querySelector("nav.mob-nav").getBoundingClientRect().top);
  const barTop = temBarra ? await p.evaluate(() => document.querySelector("[data-vbarra]").getBoundingClientRect().top) : navTop;
  await p.screenshot({ path: `${OUT}${nome}.png` });
  const m = { img: `${nome}.png`, w: 390, h: 844, hdr: 95.78, barTop: +barTop.toFixed(1), navTop: +navTop.toFixed(1), scroll, alvos: await caixas(alvos) };
  m.alvosN = m.alvos;
  if (tall) {
    await p.setViewportSize({ width: 390, height: tallMax }); await esp(500);
    await p.addStyleTag({ content: "[data-vbarra]{display:none!important}" });
    const fim = await p.evaluate((lim) => { let m = 0; document.querySelectorAll("main *").forEach((e) => { const r = e.getBoundingClientRect(); if (r.height && r.bottom < lim - 50) m = Math.max(m, r.bottom); }); return m; }, tallMax);
    const H = Math.max(844, Math.ceil(fim + 24 + 69));
    await p.setViewportSize({ width: 390, height: H }); await esp(500);
    await p.screenshot({ path: `${OUT}${nome}_tall.png` });
    m.tall = { img: `${nome}_tall.png`, h: H, alvos: await caixas(alvos) };
    await p.evaluate(() => { for (const s of document.querySelectorAll("style")) if (s.textContent.includes("[data-vbarra]{display:none!important}")) s.remove(); });
    await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  }
  mapa[nome] = m; console.log(nome, tall ? `tall H=${m.tall.h}` : "", scroll ? `scroll=${scroll}` : "", "barTop", m.barTop);
}
const cartao = (b) => `button[aria-pressed]:has(span:text-is("${b}"))`;
const sit = (r) => `[aria-label="Situação"] button:has-text("${r}")`;
const BARRA = "[data-vbarra]";
const A1 = {
  passo: "p:has-text('Passo 1 de 2')", origem: "[aria-label=Origem]", btnAnimais: "[aria-label=Origem] button:has-text('Animais')", situacao: '[aria-label="Situação"]',
  btnATocar: sit("A tocar"), btnATocarN: sit("A tocar") + " b", btnReconfirmar: sit("A reconfirmar"), btnReconfirm: sit("Reconfirm."), notaSit: "p:has-text('Inseminadas ainda sem diagnóstico')",
  selPrazo: "button:has-text('Selecionar todas no prazo')", grupoAlta: "div:text-is('01 - Alta · 5')", grupoMedia: "div:text-is('02 - Média · 4')",
  aviso: "[role=status], .mob-aviso, div:has-text('Diagnóstico salvo para')", legenda: ".ft-legenda",
  barra: BARRA, barraTxt: BARRA + " > span", continuar: BARRA + " button.mob-btn",
};
for (const n of ["4318", "4455", "4731", "4846", "4902", "2127", "2263", "2342", "2388"]) {
  A1["c" + n] = cartao(n); A1["cx" + n] = cartao(n) + " > span:first-child"; A1["b" + n] = cartao(n) + ` span:text-is("${n}")`; A1["i" + n] = cartao(n) + " > span:nth-child(2) > span:nth-child(2)";
}
A1.selo4902 = cartao("4902") + " .ft-selo"; A1.selo4846 = cartao("4846") + " .ft-selo";
const A2 = {
  passo: "p:has-text('Passo 2 de 2')", resumo: "div:has(> div:text-is('5 animais'))", resumoN: "div:text-is('5 animais'), div:text-is('2 animais')", alterar: "button:has-text('Alterar')",
  resultado: '[aria-label="Resultado do diagnóstico"]', rRet: '[aria-label="Resultado do diagnóstico"] button:has-text("Positivo — para retoque")', rReconf: '[aria-label="Resultado do diagnóstico"] button:has-text("Positivo — reconfirmada")',
  rNeg: '[aria-label="Resultado do diagnóstico"] button:has-text("Negativo")', rInd: '[aria-label="Resultado do diagnóstico"] button:has-text("Indefinido")',
  rRetTit: '[aria-label="Resultado do diagnóstico"] button:has-text("Positivo — para retoque") b', rRetDica: '[aria-label="Resultado do diagnóstico"] button:has-text("Positivo — para retoque") span',
  rNegDica: '[aria-label="Resultado do diagnóstico"] button:has-text("Negativo") span',
  data: "#dg-data", metodo: "#dg-metodo", nota: "#dg-metodo ~ p", notaSemMetodo: "p:has-text('Escolha o resultado')",
  barra: BARRA, salvar: BARRA + " button.mob-btn:has-text('Salvar (')", salvarLancar: BARRA + " button:has-text('Salvar e lançar inseminação')", salvando: BARRA + " button:has-text('Salvando')",
};
const AI = { passo: "p:has-text('Passo 1 de 2')", barra: ".lote-barra", barraN: ".lote-barra .n", continuar: ".lote-barra .lote-cta", situacao: '[aria-label="Situação"]', origem: "[aria-label=Origem]" };
for (const n of ["4731", "2388"]) { AI["c" + n] = `.lote-cartao:has(.brinco:text-is("${n}"))`; AI["cx" + n] = AI["c" + n] + " .lote-cx"; }

// ───────────── O fluxo feliz: 5 positivas, depois 2 negativas → Inseminação ─────────────
({ p } = await sessao());
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await snap("s01_lancar", { alvos: { repro: "button.mob-bloco:has-text('Reprodutivo')", navLancar: "nav.mob-nav >> text=Lançar" } });
await p.locator("button.mob-bloco", { hasText: "Reprodutivo" }).first().click(); await esp(500);
await snap("s02_repro_grade", { alvos: { inseminacao: "button.mob-bloco:has-text('Inseminação')", diagnostico: "button.mob-bloco:has-text('Diagnóstico')" } });
await p.locator("button.mob-bloco", { hasText: "Diagnóstico" }).first().click(); await esp(1500);
await snap("s03_p1", { tall: true, alvos: A1 });
const marcar = ["4318", "4455", "2127", "2263", "2342"];
for (const [i, n] of marcar.entries()) { await p.locator(cartao(n)).click(); await esp(250); await snap(`s${String(4 + i).padStart(2, "0")}_marca${i + 1}`, { tall: true, alvos: A1 }); }
await p.locator(BARRA + " button.mob-btn", { hasText: "Continuar" }).click(); await esp(900);
await snap("s09_p2", { tall: true, alvos: A2 });
await p.locator('[aria-label="Resultado do diagnóstico"] button', { hasText: "Positivo — para retoque" }).click(); await esp(300);
await snap("s10_p2_retoque", { tall: true, alvos: A2 });
await p.selectOption("#dg-metodo", "Palpação"); await esp(300);
await snap("s11_p2_metodo", { tall: true, alvos: A2 });
await cfg({ atraso: 1100, falhar: [] });
await p.locator(BARRA + " button.mob-btn", { hasText: "Salvar (" }).click();
await p.waitForSelector("text=Salvando…", { timeout: 5000 });
await snap("s12_salvando", { tall: false, alvos: A2 });
await p.waitForFunction(() => document.body.innerText.includes("Diagnóstico salvo para"), null, { timeout: 20000 }); await cfg({ atraso: 0 });
await snap("s13_p1_salvo", { tall: true, alvos: A1 });
const logA = await (await fetch(API + "/__log")).json(); console.log("POSTs:", logA.filter((x) => x.p === "/reproducao/diagnostico").map((x) => x.b.numero_matriz + ":" + x.b.resultado + ":" + x.b.metodo).join(" "));
await p.locator(cartao("4731")).click(); await esp(250); await snap("s14_marca_neg1", { tall: true, alvos: A1 });
await p.locator(cartao("2388")).click(); await esp(250); await snap("s15_marca_neg2", { tall: true, alvos: A1 });
await p.locator(BARRA + " button.mob-btn", { hasText: "Continuar" }).click(); await esp(900);
await snap("s16_p2_neg", { tall: true, alvos: A2 });
await p.locator('[aria-label="Resultado do diagnóstico"] button', { hasText: "Negativo" }).click(); await esp(300);
await snap("s17_p2_neg_ok", { tall: true, alvos: A2 });
await p.locator(BARRA + " button", { hasText: "Salvar e lançar inseminação" }).click(); await esp(1800);
await snap("s18_insem", { tall: true, alvos: AI });
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
