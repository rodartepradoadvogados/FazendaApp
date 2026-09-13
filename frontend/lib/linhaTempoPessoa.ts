// A linha do tempo de UMA pessoa na folha — sem nenhum import de runtime (só
// tipos, que o compilador apaga), no mesmo molde de lib/holeriteRegras.ts e
// lib/folhaCompetencia.ts. Ver lib/linhaTempoPessoa.test.ts.
//
// POR QUE ELA EXISTE. A folha de um mês responde "quanto sai agora". Nenhuma
// tela respondia "de onde veio isto" quando o desconto de um mês nasceu de um
// vale tirado sete meses antes: a parcela 3/13 aparecia no recibo de setembro
// e o vale de março não tinha onde ser visto ao lado dela. Aqui a folha de
// setembro é UM evento entre o vale de março e as parcelas que ele foi
// gerando — e clicar no vale acende todas as competências em que ele é
// descontado, que é a pergunta que a tela de mês, por definição, não alcança.
//
// Tudo abaixo é montado com o que o navegador JÁ TEM carregado: o ledger
// unificado (`GET /cadastro/folha-pagamento-unificada`) e a lista de vales
// (`GET /cadastro/vales`, que devolve `parcelas_detalhe` e `origem_lancamento`
// completos). Nenhum campo novo de backend é necessário — e o que ligou o
// evento à parcela foi o `vale_id` passar a viajar junto de cada linha do
// holerite, sem o qual "qual vale gerou esta parcela" continuaria sendo um
// palpite entre vales de mesmo valor no mesmo mês.
import type { LinhaFolhaUnificada } from "./api";

/**
 * Formatador de dinheiro injetado por quem chama — é sempre o `formatBRL` de
 * lib/api.ts. Vem por parâmetro, e não por import, porque este módulo precisa
 * continuar sem import de runtime nenhum para rodar no runner do Node; e vem
 * de fora, e não reescrito aqui, porque um segundo formatador de reais no
 * projeto é um jeito garantido de duas telas escreverem o mesmo valor
 * diferente.
 */
export type FormatadorBRL = (valor: number) => string;

/** O recorte de `GET /cadastro/vales` que a linha do tempo usa. */
export type ValeDaLinhaTempo = {
  id: number;
  pessoa_id: number;
  valor_total: number;
  data_pagamento: string | null;
  forma_pagamento: string;
  observacao: string | null;
  numero_lancamento_gerado: string | null;
  /** `assumida_pela_fazenda` e `motivo_assuncao` JÁ vinham no `model_dump()`
   *  de cada parcela em `GET /cadastro/vales` — o que faltava era a linha do
   *  tempo olhar para eles: sem esse terceiro estado, a parcela que a fazenda
   *  assumiu caía no ramo de `aplicada` e era escrita como "descontada na
   *  folha de ago/2026", que é o oposto do que aconteceu. */
  parcelas_detalhe?: {
    id: number; competencia: string; valor: number; aplicada: boolean;
    assumida_pela_fazenda?: boolean; motivo_assuncao?: string | null;
  }[];
  origem_lancamento?: { numero_documento: string | null; produto: string | null; fornecedor_cliente: string | null } | null;
};

export type TomEvento = "pago" | "aberto" | "vencido" | "estourada" | "vale" | "parcela" | "assumida";

export type EventoPessoa = {
  id: string;
  /** Quem acende junto ao clicar — `vale-12` liga o vale às suas parcelas. */
  grupo: string | null;
  /** ISO (AAAA-MM-DD) ou "" quando o registro não tem data nenhuma. */
  data: string;
  titulo: string;
  sub: string;
  selo: string;
  tom: TomEvento;
  valor: number;
  /** `recebe` entra para a pessoa; `desconta` sai da folha dela; `tira` é o
   *  vale em si (dinheiro que ela já pegou e vai devolver em parcelas);
   *  `assumida` é a parcela que a FAZENDA pagou no lugar dela — não saiu do
   *  salário de ninguém, então não pode ser escrita com o menos vermelho de
   *  um desconto (a tela lê o sinal daqui). */
  sentido: "recebe" | "desconta" | "tira" | "assumida";
};

const MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function mesAbrev(competencia: string): string {
  const [a, m] = (competencia || "").split("-");
  const i = parseInt(m, 10) - 1;
  return i >= 0 && i < 12 ? `${MESES_ABREV[i]}/${a}` : (competencia || "—");
}

function dataBR(iso: string | null): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return d && m && a ? `${d}/${m}/${a}` : iso;
}

function arredonda2(n: number): number {
  return Math.round(n * 100) / 100;
}

/** O que descreve um vale num olhar — a mesma regra do recibo. */
export function descricaoVale(vale: ValeDaLinhaTempo): string {
  const o = vale.origem_lancamento;
  if (o) {
    if (o.numero_documento && o.produto) return `Vale — nota ${o.numero_documento} (${o.produto})`;
    if (o.numero_documento) return `Vale — nota ${o.numero_documento}`;
    if (o.produto) return `Vale — ${o.produto}`;
  }
  const texto = (vale.observacao || "").trim();
  return texto ? `Vale — ${texto}` : "Vale";
}

/**
 * Os eventos da pessoa, do mais recente para o mais antigo.
 *
 * Três espécies, deliberadamente misturadas — é o que faz a linha do tempo
 * valer a viagem: um PAGAMENTO (folha, empreita, contrato, diária, férias/13º
 * — o que a pessoa recebeu), um VALE (o dinheiro que ela pegou adiantado) e
 * uma PARCELA (o pedaço do vale descontado numa competência). A parcela é
 * datada pela folha que a absorveu; quando não existe folha naquela
 * competência, ela fica no 1º dia da competência e o texto diz que ainda não
 * foi descontada — em vez de inventar uma data de desconto que não houve.
 */
