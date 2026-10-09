(function () {
'use strict';

/* ================= estado ================= */
let ITENS = ITENS_SEED(), PEDIDOS = PEDIDOS_SEED(), TRILHA = TRILHA_SEED();
const NOVO_F = () => ({ q: '', ini: '', fim: '', sit: 'todas', parte: '', vmin: '', vmax: '', ord: 'recentes' });
const S = {
  papel: 'admin', tema: 'claro', aba: 'apagar', passo: 'pick', dom: 'fin', tipo: null, busca: '',
  f: NOVO_F(), sel: [], exp: {}, col: {}, fil: {}, conf: {}, res: null, loadImp: false, flash: null,
  aberto: {}, modo: {}, mostrar: 8, trFiltro: 'tudo', trAberto: {}, escAberto: false, fAberto: false,
};
const EU = () => (S.papel === 'admin' ? 'Jairo' : 'Ana Paula');
const view = document.getElementById('view');
const trayEl = document.getElementById('tray');
const liveEl = document.getElementById('live');
const toastEl = document.getElementById('toast');
const reduz = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ================= utilitários ================= */
const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const getItem = (id) => ITENS.find((i) => i.id === id);
const plural = (n, s, p) => `${n} ${n === 1 ? s : p}`;
const say = (m) => { liveEl.textContent = ''; setTimeout(() => { liveEl.textContent = m; }, 30); };
function toast(m) {
  const d = document.createElement('div'); d.className = 'toast'; d.textContent = m; toastEl.appendChild(d);
  setTimeout(() => d.remove(), 3200);
}
const ICONS = {
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
  warn: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  ban: '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
  undo: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  down: '<path d="m6 9 6 6 6-6"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  back: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
  next: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  clip: '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
  pencil: '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>',
  list: '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
};
const ic = (n, cls = '') => `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[n]}</svg>`;

/* ================= regras de impacto e risco ================= */
function totaisImp(it) {
  const a = it.imp.apagar;
  return { n: a.reduce((s, x) => s + (x.n || 1), 0), din: a.reduce((s, x) => s + (x.din || 0), 0), rev: it.imp.reverter.length, av: it.imp.avisos.length };
}
function riscoItem(it) {
  if (it.risco) return it.risco;
  const t = totaisImp(it);
  if (t.n >= 10) return 'alto';
  if (t.rev > 0 || t.din > 0 || t.n > 1) return 'medio';
  return 'baixo';
}
const ORDEM_R = { baixo: 0, medio: 1, alto: 2 };
function riscoDe(itens) {
  let r = 'baixo';
  itens.forEach((i) => { const x = riscoItem(i); if (ORDEM_R[x] > ORDEM_R[r]) r = x; });
  if (itens.length >= 10) r = 'alto';
  else if (itens.length >= 2 && r === 'baixo') r = 'medio';
  return r;
}
function porque(itens) {
  const p = new Set();
  itens.forEach((i) => {
    if (i.porque) p.add(i.porque);
    const t = totaisImp(i);
    if (!i.porque) {
      if (t.din > 0) p.add('tem dinheiro em aberto');
      if (t.rev > 0) p.add('mexe em outros dados (estoque, lactação, saldos)');
      if (t.n > 1 && t.n < 10) p.add(`apaga ${t.n} registros`);
      if (t.n >= 10) p.add(`apaga ${t.n} registros`);
    }
  });
  if (itens.length >= 2) p.add(`${itens.length} itens de uma vez`);
  return [...p];
}
function analisa(ids) {
  const itens = ids.map(getItem).filter(Boolean);
  const bloq = itens.filter((i) => i.imp.bloqueia.length);
  const exec = itens.filter((i) => !i.imp.bloqueia.length);
  const tot = exec.reduce((a, i) => { const t = totaisImp(i); a.n += t.n; a.din += t.din; a.rev += t.rev; a.av += t.av; return a; }, { n: 0, din: 0, rev: 0, av: 0 });
  return { itens, bloq, exec, tot, risco: exec.length ? riscoDe(exec) : 'baixo' };
}
const RISCO_TXT = {
  baixo: ['Risco baixo', 'Um registro isolado. Nada mais muda.'],
  medio: ['Risco médio', 'Mexe em outras coisas (estoque, contas, lactação) ou apaga mais de um. Diga o motivo.'],
  alto: ['Risco alto', 'Apaga muita coisa, ou um cadastro em uso. Não dá para desfazer. Confirme digitando.'],
};
const MOTIVOS = ['Lançado em duplicidade', 'Valor ou dado errado', 'Animal ou pessoa errada', 'Era teste', 'Outro'];

/* ================= busca e filtros ================= */
function sitFinTxt(it) { return sitFin(it); }
function filtrar() {
  const f = S.f;
  let arr = S.tipo === 'todos' ? ITENS.filter((i) => !TIPOS[i.tipo].cad) : ITENS.filter((i) => i.tipo === S.tipo);
  const q = norm(f.q);
  if (q) arr = arr.filter((i) => q.split(/\s+/).every((w) => norm(i.titulo + ' ' + i.sub + ' ' + (i.parte || '')).includes(w)));
  if (f.ini) arr = arr.filter((i) => !i.data || i.data >= f.ini);
  if (f.fim) arr = arr.filter((i) => !i.data || i.data <= f.fim);
  if (f.parte) arr = arr.filter((i) => i.parte === f.parte);
  if (f.vmin !== '') arr = arr.filter((i) => (i.valor || 0) >= Number(f.vmin));
  if (f.vmax !== '') arr = arr.filter((i) => (i.valor || 0) <= Number(f.vmax));
  if (f.sit !== 'todas') {
    arr = arr.filter((i) => {
      if (i.tipo !== 'financeiro') return true;
      const s = sitFin(i);
      if (f.sit === 'aberta') return s === 'aberta' || s === 'atrasada';
      if (f.sit === 'atrasada') return s === 'atrasada';
      if (f.sit === 'paga') return s === 'paga' || s === 'parcial';
      return true;
    });
  }
  arr = arr.slice();
  if (f.ord === 'valor') arr.sort((a, b) => (b.valor || 0) - (a.valor || 0));
  else if (f.ord === 'antigos') arr.sort((a, b) => (a.data || '').localeCompare(b.data || ''));
  else if (f.ord === 'az') arr.sort((a, b) => a.titulo.localeCompare(b.titulo, 'pt-BR'));
  else arr.sort((a, b) => (b.data || '').localeCompare(a.data || '') || a.titulo.localeCompare(b.titulo, 'pt-BR'));
  return arr;
}
const temFiltro = () => { const f = S.f; return !!(f.q || f.ini || f.fim || f.parte || f.vmin !== '' || f.vmax !== '' || f.sit !== 'todas'); };
const cntTipo = (t) => ITENS.filter((i) => i.tipo === t).length;
const cntDom = (d) => d.tipos.reduce((s, t) => s + cntTipo(t), 0);

/* ================= chips de consequência por linha ================= */
function chipsDe(it) {
  const out = [];
  const im = it.imp;
  if (it.tipo === 'financeiro') {
    const s = sitFin(it);
    if (s === 'atrasada') out.push(['red', 'Atrasada']);
    else if (s === 'aberta') out.push(['', 'Em aberto']);
    else if (s === 'parcial') out.push(['amber', 'Com parcela paga']);
    else out.push(['green', it.receita ? 'Toda recebida' : 'Toda paga']);
  }
  if (im.bloqueia.length) out.push(['red', 'Bloqueado: ' + im.bloqueia[0].t.toLowerCase()]);
  const chips = [...new Set(im.reverter.map((r) => r.chip).filter(Boolean))];
  if (chips.length) chips.forEach((c) => out.push(['amber', c]));
  else if (im.reverter.length) out.push(['amber', 'Reverte outros dados']);
  const t = totaisImp(it);
  if (t.n >= 5 && !im.bloqueia.length) out.push(['', `Apaga ${t.n} registros`]);
  if (riscoItem(it) === 'alto' && !im.bloqueia.length) out.push(['red', 'Risco alto']);
  const max = 4;
  const r = out.slice(0, max).map(([k, tx]) => `<span class="chip ${k}">${esc(tx)}</span>`).join('');
  return out.length > max ? r + `<span class="chip">+${out.length - max}</span>` : r;
}

/* ================= blocos de impacto ================= */
const BL = {
  bloqueia: { rot: 'Bloqueia', sub: 'Impede de apagar enquanto você não resolver', ic: 'ban', cl: 'bq' },
  apagar: { rot: 'Será apagado', sub: 'Some do sistema e não volta', ic: 'trash', cl: 'ap' },
  reverter: { rot: 'Será revertido', sub: 'O sistema desfaz sozinho o que isto tinha feito', ic: 'undo', cl: 'rv' },
  avisos: { rot: 'Avisos', sub: 'Não impedem, mas vale saber', ic: 'info', cl: 'av' },
};
function entHtml(e, bloco, key) {
  const filhos = e.filhos || [];
  const aberto = S.fil[key];
  const mostra = filhos.length > 4 && !aberto ? filhos.slice(0, 3) : filhos;
  let h = `<li class="ent"><div class="ent-h"><strong>${esc(e.t)}</strong>${e.din ? `<span class="din">${brl(e.din)}</span>` : ''}</div>`;
  if (e.c) h += `<p class="ent-c">${esc(e.c)}</p>`;
  if (filhos.length) {
    h += `<ul class="fil">${mostra.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>`;
    if (filhos.length > 4) h += `<button class="link" data-act="fil" data-k="${esc(key)}" aria-expanded="${!!aberto}">${aberto ? 'Mostrar menos' : `Ver os ${filhos.length} itens`}</button>`;
  }
  if (bloco === 'bloqueia') {
    h += `<div class="fazer"><div><b>O que fazer</b>${esc(e.fazer)}</div><div><button class="btn btn-sm" data-act="acao" data-v="${esc(e.acao)}">${ic('next')} ${esc(e.acao)}</button></div></div>`;
  }
  return h + '</li>';
}
function blocosHtml(itens, bloqItens, ctx) {
  const multi = itens.length + bloqItens.length > 1;
  let i = 0;
  const mk = (k, ents) => {
    const b = BL[k];
    const cont = ents.reduce((s, g) => s + g.list.length, 0);
    const chave = ctx + ':' + k;
    const fechado = S.col[chave] === true;
    const corpo = ents.map((g) => {
      const head = multi ? `<div class="it-h">${esc(g.item.titulo)}<span>${esc(TIPOS[g.item.tipo].sing)}</span></div>` : '';
      return head + `<ul>${g.list.map((e, n) => entHtml(e, k, `${ctx}:${k}:${g.item.id}:${n}`)).join('')}</ul>`;
    }).join('');
    const n = k === 'apagar' ? ents.reduce((s, g) => s + g.list.reduce((a, e) => a + (e.n || 1), 0), 0) : cont;
    return `<section class="bloco ${b.cl} anim" style="--i:${i++}" aria-labelledby="${chave.replace(/[^a-z0-9]/gi, '_')}-t" data-bloco="${k}">
      <button class="bloco-h" data-act="bloco" data-k="${esc(chave)}" aria-expanded="${!fechado}">
        <span class="bloco-ic">${ic(b.ic)}</span>
        <span class="bloco-t"><span class="caps" id="${chave.replace(/[^a-z0-9]/gi, '_')}-t">${b.rot}</span><small>${b.sub}</small></span>
        <span class="bloco-n num" aria-label="${n} ${n === 1 ? 'ocorrência' : 'ocorrências'}">${n}</span>${ic('down', 'chev')}
      </button>
      <div class="bloco-b" ${fechado ? 'hidden' : ''}>${corpo}</div></section>`;
  };
  const vazio = (k, titulo, texto) => `<section class="bloco nada anim" style="--i:${i++}" data-bloco="${k}"><div class="nada-l">${ic('check')}<span><b>${titulo}</b> ${texto}</span></div></section>`;
  const g = (campo, lista) => lista.map((it) => ({ item: it, list: it.imp[campo] })).filter((x) => x.list.length);
  let h = '';
  const gb = g('bloqueia', bloqItens);
  if (gb.length) h += mk('bloqueia', gb);
  const ga = g('apagar', itens);
  if (ga.length) h += mk('apagar', ga);
  const gr = g('reverter', itens);
  h += gr.length ? mk('reverter', gr) : (itens.length ? vazio('reverter', 'Nada será revertido.', 'Nenhum estoque, saldo ou lactação muda.') : '');
  const gv = g('avisos', itens);
  h += gv.length ? mk('avisos', gv) : (itens.length ? vazio('avisos', 'Sem avisos.', 'Nada mais a observar.') : '');
  if (!gb.length) h += vazio('bloqueia', 'Nada bloqueia.', 'Pode seguir para a decisão.');
  return h;
}

/* ================= decisão (confirmação proporcional ao risco) ================= */
function exigencias(exec, modo) {
  const r = exec.length ? riscoDe(exec) : 'baixo';
  if (modo === 'pedir') return { motivo: true, palavra: false, risco: r };
  if (modo === 'aprovar') return { motivo: false, palavra: r === 'alto', risco: r };
  return { motivo: r !== 'baixo', palavra: r === 'alto', risco: r };
}
function confDe(ctx) { return (S.conf[ctx] = S.conf[ctx] || { motivo: '', outro: '', palavra: '' }); }
function motivoFinal(c) { return c.motivo === 'Outro' ? c.outro.trim() : c.motivo; }
function podeConfirmar(ctx, exec, modo) {
  if (!exec.length) return { ok: false, falta: 'Nada para confirmar: todos os itens têm bloqueio.' };
  const ex = exigencias(exec, modo), c = confDe(ctx);
  if (ex.motivo) {
    if (!c.motivo) return { ok: false, falta: 'Escolha o motivo.' };
    if (c.motivo === 'Outro' && c.outro.trim().length < 3) return { ok: false, falta: 'Escreva o motivo em poucas palavras.' };
  }
  if (ex.palavra && norm(c.palavra.trim()) !== 'apagar') return { ok: false, falta: 'Digite APAGAR para liberar o botão.' };
  return { ok: true, falta: '' };
}
function decideHtml(ctx, exec, bloqN, modo) {
  const ex = exigencias(exec, modo), c = confDe(ctx), pc = podeConfirmar(ctx, exec, modo);
  const [rl, rt] = RISCO_TXT[ex.risco];
  const why = porque(exec);
  const unico = exec.length === 1 ? exec[0] : null;
  const rid = ctx.replace(/[^a-z0-9]/gi, '_');
  let h = `<div class="risk ${ex.risco}"><div class="risk-k">Quanto pesa</div><div class="risk-seg" aria-hidden="true"><i></i><i></i><i></i></div><div class="risk-l">${ex.risco === 'baixo' ? ic('check') : ic('warn')} ${rl}</div><p>${rt}</p>${why.length ? `<p>Porque: ${esc(why.join('; '))}.</p>` : ''}</div>`;
  if (ex.motivo) {
    h += `<fieldset class="fld" style="border:0;padding:0;margin:0"><legend class="lab">Por que está ${modo === 'pedir' ? 'pedindo para apagar' : 'apagando'}? <small>(fica na trilha)</small></legend>
      <div class="motivos" role="radiogroup" aria-label="Motivo">${MOTIVOS.map((m) => `<label><input type="radio" name="mot-${rid}" value="${esc(m)}" data-in="motivo" data-ctx="${esc(ctx)}" ${c.motivo === m ? 'checked' : ''}><span>${esc(m)}</span></label>`).join('')}</div>
      ${c.motivo === 'Outro' ? `<div style="margin-top:8px"><label class="lab" for="out-${rid}">Escreva em poucas palavras</label><textarea id="out-${rid}" data-in="outro" data-ctx="${esc(ctx)}" data-fid="out-${rid}" maxlength="140">${esc(c.outro)}</textarea></div>` : ''}</fieldset>`;
  }
  if (ex.palavra) {
    const okp = norm(c.palavra.trim()) === 'apagar';
    h += `<div><label class="lab" for="pal-${rid}">Para confirmar, digite <b>APAGAR</b></label><div class="pal ${okp ? 'ok' : ''}"><input type="text" id="pal-${rid}" data-in="palavra" data-ctx="${esc(ctx)}" data-fid="pal-${rid}" autocomplete="off" autocapitalize="characters" spellcheck="false" value="${esc(c.palavra)}" aria-describedby="palh-${rid}"><span class="ok">${ic('check')}</span></div><p class="hint" id="palh-${rid}" style="margin-top:4px">Digitar de propósito evita o clique sem querer.</p></div>`;
  }
  const rot = modo === 'pedir' ? `${ic('next')} Enviar pedido ao administrador`
    : modo === 'aprovar' ? `${ic('trash')} Aprovar e apagar`
    : `${ic('trash')} Apagar ${exec.length === 1 ? (unico ? TIPOS[unico.tipo].sing : 'item') : exec.length + ' itens'}`;
  if (modo === 'pedir') h += `<p class="hint">${ic('info')} Nada é apagado agora. O administrador vê o mesmo resumo e decide.</p>`;
  if (bloqN) h += `<p class="hint">${bloqN === 1 ? '1 item bloqueado fica de fora.' : bloqN + ' itens bloqueados ficam de fora.'}</p>`;
  h += `<div><button class="btn ${modo === 'pedir' ? 'btn-pri' : 'btn-danger'} btn-block" data-act="${modo === 'aprovar' ? 'aprovar-ok' : 'confirmar'}" data-ctx="${esc(ctx)}" ${pc.ok ? '' : 'disabled'} aria-describedby="falta-${rid}">${rot}</button>
    <p class="falta" id="falta-${rid}" style="margin-top:6px">${pc.ok ? '' : ic('lock') + esc(pc.falta)}</p></div>`;
  if (unico && modo !== 'aprovar') h += `<div class="alt">Errou só um dado? <button class="link" data-act="acao" data-v="Abrir para corrigir: ${esc(unico.editar)}">Corrigir em vez de apagar</button></div>`;
  return h;
}

/* ================= páginas ================= */
function cabecalho() {
  const admin = S.papel === 'admin';
  const pend = grupos().length;
  const meus = PEDIDOS.filter((p) => p.por === 'Ana Paula' && p.status === 'pendente').length;
  const tabs = admin
    ? [['apagar', 'Apagar', 0], ['pedidos', 'Pedidos', pend], ['trilha', 'Trilha', 0]]
    : [['apagar', 'Apagar', 0], ['pedidos', 'Meus pedidos', meus]];
  return `<div class="crumb">Lançamentos › Excluir lançamentos</div>
  <h1>Excluir lançamentos</h1>
  <p class="lead">${admin ? 'Escolha o que apagar, veja o que muda e confirme. Tudo o que for apagado fica na trilha: quem, quando e o quê.' : 'Escolha o que apagar e veja o que muda. Quem decide é o administrador. Você acompanha o pedido aqui.'}</p>
  <div class="role ${admin ? 'admin' : 'func'}">${ic(admin ? 'shield' : 'user')} ${admin ? 'Administrador: apaga na hora' : 'Funcionário: o administrador aprova'}</div>
  <div class="tabs" role="tablist" aria-label="Seções">${tabs.map(([id, tx, n]) => `<button class="tab" role="tab" id="tab-${id}" aria-selected="${S.aba === id}" aria-controls="painel" tabindex="${S.aba === id ? 0 : -1}" data-act="aba" data-v="${id}">${tx}${n ? `<span class="badge" aria-label="${n} pendentes">${n}</span>` : ''}</button>`).join('')}</div>`;
}
function steps() {
  const pass = S.passo === 'pick' ? (S.tipo ? 1 : 0) : S.passo === 'impacto' ? 2 : 3;
  const nomes = ['O quê', 'Quais', 'Impacto e decisão', 'Pronto'];
  return `<nav class="steps" aria-label="Etapas"><ol>${nomes.map((n, i) => `<li class="${i < pass ? 'done' : i === pass ? 'cur' : ''}" ${i === pass ? 'aria-current="step"' : ''}><span class="dot">${i < pass ? ic('check') : i + 1}</span><span class="lbl">${n}</span></li>`).join('')}</ol></nav>`;
}

function railHtml() {
  const q = norm(S.busca);
  let corpo = '';
  if (q) {
    const lista = Object.values(TIPOS).filter((t) => q.split(/\s+/).every((w) => norm(t.nome + ' ' + t.hint + ' ' + t.kw + ' ' + DOMINIOS.find((d) => d.id === t.dom).nome).includes(w)));
    corpo = lista.length ? `<ul class="dom" style="margin:0">${lista.map((t) => tipoBtn(t, true)).join('')}</ul>` : `<div class="vazio"><h2>Nenhum tipo com "${esc(S.busca)}"</h2><p class="muted">Tente "parto", "vale", "nota", "vacina" ou use "procurar em tudo".</p></div>`;
  } else {
    corpo = DOMINIOS.map((d) => {
      const aberto = S.dom === d.id;
      return `<div class="dom ${d.cad ? 'cad' : ''}">
        <button class="dom-h" data-act="dom" data-v="${d.id}" aria-expanded="${aberto}"><span><span class="dom-n">${d.nome}</span><span class="dom-d">${d.dica}</span></span><span class="cnt" aria-label="${cntDom(d)} registros">${cntDom(d)}</span>${ic('down')}</button>
        <div class="tipos" ${aberto ? '' : 'hidden'}>${d.cad ? `<p class="cad-nota" style="padding-top:8px">${ic('warn')}<span>Cadastros mexem em tudo que usa eles. Por isso ficam separados dos lançamentos.</span></p>` : ''}<ul>${d.tipos.map((t) => tipoBtn(TIPOS[t])).join('')}</ul>${d.cad ? '<p class="hint" style="padding:8px 12px 10px">Mais 5 cadastros (princípio ativo, evento sanitário, protocolo, motivo, safra) seguem o mesmo fluxo.</p>' : ''}</div></div>`;
    }).join('');
  }
  return `<section class="rail" aria-labelledby="h-rail"><h2 class="h-sec" id="h-rail"><b>1.</b> O que você quer apagar?</h2>
    <div class="search">${ic('search')}<label class="sr" for="busca-tipo">Procurar o tipo</label><input type="search" id="busca-tipo" data-in="busca" data-fid="busca-tipo" placeholder="Procurar: parto, vale, nota, vacina…" value="${esc(S.busca)}" autocomplete="off"></div>
    <button class="todos" data-act="tipo" data-v="todos" aria-current="${S.tipo === 'todos'}">${ic('search')} Não sei onde está: procurar em tudo</button>
    ${corpo}</section>`;
}
function tipoBtn(t, comDom) {
  const d = DOMINIOS.find((x) => x.id === t.dom);
  return `<li><button class="tipo" data-act="tipo" data-v="${t.id}" aria-current="${S.tipo === t.id}"><span class="tn">${esc(t.nome)}</span><span class="cnt">${cntTipo(t.id)}</span><span class="th">${comDom ? `<span class="tdom">${d.nome}</span> · ` : ''}${esc(t.hint)}</span></button></li>`;
}

function filtrosHtml(t) {
  const f = S.f, F = t.filtros || F_PADRAO;
  const partes = [...new Set(ITENS.filter((i) => i.tipo === S.tipo && i.parte).map((i) => i.parte))].sort();
  let h = '';
  if (F.includes('periodo') && !t.cad) h += `<div class="fld"><label for="f-ini">De</label><input type="date" id="f-ini" data-in="f.ini" data-fid="f-ini" value="${f.ini}"></div><div class="fld"><label for="f-fim">Até</label><input type="date" id="f-fim" data-in="f.fim" data-fid="f-fim" value="${f.fim}"></div>`;
  if (F.includes('parte') && partes.length) h += `<div class="fld"><label for="f-parte">${esc(t.parteRot || 'Filtrar')}</label><select id="f-parte" data-in="f.parte" data-fid="f-parte"><option value="">Todos</option>${partes.map((p) => `<option ${f.parte === p ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select></div>`;
  if (F.includes('valor')) h += `<div class="fld"><label>Valor (R$)</label><div class="val2"><input type="number" inputmode="decimal" min="0" aria-label="Valor mínimo" placeholder="de" data-in="f.vmin" data-fid="f-vmin" value="${f.vmin}"><input type="number" inputmode="decimal" min="0" aria-label="Valor máximo" placeholder="até" data-in="f.vmax" data-fid="f-vmax" value="${f.vmax}"></div></div>`;
  if (F.includes('situacao')) h += `<fieldset class="fld w4"><legend>Situação das parcelas</legend><div class="rs-seg">${[['todas', 'Todas'], ['aberta', 'Em aberto'], ['atrasada', 'Atrasada'], ['paga', 'Com parcela paga']].map(([v, tx]) => `<label><input type="radio" name="sit" value="${v}" data-in="f.sit" ${f.sit === v ? 'checked' : ''}><span>${tx}</span></label>`).join('')}</div></fieldset>`;
  if (F.includes('busca')) h += `<div class="fld w4 keep"><label for="f-q">Buscar</label><div class="search" style="margin:0">${ic('search')}<input type="search" id="f-q" data-in="f.q" data-fid="f-q" value="${esc(f.q)}" placeholder="${S.tipo === 'financeiro' ? 'número, descrição, fornecedor, nota…' : 'número do animal, nome, produto…'}" autocomplete="off"></div></div>`;
  return h;
}
function mainColHtml() {
  if (!S.tipo) {
    return `<section class="main-col" aria-labelledby="h-quais"><h2 class="h-sec" id="h-quais"><b>2.</b> Quais?</h2><div class="vazio"><h2>Comece escolhendo o que apagar</h2><p class="muted">Escolha um tipo ao lado. Aqui aparecem os registros dele, com filtros que fazem sentido para aquele tipo.</p><ul><li>${ic('pencil')}<span>Errou só um dado? <b>Corrija em vez de apagar</b>. Cada linha tem o atalho.</span></li><li>${ic('list')}<span>Pode marcar vários de uma vez e ver o impacto de todos juntos.</span></li><li>${ic('shield')}<span>Antes de apagar você vê o que some, o que o sistema desfaz e o que impede.</span></li></ul></div></section>`;
  }
  const t = S.tipo === 'todos' ? { nome: 'Tudo (lançamentos, mais recentes primeiro)', filtros: ['periodo', 'busca'], sing: 'item' } : TIPOS[S.tipo];
  const arr = filtrar();
  const vis = arr.slice(0, S.mostrar);
  const selTodos = vis.length > 0 && vis.every((i) => S.sel.includes(i.id));
  const algum = vis.some((i) => S.sel.includes(i.id));
  const ordens = [['recentes', 'Mais recentes'], ['antigos', 'Mais antigos']].concat(S.tipo === 'financeiro' ? [['valor', 'Maior valor']] : [], [['az', 'A–Z']]);
  return `<section class="main-col" aria-labelledby="h-quais">
    <h2 class="h-sec" id="h-quais" tabindex="-1" style="outline:none"><b>2.</b> Quais?</h2>
    <div class="tipo-bar"><h2>${esc(t.nome)}</h2><button class="link" data-act="trocar">Trocar o tipo</button></div>
    <div class="card filtros" role="search" aria-label="Filtros" data-open="${S.fAberto ? 1 : 0}"><button class="btn btn-sm filtros-t" data-act="ftog" aria-expanded="${!!S.fAberto}">${ic('search')} Filtros${temFiltro() ? ' (ativos)' : ''} ${ic('down')}</button>${filtrosHtml(t)}${temFiltro() ? `<div class="filtros-f"><span class="hint">${arr.length} ${arr.length === 1 ? 'resultado' : 'resultados'} com os filtros</span><button class="link" data-act="limpar-f">Limpar filtros</button></div>` : ''}</div>
    <div class="card res"><div class="res-h"><label class="all"><input type="checkbox" data-act="all" ${selTodos ? 'checked' : ''} ${vis.length ? '' : 'disabled'} aria-label="Marcar todos os ${vis.length} da lista"> Marcar ${vis.length ? vis.length : ''} ${vis.length === 1 ? 'da lista' : 'da lista'}</label>
      <div class="ord"><span>${arr.length} ${arr.length === 1 ? 'registro' : 'registros'}</span><label class="sr" for="ord">Ordenar por</label><select id="ord" data-in="f.ord" data-fid="ord">${ordens.map(([v, tx]) => `<option value="${v}" ${S.f.ord === v ? 'selected' : ''}>${tx}</option>`).join('')}</select></div></div>
      ${arr.length ? `<ul id="lista">${vis.map(rowHtml).join('')}</ul>` : `<div class="sem-res"><strong>Nada com esses filtros.</strong>${temFiltro() ? 'Tire um filtro para ver mais. <button class="link" data-act="limpar-f">Limpar filtros</button>' : 'Não há registros deste tipo.'}</div>`}
      ${arr.length > vis.length ? `<div class="mais"><button class="btn btn-sm" data-act="mais">Mostrar mais ${Math.min(8, arr.length - vis.length)} (faltam ${arr.length - vis.length})</button></div>` : ''}</div>
  </section>`;
}
function rowHtml(it) {
  const sel = S.sel.includes(it.id);
  const fin = it.tipo === 'financeiro';
  const tt = S.tipo === 'todos' ? `<span class="chip blue">${esc(TIPOS[it.tipo].sing)}</span>` : '';
  const aberto = !!S.exp[it.id];
  let side = '';
  if (it.valor != null) side += `<strong class="num">${brl(it.valor)}</strong>`;
  if (it.data) side += `<span class="rs num">${dbr(it.data)}</span>`;
  let exp = '';
  if (fin) {
    exp = `<button class="exp" data-act="exp" data-id="${it.id}" aria-expanded="${aberto}" aria-controls="p-${it.id}">${plural(it.parcelas.length, 'parcela', 'parcelas')}${it.parcelas.some((p) => p.paga) ? ` · ${it.parcelas.filter((p) => p.paga).length} ${it.receita ? 'recebida' : 'paga'}${it.parcelas.filter((p) => p.paga).length > 1 ? 's' : ''}` : ''} ${ic('down')}</button>`;
  }
  let expBody = '';
  if (fin && aberto) {
    expBody = `<div class="rexp" id="p-${it.id}"><table class="parc"><thead><tr><th scope="col">Parcela</th><th scope="col">Vence</th><th scope="col">Valor</th><th scope="col">Situação</th></tr></thead><tbody>${it.parcelas.map((p) => `<tr><td>${p.n}/${it.parcelas.length}</td><td>${dbr(p.venc)}</td><td>${brl(p.valor)}</td><td>${p.paga ? `<span class="chip amber">${it.receita ? 'Recebida' : 'Paga'} ${dcurta(p.pagoEm)}</span>` : p.venc < HOJE ? '<span class="chip red">Atrasada</span>' : '<span class="chip">Em aberto</span>'}</td></tr>`).join('')}</tbody></table>
      <div class="parc-n"><span>Não dá para apagar uma parcela só: a nota inteira vai junto.</span><button class="link" data-act="acao" data-v="Abrir para corrigir: ${esc(it.editar)}" style="min-height:32px;padding:2px 0">Corrigir em vez de apagar</button></div></div>`;
  }
  return `<li class="row ${sel ? 'is-sel' : ''}" data-row="${it.id}"><label class="ck"><input type="checkbox" data-act="sel" data-id="${it.id}" ${sel ? 'checked' : ''} aria-label="Selecionar ${esc(it.titulo)}"></label>
    <div class="rmain"><div class="rt">${esc(it.titulo)}</div><div class="rs">${esc(it.sub)}</div><div class="rc">${tt}${chipsDe(it)}</div>${exp}</div>
    <div class="rside">${side}</div>${expBody}</li>`;
}
function trayResumo() {
  const por = {};
  S.sel.map(getItem).filter(Boolean).forEach((i) => { por[i.tipo] = (por[i.tipo] || 0) + 1; });
  const partes = Object.entries(por).map(([t, n]) => plural(n, TIPOS[t].sing, TIPOS[t].plur));
  const A = analisa(S.sel);
  let extra = '';
  if (A.tot.din) extra += ` · ${brl(A.tot.din)} em contas`;
  if (A.bloq.length) extra += ` · <span style="color:var(--alert-fg);font-weight:600">${plural(A.bloq.length, 'tem bloqueio', 'têm bloqueio')}</span>`;
  return partes.join(', ') + extra;
}
function renderTray() {
  const on = S.aba === 'apagar' && S.passo === 'pick' && S.sel.length > 0;
  trayEl.classList.toggle('on', on);
  trayEl.setAttribute('aria-hidden', on ? 'false' : 'true');
  if (!on) { trayEl.querySelectorAll('button').forEach((b) => (b.tabIndex = -1)); return; }
  trayEl.innerHTML = `<div class="tray-in"><div class="tray-t"><strong>${plural(S.sel.length, 'selecionado', 'selecionados')}</strong><span>${trayResumo()}</span></div><button class="btn" data-act="limpar">Limpar</button><button class="btn btn-pri" data-act="conferir">Conferir o que muda ${ic('next')}</button></div>`;
}

function renderPick() { return `<div class="pick" data-has-tipo="${S.tipo ? 1 : 0}">${railHtml()}${mainColHtml()}</div>`; }

function renderImpacto() {
  const A = analisa(S.sel);
  if (!A.itens.length) { S.passo = 'pick'; return renderPick(); }
  const admin = S.papel === 'admin';
  const modo = admin ? 'apagar' : 'pedir';
  const back = `<button class="link back" data-act="voltar">${ic('back')} Mudar a seleção</button>`;
  if (S.loadImp) {
    return `${back}<h2 class="h2" id="h-imp" tabindex="-1">Calculando o que muda…</h2><p class="muted" style="margin-bottom:12px">Olhando parcelas, estoque, lactação e vínculos.</p><div class="sk" aria-busy="true"><div></div><div></div><div></div></div>`;
  }
  const s = A.tot;
  let frase;
  if (!A.exec.length) frase = `Nada pode ser apagado agora: ${A.bloq.length === 1 ? 'o item escolhido tem' : 'os ' + A.bloq.length + ' itens escolhidos têm'} bloqueio. Resolva primeiro o que está em vermelho.`;
  else {
    const mesmo = A.exec.every((i) => i.tipo === A.exec[0].tipo);
    const nome = mesmo ? plural(A.exec.length, TIPOS[A.exec[0].tipo].sing, TIPOS[A.exec[0].tipo].plur) : plural(A.exec.length, 'item', 'itens');
    frase = `${admin ? 'Você vai apagar' : 'Você está pedindo para apagar'} <b>${nome}</b>${s.n > A.exec.length ? ` (${plural(s.n, 'registro', 'registros')} no total)` : ''}`;
    if (s.din) frase += ` e tirar <b>${brl(s.din)}</b> das contas`;
    frase += '. ';
    if (s.rev) frase += `O sistema também vai desfazer <b>${plural(s.rev, 'ajuste', 'ajustes')}</b> sozinho (estoque, lactação, saldos). `;
    if (A.bloq.length) frase += `<b>${plural(A.bloq.length, 'item fica', 'itens ficam')}</b> de fora por causa de bloqueio. `;
    frase += admin ? 'Depois de apagar, não dá para desfazer.' : 'Nada é apagado agora: o administrador decide.';
  }
  const nAv = A.exec.reduce((a, i) => a + i.imp.avisos.length, 0);
  const stat = (k, n, tx, cls = '') => `<button class="stat ${n ? '' : 'zero'}" data-act="goto" data-v="${k}" ${n ? '' : 'disabled'}>${ic(BL[k].ic)} <b>${n}</b> ${tx}</button>`;
  const stats = `<div class="stats">${stat('bloqueia', A.bloq.length, A.bloq.length === 1 ? 'bloqueio' : 'bloqueios')}${stat('apagar', s.n, s.n === 1 ? 'apagado' : 'apagados')}${stat('reverter', s.rev, s.rev === 1 ? 'revertido' : 'revertidos')}${stat('avisos', nAv, nAv === 1 ? 'aviso' : 'avisos')}</div>`;
  const escolha = `<div class="card esc anim" style="--i:1"><button class="esc-h" data-act="esc" aria-expanded="${S.escAberto}"><span><b>O que você escolheu</b> <span class="muted">(${A.itens.length})</span></span>${ic('down')}</button>
    ${S.escAberto ? `<ul class="esc-l">${A.itens.map((i) => `<li><div><div class="rt">${esc(i.titulo)}</div><div class="rs">${esc(TIPOS[i.tipo].nome)}</div></div><div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end">${i.imp.bloqueia.length ? '<span class="chip red">Bloqueado</span>' : `<span class="chip ${riscoItem(i) === 'alto' ? 'red' : riscoItem(i) === 'medio' ? 'amber' : 'green'}">${RISCO_TXT[riscoItem(i)][0]}</span>`}<button class="btn btn-sm" data-act="tirar" data-id="${i.id}" aria-label="Tirar ${esc(i.titulo)} da seleção">${ic('x')} Tirar</button></div></li>`).join('')}</ul>` : ''}</div>`;
  const esq = `<div class="imp-col"><div class="card resumo anim" style="--i:0"><p class="resumo-f">${frase}</p>${stats}${A.exec.length ? `<p class="hint" style="margin-top:10px"><a class="link" href="#decisao" data-act="goto" data-v="decisao" style="padding:0;min-height:0">Ir para a decisão</a></p>` : ''}</div>${escolha}${blocosHtml(A.exec, A.bloq, 'imp')}</div>`;
  let dir;
  if (A.exec.length) dir = `<aside class="card decide anim" style="--i:2" id="decisao" aria-labelledby="h-dec"><h3 id="h-dec">${admin ? 'Sua decisão' : 'Seu pedido'}</h3>${decideHtml('imp', A.exec, A.bloq.length, modo)}</aside>`;
  else dir = `<aside class="card decide anim" style="--i:2" id="decisao"><h3>Sem o que confirmar</h3><p class="muted">Todos os itens têm bloqueio. Resolva o que está em vermelho e volte.</p><button class="btn btn-block" data-act="voltar">${ic('back')} Mudar a seleção</button></aside>`;
  return `${back}<h2 class="h2" id="h-imp" tabindex="-1">Conferir antes de ${admin ? 'apagar' : 'pedir'}</h2><p class="muted" style="margin-bottom:14px">${admin ? 'Leia o que muda. Só depois confirme.' : 'Este é o mesmo resumo que o administrador vai ver.'}</p><div class="imp">${esq}${dir}</div>`;
}

function renderPronto() {
  const r = S.res;
  if (!r) { S.passo = 'pick'; return renderPick(); }
  const lis = (a) => a.map((x) => `<li>${esc(x)}</li>`).join('');
  const nota = (cls, icn, txt, btn) => `<div class="note ${cls}">${ic(icn)}<div>${txt}${btn || ''}</div></div>`;
  if (r.tipo === 'apagado') {
    return `<div class="slip"><span class="stamp">Apagado · ${dbr(HOJE)}</span>
      <div class="slip-h"><span class="okc"><svg viewBox="0 0 24 24" aria-hidden="true"><path class="check-tracado" d="M20 6 9 17l-5-5"/></svg></span><div><h2 tabindex="-1" id="h-pronto">Pronto. Apagado.</h2><p class="muted">Comprovante ${r.id}</p></div></div>
      <p class="slip-lead"><b data-count="${r.n}">${r.n}</b> ${r.n === 1 ? 'registro foi apagado' : 'registros foram apagados'}${r.din ? ` e <b>${brl(r.din)}</b> saíram das contas` : ''}.${r.rev ? ` O sistema desfez <b data-count="${r.rev}">${r.rev}</b> ${r.rev === 1 ? 'ajuste' : 'ajustes'} sozinho.` : ''}</p>
      ${r.fora.length ? nota('', 'warn', `<b>${plural(r.fora.length, 'item ficou', 'itens ficaram')} de fora</b> por causa de bloqueio: ${esc(r.fora.map((f) => f.titulo).join('; '))}.`, ` <button class="link" data-act="voltar-bloq">Ver os bloqueados</button>`) : ''}
      ${r.encerrados ? nota('bl', 'info', `${plural(r.encerrados, 'pedido pendente sobre', 'pedidos pendentes sobre')} este item ${r.encerrados === 1 ? 'foi encerrado' : 'foram encerrados'} junto.`) : ''}
      <dl><dt>Quem</dt><dd>${esc(r.quem)} (administrador)</dd><dt>Quando</dt><dd class="num">${dbr(HOJE)} às ${hbr(AGORA)}</dd><dt>Motivo</dt><dd>${esc(r.motivo || '— (risco baixo, sem motivo pedido)')}</dd></dl>
      <div class="slip-s"><h3 class="caps muted" style="margin-bottom:8px">O que foi apagado</h3><ul>${lis(r.apagado)}</ul></div>
      ${r.revertido.length ? `<div class="slip-s"><h3 class="caps muted" style="margin-bottom:8px">O que o sistema ajustou</h3><ul>${lis(r.revertido)}</ul></div>` : ''}
      <div class="slip-f"><button class="btn btn-pri" data-act="aba" data-v="trilha">${ic('list')} Ver na trilha</button><button class="btn" data-act="novo">Apagar outro</button><p>Fica na trilha com quem, quando e o quê. Qualquer administrador consegue consultar.</p></div></div>`;
  }
  const dupHtml = r.dup.length ? nota('bl', 'copy', `Você já tinha pedido para apagar ${r.dup.map((d) => esc(d)).join(', ')}. Não criei outro pedido: o anterior continua valendo.`, ` <button class="link" data-act="aba" data-v="pedidos">Ver meus pedidos</button>`) : '';
  const juntoHtml = r.junto.length ? nota('bl', 'user', `${esc(r.junto.join(' e '))} também pediu para apagar o mesmo. O administrador vê tudo junto, num pedido só.`) : '';
  return `<div class="slip"><span class="stamp azul">Pedido enviado</span>
    <div class="slip-h"><span class="okc wait"><svg viewBox="0 0 24 24" aria-hidden="true"><path class="check-tracado" d="M20 6 9 17l-5-5"/></svg></span><div><h2 tabindex="-1" id="h-pronto">Pedido enviado ao administrador</h2><p class="muted">Nada foi apagado ainda</p></div></div>
    <p class="slip-lead">${r.criados ? `Seu pedido para apagar <b>${esc(r.titulos.join('; '))}</b> chegou ao Jairo com o resumo do que muda.` : 'Nenhum pedido novo foi criado.'}</p>
    ${dupHtml}${juntoHtml}${r.fora.length ? nota('', 'warn', `<b>${plural(r.fora.length, 'item ficou', 'itens ficaram')} de fora</b> por causa de bloqueio: ${esc(r.fora.map((f) => f.titulo).join('; '))}.`) : ''}
    <ol class="tl"><li class="on"><span class="p">${ic('check')}</span><span>Enviado agora, ${hbr(AGORA)}</span></li><li><span class="p">${ic('clock')}</span><span>O administrador analisa</span></li><li><span class="p"></span><span>Você vê a resposta em "Meus pedidos"</span></li></ol>
    <dl><dt>Quem pediu</dt><dd>${esc(r.quem)}</dd><dt>Motivo</dt><dd>${esc(r.motivo)}</dd></dl>
    <div class="slip-f"><button class="btn btn-pri" data-act="aba" data-v="pedidos">${ic('clock')} Acompanhar meus pedidos</button><button class="btn" data-act="novo">Pedir outro</button></div></div>`;
}

/* ---------- pedidos ---------- */
function alvoExiste(p) { return !!(p.alvo && getItem(p.alvo)); }
function grupos() {
  const mapa = {};
  PEDIDOS.filter((p) => p.status === 'pendente').forEach((p) => { (mapa[p.alvo || p.id] = mapa[p.alvo || p.id] || []).push(p); });
  return Object.entries(mapa).map(([k, ps]) => ({ k, ps, item: getItem(k), sumiu: !getItem(k) }));
}
function pedidosAdmin() {
  const gs = grupos();
  const decididos = PEDIDOS.filter((p) => p.status !== 'pendente');
  let h = `<div class="lista-h"><div><h2 class="h2" id="h-ped" tabindex="-1">Pedidos de exclusão</h2><p class="muted">${gs.length ? `${plural(gs.length, 'item esperando', 'itens esperando')} sua decisão. Pedidos repetidos já vêm juntos.` : ''}</p></div></div>`;
  if (S.flash) h += `<div class="flash" role="status">${ic('check')}<span>${esc(S.flash.txt)}</span>${S.flash.trilha ? `<button class="link" data-act="aba" data-v="trilha" style="min-height:32px;padding:0">Ver na trilha</button>` : ''}</div>`;
  if (!gs.length) {
    h += `<div class="vazio" style="text-align:center"><span class="okc" style="margin:0 auto 10px"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg></span><h2>Nenhum pedido esperando</h2><p class="muted">O livro está em dia. Quando alguém pedir para apagar algo, aparece aqui com o resumo do que muda.</p></div>`;
  }
  gs.forEach((g, n) => { h += pedidoCard(g, n); });
  if (decididos.length) {
    h += `<h3 class="h-sec" style="margin:22px 0 8px">Já decididos</h3>` + decididos.map((p) => `<div class="card ped anim"><div class="ped-h"><div class="ped-t"><div><div class="rt">${esc(titPedido(p))}</div><div class="quem">${esc(p.por)} pediu em ${dbr(p.quando)}</div></div>${statusChip(p)}</div>${p.motivoRej ? `<div class="quem">Motivo da rejeição: <q>${esc(p.motivoRej)}</q></div>` : ''}</div></div>`).join('');
  }
  return h;
}
const titPedido = (p) => (getItem(p.alvo) ? getItem(p.alvo).titulo : p.titulo || '(item)');
function statusChip(p) {
  if (p.status === 'pendente') return '<span class="chip blue">' + ic('clock') + ' Aguardando</span>';
  if (p.status === 'aprovada') return '<span class="chip green">' + ic('check') + ` Aprovado${p.decididoPor ? ' por ' + esc(p.decididoPor) : ''}</span>`;
  if (p.status === 'rejeitada') return '<span class="chip amber">' + ic('x') + ` Rejeitado${p.decididoPor ? ' por ' + esc(p.decididoPor) : ''}</span>`;
  return '<span class="chip">' + esc(p.status) + '</span>';
}
function pedidoCard(g, n) {
  const key = 'g' + g.k;
  const aberto = !!S.aberto[key];
  const it = g.item;
  const A = it ? analisa([it.id]) : null;
  const chips = [];
  if (g.ps.length > 1) chips.push(`<span class="chip blue">${ic('copy')} Pedido repetido: ${g.ps.length} pessoas</span>`);
  if (g.ps.some((p) => p.mudou)) chips.push(`<span class="chip amber">${ic('warn')} Mudou desde o pedido</span>`);
  if (g.sumiu) chips.push(`<span class="chip red">${ic('ban')} Item não existe mais</span>`);
  else if (A.bloq.length) chips.push(`<span class="chip red">${ic('ban')} Bloqueado agora</span>`);
  else chips.push(`<span class="chip ${riscoItem(it) === 'alto' ? 'red' : riscoItem(it) === 'medio' ? 'amber' : 'green'}">${RISCO_TXT[riscoItem(it)][0]}</span>`);
  const titulo = it ? it.titulo : g.ps[0].titulo;
  const tipoNome = it ? TIPOS[it.tipo].nome : TIPOS[g.ps[0].tipo].nome;
  let corpo = '';
  if (aberto) {
    if (g.sumiu) {
      corpo = `<div class="note rd">${ic('ban')}<div><b>Não há mais o que apagar.</b> Este item já foi apagado ou não existe mais. Você pode arquivar o pedido.</div></div><div><button class="btn" data-act="arquivar" data-k="${esc(g.k)}">${ic('check')} Arquivar o pedido</button></div>`;
    } else {
      const ctx = 'ped:' + g.k;
      const modo = S.modo[key];
      const mudou = g.ps.find((p) => p.mudou);
      corpo = `${mudou ? `<div class="note">${ic('warn')}<div><b>Mudou desde o pedido.</b> ${esc(mudou.mudou)}</div></div>` : ''}
        <div class="calc">${ic('clock')} Resumo calculado agora, ${hbr(AGORA)}. Não é o de quando o pedido foi feito.</div>
        <div class="imp-col" style="gap:10px">${blocosHtml(A.exec, A.bloq, ctx)}</div>
        <div class="modo" role="group" aria-label="Decisão"><button class="btn ${modo === 'aprovar' ? 'btn-pri' : ''}" data-act="modo" data-k="${key}" data-v="aprovar" aria-pressed="${modo === 'aprovar'}" ${A.exec.length ? '' : 'disabled'}>${ic('check')} Aprovar e apagar</button><button class="btn ${modo === 'rejeitar' ? 'btn-pri' : ''}" data-act="modo" data-k="${key}" data-v="rejeitar" aria-pressed="${modo === 'rejeitar'}">${ic('x')} Rejeitar</button></div>`;
      if (modo === 'aprovar' && A.exec.length) corpo += `<div class="card" style="padding:14px;display:grid;gap:14px;max-width:460px">${decideHtml(ctx, A.exec, A.bloq.length, 'aprovar')}</div>`;
      if (modo === 'rejeitar') corpo += rejeitarHtml(ctx, g.k);
      if (!A.exec.length) corpo += `<p class="hint">${ic('lock')} Não dá para aprovar agora: tem bloqueio. Rejeite explicando o que fazer, ou espere o funcionário resolver.</p>`;
    }
  }
  return `<article class="card ped anim" style="--i:${n}" aria-labelledby="pt-${esc(g.k)}"><div class="ped-h"><div class="ped-t"><div><div class="rt" id="pt-${esc(g.k)}">${esc(titulo)}</div><div class="rs">${esc(tipoNome)}</div></div><div class="rc" style="margin:0">${chips.join('')}</div></div>
      <div class="quem">${g.ps.map((p) => `<span>${ic('user')} <b>${esc(p.por)}</b>, ${dbr(p.quando)} ${hbr(p.quando)}: <q>${esc(p.motivo)}</q></span>`).join('')}</div>
      <div><button class="btn btn-sm ${aberto ? '' : 'btn-pri'}" data-act="abrir" data-k="${key}" aria-expanded="${aberto}">${aberto ? 'Fechar' : 'Analisar o pedido'} ${ic('down')}</button></div></div>
    <div class="ped-b" ${aberto ? '' : 'hidden'}>${corpo}</div></article>`;
}
function rejeitarHtml(ctx, k) {
  const c = confDe(ctx + ':rej');
  const rid = ctx.replace(/[^a-z0-9]/gi, '_');
  const rapidos = ['Já foi pago: estorne antes e peça de novo', 'Corrija o dado em vez de apagar', 'Esse registro é necessário', 'Outro'];
  const ok = c.motivo && (c.motivo !== 'Outro' || c.outro.trim().length >= 3);
  return `<div class="card" style="padding:14px;display:grid;gap:12px;max-width:520px"><fieldset class="fld" style="border:0;padding:0;margin:0"><legend class="lab">Por que está rejeitando? <small>(quem pediu vai ler isto)</small></legend>
    <div class="motivos" role="radiogroup">${rapidos.map((m) => `<label><input type="radio" name="rej-${rid}" value="${esc(m)}" data-in="motivo-rej" data-ctx="${esc(ctx + ':rej')}" ${c.motivo === m ? 'checked' : ''}><span>${esc(m)}</span></label>`).join('')}</div>
    ${c.motivo === 'Outro' ? `<div style="margin-top:8px"><label class="lab" for="ro-${rid}">Escreva em poucas palavras</label><textarea id="ro-${rid}" data-in="outro" data-ctx="${esc(ctx + ':rej')}" data-fid="ro-${rid}" maxlength="140">${esc(c.outro)}</textarea></div>` : ''}</fieldset>
    <div><button class="btn btn-pri btn-block" data-act="rejeitar-ok" data-k="${esc(k)}" data-ctx="${esc(ctx + ':rej')}" ${ok ? '' : 'disabled'}>${ic('x')} Rejeitar pedido</button>${ok ? '' : `<p class="falta" style="margin-top:6px">${ic('lock')} Sem motivo não dá para rejeitar.</p>`}</div></div>`;
}
function meusPedidos() {
  const meus = PEDIDOS.filter((p) => p.por === 'Ana Paula');
  let h = `<div class="lista-h"><div><h2 class="h2" id="h-ped" tabindex="-1">Meus pedidos</h2><p class="muted">Aqui você vê o que pediu para apagar e o que o administrador respondeu.</p></div></div>`;
  if (S.flash) h += `<div class="flash" role="status">${ic('check')}<span>${esc(S.flash.txt)}</span></div>`;
  if (!meus.length) h += `<div class="vazio"><h2>Você ainda não pediu nada</h2><p class="muted">Na aba Apagar, escolha o registro e envie o pedido.</p></div>`;
  meus.forEach((p, n) => {
    const it = getItem(p.alvo);
    h += `<article class="card ped anim" style="--i:${n}"><div class="ped-h"><div class="ped-t"><div><div class="rt">${esc(titPedido(p))}</div><div class="rs">${esc(it ? TIPOS[it.tipo].nome : (TIPOS[p.tipo] ? TIPOS[p.tipo].nome : ''))} · pedido de ${dbr(p.quando)} às ${hbr(p.quando)}</div></div>${statusChip(p)}</div>
      <div class="quem"><span>Seu motivo: <q>${esc(p.motivo)}</q></span></div>
      ${p.status === 'aprovada' ? `<div class="note bl" style="margin:0">${ic('check')}<div>Apagado em ${dbr(p.decididoEm)} por ${esc(p.decididoPor)}.</div></div>` : ''}
      ${p.status === 'rejeitada' ? `<div class="note" style="margin:0">${ic('warn')}<div><b>${esc(p.decididoPor)} respondeu:</b> ${esc(p.motivoRej)}${it ? '' : ''}<div style="margin-top:6px"><button class="btn btn-sm" data-act="acao" data-v="Abrir para corrigir o registro">${ic('pencil')} Abrir para corrigir</button></div></div></div>` : ''}
      ${p.status === 'pendente' ? `<ol class="tl" style="padding:0"><li class="on"><span class="p">${ic('check')}</span><span>Enviado em ${dbr(p.quando)}</span></li><li><span class="p">${ic('clock')}</span><span>O administrador ainda não respondeu</span></li></ol><div><button class="btn btn-sm" data-act="cancelar" data-id="${p.id}">${ic('x')} Cancelar meu pedido</button></div>` : ''}
      </div></article>`;
  });
  return h;
}
function trilhaHtml() {
  const f = S.trFiltro;
  const lista = TRILHA.filter((t) => f === 'tudo' || (f === 'apagou' && (t.acao === 'apagou' || t.acao === 'aprovou')) || (f === 'pedidos' && t.pedidoDe) || (f === 'rejeitou' && t.acao === 'rejeitou'));
  let h = `<div class="lista-h"><div><h2 class="h2" id="h-tr" tabindex="-1">Trilha de exclusões</h2><p class="muted">Quem apagou, quando e o quê. Vale para o administrador também.</p></div></div>
  <div class="fcs" role="group" aria-label="Filtrar trilha">${[['tudo', 'Tudo'], ['apagou', 'Apagados'], ['pedidos', 'Vieram de pedido'], ['rejeitou', 'Rejeitados']].map(([v, tx]) => `<button class="tab" style="min-height:40px" data-act="trf" data-v="${v}" aria-pressed="${f === v}" ${f === v ? 'aria-current="true"' : ''}>${tx}</button>`).join('')}</div>`;
  if (S.flash && S.flash.trilha) h += `<div class="flash" role="status">${ic('check')}<span>${esc(S.flash.txt)}</span></div>`;
  h += lista.map((t, n) => {
    const aberto = !!S.trAberto[t.id];
    const verbo = t.acao === 'apagou' ? 'apagou' : t.acao === 'aprovou' ? `aprovou o pedido de ${t.pedidoDe} e apagou` : `rejeitou o pedido de ${t.pedidoDe} para apagar`;
    return `<article class="card tr anim" style="--i:${Math.min(n, 6)}"><button class="tr-h" data-act="tra" data-id="${t.id}" aria-expanded="${aberto}"><span class="tr-ic ${t.acao}">${ic(t.acao === 'rejeitou' ? 'x' : t.acao === 'aprovou' ? 'check' : 'trash')}</span><span><span class="rt">${esc(t.quem)} ${verbo}</span><span class="rs" style="display:block">${esc(t.titulo)}</span></span><span class="tr-w num">${dbr(t.quando)} · ${hbr(t.quando)}</span></button>
      <div class="tr-b" ${aberto ? '' : 'hidden'}><div><h4>Motivo</h4><p>${esc(t.motivo || '—')}</p></div>${t.apagado.length ? `<div><h4>O que foi apagado</h4><ul>${t.apagado.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}${t.revertido.length ? `<div><h4>O que o sistema ajustou</h4><ul>${t.revertido.map((x) => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}<p class="hint">Comprovante ${t.id} · ${esc(TIPOS[t.tipo] ? TIPOS[t.tipo].nome : t.tipo)}</p></div></article>`;
  }).join('') || '<div class="vazio"><h2>Nada por aqui</h2><p class="muted">Nenhum registro com esse filtro.</p></div>';
  return h;
}

/* ================= render ================= */
function build() {
  let corpo;
  if (S.aba === 'apagar') {
    corpo = steps() + (S.passo === 'pick' ? renderPick() : S.passo === 'impacto' ? renderImpacto() : renderPronto());
  } else if (S.aba === 'pedidos') corpo = S.papel === 'admin' ? pedidosAdmin() : meusPedidos();
  else corpo = trilhaHtml();
  return cabecalho() + `<div id="painel" role="tabpanel" aria-labelledby="tab-${S.aba}">${corpo}</div>`;
}
function render(o = {}) {
  const a = document.activeElement;
  const fid = a && a.closest && a.closest('#view') ? a.dataset.fid : null;
  const ss = fid && a.selectionStart != null ? [a.selectionStart, a.selectionEnd] : null;
  view.innerHTML = build();
  view.querySelectorAll('[data-act]').forEach((el) => { if (!el.dataset.fid) el.dataset.fid = el.dataset.act + '|' + (el.dataset.id || el.dataset.v || el.dataset.k || el.dataset.ctx || ''); });
  view.querySelectorAll('[data-in]').forEach((el) => { if (!el.dataset.fid) el.dataset.fid = 'in|' + el.dataset.in + '|' + (el.value || ''); });
  if (o.enter) { view.classList.add('enter'); clearTimeout(render.t); render.t = setTimeout(() => view.classList.remove('enter'), 900); }
  if (o.focus) {
    const el = view.querySelector(o.focus);
    if (el) el.focus({ preventScroll: !!o.noscroll });
  } else if (fid) {
    const el = view.querySelector(`[data-fid="${CSS.escape(fid)}"]`);
    if (el) { el.focus({ preventScroll: true }); if (ss) { try { el.setSelectionRange(ss[0], ss[1]); } catch (e) { /* tipo sem seleção */ } } }
  }
  if (view.classList.contains('enter')) animaNumeros();
  renderTray();
}
function animaNumeros() {
  if (reduz) return;
  view.querySelectorAll('[data-count]').forEach((el) => {
    const fim = Number(el.dataset.count), t0 = performance.now(), dur = 280;
    const passo = (t) => { const p = Math.min(1, (t - t0) / dur); el.textContent = Math.round(fim * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(passo); };
    el.textContent = '0'; requestAnimationFrame(passo);
  });
}

/* ================= ações ================= */
function irImpacto() {
  S.passo = 'impacto'; S.loadImp = true; S.conf = {}; S.col = {}; S.fil = {}; S.escAberto = false; S.flash = null;
  render({ enter: true, focus: '#h-imp' });
  window.scrollTo({ top: 0 });
  setTimeout(() => {
    S.loadImp = false;
    if (S.passo === 'impacto') { render({ enter: true, focus: '#h-imp', noscroll: true }); say(resumoVoz()); }
  }, reduz ? 60 : 260);
}
function resumoVoz() { const A = analisa(S.sel); return `Impacto calculado: ${A.tot.n} registros a apagar, ${A.tot.rev} ajustes, ${A.bloq.length} bloqueios. Risco ${A.risco}.`; }

function executar(modoAprovar, exec, motivo, pedidoDe) {
  const n = TRILHA.length + 91 - 6; // EX-2026-0091 em diante
  const id = 'EX-2026-' + String(n).padStart(4, '0');
  const tot = exec.reduce((a, i) => { const t = totaisImp(i); a.n += t.n; a.din += t.din; a.rev += t.rev; return a; }, { n: 0, din: 0, rev: 0 });
  const apagado = exec.flatMap((i) => i.imp.apagar.map((e) => e.t + (exec.length > 1 ? ` (${i.titulo})` : '')));
  const revertido = exec.flatMap((i) => i.imp.reverter.map((e) => `${e.t}: ${e.c}`));
  const ids = exec.map((i) => i.id);
  let encerrados = 0;
  ITENS = ITENS.filter((i) => !ids.includes(i.id));
  PEDIDOS.forEach((p) => { if (p.status === 'pendente' && ids.includes(p.alvo)) { encerrados++; p.status = 'aprovada'; p.decididoPor = EU(); p.decididoEm = AGORA; p.titulo = p.titulo || ''; p.encerrado = true; } });
  TRILHA.unshift({ id, quando: AGORA, quem: EU(), acao: pedidoDe ? 'aprovou' : 'apagou', pedidoDe, titulo: exec.length === 1 ? exec[0].titulo : `${exec.length} itens: ${exec.map((i) => i.titulo).join('; ')}`, tipo: exec[0].tipo, motivo, apagado, revertido });
  return { id, n: tot.n, din: tot.din, rev: tot.rev, apagado, revertido, encerrados: pedidoDe ? 0 : encerrados, ids };
}

const H = {
  aba(el) { S.aba = el.dataset.v; if (S.aba !== 'trilha' && S.aba !== 'pedidos') S.flash = null; render({ enter: true, focus: S.aba === 'apagar' ? null : '#h-' + (S.aba === 'trilha' ? 'tr' : 'ped') }); window.scrollTo({ top: 0 }); },
  dom(el) { S.dom = S.dom === el.dataset.v ? null : el.dataset.v; render(); },
  tipo(el) {
    S.tipo = el.dataset.v; S.f = NOVO_F(); S.mostrar = 8; S.exp = {};
    render({ focus: '#h-quais' });
    if (window.matchMedia('(max-width:760px)').matches) window.scrollTo({ top: 0 });
    say(`${S.tipo === 'todos' ? 'Tudo' : TIPOS[S.tipo].nome}: ${filtrar().length} registros`);
  },
  ftog() { S.fAberto = !S.fAberto; render(); },
  trocar() { S.tipo = null; render({ focus: '#busca-tipo' }); },
  'limpar-f'() { S.f = { ...NOVO_F(), ord: S.f.ord }; render({ focus: '#h-quais', noscroll: true }); },
  mais() { S.mostrar += 8; render(); },
  exp(el) { S.exp[el.dataset.id] = !S.exp[el.dataset.id]; render(); },
  sel(el) {
    const id = el.dataset.id, on = el.checked;
    S.sel = on ? [...new Set([...S.sel, id])] : S.sel.filter((x) => x !== id);
    const row = view.querySelector(`[data-row="${id}"]`); if (row) row.classList.toggle('is-sel', on);
    syncAll(); renderTray(); say(`${S.sel.length} selecionados`);
  },
  all(el) {
    const vis = filtrar().slice(0, S.mostrar).map((i) => i.id);
    S.sel = el.checked ? [...new Set([...S.sel, ...vis])] : S.sel.filter((x) => !vis.includes(x));
    view.querySelectorAll('[data-row]').forEach((r) => { const on = S.sel.includes(r.dataset.row); r.classList.toggle('is-sel', on); const c = r.querySelector('input[type=checkbox]'); if (c) c.checked = on; });
    renderTray(); say(`${S.sel.length} selecionados`);
  },
  limpar() { S.sel = []; render(); say('Seleção limpa'); },
  conferir() { irImpacto(); },
  voltar() { S.passo = 'pick'; render({ enter: true, focus: '#h-quais', noscroll: true }); },
  'voltar-bloq'() { S.passo = 'impacto'; S.res = null; irImpacto(); },
  esc() { S.escAberto = !S.escAberto; render(); },
  tirar(el) { S.sel = S.sel.filter((x) => x !== el.dataset.id); if (!S.sel.length) { S.passo = 'pick'; render({ enter: true }); } else render(); },
  bloco(el) { S.col[el.dataset.k] = !(S.col[el.dataset.k] === true); render(); },
  fil(el) { S.fil[el.dataset.k] = !S.fil[el.dataset.k]; render(); },
  goto(el, e) {
    e && e.preventDefault();
    const v = el.dataset.v;
    const alvo = v === 'decisao' ? document.getElementById('decisao') : view.querySelector(`[data-bloco="${v}"]`);
    if (alvo) { alvo.scrollIntoView({ behavior: reduz ? 'auto' : 'smooth', block: 'start' }); const f = alvo.querySelector('button,input,textarea'); if (f) f.focus({ preventScroll: true }); }
  },
  acao(el) { toast('No sistema real isto abre: ' + el.dataset.v); },
  novo() { S.passo = 'pick'; S.res = null; S.tipo = null; render({ enter: true }); window.scrollTo({ top: 0 }); },
  trf(el) { S.trFiltro = el.dataset.v; render(); },
  tra(el) { S.trAberto[el.dataset.id] = !S.trAberto[el.dataset.id]; render(); },
  abrir(el) { S.aberto[el.dataset.k] = !S.aberto[el.dataset.k]; render(); },
  modo(el) { S.modo[el.dataset.k] = el.dataset.v; render(); },
  confirmar(el) {
    const A = analisa(S.sel), modo = S.papel === 'admin' ? 'apagar' : 'pedir';
    const pc = podeConfirmar('imp', A.exec, modo); if (!pc.ok) return;
    const c = confDe('imp'), motivo = motivoFinal(c);
    if (modo === 'apagar') {
      const r = executar(false, A.exec, motivo);
      S.sel = S.sel.filter((x) => !r.ids.includes(x));
      S.res = { tipo: 'apagado', ...r, quem: EU(), motivo, fora: A.bloq };
    } else {
      const dup = [], junto = [], titulos = [];
      let criados = 0;
      A.exec.forEach((it, k) => {
        const ja = PEDIDOS.find((p) => p.alvo === it.id && p.status === 'pendente' && p.por === 'Ana Paula');
        if (ja) { dup.push(it.titulo); return; }
        PEDIDOS.forEach((p) => { if (p.alvo === it.id && p.status === 'pendente' && p.por !== 'Ana Paula' && !junto.includes(p.por)) junto.push(p.por); });
        PEDIDOS.unshift({ id: 'R' + (100 + PEDIDOS.length + k), alvo: it.id, por: 'Ana Paula', quando: AGORA, motivo, status: 'pendente' });
        criados++; titulos.push(it.titulo);
      });
      S.sel = S.sel.filter((x) => !A.exec.map((i) => i.id).includes(x));
      S.res = { tipo: 'pedido', quem: 'Ana Paula', motivo, dup, junto, titulos, criados, fora: A.bloq };
    }
    S.passo = 'pronto'; S.conf = {};
    render({ enter: true, focus: '#h-pronto' }); window.scrollTo({ top: 0 });
    say(S.res.tipo === 'apagado' ? 'Apagado. Comprovante ' + S.res.id : 'Pedido enviado ao administrador');
  },
  'aprovar-ok'(el) {
    const ctx = el.dataset.ctx, k = ctx.replace('ped:', '');
    const g = grupos().find((x) => x.k === k); if (!g || !g.item) return;
    const A = analisa([g.item.id]);
    if (!podeConfirmar(ctx, A.exec, 'aprovar').ok) return;
    const quem = g.ps.map((p) => p.por);
    const motivo = g.ps[0].motivo;
    g.ps.forEach((p) => { p.status = 'aprovada'; p.decididoPor = 'Jairo'; p.decididoEm = AGORA; });
    const r = executar(true, A.exec, motivo, quem.join(' e '));
    S.flash = { txt: `Aprovado: ${g.item.titulo}. Apagado e registrado como ${r.id}.`, trilha: true };
    delete S.aberto['g' + k]; delete S.modo['g' + k];
    render({ enter: true, focus: '#h-ped', noscroll: true }); say('Pedido aprovado e item apagado');
  },
  'rejeitar-ok'(el) {
    const ctx = el.dataset.ctx, k = el.dataset.k, c = confDe(ctx);
    const g = grupos().find((x) => x.k === k); if (!g) return;
    const mot = motivoFinal(c); if (!mot) return;
    g.ps.forEach((p) => { p.status = 'rejeitada'; p.decididoPor = 'Jairo'; p.decididoEm = AGORA; p.motivoRej = mot; });
    const n = TRILHA.length + 91 - 6;
    TRILHA.unshift({ id: 'EX-2026-' + String(n).padStart(4, '0'), quando: AGORA, quem: 'Jairo', acao: 'rejeitou', pedidoDe: g.ps.map((p) => p.por).join(' e '), titulo: titPedido(g.ps[0]), tipo: g.item ? g.item.tipo : g.ps[0].tipo, motivo: mot, apagado: [], revertido: [] });
    S.flash = { txt: `Pedido rejeitado. ${g.ps.map((p) => p.por).join(' e ')} vai ler: "${mot}"`, trilha: true };
    delete S.aberto['g' + k]; delete S.modo['g' + k];
    render({ enter: true, focus: '#h-ped', noscroll: true }); say('Pedido rejeitado');
  },
  arquivar(el) {
    const k = el.dataset.k;
    PEDIDOS.filter((p) => (p.alvo || p.id) === k && p.status === 'pendente').forEach((p) => { p.status = 'arquivada'; p.decididoPor = 'Jairo'; p.decididoEm = AGORA; });
    S.flash = { txt: 'Pedido arquivado: o item já não existia.', trilha: false };
    render({ enter: true, focus: '#h-ped', noscroll: true });
  },
  cancelar(el) {
    const p = PEDIDOS.find((x) => x.id === el.dataset.id); if (p) { p.status = 'cancelada'; }
    PEDIDOS = PEDIDOS.filter((x) => x.status !== 'cancelada');
    S.flash = { txt: 'Pedido cancelado.' }; render(); say('Pedido cancelado');
  },
};
function syncAll() {
  const vis = filtrar().slice(0, S.mostrar), c = view.querySelector('input[data-act="all"]');
  if (c) { const t = vis.length > 0 && vis.every((i) => S.sel.includes(i.id)); c.checked = t; }
}

view.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || !view.contains(el)) return;
  if (el.tagName === 'INPUT') return; // inputs tratam no 'change'
  const f = H[el.dataset.act];
  if (f) f(el, e);
});
view.addEventListener('change', (e) => {
  const el = e.target;
  if (el.tagName === 'INPUT' && el.dataset.act && H[el.dataset.act]) { H[el.dataset.act](el, e); return; }
  const k = el.dataset.in;
  if (!k || k === 'f.q' || k === 'f.vmin' || k === 'f.vmax' || k === 'busca' || k === 'palavra' || k === 'outro') return;
  if (k === 'motivo' || k === 'motivo-rej') { confDe(el.dataset.ctx).motivo = el.value; render({ focus: k === 'motivo-rej' ? null : null }); const rid = el.name; const again = view.querySelector(`input[name="${rid}"]:checked`); if (again) again.focus({ preventScroll: true }); }
  else if (k.startsWith('f.')) { S.f[k.slice(2)] = el.value; S.mostrar = 8; render(); }
});
view.addEventListener('input', (e) => {
  const el = e.target, k = el.dataset.in;
  if (!k) return;
  if (k === 'busca') { S.busca = el.value; render(); }
  else if (k === 'palavra') { confDe(el.dataset.ctx).palavra = el.value; render(); }
  else if (k === 'outro') { confDe(el.dataset.ctx).outro = el.value; render(); }
  else if (k === 'f.q' || k === 'f.vmin' || k === 'f.vmax') { S.f[k.slice(2)] = el.value; S.mostrar = 8; render(); }
});
trayEl.addEventListener('click', (e) => { const el = e.target.closest('[data-act]'); if (el && H[el.dataset.act]) H[el.dataset.act](el, e); });
view.addEventListener('keydown', (e) => {
  if (e.target.getAttribute('role') === 'tab' && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
    const tabs = [...view.querySelectorAll('[role=tab]')], i = tabs.indexOf(e.target);
    const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    n.click();
    setTimeout(() => { const t = view.querySelector('[role=tab][aria-selected=true]'); t && t.focus(); }, 0);
  }
});

/* ================= controles do mockup ================= */
function setTema(t) {
  S.tema = t; document.documentElement.dataset.theme = t;
  document.querySelectorAll('[data-tema]').forEach((b) => b.setAttribute('aria-pressed', b.dataset.tema === t));
}
function setPapel(p, manter) {
  S.papel = p;
  document.querySelectorAll('[data-papel]').forEach((b) => b.setAttribute('aria-pressed', b.dataset.papel === p));
  if (!manter) { S.aba = 'apagar'; S.passo = 'pick'; S.sel = []; S.res = null; S.flash = null; S.conf = {}; }
  render({ enter: true });
}
function reiniciar() {
  ITENS = ITENS_SEED(); PEDIDOS = PEDIDOS_SEED(); TRILHA = TRILHA_SEED();
  Object.assign(S, { aba: 'apagar', passo: 'pick', dom: 'fin', tipo: null, busca: '', f: NOVO_F(), sel: [], exp: {}, col: {}, fil: {}, conf: {}, res: null, loadImp: false, flash: null, aberto: {}, modo: {}, mostrar: 8, trAberto: {}, escAberto: false });
  render({ enter: true });
}
function cenario(id) {
  const c = CENARIOS.find((x) => x.id === id); if (!c) return;
  ITENS = ITENS_SEED(); PEDIDOS = PEDIDOS_SEED(); TRILHA = TRILHA_SEED();
  Object.assign(S, { aba: c.aba || 'apagar', passo: 'pick', tipo: c.tipo || null, f: NOVO_F(), sel: c.sel ? [...c.sel] : [], conf: {}, col: {}, fil: {}, res: null, flash: null, aberto: {}, modo: {}, mostrar: 8, exp: {}, escAberto: false });
  if (c.tipo) S.dom = TIPOS[c.tipo].dom;
  if (c.id === 'c8') { S.aberto = { gP1: true }; S.modo = {}; }
  setPapel(c.papel, true);
  if (c.passo === 'impacto') irImpacto();
}
document.getElementById('mk').addEventListener('click', (e) => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.dataset.tema) setTema(t.dataset.tema);
  else if (t.dataset.papel) setPapel(t.dataset.papel);
  else if (t.id === 'mk-reset') reiniciar();
});
document.getElementById('mk-cen').addEventListener('change', (e) => { if (e.target.value) cenario(e.target.value); e.target.value = ''; });
document.getElementById('mk-cen').innerHTML = '<option value="">Ir direto para…</option>' + CENARIOS.map((c) => `<option value="${c.id}">${c.nome}</option>`).join('');
if (window.innerWidth >= 761) document.getElementById('mk').open = true;

window.__mk = { cenario, S, setTema, setPapel, reiniciar }; // para os testes de captura
const q = new URLSearchParams(location.search);
if (q.get('tema')) setTema(q.get('tema'));
if (q.get('papel')) setPapel(q.get('papel'));
if (q.get('c')) cenario(q.get('c')); else render({ enter: true });
})();
