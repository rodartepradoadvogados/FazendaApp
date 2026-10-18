// Temporada 2 · Ep. 2 — Reprodutivo › Inseminação em lote. Captura as telas REAIS do app (produção) contra o stub (EP=t2e2).
// Rodar:  EP=t2e2 node stub-api.mjs &   (frontend: next start)   node capturar_t2e2.mjs
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
// tall = captura alta (barra escondida) para o motor rolar a imagem; scroll = posição da página na captura normal (telas de sheet/progresso)
async function snap(nome, { tall = false, alvos = {}, scroll = 0, tallMax = 2500 } = {}) {
  await esp(); await scrollar(scroll); await esp(250);
  const barTop = await p.evaluate(() => { const b = document.querySelector(".lote-barra"); const n = document.querySelector("nav.mob-nav"); return (b ? b.getBoundingClientRect().top : n.getBoundingClientRect().top); });
  const navTop = await p.evaluate(() => document.querySelector("nav.mob-nav").getBoundingClientRect().top);
  await p.screenshot({ path: `${OUT}${nome}.png` });
  const m = { img: `${nome}.png`, w: 390, h: 844, hdr: 95.78, barTop: +barTop.toFixed(1), navTop: +navTop.toFixed(1), scroll, alvos: await caixas(alvos) };
  m.alvosN = m.alvos;
  if (tall) {
    await p.setViewportSize({ width: 390, height: tallMax }); await esp(500);
    await p.addStyleTag({ content: ".lote-barra{display:none!important}" });
    const fim = await p.evaluate((lim) => { let m = 0; document.querySelectorAll("main *, .lote-view *").forEach((e) => { const r = e.getBoundingClientRect(); if (r.height && r.bottom < lim - 50) m = Math.max(m, r.bottom); }); return m; }, tallMax);
    const H = Math.max(844, Math.ceil(fim + 24 + 69));
    await p.setViewportSize({ width: 390, height: H }); await esp(500);
    await p.screenshot({ path: `${OUT}${nome}_tall.png` });
    m.tall = { img: `${nome}_tall.png`, h: H, alvos: await caixas(alvos) };
    await p.evaluate(() => { for (const s of document.querySelectorAll("style")) if (s.textContent.includes(".lote-barra{display:none!important}")) s.remove(); });
    await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  }
  mapa[nome] = m; console.log(nome, tall ? `tall H=${m.tall.h}` : "", scroll ? `scroll=${scroll}` : "");
}
const cartao = (b) => `.lote-cartao:has(.brinco:text-is("${b}"))`;
const sit = (r) => `[aria-label="Situação"] button:has-text("${r}")`;
const opcao = (n) => `.lote-opcao:has(.nm:text-is("${n}"))`;
const Q = { estrela: "4521", mimosa: "3877", boneca: "4102", joia: "1502", aurora: "4669" };
const A1 = {
  passo: ".lote-passo", origem: "[aria-label=Origem]", lotesBtn: "[aria-label=Origem] button:has-text('Lotes')", situacao: '[aria-label="Situação"]',
  btnAptas: sit("Aptas"), btnTodas: sit("Todas"), selTodas: ".lote-cartao:has-text('Selecionar todas')", grupoCab: ".lote-grupo-cab", pilulaAlta: ".lote-pill:has-text('01 - Alta')", pills: ".lote-pills",
  barra: ".lote-barra", barraN: ".lote-barra .n", continuar: ".lote-barra .lote-cta", rascunho: "p:has-text('Rascunho salvo')",
  cMimosa: cartao(Q.mimosa), cBoneca: cartao(Q.boneca), cJoia: cartao(Q.joia), cAurora: cartao(Q.aurora), cEstrela: cartao(Q.estrela),
  cxMimosa: cartao(Q.mimosa) + " .lote-cx", cxBoneca: cartao(Q.boneca) + " .lote-cx", cxJoia: cartao(Q.joia) + " .lote-cx", cxAurora: cartao(Q.aurora) + " .lote-cx", cxEstrela: cartao(Q.estrela) + " .lote-cx",
  avisoEstrela: cartao(Q.estrela) + " .lote-sug", chipEstrela: cartao(Q.estrela) + " .lote-chip",
  sheet: ".lote-sheet", sheetTitulo: ".lote-sheet h3", sheetTexto: ".lote-sheet p", deixar: ".lote-sheet button:has-text('Deixar de fora')", marcarMesmo: ".lote-sheet button:has-text('Marcar mesmo assim')",
};
const A2 = {
  passo: ".lote-passo", resumo: ".lote-resumo", data: "input[type=date]", dataExt: "input[type=date] + p", categoria: "[aria-label=Categoria]", btnConv: "[aria-label=Categoria] button:has-text('Convencional')",
  touros: "[aria-label=Touro]", opOrion: opcao("ORION"), opOrionNum: opcao("ORION") + " .num", opAtlas: opcao("ATLAS"), opDefinir: opcao("Definir depois"),
  rotTPV: ".lote-rot:has-text('Touro por vaca')", colap: ".lote-colap", colapBtn: ".lote-colap button", colapTitulo: ".lote-colap .v", colapDica: ".lote-colap .h",
  vaca1: ".lote-colap .conteudo button >> nth=0", vaca1Linha: ".lote-colap .conteudo > div > div >> nth=0", nota: ".lote-nota:has-text('Cada vaca vira')", barra: ".lote-barra", cta: ".lote-barra .lote-cta", prog: ".mob-progresso", progRot: ".lote-barra div:has(> span:has-text('Enviando'))",
  sheet: ".lote-sheet", sheetTitulo: ".lote-sheet h3", usarPadrao: ".lote-sheet .lote-opcao:has-text('Usar o padrão')",
};
const AR = { res: ".lote-res", titulo: ".lote-res h2", texto: ".lote-res p", quadro: ".lote-quadro", lin1: ".lote-quadro .lin:nth-child(1)", lin1Q: ".lote-quadro .lin:nth-child(1) .q", nova: ".lote-acoes-fim .lote-cta:first-child",
  quadroFalha: ".lote-quadro:has-text('Vacas que não salvaram')", quadroDoses: ".lote-quadro:has-text('ORION')", tentar: ".lote-acoes-fim .lote-cta:has-text('Tentar de novo')", voltar: ".lote-acoes-fim .lote-cta:has-text('Voltar e conferir')" };

