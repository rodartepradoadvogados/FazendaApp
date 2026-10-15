"use strict";
/* CowData · Lançar no financeiro — lógica do mockup (sem dependências). */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ic = (n, c = "") => `<svg class="ic ${c}" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const say = (m) => { const l = $("#live"); l.textContent = ""; setTimeout(() => (l.textContent = m), 40); };
const LS = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }, del(k) { try { localStorage.removeItem(k); } catch (e) {} } };

/* ───────────────────────── estado ───────────────────────── */
const novoItem = () => ({ produto: "", qtd: "", unit: "", total: "", edit: "unit", conta: null, sug: "", editConta: false, vale: false, valeFunc: "", valeOk: false });
const novoForm = (tipo) => ({
  fornecedor: "", novoForn: false, itens: [novoItem()], emissao: TODAY, venc: "", vencTocado: false, comp: "",
  pago: false, pagoData: TODAY, banco: 0, forma: "Pix", valorPago: "", valorPagoTocado: false,
  parc: false, nParc: 3, parcelas: [], parcEdit: false,
  doc: "", tipoDoc: "Nota fiscal", anexos: [], lendo: false,
  natureza: "", etiqueta: "", centro: "Pecuária Leiteira", resp: "Administrador", os: "", boleto: "", pedido: "",
  desc: "", acr: "", ajustes: false, classificarDepois: false, criarBem: true, vidaUtil: "10", residual: "", entregue: true, prevista: "", comprovante: "", dupOk: false,
  lido: {}, sug: {},
  leite: { mes: "2026-09", litros: "", preco: "2,85", retPct: "1,7", retTocado: false },
});
const novoLote = () => ({ forn: "", banco: 0, centro: "Pecuária Leiteira", modo: "unico", venc: "", nParc: 2, pagoData: TODAY, notas: [novaNota()] });
const novaNota = () => ({ doc: "", sem: false, emissao: TODAY, item: "", conta: "", valor: "" });
const novoSemen = () => ({ touro: "", doses: "", preco: "", forn: "Central de Sêmen Exemplo", emissao: TODAY, venc: addDays(TODAY, 30), doc: "" });

const S = {
  view: "lancar", tipo: "despesa", sub: { despesa: "uma", receita: "leite" },
  F: { despesa: novoForm("despesa"), receita: novoForm("receita") },
  lote: novoLote(), semen: novoSemen(),
  msg: null, msgC: null, fcontas: "abertas", perfil: "dono", sessao: [], ultimo: null, pedidoAberto: false, novoId: null,
  faturas: [{ id: "FT-2026-0003", forn: "Agropecuária Boa Safra", st: "Aberta", n: 2, v: 18350, venc: "2026-11-10" }, { id: "FT-2026-0002", forn: "Nutrimix Nutrição Animal", st: "Paga", n: 1, v: 3375, venc: "2026-10-08" }],
};
const F_ = () => S.F[S.tipo];
const ROT = {
  despesa: { forn: "Fornecedor", fornP: "Digite ou escolha o fornecedor", conta: "Contas a pagar", contaV: "a pagar", pago: "Já paguei", pagoD: "dar baixa agora, informando banco e forma", aberto: "Deixar a pagar", abertoD: "entra em Contas a pagar", data: "pagamento", sinal: -1, view: "pagar" },
  receita: { forn: "Cliente", fornP: "Digite ou escolha o cliente", conta: "Contas a receber", contaV: "a receber", pago: "Já recebi", pagoD: "dar baixa agora, informando banco e forma", aberto: "Deixar a receber", abertoD: "entra em Contas a receber", data: "recebimento", sinal: 1, view: "receber" },
};
const estocavel = (c) => !!c && ["3.01.01", "3.01.02.01", "3.01.03.01", "3.01.04.01", "3.04.02", "3.04.05"].some((p) => c.startsWith(p));
const catalogo = (tipo) => (tipo === "despesa" ? ITENS : ITENS_REC);
const fornDe = (tipo) => (tipo === "despesa" ? FORN : FORN_REC);
const contasDe = (tipo) => (tipo === "despesa" ? CONTAS_DESP : CONTAS_REC);

/* ───────────────────────── cálculo ───────────────────────── */
function itemTotal(it) {
  if (it.edit === "total") return parseBR(it.total);
  if (it.unit === "") return parseBR(it.total);
  const q = parseBR(it.qtd), info = itemInfo(S.tipo, it.produto);
  if (!q) return info && info.estoque ? 0 : parseBR(it.unit);   // item de estoque exige quantidade: nada de "1" implícito
  return r2(q * parseBR(it.unit));
}
function calc(F) {
  let bruto = 0; F.itens.forEach((it) => (bruto += itemTotal(it)));
  const desc = parseBR(F.desc), acr = parseBR(F.acr);
  return { bruto: r2(bruto), desc, acr, liq: r2(bruto - desc + acr) };
}
function compDe(F) { return F.comp || F.emissao.slice(0, 7); }
function gerarParcelas(F) {
  const n = Math.max(2, Math.min(36, +F.nParc || 2)), { liq } = calc(F);
  const base = Math.floor((liq / n) * 100) / 100, first = F.venc || addDays(F.emissao, 30);
  F.parcelas = Array.from({ length: n }, (_, i) => ({ venc: addMonths(first, i), valor: i === n - 1 ? r2(liq - base * (n - 1)) : base, boleto: "", paga: false }));
}
function bucket(iso) {
  const d = diffDays(iso, TODAY);
  return d < 0 ? "Vencidas" : d <= 7 ? "Até 7 dias" : d <= 14 ? "De 8 a 14 dias" : "Depois de 14 dias";
}
const itemInfo = (tipo, nome) => catalogo(tipo).find((i) => i.nome === nome);
function faltas(F, tipo, sub) {
  const f = [], c = calc(F);
  if (!F.fornecedor.trim() && sub !== "semen") f.push(ROT[tipo].forn.toLowerCase());
  if (sub === "leite") { if (!(parseBR(F.leite.litros) > 0)) f.push("litros"); }
  else { if (!F.itens.some((i) => i.produto.trim())) f.push("item"); if (c.liq <= 0) f.push("valor"); }
  if (!F.pago && !F.venc) f.push("vencimento");
  return f;
}

/* ───────────────────────── validação ───────────────────────── */
const mesFechado = (iso) => (iso ? MES_FECHADO.find((m) => iso.startsWith(m)) : null);
function validar(tipo, sub) {
  const F = S.F[tipo], R = ROT[tipo], E = [], c = calc(F);
  const add = (id, msg) => E.push({ id, msg });
  if (!F.fornecedor.trim()) add("f-forn", `Informe o ${R.forn.toLowerCase()}.`);
  if (sub === "leite") {
    if (!(parseBR(F.leite.litros) > 0)) add("f-litros", "Informe os litros entregues.");
    if (!(parseBR(F.leite.preco) > 0)) add("f-preco", "Informe o preço por litro.");
  } else {
    F.itens.forEach((it, i) => {
      const n = i + 1, info = itemInfo(tipo, it.produto);
      if (!it.produto.trim()) add(`f-it${i}-prod`, `Descreva o item ${n}.`);
      else if (it.qtd !== "" && !(parseBR(it.qtd) > 0)) add(`f-it${i}-qtd`, `A quantidade do item ${n} precisa ser maior que zero.`);
      else if (info && info.estoque && !(parseBR(it.qtd) > 0)) add(`f-it${i}-qtd`, `Informe a quantidade do item ${n} (${info.un}): é ela que dá entrada no estoque.`);
      else if (!(itemTotal(it) > 0)) add(`f-it${i}-total`, `Informe o valor do item ${n}.`);
      if (it.produto.trim() && !it.conta && !F.classificarDepois) add(`f-it${i}-conta`, `Escolha para onde o item ${n} vai (ou marque “classificar depois”).`);
      if (it.vale) {
        if (!it.valeFunc) add(`f-it${i}-func`, `Escolha o funcionário do vale (item ${n}).`);
        else { const v = valeInfo(it); if (v.acima && !it.valeOk) add(`f-it${i}-vale`, `Este vale passa do limite de 40% do salário (${BRL(v.limite)}) de ${it.valeFunc}. Reduza para ${BRL(Math.max(0, v.limite - v.ja))} ${S.perfil === "dono" ? "ou marque “lançar mesmo assim”" : "ou peça ao dono para autorizar"}.`); }
      }
    });
  }
  const mc = mesFechado(F.emissao);
  if (mc) add("f-emissao", `${mesLong(mc)} está fechado: não dá para lançar com emissão nele. Use uma data a partir de 01/09/2026 ou peça ao dono para reabrir o mês.`);
  if (!F.emissao) add("f-emissao", "Informe a data de emissão.");
  if (sub !== "leite" && F.comp && mesFechado(F.comp + "-01")) add("f-comp", `O mês do gasto (competência) ${mesLong(F.comp)} está fechado.`);
  if (sub === "leite" && mesFechado(F.leite.mes + "-01")) add("f-mes", `O mês de referência do leite (${mesLong(F.leite.mes)}) está fechado.`);
  if (!F.pago && !F.venc) add("f-venc", "Informe o vencimento.");
  if (!F.pago && F.venc && F.emissao && F.venc < F.emissao) add("f-venc", `O vencimento (${fmtD(F.venc)}) não pode ser antes da emissão (${fmtD(F.emissao)}).`);
  if (c.desc > c.bruto + 0.005) add("f-desc", `O desconto (${BRL(c.desc)}) é maior que a soma dos itens (${BRL(c.bruto)}).`);
  if (c.liq > 1e9) add("f-forn", "Confira os valores: o total passa de R$ 1 bilhão.");
  if (fornPendente(tipo) && sub !== "semen") add("f-forn", `Confirme que “${F.fornecedor.trim()}” é ${tipo === "despesa" ? "um fornecedor novo" : "um cliente novo"} ou escolha um da lista.`);
  if (tipo === "despesa" && F.criarBem && F.itens.some((i) => i.conta && naturezaAuto(i.conta) === "INVESTIMENTO") && !(parseInt(F.vidaUtil, 10) > 0 && /^\d+$/.test(String(F.vidaUtil).trim()))) add("f-vida", "Informe a vida útil do bem em anos (número inteiro maior que zero).");
  if (F.pago) {
    if (!F.pagoData) add("f-pagodata", `Informe a data do ${R.data}.`);
    else if (mesFechado(F.pagoData)) add("f-pagodata", `A data do ${R.data} (${fmtD(F.pagoData)}) cai em ${mesLong(mesFechado(F.pagoData))}, que está fechado.`);
    else if (F.emissao && F.pagoData < F.emissao) add("f-pagodata", `A data do ${R.data} (${fmtD(F.pagoData)}) é anterior à emissão (${fmtD(F.emissao)}).`);
    if (!(parseBR(F.valorPago) > 0)) add("f-valorpago", "Informe o valor efetivamente pago.");
  }
  if (F.parc && !F.pago) {
    const soma = r2(F.parcelas.reduce((s, p) => s + parseBR(p.valor), 0));
    if (Math.abs(soma - c.liq) > 0.01) add("parcs", `A soma das parcelas (${BRL(soma)}) difere do valor da nota (${BRL(c.liq)}).`);
  }
  return E;
}
function valeInfo(it) {
  const f = FUNCIONARIOS.find((x) => x.nome === it.valeFunc); if (!f) return { acima: false, limite: 0, ja: 0, salario: 0 };
  const limite = r2(f.salario * 0.4), v = itemTotal(it);
  return { salario: f.salario, limite, ja: f.vales, este: v, acima: f.vales + v > limite + 0.001 };
}
function achaDuplicado(F, tipo, sub) {
  if (!F.fornecedor.trim()) return null;
  if (sub === "leite") return LANC.find((l) => l.tipo === "receita" && l.forn === F.fornecedor && l.mes === F.leite.mes) || null;
  const doc = (F.doc || "").trim().toLowerCase(), { liq } = calc(F);
  return LANC.find((l) => l.tipo === tipo && l.forn === F.fornecedor && (doc ? (l.doc || "").trim().toLowerCase() === doc : Math.abs(l.valor - liq) < 0.01 && !l.parcela)) || null;
}

/* ───────────────────────── casca / navegação ───────────────────────── */
function go(view, o = {}) {
  S.view = view; if (o.tipo) S.tipo = o.tipo; if (view === "pagar") S.tipo = "despesa"; if (view === "receber") S.tipo = "receita";
  render(); if (!o.noFocus) { const m = $("#main"); m.focus({ preventScroll: true }); m.scrollTop = 0; window.scrollTo(0, 0); }
}
function paintNav() {
  const cur = S.view;
  ["lancar", "pagar", "receber"].forEach((v) => $$(`[data-nav="${v}"]`).forEach((a) => (cur === v ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"))));
}
function render() {
  LS.set("cowdata:mock:aba", JSON.stringify({ tipo: S.tipo, sub: S.sub }));
  paintNav();
  $("#view").innerHTML = S.view === "lancar" ? tplLancar() : tplContas(S.view === "pagar" ? "despesa" : "receita");
  if (S.view === "lancar") initLancar();
}
function initLancar() {
  const t = S.tipo, sub = S.sub[t];
  if (t === "despesa" && sub === "lote") paintLote();
  else if (t === "despesa" && sub === "semen") paintSemen();
  else if (t === "despesa" && sub === "faturas") { /* só leitura */ }
  else { paintRail(); paintFoot(); paintTotais(); paintDif(); paintVencHint(); }
  paintFornAviso();
  const tabSel = $('.tabs [aria-selected="true"]'); if (tabSel && tabSel.scrollIntoView) tabSel.scrollIntoView({ block: "nearest", inline: "center" });
}

/* ───────────────────────── templates: página ───────────────────────── */
const MODULOS = ["Alimentação", "Animais", "Balanço de estoque", "Financeiro", "Produção", "Reprodutivo", "Sanitário", "Excluir lançamento"];
function tplLancar() {
  const t = S.tipo, sub = S.sub[t];
  const subs = t === "despesa"
    ? [["uma", "Uma conta"], ["lote", "Lote de notas"], ["faturas", "Faturas"], ["semen", "Compra de sêmen"]]
    : [["leite", "Venda de leite"], ["outra", "Outra receita"]];
  return `
  <nav class="modtabs" aria-label="Tipos de lançamento">${MODULOS.map((m) => (m === "Financeiro" ? `<span class="on" aria-current="page">${m}</span>` : `<button type="button" aria-disabled="true" tabindex="-1">${m}</button>`)).join("")}</nav>
  <div class="crumb">Lançar › Financeiro › ${t === "despesa" ? "Despesa" : "Receita"}</div>
  <div class="page">
    <div class="pagehead"><div><h1 tabindex="-1">Lançar no financeiro</h1>
      <p>Para gravar basta ${t === "despesa" ? "o fornecedor, o item, o valor e o vencimento" : "o cliente, o item, o valor e o vencimento"}. O resto o sistema sugere pelo histórico — e você confere o efeito ao lado antes de salvar.</p></div></div>
    <div class="tabs" role="tablist" aria-label="Despesa ou receita" data-tabs="tipo">
      <button role="tab" id="tab-despesa" aria-selected="${t === "despesa"}" tabindex="${t === "despesa" ? 0 : -1}" data-act="tipo" data-v="despesa">Despesa<small>vira conta a pagar</small></button>
      <button role="tab" id="tab-receita" aria-selected="${t === "receita"}" tabindex="${t === "receita" ? 0 : -1}" data-act="tipo" data-v="receita">Receita<small>vira conta a receber</small></button>
    </div>
    <div class="tabs sub" role="tablist" aria-label="Forma de lançar" data-tabs="sub">
      ${subs.map(([id, l]) => `<button role="tab" id="sub-${id}" aria-selected="${sub === id}" tabindex="${sub === id ? 0 : -1}" data-act="sub" data-v="${id}">${l}</button>`).join("")}
    </div>
    <div id="body">${tplBody()}</div>
    ${tplSessao()}
  </div>`;
}
function tplBody() {
  const t = S.tipo, sub = S.sub[t];
  if (t === "despesa" && sub === "lote") return tplLote();
  if (t === "despesa" && sub === "faturas") return tplFaturas();
  if (t === "despesa" && sub === "semen") return tplSemen();
  return tplConta(t, sub);
}
function tplTopMsg() {
  const m = S.msg; if (!m) return "";
  if (m.kind === "err") return `<div class="errsum" tabindex="-1" id="errsum"><h2>${ic("alert")} Falta ${m.erros.length === 1 ? "1 coisa" : m.erros.length + " coisas"} para salvar</h2>
    <ul>${m.erros.map((e) => `<li><a href="#${e.id}" data-focus="${e.id}">${esc(e.msg)}</a></li>`).join("")}</ul></div>`;
  if (m.kind === "draft") return `<div class="banner" role="status">${ic("info")} <span>Há um rascunho de ${esc(m.quando)} nesta tela. <span class="tiny">Anexos não são guardados.</span></span>
    <span class="row"><button type="button" class="btn btn-sec btn-sm" data-act="retomar">Retomar rascunho</button><button type="button" class="btn btn-ghost btn-sm" data-act="descartar">Descartar</button></span></div>`;
  if (m.kind === "done") {
    const v = m.vinculo;
    return `<div class="done" role="status" tabindex="-1" id="donecard"><h2>${ic("check")} ${esc(m.titulo)}</h2>
      <p>${m.resumo}</p>
      ${m.avisos.map((a) => `<div class="note warn">${ic("alert")}<div>${a}</div></div>`).join("")}
      ${v && v.estado === "aberto" ? `<div class="note info">${ic("info")}<div><b>Esta conta costuma pagar vacina, exame ou serviço reprodutivo.</b> Quer vincular a um evento recente?
        <div class="row"><button type="button" class="btn btn-sec btn-sm" data-act="vincular" data-v="Vacina aftosa · 12/10 · 400 doses">Vacina aftosa · 12/10 · 400 doses</button>
        <button type="button" class="btn btn-sec btn-sm" data-act="vincular" data-v="Tratamento de mastite · vaca 0412 · 09/10">Mastite · vaca 0412 · 09/10</button>
        <button type="button" class="btn btn-ghost btn-sm" data-act="vincular" data-v="">Não se aplica</button></div></div></div>` : ""}
      ${v && v.estado === "feito" ? `<div class="note ok">${ic("check")}<div>${esc(v.texto)}</div></div>` : ""}
      <div class="row"><a class="btn btn-sec btn-sm" href="#${m.view}" data-nav="${m.view}" data-new="${esc(m.id)}" data-fconta="${m.fconta || "abertas"}">Ver em ${m.view === "pagar" ? "Contas a pagar" : "Contas a receber"}${m.fconta === "pagas" ? (m.view === "pagar" ? " › Pagas" : " › Recebidas") : ""} ${ic("arrow")}</a>
        ${m.nao_igual ? "" : `<button type="button" class="btn btn-sec btn-sm" data-act="igual">Lançar outro igual</button>`}
        <button type="button" class="btn btn-ghost btn-sm" data-act="desfazer" data-v="${esc(m.id)}">${ic("undo")} Desfazer</button></div></div>`;
  }
  return "";
}
function paintTop() { const e = $("#topmsg"); if (e) e.innerHTML = tplTopMsg(); }

/* pedidos em aberto (cartão acima do formulário) */
function tplPedidos(tipo) {
  const P = PEDIDOS[tipo]; if (!P.length || S.F[tipo].fornecedor) return "";
  return `<details class="pedidos" ${S.pedidoAberto ? "open" : ""} data-pedidos><summary>${ic("cart")} ${P.length} pedidos aguardando a nota <span class="st info">compra</span></summary>
    <div class="pl">${P.map((p) => `<div class="p"><span><b>${esc(p.forn)}</b> · ${esc(p.item)} · ${p.qtd} un · previsto ${fmtD(p.previsto)}</span><b class="num">${BRL(p.total)}</b>
      <button type="button" class="btn btn-sec btn-sm" data-act="pedido" data-v="${p.id}">Lançar a nota deste pedido</button></div>`).join("")}</div></details>`;
}

/* ───────────────────────── templates: conta (despesa/receita) ───────────────────────── */
function tplConta(tipo, sub) {
  const F = S.F[tipo], R = ROT[tipo], leite = sub === "leite";
  const lidoTag = (k) => (F.lido[k] ? `<span class="lido">lido da nota</span>` : "");
  return `
  <div id="topmsg">${tplTopMsg()}</div>
  <div id="pedidos">${tplPedidos(tipo)}</div>
  <form id="frm" class="lay" novalidate aria-label="Lançar ${tipo === "despesa" ? "despesa" : "receita"}">
    <div class="sheet">
      <section class="sec" aria-labelledby="h-quem">
        <h2 id="h-quem">${leite ? "Cliente e entrega de leite" : R.forn + " e item"}</h2>
        <div class="fld">
          <label for="f-forn">${R.forn} ${lidoTag("fornecedor")} <span id="sug-forn"></span></label>
          <div class="row" style="flex-wrap:nowrap;align-items:stretch">
            <div class="combo grow" data-combo="forn"><input class="in" id="f-forn" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="lb-forn" autocomplete="off" placeholder="${R.fornP}" value="${esc(F.fornecedor)}"><ul tabindex="-1" id="lb-forn" role="listbox" hidden></ul></div>
            <button type="button" class="btn btn-sec" data-act="novo-forn">${ic("plus")}Novo</button>
          </div>
          <div class="chips mt" role="group" aria-label="${R.forn}s recentes">${RECENTES[tipo].map((n) => `<button type="button" class="chip" data-act="pick-forn" data-v="${esc(n)}" aria-pressed="${F.fornecedor === n}">${esc(n)}</button>`).join("")}</div>
          <div id="forn-aviso" class="mt"></div>
          <div class="err" id="e-forn" hidden></div>
        </div>
        ${tipo === "receita" && sub === "outra" ? `<div class="note info mt">${ic("info")}<div>Venda de <b>animais</b> tem tela própria em Animais › Vender animal (dá baixa no rebanho e pede GTA). Aqui entram as outras receitas.</div></div>` : ""}
        <div class="mt2" id="itens">${leite ? tplLeite() : tplItens()}</div>
      </section>

      <section class="sec" aria-labelledby="h-datas" id="sec-datas"><h2 id="h-datas">Datas</h2><div id="datas">${tplDatas()}</div></section>
      <section class="sec" aria-labelledby="h-pag" id="sec-pag"><h2 id="h-pag">${tipo === "despesa" ? "Pagamento" : "Recebimento"}</h2><div id="pag">${tplPag()}</div></section>
      <section class="sec" aria-labelledby="h-doc"><h2 id="h-doc">Documento</h2><div id="doc">${tplDoc()}</div></section>
      ${tplAvancado()}
    </div>
    <aside class="rail" id="rail" aria-label="Efeito do lançamento"></aside>
    <div class="actionbar" id="foot"></div>
  </form>`;
}

function tplItens() {
  const F = F_();
  return `<div class="ledger">
    <div class="lhead" aria-hidden="true"><span>Item</span><span class="r">Qtd</span><span class="r">Unitário</span><span class="r">Total</span><span></span></div>
    ${F.itens.map((_, i) => tplItem(i)).join("")}
  </div>
  <div class="row mt"><button type="button" class="btn btn-ghost" data-act="add-item">${ic("plus")} Adicionar outro item da mesma nota</button></div>
  <div class="totais" id="totais"></div>`;
}
function tplItem(i) {
  const F = F_(), it = F.itens[i], n = i + 1, un = itemInfo(S.tipo, it.produto)?.un;
  return `<div class="item" data-i="${i}">
    <div class="c-prod fld"><span class="cell-l" aria-hidden="true">Item</span>
      <div class="combo" data-combo="prod" data-i="${i}"><input class="in" id="f-it${i}-prod" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="lb-prod-${i}" autocomplete="off" aria-label="Produto ou serviço, item ${n}" placeholder="O que foi ${S.tipo === "despesa" ? "comprado ou contratado" : "vendido"}?" value="${esc(it.produto)}"><ul tabindex="-1" id="lb-prod-${i}" role="listbox" hidden></ul></div></div>
    <div class="fld"><span class="cell-l" aria-hidden="true">Qtd${un ? " (" + un + ")" : ""}</span><input class="in r" id="f-it${i}-qtd" data-b="itens.${i}.qtd" inputmode="decimal" autocomplete="off" aria-label="Quantidade do item ${n}${un ? " em " + un : ""}" placeholder="1" value="${esc(it.qtd)}"></div>
    <div class="fld"><span class="cell-l" aria-hidden="true">Unitário</span><div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="f-it${i}-unit" data-b="itens.${i}.unit" data-m inputmode="decimal" autocomplete="off" aria-label="Valor unitário do item ${n}" placeholder="0,00" value="${esc(it.unit)}"></div></div>
    <div class="fld"><span class="cell-l" aria-hidden="true">Total</span><div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="f-it${i}-total" data-b="itens.${i}.total" data-m inputmode="decimal" autocomplete="off" aria-label="Valor total do item ${n}" placeholder="0,00" value="${esc(it.total)}"></div></div>
    ${F.itens.length > 1 ? `<button type="button" class="x" data-act="del-item" data-i="${i}" aria-label="Remover o item ${n}">${ic("trash")}</button>` : `<span></span>`}
    <div class="meta" id="meta-${i}">${tplMeta(i)}</div>
    <div class="err" id="e-it${i}" hidden style="grid-column:1/-1"></div>
  </div>`;
}
function tplMeta(i) {
  const F = F_(), it = F.itens[i], tipo = S.tipo, bits = [];
  const info = itemInfo(tipo, it.produto);
  if (it.editConta) {
    bits.push(`<div class="combo" data-combo="conta" data-i="${i}" style="min-width:min(100%,360px);flex:1"><input class="in" id="f-it${i}-conta" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="lb-conta-${i}" autocomplete="off" aria-label="Para onde vai o item ${i + 1} (busque por nome, código ou grupo)" placeholder="Busque: comida, energia, vacina, 3.04…"><ul tabindex="-1" id="lb-conta-${i}" role="listbox" hidden></ul></div>
      <button type="button" class="btn btn-ghost btn-sm" data-act="fecha-conta" data-i="${i}">Cancelar</button>`);
  } else if (it.conta) {
    bits.push(`<span class="dest" id="f-it${i}-conta" tabindex="-1">Vai para <b>${esc(grupoCurto(it.conta))}</b> · ${esc(CONTA_NOME[it.conta])} <code>${it.conta}</code></span>
      <button type="button" class="link" data-act="edit-conta" data-i="${i}">alterar</button>${it.sug ? `<span class="sug">${esc(it.sug)}</span>` : ""}`);
  } else if (it.produto.trim()) {
    bits.push(`<button type="button" class="btn btn-sec btn-sm" id="f-it${i}-conta" data-act="edit-conta" data-i="${i}">Escolher para onde vai</button>`);
  }
  const up = info && info.estoque ? ultimoPreco(it.produto, tipo) : null, uni = parseBR(it.unit);
  if (up && uni) { const d = (uni / up.unit - 1) * 100; bits.push(`<span>Último preço <b>${BRL(up.unit)}</b> (${fmtD(up.data)}) ${Math.abs(d) < 0.5 ? "· igual" : d > 0 ? `· <b style="color:${d > 15 ? "var(--warn)" : "inherit"}">${d.toFixed(0)}% acima</b>` : `· ${Math.abs(d).toFixed(0)}% abaixo`}</span>`); }
  else if (up) bits.push(`<span>Último preço <b>${BRL(up.unit)}</b> em ${fmtD(up.data)}</span>`);
  if (it.produto.trim()) {
    if (info?.estoque) bits.push(`<span>${tipo === "despesa" ? "Entra" : "Sai"} no estoque</span>`);
    else if (info?.servico || info?.bem) bits.push(`<span>${info.bem ? "Bem" : "Serviço"} · não mexe no estoque</span>`);
    else if (!info) bits.push(tipo === "despesa" && estocavel(it.conta) ? `<span class="st warn">${ic("alert")} Fora do cadastro — grava sem baixa de estoque</span>` : `<span>Item avulso · não mexe no estoque</span>`);
  }
  let vale = "";
  if (tipo === "despesa" && it.conta && it.conta.startsWith("3.07")) vale += `<label class="chk" style="flex-basis:100%"><input type="checkbox" data-act="criar-bem" data-i="${i}" ${F.criarBem ? "checked" : ""}><span><b>Cadastrar como bem no Patrimônio</b><span class="hint">Para depreciar mês a mês. Sem o bem, o valor sai do resultado e nunca depreciará.</span></span></label>${F.criarBem ? `<div class="g2" style="flex-basis:100%"><div class="fld"><label for="f-vida">Vida útil (anos)</label><input class="in r" id="f-vida" data-b="vidaUtil" inputmode="numeric" value="${esc(F.vidaUtil)}"></div><div class="fld"><label for="f-resid">Valor residual <span class="opt">(opcional)</span></label><div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="f-resid" data-b="residual" data-m inputmode="decimal" value="${esc(F.residual)}"></div></div></div>` : ""}`;
  if (tipo === "despesa" && it.conta && it.conta.startsWith("3.03.01")) {
    vale = `<label class="chk" style="flex-basis:100%"><input type="checkbox" data-act="vale" data-i="${i}" ${it.vale ? "checked" : ""}><span><b>É vale ou adiantamento de funcionário</b><span class="hint">Fica como vale a receber e não entra no resultado.</span></span></label>`;
    if (it.vale) {
      const v = valeInfo(it);
      vale += `<div class="vale" style="flex-basis:100%"><div class="fld"><label for="f-it${i}-func">Funcionário</label><select class="in" id="f-it${i}-func" data-b="itens.${i}.valeFunc"><option value="">Escolha…</option>${FUNCIONARIOS.map((f) => `<option ${it.valeFunc === f.nome ? "selected" : ""}>${f.nome}</option>`).join("")}</select></div>
        ${it.valeFunc ? `<dl><div><dt>Salário</dt><dd>${BRL(v.salario)}</dd></div><div><dt>Limite (40%)</dt><dd>${BRL(v.limite)}</dd></div><div><dt>Vales no mês</dt><dd>${BRL(v.ja)}</dd></div><div><dt>Este vale</dt><dd>${BRL(v.este)}</dd></div></dl>
        ${v.acima ? `<div class="note bad" id="f-it${i}-vale">${ic("alert")}<div><b>Passa do limite de 40% do salário.</b> Com este vale, ${esc(it.valeFunc)} fica com ${BRL(v.ja + v.este)} de ${BRL(v.limite)}.
          ${S.perfil === "dono" ? `<label class="chk"><input type="checkbox" data-act="vale-ok" data-i="${i}" ${it.valeOk ? "checked" : ""}><span>Lançar mesmo assim (autorizado pelo dono)</span></label>` : `<span class="hint" style="color:inherit">Só o dono pode autorizar acima do limite. Reduza o valor ou peça a ele.</span>`}</div></div>` : `<div class="note ok">${ic("check")}<div>Dentro do limite. Ainda cabem ${BRL(v.limite - v.ja - v.este)} neste mês.</div></div>`}` : ""}</div>`;
    }
  }
  return bits.join("") + vale;
}
function paintMeta(i) { const e = $(`#meta-${i}`); if (e) e.innerHTML = tplMeta(i); }
function paintItens() { const e = $("#itens"); if (e) { e.innerHTML = S.sub[S.tipo] === "leite" ? tplLeite() : tplItens(); paintTotais(); } }
function paintTotais() {
  const e = $("#totais"); if (!e) return; const F = F_(), c = calc(F), R = ROT[S.tipo];
  const aj = F.ajustes || parseBR(F.desc) || parseBR(F.acr);
  e.innerHTML = `${F.itens.length > 1 || aj ? `<div class="l"><span>Soma dos itens</span><span class="num">${BRL(c.bruto)}</span></div>` : ""}
    ${aj ? `<div class="l"><label for="f-desc">${S.tipo === "receita" ? "Desconto ou retenção" : "Desconto"}</label><span class="pre"><span aria-hidden="true">R$</span><input class="in r" style="width:130px;min-height:36px" id="f-desc" data-b="desc" data-m inputmode="decimal" value="${esc(F.desc)}" placeholder="0,00"></span></div>
    <div class="l"><label for="f-acr">Acréscimo (frete, juros)</label><span class="pre"><span aria-hidden="true">R$</span><input class="in r" style="width:130px;min-height:36px" id="f-acr" data-b="acr" data-m inputmode="decimal" value="${esc(F.acr)}" placeholder="0,00"></span></div>` : `<div class="l"><button type="button" class="link" data-act="ajustes">+ desconto ou acréscimo</button></div>`}
    <div class="l big"><span>Valor da nota</span><span class="num" id="liq">${BRL(c.liq)}</span></div>`;
}

