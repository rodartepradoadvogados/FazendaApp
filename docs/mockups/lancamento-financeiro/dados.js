/* Dados fictícios da "Fazenda Vale Verde" (mesmo ambiente de demonstração do repositório).
   O plano de contas e as naturezas seguem backend/fazenda (plano_conta_gerencial) e docs/financeiro-regras-v2.md. */

const TODAY = "2026-10-15";               // data de referência do mockup
const MES_FECHADO = ["2026-08"];          // meses fechados (regra: não dá para lançar com emissão neles)
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/* ───── datas ───── */
const isoToDate = (s) => new Date(s + "T12:00:00Z");
const addDays = (s, n) => { const d = isoToDate(s); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const diffDays = (a, b) => Math.round((isoToDate(a) - isoToDate(b)) / 86400000);
const fmtD = (s) => (s ? s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) : "—");
const mesLabel = (s) => MESES[+s.slice(5, 7) - 1] + "/" + s.slice(0, 4);
const mesLong = (ym) => ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"][+ym.slice(5, 7) - 1] + "/" + ym.slice(0, 4);
const addMonths = (s, n) => {
  const d = isoToDate(s); const day = d.getUTCDate(); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + n);
  const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
  d.setUTCDate(Math.min(day, last)); return d.toISOString().slice(0, 10);
};
const emDias = (iso) => { const n = diffDays(iso, TODAY); return n === 0 ? "hoje" : n === 1 ? "amanhã" : n > 0 ? `em ${n} dias` : n === -1 ? "ontem" : `há ${-n} dias`; };

/* ───── dinheiro ───── */
const nf = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const BRL = (n) => (n < 0 ? "−" : "") + "R$ " + nf.format(Math.abs(Math.round(n * 100) / 100));
const fmtNum = (n) => (n === "" || n == null || isNaN(n) ? "" : nf.format(n));
const parseBR = (v) => {
  if (typeof v === "number") return v;
  let s = String(v ?? "").replace(/R\$|\s| /g, "");
  if (!s) return 0;
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
  const n = parseFloat(s);
  return isNaN(n) ? 0 : n;
};
const r2 = (n) => Math.round(n * 100) / 100;

/* ───── plano de contas (subconjunto do plano real) ───── */
const CONTAS_DESP = [
  ["3.01.01.01", "Ração e concentrados"], ["3.01.01.02", "Silagem e volumosos"], ["3.01.01.03", "Sal mineral e suplementos"], ["3.01.01.04", "Pastagem, adubação e sementes"],
  ["3.01.02.01", "Medicamentos e vacinas"], ["3.01.02.02", "Honorários veterinários"], ["3.01.02.03", "Exames e análises"],
  ["3.01.03.01", "Sêmen e material genético"], ["3.01.03.02", "Inseminação e protocolos hormonais"],
  ["3.01.04.01", "Limpeza e higiene da ordenha"], ["3.01.04.02", "Manutenção do equipamento de ordenha"],
  ["3.02.01", "Frete do leite e de animais"],
  ["3.03.01.01", "Salários e ordenados"], ["3.03.01.04", "Diárias e empreitadas"], ["3.03.01.17", "Vales e adiantamentos"],
  ["3.03.02.01", "Contabilidade e assessoria"], ["3.03.02.02", "Consultoria técnica (zootecnista / agrônomo)"],
  ["3.04.01", "Energia elétrica"], ["3.04.02", "Combustíveis e lubrificantes"], ["3.04.03", "Manutenção de máquinas e equipamentos"],
  ["3.04.04", "Manutenção de benfeitorias, cercas e instalações"], ["3.04.05", "Materiais de consumo e utilidades"],
  ["3.04.06", "Arrendamento e aluguéis pagos"], ["3.04.07", "Telefone e internet"], ["3.04.08", "Seguros"],
  ["3.05.01", "Contribuição sobre a venda (Funrural)"], ["3.06.02", "Tarifas bancárias"],
  ["3.06.03", "Pagamento de principal de empréstimos e financiamentos"],
  ["3.07.01", "Máquinas e equipamentos"], ["3.07.02", "Benfeitorias e construções"], ["3.07.03", "Veículos"],
  ["3.08.01", "Retirada do produtor (pró-labore e distribuições)"],
];
const CONTAS_REC = [
  ["2.01.01.01", "Leite (laticínio / cooperativa)"],
  ["2.01.02.01", "Venda de bezerros e machos"], ["2.01.02.02", "Venda de vacas e novilhas"], ["2.01.02.03", "Venda de animais de descarte"],
  ["2.01.03.01", "Venda de esterco e subprodutos"], ["2.01.03.02", "Serviços prestados a terceiros"],
  ["2.02.01", "Receitas financeiras (rendimentos)"], ["2.02.02", "Arrendamento e aluguéis recebidos"], ["2.02.03", "Outras receitas"],
  ["2.03.01", "Empréstimos e financiamentos recebidos"], ["2.03.02", "Aporte do produtor / sócio"],
];
const CONTA_NOME = Object.fromEntries([...CONTAS_DESP, ...CONTAS_REC]);

