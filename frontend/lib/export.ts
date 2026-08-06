// Exportação de relatórios/listas em Excel (.xlsx) e PDF — cabeçalho e tabelas
// no padrão visual CowData (ver public/brand/cowdata-mark.svg e o mockup de
// relatório aprovado), usado em todas as exportações do sistema.
import { getUsuario } from "./api";
import { baixarArquivo } from "./nativo";

const NOME_FAZENDA = "Fazenda Estreito Ponte de Pedra";

const COR_VINHO = "3A0F1A";
const COR_VINHO_RGB: [number, number, number] = [58, 15, 26];
const COR_DOURADO_RGB: [number, number, number] = [224, 166, 60];
const COR_GRAFITE_RGB: [number, number, number] = [21, 11, 16];
const COR_MUTED_RGB: [number, number, number] = [107, 114, 128];
const COR_MUTED_CLARO_RGB: [number, number, number] = [156, 163, 175];
const COR_LINHA_RGB: [number, number, number] = [229, 231, 235];

// Cores por categoria de seção (mesma paleta do mockup "Ficha do Animal") —
// aplicadas ao pontinho ao lado do título de cada seção de um relatório em
// várias partes, para diferenciar visualmente o grupo a que ela pertence.
const CATEGORIAS: Record<string, [number, number, number]> = {
  repro: [139, 127, 240],
  saude: [78, 122, 90],
  alimentacao: [224, 166, 60],
  manejo: [91, 143, 176],
  financeiro: [122, 34, 51],
  estoque: [201, 138, 42],
};

function corSecao(titulo: string): [number, number, number] {
  const t = titulo.toLowerCase();
  if (/reprod|servi[çc]o|iatf|insemin|cio|parto|cobertura/.test(t)) return CATEGORIAS.repro;
  if (/sanit|sa[úu]de|vacina|exame|doen[çc]a|trat/.test(t)) return CATEGORIAS.saude;
  if (/aliment|dieta|trato/.test(t)) return CATEGORIAS.alimentacao;
  if (/financ|pagamento|receb|conta a |folha/.test(t)) return CATEGORIAS.financeiro;
  if (/estoque|insumo|compra/.test(t)) return CATEGORIAS.estoque;
  return CATEGORIAS.manejo;
}

export type ColunaExport = { header: string; key: string; width?: number };

function formatarValor(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  return String(v);
}

function dataHoje(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Roda a geração/entrega de um arquivo mostrando um alerta visível se algo
 *  falhar (import dinâmico de lib pesada, geração do PDF/Excel, entrega via
 *  Filesystem/Share dentro do app) — nenhuma tela deve ficar com um botão de
 *  exportar que "não faz nada" e não mostra erro nenhum. O erro original é
 *  relançado para quem chamou (algumas telas já têm feedback próprio, ex.
 *  mensagem inline) continuar funcionando normalmente. */
async function comAlertaDeErro<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    const msg = e instanceof Error ? e.message : "erro desconhecido";
    alert(`Não foi possível gerar/baixar o arquivo: ${msg}`);
    throw e;
  }
}

// Marca CowData rasterizada (public/brand/cowdata-mark.svg), carregada uma
// única vez por sessão e reutilizada no cabeçalho de todo PDF exportado.
let logoDataUrlPromise: Promise<string | null> | null = null;
async function carregarLogo(): Promise<string | null> {
  if (!logoDataUrlPromise) {
    logoDataUrlPromise = fetch("/brand/cowdata-mark-tile.png")
      .then((r) => r.blob())
      .then(
        (blob) =>
          new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result as string);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          }),
      )
      .catch(() => null);
  }
  return logoDataUrlPromise;
}

/** Cabeçalho padrão de PDF: fazenda (eyebrow) + título + subtítulo à
 * esquerda; marca CowData + autor/data à direita; linha de base sutil. */
