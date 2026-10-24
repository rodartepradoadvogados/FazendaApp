// Exportação de relatórios/listas em Excel (.xlsx) e PDF — cabeçalho e tabelas
// no padrão visual CowData (ver public/brand/cowdata-mark.svg e o mockup de
// relatório aprovado), usado em todas as exportações do sistema.
import { getFazendaAtual, getUsuario } from "./api";
import { baixarArquivo, salvarArquivo } from "./nativo";

// "baixar" (padrão) só salva o arquivo, sem abrir nada — "compartilhar" abre
// a folha nativa de compartilhar (ver lib/nativo.ts). Pedido explícito do
// usuário para separar os dois: antes "Exportar" sempre ia direto pra folha
// de compartilhar dentro do app, sem opção de só baixar.
export type ModoEntregaExport = "baixar" | "compartilhar";

async function entregarArquivo(blob: Blob, nomeArquivo: string, modo: ModoEntregaExport): Promise<void> {
  if (modo === "compartilhar") { await baixarArquivo(blob, nomeArquivo); return; }
  const gravado = await salvarArquivo(blob, nomeArquivo);
  // `salvarArquivo` só devolve `{uri}` dentro do app nativo (Capacitor) — no
  // navegador/PWA o próprio SO já mostra a notificação de download, então
  // não repete aviso nenhum aqui. Dentro do app, gravar em Directory.Documents
  // não abre nada nem mostra nada sozinho (ver comentário de `salvarArquivo`
  // em lib/nativo.ts) — sem este aviso, "Baixar" clicava, gerava o arquivo de
  // verdade, e não dava sinal nenhum de que funcionou: o usuário via a tela
  // voltar ao normal e concluía que "não exportou nada" (bug relatado com a
  // folha de campo do protocolo, mas o mecanismo é o mesmo em toda
  // exportação "Baixar" do app).
  if (gravado) alert(`Arquivo salvo: ${nomeArquivo}`);
}

// Cabeçalho de TODO arquivo exportado: o nome da fazenda ATUAL (a escolhida no
// login/troca de fazenda). BUG CORRIGIDO: antes era um nome fixo de uma fazenda
// cliente, e só os relatórios do Financeiro liam a fazenda atual — Excel e PDF
// de qualquer outra fazenda saíam com o nome errado no topo. Sem fazenda
// conhecida (sessão antiga), sai a marca do sistema, nunca o nome de outra.
const NOME_PADRAO_CABECALHO = "CowData";

function nomeDaFazenda(): string {
  return getFazendaAtual()?.nome?.trim() || NOME_PADRAO_CABECALHO;
}

// Paleta "Institucional" do redesign (ver globals.css, data-paleta="azul"):
// marinho estrutural no lugar do vinho, ouro escurecido no lugar do dourado
// antigo — mesma família de cor de toda a interface, agora também nos
// documentos exportados.
const COR_VINHO = "0E2A47";
const COR_VINHO_RGB: [number, number, number] = [14, 42, 71];
const COR_DOURADO_RGB: [number, number, number] = [138, 109, 47];
const COR_GRAFITE_RGB: [number, number, number] = [10, 31, 54];
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

export type ColunaExport = {
  header: string; key: string;
  /** Largura em caracteres no Excel. */
  width?: number;
  /** Largura em mm no PDF; sem ela a coluna se ajusta ao conteúdo (o que espreme tudo quando há muitas colunas). */
  larguraPdf?: number;
  /** Excel: grava o valor como número (ordena e soma) em vez de texto, quando o valor da linha é um number. */
  numerico?: boolean;
};

function formatarValor(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  return String(v);
}

