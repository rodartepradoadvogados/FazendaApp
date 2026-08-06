// Folha de campo de um protocolo — a grade animal × dia impressa para o
// funcionário levar ao curral e ir anotando à caneta, e a mesma grade em
// Excel para quem prefere digitar a conferência de volta.
//
// Desenho vindo da proposta aprovada:
//  - uma LINHA por animal e uma COLUNA por dia, porque é assim que o trabalho
//    acontece no tronco: passa o lote, marca a coluna do dia;
//  - ao lado de cada dia, um campo de DATA — é ele que permite dar baixa
//    depois com a data real da aplicação em vez de "hoje";
//  - os medicamentos ficam num quadro à parte, não repetidos linha a linha:
//    a dose é a mesma para o lote inteiro, e repetir só roubaria espaço da
//    coluna de observações, que é onde o funcionário escreve o que importa
//    (vaca que não veio, cio observado, frasco trocado).
import { exportarFichaPDF, exportarMultiExcel, type ColunaExport, type SecaoFicha } from "@/lib/export";
import type { DetalheCentralProtocolo } from "@/lib/api";

/** `( )` em vez de um quadradinho unicode: a fonte padrão do jsPDF (Helvetica)
 *  não tem o glifo ☐ e ele sairia como caractere quebrado no PDF. */
const CAIXA = "( )";

function dataBR(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}

function secoes(det: DetalheCentralProtocolo): SecaoFicha[] {
  const colunas: ColunaExport[] = [{ header: "Animal", key: "animal", width: 12 }];
  det.dias.forEach((d) => {
    colunas.push({ header: `${d.rotulo} ✓`, key: `ok_${d.dia}`, width: 7 });
    colunas.push({ header: `${d.rotulo} data`, key: `data_${d.dia}`, width: 12 });
  });
  colunas.push({ header: "Observações", key: "obs", width: 26 });

  const linhas = det.animais.map((a) => {
    const linha: Record<string, unknown> = { animal: a.numero_matriz, obs: "" };
    a.celulas.forEach((c) => {
      // Etapa já aplicada sai preenchida: a folha serve tanto para levar a
      // campo quanto para conferir o que já foi feito.
      linha[`ok_${c.dia}`] = c.realizada ? "X" : CAIXA;
      linha[`data_${c.dia}`] = c.realizada ? dataBR(c.data_realizacao) : "";
    });
    return linha;
  });

  const aplicacoes = det.dias.map((d) => ({
    dia: d.rotulo,
    data: dataBR(d.data_prevista),
    aplicacao: d.descricao || "—",
    situacao: `${d.realizadas} de ${d.total}`,
  }));

  return [
    { titulo: "Aplicação por animal", colunas, linhas },
    {
      titulo: "O que aplicar em cada dia",
      colunas: [
        { header: "Dia", key: "dia", width: 8 },
        { header: "Data prevista", key: "data", width: 14 },
        { header: "Aplicação", key: "aplicacao", width: 40 },
        { header: "Já aplicado", key: "situacao", width: 12 },
      ],
      linhas: aplicacoes,
    },
  ];
}

function subtitulo(det: DetalheCentralProtocolo): string {
  const partes = [
    `Início ${dataBR(det.data_inicio)}`,
    `${det.animais.length} animal(is)`,
    `${det.etapas_realizadas} de ${det.etapas_total} etapas`,
  ];
  if (det.responsavel) partes.push(`Responsável: ${det.responsavel}`);
  return partes.join(" · ");
}

function nomeArquivo(det: DetalheCentralProtocolo): string {
  const base = (det.nome || "protocolo").toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return `folha_campo_${base}`.slice(0, 80);
}

export async function exportarFolhaCampoPDF(det: DetalheCentralProtocolo) {
  return exportarFichaPDF(det.nome, subtitulo(det), secoes(det), nomeArquivo(det));
}

export async function exportarFolhaCampoExcel(det: DetalheCentralProtocolo) {
  return exportarMultiExcel(det.nome, secoes(det), nomeArquivo(det));
}