/* Nome que o dono reconhece (mesmo vocabulário do Resultado por litro e da DRE) */
function grupoDe(code) {
  if (!code) return "";
  if (code.startsWith("3.01.01")) return "Comida";
  if (code === "3.03.01.17") return "Gente · vale";
  if (code.startsWith("3.03.01")) return "Gente";
  if (code.startsWith("3.07")) return "Fora do resultado · investimento";
  if (code.startsWith("3.06.03")) return "Fora do resultado · financiamento";
  if (code.startsWith("3.08")) return "Fora do resultado · retirada do produtor";
  if (code.startsWith("3.05")) return "Impostos e taxas";
  if (code.startsWith("3.06")) return "Outras receitas e despesas";
  if (code.startsWith("3.")) return "Outros custeios";
  if (code.startsWith("2.01.01")) return "Receita de leite";
  if (code.startsWith("2.01")) return "Outras vendas";
  if (code.startsWith("2.03.01")) return "Fora do resultado · financiamento";
  if (code.startsWith("2.03")) return "Fora do resultado · aporte";
  return "Outras receitas e despesas";
}
const grupoCurto = (code) => grupoDe(code).replace(/^Fora do resultado · /, "");
function naturezaAuto(code) {
  if (!code) return "OPERACIONAL";
  if (code.startsWith("3.07")) return "INVESTIMENTO";
  if (code.startsWith("3.06.03") || code.startsWith("2.03.01")) return "FINANCIAMENTO";
  if (code.startsWith("3.08") || code.startsWith("2.03.02")) return "CAPITAL";
  if (code === "3.03.01.17") return "ADIANTAMENTO";
  return "OPERACIONAL";
}
const NATUREZAS = {
  OPERACIONAL: ["Operacional", "Entra no resultado do mês."],
  INVESTIMENTO: ["Investimento (compra de bem)", "Sai do resultado; só a depreciação entra."],
  FINANCIAMENTO: ["Financiamento", "Sai do resultado (empréstimo e principal)."],
  CAPITAL: ["Capital do produtor", "Sai do resultado (aporte e retirada)."],
  TRANSFERENCIA: ["Transferência entre contas", "Sai do resultado."],
  ADIANTAMENTO: ["Adiantamento (vale)", "Sai do resultado; fica como vale a receber do funcionário."],
  OBRIGACAO: ["Quitação de obrigação", "Sai do resultado (quita algo já reconhecido)."],
};

