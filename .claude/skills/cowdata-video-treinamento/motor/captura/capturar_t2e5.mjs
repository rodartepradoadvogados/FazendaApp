// Temporada 2 · Ep. 5 — Reprodutivo › Protocolo de IATF (em lote). Captura as telas REAIS do app (produção) contra o stub (EP=t2e5).
// Rodar:  EP=t2e5 node stub-api.mjs &   (frontend: next start)   node capturar_t2e5.mjs
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
import { animais, EP5_INFO, estadosEp2 } from "./dados.mjs";
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
const PROT = EP5_INFO.protocolo, protNome = animais.find((a) => a.numero === PROT).nome;
const A1 = {
  passo: ".lote-passo", passoTxt: ".lote-passo p", origem: "[aria-label=Origem]", situacao: '[aria-label="Situação"]', notaSit: '[aria-label="Situação"] + p',
  btnAptas: sit("Aptas"), btnAtrasadas: sit("Atrasadas"), btnPev: sit("PEV"), btnTodas: sit("Todas"), busca: ".lote-busca", buscaIn: ".lote-busca input",
  selTodas: ".lote-cartao:has-text('Selecionar todas')", grupoCab: ".lote-grupo-cab", barra: ".lote-barra", barraN: ".lote-barra .n", barraFora: ".lote-barra .n small", continuar: ".lote-barra .lote-cta",
  rascunho: "p:has-text('Rascunho salvo')", cProt: cartao(PROT), chipProt: cartao(PROT) + " .lote-chip", avisoProt: cartao(PROT) + " .lote-sug", cxProt: cartao(PROT) + " .lote-cx",
};
const A2 = {
  passo: ".lote-passo", resumo: ".lote-resumo", data: "input[type=date]", dataExt: "input[type=date] + p", tl: ".lote-tl", li0: ".lote-tl li:nth-child(1)", li1: ".lote-tl li:nth-child(2)", li2: ".lote-tl li:nth-child(3)", li3: ".lote-tl li:nth-child(4)",
  d0: ".lote-tl li:nth-child(1) .dt", d7: ".lote-tl li:nth-child(2) .dt", d9: ".lote-tl li:nth-child(3) .dt", d11: ".lote-tl li:nth-child(4) .dt",
  hm0: ".lote-tl li:nth-child(1) .hm", hm1: ".lote-tl li:nth-child(2) .hm", hm2: ".lote-tl li:nth-child(3) .hm", hm3: ".lote-tl li:nth-child(4) .hm",
  nota: ".lote-nota:has-text('Isso só agenda')", rotProt: ".lote-rot:has-text('Protocolo padrão')", barra: ".lote-barra", cta: ".lote-barra .lote-cta",
};
const AR = { res: ".lote-res", titulo: ".lote-res h2", texto: ".lote-res p", quadro: ".lote-quadro", lin0: ".lote-quadro .lin:nth-child(1)", lin1: ".lote-quadro .lin:nth-child(2)", acoes: ".lote-acoes-fim", agenda: ".lote-acoes-fim a" };

({ p } = await sessao());
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await snap("s01_lancar", { alvos: { repro: "button.mob-bloco:has-text('Reprodutivo')", protocolos: "button.mob-bloco:has-text('Protocolos')", navLancar: "nav.mob-nav >> text=Lançar" } });
await p.locator("button.mob-bloco", { hasText: "Reprodutivo" }).first().click(); await esp(500);
await snap("s02_repro_grade", { alvos: { iatf: "button.mob-bloco:has-text('Protocolo IATF')", inseminacao: "button.mob-bloco:has-text('Inseminação')", grade: ".mob-bloco >> nth=0" } });
await p.locator("button.mob-bloco", { hasText: "Protocolo IATF" }).first().click(); await esp(1500);
await snap("s03_p1_aptas", { tall: true, alvos: A1 });
await p.locator(sit("Atrasadas")).click(); await esp(400);
const atras = await p.evaluate(() => [...document.querySelectorAll(".lote-cartao .brinco")].map((e) => e.textContent));
console.log("atrasadas:", atras.join(" "));
const Y1 = Number(process.env.Y1 || 0);
await snap("s04_atrasadas", { tall: true, alvos: { ...A1, ...Object.fromEntries(atras.map((b, i) => ["c" + i, cartao(b)])), ...Object.fromEntries(atras.map((b, i) => ["cx" + i, cartao(b) + " .lote-cx"])) }, scroll: Y1 });
await p.locator(".lote-cartao", { hasText: "Selecionar todas" }).click(); await esp(400);
await snap("s05_atrasadas_marcadas", { tall: true, alvos: { ...A1, ...Object.fromEntries(atras.map((b, i) => ["c" + i, cartao(b)])), ...Object.fromEntries(atras.map((b, i) => ["cx" + i, cartao(b) + " .lote-cx"])) }, scroll: Y1 ? Y1 + 21 : 0 });
await p.locator(sit("Todas")).click(); await esp(500);
await snap("s06_todas", { tall: true, alvos: A1, scroll: Y1 ? Y1 + 21 : 0 });
await scrollar(0); await esp(300);
await p.locator(".lote-busca input").fill(protNome); await esp(600);
await snap("s07_busca_protocolo", { tall: true, alvos: A1 });
await p.locator(".lote-busca input").fill(""); await esp(500);
await scrollar(0); await esp(300);
await p.getByRole("button", { name: "Continuar" }).click(); await esp(900);
await snap("s08_p2_topo", { tall: true, alvos: A2 });
const maxScr = await p.evaluate(() => Math.max(document.scrollingElement.scrollHeight - innerHeight, document.body.scrollHeight - innerHeight));
console.log("maxScroll p2", maxScr);
await snap("s09_p2_fim", { alvos: A2, scroll: maxScr });
await cfg({ atraso: 700 });
await p.locator(".lote-cta", { hasText: /Lançar D0/ }).click();
await p.waitForSelector(".lote-res", { timeout: 20000 }); await esp(700);
await snap("s10_resultado", { tall: true, alvos: AR });
const log = await (await fetch(API + "/__log")).json(); console.log("POSTs:", JSON.stringify(log.filter((x) => x.p === "/reproducao/protocolo-iatf").map((x) => x.b)));
await p.context().close();

// ───────────── Relance: Lançar › Protocolos (a mesma tela abre pelo bloco Protocolos) ─────────────
({ p } = await sessao());
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await p.locator("button.mob-bloco", { hasText: "Protocolos" }).first().click(); await esp(600);
await snap("s11_protocolos_grade", { alvos: { iatf: "button.mob-bloco:has-text('IATF')", inducao: "button.mob-bloco:has-text('Indução')" } });
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
