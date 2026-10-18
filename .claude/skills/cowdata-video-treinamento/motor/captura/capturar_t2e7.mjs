// Temporada 2 · Ep. 7 — Produção › Pesagem corporal (por lote) e Secagem. Captura as telas REAIS do app (produção) contra o stub (EP=t2e7).
// Rodar:  EP=t2e7 node stub-api.mjs &   (frontend: next start)   EP=t2e7 node capturar_t2e7.mjs      (DSF=escala opcional)
// Novidade em relação aos Eps. 2–6: as duas telas são tabelas LARGAS dentro de uma moldura com rolagem horizontal (.gv-tabela-moldura). Para o motor poder
// "arrastar" a tabela de lado sem cortar coluna, cada estado que precisa disso ganha `hz`: recortes (um por posição de rolagem) do conteúdo da moldura.
// A barra de ação (.gv-barra, sticky) fica DENTRO da captura alta, no fim da página; barTop = topo da navegação.
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
import { animais } from "./dados.mjs";
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
const NOV = animais.filter((a) => a.grupo_primario === "06 - Novilhas").map((a) => a.numero).sort((a, b) => a.localeCompare(b, "pt-BR", { numeric: true })).slice(0, 4);
const PESOS = ["330", "315", "336", "322"];          // 312→330 · 298→315 · 340→336 (perdeu) · 305→322
const linha = (n) => `tbody tr:has(td.gv-forte:text-is("${n}"))`;
const grupo = (r) => `div[role=group][aria-label="${r}"]`;
const ALV_P = {
  faixa: ".gv-faixa", fAn: ".gv-faixa-item:nth-child(1)", fGmd: ".gv-faixa-item:nth-child(3)", fSem: ".gv-faixa-item:nth-child(4)",
  parte: grupo("Parte da tela"), pLancar: grupo("Parte da tela") + ' button:has-text("Lançar pesagens")', pHist: grupo("Parte da tela") + ' button:has-text("Histórico")',
  passo1: "section[aria-labelledby=pc-p1]", modal: grupo("Modalidade"), mAnimal: grupo("Modalidade") + ' button:has-text("Por animal")',
  mLote: grupo("Modalidade") + ' button:has-text("Por lote")', mPlan: grupo("Modalidade") + ' button:has-text("Planilha")', data: "#pc-data",
  passo2: "section[aria-labelledby=pc-p2]", lotes: grupo("Lotes"), lote06: grupo("Lotes") + ' button:has-text("06 - Novilhas")',
  frame: ".gv-tabela-moldura", thead: ".gv-tabela thead", th1: ".gv-tabela thead th:nth-child(1)", thPesoNovo: ".gv-tabela thead th:nth-child(6)",
  thGanho: ".gv-tabela thead th:nth-child(7)", thGmd: ".gv-tabela thead th:nth-child(8)", thSit: ".gv-tabela thead th:nth-child(9)",
  ...Object.fromEntries(NOV.flatMap((n, i) => [[`r${i}`, linha(n)], [`r${i}n`, linha(n) + " td:nth-child(1)"], [`r${i}in`, linha(n) + " input"], [`r${i}ant`, linha(n) + " td:nth-child(3)"],
    [`r${i}g`, linha(n) + " td:nth-child(7)"], [`r${i}gmd`, linha(n) + " td:nth-child(8)"], [`r${i}sit`, linha(n) + " td:nth-child(9)"], [`r${i}selo`, linha(n) + " .gv-selo"]])),
  barra: ".gv-barra", resumo: ".gv-barra-resumo", salvar: ".btn-primary-gold", retorno: ".gv-barra-retorno", voltar: 'button[aria-label="Voltar"] >> nth=1',
};
const SEC = ["2305", "3338"];                          // as duas vacas marcadas (Melodia, 02 - Média; Hilda, 03 - Baixa); 3013 Iolanda fica sem marcar
const lin2 = (n) => `tbody tr:has(td.gv-forte:text-is("${n}"))`;
const ALV_S = {
  faixa: ".gv-faixa", fProx: ".gv-faixa-item:nth-child(2)", passo1: "section[aria-labelledby=sc-p1]", escolher: grupo("Escolher por"),
  eAnimal: grupo("Escolher por") + ' button:has-text("Animal(is)")', eLote: grupo("Escolher por") + ' button:has-text("Lote(s)")', mostrar: grupo("Mostrar"),
  ate30: grupo("Mostrar") + ' button:has-text("Até 30 dias")', atras: grupo("Mostrar") + ' button:has-text("Atrasadas")', todas: grupo("Mostrar") + ' button:has-text("Todas")',
  frame: ".gv-tabela-moldura >> nth=0", thead: ".gv-tabela >> nth=0 >> thead", thChk: ".gv-tabela >> nth=0 >> thead th:nth-child(1)", thDel: ".gv-tabela >> nth=0 >> thead th:nth-child(3)",
  thGest: ".gv-tabela >> nth=0 >> thead th:nth-child(4)", thPrev: ".gv-tabela >> nth=0 >> thead th:nth-child(5)", thSit: ".gv-tabela >> nth=0 >> thead th:nth-child(6)",
  ...Object.fromEntries(["2305", "3338", "3013"].flatMap((n) => [[`r${n}`, lin2(n)], [`r${n}c`, lin2(n) + " input[type=checkbox]"], [`r${n}del`, lin2(n) + " td:nth-child(3)"],
    [`r${n}gest`, lin2(n) + " td:nth-child(4)"], [`r${n}prev`, lin2(n) + " td:nth-child(5)"], [`r${n}sit`, lin2(n) + " td:nth-child(6)"]])),
  passo2: "section[aria-labelledby=sc-p2]", campoData: ".gv-campo:has(#sc-data)", data: "#sc-data", campoMotivo: ".gv-campo:has(#sc-motivo)", motivo: "#sc-motivo", rotMotivo: "label[for=sc-motivo]",
  campoEcc: ".gv-campo:has(#sc-ecc)", ecc: "#sc-ecc",
  passo3: "section[aria-labelledby=sc-p3]", acrescentar: 'button:has-text("Acrescentar produto")', frameP: ".gv-tabela-moldura >> nth=1",
  thProd: ".gv-tabela >> nth=1 >> thead th:nth-child(1)", thDose: ".gv-tabela >> nth=1 >> thead th:nth-child(3)", thEst: ".gv-tabela >> nth=1 >> thead th:nth-child(7)", thTot: ".gv-tabela >> nth=1 >> thead th:nth-child(6)",
  p1: ".gv-tabela >> nth=1 >> tbody tr:nth-child(1)", p1prod: 'select[aria-label="Produto 1"]', p1dose: 'input[aria-label="Dosagem do produto 1"]', p1tot: ".gv-tabela >> nth=1 >> tbody tr:nth-child(1) td:nth-child(6)", p1est: ".gv-tabela >> nth=1 >> tbody tr:nth-child(1) td:nth-child(7)",
  p2: ".gv-tabela >> nth=1 >> tbody tr:nth-child(2)", p2prod: 'select[aria-label="Produto 2"]', p2tot: ".gv-tabela >> nth=1 >> tbody tr:nth-child(2) td:nth-child(6)", p2est: ".gv-tabela >> nth=1 >> tbody tr:nth-child(2) td:nth-child(7)",
  passo4: "section[aria-labelledby=sc-p4]", barra: ".gv-barra", resumo: ".gv-barra-resumo", salvar: ".btn-primary-gold", retorno: ".gv-barra-retorno",
  sugerido: ".gv-barra-retorno div:has(> .gv-selo)", sim: 'button:has-text("Sim, mover")', agoraNao: 'button:has-text("Agora não")', voltar: 'button[aria-label="Voltar"] >> nth=1',
};

