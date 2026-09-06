// Regras da COMPETÊNCIA — o mês de folha como objeto, e não a lista de
// lançamentos. Sem nenhum import de runtime (só tipos, que o compilador
// apaga), no mesmo molde de lib/holeriteRegras.ts: é o que permite testá-las
// com o runner nativo do Node. Ver lib/folhaCompetencia.test.ts.
//
// POR QUE ESTE MÓDULO EXISTE. A tela de Ações abria sem mês nenhum: dois
// campos de data soltos ("Vencimento — de/até"), três KPIs que somavam o que
// passasse pelo filtro e nenhuma identidade a conferir. Não havia como
// perguntar "posso fechar setembro?" — só "quanto deu o filtro?". Aqui moram
// as três coisas que faltavam para a pergunta existir:
//
//   1. QUAL É O MÊS de um lançamento (um critério só, para os cinco tipos);
//   2. A EQUAÇÃO do mês — Vencimentos − Retenções − Vales − Outros = A pagar,
//      lida da MESMA discriminação que o recibo, para os dois números não
//      poderem divergir;
//   3. AS EXCEÇÕES do mês — e só as que existem de verdade no código de hoje.
//
// Sobre (3), explicitamente: dois dos três cartões do desenho aprovado
// descreviam bugs já corrigidos no backend (folha recorrente nascendo sem
// INSS/IR, corrigida por `_corrigir_folha_gerada_sem_retencao`; e retenção
// digitada sem percentual sumindo da discriminação, corrigida em
// `_detalhe_folha`, que hoje testa o VALOR e não o percentual). Cartão para
// bug que não existe mais é ruído que ensina o usuário a ignorar o painel.
// O que está aqui foi levantado lendo o código atual.
import type { LinhaFolhaUnificada, LinhaHolerite } from "./api";

/** Um centavo — mesma tolerância de `holerite.TOLERANCIA_CONFERENCIA`. */
const CENTAVO = 0.01;

// ── O mês de um lançamento ────────────────────────────────────────────────

/**
 * O mês em que o lançamento ENTRA NO CAIXA — pago, o mês do pagamento;
 * pendente, o mês do vencimento. É exatamente o critério que a coluna "Mês"
 * da tabela já usava, e é o único que os cinco tipos sustentam: empreita,
 * contrato e diária não têm competência nenhuma (dossiê, C6).
 *
 * A competência (mês TRABALHADO) continua sendo coisa só do funcionário e
 * viaja à parte, em `competenciasDoMes` — misturar as duas numa régua só
 * seria repetir N1, a coluna com dois significados.
 */
export function mesDaLinha(l: LinhaFolhaUnificada): string {
  const d = l.data_pagamento || l.data_vencimento;
  return d ? d.slice(0, 7) : "";
}

/** Meses presentes no ledger, do mais recente para o mais antigo. */
export function mesesDoLedger(linhas: LinhaFolhaUnificada[]): string[] {
  const meses = new Set<string>();
  for (const l of linhas) {
    const m = mesDaLinha(l);
    if (m) meses.add(m);
  }
  return Array.from(meses).sort().reverse();
}

/**
 * Em que mês a tela abre. O mês corrente quando ele tem lançamento; senão o
 * mês mais recente que tem. Abrir no mês corrente por decreto deixaria a tela
 * vazia em toda fazenda que ainda não lançou nada no mês — pior do que o
 * estado de hoje, em que pelo menos tudo aparece.
 */
export function mesInicial(linhas: LinhaFolhaUnificada[], hoje: string): string {
  const meses = mesesDoLedger(linhas);
  if (meses.includes(hoje)) return hoje;
  return meses[0] || hoje;
}

/** "2026-09" + 1 → "2026-10"; −1 → "2026-08". */
export function passoMes(mes: string, delta: number): string {
  const [a, m] = mes.split("-").map((x) => parseInt(x, 10));
  if (!a || !m) return mes;
  const total = a * 12 + (m - 1) + delta;
  const ano = Math.floor(total / 12);
  const idx = total - ano * 12;
  return `${String(ano).padStart(4, "0")}-${String(idx + 1).padStart(2, "0")}`;
}

export function primeiroDiaDoMes(mes: string): string {
  return `${mes}-01`;
}

export function ultimoDiaDoMes(mes: string): string {
  const [a, m] = mes.split("-").map((x) => parseInt(x, 10));
  // Dia 0 do mês seguinte = último dia deste. `Date.UTC` para o resultado não
  // depender do fuso do aparelho (a tela roda em celular e em desktop).
  const d = new Date(Date.UTC(a, m, 0));
  return d.toISOString().slice(0, 10);
}