/* venda de leite */
const CTRL_LEITE = { "2026-08": 13420, "2026-09": 13020, "2026-10": 6110 };
function tplLeite() {
  const F = F_(), L = F.leite, litros = parseBR(L.litros), preco = parseBR(L.preco), bruto = r2(litros * preco);
  const ret = F.retTocado ? parseBR(F.desc) : r2(bruto * (parseBR(L.retPct) / 100));
  const liq = r2(bruto - ret), ctrl = CTRL_LEITE[L.mes] || 0, dif = litros ? litros - ctrl : 0, parcial = L.mes === "2026-10";
  const lt = (n) => n.toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  return `<div class="leite">
    <div class="g3">
      <div class="fld"><label for="f-mes">Mês de referência</label><select class="in" id="f-mes" data-b="leite.mes">${["2026-08", "2026-09", "2026-10"].map((m) => `<option value="${m}" ${L.mes === m ? "selected" : ""}>${mesLong(m)}</option>`).join("")}</select><div class="hint">É o mês da receita no resultado.</div></div>
      <div class="fld"><label for="f-litros">Litros entregues <span class="lido ${F.lido.litros ? "" : "hide"}">lido da nota</span></label><input class="in r" id="f-litros" data-b="leite.litros" data-m0 inputmode="numeric" placeholder="0" value="${esc(L.litros)}"><div class="err" id="e-litros" hidden></div></div>
      <div class="fld"><label for="f-preco">Preço por litro</label><div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="f-preco" data-b="leite.preco" data-m inputmode="decimal" value="${esc(L.preco)}"></div><div class="err" id="e-preco" hidden></div></div>
    </div>
    <div class="calc" aria-live="polite"><div class="l"><span>Bruto (${lt(litros)} L × ${BRL(preco)})</span><span class="num">${BRL(bruto)}</span></div>
      <div class="l"><label for="f-pct">Retenção Funrural/Senar</label><span class="row" style="gap:6px;flex-wrap:nowrap"><input class="in r" style="width:70px;min-height:36px" id="f-pct" data-b="leite.retPct" inputmode="decimal" aria-label="Percentual retido" value="${esc(L.retPct)}"><span aria-hidden="true">%</span><span class="pre"><span aria-hidden="true">R$</span><input class="in r" style="width:116px;min-height:36px" id="f-ret" data-b="ret" data-m inputmode="decimal" aria-label="Valor retido em reais" value="${F.retTocado ? esc(F.desc) : fmtNum(ret)}"></span></span></div>
      ${F.retTocado ? `<div class="tiny">Retenção ajustada à mão (${(parseBR(F.desc) / (bruto || 1) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%). <button type="button" class="link" data-act="ret-auto">Voltar ao ${esc(L.retPct)}% do padrão</button></div>` : `<div class="tiny">Percentual padrão da fazenda (Parâmetros financeiros). Edite se a nota trouxer outro.</div>`}
      <div class="l big"><span>A receber (líquido)</span><span class="num">${BRL(liq)}</span></div></div>
    ${litros ? (ctrl ? `<div class="note ${Math.abs(dif) <= 40 || parcial ? "ok" : "warn"}">${ic(Math.abs(dif) <= 40 || parcial ? "check" : "alert")}<div><b>Controle leiteiro: ${lt(ctrl)} L em ${mesLong(L.mes)}${parcial ? " (mês em andamento)" : ""}.</b> A nota diz ${lt(litros)} L (${dif > 0 ? "+" : ""}${lt(dif)} L).
      ${parcial ? "O mês ainda não fechou: a comparação vale no fim do mês." : Math.abs(dif) <= 40 ? "Dentro da tolerância de 40 L." : "Diferença acima de 40 L: confira a nota antes de salvar."}</div></div>` : "") : ""}</div>`;
}

/* datas */
function compHint() { const F = F_(); return `Mês ${S.tipo === "despesa" ? "do gasto" : "da receita"}: <b>${mesLong(compDe(F))}</b>. É nele que ${S.tipo === "despesa" ? "a despesa" : "a receita"} entra no resultado.`; }
function tplDatas() {
  const F = F_(), R = ROT[S.tipo], f = FORN[F.fornecedor] || FORN_REC[F.fornecedor];
  const comp = compDe(F), vencLabel = F.parc ? "1º vencimento" : "Vencimento";
  const q = [["Hoje", "hoje"], ["+7 dias", 7], ["+15 dias", 15], ["+30 dias", 30]];
  return `<div class="g2">
    <div class="fld"><label for="f-emissao">Emissão ${F.lido.emissao ? `<span class="lido">lido da nota</span>` : ""}</label><input type="date" class="in" id="f-emissao" data-b="emissao" value="${F.emissao}">
      <div class="hint" id="h-comp">${compHint()}</div><div class="err" id="e-emissao" hidden></div></div>
    ${F.pago ? `<div class="fld"><label>Vencimento</label><div class="hint" style="margin-top:10px">Não precisa: já ${S.tipo === "despesa" ? "paga" : "recebida"}. A data do ${R.data} está na seção ao lado.</div></div>`
      : `<div class="fld"><label for="f-venc">${vencLabel} ${F.lido.venc ? `<span class="lido">lido da nota</span>` : F.sug.venc ? `<span class="sug">${esc(F.sug.venc)}</span>` : ""}</label><input type="date" class="in" id="f-venc" data-b="venc" value="${F.venc}">
      <div class="chips mt" role="group" aria-label="Atalhos de vencimento">${q.map(([l, d]) => `<button type="button" class="chip" data-act="venc-q" data-v="${d}">${l}</button>`).join("")}<button type="button" class="chip" data-act="venc-q" data-v="dia10">Dia 10 do mês seguinte</button></div>
      <div class="err" id="e-venc" hidden></div><div id="h-venc" class="hint"></div></div>`}
  </div>`;
}
function paintDatas() { const e = $("#datas"); if (e) e.innerHTML = tplDatas(); paintVencHint(); }
function paintVencHint() {
  const F = F_(), e = $("#h-venc"); if (!e) return;
  e.innerHTML = F.venc ? (F.venc < F.emissao ? `<span style="color:var(--warn);font-weight:600">${ic("alert")} Vence antes da emissão — confira as datas.</span>` : `${fmtD(F.venc)} · ${emDias(F.venc)}`) : "";
}

/* pagamento / parcelas */
function tplPag() {
  const F = F_(), R = ROT[S.tipo], c = calc(F);
  const banco = BANCOS[F.banco];
  const pagoHtml = F.pago ? `<div class="g3 mt">
      <div class="fld"><label for="f-pagodata">Data do ${R.data}</label><input type="date" class="in" id="f-pagodata" data-b="pagoData" value="${F.pagoData}"><div class="hint">${F.pagoData > TODAY ? "Data futura: vira " + R.data + " agendado e não mexe no saldo de hoje." : "Pagamento anterior a hoje entra no saldo do dia."}</div><div class="err" id="e-pagodata" hidden></div></div>
      <div class="fld"><label for="f-banco">Conta bancária ${F.sug.banco ? `<span class="sug">${esc(F.sug.banco)}</span>` : ""}</label><select class="in" id="f-banco" data-b="banco" data-num>${BANCOS.map((b) => `<option value="${b.id}" ${F.banco === b.id ? "selected" : ""}>${b.nome} · ${b.sub}</option>`).join("")}</select><div class="hint">Saldo hoje ${BRL(banco.saldo)}</div></div>
      <div class="fld"><label for="f-compr">Nº do comprovante <span class="opt">(opcional)</span></label><input class="in" id="f-compr" data-b="comprovante" value="${esc(F.comprovante)}"></div>
      <div class="fld"><label for="f-valorpago">Valor ${S.tipo === "despesa" ? "pago" : "recebido"}</label><div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="f-valorpago" data-b="valorPago" data-m inputmode="decimal" value="${esc(F.valorPago)}"></div><div class="err" id="e-valorpago" hidden></div><div class="hint" id="h-dif"></div></div>
    </div>
    <div class="fld mt"><span class="lab">Forma de ${S.tipo === "despesa" ? "pagamento" : "recebimento"} ${F.sug.forma ? `<span class="sug">${esc(F.sug.forma)}</span>` : ""}</span><div class="chips" role="group" aria-label="Forma">${FORMAS.map((f) => `<button type="button" class="chip" data-act="forma" data-v="${f}" aria-pressed="${F.forma === f}">${f}</button>`).join("")}</div></div>` : "";
  const parcHtml = !F.pago ? `<div class="mt2"><label class="chk"><input type="checkbox" data-act="parc" ${F.parc ? "checked" : ""}><span><b>Parcelar</b><span class="hint">Cada parcela vira uma conta ${R.contaV} com seu vencimento.</span></span></label>
    ${F.parc ? `<div class="fld mt"><span class="lab">Número de parcelas</span><div class="row"><div class="chips" role="group" aria-label="Parcelas">${[2, 3, 4, 6, 10, 12].map((n) => `<button type="button" class="chip" data-act="nparc" data-v="${n}" aria-pressed="${F.nParc === n}">${n}×</button>`).join("")}</div><span class="row" style="gap:6px"><label for="f-nparc" class="tiny">ou</label><input type="number" min="2" max="36" class="in r" style="width:84px" id="f-nparc" data-b="nParc" data-num value="${F.nParc}"></span></div></div>
    <div class="mt" id="parcs" tabindex="-1">${tplParcelas()}</div><div class="err" id="e-parcs" hidden></div>` : ""}</div>` : "";
  return `<div role="radiogroup" aria-label="Situação do pagamento" class="seg2">
    <label><input type="radio" name="pagoMode" data-act="pagomode" value="aberto" ${!F.pago ? "checked" : ""}><b>${R.aberto}</b><span>${R.abertoD}</span></label>
    <label><input type="radio" name="pagoMode" data-act="pagomode" value="pago" ${F.pago ? "checked" : ""}><b>${R.pago}</b><span>${R.pagoD}</span></label></div>
    ${pagoHtml}${parcHtml}`;
}
function tplParcelas() {
  const F = F_(), c = calc(F), soma = r2(F.parcelas.reduce((s, p) => s + parseBR(p.valor), 0)), ok = Math.abs(soma - c.liq) <= 0.01;
  return `<div class="parcs" role="group" aria-label="Parcelas">
    <div class="phead" aria-hidden="true"><span>Parcela</span><span>Vencimento</span><span class="r">Valor</span><span>Nº do boleto</span><span>Paga?</span></div>
    ${F.parcelas.map((p, i) => `<div class="prow"><span class="pn">${i + 1}/${F.parcelas.length}</span>
      <input type="date" class="in" data-b="parcelas.${i}.venc" value="${p.venc}" aria-label="Vencimento da parcela ${i + 1}">
      <div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="f-par${i}-valor" data-b="parcelas.${i}.valor" data-m inputmode="decimal" value="${fmtNum(parseBR(p.valor))}" aria-label="Valor da parcela ${i + 1}"></div>
      <input class="in" data-b="parcelas.${i}.boleto" value="${esc(p.boleto)}" aria-label="Número do boleto da parcela ${i + 1}" placeholder="opcional">
      <label class="chk pchk"><input type="checkbox" data-act="parc-paga" data-i="${i}" ${p.paga ? "checked" : ""}><span>${S.tipo === "despesa" ? "Paga" : "Recebida"}</span></label></div>`).join("")}
    <div class="pfoot" id="pfoot">${pfootHtml(soma, c.liq, ok)}</div></div>`;
}
function pfootHtml(soma, liq, ok) { return `<span>Soma das parcelas</span><b class="num" style="color:${ok ? "inherit" : "var(--bad)"}">${BRL(soma)}</b><span class="tiny">${ok ? "Confere com a nota" : "Difere de " + BRL(liq)}</span><button type="button" class="link" data-act="redistribuir">Redistribuir igualmente</button>`; }
function paintPfoot() { const F = F_(), e = $("#pfoot"); if (!e) return; const soma = r2(F.parcelas.reduce((s, p) => s + parseBR(p.valor), 0)), liq = calc(F).liq; e.innerHTML = pfootHtml(soma, liq, Math.abs(soma - liq) <= 0.01); }
function paintPag() { const e = $("#pag"); if (e) e.innerHTML = tplPag(); paintDif(); }
function paintDif() {
  const F = F_(), e = $("#h-dif"); if (!e || !F.pago) return;
  const liq = calc(F).liq, vp = parseBR(F.valorPago), d = r2(vp - liq);
  e.innerHTML = Math.abs(d) < 0.005 ? "Igual ao valor da nota." : `<b style="color:${d < 0 ? "var(--ok)" : "var(--warn)"}">${d < 0 ? "Desconto de " : "Juros/multa de "}${BRL(Math.abs(d))}</b> — vai para “Outras receitas e despesas”, não para o item.`;
}

/* documento */
function tplDoc() {
  const F = F_();
  return `<div class="drop" id="dropzone"><p>Anexe a nota, o boleto ou o comprovante: o sistema <b>lê o documento e preenche</b> o que encontrar — você confere antes de salvar.</p>
    <div class="row"><button type="button" class="btn btn-sec" data-act="anexar">${ic("up")} Escolher arquivo</button><button type="button" class="btn btn-sec" data-act="foto">${ic("cam")} Tirar foto</button><button type="button" class="btn btn-ghost" data-act="xml">Colar XML</button></div></div>
    <input type="file" id="file" class="hide" multiple accept=".xml,.pdf,image/*"><input type="file" id="foto" class="hide" accept="image/*" capture="environment">
    ${F.lendo ? `<div class="reading" role="status"><span class="spin"></span> Lendo o documento…</div>` : ""}
    ${F.anexos.length ? `<ul class="files">${F.anexos.map((a, i) => `<li>${ic("file")}<span class="n">${esc(a.nome)}</span><span class="st ${a.lido ? "info" : "mute"}">${a.lido ? "lido" : "anexado"}</span><button type="button" class="btn btn-ghost btn-sm" data-act="del-anexo" data-i="${i}" aria-label="Remover ${esc(a.nome)}">${ic("x")}</button></li>`).join("")}</ul>` : ""}
    <div class="g2 mt"><div class="fld"><label for="f-doc">Número do documento <span class="opt">(opcional)</span> ${F.lido.doc ? `<span class="lido">lido da nota</span>` : ""}</label><input class="in" id="f-doc" data-b="doc" value="${esc(F.doc)}" placeholder="ex.: NF 5612"></div>
    <div class="fld"><label for="f-tipodoc">Tipo de documento</label><select class="in" id="f-tipodoc" data-b="tipoDoc">${["Nota fiscal", "Recibo", "Boleto", "Fatura", "Comprovante", "Contrato", "Ordem de serviço"].map((t) => `<option ${F.tipoDoc === t ? "selected" : ""}>${t}</option>`).join("")}</select></div></div>`;
}
function paintDoc() { const e = $("#doc"); if (e) e.innerHTML = tplDoc(); }

/* avançado */
function tplAvancado() {
  const F = F_(), tipo = S.tipo; const nat = F.natureza || (F.itens[0].conta ? naturezaAuto(F.itens[0].conta) : "OPERACIONAL");
  const auto = !F.natureza;
  return `<details class="adv" id="adv"><summary>${ic("chev")}<span>Para o contador e detalhes raros <small>natureza, competência, centro de custo, OS, boleto, pedido</small></span></summary>
    <div class="body"><div class="g2">
      <div class="fld"><label for="f-nat">Natureza do lançamento</label><select class="in" id="f-nat" data-b="natureza"><option value="">Automática (pela conta): ${NATUREZAS[nat][0]}</option>${Object.entries(NATUREZAS).map(([k, [n]]) => `<option value="${k}" ${F.natureza === k ? "selected" : ""}>${n}</option>`).join("")}</select>
        <div class="hint" id="h-nat">${natHint()}</div></div>
      <div class="fld"><label for="f-comp">Mês ${tipo === "despesa" ? "do gasto" : "da receita"} (competência)</label><input class="in" type="month" id="f-comp" data-b="comp" value="${compDe(F)}"><div class="hint">Padrão: o mês da emissão. Mude para lançar uma nota de um mês no resultado de outro.</div></div>
      <div class="fld"><label for="f-centro">Centro de custo</label><select class="in" id="f-centro" data-b="centro">${["Pecuária Leiteira", "Agricultura", "Arrendamento", "Financiamento 2026"].map((c) => `<option ${F.centro === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
      <div class="fld"><label for="f-etq">Etiqueta <span class="opt">(opcional)</span></label><input class="in" id="f-etq" data-b="etiqueta" value="${esc(F.etiqueta)}" placeholder="ex.: Medicamentos"><div class="hint">Agrupa lançamentos nos relatórios. Não define a conta.</div></div>
      <div class="fld"><label for="f-resp">Responsável</label><select class="in" id="f-resp" data-b="resp">${["Administrador", "Jairo Nasser", "Contador"].map((c) => `<option ${F.resp === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
      <div class="fld"><label for="f-os">Nº da OS ou orçamento</label><input class="in" id="f-os" data-b="os" value="${esc(F.os)}"></div>
      <div class="fld"><label for="f-bol">Linha digitável do boleto</label><input class="in" id="f-bol" data-b="boleto" value="${esc(F.boleto)}" inputmode="numeric"></div>
      ${tipo === "despesa" ? `<div class="fld" style="grid-column:1/-1"><label class="chk"><input type="checkbox" data-act="entregue" ${F.entregue ? "checked" : ""}><span><b>Mercadoria já entregue</b><span class="hint">Marcado: o estoque recebe a entrada agora. Desmarcado: só quando a mercadoria chegar.</span></span></label></div>
      ${F.entregue ? "" : `<div class="fld"><label for="f-prev">Data prevista de entrada</label><input type="date" class="in" id="f-prev" data-b="prevista" value="${F.prevista}"></div>`}
      <div class="fld"><label for="f-ped">Vincular a um pedido</label><select class="in" id="f-ped" data-b="pedido"><option value="">— nenhum —</option>${PEDIDOS.despesa.map((p) => `<option value="${p.id}" ${F.pedido === p.id ? "selected" : ""}>${p.id} · ${p.forn} · ${BRL(p.total)}</option>`).join("")}</select></div>` : ""}
    </div>
    <label class="chk mt"><input type="checkbox" data-act="classificar-depois" ${F.classificarDepois ? "checked" : ""}><span><b>Classificar depois</b><span class="hint">Grava sem a conta gerencial; a conta fica na fila “Classificar” do Resultado até alguém escolher.</span></span></label></div></details>`;
}

/* ───────────────────────── rail: efeito + histórico ───────────────────────── */
function efeito() {
  const tipo = S.tipo, sub = S.sub[tipo], F = F_(), R = ROT[tipo], c = calc(F), rows = [], leite = sub === "leite", sg = R.sinal > 0 ? "+" : "−";
  if (!(c.liq > 0)) return null;
  const agendado = F.pago && F.pagoData > TODAY;
  if (F.pago && !agendado) rows.push(["contas", R.conta, `<span class="v">Já ${tipo === "despesa" ? "paga" : "recebida"}</span><small>Baixa em ${fmtD(F.pagoData)} · ${esc(F.forma)} · não fica em aberto</small>`]);
  else if (agendado) rows.push(["contas", R.conta, `<span class="v">${tipo === "despesa" ? "Pagamento" : "Recebimento"} agendado</span><small>Para ${fmtD(F.pagoData)} (${emDias(F.pagoData)}); fica em aberto até lá. Aparece em “${bucket(F.pagoData)}”.</small>`]);
  else if (F.parc && F.parcelas.length) {
    const v = F.parcelas.map((p) => parseBR(p.valor)), iguais = Math.max(...v) - Math.min(...v) <= 0.1, p0 = F.parcelas[0], pN = F.parcelas[F.parcelas.length - 1];
    rows.push(["contas", R.conta, `<span class="v">${F.parcelas.length}× de ${iguais ? BRL(v[0]) : BRL(Math.min(...v)) + " a " + BRL(Math.max(...v))}</span><small>1ª em ${fmtD(p0.venc)} (${emDias(p0.venc)}), última em ${fmtD(pN.venc)}. Aparece em “${bucket(p0.venc)}”.</small>`]);
  } else if (F.venc) rows.push(["contas", R.conta, `<span class="v">${BRL(c.liq)}</span><small>Vence ${fmtD(F.venc)} (${emDias(F.venc)}). Aparece em “${bucket(F.venc)}”.</small>`]);
  else rows.push(["contas", R.conta, `<small>Informe o vencimento para ver onde aparece.</small>`]);
  const comp = leite ? F.leite.mes : compDe(F);
  const op = {}; let opTot = 0, fora = null, foraVal = 0;
  F.itens.forEach((it) => { if (!it.conta) return; const v = itemTotal(it); if (!(v > 0)) return; const nat = F.natureza || naturezaAuto(it.conta); if (nat !== "OPERACIONAL") { foraVal += v; fora = fora || { nat }; } else { const g = grupoCurto(it.conta); op[g] = (op[g] || 0) + v; opTot += v; } });
  const mesRot = tipo === "receita" ? `Resultado de ${mesLabel(comp + "-01")}` : `Resultado de ${mesLabel(comp + "-01")}`;
  if (leite) rows.push(["res", mesRot, `<span class="v plus">+${BRL(c.bruto)}</span><small>Receita de leite · Operacional${c.desc ? `<br>Deduções da receita (Funrural/Senar): −${BRL(c.desc)}` : ""}${parseBR(F.leite.litros) ? `<br>${BRL(parseBR(F.leite.preco))} por litro × ${fmtNum(parseBR(F.leite.litros)).replace(",00", "")} L` : ""}</small>`]);
  else if (opTot || foraVal) {
    const parts = [];
    if (opTot) parts.push(Object.entries(op).map(([g, v]) => `${esc(g)} · ${BRL(v)}`).join("<br>") + `<br>Operacional · ${esc(F.centro)}`);
    if (foraVal) parts.push(`${opTot ? "<b>Fora do resultado:</b> " : ""}${BRL(foraVal)} · ${NATUREZAS[fora.nat][0].toLowerCase()}. ${NATUREZAS[fora.nat][1]}${fora.nat === "INVESTIMENTO" && tipo === "despesa" ? (F.criarBem ? ` O bem será cadastrado no Patrimônio e depreciado em ${esc(F.vidaUtil || "10")} anos.` : ' <span style="color:var(--warn);font-weight:600">Sem bem no Patrimônio: não vai depreciar.</span>') : ""}`);
    rows.push(["res", mesRot, `<span class="v ${R.sinal > 0 ? "plus" : "minus"}">${opTot ? sg + BRL(opTot) : "Fora do resultado"}</span><small>${parts.join("<br>")}</small>`]);
  } else rows.push(["res", "Resultado", `<small>Escolha para onde o item vai para ver em qual linha do resultado ele cai.</small>`]);
  if (F.pago && !agendado) { const b = BANCOS[F.banco], vp = parseBR(F.valorPago) || c.liq; rows.push(["caixa", "Caixa", `<span class="v">${esc(b.nome)}</span><small>${BRL(b.saldo)} → <b>${BRL(b.saldo + R.sinal * vp)}</b> (${R.sinal > 0 ? "entra" : "sai"} ${BRL(vp)})</small>`]); }
  else if (agendado) rows.push(["caixa", "Caixa", `<small>Sem movimento hoje. ${R.sinal > 0 ? "Entra" : "Sai"} em ${fmtD(F.pagoData)}.</small>`]);
  else rows.push(["caixa", "Caixa", `<small>Sem movimento agora. ${R.sinal > 0 ? "Entra" : "Sai"} quando você der baixa.</small>`]);
  const est = leite ? [] : F.itens.filter((it) => it.produto.trim() && itemInfo(tipo, it.produto)?.estoque && parseBR(it.qtd) > 0);
  const fora2 = leite ? [] : F.itens.filter((it) => it.produto.trim() && !itemInfo(tipo, it.produto) && tipo === "despesa" && estocavel(it.conta));
  if (est.length || fora2.length) rows.push(["est", "Estoque", [...est.map((it) => tipo === "despesa" && !F.entregue ? `<span class="v">${esc(it.produto)}</span><small>Entra ${esc(it.qtd)} ${esc(itemInfo(tipo, it.produto).un)} quando a mercadoria chegar${F.prevista ? " (prevista " + fmtD(F.prevista) + ")" : ""}.</small>` : `<span class="v">${tipo === "despesa" ? "+" : "−"}${esc(it.qtd)} ${esc(itemInfo(tipo, it.produto).un)}</span> ${esc(it.produto)}`), ...fora2.map((it) => `<small style="color:var(--warn)"><b>${esc(it.produto)}</b> não está no estoque: grava sem baixa.</small>`)].join("<br>")]);
  return rows;
}
function efeitoCurto() {
  const tipo = S.tipo, sub = S.sub[tipo]; if (tipo === "despesa" && (sub === "lote" || sub === "semen")) return ""; const F = F_(), c = calc(F); if (!(c.liq > 0)) return "";
  const p = [], it = F.itens.find((i) => i.conta);
  p.push(`Resultado ${mesLabel(compDe(F) + "-01")}${it ? " · " + grupoCurto(it.conta) : ""}`);
  if (!F.pago) { const v = F.parc && F.parcelas.length ? F.parcelas[0].venc : F.venc; if (v) p.push(`aparece em “${bucket(v)}”`); }
  return p.join(" · ");
}
function ctxHtml() {
  const tipo = S.tipo, F = F_(), R = ROT[tipo], vi = F.itens.find((i) => i.vale && i.valeFunc);
  if (vi) { const v = valeInfo(vi); return `<dl><div><dt>Salário</dt><dd>${BRL(v.salario)}</dd></div><div><dt>Vales no mês</dt><dd>${BRL(v.ja)}</dd></div></dl><p class="habit">Limite de <b>40%</b> do salário: <b>${BRL(v.limite)}</b>. Depois deste vale: <b>${BRL(v.ja + v.este)}</b>.</p>`; }
  if (!F.fornecedor.trim()) return `<p class="empty-eff">Escolha o ${R.forn.toLowerCase()} para ver o que já foi lançado com ${tipo === "despesa" ? "ele" : "ele"} e receber sugestões de conta, prazo e forma.</p>`;
  const x = contextoDe(F.fornecedor, tipo), f = fornDe(tipo)[F.fornecedor];
  if (!x.recentes.length && !f) return `<p class="empty-eff"><b>${esc(F.fornecedor)}</b> é novo por aqui: nenhum lançamento anterior. Depois deste, o sistema passa a sugerir conta, prazo e forma.</p>`;
  return `<dl><div><dt>Em aberto</dt><dd>${BRL(x.aberto)}<div class="tiny" style="font-weight:400">${x.n} ${x.n === 1 ? "conta" : "contas"}</div></dd></div><div><dt>Último lançamento</dt><dd>${fmtD(x.ultimo)}</dd></div></dl>
    ${f ? `<p class="habit">Costuma vencer em <b>${f.prazo} dias</b>, ${tipo === "despesa" ? "pago" : "recebido"} por <b>${f.forma}</b> em <b>${BANCOS[f.banco].nome}</b>.</p>` : ""}
    ${x.recentes.length ? `<ul aria-label="Últimos lançamentos">${x.recentes.map((r) => { const ab = r.partes.filter((p) => !p.pago); const st = ab.length ? (ab[0].venc < TODAY ? ["bad", "Vencida"] : ["info", "Em aberto"]) : ["ok", tipo === "despesa" ? "Paga" : "Recebida"]; return `<li><span>${esc(r.doc)} · <b class="num">${BRL(r.total)}</b></span><small>${fmtD(r.emissao)} · ${esc(r.item)}${r.partes.length > 1 ? ` · ${r.partes.length} parcelas, ${ab.length} em aberto` : ""}</small><span class="st ${st[0]}">${st[1]}</span></li>`; }).join("")}</ul>` : ""}`;
}
function avisosRail() {
  const tipo = S.tipo, F = F_(), A = [], d = achaDuplicado(F, tipo, S.sub[tipo]);
  if (d) A.push(`<div class="note warn">${ic("alert")}<div><b>Parecida com ${d.id}.</b> ${S.sub[tipo] === "leite" ? "Já existe uma nota deste cliente para o mesmo mês" : d.doc && (F.doc || "").trim() ? "Mesmo número de documento" : "Mesmo " + ROT[tipo].forn.toLowerCase() + " e valor"}, emitida em ${fmtD(d.emissao)}. Você poderá conferir antes de salvar.</div></div>`);
  return A.join("");
}
let _prevEff = {};
function paintRail() {
  const r = $("#rail"); if (!r) return; const rows = efeito(), F = F_(); let h;
  if (S.view !== "lancar") return;
  h = `<section aria-labelledby="h-ef"><h2 id="h-ef">O que muda ao salvar</h2>${avisosRail()}
    ${rows ? `<dl class="eff">${rows.map(([k, l, v]) => `<div><dt>${l}</dt><dd data-k="${k}">${v}</dd></div>`).join("")}</dl>` : `<p class="empty-eff">Preencha o item e o valor: aqui aparece onde a conta vai aparecer, em qual linha do resultado ela cai e o que acontece com o caixa e o estoque.</p>`}</section>
    <section class="ctx" aria-labelledby="h-ctx"><h2 id="h-ctx">${F.fornecedor.trim() ? "Histórico de " + esc(F.fornecedor) : "Histórico"}</h2>${ctxHtml()}</section>`;
  r.innerHTML = h;
  $$("dd[data-k]", r).forEach((d) => { const k = d.dataset.k, t = d.textContent; if (_prevEff[k] != null && _prevEff[k] !== t) d.classList.add("flash"); _prevEff[k] = t; });
}
function paintFoot() {
  const f = $("#foot"); if (!f) return; const tipo = S.tipo, sub = S.sub[tipo], F = F_(), c = calc(F), R = ROT[tipo], falta = faltas(F, tipo, sub);
  let sm;
  if (falta.length) sm = `<span class="s miss">Falta: ${falta.join(", ")}</span>`;
  else if (F.pago) sm = `<span class="s">${F.pagoData > TODAY ? "Agendada para" : "Já " + (tipo === "despesa" ? "paga" : "recebida") + " em"} ${fmtD(F.pagoData)}</span>`;
  else if (F.parc && F.parcelas.length) sm = `<span class="s">${F.parcelas.length}× de ${BRL(parseBR(F.parcelas[0].valor))} · 1ª em ${fmtD(F.parcelas[0].venc)}</span>`;
  else sm = `<span class="s">À vista · vence ${fmtD(F.venc)}</span>`;
  const fx = efeitoCurto();
  f.innerHTML = `<div class="sum"><div class="t num">${BRL(c.liq)}</div>${sm}${fx ? `<span class="fx">${esc(fx)}</span>` : ""}</div>
    <div class="acts"><button type="button" class="btn btn-sec" data-act="salvar" data-v="outro" aria-describedby="hint-outro">Salvar e lançar outro</button>
    <button type="button" class="btn btn-gold" data-act="salvar" data-v="fim" title="Atalho: Ctrl + Enter">Salvar lançamento <kbd>Ctrl ↵</kbd></button></div>
    <span class="btnhint tiny" id="hint-outro">“Salvar e lançar outro” mantém ${R.forn.toLowerCase()}, centro e forma de pagamento e já traz as sugestões.</span>`;
}
/* ───────────────────────── lote / faturas / sêmen ───────────────────────── */
function tplLote() {
  const L = S.lote, tot = L.notas.reduce((s, n) => s + parseBR(n.valor), 0);
  return `<div id="topmsg">${tplTopMsg()}</div>
  <form id="frm" class="lay" novalidate aria-label="Lançar lote de notas">
    <div class="sheet">
      <section class="sec" aria-labelledby="h-lq"><h2 id="h-lq">Dados do lote</h2>
        <p class="hint" style="margin:-6px 0 14px;max-width:60ch">Um fornecedor, várias notas, um vencimento só. Cada nota vira uma conta completa e o lote entra numa fatura já fechada. <b>Grava tudo ou nada.</b></p>
        <div class="g3"><div class="fld"><label for="f-forn">Fornecedor (único)</label><div class="combo" data-combo="forn"><input class="in" id="f-forn" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="lb-forn" autocomplete="off" placeholder="Digite ou escolha" value="${esc(L.forn)}"><ul tabindex="-1" id="lb-forn" role="listbox" hidden></ul></div><div class="err" id="e-forn" hidden></div></div>
        <div class="fld"><label for="l-banco">Conta bancária</label><select class="in" id="l-banco" data-b="lote.banco" data-num>${BANCOS.map((b) => `<option value="${b.id}" ${L.banco === b.id ? "selected" : ""}>${b.nome}</option>`).join("")}</select></div>
        <div class="fld"><label for="l-centro">Centro de custo</label><select class="in" id="l-centro" data-b="lote.centro">${["Pecuária Leiteira", "Agricultura", "Arrendamento"].map((c) => `<option ${L.centro === c ? "selected" : ""}>${c}</option>`).join("")}</select></div></div></section>
      <section class="sec" aria-labelledby="h-ln"><h2 id="h-ln">Notas do lote <span class="tag tiny">${L.notas.length} ${L.notas.length === 1 ? "nota" : "notas"}</span></h2>
        <div id="lote-notas" tabindex="-1">${L.notas.map((n, i) => `<fieldset class="nota"><legend class="sr">Nota ${i + 1}</legend>
          <div class="fld c-doc"><label for="l-doc${i}">Nº do documento</label><input class="in" id="l-doc${i}" data-b="lote.notas.${i}.doc" value="${n.sem ? "" : esc(n.doc)}" placeholder="NF 0000" ${n.sem ? "disabled" : ""}>
            <label class="chk compact"><input type="checkbox" id="l-sem${i}" data-act="nota-sem" data-i="${i}" ${n.sem ? "checked" : ""}><span>sem número</span></label></div>
          <div class="fld c-emi"><label for="l-emi${i}">Emissão</label><input type="date" class="in" id="l-emi${i}" data-b="lote.notas.${i}.emissao" value="${n.emissao}"></div>
          <div class="fld c-item"><label for="l-item${i}">Item</label><input class="in" id="l-item${i}" data-b="lote.notas.${i}.item" value="${esc(n.item)}" placeholder="O que foi comprado"></div>
          <div class="fld c-conta"><label for="l-conta${i}">Para onde vai</label><select class="in" id="l-conta${i}" data-b="lote.notas.${i}.conta"><option value="">Escolha…</option>${agrupaOpts(CONTAS_DESP, n.conta)}</select></div>
          <div class="fld c-val"><label for="l-val${i}">Valor</label><div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="l-val${i}" data-b="lote.notas.${i}.valor" data-m inputmode="decimal" value="${esc(n.valor)}" placeholder="0,00"></div></div>
          ${L.notas.length > 1 ? `<button type="button" class="x" data-act="del-nota" data-i="${i}" aria-label="Remover a nota ${i + 1}">${ic("trash")}</button>` : ""}</fieldset>`).join("")}</div>
        <div class="row mt"><button type="button" class="btn btn-sec" data-act="add-nota">${ic("plus")} Nova nota <span class="tiny" style="color:inherit;opacity:.8">herda a emissão</span></button><button type="button" class="btn btn-ghost" data-act="importar-planilha">Importar planilha</button></div>
        <div class="err" id="e-lote" hidden></div></section>
      <section class="sec" aria-labelledby="h-lv"><h2 id="h-lv">Vencimento do lote</h2>
        <div class="chips" role="radiogroup" aria-label="Como pagar o lote">${[["unico", "Vencimento único"], ["parcelar", "Parcelar a fatura"], ["pago", "Já paguei"]].map(([k, l]) => `<button type="button" class="chip" role="radio" aria-checked="${L.modo === k}" data-act="lote-modo" data-v="${k}">${l}</button>`).join("")}</div>
        <div class="g3 mt">${L.modo === "pago" ? `<div class="fld"><label for="l-pdata">Data do pagamento</label><input type="date" class="in" id="l-pdata" data-b="lote.pagoData" value="${L.pagoData}"></div>` : `<div class="fld"><label for="l-venc">${L.modo === "parcelar" ? "1º vencimento" : "Vencimento (todas as notas)"}</label><input type="date" class="in" id="l-venc" data-b="lote.venc" value="${L.venc}"></div>`}
        ${L.modo === "parcelar" ? `<div class="fld"><label for="l-np">Parcelas</label><select class="in" id="l-np" data-b="lote.nParc" data-num>${[2, 3, 4, 6].map((n) => `<option ${L.nParc === n ? "selected" : ""}>${n}</option>`).join("")}</select></div>` : ""}</div></section>
    </div>
    <aside class="rail" id="rail" aria-label="Resumo do lote"></aside>
    <div class="actionbar" id="foot"></div>
  </form>`;
}
function agrupaOpts(list, sel) {
  const g = {}; list.forEach(([c, n]) => (g[grupoCurto(c)] = g[grupoCurto(c)] || []).push([c, n]));
  return Object.entries(g).map(([k, v]) => `<optgroup label="${esc(k)}">${v.map(([c, n]) => `<option value="${c}" ${sel === c ? "selected" : ""}>${esc(n)} (${c})</option>`).join("")}</optgroup>`).join("");
}
function paintLote() {
  const r = $("#rail"), f = $("#foot"); if (!r) return; const L = S.lote, tot = r2(L.notas.reduce((s, n) => s + parseBR(n.valor), 0)), ok = L.notas.filter((n) => parseBR(n.valor) > 0);
  const venc = L.modo === "pago" ? L.pagoData : L.venc;
  const meses = {}; ok.forEach((n) => { const k = n.emissao.slice(0, 7); meses[k] = (meses[k] || 0) + parseBR(n.valor); });
  r.innerHTML = `<section><h2>O que muda ao salvar</h2>${ok.length ? `<dl class="eff"><div><dt>Notas</dt><dd><span class="v">${ok.length} ${ok.length === 1 ? "nota" : "notas"} · ${BRL(tot)}</span><small>Cada uma vira uma conta ${L.modo === "pago" ? "já paga" : "a pagar"}.</small></dd></div>
    <div><dt>Fatura</dt><dd><span class="v">1 fatura fechada</span><small>${esc(L.forn || "do fornecedor")} · ${L.modo === "parcelar" ? L.nParc + "× a partir de " + fmtD(L.venc) : L.modo === "pago" ? "paga em " + fmtD(L.pagoData) : "vence " + fmtD(L.venc)}</small></dd></div>
    <div><dt>Resultado</dt><dd><span class="v minus">−${BRL(tot)}</span><small>${Object.entries(meses).map(([m, v]) => `${mesLabel(m + "-01")} · ${BRL(v)}`).join("<br>")}</small></dd></div>
    <div><dt>Caixa</dt><dd>${L.modo === "pago" ? `<span class="v">${esc(BANCOS[L.banco].nome)}</span><small>${BRL(BANCOS[L.banco].saldo)} → <b>${BRL(BANCOS[L.banco].saldo - tot)}</b></small>` : `<small>Sem movimento agora.</small>`}</dd></div></dl>` : `<p class="empty-eff">Preencha o valor das notas para ver a fatura que será criada.</p>`}</section>`;
  const falta = []; if (!L.forn) falta.push("fornecedor"); if (!ok.length) falta.push("valor das notas"); if (L.modo !== "pago" && !L.venc) falta.push("vencimento");
  f.innerHTML = `<div class="sum"><div class="t num">${BRL(tot)}</div>${falta.length ? `<span class="s miss">Falta: ${falta.join(", ")}</span>` : `<span class="s">${ok.length} ${ok.length === 1 ? "nota" : "notas"} · se qualquer nota falhar, nada é gravado</span>`}</div>
    <div class="acts"><button type="button" class="btn btn-gold" data-act="salvar-lote">Lançar lote <span class="tiny" style="color:inherit">(tudo ou nada)</span></button></div>`;
}

function tplFaturas() {
  const F = S.faturas, ab = F.filter((f) => f.st === "Aberta"), fe = F.filter((f) => f.st === "Fechada"), pg = F.filter((f) => f.st === "Paga"), sm = (a) => a.reduce((s, f) => s + f.v, 0);
  const stc = { Aberta: "info", Fechada: "warn", Paga: "ok" };
  return `<div id="topmsg">${tplTopMsg()}</div><div class="sheet"><section class="sec"><h2>Faturas de fornecedor</h2>
    <p class="hint" style="margin:-6px 0 14px;max-width:62ch">Fatura junta várias notas de um mesmo fornecedor num vencimento só. Para criar uma já fechada, use o <button type="button" class="link" data-act="sub" data-v="lote">Lote de notas</button>. A gestão completa fica em Contas.</p>
    <div class="kpis" style="margin-top:0"><div class="${ab.length ? "warn" : ""}"><div class="k">Abertas</div><div class="v">${ab.length}</div><div class="s">${ab.length ? BRL(sm(ab)) : "—"}</div></div><div><div class="k">Fechadas, a pagar</div><div class="v">${fe.length}</div><div class="s">${fe.length ? BRL(sm(fe)) : "—"}</div></div><div><div class="k">Pagas neste mês</div><div class="v">${pg.length}</div><div class="s">${pg.length ? BRL(sm(pg)) : "—"}</div></div></div>
    <div class="tblwrap"><table class="tbl lista"><thead><tr><th scope="col">Fatura</th><th scope="col">Fornecedor</th><th scope="col">Situação</th><th scope="col" class="r">Notas</th><th scope="col" class="r">Valor</th><th scope="col">Vencimento</th><th scope="col"><span class="sr">Ações</span></th></tr></thead><tbody>
    ${F.map((f) => `<tr><td><b>${f.id}</b></td><td>${esc(f.forn)}</td><td><span class="st ${stc[f.st]}">${f.st}</span></td><td class="r">${f.n}</td><td class="r"><b class="num">${BRL(f.v)}</b></td><td>${fmtD(f.venc)}</td><td>${f.st === "Aberta" ? `<button type="button" class="btn btn-sec btn-sm" data-act="fatura-juntar" data-v="${f.id}">Juntar notas</button> <button type="button" class="btn btn-sec btn-sm" data-act="fatura-fechar" data-v="${f.id}">Fechar fatura</button>` : f.st === "Fechada" ? `<span class="tiny">Fechada: vence em ${fmtD(f.venc)}</span>` : `<span class="tiny">Sem ações</span>`}</td></tr>`).join("")}</tbody></table></div></section></div>`;
}
function abrirJuntar(fid) {
  const f = S.faturas.find((x) => x.id === fid), cand = LANC.filter((l) => l.tipo === "despesa" && l.forn === f.forn && !l.pago && !l.fatura && !l.parcela);
  window._fat = f;
  dlg(`<div class="dh"><h2 id="dlg-t">Juntar notas à ${f.id}</h2></div><div class="db"><p>${esc(f.forn)} · fatura aberta com ${f.n} ${f.n === 1 ? "nota" : "notas"} (${BRL(f.v)}).</p>
    ${cand.length ? `<fieldset style="border:0;padding:0;margin:0;display:grid;gap:4px"><legend class="lab">Notas em aberto deste fornecedor</legend>${cand.map((l, k) => `<label class="chk"><input type="checkbox" class="fat-c" value="${l.id}|${l.venc}" ${k === 0 ? "checked" : ""}><span><b>${esc(l.item)}</b> · ${l.id} · ${esc(l.doc || "")}<span class="hint">${BRL(l.valor)} · vence ${fmtD(l.venc)}</span></span></label>`).join("")}</fieldset>` : `<div class="note info">${ic("info")}<div>Este fornecedor não tem outra nota em aberto fora de fatura.</div></div>`}</div>
    <div class="df"><button type="button" class="btn btn-ghost" data-dlg="revisar">Cancelar</button>${cand.length ? `<button type="button" class="btn btn-gold" data-dlg="juntar-ok">Juntar à fatura</button>` : ""}</div>`);
}

function tplSemen() {
  const X = S.semen, t = TOUROS.find((x) => x.id === X.touro), tot = r2(parseBR(X.doses) * parseBR(X.preco));
  return `<div id="topmsg">${tplTopMsg()}</div><form id="frm" class="lay" novalidate aria-label="Compra de sêmen"><div class="sheet"><section class="sec"><h2>Compra de sêmen</h2>
    <p class="hint" style="margin:-6px 0 14px;max-width:60ch">Soma as doses ao estoque de sêmen e gera a conta a pagar em 3.01.03.01 — Sêmen e material genético. Mesmo formulário de Animais › Comprar sêmen.</p>
    <div class="g2"><div class="fld"><label for="s-touro">Touro</label><select class="in" id="s-touro" data-b="semen.touro"><option value="">Escolha…</option>${TOUROS.map((t) => `<option value="${t.id}" ${X.touro === t.id ? "selected" : ""}>${t.nome} · ${t.id}</option>`).join("")}</select><div class="err" id="e-touro" hidden></div></div>
    <div class="fld"><label for="s-forn">Central / fornecedor</label><select class="in" id="s-forn" data-b="semen.forn">${["Central de Sêmen Exemplo", "Outra central"].map((x) => `<option ${X.forn === x ? "selected" : ""}>${x}</option>`).join("")}</select></div>
    <div class="fld"><label for="s-doses">Doses</label><input class="in r" id="s-doses" data-b="semen.doses" inputmode="numeric" value="${esc(X.doses)}" placeholder="0"><div class="err" id="e-doses" hidden></div></div>
    <div class="fld"><label for="s-preco">Preço por dose ${t ? `<span class="sug">tabela: ${BRL(t.dose)}</span>` : ""}</label><div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="s-preco" data-b="semen.preco" data-m inputmode="decimal" value="${esc(X.preco)}" placeholder="0,00"></div></div>
    <div class="fld"><label for="s-emi">Emissão</label><input type="date" class="in" id="s-emi" data-b="semen.emissao" value="${X.emissao}"></div>
    <div class="fld"><label for="s-venc">Vencimento</label><input type="date" class="in" id="s-venc" data-b="semen.venc" value="${X.venc}"></div></div></section></div>
    <aside class="rail" id="rail" aria-label="Efeito da compra"></aside><div class="actionbar" id="foot"></div></form>`;
}
function paintSemen() {
  const X = S.semen, t = TOUROS.find((x) => x.id === X.touro), d = parseBR(X.doses), tot = r2(d * parseBR(X.preco)), r = $("#rail"), f = $("#foot"); if (!r) return;
  r.innerHTML = `<section><h2>O que muda ao salvar</h2>${tot > 0 ? `<dl class="eff"><div><dt>Contas a pagar</dt><dd><span class="v">${BRL(tot)}</span><small>Vence ${fmtD(X.venc)} (${emDias(X.venc)}). Aparece em “${bucket(X.venc)}”.</small></dd></div>
    <div><dt>Estoque de sêmen</dt><dd><span class="v plus">+${d} doses</span><small>${t ? esc(t.nome) + " · " + t.id : "escolha o touro"}</small></dd></div>
    <div><dt>Resultado de ${mesLabel(X.emissao.slice(0, 8) + "01")}</dt><dd><span class="v minus">−${BRL(tot)}</span><small>Outros custeios · Reprodução e genética · Operacional</small></dd></div></dl>` : `<p class="empty-eff">Informe doses e preço para ver o efeito no estoque e nas contas.</p>`}</section>`;
  const falta = []; if (!X.touro) falta.push("touro"); if (!(d > 0)) falta.push("doses"); if (!(parseBR(X.preco) > 0)) falta.push("preço");
  f.innerHTML = `<div class="sum"><div class="t num">${BRL(tot)}</div>${falta.length ? `<span class="s miss">Falta: ${falta.join(", ")}</span>` : `<span class="s">${d} doses · vence ${fmtD(X.venc)}</span>`}</div><div class="acts"><button type="button" class="btn btn-gold" data-act="salvar-semen">Salvar compra</button></div>`;
}

/* ───────────────────────── sessão (extrato do que acabou de lançar) ───────────────────────── */
function tplSessao() {
  if (!S.sessao.length) return "";
  return `<section class="sessao" aria-labelledby="h-ses"><h2 id="h-ses">Lançado nesta sessão <span class="tiny">(${S.sessao.length})</span></h2>
    <div class="tblwrap"><table class="tbl lista"><thead><tr><th scope="col">Hora</th><th scope="col">Nº</th><th scope="col">${S.tipo === "despesa" ? "Fornecedor" : "Cliente"}</th><th scope="col">Item</th><th scope="col" class="r">Valor</th><th scope="col">Situação</th><th scope="col"><span class="sr">Ações</span></th></tr></thead><tbody>
    ${S.sessao.map((s) => `<tr data-new="${s.novo ? 1 : 0}"><td>${s.hora}</td><td><b>${s.id}</b></td><td>${esc(s.forn)}</td><td>${esc(s.item)}</td><td class="r"><b class="num">${BRL(s.valor)}</b></td><td><span class="st ${sitSimples(s.id)[0]}">${sitSimples(s.id)[1]}</span></td><td><button type="button" class="btn btn-ghost btn-sm" data-act="desfazer" data-v="${s.id}">${ic("undo")} Desfazer</button></td></tr>`).join("")}</tbody></table></div></section>`;
}
function paintSessao() { const s = $(".sessao"), tpl = tplSessao(); if (s) s.outerHTML = tpl || ""; else if (tpl) $(".page").insertAdjacentHTML("beforeend", tpl); }

/* ───────────────────────── Controle (resumido) ───────────────────────── */
function sit(l, tipo) {
  const d = diffDays(l.venc, TODAY);
  if (l.agendado && !l.pago) return ["info", `Agendada · ${fmtD(l.agendado)}`, "clock"];
  if (l.pago) return ["ok", tipo === "despesa" ? "Paga" : "Recebida", "check"];
  if (d < 0) return ["bad", `Vencida há ${-d} ${-d === 1 ? "dia" : "dias"}`, "alert"];
  if (d <= 7) return ["warn", d === 0 ? "Vence hoje" : `Vence em ${d} ${d === 1 ? "dia" : "dias"}`, "clock"];
  return ["info", `Em aberto · ${d} dias`, "clock"];
}
function tplContas(tipo) {
  const R = ROT[tipo], pagas = S.fcontas === "pagas", all = LANC.filter((l) => l.tipo === tipo);
  const abertas = all.filter((l) => !l.pago).sort((a, b) => (a.venc < b.venc ? -1 : 1)), quit = all.filter((l) => l.pago).sort((a, b) => (a.pago.data < b.pago.data ? 1 : -1));
  const tot = abertas.reduce((s, l) => s + l.valor, 0), venc = abertas.filter((l) => l.venc < TODAY), sete = abertas.filter((l) => l.venc >= TODAY && diffDays(l.venc, TODAY) <= 7);
  const grupos = ["Vencidas", "Até 7 dias", "De 8 a 14 dias", "Depois de 14 dias"], M = S.msgC;
  const linhaAberta = (l) => { const s = sit(l, tipo); return `<tr ${S.novoId === l.id ? 'data-new="1"' : ""}><td><span class="st ${s[0]}">${ic(s[2])} ${s[1]}</span></td><td class="num">${fmtD(l.venc)}</td><td>${esc(l.item)}${l.parcela ? ` <span class="tiny">(${l.parcela})</span>` : ""}<span class="sub"><span class="tag">${esc(l.centro)}</span> ${l.id}${l.doc ? " · " + esc(l.doc) : ""}</span></td><td>${esc(l.forn)}</td><td class="r"><b class="num">${BRL(l.valor)}</b></td><td><button type="button" class="btn btn-pri btn-sm" data-act="baixa" data-v="${l.id}|${l.venc}" aria-label="${tipo === "despesa" ? "Dar baixa" : "Receber"}: ${esc(l.forn)}, ${BRL(l.valor)}">${tipo === "despesa" ? "Dar baixa" : "Receber"}</button></td></tr>`; };
  return `<nav class="modtabs" aria-label="Controle financeiro"><span class="on" aria-current="page">Contas</span><button type="button" aria-disabled="true" tabindex="-1">Resumo</button><button type="button" aria-disabled="true" tabindex="-1">Consultas</button><button type="button" aria-disabled="true" tabindex="-1">Relatórios</button></nav>
  <div class="page"><div class="pagehead"><div><h1 tabindex="-1">${R.conta}</h1><p>${tipo === "despesa" ? "Tudo que ainda não foi pago, do mais urgente ao mais distante." : "Tudo que ainda não foi recebido, do mais urgente ao mais distante."} Dê baixa sem sair da lista.</p></div>
    <button type="button" class="btn btn-pri" data-act="novo-da-lista" data-v="${tipo}">${ic("plus")} Novo lançamento</button></div>
    ${M ? `<div class="done" role="status" tabindex="-1" id="donecard"><h2>${ic("check")} ${esc(M.titulo)}</h2><p>${M.resumo}</p><div class="row"><button type="button" class="btn btn-ghost btn-sm" data-act="desfaz-baixa" data-v="${esc(M.key)}">${ic("undo")} Desfazer baixa</button></div></div>` : ""}
    <div class="tabs" role="tablist" aria-label="Contas"><button role="tab" aria-selected="${tipo === "despesa"}" data-nav="pagar" id="ct-p">Contas a pagar</button><button role="tab" aria-selected="${tipo === "receita"}" data-nav="receber" id="ct-r">Contas a receber</button></div>
    <div class="kpis"><div><div class="k">Total em aberto</div><div class="v">${BRL(tot)}</div><div class="s">${abertas.length} ${abertas.length === 1 ? "conta" : "contas"}</div></div>
      <div class="${venc.length ? "bad" : ""}"><div class="k">Vencidas</div><div class="v">${BRL(venc.reduce((s, l) => s + l.valor, 0))}</div><div class="s">${venc.length} ${venc.length === 1 ? "conta" : "contas"}</div></div>
      <div class="${sete.length ? "warn" : ""}"><div class="k">Vencem em 7 dias</div><div class="v">${BRL(sete.reduce((s, l) => s + l.valor, 0))}</div><div class="s">${sete.length} ${sete.length === 1 ? "conta" : "contas"}</div></div></div>
    <div class="chips" role="group" aria-label="Mostrar" style="margin-bottom:12px"><button type="button" class="chip" data-act="fconta" data-v="abertas" aria-pressed="${!pagas}">Em aberto (${abertas.length})</button><button type="button" class="chip" data-act="fconta" data-v="pagas" aria-pressed="${pagas}">${tipo === "despesa" ? "Pagas" : "Recebidas"} (${quit.length})</button></div>
    ${pagas ? (quit.length ? `<div class="tblwrap"><table class="tbl lista"><thead><tr><th scope="col">Situação</th><th scope="col">${tipo === "despesa" ? "Pago" : "Recebido"} em</th><th scope="col">Descrição</th><th scope="col">${R.forn}</th><th scope="col" class="r">Valor</th><th scope="col">Forma</th></tr></thead><tbody>${quit.map((l) => `<tr ${S.novoId === l.id ? 'data-new="1"' : ""}><td><span class="st ok">${ic("check")} ${tipo === "despesa" ? "Paga" : "Recebida"}</span></td><td class="num">${fmtD(l.pago.data)}</td><td>${esc(l.item)}${l.parcela ? ` <span class="tiny">(${l.parcela})</span>` : ""}<span class="sub"><span class="tag">${esc(l.centro)}</span> ${l.id}${l.doc ? " · " + esc(l.doc) : ""}</span></td><td>${esc(l.forn)}</td><td class="r"><b class="num">${BRL(l.pago.valor)}</b>${Math.abs(l.pago.valor - l.valor) > 0.005 ? `<span class="sub">nota ${BRL(l.valor)}</span>` : ""}</td><td>${esc(l.pago.forma)} · ${esc(BANCOS[l.pago.banco].nome)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="note info">${ic("info")}<div>Nenhuma conta ${tipo === "despesa" ? "paga" : "recebida"} ainda.</div></div>`)
    : abertas.length ? `<div class="tblwrap"><table class="tbl lista"><thead><tr><th scope="col">Situação</th><th scope="col">Vencimento</th><th scope="col">Descrição</th><th scope="col">${R.forn}</th><th scope="col" class="r">Valor</th><th scope="col"><span class="sr">Ação</span></th></tr></thead><tbody>
    ${grupos.map((g) => { const L = abertas.filter((l) => bucket(l.venc) === g); if (!L.length) return ""; return `<tr class="grp-h"><td colspan="6">${g} · ${L.length} ${L.length === 1 ? "lançamento" : "lançamentos"} <span style="float:right" class="num">${BRL(L.reduce((s, l) => s + l.valor, 0))}</span></td></tr>` + L.map(linhaAberta).join(""); }).join("")}</tbody></table></div>` : `<div class="note info">${ic("info")}<div><b>Nada em aberto.</b> Tudo o que foi lançado já foi ${tipo === "despesa" ? "pago" : "recebido"}. <button type="button" class="link" data-act="novo-da-lista" data-v="${tipo}">Lançar uma conta</button></div></div>`}
  </div>`;
}
function abrirBaixa(key) {
  const [id, venc] = key.split("|"), l = LANC.find((x) => x.id === id && x.venc === venc && !x.pago); if (!l) return; window._baixaL = l; const R = ROT[l.tipo];
  dlg(`<div class="dh"><h2 id="dlg-t">${l.tipo === "despesa" ? "Dar baixa" : "Registrar recebimento"} · ${esc(l.forn)}</h2></div><div class="db">
    <p>${esc(l.item)}${l.parcela ? ` (${l.parcela})` : ""} · vence ${fmtD(l.venc)} · <b class="num">${BRL(l.valor)}</b></p>
    <div class="g2"><div class="fld"><label for="bx-data">Data do ${R.data}</label><input type="date" class="in" id="bx-data" value="${TODAY}"></div>
    <div class="fld"><label for="bx-banco">Conta bancária</label><select class="in" id="bx-banco">${BANCOS.map((b) => `<option value="${b.id}">${b.nome} · ${b.sub}</option>`).join("")}</select></div>
    <div class="fld"><label for="bx-valor">Valor ${l.tipo === "despesa" ? "pago" : "recebido"}</label><div class="pre"><span aria-hidden="true">R$</span><input class="in r" id="bx-valor" inputmode="decimal" value="${fmtNum(l.valor)}"></div></div>
    <div class="fld"><label for="bx-forma">Forma</label><select class="in" id="bx-forma">${FORMAS.map((f) => `<option>${f}</option>`).join("")}</select></div></div>
    <div class="hint" id="bx-dif" aria-live="polite"></div></div>
    <div class="df"><button type="button" class="btn btn-ghost" data-dlg="revisar">Cancelar</button><button type="button" class="btn btn-gold" data-dlg="baixa-ok" id="bx-ok">${l.tipo === "despesa" ? "Confirmar baixa" : "Confirmar recebimento"} de ${BRL(l.valor)}</button></div>`);
  updBaixa();
}
function updBaixa() {
  const l = window._baixaL, v = parseBR($("#bx-valor")?.value), d = $("#bx-data")?.value, h = $("#bx-dif"), ok = $("#bx-ok"); if (!l || !h) return;
  const dif = r2(v - l.valor); let m = "";
  if (Math.abs(dif) >= 0.005) m += `<b style="color:${dif < 0 ? "var(--ok)" : "var(--warn)"}">${dif < 0 ? "Desconto de " : "Juros/multa de "}${BRL(Math.abs(dif))}</b>: vai para “Outras receitas e despesas”, não para o item. `;
  if (d > TODAY) m += `Data futura: vira ${l.tipo === "despesa" ? "pagamento" : "recebimento"} agendado e não mexe no saldo de hoje.`;
  h.innerHTML = m; if (ok) ok.textContent = `${d > TODAY ? "Agendar" : l.tipo === "despesa" ? "Confirmar baixa" : "Confirmar recebimento"} de ${BRL(v)}`;
}
function confirmarBaixa() {
  const l = window._baixaL, v = parseBR($("#bx-valor").value), d = $("#bx-data").value, b = +$("#bx-banco").value, f = $("#bx-forma").value, h = $("#bx-dif"); if (!l) return false;
  const erro = !(v > 0) ? "Informe o valor." : !d ? "Informe a data." : mesFechado(d) ? `${mesLong(mesFechado(d))} está fechado: escolha uma data em um mês aberto.` : d < l.emissao ? `A data (${fmtD(d)}) é anterior à emissão (${fmtD(l.emissao)}).` : "";
  if (erro) { h.innerHTML = `<span style="color:var(--bad);font-weight:600">${ic("alert")} ${esc(erro)}</span>`; return false; }
  const key = l.id + "|" + l.venc, R = ROT[l.tipo];
  if (d > TODAY) { l.agendado = d; l.forma = f; l.banco = b; S.msgC = { key, titulo: `${l.tipo === "despesa" ? "Pagamento" : "Recebimento"} agendado: ${l.forn}`, resumo: `${BRL(v)} para ${fmtD(d)} (${esc(f)}). A conta continua em aberto até lá; o saldo de hoje não muda.` }; }
  else { l.pago = { data: d, valor: v, banco: b, forma: f }; BANCOS[b].saldo = r2(BANCOS[b].saldo + R.sinal * v); S.msgC = { key, titulo: `Baixa registrada: ${l.forn}`, resumo: `<b class="num">${BRL(v)}</b> em ${fmtD(d)} · ${esc(f)} · ${esc(BANCOS[b].nome)}. Saldo agora <b class="num">${BRL(BANCOS[b].saldo)}</b>.${Math.abs(v - l.valor) >= 0.005 ? ` ${v < l.valor ? "Desconto" : "Juros/multa"} de ${BRL(Math.abs(v - l.valor))} registrado.` : ""}` }; }
  window._baixaL = null; render(); const c = $("#donecard"); if (c) c.focus({ preventScroll: true }); say(`${S.msgC.titulo}. ${BRL(v)}.`); return true;
}
function desfazBaixa(key) {
  const [id, venc] = key.split("|"), l = LANC.find((x) => x.id === id && x.venc === venc); if (!l) return;
  if (l.pago) { BANCOS[l.pago.banco].saldo = r2(BANCOS[l.pago.banco].saldo - ROT[l.tipo].sinal * l.pago.valor); l.pago = undefined; } l.agendado = undefined;
  S.msgC = null; render(); say("Baixa desfeita: a conta voltou para em aberto e o saldo foi restaurado."); afterAction();
}

/* ───────────────────────── combobox ───────────────────────── */
function hl(t, q) { if (!q) return esc(t); const i = t.toLowerCase().indexOf(q.toLowerCase()); return i < 0 ? esc(t) : esc(t.slice(0, i)) + "<mark>" + esc(t.slice(i, i + q.length)) + "</mark>" + esc(t.slice(i + q.length)); }
const norm = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
function comboOpts(kind, q, i) {
  const tipo = S.tipo, nq = norm(q), out = [];
  if (kind === "forn") {
    const names = Object.keys(fornDe(tipo)).filter((n) => !nq || norm(n).includes(nq));
    names.forEach((n) => { const x = contextoDe(n, tipo); out.push({ v: n, l: n, s: x.n ? `Em aberto ${BRL(x.aberto)} · último em ${fmtD(x.ultimo)}` : "Sem contas em aberto" }); });
    if (q.trim() && !Object.keys(fornDe(tipo)).some((n) => norm(n) === nq)) out.push({ v: q.trim(), l: `Cadastrar “${q.trim()}” como novo ${ROT[tipo].forn.toLowerCase()}`, s: "Sem histórico ainda", novo: true });
  } else if (kind === "prod") {
    const cat = catalogo(tipo), a = cat.filter((x) => x.estoque && (!nq || norm(x.nome).includes(nq))), b = cat.filter((x) => !x.estoque && (!nq || norm(x.nome).includes(nq)));
    if (a.length) { out.push({ h: "Do estoque" }); a.forEach((x) => out.push({ v: x.nome, l: x.nome, s: `${x.un}${x.preco ? " · último preço " + BRL(x.preco) : ""}` })); }
    if (b.length) { out.push({ h: "Serviços e outros já lançados" }); b.forEach((x) => out.push({ v: x.nome, l: x.nome, s: x.bem ? "Bem do imobilizado" : "Serviço" })); }
    if (q.trim() && ![...a, ...b].some((x) => norm(x.nome) === nq)) out.push({ v: q.trim(), l: `Usar “${q.trim()}” como texto livre`, s: "Não entra no estoque", livre: true });
  } else if (kind === "conta") {
    const L = contasDe(tipo).filter(([c, n]) => !(tipo === "receita" && c.startsWith("2.01.02")) && (!nq || norm(n).includes(nq) || c.includes(nq) || norm(grupoDe(c)).includes(nq)));
    let g = ""; L.forEach(([c, n]) => { const gg = grupoDe(c); if (gg !== g) { out.push({ h: gg }); g = gg; } out.push({ v: c, l: n, s: c }); });
  }
  return out;
}
let comboCur = null;
function openCombo(inp) {
  const box = inp.closest(".combo"), kind = box.dataset.combo, ul = $("ul", box), i = box.dataset.i != null ? +box.dataset.i : null;
  comboCur = { inp, ul, kind, i, act: -1 };
  const q = inp.value.trim() && inp.dataset.pristine !== "1" ? inp.value : inp.dataset.q === "1" ? inp.value : "";
  const opts = comboOpts(kind, inp.dataset.q === "1" ? inp.value : "", i); comboCur.opts = opts;
  ul.innerHTML = opts.length ? opts.map((o, k) => (o.h ? `<li role="presentation">${esc(o.h)}</li>` : `<li role="option" id="${ul.id}-${k}" data-k="${k}"><span>${hl(o.l, inp.dataset.q === "1" ? inp.value : "")}</span><small>${esc(o.s || "")}</small></li>`)).join("") : `<li class="empty" role="presentation">Nada encontrado. Tente outra palavra.</li>`;
  ul.hidden = false; inp.setAttribute("aria-expanded", "true");
}
function closeCombo() { if (!comboCur) return; comboCur.ul.hidden = true; comboCur.inp.setAttribute("aria-expanded", "false"); comboCur.inp.removeAttribute("aria-activedescendant"); comboCur = null; }
function moveCombo(d) {
  const c = comboCur; if (!c) return; const idx = c.opts.map((o, k) => (o.h ? -1 : k)).filter((k) => k >= 0); if (!idx.length) return;
  let p = idx.indexOf(c.act); p = p < 0 ? (d > 0 ? 0 : idx.length - 1) : (p + d + idx.length) % idx.length; c.act = idx[p];
  $$("li[role=option]", c.ul).forEach((li) => li.setAttribute("aria-selected", +li.dataset.k === c.act ? "true" : "false"));
  const li = $(`li[data-k="${c.act}"]`, c.ul); if (li) { c.inp.setAttribute("aria-activedescendant", li.id); li.scrollIntoView({ block: "nearest" }); }
}
function pickCombo(k) {
  const c = comboCur; if (!c) return; const o = c.opts[k]; if (!o || o.h) return; const { kind, i, inp } = c; closeCombo();
  if (kind === "forn") { if (S.view === "lancar" && S.tipo === "despesa" && S.sub.despesa === "lote") { S.lote.forn = o.v; inp.value = o.v; paintLote(); } else aplicarForn(o.v, o.novo); }
  if (kind === "prod") escolherProduto(i, o);
  if (kind === "conta") { const it = F_().itens[i]; it.conta = o.v; it.editConta = false; it.sug = ""; if (o.v === "3.03.01.17") it.vale = true; afterConta(); paintMeta(i); const t = $(`#f-it${i}-conta`); if (t) t.focus(); }
}

/* ───────────────────────── ações de domínio ───────────────────────── */
function aplicarForn(nome, novo) {
  const tipo = S.tipo, F = F_(), f = fornDe(tipo)[nome]; F.fornecedor = nome; F.novoForn = !!novo; F.dupOk = false;
  const inp = $("#f-forn"); if (inp) inp.value = nome;
  if (f) {
    const it0 = F.itens[0], vazio = !it0.produto.trim();
    if (vazio && S.sub[tipo] !== "leite") { it0.produto = f.item; it0.conta = f.conta; it0.sug = `sugerido pelo último lançamento de ${nome.split(" ")[0]}`; const up = ultimoPreco(f.item, tipo) || (itemInfo(tipo, f.item)?.preco && { unit: itemInfo(tipo, f.item).preco }); if (up && itemInfo(tipo, f.item)?.estoque) { it0.unit = fmtNum(up.unit); it0.edit = "unit"; it0.total = ""; } }
    if (!F.vencTocado && !F.pago) { F.venc = addDays(F.emissao, f.prazo); F.sug.venc = `${f.prazo} dias, como de costume`; }
    F.forma = f.forma; F.banco = f.banco; F.sug.forma = "lembrada"; F.sug.banco = "lembrada";
    if (F.parc) gerarParcelas(F);
  }
  F.itens.forEach((_, k) => recalcLinha(k));
  S.pedidoAberto = false; $$(".chip[data-act=pick-forn]").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.v === nome)));
  const ped = $("#pedidos"); if (ped) ped.innerHTML = tplPedidos(tipo);
  paintItens(); paintDatas(); paintPag(); paintRail(); paintFoot();
  paintFornAviso(); revalidar();
  if (S.sub[tipo] === "leite") { const q = $("#f-litros"); if (q) q.focus(); }
  else if (f) { const q = $("#f-it0-qtd"); if (q) q.focus(); } else { const q = $(F.itens[0].produto ? "#f-it0-qtd" : "#f-it0-prod"); if (q) q.focus(); }
  say(f ? `${nome} escolhido. Sugerimos item, conta, prazo e forma pelo último lançamento.` : `${nome} escolhido.`);
}
function escolherProduto(i, o) {
  const tipo = S.tipo, F = F_(), it = F.itens[i], info = itemInfo(tipo, o.v);
  it.produto = o.v; it.vale = false; it.valeFunc = ""; it.valeOk = false; it.editConta = false;
  if (info) {                                   // trocar de item SEMPRE troca conta, preço e sugestão
    it.conta = info.conta; it.sug = "sugerida pelo cadastro do item";
    const up = info.estoque ? ultimoPreco(o.v, tipo) : null, p = up ? up.unit : info.preco;
    if (it.edit !== "total") it.unit = info.estoque && p ? fmtNum(p) : "";
  } else { it.conta = null; it.sug = ""; if (it.edit !== "total") it.unit = ""; }
  if (it.edit !== "total") it.total = "";
  const inp = $(`#f-it${i}-prod`); if (inp) inp.value = o.v;
  afterConta(); recalcLinha(i); paintMeta(i); paintRail(); paintFoot(); revalidar();
  const q = $(`#f-it${i}-qtd`); if (q) q.focus();
}
function afterConta() { paintAdv(); paintRail(); paintFoot(); }
function paintAdv() { /* natureza muda a dica do avançado */ const a = $("#adv"); if (!a) return; const open = a.open; const t = document.createElement("div"); t.innerHTML = tplAvancado(); a.replaceWith(t.firstElementChild); $("#adv").open = open; }
function syncLinhaDom(i) {
  const it = F_().itens[i];
  [["qtd", it.qtd], ["unit", it.unit], ["total", it.total]].forEach(([k, v]) => { const e = $(`#f-it${i}-${k}`); if (e && document.activeElement !== e) e.value = v; });
}
function recalcLinha(i) {
  const F = F_(), it = F.itens[i], q = parseBR(it.qtd) || 1;
  if (it.edit === "total") { const t = parseBR(it.total); it.unit = it.qtd && t ? fmtNum(r2(t / q)) : ""; }
  else { const t = it.unit !== "" ? itemTotal(it) : 0; it.total = t ? fmtNum(t) : ""; }
  syncLinhaDom(i); paintMeta(i); paintTotais();
  if (F.parc && !F.parcEdit) gerarParcelas(F);
  if (F.parc) { const p = $("#parcs"); if (p) p.innerHTML = tplParcelas(); }
  if (F.pago && !F.valorPagoTocado) { const v = calc(F).liq; F.valorPago = v ? fmtNum(v) : ""; const e = $("#f-valorpago"); if (e && document.activeElement !== e) e.value = F.valorPago; paintDif(); }
}
function setPath(path, val) {
  const ks = path.split("."); let o = S; if (ks[0] === "f") { ks.shift(); o = F_(); }
  else if (ks[0] === "lote") { o = S; } else if (ks[0] === "semen") { o = S; } else { o = F_(); }
  for (let i = 0; i < ks.length - 1; i++) o = o[ks[i]]; o[ks[ks.length - 1]] = val;
}
function afterChange(path) {
  const F = F_(), tipo = S.tipo;
  if (path.startsWith("lote.")) { paintLote(); revalidar(); return; }
  if (path.startsWith("semen.")) { if (path === "semen.touro") { const t = TOUROS.find((x) => x.id === S.semen.touro); if (t && !S.semen.preco) S.semen.preco = fmtNum(t.dose); } paintSemen(); revalidar(); return; }
  const m = path.match(/^itens\.(\d+)\.(\w+)$/);
  if (m) { const i = +m[1], k = m[2]; const it = F.itens[i]; if (k === "unit") it.edit = "unit"; if (k === "total") it.edit = "total"; if (k === "valeFunc") { if (!F.fornecedor.trim() && it.valeFunc) { F.fornecedor = it.valeFunc; F.novoForn = true; const fe = $("#f-forn"); if (fe) fe.value = it.valeFunc; } paintMeta(i); } recalcLinha(i); if (k === "valeFunc") { const sf = $(`#f-it${i}-func`); if (sf) sf.focus(); } }
  if (path === "emissao") { if (!F.vencTocado && FORN[F.fornecedor] && !F.pago) { F.venc = addDays(F.emissao, (fornDe(tipo)[F.fornecedor] || {}).prazo || 30); } if (F.parc && !F.parcEdit) { gerarParcelas(F); const pp = $("#parcs"); if (pp) pp.innerHTML = tplParcelas(); } const h = $("#h-comp"); if (h) h.innerHTML = compHint(); const ve = $("#f-venc"); if (ve && document.activeElement !== ve) ve.value = F.venc; F.lido.emissao = false; paintVencHint(); paintCompField(); }
  if (path === "venc") { F.vencTocado = true; F.sug.venc = ""; paintVencHint(); if (F.parc && !F.parcEdit) { gerarParcelas(F); const p = $("#parcs"); if (p) p.innerHTML = tplParcelas(); } }
  if (path === "nParc") { const n = Math.max(2, Math.min(36, Math.round(+F.nParc) || 2)); F.parcEdit = false; F.nParc = n; gerarParcelas(F); const p = $("#parcs"); if (p) p.innerHTML = tplParcelas(); $$(".chip[data-act=nparc]").forEach((c) => c.setAttribute("aria-pressed", String(+c.dataset.v === n))); }
  if (path.startsWith("parcelas.") && false) { F.parcEdit = true; const p = $("#parcs"); const act = document.activeElement; if (path.endsWith(".valor")) { const soma = r2(F.parcelas.reduce((s, x) => s + parseBR(x.valor), 0)); const ft = p && $("tfoot td.r", p); if (ft) { ft.textContent = BRL(soma); ft.style.color = Math.abs(soma - calc(F).liq) > 0.01 ? "var(--bad)" : "inherit"; $("tfoot td:last-child", p).textContent = Math.abs(soma - calc(F).liq) > 0.01 ? "Difere de " + BRL(calc(F).liq) : "Confere com a nota"; } } }
  { const mp = path.match(/^parcelas\.(\d+)\.valor$/); if (mp) { F.parcEdit = true; const i = +mp[1], n = F.parcelas.length; if (i < n - 1) { const outras = F.parcelas.slice(0, n - 1).reduce((s, p) => s + parseBR(p.valor), 0), ult = r2(calc(F).liq - outras); if (ult > 0) { F.parcelas[n - 1].valor = ult; const e = $(`#f-par${n - 1}-valor`); if (e && document.activeElement !== e) e.value = fmtNum(ult); } } paintPfoot(); } else if (path.startsWith("parcelas.")) F.parcEdit = true; }
  if (path === "valorPago") { F.valorPagoTocado = true; paintDif(); }
  if (path === "pagoData") { paintPag(); } if (path === "banco") paintDif();
  if (path === "desc" || path === "acr") { if (S.sub[tipo] === "leite" && path === "ret") { } paintTotais(); if (F.pago && !F.valorPagoTocado) { F.valorPago = fmtNum(calc(F).liq); const e = $("#f-valorpago"); if (e) e.value = F.valorPago; paintDif(); } if (F.parc && !F.parcEdit) { gerarParcelas(F); const p = $("#parcs"); if (p) p.innerHTML = tplParcelas(); } }
  if (path.startsWith("leite.")) { syncLeite(); }
  if (path === "natureza" || path === "comp") { paintAdvNat(); }
  paintRail(); paintFoot(); saveDraft(); revalidar();
}
function paintCompField() { const c = $("#f-comp"); if (c && document.activeElement !== c) c.value = compDe(F_()); }
function natHint() { const F = F_(); const nat = F.natureza || (F.itens[0].conta ? naturezaAuto(F.itens[0].conta) : "OPERACIONAL"); return NATUREZAS[nat][1] + (F.natureza ? "" : " Só mude se o contador pedir."); }
function paintAdvNat() { const h = $("#h-nat"); if (h) h.textContent = natHint(); const h2 = $("#h-comp"); if (h2) h2.innerHTML = compHint(); }
function syncLeite() {
  const F = F_(), L = F.leite, it = F.itens[0], litros = parseBR(L.litros), preco = parseBR(L.preco), bruto = r2(litros * preco);
  it.produto = "Leite"; it.conta = "2.01.01.01"; it.qtd = L.litros; it.unit = L.preco; it.edit = "unit"; it.total = fmtNum(bruto);
  if (!F.retTocado) F.desc = bruto ? fmtNum(r2(bruto * (parseBR(L.retPct) / 100))) : "";
  F.comp = L.mes; F.lido.litros = false; if (F.pago && !F.valorPagoTocado) F.valorPago = fmtNum(calc(F).liq);
  const e = $("#itens"); const act = document.activeElement && document.activeElement.id; e.innerHTML = tplLeite(); if (act) { const a = $("#" + act); if (a) { a.focus(); try { a.setSelectionRange(a.value.length, a.value.length); } catch (_) {} } }
}
function limparErro(path) { if (S.msg && S.msg.kind === "err") { S.msg = null; paintTop(); $$("[aria-invalid]").forEach((e) => e.removeAttribute("aria-invalid")); $$(".err").forEach((e) => (e.hidden = true)); } }

/* ───────────────────────── salvar ───────────────────────── */
function markErros(E) {
  $$("[aria-invalid]").forEach((e) => { e.removeAttribute("aria-invalid"); e.removeAttribute("aria-describedby"); });
  $$(".err").forEach((e) => (e.hidden = true));
  E.forEach((e) => {
    const el = $("#" + e.id), m = e.id.match(/^f-it(\d+)-/), box = m ? $("#e-it" + m[1]) : $("#e-" + e.id.replace(/^(f|l|s)-/, ""));
    if (el && "value" in el) { el.setAttribute("aria-invalid", "true"); if (box) el.setAttribute("aria-describedby", box.id); }
    if (box) { box.hidden = false; box.innerHTML = ic("alert") + `<span>${esc(e.msg)}</span>`; }
  });
}
function validarAtual() { const t = S.tipo, sub = S.sub[t]; if (t === "despesa" && sub === "lote") return validarLote(); if (t === "despesa" && sub === "semen") return validarSemen(); return validar(t, sub); }
function revalidar() {
  if (!(S.msg && S.msg.kind === "err") || !$("#frm")) return;
  const E = validarAtual();
  if (!E.length) { S.msg = null; paintTop(); markErros([]); return; }
  S.msg = { kind: "err", erros: E }; paintTop(); markErros(E);
}
function mostrarErros(E) {
  S.msg = { kind: "err", erros: E }; paintTop(); markErros(E);
  const s = $("#errsum"); if (s) { s.focus(); s.scrollIntoView({ block: "center" }); }
  say(`${E.length} ${E.length === 1 ? "item precisa" : "itens precisam"} de atenção: ${E[0].msg}`);
}
function salvar(modo) {
  const tipo = S.tipo, sub = S.sub[tipo], F = F_();
  if (sub === "leite") syncLeiteSilent();
  { const cn = fornCanonico(tipo, F.fornecedor); if (cn && cn !== F.fornecedor) { F.fornecedor = cn; const fe = $("#f-forn"); if (fe) fe.value = cn; } }
  const E = validar(tipo, sub);
  if (E.length) { mostrarErros(E); return; }
  const dup = achaDuplicado(F, tipo, sub);
  if (dup && !F.dupOk) { abrirDup(dup, () => { F.dupOk = true; salvar(modo); }, sub); return; }
  gravar(tipo, sub, modo);
}
function fornCanonico(tipo, n) { return Object.keys(fornDe(tipo)).find((k) => norm(k) === norm(n.trim())) || null; }
function fornPendente(tipo) { const F = S.F[tipo], n = F.fornecedor.trim(); return !!n && !fornCanonico(tipo, n) && !F.novoForn; }
function paintFornAviso() {
  const e = $("#forn-aviso"); if (!e) return; const tipo = S.tipo, F = F_();
  if (S.sub[tipo] === "lote" || !fornPendente(tipo)) { e.innerHTML = ""; return; }
  const n = F.fornecedor.trim(), q = norm(n).slice(0, 4), sug = Object.keys(fornDe(tipo)).find((x) => norm(x).includes(q));
  e.innerHTML = `<div class="note warn">${ic("alert")}<div><b>“${esc(n)}” não está no cadastro.</b> ${sug ? `Você quis dizer <button type="button" class="link" data-act="pick-forn" data-v="${esc(sug)}">${esc(sug)}</button>? Ou ` : ""}<button type="button" class="link" data-act="forn-novo">cadastrar “${esc(n)}” como ${tipo === "despesa" ? "fornecedor novo" : "cliente novo"}</button>.</div></div>`;
}
function syncLeiteSilent() { const F = F_(), L = F.leite, it = F.itens[0]; it.produto = "Leite"; it.conta = "2.01.01.01"; it.qtd = L.litros; it.unit = L.preco; it.edit = "unit"; F.comp = L.mes; }
function gravar(tipo, sub, modo) {
  const F = F_(), R = ROT[tipo], c = calc(F), id = proxNumero(), itensInfo = F.itens.filter((i) => i.produto.trim());
  const nomeItem = sub === "leite" ? `Leite — ${mesLong(F.leite.mes)}` : itensInfo[0].produto + (itensInfo.length > 1 ? ` +${itensInfo.length - 1}` : "");
  const agendado = F.pago && F.pagoData > TODAY, vp = parseBR(F.valorPago), nomeForn = F.fornecedor;
  const base = { id, tipo, forn: F.fornecedor, item: nomeItem, emissao: F.emissao, doc: F.doc || "", conta: F.itens[0].conta, centro: F.centro, mes: sub === "leite" ? F.leite.mes : undefined };
  const q1 = parseBR(F.itens[0].qtd) || undefined, u1 = parseBR(F.itens[0].unit) || undefined;
  if (F.pago && !agendado) { LANC.push({ ...base, valor: c.liq, venc: F.pagoData, qtd: q1, unit: u1, pago: { data: F.pagoData, valor: vp, banco: F.banco, forma: F.forma } }); BANCOS[F.banco].saldo = r2(BANCOS[F.banco].saldo + R.sinal * vp); }
  else if (agendado) LANC.push({ ...base, valor: c.liq, venc: F.pagoData, qtd: q1, unit: u1, agendado: F.pagoData, forma: F.forma, banco: F.banco });
  else if (F.parc) F.parcelas.forEach((p, i) => LANC.push({ ...base, valor: parseBR(p.valor), venc: p.venc, parcela: `${i + 1}/${F.parcelas.length}`, pago: p.paga ? { data: TODAY, valor: parseBR(p.valor), banco: F.banco, forma: F.forma } : undefined }));
  else LANC.push({ ...base, valor: c.liq, venc: F.venc, qtd: q1, unit: u1 });
  F.parcelas && F.parc && F.parcelas.forEach((p) => { if (p.paga) BANCOS[F.banco].saldo = r2(BANCOS[F.banco].saldo + R.sinal * parseBR(p.valor)); });
  const vale = F.itens.find((i) => i.vale && i.valeFunc);
  if (vale) { const f = FUNCIONARIOS.find((x) => x.nome === vale.valeFunc); if (f) { f.vales = r2(f.vales + itemTotal(vale)); LANC.find((l) => l.id === id).valeDe = { func: f.nome, valor: itemTotal(vale) }; } }
  if (F.pedido) PEDIDOS.despesa = PEDIDOS.despesa.filter((p) => p.id !== F.pedido);
  const avisos = [];
  itensInfo.forEach((it) => { if (!itemInfo(tipo, it.produto) && tipo === "despesa" && estocavel(it.conta)) avisos.push(`<b>${esc(it.produto)}</b> não está no estoque desta fazenda. O lançamento foi gravado <b>sem baixa de estoque</b>. <button type="button" class="link" data-act="cadastrar-item" data-v="${esc(it.produto)}">Cadastrar o item</button>`); });
  const nat = F.natureza || naturezaAuto(F.itens[0].conta);
  if (nat === "INVESTIMENTO" && tipo === "despesa") avisos.push(F.criarBem ? `Bem criado no Patrimônio: depreciação em ${esc(F.vidaUtil || "10")} anos${parseBR(F.residual) ? `, valor residual ${BRL(parseBR(F.residual))}` : ""}.` : "Sem bem no Patrimônio, este valor sai do resultado e <b>não vai depreciar</b>. Cadastre o bem depois.");
  if (tipo === "despesa" && !F.entregue) avisos.push(`Mercadoria ainda não entregue: o estoque só recebe a entrada quando ela chegar${F.prevista ? ` (prevista para ${fmtD(F.prevista)})` : ""}.`);
  const quando = F.pago ? (agendado ? `pagamento agendado para ${fmtD(F.pagoData)} (${esc(F.forma)}); fica em aberto até lá` : `${tipo === "despesa" ? "paga" : "recebida"} em ${fmtD(F.pagoData)} (${esc(F.forma)})`) : F.parc ? `${F.parcelas.length}× de ${BRL(parseBR(F.parcelas[0].valor))}, 1ª em ${fmtD(F.parcelas[0].venc)}` : `vence ${fmtD(F.venc)} (${emDias(F.venc)})`;
  const ehSan = ["3.01.02.01", "3.01.02.02", "3.01.02.03", "3.01.03.02"].includes(F.itens[0].conta);
  S.msg = { kind: "done", id, view: R.view, fconta: F.pago && !agendado ? "pagas" : "abertas", titulo: `Lançamento ${id} gravado`, resumo: `<b>${esc(F.fornecedor)}</b> · ${esc(nomeItem)} · <b class="num">${BRL(c.liq)}</b> · ${quando}.`, avisos, vinculo: ehSan ? { estado: "aberto" } : null };
  S.sessao.unshift({ id, hora: new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }), forn: F.fornecedor, item: nomeItem, valor: c.liq, novo: true });
  S.novoId = id; S.ultimo = JSON.parse(JSON.stringify(F)); LS.del(draftKey(tipo));
  const manter = modo === "outro" ? { centro: F.centro, forma: F.forma, banco: F.banco, sug: { forma: F.sug.forma, banco: F.sug.banco }, leite: { ...novoForm(tipo).leite, mes: F.leite.mes, retPct: F.leite.retPct, preco: F.leite.preco } } : null;
  S.F[tipo] = novoForm(tipo); if (manter) Object.assign(S.F[tipo], manter);
  render(); say(`Lançamento ${id} gravado. ${nomeForn}, ${BRL(c.liq)}.`);
  if (modo === "outro") { aplicarForn(nomeForn); window.scrollTo({ top: 0 }); const m = $("#main"); if (m) m.scrollTop = 0; }
  else { const d = $("#donecard"); if (d) { d.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: "smooth" }); const m = $("#main"); if (m) m.scrollTop = 0; } }
}
function estornaLinha(l) {
  if (l.pago) { BANCOS[l.pago.banco].saldo = r2(BANCOS[l.pago.banco].saldo - (l.tipo === "despesa" ? -1 : 1) * l.pago.valor); }
  if (l.valeDe) { const f = FUNCIONARIOS.find((x) => x.nome === l.valeDe.func); if (f) f.vales = r2(f.vales - l.valeDe.valor); }
}
function desfazer(id) {
  const L = LANC.filter((l) => l.id === id), n = L.length; L.forEach(estornaLinha);
  for (let i = LANC.length - 1; i >= 0; i--) if (LANC[i].id === id) LANC.splice(i, 1);
  S.sessao = S.sessao.filter((s) => s.id !== id); if (S.msg && S.msg.id === id) S.msg = null;
  render(); say(`Lançamento ${id} desfeito: ${n} ${n === 1 ? "conta removida" : "contas removidas"} e saldos restaurados.`); afterAction();
}
function sitSimples(id) {
  const L = LANC.filter((l) => l.id === id); if (!L.length) return ["mute", "—"]; const tipo = L[0].tipo, ab = L.filter((l) => !l.pago);
  if (!ab.length) return ["ok", tipo === "despesa" ? "Paga" : "Recebida"];
  if (L.length === 1 && L[0].agendado) return ["info", "Agendada"];
  if (ab.length < L.length) return ["info", `${L.length - ab.length} de ${L.length} ${tipo === "despesa" ? "pagas" : "recebidas"}`];
  return ["info", tipo === "despesa" ? "A pagar" : "A receber"];
}
/* diálogos */
function dlg(html) { const d = $("#dlg"); d.innerHTML = html; if (!d.open) d.showModal(); return d; }
function fechaDlg() { const d = $("#dlg"); if (d.open) d.close(); }
function abrirDup(dup, ok, sub) {
  window._dupOk = ok;
  dlg(`<div class="dh"><h2 id="dlg-t">${ic("alert")} Esta conta parece já ter sido lançada</h2></div><div class="db"><p>${sub === "leite" ? "Já existe uma nota de leite deste cliente para o mesmo mês de referência." : `Já existe um lançamento do mesmo ${ROT[S.tipo].forn.toLowerCase()} com ${(F_().doc || "").trim() ? "o mesmo número de documento" : "o mesmo valor"}.`} Confira antes de gravar de novo.</p>
    <div class="tblwrap"><table class="tbl"><thead><tr><th scope="col">Nº</th><th scope="col">Valor</th><th scope="col">Emissão</th><th scope="col">Vencimento</th><th scope="col">Situação</th></tr></thead><tbody><tr><td><b>${dup.id}</b></td><td class="num">${BRL(dup.valor)}</td><td>${fmtD(dup.emissao)}</td><td>${fmtD(dup.venc)}</td><td><span class="st ${sit(dup, dup.tipo)[0]}">${sit(dup, dup.tipo)[1]}</span></td></tr></tbody></table></div>
    <button type="button" class="link" data-dlg="abrir" data-v="${dup.id}" style="justify-self:start">Abrir ${dup.id} em ${dup.tipo === "despesa" ? "Contas a pagar" : "Contas a receber"} ${ic("arrow")}</button></div>
    <div class="df"><button type="button" class="btn btn-sec" data-dlg="salvar-mesmo">Não é duplicado: salvar mesmo assim</button><button type="button" class="btn btn-pri" data-dlg="revisar" autofocus>Voltar e revisar</button></div>`);
}

