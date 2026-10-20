// T3 · Ep. 1 (Agenda Reprodutiva) — telas REAIS do app em produção contra o stub (EP=t3e1), passo a passo, DPR 3 por padrão.
// Saída em shots_ep/: páginas ALTAS (cabeçalho e barra de baixo escondidos; o motor rola a imagem por trás das barras), folhas
// ("gavetas") do diálogo inteiro em viewport alto, telas de viewport (menu, ficha, seletor de lote) e mapa.json com as caixas
// reais do DOM (px CSS; páginas altas em coordenadas do documento; folhas relativas ao topo do diálogo).
//   EP=t3e1 node stub-api.mjs &   (e o app em produção: next start -p 3000)   →   node capturar_t3e1_ep.mjs      DSF=1 para teste rápido
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const DSF = Number(process.env.DSF || 3), OUT = "shots_ep/"; fs.mkdirSync(OUT, { recursive: true });
const API = "http://localhost:8000", APP = "http://localhost:3000";
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const ctx = await novoContexto(br, 844, DSF);
await ctx.addInitScript(() => {
  const trocar = () => { for (const p of document.querySelectorAll("header p")) if (p.textContent.includes("Estreito Ponte de Pedra")) p.textContent = "Fazenda Boa Esperança"; };
  new MutationObserver(trocar).observe(document, { childList: true, subtree: true, characterData: true }); document.addEventListener("DOMContentLoaded", trocar);
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache")) localStorage.removeItem(k); } catch {}
});
const p = await pagina(ctx); const esp = (ms = 700) => p.waitForTimeout(ms);
const mapa = { dsf: DSF }; const log = (...a) => console.log(...a);
const topo = async () => { await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); }); await esp(350); };

