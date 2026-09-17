"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Plus, Paperclip, Check, ChevronDown, ChevronRight, RefreshCw, Filter, Pencil, Trash2, Printer, History, Search, RotateCcw } from "lucide-react";
import {
  fetchPessoas, fetchFolhaPagamento, criarFolhaPagamento, atualizarFolhaPagamento, excluirFolhaPagamento,
  estornarPagamentoFolha,
  fetchFolhaPagamentoUnificada, excluirParcelaEmpreitada, excluirParcelaContrato, type LinhaFolhaUnificada,
  atualizarParcelaEmpreitada, atualizarParcelaContrato,
  fetchVales, criarVale, atualizarVale, atualizarParcelaVale, excluirParcelaVale, excluirVale, ehAdmin, formatBRL,
  fetchValesAvulsos, atualizarValeAvulso, excluirValeAvulso, previaExclusaoVale, previaExclusaoValeAvulso,
  type PreviaExclusaoVale,
  lancarGuiaFolhaEncargo, fetchGuiasFolhaEncargo, atualizarGuiaFolhaEncargo, excluirGuiaFolhaEncargo, type GuiaFolhaEncargo,
  lerDocumentoFinanceiro, anexarArquivoLancamento, formatDate,
  fetchContasCorrentes, type ContaCorrenteCadastro,
  anexarComprovanteVale, listarComprovantesVale, excluirComprovanteVale, urlComprovanteVale,
  type LinhaHolerite, type LinhaValeAssumido, type TotaisHolerite, type BasesHolerite,
} from "@/lib/api";
import { ModalDivergenciaVale, ModalResultadoDivergenciaVale, ModalConfirmarDivergenciaTotal } from "@/components/ModalDivergenciaVale";
import AcoesValeModal from "@/components/AcoesValeModal";
import PagarFolhaModal from "@/components/PagarFolhaModal";
import { Modal } from "@/components/Modal";
import { CampoMoeda } from "@/components/CampoMoeda";
import { ReciboModal } from "@/components/ReciboModal";
import { type LancamentoRecibo } from "@/lib/export";
import { Holerite, LinkExtrato } from "@/components/Holerite";
import {
  competenciaExtenso, filtrarPorSituacao, holeriteDaLinha, imprimirHolerite, imprimirHolerites,
  rotuloStatusLinha, type Holerite as DocHolerite, type SituacaoPagamento,
} from "@/lib/holerite";
import { ModalDivididoDocumento } from "@/components/ModalDivididoDocumento";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import { AvisoSalvo } from "@/components/AvisoSalvo";
import { Dropzone } from "@/components/Dropzone";
import { SecaoRecolhivel } from "@/components/ui";
import { RubricasHolerite } from "@/components/RubricasHolerite";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { BarraCompetencia } from "@/components/BarraCompetencia";
import { EquacaoFolha, OutrosPagamentosDoMes } from "@/components/EquacaoFolha";
import { ExcecoesFolha } from "@/components/ExcecoesFolha";
import { LinhaTempoPessoa } from "@/components/LinhaTempoPessoa";
import { type ValeDaLinhaTempo } from "@/lib/linhaTempoPessoa";
import {
  equacaoDoMes, excecoesDoMes, competenciasDoMes, mesDaLinha, mesInicial, mesesDoLedger,
  resumoOutrosTipos, situacaoDoMes, type Excecao,
} from "@/lib/folhaCompetencia";
import EmpreitadaView from "@/components/EmpreitadaView";
import ContratoView from "@/components/ContratoView";
import DiariaView from "@/components/DiariaView";
import FeriasDecimoTerceiroView from "@/components/FeriasDecimoTerceiroView";
import RescisaoView from "@/components/RescisaoView";

const LABEL_TIPO: Record<string, string> = {
  funcionario: "Funcionário", empreita: "Empreita", contrato: "Contrato", diaria: "Diária", ferias_decimo: "Férias / 13º",
  // "rescisao" é rótulo só de CHIP: o ledger unificado ainda não emite linhas
  // desse tipo — é por isso que a categoria declara `tipoLedger: null` abaixo.
  rescisao: "Rescisão",
};

type CategoriaFolha =
  | "todos" | "funcionario" | "empreita" | "contrato" | "diarias" | "ferias_decimo" | "rescisao";

/**
 * O QUE EXISTE EM CADA CATEGORIA — a tabela que governa a tela inteira.
 *
 * Antes, o único recorte era `mostraFormasGerais` (categoria "todos" ou
 * "funcionario"), e ele escondia só os três formulários de lançar. Tudo o
 * resto continuava na tela: sob Empreita, Contrato e Diária apareciam as
 * "Guias de FGTS/DCTF lançadas" e o "Relatório de vales e descontos" de
 * FUNCIONÁRIO — FGTS é encargo de CLT e empreiteiro não é CLT. Era a
 * reclamação do dono, e a causa não era um `if` esquecido: era não haver
 * lugar nenhum onde a pergunta "isto existe nesta categoria?" fosse
 * respondida uma vez só.
 *
 * Agora ela é respondida aqui, em dados. Cada bloco da tela lê um campo desta
 * tabela; nenhum bloco decide por conta própria se aparece. Acrescentar uma
 * categoria (ou dar FGTS a alguma delas) é editar esta tabela, não caçar
 * condições espalhadas pela renderização.
 */
type CapacidadesCategoria = {
  rotulo: string;
  /** Tipo correspondente no ledger unificado. `""` = todos os tipos;
   *  `null` = a categoria NÃO tem linha no ledger (rescisão) e por isso não
   *  tem mês, equação, exceções nem tabela — ver `RescisaoView`. */
  tipoLedger: string | null;
  /** Formulário "Nova folha" + holerite + rubricas — só CLT. */
  folhaFuncionario: boolean;
  /** Guias de FGTS/DCTF (lançar e listar) — encargo de CLT, só funcionário. */
  guias: boolean;
  /** Vale de FUNCIONÁRIO: parcelado, descontado na folha da competência. */
  valeFuncionario: boolean;
  /** Vale AVULSO: abatido da próxima parcela/etapa de empreita/contrato/diária. */
  valeAvulso: boolean;
  /** Tela própria da categoria (formulário + listagem), quando existe. */
  telaPropria: "empreita" | "contrato" | "diarias" | "ferias_decimo" | "rescisao" | null;
};

const CATEGORIAS: Record<CategoriaFolha, CapacidadesCategoria> = {
  todos: {
    rotulo: "Todos", tipoLedger: "",
    folhaFuncionario: true, guias: true, valeFuncionario: true, valeAvulso: true, telaPropria: null,
  },
  funcionario: {
    rotulo: "Funcionário", tipoLedger: "funcionario",
    folhaFuncionario: true, guias: true, valeFuncionario: true, valeAvulso: false, telaPropria: null,
  },
  empreita: {
    rotulo: "Empreita", tipoLedger: "empreita",
    folhaFuncionario: false, guias: false, valeFuncionario: false, valeAvulso: true, telaPropria: "empreita",
  },
  contrato: {
    rotulo: "Contrato", tipoLedger: "contrato",
    folhaFuncionario: false, guias: false, valeFuncionario: false, valeAvulso: true, telaPropria: "contrato",
  },
  diarias: {
    rotulo: "Diária", tipoLedger: "diaria",
    folhaFuncionario: false, guias: false, valeFuncionario: false, valeAvulso: true, telaPropria: "diarias",
  },
  ferias_decimo: {
    rotulo: "Férias / 13º", tipoLedger: "ferias_decimo",
    folhaFuncionario: false, guias: false, valeFuncionario: false, valeAvulso: false, telaPropria: "ferias_decimo",
  },
  // A rescisão é a única sem ledger: o endpoint unificado monta CINCO tipos e
  // ela não é um deles. Antes, o chip dela apagava meia tela (barra do mês,
  // equação e tabela sumiam por uma condição solta); agora a ausência é
  // DECLARADA, e a tela dela é montada com o que lhe cabe — nada some, nada
  // aparece zerado mentindo que "não há rescisão nenhuma".
  rescisao: {
    rotulo: "Rescisão", tipoLedger: null,
    folhaFuncionario: false, guias: false, valeFuncionario: false, valeAvulso: false, telaPropria: "rescisao",
  },
};

const ORDEM_CATEGORIAS: CategoriaFolha[] = [
  "todos", "funcionario", "empreita", "contrato", "diarias", "ferias_decimo", "rescisao",
];

// Aliases de URL: a Agenda linkava `categoria=empreitada` (o nome da tabela no
// banco) e o chip se chama `empreita` — o valor desconhecido caía em silêncio
// no chip "Todos". O link foi corrigido na Agenda; o alias fica para os
// eventos/notificações que já estavam gravados com o nome antigo.
const ALIAS_CATEGORIA: Record<string, CategoriaFolha> = { empreitada: "empreita", diaria: "diarias" };

// O MESMO filtro de "Contas > Holerites e recibos", com os mesmos rótulos:
// era o único lugar em que ele existia, e quem fecha o mês é quem mais
// precisa dele. Substitui o select "Status" (pendente/pago), que tinha
// exatamente este predicado sob outro nome — ver `filtrarPorSituacao`.
const SITUACOES: { id: SituacaoPagamento; label: string; dica: string }[] = [
  { id: "pagos", label: "Pagos", dica: "Só o que já foi pago" },
  { id: "a_pagar", label: "A pagar", dica: "Tudo o que ainda não foi pago, vencido ou não" },
  { id: "todos", label: "Todos", dica: "Pagos e a pagar, juntos" },
];

/** Os três cards do topo — o que a tela está fazendo agora. */
type CardFolha = "consultar" | "lancar" | "resolver";

// Cada card do topo, seu papel e o que ele conta. O número é a resposta curta
// da pergunta do card, não enfeite: quanto há no mês, quantas formas de lançar
// existem NESTA categoria, quantas pendências travam o fechamento.
const CARDS: { id: CardFolha; titulo: string; descricao: string }[] = [
  { id: "consultar", titulo: "Consultar", descricao: "o que já está lançado no mês" },
  { id: "lancar", titulo: "Lançar", descricao: "formas de lançamento desta categoria" },
  { id: "resolver", titulo: "Resolver antes de fechar", descricao: "pendências que travam o fechamento" },
];
// Acentos emprestados da paleta CowData (navy+dourado+verde+vermelho do
// painel do dono do software) — usados só nos 3 cards de "Lançar" desta
// tela, não como fundo/base (que continua o tema normal da fazenda).
const COR_LANCAR = { folha: "#E8C256", vale: "#3ECF8E", guia: "#E05C5C" };
// Fundo vinho translúcido para destacar lançamentos vencidos e não pagos.
const VENCIDO_BG = "rgba(94, 26, 46, 0.18)";

// "2026-07" → "jul/2026" (rótulo legível do mês de competência)
const MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const mesCompLabel = (comp: string) => {
  const [a, m] = (comp || "").split("-");
  const idx = parseInt(m, 10) - 1;
  return idx >= 0 && idx < 12 ? `${MESES_ABREV[idx]}/${a}` : (comp || "");
};

const selStyleLote: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", width: "100%",
};
const labelStyleLote: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
// Nome clicável na tabela — o mesmo sinal de "isto abre algo" que as colunas
// de desconto desta tela já usam (sublinhado pontilhado), e não uma classe de
// link nova: o projeto não tem nenhuma, e inventar uma aqui criaria um estilo
// de link que só existe nesta tabela.
// O que o clique no nome ABRE mudou: era a linha do tempo da pessoa, e passou
// a ser o discriminado do lançamento (é o gesto do desenho aprovado). A linha
// do tempo não perdeu a porta — ganhou um botão próprio na coluna de ações,
// com ícone de histórico; ela continua sendo a ÚNICA maneira de chegar a
// LinhaTempoPessoa em todo o sistema.
const nomeClicavel: React.CSSProperties = {
  background: "none", border: "none", padding: 0, font: "inherit", color: "inherit",
  cursor: "pointer", textDecoration: "underline dotted", textUnderlineOffset: "0.2em",
};

/*
 * Financeiro > Ações > Fechamento da folha — AQUI SE FECHA O MÊS.
 *
 * Pessoas (funcionário, veterinário, diarista etc.) vêm do cadastro em
 * Configurações > Cadastro > Pessoas; aqui se lança, se confere, se
 * acrescenta verba ao holerite e se dá baixa. A tela irmã, Contas >
 * Holerites e recibos, é SÓ CONSULTA — e as duas dizem isso na própria
 * interface, porque no menu a frase some assim que se entra.
 *
 * A TELA TEM TRÊS NÍVEIS, nesta ordem:
 *
 *   1. os três CARDS do topo — Consultar · Lançar · Resolver antes de fechar
 *      — que dizem o que a tela está fazendo agora;
 *   2. os CHIPS de categoria, que dizem sobre o quê;
 *   3. a faixa de FILTROS (que some inteira sob "Lançar": não se filtra o que
 *      ainda não existe) e, abaixo, o conteúdo em cards de grupo — cada card
 *      abre os lançamentos, e o clique no NOME abre o discriminado.
 *
 * A regra que governa tudo isso é uma só e mora em `CATEGORIAS`, acima: só
 * aparece o que compete à categoria escolhida. Antes, o único recorte era
 * `mostraFormasGerais` — e por isso as guias de FGTS e o relatório de vales
 * de FUNCIONÁRIO continuavam na tela sob Empreita, Contrato e Diária.
 */
// `data_admissao` já vem em `GET /cadastro/pessoas` (o serializador devolve a
// Pessoa inteira) e é o que a ficha da pessoa escreve como vínculo — o
// cadastro não precisou ganhar campo nenhum para a linha do tempo existir.
type PessoaFolha = { id: number; nome: string; tipos: string[]; data_admissao?: string | null };
type RegistroFolha = {
  id: number; pessoa_id: number; pessoa_nome: string; competencia: string;
  valor_bruto: number; descontos: number;
  percentual_inss: number; percentual_ir: number; valor_inss: number; valor_ir: number;
  // FGTS/DCTF — opcionais, só para projeção (ver painel "Gerar guias de FGTS/DCTF").
  percentual_fgts?: number | null; valor_fgts?: number | null;
  percentual_dctf?: number | null; valor_dctf?: number | null;
  valor_vale?: number;
  valor_liquido: number;
  data_pagamento: string | null; data_vencimento?: string | null; status: string; observacao: string | null;
  recorrente: boolean; dia_vencimento: number | null;
  conta_corrente_id?: number | null;
  origem_recorrencia_id: number | null; numero_lancamento_gerado: string | null;
  // Cada linha traz agora descrição, REFERÊNCIA (de onde o valor veio) e,
  // quando é desconto de vale, a origem com o `vale_id` — o que substitui o
  // `/vale/i.test(label)` que a tela usava para adivinhar "o que é vale".
  detalhe: LinhaHolerite[];
  // Parcelas que a FAZENDA assumiu naquela competência — campo à parte de
  // `detalhe` porque não são desconto de ninguém e não podem entrar em soma
  // nenhuma (nem no total do mês, nem no líquido, nem no holerite impresso).
  // Vêm para o painel poder explicar por que o desconto sumiu e para o botão
  // "Ações" continuar existindo no mês desconsiderado — sem elas a ação de
  // desfazer ficava sem porta de entrada.
  vale_assumido?: LinhaValeAssumido[];
  totais: TotaisHolerite;
  bases: BasesHolerite;
  usuario_nome?: string | null;
};

function arredonda2(n: number) {
  return Math.round(n * 100) / 100;
}

/** Par percentual/valor de retenção (INSS ou IR) — o valor é recalculado
 * automaticamente a partir do percentual, mas fica editável: digitar
 * diretamente no valor "trava" o campo contra o recálculo automático até
 * o percentual ser alterado de novo. */
function CampoRetencao({
  label, percentual, valor, onChangePercentual, onChangeValor,
}: {
  label: string; percentual: string; valor: string;
  onChangePercentual: (v: string) => void; onChangeValor: (v: string) => void;
}) {
  return (
    <>
      <div><label style={labelStyleLote}>{label} (%)</label>
        <input type="number" inputMode="decimal" style={selStyleLote} value={percentual} onChange={(e) => onChangePercentual(e.target.value)} /></div>
      <div><label style={labelStyleLote}>{label} (R$)</label>
        <CampoMoeda style={selStyleLote} value={Number(valor) || 0} onChange={(v) => onChangeValor(v ? String(v) : "")} /></div>
    </>
  );
}

