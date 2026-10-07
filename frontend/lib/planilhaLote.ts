// Importação de planilha (Excel/CSV) para o Lançamento em lote: lê as linhas, agrupa em notas e valida.
// Módulo puro (sem React) para poder ser testado com `node --test`.

export const COLUNAS_PLANILHA = [
  "Tipo de documento", "Número", "Data", "Tipo do item", "Produto ou serviço", "Conta gerencial",
  "Quantidade", "Valor unitário", "Desconto da nota", "Acréscimo da nota",
] as const;

export type ItemImportado = { tipoItem: "produto" | "servico"; produto: string; codigo: string; nome: string; qtd: string; unit: number };
export type NotaImportada = {
  tipoDoc: string; numero: string; semNumero: boolean; data: string; desconto: number; acrescimo: number;
  itens: ItemImportado[]; linhas: number[];
};
export type ResultadoImportacao = { notas: NotaImportada[]; erros: string[]; avisos: string[] };
export type ContaRef = { codigo: string; nome: string; ativa?: boolean };

const semAcento = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();

// Cabeçalhos aceitos (sem acento, minúsculos) → chave interna.
const ALIAS: Record<string, string> = {
  "tipo de documento": "tipoDoc", "tipo documento": "tipoDoc", "tipo doc": "tipoDoc", "documento": "tipoDoc",
  "numero": "numero", "numero do documento": "numero", "n": "numero", "nº": "numero", "nota": "numero", "numero da nota": "numero",
  "data": "data", "data emissao": "data", "emissao": "data", "data da nota": "data",
  "tipo do item": "tipoItem", "tipo item": "tipoItem", "tipo": "tipoItem",
  "produto ou servico": "produto", "produto/servico": "produto", "produto": "produto", "servico": "produto", "descricao": "produto", "item": "produto",
  "conta gerencial": "conta", "conta": "conta",
  "quantidade": "qtd", "qtd": "qtd", "qtde": "qtd",
  "valor unitario": "unit", "vl unitario": "unit", "valor unit": "unit", "preco unitario": "unit", "unitario": "unit",
  "desconto da nota": "desconto", "desconto": "desconto",
  "acrescimo da nota": "acrescimo", "acrescimo": "acrescimo",
};