/**
 * O intervalo de datas corresponde a um mês inteiro? Devolve o mês, ou null
 * quando o usuário escolheu um período próprio nos campos de data — a barra
 * do topo e os dois campos são o MESMO filtro, e a barra precisa saber quando
 * não está mais governando (senão mostraria um mês que não é o que a tabela
 * está exibindo).
 */
export function mesDoIntervalo(de: string, ate: string): string | null {
  if (!de || !ate) return null;
  const mes = de.slice(0, 7);
  return de === primeiroDiaDoMes(mes) && ate === ultimoDiaDoMes(mes) ? mes : null;
}

// O rótulo por extenso ("Setembro / 2026") é `competenciaExtenso`, de
// lib/holeriteRegras — não é reescrito aqui: a tabela de meses tem de existir
// num lugar só, e este módulo precisa continuar sem import de runtime nenhum
// para rodar no runner do Node.

/**
 * As competências (meses TRABALHADOS) das folhas de funcionário que caem no
 * mês em tela. Normalmente uma só — a folha de agosto vence em 5 de setembro
 * —, mas o dia de vencimento é configurável por lançamento (`dia_vencimento`),
 * então duas competências podem cair no mesmo mês. Dizer quais são é honesto;
 * escrever "competência 2026-08" fixo seria adivinhar.
 */
export function competenciasDoMes(linhas: LinhaFolhaUnificada[]): string[] {
  const comps = new Set<string>();
  for (const l of linhas) {
    if (l.tipo === "funcionario" && l.competencia) comps.add(l.competencia);
  }
  return Array.from(comps).sort();
}

// ── A equação do mês ──────────────────────────────────────────────────────

export type EquacaoFolha = {
  vencimentos: number;
  retencoes: number;
  vales: number;
  outros: number;
  /** Soma dos líquidos que PODEM ser pagos — folha estourada não entra. */
  aPagar: number;
  /** Soma dos excedentes das folhas estouradas, em valor absoluto. */
  foraDaConta: number;
  folhas: number;
  folhasForaDaConta: number;
  parcelasVale: number;
  pagas: number;
  aVencer: number;
  vencidas: number;
  /**
   * Σ do líquido GRAVADO no ledger menos Σ do líquido que a DISCRIMINAÇÃO
   * produz. Deveria ser sempre zero: são o mesmo número por dois caminhos.
   * Quando não é, alguma folha mudou depois de paga (ver `excecoesDoMes`).
   */
  divergencia: number;
};

function descontoDe(detalhe: LinhaHolerite[] | undefined, tipos: string[]): number {
  return (detalhe || [])
    .filter((d) => tipos.includes(d.tipo))
    .reduce((a, d) => a + (d.desconto || 0), 0);
}

function arredonda2(n: number): number {
  return Math.round(n * 100) / 100;
}

/**
 * A identidade do mês, lida da discriminação de cada folha — a MESMA lista
 * que o recibo imprime. Os totais da faixa e os do papel não podem divergir
 * porque não existem dois cálculos: existe um, aqui.
 *
 * Só funcionário entra. Empreita, contrato, diária e férias/13º são
 * pagamentos de valor único, sem composição bruto→retenções→líquido (C6):
 * empurrá-los para dentro da equação daria uma soma que não é conta de nada.
 * Eles aparecem à parte, em `resumoOutrosTipos`.
 */
export function equacaoDoMes(linhas: LinhaFolhaUnificada[]): EquacaoFolha {
  const folhas = linhas.filter((l) => l.tipo === "funcionario");
  let vencimentos = 0, retencoes = 0, vales = 0, outros = 0;
  let aPagar = 0, foraDaConta = 0, parcelasVale = 0, folhasForaDaConta = 0;
  let liquidoDiscriminado = 0, liquidoGravado = 0;
  let pagas = 0, aVencer = 0, vencidas = 0;

  for (const l of folhas) {
    vencimentos += l.totais?.total_proventos || 0;
    retencoes += descontoDe(l.detalhe, ["inss", "ir"]);
    vales += descontoDe(l.detalhe, ["vale"]);
    outros += descontoDe(l.detalhe, ["outros"]);
    parcelasVale += (l.detalhe || []).filter((d) => d.tipo === "vale").length;
    liquidoDiscriminado += l.totais?.liquido || 0;
    liquidoGravado += l.valor;
    if (l.totais?.liquido_negativo) {
      foraDaConta += l.totais.excedente;
      folhasForaDaConta += 1;
    } else {
      aPagar += l.totais?.liquido || 0;
    }
    if (l.status === "pago") pagas += 1;
    else if (l.vencido) vencidas += 1;
    else aVencer += 1;
  }

  return {
    vencimentos: arredonda2(vencimentos),
    retencoes: arredonda2(retencoes),
    vales: arredonda2(vales),
    outros: arredonda2(outros),
    aPagar: arredonda2(aPagar),
    foraDaConta: arredonda2(foraDaConta),
    folhas: folhas.length,
    folhasForaDaConta,
    parcelasVale,
    pagas,
    aVencer,
    vencidas,
    divergencia: arredonda2(liquidoGravado - liquidoDiscriminado),
  };
}