// Data local (fuso do usuário) — toISOString() é UTC e, à noite no Brasil, já
// carimbava o arquivo com o dia seguinte.
function dataHoje(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
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

// Logomarca CowData Milk rasterizada (public/brand/cowdata-horizontal-pdf.png), carregada uma
// única vez por sessão e reutilizada no cabeçalho de todo PDF exportado.
let logoDataUrlPromise: Promise<string | null> | null = null;
async function carregarLogo(): Promise<string | null> {
  if (!logoDataUrlPromise) {
    logoDataUrlPromise = fetch("/brand/cowdata-horizontal-pdf.png")
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
 * esquerda; logomarca CowData Milk + autor/data à direita; linha de base sutil. */
function desenharCabecalhoPDF(
  doc: import("jspdf").jsPDF,
  opts: { titulo: string; subtitulo?: string; usuario?: string; dataStr: string; logo: string | null; emissor?: string; fazenda?: string },
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
  doc.text((opts.fazenda || nomeDaFazenda()).toUpperCase(), left, 12, { charSpace: 0.6 });

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
    // Proporção do PNG da logomarca horizontal (900 x 202 px).
    const larg = 36;
    doc.addImage(opts.logo, "PNG", right - larg, 4.6, larg, larg * 202 / 900);
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

/** Extras opcionais da exportação de lista (Excel/PDF) — sem eles o arquivo sai exatamente como antes. */
export type OpcoesExportLista = {
  /** Filtros usados na tela (período, animais, lotes…), impressos no cabeçalho. */
  filtros?: string;
  /** Tabela de resumo (ex.: por lote: nº de vacas e média) antes da lista. */
  resumo?: { titulo: string; colunas: ColunaExport[]; linhas: Record<string, unknown>[] };
};

// A fonte padrão do jsPDF (Helvetica, WinAnsi) não tem "›", "…", "−" nem "≥/≤".
const textoPdf = (t: string) => t.replace(/›/g, ">").replace(/…/g, "...").replace(/[−–]/g, "-").replace(/≥/g, ">=").replace(/≤/g, "<=");

export async function exportarExcel(
  titulo: string,
  colunas: ColunaExport[],
  linhas: Record<string, unknown>[],
  nomeArquivoBase: string,
  modo: ModoEntregaExport = "baixar",
  opcoes?: OpcoesExportLista,
) {
  return comAlertaDeErro(async () => {
  const ExcelJS = (await import("exceljs")).default;
  const usuario = getUsuario();
  const wb = new ExcelJS.Workbook();
  wb.creator = usuario?.nome || "FazendaApp";
  wb.created = new Date();
  // O Excel recusa * ? : \ / [ ] no nome da aba — sem tirar, um título como
  // "GMD/GPD" derrubava a exportação inteira.
  const ws = wb.addWorksheet((titulo || "Relatório").replace(/[[\]*/\\?:]/g, "-").slice(0, 31) || "Relatório");

  const nCols = Math.max(colunas.length, 1);
  ws.mergeCells(1, 1, 1, nCols);
  ws.getCell(1, 1).value = nomeDaFazenda().toUpperCase();
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

  if (opcoes?.filtros) {
    ws.mergeCells(4, 1, 4, nCols);
    ws.getCell(4, 1).value = `Filtros: ${opcoes.filtros}`;
    ws.getCell(4, 1).font = { size: 9, color: { argb: "FF4B5563" } };
    ws.getCell(4, 1).alignment = { horizontal: "left", wrapText: true };
    ws.getRow(4).height = Math.min(60, 15 * Math.ceil(opcoes.filtros.length / 90));
  }

  ws.addRow([]);

  const pintarCabecalho = (row: import("exceljs").Row) => row.eachCell((c) => {
    c.font = { bold: true, color: { argb: "FFFFFFFF" } };
    c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: `FF${COR_VINHO}` } };
    c.alignment = { horizontal: "center" };
  });
  const valorCelula = (c: ColunaExport, v: unknown) => (c.numerico && typeof v === "number" ? v : formatarValor(v));

  if (opcoes?.resumo?.linhas.length) {
    const tituloResumo = ws.addRow([opcoes.resumo.titulo]);
    tituloResumo.getCell(1).font = { bold: true, size: 11 };
    pintarCabecalho(ws.addRow(opcoes.resumo.colunas.map((c) => c.header)));
    opcoes.resumo.linhas.forEach((linha) => ws.addRow(opcoes.resumo!.colunas.map((c) => valorCelula(c, linha[c.key]))));
    ws.addRow([]);
  }

  const headerRow = ws.addRow(colunas.map((c) => c.header));
  pintarCabecalho(headerRow);

  linhas.forEach((linha) => {
    ws.addRow(colunas.map((c) => (opcoes ? valorCelula(c, linha[c.key]) : formatarValor(linha[c.key]))));
  });

  colunas.forEach((c, i) => {
    ws.getColumn(i + 1).width = c.width || Math.max(12, c.header.length + 2);
  });

  const buf = await wb.xlsx.writeBuffer();
  const blob = new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
  await entregarArquivo(blob, `${nomeArquivoBase}_${dataHoje()}.xlsx`, modo);
  });
}

export async function exportarPDF(
  titulo: string,
  colunas: ColunaExport[],
  linhas: Record<string, unknown>[],
  nomeArquivoBase: string,
  modo: ModoEntregaExport = "baixar",
  opcoes?: OpcoesExportLista,
) {
  return comAlertaDeErro(async () => {
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const usuario = getUsuario();
  const logo = await carregarLogo();
  const doc = new jsPDF({ orientation: colunas.length > 6 ? "landscape" : "portrait" });
  const dataStr = new Date().toLocaleDateString("pt-BR");

  const cabecalho = () => desenharCabecalhoPDF(doc, { titulo, usuario: usuario?.nome, dataStr, logo });

  if (!opcoes?.filtros && !opcoes?.resumo?.linhas.length) {
    autoTable(doc, {
      ...ESTILO_TABELA,
      head: [colunasMaiusculas(colunas).map((c) => c.header)],
      body: linhas.map((linha) => colunas.map((c) => formatarValor(linha[c.key]))),
      startY: 31,
      margin: { top: 31 },
      didDrawPage: cabecalho,
    });
  } else {
    // Com filtros/resumo: o cabeçalho sai UMA vez por página (duas tabelas
    // podem dividir a mesma página — sem o controle, ele seria redesenhado).
    const comCabecalho = new Set<number>();
    const cabecalhoDaPagina = () => {
      const pagina = doc.getCurrentPageInfo().pageNumber;
      if (comCabecalho.has(pagina)) return;
      comCabecalho.add(pagina);
      cabecalho();
    };
    cabecalhoDaPagina();
    let y = 32;
    const largura = doc.internal.pageSize.getWidth() - 28;
    if (opcoes.filtros) {
      doc.setFont("helvetica", "normal");
      doc.setFontSize(8);
      doc.setTextColor(...COR_MUTED_RGB);
      const partes = doc.splitTextToSize(textoPdf(`Filtros: ${opcoes.filtros}`), largura) as string[];
      doc.text(partes, 14, y + 1);
      y += partes.length * 3.6 + 3;
    }
    if (opcoes.resumo?.linhas.length) {
      doc.setFont("helvetica", "bold");
      doc.setFontSize(10);
      doc.setTextColor(...COR_GRAFITE_RGB);
      doc.text(textoPdf(opcoes.resumo.titulo), 14, y + 2);
      autoTable(doc, {
        ...ESTILO_TABELA,
        head: [colunasMaiusculas(opcoes.resumo.colunas).map((c) => textoPdf(c.header))],
        body: opcoes.resumo.linhas.map((linha) => opcoes.resumo!.colunas.map((c) => textoPdf(formatarValor(linha[c.key])))),
        startY: y + 4,
        margin: { top: 31 },
        didDrawPage: cabecalhoDaPagina,
      });
      y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 8;
    }
    autoTable(doc, {
      ...ESTILO_TABELA,
      head: [colunasMaiusculas(colunas).map((c) => textoPdf(c.header))],
      body: linhas.map((linha) => colunas.map((c) => textoPdf(formatarValor(linha[c.key])))),
      startY: y,
      margin: { top: 31 },
      didDrawPage: cabecalhoDaPagina,
    });
  }

  await entregarArquivo(doc.output("blob"), `${nomeArquivoBase}_${dataHoje()}.pdf`, modo);
  });
}

export type SecaoFicha = {
  titulo: string; colunas: ColunaExport[]; linhas: Record<string, unknown>[];
  /** Começa numa página nova (ex.: um extrato por pessoa). */
  novaPagina?: boolean;
  /** Linhas a destacar com fundo dourado claro no PDF e no Excel (ex.: animais ainda dentro do prazo). */
  destacar?: (linha: Record<string, unknown>) => boolean;
};

/** Opções extras do PDF em seções — tudo opcional; sem elas o documento sai exatamente como antes. */
export type OpcoesFichaPDF = {
  orientacao?: "portrait" | "landscape";
  /** Faixa de totais logo abaixo do cabeçalho da primeira página. */
  resumo?: { rotulo: string; valor: string; detalhe?: string }[];
  /** Linhas de legenda depois da última seção. */
  legenda?: string[];
  /** Texto do rodapé; quando informado, todas as páginas ganham o rodapé e "Página X de N". */
  rodape?: string;
};

/** Opções extras do Excel em abas — tudo opcional; sem elas o arquivo sai exatamente como antes. */
export type OpcoesMultiExcel = {
  /** Complemento da linha "Gerado por…" (ex.: o filtro aplicado). */
  subtitulo?: string;
  congelarCabecalho?: boolean;
  autofiltro?: boolean;
  legenda?: string[];
};

const FUNDO_DESTAQUE_RGB: [number, number, number] = [243, 236, 217];
const FUNDO_DESTAQUE_ARGB = "FFF3ECD9";

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
  modo: ModoEntregaExport = "baixar",
  opcoes?: OpcoesMultiExcel,
) {
  return comAlertaDeErro(async () => {
    const blob = await gerarMultiExcelBlob(tituloGeral, secoes, opcoes);
    await entregarArquivo(blob, `${nomeArquivoBase}_${dataHoje()}.xlsx`, modo);
  });
}

/** Monta o .xlsx com uma aba por seção e devolve o arquivo, sem entregá-lo (quem exporta entrega; os testes inspecionam). */
export async function gerarMultiExcelBlob(tituloGeral: string, secoes: SecaoFicha[], opcoes?: OpcoesMultiExcel): Promise<Blob> {
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
    ws.getCell(1, 1).value = nomeDaFazenda().toUpperCase();
    ws.getCell(1, 1).font = { bold: true, size: 14, color: { argb: `FF${COR_VINHO}` } };
    ws.getCell(1, 1).alignment = { horizontal: "center" };
    ws.getRow(1).height = 22;

    ws.mergeCells(2, 1, 2, nCols);
    ws.getCell(2, 1).value = `${tituloGeral} — ${secao.titulo}`;
    ws.getCell(2, 1).font = { bold: true, size: 12 };
    ws.getCell(2, 1).alignment = { horizontal: "center" };

    ws.mergeCells(3, 1, 3, nCols);
    ws.getCell(3, 1).value = `Gerado por ${usuario?.nome || "—"} em ${new Date().toLocaleDateString("pt-BR")}${opcoes?.subtitulo ? ` · ${opcoes.subtitulo}` : ""}`;
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
      const row = ws.addRow(secao.colunas.map((c) => {
        const v = linha[c.key];
        return c.numerico && typeof v === "number" ? v : formatarValor(v);
      }));
      if (secao.destacar?.(linha)) {
        row.eachCell((c) => { c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: FUNDO_DESTAQUE_ARGB } }; });
      }
    });

    secao.colunas.forEach((c, i) => {
      ws.getColumn(i + 1).width = c.width || Math.max(12, c.header.length + 2);
    });

    if (opcoes?.congelarCabecalho) ws.views = [{ state: "frozen", ySplit: headerRow.number }];
    if (opcoes?.autofiltro) {
      ws.autoFilter = { from: { row: headerRow.number, column: 1 }, to: { row: headerRow.number + secao.linhas.length, column: nCols } };
    }
    if (opcoes?.legenda?.length) {
      ws.addRow([]);
      for (const linha of opcoes.legenda) {
        const row = ws.addRow([linha]);
        row.getCell(1).font = { italic: true, size: 9, color: { argb: "FF6B7280" } };
      }
    }
  }

  if (!wb.worksheets.length) {
    wb.addWorksheet("Sem dados").getCell(1, 1).value = "Nenhuma categoria selecionada tinha dados para exportar.";
  }

  const buf = await wb.xlsx.writeBuffer();
  return new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
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
  modo: ModoEntregaExport = "baixar",
  opcoes?: OpcoesFichaPDF,
) {
  return comAlertaDeErro(async () => {
    const blob = await gerarFichaPDFBlob(titulo, subtitulo, secoes, opcoes);
    await entregarArquivo(blob, `${nomeArquivoBase}_${dataHoje()}.pdf`, modo);
  });
}

