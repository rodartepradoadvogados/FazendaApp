// Temporada 2 · Ep. 12 — Protocolos › Personalizado (Lançar › Protocolos = FormProtocolos; Personalizado = ProtocoloCustomizadoApp). Captura as telas REAIS do app (produção) contra o stub (EP=t2e12).
// Rodar:  EP=t2e12 node stub-api.mjs &   (frontend: next start)   EP=t2e12 node capturar_t2e12.mjs      (DSF=escala opcional)
// Selects nativos não abrem no Chromium headless: a "lista aberta" é o mesmo <select> com size=5. A busca de matriz (SeletorAnimal) abre a lista de vacas assim que o campo existe.
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
    if (s && typeof s === "object") { o[k] = s; continue; } // caixa já calculada
    const l = p.locator(s).first();
    if (!(await l.count())) { o[k] = null; continue; }
    const b = await l.boundingBox(); o[k] = b && { x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1), h: +b.height.toFixed(1) };
  }
  return o;
}
const scrollar = (y) => p.evaluate((y) => { document.activeElement?.blur?.(); window.scrollTo(0, y); document.body.scrollTo(0, y); document.scrollingElement.scrollTo(0, y); }, y);
// tall = captura alta (viewport grande) para o motor rolar a imagem; scroll = posição da página na captura normal.
async function snap(nome, { tall = false, alvos = {}, scroll = 0, tallMax = 3000, extra = null } = {}) {
  await esp(); await scrollar(scroll); await esp(250);
  const navTop = await p.evaluate(() => document.querySelector("nav.mob-nav").getBoundingClientRect().top);
  await p.screenshot({ path: `${OUT}${nome}.png` });
  const ex = extra ? await extra() : {};
  const m = { img: `${nome}.png`, w: 390, h: 844, hdr: 95.78, barTop: +navTop.toFixed(1), navTop: +navTop.toFixed(1), scroll, alvos: await caixas({ ...alvos, ...ex }) };
  m.alvosN = m.alvos;
  if (tall) {
    // a lista de animais do seletor tem max-height 50vh: na captura alta ela cresceria; fixa em 50% de 844 px (o que o celular mostra)
    await p.addStyleTag({ content: '[style*="max-height: 50vh"]{max-height:422px !important}' });
    await p.setViewportSize({ width: 390, height: tallMax }); await esp(500);
    const fim = await p.evaluate((lim) => { let m = 0; document.querySelectorAll("main button.mob-btn, main p").forEach((e) => { const r = e.getBoundingClientRect(); if (r.height && r.bottom < lim - 50) m = Math.max(m, r.bottom); }); return m; }, tallMax); // fim do conteúdo = o botão ou o aviso abaixo dele
    const H = Math.max(844, Math.ceil(fim + 24 + 69));
    await p.setViewportSize({ width: 390, height: H }); await esp(500);
    await scrollar(0); await esp(200);
    await p.screenshot({ path: `${OUT}${nome}_tall.png` });
    m.tall = { img: `${nome}_tall.png`, h: H, alvos: await caixas({ ...alvos, ...(extra ? await extra() : {}) }) };
    await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  }
  mapa[nome] = m; console.log(nome, tall ? `tall H=${m.tall.h}` : "", scroll ? `scroll=${scroll}` : "", "barTop", m.barTop);
}
const campo = (rot) => `div:has(> label:text-is("${rot}"))`;
const ALV = {
  voltar1: 'button[aria-label="Voltar"] >> nth=0', titulo: "h1",
  protocolosBloco: "button.mob-bloco:text-is('Protocolos')", iatf: "button.mob-bloco:text-is('IATF')", inducao: "button.mob-bloco:text-is('Indução de lactação')",
  sanitario: "button.mob-bloco:text-is('Sanitário')", personalizado: "button.mob-bloco:text-is('Personalizado')",
  protoCampo: campo("Protocolo"), protoSel: campo("Protocolo") + " select",
  aplicar: campo("Aplicar em"), pillA: 'button:text-is("Animal")', pillF: 'button:text-is("Tarefa da fazenda")', pills: 'button:text-is("Animal") >> xpath=..',
  matriz: campo("Matriz (nº / nome)"), busca: 'input[placeholder="Buscar matriz…"]', matrizSel: campo("Matriz (nº / nome)") + " > button", res3654: 'button.mob-btn-2:has-text("3654")',
  data: campo("Data do D0 (1º dia do cronograma)"), dataRot: campo("Data do D0 (1º dia do cronograma)") + " > label", dataIn: campo("Data do D0 (1º dia do cronograma)") + " input",
  resp: campo("Responsável (opcional)"), respSel: campo("Responsável (opcional)") + " select",
  nota: 'p:has-text("Cronograma de")', lancar: 'button.mob-btn:text-is("Lançar protocolo")', aviso: 'p:has-text("Protocolo lançado")', rasc: 'p:has-text("Rascunho salvo")',
};
// caixa do trecho "(N dias)" dentro do <select> fechado (o texto de um select não tem caixa própria: mede com canvas na fonte do próprio select)
const caixaTrecho = (sel, trecho) => async () => ({ trecho: await p.evaluate(({ sel, trecho }) => {
  const s = document.querySelector(sel), cs = getComputedStyle(s), r = s.getBoundingClientRect(), txt = s.options[s.selectedIndex].text, i = txt.lastIndexOf(trecho);
  if (i < 0) return null; const c = document.createElement("canvas").getContext("2d"); c.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  const x0 = r.x + parseFloat(cs.paddingLeft) + parseFloat(cs.borderLeftWidth) + c.measureText(txt.slice(0, i)).width, w = c.measureText(trecho).width, h = parseFloat(cs.fontSize) * 1.3;
  return { x: +x0.toFixed(1), y: +(r.y + r.height / 2 - h / 2).toFixed(1), w: +w.toFixed(1), h: +h.toFixed(1) }; }, { sel: "main select.mob-input", trecho }) });