// ── "Também vence neste mês" — os quatro tipos sem competência ────────────

export type ResumoTipo = {
  tipo: LinhaFolhaUnificada["tipo"];
  quantidade: number;
  total: number;
  pagos: number;
  vencidos: number;
};

/**
 * Empreita, contrato, diária e férias/13º agrupados por tipo. Não somam com a
 * folha e não dividem coluna com ela — é a separação que faz a coluna "Valor"
 * parar de ter dois significados (N1).
 */
export function resumoOutrosTipos(linhas: LinhaFolhaUnificada[]): ResumoTipo[] {
  const por = new Map<string, ResumoTipo>();
  for (const l of linhas) {
    if (l.tipo === "funcionario") continue;
    const atual = por.get(l.tipo) || { tipo: l.tipo, quantidade: 0, total: 0, pagos: 0, vencidos: 0 };
    atual.quantidade += 1;
    atual.total = arredonda2(atual.total + l.valor);
    if (l.status === "pago") atual.pagos += 1;
    else if (l.vencido) atual.vencidos += 1;
    por.set(l.tipo, atual);
  }
  return Array.from(por.values()).sort((a, b) => b.total - a.total);
}

// ── As exceções do mês ────────────────────────────────────────────────────

export type GravidadeExcecao = "bloqueia" | "conferir";

export type Excecao = {
  /** Estável entre renderizações — é a chave de lista e a de "já resolvi". */
  id: string;
  gravidade: GravidadeExcecao;
  titulo: string;
  frase: string;
  /** Rótulo do botão que resolve. */
  acao: string;
  /** Folhas que a exceção alcança — a tela abre a linha de cada uma. */
  folhaIds: number[];
  /** Ordena dentro da gravidade: o dinheiro maior primeiro. */
  valor: number;
};

/**
 * As exceções REAIS de hoje, levantadas lendo o backend atual — não as do
 * desenho. Cada uma abaixo tem a linha de código que a sustenta:
 *
 * 1. FOLHA ESTOURADA (`totais.liquido_negativo`, `rules/holerite.py`). O guard
 *    de líquido negativo só existe em criar e editar folha; nem
 *    `_reconciliar_vale_competencias`, nem o self-heal da listagem, nem
 *    `_gerar_folha_recorrente` o têm — um vale novo põe a folha no vermelho
 *    sem passar por validação nenhuma. Bloqueia: o recibo não pode ser
 *    emitido e a folha fica fora do total do mês.
 *
 * 2. RECIBO QUE NÃO SOMA O LÍQUIDO PAGO (C7, o achado mais grave do dossiê, e
 *    ainda não corrigido). `_detalhe_folha` consulta `ValeParcela` NO MOMENTO
 *    DA LEITURA, inclusive para folha já paga, enquanto `valor_liquido` fica
 *    gravado e o self-heal pula pago. Editar, excluir ou criar uma parcela de
 *    vale muda retroativamente o holerite de uma competência já paga — e a
 *    discriminação deixa de somar o líquido. É detectável 100% na tela,
 *    justamente porque os dois números vêm por caminhos diferentes.
 *
 * 3. RETENÇÃO AJUSTADA À MÃO (`origem.confere === false`). O formulário
 *    recalcula o valor a partir do percentual mas deixa o campo editável;
 *    quando o valor gravado não bate com `percentual × bruto`, o servidor
 *    DECLARA a divergência em vez de escondê-la. Conferir antes de pagar.
 *
 * 4. VENCIDA E NÃO PAGA (`vencido`). O flag já existia e só pintava o fundo
 *    da linha — nunca subiu ao topo da tela nem virou número.
 *
 * O que deliberadamente NÃO virou cartão, e por quê:
 *  - "folha recorrente sem INSS/IR": corrigida no backend
 *    (`_corrigir_folha_gerada_sem_retencao` conserta toda folha ainda não
 *    paga a cada listagem). O resíduo assumido são folhas JÁ PAGAS com o
 *    líquido inflado — e essas não são "resolver antes de fechar": o dinheiro
 *    saiu, mexer nelas seria reescrever histórico financeiro.
 *  - "retenção sem percentual": a linha não some mais do holerite
 *    (`_detalhe_folha` testa o VALOR). O que resta é a referência dizendo
 *    "Valor informado, sem percentual", que já está impressa na própria linha
 *    do recibo — não é pendência de fechamento.
 *  - "vale acima de 40% do salário": já é barrado no lançamento, com
 *    confirmação explícita. A API não devolve se o estouro foi autorizado, e
 *    sem isso o cartão reapareceria eternamente em todo vale já confirmado.
 */
