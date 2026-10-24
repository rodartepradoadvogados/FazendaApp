// T3 · Ep. 7 (Alimentação: Lançar nova dieta e Necessidade Mensal — Menu › Alimentação; fecha o módulo) — telas REAIS do app em produção contra o stub (EP=t3e7), DPR 3 por padrão.
// Saída em shots_ep/: placas do Menu (recolhidas e Alimentação aberta), Menu com Alimentação aberta e as telas REAIS como PÁGINAS ALTAS (cabeçalho e barra escondidos; o motor rola a imagem
// por trás das barras reais): Lançar nova dieta em 9 estados (ld0 vazio · ld1 lote 02 escolhido · ld2 provável fim · ld3 3 tratos · ld4 40/30/30 + sobra · ld5 produto 1 escolhido · ld6 produto 1 com total ·
// ld7 4 produtos · ld8 depois de salvar), o seletor de produto aberto (pk_vp, viewport), Plano por Lote (pl0, já com a dieta nova), Consultar dietas (cs0) e Necessidade Mensal (nm0) + mapa.json com as caixas reais do DOM
// (px CSS; páginas altas em coordenadas do documento) e o TEXTO REAL do window.confirm (mapa.confirm.msg), capturado por page.on("dialog") e aceito (OK).
//   EP=t3e7 STUB_PORT=8700 node stub-api.mjs &   ·   next start -p 3700   →   STUB=8700 APP=3700 node capturar_t3e7_ep.mjs      DSF=1 para teste rápido
// O app em produção foi compilado com a API em localhost:8000: as chamadas são redirecionadas para a porta do stub por context.route. Hoje = 24/10/2026 (relógio fixo).
// O cabeçalho do app lê a fazenda atual: grava-se fazenda_atual = "Fazenda Boa Esperança" no localStorage (lib.mjs) em vez de trocar texto no DOM.
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const DSF = Number(process.env.DSF || 3), OUT = "shots_ep/"; fs.mkdirSync(OUT, { recursive: true });
const STUB = process.env.STUB || 8000, APPP = process.env.APP || 3000, API = `http://localhost:${STUB}`, APP = `http://localhost:${APPP}`;
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const ctx = await novoContexto(br, 844, DSF);
await ctx.addInitScript(() => {
  localStorage.setItem("usuario", JSON.stringify({ id: 1, nome: "Bernadete", papel: "admin", eh_dono: true, permissoes: [] }));
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache") || k.startsWith("menu_")) localStorage.removeItem(k); } catch {}
});
if (STUB != 8000) await ctx.route("http://localhost:8000/**", (r) => r.continue({ url: r.request().url().replace("localhost:8000", "localhost:" + STUB) }));
const p = await pagina(ctx); await p.clock.setFixedTime(new Date("2026-10-24T10:05:00-03:00")); const esp = (ms = 700) => p.waitForTimeout(ms);
const mapa = { dsf: DSF }; const log = (...a) => console.log(...a);
const topo = async () => { await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); }); await esp(350); };