export function eventosDaPessoa(
  linhas: LinhaFolhaUnificada[], vales: ValeDaLinhaTempo[], pessoaId: number, brl: FormatadorBRL,
): EventoPessoa[] {
  const eventos: EventoPessoa[] = [];
  const daPessoa = linhas.filter((l) => l.pessoa_id === pessoaId);

  // Data da folha de cada competência — é onde as parcelas daquele mês caem.
  const dataPorCompetencia = new Map<string, string>();
  for (const l of daPessoa) {
    if (l.tipo === "funcionario" && l.competencia) {
      const d = l.data_pagamento || l.data_vencimento;
      if (d) dataPorCompetencia.set(l.competencia, d);
    }
  }

  for (const l of daPessoa) {
    const data = l.data_pagamento || l.data_vencimento || "";
    const estourada = !!l.totais?.liquido_negativo;
    const tom: TomEvento = estourada ? "estourada" : l.status === "pago" ? "pago" : l.vencido ? "vencido" : "aberto";
    const selo = estourada ? "Estourada" : l.status === "pago" ? "Pago" : l.vencido ? "Vencido" : "A vencer";
    const detalhe = l.tipo === "funcionario"
      ? [
          l.competencia ? `competência ${mesAbrev(l.competencia)}` : "",
          estourada
            ? `descontos passam os vencimentos em ${brl(l.totais?.excedente || 0)}`
            : `líquido de ${brl(l.totais?.liquido ?? l.valor)}`,
        ].filter(Boolean).join(" · ")
      : l.descricao;
    eventos.push({
      id: `${l.tipo}-${l.origem_subtipo}-${l.origem_id}`,
      grupo: null,
      data,
      titulo: l.tipo === "funcionario"
        ? `Folha de ${data ? mesAbrev(data.slice(0, 7)) : "—"}`
        : l.descricao,
      sub: detalhe,
      selo,
      tom,
      // Estourada não é "recebeu": não há líquido, há excedente.
      valor: estourada ? arredonda2(l.totais?.excedente || 0) : l.valor,
      sentido: "recebe",
    });
  }

  for (const vale of vales) {
    if (vale.pessoa_id !== pessoaId) continue;
    const parcelas = (vale.parcelas_detalhe || []).slice()
      .sort((a, b) => a.competencia.localeCompare(b.competencia) || a.id - b.id);
    const total = parcelas.length;
    eventos.push({
      id: `vale-${vale.id}`,
      grupo: `vale-${vale.id}`,
      data: vale.data_pagamento || "",
      titulo: descricaoVale(vale),
      sub: [
        total > 1 ? `${total} parcelas` : "parcela única",
        // NULL por desenho quando a forma é desconto integral em folha: não
        // houve saída de caixa, então não existe lançamento no extrato.
        vale.forma_pagamento === "desconto_integral_folha"
          ? "sem saída de caixa"
          : (vale.numero_lancamento_gerado || "sem lançamento no extrato"),
      ].join(" · "),
      selo: "Vale",
      tom: "vale",
      valor: vale.valor_total,
      sentido: "tira",
    });
    parcelas.forEach((p, i) => {
      const dataFolha = dataPorCompetencia.get(p.competencia);
      // TRÊS estados, não dois. A parcela assumida pela fazenda tem
      // `aplicada = true` (a folha daquele mês passou por ela e a marcou),
      // então o ramo antigo a escrevia "descontada na folha de ago/2026" —
      // e o funcionário não foi descontado de nada: quem pagou foi a
      // fazenda. O estado assumido é testado ANTES de `aplicada` justamente
      // porque os dois convivem na mesma parcela.
      const assumida = !!p.assumida_pela_fazenda;
      eventos.push({
        id: `parcela-${p.id}`,
        grupo: `vale-${vale.id}`,
        data: dataFolha || `${p.competencia}-01`,
        titulo: total > 1
          ? `Parcela ${i + 1}/${total} — ${descricaoVale(vale)}`
          : `Parcela única — ${descricaoVale(vale)}`,
        sub: assumida
          ? `assumida pela fazenda em ${mesAbrev(p.competencia)} · não foi descontada`
            + (p.motivo_assuncao ? ` · ${p.motivo_assuncao}` : "")
          : p.aplicada
            ? `descontada na folha de ${mesAbrev(p.competencia)}`
            : `prevista para a competência ${mesAbrev(p.competencia)} · ainda não descontada`,
        selo: assumida ? "Assumida" : p.aplicada ? "Parcela" : "A descontar",
        tom: assumida ? "assumida" : "parcela",
        valor: p.valor,
        sentido: assumida ? "assumida" : "desconta",
      });
    });
  }

  // Mais recente primeiro. Empate no mesmo dia: o pagamento antes das parcelas
  // que ele absorveu, e o vale antes das próprias parcelas — a leitura é
  // "aconteceu isto, e dentro dele isto".
  const rank = (e: EventoPessoa) => (e.sentido === "recebe" ? 0 : e.sentido === "tira" ? 1 : 2);
  return eventos.sort(
    (a, b) => (b.data || "").localeCompare(a.data || "") || rank(a) - rank(b) || a.id.localeCompare(b.id),
  );
}

export type ResumoPessoa = {
  /** Parcelas de vale ainda não descontadas — o que ela deve à fazenda. */
  saldoValesAberto: number;
  parcelasAberto: number;
  recebidoNoAno: number;
  pagamentosNoAno: number;
  valeTiradoNoAno: number;
  valesNoAno: number;
  /** Vale tirado ÷ recebido no ano — null quando não recebeu nada no ano. */
  proporcaoValeSobreRecebido: number | null;
  competenciasEstouradas: { competencia: string; excedente: number }[];
};

/**
 * Os números do rodapé. "Recebido no ano" conta só o que foi efetivamente
 * PAGO (tem `data_pagamento`) — somar o previsto junto faria a proporção
 * "quanto do que recebe já está comprometido em vale" mentir para baixo, que
 * é justamente a leitura para a qual ela serve.
 */