export function excecoesDoMes(linhas: LinhaFolhaUnificada[]): Excecao[] {
  const excecoes: Excecao[] = [];
  const folhas = linhas.filter((l) => l.tipo === "funcionario");

  for (const l of folhas) {
    if (l.totais?.liquido_negativo) {
      excecoes.push({
        id: `estourada-${l.origem_id}`,
        gravidade: "bloqueia",
        titulo: `${l.pessoa_nome} — os descontos passam os vencimentos`,
        frase:
          `Os descontos desta folha somam mais que o salário e sobra um excedente. ` +
          `Enquanto isso durar ela fica fora do total a pagar do mês e o recibo não pode ser emitido — ` +
          `abra a linha para ver qual parcela de vale ultrapassa e adiá-la.`,
        acao: "Ver a folha",
        folhaIds: [l.origem_id],
        valor: l.totais.excedente,
      });
    }
  }

  // (2) — comparação dos dois caminhos do mesmo número.
  for (const l of folhas) {
    if (!l.totais) continue;
    const diferenca = arredonda2(l.valor - l.totais.liquido);
    if (Math.abs(diferenca) <= CENTAVO) continue;
    const pago = l.status === "pago";
    excecoes.push({
      id: `nao-soma-${l.origem_id}`,
      gravidade: "bloqueia",
      titulo: `${l.pessoa_nome} — o recibo não fecha com o valor ${pago ? "pago" : "lançado"}`,
      frase:
        `A discriminação soma um líquido diferente do que está gravado na folha. ` +
        `Uma parcela de vale desta competência foi criada, alterada ou excluída depois ` +
        `${pago ? "de a folha ser paga" : "do lançamento"} — a folha ` +
        `${pago ? "paga não é recalculada" : "precisa ser reaberta"}, então o recibo e o valor deixaram de contar a mesma história.`,
      acao: "Ver a folha",
      folhaIds: [l.origem_id],
      valor: Math.abs(diferenca),
    });
  }

  // (3) — retenção cujo valor não bate com o percentual gravado.
  for (const l of folhas) {
    const ajustadas = (l.detalhe || []).filter(
      (d) => d.origem && d.origem.tipo === "retencao" && d.origem.confere === false,
    );
    if (!ajustadas.length) continue;
    const nomes = ajustadas.map((d) => d.descricao).join(" e ");
    const total = ajustadas.reduce((a, d) => a + Math.abs(d.desconto || 0), 0);
    excecoes.push({
      id: `retencao-${l.origem_id}`,
      gravidade: "conferir",
      titulo: `${l.pessoa_nome} — ${nomes} não bate com o percentual gravado`,
      frase:
        `O valor retido foi editado à mão depois de calculado e não corresponde mais ao percentual × salário. ` +
        `O recibo declara a diferença em vez de escondê-la — confira qual dos dois está certo antes de pagar.`,
      acao: "Ver a folha",
      folhaIds: [l.origem_id],
      valor: arredonda2(total),
    });
  }

  // (4) — vencidos e não pagos, de TODOS os tipos, num cartão só: são a mesma
  // pendência repetida, e uma linha por lançamento afogaria as outras três.
  const vencidos = linhas.filter((l) => l.vencido);
  if (vencidos.length) {
    const total = arredonda2(vencidos.reduce((a, l) => a + Math.max(l.valor, 0), 0));
    const folhaIds = vencidos.filter((l) => l.tipo === "funcionario").map((l) => l.origem_id);
    excecoes.push({
      id: "vencidos",
      gravidade: "conferir",
      titulo:
        vencidos.length === 1
          ? `1 pagamento venceu e continua pendente`
          : `${vencidos.length} pagamentos venceram e continuam pendentes`,
      frase:
        `${vencidos.map((l) => l.pessoa_nome).filter((n, i, a) => a.indexOf(n) === i).join(", ")} — ` +
        `a data de vencimento já passou e a baixa não foi registrada.`,
      acao: folhaIds.length ? "Ver as folhas" : "Ver na tabela",
      folhaIds,
      valor: total,
    });
  }

  const peso = (g: GravidadeExcecao) => (g === "bloqueia" ? 0 : 1);
  return excecoes.sort((a, b) => peso(a.gravidade) - peso(b.gravidade) || b.valor - a.valor);
}