// ── caixas reais (px CSS, coordenadas do documento) ──
const coletar = () => p.evaluate(() => {
  const sy = window.scrollY, box = (r) => ({ x: +r.x.toFixed(2), y: +(r.y + sy).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) });
  const R = (e) => (e ? box(e.getBoundingClientRect()) : null);
  const txt = (e) => (e?.innerText || "").replace(/\s+/g, " ").trim();
  // caixa de um trecho de texto dentro de um elemento, mesmo quando o React separa o texto em vários nós ("{n} animais · {k} tratos (…)")
  const trecho = (el, re) => { if (!el) return null; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), ns = []; let n, all = ""; while ((n = w.nextNode())) { ns.push([n, all.length]); all += n.textContent; }
    const m = all.match(re); if (!m) return null; const i0 = m.index, i1 = m.index + m[0].length; const rg = document.createRange(); let ok0 = false, ok1 = false;
    for (const [nd, off] of ns) { const L = nd.textContent.length; if (!ok0 && i0 < off + L) { rg.setStart(nd, i0 - off); ok0 = true; } if (!ok1 && i1 <= off + L) { rg.setEnd(nd, i1 - off); ok1 = true; break; } }
    return ok0 && ok1 ? box(rg.getBoundingClientRect()) : null; };
  const o = { docH: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  o.hdrBottom = hdr ? hdr.getBoundingClientRect().bottom : 0; o.navTop = nav ? nav.getBoundingClientRect().top : 844;
  o.voltar = R(document.querySelector('button[aria-label="Voltar"]')); o.titulo = R(document.querySelector("h1")); o.tituloTxt = txt(document.querySelector("h1"));
  const folhas = (c) => [...c.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e)).map((e) => ({ txt: txt(e), ...R(e), cor: getComputedStyle(e).color, fs: getComputedStyle(e).fontSize }));
  // cartões (Plano por Lote, Consultar dietas): caixa, folhas de texto, linhas filhas diretas, trechos do cabeçalho do Plano
  o.cards = [...document.querySelectorAll(".mob-card")].map((c) => ({ txt: txt(c), ...R(c), folhas: folhas(c), linhas: [...c.children].map((d) => ({ txt: txt(d), ...R(d) })),
    efetivo: trecho(c, /\d+ animais?/), tratos: trecho(c, /\d tratos? \([^)]*\)/), cab: trecho(c, /[\d.,]+ \w+\/cab/), dia: trecho(c, /[\d.,]+ \w+\/dia/), tratosN: trecho(c, /\d tratos?(?= \()/), tratosPct: trecho(c, /\([^)]*\)/) }));
  o.ps = [...document.querySelectorAll("p")].map((e) => ({ txt: txt(e), ...R(e), cor: getComputedStyle(e).color }));
  o.menuItens = [...document.querySelectorAll("button")].filter((b) => /^(Plano por Lote|Lançar nova dieta|Consultar dietas|Necessidade Mensal)/.test(txt(b))).map((b) => ({ txt: txt(b), ...R(b) }));
  o.heads = [...document.querySelectorAll("button[aria-expanded]")].map((b) => ({ txt: txt(b), aberta: b.getAttribute("aria-expanded"), ...R(b), pai: R(b.parentElement) }));
  // Lançar nova dieta: editor "Tratos por dia" (EditorTratosDieta)
  const rot = [...document.querySelectorAll("span")].find((e) => txt(e) === "Tratos por dia");
  if (rot) { const ed = rot.parentElement;
    o.editor = { caixa: R(ed), titulo: R(rot),
      pills: [...ed.querySelectorAll("button")].slice(0, 4).map((b) => ({ txt: txt(b), ...R(b) })),
      pillsUniao: (() => { const bs = [...ed.querySelectorAll("button")].slice(0, 4).map((b) => b.getBoundingClientRect()); const x0 = Math.min(...bs.map((r) => r.x)), y0 = Math.min(...bs.map((r) => r.y)), x1 = Math.max(...bs.map((r) => r.right)), y1 = Math.max(...bs.map((r) => r.bottom)); return box({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 }); })(),
      rotuloPct: R([...ed.querySelectorAll("span")].find((e) => /^% de cada trato/.test(txt(e)))),
      labels: [...ed.querySelectorAll("label")].map((l) => ({ txt: txt(l), ...R(l), span: R(l.querySelector("span")), input: R(l.querySelector("input")), valor: l.querySelector("input")?.value ?? null })),
      soma: R([...ed.querySelectorAll("p")].find((e) => /^Soma:|^Os %/.test(txt(e)))), somaTxt: txt([...ed.querySelectorAll("p")].find((e) => /^Soma:|^Os %/.test(txt(e)))),
      rotuloSobra: R([...ed.querySelectorAll("span")].find((e) => /^A sobra do cocho/.test(txt(e)))),
      pillsSobra: [...ed.querySelectorAll("button")].slice(4).map((b) => ({ txt: txt(b), ativa: b.getAttribute("aria-pressed") === "true", ...R(b) })),
      explica: R([...ed.querySelectorAll("p")].find((e) => /^Define o ciclo/.test(txt(e)))), explicaTxt: txt([...ed.querySelectorAll("p")].find((e) => /^Define o ciclo/.test(txt(e)))) };
    const bs2 = [...ed.querySelectorAll("button")].slice(4).map((b) => b.getBoundingClientRect());
    if (bs2.length) { const x0 = Math.min(...bs2.map((r) => r.x)), y0 = Math.min(...bs2.map((r) => r.y)), x1 = Math.max(...bs2.map((r) => r.right)), y1 = Math.max(...bs2.map((r) => r.bottom)); o.editor.pillsSobraUniao = box({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 }); }
    o.campos = [...document.querySelectorAll("label")].filter((l) => !ed.contains(l)).map((l) => ({ txt: txt(l), ...R(l) }));
  }
  // Consultar dietas expandida: cabeçalho (nome · animais · tratos), itens (nome + linha T/dia/cab) e Vagão
  const cabec = [...document.querySelectorAll("div")].find((e) => e.children.length === 0 && / animais? · \d tratos?/.test(txt(e)));
  if (cabec) { o.apres = { cab: R(cabec), cabTxt: txt(cabec), tratosTrecho: trecho(cabec, /\d tratos? \([^)]*\)/), animaisTrecho: trecho(cabec, /\d+ animais?/), tratosN: trecho(cabec, /\d tratos?(?= \()/), tratosPct: trecho(cabec, /\([^)]*\)/) };
    const aberto = cabec.parentElement; const itens = [...aberto.children].filter((d) => d.children.length === 2 && d.children[1]?.children.length === 3);
    o.apres.itens = itens.map((d) => ({ txt: txt(d), ...R(d), nome: R(d.children[0]), linha: R(d.children[1]), t: R(d.children[1].children[0]), tTxt: txt(d.children[1].children[0]), dia: R(d.children[1].children[1]), cab: R(d.children[1].children[2]) }));
    const vag = [...aberto.children].find((d) => /^Vagão:/.test(txt(d))); o.apres.vagao = R(vag); o.apres.vagaoTxt = txt(vag); o.apres.vagaoT = R(vag?.querySelector("span")); o.apres.vagaoDia = vag ? trecho(vag, /[\d.,]+ kg\/dia/) : null;
    o.apres.bloco = R(aberto); }

  const tight = (e) => { if (!e) return null; const rg = document.createRange(); rg.selectNodeContents(e); return box(rg.getBoundingClientRect()); };
  const rotuloDe = (re) => [...document.querySelectorAll("label")].find((l) => re.test(txt(l).slice(0, 40)));
  // ── Lançar nova dieta ──
  const lLote = [...document.querySelectorAll("label")].find((l) => txt(l) === "Lote");
  if (lLote) { const sel = lLote.parentElement.querySelector("select");
    o.ld = { lote: R(lLote.parentElement), loteRotulo: R(lLote), loteSelect: R(sel), loteTxt: sel ? sel.selectedOptions[0]?.textContent : null };
    const ctxc = [...document.querySelectorAll(".mob-card")].find((c) => /DEL médio/.test(txt(c)));
    if (ctxc) { const sp = [...ctxc.querySelectorAll("span")].filter((s) => s.parentElement === ctxc.firstElementChild);
      o.ld.ctx = { card: R(ctxc), animais: tight(sp[0]), del: tight(sp[1]), media: tight(sp[2]), ultCl: tight(sp[3]), ultDieta: ctxc.children[1] ? tight(ctxc.children[1]) : null, ultDietaTxt: txt(ctxc.children[1]) , txt: txt(ctxc), spans: sp.map((s) => txt(s)) }; }
    const ini = rotuloDe(/^Data de início/), fim = rotuloDe(/^Provável fim/);
    o.ld.inicio = ini ? { campo: R(ini.parentElement), rotulo: R(ini), input: R(ini.parentElement.querySelector("input")), valor: ini.parentElement.querySelector("input").value } : null;
    o.ld.fim = fim ? { campo: R(fim.parentElement), rotulo: R(fim), input: R(fim.parentElement.querySelector("input")), valor: fim.parentElement.querySelector("input").value } : null;
    if (o.ld.inicio && o.ld.fim) o.ld.datas = { x: Math.min(o.ld.inicio.campo.x, o.ld.fim.campo.x), y: o.ld.inicio.campo.y, w: o.ld.fim.campo.x + o.ld.fim.campo.w - o.ld.inicio.campo.x, h: o.ld.inicio.campo.h };
    o.ld.produtos = [...document.querySelectorAll(".mob-card")].filter((c) => /^Produto \d/.test(txt(c))).map((c) => { const lr = [...c.querySelectorAll("label")];
      const lP = lr.find((l) => /^Produto \d/.test(txt(l))), lT = lr.find((l) => /^Total\/dia/.test(txt(l))), lU = lr.find((l) => txt(l) === "Unidade");
      const calc = [...c.querySelectorAll("span")].filter((s) => s.parentElement.children.length === 3 && s.parentElement.style.flexWrap === "wrap");
      return { card: R(c), rotulo: R(lP), rotuloTxt: txt(lP), campoProduto: R(lP.parentElement), botao: R(lP.parentElement.querySelector("button")), botaoTxt: txt(lP.parentElement.querySelector("button")),
        campoTotal: R(lT.parentElement), rotuloTotal: R(lT), inputTotal: R(lT.parentElement.querySelector("input")), valorTotal: lT.parentElement.querySelector("input").value,
        campoUnidade: R(lU.parentElement), rotuloUnidade: R(lU), selectUnidade: R(lU.parentElement.querySelector("select")),
        calcLinha: calc.length ? R(calc[0].parentElement) : null, calcT: calc[0] ? tight(calc[0]) : null, calcTTxt: calc[0] ? txt(calc[0]) : null, calcDia: calc[1] ? tight(calc[1]) : null, calcDiaTxt: calc[1] ? txt(calc[1]) : null, calcCab: calc[2] ? tight(calc[2]) : null, calcCabTxt: calc[2] ? txt(calc[2]) : null }; });
    const vag = [...document.querySelectorAll("div")].find((d) => /^Vagão:/.test(txt(d)) && d.children.length === 1 && d.children[0].tagName === "SPAN");
    if (vag) o.ld.vagao = { caixa: R(vag), t: tight(vag.children[0]), tTxt: txt(vag.children[0]), dia: trecho(vag, /[\d.,]+ kg\/dia/), diaTxt: (txt(vag).match(/[\d.,]+ kg\/dia/) || [""])[0], rotulo: trecho(vag, /^Vagão:/), txt: txt(vag) };
    const bs = [...document.querySelectorAll("button")]; const bSalvar = bs.find((b) => /^Salvar dieta|^Salvando/.test(txt(b))), bAdd = bs.find((b) => /Acrescentar produto/.test(txt(b)));
    o.ld.salvar = R(bSalvar); o.ld.acrescentar = R(bAdd);
    const av = [...document.querySelectorAll("p")].find((q) => /^(Dieta salva|Sem internet|Cancelado|Selecione|Adicione|Erro)/.test(txt(q))); o.ld.aviso = av ? { caixa: R(av), txt: txt(av), t: tight(av) } : null;
  }
  // ── seletor de produto (modal fixo) ──
  const mod = [...document.querySelectorAll("div.card")].find((c) => /Escolher produto/i.test(txt(c)));
  if (mod) o.pk = { caixa: R(mod), titulo: tight(mod.querySelector(".card-header")), busca: R(mod.querySelector("input")), linhas: [...mod.querySelectorAll("tbody tr")].map((tr) => ({ txt: txt(tr), ...R(tr), nome: tight(tr.children[0]) })), cabec: R(mod.querySelector("thead")) };
  // ── Necessidade Mensal ──
  const nota = o.ps.find((q) => /^Projeção simples/.test(q.txt));
  if (nota) { const pe = [...document.querySelectorAll("p")].find((q) => /^Projeção simples/.test(txt(q)));
    o.nm = { nota, notaTight: tight(pe), frase1: trecho(pe, /Projeção simples: consumo diário × 30 dias\./), frase1b: trecho(pe, /consumo diário × 30 dias/), frase2: trecho(pe, /Silagem não converte em sacas \(sempre a granel\)\./),
      itens: [...document.querySelectorAll(".mob-card")].map((c) => { const fl = [...c.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e));
        return { txt: txt(c), card: R(c), nome: tight(fl[0]), nomeTxt: txt(fl[0]), valor: tight(fl[1]), valorTxt: txt(fl[1]), sacas: fl[2] ? tight(fl[2]) : null, sacasTxt: fl[2] ? txt(fl[2]) : null }; }) }; }
  return o;
});
// páginas altas: viewport = altura do documento, cabeçalho e barra escondidos (o motor rola a imagem por trás das barras reais)
async function alta(nome) {
  const estilo = await p.addStyleTag({ content: "header,nav.mob-nav{visibility:hidden!important}" });
  const H0 = await p.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  await p.setViewportSize({ width: 390, height: Math.max(844, Math.min(H0, 5200)) }); await esp(900); await topo();
  const m = await coletar(); await p.screenshot({ path: OUT + nome + ".png" });
  await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  await estilo.evaluate((e) => e.remove()); await topo();
  mapa[nome] = m; log("alta", nome, "docH", m.docH);
}
const vp = async (nome) => { await p.screenshot({ path: OUT + nome + ".png" }); mapa[nome] = await coletar(); log("vp", nome); };
const abrirItem = async (re) => { await p.evaluate((s) => [...document.querySelectorAll("button")].find((x) => new RegExp(s).test(x.innerText.trim())).click(), re); };
const voltar = async () => { await p.getByRole("button", { name: "Voltar" }).first().click(); await esp(1300); await topo(); };