export default function FolhaPagamentoView() {
  const admin = ehAdmin();
  const [pessoas, setPessoas] = useState<PessoaFolha[]>([]);
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [regs, setRegs] = useState<RegistroFolha[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [pessoaId, setPessoaId] = useState("");
  const [competencia, setCompetencia] = useState(() => new Date().toISOString().slice(0, 7));
  const [valorBruto, setValorBruto] = useState("");
  const [descontos, setDescontos] = useState("");
  const [percentualInss, setPercentualInss] = useState("");
  const [valorInss, setValorInss] = useState("");
  const [inssManual, setInssManual] = useState(false);
  const [percentualIr, setPercentualIr] = useState("");
  const [valorIr, setValorIr] = useState("");
  const [irManual, setIrManual] = useState(false);
  // FGTS/DCTF — opcionais; em branco, não entram na projeção da guia mensal.
  const [observacao, setObservacao] = useState("");
  const [recorrente, setRecorrente] = useState(false);
  const [diaVencimento, setDiaVencimento] = useState("5");
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  // Qual folha está com o pop-up de pagamento aberto. A data do pagamento e a
  // decisão sobre a diferença moram DENTRO do pop-up (PagarFolhaModal): pagar
  // deixou de ser "escolher uma data na linha" quando passou a poder lançar
  // valor distinto numa verba.
  const [pagandoId, setPagandoId] = useState<number | null>(null);
  const [anexarAberto, setAnexarAberto] = useState(false);
  const [arquivoPreview, setArquivoPreview] = useState<File | null>(null);

  // Seletor único de categoria — antes era uma TabBar que só navegava entre
  // telas (sem filtrar nada); agora governa TANTO o que aparece em "Lançar"
  // quanto o filtro de "Consultar" logo abaixo (ver `tipoUnificado`).
  // "rescisao" é chip IRMÃO dos demais, não sub-aba de "ferias_decimo": a
  // rescisão é quem consome férias e 13º (no backend e na lei), não o
  // contrário — ver o cabeçalho de RescisaoView.tsx.
  const [categoria, setCategoria] = useState<CategoriaFolha>("todos");
  // O card do topo é o MODO da tela: consultar o mês, lançar, ou resolver o
  // que trava o fechamento. Nasce em "consultar" porque a primeira pergunta
  // de quem abre a tela é "como está o mês", não "o que eu lanço".
  const [cardAtivo, setCardAtivo] = useState<CardFolha>("consultar");
  // Cards de grupo do conteúdo — CONTROLADOS aqui (e não pelo estado interno
  // de cada SecaoRecolhivel) porque "Ver a folha", no painel de exceções,
  // precisa ABRIR o card certo antes de rolar até a linha: com dois níveis de
  // recolhimento, a linha alvo pode estar dentro de um card fechado, e o
  // `getElementById` não acha elemento que não está montado.
  const [gruposAbertos, setGruposAbertos] = useState<Record<string, boolean>>({});
  const [expandedId, setExpandedId] = useState<number | null>(null);
  // Ações do dono sobre um vale que aparece na folha (reparcelar o saldo,
  // abater, desconsiderar o mês, cancelar) — abertas do painel "Descontos de
  // vale" da própria competência, que é onde o dono vê o desconto e decide.
  // Guarda a competência junto porque "desconsiderar o vale neste mês" é
  // sobre a linha de onde o modal foi aberto, não sobre um mês a escolher.
  // `competencia` é OPCIONAL: quando o modal é aberto pelo painel de descontos
  // de uma folha, o mês é o daquela linha; quando é aberto pelo card "Vales de
  // funcionário", a linha é do vale inteiro e quem escolhe o mês é o contexto
  // do servidor (ver AcoesValeModal).
  const [acoesVale, setAcoesVale] = useState<{ valeId: number; pessoaNome: string; competencia?: string } | null>(null);

  // Expansão da linha que NÃO é de funcionário (empreita, contrato, diária,
  // férias/13º) — a folha de funcionário já tinha a sua em `expandedId`.
  // Existe porque o clique no NOME passou a significar "abre o discriminado"
  // em toda a tabela, e essas linhas não tinham expansão nenhuma: férias e
  // 13º chegam do servidor com `detalhe` (o recibo inteiro) e a tela o jogava
  // fora.
  const [expandidaChave, setExpandidaChave] = useState<string | null>(null);

  // Expansão focada de um desconto (folha ou vale) numa linha específica.
  const [expandDesc, setExpandDesc] = useState<{ id: number; tipo: "folha" | "vale" } | null>(null);
  // Folha apontada pelo painel de exceções — pisca em dourado ("é esta, aqui")
  // e volta ao normal sozinha, sem virar destaque permanente.
  const [folhaDestacada, setFolhaDestacada] = useState<number | null>(null);
  // Ficha da pessoa (linha do tempo) — abre pelo clique NO NOME, não na linha:
  // a linha continua abrindo o recibo da competência, que é o trabalho do mês.
  const [fichaPessoaId, setFichaPessoaId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editPessoaId, setEditPessoaId] = useState("");
  const [editCompetencia, setEditCompetencia] = useState("");
  const [editValorBruto, setEditValorBruto] = useState("");
  const [editDescontos, setEditDescontos] = useState("");
  const [editPercentualInss, setEditPercentualInss] = useState("");
  const [editValorInss, setEditValorInss] = useState("");
  const [editInssManual, setEditInssManual] = useState(true);
  const [editPercentualIr, setEditPercentualIr] = useState("");
  const [editValorIr, setEditValorIr] = useState("");
  const [editIrManual, setEditIrManual] = useState(true);
  const [editPercentualFgts, setEditPercentualFgts] = useState("");
  const [editValorFgts, setEditValorFgts] = useState("");
  const [editFgtsManual, setEditFgtsManual] = useState(true);
  const [editPercentualDctf, setEditPercentualDctf] = useState("");
  const [editValorDctf, setEditValorDctf] = useState("");
  const [editDctfManual, setEditDctfManual] = useState(true);
  const [editObservacao, setEditObservacao] = useState("");
  const [editRecorrente, setEditRecorrente] = useState(false);
  const [editDiaVencimento, setEditDiaVencimento] = useState("5");
  const [editContaCorrenteId, setEditContaCorrenteId] = useState("");
  const [editSalvando, setEditSalvando] = useState(false);
  const [editMsg, setEditMsg] = useState<string | null>(null);
  const [editValorVale, setEditValorVale] = useState(0);
  const [editValorLiquidoOriginal, setEditValorLiquidoOriginal] = useState(0);
  const [confirmarDivergenciaFolha, setConfirmarDivergenciaFolha] = useState<RegistroFolha | null>(null);

  // Folha de pagamento unificada — funcionário + empreita + contrato + diária + férias/13º.
  const [unificada, setUnificada] = useState<LinhaFolhaUnificada[] | null>(null);
  const [erroUnificada, setErroUnificada] = useState<string | null>(null);
  const [fUniVencDe, setFUniVencDe] = useState("");
  const [fUniVencAte, setFUniVencAte] = useState("");
  // "Pagos · A pagar · Todos" no lugar do antigo select "Status" (pendente/
  // pago): é o mesmo predicado sob o rótulo que o dono usa, e é o MESMO
  // controle da tela de Contas — ver `filtrarPorSituacao` em lib/holeriteRegras.
  const [situacao, setSituacao] = useState<SituacaoPagamento>("todos");
  const [fUniPessoa, setFUniPessoa] = useState("");
  // Busca livre por pessoa — existia só em Contas > Holerites e recibos
  // ("Buscar pessoa…"), e quem fecha o mês é quem mais precisa dela.
  const [buscaPessoa, setBuscaPessoa] = useState("");
  // O MÊS em tela — o objeto desta tela, e não mais um filtro entre outros.
  // `null` = "todos os meses" (o comportamento antigo, que continua a um
  // clique). Nasce indefinido e é resolvido quando o ledger chega, porque a
  // escolha depende do que existe: mês corrente se ele tiver lançamento,
  // senão o mês mais recente que tiver — abrir a tela vazia por decreto seria
  // pior do que o estado de hoje, em que pelo menos tudo aparece.
  const [mesFolha, setMesFolha] = useState<string | null | undefined>(undefined);
  // Deriva o filtro de tipo do seletor de categoria do topo — não é mais um
  // controle à parte, senão o usuário tinha 2 lugares pra "escolher a
  // categoria" que podiam divergir (o motivo de "não funcionar de verdade").
  const capacidades = CATEGORIAS[categoria];
  // `null` = a categoria não tem ledger (rescisão): não há mês, equação,
  // exceções nem tabela a montar, e a tela dela é outra.
  const temLedger = capacidades.tipoLedger !== null;
  const tipoUnificado = capacidades.tipoLedger ?? "";
  const [excluindoChave, setExcluindoChave] = useState<string | null>(null);
  const [excluirErro, setExcluirErro] = useState<string | null>(null);

  // Deep-link vindo do card "diária de hoje" da Agenda (?ir=folha&categoria=
  // diarias&diaria=<id>&calendario=ultimo_periodo, ver app/financeiro/page.tsx
  // e app/agenda/page.tsx) — abre direto na sub-aba Diária e, se veio um id,
  // já abre o calendário "Dias trabalhados" daquela diarista, sem o usuário
  // ter que caçar a linha na tabela de Controle de diárias.
  // A rescisão entra na MESMA lista: ?ir=folha&categoria=rescisao é o endereço
  // próprio dela — antes não havia como linkar a tela, porque ela era uma
  // sub-aba interna de "ferias_decimo" e o único endereço possível parava no
  // card errado (Férias/13º), com a Rescisão a mais um clique não linkável.
  // Continua sendo `window.location.search` (e não useSearchParams) de
  // propósito: é o padrão já usado aqui e não exige fronteira de Suspense.
  const [deepLinkDiaria, setDeepLinkDiaria] = useState<{ id: number; modo: "ultimo_periodo" | "completo" } | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const cat = params.get("categoria");
    const catNormalizada = cat ? (ALIAS_CATEGORIA[cat] ?? cat) : null;
    if (catNormalizada && catNormalizada in CATEGORIAS) {
      setCategoria(catNormalizada as CategoriaFolha);
    }
    const diariaId = params.get("diaria");
    if (diariaId && !Number.isNaN(Number(diariaId))) {
      const modo = params.get("calendario") === "completo" ? "completo" : "ultimo_periodo";
      setDeepLinkDiaria({ id: Number(diariaId), modo });
    }
  }, []);

  // Contas correntes (id + rótulo) — para o campo "Conta bancária" dos vales,
  // que precisa gravar o id (o backend agora espera conta_corrente_id, não
  // mais o rótulo em texto usado no Financeiro).
  const [contasCorrentes, setContasCorrentes] = useState<ContaCorrenteCadastro[]>([]);

  // Relatório de vales e descontos (vale de funcionário).
  const [vales, setVales] = useState<any[] | null>(null);
  const [fValeDe, setFValeDe] = useState("");
  const [fValeAte, setFValeAte] = useState("");
  const [fValePessoa, setFValePessoa] = useState("");
  const [expandedValeId, setExpandedValeId] = useState<number | null>(null);
  const [editingValeId, setEditingValeId] = useState<number | null>(null);
  const [editValePessoaId, setEditValePessoaId] = useState("");
  const [editValeValorTotal, setEditValeValorTotal] = useState("");
  const [editValeFormaPagamento, setEditValeFormaPagamento] = useState("dinheiro");
  const [editValeDataPagamento, setEditValeDataPagamento] = useState("");
  const [editValeParcelas, setEditValeParcelas] = useState("1");
  const [editValeCompetenciaInicio, setEditValeCompetenciaInicio] = useState("");
  const [editValeObservacao, setEditValeObservacao] = useState("");
  const [editValeNumeroDocumento, setEditValeNumeroDocumento] = useState("");
  const [editValeContaCorrenteId, setEditValeContaCorrenteId] = useState("");
  const [editValeSalvando, setEditValeSalvando] = useState(false);
  const [editValeMsg, setEditValeMsg] = useState<string | null>(null);
  const [excluindoValeId, setExcluindoValeId] = useState<number | null>(null);
  const [excluirValeErro, setExcluirValeErro] = useState<string | null>(null);

  // Edição de UMA parcela de vale (dentro da linha expandida) — separado da
  // edição do vale inteiro (editingValeId acima). ModalDivergenciaVale entra
  // em cena quando o valor digitado diverge do calculado.
  const [editandoParcela, setEditandoParcela] = useState<{ valeId: number; parcelaId: number } | null>(null);
  const [editParcelaValor, setEditParcelaValor] = useState("");
  const [parcelaSalvando, setParcelaSalvando] = useState(false);
  const [parcelaErro, setParcelaErro] = useState<string | null>(null);
  const [divergenciaParcela, setDivergenciaParcela] = useState<{
    vale: any; parcela: any; valorCalculado: number; valorInformado: number;
  } | null>(null);
  const [resultadoDivergencia, setResultadoDivergencia] = useState<{ valorPago: number; valorDesconto: number } | null>(null);
  // Redistribuição livre: total (parcela editada + posteriores) diferente do
  // valor pago no vale — confirma ANTES de salvar (diferente de
  // resultadoDivergencia, que só avisa depois de já ter gravado).
  const [divergenciaTotalParcela, setDivergenciaTotalParcela] = useState<{
    vale: any; parcela: any; valoresItens: Record<number, number>; valorVale: number; valorLancado: number;
  } | null>(null);

  // G15 — exclusão de UMA parcela do vale (endpoint próprio, com
  // reconciliação da folha). Primeiro chamamos sem `confirmar` para colher o
  // payload de divergência do 409 (mesmo padrão de `salvarParcela`/409
  // acima) e só então perguntamos "conceder" ou "redistribuir_igual".
  const [excluindoParcela, setExcluindoParcela] = useState<{
    vale: any; parcela: any; valor_parcela: number; valor_vale: number; soma_apos: number; parcelas_pendentes_posteriores: number;
  } | null>(null);
  const [excluirParcelaSalvando, setExcluirParcelaSalvando] = useState(false);
  const [excluirParcelaErro, setExcluirParcelaErro] = useState<string | null>(null);

  // Vale avulso (Empreitada/Contrato/Diária) — mesma seção de relatório, tabela própria.
  const [valesAvulsos, setValesAvulsos] = useState<any[] | null>(null);
  const [expandedValeAvulsoId, setExpandedValeAvulsoId] = useState<number | null>(null);
  const [editingValeAvulsoId, setEditingValeAvulsoId] = useState<number | null>(null);
  const [editValeAvulsoValor, setEditValeAvulsoValor] = useState("");
  const [editValeAvulsoFormaPagamento, setEditValeAvulsoFormaPagamento] = useState("dinheiro");
  const [editValeAvulsoDataPagamento, setEditValeAvulsoDataPagamento] = useState("");
  const [editValeAvulsoContaCorrenteId, setEditValeAvulsoContaCorrenteId] = useState("");
  const [editValeAvulsoObservacao, setEditValeAvulsoObservacao] = useState("");
  const [editValeAvulsoSalvando, setEditValeAvulsoSalvando] = useState(false);
  const [editValeAvulsoMsg, setEditValeAvulsoMsg] = useState<string | null>(null);
  const [excluindoValeAvulsoId, setExcluindoValeAvulsoId] = useState<number | null>(null);
  const [excluirValeAvulsoErro, setExcluirValeAvulsoErro] = useState<string | null>(null);
  const [divergenciaValeAvulso, setDivergenciaValeAvulso] = useState<{
    v: any; valorCalculado: number; valorInformado: number;
  } | null>(null);

  const [guias, setGuias] = useState<GuiaFolhaEncargo[] | null>(null);
  // Edição/exclusão de guia de FGTS/DCTF já lançada — mesmo padrão de
  // editingValeId/excluindoValeId, sem parcelas (a guia é um registro só).
  const [editingGuiaId, setEditingGuiaId] = useState<number | null>(null);
  const [editGuiaTipo, setEditGuiaTipo] = useState<"fgts" | "dctf">("fgts");
  const [editGuiaCompetencia, setEditGuiaCompetencia] = useState("");
  const [editGuiaCodigoReceita, setEditGuiaCodigoReceita] = useState("");
  const [editGuiaValorPrincipal, setEditGuiaValorPrincipal] = useState("");
  const [editGuiaValorMulta, setEditGuiaValorMulta] = useState("");
  const [editGuiaValorJuros, setEditGuiaValorJuros] = useState("");
  const [editGuiaDataVencimento, setEditGuiaDataVencimento] = useState("");
  const [editGuiaLinhaDigitavel, setEditGuiaLinhaDigitavel] = useState("");
  const [editGuiaMsg, setEditGuiaMsg] = useState<string | null>(null);
  const [editGuiaSalvando, setEditGuiaSalvando] = useState(false);
  const [excluindoGuiaId, setExcluindoGuiaId] = useState<number | null>(null);
  const [excluirGuiaErro, setExcluirGuiaErro] = useState<string | null>(null);
  const carregar = () => fetchFolhaPagamento().then(setRegs).catch((e) => setError(e.message));
  const carregarUnificada = () => fetchFolhaPagamentoUnificada().then(setUnificada).catch((e) => setErroUnificada(e.message));
  const carregarVales = () => fetchVales().then(setVales).catch(() => {});
  const carregarValesAvulsos = () => fetchValesAvulsos().then(setValesAvulsos).catch(() => {});
  const carregarGuias = () => fetchGuiasFolhaEncargo().then(setGuias).catch(() => {});
  useEffect(() => {
    carregar(); carregarUnificada(); carregarVales(); carregarValesAvulsos(); carregarGuias();
    fetchPessoas().then(setPessoas).catch(() => {});
    fetchContasCorrentes().then(setContasCorrentes).catch(() => {});
  }, []);

  // Rótulo da conta bancária de um vale, a partir do conta_corrente_id salvo
  // — "—" tanto para vale sem conta (desconto integral/próximo pagamento)
  // quanto para uma conta que não foi encontrada na lista carregada.
  const rotuloContaVale = (contaCorrenteId: number | null | undefined) =>
    contasCorrentes.find((c) => c.id === contaCorrenteId)?.rotulo || "—";

  async function excluirLinha(linha: LinhaFolhaUnificada) {
    const chave = `${linha.tipo}-${linha.origem_subtipo}-${linha.origem_id}`;
    setExcluirErro(null);
    setExcluindoChave(chave);
    try {
      if (linha.tipo === "funcionario") await excluirFolhaPagamento(linha.origem_id);
      else if (linha.tipo === "empreita" && linha.origem_subtipo === "parcela") await excluirParcelaEmpreitada(linha.origem_id);
      else if (linha.tipo === "contrato" && linha.origem_subtipo === "parcela") await excluirParcelaContrato(linha.origem_id);
      else return;
      carregar(); carregarUnificada();
    } catch (e: any) {
      setExcluirErro(e.message || "Erro ao excluir lançamento");
    } finally {
      setExcluindoChave(null);
    }
  }

  // Editar parcela de Empreita/Contrato diretamente na Folha de pagamento
  // unificada — mesma UX de "Editar lançamento" já usada para funcionário.
  const [editingLinhaChave, setEditingLinhaChave] = useState<string | null>(null);
  const [editLinhaData, setEditLinhaData] = useState("");
  const [editLinhaValor, setEditLinhaValor] = useState("");
  const [editLinhaMsg, setEditLinhaMsg] = useState<string | null>(null);
  const [salvandoLinha, setSalvandoLinha] = useState(false);

  // ── Cards de grupo (o 1º nível de recolhimento do conteúdo) ─────────────
  // Só o ledger nasce aberto: é o que responde "como está o mês". Guias e
  // vales são conferência, e abrem quando o dono pergunta por eles.
  const GRUPO_LEDGER = "ledger";
  const PADRAO_ABERTO: Record<string, boolean> = { [GRUPO_LEDGER]: true };
  const grupoAberto = (id: string) => gruposAbertos[id] ?? PADRAO_ABERTO[id] ?? false;
  const alternarGrupo = (id: string) => setGruposAbertos((g) => ({ ...g, [id]: !grupoAberto(id) }));

  /**
   * O que a ação de uma exceção faz: abre a folha envolvida com a
   * discriminação à vista e rola até ela, piscando a linha. O painel não
   * conserta nada por conta própria — apontar o lançamento é o serviço, e
   * quem decide o que fazer com ele continua sendo o dono. Quando a exceção
   * não tem folha (vencidos que são só empreita/contrato/diária), rola até a
   * tabela, que é onde estão os lançamentos em questão.
   *
   * ABRIR ANTES DE ROLAR é obrigatório desde que a tela ganhou dois níveis de
   * recolhimento: o painel de exceções mora no card "Resolver antes de
   * fechar" e a linha alvo mora dentro do card do ledger, que pode estar
   * fechado — e o `getElementById` não acha o que não está montado. Por isso
   * a função troca o card do topo, abre o grupo, expande a linha e só então
   * rola, dois quadros depois (um para o React pintar o card novo, outro para
   * a expansão da linha entrar na altura final).
   */
  function irParaExcecao(excecao: Excecao) {
    const reduzMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    setCardAtivo("consultar");
    setGruposAbertos((g) => ({ ...g, [GRUPO_LEDGER]: true }));
    const alvo = excecao.folhaIds[0];
    if (alvo != null) {
      setExpandedId(alvo);
      setFolhaDestacada(alvo);
    }
    const seletor = alvo == null ? "folha-tabela" : `folha-linha-${alvo}`;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      document.getElementById(seletor)?.scrollIntoView({
        behavior: reduzMovimento ? "auto" : "smooth", block: alvo == null ? "start" : "center",
      });
    }));
    // O pisco é de 0,6s (.flash-localizado); tirar a classe depois disso é o
    // que permite piscar de novo se o usuário clicar na mesma exceção.
    if (alvo != null) window.setTimeout(() => setFolhaDestacada(null), 900);
  }

  function podeEditarLinha(l: LinhaFolhaUnificada) {
    return l.status !== "pago" && l.origem_subtipo === "parcela" && (l.tipo === "empreita" || l.tipo === "contrato");
  }

  function iniciarEdicaoLinha(l: LinhaFolhaUnificada) {
    setEditingLinhaChave(`${l.tipo}-${l.origem_subtipo}-${l.origem_id}`);
    setEditLinhaData(l.data_vencimento || "");
    setEditLinhaValor(String(l.valor));
    setEditLinhaMsg(null);
  }

  async function salvarEdicaoLinha(l: LinhaFolhaUnificada) {
    setEditLinhaMsg(null);
    if (!editLinhaValor || parseFloat(editLinhaValor) <= 0) { setEditLinhaMsg("Informe o valor."); return; }
    setSalvandoLinha(true);
    try {
      const dados = { data_vencimento: editLinhaData, valor: parseFloat(editLinhaValor) };
      if (l.tipo === "empreita") await atualizarParcelaEmpreitada(l.origem_id, dados);
      else await atualizarParcelaContrato(l.origem_id, dados);
      setEditingLinhaChave(null);
      carregarUnificada();
    } catch (e: any) {
      setEditLinhaMsg(e.message || "Erro ao editar lançamento.");
    } finally {
      setSalvandoLinha(false);
    }
  }

  // O mês em tela é DERIVADO, não inicializado por efeito: enquanto o usuário
  // não escolher um mês (`mesFolha === undefined`), vale o que `mesInicial`
  // decide a partir do ledger que chegou. Guardar isso com um `setState`
  // dentro de `useEffect` daria uma renderização em cascata — e um quadro
  // inteiro em que a tela mostra "todos os meses" antes de assentar no mês.
  const mesesComLancamento = useMemo(() => mesesDoLedger(unificada || []), [unificada]);
  const mesEmTela = mesFolha === undefined
    ? (unificada ? mesInicial(unificada, new Date().toISOString().slice(0, 7)) : null)
    : mesFolha;

  const unificadaFiltrada = useMemo(() => {
    const alvo = buscaPessoa.trim().toLowerCase();
    return filtrarPorSituacao((unificada || []).filter((l) =>
      (!mesEmTela || mesDaLinha(l) === mesEmTela) &&
      (!fUniVencDe || (l.data_vencimento || "") >= fUniVencDe) &&
      (!fUniVencAte || (l.data_vencimento || "") <= fUniVencAte) &&
      (!fUniPessoa || String(l.pessoa_id) === fUniPessoa) &&
      (!alvo || l.pessoa_nome.toLowerCase().includes(alvo)) &&
      (!tipoUnificado || l.tipo === tipoUnificado)
    ), situacao);
  }, [unificada, mesEmTela, fUniVencDe, fUniVencAte, situacao, fUniPessoa, buscaPessoa, tipoUnificado]);
  // A equação, o resumo dos outros tipos e as exceções saem TODOS da mesma
  // lista já filtrada — nenhum deles recalcula o recorte por conta própria.
  const equacao = useMemo(() => equacaoDoMes(unificadaFiltrada), [unificadaFiltrada]);
  const outrosTipos = useMemo(() => resumoOutrosTipos(unificadaFiltrada), [unificadaFiltrada]);
  const excecoes = useMemo(() => excecoesDoMes(unificadaFiltrada), [unificadaFiltrada]);
  const situacaoMes = useMemo(() => situacaoDoMes(unificadaFiltrada, excecoes), [unificadaFiltrada, excecoes]);
  const competenciasEmTela = useMemo(() => competenciasDoMes(unificadaFiltrada), [unificadaFiltrada]);
  const { linhasOrdenadas: unificadaOrdenada, coluna: uniColuna, dir: uniDir, ordenar: uniOrdenar } = useOrdenacao(unificadaFiltrada);
  const somaUnificadaFiltrada = unificadaFiltrada.reduce((a, l) => a + l.valor, 0);
  // Uma folha em que os descontos passam os vencimentos tem líquido NEGATIVO —
  // e, somada aqui, REDUZIA o total a pagar do mês: o erro se disfarçava de
  // bom número. Sai da soma e vira um número próprio, em valor absoluto.
  const uniBloqueadas = unificadaFiltrada.filter((l) => l.valor < 0);
  const somaUniBloqueada = uniBloqueadas.reduce((a, l) => a + Math.abs(l.valor), 0);
  const somaUniPendente = unificadaFiltrada
    .filter((l) => l.status === "pendente" && l.valor >= 0)
    .reduce((a, l) => a + l.valor, 0);
  const somaUniPago = unificadaFiltrada.filter((l) => l.status === "pago").reduce((a, l) => a + l.valor, 0);

  const valesFiltrados = useMemo(() => (vales || []).filter((v: any) =>
    (!fValeDe || v.data_pagamento >= fValeDe) &&
    (!fValeAte || v.data_pagamento <= fValeAte) &&
    (!fValePessoa || String(v.pessoa_id) === fValePessoa)
  ).map((v: any) => {
    const parcelas: any[] = v.parcelas_detalhe || [];
    const valorParcela = parcelas.length ? parcelas[0].valor : (v.parcelas ? v.valor_total / v.parcelas : v.valor_total);
    const aplicadas = parcelas.filter((p) => p.aplicada).length;
    const valorPago = parcelas.filter((p) => p.aplicada).reduce((a, p) => a + p.valor, 0);
    return {
      ...v, valor_parcela: valorParcela, valor_pago: valorPago,
      status_desconto: aplicadas === 0 ? "Pendente" : (aplicadas === parcelas.length ? "Concluído" : `${aplicadas}/${parcelas.length} aplicadas`),
    };
  }), [vales, fValeDe, fValeAte, fValePessoa]);
  const { linhasOrdenadas: valesOrdenados, coluna: valeColuna, dir: valeDir, ordenar: valeOrdenar } = useOrdenacao(valesFiltrados);

  function iniciarEdicaoVale(v: any) {
    setEditingValeId(v.id);
    setExpandedValeId(v.id);
    setEditValePessoaId(String(v.pessoa_id));
    setEditValeValorTotal(String(v.valor_total));
    setEditValeFormaPagamento(v.forma_pagamento);
    setEditValeDataPagamento(v.data_pagamento);
    setEditValeParcelas(String(v.parcelas));
    setEditValeCompetenciaInicio(v.competencia_inicio);
    setEditValeObservacao(v.observacao || "");
    setEditValeNumeroDocumento(v.numero_documento_pagamento || "");
    setEditValeContaCorrenteId(v.conta_corrente_id ? String(v.conta_corrente_id) : "");
    setEditValeMsg(null);
  }

  async function salvarEdicaoVale(valeId: number, confirmar = false) {
    setEditValeMsg(null);
    if (!editValePessoaId) { setEditValeMsg("Selecione a pessoa."); return; }
    if (!editValeValorTotal || parseFloat(editValeValorTotal) <= 0) { setEditValeMsg("Informe o valor do vale."); return; }
    if (!editValeParcelas || Number(editValeParcelas) < 1) { setEditValeMsg("Informe ao menos 1 parcela."); return; }
    if (contaObrigatoriaVale(editValeFormaPagamento) && !editValeContaCorrenteId) {
      setEditValeMsg("Selecione a conta bancária de onde sai o vale."); return;
    }
    setEditValeSalvando(true);
    try {
      await atualizarVale(valeId, {
        pessoa_id: Number(editValePessoaId), valor_total: parseFloat(editValeValorTotal), forma_pagamento: editValeFormaPagamento,
        data_pagamento: editValeDataPagamento, parcelas: Number(editValeParcelas), competencia_inicio: editValeCompetenciaInicio,
        observacao: editValeObservacao || undefined, numero_documento_pagamento: editValeNumeroDocumento || undefined,
        conta_corrente_id: contaObrigatoriaVale(editValeFormaPagamento) && editValeContaCorrenteId ? Number(editValeContaCorrenteId) : undefined,
        confirmar,
      });
      setEditingValeId(null);
      setExpandedValeId(null);
      carregarVales(); carregar(); carregarUnificada();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.competencias_excedidas) {
        const lista = e.detail.competencias_excedidas.map((c: any) => `${c.competencia} (R$ ${c.total.toFixed(2)})`).join(", ");
        if (window.confirm(`${e.detail.mensagem}\n\nCompetências afetadas: ${lista}\n\nDeseja salvar mesmo assim?`)) {
          await salvarEdicaoVale(valeId, true);
          return;
        }
      } else {
        setEditValeMsg(e.message || "Erro ao editar vale");
      }
    } finally {
      setEditValeSalvando(false);
    }
  }

  function abrirEdicaoParcela(vale: any, parcela: any) {
    setEditandoParcela({ valeId: vale.id, parcelaId: parcela.id });
    setEditParcelaValor(String(parcela.valor));
    setParcelaErro(null);
  }

  async function salvarParcela(
    vale: any, parcela: any, acao?: "conceder" | "redistribuir_igual" | "redistribuir_livre",
    valoresItens?: Record<number, number>, confirmarDivergenciaTotal?: boolean,
    confirmarTeto?: boolean,
  ) {
    const valor = parseFloat(editParcelaValor);
    if (isNaN(valor) || valor < 0) { setParcelaErro("Informe um valor válido."); return; }
    setParcelaSalvando(true);
    setParcelaErro(null);
    try {
      const resultado = await atualizarParcelaVale(vale.id, parcela.id, {
        valor, acao, valores_parcelas: valoresItens, confirmar: !!acao,
        confirmar_divergencia_total: !!confirmarDivergenciaTotal,
        confirmar_teto: !!confirmarTeto,
      });
      setEditandoParcela(null);
      setDivergenciaParcela(null);
      setDivergenciaTotalParcela(null);
      if (resultado.diverge_valor_pago) {
        setResultadoDivergencia({ valorPago: vale.valor_total, valorDesconto: resultado.soma_parcelas_atual });
      }
      carregarVales(); carregar(); carregarUnificada();
    } catch (e: any) {
      // Duas divergências distintas, cada uma com seu próprio popup:
      // 1) valor_vale/valor_lancado — total final (redistribuir_livre) ≠ valor pago no vale.
      // 2) valor_calculado/valor_informado — o valor desta parcela ≠ o que estava calculado.
      // 3) o teto de 40% do salário na competência — o aviso que faltava nesta
      // porta: editar uma parcela para o valor cheio concentrava num mês só um
      // desconto acima do limite legal, em silêncio. Confirmável, como nas
      // outras portas do vale (criar/editar o vale inteiro).
      if (e.status === 409 && e.detail?.competencias_excedidas) {
        const lista = e.detail.competencias_excedidas.map((c: any) => `${c.competencia} (R$ ${c.total.toFixed(2)})`).join(", ");
        if (window.confirm(`${e.detail.mensagem}\n\nCompetências afetadas: ${lista}\n\nDeseja salvar mesmo assim?`)) {
          await salvarParcela(vale, parcela, acao, valoresItens, confirmarDivergenciaTotal, true);
          return;
        }
      } else if (e.status === 409 && e.detail?.valor_vale !== undefined) {
        setDivergenciaTotalParcela({
          vale, parcela, valoresItens: valoresItens || {}, valorVale: e.detail.valor_vale, valorLancado: e.detail.valor_lancado,
        });
      } else if (e.status === 409 && e.detail?.diferenca !== undefined) {
        setDivergenciaParcela({
          vale, parcela, valorCalculado: e.detail.valor_calculado, valorInformado: e.detail.valor_informado,
        });
      } else {
        setParcelaErro(e.message || "Erro ao editar parcela");
      }
    } finally {
      setParcelaSalvando(false);
    }
  }

  async function pedirExcluirParcela(vale: any, parcela: any) {
    setExcluirParcelaErro(null);
    try {
      // Sem `confirmar`: o backend sempre responde 409 (payload de
      // divergência) — nunca apaga direto daqui.
      await excluirParcelaVale(vale.id, parcela.id);
    } catch (e: any) {
      if (e.status === 409 && e.detail?.valor_parcela !== undefined) {
        setExcluindoParcela({ vale, parcela, ...e.detail });
      } else {
        setExcluirParcelaErro(e.message || "Erro ao excluir parcela");
      }
    }
  }

  async function confirmarExcluirParcela(acao: "conceder" | "redistribuir_igual") {
    if (!excluindoParcela) return;
    setExcluirParcelaSalvando(true);
    setExcluirParcelaErro(null);
    try {
      await excluirParcelaVale(excluindoParcela.vale.id, excluindoParcela.parcela.id, { acao, confirmar: true });
      setExcluindoParcela(null);
      carregarVales(); carregar(); carregarUnificada();
    } catch (e: any) {
      setExcluirParcelaErro(e.message || "Erro ao excluir parcela");
    } finally {
      setExcluirParcelaSalvando(false);
    }
  }

  // EXCLUIR ≠ CANCELAR. Excluir é para o vale que NUNCA DEVERIA TER EXISTIDO
  // (valor errado, pessoa errada, duplicado): apaga o vale E a saída de caixa
  // que ele criou no Financeiro. Para o vale que aconteceu e só não vai mais
  // ser cobrado do funcionário, a porta é "Cancelar o vale" (painel de ações),
  // que mantém a saída de caixa no extrato e pode ser desfeita. Por isso o
  // diálogo pergunta com o lançamento NOMEADO (LC-..., valor e data) e diz, em
  // uma linha, qual é a outra porta — os dois textos vêm do backend, que é
  // quem sabe qual lançamento existe e o que ele tem dentro.
  async function excluirValeHandler(v: any) {
    setExcluirValeErro(null);
    // O botão já fica travado durante a CONSULTA da prévia, não só durante a
    // exclusão: sem isso, dois cliques seguidos abrem dois diálogos.
    setExcluindoValeId(v.id);
    let previa: PreviaExclusaoVale;
    try {
      previa = await previaExclusaoVale(v.id);
    } catch (e: any) {
      setExcluirValeErro(e.message || "Erro ao conferir o vale");
      setExcluindoValeId(null);
      return;
    }
    // Recusa do backend (comprovante anexado, folha paga, valor acertado à
    // mão no Financeiro...): mostra o motivo em vez de perguntar algo que já
    // se sabe que vai dar erro.
    if (!previa.pode_excluir) {
      setExcluirValeErro(previa.impedimento || "Este vale não pode ser excluído.");
      setExcluindoValeId(null);
      return;
    }
    if (!window.confirm(`${previa.confirmacao}\n\n${previa.alternativa}`)) { setExcluindoValeId(null); return; }
    try {
      await excluirVale(v.id);
      if (expandedValeId === v.id) setExpandedValeId(null);
      carregarVales(); carregar(); carregarUnificada();
    } catch (e: any) {
      setExcluirValeErro(e.message || "Erro ao excluir vale");
    } finally {
      setExcluindoValeId(null);
    }
  }

  // Edição/exclusão de guia de FGTS/DCTF já lançada — mesmo padrão de
  // iniciarEdicaoVale/salvarEdicaoVale/excluirValeHandler acima.
  function iniciarEdicaoGuia(g: GuiaFolhaEncargo) {
    setEditingGuiaId(g.id);
    setEditGuiaTipo(g.tipo);
    setEditGuiaCompetencia(g.competencia);
    setEditGuiaCodigoReceita(g.codigo_receita || "");
    setEditGuiaValorPrincipal(String(g.valor_principal));
    setEditGuiaValorMulta(String(g.valor_multa || 0));
    setEditGuiaValorJuros(String(g.valor_juros || 0));
    setEditGuiaDataVencimento(g.data_vencimento);
    setEditGuiaLinhaDigitavel(g.linha_digitavel || "");
    setEditGuiaMsg(null);
  }

  async function salvarEdicaoGuia(guiaId: number) {
    setEditGuiaMsg(null);
    if (!editGuiaCompetencia) { setEditGuiaMsg("Informe a competência."); return; }
    if (!editGuiaValorPrincipal || parseFloat(editGuiaValorPrincipal) < 0) { setEditGuiaMsg("Informe o valor principal."); return; }
    if (!editGuiaDataVencimento) { setEditGuiaMsg("Informe o vencimento."); return; }
    setEditGuiaSalvando(true);
    try {
      await atualizarGuiaFolhaEncargo(guiaId, {
        tipo: editGuiaTipo, competencia: editGuiaCompetencia,
        codigo_receita: editGuiaTipo === "dctf" ? (editGuiaCodigoReceita || undefined) : undefined,
        valor_principal: parseFloat(editGuiaValorPrincipal),
        valor_multa: parseFloat(editGuiaValorMulta) || 0,
        valor_juros: parseFloat(editGuiaValorJuros) || 0,
        data_vencimento: editGuiaDataVencimento,
        linha_digitavel: editGuiaLinhaDigitavel || undefined,
      });
      setEditingGuiaId(null);
      carregarGuias(); carregarUnificada();
    } catch (e: any) {
      setEditGuiaMsg(e.message || "Erro ao editar guia");
    } finally {
      setEditGuiaSalvando(false);
    }
  }

  async function excluirGuiaHandler(g: GuiaFolhaEncargo) {
    if (!window.confirm(`Excluir a guia de ${g.tipo === "fgts" ? "FGTS" : "DCTF"} de ${mesCompLabel(g.competencia)}? A conta a pagar vinculada também será excluída.`)) return;
    setExcluirGuiaErro(null);
    setExcluindoGuiaId(g.id);
    try {
      await excluirGuiaFolhaEncargo(g.id);
      if (editingGuiaId === g.id) setEditingGuiaId(null);
      carregarGuias(); carregarUnificada();
    } catch (e: any) {
      setExcluirGuiaErro(e.message || "Erro ao excluir guia");
    } finally {
      setExcluindoGuiaId(null);
    }
  }

  const ordGuias = useOrdenacao(guias ?? []);

  const valesAvulsosFiltrados = useMemo(() => (valesAvulsos || []).filter((v: any) =>
    (!fValeDe || v.data_pagamento >= fValeDe) &&
    (!fValeAte || v.data_pagamento <= fValeAte) &&
    (!fValePessoa || String(v.pessoa_id) === fValePessoa)
  ), [valesAvulsos, fValeDe, fValeAte, fValePessoa]);
  const { linhasOrdenadas: valesAvulsosOrdenados, coluna: valeAvulsoColuna, dir: valeAvulsoDir, ordenar: valeAvulsoOrdenar } = useOrdenacao(valesAvulsosFiltrados);

  function iniciarEdicaoValeAvulso(v: any) {
    setEditingValeAvulsoId(v.id);
    setExpandedValeAvulsoId(v.id);
    setEditValeAvulsoValor(String(v.valor));
    setEditValeAvulsoFormaPagamento(v.forma_pagamento);
    setEditValeAvulsoDataPagamento(v.data_pagamento);
    setEditValeAvulsoContaCorrenteId(v.conta_corrente_id ? String(v.conta_corrente_id) : "");
    setEditValeAvulsoObservacao(v.observacao || "");
    setEditValeAvulsoMsg(null);
  }

  async function salvarEdicaoValeAvulso(
    v: any, acao?: "conceder" | "redistribuir_igual" | "redistribuir_livre", valoresItens?: Record<number, number>,
  ) {
    setEditValeAvulsoMsg(null);
    if (!editValeAvulsoValor || parseFloat(editValeAvulsoValor) <= 0) { setEditValeAvulsoMsg("Informe o valor do vale."); return; }
    if (contaObrigatoriaValeAvulso(editValeAvulsoFormaPagamento) && !editValeAvulsoContaCorrenteId) {
      setEditValeAvulsoMsg("Selecione a conta bancária de onde sai o vale."); return;
    }
    setEditValeAvulsoSalvando(true);
    try {
      await atualizarValeAvulso(v.id, {
        origem_tipo: v.origem_tipo, origem_id: v.origem_id, valor: parseFloat(editValeAvulsoValor),
        forma_pagamento: editValeAvulsoFormaPagamento, data_pagamento: editValeAvulsoDataPagamento,
        conta_corrente_id: contaObrigatoriaValeAvulso(editValeAvulsoFormaPagamento) && editValeAvulsoContaCorrenteId
          ? Number(editValeAvulsoContaCorrenteId) : undefined,
        observacao: editValeAvulsoObservacao || undefined, acao, valores_itens: valoresItens, confirmar: !!acao,
      });
      setEditingValeAvulsoId(null);
      setExpandedValeAvulsoId(null);
      setDivergenciaValeAvulso(null);
      carregarValesAvulsos(); carregarUnificada();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.diferenca !== undefined) {
        setDivergenciaValeAvulso({ v, valorCalculado: e.detail.valor_calculado, valorInformado: e.detail.valor_informado });
      } else {
        setEditValeAvulsoMsg(e.message || "Erro ao editar vale");
      }
    } finally {
      setEditValeAvulsoSalvando(false);
    }
  }

  // Mesmo desenho do vale de funcionário acima (ver o comentário lá): o
  // diálogo nomeia a saída de caixa que vai junto e diz qual é a alternativa
  // — aqui, editar o vale, porque "cancelar o vale" é ação do vale de
  // funcionário e não existe para o avulso.
  async function excluirValeAvulsoHandler(v: any) {
    setExcluirValeAvulsoErro(null);
    setExcluindoValeAvulsoId(v.id);
    let previa: PreviaExclusaoVale;
    try {
      previa = await previaExclusaoValeAvulso(v.id);
    } catch (e: any) {
      setExcluirValeAvulsoErro(e.message || "Erro ao conferir o vale");
      setExcluindoValeAvulsoId(null);
      return;
    }
    if (!previa.pode_excluir) {
      setExcluirValeAvulsoErro(previa.impedimento || "Este vale não pode ser excluído.");
      setExcluindoValeAvulsoId(null);
      return;
    }
    if (!window.confirm(`${previa.confirmacao}\n\n${previa.alternativa}`)) { setExcluindoValeAvulsoId(null); return; }
    try {
      await excluirValeAvulso(v.id);
      if (expandedValeAvulsoId === v.id) setExpandedValeAvulsoId(null);
      carregarValesAvulsos(); carregarUnificada();
    } catch (e: any) {
      setExcluirValeAvulsoErro(e.message || "Erro ao excluir vale");
    } finally {
      setExcluindoValeAvulsoId(null);
    }
  }

  useEffect(() => {
    if (inssManual) return;
    const novo = arredonda2((parseFloat(valorBruto) || 0) * (parseFloat(percentualInss) || 0) / 100);
    setValorInss(novo ? String(novo) : "");
  }, [valorBruto, percentualInss, inssManual]);
  useEffect(() => {
    if (irManual) return;
    const novo = arredonda2((parseFloat(valorBruto) || 0) * (parseFloat(percentualIr) || 0) / 100);
    setValorIr(novo ? String(novo) : "");
  }, [valorBruto, percentualIr, irManual]);
  useEffect(() => {
    if (editInssManual) return;
    const novo = arredonda2((parseFloat(editValorBruto) || 0) * (parseFloat(editPercentualInss) || 0) / 100);
    setEditValorInss(novo ? String(novo) : "");
  }, [editValorBruto, editPercentualInss, editInssManual]);
  useEffect(() => {
    if (editIrManual) return;
    const novo = arredonda2((parseFloat(editValorBruto) || 0) * (parseFloat(editPercentualIr) || 0) / 100);
    setEditValorIr(novo ? String(novo) : "");
  }, [editValorBruto, editPercentualIr, editIrManual]);
  useEffect(() => {
    if (editFgtsManual) return;
    const novo = arredonda2((parseFloat(editValorBruto) || 0) * (parseFloat(editPercentualFgts) || 0) / 100);
    setEditValorFgts(novo ? String(novo) : "");
  }, [editValorBruto, editPercentualFgts, editFgtsManual]);
  useEffect(() => {
    if (editDctfManual) return;
    const novo = arredonda2((parseFloat(editValorBruto) || 0) * (parseFloat(editPercentualDctf) || 0) / 100);
    setEditValorDctf(novo ? String(novo) : "");
  }, [editValorBruto, editPercentualDctf, editDctfManual]);

  const valorLiquido = useMemo(
    () => (parseFloat(valorBruto) || 0) - (parseFloat(descontos) || 0) - (parseFloat(valorInss) || 0) - (parseFloat(valorIr) || 0),
    [valorBruto, descontos, valorInss, valorIr]
  );
  const editValorLiquido = useMemo(
    () => (parseFloat(editValorBruto) || 0) - (parseFloat(editDescontos) || 0) - (parseFloat(editValorInss) || 0) - (parseFloat(editValorIr) || 0) - editValorVale,
    [editValorBruto, editDescontos, editValorInss, editValorIr, editValorVale]
  );

  async function salvar() {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a pessoa." }); return; }
    if (!competencia) { setMsg({ tipo: "erro", texto: "Informe o mês de competência." }); return; }
    if (!valorBruto || parseFloat(valorBruto) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor bruto." }); return; }
    if (recorrente && (!diaVencimento || Number(diaVencimento) < 1 || Number(diaVencimento) > 28)) {
      setMsg({ tipo: "erro", texto: "Informe o dia de vencimento (1 a 28) para lançamentos recorrentes." }); return;
    }
    setSalvando(true);
    try {
      await criarFolhaPagamento({
        pessoa_id: Number(pessoaId), competencia, valor_bruto: parseFloat(valorBruto),
        descontos: parseFloat(descontos) || 0,
        percentual_inss: parseFloat(percentualInss) || 0, percentual_ir: parseFloat(percentualIr) || 0,
        valor_inss: parseFloat(valorInss) || 0, valor_ir: parseFloat(valorIr) || 0,
        observacao: observacao || undefined,
        recorrente, dia_vencimento: recorrente ? Number(diaVencimento) : null,
        conta_corrente_id: contaCorrenteId ? Number(contaCorrenteId) : undefined,
      });
      setMsg({
        tipo: "sucesso",
        texto: recorrente
          ? "Lançamento de folha criado — as próximas competências serão geradas automaticamente em Contas a Pagar."
          : "Lançamento de folha criado.",
      });
      setPessoaId(""); setValorBruto(""); setDescontos(""); setObservacao(""); setRecorrente(false); setDiaVencimento("5"); setContaCorrenteId("");
      setPercentualInss(""); setValorInss(""); setInssManual(false);
      setPercentualIr(""); setValorIr(""); setIrManual(false);
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar folha" });
    } finally {
      setSalvando(false);
    }
  }

  /**
   * Estornar o pagamento — a porta de saída que faltava.
   *
   * `POST /cadastro/folha-pagamento/{id}/estornar` existe desde o C7 e nenhuma
   * tela o chamava: o holerite mandava o usuário "estornar o pagamento para
   * acrescentar ou corrigir vencimentos e descontos" e não havia botão nenhum.
   * Só admin: o estorno desfaz a baixa da conta a pagar e DESCONGELA a
   * discriminação de um recibo já emitido.
   */
  const [estornandoId, setEstornandoId] = useState<number | null>(null);
  const [estornoErro, setEstornoErro] = useState<string | null>(null);
  async function estornarFolha(r: RegistroFolha) {
    if (!window.confirm(
      `Estornar o pagamento da folha de ${r.pessoa_nome} (${mesCompLabel(r.competencia)})?\n\n`
      + "A baixa da conta a pagar é desfeita, o lançamento volta a \"pendente\" e o recibo "
      + "volta a ser calculado ao vivo — podendo mudar se houver vale ou rubrica pendente.",
    )) return;
    setEstornoErro(null);
    setEstornandoId(r.id);
    try {
      await estornarPagamentoFolha(r.id);
      carregar(); carregarUnificada();
    } catch (e: any) {
      setEstornoErro(e.message || "Erro ao estornar o pagamento da folha");
    } finally {
      setEstornandoId(null);
    }
  }

  function iniciarEdicao(r: RegistroFolha) {
    setEditingId(r.id);
    setExpandedId(r.id);
    setEditPessoaId(String(r.pessoa_id));
    setEditCompetencia(r.competencia);
    setEditValorBruto(String(r.valor_bruto));
    setEditDescontos(String(r.descontos));
    setEditPercentualInss(r.percentual_inss ? String(r.percentual_inss) : "");
    setEditValorInss(r.valor_inss ? String(r.valor_inss) : "");
    setEditInssManual(true);
    setEditPercentualIr(r.percentual_ir ? String(r.percentual_ir) : "");
    setEditValorIr(r.valor_ir ? String(r.valor_ir) : "");
    setEditIrManual(true);
    setEditPercentualFgts(r.percentual_fgts != null ? String(r.percentual_fgts) : "");
    setEditValorFgts(r.valor_fgts != null ? String(r.valor_fgts) : "");
    setEditFgtsManual(true);
    setEditPercentualDctf(r.percentual_dctf != null ? String(r.percentual_dctf) : "");
    setEditValorDctf(r.valor_dctf != null ? String(r.valor_dctf) : "");
    setEditDctfManual(true);
    setEditObservacao(r.observacao || "");
    setEditRecorrente(r.recorrente);
    setEditDiaVencimento(r.dia_vencimento ? String(r.dia_vencimento) : "5");
    setEditContaCorrenteId(r.conta_corrente_id ? String(r.conta_corrente_id) : "");
    setEditValorVale(arredonda2(r.valor_vale || 0));
    setEditValorLiquidoOriginal(r.valor_liquido);
    setEditMsg(null);
  }

  function pedirSalvarEdicao(r: RegistroFolha) {
    if (Math.abs(editValorLiquido - editValorLiquidoOriginal) > 0.005) {
      setConfirmarDivergenciaFolha(r);
    } else {
      salvarEdicao(r);
    }
  }

  async function salvarEdicao(r: RegistroFolha) {
    setEditMsg(null);
    if (!editPessoaId || !editCompetencia || !editValorBruto || parseFloat(editValorBruto) <= 0) {
      setEditMsg("Preencha pessoa, competência e valor bruto.");
      return;
    }
    setEditSalvando(true);
    try {
      await atualizarFolhaPagamento(r.id, {
        pessoa_id: Number(editPessoaId), competencia: editCompetencia, valor_bruto: parseFloat(editValorBruto) || 0,
        descontos: parseFloat(editDescontos) || 0,
        percentual_inss: parseFloat(editPercentualInss) || 0, percentual_ir: parseFloat(editPercentualIr) || 0,
        valor_inss: parseFloat(editValorInss) || 0, valor_ir: parseFloat(editValorIr) || 0,
        percentual_fgts: editPercentualFgts ? parseFloat(editPercentualFgts) : undefined,
        valor_fgts: editValorFgts ? parseFloat(editValorFgts) : undefined,
        percentual_dctf: editPercentualDctf ? parseFloat(editPercentualDctf) : undefined,
        valor_dctf: editValorDctf ? parseFloat(editValorDctf) : undefined,
        observacao: editObservacao || undefined,
        recorrente: editRecorrente, dia_vencimento: editRecorrente ? Number(editDiaVencimento) : null,
        conta_corrente_id: editContaCorrenteId ? Number(editContaCorrenteId) : undefined,
        status: r.status, data_pagamento: r.data_pagamento || undefined,
      });
      setEditingId(null);
      carregar();
    } catch (e: any) {
      setEditMsg(e.message || "Erro ao atualizar lançamento de folha");
    } finally {
      setEditSalvando(false);
    }
  }

  // Índice de FolhaPagamento por id — usado para renderizar a linha rica
  // (expandir detalhe, editar, marcar como pago) dentro da folha unificada.
  const regsPorId = useMemo(() => {
    const m: Record<number, RegistroFolha> = {};
    (regs || []).forEach((r) => { m[r.id] = r; });
    return m;
  }, [regs]);

  // O documento de um lançamento de folha — o MESMO objeto que a tela de
  // Contas renderiza e que a impressão consome, montado uma vez só. É aqui
  // que a expansão da linha deixa de ser uma lista "rótulo → valor" e passa a
  // ser o recibo de quatro colunas, com cada desconto clicável até a origem.
  function holeriteDoRegistro(r: RegistroFolha): DocHolerite | null {
    return holeriteDaLinha({
      tipo: "funcionario", origem_id: r.id, origem_subtipo: "folha",
      pessoa_id: r.pessoa_id, pessoa_nome: r.pessoa_nome,
      descricao: `Folha — ${r.competencia}`,
      valor: r.valor_liquido,
      data_vencimento: r.data_vencimento ?? null,
      data_pagamento: r.data_pagamento,
      status: r.status === "pago" ? "pago" : "pendente",
      pode_excluir: r.status !== "pago",
      vencido: false,
      detalhe: r.detalhe, totais: r.totais, bases: r.bases,
      // A explicação do mês assumido viaja junto para o documento (fora de
      // `detalhe`, como sempre): a prévia do recibo aqui e a tela de Contas
      // mostram o mesmo papel, e um explicar o desconto sumido enquanto o
      // outro cala seria a mesma divergência que `lib/holerite.ts` existe
      // para não deixar acontecer.
      vale_assumido: r.vale_assumido,
      competencia: r.competencia,
      numero_lancamento_gerado: r.numero_lancamento_gerado,
      observacao: r.observacao,
    });
  }

  // Imprimir holerite — em PDF (identidade visual de relatórios) ou Excel.
  const [imprimindoHoleriteChave, setImprimindoHoleriteChave] = useState<string | null>(null);
  const [imprimindoHoleriteMes, setImprimindoHoleriteMes] = useState(false);
  const [holeriteExportando, setHoleriteExportando] = useState(false);

  // Botão POR LINHA — imprime o holerite só daquele funcionário, nas MESMAS
  // quatro colunas da tela (Descrição · Referência · Vencimentos · Descontos).
  // Antes o PDF era montado à parte, em duas colunas "Item | Valor": a
  // referência não tinha onde entrar e o dono recebia sete linhas escritas
  // "Vale" também no papel. Agora tela, PDF e Excel leem de lib/holerite.
  async function imprimirHoleriteLinha(r: RegistroFolha, formato: "pdf" | "excel") {
    const documento = holeriteDoRegistro(r);
    if (!documento) return;
    setHoleriteExportando(true);
    try {
      await imprimirHolerite(documento, formato);
    } catch {
      // erro já mostrado ao usuário dentro de exportarFichaPDF/exportarMultiExcel (lib/export.ts)
    } finally {
      setHoleriteExportando(false);
      setImprimindoHoleriteChave(null);
    }
  }

  // Todos os funcionários que aparecem na tabela com os filtros atuais
  // (Vencimento/Status/Pessoa/Tipo) — base do botão de lote "do mês filtrado".
  const funcionariosFolhaFiltrados = useMemo(() => {
    const vistos = new Set<number>();
    const lista: RegistroFolha[] = [];
    unificadaFiltrada.forEach((l) => {
      if (l.tipo !== "funcionario") return;
      const r = regsPorId[l.origem_id];
      if (r && !vistos.has(r.id)) { vistos.add(r.id); lista.push(r); }
    });
    return lista;
  }, [unificadaFiltrada, regsPorId]);

  // Botão de LOTE — imprime de uma vez o holerite de todos os funcionários
  // que estão passando pelo filtro atual da tabela (ex.: um mês específico).
  async function imprimirHoleritesDoMes(formato: "pdf" | "excel") {
    if (!funcionariosFolhaFiltrados.length) return;
    setHoleriteExportando(true);
    try {
      const competencias = Array.from(new Set(funcionariosFolhaFiltrados.map((x) => x.competencia))).sort();
      const subtitulo = competencias.length === 1
        ? competenciaExtenso(competencias[0])
        : `${competencias.map(mesCompLabel).join(", ")} — filtro atual`;
      const base = `holerites_${competencias.length === 1 ? competencias[0] : "filtro"}`;
      // Folha em que os descontos passam os vencimentos fica FORA do lote: um
      // papel dizendo que o funcionário deve dinheiro não é comprovante de
      // pagamento (ver `bloqueioDeImpressao`).
      const documentos = funcionariosFolhaFiltrados
        .map(holeriteDoRegistro)
        .filter((d): d is DocHolerite => !!d && !d.totais.liquido_negativo);
      if (!documentos.length) return;
      await imprimirHolerites(documentos, subtitulo, base, formato);
    } catch {
      // erro já mostrado ao usuário dentro de exportarFichaPDF/exportarMultiExcel (lib/export.ts)
    } finally {
      setHoleriteExportando(false);
      setImprimindoHoleriteMes(false);
    }
  }

  // Imprimir recibo de pagamento (empreitada/contrato/diária) — reaproveita o
  // ReciboModal já usado no financeiro.
  const [reciboLinha, setReciboLinha] = useState<LancamentoRecibo | null>(null);

  // Quantas formas de lançar existem NESTA categoria — o número do card
  // "Lançar". A tela própria da categoria (empreita, contrato, diária,
  // férias/13º, rescisão) conta como uma.
  const formasDeLancar =
    (capacidades.folhaFuncionario ? 1 : 0) + (capacidades.valeFuncionario ? 1 : 0)
    + (capacidades.guias ? 1 : 0) + (capacidades.telaPropria ? 1 : 0);
  // A tela própria da categoria, montada com a metade que o card pede: os
  // formulários sob "Lançar", a listagem (e as ações sobre cada item) sob
  // "Consultar". Sem esse corte, escolher "Lançar" continuaria despejando a
  // listagem inteira embaixo do formulário e o card não significaria nada.
  const telaDaCategoria = (mostrar: "lancar" | "listar") => {
    switch (capacidades.telaPropria) {
      case "empreita": return <EmpreitadaView mostrar={mostrar} />;
      case "contrato": return <ContratoView mostrar={mostrar} />;
      case "diarias": return <DiariaView mostrar={mostrar} deepLinkDiariaId={deepLinkDiaria?.id} deepLinkModo={deepLinkDiaria?.modo} />;
      case "ferias_decimo": return <FeriasDecimoTerceiroView mostrar={mostrar} />;
      // Sem props de pessoa: RescisaoView busca as próprias desde que deixou
      // de ser sub-aba de Férias/13º (que lhe emprestava a lista).
      case "rescisao": return <RescisaoView mostrar={mostrar} />;
      default: return null;
    }
  };

  return (
    <div>
      {/* O título "Controle Financeiro" é o <h1> da própria página
          (app/financeiro/page.tsx) — repeti-lo aqui daria dois títulos iguais
          empilhados. O que falta abaixo dele é o papel DESTA tela. */}
      {/* O papel da tela, dito na própria tela. As duas telas de folha diziam
          o que fazem só no texto do menu, que some assim que se entra — e o
          dono acabava lançando de um lado e conferindo do outro sem saber
          qual era qual. */}
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", margin: "0 0 1rem" }}>
        <strong style={{ color: "var(--text)" }}>Aqui se fecha a folha</strong> — lançar, conferir,
        acrescentar vencimento/desconto e pagar. Para só consultar e imprimir o recibo, use{" "}
        <a href="/financeiro?ir=folha_relatorio" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}
          title="Abrir Contas > Holerites e recibos (só consulta)">Contas › Holerites e recibos</a>.
      </p>

      {/* Os três cards — o MODO da tela. Acento por borda esquerda, como o
          resto da casa; o card ativo troca o fundo, não só a borda. */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        {CARDS.map((c) => {
          const ativo = cardAtivo === c.id;
          const numero = c.id === "consultar"
            ? (temLedger ? formatBRL(somaUnificadaFiltrada) : "—")
            : c.id === "lancar" ? String(formasDeLancar)
            : (temLedger ? String(excecoes.length) : "—");
          return (
            <button key={c.id} type="button" aria-pressed={ativo} onClick={() => setCardAtivo(c.id)}
              title={c.descricao}
              style={{
                textAlign: "left", cursor: "pointer", font: "inherit",
                background: ativo ? "color-mix(in srgb, var(--dourado-light) 12%, var(--surface))" : "var(--surface)",
                border: "1px solid var(--border)",
                borderLeft: `4px solid ${ativo ? "var(--dourado)" : "var(--border)"}`,
                borderRadius: "var(--r-sm)", padding: "0.7rem 1rem",
                display: "flex", flexDirection: "column", gap: "0.1rem",
              }}>
              <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text)" }}>{c.titulo}</span>
              <span style={{ fontSize: "1.15rem", fontWeight: 800, fontVariantNumeric: "tabular-nums", color: ativo ? "var(--dourado-light)" : "var(--text)" }}>
                {numero}
              </span>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{c.descricao}</span>
            </button>
          );
        })}
      </div>

      {/* Seletor de categoria — governa TUDO o que aparece abaixo, via a
          tabela CATEGORIAS: o que se pode lançar, o que se consulta e o que
          sequer existe naquela categoria (empreiteiro não tem FGTS). */}
      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        {ORDEM_CATEGORIAS.map((cat) => (
          <button key={cat} type="button" aria-pressed={categoria === cat} onClick={() => setCategoria(cat)}
            title={`Ver só ${CATEGORIAS[cat].rotulo.toLowerCase()}`}
            style={{ fontSize: "0.82rem", fontWeight: 600, padding: "0.45rem 0.9rem", borderRadius: "999px",
              border: `1px solid ${categoria === cat ? "var(--dourado)" : "var(--border)"}`,
              background: categoria === cat ? "var(--dourado)" : "var(--surface)",
              color: categoria === cat ? "var(--vinho-dark, #0A1F36)" : "var(--text-muted)", cursor: "pointer" }}>
            {CATEGORIAS[cat].rotulo}
          </button>
        ))}
      </div>

      {error && <div className="alert-critico mb-3"><span>Sem dados: {error}.</span></div>}
      <AvisoSalvo texto={msg?.tipo === "sucesso" ? msg.texto : null} />

      {/* ── FAIXA DE FILTROS ────────────────────────────────────────────────
          Some INTEIRA sob o card "Lançar": não se filtra o que ainda não
          existe. E não aparece na rescisão, que não tem ledger a filtrar. */}
      {cardAtivo !== "lancar" && temLedger && (<>
        {/* O MÊS é o primeiro filtro, e é um objeto próprio (não dois campos
            de data soltos): é ele que define "o mês que se está fechando". A
            equação que confere esse mês fica no card Consultar, junto do que
            ela soma. */}
        <BarraCompetencia
          mes={mesEmTela}
          mesesComLancamento={mesesComLancamento}
          competencias={competenciasEmTela}
          situacao={situacaoMes}
          quantidade={unificadaFiltrada.length}
          onMes={setMesFolha}
        />
        <div className="card mb-3">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtrar dentro do mês</div>
          <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
            <span style={{ ...labelStyleLote, marginRight: "0.2rem" }}>Situação do pagamento</span>
            {SITUACOES.map((sit) => (
              <button key={sit.id} type="button" className="btn-ghost" title={sit.dica}
                aria-pressed={situacao === sit.id} onClick={() => setSituacao(sit.id)}
                style={{
                  fontSize: "0.76rem",
                  borderColor: situacao === sit.id ? "var(--dourado)" : undefined,
                  color: situacao === sit.id ? "var(--dourado-light)" : undefined,
                  fontWeight: situacao === sit.id ? 700 : undefined,
                  background: situacao === sit.id ? "color-mix(in srgb, var(--dourado-light) 12%, transparent)" : undefined,
                }}>{sit.label}</button>
            ))}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div><label style={labelStyleLote}>Vencimento — de</label>
              <input type="date" style={selStyleLote} value={fUniVencDe} onChange={(e) => setFUniVencDe(e.target.value)} /></div>
            <div><label style={labelStyleLote}>Vencimento — até</label>
              <input type="date" style={selStyleLote} value={fUniVencAte} onChange={(e) => setFUniVencAte(e.target.value)} /></div>
            <div><label style={labelStyleLote}>Pessoa</label>
              <select style={selStyleLote} value={fUniPessoa} onChange={(e) => setFUniPessoa(e.target.value)}>
                <option value="">Todos</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select></div>
            <div><label style={labelStyleLote}>Buscar pessoa…</label>
              <div style={{ position: "relative" }}>
                <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
                <input style={{ ...selStyleLote, paddingLeft: "1.6rem" }} value={buscaPessoa}
                  onChange={(e) => setBuscaPessoa(e.target.value)} placeholder="parte do nome" /></div></div>
          </div>
        </div>
      </>)}

      {/* ── CARD "RESOLVER ANTES DE FECHAR" ───────────────────────────────── */}
      {cardAtivo === "resolver" && (temLedger ? (
        <ExcecoesFolha excecoes={excecoes} onResolver={irParaExcecao} />
      ) : (
        <div className="card mb-3" style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
          A rescisão não entra no ledger unificado do mês — não há pendência de fechamento a apontar aqui.
          O que a rescisão gera é uma conta a pagar, que aparece em{" "}
          <strong style={{ color: "var(--text)" }}>Contas a pagar</strong>.
        </div>
      ))}

      {/* ── CARD "LANÇAR" ──────────────────────────────────────────────────
          Os três formulários gerais (folha, vale, guia) lado a lado, no mesmo
          formato, cores e acentos de sempre — e, quando a categoria tem tela
          própria, ela entra aqui com os formulários dela. */}
      {cardAtivo === "lancar" && (<>
      {capacidades.telaPropria && telaDaCategoria("lancar")}
      {(capacidades.folhaFuncionario || capacidades.valeFuncionario || capacidades.guias) && (<>
      {anexarAberto && (
        <ModalDivididoDocumento title="Anexar comprovante — leitura automática (despesa)" onClose={() => { setAnexarAberto(false); setArquivoPreview(null); }} arquivo={arquivoPreview}>
          <FormFinanceiro tipo="despesa" responsaveis={nomesResponsaveis} onArquivoParaLeitura={setArquivoPreview}
            onSalvo={(mensagem) => { setAnexarAberto(false); setArquivoPreview(null); setMsg({ tipo: "sucesso", texto: mensagem }); carregar(); carregarUnificada(); }} />
        </ModalDivididoDocumento>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 items-start">
      {/* 1) Novo lançamento de folha — acento dourado */}
      {capacidades.folhaFuncionario && (
      <div style={{ borderLeft: `4px solid ${COR_LANCAR.folha}`, borderRadius: "var(--r-sm)", marginBottom: "0.9rem" }}>
      <SecaoRecolhivel titulo="Nova folha — Funcionário" icon={Plus} defaultAberta={false} descricao="Lance a folha de uma pessoa em uma competência">
        <div className="mb-3" style={{ textAlign: "right" }}>
          <button className="btn-ghost" title="Anexar recibo ou comprovante e preencher por leitura automática" style={{ fontSize: "0.75rem" }} onClick={() => setAnexarAberto(true)}>
            <Paperclip size={13} /> Anexar recibo/comprovante
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Pessoa</label>
            <select style={selStyleLote} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
              <option value="">Selecione…</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipos.join(", ")})</option>)}
            </select></div>
          <div><label style={labelStyleLote}>Competência (mês)</label>
            <input type="month" style={selStyleLote} value={competencia} onChange={(e) => setCompetencia(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Valor bruto (R$)</label>
            <CampoMoeda style={selStyleLote} value={Number(valorBruto) || 0} onChange={(v) => setValorBruto(v ? String(v) : "")} /></div>
          <div><label style={labelStyleLote}>Outros descontos (R$)</label>
            <CampoMoeda style={selStyleLote} value={Number(descontos) || 0} onChange={(v) => setDescontos(v ? String(v) : "")} /></div>
        </div>
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "-0.5rem", marginBottom: "0.75rem" }}>
          Competência = mês trabalhado. O pagamento (conta a pagar) é lançado no dia 5 do mês seguinte
          {recorrente ? " (ou no dia escolhido abaixo)" : ""}.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <CampoRetencao
            label="INSS" percentual={percentualInss} valor={valorInss}
            onChangePercentual={(v) => { setPercentualInss(v); setInssManual(false); }}
            onChangeValor={(v) => { setValorInss(v); setInssManual(true); }}
          />
          <CampoRetencao
            label="IR" percentual={percentualIr} valor={valorIr}
            onChangePercentual={(v) => { setPercentualIr(v); setIrManual(false); }}
            onChangeValor={(v) => { setValorIr(v); setIrManual(true); }}
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <div><label style={labelStyleLote}>Observação</label>
            <input style={selStyleLote} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
          <div className="flex items-end"><span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Valor líquido: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(valorLiquido)}</strong></span></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Conta bancária (opcional)</label>
            <select style={selStyleLote} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
              <option value="">Não informar</option>
              {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
            </select></div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 items-end">
          <div className="flex items-center gap-2" style={{ paddingBottom: "0.4rem" }}>
            <input id="folha-recorrente" type="checkbox" checked={recorrente} onChange={(e) => setRecorrente(e.target.checked)} />
            <label htmlFor="folha-recorrente" style={{ fontSize: "0.8rem" }}>Recorrente (lançar em Contas a Pagar todo mês)</label>
          </div>
          {recorrente && (
            <div><label style={labelStyleLote}>Dia de vencimento no mês seguinte (1–28)</label>
              <input type="number" min={1} max={28} style={selStyleLote} value={diaVencimento} onChange={(e) => setDiaVencimento(e.target.value)} /></div>
          )}
        </div>
        {recorrente && (
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
            A partir do próximo mês, o sistema gera automaticamente o lançamento de folha e a conta a pagar correspondente — não é preciso relançar manualmente.
          </p>
        )}
        {/* Sucesso já aparece no topo (AvisoSalvo) — aqui só o erro, contextual. */}
        {msg?.tipo === "erro" && <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>}
        <button className="btn-primary" title="Salvar o lançamento de folha" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Lançar"}
        </button>
      </SecaoRecolhivel>
      </div>
      )}

      {/* 2) Vale de funcionário — acento verde */}
      {capacidades.valeFuncionario && (
      <div style={{ borderLeft: `4px solid ${COR_LANCAR.vale}`, borderRadius: "var(--r-sm)", marginBottom: "0.9rem" }}>
      <SecaoRecolhivel titulo="Novo vale" icon={Plus} defaultAberta={false} descricao="Adiantamento pago à parte, descontado da folha">
        <ValeFuncionarioSection pessoas={pessoas} contasCorrentes={contasCorrentes} onLancado={() => { carregar(); carregarUnificada(); carregarVales(); }} />
      </SecaoRecolhivel>
      </div>
      )}

      {/* 3) Lançar guia de FGTS/DCTF — acento vermelho — manual ou por leitura
          automática do PDF/foto da guia real. Só sob Funcionário e Todos:
          FGTS/DCTF são encargos de CLT, e o empreiteiro não é CLT (decisão do
          dono, e a razão de a guia sumir das outras categorias). */}
      {capacidades.guias && (
      <div style={{ borderLeft: `4px solid ${COR_LANCAR.guia}`, borderRadius: "var(--r-sm)", marginBottom: "0.9rem" }}>
      <SecaoRecolhivel
        titulo="Lançar guia de FGTS/DCTF" icon={Plus} defaultAberta={false}
        descricao="Manual ou por leitura automática do PDF/foto da guia — cria a conta a pagar e guarda os dados para relatório"
      >
        <LancarGuiaFgtsDctfSection onLancado={() => { carregarUnificada(); carregarGuias(); }} />
      </SecaoRecolhivel>
      </div>
      )}
      </div>
      {categoria === "todos" && (
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
          Empreita, contrato, diária, férias/13º e rescisão têm formulário próprio — escolha a categoria acima
          para lançar cada uma delas.
        </p>
      )}
      </>)}
      </>)}

      {/* ── CARD "CONSULTAR" ───────────────────────────────────────────────
          O ledger unificado é montado pelo backend com CINCO tipos —
          funcionario, empreita, contrato, diaria, ferias_decimo. A rescisão
          não é um deles, e é por isso que ela tem TELA PRÓPRIA: mostrar a
          barra do mês, a equação e a tabela zeradas diria "não há rescisão
          nenhuma", o que é falso — elas estão na tabela da própria tela de
          Rescisão. Quando o ledger passar a emitir o 6º tipo, é só dar um
          `tipoLedger` à categoria em CATEGORIAS. */}
      {cardAtivo === "consultar" && (!temLedger ? (<>
        {telaDaCategoria("listar")}
        <div className="card mb-3" style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
          A conta a pagar gerada ao fechar uma rescisão aparece em{" "}
          <strong style={{ color: "var(--text)" }}>Contas a pagar</strong> — o ledger unificado
          da folha ainda não inclui rescisão, e por isso ela não entra na equação do mês acima.
        </div>
      </>) : (<>

      {/* A EQUAÇÃO do mês no lugar dos três KPIs soltos (Lançamentos/
          Pendente/Pago) que não formavam conta nenhuma: sem identidade a
          conferir, um total errado não tinha como saltar aos olhos. */}
      <EquacaoFolha eq={equacao} />
      <OutrosPagamentosDoMes resumo={outrosTipos} />

      {/* Total filtrado + ação em lote de holerites — fora do cabeçalho clicável
          da SecaoRecolhivel abaixo (não dá pra aninhar um <button> dentro do
          <button> do cabeçalho), mas visualmente bem ao lado um do outro. */}
      <div className="flex items-center justify-between gap-2 mb-2" style={{ flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.78rem", fontWeight: 700, whiteSpace: "nowrap" }}>
          Total filtrado: {formatBRL(somaUnificadaFiltrada)}
          <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>
            {" "}· {formatBRL(somaUniPendente)} a pagar · {formatBRL(somaUniPago)} pago
            {uniBloqueadas.length > 0 ? ` · ${formatBRL(somaUniBloqueada)} fora da conta` : ""}
          </span>
        </span>
        {capacidades.folhaFuncionario && (
        <span style={{ position: "relative" }}>
          <button className="btn-ghost" type="button" title="Imprimir o holerite de todos os funcionários que estão passando pelo filtro atual (ex.: um mês específico)"
            style={{ fontSize: "0.75rem" }} disabled={!funcionariosFolhaFiltrados.length}
            onClick={() => setImprimindoHoleriteMes((v) => !v)}>
            <Printer size={13} /> Imprimir holerite do mês
          </button>
          {imprimindoHoleriteMes && (
            <span className="flex items-center gap-1" style={{ position: "absolute", top: "100%", right: 0, zIndex: 6, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem", whiteSpace: "nowrap" }}>
              <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginRight: "0.2rem" }}>Formato:</span>
              <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={holeriteExportando} onClick={() => imprimirHoleritesDoMes("pdf")}>PDF</button>
              <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={holeriteExportando} onClick={() => imprimirHoleritesDoMes("excel")}>Excel</button>
            </span>
          )}
        </span>
        )}
      </div>

      {/* Folha de pagamento — funcionário, empreita, contrato, diária e férias/13º num único ledger;
          recolhida por padrão, expande ao clicar no cabeçalho. Prioriza pendências (destacando as vencidas em vinho). */}
      <SecaoRecolhivel
        titulo={categoria === "todos" ? "Folha de pagamento" : `${capacidades.rotulo} — lançamentos do mês`}
        icon={Filter}
        aberta={grupoAberto(GRUPO_LEDGER)} onAlternar={() => alternarGrupo(GRUPO_LEDGER)}
        badge={<span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
          {unificadaFiltrada.length} {unificadaFiltrada.length === 1 ? "lançamento" : "lançamentos"} · {formatBRL(somaUnificadaFiltrada)}
        </span>}
        descricao="Clique no nome da pessoa para abrir o discriminado do lançamento."
      >
        {erroUnificada ? <div className="alert-critico"><span>Sem dados: {erroUnificada}.</span></div> : (
        <div className="overflow-x-auto" id="folha-tabela">
          <table className="fazenda-table">
            <thead><tr>
              <ThOrdenavel label="Tipo" campo="tipo" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} />
              <th title="Mês de pagamento (quando pago) ou de vencimento (quando pendente)">Mês</th>
              <ThOrdenavel label="Pessoa" campo="pessoa_nome" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} />
              <th title="Mês de referência do salário (só funcionário)">Competência</th>
              <ThOrdenavel label="Vencimento" campo="data_vencimento" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} />
              <ThOrdenavel label="Valor" campo="valor" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} alinhar="right" />
              <th style={{ textAlign: "right" }}>Descontos de folha</th>
              <th style={{ textAlign: "right" }}>Descontos de vale</th>
              <ThOrdenavel label="Status" campo="status" coluna={uniColuna} dir={uniDir} ordenar={uniOrdenar} />
              <th style={{ textAlign: "right" }}>Valor pago</th>
              {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
              <th></th>
            </tr></thead>
            <tbody>
              {unificadaOrdenada.map((l) => {
                const chave = `${l.tipo}-${l.origem_subtipo}-${l.origem_id}`;
                if (l.tipo !== "funcionario") {
                  const editavel = podeEditarLinha(l);
                  const editandoLinha = editingLinhaChave === chave;
                  const aberta = expandidaChave === chave;
                  const docLinha = holeriteDaLinha(l);
                  const statusLinha = rotuloStatusLinha(l.status);
                  return (
                    <Fragment key={chave}>
                    <tr style={l.vencido ? { background: VENCIDO_BG } : undefined}>
                      <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{LABEL_TIPO[l.tipo]}</td>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem", whiteSpace: "nowrap" }}>
                        <span className="flex items-center gap-1">
                          {aberta ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                          {(() => { const d = l.data_pagamento || l.data_vencimento; return d ? mesCompLabel(d.slice(0, 7)) : "—"; })()}
                        </span>
                      </td>
                      <td style={{ fontSize: "0.82rem" }}>
                        <button type="button" style={nomeClicavel}
                          title={`Abrir o discriminado deste lançamento de ${l.pessoa_nome}`}
                          onClick={() => setExpandidaChave(aberta ? null : chave)}>
                          {l.pessoa_nome}
                        </button>
                      </td>
                      <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>—</td>
                      <td style={{ fontSize: "0.78rem" }}>{l.data_vencimento ? l.data_vencimento.split("-").reverse().join("/") : "—"}{l.vencido && " ⚠"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(l.valor)}</td>
                      <td style={{ textAlign: "right", fontSize: "0.76rem", color: "var(--text-muted)" }}>—</td>
                      <td style={{ textAlign: "right", fontSize: "0.76rem", color: "var(--text-muted)" }}>—</td>
                      <td><span title={statusLinha.titulo} style={{ fontSize: "0.72rem", fontWeight: 700, color: statusLinha.cor }}>{statusLinha.texto}</span></td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{l.status === "pago" ? formatBRL(l.valor) : "—"}</td>
                      {admin && <td>—</td>}
                      <td style={{ textAlign: "right" }}>
                        <span className="flex items-center gap-2" style={{ justifyContent: "flex-end" }}>
                          {/* A OUTRA porta para a linha do tempo, agora que o
                              nome abre o discriminado. Continua sendo o único
                              caminho até LinhaTempoPessoa no sistema inteiro. */}
                          <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                            title={`Linha do tempo de ${l.pessoa_nome} — pagamentos, vales e parcelas em ordem`}
                            onClick={() => setFichaPessoaId(l.pessoa_id)}>
                            <History size={13} />
                          </button>
                          <button className="btn-ghost" title="Imprimir recibo de pagamento" style={{ fontSize: "0.72rem" }}
                            onClick={() => setReciboLinha({
                              numero_lancamento: `${l.tipo}-${l.origem_id}`,
                              tipo: "despesa",
                              fornecedor: l.pessoa_nome,
                              descricao: l.descricao,
                              valor: l.valor,
                              data_pagamento: l.data_pagamento,
                              data_vencimento: l.data_vencimento,
                            })}>
                            <Printer size={13} />
                          </button>
                          {editavel && (
                            <button className="btn-ghost" title="Editar este lançamento (enquanto não estiver pago)" style={{ fontSize: "0.72rem" }}
                              onClick={() => (editandoLinha ? setEditingLinhaChave(null) : iniciarEdicaoLinha(l))}>
                              <Pencil size={13} />
                            </button>
                          )}
                          {l.pode_excluir && (
                            <button className="btn-ghost" title="Excluir este lançamento pendente" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                              disabled={excluindoChave === chave}
                              onClick={() => { if (window.confirm("Excluir este lançamento de folha pendente?")) excluirLinha(l); }}>
                              <Trash2 size={13} />
                            </button>
                          )}
                        </span>
                      </td>
                    </tr>
                    {aberta && (
                      <tr><td colSpan={admin ? 12 : 11}>
                        <div style={{ padding: "0.6rem 0" }}>
                          {/* Férias e 13º chegam com `detalhe` — o recibo de
                              quatro colunas, igual ao holerite. Empreita,
                              contrato e diária são pagamento de valor único,
                              sem composição: o que se pode discriminar deles é
                              a referência (de onde veio e para quando). */}
                          {docLinha
                            ? <Holerite documento={docLinha} compacto cabecalho={false} />
                            : (
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ fontSize: "0.8rem" }}>
                                <div><div style={labelStyleLote}>Descrição</div>{l.descricao}</div>
                                <div><div style={labelStyleLote}>Referência</div>
                                  {l.data_vencimento ? `vence em ${formatDate(l.data_vencimento)}` : "sem vencimento"}
                                  {l.data_pagamento ? ` · pago em ${formatDate(l.data_pagamento)}` : ""}</div>
                                <div><div style={labelStyleLote}>Valor</div>{formatBRL(l.valor)}</div>
                                <div><div style={labelStyleLote}>No extrato</div>
                                  {l.numero_lancamento_gerado
                                    ? <LinkExtrato numero={l.numero_lancamento_gerado} />
                                    : <span style={{ color: "var(--text-muted)" }}>—</span>}</div>
                              </div>
                            )}
                        </div>
                      </td></tr>
                    )}
                    {editandoLinha && (
                      <tr>
                        <td colSpan={admin ? 12 : 11} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-2">
                            <div><label style={labelStyleLote}>Vencimento</label>
                              <input type="date" style={selStyleLote} value={editLinhaData} onChange={(e) => setEditLinhaData(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Valor (R$)</label>
                              <CampoMoeda style={selStyleLote} value={Number(editLinhaValor) || 0} onChange={(v) => setEditLinhaValor(v ? String(v) : "")} /></div>
                          </div>
                          {editLinhaMsg && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{editLinhaMsg}</p>}
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button className="btn-primary" disabled={salvandoLinha} onClick={() => salvarEdicaoLinha(l)}>
                              <Check size={14} /> {salvandoLinha ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="btn-ghost" onClick={() => setEditingLinhaChave(null)}>Cancelar</button>
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                }
                const r = regsPorId[l.origem_id];
                if (!r) return null;
                const expandido = expandedId === r.id;
                const editando = editingId === r.id;
                const descFolha = arredonda2(r.descontos + r.valor_inss + r.valor_ir);
                const descVale = arredonda2(r.valor_vale || 0);
                const descAberto = expandDesc && expandDesc.id === r.id;
                // Era `r.detalhe.filter((d) => /vale/i.test(d.label))`: a tela
                // descobria "o que é vale" por regex no rótulo em português,
                // porque o servidor mandava só texto. Agora a linha declara o
                // próprio tipo e carrega o vale de origem.
                const valeLinhas = r.detalhe.filter((d) => d.tipo === "vale");
                // As parcelas que a fazenda assumiu naquele mês. Vêm em campo
                // PRÓPRIO (nunca em `r.detalhe`), então `descVale` e todos os
                // totais do mês seguem sem elas — aqui elas só explicam o
                // desconto que sumiu e devolvem o botão "Ações" à competência
                // desconsiderada, que era onde a volta atrás ficava sem porta.
                const valeAssumido = r.vale_assumido || [];
                const temPainelVale = descVale > 0 || valeAssumido.length > 0;
                const documento = holeriteDoRegistro(r);
                return (
                  <Fragment key={chave}>
                    <tr id={`folha-linha-${r.id}`}
                      className={`row-clickable${folhaDestacada === r.id ? " flash-localizado" : ""}`}
                      title="Clique para ver a discriminação deste lançamento de folha" onClick={() => setExpandedId(expandido ? null : r.id)}
                      style={l.vencido ? { background: VENCIDO_BG } : undefined}>
                      <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{LABEL_TIPO.funcionario}</td>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem", whiteSpace: "nowrap" }}
                        title={r.data_pagamento ? "Mês em que a folha foi paga" : "Mês de vencimento (pagamento previsto)"}>
                        <span className="flex items-center gap-1">
                          {expandido ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                          {(() => { const d = r.data_pagamento || r.data_vencimento; return d ? mesCompLabel(d.slice(0, 7)) : "—"; })()}
                        </span>
                      </td>
                      <td style={{ fontSize: "0.82rem" }}>
                        {/* O NOME abre o discriminado — o gesto do desenho
                            aprovado ("clicou no nome, abre o discriminado
                            daquele contrato"). A linha do tempo da pessoa, que
                            antes morava aqui, ganhou botão próprio na coluna
                            de ações: continua sendo a única porta para ela. */}
                        <button type="button" style={nomeClicavel}
                          title={`Abrir o discriminado da folha de ${r.pessoa_nome} — ${mesCompLabel(r.competencia)}`}
                          onClick={(e) => { e.stopPropagation(); setExpandedId(expandido ? null : r.id); }}>
                          {r.pessoa_nome}
                        </button>
                        {(r.recorrente || r.origem_recorrencia_id) && (
                          <span title={r.recorrente ? "Modelo recorrente — gera Contas a Pagar todo mês" : "Gerado automaticamente pela recorrência"} style={{ marginLeft: "0.4rem", display: "inline-flex", verticalAlign: "middle", color: "var(--dourado-light)" }}>
                            <RefreshCw size={12} />
                          </span>
                        )}
                      </td>
                      <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{r.competencia}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.data_vencimento ? r.data_vencimento.split("-").reverse().join("/") : "—"}{l.vencido && " ⚠"}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(r.valor_bruto)}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem", color: descFolha ? "var(--red)" : "var(--text-muted)", cursor: "pointer", textDecoration: descFolha ? "underline dotted" : undefined }}
                        title="Clique para ver o detalhe dos descontos de folha (INSS, IR, outros)"
                        onClick={(e) => { e.stopPropagation(); setExpandDesc(descAberto && expandDesc!.tipo === "folha" ? null : { id: r.id, tipo: "folha" }); }}>
                        {formatBRL(descFolha)}
                      </td>
                      {/* O VALOR aqui é só o que foi efetivamente descontado
                          (`valor_vale`, que ignora a parcela assumida). O que
                          muda com a parcela assumida é a porta: sem o pontilhado
                          a célula zerada não parecia clicável, e era ali dentro
                          que morava o único acesso ao desfazer. */}
                      <td style={{ textAlign: "right", fontSize: "0.78rem", color: descVale ? "var(--amber)" : "var(--text-muted)", cursor: "pointer", textDecoration: temPainelVale ? "underline dotted" : undefined }}
                        title={descVale
                          ? "Clique para ver as parcelas de vale descontadas nesta folha"
                          : valeAssumido.length
                            ? "Nada foi descontado: a fazenda assumiu a parcela de vale deste mês. Clique para ver o motivo e desfazer."
                            : "Clique para ver as parcelas de vale descontadas nesta folha"}
                        onClick={(e) => { e.stopPropagation(); setExpandDesc(descAberto && expandDesc!.tipo === "vale" ? null : { id: r.id, tipo: "vale" }); }}>
                        {formatBRL(descVale)}
                      </td>
                      <td>{(() => { const st = rotuloStatusLinha(r.status); return (
                        <span title={st.titulo} style={{ fontSize: "0.72rem", fontWeight: 700, color: st.cor }}>{st.texto}</span>
                      ); })()}</td>
                      <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{r.status === "pago" ? formatBRL(r.valor_liquido) : "—"}</td>
                      {admin && <td>{r.usuario_nome ?? "—"}</td>}
                      <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                        <span className="flex items-center gap-2" style={{ justifyContent: "flex-end" }}>
                          <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                            title={`Linha do tempo de ${r.pessoa_nome} — folhas, vales e parcelas em ordem`}
                            onClick={() => setFichaPessoaId(r.pessoa_id)}>
                            <History size={13} />
                          </button>
                          <span style={{ position: "relative" }}>
                            <button className="btn-ghost" title={`Imprimir holerite de ${r.pessoa_nome} (${mesCompLabel(r.competencia)})`} style={{ fontSize: "0.72rem" }}
                              onClick={() => setImprimindoHoleriteChave(imprimindoHoleriteChave === chave ? null : chave)}>
                              <Printer size={13} />
                            </button>
                            {imprimindoHoleriteChave === chave && (
                              <span className="flex items-center gap-1" style={{ position: "absolute", top: "100%", right: 0, zIndex: 5, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem", whiteSpace: "nowrap" }}>
                                <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginRight: "0.2rem" }}>Formato:</span>
                                <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={holeriteExportando} onClick={() => imprimirHoleriteLinha(r, "pdf")}>PDF</button>
                                <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={holeriteExportando} onClick={() => imprimirHoleriteLinha(r, "excel")}>Excel</button>
                              </span>
                            )}
                          </span>
                          {r.status === "pendente" && (
                            <>
                              <button className="btn-ghost" title="Pagar — dá para lançar valor distinto do previsto no vale e decidir o destino da diferença" style={{ fontSize: "0.72rem" }} onClick={() => setPagandoId(r.id)}>Pagar</button>
                              <button className="btn-ghost" title="Excluir este lançamento pendente" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                                disabled={excluindoChave === chave}
                                onClick={() => { if (window.confirm("Excluir este lançamento de folha pendente?")) excluirLinha(l); }}>
                                <Trash2 size={13} />
                              </button>
                            </>
                          )}
                          {/* Só admin: o estorno desfaz a baixa da conta a
                              pagar e descongela a discriminação de um recibo
                              já emitido. Não é vermelho — não exclui nada. */}
                          {r.status === "pago" && admin && (
                            <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                              title="Estornar o pagamento — desfaz a baixa e devolve a folha a pendente, para poder corrigir"
                              disabled={estornandoId === r.id}
                              onClick={() => estornarFolha(r)}>
                              <RotateCcw size={13} /> {estornandoId === r.id ? "Estornando…" : "Estornar"}
                            </button>
                          )}
                        </span>
                      </td>
                    </tr>
                    {descAberto && (
                      <tr><td colSpan={admin ? 12 : 11}>
                        <div style={{ padding: "0.5rem 0" }} onClick={(e) => e.stopPropagation()}>
                          <p style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.3rem" }}>
                            {expandDesc!.tipo === "folha" ? "Descontos de folha" : "Descontos de vale"} — {r.pessoa_nome}, {mesCompLabel(r.competencia)}
                          </p>
                          <table style={{ width: "100%", maxWidth: 460, fontSize: "0.78rem" }}>
                            <tbody>
                              {expandDesc!.tipo === "folha" ? (
                                // Lido do MESMO discriminado do recibo — este
                                // painel e o holerite ao lado montavam a lista
                                // por conta própria e podiam discordar sobre
                                // uma retenção digitada sem percentual.
                                r.detalhe.filter((d) => ["inss", "ir", "outros"].includes(d.tipo)).map((d, i) => (
                                  <tr key={i}>
                                    <td style={{ padding: "0.15rem 0.5rem 0.15rem 0" }}>
                                      {d.descricao}
                                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{d.referencia}</div>
                                    </td>
                                    <td style={{ textAlign: "right", color: "var(--red)", verticalAlign: "top" }}>− {formatBRL(d.desconto || 0)}</td>
                                  </tr>
                                ))
                              ) : (
                                <>
                                {/* Uma linha por parcela, com a REFERÊNCIA que
                                    desempata: "Parcela 3 de 13 · vale de
                                    12/03/2026" no lugar de N linhas idênticas
                                    escritas "Vale". */}
                                {valeLinhas.map((d, i) => (
                                  <tr key={i}>
                                    <td style={{ padding: "0.15rem 0.5rem 0.15rem 0" }}>
                                      {d.descricao}
                                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{d.referencia}</div>
                                    </td>
                                    <td style={{ textAlign: "right", color: "var(--amber)", verticalAlign: "top" }}>− {formatBRL(d.desconto || 0)}</td>
                                    <td style={{ textAlign: "right", verticalAlign: "top", paddingLeft: "0.5rem" }}>
                                      {/* O vale só é editável enquanto a folha não virou recibo:
                                          folha paga tem a discriminação congelada e nenhuma ação
                                          pode reescrevê-la (o backend recusa do mesmo jeito). */}
                                      {r.status !== "pago" && d.origem && "vale_id" in d.origem && (
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                                          title="Reparcelar o saldo, abater um valor, desconsiderar este mês ou cancelar o vale"
                                          onClick={() => setAcoesVale({
                                            valeId: (d.origem as any).vale_id, pessoaNome: r.pessoa_nome, competencia: r.competencia,
                                          })}>
                                          <Pencil size={12} /> Ações
                                        </button>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                                {/* As parcelas que a FAZENDA assumiu. Não são
                                    desconto — o valor vai riscado e em cinza, sem
                                    o sinal de menos, justamente para não ser lido
                                    como cobrança —, e nenhuma soma da tela as
                                    enxerga: elas nem chegam em `r.detalhe`. Estão
                                    aqui por dois motivos: dizer POR QUE o desconto
                                    do mês sumiu, e devolver o botão "Ações" ao mês
                                    desconsiderado, que é a única porta para voltar
                                    a descontá-lo. */}
                                {valeAssumido.map((d, i) => (
                                  <tr key={`assumido-${i}`}>
                                    <td style={{ padding: "0.15rem 0.5rem 0.15rem 0" }}>
                                      {d.descricao}
                                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                                        {d.referencia} · assumida pela fazenda{d.motivo ? ` — ${d.motivo}` : ""}
                                      </div>
                                    </td>
                                    <td style={{ textAlign: "right", color: "var(--text-muted)", verticalAlign: "top", textDecoration: "line-through" }}
                                      title="A fazenda assumiu este valor: ele não foi descontado do funcionário e não entra em desconto nenhum desta folha.">
                                      {formatBRL(d.valor_assumido)}
                                    </td>
                                    <td style={{ textAlign: "right", verticalAlign: "top", paddingLeft: "0.5rem" }}>
                                      {r.status !== "pago" && d.origem && "vale_id" in d.origem && (
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                                          title="Voltar a descontar este mês, reparcelar o saldo, abater um valor ou cancelar o vale"
                                          onClick={() => setAcoesVale({
                                            valeId: (d.origem as any).vale_id, pessoaNome: r.pessoa_nome, competencia: r.competencia,
                                          })}>
                                          <Pencil size={12} /> Ações
                                        </button>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                                </>
                              )}
                              {expandDesc!.tipo === "folha" && descFolha === 0 && <tr><td style={{ color: "var(--text-muted)" }}>Sem descontos de folha nesta competência.</td></tr>}
                              {expandDesc!.tipo === "vale" && !valeLinhas.length && !valeAssumido.length && <tr><td style={{ color: "var(--text-muted)" }}>Sem parcelas de vale nesta competência.</td></tr>}
                            </tbody>
                          </table>
                        </div>
                      </td></tr>
                    )}
                    {expandido && !editando && (
                      <tr><td colSpan={admin ? 12 : 11}>
                        <div style={{ padding: "0.6rem 0" }} onClick={(e) => e.stopPropagation()}>
                          {/* A prévia do recibo, na própria linha: as quatro
                              colunas do papel, e cada desconto clicável até a
                              origem. Antes era uma lista "rótulo → valor" em
                              que sete parcelas de vale saíam idênticas. */}
                          {documento
                            ? <Holerite documento={documento} compacto cabecalho={false} />
                            : <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Sem discriminação para esta competência.</p>}
                          {r.status !== "pago" ? (
                            <button className="btn-ghost mt-2" title="Editar este lançamento de folha (enquanto não estiver pago)" style={{ fontSize: "0.75rem" }} onClick={() => iniciarEdicao(r)}>
                              <Pencil size={12} /> Editar lançamento
                            </button>
                          ) : (
                            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                              Lançamento já pago — não pode mais ser editado. {admin ? "Use \u201cEstornar\u201d na linha para reabri-lo." : "Peça a um administrador para estornar o pagamento."}
                            </p>
                          )}
                          {estornoErro && <p style={{ color: "var(--red)", fontSize: "0.78rem", marginTop: "0.4rem" }}>{estornoErro}</p>}

                          {/* O PAINEL DE RUBRICAS — acrescentar vencimento e
                              desconto ao holerite. Ele morava em Contas >
                              Holerites e recibos, que passou a ser só
                              consulta: era o único jeito de acrescentar uma
                              verba a um holerite, e ficava justamente na tela
                              onde nada se altera. Fica FORA do papel, abaixo
                              dele — o recibo continua sendo quatro colunas sem
                              botão nenhum entre os números (ver o cabeçalho de
                              RubricasHolerite.tsx). */}
                          <RubricasHolerite
                            key={r.id}
                            folhaId={r.id}
                            bloqueio={r.status === "pago"
                              ? "Esta folha já foi paga e o recibo está congelado — estorne o pagamento para acrescentar ou corrigir vencimentos e descontos."
                              : null}
                            onMudou={() => { carregar(); carregarUnificada(); }}
                          />
                        </div>
                      </td></tr>
                    )}
                    {editando && (
                      <tr><td colSpan={admin ? 12 : 11}>
                        <div style={{ padding: "0.75rem 0" }} onClick={(e) => e.stopPropagation()}>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Pessoa</label>
                              <select style={selStyleLote} value={editPessoaId} onChange={(e) => setEditPessoaId(e.target.value)}>
                                {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipos.join(", ")})</option>)}
                              </select></div>
                            <div><label style={labelStyleLote}>Competência (mês)</label>
                              <input type="month" style={selStyleLote} value={editCompetencia} onChange={(e) => setEditCompetencia(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Valor bruto (R$)</label>
                              <CampoMoeda style={selStyleLote} value={Number(editValorBruto) || 0} onChange={(v) => setEditValorBruto(v ? String(v) : "")} /></div>
                            <div><label style={labelStyleLote}>Outros descontos (R$)</label>
                              <CampoMoeda style={selStyleLote} value={Number(editDescontos) || 0} onChange={(v) => setEditDescontos(v ? String(v) : "")} /></div>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <CampoRetencao
                              label="INSS" percentual={editPercentualInss} valor={editValorInss}
                              onChangePercentual={(v) => { setEditPercentualInss(v); setEditInssManual(false); }}
                              onChangeValor={(v) => { setEditValorInss(v); setEditInssManual(true); }}
                            />
                            <CampoRetencao
                              label="IR" percentual={editPercentualIr} valor={editValorIr}
                              onChangePercentual={(v) => { setEditPercentualIr(v); setEditIrManual(false); }}
                              onChangeValor={(v) => { setEditValorIr(v); setEditIrManual(true); }}
                            />
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <CampoRetencao
                              label="FGTS" percentual={editPercentualFgts} valor={editValorFgts}
                              onChangePercentual={(v) => { setEditPercentualFgts(v); setEditFgtsManual(false); }}
                              onChangeValor={(v) => { setEditValorFgts(v); setEditFgtsManual(true); }}
                            />
                            <CampoRetencao
                              label="DCTF" percentual={editPercentualDctf} valor={editValorDctf}
                              onChangePercentual={(v) => { setEditPercentualDctf(v); setEditDctfManual(false); }}
                              onChangeValor={(v) => { setEditValorDctf(v); setEditDctfManual(true); }}
                            />
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Observação</label>
                              <input style={selStyleLote} value={editObservacao} onChange={(e) => setEditObservacao(e.target.value)} /></div>
                            <div className="flex items-end"><span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Valor líquido: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(editValorLiquido)}</strong></span></div>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Conta bancária (opcional)</label>
                              <select style={selStyleLote} value={editContaCorrenteId} onChange={(e) => setEditContaCorrenteId(e.target.value)}>
                                <option value="">Não informar</option>
                                {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
                              </select></div>
                          </div>
                          {editValorVale > 0 && (
                            <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
                              Desconto de vale (já incluído acima): <strong>{formatBRL(editValorVale)}</strong> — para ajustar o valor do vale, edite-o em "Relatório de vales e descontos".
                            </p>
                          )}
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3 items-end">
                            <div className="flex items-center gap-2" style={{ paddingBottom: "0.4rem" }}>
                              <input id="folha-edit-recorrente" type="checkbox" checked={editRecorrente} onChange={(e) => setEditRecorrente(e.target.checked)} />
                              <label htmlFor="folha-edit-recorrente" style={{ fontSize: "0.8rem" }}>Recorrente</label>
                            </div>
                            {editRecorrente && (
                              <div><label style={labelStyleLote}>Dia de vencimento no mês seguinte (1–28)</label>
                                <input type="number" min={1} max={28} style={selStyleLote} value={editDiaVencimento} onChange={(e) => setEditDiaVencimento(e.target.value)} /></div>
                            )}
                          </div>
                          {editMsg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{editMsg}</p>}
                          <div className="flex items-center gap-2">
                            <button className="btn-primary" title="Salvar as alterações deste lançamento" style={{ fontSize: "0.78rem" }} onClick={() => pedirSalvarEdicao(r)} disabled={editSalvando}>
                              <Check size={13} /> {editSalvando ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="btn-ghost" title="Cancelar a edição" style={{ fontSize: "0.78rem" }} onClick={() => setEditingId(null)}>Cancelar</button>
                          </div>
                        </div>
                      </td></tr>
                    )}
                  </Fragment>
                );
              })}
              {excluirErro && <tr><td colSpan={admin ? 12 : 11} style={{ color: "var(--red)", fontSize: "0.8rem" }}>{excluirErro}</td></tr>}
              {unificada && !unificadaOrdenada.length && <tr><td colSpan={admin ? 12 : 11} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{unificada.length ? "Nenhum lançamento de folha para os filtros escolhidos." : "Nenhum lançamento de folha ainda."}</td></tr>}
            </tbody>
          </table>
        </div>
        )}
      </SecaoRecolhivel>

      {/* Relatório de guias de FGTS/DCTF já lançadas — dados estruturados
          (não só o PDF anexado), para acompanhar competência a competência.
          Só sob Funcionário e Todos: era este bloco que aparecia embaixo de
          Empreita, Contrato e Diária cobrando encargo de CLT de quem não é
          CLT. Quem decide agora é `capacidades.guias`, não um `if` local. */}
      {capacidades.guias && (
      <SecaoRecolhivel titulo="Guias de FGTS/DCTF lançadas" icon={Filter}
        aberta={grupoAberto("guias")} onAlternar={() => alternarGrupo("guias")}
        badge={guias ? <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{guias.length}</span> : null}
        descricao="Competência, valores e origem (manual ou leitura automática) de cada guia">
        {excluirGuiaErro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{excluirGuiaErro}</p>}
        {!guias || !guias.length ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma guia lançada ainda.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Tipo" campo="tipo" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} />
                <ThOrdenavel label="Competência" campo="competencia" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} />
                <ThOrdenavel label="Cód. receita" campo="codigo_receita" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} />
                <ThOrdenavel label="Principal" campo="valor_principal" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} alinhar="right" />
                <ThOrdenavel label="Multa" campo="valor_multa" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} alinhar="right" />
                <ThOrdenavel label="Juros" campo="valor_juros" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} alinhar="right" />
                <ThOrdenavel label="Total" campo="valor_total" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} alinhar="right" />
                <ThOrdenavel label="Vencimento" campo="data_vencimento" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} />
                <ThOrdenavel label="Origem" campo="origem" coluna={ordGuias.coluna} dir={ordGuias.dir} ordenar={ordGuias.ordenar} />
                <th>Ações</th>
              </tr></thead>
              <tbody>
                {ordGuias.linhasOrdenadas.map((g) => (
                  <Fragment key={g.id}>
                  <tr>
                    <td>{g.tipo === "fgts" ? "FGTS" : "DCTF"}</td>
                    <td>{mesCompLabel(g.competencia)}</td>
                    <td>{g.codigo_receita || "—"}</td>
                    <td style={{ textAlign: "right" }}>{formatBRL(g.valor_principal)}</td>
                    <td style={{ textAlign: "right" }}>{formatBRL(g.valor_multa)}</td>
                    <td style={{ textAlign: "right" }}>{formatBRL(g.valor_juros)}</td>
                    <td style={{ textAlign: "right", fontWeight: 700 }}>{formatBRL(g.valor_total)}</td>
                    <td>{formatDate(g.data_vencimento)}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{g.origem === "leitura_automatica" ? "Leitura automática" : "Manual"}</td>
                    <td>
                      <span className="flex items-center gap-2">
                        <button className="btn-ghost" title="Editar esta guia" style={{ fontSize: "0.72rem" }}
                          onClick={() => (editingGuiaId === g.id ? setEditingGuiaId(null) : iniciarEdicaoGuia(g))}>
                          <Pencil size={13} />
                        </button>
                        <button className="btn-ghost" title="Excluir esta guia" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                          disabled={excluindoGuiaId === g.id}
                          onClick={() => excluirGuiaHandler(g)}>
                          <Trash2 size={13} />
                        </button>
                      </span>
                    </td>
                  </tr>
                  {editingGuiaId === g.id && (
                    <tr>
                      <td colSpan={10} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                          <div><label style={labelStyleLote}>Tipo</label>
                            <select style={selStyleLote} value={editGuiaTipo} onChange={(e) => setEditGuiaTipo(e.target.value as "fgts" | "dctf")}>
                              <option value="fgts">FGTS</option>
                              <option value="dctf">DCTF</option>
                            </select></div>
                          <div><label style={labelStyleLote}>Competência (mês)</label>
                            <input type="month" style={selStyleLote} value={editGuiaCompetencia} onChange={(e) => setEditGuiaCompetencia(e.target.value)} /></div>
                          {editGuiaTipo === "dctf" && (
                            <div><label style={labelStyleLote}>Código da receita</label>
                              <input style={selStyleLote} value={editGuiaCodigoReceita} onChange={(e) => setEditGuiaCodigoReceita(e.target.value)} /></div>
                          )}
                          <div><label style={labelStyleLote}>Vencimento</label>
                            <input type="date" style={selStyleLote} value={editGuiaDataVencimento} onChange={(e) => setEditGuiaDataVencimento(e.target.value)} /></div>
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                          <div><label style={labelStyleLote}>Valor principal (R$)</label>
                            <CampoMoeda style={selStyleLote} value={Number(editGuiaValorPrincipal) || 0} onChange={(v) => setEditGuiaValorPrincipal(v ? String(v) : "")} /></div>
                          <div><label style={labelStyleLote}>Multa (R$)</label>
                            <CampoMoeda style={selStyleLote} value={Number(editGuiaValorMulta) || 0} onChange={(v) => setEditGuiaValorMulta(v ? String(v) : "")} /></div>
                          <div><label style={labelStyleLote}>Juros (R$)</label>
                            <CampoMoeda style={selStyleLote} value={Number(editGuiaValorJuros) || 0} onChange={(v) => setEditGuiaValorJuros(v ? String(v) : "")} /></div>
                          <div><label style={labelStyleLote}>Linha digitável</label>
                            <input style={selStyleLote} value={editGuiaLinhaDigitavel} onChange={(e) => setEditGuiaLinhaDigitavel(e.target.value)} /></div>
                        </div>
                        {editGuiaMsg && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{editGuiaMsg}</p>}
                        <div style={{ display: "flex", gap: "0.5rem" }}>
                          <button className="btn-primary" disabled={editGuiaSalvando} onClick={() => salvarEdicaoGuia(g.id)}>
                            <Check size={14} /> {editGuiaSalvando ? "Salvando…" : "Salvar"}
                          </button>
                          <button className="btn-ghost" onClick={() => setEditingGuiaId(null)}>Cancelar</button>
                        </div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SecaoRecolhivel>
      )}

      {/* Relatório de vales e descontos — vale de FUNCIONÁRIO, filtrável e
          ordenável. Estava no mesmo card dos vales de empreitada/contrato/
          diária, e por isso aparecia inteiro sob qualquer categoria: quem
          escolhia "Empreita" via a tabela de vales de CLT logo abaixo. São
          dois relatórios de coisas diferentes e agora são dois cards, cada um
          declarado por sua categoria. */}
      {capacidades.valeFuncionario && (
      <SecaoRecolhivel titulo="Vales de funcionário" icon={Filter}
        aberta={grupoAberto("vales_funcionario")} onAlternar={() => alternarGrupo("vales_funcionario")}
        badge={vales ? <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{valesOrdenados.length}</span> : null}
        descricao="Vales de funcionário lançados, com parcelamento e status de aplicação">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Data do vale — de</label>
            <input type="date" style={selStyleLote} value={fValeDe} onChange={(e) => setFValeDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Data do vale — até</label>
            <input type="date" style={selStyleLote} value={fValeAte} onChange={(e) => setFValeAte(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Pessoa</label>
            <select style={selStyleLote} value={fValePessoa} onChange={(e) => setFValePessoa(e.target.value)}>
              <option value="">Todos</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></div>
        </div>
        {excluirValeErro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{excluirValeErro}</p>}
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <th style={{ width: "1.5rem" }} />
              <ThOrdenavel label="Data" campo="data_pagamento" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} />
              <ThOrdenavel label="Pessoa" campo="pessoa_nome" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} />
              <ThOrdenavel label="Valor bruto" campo="valor_total" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} alinhar="right" />
              <ThOrdenavel label="Nº parcelas" campo="parcelas" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} alinhar="right" />
              <ThOrdenavel label="Valor da parcela" campo="valor_parcela" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} alinhar="right" />
              <ThOrdenavel label="Status" campo="status_desconto" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} />
              <ThOrdenavel label="Valor pago" campo="valor_pago" coluna={valeColuna} dir={valeDir} ordenar={valeOrdenar} alinhar="right" />
              <th>Documento</th>
              <th>Conta bancária</th>
              <th>Origem</th>
              <th>Ações</th>
            </tr></thead>
            <tbody>
              {valesOrdenados.map((v: any) => (
                <Fragment key={v.id}>
                <tr style={{ cursor: "pointer" }} onClick={() => setExpandedValeId(expandedValeId === v.id ? null : v.id)}>
                  <td>{expandedValeId === v.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                  <td style={{ fontSize: "0.78rem" }}>{v.data_pagamento ? v.data_pagamento.split("-").reverse().join("/") : "—"}</td>
                  <td style={{ fontSize: "0.82rem" }}>{v.pessoa_nome}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(v.valor_total)}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{v.parcelas}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{formatBRL(v.valor_parcela)}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{v.status_desconto}</td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{formatBRL(v.valor_pago)}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{v.numero_documento_pagamento || "—"}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{rotuloContaVale(v.conta_corrente_id)}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}
                      title={v.origem_lancamento ? `${v.origem_lancamento.produto} — nota ${v.origem_lancamento.numero_documento ?? "s/ nº"} — ${v.origem_lancamento.fornecedor_cliente ?? ""}` : undefined}>
                    {v.origem_lancamento
                      ? `${v.origem_lancamento.numero_lancamento} — ${v.origem_lancamento.produto}`
                      : "Lançamento avulso"}
                  </td>
                  <td>
                    <span className="flex items-center gap-1">
                      {/* O MESMO menu de ações do painel "Descontos de vale"
                          da folha — mesmo modal, mesmas regras, nenhuma
                          duplicada. Ele só existia lá dentro, e é AQUI que o
                          dono procura o vale: este card é a lista dos vales.
                          Sem competência fixa de propósito — a linha é do
                          vale inteiro, não de um mês, então quem escolhe o mês
                          alvo é o contexto do servidor (a 1ª competência ainda
                          pendente; ver AcoesValeModal). É também a única porta
                          de um vale CANCELADO e a de um mês desconsiderado que
                          não tem folha lançada: nos dois casos não existe
                          painel de descontos nenhum para abrigar o botão. */}
                      <button className="btn-ghost" title="Ações do vale — reparcelar, abater, desconsiderar um mês, cancelar (e desfazer)"
                        style={{ fontSize: "0.72rem" }}
                        onClick={(e) => { e.stopPropagation(); setAcoesVale({ valeId: v.id, pessoaNome: v.pessoa_nome }); }}>
                        <Pencil size={13} /> Ações
                      </button>
                      <button className="btn-ghost" title="Excluir este vale" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                        disabled={excluindoValeId === v.id}
                        onClick={(e) => { e.stopPropagation(); excluirValeHandler(v); }}>
                        <Trash2 size={13} />
                      </button>
                    </span>
                  </td>
                </tr>
                {expandedValeId === v.id && (
                  <tr>
                    <td colSpan={12} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                      {editingValeId === v.id ? (
                        <div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Pessoa</label>
                              <select style={selStyleLote} value={editValePessoaId} onChange={(e) => setEditValePessoaId(e.target.value)}>
                                {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                              </select></div>
                            <div><label style={labelStyleLote}>Valor total (R$)</label>
                              <CampoMoeda style={selStyleLote} value={Number(editValeValorTotal) || 0} onChange={(v) => setEditValeValorTotal(v ? String(v) : "")} /></div>
                            <div><label style={labelStyleLote}>Forma de pagamento</label>
                              <select style={selStyleLote} value={editValeFormaPagamento} onChange={(e) => setEditValeFormaPagamento(e.target.value)}>
                                {FORMAS_VALE.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                              </select></div>
                            <div><label style={labelStyleLote}>Data do pagamento</label>
                              <input type="date" style={selStyleLote} value={editValeDataPagamento} onChange={(e) => setEditValeDataPagamento(e.target.value)} /></div>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Parcelas do desconto</label>
                              <input type="number" min={1} style={selStyleLote} value={editValeParcelas} onChange={(e) => setEditValeParcelas(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Data do primeiro desconto</label>
                              <input type="month" style={selStyleLote} value={editValeCompetenciaInicio} onChange={(e) => setEditValeCompetenciaInicio(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Nº do documento do pagamento</label>
                              <input style={selStyleLote} value={editValeNumeroDocumento} onChange={(e) => setEditValeNumeroDocumento(e.target.value)} /></div>
                            <div><label style={labelStyleLote}>Observação</label>
                              <input style={selStyleLote} value={editValeObservacao} onChange={(e) => setEditValeObservacao(e.target.value)} /></div>
                          </div>
                          {contaObrigatoriaVale(editValeFormaPagamento) && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                              <div><label style={labelStyleLote}>Conta bancária</label>
                                <select style={selStyleLote} value={editValeContaCorrenteId} onChange={(e) => setEditValeContaCorrenteId(e.target.value)}>
                                  <option value="">Selecione…</option>
                                  {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
                                </select></div>
                            </div>
                          )}
                          {editValeMsg && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{editValeMsg}</p>}
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button className="btn-primary" disabled={editValeSalvando} onClick={() => salvarEdicaoVale(v.id)}>
                              <Check size={14} /> {editValeSalvando ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="btn-ghost" onClick={() => { setEditingValeId(null); setExpandedValeId(null); }}>Cancelar</button>
                          </div>
                        </div>
                      ) : (
                        <div>
                          <table className="fazenda-table" style={{ marginBottom: "0.6rem" }}>
                            <thead><tr><th>Nº parcela</th><th>Competência</th><th style={{ textAlign: "right" }}>Valor</th><th>Situação</th><th></th></tr></thead>
                            <tbody>
                              {(v.parcelas_detalhe || []).map((p: any, i: number) => (
                                <tr key={p.id}>
                                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{i + 1}/{(v.parcelas_detalhe || []).length}</td>
                                  <td style={{ fontSize: "0.78rem" }}>{mesCompLabel(p.competencia)}</td>
                                  <td style={{ textAlign: "right", fontSize: "0.78rem" }}>
                                    {editandoParcela?.parcelaId === p.id ? (
                                      <CampoMoeda autoFocus
                                        style={{ ...selStyleLote, width: "7rem", textAlign: "right", display: "inline-block" }}
                                        value={Number(editParcelaValor) || 0} onChange={(v) => setEditParcelaValor(v ? String(v) : "")} />
                                    ) : formatBRL(p.valor)}
                                  </td>
                                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{p.aplicada ? "Aplicada na folha" : "Pendente"}</td>
                                  <td>
                                    {editandoParcela?.parcelaId === p.id ? (
                                      <div style={{ display: "flex", gap: "0.3rem" }}>
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} disabled={parcelaSalvando}
                                          onClick={() => salvarParcela(v, p)}>
                                          <Check size={13} /> {parcelaSalvando ? "Salvando…" : "Salvar"}
                                        </button>
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }}
                                          onClick={() => { setEditandoParcela(null); setParcelaErro(null); }}>Cancelar</button>
                                      </div>
                                    ) : (
                                      <div style={{ display: "flex", gap: "0.3rem" }}>
                                        <button className="btn-ghost" title="Editar esta parcela" style={{ fontSize: "0.72rem" }}
                                          onClick={() => abrirEdicaoParcela(v, p)}>
                                          <Pencil size={12} />
                                        </button>
                                        <button className="btn-ghost" title={p.aplicada ? "Parcela já aplicada na folha — não pode ser excluída" : "Excluir esta parcela"}
                                          style={{ fontSize: "0.72rem", color: p.aplicada ? undefined : "var(--red)" }}
                                          disabled={p.aplicada} onClick={() => pedirExcluirParcela(v, p)}>
                                          <Trash2 size={12} />
                                        </button>
                                      </div>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {parcelaErro && editandoParcela?.valeId === v.id && (
                            <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{parcelaErro}</p>
                          )}
                          {excluirParcelaErro && excluindoParcela === null && (
                            <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{excluirParcelaErro}</p>
                          )}
                          {v.observacao && <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>Observação: {v.observacao}</p>}
                          <button className="btn-ghost" onClick={() => iniciarEdicaoVale(v)}>
                            <Pencil size={12} /> Editar vale
                          </button>
                          <ComprovanteVale tipo="funcionario" valeId={v.id} />
                        </div>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
              {vales && !valesOrdenados.length && <tr><td colSpan={12} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{vales.length ? "Nenhum vale para os filtros escolhidos." : "Nenhum vale lançado ainda."}</td></tr>}
            </tbody>
          </table>
        </div>
      </SecaoRecolhivel>
      )}

      {capacidades.valeAvulso && (
      <SecaoRecolhivel titulo="Vales de empreitada, contrato e diária" icon={Filter}
        aberta={grupoAberto("vales_avulsos")} onAlternar={() => alternarGrupo("vales_avulsos")}
        badge={valesAvulsos ? <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{valesAvulsosOrdenados.length}</span> : null}
        descricao="Adiantamentos abatidos da próxima parcela/etapa pendente">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Data do vale — de</label>
            <input type="date" style={selStyleLote} value={fValeDe} onChange={(e) => setFValeDe(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Data do vale — até</label>
            <input type="date" style={selStyleLote} value={fValeAte} onChange={(e) => setFValeAte(e.target.value)} /></div>
          <div><label style={labelStyleLote}>Pessoa</label>
            <select style={selStyleLote} value={fValePessoa} onChange={(e) => setFValePessoa(e.target.value)}>
              <option value="">Todos</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></div>
        </div>
        {excluirValeAvulsoErro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{excluirValeAvulsoErro}</p>}
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <th style={{ width: "1.5rem" }} />
              <ThOrdenavel label="Data" campo="data_pagamento" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} />
              <ThOrdenavel label="Pessoa" campo="pessoa_nome" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} />
              <ThOrdenavel label="Abatido de" campo="origem_descricao" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} />
              <th>Parcela</th>
              <ThOrdenavel label="Valor" campo="valor" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} alinhar="right" />
              <ThOrdenavel label="Forma de pagamento" campo="forma_pagamento" coluna={valeAvulsoColuna} dir={valeAvulsoDir} ordenar={valeAvulsoOrdenar} />
              <th>Conta bancária</th>
              <th>Origem</th>
              <th>Ações</th>
            </tr></thead>
            <tbody>
              {valesAvulsosOrdenados.map((v: any) => (
                <Fragment key={v.id}>
                <tr style={{ cursor: "pointer" }} onClick={() => setExpandedValeAvulsoId(expandedValeAvulsoId === v.id ? null : v.id)}>
                  <td>{expandedValeAvulsoId === v.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
                  <td style={{ fontSize: "0.78rem" }}>{v.data_pagamento ? v.data_pagamento.split("-").reverse().join("/") : "—"}</td>
                  <td style={{ fontSize: "0.82rem" }}>{v.pessoa_nome}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{v.origem_descricao}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                    {v.total_parcelas_origem
                      ? (v.parcelas_referenciadas || []).map((r: any) => r.numero_parcela).filter(Boolean).join(", ") || "—"
                      : "—"}
                    {v.total_parcelas_origem ? ` de ${v.total_parcelas_origem}` : ""}
                  </td>
                  <td style={{ textAlign: "right", fontSize: "0.78rem", fontWeight: 600 }}>{formatBRL(v.valor)}</td>
                  <td style={{ fontSize: "0.78rem" }}>{FORMAS_VALE_AVULSO.find((f) => f.value === v.forma_pagamento)?.label || v.forma_pagamento}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{rotuloContaVale(v.conta_corrente_id)}</td>
                  <td style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}
                      title={v.origem_lancamento ? `${v.origem_lancamento.produto} — nota ${v.origem_lancamento.numero_documento ?? "s/ nº"} — ${v.origem_lancamento.fornecedor_cliente ?? ""}` : undefined}>
                    {v.origem_lancamento
                      ? `${v.origem_lancamento.numero_lancamento} — ${v.origem_lancamento.produto}`
                      : "Lançamento avulso"}
                  </td>
                  <td>
                    <button className="btn-ghost" title="Excluir este vale" style={{ fontSize: "0.72rem", color: "var(--red)" }}
                      disabled={excluindoValeAvulsoId === v.id}
                      onClick={(e) => { e.stopPropagation(); excluirValeAvulsoHandler(v); }}>
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
                {expandedValeAvulsoId === v.id && (
                  <tr>
                    <td colSpan={10} style={{ background: "var(--surface-2)", padding: "0.75rem 1rem" }}>
                      {editingValeAvulsoId === v.id ? (
                        <div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Abatido de</label>
                              <input style={selStyleLote} value={v.origem_descricao} disabled /></div>
                            <div><label style={labelStyleLote}>Valor (R$)</label>
                              <CampoMoeda style={selStyleLote} value={Number(editValeAvulsoValor) || 0} onChange={(v) => setEditValeAvulsoValor(v ? String(v) : "")} /></div>
                            <div><label style={labelStyleLote}>Forma de pagamento</label>
                              <select style={selStyleLote} value={editValeAvulsoFormaPagamento} onChange={(e) => setEditValeAvulsoFormaPagamento(e.target.value)}>
                                {FORMAS_VALE_AVULSO.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
                              </select></div>
                            <div><label style={labelStyleLote}>Data do pagamento</label>
                              <input type="date" style={selStyleLote} value={editValeAvulsoDataPagamento} onChange={(e) => setEditValeAvulsoDataPagamento(e.target.value)} /></div>
                          </div>
                          {contaObrigatoriaValeAvulso(editValeAvulsoFormaPagamento) && (
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                              <div><label style={labelStyleLote}>Conta bancária</label>
                                <select style={selStyleLote} value={editValeAvulsoContaCorrenteId} onChange={(e) => setEditValeAvulsoContaCorrenteId(e.target.value)}>
                                  <option value="">Selecione…</option>
                                  {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
                                </select></div>
                            </div>
                          )}
                          <div className="grid grid-cols-1 gap-3 mb-3">
                            <div><label style={labelStyleLote}>Observação</label>
                              <input style={selStyleLote} value={editValeAvulsoObservacao} onChange={(e) => setEditValeAvulsoObservacao(e.target.value)} /></div>
                          </div>
                          {editValeAvulsoMsg && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.5rem" }}>{editValeAvulsoMsg}</p>}
                          <div style={{ display: "flex", gap: "0.5rem" }}>
                            <button className="btn-primary" disabled={editValeAvulsoSalvando} onClick={() => salvarEdicaoValeAvulso(v)}>
                              <Check size={14} /> {editValeAvulsoSalvando ? "Salvando…" : "Salvar"}
                            </button>
                            <button className="btn-ghost" onClick={() => { setEditingValeAvulsoId(null); setExpandedValeAvulsoId(null); }}>Cancelar</button>
                          </div>
                        </div>
                      ) : (
                        <div>
                          {v.observacao && <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>Observação: {v.observacao}</p>}
                          <button className="btn-ghost" onClick={() => iniciarEdicaoValeAvulso(v)}>
                            <Pencil size={12} /> Editar vale
                          </button>
                          <ComprovanteVale tipo="avulso" valeId={v.id} />
                        </div>
                      )}
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
              {valesAvulsos && !valesAvulsosOrdenados.length && <tr><td colSpan={10} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>{valesAvulsos.length ? "Nenhum vale para os filtros escolhidos." : "Nenhum vale de empreitada/contrato/diária lançado ainda."}</td></tr>}
            </tbody>
          </table>
        </div>
      </SecaoRecolhivel>
      )}

      {/* A listagem da tela própria da categoria — "Empreitas lançadas",
          "Controle de diárias", "Férias lançadas"… É onde moram as ações que
          só existem ali (concluir etapa, redistribuir parcelas, encerrar e
          cobrar, reabrir, marcar como pago). O formulário correspondente fica
          sob o card "Lançar"; aqui só o que já foi lançado. */}
      {capacidades.telaPropria && telaDaCategoria("listar")}

      </>))}
      {/* ↑ fim do card "Consultar" */}

      {divergenciaParcela && (
        <ModalDivergenciaVale
          valorCalculado={divergenciaParcela.valorCalculado}
          valorInformado={divergenciaParcela.valorInformado}
          itensPendentes={(divergenciaParcela.vale.parcelas_detalhe || [])
            // Só as parcelas POSTERIORES à editada entram na redistribuição —
            // nunca mexe em parcela anterior/já vencida (mesma regra do backend).
            .filter((p: any) => p.id !== divergenciaParcela.parcela.id && !p.aplicada && p.competencia > divergenciaParcela.parcela.competencia)
            .map((p: any) => ({ id: p.id, label: mesCompLabel(p.competencia), valor: p.valor }))}
          salvando={parcelaSalvando}
          onCancelar={() => setDivergenciaParcela(null)}
          onConfirmar={(acao, valoresItens) => salvarParcela(divergenciaParcela.vale, divergenciaParcela.parcela, acao, valoresItens)}
        />
      )}
      {divergenciaTotalParcela && (
        <ModalConfirmarDivergenciaTotal
          valorVale={divergenciaTotalParcela.valorVale}
          valorLancado={divergenciaTotalParcela.valorLancado}
          salvando={parcelaSalvando}
          onCancelar={() => setDivergenciaTotalParcela(null)}
          onConfirmar={() => salvarParcela(
            divergenciaTotalParcela.vale, divergenciaTotalParcela.parcela, "redistribuir_livre",
            divergenciaTotalParcela.valoresItens, true,
          )}
        />
      )}
      {divergenciaValeAvulso && (
        <ModalDivergenciaVale
          valorCalculado={divergenciaValeAvulso.valorCalculado}
          valorInformado={divergenciaValeAvulso.valorInformado}
          itensPendentes={[]}
          permiteRedistribuir={divergenciaValeAvulso.v.origem_tipo !== "diaria"}
          salvando={editValeAvulsoSalvando}
          onCancelar={() => setDivergenciaValeAvulso(null)}
          onConfirmar={(acao) => salvarEdicaoValeAvulso(divergenciaValeAvulso.v, acao)}
        />
      )}
      {(() => {
        // O pop-up do ATO do pagamento (ver PagarFolhaModal): valor distinto
        // por verba e a decisão sobre a diferença. Vive fora da tabela, como
        // os demais modais — a linha não tem largura para o discriminado.
        const emPagamento = (regs || []).find((r) => r.id === pagandoId);
        if (!emPagamento) return null;
        return (
          <PagarFolhaModal
            registro={emPagamento}
            contasCorrentes={contasCorrentes}
            onPago={() => {
              // Recarrega o que o pagamento pode ter mexido: a folha, o
              // relatório de vales (a decisão muda saldo/parcelas) e a visão
              // unificada.
              setPagandoId(null);
              carregar(); carregarUnificada(); carregarVales();
            }}
            onFechar={() => setPagandoId(null)}
          />
        );
      })()}
      {acoesVale && (
        <AcoesValeModal
          valeId={acoesVale.valeId}
          pessoaNome={acoesVale.pessoaNome}
          competencia={acoesVale.competencia}
          contasCorrentes={contasCorrentes}
          onFeito={() => {
            // Recarrega tudo o que a ação pode ter mexido: a folha (o
            // desconto do mês muda), o relatório de vales (saldo/parcelas) e
            // a visão unificada. "Desconsiderar"/"cancelar" mexem também no
            // Financeiro, mas essa tela não mostra o extrato.
            setAcoesVale(null);
            carregar(); carregarUnificada(); carregarVales();
          }}
          onFechar={() => setAcoesVale(null)}
        />
      )}
      {excluindoParcela && (
        <Modal title="Excluir parcela do vale" onClose={() => setExcluindoParcela(null)} width="460px">
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.85rem" }}>
            <div className="flex items-start gap-2" style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.7rem 0.9rem" }}>
              <p style={{ marginBottom: "0.3rem" }}>Excluir esta parcela muda o valor total lançado do vale.</p>
              <p>Valor da parcela: <b>{formatBRL(excluindoParcela.valor_parcela)}</b></p>
              <p>Valor do vale: <b>{formatBRL(excluindoParcela.valor_vale)}</b></p>
              <p>Soma das parcelas após excluir (concedendo): <b>{formatBRL(excluindoParcela.soma_apos)}</b></p>
            </div>
            {excluirParcelaErro && <p style={{ color: "var(--red)" }}>{excluirParcelaErro}</p>}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.3rem" }}>
              <button className="btn-ghost" style={{ textAlign: "left", padding: "0.6rem 0.8rem" }}
                disabled={excluirParcelaSalvando} onClick={() => confirmarExcluirParcela("conceder")}>
                <b>Conceder</b>
                <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                  Só esta parcela some — o valor total do vale não muda, a soma das parcelas fica menor.
                </div>
              </button>
              {excluindoParcela.parcelas_pendentes_posteriores > 0 && (
                <button className="btn-ghost" style={{ textAlign: "left", padding: "0.6rem 0.8rem" }}
                  disabled={excluirParcelaSalvando} onClick={() => confirmarExcluirParcela("redistribuir_igual")}>
                  <b>Redistribuir igualmente</b>
                  <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                    Divide o valor desta parcela entre as {excluindoParcela.parcelas_pendentes_posteriores} parcela(s) pendente(s) posteriores — a soma se mantém.
                  </div>
                </button>
              )}
              <button className="btn-ghost" disabled={excluirParcelaSalvando} onClick={() => setExcluindoParcela(null)}>Cancelar</button>
            </div>
          </div>
        </Modal>
      )}
      {confirmarDivergenciaFolha && (
        <Modal title="Valor líquido diferente do lançado" onClose={() => setConfirmarDivergenciaFolha(null)} width="440px">
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.85rem" }}>
            <p>O valor líquido editado é diferente do que estava lançado. Confirma a alteração ou volta para editar?</p>
            <p>Valor líquido anterior: <b>{formatBRL(editValorLiquidoOriginal)}</b></p>
            <p>Valor líquido novo: <b>{formatBRL(editValorLiquido)}</b></p>
            <p>Diferença: <b style={{ color: editValorLiquido - editValorLiquidoOriginal >= 0 ? "var(--green-light)" : "var(--red)" }}>
              {formatBRL(editValorLiquido - editValorLiquidoOriginal)}
            </b></p>
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.3rem" }}>
              <button className="btn-primary" disabled={editSalvando}
                onClick={() => { const r = confirmarDivergenciaFolha; setConfirmarDivergenciaFolha(null); salvarEdicao(r); }}>
                <Check size={14} /> {editSalvando ? "Salvando…" : "Confirmar valor diferente"}
              </button>
              <button className="btn-ghost" onClick={() => setConfirmarDivergenciaFolha(null)}>Voltar ao lançamento</button>
            </div>
          </div>
        </Modal>
      )}
      {reciboLinha && <ReciboModal lanc={reciboLinha} onClose={() => setReciboLinha(null)} />}

      {/* A ficha da pessoa lê o ledger INTEIRO (`unificada`), não o mês
          filtrado: a pergunta que ela responde é justamente a que atravessa
          competências — a parcela 3/13 de setembro nasceu de um vale de
          março, e o vale de março não está no mês em tela. */}
      {fichaPessoaId != null && (() => {
        const p = pessoas.find((x) => x.id === fichaPessoaId);
        return (
          <LinhaTempoPessoa
            pessoa={p || { id: fichaPessoaId, nome: "—", tipos: [] }}
            linhas={unificada || []}
            vales={(vales || []) as ValeDaLinhaTempo[]}
            ano={(mesEmTela || new Date().toISOString().slice(0, 7)).slice(0, 4)}
            onFechar={() => setFichaPessoaId(null)}
          />
        );
      })()}
      {resultadoDivergencia && (
        <ModalResultadoDivergenciaVale
          valorPago={resultadoDivergencia.valorPago}
          valorDesconto={resultadoDivergencia.valorDesconto}
          onFechar={() => setResultadoDivergencia(null)}
        />
      )}
    </div>
  );
}

const FORMAS_VALE = [
  { value: "dinheiro", label: "Dinheiro" }, { value: "pix", label: "Pix" },
  { value: "transferencia", label: "Transferência" }, { value: "desconto_integral_folha", label: "Desconto integral na próxima folha" },
];

const FORMAS_VALE_AVULSO = [
  { value: "dinheiro", label: "Dinheiro" }, { value: "pix", label: "Pix" },
  { value: "transferencia", label: "Transferência" }, { value: "desconto_proximo_pagamento", label: "Descontar do próximo pagamento" },
];

// Espelha `_validar_conta_vale`/`_validar_conta_vale_avulso` (backend): a
// conta bancária só é obrigatória quando o dinheiro sai AGORA (dinheiro/pix/
// transferência) — "desconto_integral_folha"/"desconto_proximo_pagamento" não
// movimentam banco nenhum na hora do vale.
const contaObrigatoriaVale = (forma: string) => forma !== "desconto_integral_folha";
const contaObrigatoriaValeAvulso = (forma: string) => forma !== "desconto_proximo_pagamento";

/**
 * Comprovante de pagamento do vale (D7-D10) — mesmo padrão visual de
 * "Anexos" já usado no lançamento financeiro (Dropzone + lista com link/
 * excluir, ver app/financeiro/page.tsx), só que ancorado no vale em vez do
 * lançamento: aqui não há categoria/nº de documento para escolher, porque
 * o vale já é o documento inteiro — só falta anexar a prova de que o
 * dinheiro foi entregue (recibo assinado, foto do PIX etc.).
 */
function ComprovanteVale({ tipo, valeId }: { tipo: "funcionario" | "avulso"; valeId: number }) {
  const [comprovantes, setComprovantes] = useState<{ id: number; nome_arquivo: string; mime_type: string; criado_em: string }[] | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    listarComprovantesVale(tipo, valeId).then(setComprovantes).catch(() => setComprovantes([]));
  }, [tipo, valeId]);

  const enviar = async (file: File) => {
    setEnviando(true); setErro(null);
    try {
      const novo = await anexarComprovanteVale(tipo, valeId, file);
      setComprovantes((p) => [...(p || []), { id: novo.id, nome_arquivo: novo.nome_arquivo, mime_type: file.type, criado_em: new Date().toISOString() }]);
    } catch (e: any) {
      setErro(e.message || "Erro ao anexar o comprovante");
    } finally {
      setEnviando(false);
    }
  };

  const remover = async (id: number) => {
    try {
      await excluirComprovanteVale(id);
      setComprovantes((p) => (p || []).filter((a) => a.id !== id));
    } catch (e: any) {
      setErro(e.message || "Erro ao excluir o comprovante");
    }
  };

  return (
    <div style={{ borderTop: "1px solid var(--border)", paddingTop: "0.6rem", marginTop: "0.6rem" }}>
      <label style={labelStyleLote}>Comprovante de pagamento</label>
      <Dropzone
        compact
        accept="application/pdf,image/jpeg,image/png"
        disabled={enviando}
        label={enviando ? "Enviando…" : "Arraste o comprovante aqui, ou"}
        onFiles={(files) => enviar(files[0])}
      />
      {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem", margin: "0.3rem 0" }}>{erro}</p>}
      {comprovantes === null ? (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Carregando comprovantes…</p>
      ) : comprovantes.length === 0 ? (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Nenhum comprovante anexado ainda.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0.3rem 0 0" }}>
          {comprovantes.map((a) => (
            <li key={a.id} className="flex items-center gap-2" style={{ padding: "0.2rem 0", fontSize: "0.78rem" }}>
              <a href={urlComprovanteVale(a.id)} target="_blank" rel="noreferrer" style={{ color: "var(--dourado-light)", flex: 1 }}
                title="Abrir este comprovante numa aba nova">
                {a.nome_arquivo}
              </a>
              <button type="button" className="btn-ghost" title="Excluir comprovante" onClick={() => remover(a.id)}><Trash2 size={13} /></button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Vale de funcionário — só o formulário de lançamento. A lista de parcelas
 * geradas não aparece mais aqui: ela vira a expansão da folha listada (na
 * competência em que a parcela é aplicada), por decisão explícita do
 * usuário — ver `_detalhe_folha` no backend.
 */
function ValeFuncionarioSection({
  pessoas, contasCorrentes, onLancado,
}: { pessoas: PessoaFolha[]; contasCorrentes: ContaCorrenteCadastro[]; onLancado: () => void }) {
  const [pessoaId, setPessoaId] = useState("");
  const [valorTotal, setValorTotal] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("dinheiro");
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [parcelas, setParcelas] = useState("1");
  const [competenciaInicio, setCompetenciaInicio] = useState(() => new Date().toISOString().slice(0, 7));
  const [observacao, setObservacao] = useState("");
  const [numeroDocumentoPagamento, setNumeroDocumentoPagamento] = useState("");
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);
  // Id do vale recém-lançado — só existe DEPOIS de salvo (a rota de
  // comprovante é ancorada no id do vale), por isso o anexo aparece aqui
  // embaixo da mensagem de sucesso, não junto dos campos do formulário.
  const [valeRecemCriadoId, setValeRecemCriadoId] = useState<number | null>(null);

  async function lancar(confirmar = false) {
    setMsg(null);
    if (!pessoaId) { setMsg({ tipo: "erro", texto: "Selecione a pessoa." }); return; }
    if (!valorTotal || parseFloat(valorTotal) <= 0) { setMsg({ tipo: "erro", texto: "Informe o valor do vale." }); return; }
    if (!parcelas || Number(parcelas) < 1) { setMsg({ tipo: "erro", texto: "Informe ao menos 1 parcela." }); return; }
    if (contaObrigatoriaVale(formaPagamento) && !contaCorrenteId) {
      setMsg({ tipo: "erro", texto: "Selecione a conta bancária de onde sai o vale." }); return;
    }
    setSalvando(true);
    try {
      const vale = await criarVale({
        pessoa_id: Number(pessoaId), valor_total: parseFloat(valorTotal), forma_pagamento: formaPagamento,
        data_pagamento: dataPagamento, parcelas: Number(parcelas), competencia_inicio: competenciaInicio,
        observacao: observacao || undefined, numero_documento_pagamento: numeroDocumentoPagamento || undefined,
        conta_corrente_id: contaObrigatoriaVale(formaPagamento) && contaCorrenteId ? Number(contaCorrenteId) : undefined,
        confirmar,
      });
      setValeRecemCriadoId(vale.id);
      setMsg({ tipo: "sucesso", texto: "Vale lançado — o desconto aparecerá na expansão da folha de cada competência afetada." });
      setPessoaId(""); setValorTotal(""); setParcelas("1"); setObservacao(""); setNumeroDocumentoPagamento(""); setContaCorrenteId("");
      onLancado();
    } catch (e: any) {
      if (e.status === 409 && e.detail?.competencias_excedidas) {
        const lista = e.detail.competencias_excedidas.map((c: any) => `${c.competencia} (R$ ${c.total.toFixed(2)})`).join(", ");
        if (window.confirm(`${e.detail.mensagem}\n\nCompetências afetadas: ${lista}\n\nDeseja lançar mesmo assim?`)) {
          await lancar(true);
          setSalvando(false);
          return;
        }
      } else {
        setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar vale" });
      }
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        Adiantamento pago à parte, descontado da folha em uma ou mais competências. Se a soma dos descontos de vale
        de uma competência ultrapassar 40% do salário base da pessoa, o sistema pede confirmação antes de lançar.
      </p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyleLote}>Pessoa</label>
          <select style={selStyleLote} value={pessoaId} onChange={(e) => setPessoaId(e.target.value)}>
            <option value="">Selecione…</option>{pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.tipos.join(", ")})</option>)}
          </select></div>
        <div><label style={labelStyleLote}>Valor total (R$)</label>
          <CampoMoeda style={selStyleLote} value={Number(valorTotal) || 0} onChange={(v) => setValorTotal(v ? String(v) : "")} /></div>
        <div><label style={labelStyleLote}>Forma de pagamento</label>
          <select style={selStyleLote} value={formaPagamento} onChange={(e) => setFormaPagamento(e.target.value)}>
            {FORMAS_VALE.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select></div>
        <div><label style={labelStyleLote}>Data do pagamento</label>
          <input type="date" style={selStyleLote} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div><label style={labelStyleLote}>Parcelas do desconto</label>
          <input type="number" min={1} style={selStyleLote} value={parcelas} onChange={(e) => setParcelas(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Data do primeiro desconto</label>
          <input type="month" style={selStyleLote} value={competenciaInicio} onChange={(e) => setCompetenciaInicio(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Nº do documento do pagamento</label>
          <input style={selStyleLote} title="Para controle de extrato" value={numeroDocumentoPagamento} onChange={(e) => setNumeroDocumentoPagamento(e.target.value)} /></div>
        <div><label style={labelStyleLote}>Observação</label>
          <input style={selStyleLote} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></div>
      </div>
      {contaObrigatoriaVale(formaPagamento) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          <div><label style={labelStyleLote}>Conta bancária</label>
            <select style={selStyleLote} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
              <option value="">Selecione…</option>
              {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
            </select></div>
        </div>
      )}
      {msg?.tipo === "erro" ? (
        <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>
      ) : (
        <AvisoSalvo texto={msg?.texto ?? null} aviso2="Pronto para lançar outro vale." />
      )}
      <button className="btn-primary" title="Lançar o vale" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={() => lancar(false)} disabled={salvando}>
        <Check size={14} /> {salvando ? "Salvando…" : "Lançar vale"}
      </button>
      {/* Só existe depois de salvo (a rota de comprovante é ancorada no id
          do vale) — mesmo componente/mecanismo de anexo já usado na
          listagem de vales abaixo (ver ComprovanteVale). */}
      {valeRecemCriadoId != null && <ComprovanteVale tipo="funcionario" valeId={valeRecemCriadoId} />}
    </div>
  );
}

/*
 * Lançar guia de FGTS/DCTF — manual ou por leitura automática do PDF/foto da
 * guia real (mesmo leitor que já reconhece boleto, ver POST /financeiro/
 * ler-documento). Cria a conta a pagar (mesmo padrão de sempre) e grava os
 * campos estruturados numa tabela própria (GuiaFolhaEncargo), para dar pra
 * montar relatório em cima disso depois. Substitui o antigo "Gerar guias de
 * FGTS/DCTF" (soma projetada dos lançamentos de folha, sem vínculo com uma
 * guia real, sem cálculo de fórmula legal) — decisão do usuário.
 */
function LancarGuiaFgtsDctfSection({ onLancado }: { onLancado: () => void }) {
  const [tipo, setTipo] = useState<"fgts" | "dctf">("fgts");
  const [competencia, setCompetencia] = useState(() => new Date().toISOString().slice(0, 7));
  const [codigoReceita, setCodigoReceita] = useState("");
  const [valorPrincipal, setValorPrincipal] = useState("");
  const [valorMulta, setValorMulta] = useState("0");
  const [valorJuros, setValorJuros] = useState("0");
  const [dataVencimento, setDataVencimento] = useState("");
  const [linhaDigitavel, setLinhaDigitavel] = useState("");
  const [origem, setOrigem] = useState<"manual" | "leitura_automatica">("manual");
  const [arquivoLido, setArquivoLido] = useState<File | null>(null);
  const [lendo, setLendo] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const valorTotal = (parseFloat(valorPrincipal) || 0) + (parseFloat(valorMulta) || 0) + (parseFloat(valorJuros) || 0);

  async function lerGuia(file: File) {
    setLendo(true); setMsg(null);
    // O arquivo em si fica retido independente do resultado da leitura —
    // antes, uma falha na OCR (scan ruim, PDF que o parser não entende,
    // timeout numa conexão rural lenta) deixava `arquivoLido` nulo pra
    // sempre, e "Lançar guia" seguia criando a conta a pagar sem anexar
    // nada, sem avisar o usuário. Anexar não deveria depender de ler.
    setArquivoLido(file);
    try {
      const d = await lerDocumentoFinanceiro(file);
      if (d.tipo_documento === "guia_dctf") setTipo("dctf");
      else if (d.tipo_documento === "guia_fgts") setTipo("fgts");
      if (d.competencia) setCompetencia(d.competencia);
      if (d.codigo_receita) setCodigoReceita(d.codigo_receita);
      if (d.valor_principal != null) setValorPrincipal(String(d.valor_principal));
      if (d.valor_multa != null) setValorMulta(String(d.valor_multa));
      if (d.valor_juros != null) setValorJuros(String(d.valor_juros));
      if (d.data_vencimento) setDataVencimento(d.data_vencimento);
      if (d.linha_digitavel) setLinhaDigitavel(d.linha_digitavel);
      setOrigem("leitura_automatica");
      if (d.tipo_documento !== "guia_fgts" && d.tipo_documento !== "guia_dctf") {
        setMsg({ tipo: "erro", texto: "Este documento não parece uma guia de FGTS/DCTF — confira os campos preenchidos antes de lançar." });
      }
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: `${e.message || "Erro ao ler o documento"} — o arquivo foi mantido para anexo; preencha os campos manualmente.` });
    } finally {
      setLendo(false);
    }
  }

  async function lancar() {
    setMsg(null);
    if (!competencia || !dataVencimento || !valorPrincipal) {
      setMsg({ tipo: "erro", texto: "Informe competência, valor principal e vencimento." });
      return;
    }
    setSalvando(true);
    try {
      const guia = await lancarGuiaFolhaEncargo({
        tipo, competencia, codigo_receita: tipo === "dctf" ? (codigoReceita || undefined) : undefined,
        valor_principal: parseFloat(valorPrincipal) || 0,
        valor_multa: parseFloat(valorMulta) || 0, valor_juros: parseFloat(valorJuros) || 0,
        data_vencimento: dataVencimento, linha_digitavel: linhaDigitavel || undefined, origem,
      });
      let falhaAnexo: string | null = null;
      if (arquivoLido && guia.numero_lancamento) {
        // numero_documento = número do boleto/linha digitável — é o que torna
        // a guia arquivada pesquisável por esse número em Central de
        // Documentos e no filtro de Financeiro (pedido explícito do usuário).
        try {
          await anexarArquivoLancamento(
            guia.numero_lancamento, arquivoLido, tipo === "fgts" ? "Guia FGTS" : "Guia DCTF",
            linhaDigitavel || undefined, dataVencimento || undefined,
          );
        } catch (e: any) {
          falhaAnexo = e.message || "erro desconhecido";
        }
      }
      setMsg(falhaAnexo
        ? { tipo: "erro", texto: `Guia de ${tipo === "fgts" ? "FGTS" : "DCTF"} lançada em Contas a Pagar, mas o arquivo NÃO foi anexado (${falhaAnexo}). Anexe manualmente pelo lançamento em Contas a Pagar.` }
        : { tipo: "sucesso", texto: `Guia de ${tipo === "fgts" ? "FGTS" : "DCTF"} lançada em Contas a Pagar.` });
      setValorPrincipal(""); setValorMulta("0"); setValorJuros("0"); setDataVencimento(""); setLinhaDigitavel(""); setCodigoReceita("");
      setArquivoLido(null); setOrigem("manual");
      onLancado();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao lançar a guia" });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div>
      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        Lance a guia de verdade — arraste o PDF ou foto da guia (leitura automática preenche os campos abaixo) ou
        digite manualmente. Cria a conta a pagar e guarda os dados da guia para relatório.
      </p>
      <div className="flex items-center gap-2 mb-3">
        {(["fgts", "dctf"] as const).map((t) => (
          <button key={t} type="button" onClick={() => setTipo(t)}
            style={{ fontSize: "0.78rem", fontWeight: 700, padding: "0.35rem 0.9rem", borderRadius: "999px",
              border: `1px solid ${tipo === t ? COR_LANCAR.guia : "var(--border)"}`,
              background: tipo === t ? "rgba(224,92,92,0.12)" : "transparent",
              color: tipo === t ? COR_LANCAR.guia : "var(--text-muted)" }}>
            {t === "fgts" ? "FGTS" : "DCTF"}
          </button>
        ))}
      </div>
      <Dropzone
        compact
        accept="application/pdf,image/jpeg,image/png"
        disabled={lendo}
        label={lendo ? "Lendo…" : arquivoLido ? `Arquivo selecionado: ${arquivoLido.name} — arraste outro para substituir, ou` : "Arraste a guia aqui (PDF ou foto), ou"}
        onFiles={(files) => lerGuia(files[0])}
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 mb-3">
        <div><label style={labelStyleLote}>Competência</label>
          <input type="month" style={selStyleLote} value={competencia} onChange={(e) => setCompetencia(e.target.value)} /></div>
        {tipo === "dctf" && (
          <div><label style={labelStyleLote}>Código da receita</label>
            <input style={selStyleLote} value={codigoReceita} onChange={(e) => setCodigoReceita(e.target.value)} /></div>
        )}
        <div><label style={labelStyleLote}>Valor principal (R$)</label>
          <CampoMoeda style={selStyleLote} value={Number(valorPrincipal) || 0} onChange={(v) => setValorPrincipal(v ? String(v) : "")} /></div>
        <div><label style={labelStyleLote}>Multa (R$)</label>
          <CampoMoeda style={selStyleLote} value={Number(valorMulta) || 0} onChange={(v) => setValorMulta(v ? String(v) : "")} /></div>
        <div><label style={labelStyleLote}>Juros (R$)</label>
          <CampoMoeda style={selStyleLote} value={Number(valorJuros) || 0} onChange={(v) => setValorJuros(v ? String(v) : "")} /></div>
        <div><label style={labelStyleLote}>Vencimento</label>
          <input type="date" style={selStyleLote} value={dataVencimento} onChange={(e) => setDataVencimento(e.target.value)} /></div>
      </div>
      <p style={{ fontSize: "0.8rem", marginBottom: "0.75rem" }}>Valor total: <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(valorTotal)}</strong></p>
      {msg?.tipo === "erro" ? (
        <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>
      ) : (
        <AvisoSalvo texto={msg?.texto ?? null} aviso2="Pronto para lançar outra guia." />
      )}
      <button className="btn-primary" title="Lançar a guia" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={lancar} disabled={salvando}>
        <Check size={14} /> {salvando ? "Salvando…" : "Lançar guia"}
      </button>
    </div>
  );
}
