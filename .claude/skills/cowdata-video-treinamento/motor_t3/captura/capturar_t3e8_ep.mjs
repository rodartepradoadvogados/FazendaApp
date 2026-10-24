// T3 · Ep. 8 (Sanidade — Menu › Sanidade, módulo inteiro) — telas REAIS do app em produção contra o stub (EP=t3e8), DPR 3 por padrão.
// Saída em shots_ep/: placas do Menu (recolhidas e Sanidade aberta), Menu com Sanidade aberta e as telas REAIS como PÁGINAS ALTAS (cabeçalho e barra escondidos; o motor rola a imagem por trás das
// barras reais): Vacinas e exames (vl0), o dia de hoje em estados (ex0…ex9: preparação, quem aplica, como aplicar, tronco, "Não aplicar", sem sinal), o Histórico de tratamentos e vacinas
// (hs0 padrão · hs1 "Lote(s)" · hs2 lotes 01 e 02 · hs3 depois de marcar "Curado") e Remédios por Doença (rm0 · rm1) + gaveta "Não aplicar" (na_vp, viewport) + mapa.json com as caixas
// reais do DOM (px CSS; páginas altas em coordenadas do documento): botões, rótulos, folhas de texto, cartões, faixas, selects e o que a tela pede.
//   EP=t3e8 STUB_PORT=8800 node stub-api.mjs &   ·   next start -p 3800   →   STUB=8800 APP=3800 node capturar_t3e8_ep.mjs      DSF=1 para teste rápido
// O app em produção foi compilado com a API em localhost:8000: as chamadas são redirecionadas para a porta do stub por context.route (e abortadas na demonstração "sem sinal").
// Hoje = 24/10/2026 (relógio fixo). O cabeçalho lê `fazenda_atual` do localStorage (lib.mjs): "Fazenda Boa Esperança"; usuário "Zé".
import fs from "fs";
import { chromium, novoContexto, pagina } from "./lib.mjs";
const DSF = Number(process.env.DSF || 3), OUT = "shots_ep/"; fs.mkdirSync(OUT, { recursive: true });
const STUB = process.env.STUB || 8000, APPP = process.env.APP || 3000, API = `http://localhost:${STUB}`, APP = `http://localhost:${APPP}`;
const ALTURA_MAX = 5200;
const br = await chromium.launch({ args: ["--lang=pt-BR"], env: { ...process.env, LANGUAGE: "pt_BR", LC_ALL: "pt_BR.UTF-8", LANG: "pt_BR.UTF-8" } });
const ctx = await novoContexto(br, 844, DSF);
await ctx.addInitScript(() => {
  localStorage.setItem("usuario", JSON.stringify({ id: 1, nome: "Zé", papel: "admin", eh_dono: true, permissoes: [] }));
  try { for (const k of Object.keys(localStorage)) if (k.startsWith("rascunho") || k.startsWith("mob_cache") || k.startsWith("menu_")) localStorage.removeItem(k); } catch {}
});
let SEM_SINAL = false; // demonstração "sem sinal": as chamadas à API falham (o app segue com a cópia guardada no celular)
if (STUB != 8000) await ctx.route("http://localhost:8000/**", (r) => (SEM_SINAL ? r.abort("internetdisconnected") : r.continue({ url: r.request().url().replace("localhost:8000", "localhost:" + STUB) })));
const p = await pagina(ctx); await p.clock.setFixedTime(new Date("2026-10-24T10:05:00-03:00")); const esp = (ms = 700) => p.waitForTimeout(ms);
const mapa = { dsf: DSF }; const log = (...a) => console.log(...a);
const topo = async () => { await p.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); document.body.scrollTo(0, 0); document.scrollingElement.scrollTo(0, 0); }); await esp(350); };

