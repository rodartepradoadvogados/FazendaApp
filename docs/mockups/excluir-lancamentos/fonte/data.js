/* DADOS FICTÍCIOS — nenhum CPF, nome real de cliente ou dado da fazenda. */
const HOJE = '2026-10-09';
const AGORA = '2026-10-09T14:32';

const brl = (n) => (n < 0 ? '−' : '') + 'R$ ' + Math.abs(n).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dbr = (iso) => { if (!iso) return '—'; const [y, m, d] = iso.slice(0, 10).split('-'); return `${d}/${m}/${y}`; };
const dcurta = (iso) => { if (!iso) return '—'; const [y, m, d] = iso.slice(0, 10).split('-'); return `${d}/${m}`; };
const hbr = (iso) => iso.length > 10 ? iso.slice(11, 16) : '';
const MESES = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];

/* ---------- DOMÍNIOS e TIPOS ---------- */
const DOMINIOS = [
  { id: 'fin', nome: 'Financeiro', dica: 'Notas, parcelas, compras e vendas', tipos: ['financeiro', 'compra_animal', 'venda_animal', 'compra_semen'] },
  { id: 'reb', nome: 'Rebanho', dica: 'Animais, partos, inseminações, leite', tipos: ['animal', 'parto', 'servico', 'secagem', 'controle', 'movimento_lote'] },
  { id: 'san', nome: 'Sanidade', dica: 'Remédios, vacinas, protocolos, exames', tipos: ['sanidade', 'protocolo_sanitario_lancamento', 'protocolo_iatf_lancamento', 'exame_resultado'] },
  { id: 'pes', nome: 'Pessoal', dica: 'Vales, folha e diárias', tipos: ['vale', 'folha', 'diaria_pagamento'] },
  { id: 'est', nome: 'Estoque', dica: 'Entradas e saídas feitas à mão', tipos: ['movimento_estoque'] },
  { id: 'cad', nome: 'Cadastros', dica: 'Lotes, pessoas, fornecedores, doenças', cad: true, tipos: ['lote', 'pessoa', 'fornecedor', 'doenca'] },
];

/* filtros: quais campos aparecem para cada tipo */
const F_PADRAO = ['periodo', 'busca'];
const TIPOS = {
  financeiro: { nome: 'Nota ou conta (com parcelas)', sing: 'nota', plur: 'notas', hint: 'Conta a pagar ou a receber. Apagar leva todas as parcelas junto.', filtros: ['periodo', 'situacao', 'parte', 'valor', 'busca'], parteRot: 'Fornecedor ou cliente', kw: 'financeiro conta pagar receber parcela boleto nota fiscal' },
  compra_animal: { nome: 'Compra de animal', sing: 'compra', plur: 'compras', hint: 'A compra e a conta que ela gerou.', filtros: ['periodo', 'parte', 'busca'], parteRot: 'Vendedor', kw: 'compra animal gta' },
  venda_animal: { nome: 'Venda de animal', sing: 'venda', plur: 'vendas', hint: 'A venda e a conta a receber que ela gerou.', filtros: ['periodo', 'parte', 'busca'], parteRot: 'Comprador', kw: 'venda animal gta' },
  compra_semen: { nome: 'Compra de sêmen', sing: 'compra', plur: 'compras', hint: 'As doses saem do estoque de sêmen.', filtros: ['periodo', 'busca'], kw: 'semen dose touro' },
  animal: { nome: 'Ficha do animal', sing: 'animal', plur: 'animais', hint: 'Apaga o animal e todo o histórico dele.', filtros: ['busca', 'parte'], parteRot: 'Lote', kw: 'animal vaca ficha brinco numero' },
  parto: { nome: 'Parto e nascimento', sing: 'parto', plur: 'partos', hint: 'Mexe na lactação e nas crias.', filtros: ['periodo', 'busca'], kw: 'parto nascimento cria aborto lactacao' },
  servico: { nome: 'Inseminação ou cobertura', sing: 'inseminação', plur: 'inseminações', hint: 'Inclui o diagnóstico de prenhez.', filtros: ['periodo', 'busca'], kw: 'ia inseminacao cobertura servico diagnostico prenhez' },
  secagem: { nome: 'Secagem', sing: 'secagem', plur: 'secagens', hint: 'Reabre a lactação e devolve o remédio ao estoque.', filtros: ['periodo', 'busca'], kw: 'secagem seca vaca' },
  controle: { nome: 'Pesagem do leite (controle leiteiro)', sing: 'pesagem', plur: 'pesagens', hint: 'Um dia de leite de uma vaca.', filtros: ['periodo', 'busca'], kw: 'controle leiteiro leite producao pesagem' },
  movimento_lote: { nome: 'Troca de lote', sing: 'troca de lote', plur: 'trocas de lote', hint: 'A vaca pode voltar ao lote de antes.', filtros: ['periodo', 'busca'], kw: 'lote movimentacao troca' },
  sanidade: { nome: 'Remédio ou vacina aplicado', sing: 'aplicação', plur: 'aplicações', hint: 'O remédio volta para o estoque.', filtros: ['periodo', 'busca'], kw: 'sanidade remedio vacina aplicacao medicamento' },
  protocolo_sanitario_lancamento: { nome: 'Tratamento por protocolo (ex.: mastite)', sing: 'tratamento', plur: 'tratamentos', hint: 'Apaga as etapas e o que já foi aplicado.', filtros: ['periodo', 'busca'], kw: 'protocolo tratamento mastite curativo' },
  protocolo_iatf_lancamento: { nome: 'Protocolo de hormônio (IATF)', sing: 'protocolo', plur: 'protocolos', hint: 'Apaga a agenda de todas as vacas do protocolo.', filtros: ['periodo', 'busca'], kw: 'iatf hormonio protocolo' },
  exame_resultado: { nome: 'Resultado de exame', sing: 'exame', plur: 'exames', hint: 'O animal volta a constar sem exame.', filtros: ['periodo', 'busca'], kw: 'exame cmt brucelose resultado' },
  vale: { nome: 'Vale de funcionário', sing: 'vale', plur: 'vales', hint: 'Desfaz o desconto na folha e na empreitada.', filtros: ['periodo', 'busca'], kw: 'vale adiantamento funcionario' },
  folha: { nome: 'Folha de pagamento', sing: 'folha', plur: 'folhas', hint: 'Apaga as linhas da folha e a conta gerada.', filtros: ['periodo', 'busca'], kw: 'folha pagamento salario' },
  diaria_pagamento: { nome: 'Pagamento de diária', sing: 'pagamento', plur: 'pagamentos', hint: 'A diária volta a ficar devendo.', filtros: ['periodo', 'busca'], kw: 'diaria pagamento' },
  movimento_estoque: { nome: 'Entrada ou saída de estoque (manual)', sing: 'movimento', plur: 'movimentos', hint: 'O saldo do produto volta ao que era.', filtros: ['periodo', 'busca'], kw: 'estoque entrada saida ajuste saldo' },
  lote: { nome: 'Lote', sing: 'lote', plur: 'lotes', hint: 'Os animais do lote ficam sem lote.', filtros: ['busca'], cad: true, kw: 'lote cadastro' },
  pessoa: { nome: 'Pessoa ou funcionário', sing: 'pessoa', plur: 'pessoas', hint: 'Só sai se não tiver folha nem vale.', filtros: ['busca'], cad: true, kw: 'pessoa funcionario cadastro' },
  fornecedor: { nome: 'Fornecedor, cliente ou corretor', sing: 'fornecedor', plur: 'fornecedores', hint: 'As notas continuam, mas perdem a ligação.', filtros: ['busca'], cad: true, kw: 'fornecedor cliente corretor cadastro' },
  doenca: { nome: 'Doença', sing: 'doença', plur: 'doenças', hint: 'Protocolos e regras perdem a ligação.', filtros: ['busca'], cad: true, kw: 'doenca cadastro' },
};
Object.keys(TIPOS).forEach((k) => {
  TIPOS[k].id = k;
  const d = DOMINIOS.find((x) => x.tipos.includes(k));
  TIPOS[k].dom = d.id;
});