/* rascunho */
const draftKey = (t) => `cowdata:mock:rascunho:${t}:vale-verde:admin`;
let _dt = null;
function saveDraft() {
  clearTimeout(_dt); _dt = setTimeout(() => {
    if (S.msg && S.msg.kind === "draft") return;   // não sobrescreve o rascunho antes de o usuário decidir
    const tipo = S.tipo, F = F_(); if (S.sub[tipo] === "lote" || S.sub[tipo] === "faturas" || S.sub[tipo] === "semen") return;
    const sujo = F.fornecedor || F.itens.some((i) => i.produto || i.total || i.unit);
    if (sujo) LS.set(draftKey(tipo), JSON.stringify({ t: Date.now(), F: { ...F, anexos: [], lendo: false } }));
  }, 600);
}
function checarRascunho() {
  const t = S.tipo, raw = LS.get(draftKey(t)); if (!raw || S.msg) return;
  try { const d = JSON.parse(raw); const F = S.F[t]; if (F.fornecedor || F.itens.some((i) => i.produto)) return; S.msg = { kind: "draft", quando: new Date(d.t).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) }; } catch (e) {}
}

/* leitura de documento (simulada) */
function lerDocumento(nome) {
  const tipo = S.tipo, F = F_(); F.anexos.push({ nome, lido: false }); F.lendo = true; paintDoc(); say("Lendo o documento…");
  setTimeout(() => {
    F.lendo = false; F.anexos[F.anexos.length - 1].lido = true;
    if (tipo === "despesa") {
      F.fornecedor = "Nutrimix Nutrição Animal"; const f = FORN[F.fornecedor]; const it = F.itens[0];
      it.produto = "Sal mineral 25kg"; it.qtd = "25"; it.unit = "33,60"; it.edit = "unit"; it.total = fmtNum(840); it.conta = "3.01.01.03"; it.sug = "sugerida pelo cadastro do item";
      F.emissao = TODAY; F.venc = addDays(TODAY, 30); F.vencTocado = true; F.doc = "NF 5612"; F.tipoDoc = "Nota fiscal"; F.forma = f.forma; F.banco = f.banco; F.sug.forma = "lembrada";
      F.lido = { fornecedor: 1, valor: 1, venc: 1, doc: 1, emissao: 1 };
    } else {
      F.fornecedor = "Laticínio Vale do Sol"; F.leite = { ...F.leite, mes: "2026-09", litros: "13000", preco: "2,85" }; F.emissao = TODAY; F.venc = addDays(TODAY, 20); F.vencTocado = true; F.doc = "Nota 7790"; F.lido = { fornecedor: 1, litros: 1, venc: 1, doc: 1, emissao: 1 }; syncLeiteSilent();
    }
    render(); say("Documento lido: conferimos fornecedor, item, valor e vencimento. Revise e salve.");
  }, 900);
}