// ── caixas reais (px CSS, coordenadas do documento) ──
const coletar = () => p.evaluate((ALT) => {
  const sy = window.scrollY, box = (r) => ({ x: +r.x.toFixed(2), y: +(r.y + sy).toFixed(2), w: +r.width.toFixed(2), h: +r.height.toFixed(2) });
  const R = (e) => (e ? box(e.getBoundingClientRect()) : null);
  const txt = (e) => (e?.innerText || e?.textContent || "").replace(/\s+/g, " ").trim();
  const tight = (e) => { if (!e) return null; const rg = document.createRange(); rg.selectNodeContents(e); return box(rg.getBoundingClientRect()); }; // caixa justa do texto do elemento
  const uniao = (...els) => { const bs = els.filter(Boolean).map((e) => e.getBoundingClientRect()); if (!bs.length) return null; const x0 = Math.min(...bs.map((r) => r.x)), y0 = Math.min(...bs.map((r) => r.y)), x1 = Math.max(...bs.map((r) => r.right)), y1 = Math.max(...bs.map((r) => r.bottom)); return box({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 }); };
  // caixa de um trecho de texto dentro de um elemento, mesmo quando o React separa o texto em vários nós
  const trecho = (el, re) => { if (!el) return null; const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), ns = []; let n, all = ""; while ((n = w.nextNode())) { ns.push([n, all.length]); all += n.textContent; }
    const m = all.match(re); if (!m) return null; const i0 = m.index, i1 = m.index + m[0].length; const rg = document.createRange(); let ok0 = false, ok1 = false;
    for (const [nd, off] of ns) { const L = nd.textContent.length; if (!ok0 && i0 < off + L) { rg.setStart(nd, i0 - off); ok0 = true; } if (!ok1 && i1 <= off + L) { rg.setEnd(nd, i1 - off); ok1 = true; break; } }
    return ok0 && ok1 ? box(rg.getBoundingClientRect()) : null; };
  const visivel = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.closest("header,nav.mob-nav") && getComputedStyle(e).visibility !== "hidden"; };
  const lista = (sel) => [...document.querySelectorAll(sel)].filter(visivel);
  const item = (e) => ({ txt: txt(e), ...R(e), tight: tight(e), ativa: e.getAttribute("aria-pressed") === "true" || e.classList.contains("ativa") || undefined, off: e.disabled || undefined, marcada: e.type === "checkbox" ? e.checked : undefined });
  const o = { docH: Math.min(ALT, Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)), docHReal: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight) };
  const hdr = document.querySelector("header"), nav = document.querySelector("nav.mob-nav");
  o.hdrBottom = hdr ? hdr.getBoundingClientRect().bottom : 0; o.navTop = nav ? nav.getBoundingClientRect().top : 844;
  o.voltar = R(document.querySelector('button[aria-label="Voltar"]')); o.titulo = R(document.querySelector("h1")); o.tituloTxt = txt(document.querySelector("h1")); o.tituloTight = tight(document.querySelector("h1"));
  // Menu: itens da seção Sanidade e cabeçalhos das seções
  o.menuItens = lista("button").filter((b) => /^(Vacinas e exames|Histórico de tratamentos e vacinas|Remédios por Doença)/.test(txt(b))).map((b) => ({ txt: txt(b), ...R(b), kids: [...b.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e)).map((e) => ({ txt: txt(e), ...R(e), tight: tight(e) })) }));
  o.heads = [...document.querySelectorAll("button[aria-expanded]")].map((b) => ({ txt: txt(b), aberta: b.getAttribute("aria-expanded"), ...R(b), pai: R(b.parentElement) }));
  // peças genéricas (qualquer tela): o roteiro escolhe por texto
  o.folhas = lista("main *, #__next *, body *").filter((e) => e.children.length === 0 && txt(e) && !["SCRIPT", "STYLE", "OPTION", "OPTGROUP", "svg", "path"].includes(e.tagName)).map(item);
  o.botoes = lista("button").map(item);
  o.rotulos = lista(".mob-san-rotulo").map(item);
  o.faixas = lista(".mob-san-faixa").map(item);
  o.linhasSan = lista(".mob-san-linha").map((e) => ({ ...item(e), folhas: [...e.querySelectorAll("*")].filter((f) => f.children.length === 0 && txt(f)).map(item), check: item(e.querySelector("input[type=checkbox]") || e) }));
  o.ps = lista("p").map(item);
  o.selects = lista("select").map((e) => ({ ...item(e), valor: e.selectedOptions[0]?.textContent ?? null, label: item(document.querySelector(`label[for="${e.id}"]`) || e) }));
  o.inputs = lista("input").map(item);
  o.cartoes = lista(".mob-card").map((c) => ({ ...item(c), folhas: [...c.querySelectorAll("*")].filter((f) => f.children.length === 0 && txt(f)).map(item) }));
  o.linhasLista = lista("button.mob-linha").map((b) => ({ ...item(b), folhas: [...b.querySelectorAll("*")].filter((f) => f.children.length === 0 && txt(f)).map(item) }));
  o.secoes = lista("section[aria-label]").map((s) => ({ rot: s.getAttribute("aria-label"), ...item(s.firstElementChild), bloco: R(s), folhas: [...s.firstElementChild.querySelectorAll("*")].filter((f) => f.children.length === 0 && txt(f)).map(item) }));
  // período (De / Até), escopo, grupos de pílulas, exportar, contagem — Histórico
  const datas = [...document.querySelectorAll("input[type=date]")];
  if (datas.length >= 2) { const l0 = datas[0].closest("label"), l1 = datas[1].closest("label");
    o.periodo = { de: R(l0), ate: R(l1), uniao: uniao(l0, l1), rotDe: tight(l0.querySelector("span")), rotAte: tight(l1.querySelector("span")), deVal: datas[0].value, ateVal: datas[1].value }; }
  const g = document.querySelector('[role=group][aria-label=Escopo]');
  if (g) o.escopo = { caixa: R(g), btns: [...g.querySelectorAll("button")].map((b) => ({ txt: txt(b), ativa: b.getAttribute("aria-pressed") === "true", ...R(b), tight: tight(b) })) };
  o.lotePills = lista("button.lote-pill").map((b) => ({ txt: txt(b), ativa: b.getAttribute("aria-pressed") === "true", ...R(b) }));
  o.lotePillsUniao = uniao(...document.querySelectorAll("button.lote-pill"));
  o.grupos = [...document.querySelectorAll("div")].filter((d) => [...d.children].filter((c) => c.tagName === "BUTTON" && c.classList.contains("mob-pill")).length >= 2).map((d) => {
    const rot = d.previousElementSibling; const bs = [...d.children].filter((c) => c.tagName === "BUTTON");
    return { rotulo: txt(rot), rot: R(rot), rotTight: tight(rot), pills: bs.map((b) => ({ txt: txt(b), ativa: b.getAttribute("aria-pressed") === "true", ...R(b) })), uniao: R(d), comRotulo: uniao(rot, d) }; });
  const bx = document.querySelector('button[title="Exportar para Excel"]'), bp = document.querySelector('button[title="Exportar para PDF"]');
  if (bx && bp) o.exportar = { excel: R(bx), pdf: R(bp), uniao: uniao(bx, bp) };
  o.contagem = lista("p").filter((e) => /^\d+ aplicações?/.test(txt(e))).map((e) => ({ txt: txt(e), ...R(e), tight: tight(e) }))[0] ?? null;
  o.msgCura = lista("p[role=status]").map((e) => ({ txt: txt(e), ...R(e), tight: tight(e) }))[0] ?? null;
  // cartões de registro do Histórico (Nº …): partes medidas dentro de cada folha de texto
  o.regs = lista(".mob-card").filter((c) => /^Nº \d/.test(txt(c))).slice(0, 16).map((c) => {
    const fl = [...c.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e));
    const tl = (re, leaf) => { const e = fl.find((x) => leaf.test(txt(x))); return e ? trecho(e, re) : null; };
    const bt = [...c.querySelectorAll("button")].map((b) => ({ txt: txt(b), ...R(b), ativa: b.getAttribute("aria-pressed") === "true" }));
    const et = fl.find((x) => /^(Curativo|Preventivo)$/.test(txt(x)));
    return { txt: txt(c), ...R(c), folhas: fl.map(item), etiqueta: et ? { txt: txt(et), ...R(et) } : null, numero: tl(/Nº \d+/, /^Nº \d/), data: tl(/\d\d\/\d\d\/\d{4}/, /^\d\d\/\d\d\/\d{4}$/),
      produto: (() => { const e = fl[3]; return e ? { txt: txt(e), ...R(e), tight: tight(e) } : null; })(),
      dose: tl(/\d+(,\d+)? mL/, / mL/), via: tl(/Intramuscular|Intravenosa|Subcutânea|Intramamária/, /Intramuscular|Intravenosa|Subcutânea|Intramamária/), doenca: tl(/(Mastite clínica|Pneumonia)$/, /(Mastite clínica|Pneumonia)$/),
      lote: tl(/Lote \d\d - [^·]+/, /^Lote \d\d/), responsavel: tl(/Responsável: .+$/, /Responsável:/), carencia: (() => { const e = fl.find((x) => /^Carência:/.test(txt(x))); return e ? { txt: txt(e), ...R(e), tight: tight(e) } : null; })(),
      curadoTxt: tl(/(Não curado|Curado)$/, /^(Curado|Não curado)$/), botoes: bt, grupoBotoes: (() => { const gp = c.querySelector('[role=group]'); return gp ? R(gp) : null; })() }; });
  o.nRegs = o.regs.length;
  // Remédios por Doença: cartões das opções e o aviso do substituto
  o.aviso = lista("div[role=status]").map((e) => ({ txt: txt(e), ...R(e), tight: tight(e) }))[0] ?? null;
  o.opcoes = lista(".mob-card").filter((c) => /escolha/.test(txt(c)) && !/^Nº/.test(txt(c))).map((c) => { const fl = [...c.querySelectorAll("*")].filter((e) => e.children.length === 0 && txt(e));
    const f = (re) => { const e = fl.find((x) => re.test(txt(x))); return e ? { txt: txt(e), ...R(e), tight: tight(e) } : null; };
    return { txt: txt(c), ...R(c), escolha: f(/ª escolha/), status: f(/^(Em estoque|Sem estoque|Estoque baixo)$/), nome: fl[2] ? { txt: txt(fl[2]), ...R(fl[2]), tight: tight(fl[2]) } : null, estoque: f(/em estoque$|Sem apresentações/), obs: f(/^Observação:/),
      obsTrecho: (() => { const e = [...c.querySelectorAll("div")].find((d) => /^Observação:/.test(txt(d)) && d.children.length === 1); return e ? { cab: trecho(e, /^Observação:/), todo: tight(e) } : null; })(),
      dose: f(/^Dose:/), via: f(/^Via:/), carencia: f(/^Carência:/), marca: f(/\(frasco/), folhas: fl.map(item) }; });
  return o;
}, ALTURA_MAX);
// páginas altas: viewport = altura do documento (no máximo 5200 px), cabeçalho e barra escondidos (o motor rola a imagem por trás das barras reais)
async function alta(nome) {
  const estilo = await p.addStyleTag({ content: "header,nav.mob-nav{visibility:hidden!important}" });
  const H0 = await p.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body.scrollHeight));
  await p.setViewportSize({ width: 390, height: Math.max(844, Math.min(H0, ALTURA_MAX)) }); await esp(1100); await topo();
  const m = await coletar(); await p.screenshot({ path: OUT + nome + ".png" });
  await p.setViewportSize({ width: 390, height: 844 }); await esp(500);
  await estilo.evaluate((e) => e.remove()); await topo();
  mapa[nome] = m; log("alta", nome, "docH", m.docH, "real", m.docHReal);
}
const vp = async (nome) => { await p.screenshot({ path: OUT + nome + ".png" }); mapa[nome] = await coletar(); log("vp", nome); };
const abrirItem = async (re) => { await p.evaluate((s) => [...document.querySelectorAll("button")].find((x) => new RegExp(s).test(x.innerText.trim())).click(), re); };
const voltar = async () => { await p.getByRole("button", { name: "Voltar" }).first().click(); await esp(1300); await topo(); };
const reabrir = async () => { if (!(await coletar()).menuItens.length) { await p.locator("button[aria-expanded]", { hasText: /^Sanidade/ }).first().click(); await esp(900); log("reabri Sanidade"); } };