/* ---------- construtores de impacto ---------- */
const P = (n, venc, valor, paga, pagoEm, conta) => ({ n, venc, valor, paga: !!paga, pagoEm, conta });
const ap = (t, c, o = {}) => ({ t, c, n: o.n ?? 1, din: o.din || 0, filhos: o.filhos || [], chip: o.chip });
const rv = (t, c, o = {}) => ({ t, c, filhos: o.filhos || [], chip: o.chip });
const av = (t, c, o = {}) => ({ t, c, filhos: o.filhos || [] });
const bq = (t, c, fazer, acao) => ({ t, c, fazer, acao });

function sitFin(it) {
  const ps = it.parcelas;
  const pagas = ps.filter((p) => p.paga).length;
  if (pagas === ps.length) return 'paga';
  if (pagas > 0) return 'parcial';
  if (ps.some((p) => p.venc < HOJE)) return 'atrasada';
  return 'aberta';
}

/* Gera o impacto de uma nota financeira a partir das parcelas e do que ela trouxe junto. */
function finImp(it, o = {}) {
  const ps = it.parcelas, tot = ps.length;
  const pagas = ps.filter((p) => p.paga);
  const abertas = ps.filter((p) => !p.paga);
  const verbo = it.receita ? 'entraram no' : 'saíram do';
  const imp = { bloqueia: [], apagar: [], reverter: [], avisos: [] };
  if (pagas.length) {
    const soma = pagas.reduce((s, p) => s + p.valor, 0);
    imp.bloqueia.push(bq(
      pagas.length === 1 ? `Parcela ${pagas[0].n}/${tot} já foi ${it.receita ? 'recebida' : 'paga'}` : `${pagas.length} parcelas já foram ${it.receita ? 'recebidas' : 'pagas'}`,
      `${brl(soma)} ${verbo} caixa (${pagas.map((p) => p.conta + ', ' + dcurta(p.pagoEm)).join(' · ')}). Se a nota sumir agora, o saldo da conta e o relatório do mês ficam errados.`,
      `${it.receita ? 'Desfaça o recebimento' : 'Estorne o pagamento'} ${pagas.length === 1 ? 'da parcela ' + pagas[0].n + '/' + tot : 'das ' + pagas.length + ' parcelas'} primeiro. Depois volte aqui.`,
      pagas.length === 1 ? `Abrir parcela ${pagas[0].n}/${tot}` : 'Abrir pagamentos',
    ));
  }
  imp.apagar.push(ap(`Nota ${it.num}`, `${it.titulo.split('·')[1].trim()} — a nota deixa de existir.`));
  imp.apagar.push(ap(`${tot} ${tot === 1 ? 'parcela' : 'parcelas'}`, `${brl(abertas.reduce((s, p) => s + p.valor, 0))} saem ${it.receita ? 'das contas a receber' : 'das contas a pagar'}.`, {
    n: tot, din: abertas.reduce((s, p) => s + p.valor, 0),
    filhos: ps.map((p) => `${p.n}/${tot} · vence ${dbr(p.venc)} · ${brl(p.valor)} · ${p.paga ? (it.receita ? 'RECEBIDA' : 'PAGA') + ' em ' + dbr(p.pagoEm) : 'em aberto'}`),
  }));
  if (o.produtos && o.produtos.length) {
    imp.apagar.push(ap(`${o.produtos.length} ${o.produtos.length === 1 ? 'produto lançado' : 'produtos lançados'} na nota`, 'Linhas de produto da nota.', { n: o.produtos.length, filhos: o.produtos.map((p) => `${p.nome} · ${p.qtd} ${p.un}`) }));
    o.produtos.forEach((p) => {
      imp.reverter.push(rv(`Estoque de ${p.nome}`, `Os ${p.qtd} ${p.un} que entraram com esta nota saem do estoque: o saldo vai de ${p.de} para ${p.para}.`, { chip: 'Mexe no estoque' }));
      if (p.para < 0) imp.avisos.push(av(`Estoque de ${p.nome} vai ficar negativo (${p.para})`, `Já foi usado mais do que sobrou. O sistema apaga assim mesmo e deixa o saldo em ${p.para}. Confira o estoque depois.`));
    });
  }
  if (o.anexos) imp.apagar.push(ap(`${o.anexos.length} ${o.anexos.length === 1 ? 'anexo' : 'anexos'}`, 'O arquivo também sai do armazenamento.', { filhos: o.anexos, n: o.anexos.length }));
  if (o.vale) {
    imp.apagar.push(ap(`Vale nº ${o.vale.num} de ${o.vale.quem}`, `O vale de ${brl(o.vale.valor)} que esta nota gerou também é apagado.`));
    imp.reverter.push(rv('Empreitada: ' + o.vale.empreitada, `O abatimento de ${brl(o.vale.valor)} some: a parcela da empreitada volta de ${brl(o.vale.de)} para ${brl(o.vale.para)} a pagar.`, { chip: 'Desfaz abatimento' }));
    imp.reverter.push(rv(`Conta corrente de ${o.vale.quem}`, `O vale sai do saldo: ${o.vale.quem} deixa de dever ${brl(o.vale.valor)}.`));
  }
  if (o.fatura) imp.avisos.push(av(`Fatura ${o.fatura.num} muda`, `Esta nota sai da fatura. O total cai de ${brl(o.fatura.de)} para ${brl(o.fatura.para)}.`));
  const mes = MESES[parseInt(it.data.slice(5, 7), 10) - 1];
  if (!pagas.length) imp.avisos.push(av(`Relatório de ${mes} muda`, `${it.receita ? 'A receita' : 'A despesa'} de ${brl(it.valor)} deixa de aparecer em ${mes}.`));
  it.imp = imp;
  return it;
}
const nota = (id, num, desc, parte, data, valor, parcelas, o = {}) => finImp({ id, tipo: 'financeiro', num, titulo: `${num} · ${desc}`, sub: parte, data, valor, parte, parcelas, receita: !!o.receita, editar: 'Financeiro › Contas a pagar' }, o);

