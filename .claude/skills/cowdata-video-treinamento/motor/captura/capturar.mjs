import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const OUT = "shots/"; const mapa = {};
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const ctx = await novoContexto(br);
// o cabeçalho do app tem o nome de uma fazenda real escrito direto no layout; no vídeo só vale o nome fictício
await ctx.addInitScript(() => {
  const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
  new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
});
const p = await pagina(ctx);
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
async function snap(nome, { tall = false, alvos = {} } = {}) {
  await esp();
  await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); });
  await esp(250);
  const barTop = await p.evaluate(() => { const b = document.querySelector(".lote-barra"); const n = document.querySelector("nav.mob-nav"); return (b ? b.getBoundingClientRect().top : n.getBoundingClientRect().top); });
  const navTop = await p.evaluate(() => document.querySelector("nav.mob-nav").getBoundingClientRect().top);
  await p.screenshot({ path: `${OUT}${nome}.png` });
  const m = { img: `${nome}.png`, w: 390, h: 844, hdr: 95.78, barTop: +barTop.toFixed(1), navTop: +navTop.toFixed(1), alvos: await caixas(alvos) };
  m.alvosN = m.alvos;
  if (tall) {
    const sc = await p.evaluate(() => document.scrollingElement.scrollTop + document.body.scrollTop);
    await p.setViewportSize({ width: 390, height: 2600 }); await esp(500);
    await p.addStyleTag({ content: ".lote-barra{display:none!important}" });
    const fim = await p.evaluate(() => { let m = 0; document.querySelectorAll("main *, .lote-view *").forEach((e) => { const r = e.getBoundingClientRect(); if (r.height && r.bottom < 2500) m = Math.max(m, r.bottom); }); return m; });
    const H = Math.max(844, Math.ceil(fim + 24 + 69));
    await p.setViewportSize({ width: 390, height: H }); await esp(500);
    await p.screenshot({ path: `${OUT}${nome}_tall.png` });
    m.tall = { img: `${nome}_tall.png`, h: H, alvos: await caixas(alvos) };
    await p.evaluate(() => { for (const s of document.querySelectorAll("style")) if (s.textContent.includes(".lote-barra{display:none!important}")) s.remove(); });
    await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  }
  mapa[nome] = m; console.log(nome, tall ? `tall H=${m.tall.h}` : "");
}
const cartao = (b) => `.lote-cartao:has(.brinco:text-is("${b}"))`;
await p.goto("http://localhost:3000/app", { waitUntil: "networkidle" }); await esp(1200);
await snap("s00_agenda", { alvos: { navLancar: "nav.mob-nav >> text=Lançar", navAgenda: "nav.mob-nav >> text=Agenda" } });
await p.getByRole("link", { name: /Lançar/ }).last().click(); await p.waitForURL(/lancar/); await esp(900);
await snap("s01_lancar", { tall: true, alvos: { movimentar: "button:has-text('Movimentar'):not(nav *)", navLancar: "nav.mob-nav >> text=Lançar" } });
await p.getByRole("button", { name: "Movimentar", exact: true }).click();
await snap("s02_mov_p1", { alvos: { origem: "[aria-label=Origem]", lotesBtn: "[aria-label=Origem] button:has-text('Lotes')" } });
await p.locator("[aria-label=Origem] button", { hasText: "Lotes" }).click();
await snap("s03_origem_lotes", { alvos: { pilulaAlta: ".lote-pill:has-text('01 - Alta')", pills: ".lote-pills" } });
await p.locator(".lote-pill", { hasText: "01 - Alta" }).click();
const A = { grupoCab: ".lote-grupo-cab", barra: ".lote-barra", barraN: ".lote-barra .n", continuar: ".lote-barra .lote-cta", c3990: cartao("3990"), c4033: cartao("4033"), c4078: cartao("4078"), cx3990: cartao("3990") + " .lote-cx", cx4033: cartao("4033") + " .lote-cx", cx4078: cartao("4078") + " .lote-cx", c1502: cartao("1502"), del3990: cartao("3990") + " .lote-l2" };
await snap("s04_alta_aberto", { tall: true, alvos: A });
await p.locator(cartao("3990")).click(); await snap("s05_marc1", { tall: true, alvos: A });
await p.locator(cartao("4033")).click(); await snap("s06_marc2", { tall: true, alvos: A });
await p.locator(cartao("4078")).click(); await snap("s07_marc3", { tall: true, alvos: A });
await p.getByRole("button", { name: "Continuar" }).click();
const B = { passo: ".lote-passo", resumo: ".lote-resumo", rotDestino: ".lote-rot:has-text('Lote de destino')", opcoes: ".lote-opcoes", opMedia: ".lote-opcao:has-text('02 - Média')", opMediaNum: ".lote-opcao:has-text('02 - Média') .num", opAlta: ".lote-opcao:has-text('01 - Alta')", dp: ".lote-dp", dpDepois: ".lote-dp .lin:last-child", dpBrincos: ".lote-dp .brincos", rotMotivo: ".lote-rot:has-text('Motivo')", colap: ".lote-colap", colapBtn: ".lote-colap button", pillMotivo: ".lote-pill:has-text('Final de DEL')", data: "input[type=date]", dataExt: "input[type=date] + p", cta: ".lote-barra .lote-cta" };
await snap("s08_p2_topo", { tall: true, alvos: B });
await p.locator(".lote-opcao", { hasText: "02 - Média" }).click();
await snap("s09_p2_destino", { tall: true, alvos: B });
await p.locator(".lote-colap button").first().click();
await snap("s10_p2_motivo_aberto", { tall: true, alvos: B });
await p.locator(".lote-pill", { hasText: "Final de DEL" }).click();
await snap("s11_p2_motivo_ok", { tall: true, alvos: B });
await p.locator(".lote-cta", { hasText: /^Movimentar \d/ }).click();
await snap("s12_resultado", { tall: true, alvos: { res: ".lote-res", titulo: ".lote-res h2", quadro: ".lote-quadro", lin1: ".lote-quadro .lin:nth-child(1)", lin2: ".lote-quadro .lin:nth-child(2)", nova: ".lote-acoes-fim .lote-cta:first-child", verLotes: "a:has-text('Ver lotes')" } });
await p.getByRole("link", { name: "Ver lotes" }).click();
await p.waitForTimeout(800);
await snap("s13_composicao", { tall: true, alvos: { abas: "button:has-text('Composição')", comp: "button:has-text('Composição')" } });
await p.getByRole("button", { name: /Composição/ }).click();
await snap("s14_composicao_lista", { tall: true, alvos: { n39: "text=39 animal(is)", n41: "text=41 animal(is)", r01: "text=01 - Alta", r02: "text=02 - Média" } });
fs.writeFileSync("mapa.json", JSON.stringify(mapa, null, 1));
await br.close();