await fetch(API + "/__reset");
// ═══ 1) Menu: placas recolhidas (abertura 3D) e Menu com Sanidade aberta ═══
const COLAPSADAS = ["protocolos-restrito", "reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro", "modulos", "administracao", "app"];
await p.goto(APP + "/app/menu", { waitUntil: "networkidle" }); await esp(1500);
await p.evaluate((c) => localStorage.setItem("mob_menu_secoes_colapsadas", JSON.stringify(c)), COLAPSADAS);
await p.reload({ waitUntil: "networkidle" }); await esp(1500);
const heads = await p.$$eval("button[aria-expanded]", (bs) => bs.map((b) => { const rr = (b.parentElement || b).getBoundingClientRect(); return { txt: b.innerText.replace(/\s+/g, " ").trim(), px: rr.x, py: rr.y, pw: rr.width, ph: rr.height }; }));
const nomes = ["reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro"];
for (let i = 0; i < 6; i++) { const h = heads[i]; await p.screenshot({ path: OUT + `placa_${nomes[i]}.png`, clip: { x: h.px, y: h.py, width: h.pw, height: h.ph } }); }
mapa.heads = heads; mapa.placasNomes = nomes;
await p.locator("button[aria-expanded]", { hasText: /^Sanidade/ }).first().click(); await esp(900);
await p.screenshot({ path: OUT + "menu_sanid.png" });
{ const r = await p.locator("button[aria-expanded]", { hasText: /^Sanidade/ }).first().evaluate((b) => { const r = b.parentElement.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }); await p.screenshot({ path: OUT + "placa_sanidade_aberta.png", clip: { x: r.x, y: r.y, width: r.w, height: r.h } }); mapa.sanidCard = r; }
mapa.menu_sanid = await coletar(); log("menu_sanid", JSON.stringify(mapa.menu_sanid.menuItens.map((i) => [i.txt.slice(0, 26), Math.round(i.y)])), JSON.stringify(mapa.menu_sanid.heads.map((h) => [h.txt.slice(0, 12), h.aberta, Math.round(h.pai.y), Math.round(h.pai.h)])));