/* ---------- ITENS ---------- */
const ITENS_SEED = () => [
  /* FINANCEIRO */
  nota('F1', 'LC-2026-00412', 'Ração concentrado 20%', 'Agro Estreito Rações', '2026-09-12', 12600,
    [P(1, '2026-09-15', 4200, true, '2026-09-15', 'Cresol c/c principal'), P(2, '2026-10-15', 4200), P(3, '2026-11-15', 4200)],
    { produtos: [{ nome: 'Ração concentrado 20%', qtd: 120, un: 'sacos', de: 180, para: 60 }, { nome: 'Sal mineral', qtd: 20, un: 'sacos', de: 63, para: 43 }], anexos: ['NF-e 18422.pdf'] }),
  nota('F2', 'LC-2026-00431', 'Energia elétrica de setembro', 'Cooperativa de Energia Vale Verde', '2026-09-28', 1874.30,
    [P(1, '2026-10-20', 1874.30)], { anexos: ['boleto-energia-set.pdf'] }),
  nota('F3', 'LC-2026-00398', 'Vale — adiantamento Carlos Eduardo', 'Carlos Eduardo (empreiteiro)', '2026-09-05', 800,
    [P(1, '2026-10-05', 800)], { vale: { num: 27, quem: 'Carlos Eduardo', valor: 800, empreitada: 'Cerca do pasto 4', de: 1700, para: 2500 } }),
  nota('F4', 'LC-2026-00377', 'Medicamentos — mastite e verminose', 'Agrovet Sul Distribuidora', '2026-09-20', 3360,
    [P(1, '2026-10-10', 1680), P(2, '2026-11-10', 1680)],
    { produtos: [{ nome: 'Pomada intramamária', qtd: 30, un: 'bisnagas', de: 12, para: -18 }, { nome: 'Ivermectina', qtd: 20, un: 'frascos', de: 45, para: 25 }], anexos: ['NF-e 77310.pdf'], fatura: { num: 'FT-2026-009', de: 9480, para: 6120 } }),
  nota('F5', 'LC-2026-00352', 'Venda de leite — setembro', 'Laticínios Serra Azul', '2026-09-30', 48920,
    [P(1, '2026-10-05', 48920, true, '2026-10-06', 'Cresol c/c principal')], { receita: true, anexos: ['extrato-laticinio-set.pdf'] }),
  nota('F6', 'LC-2026-00440', 'Diesel do trator', 'Posto Estreito', '2026-10-02', 920, [P(1, '2026-10-20', 920)], {}),
  nota('F7', 'LC-2026-00301', 'Sal mineral — 40 sacos', 'Agro Estreito Rações', '2026-08-14', 4480,
    [P(1, '2026-09-14', 2240, true, '2026-09-14', 'Cresol c/c principal'), P(2, '2026-10-14', 2240, true, '2026-10-08', 'Cresol c/c principal')],
    { produtos: [{ nome: 'Sal mineral', qtd: 40, un: 'sacos', de: 63, para: 23 }] }),
  nota('F8', 'LC-2026-00415', 'Manutenção da ordenhadeira', 'Mecânica Rio Claro', '2026-09-25', 2150, [P(1, '2026-09-30', 2150)], { anexos: ['orcamento-ordenhadeira.pdf'] }),
  nota('F9', 'LC-2026-00409', 'Frete da silagem de milho', 'Transportes Rio Claro', '2026-09-22', 3900,
    [P(1, '2026-11-10', 1300), P(2, '2026-12-10', 1300), P(3, '2027-01-10', 1300)], {}),
  nota('F10', 'LC-2026-00287', 'Honorários contábeis — agosto', 'Escritório Contábil Horizonte', '2026-08-30', 1200,
    [P(1, '2026-09-10', 1200, true, '2026-09-10', 'Cresol c/c principal')], {}),

  /* COMPRA / VENDA */
  { id: 'CA1', tipo: 'compra_animal', titulo: '1388 — Fazenda Boa Vista — 03/09/2026', sub: 'R$ 5.200,00 · lançamento LC-2026-00380 · GTA 4471', data: '2026-09-03', valor: 5200, parte: 'Fazenda Boa Vista', editar: 'Lançamentos › Comprar animal',
    imp: { bloqueia: [bq('A conta da compra já foi paga', 'R$ 5.200,00 saíram da conta Cresol em 05/09 (lançamento LC-2026-00380).', 'Estorne o pagamento primeiro. Depois volte aqui.', 'Abrir pagamento')], apagar: [ap('Compra do animal 1388', 'Registro da compra.')], reverter: [], avisos: [] } },
  { id: 'CA2', tipo: 'compra_animal', titulo: '1395, 1396, 1397 — Fazenda Boa Vista — 03/09/2026', sub: 'Compra em lote (3 animais) · R$ 15.600,00 · GTA 4472', data: '2026-09-03', valor: 5200, parte: 'Fazenda Boa Vista', editar: 'Lançamentos › Comprar animal',
    imp: { bloqueia: [], apagar: [ap('Compra do animal 1395', 'Só este animal sai da compra.')], reverter: [], avisos: [av('A conta financeira continua', 'A compra tem mais 2 animais. A conta de R$ 15.600,00 e a comissão ficam como estão, valendo para os outros dois.')] } },
  { id: 'VA1', tipo: 'venda_animal', titulo: '1210 — Frigorífico Planalto — 30/09/2026', sub: 'R$ 4.800,00 · lançamento LC-2026-00362', data: '2026-09-30', valor: 4800, parte: 'Frigorífico Planalto', editar: 'Lançamentos › Vender animal',
    imp: { bloqueia: [], apagar: [ap('Venda do animal 1210', 'Registro da venda.'), ap('Conta a receber LC-2026-00362', `${brl(4800)} saem das contas a receber.`, { din: 4800, filhos: ['1/1 · vence 15/10/2026 · R$ 4.800,00 · em aberto'] })], reverter: [], avisos: [av('O animal não volta ao rebanho', 'A ficha do animal 1210 continua baixada. Se foi engano, reative o animal depois.')] } },
  { id: 'CS1', tipo: 'compra_semen', titulo: 'Jasper (NAAB 7HO14122) — Central Genética Sul — 11/09/2026', sub: '20 doses · R$ 85,00 por dose · LC-2026-00391', data: '2026-09-11', valor: 1700, parte: 'Central Genética Sul', editar: 'Lançamentos › Comprar sêmen',
    imp: { bloqueia: [], apagar: [ap('Compra de 20 doses de Jasper', 'Registro da compra.'), ap('Conta LC-2026-00391', brl(1700) + ' saem das contas a pagar.', { din: 1700, filhos: ['1/1 · vence 11/10/2026 · R$ 1.700,00 · em aberto'] })], reverter: [rv('Estoque de sêmen de Jasper', '20 doses saem do botijão: o saldo vai de 31 para 11.', { chip: 'Mexe no estoque' })], avisos: [] } },

  /* REBANHO */
  { id: 'A1', tipo: 'animal', titulo: '1042', sub: 'Girolando · Lote 03 — Média produção', data: null, parte: 'Lote 03', risco: 'alto', porque: 'apaga a ficha e todo o histórico', editar: 'Rebanho › Ficha do animal',
    imp: { bloqueia: [], apagar: [ap('Ficha do animal 1042', 'Girolando, Lote 03. A vaca deixa de existir no sistema.'), ap('11 inseminações e coberturas', 'Todo o histórico reprodutivo.', { n: 11 }), ap('2 partos', '14/09/2026 e 19/11/2025.', { n: 2 }), ap('38 pesagens de leite', 'Mais de um ano de produção da vaca.', { n: 38 }), ap('14 aplicações de remédio e vacina', 'Todo o histórico sanitário.', { n: 14 }), ap('2 lactações', 'Atual e anterior.', { n: 2 }), ap('1 colostragem e 5 fotos', 'Registros ligados à ficha.', { n: 6 })],
      reverter: [rv('Estoque de remédios', 'As 14 aplicações devolvem o remédio: Ivermectina +3 frascos, Pomada intramamária +2 bisnagas, vacinas +9 doses.', { chip: 'Mexe no estoque' })],
      avisos: [av('As crias 1301 e 1302 ficam sem mãe cadastrada', 'Elas não são apagadas, mas deixam de ter a 1042 como mãe.'), av('Médias do Lote 03 mudam', 'As 38 pesagens saem das médias de produção dos últimos 12 meses.')] } },
  { id: 'A2', tipo: 'animal', titulo: '0877', sub: 'Holandês · Lote 05 — Secas', data: null, parte: 'Lote 05', risco: 'alto', porque: 'apaga a ficha e todo o histórico', editar: 'Rebanho › Ficha do animal',
    imp: { bloqueia: [], apagar: [ap('Ficha do animal 0877', 'Holandês, Lote 05.'), ap('7 inseminações e coberturas', 'Todo o histórico reprodutivo.', { n: 7 }), ap('1 parto', 'Aborto de 02/08/2026.', { n: 1 }), ap('22 pesagens de leite', 'Produção da vaca.', { n: 22 }), ap('6 aplicações de remédio', 'Histórico sanitário.', { n: 6 }), ap('1 lactação', 'Atual.', { n: 1 })], reverter: [rv('Estoque de remédios', 'As 6 aplicações devolvem o remédio: Pomada intramamária +3 bisnagas, Ivermectina +1 frasco.', { chip: 'Mexe no estoque' })], avisos: [av('Tem tratamento em andamento', 'Há um protocolo de mastite aberto para a 0877. Ele também será apagado.')] } },
  { id: 'A3', tipo: 'animal', titulo: '1301', sub: 'Girolando · Lote 01 — Bezerras', data: null, parte: 'Lote 01', risco: 'alto', porque: 'apaga a ficha e o histórico', editar: 'Rebanho › Ficha do animal',
    imp: { bloqueia: [], apagar: [ap('Ficha do animal 1301', 'Bezerra nascida em 14/09/2026.'), ap('1 colostragem', 'Registro de IgG.', { n: 1 }), ap('2 fotos do campo', 'Fotos ligadas à ficha.', { n: 2 }), ap('1 aplicação de remédio', 'Vacina de nascimento.', { n: 1 })], reverter: [rv('Estoque de vacinas', 'A vacina aplicada volta ao estoque: +1 dose.', { chip: 'Mexe no estoque' })], avisos: [av('Parto da 1042 fica sem cria 1301', 'O parto de 14/09 continua, mas perde essa cria.')] } },

  { id: 'P1', tipo: 'parto', titulo: '1042 — 14/09/2026', sub: 'Parto nº 2 · normal · crias 1301 e 1302', data: '2026-09-14', risco: 'alto', porque: 'mexe na lactação, em DEL e em crias', editar: 'Lançamentos › Parto',
    imp: { bloqueia: [], apagar: [ap('Parto da 1042 em 14/09/2026', 'O parto deixa de existir.'), ap('1 pendência de retenção de placenta na Agenda', 'O aviso do dia 14/09 some da Agenda.'), ap('Ficha da cria 1301', 'Nasceu só por este parto e não tem outro registro: ela é apagada junto.')],
      reverter: [rv('Lactação nova de 14/09 é removida', 'A 1042 deixa de constar como "em lactação" a partir de 14/09.', { chip: 'Mexe na lactação' }), rv('Lactação anterior é reaberta', 'A lactação de 19/11/2025 tinha sido fechada por este parto. Ela volta a ficar aberta.'), rv('Dias em leite (DEL) recalculado', 'O DEL da 1042 passa de 25 para 324 dias (conta a partir do parto de 19/11/2025).')],
      avisos: [av('A cria 1302 NÃO é apagada', 'Ela já tem uma pesagem lançada. Fica no rebanho, mas sem o parto de origem.'), av('9 pesagens de leite ficam sem lactação', 'As pesagens lançadas depois de 14/09 vão aparecer como "sem lactação" no relatório de DEL.')] } },
  { id: 'P2', tipo: 'parto', titulo: '0877 — 02/08/2026', sub: 'Aborto', data: '2026-08-02', editar: 'Lançamentos › Parto',
    imp: { bloqueia: [], apagar: [ap('Aborto da 0877 em 02/08/2026', 'O registro deixa de existir.')], reverter: [rv('Lactação aberta pelo aborto é removida', 'A 0877 deixa de constar como "em lactação" desde 02/08.', { chip: 'Mexe na lactação' }), rv('Dias em leite (DEL) recalculado', 'O DEL da 0877 passa de 68 para 355 dias (conta a partir do parto anterior).')], avisos: [av('22 pesagens de leite ficam sem lactação', 'As pesagens depois de 02/08 vão aparecer como "sem lactação" no relatório de DEL.')] } },
  { id: 'P3', tipo: 'parto', titulo: '0911 — 20/07/2026', sub: 'Parto nº 3 · normal · cria 1288', data: '2026-07-20', editar: 'Lançamentos › Parto',
    imp: { bloqueia: [], apagar: [ap('Parto da 0911 em 20/07/2026', 'O parto deixa de existir.'), ap('Ficha da cria 1288', 'Nasceu só por este parto e não tem outro registro: ela é apagada junto.')], reverter: [rv('Lactação nova de 20/07 é removida', 'A 0911 deixa de constar como "em lactação" desde 20/07.', { chip: 'Mexe na lactação' }), rv('Dias em leite (DEL) recalculado', 'O DEL da 0911 passa de 81 para 412 dias.')], avisos: [] } },

  { id: 'S1', tipo: 'servico', titulo: '0877 — 21/09/2026', sub: 'IA · Jasper · diagnóstico: aguardando', data: '2026-09-21', editar: 'Lançamentos › Inseminação',
    imp: { bloqueia: [], apagar: [ap('Inseminação da 0877 em 21/09/2026', 'Touro Jasper. O registro deixa de existir.')], reverter: [rv('A inseminação anterior volta a valer', 'A IA de 28/08 (touro Jasper) volta a ser a "IA atual" da 0877.', { chip: 'Mexe na reprodução' }), rv('Perda de prenhez desfeita', 'A perda marcada em 28/08 por causa desta nova IA some (ninguém tinha confirmado o motivo).'), rv('Dose de sêmen volta ao botijão', 'Jasper: o saldo vai de 11 para 12 doses.', { chip: 'Mexe no estoque' })], avisos: [] } },
  { id: 'SC1', tipo: 'secagem', titulo: '0645 — 01/10/2026', sub: 'Fim da lactação · escore 3,0', data: '2026-10-01', editar: 'Lançamentos › Secagem',
    imp: { bloqueia: [], apagar: [ap('Secagem da 0645 em 01/10/2026', 'O registro deixa de existir.'), ap('2 aplicações na Sanidade', 'Antibiótico de secagem e selante de teto.', { n: 2 }), ap('1 vacina pré-parto programada', 'A aplicação de 02/10 some da Agenda.')], reverter: [rv('Lactação da 0645 é reaberta', 'A secagem tinha fechado a lactação. Ela volta a ficar aberta.', { chip: 'Mexe na lactação' }), rv('Estoque devolvido', 'Antibiótico de secagem +1 bisnaga, selante de teto +1.', { chip: 'Mexe no estoque' })], avisos: [av('Pesagens de leite voltam a ser aceitas', 'A 0645 volta a constar em lactação e a entrar nas médias do lote.')] } },
  { id: 'C1', tipo: 'controle', titulo: '0911 — 02/10/2026', sub: '18,4 kg', data: '2026-10-02', editar: 'Lançamentos › Controle leiteiro', imp: { bloqueia: [], apagar: [ap('Pesagem da 0911 em 02/10/2026', '18,4 kg de leite deixam de contar.')], reverter: [], avisos: [] } },
  { id: 'C2', tipo: 'controle', titulo: '1102 — 02/10/2026', sub: '26,1 kg', data: '2026-10-02', editar: 'Lançamentos › Controle leiteiro', imp: { bloqueia: [], apagar: [ap('Pesagem da 1102 em 02/10/2026', '26,1 kg de leite deixam de contar.')], reverter: [], avisos: [] } },
  { id: 'C3', tipo: 'controle', titulo: '0877 — 28/09/2026', sub: '21,7 kg', data: '2026-09-28', editar: 'Lançamentos › Controle leiteiro', imp: { bloqueia: [], apagar: [ap('Pesagem da 0877 em 28/09/2026', '21,7 kg de leite deixam de contar.')], reverter: [], avisos: [] } },
  { id: 'M1', tipo: 'movimento_lote', titulo: '0911 — 29/09/2026', sub: 'Lote 02 → Lote 03', data: '2026-09-29', editar: 'Rebanho › Trocar lote',
    imp: { bloqueia: [], apagar: [ap('Troca de lote da 0911 em 29/09/2026', 'Lote 02 → Lote 03.')], reverter: [rv('A vaca volta para o Lote 02', 'Foi a última troca de lote da 0911, então ela volta ao lote de antes.', { chip: 'Troca o lote' })], avisos: [] } },
  { id: 'M2', tipo: 'movimento_lote', titulo: '1102 — 15/09/2026', sub: 'Lote 03 → Lote 04', data: '2026-09-15', editar: 'Rebanho › Trocar lote',
    imp: { bloqueia: [], apagar: [ap('Troca de lote da 1102 em 15/09/2026', 'Lote 03 → Lote 04.')], reverter: [], avisos: [av('O lote atual NÃO muda', 'A 1102 já foi trocada de lote de novo depois disso. Só o histórico é apagado.')] } },

  /* SANIDADE */
  { id: 'SA1', tipo: 'sanidade', titulo: '1042 — 02/10/2026', sub: 'Ivermectina · 1 frasco', data: '2026-10-02', editar: 'Sanidade › Aplicações',
    imp: { bloqueia: [], apagar: [ap('Aplicação de Ivermectina na 1042 em 02/10/2026', 'O registro deixa de existir.')], reverter: [rv('Estoque de Ivermectina', '1 frasco volta ao estoque: o saldo vai de 45 para 46.', { chip: 'Mexe no estoque' })], avisos: [] } },
  { id: 'SA2', tipo: 'protocolo_sanitario_lancamento', titulo: '0877 — Protocolo de mastite — 05/10/2026', sub: '3/5 etapas realizadas', data: '2026-10-05', editar: 'Sanidade › Protocolos',
    imp: { bloqueia: [], apagar: [ap('Tratamento de mastite da 0877', 'Começou em 05/10/2026.'), ap('5 etapas do protocolo', 'Agenda das aplicações.', { n: 5, filhos: ['D1 · 05/10 · feita', 'D2 · 06/10 · feita', 'D3 · 07/10 · feita', 'D4 · 08/10 · programada', 'D5 · 09/10 · programada'] }), ap('3 aplicações já registradas na Sanidade', 'Pomada intramamária e anti-inflamatório.', { n: 3 })], reverter: [rv('Estoque devolvido', 'Pomada intramamária +3 bisnagas, anti-inflamatório +1 frasco.', { chip: 'Mexe no estoque' })], avisos: [av('O aviso de leite em carência some', 'A 0877 está com leite em carência até 14/10. Apagando, o sistema deixa de avisar para descartar o leite dela.')] } },
  { id: 'SA3', tipo: 'protocolo_iatf_lancamento', titulo: 'IATF Lote 03 — D0 05/10/2026', sub: '12 vacas · 8/36 aplicações feitas', data: '2026-10-05', risco: 'alto', porque: 'apaga a agenda de 12 vacas', editar: 'Sanidade › Protocolos',
    imp: { bloqueia: [], apagar: [ap('Protocolo IATF do Lote 03', 'D0 em 05/10/2026.'), ap('36 aplicações programadas, 12 vacas', 'Toda a agenda do protocolo.', { n: 36 }), ap('8 aplicações já registradas na Sanidade', 'Hormônios já dados.', { n: 8 })], reverter: [rv('Hormônios voltam ao estoque', 'GnRH +4 doses, prostaglandina +4 doses.', { chip: 'Mexe no estoque' })], avisos: [av('A agenda de IA das 12 vacas some', 'A inseminação marcada para 15/10 deixa de existir para todas elas.')] } },
  { id: 'SA4', tipo: 'exame_resultado', titulo: '1042 — CMT — 03/10/2026', sub: 'Resultado: 1+ em dois tetos', data: '2026-10-03', editar: 'Sanidade › Exames', imp: { bloqueia: [], apagar: [ap('Resultado de CMT da 1042 em 03/10/2026', 'O registro deixa de existir.')], reverter: [], avisos: [av('A vaca volta a constar sem exame', 'A 1042 entra de novo na lista de vacas para fazer CMT.')] } },

  /* PESSOAL */
  { id: 'V1', tipo: 'vale', titulo: 'Vale nº 31 — Maria Aparecida', sub: 'R$ 500,00 em 3 parcelas · 1 já descontada', data: '2026-08-28', valor: 500, editar: 'Financeiro › Vales',
    imp: { bloqueia: [bq('Parcela 1/3 já foi descontada na folha', 'R$ 166,67 foram descontados da folha de setembro, que foi paga em 05/10.', 'Desfaça o desconto na folha de setembro primeiro (ou estorne a folha). Depois volte aqui.', 'Abrir folha de setembro')], apagar: [ap('Vale nº 31', 'R$ 500,00 em 3 parcelas.', { n: 3 })], reverter: [], avisos: [] } },
  { id: 'V2', tipo: 'vale', titulo: 'Vale nº 33 — Marcos', sub: 'R$ 300,00 em 1 parcela · nada descontado ainda', data: '2026-10-03', valor: 300, editar: 'Financeiro › Vales',
    imp: { bloqueia: [], apagar: [ap('Vale nº 33', 'R$ 300,00 em 1 parcela.', { din: 300 }), ap('1 comprovante', 'O arquivo também sai do armazenamento.', { filhos: ['recibo-vale-33.jpg'] })], reverter: [rv('Conta corrente de Marcos', 'O vale sai do saldo: Marcos deixa de dever R$ 300,00.')], avisos: [av('Folha de outubro', 'O desconto de R$ 300,00 previsto para outubro deixa de entrar na folha.')] } },
  { id: 'FP1', tipo: 'folha', titulo: 'Folha de setembro/2026 — Carlos Eduardo', sub: 'R$ 2.640,00 · paga em 05/10', data: '2026-09-30', valor: 2640, editar: 'Financeiro › Folha',
    imp: { bloqueia: [bq('A folha já foi paga', 'R$ 2.640,00 saíram do caixa em 05/10 (conta Cresol).', 'Estorne o pagamento da folha primeiro. Depois volte aqui.', 'Abrir pagamento da folha')], apagar: [ap('Folha de setembro de Carlos Eduardo', '6 linhas de salário e descontos.', { n: 6 })], reverter: [], avisos: [] } },
  { id: 'FP2', tipo: 'folha', titulo: 'Folha de outubro/2026 — Maria Aparecida', sub: 'R$ 2.980,00 · em aberto', data: '2026-10-05', valor: 2980, editar: 'Financeiro › Folha',
    imp: { bloqueia: [], apagar: [ap('Folha de outubro de Maria Aparecida', 'Valores e descontos.'), ap('6 linhas da folha', 'Salário, hora extra, INSS e outros.', { n: 6, filhos: ['Salário · R$ 2.400,00', 'Hora extra · R$ 380,00', 'Adicional noturno · R$ 200,00', 'INSS · −R$ 180,00', 'Vale (parcela 2/3) · −R$ 166,67', 'Outros · R$ 346,67'] }), ap('Conta a pagar LC-2026-00446', brl(2980) + ' saem das contas a pagar.', { din: 2980 })], reverter: [rv('Parcela de vale volta a ficar em aberto', 'A parcela 2/3 do vale nº 31 (R$ 166,67), que seria descontada nesta folha, volta a esperar uma folha.')], avisos: [av('Fechamento de outubro', 'A folha de outubro precisa ser refeita antes do pagamento.')] } },
  { id: 'D1', tipo: 'diaria_pagamento', titulo: 'Zé Roberto — 04/10/2026', sub: 'R$ 180,00 · baixado', data: '2026-10-04', valor: 180, editar: 'Financeiro › Diárias',
    imp: { bloqueia: [], apagar: [ap('Pagamento de R$ 180,00 da diária de Zé Roberto', 'Registro do pagamento.'), ap('Conta baixada LC-2026-00443', 'A conta que registrava esse pagamento também sai.', { din: 0 })], reverter: [rv('A diária volta a ficar devendo', 'O saldo devedor de Zé Roberto volta de R$ 0,00 para R$ 180,00.')], avisos: [] } },

  /* ESTOQUE */
  { id: 'E1', tipo: 'movimento_estoque', titulo: 'Sal mineral — Saída de ajuste — 03/10/2026', sub: '27 sacos', data: '2026-10-03', editar: 'Estoque › Histórico',
    imp: { bloqueia: [], apagar: [ap('Saída de ajuste de 27 sacos de sal mineral', 'Movimento manual de 03/10.')], reverter: [rv('Saldo de Sal mineral', 'Os 27 sacos voltam: o saldo vai de 63 para 90.', { chip: 'Mexe no estoque' })], avisos: [] } },
  { id: 'E2', tipo: 'movimento_estoque', titulo: 'Ração concentrado 20% — Entrada manual — 28/09/2026', sub: '40 sacos', data: '2026-09-28', editar: 'Estoque › Histórico',
    imp: { bloqueia: [], apagar: [ap('Entrada manual de 40 sacos de ração', 'Movimento de 28/09.')], reverter: [rv('Saldo de Ração concentrado 20%', 'Os 40 sacos saem: o saldo vai de 35 para −5.', { chip: 'Mexe no estoque' })], avisos: [av('Estoque de Ração vai ficar negativo (−5)', 'Já foi usado mais do que sobrou. O sistema apaga assim mesmo. Confira a contagem física.')] } },
  { id: 'E3', tipo: 'movimento_estoque', titulo: 'Ivermectina — Saída — 30/09/2026', sub: '2 frascos', data: '2026-09-30', editar: 'Estoque › Histórico',
    imp: { bloqueia: [], apagar: [ap('Saída de 2 frascos de Ivermectina', 'Movimento manual de 30/09.')], reverter: [rv('Saldo de Ivermectina', 'Os 2 frascos voltam: o saldo vai de 45 para 47.', { chip: 'Mexe no estoque' })], avisos: [] } },

  /* CADASTROS */
  { id: 'L1', tipo: 'lote', titulo: '04 — Recria', sub: '23 animais', data: null, risco: 'alto', porque: 'cadastro em uso por 23 animais', editar: 'Configurações › Cadastros',
    imp: { bloqueia: [bq('Lote em uso por 23 animais', 'Se o lote sumir, os 23 animais ficam com um lote que não existe mais e saem dos relatórios por lote.', 'Mova os 23 animais para outro lote primeiro (Rebanho › Trocar lote em massa).', 'Abrir troca de lote em massa')], apagar: [ap('Lote 04 — Recria', 'O cadastro do lote.')], reverter: [], avisos: [] } },
  { id: 'L2', tipo: 'lote', titulo: '09 — Teste', sub: 'nenhum animal', data: null, risco: 'medio', porque: 'é um cadastro (sem uso)', editar: 'Configurações › Cadastros',
    imp: { bloqueia: [], apagar: [ap('Lote 09 — Teste', 'O cadastro do lote. Nenhum animal usa.')], reverter: [], avisos: [] } },
  { id: 'PE1', tipo: 'pessoa', titulo: 'Maria Aparecida', sub: 'Ordenhadora', data: null, risco: 'alto', porque: 'cadastro em uso', editar: 'Configurações › Cadastros',
    imp: { bloqueia: [bq('Maria Aparecida tem 6 folhas e 2 vales', 'Apagar a pessoa deixaria folhas e vales sem dono.', 'Apague as 6 folhas e os 2 vales dela primeiro (Financeiro).', 'Abrir folhas e vales da Maria')], apagar: [ap('Cadastro de Maria Aparecida', 'Pessoa.')], reverter: [], avisos: [] } },
  { id: 'PE2', tipo: 'pessoa', titulo: 'Zé Teste', sub: 'Cadastro de teste', data: null, risco: 'medio', porque: 'é um cadastro (sem uso)', editar: 'Configurações › Cadastros',
    imp: { bloqueia: [], apagar: [ap('Cadastro de Zé Teste', 'Pessoa sem folha, sem vale e sem diária.')], reverter: [], avisos: [] } },
  { id: 'FO1', tipo: 'fornecedor', titulo: 'Agro Estreito Rações', sub: 'Fornecedor · Alimentação', data: null, risco: 'alto', porque: 'cadastro em uso por 14 itens e 12 notas', editar: 'Configurações › Cadastros',
    imp: { bloqueia: [], apagar: [ap('Fornecedor Agro Estreito Rações', 'O cadastro.')], reverter: [rv('14 itens do estoque perdem o fornecedor', 'Eles continuam, só ficam sem fornecedor ligado.', { chip: 'Desliga vínculos' })], avisos: [av('12 notas continuam com o nome escrito', 'O nome fica nas notas antigas, mas elas deixam de ter ligação com o cadastro. Os relatórios por fornecedor não somam mais.')] } },
  { id: 'DO1', tipo: 'doenca', titulo: 'Mastite subclínica', sub: 'Ativa', data: null, risco: 'alto', porque: 'cadastro em uso', editar: 'Configurações › Cadastros',
    imp: { bloqueia: [], apagar: [ap('Doença: mastite subclínica', 'O cadastro.')], reverter: [rv('2 regras do calendário e 3 protocolos perdem a ligação', 'Eles continuam, só ficam sem doença ligada.', { chip: 'Desliga vínculos' })], avisos: [] } },
];