function desenharCabecalhoPDF(
  doc: import("jspdf").jsPDF,
  opts: { titulo: string; subtitulo?: string; usuario?: string; dataStr: string; logo: string | null; emissor?: string },
) {
  const pageWidth = doc.internal.pageSize.getWidth();
  const left = 14;

  // Identificação de quem emite o documento (ex.: "CowData" no recibo) — só
  // aparece quando o chamador pede via opts.emissor; os demais exports (que
  // não passam esse campo) continuam exatamente como antes.
  if (opts.emissor) {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(...COR_DOURADO_RGB);
    doc.text(opts.emissor, left, 6.5, { charSpace: 0.3 });
  }

  doc.setFont("helvetica", "bold");
  doc.setFontSize(7.5);
  doc.setTextColor(...COR_MUTED_CLARO_RGB);
  doc.text(NOME_FAZENDA.toUpperCase(), left, 12, { charSpace: 0.6 });

  doc.setFont("helvetica", "bold");
  doc.setFontSize(15);
  doc.setTextColor(...COR_VINHO_RGB);
  doc.text(opts.titulo, left, 19.5);

  if (opts.subtitulo) {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8.5);
    doc.setTextColor(...COR_MUTED_RGB);
    doc.text(opts.subtitulo, left, 24.5);
  }

  const right = pageWidth - 14;
  if (opts.logo) {
    const tile = 8;
    doc.addImage(opts.logo, "PNG", right - tile, 6, tile, tile);
  }
  doc.setFont("helvetica", "normal");
  doc.setFontSize(7);
  doc.setTextColor(...COR_MUTED_CLARO_RGB);
  doc.text(`Gerado por ${opts.usuario || "—"}`, right, 18, { align: "right" });
  doc.text(opts.dataStr, right, 21.5, { align: "right" });

  doc.setDrawColor(...COR_LINHA_RGB);
  doc.setLineWidth(0.3);
  doc.line(left, 27.5, pageWidth - 14, 27.5);
}

/** Estilo de tabela padrão: cabeçalho maiúsculo cinza sem preenchimento,
 * linhas separadas só por um traço inferior claro — sem blocos de cor. */
const ESTILO_TABELA = {
  theme: "plain" as const,
  styles: { fontSize: 8, cellPadding: 2.2, textColor: [55, 65, 81] as [number, number, number], lineColor: COR_LINHA_RGB, lineWidth: { bottom: 0.15, top: 0, left: 0, right: 0 } },
  headStyles: { textColor: COR_MUTED_RGB, fontStyle: "bold" as const, fontSize: 7, lineColor: COR_MUTED_CLARO_RGB, lineWidth: { bottom: 0.3, top: 0, left: 0, right: 0 } },
};

function colunasMaiusculas(colunas: ColunaExport[]): ColunaExport[] {
  return colunas.map((c) => ({ ...c, header: c.header.toUpperCase() }));
}

export async function exportarExcel(
  titulo: string,
  colunas: ColunaExport[],
  linhas: Record<string, unknown>[],
  nomeArquivoBase: string,
) {
  return comAlertaDeErro(async () => {
  const ExcelJS = (await import("exceljs")).default;
  const usuario = getUsuario();
  const wb = new ExcelJS.Workbook();
  wb.creator = usuario?.nome || "FazendaApp";
  wb.created = new Date();
  const ws = wb.addWorksheet((titulo || "Relatório").slice(0, 31));

  const nCols = Math.max(colunas.length, 1);
  ws.mergeCells(1, 1, 1, nCols);
  ws.getCell(1, 1).value = NOME_FAZENDA.toUpperCase();
  ws.getCell(1, 1).font = { bold: true, size: 14, color: { argb: `FF${COR_VINHO}` } };
  ws.getCell(1, 1).alignment = { horizontal: "center" };
  ws.getRow(1).height = 22;

  ws.mergeCells(2, 1, 2, nCols);
  ws.getCell(2, 1).value = titulo;
  ws.getCell(2, 1).font = { bold: true, size: 12 };
  ws.getCell(2, 1).alignment = { horizontal: "center" };

  ws.mergeCells(3, 1, 3, nCols);
  ws.getCell(3, 1).value = `Gerado por ${usuario?.nome || "—"} em ${new Date().toLocaleDateString("pt-BR")}`;
  ws.getCell(3, 1).font = { italic: true, size: 9, color: { argb: "FF888888" } };
  ws.getCell(3, 1).alignment = { horizontal: "center" };

  ws.addRow([]);

  const headerRow = ws.addRow(colunas.map((c) => c.header));
  headerRow.eachCell((c) => {
    c.font = { bold: true, color: { argb: "FFFFFFFF" } };
    c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: `FF${COR_VINHO}` } };
    c.alignment = { horizontal: "center" };
  });

  linhas.forEach((linha) => {
    ws.addRow(colunas.map((c) => formatarValor(linha[c.key])));
  });

  colunas.forEach((c, i) => {
    ws.getColumn(i + 1).width = c.width || Math.max(12, c.header.length + 2);
  });

  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await baixarArquivo(blob, `${nomeArquivoBase}_${dataHoje()}.xlsx`);
  });
}