// ───────────── Rodada A: o fluxo feliz (4 aptas do 01 - Alta, ORION 12 → 8) ─────────────
({ p } = await sessao());
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await snap("s01_lancar", { alvos: { repro: "button.mob-bloco:has-text('Reprodutivo')", navLancar: "nav.mob-nav >> text=Lançar" } });
await p.locator("button.mob-bloco", { hasText: "Reprodutivo" }).first().click(); await esp(500);
await snap("s02_repro_grade", { alvos: { inseminacao: "button.mob-bloco:has-text('Inseminação')", diagnostico: "button.mob-bloco:has-text('Diagnóstico')", grade: ".mob-bloco >> nth=0" } });
await p.locator("button.mob-bloco", { hasText: "Inseminação" }).first().click(); await esp(1500);
await snap("s03_p1_animais", { alvos: A1 });
await p.locator("[aria-label=Origem] button", { hasText: "Lotes" }).click();
await snap("s04_origem_lotes", { alvos: A1 });
await p.locator(".lote-pill", { hasText: "01 - Alta" }).click();
await snap("s05_alta_aptas", { tall: true, alvos: A1 });
await p.locator(".lote-cartao", { hasText: "Selecionar todas" }).click();
await snap("s06_aptas_marcadas", { tall: true, alvos: A1 });
await p.locator(sit("Todas")).click();
await snap("s07_todas", { tall: true, alvos: A1 });
// rola até a Estrela (gestante) e abre o sheet de confirmação
const yEst = await p.evaluate(() => { const c = [...document.querySelectorAll(".lote-cartao")].find((e) => e.querySelector(".brinco")?.textContent === "4521"); const sc = document.scrollingElement.scrollTop + document.body.scrollTop; return Math.round(c.getBoundingClientRect().top + sc - 230); });
console.log("yEst", yEst);
await scrollar(yEst); await esp(400);
await p.locator(cartao(Q.estrela)).click(); await esp(500);
await snap("s08_sheet_estrela", { alvos: A1, scroll: yEst });
await p.locator(".lote-sheet button", { hasText: "Deixar de fora" }).click(); await esp(400);
await snap("s09_todas_estrela_fora", { alvos: A1, scroll: yEst });
await scrollar(0); await esp(300);
await p.getByRole("button", { name: "Continuar" }).click(); await esp(900);
await snap("s10_p2_topo", { tall: true, alvos: A2 });
await p.locator(".lote-opcao", { hasText: "ORION" }).first().click();
await snap("s11_p2_orion", { tall: true, alvos: A2 });
await p.locator(".lote-colap button").first().click();
await snap("s12_p2_touro_vaca", { tall: true, alvos: A2 });
await p.locator(".lote-colap .conteudo button").first().click(); await esp(400);
const yFim = await p.evaluate(() => Math.round(document.scrollingElement.scrollTop + document.body.scrollTop));
await snap("s13_sheet_troca", { alvos: A2, scroll: yFim });
await p.locator(".lote-sheet .lote-opcao", { hasText: "Usar o padrão" }).click(); await esp(400);
const maxScr = await p.evaluate(() => Math.max(document.scrollingElement.scrollHeight - innerHeight, document.body.scrollHeight - innerHeight));
console.log("maxScroll", maxScr);
await snap("s14_p2_pronto", { alvos: A2, scroll: maxScr });
// envio: cada POST demora para dar tempo de ver "1 de 4" e "3 de 4"
await cfg({ atraso: 2600, falhar: [] });
await p.locator(".lote-cta", { hasText: /Salvar inseminação/ }).click();
await p.waitForFunction(() => document.body.innerText.includes("1 de 4"), null, { timeout: 15000 });
await snap("s15_progresso1", { alvos: A2, scroll: maxScr });
await p.waitForFunction(() => document.body.innerText.includes("3 de 4"), null, { timeout: 20000 });
await snap("s16_progresso3", { alvos: A2, scroll: maxScr });
await p.waitForSelector(".lote-res", { timeout: 20000 }); await esp(600);
await snap("s17_resultado", { tall: true, alvos: AR });
const logA = await (await fetch(API + "/__log")).json(); console.log("POSTs A:", logA.filter((x) => x.p === "/reproducao/servico").map((x) => x.b.numero_matriz + ":" + x.b.reprodutor).join(" "));
await p.context().close();