/* ---------- PEDIDOS ---------- */
const PEDIDOS_SEED = () => [
  { id: 'R1', alvo: 'P1', por: 'Ana Paula', quando: '2026-10-08T14:12', motivo: 'Lancei no animal errado, era a 1024.', status: 'pendente', mudou: 'A cria 1302 ganhou uma pesagem ontem (08/10). Quando o pedido foi feito, ela seria apagada; agora ela fica.' },
  { id: 'R2', alvo: 'C9', titulo: 'Pesagem da 0911 em 01/10/2026', tipo: 'controle', por: 'Marcos', quando: '2026-10-07T09:30', motivo: 'Pesagem duplicada.', status: 'pendente' },
  { id: 'R3', alvo: 'F2', por: 'Ana Paula', quando: '2026-10-08T16:40', motivo: 'Conta de energia lançada duas vezes.', status: 'pendente' },
  { id: 'R4', alvo: 'F2', por: 'Marcos', quando: '2026-10-09T08:05', motivo: 'Lançamento em duplicidade.', status: 'pendente' },
  { id: 'R5', alvo: 'F1', por: 'Marcos', quando: '2026-10-09T10:20', motivo: 'Nota da ração foi lançada duas vezes.', status: 'pendente' },
  { id: 'R6', alvo: null, titulo: 'Pesagem da 0877 em 27/09/2026', tipo: 'controle', por: 'Ana Paula', quando: '2026-10-05T10:02', motivo: 'Peso digitado errado.', status: 'aprovada', decididoPor: 'Jairo', decididoEm: '2026-10-06T11:05' },
  { id: 'R7', alvo: null, titulo: 'Venda do animal 1198 em 25/09/2026', tipo: 'venda_animal', por: 'Ana Paula', quando: '2026-10-02T15:48', motivo: 'Valor errado.', status: 'rejeitada', decididoPor: 'Jairo', decididoEm: '2026-10-03T08:15', motivoRej: 'A conta já foi recebida. Corrija o valor em vez de apagar a venda.' },
];