export function resumoDaPessoa(
  linhas: LinhaFolhaUnificada[], vales: ValeDaLinhaTempo[], pessoaId: number, ano: string,
): ResumoPessoa {
  let saldoValesAberto = 0, parcelasAberto = 0, valeTiradoNoAno = 0, valesNoAno = 0;
  for (const vale of vales) {
    if (vale.pessoa_id !== pessoaId) continue;
    for (const p of vale.parcelas_detalhe || []) {
      // Parcela assumida pela fazenda não é dívida da pessoa, e sai da conta
      // ANTES de `aplicada` ser consultada. Hoje o desconsiderar acaba
      // marcando `aplicada` de tabela, e por isso o saldo já vinha certo — por
      // acidente. Escrever a regra aqui é o que impede o acidente de virar
      // erro no dia em que a marca não for gravada.
      if (p.assumida_pela_fazenda) continue;
      if (!p.aplicada) { saldoValesAberto += p.valor; parcelasAberto += 1; }
    }
    if ((vale.data_pagamento || "").startsWith(ano)) {
      valeTiradoNoAno += vale.valor_total;
      valesNoAno += 1;
    }
  }

  let recebidoNoAno = 0, pagamentosNoAno = 0;
  const competenciasEstouradas: { competencia: string; excedente: number }[] = [];
  for (const l of linhas) {
    if (l.pessoa_id !== pessoaId) continue;
    if (l.status === "pago" && (l.data_pagamento || "").startsWith(ano) && l.valor > 0) {
      recebidoNoAno += l.valor;
      pagamentosNoAno += 1;
    }
    if (l.totais?.liquido_negativo) {
      competenciasEstouradas.push({
        competencia: l.competencia || (l.data_vencimento || "").slice(0, 7),
        excedente: l.totais.excedente,
      });
    }
  }

  return {
    saldoValesAberto: arredonda2(saldoValesAberto),
    parcelasAberto,
    recebidoNoAno: arredonda2(recebidoNoAno),
    pagamentosNoAno,
    valeTiradoNoAno: arredonda2(valeTiradoNoAno),
    valesNoAno,
    proporcaoValeSobreRecebido: recebidoNoAno > 0 ? Math.round((valeTiradoNoAno / recebidoNoAno) * 100) / 100 : null,
    competenciasEstouradas: competenciasEstouradas.sort((a, b) => a.competencia.localeCompare(b.competencia)),
  };
}

/** A nota que aparece ao acender um vale — o que aquele grupo conta junto. */
export function notaDoGrupo(
  vales: ValeDaLinhaTempo[], grupo: string, brl: FormatadorBRL,
): { titulo: string; texto: string } | null {
  const id = parseInt(grupo.replace("vale-", ""), 10);
  const vale = vales.find((v) => v.id === id);
  if (!vale) return null;
  const parcelas = vale.parcelas_detalhe || [];
  // TRÊS categorias que não se misturam, e nenhuma parcela em duas delas: a
  // assumida sai da conta primeiro, porque ela chega aqui com `aplicada`
  // marcado e antes era contada como descontada — o rodapé dizia "3 de 13 já
  // foram descontadas" incluindo um mês que a fazenda pagou. Ela também não
  // "falta": não há nada a cobrar por ela.
  const assumidas = parcelas.filter((p) => p.assumida_pela_fazenda);
  const descontadas = parcelas.filter((p) => !p.assumida_pela_fazenda && p.aplicada);
  const abertas = parcelas.filter((p) => !p.assumida_pela_fazenda && !p.aplicada);
  const saldo = arredonda2(abertas.reduce((a, p) => a + p.valor, 0));
  const assumido = arredonda2(assumidas.reduce((a, p) => a + p.valor, 0));
  const proximas = abertas.map((p) => mesAbrev(p.competencia));
  const mesesAssumidos = assumidas.map((p) => mesAbrev(p.competencia));
  return {
    titulo: `${descricaoVale(vale)} de ${brl(vale.valor_total)} — ${parcelas.length} ${parcelas.length === 1 ? "parcela acesa" : "parcelas acesas"} acima`,
    texto: [
      `Tirado em ${dataBR(vale.data_pagamento)}.`,
      descontadas.length
        ? `${descontadas.length} de ${parcelas.length} já ${descontadas.length === 1 ? "foi descontada" : "foram descontadas"}.`
        : "Nenhuma parcela foi descontada ainda.",
      assumidas.length
        ? `A fazenda assumiu ${assumidas.length} (${brl(assumido)}), em ${mesesAssumidos.join(", ")} — `
          + `${assumidas.length === 1 ? "esse mês não foi descontado" : "esses meses não foram descontados"} do funcionário.`
        : "",
      abertas.length
        ? `Faltam ${abertas.length} (${brl(saldo)} a descontar), em ${proximas.join(", ")}.`
        : "Não há saldo a descontar.",
    ].filter(Boolean).join(" "),
  };
}