({ p } = await sessao());
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await snap("s01_lancar", { alvos: { prod: "button.mob-bloco:has-text('Produção (Leite)')", navLancar: "nav.mob-nav >> text=Lançar" } });
await p.locator("button.mob-bloco", { hasText: "Produção (Leite)" }).first().click(); await esp(600);
await snap("s02_prod_grade", { alvos: { pesagem: "button.mob-bloco:has-text('Pesagem corporal')", secagem: "button.mob-bloco:has-text('Secagem')", grade: ".mob-bloco >> nth=0" } });

// ───────────── Parte A · Pesagem corporal ─────────────
await p.locator("button.mob-bloco", { hasText: "Pesagem corporal" }).first().click(); await esp(1700);
await snap("p03_pesagem", { tall: true, alvos: ALV_P });
await p.locator(ALV_P.lote06).click(); await esp(900);
await snap("p04_lote", { tall: true, alvos: ALV_P, hz: ALV_P.frame });
for (let i = 0; i < 4; i++) {
  await p.fill(ALV_P["r" + i + "in"], PESOS[i]); await esp(500);
  await snap("p0" + (5 + i) + "_peso" + (i + 1), { tall: true, alvos: ALV_P, hz: ALV_P.frame });
}
await cfg({ atraso: 600 });
await p.evaluate(() => document.body.scrollTo(0, 1e6)); await esp(300);
await p.locator(ALV_P.salvar).click();
await p.waitForSelector(".gv-barra-retorno", { timeout: 15000 }); await esp(900);
await snap("p09_salvo", { tall: true, alvos: ALV_P });
let log = await (await fetch(API + "/__log")).json(); console.log("POSTs pesagem:", JSON.stringify(log.filter((x) => x.p === "/producao/pesagens").map((x) => x.b)));