/* ---------- TRILHA ---------- */
const TRILHA_SEED = () => [
  { id: 'EX-2026-0090', quando: '2026-10-08T16:40', quem: 'Jairo', acao: 'apagou', titulo: 'Pesagem da 0911 em 02/10/2026', tipo: 'controle', motivo: 'Pesagem duplicada', apagado: ['Pesagem da 0911 em 02/10/2026 (18,4 kg)'], revertido: [] },
  { id: 'EX-2026-0089', quando: '2026-10-06T11:05', quem: 'Jairo', acao: 'aprovou', pedidoDe: 'Ana Paula', titulo: 'Pesagem da 0877 em 27/09/2026', tipo: 'controle', motivo: 'Peso digitado errado', apagado: ['Pesagem da 0877 em 27/09/2026 (31,9 kg)'], revertido: [] },
  { id: 'EX-2026-0088', quando: '2026-10-03T08:15', quem: 'Jairo', acao: 'rejeitou', pedidoDe: 'Ana Paula', titulo: 'Venda do animal 1198 em 25/09/2026', tipo: 'venda_animal', motivo: 'A conta já foi recebida. Corrija o valor em vez de apagar a venda.', apagado: [], revertido: [] },
  { id: 'EX-2026-0087', quando: '2026-09-29T17:22', quem: 'Jairo', acao: 'apagou', titulo: 'Nota LC-2026-00290 · Peças do trator', tipo: 'financeiro', motivo: 'Valor ou dado errado', apagado: ['Nota LC-2026-00290', '2 parcelas em aberto (R$ 1.620,00)'], revertido: [] },
  { id: 'EX-2026-0086', quando: '2026-09-22T09:10', quem: 'Jairo', acao: 'apagou', titulo: 'Entrada manual de 10 sacos de sal mineral', tipo: 'movimento_estoque', motivo: 'Era teste', apagado: ['Entrada manual de 10 sacos de sal mineral'], revertido: ['Saldo de Sal mineral voltou de 73 para 63'] },
  { id: 'EX-2026-0085', quando: '2026-09-15T13:47', quem: 'Jairo', acao: 'apagou', titulo: 'Parto da 0645 em 02/09/2026', tipo: 'parto', motivo: 'Animal ou pessoa errada', apagado: ['Parto da 0645 em 02/09/2026', 'Ficha da cria 1280'], revertido: ['Lactação nova removida', 'DEL da 0645: 13 → 241 dias'] },
];