/* ───────────────────────── eventos ───────────────────────── */
function afterAction() { requestAnimationFrame(() => { const c = $("#donecard") || $(".pagehead h1"); if (c) { c.setAttribute("tabindex", "-1"); c.focus({ preventScroll: true }); } }); }
const doc = document;
doc.addEventListener("toggle", (e) => { if (e.target.matches && e.target.matches("details[data-pedidos]")) S.pedidoAberto = e.target.open; }, true);
doc.addEventListener("click", (e) => {
  const t = e.target;
  const ci = t.closest(".combo input"); if (ci) { if (ci.getAttribute("aria-expanded") !== "true") { ci.dataset.q = "0"; openCombo(ci); } return; }
  const nav = t.closest("[data-nav]"); if (nav) { e.preventDefault(); if (nav.dataset.new) S.novoId = nav.dataset.new; S.fcontas = nav.dataset.fconta || "abertas"; S.msgC = null; go(nav.dataset.nav); return; }
  const fo = t.closest("[data-focus]"); if (fo) { e.preventDefault(); const el = $("#" + fo.dataset.focus); if (el) { const dt = el.closest("details"); if (dt) dt.open = true; el.scrollIntoView({ block: "center" }); el.focus(); } return; }
  const dl = t.closest("[data-dlg]"); if (dl) {
    const a = dl.dataset.dlg;
    if (a === "baixa-ok") { if (confirmarBaixa()) { fechaDlg(); afterAction(); } return; }
    if (a === "desfazer-ok") { fechaDlg(); desfazer(dl.dataset.v); afterAction(); return; }
    if (a === "juntar-ok") { const f = window._fat; $$(".fat-c:checked").forEach((c) => { const [id, venc] = c.value.split("|"), l = LANC.find((x) => x.id === id && x.venc === venc); if (l) { l.fatura = f.id; f.n += 1; f.v = r2(f.v + l.valor); } }); fechaDlg(); $("#body").innerHTML = tplFaturas(); say("Notas juntadas à fatura."); afterAction(); return; }
    fechaDlg();
    if (a === "salvar-mesmo" && window._dupOk) window._dupOk(); if (a === "abrir") { S.novoId = dl.dataset.v; go("pagar"); } return;
  }
  const b = t.closest("[data-act]"); if (!b) return; const a = b.dataset.act, v = b.dataset.v, i = b.dataset.i != null ? +b.dataset.i : null, F = F_(), tipo = S.tipo;
  switch (a) {
    case "tipo": S.tipo = v; S.msg = null; checarRascunho(); render(); $(`#tab-${v}`).focus(); break;
    case "sub": S.sub[tipo] = v; S.msg = null; render(); $(`#sub-${v}`)?.focus(); break;
    case "pick-forn": aplicarForn(v); break;
    case "novo-forn": dlg(`<div class="dh"><h2 id="dlg-t">Cadastrar ${ROT[tipo].forn.toLowerCase()}</h2></div><div class="db"><p>No produto, esta janela abre o cadastro completo (nome, CNPJ/CPF, contato). No mockup, digite o nome na caixa para criar na hora.</p></div><div class="df"><button type="button" class="btn btn-pri" data-dlg="revisar" autofocus>Entendi</button></div>`); break;
    case "add-item": F.itens.push(novoItem()); paintItens(); { const n = F.itens.length - 1; const e2 = $(`#f-it${n}-prod`); if (e2) e2.focus(); } paintRail(); paintFoot(); break;
    case "del-item": F.itens.splice(i, 1); paintItens(); paintRail(); paintFoot(); revalidar(); { const nx = $(`#f-it${Math.min(i, F.itens.length - 1)}-prod`); if (nx) nx.focus(); } say("Item removido."); break;
    case "edit-conta": F.itens[i].editConta = true; paintMeta(i); { const c = $(`#f-it${i}-conta`); if (c) { c.focus(); openCombo(c); } } break;
    case "fecha-conta": F.itens[i].editConta = false; paintMeta(i); break;
    case "vale": F.itens[i].vale = b.checked; if (!b.checked) { F.itens[i].valeFunc = ""; F.itens[i].valeOk = false; } paintMeta(i); paintRail(); break;
    case "entregue": F.entregue = b.checked; paintAdv(); { const a = $("#adv"); if (a) a.open = true; } paintRail(); break;
    case "criar-bem": F.criarBem = b.checked; paintMeta(i); paintRail(); break;
    case "vale-ok": F.itens[i].valeOk = b.checked; break;
    case "ajustes": F.ajustes = true; paintTotais(); $("#f-desc")?.focus(); break;
    case "venc-q": { F.vencTocado = true; F.sug.venc = ""; F.venc = v === "dia10" ? addMonths(F.emissao.slice(0, 8) + "10", 1) : v === "hoje" ? TODAY : addDays(F.emissao, +v); paintDatas(); if (F.parc && !F.parcEdit) { gerarParcelas(F); const p = $("#parcs"); if (p) p.innerHTML = tplParcelas(); } paintRail(); paintFoot(); saveDraft(); $("#f-venc")?.focus(); break; }
    case "pagomode": F.pago = b.value === "pago"; if (F.pago) { F.parc = false; F.valorPago = fmtNum(calc(F).liq) || ""; F.valorPagoTocado = false; } paintDatas(); paintPag(); paintRail(); paintFoot(); saveDraft(); revalidar(); break;
    case "forma": F.forma = v; F.sug.forma = ""; paintPag(); paintRail(); saveDraft(); break;
    case "parc": F.parc = b.checked; if (F.parc) { F.parcEdit = false; gerarParcelas(F); } paintDatas(); paintPag(); paintRail(); paintFoot(); saveDraft(); break;
    case "nparc": F.nParc = +v; F.parcEdit = false; gerarParcelas(F); paintPag(); paintRail(); paintFoot(); break;
    case "parc-paga": F.parcelas[i].paga = b.checked; break;
    case "anexar": $("#file").click(); break;
    case "foto": $("#foto").click(); break;
    case "xml": dlg(`<div class="dh"><h2 id="dlg-t">Colar o XML da nota</h2></div><div class="db"><label class="lab" for="xmlt">Código XML</label><textarea class="in" id="xmlt" rows="6" style="font-family:monospace;font-size:13px" placeholder="Cole aqui o conteúdo do XML da NF-e"></textarea></div><div class="df"><button type="button" class="btn btn-ghost" data-dlg="revisar">Cancelar</button><button type="button" class="btn btn-pri" data-dlg="xml-ok">Importar</button></div>`); break;
    case "del-anexo": F.anexos.splice(i, 1); paintDoc(); break;
    case "classificar-depois": F.classificarDepois = b.checked; break;
    case "salvar": e.preventDefault(); salvar(v); break;
    case "salvar-lote": e.preventDefault(); salvarLote(); break;
    case "salvar-semen": e.preventDefault(); salvarSemen(); break;
    case "retomar": { const d = JSON.parse(LS.get(draftKey(tipo)) || "{}"); if (d.F) { S.F[tipo] = { ...novoForm(tipo), ...d.F }; } S.msg = null; render(); say("Rascunho retomado."); break; }
    case "descartar": LS.del(draftKey(tipo)); S.msg = null; paintTop(); say("Rascunho descartado."); break;
    case "igual": { const U = S.ultimo; if (U) { S.F[tipo] = { ...novoForm(tipo), ...JSON.parse(JSON.stringify(U)), emissao: TODAY, doc: "", anexos: [], lido: {}, dupOk: true, pago: false, venc: addDays(TODAY, (fornDe(tipo)[U.fornecedor] || {}).prazo || 30) }; S.msg = null; render(); $("#f-it0-qtd")?.focus(); say("Cópia do último lançamento pronta: ajuste o que mudou."); } break; }
    case "desfazer": { const L = LANC.filter((l) => l.id === v), pagas = L.filter((l) => l.pago); if (pagas.length) { dlg(`<div class="dh"><h2 id="dlg-t">${ic("alert")} Desfazer ${esc(v)}?</h2></div><div class="db"><p>${pagas.length === 1 ? "Há 1 parcela já " + (L[0].tipo === "despesa" ? "paga" : "recebida") : "Há " + pagas.length + " parcelas já " + (L[0].tipo === "despesa" ? "pagas" : "recebidas")}, no total de <b class="num">${BRL(pagas.reduce((s, l) => s + l.pago.valor, 0))}</b>. Ao desfazer, a nota inteira some e o saldo do banco volta ao que era antes.</p></div><div class="df"><button type="button" class="btn btn-pri" data-dlg="revisar" autofocus>Manter o lançamento</button><button type="button" class="btn btn-sec" data-dlg="desfazer-ok" data-v="${esc(v)}">Desfazer mesmo assim</button></div>`); } else desfazer(v); break; }
    case "vincular": if (S.msg && S.msg.vinculo) { S.msg.vinculo = { estado: "feito", texto: v ? `Vinculado a: ${v}.` : "Sem vínculo. Você pode vincular depois, em Sanidade." }; paintTop(); say(v ? "Vinculado." : "Sem vínculo."); } break;
    case "pedido": { const p = PEDIDOS.despesa.find((x) => x.id === v); const FF = S.F.despesa; FF.itens[0] = { ...novoItem(), produto: p.item, qtd: String(p.qtd), unit: fmtNum(p.unit), conta: itemInfo("despesa", p.item).conta, sug: "vinda do pedido " + p.id }; FF.pedido = p.id; S.tipo = "despesa"; aplicarForn(p.forn); F_().itens[0].edit = "unit"; recalcLinha(0); paintAdv(); say(`Pedido ${p.id} carregado.`); break; }
    case "cadastrar-item": dlg(`<div class="dh"><h2 id="dlg-t">Cadastrar “${esc(v)}” no estoque</h2></div><div class="db"><p>No produto, abre o cadastro de estoque com o nome já preenchido. Os próximos lançamentos passam a dar entrada no saldo.</p></div><div class="df"><button type="button" class="btn btn-pri" data-dlg="revisar" autofocus>Entendi</button></div>`); break;
    case "importar-planilha": dlg(`<div class="dh"><h2 id="dlg-t">Importar planilha de notas</h2></div><div class="db"><p>Aceita .xlsx ou .csv com colunas: número, emissão, item, conta e valor. As linhas entram na tabela para você conferir antes de gravar.</p></div><div class="df"><button type="button" class="btn btn-pri" data-dlg="revisar" autofocus>Entendi</button></div>`); break;
    case "lote-modo": S.lote.modo = v; $("#body").innerHTML = tplLote(); paintLote(); break;
    case "add-nota": { const ult = S.lote.notas[S.lote.notas.length - 1]; S.lote.notas.push({ ...novaNota(), emissao: ult.emissao }); $("#body").innerHTML = tplLote(); paintLote(); const nn = $$("#lote-notas .nota"); nn[nn.length - 1].querySelector("input").focus(); break; }
    case "del-nota": S.lote.notas.splice(i, 1); $("#body").innerHTML = tplLote(); paintLote(); break;
    case "fatura-acao": say(v === "juntar" ? "No produto, abre a seleção de notas do fornecedor para juntar à fatura." : "Fatura fechada: ela passa a vencer na data da fatura."); dlg(`<div class="dh"><h2 id="dlg-t">${v === "juntar" ? "Juntar notas à fatura" : "Fechar a fatura"}</h2></div><div class="db"><p>${v === "juntar" ? "Escolha as notas em aberto do fornecedor para entrarem nesta fatura." : "Depois de fechada, a fatura vence numa data só e não aceita novas notas."}</p></div><div class="df"><button type="button" class="btn btn-pri" data-dlg="revisar" autofocus>Entendi</button></div>`); break;
    case "novo-da-lista": S.tipo = v; S.sub[v] = v === "despesa" ? "uma" : "leite"; go("lancar", { tipo: v }); checarRascunho(); break;
    case "baixa": S.msgC = null; abrirBaixa(v); break;
    case "desfaz-baixa": desfazBaixa(v); break;
    case "fconta": S.fcontas = v; render(); break;
    case "forn-novo": F.novoForn = true; paintFornAviso(); paintRail(); revalidar(); break;
    case "nota-sem": { S.lote.notas[i].sem = b.checked; if (b.checked) S.lote.notas[i].doc = ""; $("#body").innerHTML = tplLote(); paintLote(); $(`#l-sem${i}`)?.focus(); break; }
    case "fatura-juntar": abrirJuntar(v); break;
    case "fatura-fechar": { const f = S.faturas.find((x) => x.id === v); f.st = "Fechada"; S.msg = { kind: "done", id: f.id, view: "pagar", fconta: "abertas", titulo: `${f.id} fechada`, resumo: `${esc(f.forn)} · ${f.n} notas · <b class="num">${BRL(f.v)}</b> · vence ${fmtD(f.venc)}. Ela não aceita mais notas.`, avisos: [], vinculo: null, nao_igual: true }; $("#body").innerHTML = tplFaturas(); say(`${f.id} fechada.`); afterAction(); break; }
    case "ret-auto": F.retTocado = false; syncLeite(); paintRail(); paintFoot(); break;
    case "redistribuir": F.parcEdit = false; gerarParcelas(F); { const p = $("#parcs"); if (p) p.innerHTML = tplParcelas(); } paintRail(); paintFoot(); say("Parcelas redistribuídas igualmente."); break;
  }
});
doc.addEventListener("input", (e) => {
  const t = e.target;
  if (t.matches(".combo input")) { t.dataset.q = "1"; openCombo(t); if (t.closest("[data-combo=forn]") && S.view === "lancar") { if (S.sub[S.tipo] === "lote") S.lote.forn = t.value; else { F_().fornecedor = t.value; F_().novoForn = false; F_().lido.fornecedor = false; const av = $("#forn-aviso"); if (av) av.innerHTML = ""; paintFoot(); paintRail(); revalidar(); } } if (t.closest("[data-combo=prod]")) { const i = +t.closest(".combo").dataset.i, it = F_().itens[i]; it.produto = t.value; if (it.sug && !itemInfo(S.tipo, t.value)) { it.conta = null; it.sug = ""; if (it.edit !== "total") { it.unit = ""; it.total = ""; } recalcLinha(i); } paintMeta(i); paintFoot(); paintRail(); saveDraft(); revalidar(); } return; }
  if (t.id === "bx-valor" || t.id === "bx-data") { updBaixa(); return; }
  const p = t.dataset.b; if (!p) return;
  let val = t.type === "checkbox" ? t.checked : t.value; if (t.hasAttribute("data-num")) val = +val;
  if (p === "ret") { const F = F_(); F.retTocado = true; F.desc = val; syncLeite(); paintRail(); paintFoot(); return; }
  if (p === "desc") F_().retTocado = true;
  if (S.view === "lancar" && S.tipo === "despesa" && /^lote\./.test(p)) { setPath(p, val); afterChange(p); return; }
  setPath(p, val); afterChange(p);
});
doc.addEventListener("change", (e) => {
  const t = e.target;
  if (t.id === "file" || t.id === "foto") { const f = [...t.files]; t.value = ""; if (f.length) lerDocumento(f[0].name); return; }
  if (t.matches("[data-act=vale]")) { /* tratado no click */ }
  if (t.dataset.b === "itens" ) return;
});
doc.addEventListener("focusout", (e) => {
  const t = e.target;
  if (t.matches(".combo input")) setTimeout(() => { if (comboCur && comboCur.inp === t) { closeCombo(); } const F = F_(); if (S.view === "lancar" && t.closest("[data-combo=forn]")) paintFornAviso();
    if (S.view === "lancar" && t.closest("[data-combo=prod]")) { const i = +t.closest(".combo").dataset.i, it = F_().itens[i], info = it && itemInfo(S.tipo, it.produto); if (info && !it.conta) escolherProduto(i, { v: info.nome }); }
    t.dataset.q = "0"; }, 140);
  if (t.hasAttribute && t.hasAttribute("data-m0")) { const v = parseBR(t.value); t.value = v ? v.toLocaleString("pt-BR") : ""; try { setPath(t.dataset.b, t.value); } catch (_) {} }
  if (t.hasAttribute && t.hasAttribute("data-m")) { const v = parseBR(t.value); t.value = v ? fmtNum(v) : ""; const p = t.dataset.b; if (p) { try { setPath(p, t.value); } catch (_) {} } }
  if (t.dataset && t.dataset.b === "itens.0.unit") {}
});
doc.addEventListener("mousedown", (e) => { const li = e.target.closest(".combo li[role=option]"); if (li && comboCur) { e.preventDefault(); pickCombo(+li.dataset.k); } });
function focusNext(t) {
  const els = $$("#frm input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]):not([disabled]):not([readonly]), #frm select:not([disabled]), #frm textarea").filter((e) => e.offsetParent !== null);
  const n = els[els.indexOf(t) + 1];
  if (n) { n.focus(); if (n.select && n.type !== "date" && n.tagName !== "SELECT") { try { n.select(); } catch (_) {} } } else { const b = $("#foot [data-act=salvar][data-v=fim]"); if (b) b.focus(); }
}
doc.addEventListener("keydown", (e) => {
  const t = e.target;
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && $("#frm") && !$("#dlg").open) { e.preventDefault(); closeCombo(); const sub = S.sub[S.tipo]; if (S.tipo === "despesa" && sub === "lote") salvarLote(); else if (S.tipo === "despesa" && sub === "semen") salvarSemen(); else salvar("fim"); return; }
  if (t.matches && t.matches(".combo input")) {
    if (!comboCur && e.key === "ArrowDown") { e.preventDefault(); t.dataset.q = "0"; openCombo(t); moveCombo(1); return; }
    if (comboCur) {
      if (e.key === "ArrowDown") { e.preventDefault(); moveCombo(1); } else if (e.key === "ArrowUp") { e.preventDefault(); moveCombo(-1); }
      else if (e.key === "Enter") { e.preventDefault(); if (comboCur.act >= 0) pickCombo(comboCur.act); else { const o = comboCur.opts.findIndex((x) => !x.h); if (comboCur.kind === "forn" && t.value.trim() && o >= 0) pickCombo(o); else { closeCombo(); focusNext(t); } } }
      else if (e.key === "Escape") { e.stopPropagation(); closeCombo(); }
      return;
    }
  }
  if (e.key === "Enter" && !e.shiftKey && t.matches && t.matches("#frm input:not([type=checkbox]):not([type=radio]):not([type=file]), #frm select")) { e.preventDefault(); focusNext(t); return; }
  if (t.matches && t.matches("[role=tab]") && (e.key === "ArrowRight" || e.key === "ArrowLeft")) { const tabs = $$("[role=tab]", t.parentElement); const k = tabs.indexOf(t) + (e.key === "ArrowRight" ? 1 : -1); const n = tabs[(k + tabs.length) % tabs.length]; n.focus(); n.click(); e.preventDefault(); }
});
doc.addEventListener("submit", (e) => { e.preventDefault(); });
doc.addEventListener("dragover", (e) => { const z = e.target.closest && e.target.closest("#dropzone"); if (z) { e.preventDefault(); z.classList.add("over"); } });
doc.addEventListener("dragleave", (e) => { const z = e.target.closest && e.target.closest("#dropzone"); if (z) z.classList.remove("over"); });
doc.addEventListener("drop", (e) => { const z = e.target.closest && e.target.closest("#dropzone"); if (z) { e.preventDefault(); z.classList.remove("over"); const f = e.dataTransfer.files[0]; lerDocumento(f ? f.name : "documento.pdf"); } });
$("#dlg").addEventListener("click", (e) => { const x = e.target.closest("[data-dlg=xml-ok]"); if (x) { fechaDlg(); lerDocumento("nota.xml"); } });