export async function exportarPDF(
  titulo: string,
  colunas: ColunaExport[],
  linhas: Record<string, unknown>[],
  nomeArquivoBase: string,
) {
  return comAlertaDeErro(async () => {
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const usuario = getUsuario();
  const logo = await carregarLogo();
  const doc = new jsPDF({ orientation: colunas.length > 6 ? "landscape" : "portrait" });
  const dataStr = new Date().toLocaleDateString("pt-BR");

  const cabecalho = () => desenharCabecalhoPDF(doc, { titulo, usuario: usuario?.nome, dataStr, logo });

  autoTable(doc, {
    ...ESTILO_TABELA,
    head: [colunasMaiusculas(colunas).map((c) => c.header)],
    body: linhas.map((linha) => colunas.map((c) => formatarValor(linha[c.key]))),
    startY: 31,
    margin: { top: 31 },
    didDrawPage: cabecalho,
  });

  await baixarArquivo(doc.output("blob"), `${nomeArquivoBase}_${dataHoje()}.pdf`);
  });
}

export type SecaoFicha = { titulo: string; colunas: ColunaExport[]; linhas: Record<string, unknown>[] };

/**
 * Excel com várias abas (uma planilha por seção/categoria) — usado quando um
 * relatório é discriminado em várias listas e o usuário pode escolher quais
 * exportar juntas num único arquivo (ex.: Agenda Reprodutiva). Cada aba leva
 * o mesmo cabeçalho padronizado da fazenda; seções sem linha nenhuma não
 * geram aba (evita abas vazias no meio do arquivo).
 */
export async function exportarMultiExcel(
  tituloGeral: string,
  secoes: SecaoFicha[],
  nomeArquivoBase: string,
) {
  return comAlertaDeErro(async () => {
  const ExcelJS = (await import("exceljs")).default;
  const usuario = getUsuario();
  const wb = new ExcelJS.Workbook();
  wb.creator = usuario?.nome || "FazendaApp";
  wb.created = new Date();

  const nomesUsados = new Set<string>();
  for (const secao of secoes) {
    if (!secao.linhas.length) continue;
    let nomeAba = secao.titulo.replace(/[[\]*/\\?:]/g, "").slice(0, 31) || "Aba";
    let sufixo = 2;
    while (nomesUsados.has(nomeAba)) {
      nomeAba = `${secao.titulo.slice(0, 28)} (${sufixo++})`;
    }
    nomesUsados.add(nomeAba);

    const ws = wb.addWorksheet(nomeAba);
    const nCols = Math.max(secao.colunas.length, 1);

    ws.mergeCells(1, 1, 1, nCols);
    ws.getCell(1, 1).value = NOME_FAZENDA.toUpperCase();
    ws.getCell(1, 1).font = { bold: true, size: 14, color: { argb: `FF${COR_VINHO}` } };
    ws.getCell(1, 1).alignment = { horizontal: "center" };
    ws.getRow(1).height = 22;

    ws.mergeCells(2, 1, 2, nCols);
    ws.getCell(2, 1).value = `${tituloGeral} — ${secao.titulo}`;
    ws.getCell(2, 1).font = { bold: true, size: 12 };
    ws.getCell(2, 1).alignment = { horizontal: "center" };

    ws.mergeCells(3, 1, 3, nCols);
    ws.getCell(3, 1).value = `Gerado por ${usuario?.nome || "—"} em ${new Date().toLocaleDateString("pt-BR")}`;
    ws.getCell(3, 1).font = { italic: true, size: 9, color: { argb: "FF888888" } };
    ws.getCell(3, 1).alignment = { horizontal: "center" };

    ws.addRow([]);

    const headerRow = ws.addRow(secao.colunas.map((c) => c.header));
    headerRow.eachCell((c) => {
      c.font = { bold: true, color: { argb: "FFFFFFFF" } };
      c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: `FF${COR_VINHO}` } };
      c.alignment = { horizontal: "center" };
    });

    secao.linhas.forEach((linha) => {
      ws.addRow(secao.colunas.map((c) => formatarValor(linha[c.key])));
    });

    secao.colunas.forEach((c, i) => {
      ws.getColumn(i + 1).width = c.width || Math.max(12, c.header.length + 2);
    });
  }

  if (!wb.worksheets.length) {
    wb.addWorksheet("Sem dados").getCell(1, 1).value = "Nenhuma categoria selecionada tinha dados para exportar.";
  }

  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await baixarArquivo(blob, `${nomeArquivoBase}_${dataHoje()}.xlsx`);
  });
}