/** Monta o PDF em seções e devolve o arquivo, sem entregá-lo (quem exporta entrega; os testes e a conferência visual usam). */
export async function gerarFichaPDFBlob(titulo: string, subtitulo: string, secoes: SecaoFicha[], opcoes?: OpcoesFichaPDF): Promise<Blob> {
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const usuario = getUsuario();
  const logo = await carregarLogo();
  const doc = new jsPDF({ orientation: opcoes?.orientacao ?? "portrait" });
  const dataStr = new Date().toLocaleDateString("pt-BR");
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margemInferior = opcoes?.rodape !== undefined ? 16 : 10;

  const cabecalho = () => desenharCabecalhoPDF(doc, { titulo, subtitulo, usuario: usuario?.nome, dataStr, logo });

  let cursorY = 32;
  let alguma = false;

  // Faixa de totais logo abaixo do cabeçalho da primeira página.
  if (opcoes?.resumo?.length) {
    const largura = Math.min(72, (pageWidth - 28) / opcoes.resumo.length);
    opcoes.resumo.forEach((item, i) => {
      const x = 14 + i * largura;
      doc.setFont("helvetica", "bold");
      doc.setFontSize(6.5);
      doc.setTextColor(...COR_MUTED_RGB);
      doc.text(item.rotulo.toUpperCase(), x, cursorY + 1, { charSpace: 0.4 });
      doc.setFontSize(14);
      doc.setTextColor(...COR_GRAFITE_RGB);
      doc.text(item.valor, x, cursorY + 7.5);
      if (item.detalhe) {
        doc.setFont("helvetica", "normal");
        doc.setFontSize(7);
        doc.setTextColor(...COR_MUTED_RGB);
        doc.text(item.detalhe, x, cursorY + 11.5);
      }
    });
    cursorY += 15;
    doc.setDrawColor(...COR_LINHA_RGB);
    doc.setLineWidth(0.3);
    doc.line(14, cursorY, pageWidth - 14, cursorY);
    cursorY += 7;
  }

  for (const secao of secoes) {
    if (!secao.linhas.length) continue;
    const jaTinhaSecao = alguma;
    alguma = true;
    if (cursorY > pageHeight - 40 || (secao.novaPagina && jaTinhaSecao)) {
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

    const columnStyles: Record<number, { cellWidth: number }> = {};
    secao.colunas.forEach((c, i) => { if (c.larguraPdf) columnStyles[i] = { cellWidth: c.larguraPdf }; });

    autoTable(doc, {
      ...ESTILO_TABELA,
      head: [colunasMaiusculas(secao.colunas).map((c) => c.header)],
      body: secao.linhas.map((linha) => secao.colunas.map((c) => formatarValor(linha[c.key]))),
      startY: cursorY,
      margin: { top: 32, left: 14, right: 14, bottom: margemInferior },
      columnStyles,
      rowPageBreak: "avoid",
      didDrawPage: cabecalho,
      didParseCell: secao.destacar
        ? (dados) => {
            if (dados.section === "body" && secao.destacar!(secao.linhas[dados.row.index])) dados.cell.styles.fillColor = FUNDO_DESTAQUE_RGB;
          }
        : undefined,
    });
    cursorY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 8;
  }

  if (!alguma) {
    cabecalho();
    doc.setFontSize(10);
    doc.setTextColor(...COR_MUTED_RGB);
    doc.text("Nenhum lançamento encontrado para este animal.", 14, 40);
  }

  if (alguma && opcoes?.legenda?.length) {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(7.5);
    doc.setTextColor(...COR_MUTED_RGB);
    const linhas = opcoes.legenda.flatMap((l) => doc.splitTextToSize(l, pageWidth - 28) as string[]);
    if (cursorY + linhas.length * 4 > pageHeight - margemInferior) {
      doc.addPage();
      cabecalho();
      cursorY = 32;
    }
    linhas.forEach((l, i) => doc.text(l, 14, cursorY - 2 + i * 4));
  }

  // Rodapé e "Página X de N" (só quando pedido) — depois de saber quantas páginas saíram.
  if (opcoes?.rodape !== undefined) {
    const total = doc.getNumberOfPages();
    for (let i = 1; i <= total; i++) {
      doc.setPage(i);
      doc.setDrawColor(...COR_LINHA_RGB);
      doc.setLineWidth(0.2);
      doc.line(14, pageHeight - 11, pageWidth - 14, pageHeight - 11);
      doc.setFont("helvetica", "normal");
      doc.setFontSize(7);
      doc.setTextColor(...COR_MUTED_RGB);
      doc.text(opcoes.rodape, 14, pageHeight - 7);
      doc.text(`Página ${i} de ${total}`, pageWidth - 14, pageHeight - 7, { align: "right" });
    }
  }

  return doc.output("blob");
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

// ───────────────────────────────────────────────────────────────────────────
// Relatórios do Financeiro (Fase B do redesenho) — exportação do molde único
// (RelatorioShell): cabeçalho do CLIENTE (nome da fazenda atual, período,
// comparação, regime e centro), NÚMEROS de verdade no Excel (célula numérica
// com formato, não texto) e linhas de total em negrito. O PDF usa o mesmo
// cabeçalho/estilo dos outros exports.
// ───────────────────────────────────────────────────────────────────────────

export type TipoColunaRelatorio = "texto" | "brl" | "brlL" | "pct" | "litros" | "num";
export type ColunaRelatorio = { header: string; tipo: TipoColunaRelatorio; width?: number };
/** `pct` vem em PONTOS percentuais (7,5 = 7,5%); o Excel recebe a fração. */
export type LinhaRelatorio = { valores: (string | number | null)[]; total?: boolean; nivel?: number;
  /** Formato desta linha quando difere do da coluna (ex.: uma linha de litros numa tabela em R$). */
  tipos?: (TipoColunaRelatorio | undefined)[] };
export type RelatorioParaExportar = {
  titulo: string;
  pergunta?: string;
  contexto: { periodo: string; comparacao?: string | null; regime: string; centro: string };
  colunas: ColunaRelatorio[];
  linhas: LinhaRelatorio[];
  notas?: string[];
  nomeArquivoBase: string;
  /** Rodapé automático das réguas de referência (parecer 7.5, texto devolvido por POST /relatorios/exportacoes):
   *  sai NO MESMO BLOCO da tabela que tem as réguas (última linha da tabela), sem opção de remover. */
  rodapeReguas?: string | null;
};

export function linhaDeContexto(c: RelatorioParaExportar["contexto"]): string {
  return [`Período: ${c.periodo}`, c.comparacao ? `comparado com ${c.comparacao}` : null, `Regime: ${c.regime}`, `Centro de custo: ${c.centro}`]
    .filter(Boolean).join(" · ");
}

const FORMATO_EXCEL: Record<TipoColunaRelatorio, string | undefined> = {
  texto: undefined,
  brl: '"R$" #,##0.00;-"R$" #,##0.00',
  brlL: '"R$" #,##0.0000;-"R$" #,##0.0000',
  pct: "0.0%;-0.0%",
  litros: '#,##0" L"',
  num: "#,##0.00",
};

function textoCelula(v: string | number | null, tipo: TipoColunaRelatorio): string {
  if (v == null || v === "") return "—";
  if (typeof v === "string") return v;
  const menos = v < 0 ? "−" : "";
  const abs = Math.abs(v);
  const n = (casas: number) => abs.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  if (tipo === "brl") return `${menos}R$ ${n(2)}`;
  if (tipo === "brlL") return `${menos}R$ ${n(4)}`;
  if (tipo === "pct") return `${menos}${n(1)}%`;
  if (tipo === "litros") return `${menos}${n(0)} L`;
  if (tipo === "num") return `${menos}${n(2)}`;
  return String(v);
}

export async function exportarRelatorioExcel(r: RelatorioParaExportar, modo: ModoEntregaExport = "baixar") {
  return comAlertaDeErro(async () => {
    const ExcelJS = (await import("exceljs")).default;
    const usuario = getUsuario();
    const wb = new ExcelJS.Workbook();
    wb.creator = usuario?.nome || "CowData";
    wb.created = new Date();
    const ws = wb.addWorksheet((r.titulo || "Relatório").replace(/[[\]*/\\?:]/g, "").slice(0, 31));
    const nCols = Math.max(r.colunas.length, 1);
    const cab = (linha: number, valor: string, font: Partial<import("exceljs").Font>) => {
      ws.mergeCells(linha, 1, linha, nCols);
      const c = ws.getCell(linha, 1);
      c.value = valor; c.font = font; c.alignment = { horizontal: "left", wrapText: true };
    };
    cab(1, nomeDaFazenda(), { bold: true, size: 14, color: { argb: `FF${COR_VINHO}` } });
    cab(2, r.pergunta ? `${r.titulo} — ${r.pergunta}` : r.titulo, { bold: true, size: 12 });
    cab(3, linhaDeContexto(r.contexto), { size: 10 });
    cab(4, `Gerado por ${usuario?.nome || "—"} em ${new Date().toLocaleDateString("pt-BR")}`, { italic: true, size: 9, color: { argb: "FF6B7280" } });
    ws.addRow([]);
    const head = ws.addRow(r.colunas.map((c) => c.header));
    head.eachCell((c, i) => {
      c.font = { bold: true, color: { argb: "FFFFFFFF" } };
      c.fill = { type: "pattern", pattern: "solid", fgColor: { argb: `FF${COR_VINHO}` } };
      c.alignment = { horizontal: r.colunas[i - 1]?.tipo === "texto" ? "left" : "right" };
    });
    ws.views = [{ state: "frozen", ySplit: head.number }];
    for (const linha of r.linhas) {
      const row = ws.addRow(r.colunas.map((col, i) => {
        const v = linha.valores[i];
        if (v == null || v === "") return null;
        if (typeof v === "number") return (linha.tipos?.[i] ?? col.tipo) === "pct" ? v / 100 : v;
        return v;
      }));
      r.colunas.forEach((col, i) => {
        const cell = row.getCell(i + 1);
        const fmt = FORMATO_EXCEL[linha.tipos?.[i] ?? col.tipo];
        if (fmt && typeof cell.value === "number") cell.numFmt = fmt;
        if (i === 0 && linha.nivel) cell.alignment = { indent: linha.nivel };
      });
      if (linha.total) {
        row.font = { bold: true };
        row.eachCell((c) => { c.border = { top: { style: "thin", color: { argb: "FF9CA3AF" } } }; });
      }
    }
    if (r.rodapeReguas) {
      // Mesmo bloco da régua: a linha logo abaixo da tabela, mesclada e com borda (não é nota solta).
      const row = ws.addRow([r.rodapeReguas]);
      ws.mergeCells(row.number, 1, row.number, nCols);
      const c = row.getCell(1);
      c.font = { size: 9, italic: true };
      c.alignment = { wrapText: true, vertical: "top" };
      c.border = { top: { style: "thin" }, bottom: { style: "thin" }, left: { style: "thin" }, right: { style: "thin" } };
      row.height = Math.min(120, 15 * Math.ceil(r.rodapeReguas.length / 110));
    }
    if (r.notas?.length) {
      ws.addRow([]);
      for (const n of r.notas) {
        const row = ws.addRow([n]);
        ws.mergeCells(row.number, 1, row.number, nCols);
        row.getCell(1).font = { size: 9, color: { argb: "FF6B7280" } };
        row.getCell(1).alignment = { wrapText: true };
      }
    }
    r.colunas.forEach((c, i) => { ws.getColumn(i + 1).width = c.width || (c.tipo === "texto" ? 38 : 16); });
    const buf = await wb.xlsx.writeBuffer();
    const blob = new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    await entregarArquivo(blob, `${r.nomeArquivoBase}_${dataHoje()}.xlsx`, modo);
  });
}

// A fonte padrão do jsPDF (Helvetica, WinAnsi) não tem "−", "Δ", "›" e "…": troca pelos equivalentes que ela tem.
const paraPdf = (t: string) => t.replace(/Δ%/g, "Var. %").replace(/Δ/g, "Var.").replace(/[−–]/g, "-").replace(/›/g, ">").replace(/…/g, "...");

export async function exportarRelatorioPDF(r0: RelatorioParaExportar, modo: ModoEntregaExport = "baixar") {
  const r: RelatorioParaExportar = {
    ...r0, titulo: paraPdf(r0.titulo),
    contexto: { ...r0.contexto, periodo: paraPdf(r0.contexto.periodo), comparacao: r0.contexto.comparacao ? paraPdf(r0.contexto.comparacao) : r0.contexto.comparacao },
    colunas: r0.colunas.map((c) => ({ ...c, header: paraPdf(c.header) })),
    linhas: r0.linhas.map((l) => ({ ...l, valores: l.valores.map((v) => (typeof v === "string" ? paraPdf(v) : v)) })),
    notas: r0.notas?.map(paraPdf),
    rodapeReguas: r0.rodapeReguas ? paraPdf(r0.rodapeReguas) : r0.rodapeReguas,
  };
  return comAlertaDeErro(async () => {
    const { default: jsPDF } = await import("jspdf");
    const { default: autoTable } = await import("jspdf-autotable");
    const usuario = getUsuario();
    const logo = await carregarLogo();
    const doc = new jsPDF({ orientation: r.colunas.length > 6 ? "landscape" : "portrait" });
    const dataStr = new Date().toLocaleDateString("pt-BR");
    const cabecalho = () => desenharCabecalhoPDF(doc, {
      titulo: r.titulo, subtitulo: linhaDeContexto(r.contexto), usuario: usuario?.nome, dataStr, logo, fazenda: nomeDaFazenda(),
    });
    const totais = new Set(r.linhas.map((l, i) => (l.total ? i : -1)).filter((i) => i >= 0));
    autoTable(doc, {
      ...ESTILO_TABELA,
      head: [r.colunas.map((c) => c.header.toUpperCase())],
      body: r.linhas.map((l) => r.colunas.map((c, i) => {
        const t = paraPdf(textoCelula(l.valores[i], l.tipos?.[i] ?? c.tipo));
        return i === 0 && l.nivel ? `${"   ".repeat(l.nivel)}${t}` : t;
      })),
      columnStyles: Object.fromEntries(r.colunas.map((c, i) => [i, { halign: c.tipo === "texto" ? "left" : "right" }])),
      // Rodapé das réguas (parecer 7.5): última linha da PRÓPRIA tabela, ocupando todas as colunas.
      ...(r.rodapeReguas ? {
        foot: [[{ content: r.rodapeReguas, colSpan: r.colunas.length, styles: { fontStyle: "italic" as const, fontSize: 7.5, halign: "left" as const, fillColor: [255, 255, 255] as [number, number, number], textColor: [40, 40, 40] as [number, number, number], lineWidth: 0.2 } }]],
        showFoot: "lastPage" as const,
      } : {}),
      startY: 31,
      margin: { top: 31 },
      didParseCell: (d) => {
        if (d.section === "head") d.cell.styles.halign = r.colunas[d.column.index]?.tipo === "texto" ? "left" : "right";
        if (d.section === "body" && totais.has(d.row.index)) d.cell.styles.fontStyle = "bold";
      },
      didDrawPage: cabecalho,
    });
    if (r.notas?.length) {
      let y = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 8;
      doc.setFont("helvetica", "normal");
      doc.setFontSize(7.5);
      doc.setTextColor(...COR_MUTED_RGB);
      const largura = doc.internal.pageSize.getWidth() - 28;
      for (const n of r.notas) {
        const partes = doc.splitTextToSize(n, largura) as string[];
        if (y + partes.length * 3.6 > doc.internal.pageSize.getHeight() - 12) { doc.addPage(); cabecalho(); y = 34; }
        doc.text(partes, 14, y);
        y += partes.length * 3.6 + 1.5;
      }
    }
    await entregarArquivo(doc.output("blob"), `${r.nomeArquivoBase}_${dataHoje()}.pdf`, modo);
  });
}
