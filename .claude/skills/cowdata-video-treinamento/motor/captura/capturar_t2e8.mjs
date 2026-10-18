// Temporada 2 · Ep. 8 — Produção › BST (PainelLancarBst). Captura as telas REAIS do app (produção) contra o stub (EP=t2e8).
// Rodar:  EP=t2e8 node stub-api.mjs &   (frontend: next start)   EP=t2e8 node capturar_t2e8.mjs      (DSF=escala opcional)
// Novidade em relação aos Eps. 2–6: as duas telas são tabelas LARGAS dentro de uma moldura com rolagem horizontal (.gv-tabela-moldura). Para o motor poder
// "arrastar" a tabela de lado sem cortar coluna, cada estado que precisa disso ganha `hz`: recortes (um por posição de rolagem) do conteúdo da moldura.
// A barra de ação (.gv-barra, sticky) fica DENTRO da captura alta, no fim da página; barTop = topo da navegação.
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const OUT = "shots/"; fs.mkdirSync(OUT, { recursive: true }); const mapa = {};
const API = "http://localhost:8000";
const cfg = (o) => fetch(API + "/__cfg", { method: "POST", body: JSON.stringify(o) });
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const DSF = Number(process.env.DSF || 0) || undefined;

async function sessao() {
  await fetch(API + "/__reset");
  const ctx = await novoContexto(br, 844, DSF);
  // o cabeçalho do app tem o nome de uma fazenda real escrito direto no layout; no vídeo só vale o nome fictício
  await ctx.addInitScript(() => {
    const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
    new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
    try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho")) localStorage.removeItem(k); } catch {}
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
// quem rola é o BODY (o app é uma coluna única dentro dele)
const scrollar = (y) => p.evaluate((y) => { document.activeElement?.blur?.(); window.scrollTo(0, y); document.body.scrollTo(0, y); document.scrollingElement.scrollTo(0, y); }, y);
const altura = () => p.evaluate(() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight));
// tall = captura alta com a página inteira (viewport = altura do documento: a barra sticky fica na posição natural, no fim) — o motor rola a imagem por trás
// do cabeçalho; barTop = topo da navegação. hz = {sel} → recortes do conteúdo de uma moldura de tabela em várias posições de rolagem horizontal.
async function snap(nome, { tall = false, alvos = {}, scroll = 0, hz = null } = {}) {
  await esp(); await scrollar(scroll); await esp(250);
  // digitar num campo rola a moldura da tabela de lado (foco): volta a 0, a geometria (mapa) e a imagem alta valem para a tabela "de pé"; o resto vem dos recortes hz
  await p.evaluate(() => document.querySelectorAll(".gv-tabela-moldura").forEach((e) => { e.scrollLeft = 0; })); await esp(150);
  const navTop = await p.evaluate(() => document.querySelector("nav.mob-nav").getBoundingClientRect().top);
  await p.screenshot({ path: `${OUT}${nome}.png` });
  const m = { img: `${nome}.png`, w: 390, h: 844, hdr: 95.78, barTop: +navTop.toFixed(1), navTop: +navTop.toFixed(1), scroll, alvos: await caixas(alvos) };
  m.alvosN = m.alvos;
  if (tall) {
    const D = await altura();
    await p.setViewportSize({ width: 390, height: D }); await esp(600);
    const D2 = await altura(); if (D2 !== D) { await p.setViewportSize({ width: 390, height: D2 }); await esp(600); }
    await scrollar(0); await esp(200);
    await p.screenshot({ path: `${OUT}${nome}_tall.png` });
    m.tall = { img: `${nome}_tall.png`, h: D2, alvos: await caixas(alvos) };
    if (hz) {
      const fr = p.locator(hz).first(); const b = await fr.boundingBox();
      const f = await fr.evaluate((e) => ({ cl: e.clientLeft, ct: e.clientTop, cw: e.clientWidth, ch: e.clientHeight, sw: e.scrollWidth }));
      const S = f.sw - f.cw, K = Math.max(1, Math.ceil(S / f.cw)), shots = [];
      for (let i = 0; i <= (S > 0 ? K : 0); i++) {
        const sl = S > 0 ? Math.round((S * i) / K) : 0;
        await fr.evaluate((e, v) => { e.scrollLeft = v; }, sl); await esp(200);
        const real = await fr.evaluate((e) => e.scrollLeft);
        const img = `${nome}_hz${i}.png`;
        await p.screenshot({ path: OUT + img, clip: { x: b.x + f.cl, y: b.y + f.ct, width: f.cw, height: f.ch } });
        shots.push({ sl: real, img });
      }
      await fr.evaluate((e) => { e.scrollLeft = 0; });
      m.hz = { box: { x: +(b.x + f.cl).toFixed(2), y: +(b.y + f.ct).toFixed(2), w: f.cw, h: f.ch }, S, sw: f.sw, shots };
    }
    await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  }
  mapa[nome] = m; console.log(nome, tall ? `tall H=${m.tall.h}` : "", m.hz ? `hz S=${m.hz.S} shots=${m.hz.shots.length}` : "", scroll ? `scroll=${scroll}` : "", "barTop", m.barTop);
}

// ── ids ──
const AP = ["1502", "3877"];   // 1502 Jóia (1ª linha de Aptas) fica de fora da aplicação e depois é marcada inapta
const ALV = {
  faixa: ".bst-topo", pergunta: ".bst-pergunta", prox: ".bst-prox", proxRot: ".bst-prox-rot", proxData: ".bst-prox-data", proxTxt: ".bst-prox-txt", ajustar: ".bst-prox .bst-btn",
  segs: ".bst-segs", segA: ".bst-seg >> nth=0", segI: ".bst-seg >> nth=1", segN: ".bst-seg >> nth=2", segAv: ".bst-seg >> nth=0 >> .bst-seg-v", segIv: ".bst-seg >> nth=1 >> .bst-seg-v", segNv: ".bst-seg >> nth=2 >> .bst-seg-v",
  segAn: ".bst-seg >> nth=0 >> .bst-seg-n", segIn: ".bst-seg >> nth=1 >> .bst-seg-n", segNn: ".bst-seg >> nth=2 >> .bst-seg-n",
  passo1: "section:has(.bst-tool)", cont: ".gp-contagem", tool: ".bst-tool", marcarTodas: 'button.bst-btn:has-text("arcar todas"), button.bst-btn:has-text("esmarcar")', lote: ".bst-lotes summary", delTog: '[aria-labelledby="bst-lbl-del"]',
  frame: ".gv-tabela-moldura", thead: ".gv-tabela thead", thChk: ".gv-tabela thead th:nth-child(1)", thN: ".gv-tabela thead th:nth-child(2)", thLote: ".gv-tabela thead th:nth-child(3)",
  thDp: ".gv-tabela thead th:nth-child(4)", thDa: ".gv-tabela thead th:nth-child(5)", thSit: ".gv-tabela thead th:nth-child(6)",
  ...Object.fromEntries([1, 2, 3, 4, 5, 6, 7, 8].flatMap((i) => [[`r${i}`, `.gv-tabela tbody tr:nth-child(${i})`], [`r${i}c`, `.gv-tabela tbody tr:nth-child(${i}) input[type=checkbox]`],
    [`r${i}dp`, `.gv-tabela tbody tr:nth-child(${i}) td:nth-child(4)`], [`r${i}sit`, `.gv-tabela tbody tr:nth-child(${i}) td:nth-child(6)`], [`r${i}n`, `.gv-tabela tbody tr:nth-child(${i}) td:nth-child(2)`]])),
  ajuda: ".gv-ajuda >> nth=1",
  params: ".bst-params", pTit: ".bst-params-tit", pData: ".gv-campo:has(#bst-data)", pProduto: ".gv-campo:has(#bst-produto)", produto: "#bst-produto", pDose: ".gv-campo:has(#bst-dose)", dose: "#bst-dose",
  pUn: ".gv-campo:has(#bst-un)", pModo: ".gv-campo:has(#bst-lbl-dose)", pPor: '[aria-labelledby="bst-lbl-dose"] button:has-text("Por animal")', pResp: ".gv-campo:has(#bst-resp)",
  barra: ".gv-barra", resumo: ".bst-resumo", resumoLinha: ".bst-resumo-linha >> nth=0", aplicar: ".gv-barra-miolo .btn-primary-gold", inapta: ".gv-barra-miolo button.bst-perigo", dosEprod: ".gv-barra-miolo button:has-text(\"Dose e produto\")",
  conf: ".bst-conf", confP: ".bst-conf p", confOk: ".bst-conf button >> nth=1", confCancel: ".bst-conf button >> nth=0", ret: ".bst-ret", retTxt: ".bst-ret-txt", verIncluir: '.bst-ret button:has-text("Ver em Incluir")',
  voltar: 'button[aria-label="Voltar"] >> nth=1',
};
({ p } = await sessao());
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await snap("s01_lancar", { alvos: { prod: "button.mob-bloco:has-text('Produção (Leite)')", navLancar: "nav.mob-nav >> text=Lançar" } });
await p.locator("button.mob-bloco", { hasText: "Produção (Leite)" }).first().click(); await esp(600);
await snap("s02_prod_grade", { alvos: { bst: "button.mob-bloco:has-text('BST')", grade: ".mob-bloco >> nth=0" } });
await p.locator("button.mob-bloco", { hasText: "BST" }).first().click(); await esp(2200);
await snap("b03_bst", { tall: true, alvos: ALV, hz: ALV.frame });
await p.locator(ALV.marcarTodas).first().click(); await esp(700);
await snap("b04_todas", { tall: true, alvos: ALV, hz: ALV.frame });
await p.locator(ALV.r1c).click(); await esp(600);
await snap("b05_desmarca", { tall: true, alvos: ALV, hz: ALV.frame });
await p.fill(ALV.dose, "1"); await esp(600);
await snap("b06_dose", { tall: true, alvos: ALV, hz: ALV.frame });
await cfg({ atraso: 700 });
await p.locator(ALV.aplicar).click(); await esp(700);
await snap("b07_confirma", { tall: true, alvos: ALV });
await p.locator(ALV.confOk).click();
await p.waitForSelector(".bst-ret", { timeout: 15000 }); await esp(1800);
await snap("b08_aplicado", { tall: true, alvos: ALV, hz: ALV.frame });
await p.locator(ALV.r1c).click(); await esp(600);
await snap("b09_marca1", { tall: true, alvos: ALV, hz: ALV.frame });
await p.locator(ALV.inapta).click(); await esp(700);
await snap("b10_conf_inapta", { tall: true, alvos: ALV });
await p.locator(ALV.confOk).click();
await p.waitForFunction(() => document.querySelector(".bst-ret-txt")?.textContent.includes("inapta"), null, { timeout: 15000 }); await esp(1800);
await snap("b11_inapta", { tall: true, alvos: ALV, hz: ALV.frame });
const log = await (await fetch(API + "/__log")).json();
console.log("POSTs BST:", JSON.stringify(log.filter((x) => x.p.startsWith("/agenda/bst")).map((x) => x.b)));
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