/* salvar lote / sêmen */
function validarLote() {
  const L = S.lote, E = [], ok = L.notas.filter((n) => parseBR(n.valor) > 0);
  if (!L.forn.trim()) E.push({ id: "f-forn", msg: "Informe o fornecedor do lote." });
  else if (!FORN[L.forn]) E.push({ id: "f-forn", msg: `Escolha um fornecedor cadastrado da lista (“${L.forn}” não está no cadastro).` });
  if (!ok.length) E.push({ id: "l-val0", msg: "Preencha o valor de pelo menos uma nota." });
  const vistos = {};
  L.notas.forEach((n, i) => {
    const k = i + 1; if (!(parseBR(n.valor) > 0)) return;
    if (!n.conta) E.push({ id: `l-conta${i}`, msg: `Escolha para onde vai a nota ${k}.` });
    if (!n.sem && !n.doc.trim()) E.push({ id: `l-doc${i}`, msg: `Informe o número da nota ${k} ou marque “sem número”.` });
    else if (!n.sem) {
      const d = LANC.find((l) => l.tipo === "despesa" && l.forn === L.forn && (l.doc || "").trim().toLowerCase() === n.doc.trim().toLowerCase());
      if (d) E.push({ id: `l-doc${i}`, msg: `A nota ${n.doc.trim()} deste fornecedor já foi lançada (${d.id}).` });
      else if (vistos[n.doc.trim().toLowerCase()]) E.push({ id: `l-doc${i}`, msg: `O número ${n.doc.trim()} aparece duas vezes neste lote.` });
      vistos[n.doc.trim().toLowerCase()] = 1;
    }
    const mc = mesFechado(n.emissao); if (mc) E.push({ id: `l-emi${i}`, msg: `A nota ${k} tem emissão em ${mesLong(mc)}, que está fechado.` });
    if (L.modo !== "pago" && L.venc && n.emissao > L.venc) E.push({ id: "l-venc", msg: `O vencimento do lote (${fmtD(L.venc)}) é anterior à emissão da nota ${k} (${fmtD(n.emissao)}).` });
  });
  if (L.modo !== "pago" && !L.venc) E.push({ id: "l-venc", msg: "Informe o vencimento do lote." });
  if (L.modo === "pago") { const mc = mesFechado(L.pagoData); if (mc) E.push({ id: "l-pdata", msg: `A data do pagamento cai em ${mesLong(mc)}, que está fechado.` }); }
  return E;
}
function salvarLote() {
  const E = validarLote(); if (E.length) { mostrarErros(E); return; }
  const L = S.lote, ok = L.notas.filter((n) => parseBR(n.valor) > 0), ids = [], tot = r2(ok.reduce((s, n) => s + parseBR(n.valor), 0));
  ok.forEach((n) => {
    const id = proxNumero(); ids.push(id); const v = parseBR(n.valor);
    LANC.push({ id, tipo: "despesa", forn: L.forn, item: n.item || CONTA_NOME[n.conta], valor: v, emissao: n.emissao, venc: L.modo === "pago" ? L.pagoData : L.venc, doc: n.sem ? "sem número" : n.doc, conta: n.conta, centro: L.centro, pago: L.modo === "pago" ? { data: L.pagoData, valor: v, banco: L.banco, forma: "Pix" } : undefined });
    S.sessao.unshift({ id, hora: new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }), forn: L.forn, item: n.item || CONTA_NOME[n.conta], valor: v, novo: true });
  });
  if (L.modo === "pago") BANCOS[L.banco].saldo = r2(BANCOS[L.banco].saldo - tot);
  S.msg = { kind: "done", id: ids[0], view: "pagar", fconta: L.modo === "pago" ? "pagas" : "abertas", titulo: `Lote gravado: ${ids.length} ${ids.length === 1 ? "nota" : "notas"}`, resumo: `<b>${esc(L.forn)}</b> · ${ids[0]}${ids.length > 1 ? " a " + ids[ids.length - 1] : ""} · <b class="num">${BRL(tot)}</b> numa fatura fechada.`, avisos: [], vinculo: null, nao_igual: true };
  S.novoId = ids[0]; S.lote = novoLote(); render(); say(`Lote gravado com ${ids.length} notas.`); const d = $("#donecard"); if (d) d.focus({ preventScroll: true }); window.scrollTo(0, 0);
}
function validarSemen() {
  const X = S.semen, E = [];
  if (!X.touro) E.push({ id: "s-touro", msg: "Escolha o touro." });
  if (!(parseBR(X.doses) > 0)) E.push({ id: "s-doses", msg: "Informe o número de doses." });
  if (!(parseBR(X.preco) > 0)) E.push({ id: "s-preco", msg: "Informe o preço por dose." });
  const mc = mesFechado(X.emissao); if (mc) E.push({ id: "s-emi", msg: `A emissão cai em ${mesLong(mc)}, que está fechado.` });
  if (X.venc && X.emissao && X.venc < X.emissao) E.push({ id: "s-venc", msg: `O vencimento (${fmtD(X.venc)}) é anterior à emissão (${fmtD(X.emissao)}).` });
  return E;
}
function salvarSemen() {
  const E = validarSemen(); if (E.length) { mostrarErros(E); return; }
  const X = S.semen, t = TOUROS.find((x) => x.id === X.touro), tot = r2(parseBR(X.doses) * parseBR(X.preco)), id = proxNumero();
  LANC.push({ id, tipo: "despesa", forn: X.forn, item: `Sêmen — ${t.nome}`, valor: tot, emissao: X.emissao, venc: X.venc, doc: X.doc || "", conta: "3.01.03.01", centro: "Pecuária Leiteira" });
  S.sessao.unshift({ id, hora: new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }), forn: X.forn, item: `Sêmen — ${t.nome}`, valor: tot, novo: true });
  S.msg = { kind: "done", id, view: "pagar", fconta: "abertas", titulo: `Compra ${id} gravada`, resumo: `<b>${esc(X.forn)}</b> · ${parseBR(X.doses)} doses de ${esc(t.nome)} · <b class="num">${BRL(tot)}</b> · vence ${fmtD(X.venc)}.`, avisos: [], vinculo: null, nao_igual: true };
  S.novoId = id; S.semen = novoSemen(); render(); say("Compra de sêmen gravada. As doses entraram no estoque."); const d = $("#donecard"); if (d) d.focus({ preventScroll: true });
}