// ═══ 2) Vacinas e exames: a lista (atrasado, hoje, amanhã) ═══
await abrirItem("^Vacinas e exames"); await p.waitForSelector("text=Atrasados", { timeout: 15000 }); await p.waitForSelector("text=guardado no celular", { timeout: 15000 }); await esp(1500); await topo();
await p.screenshot({ path: OUT + "vl_vp.png" }); mapa.vl_vp = await coletar();
await alta("vl0");
// ═══ 3) O dia de hoje (Vacina brucelose B19): preparação → quem aplica → como aplicar → tronco ═══
await p.getByRole("button", { name: /^Abrir Vacina brucelose B19/ }).click(); await p.waitForSelector("text=Preparação antes do curral", { timeout: 15000 }); await esp(1500); await topo();
await p.screenshot({ path: OUT + "ex_vp.png" }); mapa.ex_vp = await coletar();
await alta("ex0");                                                            // preparação: nada conferido
const caixas = p.locator('label.mob-san-linha input[type=checkbox]');
const nCx = (await caixas.count()) - 1; log("itens da preparação", nCx); // o último checkbox é o "Estou ciente" do cartão de ciência (some quando tudo está conferido)
await caixas.nth(0).check(); await esp(400); await topo(); await alta("ex0a");  // 1 conferido
await caixas.nth(1).check(); await esp(400); await topo(); await alta("ex0b");  // 2 conferidos
for (let i = 2; i < nCx; i++) await caixas.nth(i).check(); await esp(500); await topo();
await alta("ex1");                                                            // tudo conferido: "Tudo conferido, começar"
await p.getByRole("button", { name: "Tudo conferido, começar" }).click(); await p.waitForSelector("text=Quem está aplicando", { timeout: 8000 }); await esp(900); await topo();
await alta("ex2");                                                            // quem está aplicando (nada escolhido)
await p.locator("button.mob-san-chip", { hasText: "Dra. Ana" }).click(); await esp(600); await topo();
await alta("ex3");                                                            // Dra. Ana escolhida
await p.getByRole("button", { name: "Continuar", exact: true }).click(); await p.waitForSelector("text=Como vai aplicar?", { timeout: 8000 }); await esp(900); await topo();
await alta("ex4");                                                            // Como vai aplicar? Tronco / Grupo
await p.locator("button.mob-san-chip", { hasText: /^Tronco/ }).click(); await p.waitForSelector("text=APLICADO", { timeout: 8000 }); await esp(1200); await topo();
await alta("ex5");                                                            // Tronco: Animal 1 de 5
await p.getByRole("button", { name: /APLICADO · PRÓXIMO/ }).click(); await p.waitForSelector("text=Animal 1 de 4", { timeout: 8000 }); await esp(1800); await topo();
await alta("ex6");                                                            // depois do 1º aplicado (Animal 1 de 4; "Últimos registrados")
await p.getByRole("button", { name: /APLICADO · PRÓXIMO/ }).click(); await p.waitForSelector("text=Animal 1 de 3", { timeout: 8000 }); await esp(1800); await topo();
await alta("ex6b");                                                           // 2º aplicado (Animal 1 de 3)
await p.getByRole("button", { name: /^Não aplicar/ }).first().click(); await p.waitForSelector("text=Doente ou em tratamento", { timeout: 8000 }); await esp(1000);
await p.screenshot({ path: OUT + "na_vp.png" }); mapa.na_vp = await coletar(); log("vp na_vp");  // gaveta "Não aplicar em …" (diálogo fixo: captura da tela)
await p.getByRole("button", { name: "Doente ou em tratamento" }).click(); await p.waitForSelector("text=Animal 1 de 2", { timeout: 8000 }); await esp(1500); await topo();
await alta("ex7");                                                            // 1 animal em "Não aplicados"; aviso de saiu do rebanho no topo
// sem sinal: a API falha; "Atualizar" cai na cópia guardada no celular e a tela diz isso
SEM_SINAL = true;
await p.getByRole("button", { name: /Atualizar/ }).first().click(); await p.waitForSelector("text=Sem sinal: usando o dia guardado", { timeout: 15000 }); await esp(1500); await topo();
await topo(); await vp("ex8");                                                // "Sem sinal: usando o dia guardado neste celular (…)" — captura da TELA (o aviso laranja de conexão do app empurra o conteúdo; cabeçalho e aviso são os reais)
SEM_SINAL = false;
await p.getByRole("button", { name: "Tentar novamente" }).first().click().catch(() => {}); await p.waitForFunction(() => !/Sem conexão com o servidor/.test(document.body.innerText), null, { timeout: 20000 }).catch(() => log("banner de offline persiste")); await esp(800);
// volta à lista e ao Menu
await voltar(); await p.waitForSelector("text=Hoje e amanhã", { timeout: 15000 }); await esp(1200); await topo();
await alta("vl1");                                                            // a lista depois do dia (volta com sinal)
await voltar(); await reabrir();
// ═══ 4) Histórico de tratamentos e vacinas ═══
await abrirItem("^Histórico de tratamentos e vacinas"); await p.waitForSelector("text=Nº", { timeout: 15000 }); await esp(1800); await topo();
await p.screenshot({ path: OUT + "hs_vp.png" }); mapa.hs_vp = await coletar();
await alta("hs0");
await p.getByRole("button", { name: "Lote(s)", exact: true }).click(); await esp(1500); await topo();
await alta("hs1");
await p.locator("button.lote-pill", { hasText: /^01 - Alta/ }).click(); await esp(900);
await p.locator("button.lote-pill", { hasText: /^02 - Média/ }).click(); await p.waitForSelector("section[aria-label^=Lote]", { timeout: 15000 }); await esp(1500); await topo();
await alta("hs2");                                                            // lotes 01 e 02: blocos por lote
// marcar "Curado" no primeiro curativo do bloco 01
await p.locator(".mob-card", { hasText: /^Nº \d+Curativo/ }).first().getByRole("button", { name: /Marcar curado/ }).click(); await p.waitForSelector("text=marcado como curado", { timeout: 8000 }); await esp(1800); await topo();
await alta("hs3");
// ═══ 5) Remédios por Doença ═══
await voltar(); await reabrir();
await abrirItem("^Remédios por Doença"); await p.waitForSelector("text=Escolha uma doença", { timeout: 15000 }); await esp(1500); await topo();
await p.screenshot({ path: OUT + "rm_vp.png" }); mapa.rm_vp = await coletar();
await alta("rm0");
await p.selectOption("#remedios-doenca", { label: "Mastite clínica" }); await p.waitForSelector("text=1ª escolha", { timeout: 15000 }); await esp(1800); await topo();
await alta("rm1");
fs.writeFileSync(OUT + "mapa.json", JSON.stringify(mapa, null, 1));
await br.close(); log("ok");