// ── coleta das caixas reais (px CSS, coordenadas do documento = viewport quando a página está sem rolagem) ──
const coletar = () => p.evaluate(() => {
  const sy = window.scrollY, R = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return { x: +r.x.toFixed(2), y: +(r.y + sy).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) }; };
  const txt = (e) => (e?.innerText || "").replace(/\s+/g, " ").trim();
  const o = { docH: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  o.hdrBottom = hdr ? hdr.getBoundingClientRect().bottom : 0; o.navTop = nav ? nav.getBoundingClientRect().top : 844;
  o.voltar = R(document.querySelector('button[aria-label="Voltar"]'));
  const tit = [...document.querySelectorAll("span")].find((s) => s.textContent.trim() === "Cards configuráveis"); o.titulo = R(tit);
  o.novo = R([...document.querySelectorAll("button")].find((b) => b.textContent.includes("Novo card")));
  o.btns = [...document.querySelectorAll(".ft-botao-mob")].map((b) => ({ txt: txt(b), ...R(b) }));
  o.limpar = R([...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Limpar filtro"));
  o.dets = [...document.querySelectorAll("details")].map((d) => {
    const s = d.querySelector("summary");
    const r = { txt: txt(s), open: d.open, ...R(d), sum: R(s), gear: R(d.querySelector('button[title="Editar card"]')), trash: R(d.querySelector('button[title="Remover card"]')), badge: R(s.querySelector("span span")) };
    r.rows = [...d.querySelectorAll("button")].filter((b) => /^Nº|Nº \d/.test(txt(b)) || /Nº \d+/.test(txt(b))).filter((b) => !b.title && b.querySelector("svg")).map((b) => {
      const spans = [...b.querySelectorAll("span")]; const pick = (re) => spans.find((s) => re.test(s.firstChild?.textContent || "") && s.children.length >= 0 && /^(Toque|Retoque)/.test(txt(s)) && re.test(txt(s)));
      return { num: txt(b).match(/Nº (\d+)/)?.[1], txt: txt(b), ...R(b), toque: R(spans.find((s) => /^Toque\b/.test(txt(s)))), retoque: R(spans.find((s) => /^Retoque\b/.test(txt(s)))),
        res: [...b.querySelectorAll(".ft-res")].map((e) => ({ letra: txt(e), ...R(e) })), chip: R(b.querySelector(".ft-st")), selo: R(b.querySelector(".ft-selo")), seloTxt: txt(b.querySelector(".ft-selo")), breve: b.classList.contains("ft-cartao-breve"), ainda: b.classList.contains("ft-cartao-ainda") };
    });
    r.rowsLista = [...d.querySelectorAll("div")].filter((x) => x.querySelector(':scope > button svg') && x.querySelector('button[title^="Enviar"]')).map((x) => {
      const bs = x.querySelectorAll("button"); return { txt: txt(x), ...R(x), link: R(bs[0]), mail: R(x.querySelector('button[title^="Enviar"]')) };
    });
    r.ordenar = R(d.querySelector("select.mob-input")); r.excel = R([...d.querySelectorAll("button")].find((b) => /Excel/.test(b.textContent))); r.pdf = R([...d.querySelectorAll("button")].find((b) => /PDF/.test(b.textContent)));
    return r;
  });
  const leg = document.querySelector('[data-testid="legenda-toque"]'); o.legenda = leg ? { ...R(leg), itens: [...leg.children].map((c) => ({ txt: txt(c), ...R(c), res: R(c.querySelector(".ft-res, .ft-selo, .ft-traco")) })) } : null;
  const busca = o.dets.find((d) => /Buscar por parâmetro/.test(d.txt));
  if (busca) { const d = [...document.querySelectorAll("details")].find((x) => /Buscar por parâmetro/.test(txt(x.querySelector("summary")))); o.busca = { ...busca, selects: [...d.querySelectorAll("select")].map((e) => R(e)), inputs: [...d.querySelectorAll("input")].map((e) => R(e)), botao: R([...d.querySelectorAll("button")].find((b) => /Buscar animais/.test(b.textContent))) }; }
  o.email = R(document.querySelector('input[type="email"]')); const em = document.querySelector('input[type="email"]'); if (em) { const bs = em.parentElement.querySelectorAll("button"); o.emailOk = R(bs[0]); o.emailX = R(bs[1]); }
  return o;
});

// ── páginas altas: viewport = altura do documento, cabeçalho e barra escondidos ──
async function alta(nome) {
  const estilo = await p.addStyleTag({ content: "header,nav.mob-nav{visibility:hidden!important}" });
  const H0 = await p.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  await p.setViewportSize({ width: 390, height: Math.max(844, Math.min(H0, 5200)) }); await esp(900); await topo();
  const m = await coletar(); await p.screenshot({ path: OUT + nome + ".png" });
  await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  await estilo.evaluate((e) => e.remove()); await topo();
  mapa[nome] = m; log("alta", nome, "docH", m.docH);
}
// ── folha (gaveta): o diálogo inteiro, sem rolagem interna (viewport alto), caixas relativas ao topo do diálogo ──
async function folha(nome, extra) {
  const dlg = p.locator('[role="dialog"]');
  await p.setViewportSize({ width: 390, height: 2300 }); await esp(700);
  const info = await dlg.evaluate((d) => {
    const r0 = d.getBoundingClientRect(), R = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return { x: +r.x.toFixed(2), y: +(r.y - r0.y).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) }; };
    const txt = (e) => (e?.innerText || "").replace(/\s+/g, " ").trim();
    const sel = [...d.querySelectorAll("select")];
    const o = { h: r0.height, w: r0.width, titulo: R(d.querySelector("h2")), fechar: R(d.querySelector('button[aria-label="Fechar"]')), nome: R(d.querySelector("input")), nomeLabel: R([...d.querySelectorAll("label,div,span")].find((e) => e.children.length === 0 && txt(e) === "Nome do card")),
      categoria: R(sel[0]), situacao: R(sel[1]), loteBtn: R([...d.querySelectorAll("button")].find((b) => b.title && /Escolher um ou vários/.test(b.title))),
      salvar: R([...d.querySelectorAll("button")].find((b) => /Salvar card/.test(b.textContent))), adicionar: R([...d.querySelectorAll("button")].find((b) => /Adicionar período/.test(b.textContent))),
      nums: [...d.querySelectorAll('input[type="number"]')].map(R), chips: [...d.querySelectorAll("span")].filter((s) => /^\d+ a \d+$/.test(txt(s))).map((s) => ({ txt: txt(s), ...R(s) })),
      periodoLabel: R([...d.querySelectorAll("label,div,span")].find((e) => e.children.length === 0 && /^Períodos/.test(txt(e)))), labelSit: R([...d.querySelectorAll("label,div,span")].find((e) => e.children.length === 0 && txt(e) === "Situação reprodutiva")),
      opcoes: sel[1] ? [...sel[1].options].map((op) => ({ txt: op.text, ...R(op) })) : [] };
    return o;
  });
  await dlg.screenshot({ path: OUT + nome + ".png" });
  await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  mapa[nome] = { ...info, ...(extra || {}) }; log("folha", nome, "h", info.h);
}
const vp = async (nome, extra = {}) => { await p.screenshot({ path: OUT + nome + ".png" }); mapa[nome] = { ...(await coletar()), ...extra }; log("vp", nome); };