await fetch(API + "/__reset");
// ═══ 1) Menu: placas recolhidas (abertura 3D) e Menu com Alimentação aberta ═══
const COLAPSADAS = ["protocolos-restrito", "reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro", "modulos", "administracao", "app"];
await p.goto(APP + "/app/menu", { waitUntil: "networkidle" }); await esp(1500);
await p.evaluate((c) => localStorage.setItem("mob_menu_secoes_colapsadas", JSON.stringify(c)), COLAPSADAS);
await p.reload({ waitUntil: "networkidle" }); await esp(1500);
const heads = await p.$$eval("button[aria-expanded]", (bs) => bs.map((b) => { const rr = (b.parentElement || b).getBoundingClientRect(); return { txt: b.innerText.replace(/\s+/g, " ").trim(), px: rr.x, py: rr.y, pw: rr.width, ph: rr.height }; }));
const nomes = ["reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro"];
for (let i = 0; i < 6; i++) { const h = heads[i]; await p.screenshot({ path: OUT + `placa_${nomes[i]}.png`, clip: { x: h.px, y: h.py, width: h.pw, height: h.ph } }); }
mapa.heads = heads; mapa.placasNomes = nomes;
await p.locator("button[aria-expanded]", { hasText: "Alimentação" }).first().click(); await esp(900);
await p.screenshot({ path: OUT + "menu_alim.png" });
{ const r = await p.locator("button[aria-expanded]", { hasText: "Alimentação" }).first().evaluate((b) => { const r = b.parentElement.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); await p.screenshot({ path: OUT + "placa_alimentacao_aberta.png", clip: { x: r.x, y: r.y, width: r.w, height: r.h } }); mapa.alimCard = r; }
mapa.menu_alim = await coletar(); log("menu_alim", JSON.stringify(mapa.menu_alim.menuItens.map((i) => [i.txt.slice(0, 22), Math.round(i.y)])), JSON.stringify(mapa.menu_alim.heads.map((h) => [h.txt.slice(0, 12), h.aberta, Math.round(h.pai.y), Math.round(h.pai.h)])));

// ═══ 2) Lançar nova dieta — formulário em estados ═══
const reabrir = async () => { if (!(await coletar()).menuItens.length) { await p.locator("button[aria-expanded]", { hasText: "Alimentação" }).first().click(); await esp(900); } };
await abrirItem("^Lançar nova dieta"); await p.waitForSelector("text=Tratos por dia", { timeout: 15000 }); await esp(1500); await topo();
await p.screenshot({ path: OUT + "ld_vp.png" }); mapa.ld_vp = await coletar();
await alta("ld0");                                                       // vazio: "Selecione o lote…", início = hoje, 2 tratos 50/50
await p.selectOption("select.mob-input >> nth=0", "02"); await p.waitForSelector("text=DEL médio", { timeout: 15000 }); await esp(1200); await topo();
await alta("ld1");                                                       // lote 02 - Média: cartão de contexto
await p.locator('input[type=date]').nth(1).fill("2026-12-31"); await esp(500);
await alta("ld2");                                                       // provável fim 31/12/2026
await p.getByRole("button", { name: "3", exact: true }).first().click(); await esp(500);
await alta("ld3");                                                       // 3 tratos (33,33 / 33,33 / 33,34)
{ const ins = p.locator('input[type=number]'); await ins.nth(0).fill("40"); await ins.nth(1).fill("30"); await ins.nth(2).fill("30"); await esp(400); }
await p.getByRole("button", { name: /^Trato 3 → Trato 1$/ }).click(); await esp(500);
await alta("ld4");                                                       // 40/30/30, sobra lida entre Trato 3 → Trato 1
// produto 1: seletor aberto (viewport) e escolha da silagem
const abrePicker = async (idx) => { await p.locator(".mob-card", { hasText: `Produto ${idx}` }).locator("button").first().click(); await p.waitForSelector("text=Escolher produto", { timeout: 8000 }); await esp(700); };
await abrePicker(1); await p.screenshot({ path: OUT + "pk_vp.png" }); mapa.pk_vp = await coletar();
await p.locator("tr", { hasText: "Silagem de milho" }).first().click(); await esp(600); await topo();
await alta("ld5");                                                       // produto 1 escolhido, sem total ainda
await p.locator('input[type=number][placeholder="0"]').first().fill("1230"); await esp(500);
await alta("ld6");                                                       // silagem 1230 kg: T1·T2·T3, kg/dia, kg/cab
const OUTROS = [["Concentrado lactação", "328"], ["Feno de tifton", "82"], ["Núcleo mineral", "8.2"]];
for (let k = 0; k < OUTROS.length; k++) {
  await p.getByRole("button", { name: /Acrescentar produto/ }).click(); await esp(400);
  await abrePicker(k + 2); await p.locator("tr", { hasText: OUTROS[k][0] }).first().click(); await esp(500);
  await p.locator('input[type=number][placeholder="0"]').nth(k + 1).fill(OUTROS[k][1]); await esp(400);
}
await topo(); await alta("ld7");                                         // 4 produtos preenchidos + Vagão
// salvar: o window.confirm é NATIVO e não renderiza no headless — captura o texto REAL e aceita (OK)
mapa.confirm = null;
p.once("dialog", async (d) => { mapa.confirm = { tipo: d.type(), msg: d.message() }; await d.accept(); });
await p.getByRole("button", { name: "Salvar dieta" }).click(); await p.waitForSelector("text=Dieta salva", { timeout: 15000 }); await esp(1500); await topo();
log("confirm:", JSON.stringify(mapa.confirm));
await alta("ld8");                                                       // depois de salvar: aviso "Dieta salva para o lote 02." e formulário zerado
// ═══ 3) Voltar → Plano por Lote (já com a dieta nova) ═══
await voltar(); await reabrir(); mapa.menu_alim_volta = await coletar();
await abrirItem("^Plano por Lote"); await p.waitForSelector("text=Lote 2", { timeout: 15000 }); await esp(1800); await topo();
await p.screenshot({ path: OUT + "pl_vp.png" }); mapa.pl_vp = await coletar();
await alta("pl0");
// ═══ 4) Consultar dietas (a anterior do lote 2 encerrada) ═══
await voltar(); await reabrir();
await abrirItem("^Consultar dietas"); await p.waitForSelector("text=Encerrada", { timeout: 15000 }); await esp(1500); await topo();
await alta("cs0");
// ═══ 5) Necessidade Mensal ═══
await voltar(); await reabrir();
await abrirItem("^Necessidade Mensal"); await p.waitForSelector("text=Projeção simples", { timeout: 15000 }); await esp(1800); await topo();
await p.screenshot({ path: OUT + "nm_vp.png" }); mapa.nm_vp = await coletar();
await alta("nm0");
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1));
await br.close(); log("ok");