// ───────────── Rodada B: uma vaca falha na 1ª tentativa (Boneca 4102) ─────────────
({ p } = await sessao());
await cfg({ atraso: 150, falhar: [Q.boneca] });
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await p.locator("button.mob-bloco", { hasText: "Reprodutivo" }).first().click(); await esp(500);
await p.locator("button.mob-bloco", { hasText: "Inseminação" }).first().click(); await esp(1300);
await p.locator("[aria-label=Origem] button", { hasText: "Lotes" }).click(); await esp(300);
await p.locator(".lote-pill", { hasText: "01 - Alta" }).click(); await esp(300);
await p.locator(".lote-cartao", { hasText: "Selecionar todas" }).click(); await esp(300);
await p.getByRole("button", { name: "Continuar" }).click(); await esp(900);
await p.locator(".lote-opcao", { hasText: "ORION" }).first().click(); await esp(300);
await p.locator(".lote-cta", { hasText: /Salvar inseminação/ }).click();
await p.waitForSelector(".lote-res", { timeout: 20000 }); await esp(700);
await snap("s18_resultado_falha", { tall: true, alvos: AR });
await cfg({ atraso: 0 });
await p.locator(".lote-cta", { hasText: "Tentar de novo" }).click(); await esp(1500);
await snap("s19_resultado_retry", { tall: true, alvos: AR });
await p.context().close();
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