// caixa de um trecho de texto dentro de um elemento (Range sobre o nó de texto)
const caixaRange = (sel, trecho, chave) => async () => ({ [chave]: await p.evaluate(({ sel, trecho }) => { const e = [...document.querySelectorAll(sel)].find((x) => x.textContent.includes(trecho)); if (!e) return null;
  const n = e.firstChild, i = n.textContent.indexOf(trecho), r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + trecho.length); const b = r.getBoundingClientRect();
  return { x: +b.x.toFixed(1), y: +b.y.toFixed(1), w: +b.width.toFixed(1), h: +b.height.toFixed(1) }; }, { sel, trecho }) });
({ p } = await sessao());
await p.goto("http://localhost:3000/app/lancar", { waitUntil: "networkidle" }); await esp(1400);
await snap("p01_lancar", { alvos: { protocolosBloco: ALV.protocolosBloco } });
await p.locator(ALV.protocolosBloco).first().click(); await esp(800);
await snap("p02_grade", { alvos: { iatf: ALV.iatf, inducao: ALV.inducao, sanitario: ALV.sanitario, personalizado: ALV.personalizado, v1: ALV.voltar1 } });
await p.locator(ALV.personalizado).first().click(); await esp(1200);
await snap("p03_form", { tall: true, alvos: ALV });
// lista aberta: o mesmo <select> como caixa de lista
await p.evaluate(() => { const s = document.querySelector("main select.mob-input"); s.size = 5; }); await esp(500);
// caixas de cada opção da lista aberta e do trecho "(N dias)" de cada uma (a caixa do <option> vem do próprio Chromium; o trecho é medido com canvas na fonte da opção)
const opcoes = async () => p.evaluate(() => { const s = document.querySelector("main select.mob-input"), o = {}; const c = document.createElement("canvas").getContext("2d");
  [...s.options].forEach((op, i) => { const r = op.getBoundingClientRect(), cs = getComputedStyle(op); c.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
    o["op" + i] = { x: +r.x.toFixed(1), y: +r.y.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1) };
    const k = op.text.lastIndexOf("("); if (k > 0) { const x0 = r.x + parseFloat(cs.paddingLeft) + c.measureText(op.text.slice(0, k)).width; o["dias" + i] = { x: +x0.toFixed(1), y: +r.y.toFixed(1), w: +c.measureText(op.text.slice(k)).width.toFixed(1), h: +r.height.toFixed(1) }; } });
  return o; });
await snap("p04_lista", { tall: true, alvos: ALV, extra: async () => { const o = await opcoes(); console.log(JSON.stringify(o)); return o; } });
await p.evaluate(() => { for (const s of document.querySelectorAll("select")) s.removeAttribute("size"); });
await p.selectOption(ALV.protoSel, { label: "Cuidados pós-parto (10 dias)" }); await esp(900);
await snap("p05_proto", { tall: true, alvos: ALV, extra: caixaTrecho("select", "(10 dias)") });
await p.fill(ALV.busca, "3654"); await esp(700);
await snap("p06_busca", { tall: true, alvos: ALV });
await p.locator(ALV.res3654).first().click(); await esp(800);
await snap("p07_matriz", { tall: true, alvos: ALV });
await p.locator(ALV.pillF).first().click(); await esp(800);
await snap("p08_tarefa", { tall: true, alvos: ALV });
await p.locator(ALV.pillA).first().click(); await esp(800);
await snap("p09_volta", { tall: true, alvos: ALV, extra: caixaRange("label", "1º dia", "primeiro") });
await p.selectOption(ALV.respSel, { label: "Cláudio" }); await esp(800);
await snap("p10_resp", { tall: true, alvos: ALV, extra: caixaRange("label", "1º dia", "primeiro") });
await cfg({ atraso: 700 });
await p.locator(ALV.lancar).scrollIntoViewIfNeeded(); await p.locator(ALV.lancar).click();
await p.waitForSelector(ALV.aviso, { timeout: 10000 }); await esp(900);
await snap("p11_ok", { tall: true, alvos: ALV });
const log = await (await fetch(API + "/__log")).json();
console.log("POSTs:", JSON.stringify(log.map((x) => [x.p, x.b])));
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