// ───────────── Parte B · Secagem ─────────────
await scrollar(0); await esp(300);
await p.locator(ALV_P.voltar).click(); await esp(800);
await snap("q01_grade", { alvos: { secagem: "button.mob-bloco:has-text('Secagem')", pesagem: "button.mob-bloco:has-text('Pesagem corporal')", grade: ".mob-bloco >> nth=0" } });
await p.locator("button.mob-bloco", { hasText: "Secagem" }).first().click(); await esp(1800);
await snap("q02_secagem", { tall: true, alvos: ALV_S, hz: ALV_S.frame });
await p.locator(`input[aria-label="Marcar a vaca ${SEC[0]}"]`).click(); await esp(600);
await snap("q03_marca1", { tall: true, alvos: ALV_S });
await p.locator(`input[aria-label="Marcar a vaca ${SEC[1]}"]`).click(); await esp(600);
await snap("q04_marca2", { tall: true, alvos: ALV_S });
await p.fill("#sc-data", "2026-10-17"); await esp(500);
await snap("q05_data", { tall: true, alvos: ALV_S });
await p.selectOption("#sc-motivo", "rotina"); await esp(500);
await snap("q06_motivo", { tall: true, alvos: ALV_S });
await p.fill("#sc-ecc", "3.25"); await esp(500);
await snap("q07_ecc", { tall: true, alvos: ALV_S });
await p.locator(ALV_S.acrescentar).click(); await esp(700);
await snap("q08_prod_novo", { tall: true, alvos: ALV_S });
await p.selectOption(ALV_S.p1prod, "Antibiótico secagem (bisnaga)"); await esp(300);
await p.selectOption('select[aria-label="Via do produto 1"]', "Intramamária"); await p.fill(ALV_S.p1dose, "1"); await p.selectOption('select[aria-label="Unidade do produto 1"]', "unidade"); await esp(600);
await snap("q09_prod1", { tall: true, alvos: ALV_S });
await p.locator(ALV_S.acrescentar).click(); await esp(700);
await snap("q10_prod2_novo", { tall: true, alvos: ALV_S });
await p.selectOption(ALV_S.p2prod, "Selante de teto"); await esp(300);
await p.selectOption('select[aria-label="Via do produto 2"]', "Intramamária"); await p.fill('input[aria-label="Dosagem do produto 2"]', "1"); await p.selectOption('select[aria-label="Unidade do produto 2"]', "unidade"); await esp(600);
await snap("q11_prod2", { tall: true, alvos: ALV_S, hz: ALV_S.frameP });
await cfg({ atraso: 600 });
await p.evaluate(() => document.body.scrollTo(0, 1e6)); await esp(300);
await p.locator(ALV_S.salvar).click();
await p.waitForSelector("text=Lote sugerido", { timeout: 20000 }); await esp(900);
await snap("q12_salvo", { tall: true, alvos: ALV_S });
await p.locator(ALV_S.sim).click(); await p.waitForSelector("text=movida para o lote", { timeout: 15000 }); await esp(900);
await snap("q13_mov1", { tall: true, alvos: ALV_S });
await p.locator(ALV_S.sim).click(); await p.waitForFunction(() => document.body.innerText.split("movida para o lote").length > 2, null, { timeout: 15000 }); await esp(900);
await snap("q14_mov2", { tall: true, alvos: ALV_S });
log = await (await fetch(API + "/__log")).json();
console.log("POSTs secagem:", JSON.stringify(log.filter((x) => x.p === "/producao/secagem" || x.p === "/movimentacoes/mover").map((x) => x.b)));
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
