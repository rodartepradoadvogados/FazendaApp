"use client";

import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { Calendar, Filter, Plus, RefreshCw, ChevronDown, ChevronRight, ChevronLeft, AlertTriangle, CheckCircle2, Check, X, Syringe, Wheat, Wallet, RotateCcw, ExternalLink, Megaphone, User, FileSpreadsheet, FileText, PackageSearch, Layers } from "lucide-react";
import {
  fetchAgenda, addEventoManual, marcarEventoRealizado, desmarcarEventoRealizado,
  fetchProtocoloInducaoConcluidos, fetchAnimais, fetchLotes, today, fetchPrincipiosAtivos, fetchEventosSanitarios,
  cadastrarPreventivo, marcarCuraAplicacao, marcarCuraProtocolo, fetchProtocolosIatfAtivos,
  criarMovimentacao, fetchMotivosMovimentacao, fetchPessoas, criarPessoa, salvarDiasDiaria, atualizarServico,
  authFetch, API, mensagemErroApi,
} from "@/lib/api";
import { exportarExcel, exportarPDF } from "@/lib/export";
import { VIAS_APLICACAO } from "@/lib/constants";

// Unidades aceitas na aplicação (mesma lista usada em Sanidade/Cadastro).
const UNIDADES_APLICACAO = ["ml", "kg", "L", "unidade", "dose", "saca 30kg", "saca 60kg"];
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { SelecaoLotesTabela, LoteRow } from "@/components/SelecaoLotesTabela";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { Indicador, SecaoRecolhivel } from "@/components/ui";
import { PainelLancarBst } from "@/components/PainelLancarBst";
import { casaBusca } from "@/lib/busca";

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
  "Produção":          "var(--blue)",
  "Gestão/Financeiro": "var(--cat-financeiro)",
  "Atividades":        "var(--text-muted)",
};
const COR_CATEGORIA_LC: Record<string, string> = Object.fromEntries(Object.entries(COR_CATEGORIA).map(([k, v]) => [k.toLowerCase(), v]));
function corCategoria(categoria: string): string {
  return COR_CATEGORIA_LC[(categoria || "").toLowerCase()] || "var(--text-muted)";
}
const LEGENDA_CATEGORIAS = ["Reprodutivo", "Sanidade", "Produção", "Gestão/Financeiro"];