/* ---------- CENÁRIOS (atalhos) ---------- */
const CENARIOS = [
  { id: 'c1', nome: '1. Nota com parcela paga (bloqueio)', tipo: 'financeiro', sel: ['F1', 'F2'], passo: 'impacto', papel: 'admin' },
  { id: 'c2', nome: '2. Animal com cascata (alto risco)', tipo: 'animal', sel: ['A1'], passo: 'impacto', papel: 'admin' },
  { id: 'c3', nome: '3. Parto com crias e lactação', tipo: 'parto', sel: ['P1'], passo: 'impacto', papel: 'admin' },
  { id: 'c4', nome: '4. Vale e folha', tipo: 'folha', sel: ['FP2', 'FP1'], passo: 'impacto', papel: 'admin' },
  { id: 'c5', nome: '5. Estoque (baixo e médio risco)', tipo: 'movimento_estoque', sel: ['E1', 'E2'], passo: 'impacto', papel: 'admin' },
  { id: 'c6', nome: '6. Cadastro em uso (bloqueio)', tipo: 'lote', sel: ['L1', 'L2'], passo: 'impacto', papel: 'admin' },
  { id: 'c7', nome: '7. Funcionário pedindo exclusão', tipo: 'parto', sel: ['P2'], passo: 'impacto', papel: 'func' },
  { id: 'c8', nome: '8. Painel do administrador: pedidos', aba: 'pedidos', papel: 'admin' },
  { id: 'c9', nome: '9. Funcionário: meus pedidos', aba: 'pedidos', papel: 'func' },
  { id: 'c10', nome: '10. Trilha (histórico)', aba: 'trilha', papel: 'admin' },
  { id: 'c11', nome: '11. Funcionário pede algo já pedido', tipo: 'financeiro', sel: ['F2', 'F6'], passo: 'impacto', papel: 'func' },
];