/* ───────────────────────── barra do mockup ───────────────────────── */
function setTema(t) { document.documentElement.dataset.tema = t; document.documentElement.style.colorScheme = t === "escuro" ? "dark" : "light"; setAttrBtns(".mockbar [data-tema]", "tema", t); }
function setAttrBtns(sel, attr, val) { $$(sel).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset[attr] === val))); }
$$(".mockbar [data-dev]").forEach((b) => b.addEventListener("click", () => { document.body.dataset.device = b.dataset.dev; setAttrBtns(".mockbar [data-dev]", "dev", b.dataset.dev); }));
$$(".mockbar [data-tema]").forEach((b) => b.addEventListener("click", () => setTema(b.dataset.tema)));
$$(".mockbar [data-perfil]").forEach((b) => b.addEventListener("click", () => { S.perfil = b.dataset.perfil; setAttrBtns(".mockbar [data-perfil]", "perfil", S.perfil); if (S.view === "lancar") { const F = F_(); F.itens.forEach((_, i) => paintMeta(i)); revalidar(); } }));
$$(".mockbar [data-pal]").forEach((b) => b.addEventListener("click", () => { document.documentElement.dataset.pal = b.dataset.pal; setAttrBtns(".mockbar [data-pal]", "pal", b.dataset.pal); }));
if (innerWidth <= 520) { document.body.dataset.device = "mobile"; setAttrBtns(".mockbar [data-dev]", "dev", "mobile"); document.body.classList.add("real-phone"); }