export default function AgendaPage() {
  const router = useRouter();
  const [data, setData] = useState(today());
  const [agenda, setAgenda] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
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
  const [calendarioAberto, setCalendarioAberto] = useState(false);
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
  useEffect(() => { if (vinculo === "animal" && !animaisTodos.length) fetchAnimais().then(setAnimaisTodos).catch(() => {}); }, [vinculo, animaisTodos.length]);
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
  const [datasAbertas, setDatasAbertas] = useState<Set<string>>(new Set());
  const toggleData = (d: string) => setDatasAbertas(p => { const n = new Set(p); n.has(d) ? n.delete(d) : n.add(d); return n; });
  // Painéis recolhíveis (candidatas IATF, BST aptos, BST excluídos) — começam recolhidos.
  const [paineis, setPaineis] = useState<Set<string>>(new Set());
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
  // Cronograma sanitário (ver fazenda/rules/cronograma_sanitario.py) — 3 cards
  // novos na Agenda: (1) animal que entrou na janela — incluir/excluir direto,
  // sem expandir; (2) decisão de modo (veterinário/própria/adiar) — mesmo id
  // de evento seja "modo" (normal) ou "urgente" (perto da data, sem decisão);
  // (3) aplicar — mesmo padrão checklist do protocolo customizado acima.
  const [pessoasCronograma, setPessoasCronograma] = useState<any[]>([]);
  useEffect(() => { fetchPessoas().then(setPessoasCronograma).catch(() => setPessoasCronograma([])); }, []);
  const veterinariosCronograma = useMemo(
    () => pessoasCronograma.filter((p) => p.ativo !== false && (p.tipos || []).includes("Veterinário")).sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    [pessoasCronograma]
  );
  const [cronogramaModoAbertos, setCronogramaModoAbertos] = useState<Set<string>>(new Set());
  const toggleCronogramaModo = (id: string) => setCronogramaModoAbertos(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  // "" = ainda escolhendo entre veterinário/própria/adiar; "veterinario"/"adiar" = sub-formulário aberto.
  const [cronogramaAcao, setCronogramaAcao] = useState<Record<string, "" | "veterinario" | "adiar">>({});
  const [cronogramaVetSel, setCronogramaVetSel] = useState<Record<string, string>>({});
  const [cronogramaNovoVet, setCronogramaNovoVet] = useState<Record<string, boolean>>({});
  const [cronogramaNovoVetNome, setCronogramaNovoVetNome] = useState<Record<string, string>>({});
  const [cronogramaCriandoVet, setCronogramaCriandoVet] = useState<Set<string>>(new Set());
  const [cronogramaAdiarData, setCronogramaAdiarData] = useState<Record<string, string>>({});
  const [cronogramaAdiarMotivo, setCronogramaAdiarMotivo] = useState<Record<string, string>>({});

  const [cronogramaAplicarAbertos, setCronogramaAplicarAbertos] = useState<Set<string>>(new Set());
  const toggleCronogramaAplicar = (id: string) => setCronogramaAplicarAbertos(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const [cronogramaAplicarChecks, setCronogramaAplicarChecks] = useState<Record<string, Set<string>>>({});
  const abrirCronogramaAplicar = (id: string, animais: string[]) => {
    setCronogramaAplicarChecks((p) => (p[id] ? p : { ...p, [id]: new Set(animais) }));
    toggleCronogramaAplicar(id);
  };
  const toggleAnimalCronogramaAplicar = (id: string, numero: string) => setCronogramaAplicarChecks((p) => {
    const atual = new Set(p[id] || []);
    atual.has(numero) ? atual.delete(numero) : atual.add(numero);
    return { ...p, [id]: atual };
  });

  const decidirCronogramaAnimal = async (e: any, incluir: boolean) => {
    setMarcando((p) => new Set(p).add(e.id));
    try {
      await marcarEventoRealizado(e.id, undefined, undefined, { incluir });
      await carregar();
      mostrarFeedback(incluir ? `Matriz ${e.numero_animal} incluída no cronograma.` : `Matriz ${e.numero_animal} excluída do cronograma.`);
    } catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

  const decidirCronogramaModo = async (e: any, modo: "veterinario" | "propria") => {
    if (modo === "veterinario" && !cronogramaVetSel[e.id]) { mostrarFeedback("Selecione o veterinário.", true); return; }
    setMarcando((p) => new Set(p).add(e.id));
    try {
      await marcarEventoRealizado(e.id, undefined, undefined, {
        modo, veterinario_pessoa_id: modo === "veterinario" ? Number(cronogramaVetSel[e.id]) : undefined,
      });
      setCronogramaAcao((p) => ({ ...p, [e.id]: "" }));
      await carregar();
      mostrarFeedback("Cronograma agendado.");
    } catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

  const adiarCronograma = async (e: any) => {
    const novaData = cronogramaAdiarData[e.id];
    if (!novaData) { mostrarFeedback("Informe a nova data.", true); return; }
    setMarcando((p) => new Set(p).add(e.id));
    try {
      await marcarEventoRealizado(e.id, undefined, undefined, { nova_data: novaData, motivo: cronogramaAdiarMotivo[e.id] || undefined });
      setCronogramaAcao((p) => ({ ...p, [e.id]: "" }));
      await carregar();
      mostrarFeedback("Data adiada.");
    } catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

  const criarVetInlineCronograma = async (e: any) => {
    const nome = (cronogramaNovoVetNome[e.id] || "").trim();
    if (!nome) return;
    setCronogramaCriandoVet((p) => new Set(p).add(e.id));
    try {
      const novo = await criarPessoa({ nome, tipos: ["Veterinário"] });
      setPessoasCronograma((p) => [...p, novo]);
      setCronogramaVetSel((p) => ({ ...p, [e.id]: String(novo.id) }));
      setCronogramaNovoVet((p) => ({ ...p, [e.id]: false }));
      setCronogramaNovoVetNome((p) => ({ ...p, [e.id]: "" }));
    } catch (err: any) { mostrarFeedback(err.message || "Erro ao cadastrar veterinário", true); }
    finally { setCronogramaCriandoVet((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

  const aplicarCronogramaLote = async (e: any) => {
    setMarcando((p) => new Set(p).add(e.id));
    try {
      await marcarEventoRealizado(e.id);
      await carregar();
      mostrarFeedback("Aplicação registrada para todos os animais incluídos.");
    } catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

  const aplicarCronogramaIndividual = async (e: any) => {
    const checks = cronogramaAplicarChecks[e.id] || new Set(e.animais);
    setMarcando((p) => new Set(p).add(e.id));
    try {
      await marcarEventoRealizado(e.id, Array.from(checks));
      await carregar();
      mostrarFeedback(`Aplicação registrada em ${checks.size} animal(is).`);
    } catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setMarcando((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
  };

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

  // Janela de contas a pagar/receber que o backend calcula: 10 dias por padrão,
  // ou até a data "Até" escolhida (se o usuário ampliar o período). Na visão
  // de calendário, amplia também até o fim do mês exibido (senão eventos
  // financeiros de um mês futuro não chegariam a tempo de aparecer nele).
  const ultimoDiaDoMesCalendario = new Date(mesCalendario.ano, mesCalendario.mes + 1, 0).getDate();
  const ultimoDiaMesCalendarioIso = isoLocal(mesCalendario.ano, mesCalendario.mes, ultimoDiaDoMesCalendario);
  const diasParaCalendario = calendarioAberto ? Math.max(0, diasEntre(data, ultimoDiaMesCalendarioIso)) : 0;
  const diasJanela = Math.max(
    ate ? Math.max(DIAS_PADRAO_FUTURO, diasEntre(data, ate)) : DIAS_PADRAO_FUTURO,
    diasParaCalendario,
  );

  const carregar = useCallback(async () => {
    setLoading(true);
    try { setAgenda(await fetchAgenda(data, diasJanela)); setErro(null); }
    catch (e: any) { setAgenda(null); setErro(e?.message || "erro desconhecido"); }
    finally { setLoading(false); }
  }, [data, diasJanela]);

  useEffect(() => { carregar(); }, [carregar]);

  // Protocolos IATF ativos/concluídos (D0..D11) — alimenta os quadros "IATF
  // atual" (etapas ainda em aberto) e "Última IATF" (grupo mais recente já
  // concluído, com data de D0/D11 e os animais que entraram nele).
  const [iatfAtivos, setIatfAtivos] = useState<any[]>([]);
  const carregarIatfAtivos = useCallback(async () => {
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
    () => (agenda?.eventos || []).filter((e: any) => e.comunicado),
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
  const eventosPendentes = useMemo(
    () => eventosBase.filter((e: any) => e.data < hoje),
    [eventosBase, hoje],
  );
  // Localiza um evento pelo id independente da seção (pendentes/futuros) em
  // que ele está renderizado — usado pela confirmação em lote por dia.
  const eventoPorId = useMemo(
    () => new Map<string, any>((agenda?.eventos || []).map((e: any) => [e.id, e])),
    [agenda],
  );

  // ── Dar baixa em sanidade (evento_sanitario / calendario_sanitario) sem sair
  // da Agenda — individual (1º clique confirma os dados, 2º confirma a baixa)
  // ou em lote (várias pendências da MESMA categoria de uma vez, cada uma com
  // seus próprios dados, pré-preenchidos do cadastro/lançamento e editáveis).
  type CampoBaixaSanidade = {
    produto: string; dose: string; unidade: string; via: string;
    principioAtivoId: string; veterinario: string; freqValor: string; freqUnidade: string;
  };
  const CAMPOS_VAZIOS: CampoBaixaSanidade = { produto: "", dose: "", unidade: "", via: "", principioAtivoId: "", veterinario: "", freqValor: "1", freqUnidade: "meses" };
  const [principiosAtivos, setPrincipiosAtivos] = useState<{ id: number; nome: string }[]>([]);
  const [eventosSanitarios, setEventosSanitarios] = useState<any[]>([]);
  useEffect(() => {
    fetchPrincipiosAtivos().then((d: any[]) => setPrincipiosAtivos(d.filter((p) => p.ativo !== false))).catch(() => {});
    fetchEventosSanitarios().then(setEventosSanitarios).catch(() => {});
  }, []);
  function ehExameSanitario(e: any): boolean {
    if (e.categoria_preventiva != null) return e.categoria_preventiva === "exame";
    return eventosSanitarios.find((x: any) => x.id === e.evento_sanitario_id)?.categoria_preventiva === "exame";
  }
  function nomeEventoSanitario(e: any): string {
    return eventosSanitarios.find((x: any) => x.id === e.evento_sanitario_id)?.nome || (e.descricao || "").split(" — ")[0];
  }
  function elegivelBaixaInline(e: any): boolean {
    // Só quando a pendência já mira uma matriz específica — sem isso não há
    // como resolver sem escolher os animais (aí vale mais abrir o lançamento).
    return (e.tipo === "evento_sanitario" || e.tipo === "calendario_sanitario") && !!e.numero_animal;
  }
  // Agrupamento do "dar baixa em lote": categoria/lote-alvo (categoria_alvo) +
  // evento sanitário, para que só entrem no mesmo grupo pendências que fazem
  // sentido receber os MESMOS dados (mesmo medicamento/dose/via) de uma vez.
  function grupoLoteChave(e: any): string {
    return `${e.categoria_alvo || "—"}::${e.evento_sanitario_id ?? ""}`;
  }
  function grupoLoteRotulo(e: any): string {
    return e.categoria_alvo || "Sem lote/categoria definido";
  }
  const camposIniciais = (e: any): CampoBaixaSanidade => ({
    produto: e.produto || "", dose: e.dose != null ? String(e.dose) : "", unidade: e.unidade || "",
    via: e.via || "", principioAtivoId: e.principio_ativo_id ? String(e.principio_ativo_id) : "",
    veterinario: e.veterinario || "", freqValor: "1", freqUnidade: "meses",
  });
  const [camposBaixa, setCamposBaixa] = useState<Record<string, CampoBaixaSanidade>>({});
  const abrirCampos = (e: any) => setCamposBaixa((p) => (p[e.id] ? p : { ...p, [e.id]: camposIniciais(e) }));
  const atualizarCampo = (id: string, campo: keyof CampoBaixaSanidade, valor: string) =>
    setCamposBaixa((p) => ({ ...p, [id]: { ...(p[id] || CAMPOS_VAZIOS), [campo]: valor } }));

  const [expandidoBaixa, setExpandidoBaixa] = useState<Set<string>>(new Set());
  const [abrirLancamento, setAbrirLancamento] = useState<Record<string, boolean>>({});
  const [resolvendoBaixa, setResolvendoBaixa] = useState<Set<string>>(new Set());

  const [loteDia, setLoteDia] = useState<Record<string, boolean>>({});
  const [categoriaLoteDia, setCategoriaLoteDia] = useState<Record<string, string>>({});
  const [selecionadosLote, setSelecionadosLote] = useState<Record<string, Set<string>>>({});
  const [resolvendoLoteDia, setResolvendoLoteDia] = useState<Set<string>>(new Set());
  const toggleLoteDia = (dia: string) => setLoteDia((p) => {
    const ligado = !p[dia];
    if (!ligado) {
      setSelecionadosLote((s) => { const n = { ...s }; delete n[dia]; return n; });
      setCategoriaLoteDia((c) => { const n = { ...c }; delete n[dia]; return n; });
    }
    return { ...p, [dia]: ligado };
  });
  const toggleSelecaoLote = (dia: string, e: any) => {
    setSelecionadosLote((p) => {
      const atual = new Set(p[dia] || []);
      if (atual.has(e.id)) atual.delete(e.id); else { atual.add(e.id); abrirCampos(e); }
      return { ...p, [dia]: atual };
    });
    setCategoriaLoteDia((p) => (p[dia] ? p : { ...p, [dia]: grupoLoteChave(e) }));
  };
  // "Selecionar todos" de um grupo (mesma categoria/lote-alvo + evento): troca
  // a seleção do dia inteiro para esse grupo e abre a linha única compartilhada
  // (ver camposBaixa[chaveCamposGrupo(dia)]).
  const chaveCamposGrupo = (dia: string) => `__grupo__${dia}`;
  const selecionarTodosGrupo = (dia: string, grupo: string, itens: any[]) => {
    setSelecionadosLote((p) => ({ ...p, [dia]: new Set(itens.map((it) => it.id)) }));
    setCategoriaLoteDia((p) => ({ ...p, [dia]: grupo }));
    if (itens.length) abrirCampos({ ...itens[0], id: chaveCamposGrupo(dia) });
  };

  // Chama o mesmo endpoint que a tela de Lançamentos usa para "Preventivo" —
  // cria/atualiza a regra recorrente e, se não for exame, registra a aplicação
  // (com baixa de estoque) já com os dados confirmados/editados aqui mesmo.
  async function resolverSanidade(e: any, camposOverride?: CampoBaixaSanidade): Promise<boolean> {
    const c = camposOverride || camposBaixa[e.id] || camposIniciais(e);
    const exame = ehExameSanitario(e);
    // "Repetir a cada" = 0 é intencional: usuário não quer gerar agendamento
    // futuro, só registrar esta aplicação (ver cadastrar_preventivo no backend).
    const freq = c.freqValor.trim() === "" ? 1 : Number(c.freqValor);
    try {
      await cadastrarPreventivo({
        evento_sanitario_id: e.evento_sanitario_id,
        categoria_alvo: e.categoria_alvo || undefined,
        data_evento: e.data,
        frequencia_valor: Number.isFinite(freq) && freq >= 0 ? freq : 1,
        frequencia_unidade: c.freqUnidade,
        animais: e.numero_animal ? [e.numero_animal] : [],
        aplicar: !exame,
        veterinario: exame ? (c.veterinario || undefined) : undefined,
        produto: exame ? undefined : (c.produto || undefined),
        dose: exame || !c.dose ? undefined : Number(c.dose),
        unidade: exame ? undefined : (c.unidade || undefined),
        via: exame ? undefined : (c.via || undefined),
        principio_ativo_id: exame || !c.principioAtivoId ? undefined : Number(c.principioAtivoId),
      });
      await marcarEventoRealizado(e.id);
      return true;
    } catch (err: any) {
      mostrarFeedback(err.message || "Erro ao dar baixa", true);
      return false;
    }
  }

  const confirmarBaixaIndividual = async (e: any) => {
    setResolvendoBaixa((p) => new Set(p).add(e.id));
    const ok = await resolverSanidade(e);
    setResolvendoBaixa((p) => { const n = new Set(p); n.delete(e.id); return n; });
    if (ok) {
      setExpandidoBaixa((p) => { const n = new Set(p); n.delete(e.id); return n; });
      await carregar();
      mostrarFeedback("Baixa registrada.");
    }
  };

  const confirmarLoteDia = async (dia: string) => {
    const ids = Array.from(selecionadosLote[dia] || []);
    if (!ids.length) return;
    // Linha única (grupo inteiro selecionado): os mesmos campos valem p/ todos.
    const camposGrupo = camposBaixa[chaveCamposGrupo(dia)];
    setResolvendoLoteDia((p) => new Set(p).add(dia));
    let falhas = 0;
    for (const id of ids) {
      const e = eventoPorId.get(id);
      if (!e) continue;
      if (!(await resolverSanidade(e, camposGrupo))) falhas++;
    }
    setResolvendoLoteDia((p) => { const n = new Set(p); n.delete(dia); return n; });
    setSelecionadosLote((p) => { const n = { ...p }; delete n[dia]; return n; });
    setCategoriaLoteDia((p) => { const n = { ...p }; delete n[dia]; return n; });
    setCamposBaixa((p) => { const n = { ...p }; delete n[chaveCamposGrupo(dia)]; return n; });
    setLoteDia((p) => ({ ...p, [dia]: false }));
    await carregar();
    mostrarFeedback(falhas ? `Baixa em lote concluída com ${falhas} erro(s).` : "Baixa em lote registrada para todos os selecionados.", falhas > 0);
  };

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

  // Descartar pendência sanitária sem aplicar (ex.: pendência antiga que não
  // faz mais sentido registrar) — some da Agenda sem criar Sanidade nem baixa
  // de estoque, ao contrário de "Dar baixa". Reaproveita o mesmo
  // EventoRealizado usado em "Realizado", então é reversível (desfazer).
  const [descartando, setDescartando] = useState<Set<string>>(new Set());
  const descartarPendencia = async (e: any) => {
    setDescartando((p) => new Set(p).add(e.id));
    try {
      await marcarEventoRealizado(e.id);
      cancelarConfirmacao(`descartar:${e.id}`);
      await carregar();
      mostrarFeedback("Pendência descartada (nenhuma aplicação foi registrada).");
    } catch (err: any) { mostrarFeedback(err.message, true); }
    finally { setDescartando((p) => { const n = new Set(p); n.delete(e.id); return n; }); }
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

  // Botão "Descartar" — mesma UX de confirmação do BotaoRealizado, mas para
  // pendências sanitárias que o usuário decide não aplicar (ex.: pendência
  // antiga substituída por um lançamento retroativo já feito por fora).
  const BotaoDescartar = ({ e }: { e: any }) => {
    const chave = `descartar:${e.id}`;
    if (confirmando.has(chave)) {
      return (
        <span className="flex items-center gap-1" style={{ fontSize: "0.66rem" }} onClick={(ev) => ev.stopPropagation()}>
          Descartar sem aplicar?
          <button className="btn-ghost" style={{ color: "var(--red)", padding: "0.1rem 0.3rem" }} disabled={descartando.has(e.id)} onClick={() => descartarPendencia(e)}>Sim</button>
          <button className="btn-ghost" style={{ padding: "0.1rem 0.3rem" }} onClick={() => cancelarConfirmacao(chave)}>Não</button>
        </span>
      );
    }
    return (
      <button className="btn-ghost" style={{ fontSize: "0.66rem", color: "var(--text-muted)" }} disabled={descartando.has(e.id)}
        title="Remove esta pendência da Agenda sem registrar aplicação nem baixar estoque"
        onClick={(ev) => { ev.stopPropagation(); pedirConfirmacao(chave); }}>
        <X size={11} /> Descartar
      </button>
    );
  };

  // Linha de confirmação de uma pendência de sanidade (evento_sanitario /
  // calendario_sanitario) — os campos vêm do cadastro/lançamento (produto,
  // dose, unidade, via, princípio ativo, veterinário), pré-preenchidos e
  // editáveis. Em modo lote, some o botão individual (a confirmação é única,
  // via "Confirmar baixa em lote" no rodapé do dia).
  const inputInline: React.CSSProperties = { width: "100%", fontSize: "0.78rem", padding: "0.3rem 0.5rem", borderRadius: 6, background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" };
  const rotuloInline: React.CSSProperties = { fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
  const PainelConfirmarBaixa = ({ e, loteModo }: { e: any; loteModo: boolean }) => {
    const campos = camposBaixa[e.id] || camposIniciais(e);
    const exame = ehExameSanitario(e);
    const set = (campo: keyof typeof campos, valor: string) => atualizarCampo(e.id, campo, valor);
    return (
      <div style={{ padding: "0.6rem 0" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "0.6rem" }}>
          <div>
            <label style={rotuloInline}>Evento sanitário</label>
            <div style={{ fontSize: "0.8rem", fontWeight: 700 }}>{nomeEventoSanitario(e)}</div>
          </div>
          {exame ? (
            <div>
              <label style={rotuloInline}>Veterinário</label>
              <input style={inputInline} value={campos.veterinario} onChange={(ev) => set("veterinario", ev.target.value)} placeholder="ex.: Dr. Carlos" />
            </div>
          ) : (
            <>
              <div>
                <label style={rotuloInline}>Medicamento</label>
                <input style={inputInline} value={campos.produto} onChange={(ev) => set("produto", ev.target.value)} placeholder="ex.: VACINA RB 51" />
              </div>
              <div>
                <label style={rotuloInline}>Princípio ativo</label>
                <select style={inputInline} value={campos.principioAtivoId} onChange={(ev) => set("principioAtivoId", ev.target.value)}>
                  <option value="">—</option>
                  {principiosAtivos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </div>
              <div>
                <label style={rotuloInline}>Dosagem</label>
                <input type="number" inputMode="decimal" style={inputInline} value={campos.dose} onChange={(ev) => set("dose", ev.target.value)} />
              </div>
              <div>
                <label style={rotuloInline}>Unidade</label>
                <select style={inputInline} value={campos.unidade} onChange={(ev) => set("unidade", ev.target.value)}>
                  <option value="">—</option>
                  {UNIDADES_APLICACAO.map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
              </div>
              <div>
                <label style={rotuloInline}>Via</label>
                <select style={inputInline} value={campos.via} onChange={(ev) => set("via", ev.target.value)}>
                  <option value="">—</option>
                  {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </div>
            </>
          )}
          <div>
            <label style={rotuloInline}>Repetir a cada</label>
            <div style={{ display: "flex", gap: "0.3rem" }}>
              <input type="number" min={0} inputMode="numeric" style={{ ...inputInline, width: 60 }} value={campos.freqValor} onChange={(ev) => set("freqValor", ev.target.value)} title="0 = não repetir (não gera agendamento futuro, só esta aplicação)" />
              <select style={inputInline} value={campos.freqUnidade} onChange={(ev) => set("freqUnidade", ev.target.value)}>
                <option value="dias">dia(s)</option>
                <option value="meses">mês(es)</option>
                <option value="anos">ano(s)</option>
              </select>
            </div>
            {Number(campos.freqValor) === 0 && (
              <p style={{ fontSize: "0.66rem", color: "var(--amber)", marginTop: "0.2rem" }}>0 = não repete: sem agendamento futuro, só esta aplicação.</p>
            )}
          </div>
        </div>
        {!loteModo && (
          <div className="flex items-center gap-2 mt-2">
            <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={resolvendoBaixa.has(e.id)} onClick={() => confirmarBaixaIndividual(e)}>
              <Check size={12} /> {resolvendoBaixa.has(e.id) ? "Salvando…" : "Confirmar baixa"}
            </button>
            <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setExpandidoBaixa((p) => { const n = new Set(p); n.delete(e.id); return n; })}>Cancelar</button>
          </div>
        )}
      </div>
    );
  };

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
        } else if (e.tipo === "cronograma_sanitario_animal") {
          linhas.push({ tipo: "cronograma_animal", e });
        } else if (e.tipo === "cronograma_sanitario_modo" || e.tipo === "cronograma_sanitario_urgente") {
          linhas.push({ tipo: "cronograma_modo", e });
        } else if (e.tipo === "cronograma_sanitario_aplicar") {
          linhas.push({ tipo: "cronograma_aplicar", e });
        } else if (e.categoria === "Gestão/Financeiro" && e.ref) {
          const arr = financeiroPorRef.get(e.ref) ?? [];
          arr.push(e); financeiroPorRef.set(e.ref, arr);
        } else {
          linhas.push({ tipo: "simples", e });
        }
      });
      financeiroPorRef.forEach((itens, ref) => linhas.push({ tipo: "grupo", ref, itens }));

      // Pendências elegíveis para o fluxo "dar baixa em lote" (mesmo dia) —
      // só sanidade com matriz definida (ver elegivelBaixaInline). Separadas
      // por categoria/lote-alvo + evento sanitário (grupoLoteChave), já que só
      // faz sentido preencher os mesmos dados de uma vez para pendências
      // realmente iguais.
      const elegiveisDia = evs.filter((e: any) => elegivelBaixaInline(e));
      const loteAtivoDia = !!loteDia[d];
      const gruposElegiveisDia = new Map<string, any[]>();
      elegiveisDia.forEach((e: any) => {
        const g = grupoLoteChave(e);
        (gruposElegiveisDia.get(g) ?? gruposElegiveisDia.set(g, []).get(g)!).push(e);
      });
      const grupoAtivoDia = categoriaLoteDia[d];
      const itensGrupoAtivo = grupoAtivoDia ? (gruposElegiveisDia.get(grupoAtivoDia) || []) : [];
      // Todos do grupo selecionados (via "Selecionar todos" ou marcando um a
      // um) — nesse caso mostra 1 linha só, em vez de um painel por pendência.
      const modoLinhaUnicaDia = loteAtivoDia && !!grupoAtivoDia && itensGrupoAtivo.length > 1 &&
        itensGrupoAtivo.every((it) => selecionadosLote[d]?.has(it.id));

      return (
        <div key={d} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", background: "var(--surface-2)" }}>
            <button onClick={() => toggleData(d)} style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.9rem", background: "transparent", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
              {aberto ? <ChevronDown size={15} style={{ color: "var(--text-muted)" }} /> : <ChevronRight size={15} style={{ color: "var(--text-muted)" }} />}
              <span style={{ fontWeight: 700, minWidth: "8rem" }}>{new Date(d + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short", year: "2-digit" })}</span>
              <span style={{ flex: 1, fontSize: "0.78rem", color: "var(--text-muted)" }}>{evs.length} evento{evs.length !== 1 ? "s" : ""}</span>
            </button>
            {elegiveisDia.length > 1 && (
              <label className="flex items-center gap-1" style={{ fontSize: "0.7rem", color: "var(--text-muted)", cursor: "pointer", padding: "0 0.9rem", whiteSpace: "nowrap" }}
                title="Selecione várias pendências da mesma categoria e confirme a baixa de todas juntas, sem sair da Agenda">
                <input type="checkbox" checked={loteAtivoDia} onChange={() => toggleLoteDia(d)} /> Dar baixa em lote
              </label>
            )}
            {loteAtivoDia && gruposElegiveisDia.size > 0 && (
              <div className="flex items-center gap-1" style={{ flexWrap: "wrap", padding: "0 0.9rem 0.5rem" }}>
                {Array.from(gruposElegiveisDia.entries()).filter(([g]) => !grupoAtivoDia || g === grupoAtivoDia).map(([g, itens]) => {
                  const todosDoGrupoSelecionados = itens.length > 0 && itens.every((it) => selecionadosLote[d]?.has(it.id));
                  return (
                    <button key={g} className="btn-ghost" style={{ fontSize: "0.68rem", padding: "0.15rem 0.5rem", borderRadius: 999, border: "1px solid var(--border)" }}
                      title={`${grupoLoteRotulo(itens[0])} — ${itens.length} pendência(s)`}
                      onClick={() => todosDoGrupoSelecionados
                        ? (setSelecionadosLote((p) => { const n = { ...p }; delete n[d]; return n; }), setCategoriaLoteDia((p) => { const n = { ...p }; delete n[d]; return n; }))
                        : selecionarTodosGrupo(d, g, itens)}>
                      {todosDoGrupoSelecionados ? "Desmarcar todos" : "Selecionar todos"}: {grupoLoteRotulo(itens[0])} ({itens.length})
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          {aberto && (
            <div className="overflow-x-auto">
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr><th></th><th>Nº Animal</th><th>Descrição</th><th>Obs.</th><th>Origem</th><th></th></tr></thead>
                <tbody>
                  {linhas.map((linha, i) => {
                    if (linha.tipo === "simples") {
                      const e = linha.e;
                      const elegivel = elegivelBaixaInline(e);
                      const selecionadoLote = elegivel && (selecionadosLote[d]?.has(e.id) ?? false);
                      // Em modo linha única (grupo inteiro selecionado), o painel some daqui
                      // e some 1 vez só, compartilhado, logo antes do botão de confirmar.
                      const painelAberto = elegivel && (loteAtivoDia ? (selecionadoLote && !modoLinhaUnicaDia) : expandidoBaixa.has(e.id));
                      const linkFormularioCompleto = (numeroObrigatorio: boolean) => {
                        const ev = e as any;
                        const p = new URLSearchParams({ ir: "preventivo_aplicacao", evento_agenda: e.id });
                        if (ev.evento_sanitario_id) p.set("evento_sanitario_id", String(ev.evento_sanitario_id));
                        if (numeroObrigatorio && e.numero_animal) p.set("numero_matriz", e.numero_animal);
                        if (e.data) p.set("data", e.data);
                        // Pendência de uma regra do calendário sanitário JÁ existente
                        // (tipo calendario_sanitario) — leva o id para não criar uma
                        // regra nova duplicada ao dar baixa em Lançamentos.
                        if (ev.tipo === "calendario_sanitario" && ev.calendario_id) p.set("calendario_id", String(ev.calendario_id));
                        return `/lancamentos?${p.toString()}`;
                      };
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
                            <td style={{ fontWeight: e.numero_animal ? 700 : 400 }}>{e.numero_animal || (e.lote ? `Lote: ${e.lote}` : "—")}</td>
                            <td style={{ fontSize: "0.83rem" }} title={categoriaLabel(e.categoria)}>{e.descricao}{mostrarAtraso && pillAtraso(e.data)}</td>
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem", whiteSpace: "pre-line", maxWidth: "26rem" }}>{e.observacao || "—"}</td>
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
                              ) : (e as any).tipo === "evento_sanitario" || (e as any).tipo === "calendario_sanitario" ? (
                                !elegivel ? (
                                  // Sem matriz específica (gatilho de época/rebanho) — não dá pra
                                  // resolver inline sem escolher os animais; segue para o formulário,
                                  // que já sabe tratar exame (sem produto/dose) e vacina/tratamento.
                                  <div className="flex flex-col gap-1" style={{ alignItems: "flex-start" }}>
                                    <a href={linkFormularioCompleto(false)} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} title="Aplicar/confirmar (evento sem matriz específica — escolha o alvo no formulário)">
                                      <Syringe size={12} /> Dar baixa (aplicar)
                                    </a>
                                    <BotaoDescartar e={e} />
                                  </div>
                                ) : loteAtivoDia ? (
                                  <label className="flex items-center gap-1" style={{ fontSize: "0.72rem", opacity: (!categoriaLoteDia[d] || categoriaLoteDia[d] === grupoLoteChave(e)) ? 1 : 0.4, cursor: (!categoriaLoteDia[d] || categoriaLoteDia[d] === grupoLoteChave(e)) ? "pointer" : "not-allowed" }}
                                    title={(!categoriaLoteDia[d] || categoriaLoteDia[d] === grupoLoteChave(e)) ? "Selecionar para dar baixa em lote" : "Só é possível combinar pendências da mesma categoria/lote e evento"}>
                                    <input type="checkbox" disabled={!!categoriaLoteDia[d] && categoriaLoteDia[d] !== grupoLoteChave(e)} checked={selecionadoLote}
                                      onChange={() => toggleSelecaoLote(d, e)} />
                                    Selecionar
                                  </label>
                                ) : (abrirLancamento[e.id] ?? false) ? (
                                  <div className="flex flex-col gap-1" style={{ alignItems: "flex-start" }}>
                                    <a href={linkFormularioCompleto(true)} className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} title="Abre a tela completa de lançamento">
                                      <Syringe size={12} /> Dar baixa (aplicar)
                                    </a>
                                    <label className="flex items-center gap-1" style={{ fontSize: "0.66rem", color: "var(--text-muted)", cursor: "pointer" }}>
                                      <input type="checkbox" checked={abrirLancamento[e.id] ?? false} onChange={() => setAbrirLancamento((p) => ({ ...p, [e.id]: !p[e.id] }))} /> abrir lançamento
                                    </label>
                                  </div>
                                ) : (
                                  <div className="flex flex-col gap-1" style={{ alignItems: "flex-start" }}>
                                    <button className="btn-ghost" style={{ fontSize: "0.68rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                                      disabled={resolvendoBaixa.has(e.id)}
                                      onClick={() => { abrirCampos(e); setExpandidoBaixa((p) => new Set(p).add(e.id)); }}
                                      title="Confirma os dados e dá baixa sem sair da Agenda">
                                      <Syringe size={12} /> Dar baixa (aplicar)
                                    </button>
                                    <label className="flex items-center gap-1" style={{ fontSize: "0.66rem", color: "var(--text-muted)", cursor: "pointer" }}>
                                      <input type="checkbox" checked={abrirLancamento[e.id] ?? false} onChange={() => setAbrirLancamento((p) => ({ ...p, [e.id]: !p[e.id] }))} /> abrir lançamento
                                    </label>
                                    <BotaoDescartar e={e} />
                                  </div>
                                )
                              ) : (e as any).tipo === "confirmar_cura" ? (
                                <span className="flex items-center gap-1" style={{ fontSize: "0.72rem" }} onClick={(ev) => ev.stopPropagation()}>
                                  Curado?
                                  <button className="btn-ghost" style={{ color: "var(--green-light)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(e.id)} onClick={() => confirmarCura(e, true)}>Sim</button>
                                  <button className="btn-ghost" style={{ color: "var(--red)", padding: "0.1rem 0.4rem" }} disabled={marcando.has(e.id)} onClick={() => confirmarCura(e, false)}>Não</button>
                                </span>
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
                          {painelAberto && (
                            <tr style={{ background: "var(--surface-2)" }}>
                              <td></td>
                              <td colSpan={5}>
                                <PainelConfirmarBaixa e={e} loteModo={loteAtivoDia} />
                              </td>
                            </tr>
                          )}
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
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || "—"}</td>
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
                                              <a
                                                href={`/lancamentos?ir=inseminacao&numero_matriz=${encodeURIComponent(numero)}&protocolo=${encodeURIComponent(e.protocolo || "")}`}
                                                className="btn-ghost" style={{ fontSize: "0.7rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                                              >
                                                <Syringe size={12} /> Ir para Inseminação
                                              </a>
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
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || "—"}</td>
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
                    if (linha.tipo === "cronograma_animal") {
                      const e = linha.e;
                      return (
                        <tr key={`cron-animal-${i}`}>
                          {tdAccent(e.categoria)}
                          <td style={{ fontWeight: 700 }}>{e.numero_animal}</td>
                          <td style={{ fontSize: "0.83rem" }} title={categoriaLabel(e.categoria)}>{e.descricao}{mostrarAtraso && pillAtraso(e.data)}</td>
                          <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || "—"}</td>
                          <td style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>auto</td>
                          <td>
                            <span className="flex items-center gap-1">
                              <button className="btn-primary" style={{ fontSize: "0.68rem" }} disabled={marcando.has(e.id)} onClick={() => decidirCronogramaAnimal(e, true)}>
                                <Check size={11} /> Incluir
                              </button>
                              <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={marcando.has(e.id)} onClick={() => decidirCronogramaAnimal(e, false)}>
                                <X size={11} /> Excluir
                              </button>
                            </span>
                          </td>
                        </tr>
                      );
                    }
                    if (linha.tipo === "cronograma_modo") {
                      const e = linha.e;
                      const urgente = e.tipo === "cronograma_sanitario_urgente";
                      const abertoCron = cronogramaModoAbertos.has(e.id);
                      const acao = cronogramaAcao[e.id] || "";
                      return (
                        <React.Fragment key={`cron-modo-${i}`}>
                          <tr style={{ cursor: "pointer" }} onClick={() => toggleCronogramaModo(e.id)}>
                            {tdAccent(e.categoria)}
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>—</td>
                            <td style={{ fontSize: "0.83rem" }} title={categoriaLabel(e.categoria)}>
                              {abertoCron ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                              {e.descricao}
                              {urgente && (
                                <span style={{ marginLeft: "0.5rem", fontSize: "0.66rem", fontWeight: 700, color: "var(--red)", background: "rgba(220,38,38,0.12)", padding: "0.05rem 0.45rem", borderRadius: 999 }}>
                                  Urgente
                                </span>
                              )}
                            </td>
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || "—"}</td>
                            <td style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>auto</td>
                            <td onClick={(ev) => ev.stopPropagation()} />
                          </tr>
                          {abertoCron && (
                            <tr style={{ background: "var(--surface-2)" }}>
                              <td></td>
                              <td colSpan={5}>
                                <div style={{ padding: "0.6rem 0" }}>
                                  {!acao ? (
                                    <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                                      <button className="btn-secondary" style={{ fontSize: "0.72rem" }} onClick={() => setCronogramaAcao((p) => ({ ...p, [e.id]: "veterinario" }))}>
                                        Veterinário
                                      </button>
                                      <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id)} onClick={() => decidirCronogramaModo(e, "propria")}>
                                        Aplicação própria
                                      </button>
                                      {urgente && (
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setCronogramaAcao((p) => ({ ...p, [e.id]: "adiar" }))}>
                                          Adiar
                                        </button>
                                      )}
                                    </div>
                                  ) : acao === "veterinario" ? (
                                    <div style={{ maxWidth: 420 }}>
                                      <label style={rotuloInline}>Veterinário</label>
                                      {!cronogramaNovoVet[e.id] ? (
                                        <>
                                          <select style={inputInline} value={cronogramaVetSel[e.id] || ""} onChange={(ev) => setCronogramaVetSel((p) => ({ ...p, [e.id]: ev.target.value }))}>
                                            <option value="">Selecione…</option>
                                            {veterinariosCronograma.map((v) => <option key={v.id} value={v.id}>{v.nome}</option>)}
                                          </select>
                                          <button type="button" className="btn-ghost" style={{ fontSize: "0.7rem", marginTop: "0.35rem" }} onClick={() => setCronogramaNovoVet((p) => ({ ...p, [e.id]: true }))}>
                                            + cadastrar novo veterinário
                                          </button>
                                        </>
                                      ) : (
                                        <div className="flex items-center gap-2" style={{ marginTop: "0.3rem" }}>
                                          <input style={inputInline} placeholder="Nome do veterinário" value={cronogramaNovoVetNome[e.id] || ""} onChange={(ev) => setCronogramaNovoVetNome((p) => ({ ...p, [e.id]: ev.target.value }))} />
                                          <button className="btn-secondary" style={{ fontSize: "0.7rem" }} disabled={cronogramaCriandoVet.has(e.id)} onClick={() => criarVetInlineCronograma(e)}>
                                            {cronogramaCriandoVet.has(e.id) ? "Salvando…" : "Salvar"}
                                          </button>
                                          <button className="btn-ghost" style={{ fontSize: "0.7rem" }} onClick={() => setCronogramaNovoVet((p) => ({ ...p, [e.id]: false }))}>Cancelar</button>
                                        </div>
                                      )}
                                      <div className="flex items-center gap-2 mt-2">
                                        <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id) || !cronogramaVetSel[e.id]} onClick={() => decidirCronogramaModo(e, "veterinario")}>
                                          <Check size={12} /> Confirmar
                                        </button>
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setCronogramaAcao((p) => ({ ...p, [e.id]: "" }))}>Voltar</button>
                                      </div>
                                    </div>
                                  ) : (
                                    <div style={{ maxWidth: 320 }}>
                                      <label style={rotuloInline}>Nova data</label>
                                      <input type="date" style={inputInline} value={cronogramaAdiarData[e.id] || ""} onChange={(ev) => setCronogramaAdiarData((p) => ({ ...p, [e.id]: ev.target.value }))} />
                                      <label style={{ ...rotuloInline, marginTop: "0.4rem" }}>Motivo (opcional)</label>
                                      <input style={inputInline} value={cronogramaAdiarMotivo[e.id] || ""} onChange={(ev) => setCronogramaAdiarMotivo((p) => ({ ...p, [e.id]: ev.target.value }))} />
                                      <div className="flex items-center gap-2 mt-2">
                                        <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id)} onClick={() => adiarCronograma(e)}>
                                          <Check size={12} /> Confirmar adiamento
                                        </button>
                                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setCronogramaAcao((p) => ({ ...p, [e.id]: "" }))}>Voltar</button>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    }
                    if (linha.tipo === "cronograma_aplicar") {
                      const e = linha.e;
                      const abertoCron = cronogramaAplicarAbertos.has(e.id);
                      const checks = cronogramaAplicarChecks[e.id] || new Set(e.animais);
                      return (
                        <React.Fragment key={`cron-aplicar-${i}`}>
                          <tr style={{ cursor: "pointer" }} onClick={() => abrirCronogramaAplicar(e.id, e.animais)}>
                            {tdAccent(e.categoria)}
                            <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{e.animais.length} animal(is)</td>
                            <td style={{ fontSize: "0.83rem" }} title={categoriaLabel(e.categoria)}>
                              {abertoCron ? <ChevronDown size={12} style={{ display: "inline", marginRight: "0.3rem" }} /> : <ChevronRight size={12} style={{ display: "inline", marginRight: "0.3rem" }} />}
                              {e.descricao}{mostrarAtraso && pillAtraso(e.data)}
                            </td>
                            <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{e.observacao || "—"}</td>
                            <td style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>auto</td>
                            <td onClick={(ev) => ev.stopPropagation()}>
                              <button className="btn-primary" style={{ fontSize: "0.68rem" }} disabled={marcando.has(e.id)} onClick={() => aplicarCronogramaLote(e)}>
                                <Check size={11} /> Aplicar em lote
                              </button>
                            </td>
                          </tr>
                          {abertoCron && (
                            <tr style={{ background: "var(--surface-2)" }}>
                              <td></td>
                              <td colSpan={5}>
                                <div style={{ padding: "0.5rem 0" }}>
                                  <table className="fazenda-table" style={{ margin: 0 }}>
                                    <thead><tr><th></th><th>Nº</th></tr></thead>
                                    <tbody>
                                      {e.animais.map((numero: string) => (
                                        <tr key={numero}>
                                          <td><input type="checkbox" checked={checks.has(numero)} onChange={() => toggleAnimalCronogramaAplicar(e.id, numero)} /></td>
                                          <td style={{ fontWeight: 700 }}>{numero}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                  <div className="flex items-center gap-2 mt-2">
                                    <button className="btn-primary" style={{ fontSize: "0.72rem" }} disabled={marcando.has(e.id) || !checks.size} onClick={() => aplicarCronogramaIndividual(e)}>
                                      <Check size={12} /> Individualizado ({checks.size}/{e.animais.length})
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
                            <td style={{ color: "var(--amber)", fontSize: "0.78rem", fontWeight: e.observacao ? 700 : 400 }}>{e.observacao || "—"}</td>
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
                  {modoLinhaUnicaDia && itensGrupoAtivo.length > 0 && (
                    <tr style={{ background: "var(--surface-2)" }}>
                      <td></td>
                      <td colSpan={5}>
                        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem" }}>
                          {itensGrupoAtivo.length} pendências de "{grupoLoteRotulo(itensGrupoAtivo[0])}" — os dados abaixo valem para todas.
                        </div>
                        <PainelConfirmarBaixa e={{ ...itensGrupoAtivo[0], id: chaveCamposGrupo(d) }} loteModo={true} />
                      </td>
                    </tr>
                  )}
                  {loteAtivoDia && (selecionadosLote[d]?.size ?? 0) > 0 && (
                    <tr style={{ background: "var(--surface-2)" }}>
                      <td colSpan={6} style={{ textAlign: "right", padding: "0.6rem 0.9rem" }}>
                        <button className="btn-primary" style={{ fontSize: "0.75rem" }} disabled={resolvendoLoteDia.has(d)} onClick={() => confirmarLoteDia(d)}>
                          <Check size={13} /> {resolvendoLoteDia.has(d) ? "Salvando…" : `Confirmar baixa em lote (${selecionadosLote[d]!.size})`}
                        </button>
                      </td>
                    </tr>
                  )}
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
      <div style={{ display: "grid", gridTemplateColumns: diaSelecionado ? "1fr 320px" : "1fr", gap: "1.25rem", alignItems: "start" }}>
        <div>
          <div className="flex items-center justify-between mb-3">
            <button className="btn-ghost" onClick={() => mudarMes(-1)} title="Mês anterior"><ChevronLeft size={16} /></button>
            <button className="btn-ghost" onClick={irParaMesAtual} style={{ fontWeight: 700, fontSize: "0.9rem" }}>
              {NOMES_MES[mesCalendario.mes]} de {mesCalendario.ano}
            </button>
            <button className="btn-ghost" onClick={() => mudarMes(1)} title="Próximo mês"><ChevronRight size={16} /></button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: "4px" }}>
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
                <button key={iso} type="button" onClick={() => abrirDiaCalendario(iso)}
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
                      <span style={{ fontSize: "0.62rem", color: "var(--text-muted)" }}>{evs.length} evento{evs.length !== 1 ? "s" : ""}</span>
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
              <span style={{ fontSize: "0.85rem", textTransform: "capitalize" }}>
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
  const abrirAlertasEstoque = () => {
    setPaineis((p) => new Set(p).add("estoqueAlertas"));
    const reduzMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    estoqueAlertasRef.current?.scrollIntoView({ behavior: reduzMovimento ? "auto" : "smooth", block: "start" });
  };

  // Compromisso "Aplicação de BST hoje" na Agenda: ao clicar, abre (não
  // alterna) as listas BST aptos + Incluir no próximo BST e rola até elas —
  // é a mesma informação já mostrada nos quadros/listas acima, só que o
  // usuário chega direto nela a partir do evento do dia.
  const bstIndicadoresRef = useRef<HTMLDivElement>(null);
  const abrirListasBst = () => {
    setListaAtiva((p) => { const n = new Set(p); n.add("bstAptos"); n.add("bstNunca"); return n; });
    const reduzMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    bstIndicadoresRef.current?.scrollIntoView({ behavior: reduzMovimento ? "auto" : "smooth", block: "start" });
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

  return (
    <div className="p-6 animate-in">
      {/* Filtros da agenda cronológica — primeiro elemento da página (C1):
          "Data de referência" saiu (C2); o estado `data` continua existindo
          por baixo (ancora `carregar()`), só o controle sumiu — a agenda
          passa a ancorar sempre em hoje. */}
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtrar agenda</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label>
            <input type="date" value={de} onChange={e => setDe(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label>
            <input type="date" value={ate} onChange={e => setAte(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
            <select value={fCat} onChange={e => setFCat(e.target.value)} style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }}>
              <option value="">Todas</option>{CATEGORIAS.map(c => <option key={c}>{c}</option>)}
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Buscar</label>
            <input value={filtro} onChange={e => setFiltro(e.target.value)} placeholder="texto ou nº..." style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", color: "var(--text)", fontSize: "0.8rem" }} /></div>
        </div>
        {(de || ate || fCat || filtro) && <button className="btn-ghost" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }} onClick={() => { setDe(""); setAte(""); setFCat(""); setFiltro(""); }}>Limpar filtros</button>}
      </div>

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Calendar size={22} style={{ color: "var(--dourado)" }} />
            Agenda
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Eventos preditivos gerados automaticamente pelas regras da fazenda
          </p>
        </div>
        <div className="flex items-end gap-2">
          <button onClick={carregar} className="btn-ghost" title="Recarregar">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>
          <button onClick={() => setCalendarioAberto((a) => !a)} className="btn-primary" title="Ver o calendário mensal por cima dos indicadores">
            <Calendar size={16} /> {calendarioAberto ? "Fechar calendário" : "Calendário"}
          </button>
        </div>
      </div>

      {/* Erro de carregamento — distinto do estado "sem dados" */}
      {erro && (
        <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Não foi possível carregar a agenda: {erro}</span></div>
      )}

      {/* Feedback transitório de ações (sucesso em verde, erro em vermelho) */}
      {feedback && (
        <div className="mb-4" style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", padding: "0.5rem 0.9rem", borderRadius: "var(--r-sm)",
          background: feedback.erro ? "rgba(192,57,43,0.15)" : "rgba(20,83,45,0.35)",
          border: "1px solid " + (feedback.erro ? "var(--red)" : "var(--green-light)"),
          color: feedback.erro ? "var(--red)" : "var(--green-light)" }}>
          {feedback.erro ? <AlertTriangle size={15} /> : <CheckCircle2 size={15} />} {feedback.msg}
        </div>
      )}

      {/* Informações gerenciais — cada quadro clicável expande/recolhe uma
          lista logo abaixo (estado listaAtiva); "Alertas de estoque" rola até
          a seção de Estoque, no final da página. */}
      {loading && !agenda ? (
        <div className="mb-4"><p style={{ color: "var(--text-muted)", padding: "1rem" }}>Carregando…</p></div>
      ) : agenda && (
        calendarioAberto ? (
          // Calendário mensal por cima dos indicadores (C3-C4) — mesmo
          // renderCalendario() reaproveitado da antiga visualização de baixo,
          // só que agora sobrepondo este bloco em vez de trocar de aba.
          <div className="card mb-2">
            <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <span className="flex items-center gap-2"><Calendar size={15} style={{ color: "var(--dourado)" }} /> Calendário</span>
              <div className="flex items-center gap-2">
                {/* O botão "Adicionar" saiu do cabeçalho da página (C3), mas o
                    evento manual não podia sair com ele: o atalho "Agendar" de
                    cada linha só cria evento de UM animal, com descrição fixa
                    da linha. Sem este gatilho, evento livre ou vinculado a
                    lote(s) ficaria sem nenhum caminho na tela — o modal e o
                    POST /agenda/manual continuariam existindo, inalcançáveis.
                    O calendário é onde faz sentido: quem está olhando o mês é
                    quem quer marcar alguma coisa nele. */}
                <button className="btn-ghost" onClick={() => setShowModal(true)} title="Criar evento manual — livre, por lote ou para vários animais">
                  <Plus size={14} /> Novo evento
                </button>
                <button className="btn-ghost" onClick={() => setCalendarioAberto(false)} title="Fechar e voltar aos indicadores"><X size={14} /> Fechar</button>
              </div>
            </div>
            {renderCalendario()}
          </div>
        ) : (
        <div ref={bstIndicadoresRef} className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-2">
          <Indicador categoria="reprodutivo" cor="var(--blue)" valor={candidatas.length} rotulo="Candidatas à próxima IATF"
            onClick={() => toggleLista("iatf")} podeClicar={candidatas.length > 0}
            extra={candidatas.length > 0 && (listaAtiva.has("iatf") ? <ChevronDown size={11} /> : <ChevronRight size={11} />)} />

          <Indicador categoria="reprodutivo" cor="var(--green-light)" valor={`${animaisIatfAtual.length} animal(is)`} rotulo="IATF atual"
            onClick={() => toggleLista("iatfAtual")} podeClicar={animaisIatfAtual.length > 0}
            title="Animais com alguma etapa (D0/D7/D9/D11) ainda em aberto — só passa de zero durante o protocolo, do D0 até a inseminação (D11)"
            extra={animaisIatfAtual.length > 0 && (listaAtiva.has("iatfAtual") ? <ChevronDown size={11} /> : <ChevronRight size={11} />)} />

          <Indicador categoria="reprodutivo" cor={grupoUltimaIatf ? undefined : "var(--text-muted)"} rotulo="Última IATF"
            onClick={() => toggleLista("iatfUltima")} podeClicar={!!grupoUltimaIatf}
            valor={grupoUltimaIatf ? (
              <>
                <span style={{ display: "block", fontSize: "0.86rem", fontWeight: 700, color: "var(--dourado-light)", lineHeight: 1.35 }}>
                  D0 {fmtCurtaAno(grupoUltimaIatf.data_d0)} · D11 {fmtCurtaAno(grupoUltimaIatf.data_d11)}
                </span>
                <span style={{ display: "block", fontSize: "1.15rem", fontWeight: 800, marginTop: "0.1rem", color: "var(--text)" }}>{grupoUltimaIatf.animais.length} animal(is)</span>
              </>
            ) : "—"}
            extra={!!grupoUltimaIatf && (listaAtiva.has("iatfUltima") ? <ChevronDown size={11} /> : <ChevronRight size={11} />)} />

          <Indicador categoria="sanidade" cor="var(--green-light)" rotulo="BST aptos"
            onClick={() => toggleLista("bstAptos")} podeClicar={bstAptos.length > 0}
            valor={<>
              {bstAptos.length}
              {proxBST && <span style={{ display: "block", fontSize: "0.7rem", fontWeight: 400, color: "var(--text-muted)" }}>Próx. aplicação: {proxBST}</span>}
            </>}
            extra={bstAptos.length > 0 && (listaAtiva.has("bstAptos") ? <ChevronDown size={11} /> : <ChevronRight size={11} />)} />

          <Indicador categoria="sanidade" cor="var(--amber)" valor={bstExcl.length} rotulo="BST excluídos"
            onClick={() => toggleLista("bstExcl")} podeClicar={bstExcl.length > 0}
            extra={bstExcl.length > 0 && (listaAtiva.has("bstExcl") ? <ChevronDown size={11} /> : <ChevronRight size={11} />)} />

          <Indicador categoria="sanidade" cor="var(--blue)" valor={bstNuncaAplicados.length} rotulo="Incluir no próximo BST"
            onClick={() => toggleLista("bstNunca")} podeClicar={bstNuncaAplicados.length > 0}
            extra={bstNuncaAplicados.length > 0 && (listaAtiva.has("bstNunca") ? <ChevronDown size={11} /> : <ChevronRight size={11} />)} />

          <Indicador categoria="geral" cor={eventosPendentes.length > 0 ? "var(--red)" : undefined}
            corLabel={eventosPendentes.length > 0 ? "var(--red)" : undefined} borda={eventosPendentes.length > 0 ? "var(--red)" : undefined}
            valor={eventosPendentes.length} rotulo="Pendências"
            onClick={() => toggleLista("pendencias")} podeClicar={eventosPendentes.length > 0}
            extra={eventosPendentes.length > 0 && (listaAtiva.has("pendencias") ? <ChevronDown size={11} /> : <ChevronRight size={11} />)} />

          <Indicador categoria="geral" cor="var(--amber)" valor={estoqueAlertasTotal} rotulo="Alertas de estoque"
            onClick={() => abrirAlertasEstoque()} podeClicar={estoqueAlertasTotal > 0}
            title="Ver o detalhe dos alertas de estoque, no final da página"
            extra={estoqueAlertasTotal > 0 && <PackageSearch size={11} />} />
        </div>
        )
      )}
      {eventosPendentes.length > 0 && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginBottom: "0.5rem" }}>
          Pendências: tudo que não foi realizado até o dia anterior a hoje.
        </p>
      )}

      {/* Legenda de categorias — mesma cor usada na tira à esquerda de cada
          linha da agenda mais abaixo. */}
      <div className="flex items-center gap-3 mb-4" style={{ flexWrap: "wrap", fontSize: "0.75rem", color: "var(--text-muted)" }}>
        {LEGENDA_CATEGORIAS.map((c) => (
          <span key={c} className="flex items-center gap-1">
            <span style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: corCategoria(c) }} />
            {c}
          </span>
        ))}
        {(proxVisita || proxBST) && (
          <span style={{ marginLeft: "auto" }}>
            {proxVisita && <>Próx. visita IATF: <strong style={{ color: "var(--text)" }}>{proxVisita}</strong></>}
            {proxVisita && proxBST && " · "}
            {proxBST && <>Próx. BST: <strong style={{ color: "var(--text)" }}>{proxBST}</strong></>}
          </span>
        )}
      </div>

      {/* Listas expansíveis — abrem/fecham a partir do clique nos quadros acima */}
      {(candidatas.length > 0 || animaisIatfAtual.length > 0 || (grupoUltimaIatf?.animais?.length ?? 0) > 0 ||
        bstAptos.length > 0 || bstExcl.length > 0 || bstNuncaAplicados.length > 0 || eventosPendentes.length > 0) && (
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

          {listaAtiva.has("pendencias") && eventosPendentes.length > 0 && (
            <div className="mb-2">{renderEventos(eventosPendentes, true)}</div>
          )}
        </div>
      )}

      {/* "Concluídos no período" (C7-C10) — card genérico no lugar do antigo
          card fixo só de indução de lactação: cobre etapas e atividades de
          qualquer tipo, com filtro de/até (padrão últimos 7 dias). Pequeno e
          recolhível por padrão (SecaoRecolhivel) para não competir com os
          indicadores em destaque acima. */}
      <SecaoRecolhivel
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

      {/* Comunicados — avisos informativos (ex.: nova dieta do lote). Diferente
          de uma atividade: não têm botão de excluir/realizado, ficam fixos
          enquanto vigoram e somem sozinhos quando a data passa. */}
      {comunicados.length > 0 && (
        <div className="card mb-4" style={{ border: "1px solid var(--dourado)" }}>
          <div className="card-header mb-3 flex items-center gap-2" style={{ color: "var(--dourado-light)" }}>
            <Megaphone size={15} /> Comunicados ({comunicados.length})
          </div>
          <div className="space-y-2">
            {comunicados.map((e: any) => (
              <div key={e.id} className="flex items-start justify-between gap-3" style={{ padding: "0.6rem 0.8rem", borderRadius: "var(--r-sm)", background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                <div>
                  <p style={{ fontSize: "0.83rem", fontWeight: 600 }}>{e.descricao}</p>
                  {e.observacao && <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>{e.observacao}</p>}
                </div>
                {/* Só o comunicado de NOVA DIETA leva à tela de dieta. A
                    condição era por categoria, e o alerta de sobra também sai
                    como "alimentacao" — então herdava este botão, que é
                    exatamente o atalho de lançamento que o alerta de sobra não
                    pode ter: ele é comunicado, resolve-se com o Check e nada
                    mais. */}
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

      {/* Linha do tempo unificada — Atrasados (antes de hoje) seguido de Hoje/
          próximos. A grade do mês agora só aparece como overlay dos
          indicadores (botão "Calendário" do cabeçalho, C3-C5) — este card
          não tem mais a pílula que trocava entre as duas visões. */}
      <div className="card">
        <div className="card-header mb-1 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          <span>Agenda ({eventosPendentes.length + eventosFuturos.length})</span>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            {!ate && (
              <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>próximos {DIAS_PADRAO_FUTURO} dias — defina "Até" para ampliar</span>
            )}
            <ExportarAgendaBotoes eventos={[...eventosPendentes, ...eventosFuturos]} />
          </div>
        </div>
        {loading ? (
          <p style={{ color: "var(--text-muted)", padding: "2rem", textAlign: "center" }}>Carregando agenda...</p>
        ) : (
          <div style={{ marginTop: "0.75rem" }}>
            <div className="flex items-center gap-2" style={{ color: "var(--dourado-light)", fontWeight: 700, fontSize: "0.8rem", margin: "0.6rem 0" }}>
              <Calendar size={14} /> Hoje · {new Date(hoje + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "long" })}
            </div>
            {eventosFuturos.length > 0 ? (
              <div className="space-y-2 mb-3">{renderEventos(eventosFuturos)}</div>
            ) : (
              <p style={{ color: "var(--text-muted)", padding: "1rem", textAlign: "center" }}>Nenhum evento no filtro atual.</p>
            )}
            {eventosPendentes.length > 0 && (
              <>
                <div className="flex items-center gap-2" style={{ color: "var(--red)", fontWeight: 700, fontSize: "0.8rem", margin: "0.6rem 0" }}>
                  <AlertTriangle size={14} /> Atrasados ({eventosPendentes.length})
                </div>
                <div className="space-y-2">{renderEventos(eventosPendentes, true)}</div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Estoque — alertas de saldo negativo/abaixo do mínimo, no final da
          página. Sempre visível (informação, não pendência a marcar como
          feita) — some sozinho quando o saldo normalizar. Cada item vira um
          quadro individual (mesmo estilo dos cartões da Capa): fundo ouro e
          contorno amarelo para abaixo do mínimo (mas ainda positivo); fundo
          vinho transparente e contorno vermelho para saldo zero/negativo. */}
      <div ref={estoqueAlertasRef} />
      {(estoqueNegativo.length > 0 || estoqueAbaixoMinimo.length > 0) && (
        <div className="card mt-4" style={{ border: "1px solid var(--red)" }}>
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

              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Categoria</label>
                <select
                  value={form.categoria}
                  onChange={e => setForm(p => ({ ...p, categoria: e.target.value }))}
                  style={{ width: "100%", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", color: "var(--text)", fontSize: "0.875rem" }}
                >
                  {CATEGORIAS.map(c => <option key={c}>{c}</option>)}
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

    </div>
  );
}