/**
 * PDF com várias seções (uma tabela por tipo de lançamento) — usado na ficha
 * única do animal. Pode gerar quantas páginas forem necessárias: cada seção
 * só entra se tiver alguma linha, e o cabeçalho da fazenda é redesenhado em
 * toda página nova (seja por quebra automática de uma tabela grande, seja
 * por falta de espaço para o título da próxima seção). Cada título de seção
 * leva um pontinho colorido por categoria (reprodução/sanidade/alimentação/
 * financeiro/estoque/manejo), no mesmo padrão do relatório-modelo aprovado.
 */
export async function exportarFichaPDF(
  titulo: string,
  subtitulo: string,
  secoes: SecaoFicha[],
  nomeArquivoBase: string,
) {
  return comAlertaDeErro(async () => {
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const usuario = getUsuario();
  const logo = await carregarLogo();
  const doc = new jsPDF({ orientation: "portrait" });
  const dataStr = new Date().toLocaleDateString("pt-BR");
  const pageHeight = doc.internal.pageSize.getHeight();

  const cabecalho = () => desenharCabecalhoPDF(doc, { titulo, subtitulo, usuario: usuario?.nome, dataStr, logo });

  let cursorY = 32;
  let alguma = false;
  for (const secao of secoes) {
    if (!secao.linhas.length) continue;
    alguma = true;
    if (cursorY > pageHeight - 40) {
      doc.addPage();
      cabecalho();
      cursorY = 32;
    }
    const [r, g, b] = corSecao(secao.titulo);
    doc.setFillColor(r, g, b);
    doc.circle(15.3, cursorY - 1.3, 0.9, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10.5);
    doc.setTextColor(...COR_GRAFITE_RGB);
    doc.text(secao.titulo, 18, cursorY);
    cursorY += 4;

    autoTable(doc, {
      ...ESTILO_TABELA,
      head: [colunasMaiusculas(secao.colunas).map((c) => c.header)],
      body: secao.linhas.map((linha) => secao.colunas.map((c) => formatarValor(linha[c.key]))),
      startY: cursorY,
      margin: { top: 32 },
      didDrawPage: cabecalho,
    });
    cursorY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 8;
  }

  if (!alguma) {
    cabecalho();
    doc.setFontSize(10);
    doc.setTextColor(...COR_MUTED_RGB);
    doc.text("Nenhum lançamento encontrado para este animal.", 14, 40);
  }

  await baixarArquivo(doc.output("blob"), `${nomeArquivoBase}_${dataHoje()}.pdf`);
  });
}

export type LancamentoRecibo = {
  numero_lancamento: string | null;
  tipo: string;
  fornecedor: string;
  descricao: string;
  /** Valor TOTAL da conta/lançamento original (ex.: R$ 40.000 de uma compra
   * parcelada) — não necessariamente o que foi efetivamente pago nesta baixa,
   * ver `valor_pago` abaixo. */
  valor: number;
  /** Valor efetivamente pago/recebido NESTA baixa. Quando presente e menor
   * que `valor`, o recibo deixa explícito que houve pagamento parcial (ver
   * #— bug: recibo mostrava o valor total da conta como se fosse o valor
   * pago). Undefined/null quando a informação de baixa não se aplica (ex.:
   * recibo de folha de pagamento gerado fora do fluxo de Financeiro). */
  valor_pago?: number | null;
  /** Parcela(s) nova(s) criada(s) com o RESTANTE não pago nesta baixa (o
   * usuário reparcelou a diferença em vez de dar desconto) — cada item é uma
   * nova conta a pagar/receber com seu próprio valor e vencimento. */
  reparcelamento?: { valor: number; data_vencimento?: string | null; parcela_num?: number | null }[];
  data_pagamento?: string | null;
  data_vencimento?: string | null;
  data_emissao?: string | null;
  forma_pagamento?: string | null;
  tipo_documento?: string | null;
  centro_custo?: string | null;
  itens?: { produto: string; quantidade?: number | null; valor_unitario?: number | null; valor_total?: number | null }[];
};

function fmtDataBR(iso?: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return d && m && a ? `${d}/${m}/${a}` : iso;
}

function fmtBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Gera o PDF do recibo de um lançamento — usado tanto para "Salvar" (baixa
 * direto) quanto para "Enviar" (o mesmo PDF vira o anexo do e-mail).
 *
 * Bug corrigido: com pagamento PARCIAL (ex.: conta de R$ 40.000, pago
 * R$ 20.000 e reparcelado o restante), o recibo mostrava o valor TOTAL da
 * conta original como se fosse o valor pago. Agora, quando `valor_pago` vem
 * preenchido e é diferente de `valor` (a conta original), o recibo mostra os
 * dois separadamente — e, se o restante foi reparcelado (`reparcelamento`),
 * lista a(s) nova(s) parcela(s) com valor e vencimento. */