export function paraNumero(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  let s = String(v).replace(/[R$\s]/g, "");
  if (!s) return null;
  const temVirg = s.includes(","), temPonto = s.includes(".");
  if (temVirg && temPonto) s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  else if (temVirg) s = s.replace(",", ".");
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function paraDataISO(v: unknown): string | null {
  if (v === null || v === undefined || v === "") return null;
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? null : v.toISOString().slice(0, 10);
  if (typeof v === "number") { // serial do Excel (dias desde 1899-12-30)
    if (v < 20000 || v > 80000) return null;
    return new Date(Math.round((v - 25569) * 86400000)).toISOString().slice(0, 10);
  }
  const s = String(v).trim();
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return valida(+m[1], +m[2], +m[3]);
  m = s.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2,4})$/);
  if (m) return valida(m[3].length === 2 ? 2000 + +m[3] : +m[3], +m[2], +m[1]);
  return null;
}
function valida(a: number, m: number, d: number): string | null {
  const dt = new Date(Date.UTC(a, m - 1, d));
  if (dt.getUTCFullYear() !== a || dt.getUTCMonth() !== m - 1 || dt.getUTCDate() !== d) return null;
  return `${a}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

/** CSV simples (vírgula ou ponto e vírgula, aspas duplas). */
export function lerCsv(texto: string): string[][] {
  const t = texto.replace(/^﻿/, "");
  const primeira = t.split(/\r?\n/, 1)[0] || "";
  const sep = (primeira.match(/;/g) || []).length > (primeira.match(/,/g) || []).length ? ";" : (primeira.includes("\t") ? "\t" : ",");
  const linhas: string[][] = []; let atual: string[] = []; let campo = ""; let aspas = false;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (aspas) { if (c === '"') { if (t[i + 1] === '"') { campo += '"'; i++; } else aspas = false; } else campo += c; }
    else if (c === '"') aspas = true;
    else if (c === sep) { atual.push(campo); campo = ""; }
    else if (c === "\n" || c === "\r") { if (c === "\r" && t[i + 1] === "\n") i++; atual.push(campo); linhas.push(atual); atual = []; campo = ""; }
    else campo += c;
  }
  if (campo !== "" || atual.length) { atual.push(campo); linhas.push(atual); }
  return linhas.filter((l) => l.some((c) => String(c).trim() !== ""));
}

/** Converte a matriz (1ª linha = cabeçalho) em notas, conferindo contas e produtos contra os cadastros. */
export function interpretarLinhas(
  matriz: unknown[][], contas: ContaRef[], produtosEstoque: string[], tiposDocPadrao = "Nota fiscal",
): ResultadoImportacao {
  const erros: string[] = [], avisos: string[] = [];
  if (!matriz.length) return { notas: [], erros: ["A planilha está vazia."], avisos };
  const cab = matriz[0].map((c) => ALIAS[semAcento(String(c ?? ""))] || "");
  const falta = ["numero", "data", "produto", "unit"].filter((k) => !cab.includes(k));
  if (falta.length) {
    const nomes: Record<string, string> = { numero: "Número", data: "Data", produto: "Produto ou serviço", unit: "Valor unitário" };
    return { notas: [], erros: [`Faltam colunas na planilha: ${falta.map((k) => nomes[k]).join(", ")}. Baixe o modelo para ver o formato.`], avisos };
  }
  const col = (linha: unknown[], k: string) => { const i = cab.indexOf(k); return i < 0 ? undefined : linha[i]; };
  const contasAtivas = contas.filter((c) => c.ativa !== false);
  const porCodigo = new Map(contasAtivas.map((c) => [semAcento(c.codigo), c]));
  const porNome = new Map<string, ContaRef[]>();
  for (const c of contasAtivas) { const k = semAcento(c.nome); porNome.set(k, [...(porNome.get(k) || []), c]); }
  const estoque = new Map(produtosEstoque.map((p) => [semAcento(p), p]));

  const notas: NotaImportada[] = [];
  let chaveAtual = ""; let atual: NotaImportada | null = null;
  const comErroDeLinha = new Set<NotaImportada>();
  for (let r = 1; r < matriz.length; r++) {
    const linha = matriz[r]; const nl = r + 1;
    if (!linha.some((c) => String(c ?? "").trim() !== "")) continue;
    const txt = (k: string) => String(col(linha, k) ?? "").trim();
    const numero = txt("numero");
    const dataIso = paraDataISO(col(linha, "data"));
    if (!dataIso) { erros.push(`Linha ${nl}: data inválida ("${txt("data")}"). Use dd/mm/aaaa.`); continue; }
    const tipoDoc = txt("tipoDoc") || tiposDocPadrao;
    const chave = `${semAcento(tipoDoc)}|${semAcento(numero)}|${dataIso}`;
    if (!atual || chave !== chaveAtual) {
      if (numero && notas.some((n) => n.numero && semAcento(n.numero) === semAcento(numero) && semAcento(n.tipoDoc) === semAcento(tipoDoc)))
        erros.push(`Linha ${nl}: a nota ${numero} aparece em dois blocos separados. Junte as linhas dela.`);
      atual = { tipoDoc, numero, semNumero: !numero, data: dataIso, desconto: 0, acrescimo: 0, itens: [], linhas: [] };
      notas.push(atual); chaveAtual = chave;
    }
    atual.linhas.push(nl);
    const desc = paraNumero(col(linha, "desconto")), acr = paraNumero(col(linha, "acrescimo"));
    if (desc) atual.desconto = desc;
    if (acr) atual.acrescimo = acr;

    const produto = txt("produto");
    if (!produto) { erros.push(`Linha ${nl}: informe o produto ou serviço.`); comErroDeLinha.add(atual); continue; }
    const unit = paraNumero(col(linha, "unit"));
    if (unit === null || unit <= 0) { erros.push(`Linha ${nl}: valor unitário inválido.`); comErroDeLinha.add(atual); continue; }
    const tipoTxt = semAcento(txt("tipoItem"));
    const noEstoque = estoque.get(semAcento(produto));
    let tipoItem: "produto" | "servico" = tipoTxt.startsWith("serv") ? "servico" : tipoTxt.startsWith("prod") ? "produto" : (noEstoque ? "produto" : "servico");
    if (tipoItem === "produto" && !noEstoque) avisos.push(`Linha ${nl}: "${produto}" não está no estoque; escolha o produto na tela.`);
    const qtdN = paraNumero(col(linha, "qtd"));
    if (tipoItem === "produto" && !(qtdN && qtdN > 0)) { erros.push(`Linha ${nl}: informe a quantidade do produto.`); comErroDeLinha.add(atual); continue; }
    let codigo = "", nome = "";
    const contaTxt = txt("conta");
    if (contaTxt) {
      const achada = porCodigo.get(semAcento(contaTxt)) || (porNome.get(semAcento(contaTxt)) || [])[0]
        || contasAtivas.find((c) => semAcento(`${c.codigo} ${c.nome}`) === semAcento(contaTxt));
      if (achada) { codigo = achada.codigo; nome = achada.nome; }
      else avisos.push(`Linha ${nl}: conta gerencial "${contaTxt}" não encontrada; escolha na tela.`);
      if ((porNome.get(semAcento(contaTxt)) || []).length > 1 && !porCodigo.has(semAcento(contaTxt))) avisos.push(`Linha ${nl}: há mais de uma conta chamada "${contaTxt}"; usei a primeira. Use o código para ser exato.`);
    }
    atual.itens.push({ tipoItem, produto: noEstoque && tipoItem === "produto" ? noEstoque : produto, codigo, nome, qtd: tipoItem === "servico" ? String(qtdN && qtdN > 0 ? qtdN : 1).replace(".", ",") : String(qtdN).replace(".", ","), unit });
  }
  for (const n of notas) {
    if (comErroDeLinha.has(n)) continue;
    if (!n.itens.length) erros.push(`Nota ${n.numero || "(sem número)"}: nenhum item válido.`);
    else {
      const liquido = n.itens.reduce((s, i) => s + (Number(i.qtd.replace(",", ".")) || 0) * i.unit, 0) - n.desconto + n.acrescimo;
      if (liquido <= 0) erros.push(`Nota ${n.numero || "(sem número)"}: o valor líquido deve ser positivo.`);
    }
  }
  if (!notas.length && !erros.length) erros.push("Nenhuma linha de nota encontrada na planilha.");
  return { notas, erros, avisos };
}

/** Lê .xlsx (1ª aba) ou .csv e devolve a matriz de células. */
export async function lerArquivoPlanilha(arquivo: File): Promise<unknown[][]> {
  const nome = arquivo.name.toLowerCase();
  if (nome.endsWith(".csv") || nome.endsWith(".txt")) return lerCsv(await arquivo.text());
  if (!nome.endsWith(".xlsx")) throw new Error("Use um arquivo .xlsx ou .csv.");
  const ExcelJS = (await import("exceljs")).default;
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.load(await arquivo.arrayBuffer());
  const ws = wb.worksheets[0];
  if (!ws) throw new Error("A planilha não tem nenhuma aba.");
  const out: unknown[][] = [];
  ws.eachRow({ includeEmpty: false }, (row) => {
    const cels: unknown[] = [];
    for (let c = 1; c <= row.cellCount; c++) {
      const v: any = row.getCell(c).value;
      cels.push(v && typeof v === "object" && !(v instanceof Date) ? (v.result ?? v.text ?? (Array.isArray(v.richText) ? v.richText.map((t: any) => t.text).join("") : "")) : v);
    }
    out.push(cels);
  });
  return out;
}

/** Baixa o modelo (.xlsx) com cabeçalhos e duas notas de exemplo. */
export async function baixarModeloPlanilha(): Promise<void> {
  const ExcelJS = (await import("exceljs")).default;
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet("Notas");
  ws.addRow([...COLUNAS_PLANILHA]);
  ws.addRow(["Nota fiscal", "48213", "03/10/2026", "serviço", "Lavagem completa", "", 2, 60, 0, 0]);
  ws.addRow(["Nota fiscal", "48390", "05/10/2026", "produto", "Óleo diesel S10", "", 40, 5.89, 0, 0]);
  ws.addRow(["Nota fiscal", "48390", "05/10/2026", "serviço", "Troca de filtro", "", 1, 80, 10, 0]);
  ws.getRow(1).font = { bold: true };
  ws.columns.forEach((c, i) => { c.width = [18, 12, 12, 14, 30, 24, 12, 14, 16, 16][i]; });
  const ajuda = wb.addWorksheet("Como preencher");
  [["Uma linha por item. Linhas da mesma nota (mesmo tipo, número e data) ficam juntas."],
   ["Tipo do item: produto ou serviço. Em branco: vira produto se existir no estoque, senão serviço."],
   ["Conta gerencial: código (ex.: 3.01.02.01) ou nome exato; em branco você escolhe na tela."],
   ["Desconto e acréscimo da nota: preencha em qualquer linha da nota."],
   ["Datas em dd/mm/aaaa. Valores com vírgula ou ponto decimal."]].forEach((l) => ajuda.addRow(l));
  ajuda.getColumn(1).width = 110;
  const buf = await wb.xlsx.writeBuffer();
  const url = URL.createObjectURL(new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
  const a = document.createElement("a"); a.href = url; a.download = "modelo-lancamento-em-lote.xlsx"; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
