// Folha de campo de um protocolo — a grade animal × dia impressa para o
// funcionário levar ao curral e ir anotando à caneta, e a mesma grade em
// Excel para quem prefere digitar a conferência de volta.
//
// Desenho vindo da proposta aprovada:
//  - uma LINHA por animal e uma COLUNA por dia, porque é assim que o trabalho
//    acontece no tronco: passa o lote, marca a coluna do dia;
//  - junto do X, a DATA da aplicação — é ela que permite dar baixa depois com
//    a data real em vez de "hoje";
//  - os medicamentos ficam num quadro à parte, não repetidos linha a linha:
//    a dose é a mesma para o lote inteiro, e repetir só roubaria espaço da
//    coluna de observações, que é onde o funcionário escreve o que importa
//    (vaca que não veio, cio observado, frasco trocado).
//
// A grade se ADAPTA ao formato do protocolo: cronograma longo com lote pequeno
// (indução: 12-19 dias, 1-2 vacas) sai transposto, uma linha por dia. Ver
// `secoes()` no fim do arquivo.
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

/** dd/mm — nas células da grade, onde a largura é disputada. */
function dataCurta(iso: string | null | undefined): string {
  if (!iso) return "";
  const [, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}`;
}

/** O que se escreve na célula (animal × dia) da grade. */
function celula(realizada: boolean, dataRealizacao: string | null | undefined): string {
  if (!realizada) return CAIXA;
  const quando = dataCurta(dataRealizacao);
  return quando ? `X ${quando}` : "X";
}

/** Grade com uma linha por DIA e uma coluna por animal.
 *
 *  É o desenho certo quando o cronograma é longo e o lote é pequeno — a
 *  indução de lactação típica tem 12 a 19 dias para 1 ou 2 vacas. No desenho
 *  transposto (uma coluna por dia) isso virava 26 colunas numa folha A4
 *  retrato: os cabeçalhos quebravam letra a letra ("D/A/T/A" empilhado) e a
 *  folha ficava ilegível.
 *
 *  Aqui o "o que aplicar" entra na própria linha do dia, então a folha inteira
 *  cabe numa tabela só: o funcionário lê a linha do dia, vê o que aplicar e
 *  marca na coluna da vaca. */
function secoesPorDia(det: DetalheCentralProtocolo): SecaoFicha[] {
  const colunas: ColunaExport[] = [
    { header: "Dia", key: "dia", width: 8 },
    { header: "Data prevista", key: "data", width: 15 },
    { header: "O que aplicar", key: "aplicacao", width: 52 },
  ];
  det.animais.forEach((a) => {
    colunas.push({ header: a.numero_matriz, key: `an_${a.numero_matriz}`, width: 13 });
  });
  colunas.push({ header: "Observações", key: "obs", width: 30 });

  const linhas = det.dias.map((d) => {
    const linha: Record<string, unknown> = {
      dia: d.rotulo,
      data: dataBR(d.data_prevista),
      aplicacao: d.descricao || "—",
      obs: "",
    };
    det.animais.forEach((a) => {
      const c = a.celulas.find((x) => x.dia === d.dia);
      linha[`an_${a.numero_matriz}`] = c ? celula(c.realizada, c.data_realizacao) : "—";
    });
    return linha;
  });

  return [{ titulo: "Cronograma e aplicação", colunas, linhas }];
}

/** Grade com uma linha por ANIMAL e uma coluna por dia — o desenho original,
 *  certo quando o lote é grande e o cronograma curto (IATF: 4 dias, 20+ vacas).
 *  A data de cada aplicação vai junto do X na própria célula, em vez de numa
 *  segunda coluna por dia: duas colunas por dia dobravam a largura e é o que
 *  estourava a folha assim que o cronograma passava de meia dúzia de dias. */
function secoesPorAnimal(det: DetalheCentralProtocolo): SecaoFicha[] {
  const colunas: ColunaExport[] = [{ header: "Animal", key: "animal", width: 14 }];
  det.dias.forEach((d) => {
    colunas.push({ header: d.rotulo, key: `ok_${d.dia}`, width: 13 });
  });
  colunas.push({ header: "Observações", key: "obs", width: 26 });

  const linhas = det.animais.map((a) => {
    const linha: Record<string, unknown> = { animal: a.numero_matriz, obs: "" };
    a.celulas.forEach((c) => {
      // Etapa já aplicada sai preenchida: a folha serve tanto para levar a
      // campo quanto para conferir o que já foi feito.
      linha[`ok_${c.dia}`] = celula(c.realizada, c.data_realizacao);
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

function secoes(det: DetalheCentralProtocolo): SecaoFicha[] {
  // Escolhe o layout que produz a folha mais ESTREITA. O que estoura o A4
  // retrato é a quantidade de COLUNAS; linha não é problema, a tabela pagina
  // sozinha. Então o lado menor (dias ou animais) é que vira coluna:
  //   por animal → 1 (animal) + nDias + 1 (observações)
  //   por dia    → 3 (dia, data, o que aplicar) + nAnimais + 1 (observações)
  // Empate cai no desenho por animal, que é o mais familiar no curral.
  const colunasPorAnimal = det.dias.length + 2;
  const colunasPorDia = det.animais.length + 4;
  return colunasPorDia < colunasPorAnimal ? secoesPorDia(det) : secoesPorAnimal(det);
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