/* ───── catálogo de itens (estoque e serviços usados antes) ───── */
const ITENS = [
  { nome: "Ração concentrada", un: "kg", conta: "3.01.01.01", estoque: true, preco: 1.9 },
  { nome: "Sal mineral 25kg", un: "un", conta: "3.01.01.03", estoque: true, preco: 33.75 },
  { nome: "Silagem de milho", un: "t", conta: "3.01.01.02", estoque: true, preco: 330 },
  { nome: "Vacina aftosa", un: "dose", conta: "3.01.02.01", estoque: true, preco: 3.4 },
  { nome: "Antibiótico intramamário", un: "un", conta: "3.01.02.01", estoque: true, preco: 18.5 },
  { nome: "Diesel S10", un: "L", conta: "3.04.02", estoque: true, preco: 6.1 },
  { nome: "Produto de limpeza da ordenha", un: "un", conta: "3.01.04.01", estoque: true, preco: 142 },
  { nome: "Energia elétrica", un: "", conta: "3.04.01", estoque: false, servico: true },
  { nome: "Honorários contábeis", un: "", conta: "3.03.02.01", estoque: false, servico: true },
  { nome: "Manutenção da ordenhadeira", un: "", conta: "3.01.04.02", estoque: false, servico: true },
  { nome: "Consulta veterinária", un: "", conta: "3.01.02.02", estoque: false, servico: true },
  { nome: "Resfriador de leite 2.000 L", un: "un", conta: "3.07.01", estoque: false, bem: true },
];
const ITENS_REC = [
  { nome: "Leite", un: "L", conta: "2.01.01.01", estoque: true, preco: 2.85 },
  { nome: "Esterco e subprodutos", un: "t", conta: "2.01.03.01", estoque: false },
  { nome: "Aluguel de pasto", un: "", conta: "2.02.02", estoque: false, servico: true },
  { nome: "Serviço de silagem para terceiros", un: "", conta: "2.01.03.02", estoque: false, servico: true },
];

/* ───── fornecedores / clientes: o que o sistema já sabe de cada um ───── */
const FORN = {
  "Agropecuária Boa Safra": { prazo: 30, forma: "Boleto", item: "Ração concentrada", conta: "3.01.01.01", banco: 0 },
  "Nutrimix Nutrição Animal": { prazo: 30, forma: "Boleto", item: "Sal mineral 25kg", conta: "3.01.01.03", banco: 0 },
  "Vetnil Saúde Animal": { prazo: 20, forma: "Pix", item: "Antibiótico intramamário", conta: "3.01.02.01", banco: 0 },
  "Energia Elétrica Regional": { prazo: 12, forma: "Boleto", item: "Energia elétrica", conta: "3.04.01", banco: 0 },
  "Contabilidade Souza & Lima": { prazo: 10, forma: "Pix", item: "Honorários contábeis", conta: "3.03.02.01", banco: 0 },
  "Posto Estrada Real": { prazo: 15, forma: "Boleto", item: "Diesel S10", conta: "3.04.02", banco: 0 },
  "Oficina Ordenha Forte": { prazo: 10, forma: "Pix", item: "Manutenção da ordenhadeira", conta: "3.01.04.02", banco: 1 },
  "Silos do Vale Ltda.": { prazo: 30, forma: "Boleto", item: "Silagem de milho", conta: "3.01.01.02", banco: 0 },
  "Metalúrgica Frio Sul": { prazo: 30, forma: "Boleto", item: "Resfriador de leite 2.000 L", conta: "3.07.01", banco: 0 },
  "Central de Sêmen Exemplo": { prazo: 30, forma: "Boleto", item: "Sêmen", conta: "3.01.03.01", banco: 0 },
  "Veterinária Dra. Helena Prado": { prazo: 7, forma: "Pix", item: "Consulta veterinária", conta: "3.01.02.02", banco: 0 },
};
const FORN_REC = {
  "Laticínio Vale do Sol": { prazo: 20, forma: "TED", item: "Leite", conta: "2.01.01.01", banco: 0 },
  "Fazenda Três Marias": { prazo: 15, forma: "Pix", item: "Aluguel de pasto", conta: "2.02.02", banco: 0 },
  "Adubos Rio Claro": { prazo: 10, forma: "Pix", item: "Esterco e subprodutos", conta: "2.01.03.01", banco: 0 },
};
const RECENTES = {
  despesa: ["Agropecuária Boa Safra", "Nutrimix Nutrição Animal", "Vetnil Saúde Animal", "Energia Elétrica Regional"],
  receita: ["Laticínio Vale do Sol", "Fazenda Três Marias", "Adubos Rio Claro"],
};
const BANCOS = [
  { id: 0, nome: "Banco Exemplo", sub: "Ag. 0001 · C/C 12345-6", saldo: 83970 },
  { id: 1, nome: "Cooperativa Exemplo", sub: "Ag. 0200 · C/C 98765-4", saldo: 6200 },
];
const FORMAS = ["Pix", "Boleto", "TED", "Dinheiro", "Cartão"];
const FUNCIONARIOS = [
  { nome: "Adão Lima", salario: 2400, vales: 300 },
  { nome: "Marcos Souza", salario: 2650, vales: 0 },
  { nome: "Rita Ferreira", salario: 2800, vales: 800 },
];
const PEDIDOS = {
  despesa: [
    { id: "PD-2026-0007", forn: "Nutrimix Nutrição Animal", item: "Sal mineral 25kg", qtd: 120, unit: 33.75, total: 4050, previsto: "2026-10-22" },
    { id: "PD-2026-0008", forn: "Vetnil Saúde Animal", item: "Vacina aftosa", qtd: 400, unit: 3.4, total: 1360, previsto: "2026-10-28" },
  ],
  receita: [],
};
const TOUROS = [
  { id: "7HO00001", nome: "Touro Exemplo A (Holandês)", dose: 78 },
  { id: "7HO00002", nome: "Touro Exemplo B (Holandês)", dose: 92 },
  { id: "29GI00003", nome: "Touro Exemplo C (Gir leiteiro)", dose: 64 },
];