await fetch(API + "/__reset");
// ═══ 1) Menu: placas (abertura 3D) e Menu com Reprodução aberta ═══
await p.goto(APP + "/app/menu", { waitUntil: "networkidle" }); await esp(1500);
await p.evaluate(() => localStorage.setItem("mob_menu_secoes_colapsadas", JSON.stringify(["protocolos-restrito", "reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro", "modulos", "administracao", "app"])));
await p.reload({ waitUntil: "networkidle" }); await esp(1500);
const heads = await p.$$eval("button[aria-expanded]", (bs) => bs.map((b) => { const rr = (b.parentElement || b).getBoundingClientRect(); return { txt: b.innerText.replace(/\s+/g, " ").trim(), px: rr.x, py: rr.y, pw: rr.width, ph: rr.height }; }));
const nomes = ["reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro"];
for (let i = 0; i < 6; i++) { const h = heads[i]; await p.screenshot({ path: OUT + `placa_${nomes[i]}.png`, clip: { x: h.px, y: h.py, width: h.pw, height: h.ph } }); }
mapa.heads = heads;
await p.locator("button[aria-expanded]", { hasText: "Reprodução" }).first().click(); await esp(900);
await p.screenshot({ path: OUT + "menu_repro.png" });
{ const r = await p.locator("button[aria-expanded]", { hasText: "Reprodução" }).first().evaluate((b) => { const r = b.parentElement.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); await p.screenshot({ path: OUT + "placa_reproducao_aberta.png", clip: { x: r.x, y: r.y, width: r.w, height: r.h } }); mapa.reproCard = r; }
mapa.menu = await p.evaluate(() => {
  const R = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
  const items = [...document.querySelectorAll("button")].filter((b) => /Agenda Reprodutiva|Protocolos IATF|Ciclos de 21 dias/.test(b.innerText)).map((b) => ({ txt: b.innerText.replace(/\s+/g, " ").trim(), ...R(b) }));
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  return { items, hdrBottom: hdr.getBoundingClientRect().bottom, navTop: nav.getBoundingClientRect().top };
});
log("menu", JSON.stringify(mapa.menu.items.map((i) => i.txt)));

// ═══ 2) Agenda Reprodutiva: estado inicial (3 cards) ═══
await p.locator("button", { hasText: "Agenda Reprodutiva" }).first().click(); await esp(2400); await topo();
await p.screenshot({ path: OUT + "ag0_vp.png" });   // viewport com cabeçalho e barra reais (fonte das faixas fixas)
await alta("ag0");

// ═══ 3) Novo card, campo a campo ═══
await p.locator("button", { hasText: "Novo card" }).first().click(); await esp(1600);
await p.screenshot({ path: OUT + "gav0_vp.png" });
await folha("d0");
const dlg = p.locator('[role="dialog"]');
const NOME = "Inseminadas 30–59 · 01 - Alta";
const passos = ["Inse", "Inseminadas", "Inseminadas 30–59", "Inseminadas 30–59 · 01", NOME];
for (let i = 0; i < passos.length; i++) { await dlg.locator("input").first().fill(passos[i]); await esp(250); await folha("dn" + (i + 1), { texto: passos[i] }); }
await dlg.locator("select").nth(0).selectOption("vaca"); await esp(300); await folha("dcat");
await dlg.locator("button[title^='Escolher um ou vários']").click(); await esp(900);
await vp("pk0"); { const m = await p.evaluate(() => { const R = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }; const tr = [...document.querySelectorAll("tr")].map((t) => ({ txt: t.innerText.replace(/\s+/g, " ").trim(), ...R(t) })); const ok = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "OK"); return { tr, ok: R(ok) }; }); mapa.pkx = m; }
await p.getByText("01 - Alta", { exact: true }).first().click(); await esp(400); await vp("pk1");
await p.getByRole("button", { name: "OK" }).click(); await esp(600); await folha("dlote");
await dlg.locator("select").nth(1).evaluate((s) => { s.size = 6; }); await esp(400); await folha("dsit");
await dlg.locator("select").nth(1).evaluate((s) => { s.removeAttribute("size"); s.size = 0; });
await dlg.locator("select").nth(1).selectOption("inseminada"); await esp(500); await folha("dins");
await dlg.locator('input[type="number"]').nth(0).fill("30"); await esp(250); await folha("dde");
await dlg.locator('input[type="number"]').nth(1).fill("59"); await esp(250); await folha("date");
await dlg.getByRole("button", { name: /Adicionar período/ }).click(); await esp(500); await folha("dchip");