export async function gerarReciboPDF(lanc: LancamentoRecibo) {
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const usuario = getUsuario();
  const logo = await carregarLogo();
  const doc = new jsPDF({ orientation: "portrait" });
  const dataStr = new Date().toLocaleDateString("pt-BR");

  // "CowData" identifica quem emite o recibo, no topo do documento.
  desenharCabecalhoPDF(doc, { titulo: "Recibo", usuario: usuario?.nome, dataStr, logo, emissor: "CowData" });

  const houvePagamentoParcial =
    lanc.valor_pago != null && Math.round((lanc.valor - lanc.valor_pago) * 100) / 100 !== 0;

  const rotuloContraparte = lanc.tipo === "receita" ? "Recebemos de" : "Pagamos a";
  const linhas: [string, string][] = [
    ["Nº do lançamento", lanc.numero_lancamento || "—"],
    [rotuloContraparte, lanc.fornecedor || "—"],
    ["Descrição", lanc.descricao || "—"],
    ...(houvePagamentoParcial
      ? ([
          ["Valor da conta original", fmtBRL(lanc.valor)],
          ["Valor pago nesta baixa", fmtBRL(lanc.valor_pago as number)],
        ] as [string, string][])
      : ([["Valor", fmtBRL(lanc.valor_pago ?? lanc.valor)]] as [string, string][])),
    ["Data de emissão", fmtDataBR(lanc.data_emissao)],
    ["Data de vencimento", fmtDataBR(lanc.data_vencimento)],
    ["Data de pagamento", fmtDataBR(lanc.data_pagamento)],
    ["Forma de pagamento", lanc.forma_pagamento || "—"],
    ["Tipo de documento", lanc.tipo_documento || "—"],
  ];

  let cursorY = 35;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  for (const [rotulo, valor] of linhas) {
    doc.setFont("helvetica", "bold");
    doc.setTextColor(...COR_GRAFITE_RGB);
    doc.text(`${rotulo}:`, 14, cursorY);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(55, 65, 81);
    doc.text(valor, 62, cursorY);
    cursorY += 6;
  }
  cursorY += 4;

  const reparcelamento = lanc.reparcelamento || [];
  if (houvePagamentoParcial && reparcelamento.length) {
    const [r, g, b] = corSecao("financeiro");
    doc.setFillColor(r, g, b);
    doc.circle(15.3, cursorY - 1.3, 0.9, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10.5);
    doc.setTextColor(...COR_GRAFITE_RGB);
    doc.text("Restante reparcelado", 18, cursorY);
    cursorY += 4;
    autoTable(doc, {
      ...ESTILO_TABELA,
      head: [["PARCELA", "NOVO VENCIMENTO", "VALOR"]],
      body: reparcelamento.map((p, i) => [
        p.parcela_num != null ? String(p.parcela_num) : String(i + 1),
        fmtDataBR(p.data_vencimento),
        fmtBRL(p.valor),
      ]),
      startY: cursorY,
    });
    cursorY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 10;
  }

  const itens = (lanc.itens || []).filter((i) => i.produto);
  if (itens.length) {
    const [r, g, b] = corSecao("estoque");
    doc.setFillColor(r, g, b);
    doc.circle(15.3, cursorY - 1.3, 0.9, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10.5);
    doc.setTextColor(...COR_GRAFITE_RGB);
    doc.text("Itens", 18, cursorY);
    cursorY += 4;
    autoTable(doc, {
      ...ESTILO_TABELA,
      head: [["PRODUTO/SERVIÇO", "QTD.", "VALOR UNIT.", "VALOR TOTAL"]],
      body: itens.map((i) => [
        i.produto,
        i.quantidade != null ? String(i.quantidade) : "—",
        i.valor_unitario != null ? i.valor_unitario.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "—",
        i.valor_total != null ? i.valor_total.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) : "—",
      ]),
      startY: cursorY,
    });
    cursorY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 10;
  }

  doc.setFont("helvetica", "italic");
  doc.setFontSize(8);
  doc.setTextColor(...COR_MUTED_RGB);
  doc.text(`Recibo gerado por ${usuario?.nome || "—"} em ${dataStr}`, 14, cursorY + 10);

  return doc;
}