function cenario(n) {
  S.msg = null; _prevEff = {};
  const reset = () => { S.F = { despesa: novoForm("despesa"), receita: novoForm("receita") }; S.tipo = "despesa"; S.sub = { despesa: "uma", receita: "leite" }; S.view = "lancar"; S.pedidoAberto = false; };
  reset();
  const F = S.F.despesa;
  const fill = (forn) => { const f = FORN[forn]; F.fornecedor = forn; F.forma = f.forma; F.banco = f.banco; F.venc = addDays(TODAY, f.prazo); F.sug.venc = `${f.prazo} dias, como de costume`; F.sug.forma = "lembrada"; };
  const item = (i, nome, qtd, unit) => { const it = F.itens[i] || (F.itens[i] = novoItem()); const info = itemInfo("despesa", nome); it.produto = nome; it.qtd = String(qtd); it.unit = fmtNum(unit); it.edit = "unit"; it.total = fmtNum(qtd * unit); it.conta = info?.conta || null; it.sug = it.conta ? "sugerida pelo cadastro do item" : ""; };
  switch (n) {
    case "vazio": break;
    case "doc": render(); lerDocumento("NF-5612-nutrimix.pdf"); return;
    case "parcelado": fill("Nutrimix Nutrição Animal"); item(0, "Sal mineral 25kg", 120, 33.75); F.parc = true; F.nParc = 3; gerarParcelas(F); break;
    case "pago": fill("Vetnil Saúde Animal"); item(0, "Antibiótico intramamário", 70, 18.5); F.pago = true; F.valorPago = fmtNum(1285); F.valorPagoTocado = true; F.venc = ""; break;
    case "duplicado": fill("Agropecuária Boa Safra"); item(0, "Ração concentrada", 8000, 1.9); break;
    case "vale": F.fornecedor = "Adão Lima"; F.novoForn = true; { const it = F.itens[0]; it.produto = "Adiantamento de salário"; it.total = "800,00"; it.edit = "total"; it.conta = "3.03.01.17"; it.vale = true; it.valeFunc = "Adão Lima"; } F.pago = true; F.valorPago = "800,00"; F.valorPagoTocado = true; F.forma = "Pix"; break;
    case "bem": fill("Metalúrgica Frio Sul"); item(0, "Resfriador de leite 2.000 L", 1, 18000); F.parc = true; F.nParc = 6; gerarParcelas(F); break;
    case "erro": render(); salvar("fim"); return;
    case "fechado": fill("Nutrimix Nutrição Animal"); item(0, "Sal mineral 25kg", 25, 33.6); F.emissao = "2026-08-20"; render(); salvar("fim"); return;
    case "leite": S.tipo = "receita"; S.sub.receita = "leite"; { const R = S.F.receita; R.fornecedor = "Laticínio Vale do Sol"; R.leite = { mes: "2026-09", litros: "13000", preco: "2,85", retPct: "1,7" }; R.venc = addDays(TODAY, 20); R.vencTocado = true; R.forma = "TED"; R.sug.forma = "lembrada"; R.emissao = TODAY; R.itens[0] = { ...novoItem(), produto: "Leite", conta: "2.01.01.01", qtd: "13000", unit: "2,85", edit: "unit", total: fmtNum(37050) }; R.desc = fmtNum(r2(37050 * 0.017)); R.comp = "2026-09"; } break;
    case "lote": S.sub.despesa = "lote"; S.lote = { ...novoLote(), forn: "Agropecuária Boa Safra", venc: addDays(TODAY, 30), notas: [{ doc: "NF 1601", sem: false, emissao: "2026-10-08", item: "Ração concentrada", conta: "3.01.01.01", valor: "9.800,00" }, { doc: "NF 1612", sem: false, emissao: "2026-10-13", item: "Ração concentrada", conta: "3.01.01.01", valor: "5.600,00" }] }; break;
    case "faturas": S.sub.despesa = "faturas"; break;
    case "semen": S.sub.despesa = "semen"; S.semen = { ...novoSemen(), touro: "7HO00002", doses: "20", preco: "92,00" }; break;
    case "controle": go("pagar"); return;
  }
  render(); window.scrollTo(0, 0);
  const sub = S.sub[S.tipo]; if (sub === "lote") paintLote(); if (sub === "semen") paintSemen();
}
$("#mb-cen").addEventListener("change", (e) => { if (e.target.value) { cenario(e.target.value); e.target.value = ""; } });