// ═══ 4) Salvar → a gaveta desce e o card aparece ═══
await dlg.getByRole("button", { name: /Salvar card/ }).click(); await esp(2000); await topo();
await alta("ag1");
// ═══ 5) Filtro A tocar → + A reconfirmar → + Reconfirmadas → limpar ═══
const btns = p.locator(".ft-botao-mob");
await btns.nth(0).click(); await esp(900); await topo(); await alta("f1");
await btns.nth(1).click(); await esp(900); await topo(); await alta("f2");
await btns.nth(2).click(); await esp(900); await topo(); await alta("f3");
await p.getByRole("button", { name: "Limpar filtro" }).click(); await esp(800); await topo();
// ═══ 6) Abrir o card novo (rolar até ele) e depois a Gestantes ═══
const det = (re) => p.locator("details").filter({ has: p.locator("summary", { hasText: re }) }).first();
await det(/Inseminadas 30–59 · 01/).locator("summary").click(); await esp(900); await topo(); await alta("ag2");
await det(/Gestantes 60–89/).locator("summary").click(); await esp(900); await topo(); await alta("ag3");
await det(/Inseminadas 30–59 · 01/).locator("summary").click(); await esp(500); await det(/Gestantes 60–89/).locator("summary").click(); await esp(700); await topo();
// ═══ 7) Engrenagem → "Editar card" ═══
await p.locator('button[title="Editar card"]').nth(3).click(); await esp(1600);
await folha("dedit");
await p.locator('[role="dialog"] button[aria-label="Fechar"]').click(); await esp(900); await topo();
// ═══ 8) Buscar por parâmetro ═══
await det(/Buscar por parâmetro/).locator("summary").click(); await esp(900); await topo(); await alta("ag5");
// ═══ 9) Lista fixa "Inseminadas 30–59 dias (tocar)" ═══
await det(/Inseminadas 30–59 dias/).locator("summary").click(); await esp(900); await topo(); await alta("ag7");
// e-mail do último diagnóstico (envelope)
await det(/Inseminadas 30–59 dias/).locator('button[title^="Enviar"]').first().click(); await esp(700); await topo(); await alta("ag8");
await det(/Inseminadas 30–59 dias/).locator('button[title^="Enviar"]').first().click(); await esp(500);
// ═══ 10) Ficha do animal ═══
await det(/Inseminadas 30–59 dias/).locator("button", { hasText: "Nº 4318" }).first().click(); await esp(1800); await topo();
await p.screenshot({ path: OUT + "ficha_vp.png" }); mapa.ficha = await coletar();
mapa.fichaBoxes = await p.evaluate(() => { const R = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }; const hdr = document.querySelector("header"); return { voltar: R(document.querySelector('button[aria-label="Voltar"]')), h1: R(document.querySelector("h1")) }; });
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1));
await br.close(); log("ok");