/* ───── livro de contas (o que o Controle financeiro lista) ───── */
const LANC = [
  { id: "LC-2026-00013", tipo: "despesa", forn: "Agropecuária Boa Safra", item: "Ração concentrada", valor: 15200, emissao: "2026-09-06", venc: "2026-10-06", doc: "NF 1520", conta: "3.01.01.01", centro: "Pecuária Leiteira" },
  { id: "LC-2026-00014", tipo: "despesa", forn: "Energia Elétrica Regional", item: "Energia elétrica — mês corrente", valor: 1560, emissao: "2026-10-05", venc: "2026-10-18", doc: "Fatura 88120", conta: "3.04.01", centro: "Pecuária Leiteira" },
  { id: "LC-2026-00015", tipo: "despesa", forn: "Vetnil Saúde Animal", item: "Antibióticos e vacinas", valor: 1280, emissao: "2026-09-30", venc: "2026-10-20", doc: "NF 4417", conta: "3.01.02.01", centro: "Pecuária Leiteira" },
  { id: "LC-2026-00016", tipo: "despesa", forn: "Nutrimix Nutrição Animal", item: "Sal mineral (3 parcelas)", valor: 1350, emissao: "2026-09-25", venc: "2026-10-25", doc: "NF 5530", parcela: "1/3", conta: "3.01.01.03", centro: "Pecuária Leiteira" },
  { id: "LC-2026-00016", tipo: "despesa", forn: "Nutrimix Nutrição Animal", item: "Sal mineral (3 parcelas)", valor: 1350, emissao: "2026-09-25", venc: "2026-11-25", doc: "NF 5530", parcela: "2/3", conta: "3.01.01.03", centro: "Pecuária Leiteira" },
  { id: "LC-2026-00016", tipo: "despesa", forn: "Nutrimix Nutrição Animal", item: "Sal mineral (3 parcelas)", valor: 1350, emissao: "2026-09-25", venc: "2026-12-25", doc: "NF 5530", parcela: "3/3", conta: "3.01.01.03", centro: "Pecuária Leiteira" },
  { id: "LC-2026-00017", tipo: "despesa", forn: "Oficina Ordenha Forte", item: "Manutenção da ordenhadeira", valor: 980, emissao: "2026-10-08", venc: "2026-11-05", doc: "OS 331", conta: "3.01.04.02", centro: "Pecuária Leiteira" },
  { id: "LC-2026-00018", tipo: "despesa", forn: "Posto Estrada Real", item: "Diesel S10", valor: 840, emissao: "2026-10-12", venc: "2026-11-12", doc: "NF 9921", conta: "3.04.02", centro: "Pecuária Leiteira" },
  /* já pagas (histórico que alimenta contexto e último preço) */
  { id: "LC-2026-00009", tipo: "despesa", forn: "Nutrimix Nutrição Animal", item: "Sal mineral 25kg", qtd: 100, unit: 33.75, valor: 3375, emissao: "2026-09-08", venc: "2026-10-08", doc: "NF 5301", conta: "3.01.01.03", centro: "Pecuária Leiteira", pago: { data: "2026-10-07", valor: 3375, banco: 0, forma: "Boleto" } },
  { id: "LC-2026-00010", tipo: "despesa", forn: "Agropecuária Boa Safra", item: "Ração concentrada", qtd: 7000, unit: 1.89, valor: 13230, emissao: "2026-08-05", venc: "2026-09-04", doc: "NF 1344", conta: "3.01.01.01", centro: "Pecuária Leiteira", pago: { data: "2026-09-04", valor: 13230, banco: 0, forma: "Boleto" } },
  { id: "LC-2026-00011", tipo: "despesa", forn: "Vetnil Saúde Animal", item: "Vacinas", valor: 1400, emissao: "2026-08-20", venc: "2026-09-09", doc: "NF 4301", conta: "3.01.02.01", centro: "Pecuária Leiteira", pago: { data: "2026-09-09", valor: 1400, banco: 0, forma: "Pix" } },
  { id: "LC-2026-00012", tipo: "despesa", forn: "Posto Estrada Real", item: "Diesel S10", qtd: 172, unit: 6.1, valor: 1050, emissao: "2026-09-10", venc: "2026-09-25", doc: "NF 9710", conta: "3.04.02", centro: "Pecuária Leiteira", pago: { data: "2026-09-25", valor: 1050, banco: 0, forma: "Boleto" } },
  { id: "LC-2026-00005", tipo: "receita", forn: "Laticínio Vale do Sol", item: "Leite — setembro/2026", valor: 18000, emissao: "2026-10-01", venc: "2026-10-30", doc: "Nota 7712", conta: "2.01.01.01", centro: "Pecuária Leiteira" },
  { id: "LC-2026-00004", tipo: "receita", forn: "Laticínio Vale do Sol", item: "Leite — agosto/2026", valor: 33040, emissao: "2026-09-01", venc: "2026-09-20", doc: "Nota 7501", conta: "2.01.01.01", centro: "Pecuária Leiteira", pago: { data: "2026-09-21", valor: 33040, banco: 0, forma: "TED" } },
];
const PRECO_ANT = {}; // último preço pago por item (derivado do livro)

function ultimoPreco(itemNome, tipo) {
  const L = LANC.filter((l) => l.tipo === tipo && l.item === itemNome && l.unit).sort((a, b) => (a.emissao < b.emissao ? 1 : -1));
  return L[0] ? { unit: L[0].unit, data: L[0].emissao, forn: L[0].forn } : null;
}
function contextoDe(forn, tipo) {
  const L = LANC.filter((l) => l.tipo === tipo && l.forn === forn);
  const abertas = L.filter((l) => !l.pago);
  const ultimas = {};
  L.sort((a, b) => (a.emissao < b.emissao ? 1 : -1)).forEach((l) => {
    const k = l.doc + "|" + l.id; if (!ultimas[k]) ultimas[k] = { id: l.id, doc: l.doc, emissao: l.emissao, item: l.item, partes: [], total: 0 };
    ultimas[k].partes.push(l); ultimas[k].total += l.valor;
  });
  return { n: abertas.length, aberto: abertas.reduce((s, l) => s + l.valor, 0), ultimo: L[0]?.emissao, recentes: Object.values(ultimas).slice(0, 3) };
}
let seq = 20;
const proxNumero = () => `LC-2026-${String(++seq).padStart(5, "0")}`;