/* ───────────────────────── início ───────────────────────── */
try { const a = JSON.parse(LS.get("cowdata:mock:aba") || "null"); if (a && a.tipo) { S.tipo = a.tipo; S.sub = { ...S.sub, ...a.sub }; } } catch (e) {}
checarRascunho();
render();
if (location.hash === "#pagar") go("pagar", { noFocus: true });

/* altura real da barra do mockup (ela pode quebrar em duas linhas) */
(function () { const mb = $(".mockbar"); const set = () => document.documentElement.style.setProperty("--mbh", mb.offsetHeight + "px"); set(); if (window.ResizeObserver) new ResizeObserver(set).observe(mb); })();

/* tema: segue o visualizador (data-theme="dark|light") ou o sistema; os botões do mockup podem sobrescrever */
(function () {
  const root = document.documentElement, qual = () => (root.dataset.theme === "dark" || (!root.dataset.theme && window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches)) ? "escuro" : "claro";
  setTema(qual());
  if (window.MutationObserver) new MutationObserver(() => setTema(qual())).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  if (window.matchMedia) { const m = matchMedia("(prefers-color-scheme: dark)"); (m.addEventListener ? m.addEventListener.bind(m, "change") : m.addListener.bind(m))(() => { if (!root.dataset.theme) setTema(qual()); }); }
})();
