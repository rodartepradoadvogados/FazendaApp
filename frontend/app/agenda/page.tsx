"use client";

import React, { Suspense, useEffect, useLayoutEffect, useState, useCallback, useMemo, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { Calendar, Plus, RefreshCw, ChevronDown, ChevronRight, ChevronLeft, AlertTriangle, CheckCircle2, Check, X, Syringe, Heart, Wheat, Wallet, RotateCcw, ExternalLink, Megaphone, User, FileSpreadsheet, FileText, PackageSearch, Layers, Search, HeartPulse, Repeat, ClipboardList } from "lucide-react";
import {
  fetchAgendaDia, fetchAgendaPainel, fetchAgendaProjecao, materializarAgendaComIntervalo,
  addEventoManual, marcarEventoRealizado as marcarEventoRealizadoApi, desmarcarEventoRealizado,
  fetchProtocoloInducaoConcluidos, fetchAnimais, fetchLotes, today,
  marcarCuraAplicacao, marcarCuraProtocolo, confirmarLactacaoInducao, fetchProtocolosIatfAtivos,
  criarMovimentacao, fetchMotivosMovimentacao, salvarDiasDiaria, atualizarServico,
  authFetch, API, mensagemErroApi, fetchLancamentos,
} from "@/lib/api";
import { PagarContaModal, type ContaParaPagar } from "@/components/PagarContaModal";
import { exportarExcel, exportarPDF } from "@/lib/export";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { SelecaoLotesTabela, LoteRow } from "@/components/SelecaoLotesTabela";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { SecaoRecolhivel } from "@/components/ui";
import { SubAbasAgenda, type VisaoAgenda } from "@/components/agenda/SubAbasAgenda";
import { CartaoPainel, GrupoPainel } from "@/components/agenda/CartaoPainel";
import { OQueVem } from "@/components/agenda/OQueVem";
import { SemanaAgenda, inicioDaSemana } from "@/components/agenda/SemanaAgenda";
import { ProjecaoAgenda, SeletorHorizonte, type ProjecaoDados } from "@/components/agenda/ProjecaoAgenda";
import { lerCacheAgenda, gravarCacheAgenda } from "@/components/agenda/cacheAgenda";
import { PainelLancarBst } from "@/components/PainelLancarBst";
import { casaBusca } from "@/lib/busca";
import { moduloContratado } from "@/lib/modulos";
import { CartaoVacinasPrevistas, NotasSanitario } from "@/components/sanitario/AgendaSanitario";
import { categoriasAgendaVisiveis, gruposPainelVisiveis, podeVincularAnimalLote, resumoContasAgenda } from "@/lib/agendaModulos";
import { GavetaLancamento } from "@/components/lancamentos/GavetaLancamento";
import { DefinirDataVisitaModal } from "@/components/reproducao/DefinirDataVisitaModal";
// Mesmo formulário de components/lancamentos/* que a tela de Lançamentos
// abre na gaveta (ver GAVETA_LEAFS em app/lancamentos/page.tsx) — aqui abre
// direto da Agenda, sem navegar pra outra página (ver abrirGavetaInseminacao
// mais abaixo).
const FormInseminacao = dynamic(() => import("@/components/lancamentos/FormInseminacao").then((m) => m.FormInseminacao), { ssr: false });

const COLUNAS_AGENDA = [
  { header: "Data", key: "data" }, { header: "Categoria", key: "categoria" },
  { header: "Nº Animal", key: "numero_animal" }, { header: "Descrição", key: "descricao" },
  { header: "Obs.", key: "observacao" },
];

const DIAS_PADRAO_FUTURO = 10;
function addDias(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function diasEntre(aIso: string, bIso: string): number {
  return Math.round((new Date(bIso + "T00:00:00").getTime() - new Date(aIso + "T00:00:00").getTime()) / 86400000);
}
// Monta "aaaa-mm-dd" a partir de componentes locais (sem passar por Date →
// toISOString, que converte para UTC e pode voltar um dia — mesmo cuidado do
// resto do arquivo, que sempre ancora Date com "T00:00:00" para evitar isso).
function isoLocal(ano: number, mes: number, dia: number): string {
  return `${ano}-${String(mes + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}
const NOMES_MES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const DIAS_SEMANA_ABREV = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

const CATEGORIAS = ["Reprodutivo", "Sanidade", "Produção", "Gestão/Financeiro", "Atividades"];
const TIPOS_EVENTO = ["Compra", "Venda", "Serviço", "Outro"];
const BADGE_CLASS: Record<string, string> = {
  "Reprodutivo":       "badge-reprodutivo",
  "Sanidade":          "badge-sanidade",
  "Produção":          "badge-producao",
  "Gestão/Financeiro": "badge-financeiro",
  "Atividades":        "badge-atividades",
};
// Várias pendências (sanidade, protocolo_sanitario, aplicacao_agendada...) chegam
// com `categoria` em minúsculo ("sanidade"), enquanto o filtro/badge acima usa a
// forma capitalizada — sem isto, o filtro "Sanidade" nunca as encontra e a pílula
// cai no estilo padrão. Normaliza os dois lados por comparação/lookup.
const BADGE_CLASS_LC: Record<string, string> = Object.fromEntries(Object.entries(BADGE_CLASS).map(([k, v]) => [k.toLowerCase(), v]));
function badgeClasse(categoria: string): string {
  return BADGE_CLASS_LC[(categoria || "").toLowerCase()] || "badge-atividades";
}
function categoriaLabel(categoria: string): string {
  return categoria ? categoria.charAt(0).toUpperCase() + categoria.slice(1) : categoria;
}
// Cor de destaque por categoria — usada como borda/pontinho nas linhas da
// linha do tempo, no lugar da pílula de categoria repetida em toda linha.
const COR_CATEGORIA: Record<string, string> = {
  "Reprodutivo":       "var(--cat-reproducao)",
  "Sanidade":          "var(--cat-sanidade)",
  "Produção":          "var(--cat-producao)",
  "Gestão/Financeiro": "var(--cat-financeiro)",
  "Atividades":        "var(--text-muted)",
};
const COR_CATEGORIA_LC: Record<string, string> = Object.fromEntries(Object.entries(COR_CATEGORIA).map(([k, v]) => [k.toLowerCase(), v]));
function corCategoria(categoria: string): string {
  return COR_CATEGORIA_LC[(categoria || "").toLowerCase()] || "var(--text-muted)";
}
const LEGENDA_CATEGORIAS = ["Reprodutivo", "Sanidade", "Produção", "Gestão/Financeiro"];

// A página lê `?visao=` (useSearchParams), então precisa de um Suspense. O
// fallback já desenha o topo (título e sub-abas) de forma síncrona — nada de
// skeleton nem de atraso artificial na primeira renderização.
export default function AgendaPage() {
  return (
    <Suspense fallback={<div className="p-6 ag2"><div className="ag2-topo"><div className="ag2-topo-esq"><h1><Calendar size={22} style={{ color: "var(--dourado)" }} /> Agenda</h1><SubAbasAgenda ativa="dia" onChange={() => {}} /></div></div></div>}>
      <AgendaConteudo />
    </Suspense>
  );
}

// Insights › Listas › Agenda Reprodutiva (a aba "vet" de /relatorios, aberta pelo ?sub=).
const URL_AGENDA_REPRODUTIVA = "/relatorios?sub=vet";
/** Comunicado da Agenda (nova dieta, sobra, visita reprodutiva…): só o que a lista usa de campos fixos. */
type ComunicadoAgenda = { id: string; descricao: string; data: string; tipo?: string; categoria?: string; observacao?: string };

function AgendaConteudo() {
  const router = useRouter();
  // "Definir nova data da visita" (comunicado da visita reprodutiva) — mesmo diálogo da Agenda Reprodutiva do Insights.
  const [definindoVisita, setDefinindoVisita] = useState<{ data: string | null; origem: "definida" | "calculada" | null; intervalo: number | null; ultima: string | null } | null>(null);
  // Módulos contratados (Plano Financeiro §2.6). A página só monta depois do AuthShell confirmar o login
  // (nunca é desenhada no servidor), então ler o contrato do localStorage na inicialização é seguro.
  // Os efeitos de carga abaixo consultam moduloContratado() direto, sem esperar este estado.
  const [mods] = useState(() => ({
    rebanho: moduloContratado("rebanho"), estoque: moduloContratado("estoque"), reprodutivo: moduloContratado("reprodutivo"),
    sanitario: moduloContratado("sanitario"), financeiro: moduloContratado("financeiro"),
  }));
  const temMod = useCallback((chave: string) => (mods as Record<string, boolean>)[chave] ?? true, [mods]);
  const categoriasVisiveis = useMemo(() => categoriasAgendaVisiveis(CATEGORIAS, temMod), [temMod]);
  const gruposPainel = useMemo(() => gruposPainelVisiveis(temMod), [temMod]);
  const podeVincular = podeVincularAnimalLote(temMod);
  const [data, setData] = useState(today());
  const [agenda, setAgenda] = useState<any>(null);
  // `loading` só vale para a PRIMEIRA carga sem nenhum dado (nem cache): a tela
  // já está desenhada e mostra uma linha de status. Depois disso, atualizar é
  // "atualizando" (sem esconder a lista, sem skeleton).
  const [loading, setLoading] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  // Sub-abas com URL: ?visao=dia|painel (padrão: dia). A troca é instantânea
  // (estado local) e a URL acompanha via history.replaceState.
  const parametrosUrl = useSearchParams();
  const visaoDaUrl: VisaoAgenda = parametrosUrl.get("visao") === "painel" ? "painel" : "dia";
  const [visao, setVisaoEstado] = useState<VisaoAgenda>(visaoDaUrl);
  useEffect(() => { setVisaoEstado(visaoDaUrl); }, [visaoDaUrl]);
  const mudarVisao = useCallback((v: VisaoAgenda) => {
    setVisaoEstado(v);
    const p = new URLSearchParams(window.location.search);
    p.set("visao", v);
    window.history.replaceState(null, "", `${window.location.pathname}?${p.toString()}`);
  }, []);
  // Visão do Dia a dia: Lista | Semana | Mês (lembra a última escolha, só por conveniência).
  type ModoDia = "lista" | "semana" | "mes";
  const [modoDia, setModoDiaEstado] = useState<ModoDia>("lista");
  useEffect(() => {
    try { const m = window.localStorage.getItem("agenda.modoDia"); if (m === "lista" || m === "semana" || m === "mes") setModoDiaEstado(m); } catch { /* sem storage */ }
  }, []);
  const setModoDia = (m: ModoDia) => { setModoDiaEstado(m); try { window.localStorage.setItem("agenda.modoDia", m); } catch { /* sem storage */ } };
  const [semanaInicio, setSemanaInicio] = useState(() => inicioDaSemana(today()));
  // Painel: horizonte da programação projetada (7/30/60/90 dias).
  const [horizonte, setHorizonte] = useState(30);
  const [projecao, setProjecao] = useState<Record<number, ProjecaoDados>>({});
  const [projecaoCarregando, setProjecaoCarregando] = useState(false);
  const [projecaoErro, setProjecaoErro] = useState<string | null>(null);
  const [concluidosAberto, setConcluidosAberto] = useState(false);
  // Toque duplo protegido: a mesma marcação (mesmo id e mesmos dados) que ainda
  // está no ar devolve a MESMA promessa, em vez de disparar um 2º POST — o
  // `disabled` dos botões só vale depois do próximo render, e o segundo toque
  // do dedo chega antes.
  const marcacoesEmVoo = useRef(new Map<string, Promise<any>>());
  const marcarEventoRealizado = useCallback((id: string, ...resto: any[]) => {
    const chave = `${id}|${JSON.stringify(resto)}`;
    const emVoo = marcacoesEmVoo.current.get(chave);
    if (emVoo) return emVoo;
    const p = (marcarEventoRealizadoApi as (...a: any[]) => Promise<any>)(id, ...resto).finally(() => { marcacoesEmVoo.current.delete(chave); });
    marcacoesEmVoo.current.set(chave, p);
    return p;
  }, []);
  // Mensagem transitória de sucesso/erro exibida sob o cabeçalho (substitui alert()).
  const [feedback, setFeedback] = useState<{ msg: string; erro?: boolean } | null>(null);
  const mostrarFeedback = (msg: string, erro = false) => {
    setFeedback({ msg, erro });
    setTimeout(() => setFeedback((f) => (f && f.msg === msg ? null : f)), 4000);
  };
  const [filtro, setFiltro] = useState("");
  const [fCat, setFCat] = useState("");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  // Calendário mensal com painel lateral — antes era a 2ª "visualização" da
  // agenda (pílula Linha do tempo/Calendário, trocava o card de baixo);
  // agora é um overlay que o botão "Calendário" do cabeçalho abre por cima
  // dos indicadores (ver C3-C5 da sessão 1 — o card de baixo só mostra a
  // linha do tempo). Mês próprio (não usa "data"/referência) para navegar
  // livremente sem afetar o resto dos cálculos da agenda.
  const [mesCalendario, setMesCalendario] = useState(() => { const d = new Date(); return { ano: d.getFullYear(), mes: d.getMonth() }; });
  // Começa com hoje já selecionado para que a lista de compromissos apareça
  // ao lado do calendário assim que a visão é aberta, sem precisar clicar
  // num dia primeiro.
  const [diaSelecionado, setDiaSelecionado] = useState<string | null>(() => today());
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState({
    data_evento: today(), descricao: "", categoria: "Gestão/Financeiro", observacao: "",
    tipo_evento: "", recorrente: false, recorrenciaNumero: "", recorrenciaFrequencia: "dias" as "dias" | "meses",
  });
  const [vinculo, setVinculo] = useState<"nenhum" | "animal" | "lote">("nenhum");
  const [animaisSelecionados, setAnimaisSelecionados] = useState<Set<string>>(new Set());
  const [lotesSelecionados, setLotesSelecionados] = useState<Set<string>>(new Set());
  const [animaisTodos, setAnimaisTodos] = useState<AnimalRow[]>([]);
  const [lotesTodos, setLotesTodos] = useState<LoteRow[]>([]);
  const [pickerAberto, setPickerAberto] = useState<"lote" | null>(null);
  useEffect(() => { if (vinculo === "animal" && !animaisTodos.length && moduloContratado("rebanho")) fetchAnimais().then(setAnimaisTodos).catch(() => {}); }, [vinculo, animaisTodos.length]);
  const abrirPickerLotes = async () => {
    if (!lotesTodos.length) fetchLotes().then(setLotesTodos).catch(() => {});
    setPickerAberto("lote");
  };
  const toggleAnimalSelecionado = (numero: string) => setAnimaisSelecionados((p) => { const n = new Set(p); n.has(numero) ? n.delete(numero) : n.add(numero); return n; });
  const toggleLoteSelecionado = (codigo: string) => setLotesSelecionados((p) => { const n = new Set(p); n.has(codigo) ? n.delete(codigo) : n.add(codigo); return n; });
  const toggleTodosLotes = () => setLotesSelecionados((p) => (p.size === lotesTodos.length ? new Set() : new Set(lotesTodos.map((l) => l.codigo))));
  const pickerColunasAnimais = [
    { header: "Nº", render: (a: AnimalRow) => a.numero },
    { header: "Grupo", render: (a: AnimalRow) => a.grupo_primario || "—" },
    { header: "Categoria", render: (a: AnimalRow) => a.categoria_abrev || a.categoria_completa || "—" },
  ];
  // Hoje começa aberto (achado do lote 2: timeline não pode nascer 100%
  // colapsada — quem abre a Agenda quer ver o dia de hoje sem precisar
  // clicar); os demais dias (Próximos/Atrasados) começam fechados.
  const [datasAbertas, setDatasAbertas] = useState<Set<string>>(() => new Set([today()]));
  const toggleData = (d: string) => setDatasAbertas(p => { const n = new Set(p); n.has(d) ? n.delete(d) : n.add(d); return n; });
  // Painéis recolhíveis (candidatas IATF, BST aptos, BST excluídos) — começam recolhidos.
  const [paineis, setPaineis] = useState<Set<string>>(new Set());
  // "Pagar" direto na linha de Contas a pagar da Agenda — mesma janela de
  // Ações > Pagamento e do Fechamento da folha.
  const [pagandoConta, setPagandoConta] = useState<ContaParaPagar | null>(null);
  const [resolvendoPagamento, setResolvendoPagamento] = useState<string | null>(null);
  const abrirPagamento = async (ref: string) => {
    setResolvendoPagamento(ref);
    try {
      const d = await fetchLancamentos();
      const conta = (d.lancamentos || []).find((l: any) => l.numero_lancamento === ref && l.tipo === "despesa" && !l.data_pagamento);
      if (!conta) { mostrarFeedback("Esta conta já foi paga ou não foi encontrada em Contas a pagar.", true); return; }
      setPagandoConta({
        lancamentoId: conta.id, titulo: conta.descricao || `Lançamento ${ref}`, detalhe: conta.fornecedor || undefined,
        valorPrevisto: conta.valor, dataVencimento: conta.data_vencimento,
      });
    } catch (e: any) { mostrarFeedback(e.message || "Não foi possível abrir o pagamento.", true); }
    finally { setResolvendoPagamento(null); }
  };
  const togglePainel = (k: string) => setPaineis(p => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });
  // Protocolo IATF: grupo (lançamento+dia) expandido mostra os animais + hormônio do dia.
  const [iatfAbertos, setIatfAbertos] = useState<Set<string>>(new Set());
  const toggleIatf = (id: string) => setIatfAbertos(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const [iatfChecks, setIatfChecks] = useState<Record<string, Set<string>>>({});
  const abrirIatf = (id: string, animais: string[]) => {
    setIatfChecks((p) => (p[id] ? p : { ...p, [id]: new Set(animais) }));
    toggleIatf(id);
  };
  const toggleAnimalIatf = (id: string, numero: string) => setIatfChecks((p) => {
    const atual = new Set(p[id] || []);
    atual.has(numero) ? atual.delete(numero) : atual.add(numero);
    return { ...p, [id]: atual };
  });
  // Protocolo customizado (Configurações > Protocolos): mesmo padrão do IATF
  // acima — grupo (lançamento+dia) expandido mostra os animais com checkbox,
  // permitindo confirmar só um subconjunto (o backend já aceita `animais`
  // parcial em marcar_realizado; só faltava esta UI usar isso em vez de
  // marcar o grupo inteiro de uma vez).
  const [protocoloCustomAbertos, setProtocoloCustomAbertos] = useState<Set<string>>(new Set());
  const toggleProtocoloCustom = (id: string) => setProtocoloCustomAbertos(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const [protocoloCustomChecks, setProtocoloCustomChecks] = useState<Record<string, Set<string>>>({});
  const abrirProtocoloCustom = (id: string, animais: string[]) => {
    setProtocoloCustomChecks((p) => (p[id] ? p : { ...p, [id]: new Set(animais) }));
    toggleProtocoloCustom(id);
  };
  const toggleAnimalProtocoloCustom = (id: string, numero: string) => setProtocoloCustomChecks((p) => {
    const atual = new Set(p[id] || []);
    atual.has(numero) ? atual.delete(numero) : atual.add(numero);
    return { ...p, [id]: atual };
  });
  // Data de início da lactação no card "Confirmar início de lactação"
  // (indução) — pré-preenchida com e.data_sugerida (última etapa do
  // protocolo), editável antes de confirmar "Sim". Estado por eventoId.
  const [lactacaoInducaoData, setLactacaoInducaoData] = useState<Record<string, string>>({});
  // "Incluir nos aptos ao BST?" — o protocolo de indução já aplica BST no
  // animal, então confirmar isto aqui marca `Animal.
  // bst_pendente_inducao_lactacao`, que entra direto em "Incluir no próximo
  // BST" com a notinha "(ind.lact.)" (ver PainelLancarBst.tsx).
  const [inducaoIncluirBst, setInducaoIncluirBst] = useState<Record<string, boolean>>({});

  // Indução de lactação: mesmo padrão do protocolo IATF (grupo lançamento+dia
  // expandido mostra os animais + medicamentos/observação de manejo do dia).
  const [inducaoAbertos, setInducaoAbertos] = useState<Set<string>>(new Set());
  const toggleInducao = (id: string) => setInducaoAbertos(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const [inducaoChecks, setInducaoChecks] = useState<Record<string, Set<string>>>({});
  const abrirInducao = (id: string, animais: string[]) => {
    setInducaoChecks((p) => (p[id] ? p : { ...p, [id]: new Set(animais) }));
    toggleInducao(id);
  };
  const toggleAnimalInducao = (id: string, numero: string) => setInducaoChecks((p) => {
    const atual = new Set(p[id] || []);
    atual.has(numero) ? atual.delete(numero) : atual.add(numero);
    return { ...p, [id]: atual };
  });
  // Sugestão de movimentação entre lotes: clicar na linha abre uma janela
  // suspensa com 3 opções — aceitar (move para o 1º lote sugerido), mudar
  // para outro lote (qualquer lote cadastrado, não só os sugeridos) ou
  // cancelar (dispensa a sugestão — mesma mecânica de "descartar" usada em
  // outras pendências, some até o animal mudar de lote de novo).
  const [sugestaoMovAberta, setSugestaoMovAberta] = useState<any | null>(null);
  const [lotesTodosMov, setLotesTodosMov] = useState<any[]>([]);
  const [motivosMov, setMotivosMov] = useState<string[]>([]);
  const [destinoMov, setDestinoMov] = useState("");
  const [salvandoSugestaoMov, setSalvandoSugestaoMov] = useState(false);
  const abrirSugestaoMov = (e: any) => {
    setSugestaoMovAberta(e);
    setDestinoMov(e.lotes_sugeridos?.[0]?.codigo ?? "");
    if (!lotesTodosMov.length) fetchLotes().then(setLotesTodosMov).catch(() => {});
    if (!motivosMov.length) fetchMotivosMovimentacao().then(setMotivosMov).catch(() => {});
  };
  const fecharSugestaoMov = () => setSugestaoMovAberta(null);
  const aceitarSugestaoMov = async () => {
    if (!sugestaoMovAberta || !destinoMov) return;
    setSalvandoSugestaoMov(true);
    try {
      await criarMovimentacao({
        data_movimento: today(), motivo: motivosMov.includes("Aptidão") ? "Aptidão" : (motivosMov[0] || "Aptidão"),
        lote_destino_codigo: destinoMov, animais: [sugestaoMovAberta.numero_animal],
        origem: "sugestao_passiva",
      });
      setSugestaoMovAberta(null);
      await carregar();
      mostrarFeedback("Movido para o lote sugerido.");
    } catch (e: any) {
      mostrarFeedback(e?.message || "Erro ao mover o animal.");
    } finally {
      setSalvandoSugestaoMov(false);
    }
  };
  const cancelarSugestaoMov = async () => {
    if (!sugestaoMovAberta) return;
    setSalvandoSugestaoMov(true);
    try {
      await marcarEventoRealizado(sugestaoMovAberta.id);
      setSugestaoMovAberta(null);
      await carregar();
    } catch (e: any) {
      mostrarFeedback(e?.message || "Erro ao dispensar a sugestão.");
    } finally {
      setSalvandoSugestaoMov(false);
    }
  };

  // "Deseja cumprir essa atividade?" — confirmação antes de marcar realizado,
  // em vez de agir no primeiro clique.
  const [confirmando, setConfirmando] = useState<Set<string>>(new Set());
  const pedirConfirmacao = (chave: string) => setConfirmando((p) => new Set(p).add(chave));
  const cancelarConfirmacao = (chave: string) => setConfirmando((p) => { const n = new Set(p); n.delete(chave); return n; });

  // Janela que o Dia a dia pede ao backend: sempre hoje+10 (padrão) ou até a
  // data "Até" escolhida; na Semana e no Mês, até o fim do período mostrado
  // (senão tarefas financeiras/futuras do fim do mês não chegariam a tempo).
  const calendarioAberto = modoDia === "mes";
  const ultimoDiaDoMesCalendario = new Date(mesCalendario.ano, mesCalendario.mes + 1, 0).getDate();
  const ultimoDiaMesCalendarioIso = isoLocal(mesCalendario.ano, mesCalendario.mes, ultimoDiaDoMesCalendario);
  const limiteBusca = (() => {
    const padrao = ate && ate > addDias(data, DIAS_PADRAO_FUTURO) ? ate : addDias(data, DIAS_PADRAO_FUTURO);
    if (modoDia === "mes" && ultimoDiaMesCalendarioIso > padrao) return ultimoDiaMesCalendarioIso;
    if (modoDia === "semana" && addDias(semanaInicio, 6) > padrao) return addDias(semanaInicio, 6);
    return padrao;
  })();

  // Leitura da visão ativa (só GET). Sem skeleton: atualizar mantém o que já
  // está na tela (stale-while-revalidate) e só troca quando o dado novo chega.
  const carregar = useCallback(async () => {
    setAtualizando(true);
    try {
      const novo = visao === "painel" ? await fetchAgendaPainel(data) : await fetchAgendaDia(data, limiteBusca);
      setAgenda((prev: any) => ({ ...(prev || {}), ...novo }));
      gravarCacheAgenda(visao, data, novo);
      setErro(null);
    } catch (e: any) {
      // Erro de rede não apaga a lista que já está na tela.
      setErro(e?.message || "erro desconhecido");
    } finally { setLoading(false); setAtualizando(false); }
  }, [data, limiteBusca, visao]);

  // 1ª dobra sem espera: antes da primeira pintura, usa o que a última visita
  // deixou (mesmo dia e mesma conta). Se não houver, a tela já está desenhada e
  // só a lista mostra "Buscando as tarefas…".
  useLayoutEffect(() => {
    const guardado = lerCacheAgenda(visao, data);
    if (guardado) { setAgenda((prev: any) => ({ ...guardado, ...(prev || {}) })); setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visao]);

  // Gaveta lateral (T2, mockup 1e) — Inseminação aberta direto
  // daqui, sem navegar pra /lancamentos (ver
  // abrirGavetaInseminacao mais abaixo, usado no lugar dos antigos
  // <a href="/lancamentos?ir=..."> ). animais próprios (não reusa
  // `animaisTodos`, que só carrega sob demanda pro vínculo do evento manual)
  // porque aqui precisam estar prontos assim que a Agenda abre.
  const [animaisGaveta, setAnimaisGaveta] = useState<AnimalRow[]>([]);
  useEffect(() => {
    // Só com o módulo contratado: sem rebanho seria um 403 garantido a cada abertura.
    if (moduloContratado("rebanho")) fetchAnimais().then(setAnimaisGaveta).catch(() => {});
  }, []);
  type GavetaAgendaEstado =
    | { tipo: "inseminacao"; prefill: { numeroMatriz?: string | null; protocolo?: string | null } }
    | null;
  const [gavetaAgenda, setGavetaAgenda] = useState<GavetaAgendaEstado>(null);
  const [formKeyGavetaAgenda, setFormKeyGavetaAgenda] = useState(0);
  const [mensagemSalvaGavetaAgenda, setMensagemSalvaGavetaAgenda] = useState<string | null>(null);
  const abrirGavetaInseminacao = useCallback((prefill: Extract<GavetaAgendaEstado, { tipo: "inseminacao" }>["prefill"]) => {
    setGavetaAgenda({ tipo: "inseminacao", prefill });
    setMensagemSalvaGavetaAgenda(null);
  }, []);
  const fecharGavetaAgenda = useCallback(() => { setGavetaAgenda(null); setMensagemSalvaGavetaAgenda(null); }, []);
  const aoSalvarGavetaAgenda = useCallback(() => {
    setMensagemSalvaGavetaAgenda("Lançamento salvo com sucesso.");
    carregar();
  }, [carregar]);
  const salvarEProximoGavetaAgenda = useCallback(() => { setMensagemSalvaGavetaAgenda(null); setFormKeyGavetaAgenda((k) => k + 1); }, []);
  const concluirGavetaAgenda = useCallback(() => { setMensagemSalvaGavetaAgenda(null); setGavetaAgenda(null); }, []);

  useEffect(() => { carregar(); }, [carregar]);

  // Recorrências (a parte que ESCREVE) rodam no máx. a cada 15 min por
  // navegador, depois do primeiro desenho; se rodaram agora, relê em silêncio.
  useEffect(() => {
    let vivo = true;
    materializarAgendaComIntervalo(data).then((rodou) => { if (vivo && rodou) carregar(); }).catch(() => undefined);
    return () => { vivo = false; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // Programação projetada do Painel: só depois do 1º desenho do Painel e uma vez
  // por horizonte (o que já veio fica em memória ao trocar 30 -> 60 -> 90).
  const carregarProjecao = useCallback(async (dias: number) => {
    setProjecaoCarregando(true);
    try {
      const dadosProj = await fetchAgendaProjecao(dias, data);
      setProjecao((p) => ({ ...p, [dias]: dadosProj }));
      setProjecaoErro(null);
    } catch (e: any) { setProjecaoErro(e?.message || "erro desconhecido"); }
    finally { setProjecaoCarregando(false); }
  }, [data]);
  useEffect(() => {
    if (visao !== "painel" || projecao[horizonte]) return;
    carregarProjecao(horizonte);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visao, horizonte]);

  // Protocolos IATF ativos/concluídos (D0..D11) — alimenta os quadros "IATF
  // atual" (etapas ainda em aberto) e "Última IATF" (grupo mais recente já
  // concluído, com data de D0/D11 e os animais que entraram nele).
  const [iatfAtivos, setIatfAtivos] = useState<any[]>([]);
  const carregarIatfAtivos = useCallback(async () => {
    if (!moduloContratado("reprodutivo")) { setIatfAtivos([]); return; }
    try { setIatfAtivos(await fetchProtocolosIatfAtivos()); } catch { setIatfAtivos([]); }
  }, []);
  useEffect(() => { carregarIatfAtivos(); }, [carregarIatfAtivos]);
  // Indução de lactação concluídas — mesma ideia (desfazer se marcado por engano).
  const [inducaoConcluidos, setInducaoConcluidos] = useState<any[]>([]);
  const carregarConcluidosInducao = useCallback(async () => {
    try { setInducaoConcluidos(await fetchProtocoloInducaoConcluidos()); } catch { setInducaoConcluidos([]); }
  }, []);
  useEffect(() => { carregarConcluidosInducao(); }, [carregarConcluidosInducao]);

  // Card "Concluídos no período" (C7-C10) — segunda fonte, genérica: marcações
  // de EventoRealizado que não pertencem a nenhum fluxo especializado (IATF e
  // indução de lactação gravam a própria conclusão no modelo de origem e não
  // passam por aqui — ver GET /agenda/protocolo-*-concluidos acima). Filtro
  // de/até, padrão últimos 7 dias.
  const [concDe, setConcDe] = useState(() => addDias(today(), -7));
  const [concAte, setConcAte] = useState(() => today());
  const [realizadosGenericos, setRealizadosGenericos] = useState<{ evento_id: string; marcado_em: string; rotulo: string | null }[]>([]);
  const [carregandoRealizados, setCarregandoRealizados] = useState(false);
  const carregarRealizadosGenericos = useCallback(async () => {
    setCarregandoRealizados(true);
    try {
      const qs = new URLSearchParams();
      if (concDe) qs.set("de", concDe);
      if (concAte) qs.set("ate", concAte);
      const res = await authFetch(`${API}/agenda/realizados?${qs.toString()}`, { cache: "no-store" });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(mensagemErroApi(d.detail) || "Erro ao buscar concluídos no período"); }
      setRealizadosGenericos(await res.json());
    } catch { setRealizadosGenericos([]); }
    finally { setCarregandoRealizados(false); }
  }, [concDe, concAte]);
  useEffect(() => { carregarRealizadosGenericos(); }, [carregarRealizadosGenericos]);
  // Indução de lactação filtrada pelo mesmo período do card (a fonte acima
  // devolve todas as já concluídas, sem filtro de data — a conta é feita
  // aqui, pelo "concluído em" de cada grupo).
  const inducaoConcluidosPeriodo = useMemo(
    () => inducaoConcluidos.filter((g: any) => g.data_realizacao && (!concDe || g.data_realizacao >= concDe) && (!concAte || g.data_realizacao <= concAte)),
    [inducaoConcluidos, concDe, concAte],
  );

  const [desfazendo, setDesfazendo] = useState<Set<string>>(new Set());
  const desfazerIatf = async (id: string) => {
    setDesfazendo((p) => new Set(p).add(id));
    try {
      await desmarcarEventoRealizado(id);
      await Promise.all([carregar(), carregarIatfAtivos(), carregarConcluidosInducao(), carregarRealizadosGenericos()]);
      mostrarFeedback("Desfeito.");
    }
    catch (e: any) { mostrarFeedback(e.message, true); }
    finally { setDesfazendo((p) => { const n = new Set(p); n.delete(id); return n; }); }
  };

  // Deep-link do sino/push (ver NotificationBell.tsx::destino /
  // push.py::url_destino): "?abrir_sugestao=<evento_id>" abre direto a
  // janela "Ver sugestão" da sugestão de mudança de lote, em vez de só cair
  // na lista genérica da Agenda sem achar o item pra tratar. Se a sugestão
  // não existir mais nesse dia (ex.: o animal já não atende a nenhum
  // critério), avisa com clareza em vez de ficar silenciosamente em branco.
  const tratouAbrirSugestao = useRef(false);
  useEffect(() => {
    if (tratouAbrirSugestao.current || !agenda) return;
    const idAlvo = new URLSearchParams(window.location.search).get("abrir_sugestao");
    if (!idAlvo) return;
    tratouAbrirSugestao.current = true;
    const alvo = (agenda.eventos || []).find((e: any) => e.tipo === "sugestao_movimentacao" && e.id === idAlvo);
    if (alvo) {
      setDatasAbertas((p) => new Set(p).add(alvo.data));
      abrirSugestaoMov(alvo);
    } else {
      mostrarFeedback("Esta sugestão não está mais disponível — o animal pode já ter mudado de lote, ou não atende mais a nenhum critério.", true);
    }
    const params = new URLSearchParams(window.location.search);
    params.delete("abrir_sugestao");
    const qs = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (qs ? `?${qs}` : ""));
  }, [agenda]);

  const hoje = today();
  // Comunicados (ex.: aviso de nova dieta) são informativos, não atividades:
  // ficam fixos enquanto vigoram (hoje/amanhã), não têm ação de excluir/dar
  // baixa, e somem sozinhos no dia seguinte — por isso vivem numa seção
  // própria, sempre visível, sem passar pelos filtros da agenda cronológica.
  const comunicados = useMemo(
    () => (agenda?.comunicados as any[] | undefined) || (agenda?.eventos || []).filter((e: any) => e.comunicado),
    [agenda],
  );
  // Estoque negativo/abaixo do mínimo — informação sempre visível (não é uma
  // pendência que se "resolve", é um alerta que só some quando o saldo normalizar.
  const estoqueNegativo: any[] = agenda?.estoque_negativo || [];
  const estoqueAbaixoMinimo: any[] = agenda?.estoque_abaixo_minimo || [];
  const eventosBase = useMemo(
    () => (agenda?.eventos || []).filter((e: any) => {
      if (e.comunicado) return false;
      if (fCat && (e.categoria || "").toLowerCase() !== fCat.toLowerCase()) return false;
      if (de && e.data < de) return false;
      if (ate && e.data > ate) return false;
      if (!casaBusca(`${e.descricao} ${e.numero_animal} ${e.categoria}`, filtro)) return false;
      return true;
    }),
    [agenda, fCat, de, ate, filtro],
  );
  // Próximos eventos: por padrão só os próximos 10 dias; se o usuário definir
  // "Até" explicitamente, respeita o período escolhido (pode ser maior ou menor).
  const limiteFuturo = ate || addDias(hoje, DIAS_PADRAO_FUTURO);
  const eventosFuturos = useMemo(
    () => eventosBase.filter((e: any) => e.data >= hoje && e.data <= limiteFuturo),
    [eventosBase, hoje, limiteFuturo],
  );
  // Redesign T3 (mockup 1i): a linha do tempo agora separa Hoje de Próximos
  // dias (antes "Futuros" misturava os dois sob o mesmo rótulo "Hoje") — só
  // uma partição por data de `eventosFuturos`, mesma lista/mesmo filtro.
  const eventosHoje = useMemo(() => eventosFuturos.filter((e: any) => e.data === hoje), [eventosFuturos, hoje]);
  const eventosProximos = useMemo(() => eventosFuturos.filter((e: any) => e.data > hoje), [eventosFuturos, hoje]);
  // "Fechar o dia" (delight) — contagem BRUTA de pendências de hoje, sem os
  // filtros de categoria/período/busca (fCat/de/ate/filtro) que só afetam o
  // que é MOSTRADO, não se o dia está de fato fechado. Um `useEffect` que
  // observa essa contagem cair de >0 para 0 pega a última tarefa concluída
  // por QUALQUER um dos vários fluxos de conclusão do arquivo (marcarRealizado,
  // aplicarCronogramaLote, confirmarCura, descartarPendencia etc.) sem precisar
  // instrumentar cada handler — todos chamam `carregar()` no final, que
  // recarrega `agenda` e recalcula esta contagem. `totalHojeRef` guarda o
  // MAIOR valor visto para "hoje" (a agenda só lista pendências, as
  // concluídas somem da lista) — é o "N" de "N de N concluídas"; reseta
  // quando a data muda.
  const pendenciasHojeBrutas = useMemo(
    () => (agenda?.eventos || []).filter((e: any) => !e.comunicado && e.data === hoje).length,
    [agenda, hoje],
  );
  const pendenciasHojeAnteriorRef = useRef<number | null>(null);
  const totalHojeRef = useRef<{ dia: string; total: number }>({ dia: hoje, total: 0 });
  const [diaFechado, setDiaFechado] = useState<{ total: number } | null>(null);
  useEffect(() => {
    if (totalHojeRef.current.dia !== hoje) totalHojeRef.current = { dia: hoje, total: 0 };
    if (pendenciasHojeBrutas > totalHojeRef.current.total) totalHojeRef.current.total = pendenciasHojeBrutas;

    const anterior = pendenciasHojeAnteriorRef.current;
    if (anterior != null && anterior > 0 && pendenciasHojeBrutas === 0) {
      setDiaFechado({ total: totalHojeRef.current.total });
    } else if (pendenciasHojeBrutas > 0) {
      setDiaFechado(null);
    }
    pendenciasHojeAnteriorRef.current = pendenciasHojeBrutas;
  }, [pendenciasHojeBrutas, hoje]);
  const eventosPendentes = useMemo(
    () => eventosBase.filter((e: any) => e.data < hoje),
    [eventosBase, hoje],
  );
  // Dia a dia gerencial: os dias com tarefa ATRASADA já chegam abertos (quem abre
  // a agenda quer ver o que ficou para trás sem clicar), uma vez por carga de dados.
  const atrasadosAbertosRef = useRef(false);
  useEffect(() => {
    if (atrasadosAbertosRef.current || eventosPendentes.length === 0) return;
    atrasadosAbertosRef.current = true;
    setDatasAbertas((p) => { const n = new Set(p); eventosPendentes.forEach((e: any) => n.add(e.data)); return n; });
  }, [eventosPendentes]);

  // Protocolo IATF: qual medicamento/frasco foi aplicado em cada hormônio do
  // dia (ex.: D9). Chave = eventoId → índice do hormônio → estoque_id escolhido.
  const [medIatf, setMedIatf] = useState<Record<string, Record<number, number | null>>>({});
  const escolherMedIatf = (eventoId: string, idx: number, estoqueId: number | null) =>
    setMedIatf((p) => ({ ...p, [eventoId]: { ...(p[eventoId] || {}), [idx]: estoqueId } }));

  const [marcando, setMarcando] = useState<Set<string>>(new Set());
  const marcarRealizado = async (eventoId: string, animais?: string[], hormonios?: any[]) => {
    setMarcando((p) => new Set(p).add(eventoId));
    try {
      // Monta os medicamentos aplicados (com o frasco escolhido) a partir dos
      // hormônios do dia e da seleção do usuário.
      const sel = medIatf[eventoId] || {};
      const medicamentos = (hormonios || []).map((h: any, idx: number) => {
        const estoqueId = sel[idx] ?? (h.opcoes?.length === 1 ? h.opcoes[0].estoque_id : null);
        const op = (h.opcoes || []).find((o: any) => o.estoque_id === estoqueId);
        return { produto: op?.nome || h.produto, estoque_id: estoqueId ?? undefined, dose: h.dose, unidade: h.unidade, via: h.via };
      }).filter((m: any) => m.produto);
      await marcarEventoRealizado(eventoId, animais, medicamentos);
      cancelarConfirmacao(eventoId);
      await carregar();
      if (eventoId.startsWith("protocolo_iatf_")) await carregarIatfAtivos();
      if (eventoId.startsWith("protocolo_inducao_")) await carregarConcluidosInducao();
      mostrarFeedback("Atividade marcada como realizada.");
    }
    catch (e: any) { mostrarFeedback(e.message, true); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(eventoId); return n; }); }
  };

  // Confirmação de cura (Sim/Não) — diferente de "Realizado": a resposta é
  // persistida (Sanidade.curada / ProtocoloSanitarioLancamento.curada) antes
  // de sumir da Agenda, para alimentar o relatório Taxa de cura.
  const confirmarCura = async (e: any, curada: boolean) => {
    setMarcando((p) => new Set(p).add(e.id));
    try {
      if (e.cura_origem === "protocolo") await marcarCuraProtocolo(e.cura_id, curada);
      else await marcarCuraAplicacao(e.cura_id, curada);
      await marcarEventoRealizado(e.id);
      await carregar();
      mostrarFeedback(curada ? "Cura confirmada." : "Registrado: não curado.");
    }
    catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

  // Confirmação de início de lactação (indução) — "Sim" abre a Lactacao
  // (origem "inducao") na data escolhida; "Não" não chama o backend de
  // produção (não existe resposta própria para gravar, ao contrário da
  // cura) — só marcarEventoRealizado tira o card da Agenda.
  const confirmarLactacaoInducaoAgenda = async (e: any, entrouEmLactacao: boolean) => {
    setMarcando((p) => new Set(p).add(e.id));
    try {
      if (entrouEmLactacao) {
        const dataInicio = lactacaoInducaoData[e.id] || e.data_sugerida || undefined;
        await confirmarLactacaoInducao(e.lancamento_id, e.numero_matriz, true, dataInicio, !!inducaoIncluirBst[e.id]);
      }
      await marcarEventoRealizado(e.id);
      await carregar();
      mostrarFeedback(entrouEmLactacao ? "Lactação iniciada." : "Registrado: não entrou em lactação.");
    }
    catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

  // "Contar diária" / "Descartar diária" / "Contar meia diária" — card de
  // diarista ativo sem folga marcada hoje (ver eventos_diaria_trabalho em
  // agenda.py). ANTES eram "Importar agora" (só levava pro Financeiro, o
  // usuário tinha que repetir a decisão lá) e "Realizado" (só dispensava o
  // card da Agenda, sem tocar em nada do controle de diárias — o dia ficava
  // contado por omissão, sem registro explícito). Agora as três chamam
  // DIRETO o mesmo endpoint que o calendário "Dias trabalhados" do Controle
  // de diárias usa (`salvarDiasDiaria`, ver rh_contratos.py::salvar_dias_diaria):
  // "Contar" grava o dia sem exceção (conta, que é o padrão do calendário
  // esparso); "Descartar" grava uma folga explícita; "Contar meia diária"
  // grava a exceção de meia diária (metade do valor) — nenhuma etapa
  // intermediária, tudo resolvido com um clique aqui mesmo na Agenda.
  const [processandoDiaria, setProcessandoDiaria] = useState<Set<string>>(new Set());
  const decidirDiaria = async (e: any, decisao: "contar" | "descartar" | "meia") => {
    setProcessandoDiaria((p) => new Set(p).add(e.id));
    try {
      await salvarDiasDiaria(e.diaria_id, {
        periodo_inicio: e.data, periodo_fim: e.data,
        dias_nao_trabalhados: decisao === "descartar" ? [e.data] : [],
        dias_meia_diaria: decisao === "meia" ? [e.data] : [],
      });
      // O dia já está gravado certo no calendário da diária (linha acima) —
      // isto só cala o lembrete de hoje na Agenda, mesmo EventoRealizado que
      // qualquer outro "Realizado" usa.
      await marcarEventoRealizado(e.id);
      await carregar();
      mostrarFeedback(
        decisao === "contar" ? "Diária contada."
          : decisao === "meia" ? "Meia diária contada — hoje vale metade do valor no Controle de diárias."
          : "Diária descartada — hoje virou folga no Controle de diárias."
      );
    } catch (err: any) {
      // 409 = o período já tem pagamento registrado (ver salvar_dias_diaria);
      // o card só cobre "hoje" e não tem contexto pra oferecer o
      // "confirmar mesmo assim" com segurança — manda resolver no Controle de
      // diárias, que já sabe pedir essa confirmação.
      mostrarFeedback(err.message || "Erro ao registrar a diária. Abra o Controle de diárias para resolver.", true);
    } finally {
      setProcessandoDiaria((p) => { const n = new Set(p); n.delete(e.id); return n; });
    }
  };

  // Pendência "Cadastrar motivo da perda de prenhez" (ver
  // eventos_perda_prenhez_pendente em agenda.py) — perda já registrada
  // (manual ou automática por reinseminação), só falta o motivo. "Aborto"/
  // "Natimorto"/"Outros" gravam o motivo escolhido; "Descartar" grava o
  // sentinela `nao_informado` — a perda CONTINUA registrada, só o motivo que
  // o usuário optou por não informar (não é a mesma coisa que excluir a
  // perda). Os dois casos usam o mesmo PUT de sempre (atualizarServico):
  // assim que `motivo_perda_prenhez` deixa de ser nulo, o card some sozinho
  // da Agenda no próximo carregamento — sem precisar de EventoRealizado.
  const [salvandoMotivoPerda, setSalvandoMotivoPerda] = useState<Set<string>>(new Set());
  const cadastrarMotivoPerda = async (e: any, motivo: string) => {
    setSalvandoMotivoPerda((p) => new Set(p).add(e.id));
    try {
      await atualizarServico(e.servico_id, { motivo_perda_prenhez: motivo });
      await carregar();
      mostrarFeedback(
        motivo === "nao_informado"
          ? "Pendência descartada — a perda de prenhez continua registrada."
          : "Motivo da perda de prenhez registrado."
      );
    } catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setSalvandoMotivoPerda((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

  // Botão "Realizado" com confirmação inline ("Deseja cumprir essa atividade?
  // Sim/Não") em vez de agir direto no primeiro clique.
  const BotaoRealizado = ({ chave, onConfirmar, compacto }: { chave: string; onConfirmar: () => void; compacto?: boolean }) => {
    if (confirmando.has(chave)) {
      return (
        <span className="flex items-center gap-1" style={{ fontSize: "0.68rem" }} onClick={(e) => e.stopPropagation()}>
          Cumpriu?
          <button className="btn-ghost" style={{ color: "var(--green-light)", padding: "0.1rem 0.3rem" }} disabled={marcando.has(chave)} onClick={onConfirmar}>Sim</button>
          <button className="btn-ghost" style={{ padding: "0.1rem 0.3rem" }} onClick={() => cancelarConfirmacao(chave)}>Não</button>
        </span>
      );
    }
    return (
      <button className="btn-ghost" style={{ fontSize: "0.68rem" }} title="Marcar como realizado" disabled={marcando.has(chave)} onClick={(e) => { e.stopPropagation(); pedirConfirmacao(chave); }}>
        <CheckCircle2 size={12} /> {compacto ? "" : "Realizado"}
      </button>
    );
  };

  const inputInline: React.CSSProperties = { width: "100%", fontSize: "0.78rem", padding: "0.3rem 0.5rem", borderRadius: 6, background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" };

  const fecharModalNovoEvento = () => {
    setShowModal(false);
    setVinculo("nenhum");
    setAnimaisSelecionados(new Set());
    setLotesSelecionados(new Set());
    setForm({ data_evento: today(), descricao: "", categoria: "Gestão/Financeiro", observacao: "", tipo_evento: "", recorrente: false, recorrenciaNumero: "", recorrenciaFrequencia: "dias" });
  };

  const handleAddEvento = async () => {
    try {
      const numeroIntervalo = Math.max(1, Math.round(Number(form.recorrenciaNumero) || 0));
      await addEventoManual({
        data_evento: form.data_evento,
        descricao: form.descricao,
        categoria: form.categoria,
        observacao: form.observacao || undefined,
        numero_animal: vinculo === "animal" && animaisSelecionados.size ? Array.from(animaisSelecionados).join(",") : undefined,
        lotes: vinculo === "lote" && lotesSelecionados.size ? Array.from(lotesSelecionados).join(",") : undefined,
        tipo_evento: form.tipo_evento || undefined,
        recorrente: form.recorrente,
        intervalo_dias: form.recorrente && form.recorrenciaFrequencia === "dias" ? numeroIntervalo : undefined,
        intervalo_meses: form.recorrente && form.recorrenciaFrequencia === "meses" ? numeroIntervalo : undefined,
      });
      fecharModalNovoEvento();
      carregar();
      mostrarFeedback("Evento adicionado.");
    } catch (e: any) { mostrarFeedback(e.message, true); }
  };

  // Extrai o valor de "Conta a pagar: X — R$ 1,234.56" (formatação :,.2f do Python — vírgula de milhar, ponto decimal).
  const extrairValor = (desc: string) => { const m = desc.match(/R\$\s*([\d,]+\.\d{2})/); return m ? m[1].replace(/,/g, "") : null; };

  // Tira colorida à esquerda da linha (categoria) no lugar da pílula repetida
  // em toda linha — só a cor muda o suficiente para identificar a categoria.
  const tdAccent = (categoria: string) => <td style={{ padding: 0, width: 4, background: corCategoria(categoria) }}></td>;
  // "N dias atrasado" — só aparece na seção de Atrasados (mostrarAtraso=true).
  const pillAtraso = (dataEvento: string) => (
    <span style={{ marginLeft: "0.5rem", fontSize: "0.68rem", fontWeight: 700, color: "var(--red)", background: "rgba(220,38,38,0.12)", padding: "0.05rem 0.45rem", borderRadius: 999, whiteSpace: "nowrap" }}>
      {diasEntre(dataEvento, hoje)} dia{diasEntre(dataEvento, hoje) !== 1 ? "s" : ""} atrasado
    </span>
  );

  const renderEventos = (lista: any[], mostrarAtraso?: boolean) => {
    const porData = new Map<string, any[]>();
    lista.forEach((e: any) => { (porData.get(e.data) ?? porData.set(e.data, []).get(e.data)!).push(e); });
    return Array.from(porData.keys()).sort().map((d) => {
      const evs = porData.get(d)!; const aberto = datasAbertas.has(d);

      // Dentro do dia, agrupa Gestão/Financeiro por referência (nº do lançamento/nota).
      const financeiroPorRef = new Map<string, any[]>();
      const linhas: any[] = [];
      evs.forEach((e: any) => {
        if (e.tipo === "protocolo_iatf") {
          linhas.push({ tipo: "iatf", e });
        } else if (e.tipo === "protocolo_inducao") {
          linhas.push({ tipo: "inducao", e });
        } else if (e.tipo === "protocolo_customizado" && (e.animais?.length ?? 0) > 1) {
          // Só usa o card expansível (com seleção por animal) quando há mais de
          // 1 animal no grupo — com 1 só, o fallback genérico (linha "simples",
          // numero_animal já preenchido) é suficiente e mais direto.
          linhas.push({ tipo: "protocolo_custom", e });
        } else if (e.categoria === "Gestão/Financeiro" && e.ref) {
          const arr = financeiroPorRef.get(e.ref) ?? [];
          arr.push(e); financeiroPorRef.set(e.ref, arr);
        } else {
          linhas.push({ tipo: "simples", e });
        }
      });
      financeiroPorRef.forEach((itens, ref) => linhas.push({ tipo: "grupo", ref, itens }));

      return (
        <div key={d} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", background: "var(--surface-2)" }}>
            <button onClick={() => toggleData(d)} style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.9rem", background: "transparent", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
              {aberto ? <ChevronDown size={15} style={{ color: "var(--text-muted)" }} /> : <ChevronRight size={15} style={{ color: "var(--text-muted)" }} />}
              <span style={{ fontWeight: 700, minWidth: "8rem" }}>{new Date(d + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short", year: "2-digit" })}</span>
              <span style={{ flex: 1, fontSize: "0.78rem", color: "var(--text-muted)" }}>{evs.length} evento{evs.length !== 1 ? "s" : ""}</span>
            </button>
          </div>
          {aberto && (
            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th></th><th>Nº Animal</th><th>Descrição</th><th>Obs.</th><th>Origem</th><th></th></tr></thead>
                <tbody>
                  {linhas.map((linha, i) => {
                    if (linha.tipo === "simples") {
                      const e = linha.e;
                      const ehSugestaoMov = (e as any).tipo === "sugestao_movimentacao";
                      const ehBstAplicacao = (e as any).tipo === "bst_aplicacao";
                      // Diária de diarista ativa hoje — clicar no CARD (fora dos botões)
                      // leva direto pro Controle de diárias (Financeiro > Ações > Folha
                      // de pagamento > Diária), mesmo destino do link usado pelos botões
                      // de baixo (ver `link` gerado em agenda.py::eventos_diaria_trabalho).
                      const ehDiariaTrabalho = (e as any).tipo === "diaria_trabalho";
                      return (
                        <React.Fragment key={i}>
                          <tr
                            style={(ehSugestaoMov || ehBstAplicacao || ehDiariaTrabalho) ? { cursor: "pointer" } : undefined}
                            onClick={
                              ehSugestaoMov ? () => abrirSugestaoMov(e)
                              : ehBstAplicacao ? () => abrirListasBst()
                              : ehDiariaTrabalho ? () => router.push((e as any).link)
                              : undefined
                            }
                          >
                            {tdAccent(e.categoria)}
                            <td style={{ fontWeight: e.numero_animal ? 700 : 400 }}>{e.numero_animal || (e.lote ? `Lote: ${e.lote}` : <span className="ag2-nada">—</span>)}</td>
                            <td style={{ fontSize: "0.83rem" }} title={categoriaLabel(e.categoria)}>{e.descricao}{mostrarAtraso && pillAtraso(e.data)}</td>
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem", whiteSpace: "pre-line", maxWidth: "26rem" }}>{e.observacao || <span className="ag2-nada">—</span>}</td>
                            <td style={{ fontSize: "0.7rem", color: e.fonte === "manual" ? "var(--amber)" : "var(--text-muted)" }}>{e.fonte === "manual" ? "manual" : "auto"}</td>
                            <td onClick={(ehSugestaoMov || ehBstAplicacao || ehDiariaTrabalho) ? (ev) => ev.stopPropagation() : undefined}>
                              {ehSugestaoMov ? (
                                <button className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirSugestaoMov(e)}>
                                  <Layers size={12} /> Ver sugestão
                                </button>
                              ) : (e as any).tipo === "colostragem_pendente" || (e as any).tipo === "igg_pendente" ? (
                                // Sem "Cumpriu? Sim/Não" aqui de propósito: essa pendência só
                                // desaparece de verdade quando o dado é preenchido na ficha (o
                                // backend recalcula a falta a partir do registro de colostragem,
                                // não de um "realizado" manual) — um botão de marcar-feito direto
                                // mascararia o problema em vez de resolvê-lo.
                                <a href={(e as any).link} className="btn-primary" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", whiteSpace: "nowrap" }} title="Abrir a ficha do animal para lançar o dado pendente">
                                  <User size={12} /> Lançar
                                </a>
                              ) : ehDiariaTrabalho ? (
                                <div className="flex flex-col gap-1" style={{ alignItems: "flex-start" }}>
                                  <button className="btn-primary" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", whiteSpace: "nowrap" }}
                                    disabled={processandoDiaria.has(e.id)}
                                    title="Registra hoje na contagem de diárias — direto, sem passar pelo Financeiro"
                                    onClick={() => decidirDiaria(e, "contar")}>
                                    <CheckCircle2 size={12} /> Contar diária
                                  </button>
                                  <button className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", color: "var(--amber)" }}
                                    disabled={processandoDiaria.has(e.id)}
                                    title="Registra hoje como meia diária — metade do valor na contagem de diárias"
                                    onClick={() => decidirDiaria(e, "meia")}>
                                    <CheckCircle2 size={12} /> Contar meia diária
                                  </button>
                                  <button className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", color: "var(--text-muted)" }}
                                    disabled={processandoDiaria.has(e.id)}
                                    title="Marca hoje como folga — não entra na contagem de diárias"
                                    onClick={() => decidirDiaria(e, "descartar")}>
                                    <X size={12} /> Descartar diária
                                  </button>
                                </div>
                              ) : (e as any).link ? (
                                <div className="flex flex-col gap-1" style={{ alignItems: "flex-start" }}>
                                  <a href={(e as any).link} className="btn-primary" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", whiteSpace: "nowrap" }} title="Abrir a tela de importação">
                                    <ExternalLink size={12} /> Importar agora
                                  </a>
                                  <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id)} />
                                </div>
                              ) : e.categoria === "alimentacao" ? (
                                <a href={`/alimentacao?lote=${encodeURIComponent(e.lote ?? "")}`} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                                  <Wheat size={12} /> Ir para Dieta
                                </a>
                              ) : (e as any).tipo === "confirmar_cura" ? (
                                <span className="flex items-center gap-1" style={{ fontSize: "0.72rem" }} onClick={(ev) => ev.stopPropagation()}>
                                  Curado?
                                  <button className="btn-ghost" style={{ color: "var(--green-light)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(e.id)} onClick={() => confirmarCura(e, true)}>Sim</button>
                                  <button className="btn-ghost" style={{ color: "var(--red)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(e.id)} onClick={() => confirmarCura(e, false)}>Não</button>
                                </span>
                              ) : (e as any).tipo === "confirmar_lactacao_inducao" ? (
                                <div className="flex flex-col gap-1" style={{ alignItems: "flex-start", maxWidth: "22rem" }} onClick={(ev) => ev.stopPropagation()}>
                                  {(e as any).aviso ? (
                                    <span style={{ fontSize: "0.68rem", color: "var(--red)" }}>{(e as any).aviso}</span>
                                  ) : null}
                                  <span className="flex items-center gap-2 flex-wrap" style={{ fontSize: "0.72rem" }}>
                                    Entrou em lactação?
                                    <input
                                      type="date"
                                      style={{ ...inputInline, width: "auto" }}
                                      value={lactacaoInducaoData[e.id] ?? (e as any).data_sugerida ?? ""}
                                      onChange={(ev) => setLactacaoInducaoData((p) => ({ ...p, [e.id]: ev.target.value }))}
                                    />
                                    <button className="btn-ghost" style={{ color: "var(--green-light)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(e.id)} onClick={() => confirmarLactacaoInducaoAgenda(e, true)}>Sim</button>
                                    <button className="btn-ghost" style={{ color: "var(--red)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(e.id)} onClick={() => confirmarLactacaoInducaoAgenda(e, false)}>Não</button>
                                  </span>
                                  <label className="flex items-center gap-1" style={{ fontSize: "0.68rem", color: "var(--text-muted, #6b7280)", cursor: "pointer" }}>
                                    <input
                                      type="checkbox"
                                      checked={inducaoIncluirBst[e.id] ?? true}
                                      onChange={(ev) => setInducaoIncluirBst((p) => ({ ...p, [e.id]: ev.target.checked }))}
                                    />
                                    Incluir nos aptos ao BST (protocolo já aplicou)
                                  </label>
                                </div>
                              ) : ehBstAplicacao ? (
                                <button className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirListasBst()}>
                                  <Layers size={12} /> Ver listas
                                </button>
                              ) : (e as any).tipo === "perda_prenhez_motivo" ? (
                                <div className="flex flex-col gap-1" style={{ alignItems: "flex-start" }}>
                                  <div className="flex items-center gap-1" style={{ flexWrap: "wrap" }}>
                                    <button className="btn-ghost" style={{ fontSize: "0.66rem" }} disabled={salvandoMotivoPerda.has(e.id)} title="Cadastrar motivo: aborto" onClick={() => cadastrarMotivoPerda(e, "aborto")}>Aborto</button>
                                    <button className="btn-ghost" style={{ fontSize: "0.66rem" }} disabled={salvandoMotivoPerda.has(e.id)} title="Cadastrar motivo: natimorto" onClick={() => cadastrarMotivoPerda(e, "natimorto")}>Natimorto</button>
                                    <button className="btn-ghost" style={{ fontSize: "0.66rem" }} disabled={salvandoMotivoPerda.has(e.id)} title="Cadastrar motivo: outros" onClick={() => cadastrarMotivoPerda(e, "outros")}>Outros</button>
                                  </div>
                                  <button className="btn-ghost" style={{ fontSize: "0.66rem", color: "var(--text-muted)" }} disabled={salvandoMotivoPerda.has(e.id)}
                                    title="A perda de prenhez continua registrada — só o motivo fica sem informar"
                                    onClick={() => cadastrarMotivoPerda(e, "nao_informado")}>
                                    <X size={11} /> Descartar
                                  </button>
                                </div>
                              ) : (
                                <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id)} />
                              )}
                            </td>
                          </tr>
                        </React.Fragment>
                      );
                    }
                    if (linha.tipo === "iatf") {
                      const e = linha.e;
                      const abertoIatf = iatfAbertos.has(e.id);
                      const checks = iatfChecks[e.id] || new Set(e.animais);
                      const ehD11 = e.dia === 11;
                      return (
                        <React.Fragment key={`iatf-${i}`}>
                          <tr style={{ cursor: "pointer" }} onClick={() => abrirIatf(e.id, e.animais)}>
                            {tdAccent("Reprodutivo")}
                            <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{e.animais.length} animal(is)</td>
                            <td style={{ fontSize: "0.83rem" }} title="Reprodutivo">
                              {abertoIatf ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                              {e.descricao}{mostrarAtraso && pillAtraso(e.data)}
                            </td>
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || <span className="ag2-nada">—</span>}</td>
                            <td style={{ fontSize: "0.7rem", color: "var(--amber)" }}>manual</td>
                            <td onClick={(ev) => ev.stopPropagation()}>
                              {!ehD11 && <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id, undefined, e.hormonios)} />}
                            </td>
                          </tr>
                          {abertoIatf && (
                            <tr style={{ background: "var(--surface-2)" }}>
                              <td></td>
                              <td colSpan={5}>
                                <div style={{ padding: "0.5rem 0" }}>
                                  <p style={{ fontSize: "0.78rem", marginBottom: "0.4rem" }}>
                                    <Syringe size={12} style={{ display: "inline", marginRight: "0.3rem" }} />
                                    <strong>Hormônio/ação do dia:</strong> {e.hormonio}
                                  </p>
                                  <table className="fazenda-table" style={{ margin: 0 }}>
                                    <thead><tr>{!ehD11 && <th></th>}<th>Nº</th>{ehD11 && <th></th>}</tr></thead>
                                    <tbody>
                                      {e.animais.map((numero: string) => (
                                        <tr key={numero}>
                                          {!ehD11 && (
                                            <td>
                                              <input type="checkbox" checked={checks.has(numero)} onChange={() => toggleAnimalIatf(e.id, numero)} />
                                            </td>
                                          )}
                                          <td style={{ fontWeight: 700 }}>{numero}</td>
                                          {ehD11 && (
                                            <td>
                                              <button
                                                type="button"
                                                onClick={() => abrirGavetaInseminacao({ numeroMatriz: numero, protocolo: e.protocolo || null })}
                                                className="btn-ghost" style={{ fontSize: "0.7rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                                              >
                                                <Syringe size={12} /> Ir para Inseminação
                                              </button>
                                            </td>
                                          )}
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                  {!ehD11 && (e.hormonios?.length ?? 0) > 0 && (
                                    <div style={{ marginTop: "0.6rem", background: "var(--surface)", border: "1px solid var(--dourado)", borderRadius: 8, padding: "0.55rem 0.7rem" }}>
                                      <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.35rem" }}>
                                        Qual medicamento/frasco você está usando?
                                      </div>
                                      {e.hormonios.map((h: any, idx: number) => {
                                        const sel = medIatf[e.id]?.[idx] ?? (h.opcoes?.length === 1 ? h.opcoes[0].estoque_id : "");
                                        return (
                                          <div key={idx} className="flex items-center gap-2" style={{ marginBottom: "0.3rem", flexWrap: "wrap" }}>
                                            <span style={{ fontSize: "0.76rem", minWidth: 130 }}>
                                              {h.produto}{h.dose ? ` · ${h.dose}${h.unidade || ""}` : ""}
                                            </span>
                                            {(h.opcoes?.length ?? 0) === 0 ? (
                                              <span style={{ fontSize: "0.72rem", color: "var(--amber)" }}>Sem medicamento em estoque para este princípio.</span>
                                            ) : (
                                              <select style={{ width: "auto", minWidth: 220, fontSize: "0.76rem", padding: "0.3rem 0.5rem", borderRadius: 6, background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }} value={sel ?? ""}
                                                onChange={(ev) => escolherMedIatf(e.id, idx, ev.target.value ? Number(ev.target.value) : null)}>
                                                <option value="">Selecione o frasco…</option>
                                                {h.opcoes.map((o: any) => (
                                                  <option key={o.estoque_id} value={o.estoque_id}>
                                                    {o.nome}{o.marca ? ` · ${o.marca}` : ""} — saldo {o.saldo} {o.unidade || ""}{!o.estoque_inicializado ? " (sem estoque inicial)" : ""}
                                                  </option>
                                                ))}
                                              </select>
                                            )}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                  {!ehD11 && (
                                    <div className="flex items-center gap-2 mt-2">
                                      <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id) || !checks.size}
                                        onClick={() => marcarRealizado(e.id, Array.from(checks), e.hormonios)}>
                                        <Check size={12} /> Confirmar realizado ({checks.size}/{e.animais.length})
                                      </button>
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    }
                    if (linha.tipo === "protocolo_custom") {
                      const e = linha.e;
                      const aberto = protocoloCustomAbertos.has(e.id);
                      const checks = protocoloCustomChecks[e.id] || new Set(e.animais);
                      return (
                        <React.Fragment key={`protocolo-custom-${i}`}>
                          <tr style={{ cursor: "pointer" }} onClick={() => abrirProtocoloCustom(e.id, e.animais)}>
                            {tdAccent(e.categoria)}
                            <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{e.animais.length} animal(is)</td>
                            <td style={{ fontSize: "0.83rem" }} title={categoriaLabel(e.categoria)}>
                              {aberto ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                              {e.descricao}{mostrarAtraso && pillAtraso(e.data)}
                            </td>
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || <span className="ag2-nada">—</span>}</td>
                            <td style={{ fontSize: "0.7rem", color: "var(--amber)" }}>manual</td>
                            <td onClick={(ev) => ev.stopPropagation()} />
                          </tr>
                          {aberto && (
                            <tr style={{ background: "var(--surface-2)" }}>
                              <td></td>
                              <td colSpan={5}>
                                <div style={{ padding: "0.5rem 0" }}>
                                  <table className="fazenda-table" style={{ margin: 0 }}>
                                    <thead><tr><th></th><th>Nº</th></tr></thead>
                                    <tbody>
                                      {e.animais.map((numero: string) => (
                                        <tr key={numero}>
                                          <td><input type="checkbox" checked={checks.has(numero)} onChange={() => toggleAnimalProtocoloCustom(e.id, numero)} /></td>
                                          <td style={{ fontWeight: 700 }}>{numero}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                  <div className="flex items-center gap-2 mt-2">
                                    <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id) || !checks.size}
                                      onClick={() => marcarRealizado(e.id, Array.from(checks))}>
                                      <Check size={12} /> Confirmar realizado ({checks.size}/{e.animais.length})
                                    </button>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    }
                    if (linha.tipo === "inducao") {
                      const e = linha.e;
                      const abertoInducao = inducaoAbertos.has(e.id);
                      const checks = inducaoChecks[e.id] || new Set(e.animais);
                      return (
                        <React.Fragment key={`inducao-${i}`}>
                          <tr style={{ cursor: "pointer" }} onClick={() => abrirInducao(e.id, e.animais)}>
                            {tdAccent("Produção")}
                            <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{e.animais.length} animal(is)</td>
                            <td style={{ fontSize: "0.83rem" }} title="Produção">
                              {abertoInducao ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                              {e.descricao}{mostrarAtraso && pillAtraso(e.data)}
                            </td>
                            <td style={{ color: "var(--amber)", fontSize: "0.78rem", fontWeight: e.observacao ? 700 : 400 }}>{e.observacao || <span className="ag2-nada">—</span>}</td>
                            <td style={{ fontSize: "0.7rem", color: "var(--amber)" }}>manual</td>
                            <td onClick={(ev) => ev.stopPropagation()}>
                              <BotaoRealizado chave={e.id} onConfirmar={() => marcarRealizado(e.id, undefined, e.medicamentos_opcoes)} />
                            </td>
                          </tr>
                          {abertoInducao && (
                            <tr style={{ background: "var(--surface-2)" }}>
                              <td></td>
                              <td colSpan={5}>
                                <div style={{ padding: "0.5rem 0" }}>
                                  <p style={{ fontSize: "0.78rem", marginBottom: "0.2rem" }}>
                                    <Syringe size={12} style={{ display: "inline", marginRight: "0.3rem" }} />
                                    <strong>Medicamento(s) do dia:</strong> {e.medicamentos}
                                  </p>
                                  {e.observacao && (
                                    <p style={{ fontSize: "0.78rem", marginBottom: "0.4rem", color: "var(--amber)" }}>
                                      <strong>Observação para o funcionário:</strong> {e.observacao}
                                    </p>
                                  )}
                                  <table className="fazenda-table" style={{ margin: 0 }}>
                                    <thead><tr><th></th><th>Nº</th></tr></thead>
                                    <tbody>
                                      {e.animais.map((numero: string) => (
                                        <tr key={numero}>
                                          <td><input type="checkbox" checked={checks.has(numero)} onChange={() => toggleAnimalInducao(e.id, numero)} /></td>
                                          <td style={{ fontWeight: 700 }}>{numero}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                  {(e.medicamentos_opcoes?.length ?? 0) > 0 && (
                                    <div style={{ marginTop: "0.6rem", background: "var(--surface)", border: "1px solid var(--dourado)", borderRadius: 8, padding: "0.55rem 0.7rem" }}>
                                      <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.35rem" }}>
                                        Qual medicamento/frasco você está usando?
                                      </div>
                                      {e.medicamentos_opcoes.map((h: any, idx: number) => {
                                        const sel = medIatf[e.id]?.[idx] ?? (h.opcoes?.length === 1 ? h.opcoes[0].estoque_id : "");
                                        return (
                                          <div key={idx} className="flex items-center gap-2" style={{ marginBottom: "0.3rem", flexWrap: "wrap" }}>
                                            <span style={{ fontSize: "0.76rem", minWidth: 130 }}>
                                              {h.produto}{h.dose ? ` · ${h.dose}${h.unidade || ""}` : ""}
                                            </span>
                                            {(h.opcoes?.length ?? 0) === 0 ? (
                                              <span style={{ fontSize: "0.72rem", color: "var(--amber)" }}>Sem medicamento em estoque para este princípio.</span>
                                            ) : (
                                              <select style={{ width: "auto", minWidth: 220, fontSize: "0.76rem", padding: "0.3rem 0.5rem", borderRadius: 6, background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }} value={sel ?? ""}
                                                onChange={(ev) => escolherMedIatf(e.id, idx, ev.target.value ? Number(ev.target.value) : null)}>
                                                <option value="">Selecione o frasco…</option>
                                                {h.opcoes.map((o: any) => (
                                                  <option key={o.estoque_id} value={o.estoque_id}>
                                                    {o.nome}{o.marca ? ` · ${o.marca}` : ""} — saldo {o.saldo} {o.unidade || ""}{!o.estoque_inicializado ? " (sem estoque inicial)" : ""}
                                                  </option>
                                                ))}
                                              </select>
                                            )}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                  <div className="flex items-center gap-2 mt-2">
                                    <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id) || !checks.size}
                                      onClick={() => marcarRealizado(e.id, Array.from(checks), e.medicamentos_opcoes)}>
                                      <Check size={12} /> Confirmar realizado ({checks.size}/{e.animais.length})
                                    </button>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    }
                    // Grupo Gestão/Financeiro por nota/lançamento.
                    const { ref, itens } = linha;
                    const chaveGrupo = `${d}:${ref}`;
                    const abertoGrupo = paineis.has(chaveGrupo);
                    const total = itens.reduce((acc: number, it: any) => acc + (Number(extrairValor(it.descricao)) || 0), 0);
                    return (
                      <React.Fragment key={`g-${i}`}>
                        <tr style={{ cursor: "pointer" }} onClick={() => togglePainel(chaveGrupo)}>
                          {tdAccent("Gestão/Financeiro")}
                          <td>—</td>
                          <td style={{ fontSize: "0.83rem" }} title="Gestão/Financeiro">
                            {abertoGrupo ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                            Nota/lançamento <strong>{ref}</strong> — {itens.length} {itens.length !== 1 ? "itens" : "item"} — R$ {total.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}{mostrarAtraso && pillAtraso(itens[0]?.data || d)}
                          </td>
                          <td>—</td>
                          <td style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>auto</td>
                          <td onClick={(ev) => ev.stopPropagation()}>
                            <button type="button" className="btn-primary" disabled={resolvendoPagamento === ref}
                              style={{ fontSize: "0.68rem", padding: "0.15rem 0.6rem", marginRight: "0.3rem" }}
                              title="Pagar esta conta aqui mesmo (data, forma, conta bancária, comprovante)"
                              onClick={() => abrirPagamento(ref)}>
                              {resolvendoPagamento === ref ? "Abrindo…" : "Pagar"}
                            </button>
                            <a href={`/financeiro?ir=a_pagar&ref=${encodeURIComponent(ref)}`} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                              <Wallet size={12} /> Ir para Financeiro
                            </a>
                          </td>
                        </tr>
                        {abertoGrupo && (
                          <tr style={{ background: "var(--surface-2)" }}>
                            <td></td><td></td>
                            <td colSpan={3} style={{ padding: "0.4rem 0.9rem" }}>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                                {itens.map((it: any, j: number) => (
                                  <span key={`g-${i}-${j}`} title={it.observacao || undefined}
                                    style={{ fontSize: "0.74rem", color: "var(--text-muted)", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 999, padding: "0.2rem 0.65rem" }}>
                                    {it.descricao}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td></td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      );
    });
  };

  // ── Visão de calendário (opção 2 do mockup) — grade do mês com um ponto por
  // categoria presente em cada dia + painel lateral com a lista de
  // compromissos, sempre visível (hoje pré-selecionado, ou o dia 1º do mês
  // exibido quando "hoje" cai fora dele), reaproveitando renderEventos
  // (mesma interação de dar baixa/marcar realizado da linha do tempo, sem
  // duplicar lógica).
  const selecionarPrimeiroDiaDoMes = (ano: number, mes: number) => {
    const dentroDoMesAtual = hoje.slice(0, 4) === String(ano) && Number(hoje.slice(5, 7)) - 1 === mes;
    setDiaSelecionado(dentroDoMesAtual ? hoje : isoLocal(ano, mes, 1));
  };
  const mudarMes = (delta: number) => {
    setMesCalendario((p) => {
      let mes = p.mes + delta, ano = p.ano;
      if (mes < 0) { mes = 11; ano -= 1; } else if (mes > 11) { mes = 0; ano += 1; }
      selecionarPrimeiroDiaDoMes(ano, mes);
      return { ano, mes };
    });
  };
  const irParaMesAtual = () => { const d = new Date(); setMesCalendario({ ano: d.getFullYear(), mes: d.getMonth() }); setDiaSelecionado(hoje); };
  const abrirDiaCalendario = (iso: string) => {
    setDiaSelecionado((prev) => (prev === iso ? null : iso));
    setDatasAbertas((p) => { const n = new Set(p); n.add(iso); return n; });
  };

  const renderCalendario = () => {
    const primeiroDiaIso = isoLocal(mesCalendario.ano, mesCalendario.mes, 1);
    const diasNoMes = new Date(mesCalendario.ano, mesCalendario.mes + 1, 0).getDate();
    const ultimoDiaIso = isoLocal(mesCalendario.ano, mesCalendario.mes, diasNoMes);
    const primeiroDiaSemana = new Date(mesCalendario.ano, mesCalendario.mes, 1).getDay();

    const eventosDoMes = eventosBase.filter((e: any) => e.data >= primeiroDiaIso && e.data <= ultimoDiaIso);
    const eventosPorDiaCal = new Map<string, any[]>();
    eventosDoMes.forEach((e: any) => { (eventosPorDiaCal.get(e.data) ?? eventosPorDiaCal.set(e.data, []).get(e.data)!).push(e); });

    const celulas: (string | null)[] = [];
    for (let i = 0; i < primeiroDiaSemana; i++) celulas.push(null);
    for (let dia = 1; dia <= diasNoMes; dia++) celulas.push(isoLocal(mesCalendario.ano, mesCalendario.mes, dia));

    const eventosDoDiaSelecionado = diaSelecionado ? (eventosPorDiaCal.get(diaSelecionado) || []) : [];

    return (
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "1.25rem", alignItems: "start" }}>
        <div>
          <div className="flex items-center justify-between mb-3">
            <button className="btn-ghost" onClick={() => mudarMes(-1)} title="Mês anterior"><ChevronLeft size={16} /></button>
            <button className="btn-ghost" onClick={irParaMesAtual} style={{ fontWeight: 700, fontSize: "0.9rem" }}>
              {NOMES_MES[mesCalendario.mes]} de {mesCalendario.ano}
            </button>
            <button className="btn-ghost" onClick={() => mudarMes(1)} title="Próximo mês"><ChevronRight size={16} /></button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: "4px" }}>
            {DIAS_SEMANA_ABREV.map((d) => (
              <div key={d} style={{ textAlign: "center", fontSize: "0.68rem", fontWeight: 700, color: "var(--text-muted)", padding: "0.2rem 0" }}>{d}</div>
            ))}
            {celulas.map((iso, i) => {
              if (!iso) return <div key={`vazio-${i}`} />;
              const evs = eventosPorDiaCal.get(iso) || [];
              const categoriasUnicas = Array.from(new Set(evs.map((e: any) => e.categoria)));
              const atrasado = iso < hoje && evs.length > 0;
              const ehHoje = iso === hoje;
              const ehSelecionado = iso === diaSelecionado;
              return (
                <button key={iso} type="button" onClick={() => abrirDiaCalendario(iso)} className="ag2-cel" aria-pressed={ehSelecionado}
                  aria-label={`${Number(iso.slice(8, 10))}: ${evs.length} ${evs.length === 1 ? "tarefa" : "tarefas"}`}
                  title={evs.length ? `${evs.length} evento${evs.length !== 1 ? "s" : ""}` : undefined}
                  style={{
                    minHeight: "4.4rem", padding: "0.3rem 0.35rem", borderRadius: "var(--r-sm)", textAlign: "left", cursor: "pointer",
                    display: "flex", flexDirection: "column", gap: "0.25rem",
                    border: "1px solid " + (ehSelecionado ? "var(--dourado)" : ehHoje ? "var(--dourado-light)" : "var(--border)"),
                    background: ehSelecionado ? "rgba(184,134,11,0.18)" : ehHoje ? "rgba(184,134,11,0.08)" : "var(--surface-2)",
                  }}>
                  <span style={{ fontSize: "0.78rem", fontWeight: ehHoje ? 800 : 600, color: atrasado ? "var(--red)" : "var(--text)" }}>
                    {Number(iso.slice(8, 10))}
                  </span>
                  {evs.length > 0 && (
                    <>
                      <div className="flex items-center gap-1" style={{ flexWrap: "wrap" }}>
                        {categoriasUnicas.slice(0, 4).map((c: any) => (
                          <span key={c} style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: corCategoria(c) }} />
                        ))}
                      </div>
                      <span className="ag2-cel-txt" style={{ fontSize: "0.62rem", color: "var(--text-muted)" }}>{evs.length} evento{evs.length !== 1 ? "s" : ""}</span>
                      <span className="ag2-cel-num" aria-hidden="true">{evs.length}</span>
                    </>
                  )}
                </button>
              );
            })}
          </div>
        </div>
        {diaSelecionado && (
          <div className="card" style={{ background: "var(--surface-2)" }}>
            <div className="card-header mb-2 flex items-center justify-between" style={{ gap: "0.5rem" }}>
              <span className="ag2-cap1" style={{ fontSize: "0.85rem" }}>
                {new Date(diaSelecionado + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })}
              </span>
              <button className="btn-ghost" onClick={() => setDiaSelecionado(null)} title="Fechar"><X size={14} /></button>
            </div>
            {eventosDoDiaSelecionado.length > 0 ? (
              <div className="space-y-2">{renderEventos(eventosDoDiaSelecionado, diaSelecionado < hoje)}</div>
            ) : (
              <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", padding: "0.5rem 0" }}>Nenhum evento nesse dia.</p>
            )}
          </div>
        )}
      </div>
    );
  };

  // Painel lateral novo (redesign T3, mockup 1i): mini-calendário do mês,
  // só leitura — deliberadamente SEM o mecanismo de dia selecionado/painel
  // lateral do renderCalendario() acima (aquele abre um segundo grid de
  // 320px que não cabe dentro dos 250px deste painel). Clicar num dia aqui
  // só filtra a lista principal (reaproveita `de`/`ate`, os mesmos estados
  // do filtro de período) — nenhum estado novo de seleção de dia.
  const renderMiniCalendario = () => {
    const primeiroDiaIso = isoLocal(mesCalendario.ano, mesCalendario.mes, 1);
    const diasNoMes = new Date(mesCalendario.ano, mesCalendario.mes + 1, 0).getDate();
    const ultimoDiaIso = isoLocal(mesCalendario.ano, mesCalendario.mes, diasNoMes);
    const primeiroDiaSemana = new Date(mesCalendario.ano, mesCalendario.mes, 1).getDay();
    const eventosDoMes = eventosBase.filter((e: any) => e.data >= primeiroDiaIso && e.data <= ultimoDiaIso);
    const contagemPorDia = new Map<string, number>();
    eventosDoMes.forEach((e: any) => contagemPorDia.set(e.data, (contagemPorDia.get(e.data) || 0) + 1));
    const celulas: (string | null)[] = [];
    for (let i = 0; i < primeiroDiaSemana; i++) celulas.push(null);
    for (let dia = 1; dia <= diasNoMes; dia++) celulas.push(isoLocal(mesCalendario.ano, mesCalendario.mes, dia));

    return (
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <button className="btn-ghost" onClick={() => mudarMes(-1)} title="Mês anterior" style={{ padding: "0.2rem" }}><ChevronLeft size={14} /></button>
          <span style={{ fontWeight: 700, fontSize: "0.8rem" }}>{NOMES_MES[mesCalendario.mes]} {mesCalendario.ano}</span>
          <button className="btn-ghost" onClick={() => mudarMes(1)} title="Próximo mês" style={{ padding: "0.2rem" }}><ChevronRight size={14} /></button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: "2px" }}>
          {DIAS_SEMANA_ABREV.map((d) => (
            <div key={d} style={{ textAlign: "center", fontSize: "0.6rem", fontWeight: 700, color: "var(--text-muted)" }}>{d[0]}</div>
          ))}
          {celulas.map((iso, i) => {
            if (!iso) return <div key={`vazio-${i}`} />;
            const n = contagemPorDia.get(iso) || 0;
            const atrasado = iso < hoje && n > 0;
            const ehHoje = iso === hoje;
            const ehFiltro = de === iso && ate === iso;
            return (
              <button key={iso} type="button" title={n ? `${n} evento${n !== 1 ? "s" : ""} — clique para filtrar a lista neste dia` : iso}
                onClick={() => { if (ehFiltro) { setDe(""); setAte(""); } else { setDe(iso); setAte(iso); } }}
                style={{
                  aspectRatio: "1", fontSize: "0.68rem", borderRadius: "4px", cursor: "pointer",
                  border: "1px solid " + (ehFiltro ? "var(--dourado)" : "transparent"),
                  background: ehFiltro ? "rgba(184,134,11,0.18)" : ehHoje ? "rgba(184,134,11,0.08)" : "transparent",
                  color: atrasado ? "var(--red)" : "var(--text)", fontWeight: ehHoje ? 800 : 500,
                  display: "flex", alignItems: "center", justifyContent: "center", position: "relative",
                }}>
                {Number(iso.slice(8, 10))}
                {n > 0 && <span style={{ position: "absolute", bottom: 2, width: 4, height: 4, borderRadius: "50%", background: atrasado ? "var(--red)" : "var(--dourado-light)" }} />}
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  const candidatas = agenda?.candidatas_iatf || [];
  const bstAptos = agenda?.bst_elegiveis || [];
  const bstExcl = agenda?.bst_excluidos || [];
  const bstNuncaAplicados = agenda?.bst_nunca_aplicados || [];
  const estoqueAlertasTotal = (agenda?.estoque_negativo?.length || 0) + (agenda?.estoque_abaixo_minimo?.length || 0);

  // "IATF atual" — protocolos com pelo menos uma etapa (D0/D7/D9/D11) ainda em
  // aberto agora (ver GET /reproducao/protocolo-iatf/ativos); some sozinho
  // quando não há nenhum D0 em andamento até a inseminação (D11). "Última
  // IATF" — o grupo mais recente já concluído (D11 com baixa), com os
  // animais que entraram nele (para o quadro "ÚLTIMA IATF").
  const gruposIatfAtivos = iatfAtivos.filter((g: any) => !g.concluido);
  const animaisIatfAtual = gruposIatfAtivos.flatMap((g: any) =>
    (g.animais || []).map((a: any) => ({ ...a, nome_protocolo: g.nome_protocolo, data_d0: g.data_d0 }))
  );
  const grupoUltimaIatf = iatfAtivos
    .filter((g: any) => g.concluido)
    .sort((a: any, b: any) => (b.data_d11 || "").localeCompare(a.data_d11 || ""))[0] || null;

  // Próxima visita reprodutiva/BST — ancorada no serviço mais recente do
  // rebanho (calculada no backend; ex.: último serviço 03/07 -> visita 24/07).
  const fmtCurta = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" }) : null);
  // Igual a fmtCurta, mas com o ano (2 dígitos) — usado no quadro "Última
  // IATF" (ex.: D0 03/07/26), onde a data sozinha ficaria ambígua entre anos.
  const fmtCurtaAno = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" }) : null);
  const proxVisita = fmtCurta(agenda?.proxima_visita_iatf);
  const proxBST = fmtCurta(agenda?.proxima_visita_bst);

  // Referência para rolar até a seção "Estoque — alertas" (agora no final da
  // página) quando o quadro "Alertas de estoque" das informações gerenciais
  // é clicado.
  const estoqueAlertasRef = useRef<HTMLDivElement>(null);
  // Rolagem pendente para uma seção do Painel: quem clica de outra sub-aba (ex.:
  // o evento "Aplicação de BST" no Dia a dia) troca de visão e rola depois que
  // o Painel estiver desenhado.
  const rolarPara = useRef<"bst" | "estoque" | "concluidos" | null>(null);
  const concluidosRef = useRef<HTMLDivElement>(null);
  const rolarAteSecao = (alvo: "bst" | "estoque" | "concluidos") => {
    const el = alvo === "bst" ? bstIndicadoresRef.current : alvo === "estoque" ? estoqueAlertasRef.current : concluidosRef.current;
    if (!el) return false;
    const reduzMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ behavior: reduzMovimento ? "auto" : "smooth", block: "start" });
    return true;
  };
  useEffect(() => {
    if (visao !== "painel" || !rolarPara.current) return;
    const alvo = rolarPara.current;
    const id = requestAnimationFrame(() => { if (rolarAteSecao(alvo)) rolarPara.current = null; });
    return () => cancelAnimationFrame(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visao, agenda]);
  const abrirAlertasEstoque = () => {
    setPaineis((p) => new Set(p).add("estoqueAlertas"));
    rolarPara.current = "estoque";
    if (visao !== "painel") mudarVisao("painel"); else rolarAteSecao("estoque");
  };

  // Compromisso "Aplicação de BST" na Agenda (aparece com antecedência, na
  // data real da próxima aplicação — não só no dia em que ela cai): ao
  // clicar, abre (não alterna) as listas BST aptos + Incluir no próximo BST
  // e rola até elas — é a mesma informação já mostrada nos quadros/listas
  // acima, só que o usuário chega direto nela a partir do evento.
  const bstIndicadoresRef = useRef<HTMLDivElement>(null);
  const abrirListasBst = () => {
    setListaAtiva((p) => { const n = new Set(p); n.add("bstAptos"); n.add("bstNunca"); return n; });
    rolarPara.current = "bst";
    if (visao !== "painel") mudarVisao("painel"); else rolarAteSecao("bst");
  };

  const ordIatf = useOrdenacao(candidatas);
  const [listaAtiva, setListaAtiva] = useState<Set<string>>(new Set());
  const toggleLista = (k: string) => setListaAtiva((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });

  // Ação rápida "Adicionar à agenda" a partir de uma linha de candidata/apta —
  // cria o evento manual já vinculado ao animal, sem precisar abrir o modal geral.
  const [agendandoNumero, setAgendandoNumero] = useState<string | null>(null);
  const agendarAnimal = async (numero: string, descricao: string, categoria: string) => {
    setAgendandoNumero(numero);
    try {
      await addEventoManual({ data_evento: today(), descricao, categoria, numero_animal: numero });
      carregar();
      mostrarFeedback(`Evento adicionado à agenda para o animal ${numero}.`);
    } catch (e: any) { mostrarFeedback(e.message, true); }
    finally { setAgendandoNumero(null); }
  };
  const BotaoAgendar = ({ numero, descricao, categoria }: { numero: string; descricao: string; categoria: string }) => (
    <button className="btn-ghost" disabled={agendandoNumero === numero} title="Adicionar à agenda" onClick={() => agendarAnimal(numero, descricao, categoria)}
      style={{ fontSize: "0.72rem", padding: "0.15rem 0.5rem" }}>
      <Plus size={12} /> {agendandoNumero === numero ? "…" : "Agendar"}
    </button>
  );

  // Exportar Excel/PDF da Agenda — pede o período (data início/fim) antes de
  // gerar, para filtrar exatamente o que sai no arquivo (em vez de sempre
  // exportar tudo o que está carregado na tela).
  const ExportarAgendaBotoes = ({ eventos }: { eventos: any[] }) => {
    const [aberto, setAberto] = useState<"excel" | "pdf" | null>(null);
    const [inicio, setInicio] = useState("");
    const [fim, setFim] = useState("");
    const [gerando, setGerando] = useState(false);
    const semDados = eventos.length === 0;
    const btn: React.CSSProperties = {
      display: "flex", alignItems: "center", gap: "0.35rem", padding: "0.4rem 0.7rem", borderRadius: "var(--r-sm)",
      border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text-muted)",
      fontSize: "0.78rem", fontWeight: 600, cursor: semDados ? "not-allowed" : "pointer", opacity: semDados ? 0.5 : 1,
    };
    const confirmar = async () => {
      setGerando(true);
      try {
        const filtrados = eventos.filter((e) => (!inicio || e.data >= inicio) && (!fim || e.data <= fim));
        if (aberto === "excel") await exportarExcel("Agenda", COLUNAS_AGENDA, filtrados, "agenda");
        else await exportarPDF("Agenda", COLUNAS_AGENDA, filtrados, "agenda");
        setAberto(null);
      } catch {
        // erro já mostrado ao usuário dentro de exportarExcel/exportarPDF (lib/export.ts)
      } finally { setGerando(false); }
    };
    return (
      <div style={{ position: "relative" }}>
        <div className="flex items-center gap-2">
          <button type="button" style={btn} disabled={semDados} onClick={() => setAberto("excel")} title="Exportar para Excel">
            <FileSpreadsheet size={14} /> Excel
          </button>
          <button type="button" style={btn} disabled={semDados} onClick={() => setAberto("pdf")} title="Exportar para PDF">
            <FileText size={14} /> PDF
          </button>
        </div>
        {aberto && (
          <div className="card" style={{ position: "absolute", top: "2.3rem", right: 0, zIndex: 20, width: "260px", padding: "0.9rem" }}>
            <p style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.5rem" }}>
              Exportar {aberto === "excel" ? "Excel" : "PDF"} — período
            </p>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <div>
                <label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>De</label>
                <input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem", color: "var(--text)", fontSize: "0.75rem" }} />
              </div>
              <div>
                <label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Até</label>
                <input type="date" value={fim} onChange={(e) => setFim(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem", color: "var(--text)", fontSize: "0.75rem" }} />
              </div>
            </div>
            <p style={{ fontSize: "0.66rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>Deixe em branco para exportar tudo o que está carregado.</p>
            <div className="flex items-center gap-2">
              <button className="btn-primary" style={{ fontSize: "0.75rem" }} disabled={gerando} onClick={confirmar}>{gerando ? "Gerando…" : "Exportar"}</button>
              <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setAberto(null)}>Cancelar</button>
            </div>
          </div>
        )}
      </div>
    );
  };

  // ─────────────────────────── Sub-aba "Dia a dia" ───────────────────────────
  // Só lista e calendário para a rotina: sem cartões, sem candidatas, sem lista
  // de espera (animal na janela NUNCA é tarefa — R1). Tudo isso mora no Painel.
  const rolarParaId = (id: string) => {
    const reduz = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(id)?.scrollIntoView({ behavior: reduz ? "auto" : "smooth", block: "start" });
  };
  const limite7 = addDias(hoje, 7);
  const proximos7 = eventosProximos.filter((e: any) => e.data <= limite7).length;
  const semanaFim = addDias(semanaInicio, 6);
  const eventosDaSemana = eventosBase.filter((e: any) => e.data >= semanaInicio && e.data <= semanaFim);
  const mudarSemana = (delta: number) => {
    const novo = delta === 0 ? inicioDaSemana(hoje) : addDias(semanaInicio, delta * 7);
    setSemanaInicio(novo);
    setDiaSelecionado(delta === 0 ? hoje : novo);
  };
  const horaAtualizado = agenda?.gerado_em ? new Date(agenda.gerado_em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : null;

  // Card de comunicados (Painel: todos; Dia a dia: só a visita reprodutiva).
  const renderComunicados = (lista: ComunicadoAgenda[]) => (
    <>
      {/* Comunicados — avisos informativos (ex.: nova dieta do lote). Diferente
          de uma atividade: não têm botão de excluir/realizado, ficam fixos
          enquanto vigoram e somem sozinhos quando a data passa. */}
      {lista.length > 0 && (
        <div className="card mb-4" style={{ border: "1px solid var(--dourado)" }}>
          <div className="card-header mb-3 flex items-center gap-2" style={{ color: "var(--dourado-light)" }}>
            <Megaphone size={15} /> Comunicados ({lista.length})
          </div>
          <div className="space-y-2">
            {lista.map((e: any) => (
              // Visita reprodutiva: o card inteiro leva à Agenda Reprodutiva (Insights › Listas); os botões abaixo também.
              <div key={e.id} className="flex items-start justify-between gap-3" data-testid={e.tipo === "visita_reprodutiva" ? "comunicado-visita-reprodutiva" : undefined}
                onClick={e.tipo === "visita_reprodutiva" ? () => router.push(URL_AGENDA_REPRODUTIVA) : undefined}
                style={{ padding: "0.6rem 0.8rem", borderRadius: "var(--r-sm)", background: "var(--surface-2)", border: "1px solid var(--border)", cursor: e.tipo === "visita_reprodutiva" ? "pointer" : undefined }}>
                <div>
                  <p style={{ fontSize: "0.83rem", fontWeight: 600 }}>
                    {e.tipo === "visita_reprodutiva"
                      ? <a href={URL_AGENDA_REPRODUTIVA} onClick={(ev) => ev.stopPropagation()} style={{ color: "inherit", textDecoration: "underline" }}>{e.descricao}</a>
                      : e.descricao}
                  </p>
                  {e.observacao && <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>{e.observacao}</p>}
                </div>
                {/* Só o comunicado de NOVA DIETA leva à tela de dieta. A
                    condição era por categoria, e o alerta de sobra também sai
                    como "alimentacao" — então herdava este botão, que é
                    exatamente o atalho de lançamento que o alerta de sobra não
                    pode ter: ele é comunicado, resolve-se com o Check e nada
                    mais. */}
                {e.tipo === "visita_reprodutiva" && (
                  <div className="flex items-center gap-2" style={{ flexWrap: "wrap", justifyContent: "flex-end" }} onClick={(ev) => ev.stopPropagation()}>
                    <a href={URL_AGENDA_REPRODUTIVA} className="btn-secondary" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", whiteSpace: "nowrap", textDecoration: "none" }}>
                      <ClipboardList size={12} /> Ver agenda reprodutiva
                    </a>
                    <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", whiteSpace: "nowrap" }}
                      onClick={() => setDefinindoVisita({ data: e.data_visita ?? e.data, origem: e.origem_visita ?? null, intervalo: e.intervalo_visita ?? null, ultima: e.ultima_visita ?? null })}>
                      <Calendar size={12} /> Definir nova data da visita
                    </button>
                  </div>
                )}
                {e.categoria === "alimentacao" && (e as any).tipo === "nova_dieta" && (
                  <a href={`/alimentacao?lote=${encodeURIComponent(e.lote ?? "")}`} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", whiteSpace: "nowrap" }}>
                    <Wheat size={12} /> Ir para Dieta
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );

  const renderDiaADia = () => (
    <div id="ag2-painel-dia" role="tabpanel" aria-labelledby="ag2-tab-dia">
      {renderComunicados((agenda?.comunicados_dia as ComunicadoAgenda[] | undefined) || [])}

      <div className="ag2-controles">
        <div className="ag2-visoes" role="group" aria-label="Como ver as tarefas">
          {([["lista", "Lista"], ["semana", "Semana"], ["mes", "Mês"]] as const).map(([id, rotulo]) => (
            <button key={id} type="button" aria-pressed={modoDia === id} onClick={() => { setModoDia(id); if (id === "semana") { setSemanaInicio(inicioDaSemana(hoje)); setDiaSelecionado(hoje); } }}>{rotulo}</button>
          ))}
        </div>
        <div className="ag2-busca">
          <Search size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} aria-hidden="true" />
          <input id="agenda-filtro-busca" aria-label="Buscar tarefa, lote ou número do animal" value={filtro} onChange={(e) => setFiltro(e.target.value)} placeholder="Buscar tarefa, lote, animal…" />
        </div>
        <select id="agenda-filtro-categoria" className="ag2-select" aria-label="Categoria" value={fCat} onChange={(e) => setFCat(e.target.value)}>
          <option value="">Categoria</option>{categoriasVisiveis.map((c) => <option key={c}>{c}</option>)}
        </select>
        {(de || ate || fCat || filtro) && (
          <button className="btn-ghost" onClick={() => { setDe(""); setAte(""); setFCat(""); setFiltro(""); }}>Limpar filtros</button>
        )}
      </div>

      {agenda?.eventos ? (
      <p className="ag2-linha-contagem" aria-live="polite">
        {eventosPendentes.length > 0 ? (
          <button type="button" className="ag2-link ag2-atraso" onClick={() => { setModoDia("lista"); setTimeout(() => rolarParaId("ag2-atrasadas"), 30); }}>
            <AlertTriangle size={14} style={{ display: "inline", verticalAlign: "-2px" }} aria-hidden="true" /> {eventosPendentes.length} {eventosPendentes.length === 1 ? "atrasada" : "atrasadas"}
          </button>
        ) : <span>Nada atrasado</span>}
        <span aria-hidden="true">·</span>
        <button type="button" className="ag2-link" onClick={() => { setModoDia("lista"); setTimeout(() => rolarParaId("ag2-hoje"), 30); }}><strong>{eventosHoje.length}</strong> de hoje</button>
        <span aria-hidden="true">·</span>
        <span><strong>{proximos7}</strong> nos próximos 7 dias</span>
        {(agenda?.resumo?.avisos ?? 0) > 0 && (
          <>
            <span aria-hidden="true">·</span>
            <button type="button" className="ag2-link" title="Avisos informativos (ex.: nova dieta) ficam no Painel" onClick={() => { mudarVisao("painel"); }}>
              {agenda.resumo.avisos} {agenda.resumo.avisos === 1 ? "aviso" : "avisos"}
            </button>
          </>
        )}
      </p>
      ) : <p className="ag2-linha-contagem" aria-hidden="true">&nbsp;</p>}

      <div className={"ag2-corpo" + (modoDia === "lista" ? "" : " ag2-corpo-um")}>
        {modoDia === "lista" && (
          <div className="card ag2-lista" style={{ padding: "0.75rem" }}>
            <div className="card-header mb-1 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <span>Tarefas ({eventosPendentes.length + eventosFuturos.length})</span>
              <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                {!ate && <span className="ag2-dica-lista" style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>próximos {DIAS_PADRAO_FUTURO} dias — em Semana ou Mês você vê mais</span>}
                <ExportarAgendaBotoes eventos={[...eventosPendentes, ...eventosFuturos]} />
              </div>
            </div>
            {loading && !agenda ? (
              <p className="ag2-carregando" role="status">Buscando as tarefas…</p>
            ) : (
              <div style={{ marginTop: "0.5rem" }}>
                {eventosPendentes.length > 0 && (
                  <section id="ag2-atrasadas" style={{ scrollMarginTop: "1rem" }}>
                    <div className="flex items-center gap-2" style={{ color: "var(--alert-fg)", fontWeight: 700, fontSize: "0.85rem", margin: "0.4rem 0" }}>
                      <AlertTriangle size={14} aria-hidden="true" /> Atrasadas ({eventosPendentes.length})
                    </div>
                    <div className="space-y-2 mb-3">{renderEventos(eventosPendentes, true)}</div>
                  </section>
                )}
                <section id="ag2-hoje" style={{ scrollMarginTop: "1rem" }}>
                  <div className="flex items-center gap-2" style={{ fontWeight: 700, fontSize: "0.85rem", margin: "0.4rem 0" }}>
                    <Calendar size={14} style={{ color: "var(--dourado)" }} aria-hidden="true" /> Hoje · {new Date(hoje + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "long" })} ({eventosHoje.length})
                  </div>
                  {eventosHoje.length > 0 ? (
                    <div className="space-y-2 mb-3">{renderEventos(eventosHoje)}</div>
                  ) : (
                    <p style={{ color: "var(--text-muted)", padding: "0.5rem", fontSize: "0.9rem" }}>Nada para hoje.</p>
                  )}
                </section>
                {diaFechado && diaFechado.total > 0 && (
                  <div className="animate-in mb-3" style={{ padding: "0.55rem 0.7rem", borderLeft: "3px solid var(--dourado)", background: "var(--surface-2)", fontSize: "0.9rem", fontVariantNumeric: "tabular-nums" }}>
                    Dia fechado — {diaFechado.total} de {diaFechado.total} concluídas.
                  </div>
                )}
                {eventosProximos.length > 0 && (
                  <section>
                    <div className="flex items-center gap-2" style={{ color: "var(--text-muted)", fontWeight: 700, fontSize: "0.85rem", margin: "0.4rem 0" }}>
                      <Calendar size={14} aria-hidden="true" /> Próximos dias ({eventosProximos.length})
                    </div>
                    <div className="space-y-2 mb-1">{renderEventos(eventosProximos)}</div>
                  </section>
                )}
                {eventosHoje.length === 0 && eventosProximos.length === 0 && eventosPendentes.length === 0 && (
                  <p style={{ color: "var(--text-muted)", padding: "1rem", textAlign: "center" }}>{agenda ? "Nenhuma tarefa no filtro atual." : ""}</p>
                )}
              </div>
            )}
          </div>
        )}

        {modoDia === "semana" && (
          <div className="card ag2-lista" style={{ padding: "0.75rem" }}>
            <SemanaAgenda eventos={eventosDaSemana} hoje={hoje} inicio={semanaInicio} selecionado={diaSelecionado}
              cor={corCategoria} onMudarSemana={mudarSemana} onSelecionar={(iso) => setDiaSelecionado((atual) => (atual === iso ? null : iso))} />
            {diaSelecionado && diaSelecionado >= semanaInicio && diaSelecionado <= semanaFim && (
              <div style={{ marginTop: "0.75rem" }}>
                <p className="ag2-cap1" style={{ marginBottom: "0.4rem" }}>
                  {new Date(diaSelecionado + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })}
                </p>
                {eventosDaSemana.filter((e: any) => e.data === diaSelecionado).length > 0
                  ? <div className="space-y-2">{renderEventos(eventosDaSemana.filter((e: any) => e.data === diaSelecionado), diaSelecionado < hoje)}</div>
                  : <p className="ag2-mudo">Nenhuma tarefa nesse dia.</p>}
              </div>
            )}
          </div>
        )}

        {modoDia === "mes" && (
          <div className="card ag2-lista" style={{ padding: "0.75rem" }}>{renderCalendario()}</div>
        )}

        {modoDia === "lista" && (
          <div className="flex flex-col gap-3">
            <OQueVem eventos={eventosBase} hoje={hoje} carregando={!agenda?.eventos} onVerSemana={() => { setModoDia("semana"); setSemanaInicio(inicioDaSemana(hoje)); setDiaSelecionado(hoje); }} />
            {agenda?.hormonios_check && agenda.hormonios_check.length > 0 && (
              <div className="card">
                <div className="card-header mb-2" style={{ fontSize: "0.8rem" }}>Precisa de insumo</div>
                <div className="flex flex-col gap-1">
                  {agenda.hormonios_check.map((h: any) => (
                    <div key={h.nome} className="flex items-center justify-between" style={{ fontSize: "0.85rem", gap: "0.5rem" }}>
                      <span>{h.nome}</span>
                      <strong style={{ color: h.suficiente ? "var(--text)" : "var(--alert-fg)" }}>
                        {h.suficiente ? `${h.estoque_atual} ${h.unidade}` : `faltam ${Math.ceil(h.falta)}`}
                      </strong>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );

  // ─────────────────────────── Sub-aba "Painel" ───────────────────────────
  // Todos os cartões da Agenda antiga (agora em 3 grupos), concluídos no período
  // e a programação projetada. Lê /agenda/painel (estado de agora) e
  // /agenda/projecao (o futuro, só números por semana).
  const projAtual: ProjecaoDados | null = projecao[horizonte] || null;
  const cartoesProj = projAtual?.cards || {};
  const fmtBR = (n: number) => n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const repasse = agenda?.repasse || null;
  const repasseProj = cartoesProj.repasse || null;
  const contasAgora: any[] = agenda?.contas_a_pagar || [];
  const valorContas = resumoContasAgenda(contasAgora).saldo;
  // "A receber" (contrato F): lista separada de "Contas a pagar", mesmo formato; ausente = vazia.
  const contasReceber: any[] = agenda?.contas_a_receber || [];
  const valorReceber = resumoContasAgenda(contasReceber).saldo;
  const totalConcluidos = inducaoConcluidosPeriodo.length + realizadosGenericos.length;
  const pendencias = agenda?.pendencias || { n: 0, mais_antiga_dias: null };
  const linkConfigRepasse = "/parametros";

  const renderPainel = () => (
    <div id="ag2-painel-painel" role="tabpanel" aria-labelledby="ag2-tab-painel">
      <div className="ag2-painel-topo">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem 0.9rem" }}>
          <SeletorHorizonte valor={horizonte} onChange={setHorizonte} />
          <span className="ag2-mudo">Próximos {horizonte} dias a partir de hoje</span>
        </div>
        <button type="button" className="ag2-link" onClick={() => mudarVisao("dia")}>Voltar ao dia a dia</button>
      </div>

      {loading && !agenda ? (
        <p className="ag2-carregando" role="status">Buscando os números do painel…</p>
      ) : (
        <div ref={bstIndicadoresRef} style={{ scrollMarginTop: "1rem" }}>
          {gruposPainel.reproducao && (
          <GrupoPainel titulo="Reprodução" cor="var(--cat-reproducao)">
            <CartaoPainel titulo="Candidatas à próxima IATF" icon={HeartPulse} cor="var(--cat-reproducao)" valor={candidatas.length}
              detalhe={proxVisita ? <>próxima visita {proxVisita}</> : "vacas aptas a entrar em protocolo"}
              onClick={candidatas.length > 0 ? () => toggleLista("iatf") : undefined} aberto={listaAtiva.has("iatf")} />
            <CartaoPainel titulo="IATF em andamento" icon={HeartPulse} cor="var(--cat-reproducao)" valor={animaisIatfAtual.length}
              detalhe={gruposIatfAtivos.length > 0 ? `${gruposIatfAtivos.length} ${gruposIatfAtivos.length === 1 ? "protocolo" : "protocolos"} · etapas D0 a D11 em aberto` : "nenhum protocolo em andamento"}
              onClick={animaisIatfAtual.length > 0 ? () => toggleLista("iatfAtual") : undefined} aberto={listaAtiva.has("iatfAtual")} />
            <CartaoPainel titulo="Última IATF" icon={HeartPulse} cor="var(--cat-reproducao)"
              valor={grupoUltimaIatf ? grupoUltimaIatf.animais.length : "—"}
              detalhe={grupoUltimaIatf ? <>D0 {fmtCurtaAno(grupoUltimaIatf.data_d0)} · D11 {fmtCurtaAno(grupoUltimaIatf.data_d11)}</> : "nenhuma concluída ainda"}
              onClick={grupoUltimaIatf ? () => toggleLista("iatfUltima") : undefined} aberto={listaAtiva.has("iatfUltima")} />
            {repasse && (
              repasse.usar ? (
                <CartaoPainel titulo="Cio de repasse (adesivo)" icon={Repeat} cor="var(--cat-reproducao)" href={linkConfigRepasse}
                  valor={repasseProj ? repasseProj.checagens : repasse.checagens}
                  detalhe={<>
                    {(repasseProj ? repasseProj.checagens : repasse.checagens)} {(repasseProj ? repasseProj.checagens : repasse.checagens) === 1 ? "checagem" : "checagens"} × {repasseProj ? repasseProj.vacas : repasse.vacas} {(repasseProj ? repasseProj.vacas : repasse.vacas) === 1 ? "vaca" : "vacas"}
                    {(repasseProj?.proxima || repasse.proxima) ? <> · próxima {fmtCurta(repasseProj?.proxima || repasse.proxima)}</> : null}
                    {!repasse.mostrar_na_agenda ? " · sem aviso no Dia a dia" : ""}
                  </>}
                  titleAttr="Checagens de retorno ao cio previstas (serviços × vacas). Toque para configurar a regra em Protocolos." />
              ) : (
                <CartaoPainel titulo="Cio de repasse (adesivo)" icon={Repeat} cor="var(--cat-reproducao)" href={linkConfigRepasse}
                  valor="Desligado" desligado detalhe="Toque para configurar em Protocolos" />
              )
            )}
          </GrupoPainel>
          )}

          {gruposPainel.sanidade && (
          <GrupoPainel titulo="Sanidade" cor="var(--cat-sanidade)">
            <CartaoPainel titulo="BST · vacas aptas" icon={Syringe} cor="var(--cat-sanidade)" valor={bstAptos.length}
              detalhe={proxBST ? <>próxima aplicação {proxBST}</> : "sem aplicação prevista"}
              onClick={bstAptos.length > 0 ? () => toggleLista("bstAptos") : undefined} aberto={listaAtiva.has("bstAptos")} />
            <CartaoPainel titulo="BST · excluídas" icon={Syringe} cor="var(--cat-sanidade)" valor={bstExcl.length}
              detalhe="fora do ciclo agora (DEL ou marcação)"
              onClick={bstExcl.length > 0 ? () => toggleLista("bstExcl") : undefined} aberto={listaAtiva.has("bstExcl")} />
            <CartaoPainel titulo="Incluir no próximo BST" icon={Syringe} cor="var(--cat-sanidade)" valor={bstNuncaAplicados.length}
              detalhe="nunca receberam ou pedem reanálise"
              onClick={bstNuncaAplicados.length > 0 ? () => toggleLista("bstNunca") : undefined} aberto={listaAtiva.has("bstNunca")} />
            {/* Vacinas previstas · 30 d (Sanitário Preventivo v2): só números, com
                link para Sanidade › Preventiva › Painel. */}
            <CartaoVacinasPrevistas />
          </GrupoPainel>
          )}

          <GrupoPainel titulo={gruposPainel.estoque ? "Estoque e gestão" : "Gestão"} cor={gruposPainel.estoque ? "var(--cat-estoque)" : "var(--cat-gestao)"}>
            <CartaoPainel titulo="Pendências" icon={AlertTriangle} cor="var(--cat-financeiro)" valor={pendencias.n} alerta={pendencias.n > 0}
              detalhe={pendencias.n > 0 ? (pendencias.mais_antiga_dias != null ? `a mais antiga há ${pendencias.mais_antiga_dias} ${pendencias.mais_antiga_dias === 1 ? "dia" : "dias"}` : "atrasadas") : "nada atrasado"}
              onClick={pendencias.n > 0 ? () => { mudarVisao("dia"); setModoDia("lista"); setTimeout(() => rolarParaId("ag2-atrasadas"), 250); } : undefined} />
            {gruposPainel.estoque && (
            <CartaoPainel titulo="Alertas de estoque" icon={PackageSearch} cor="var(--cat-estoque)" valor={estoqueAlertasTotal} alerta={estoqueAlertasTotal > 0}
              detalhe={estoqueAlertasTotal > 0 ? `${estoqueNegativo.length} negativos · ${estoqueAbaixoMinimo.length} abaixo do mínimo` : "tudo dentro do mínimo"}
              onClick={estoqueAlertasTotal > 0 ? () => abrirAlertasEstoque() : undefined} aberto={paineis.has("estoqueAlertas")} />
            )}
            {gruposPainel.financeiro && (<>
            <CartaoPainel titulo="Contas a pagar" icon={Wallet} cor="var(--cat-financeiro)" valor={contasAgora.length}
              detalhe={contasAgora.length > 0 ? `${fmtBR(valorContas)} em ${DIAS_PADRAO_FUTURO} dias` : `nada a vencer em ${DIAS_PADRAO_FUTURO} dias`} href={contasAgora.length > 0 ? "/financeiro" : undefined} />
            <CartaoPainel titulo="A receber" icon={Wallet} cor="var(--cat-financeiro)" valor={contasReceber.length}
              detalhe={contasReceber.length > 0 ? `${fmtBR(valorReceber)} em ${DIAS_PADRAO_FUTURO} dias` : `nada a receber em ${DIAS_PADRAO_FUTURO} dias`} href={contasReceber.length > 0 ? "/financeiro" : undefined} />
            </>)}
            <CartaoPainel titulo="Concluídos no período" icon={CheckCircle2} cor="var(--cat-gestao)" valor={totalConcluidos}
              detalhe={<>{fmtCurta(concDe)} a {fmtCurta(concAte)}</>}
              onClick={() => { setConcluidosAberto(true); setTimeout(() => rolarAteSecao("concluidos"), 50); }} aberto={concluidosAberto} />
          </GrupoPainel>
        </div>
      )}

      {gruposPainel.sanidade && <NotasSanitario />}

      <ProjecaoAgenda dados={projAtual} carregando={projecaoCarregando} erro={projecaoErro} horizonte={horizonte} onTentar={() => carregarProjecao(horizonte)} />

      {/* Listas expansíveis — abrem/fecham a partir do clique nos quadros acima */}
      {(candidatas.length > 0 || animaisIatfAtual.length > 0 || (grupoUltimaIatf?.animais?.length ?? 0) > 0 ||
        bstAptos.length > 0 || bstExcl.length > 0 || bstNuncaAplicados.length > 0) && (
        <div className="mb-4">
          {listaAtiva.has("iatf") && (
            <div className="card mb-2" style={{ overflowX: "auto" }}>
              <table className="fazenda-table">
                <thead><tr>
                  <ThOrdenavel label="Nº Animal" campo="numero_matriz" coluna={ordIatf.coluna} dir={ordIatf.dir} ordenar={ordIatf.ordenar} />
                  <ThOrdenavel label="Estado" campo="estado_rotulo" coluna={ordIatf.coluna} dir={ordIatf.dir} ordenar={ordIatf.ordenar} />
                  <ThOrdenavel label="DEL" campo="del_dias" coluna={ordIatf.coluna} dir={ordIatf.dir} ordenar={ordIatf.ordenar} />
                  <ThOrdenavel label="Motivo" campo="motivo" coluna={ordIatf.coluna} dir={ordIatf.dir} ordenar={ordIatf.ordenar} />
                  <th></th>
                </tr></thead>
                <tbody>
                  {ordIatf.linhasOrdenadas.map((c: any, i: number) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>{c.numero_matriz}</td>
                      {/* Estado recalculado dos registros, não o `sit_rep` do
                          CSV: era ele que fazia a tela escrever "Gestante" ao
                          lado de uma candidata a protocolo. */}
                      <td><span className="badge-reprodutivo" style={{ padding: "0.1rem 0.4rem", borderRadius: "var(--r-sm)", fontSize: "0.75rem" }}>{c.estado_rotulo || c.sit_rep}</span></td>
                      <td>{c.del_dias ?? "—"}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{c.motivo}</td>
                      <td><BotaoAgendar numero={c.numero_matriz} descricao="IATF: candidata a novo serviço" categoria="Reprodutivo" /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {listaAtiva.has("iatfAtual") && (
            <div className="card mb-2" style={{ overflowX: "auto" }}>
              <table className="fazenda-table">
                <thead><tr><th>Nº Animal</th><th>Protocolo</th><th>D0</th><th>Próxima etapa</th><th>Data da próxima etapa</th></tr></thead>
                <tbody>
                  {animaisIatfAtual.map((a: any, i: number) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>{a.numero_matriz}</td>
                      <td style={{ fontSize: "0.78rem" }}>{a.nome_protocolo}</td>
                      <td style={{ fontSize: "0.78rem" }}>{fmtCurta(a.data_d0)}</td>
                      <td><span className="badge-reprodutivo" style={{ padding: "0.1rem 0.4rem", borderRadius: "var(--r-sm)", fontSize: "0.75rem" }}>{a.etapa_atual}</span></td>
                      <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{a.data_etapa_atual ? fmtCurta(a.data_etapa_atual) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {listaAtiva.has("iatfUltima") && grupoUltimaIatf && (
            <div className="card mb-2" style={{ overflowX: "auto" }}>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
                {grupoUltimaIatf.nome_protocolo} — D0 {fmtCurtaAno(grupoUltimaIatf.data_d0)} · D11 {fmtCurtaAno(grupoUltimaIatf.data_d11)}
                {grupoUltimaIatf.proxima_visita && <> · próxima visita {fmtCurtaAno(grupoUltimaIatf.proxima_visita)}</>}
              </p>
              <table className="fazenda-table">
                <thead><tr><th>Nº Animal</th></tr></thead>
                <tbody>
                  {grupoUltimaIatf.animais.map((a: any) => (
                    <tr key={a.numero_matriz}><td style={{ fontWeight: 700 }}>{a.numero_matriz}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {(listaAtiva.has("bstAptos") || listaAtiva.has("bstExcl") || listaAtiva.has("bstNunca")) && (
            <div className="mb-2">
              {/* As 3 listas (aptas/inaptas/incluir no próximo) viram um painel só,
                  com seleção — pode aplicar em umas e deixar de aplicar em outras
                  na mesma tela, sem sair da Agenda. */}
              <PainelLancarBst agenda={agenda} onAtualizado={carregar} />
            </div>
          )}

        </div>
      )}

      <div ref={concluidosRef} style={{ scrollMarginTop: "1rem" }}>
      {/* "Concluídos no período" (C7-C10) — card genérico no lugar do antigo
          card fixo só de indução de lactação: cobre etapas e atividades de
          qualquer tipo, com filtro de/até (padrão últimos 7 dias). Pequeno e
          recolhível por padrão (SecaoRecolhivel) para não competir com os
          indicadores em destaque acima. */}
      <SecaoRecolhivel
        aberta={concluidosAberto} onAlternar={() => setConcluidosAberto((a) => !a)}
        titulo="Concluídos no período"
        icon={CheckCircle2}
        descricao="Etapas e atividades marcadas como concluídas no período selecionado — inclui desfazer, se marcado por engano"
        badge={<span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{inducaoConcluidosPeriodo.length + realizadosGenericos.length} no período</span>}
      >
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
          <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>De</label>
            <input type="date" value={concDe} onChange={e => setConcDe(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem", color: "var(--text)", fontSize: "0.78rem" }} /></div>
          <div><label style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>Até</label>
            <input type="date" value={concAte} onChange={e => setConcAte(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem", color: "var(--text)", fontSize: "0.78rem" }} /></div>
        </div>
        {carregandoRealizados ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Carregando…</p>
        ) : (inducaoConcluidosPeriodo.length + realizadosGenericos.length) === 0 ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>Nenhuma etapa ou atividade concluída neste período.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><th>Concluído em</th><th>Tipo</th><th>Detalhe</th><th></th></tr></thead>
              <tbody>
                {inducaoConcluidosPeriodo.map((g: any) => (
                  <tr key={`ind_${g.id}`}>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{g.data_realizacao ? new Date(g.data_realizacao + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                    <td style={{ fontSize: "0.8rem" }}>Indução de lactação</td>
                    <td style={{ fontSize: "0.78rem" }}>{g.nome_protocolo} — D{g.dia} — {g.animais.join(", ")}</td>
                    <td>
                      <button className="btn-ghost" style={{ fontSize: "0.7rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} disabled={desfazendo.has(g.id)} onClick={() => desfazerIatf(g.id)}>
                        <RotateCcw size={12} /> Desfazer
                      </button>
                    </td>
                  </tr>
                ))}
                {realizadosGenericos.map((r) => (
                  <tr key={`gen_${r.evento_id}`}>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{new Date(r.marcado_em.slice(0, 10) + "T00:00:00").toLocaleDateString("pt-BR")}</td>
                    <td style={{ fontSize: "0.8rem" }}>{r.rotulo || "Evento"}</td>
                    {/* Sem rótulo conhecido para o prefixo: EventoRealizado só guarda
                        um hash (evento_id), não o texto original da pendência — em
                        vez de inventar uma descrição, mostra o id cru, honesto sobre
                        o que dá para nomear (ver _rotulo_evento_realizado no backend). */}
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: r.rotulo ? undefined : "monospace" }}>{r.rotulo ? "—" : r.evento_id}</td>
                    <td>
                      <button className="btn-ghost" style={{ fontSize: "0.7rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} disabled={desfazendo.has(r.evento_id)} onClick={() => desfazerIatf(r.evento_id)}>
                        <RotateCcw size={12} /> Desfazer
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SecaoRecolhivel>

      </div>
      {renderComunicados(comunicados)}

      <div ref={estoqueAlertasRef} style={{ scrollMarginTop: "1rem" }} />
      {(estoqueNegativo.length > 0 || estoqueAbaixoMinimo.length > 0) && (
        <div className="card mt-4" style={{ border: "1px solid var(--red)" }} id="ag2-estoque-alertas">
          <button onClick={() => togglePainel("estoqueAlertas")} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.5rem", background: "none", border: "none", color: "var(--red)", cursor: "pointer", textAlign: "left", padding: 0 }}>
            {paineis.has("estoqueAlertas") ? <ChevronDown size={15} style={{ color: "var(--text-muted)" }} /> : <ChevronRight size={15} style={{ color: "var(--text-muted)" }} />}
            <span className="card-header" style={{ margin: 0, color: "var(--red)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <AlertTriangle size={15} /> Estoque — alertas ({estoqueNegativo.length + estoqueAbaixoMinimo.length})
            </span>
          </button>
          {paineis.has("estoqueAlertas") && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
              {estoqueNegativo.map((i) => (
                <div key={`neg_${i.nome}`} style={{ padding: "0.85rem", borderRadius: "var(--r-sm)", background: "color-mix(in srgb, var(--vinho) 25%, transparent)", border: "1px solid var(--red)" }}>
                  <p style={{ fontWeight: 700, fontSize: "0.85rem" }}>{i.nome}</p>
                  <p style={{ fontSize: "0.85rem", color: "var(--red)", fontWeight: 700, marginTop: "0.2rem" }}>{i.quantidade} {i.unidade || ""}</p>
                  <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.1rem" }}>saldo negativo</p>
                </div>
              ))}
              {estoqueAbaixoMinimo.map((i) => (
                <div key={`min_${i.nome}`} style={{ padding: "0.85rem", borderRadius: "var(--r-sm)", background: "color-mix(in srgb, var(--dourado) 20%, transparent)", border: "1px solid var(--amber)" }}>
                  <p style={{ fontWeight: 700, fontSize: "0.85rem" }}>{i.nome}</p>
                  <p style={{ fontSize: "0.85rem", fontWeight: 700, marginTop: "0.2rem" }}>{i.quantidade} de {i.estoque_minimo} {i.unidade || ""}</p>
                  <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.1rem" }}>abaixo do mínimo</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div className="p-6 animate-in ag2">
      <div className="ag2-topo">
        <div className="ag2-topo-esq">
          <h1><Calendar size={22} style={{ color: "var(--dourado)" }} aria-hidden="true" /> Agenda</h1>
          <SubAbasAgenda ativa={visao} onChange={mudarVisao}
            atrasadas={agenda?.resumo?.atrasadas ?? agenda?.pendencias?.n ?? eventosPendentes.length}
            alertasPainel={estoqueAlertasTotal || agenda?.resumo?.alertas_estoque || 0} />
        </div>
        <div className="ag2-topo-dir">
          {horaAtualizado && <span className="ag2-atualizado">Atualizado {horaAtualizado}</span>}
          <button onClick={carregar} className="btn-ghost ag2-icone-btn" title="Atualizar" aria-label="Atualizar a agenda">
            <RefreshCw size={16} className={atualizando ? "animate-spin" : ""} />
          </button>
          <button onClick={() => setShowModal(true)} className="btn-primary" title="Criar uma tarefa manual — livre, por lote ou para vários animais">
            <Plus size={16} aria-hidden="true" /> Nova tarefa
          </button>
        </div>
      </div>

      {pagandoConta && (
        <PagarContaModal conta={pagandoConta} onClose={() => setPagandoConta(null)}
          onPago={() => { setPagandoConta(null); mostrarFeedback("Pagamento registrado."); carregar(); }} />
      )}
      {/* Erro de carregamento — distinto do estado "sem dados"; a lista que já está na tela fica. */}
      {erro && (
        <div className="alert-critico mb-4" role="alert">
          <AlertTriangle size={18} aria-hidden="true" /><span>Não foi possível atualizar a agenda: {erro}</span>
          <button type="button" className="btn-ghost" onClick={carregar} style={{ marginLeft: "auto" }}>Tentar de novo</button>
        </div>
      )}

      {/* Feedback transitório de ações (sucesso em verde, erro em vermelho) */}
      {feedback && (
        <div className="ag2-aviso-topo" role="status" style={{
          background: feedback.erro ? "rgba(192,57,43,0.15)" : "rgba(20,83,45,0.35)",
          border: "1px solid " + (feedback.erro ? "var(--red)" : "var(--green-light)"),
          color: feedback.erro ? "var(--alert-fg)" : "var(--green-light)" }}>
          {feedback.erro ? <AlertTriangle size={15} aria-hidden="true" /> : <CheckCircle2 size={15} aria-hidden="true" />} {feedback.msg}
        </div>
      )}

      {visao === "painel" ? renderPainel() : renderDiaADia()}

      {definindoVisita && (
        <DefinirDataVisitaModal dataAtual={definindoVisita.data} origem={definindoVisita.origem} intervalo={definindoVisita.intervalo} ultimaVisita={definindoVisita.ultima}
          onClose={() => setDefinindoVisita(null)} onSalvo={() => { carregar(); }} />
      )}

      {/* Modal sugestão de movimentação entre lotes */}
      {sugestaoMovAberta && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50, padding: "1rem" }}>
          <div className="card" style={{ width: "480px", maxWidth: "95vw" }}>
            <div className="card-header mb-3 flex items-center gap-2"><Layers size={16} style={{ color: "var(--dourado)" }} /> Sugestão de movimentação de lote</div>
            <p style={{ fontSize: "0.85rem", marginBottom: "0.25rem" }}>
              Matriz <strong>{sugestaoMovAberta.numero_animal}</strong> — lote atual: {sugestaoMovAberta.lote || "—"}
            </p>
            {sugestaoMovAberta.motivo && (
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.9rem" }}>Motivo: {sugestaoMovAberta.motivo}</p>
            )}
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>
              Aceitar sugestão / mudar para outro lote:
            </label>
            <select
              value={destinoMov} onChange={(e) => setDestinoMov(e.target.value)}
              style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem", marginBottom: "1rem" }}
            >
              {sugestaoMovAberta.lotes_sugeridos?.map((l: any) => (
                <option key={l.codigo} value={l.codigo}>{l.rotulo} (sugerido)</option>
              ))}
              {lotesTodosMov
                .filter((l: any) => !sugestaoMovAberta.lotes_sugeridos?.some((s: any) => s.codigo === l.codigo))
                .map((l: any) => <option key={l.codigo} value={l.codigo}>{l.rotulo}</option>)}
            </select>
            <div className="flex items-center gap-2">
              <button className="btn-primary" style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.35rem" }} disabled={salvandoSugestaoMov || !destinoMov} onClick={aceitarSugestaoMov}>
                <Check size={14} /> {salvandoSugestaoMov ? "Movendo…" : "Confirmar movimentação"}
              </button>
              <button className="btn-ghost" style={{ fontSize: "0.8rem", color: "var(--red)", display: "flex", alignItems: "center", gap: "0.35rem" }} disabled={salvandoSugestaoMov} onClick={cancelarSugestaoMov}>
                <X size={14} /> Cancelar sugestão
              </button>
              <button className="btn-ghost" style={{ fontSize: "0.8rem", marginLeft: "auto" }} onClick={fecharSugestaoMov}>Fechar</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal adicionar evento */}
      {showModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50, padding: "1rem" }}>
          <div className="card" style={{ width: "520px", maxWidth: "95vw", maxHeight: "90vh", overflowY: "auto" }}>
            <div className="card-header mb-4">Adicionar Evento Manual</div>
            <div className="space-y-3">
              {[
                { label: "Data", key: "data_evento", type: "date" },
                { label: "Descrição", key: "descricao", type: "text" },
              ].map(f => (
                <div key={f.key}>
                  <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>{f.label}</label>
                  <input
                    type={f.type}
                    value={(form as any)[f.key]}
                    onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
                    style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                  />
                </div>
              ))}

              {podeVincular && (
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Vincular a (opcional)</label>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  {[
                    { v: "nenhum", label: "Nenhum (tarefa livre)" },
                    { v: "animal", label: "Animal(is)" },
                    { v: "lote", label: "Lote(s)" },
                  ].map((o) => (
                    <button key={o.v} type="button" title={o.label}
                      onClick={() => { setVinculo(o.v as any); if (o.v === "nenhum") { setAnimaisSelecionados(new Set()); setLotesSelecionados(new Set()); } }}
                      style={{ fontSize: "0.75rem", padding: "0.3rem 0.7rem", borderRadius: "999px", cursor: "pointer",
                        border: "1px solid " + (vinculo === o.v ? "var(--dourado)" : "var(--border)"),
                        background: vinculo === o.v ? "var(--dourado)" : "transparent",
                        color: vinculo === o.v ? "#1a1a1a" : "var(--text-muted)", fontWeight: vinculo === o.v ? 700 : 400 }}>
                      {o.label}
                    </button>
                  ))}
                </div>
                {vinculo === "animal" && (
                  <div className="mt-2">
                    <AnimalPickerModal animais={animaisTodos} selecionados={animaisSelecionados} onToggle={toggleAnimalSelecionado} colunas={pickerColunasAnimais} titulo="Selecionar animal(is)" />
                  </div>
                )}
                {vinculo === "lote" && (
                  <div className="mt-2">
                    <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={abrirPickerLotes}>
                      {lotesSelecionados.size ? `${lotesSelecionados.size} lote(s) selecionado(s) — alterar` : "Selecionar lotes…"}
                    </button>
                  </div>
                )}
              </div>
              )}

              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Categoria</label>
                <select
                  value={form.categoria}
                  onChange={e => setForm(p => ({ ...p, categoria: e.target.value }))}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                >
                  {categoriasVisiveis.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>

              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Tipo de evento (opcional)</label>
                <select
                  value={form.tipo_evento}
                  onChange={e => setForm(p => ({ ...p, tipo_evento: e.target.value }))}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                >
                  <option value="">—</option>
                  {TIPOS_EVENTO.map(t => <option key={t}>{t}</option>)}
                </select>
              </div>

              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Observação (opcional)</label>
                <input
                  type="text" value={form.observacao}
                  onChange={e => setForm(p => ({ ...p, observacao: e.target.value }))}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                />
              </div>

              <div>
                <label className="flex items-center gap-2" style={{ fontSize: "0.82rem" }}>
                  <input type="checkbox" checked={form.recorrente} onChange={e => setForm(p => ({ ...p, recorrente: e.target.checked }))} /> Repetir este evento
                </label>
                {form.recorrente && (
                  <div className="flex items-center gap-2 mt-2">
                    <span style={{ fontSize: "0.8rem" }}>A cada</span>
                    <input type="number" min={1} value={form.recorrenciaNumero}
                      onChange={e => setForm(p => ({ ...p, recorrenciaNumero: e.target.value }))}
                      style={{ width: "5rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.5rem", color: "var(--text)", fontSize: "0.875rem" }} />
                    <select value={form.recorrenciaFrequencia}
                      onChange={e => setForm(p => ({ ...p, recorrenciaFrequencia: e.target.value as "dias" | "meses" }))}
                      style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}>
                      <option value="dias">dias</option>
                      <option value="meses">meses</option>
                    </select>
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={fecharModalNovoEvento} className="btn-ghost">Cancelar</button>
              <button onClick={handleAddEvento} className="btn-primary" disabled={!form.descricao || (form.recorrente && !form.recorrenciaNumero)}>Salvar</button>
            </div>
          </div>
        </div>
      )}

      {/* Picker de lotes para o vínculo do evento manual (animal usa AnimalPickerModal inline acima) */}
      {pickerAberto === "lote" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 55, padding: "1rem" }}>
          <div className="card" style={{ width: "640px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="card-header mb-3">Selecionar lote(s)</div>
            <SelecaoLotesTabela lotes={lotesTodos} selecionados={lotesSelecionados} toggle={toggleLoteSelecionado} toggleTodos={toggleTodosLotes} />
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setPickerAberto(null)} className="btn-primary">OK</button>
            </div>
          </div>
        </div>
      )}

      {/* Gaveta lateral (T2, mockup 1e) — Inseminação aberta direto de uma
          linha da Agenda (ver abrirGavetaInseminacao acima), sem navegar pra
          /lancamentos. */}
      <GavetaLancamento
        aberto={gavetaAgenda != null}
        onFechar={fecharGavetaAgenda}
        titulo="Inseminação"
        icone={Heart}
        mensagemSalva={mensagemSalvaGavetaAgenda}
        onSalvarProximo={salvarEProximoGavetaAgenda}
        onConcluir={concluirGavetaAgenda}
      >
        {gavetaAgenda?.tipo === "inseminacao" && (
          <FormInseminacao
            key={formKeyGavetaAgenda}
            animais={animaisGaveta}
            prefill={gavetaAgenda.prefill}
            onSalvo={aoSalvarGavetaAgenda}
          />
        )}
      </GavetaLancamento>
    </div>
  );
}
