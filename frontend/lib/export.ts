// Exportação de relatórios/listas em Excel (.xlsx) e PDF — cabeçalho padronizado
// com nome da fazenda, título do relatório, usuário logado e data de geração.
import { getUsuario } from "./api";

const NOME_FAZENDA = "Fazenda Estreito Ponte de Pedra";
const COR_VINHO = "5E1A2E";
const COR_VINHO_RGB: [number, number, number] = [94, 26, 46];
const COR_DOURADO_RGB: [number, number, number] = [184, 134, 11];

export type ColunaExport = { header: string; key: string; width?: number };

function formatarValor(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  return String(v);
}

function dataHoje(): string {
  return new Date().toISOString().slice(0, 10);
}

function baixarBlob(blob: Blob, nomeArquivo: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function exportarExcel(
  titulo: string,
  colunas: ColunaExport[],
  linhas: Record<string, unknown>[],
  nomeArquivoBase: string,
) {
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
  baixarBlob(blob, `${nomeArquivoBase}_${dataHoje()}.xlsx`);
}

export async function exportarPDF(
  titulo: string,
  colunas: ColunaExport[],
  linhas: Record<string, unknown>[],
  nomeArquivoBase: string,
) {
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const usuario = getUsuario();
  const doc = new jsPDF({ orientation: colunas.length > 6 ? "landscape" : "portrait" });
  const dataStr = new Date().toLocaleDateString("pt-BR");
  const pageWidth = doc.internal.pageSize.getWidth();

  const desenharCabecalho = () => {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(14);
    doc.setTextColor(...COR_VINHO_RGB);
    doc.text(NOME_FAZENDA.toUpperCase(), pageWidth / 2, 12, { align: "center" });
    doc.setFontSize(11);
    doc.setTextColor(30, 30, 30);
    doc.text(titulo, pageWidth / 2, 19, { align: "center" });
    doc.setFont("helvetica", "italic");
    doc.setFontSize(8);
    doc.setTextColor(120, 120, 120);
    doc.text(`Gerado por ${usuario?.nome || "—"} em ${dataStr}`, pageWidth / 2, 24, { align: "center" });
    doc.setDrawColor(...COR_DOURADO_RGB);
    doc.setLineWidth(0.5);
    doc.line(14, 26.5, pageWidth - 14, 26.5);
  };

  autoTable(doc, {
    head: [colunas.map((c) => c.header)],
    body: linhas.map((linha) => colunas.map((c) => formatarValor(linha[c.key]))),
    startY: 30,
    margin: { top: 30 },
    styles: { fontSize: 8, cellPadding: 2 },
    headStyles: { fillColor: COR_VINHO_RGB, textColor: 255 },
    alternateRowStyles: { fillColor: [245, 240, 235] },
    didDrawPage: desenharCabecalho,
  });

  doc.save(`${nomeArquivoBase}_${dataHoje()}.pdf`);
}

export type SecaoFicha = { titulo: string; colunas: ColunaExport[]; linhas: Record<string, unknown>[] };

/**
 * PDF com várias seções (uma tabela por tipo de lançamento) — usado na ficha
 * única do animal. Pode gerar quantas páginas forem necessárias: cada seção
 * só entra se tiver alguma linha, e o cabeçalho da fazenda é redesenhado em
 * toda página nova (seja por quebra automática de uma tabela grande, seja
 * por falta de espaço para o título da próxima seção).
 */
export async function exportarFichaPDF(
  titulo: string,
  subtitulo: string,
  secoes: SecaoFicha[],
  nomeArquivoBase: string,
) {
  const { default: jsPDF } = await import("jspdf");
  const { default: autoTable } = await import("jspdf-autotable");
  const usuario = getUsuario();
  const doc = new jsPDF({ orientation: "portrait" });
  const dataStr = new Date().toLocaleDateString("pt-BR");
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();

  const desenharCabecalho = () => {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(14);
    doc.setTextColor(...COR_VINHO_RGB);
    doc.text(NOME_FAZENDA.toUpperCase(), pageWidth / 2, 12, { align: "center" });
    doc.setFontSize(11);
    doc.setTextColor(30, 30, 30);
    doc.text(titulo, pageWidth / 2, 19, { align: "center" });
    doc.setFontSize(9);
    doc.setTextColor(80, 80, 80);
    doc.text(subtitulo, pageWidth / 2, 24, { align: "center" });
    doc.setFont("helvetica", "italic");
    doc.setFontSize(8);
    doc.setTextColor(120, 120, 120);
    doc.text(`Gerado por ${usuario?.nome || "—"} em ${dataStr}`, pageWidth / 2, 29, { align: "center" });
    doc.setDrawColor(...COR_DOURADO_RGB);
    doc.setLineWidth(0.5);
    doc.line(14, 31.5, pageWidth - 14, 31.5);
  };

  let cursorY = 35;
  let alguma = false;
  for (const secao of secoes) {
    if (!secao.linhas.length) continue;
    alguma = true;
    if (cursorY > pageHeight - 40) {
      doc.addPage();
      desenharCabecalho();
      cursorY = 35;
    }
    doc.setFont("helvetica", "bold");
    doc.setFontSize(10.5);
    doc.setTextColor(...COR_VINHO_RGB);
    doc.text(secao.titulo, 14, cursorY);
    cursorY += 4;

    autoTable(doc, {
      head: [secao.colunas.map((c) => c.header)],
      body: secao.linhas.map((linha) => secao.colunas.map((c) => formatarValor(linha[c.key]))),
      startY: cursorY,
      margin: { top: 35 },
      styles: { fontSize: 7.5, cellPadding: 1.5 },
      headStyles: { fillColor: COR_VINHO_RGB, textColor: 255, fontSize: 7.5 },
      alternateRowStyles: { fillColor: [245, 240, 235] },
      didDrawPage: desenharCabecalho,
    });
    cursorY = (doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable.finalY + 8;
  }

  if (!alguma) {
    desenharCabecalho();
    doc.setFontSize(10);
    doc.setTextColor(120, 120, 120);
    doc.text("Nenhum lançamento encontrado para este animal.", 14, 40);
  }

  doc.save(`${nomeArquivoBase}_${dataHoje()}.pdf`);
}
