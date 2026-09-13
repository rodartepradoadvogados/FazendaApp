"use client";
import React, { useEffect, useMemo, useState } from "react";
import { Plus } from "lucide-react";
import {
  fetchEventosSanitarios, fetchDoencas, fetchPrincipiosAtivos, fetchCalendarioSanitario, criarCalendarioSanitario,
  atualizarCalendarioSanitario, excluirCalendarioSanitario, fetchExames, atualizarEventoSanitario, criarEventoSanitario,
  criarExame, fetchEventosVidaVocabulario, fetchCategoriasManejo, fetchChecklistTemplate, fetchServicosCadastro, formatDate,
  type ChecklistTemplateItemDTO,
} from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { VIAS_APLICACAO } from "@/lib/constants";
import { EstoquePicker } from "@/components/EstoquePicker";
import { SecaoRecolhivel, MultiFiltro } from "@/components/ui";
import { Campo, inputStyle, nota, type EstoqueItem, unidadesCompativeis } from "@/components/lancamentos/comumForms";
import { FREQUENCIA_UNIDADES, type ExameDef } from "@/components/lancamentos/_shared";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { WizardProtocolo, type PassoWizard } from "@/components/protocolos/WizardProtocolo";

type EventoSanitarioDTO = {
  id: number; nome: string; ativo: boolean; categoria_preventiva: string | null; tipo_agendamento: string;
  doenca_id: number | null; doenca_nome: string | null; exame_definicao_id: number | null; exame_definicao_nome: string | null;
  produto_padrao: string | null; dose_padrao: number | null; unidade_padrao: string | null; via_padrao: string | null;
  veterinario_padrao_pessoa_id: number | null; veterinario_padrao_nome: string | null;
  gatilho: string | null; gatilho_lote: string | null; gatilho_idade_meses: number | null; offset_dias: number | null;
  janela_de_valor: number | null; janela_de_unidade: "dias" | "meses" | null;
  janela_ate_valor: number | null; janela_ate_unidade: "dias" | "meses" | null;
  acao_fora_janela: string | null; teto_etario_valor: number | null; teto_etario_unidade: "dias" | "meses" | null;
  servico_financeiro: string | null;
};
type OpcaoNomeAtivo = { id: number; nome: string; ativo: boolean };
type RegraCalendario = {
  id: number; evento_sanitario_id: number; evento_sanitario_nome: string;
  categoria_alvo: string | null; doenca_id: number | null; doenca_nome: string | null;
  produto: string | null; principio_ativo_id: number | null; principio_ativo_nome: string | null;
  dosagem: string | null; unidade: string | null; responsavel: string | null; veterinario: string | null;
  frequencia_valor: number; frequencia_unidade: string;
  data_evento: string; proxima_ocorrencia: string; observacao: string | null; ativo: boolean;
  categoria_preventiva: string | null; ultimo_evento_data: string | null; ultimo_evento_id: number | null;
  usa_cronograma?: boolean;
  checklist_itens?: ChecklistTemplateItemDTO[];
  // Regra por evento de vida não tem uma única "próxima ocorrência" — a data
  // calculada aqui é vestigial (bug relatado pelo usuário em 12/09/2026).
  proxima_ocorrencia_por_animal?: boolean;
};

// vacina | exame | tratamento | avulso/outro (nada marcado nos três primeiros) | todos.
const TIPOS_REGRA_FILTRO = [
  { v: "todos", l: "Todos" }, { v: "vacina", l: "Vacina" }, { v: "tratamento", l: "Tratamento" },
  { v: "exame", l: "Exame" }, { v: "avulso", l: "Avulso/outro" },
] as const;
export function tipoRegra(r: { categoria_preventiva: string | null }): "vacina" | "tratamento" | "exame" | "avulso" {
  if (r.categoria_preventiva === "exame") return "exame";
  if (r.categoria_preventiva === "tratamento") return "tratamento";
  if (r.categoria_preventiva === "vacina") return "vacina";
  return "avulso";
}
// Separador usado para guardar mais de uma categoria-alvo no mesmo campo
// (texto único no banco — cada regra continua com um único categoria_alvo).
const SEP_CATEGORIAS = ", ";

// ─────────────────────────── Wizard novo de 5 passos (redesenho do evento
// sanitário, docs/redesenho-evento-sanitario.md, seção 3.7.0) — substitui em
// bloco o wizard antigo de 4 passos (Identificação → Critérios → Roteiro →
// Revisão), que era a origem do bug de sobrescrita silenciosa no passo
// "Critérios". Passos novos:
//   1. Tipo — Vacina/Tratamento (mesmo bucket, mesmos campos) ou Exame.
//   2. Identificação — evento (selecionar ou criar) + doença + campos do tipo.
//   3. Critérios — categoria-alvo, disparo, veterinário/responsável. Escolher
//      um evento que já tem regra vinculada mostra um banner (fix do bug) em
//      vez de pré-preencher e sobrescrever em silêncio.
//   4. Checklist — nasce do template do tipo (3.7.3), ajustável só nesta regra.
//   5. Revisão — resumo + Salvar.
// ─────────────────────────────────────────────────────────────────────────
type TipoBucket = "vacina_tratamento" | "exame";
type ModoEvento = "existente" | "novo";
type CalendarioForm = {
  // Passo 1 — Tipo
  tipoBucket: TipoBucket;
  categoriaPreventiva: "vacina" | "tratamento";

  // Passo 2 — Identificação
  modoEvento: ModoEvento;
  eventoId: string; // preenchido depois de criar, se modoEvento === "novo"
  nomeNovoEvento: string;
  doencaId: string;
  produtoPadrao: string; dosePadrao: string; unidadePadrao: string; viaPadrao: string;
  modoExame: ModoEvento;
  exameDefinicaoId: string;
  novoExameNome: string; novoExameTipoResultado: "diagnostico" | "numerico";
  novoExameFaixaMin: string; novoExameFaixaMax: string;
  novoExameAcaoAbaixo: string; novoExameAcaoDentro: string; novoExameAcaoAcima: string;

  // Passo 3 — Critérios
  decisaoConflito: "editar" | "nova" | null;
  categoriaAlvoSel: string[];
  modoFreq: "periodica" | "evento_vida";
  freqValor: string; freqUnidade: string; dataEvento: string;
  gatilho: string; gatilhoLote: string; gatilhoIdadeMeses: string; offsetDias: string;
  janelaDeValor: string; janelaDeUnidade: "dias" | "meses";
  janelaAteValor: string; janelaAteUnidade: "dias" | "meses";
  acaoForaJanela: string;
  tetoEtarioValor: string; tetoEtarioUnidade: "dias" | "meses";
  veterinarioPadraoId: string;
  responsavel: string; veterinario: string;
  principioId: string; produto: string; dosagem: string; unidade: string;
  observacao: string; realizado: boolean; servicoFinanceiro: string;

  // Passo 4 — Checklist
  checklistItens: ChecklistTemplateItemDTO[];
};
const calendarioFormVazio = (): CalendarioForm => ({
  tipoBucket: "vacina_tratamento", categoriaPreventiva: "vacina",
  modoEvento: "existente", eventoId: "", nomeNovoEvento: "", doencaId: "",
  produtoPadrao: "", dosePadrao: "", unidadePadrao: "", viaPadrao: "",
  modoExame: "existente", exameDefinicaoId: "", novoExameNome: "", novoExameTipoResultado: "diagnostico",
  novoExameFaixaMin: "", novoExameFaixaMax: "", novoExameAcaoAbaixo: "", novoExameAcaoDentro: "", novoExameAcaoAcima: "",
  decisaoConflito: null, categoriaAlvoSel: [],
  modoFreq: "periodica", freqValor: "1", freqUnidade: "meses", dataEvento: "",
  gatilho: "nascimento", gatilhoLote: "", gatilhoIdadeMeses: "", offsetDias: "0",
  janelaDeValor: "", janelaDeUnidade: "meses", janelaAteValor: "", janelaAteUnidade: "meses",
  acaoForaJanela: "", tetoEtarioValor: "", tetoEtarioUnidade: "meses", veterinarioPadraoId: "",
  responsavel: "", veterinario: "", principioId: "", produto: "", dosagem: "", unidade: "",
  observacao: "", realizado: false, servicoFinanceiro: "",
  checklistItens: [],
});

export function FormCalendarioSanitario({ estoque }: { estoque: EstoqueItem[] }) {
  const [eventos, setEventos] = useState<EventoSanitarioDTO[]>([]);
  const [exames, setExames] = useState<ExameDef[]>([]);
  const [doencas, setDoencas] = useState<OpcaoNomeAtivo[]>([]);
  const [principios, setPrincipios] = useState<OpcaoNomeAtivo[]>([]);
  const [categoriasVida, setCategoriasVida] = useState<string[]>([]);
  const [servicos, setServicos] = useState<OpcaoNomeAtivo[]>([]);
  const [regras, setRegras] = useState<RegraCalendario[] | null>(null);
  const [tela, setTela] = useState<"lista" | "wizard">("lista");

  const [editando, setEditando] = useState<number | null>(null);
  const [form, setForm] = useState<CalendarioForm>(calendarioFormVazio());
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [tipoFiltroRegras, setTipoFiltroRegras] = useState<"todos" | "vacina" | "tratamento" | "exame" | "avulso">("todos");
  const regrasFiltradas = useMemo(
    () => (regras ?? []).filter((r) => tipoFiltroRegras === "todos" || tipoRegra(r) === tipoFiltroRegras),
    [regras, tipoFiltroRegras]
  );
  const ordRegras = useOrdenacao(regrasFiltradas);
  const ordEventos = useOrdenacao(eventos);

  const { pessoas: pessoasAtivas } = usePessoasAtivas();
  const veterinariosZootecnistas = useMemo(
    () => pessoasAtivas.filter((p) => (p.tipos || []).some((t: string) => ["Veterinário", "Zootecnista"].includes(t))),
    [pessoasAtivas]
  );
  const [gatilhosVida, setGatilhosVida] = useState<{ gatilho: string; rotulo: string }[]>([]);
  useEffect(() => { fetchEventosVidaVocabulario().then(setGatilhosVida).catch(() => {}); }, []);

  const carregarRegras = () => fetchCalendarioSanitario().then(setRegras).catch((e) => setErro(e.message));
  const carregarEventos = () => fetchEventosSanitarios().then(setEventos).catch(() => {});
  useEffect(() => {
    carregarEventos();
    fetchExames().then(setExames).catch(() => {});
    fetchDoencas().then((d) => setDoencas(d.filter((e: OpcaoNomeAtivo) => e.ativo))).catch(() => {});
    fetchPrincipiosAtivos().then((d) => setPrincipios(d.filter((e: OpcaoNomeAtivo) => e.ativo !== false))).catch(() => {});
    fetchCategoriasManejo().then((d) => setCategoriasVida(d.filter((c) => c.ativo).map((c) => c.nome))).catch(() => {});
    fetchServicosCadastro().then((d: OpcaoNomeAtivo[]) => setServicos(d.filter((s) => s.ativo !== false))).catch(() => {});
    carregarRegras();
  }, []);

  const eventosBucket = useMemo(
    () => eventos.filter((e) => e.ativo && (form.tipoBucket === "exame" ? e.categoria_preventiva === "exame" : e.categoria_preventiva !== "exame")),
    [eventos, form.tipoBucket]
  );
  const eventoSel = eventos.find((e) => String(e.id) === form.eventoId);
  const ehExame = form.tipoBucket === "exame";
  // Regra já vinculada a este evento (fix do bug — seção 3.7.0): só conta
  // quando estamos CRIANDO (editando uma regra já traz seus próprios dados,
  // não há nada a sobrescrever em silêncio).
  const regraVinculada = editando === null && form.eventoId
    ? (regras ?? []).find((r) => r.evento_sanitario_id === Number(form.eventoId))
    : undefined;
  const temConflito = !!regraVinculada && form.decisaoConflito === null;

  const limpar = () => { setEditando(null); setForm(calendarioFormVazio()); };

  // Checklist padrão do tipo — ponto de partida do passo 4 (seção 3.7.3),
  // recarregado sempre que o bucket muda NUMA REGRA NOVA sem checklist ainda
  // tocado manualmente (editar uma regra existente usa o que já foi salvo
  // para ela, carregado em `abrirEdicao`, e nunca é sobrescrito por aqui).
  // `wizardAberturaId` muda a cada "+ Nova regra" — sem ele, abrir uma
  // segunda regra nova depois de já ter aberto (e fechado) uma primeira não
  // dispara o efeito de novo (ehExame/editando/checklistTocado já estavam
  // nesses mesmos valores desde a primeira vez), e o passo Checklist nasce
  // vazio em silêncio.
  const [checklistTocado, setChecklistTocado] = useState(false);
  const [wizardAberturaId, setWizardAberturaId] = useState(0);
  useEffect(() => {
    if (editando !== null) return;
    if (checklistTocado) return;
    fetchChecklistTemplate(ehExame ? "exame" : "vacina")
      .then((itens) => setForm((f) => ({ ...f, checklistItens: itens })))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ehExame, editando, checklistTocado, wizardAberturaId]);

  const abrirEdicao = (r: RegraCalendario) => {
    setEditando(r.id);
    setChecklistTocado(true); // edição usa o que já foi salvo — nunca recarrega do template
    const ev = eventos.find((e) => e.id === r.evento_sanitario_id);
    const bucket: TipoBucket = ev?.categoria_preventiva === "exame" ? "exame" : "vacina_tratamento";
    setForm((f) => ({
      ...f,
      tipoBucket: bucket, categoriaPreventiva: ev?.categoria_preventiva === "tratamento" ? "tratamento" : "vacina",
      modoEvento: "existente", eventoId: String(r.evento_sanitario_id),
      doencaId: r.doenca_id ? String(r.doenca_id) : "",
      produtoPadrao: ev?.produto_padrao || "", dosePadrao: ev?.dose_padrao != null ? String(ev.dose_padrao) : "",
      unidadePadrao: ev?.unidade_padrao || "", viaPadrao: ev?.via_padrao || "",
      modoExame: "existente", exameDefinicaoId: ev?.exame_definicao_id ? String(ev.exame_definicao_id) : "",
      decisaoConflito: "editar", // editando de verdade — não há banner a resolver
      categoriaAlvoSel: r.categoria_alvo ? r.categoria_alvo.split(SEP_CATEGORIAS).map((c) => c.trim()).filter(Boolean) : [],
      modoFreq: ev?.tipo_agendamento === "evento" ? "evento_vida" : "periodica",
      gatilho: ev?.gatilho || "nascimento", gatilhoLote: ev?.gatilho_lote || "",
      gatilhoIdadeMeses: ev?.gatilho_idade_meses ? String(ev.gatilho_idade_meses) : "",
      offsetDias: ev?.offset_dias != null ? String(ev.offset_dias) : "0",
      janelaDeValor: ev?.janela_de_valor != null ? String(ev.janela_de_valor) : "", janelaDeUnidade: ev?.janela_de_unidade || "meses",
      janelaAteValor: ev?.janela_ate_valor != null ? String(ev.janela_ate_valor) : "", janelaAteUnidade: ev?.janela_ate_unidade || "meses",
      acaoForaJanela: ev?.acao_fora_janela || "",
      tetoEtarioValor: ev?.teto_etario_valor != null ? String(ev.teto_etario_valor) : "", tetoEtarioUnidade: ev?.teto_etario_unidade || "meses",
      veterinarioPadraoId: ev?.veterinario_padrao_pessoa_id ? String(ev.veterinario_padrao_pessoa_id) : "",
      freqValor: String(r.frequencia_valor), freqUnidade: r.frequencia_unidade, dataEvento: r.data_evento,
      responsavel: r.responsavel || "", veterinario: r.veterinario || "",
      principioId: r.principio_ativo_id ? String(r.principio_ativo_id) : "", produto: r.produto || "",
      dosagem: r.dosagem || "", unidade: r.unidade || "", observacao: r.observacao || "", realizado: false,
      servicoFinanceiro: ev?.servico_financeiro || "",
      checklistItens: r.checklist_itens && r.checklist_itens.length ? r.checklist_itens : f.checklistItens,
    }));
    setTela("wizard");
  };

  const novaRegra = () => { limpar(); setChecklistTocado(false); setWizardAberturaId((n) => n + 1); setTela("wizard"); };

  const excluir = async (r: RegraCalendario) => {
    if (!window.confirm(`Excluir a regra do calendário "${r.evento_sanitario_nome}" de ${formatDate(r.data_evento)}?`)) return;
    try { await excluirCalendarioSanitario(r.id); carregarRegras(); }
    catch (e: any) { setErro(e.message); }
  };

  const precisaCicloRegra = form.modoFreq === "periodica";

  async function salvar(): Promise<boolean> {
    setErro(null); setSucesso(null);
    setSalvando(true);
    try {
      // Passo 2 — garante que o evento sanitário exista (cria ou atualiza).
      let eventoId = form.eventoId;
      const dadosEvento = {
        categoria_preventiva: ehExame ? "exame" : form.categoriaPreventiva,
        doenca_id: form.doencaId ? Number(form.doencaId) : undefined,
        // "periodica": NÃO é "epoca" — a periodicidade mora só na regra
        // (CalendarioSanitario.frequencia_valor/unidade), nunca também aqui.
        // Achado real na reverificação E2E de 13/09/2026: gravar "epoca" +
        // data_primeiro/frequencia_* no EventoSanitario ao mesmo tempo que a
        // regra cria o MESMO agendamento duplicado (ver eventos_agenda() no
        // backend) — e pior, excluir a regra depois não apaga essa cópia: o
        // evento continua "ativo" com o próprio agendamento e a pendência
        // RESSUSCITA na Agenda (com o texto genérico antigo, sem categoria-
        // alvo), mesmo com a regra já sumida de "Regras cadastradas".
        tipo_agendamento: (form.modoFreq === "evento_vida" ? "evento" : "nenhum") as "evento" | "nenhum",
        gatilho: form.modoFreq === "evento_vida" ? form.gatilho : undefined,
        gatilho_lote: form.modoFreq === "evento_vida" && form.gatilho === "entrada_lote" ? form.gatilhoLote.trim() : undefined,
        gatilho_idade_meses: form.modoFreq === "evento_vida" && form.gatilho === "novilha_apta" ? Number(form.gatilhoIdadeMeses) : undefined,
        offset_dias: form.modoFreq === "evento_vida" ? (form.offsetDias ? Number(form.offsetDias) : 0) : undefined,
        produto_padrao: ehExame ? undefined : (form.produtoPadrao || undefined),
        dose_padrao: ehExame ? undefined : (form.dosePadrao ? Number(form.dosePadrao) : undefined),
        unidade_padrao: ehExame ? undefined : (form.unidadePadrao || undefined),
        via_padrao: ehExame ? undefined : (form.viaPadrao || undefined),
        exame_definicao_id: ehExame && form.exameDefinicaoId ? Number(form.exameDefinicaoId) : undefined,
        janela_de_valor: form.modoFreq === "evento_vida" && form.janelaDeValor ? Number(form.janelaDeValor) : undefined,
        janela_de_unidade: form.modoFreq === "evento_vida" && form.janelaDeValor ? form.janelaDeUnidade : undefined,
        janela_ate_valor: form.modoFreq === "evento_vida" && form.janelaAteValor ? Number(form.janelaAteValor) : undefined,
        janela_ate_unidade: form.modoFreq === "evento_vida" && form.janelaAteValor ? form.janelaAteUnidade : undefined,
        acao_fora_janela: form.modoFreq === "evento_vida" ? (form.acaoForaJanela || undefined) : undefined,
        teto_etario_valor: form.modoFreq === "evento_vida" && form.tetoEtarioValor ? Number(form.tetoEtarioValor) : undefined,
        teto_etario_unidade: form.modoFreq === "evento_vida" && form.tetoEtarioValor ? form.tetoEtarioUnidade : undefined,
        veterinario_padrao_pessoa_id: form.veterinarioPadraoId ? Number(form.veterinarioPadraoId) : undefined,
        servico_financeiro: form.servicoFinanceiro || undefined,
      };
      if (form.modoEvento === "novo") {
        const novo = await criarEventoSanitario({ nome: form.nomeNovoEvento.trim(), ...dadosEvento });
        eventoId = String(novo.id);
      } else {
        await atualizarEventoSanitario(Number(eventoId), { nome: eventoSel!.nome, ativo: true, ...dadosEvento });
      }

      const dadosRegra = {
        evento_sanitario_id: Number(eventoId),
        categoria_alvo: form.categoriaAlvoSel.length ? form.categoriaAlvoSel.join(SEP_CATEGORIAS) : undefined,
        doenca_id: form.doencaId ? Number(form.doencaId) : undefined,
        produto: ehExame ? undefined : (form.produto || undefined),
        principio_ativo_id: ehExame ? undefined : (form.principioId ? Number(form.principioId) : undefined),
        dosagem: ehExame ? undefined : (form.dosagem || undefined),
        unidade: ehExame ? undefined : (form.unidade || undefined),
        responsavel: form.responsavel || undefined,
        veterinario: form.veterinario || undefined,
        frequencia_valor: Number(form.freqValor) || 1, frequencia_unidade: form.freqUnidade,
        data_evento: form.dataEvento || new Date().toISOString().slice(0, 10),
        observacao: form.observacao || undefined, realizado: form.realizado,
        checklist_itens: form.checklistItens,
      };
      if (editando) await atualizarCalendarioSanitario(editando, dadosRegra);
      else await criarCalendarioSanitario(dadosRegra);
      setSucesso(editando ? "Regra atualizada com sucesso." : "Regra do calendário sanitário criada com sucesso.");
      limpar();
      setChecklistTocado(false);
      carregarEventos();
      carregarRegras();
      setTela("lista");
      return true;
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar a regra do calendário sanitário");
      return false;
    } finally {
      setSalvando(false);
    }
  }

  async function criarExameInline(f: CalendarioForm, sf: (f: CalendarioForm) => void) {
    try {
      const ex = await criarExame({
        nome: f.novoExameNome.trim(), tipo_resultado: f.novoExameTipoResultado,
        faixa_min: f.novoExameTipoResultado === "numerico" ? Number(f.novoExameFaixaMin) : undefined,
        faixa_max: f.novoExameTipoResultado === "numerico" ? Number(f.novoExameFaixaMax) : undefined,
        acao_abaixo: f.novoExameAcaoAbaixo || undefined, acao_dentro: f.novoExameAcaoDentro || undefined,
        acao_acima: f.novoExameAcaoAcima || undefined,
      });
      setExames((prev) => [...prev, ex]);
      sf({ ...f, exameDefinicaoId: String(ex.id), modoExame: "existente" });
    } catch (e: any) {
      setErro(e.message || "Erro ao cadastrar o exame");
    }
  }

  const passos: PassoWizard<CalendarioForm>[] = [
    {
      id: "tipo", titulo: "Tipo",
      render: ({ form: f, setForm: sf }) => (
        <div>
          <p style={nota}>Vacina e Tratamento usam exatamente os mesmos campos — só Exame é diferente (sem produto/dose/via, sem baixa de estoque).</p>
          <div className="flex items-center gap-2 mt-3">
            <button type="button" className={f.tipoBucket === "vacina_tratamento" ? "btn-primary" : "btn-secondary"}
              onClick={() => sf({ ...f, tipoBucket: "vacina_tratamento" })}>Vacina / Tratamento</button>
            <button type="button" className={f.tipoBucket === "exame" ? "btn-primary" : "btn-secondary"}
              onClick={() => sf({ ...f, tipoBucket: "exame", modoEvento: "existente", eventoId: "" })}>Exame</button>
          </div>
          {f.tipoBucket === "vacina_tratamento" && (
            <div className="flex items-center gap-4 mt-3" style={{ fontSize: "0.85rem" }}>
              <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
                <input type="radio" checked={f.categoriaPreventiva === "vacina"} onChange={() => sf({ ...f, categoriaPreventiva: "vacina" })} /> Vacina
              </label>
              <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
                <input type="radio" checked={f.categoriaPreventiva === "tratamento"} onChange={() => sf({ ...f, categoriaPreventiva: "tratamento" })} /> Tratamento
              </label>
            </div>
          )}
        </div>
      ),
    },
    {
      id: "identificacao", titulo: "Identificação",
      validar: (f) => {
        if (f.modoEvento === "existente" && !f.eventoId) return "Selecione o evento sanitário, ou escolha \"Criar novo\".";
        if (f.modoEvento === "novo" && !f.nomeNovoEvento.trim()) return "Informe o nome do novo evento.";
        if (f.tipoBucket === "exame" && f.modoExame === "existente" && !f.exameDefinicaoId) return "Selecione o exame, ou escolha \"Criar novo\".";
        if (f.tipoBucket === "exame" && f.modoExame === "novo" && !f.novoExameNome.trim()) return "Informe o nome do novo exame.";
        return null;
      },
      render: ({ form: f, setForm: sf }) => (
        <div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Campo label="Evento sanitário" full>
              <div className="flex items-center gap-2 mb-2">
                <button type="button" className={f.modoEvento === "existente" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.75rem" }}
                  onClick={() => sf({ ...f, modoEvento: "existente" })}>Selecionar existente</button>
                <button type="button" className={f.modoEvento === "novo" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.75rem" }}
                  onClick={() => sf({ ...f, modoEvento: "novo", eventoId: "", decisaoConflito: null })}><Plus size={13} /> Criar novo</button>
              </div>
              {f.modoEvento === "existente" ? (
                <select style={inputStyle} value={f.eventoId} onChange={(e) => sf({ ...f, eventoId: e.target.value, decisaoConflito: null })}>
                  <option value="">Selecione…</option>
                  {eventosBucket.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
                </select>
              ) : (
                <input style={inputStyle} value={f.nomeNovoEvento} onChange={(e) => sf({ ...f, nomeNovoEvento: e.target.value })} placeholder="ex.: Brucelose B19" />
              )}
            </Campo>
            <Campo label="Doença combatida">
              <select style={inputStyle} value={f.doencaId} onChange={(e) => sf({ ...f, doencaId: e.target.value })}>
                <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
              </select>
            </Campo>
          </div>
          {f.tipoBucket === "exame" ? (
            <div className="mt-3" style={{ paddingTop: "0.75rem", borderTop: "1px solid var(--border)" }}>
              <Campo label="Exame (define como o resultado é lançado)" full>
                <div className="flex items-center gap-2 mb-2">
                  <button type="button" className={f.modoExame === "existente" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.75rem" }}
                    onClick={() => sf({ ...f, modoExame: "existente" })}>Selecionar existente</button>
                  <button type="button" className={f.modoExame === "novo" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.75rem" }}
                    onClick={() => sf({ ...f, modoExame: "novo" })}><Plus size={13} /> Criar novo</button>
                </div>
                {f.modoExame === "existente" ? (
                  <select style={inputStyle} value={f.exameDefinicaoId} onChange={(e) => sf({ ...f, exameDefinicaoId: e.target.value })}>
                    <option value="">Selecione…</option>
                    {exames.map((ex) => <option key={ex.id} value={ex.id}>{ex.nome}</option>)}
                  </select>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Campo label="Nome do exame"><input style={inputStyle} value={f.novoExameNome} onChange={(e) => sf({ ...f, novoExameNome: e.target.value })} /></Campo>
                    <Campo label="Tipo de resultado">
                      <select style={inputStyle} value={f.novoExameTipoResultado} onChange={(e) => sf({ ...f, novoExameTipoResultado: e.target.value as "diagnostico" | "numerico" })}>
                        <option value="diagnostico">Diagnóstico (positivo/negativo/indefinido)</option>
                        <option value="numerico">Numérico (faixa)</option>
                      </select>
                    </Campo>
                    {f.novoExameTipoResultado === "numerico" && (
                      <>
                        <Campo label="Faixa mínima"><input type="number" style={inputStyle} value={f.novoExameFaixaMin} onChange={(e) => sf({ ...f, novoExameFaixaMin: e.target.value })} /></Campo>
                        <Campo label="Faixa máxima"><input type="number" style={inputStyle} value={f.novoExameFaixaMax} onChange={(e) => sf({ ...f, novoExameFaixaMax: e.target.value })} /></Campo>
                        <Campo label="Conduta abaixo da faixa"><input style={inputStyle} value={f.novoExameAcaoAbaixo} onChange={(e) => sf({ ...f, novoExameAcaoAbaixo: e.target.value })} /></Campo>
                        <Campo label="Conduta dentro da faixa"><input style={inputStyle} value={f.novoExameAcaoDentro} onChange={(e) => sf({ ...f, novoExameAcaoDentro: e.target.value })} /></Campo>
                        <Campo label="Conduta acima da faixa"><input style={inputStyle} value={f.novoExameAcaoAcima} onChange={(e) => sf({ ...f, novoExameAcaoAcima: e.target.value })} /></Campo>
                      </>
                    )}
                    <div style={{ gridColumn: "1 / -1" }}>
                      <button type="button" className="btn-secondary" style={{ fontSize: "0.75rem" }} disabled={!f.novoExameNome.trim()}
                        onClick={() => criarExameInline(f, sf)}>Cadastrar este exame agora</button>
                      <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>Cadastra o exame já, sem sair do wizard — depois escolha-o em "Selecionar existente".</p>
                    </div>
                  </div>
                )}
              </Campo>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3" style={{ paddingTop: "0.75rem", borderTop: "1px solid var(--border)" }}>
              <Campo label="Produto padrão (opcional)"><EstoquePicker itens={estoque} value={f.produtoPadrao} onChange={(v) => sf({ ...f, produtoPadrao: v })} /></Campo>
              <Campo label="Dose padrão (opcional)"><input type="number" style={inputStyle} value={f.dosePadrao} onChange={(e) => sf({ ...f, dosePadrao: e.target.value })} /></Campo>
              <Campo label="Via padrão (opcional)">
                <select style={inputStyle} value={f.viaPadrao} onChange={(e) => sf({ ...f, viaPadrao: e.target.value })}>
                  <option value="">—</option>
                  {/* Regra antiga com via em texto livre (antes desta correção) continua aparecendo, mesmo fora da lista fixa. */}
                  {!VIAS_APLICACAO.includes(f.viaPadrao) && f.viaPadrao && <option value={f.viaPadrao}>{f.viaPadrao}</option>}
                  {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </Campo>
              <p style={{ gridColumn: "1 / -1", fontSize: "0.7rem", color: "var(--text-muted)" }}>Opcionais — a regra (próximo passo) e a realização ainda podem sobrescrever.</p>
            </div>
          )}
        </div>
      ),
    },
    {
      id: "criterios", titulo: "Critérios",
      validar: (f) => {
        if (regraVinculada && f.decisaoConflito === null) return "Escolha uma das opções acima antes de continuar.";
        const precisaCiclo = f.modoFreq === "periodica";
        if (precisaCiclo && (!f.dataEvento || !f.freqValor)) return "Selecione a frequência e a data do evento.";
        if (f.modoFreq === "evento_vida" && f.gatilho === "entrada_lote" && !f.gatilhoLote.trim()) return "Informe o lote do gatilho (entrada no lote).";
        if (f.modoFreq === "evento_vida" && f.gatilho === "novilha_apta" && !f.gatilhoIdadeMeses) return "Informe a idade-alvo em meses (aptidão de novilha).";
        if (f.realizado && f.dataEvento && f.dataEvento > new Date().toISOString().slice(0, 10))
          return "Só é possível marcar como realizado um evento de hoje ou retroativo — a data informada é futura.";
        return null;
      },
      render: ({ form: f, setForm: sf }) => {
        if (regraVinculada && f.decisaoConflito === null) {
          return (
            <div style={{ padding: "0.9rem 1rem", borderRadius: 10, border: "1.5px solid var(--dourado)", background: "rgba(212,175,55,0.1)" }}>
              <p style={{ fontSize: "0.85rem", fontWeight: 700, marginBottom: "0.4rem" }}>Este evento já tem uma regra cadastrada</p>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>
                {regraVinculada.categoria_alvo || "Rebanho todo"} — próxima ocorrência{" "}
                {regraVinculada.proxima_ocorrencia_por_animal ? "calculada por animal (evento de vida)" : formatDate(regraVinculada.proxima_ocorrencia)}. Nada foi alterado.
              </p>
              <div className="flex items-center gap-2">
                <button type="button" className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={() => abrirEdicao(regraVinculada)}>Editar essa regra</button>
                <button type="button" className="btn-secondary" style={{ fontSize: "0.8rem" }} onClick={() => sf({ ...f, decisaoConflito: "nova" })}>Criar uma regra nova mesmo assim</button>
              </div>
            </div>
          );
        }
        return (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Campo label="Categoria(s) alvo (período de vida)" full>
              <MultiFiltroCategorias categoriasVida={categoriasVida} f={f} sf={sf} />
            </Campo>
            <Campo label="Repetir por" full>
              <div className="flex items-center gap-4" style={{ fontSize: "0.85rem" }}>
                <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
                  <input type="radio" checked={f.modoFreq === "periodica"} onChange={() => sf({ ...f, modoFreq: "periodica" })} /> Frequência periódica
                </label>
                <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
                  <input type="radio" checked={f.modoFreq === "evento_vida"} onChange={() => sf({ ...f, modoFreq: "evento_vida" })} /> Evento de vida do animal
                </label>
              </div>
            </Campo>
            {f.modoFreq === "evento_vida" ? (
              <>
                <Campo label="Evento de vida">
                  <select style={inputStyle} value={f.gatilho} onChange={(e) => sf({ ...f, gatilho: e.target.value })}>
                    {gatilhosVida.map((g) => <option key={g.gatilho} value={g.gatilho}>{g.rotulo}</option>)}
                  </select>
                </Campo>
                {f.gatilho === "entrada_lote" && (
                  <Campo label="Lote do gatilho"><input style={inputStyle} value={f.gatilhoLote} onChange={(e) => sf({ ...f, gatilhoLote: e.target.value })} placeholder="ex.: PRE_PARTO" /></Campo>
                )}
                {f.gatilho === "novilha_apta" && (
                  <Campo label="Idade-alvo (meses)"><input type="number" min={1} style={inputStyle} value={f.gatilhoIdadeMeses} onChange={(e) => sf({ ...f, gatilhoIdadeMeses: e.target.value })} placeholder="ex.: 13" /></Campo>
                )}
                {!f.janelaDeValor && (
                  <Campo label="Dias após o gatilho"><input type="number" style={inputStyle} value={f.offsetDias} onChange={(e) => sf({ ...f, offsetDias: e.target.value })} /></Campo>
                )}
                <Campo label="Janela — de">
                  <div className="flex items-center gap-2">
                    <input type="number" min={0} style={inputStyle} value={f.janelaDeValor} onChange={(e) => sf({ ...f, janelaDeValor: e.target.value })} placeholder="3" />
                    <select style={inputStyle} value={f.janelaDeUnidade} onChange={(e) => sf({ ...f, janelaDeUnidade: e.target.value as "dias" | "meses" })}>
                      <option value="dias">dias</option><option value="meses">meses</option>
                    </select>
                  </div>
                </Campo>
                <Campo label="Janela — até">
                  <div className="flex items-center gap-2">
                    <input type="number" min={0} style={inputStyle} value={f.janelaAteValor} onChange={(e) => sf({ ...f, janelaAteValor: e.target.value })} placeholder="8" />
                    <select style={inputStyle} value={f.janelaAteUnidade} onChange={(e) => sf({ ...f, janelaAteUnidade: e.target.value as "dias" | "meses" })}>
                      <option value="dias">dias</option><option value="meses">meses</option>
                    </select>
                  </div>
                </Campo>
                <Campo label="Ação ao sair da janela sem aplicação" full>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    {([
                      ["sair", "Sair", "Encerra — passa a constar como lacuna permanente no histórico"],
                      ["manter", "Manter até aplicação", "Continua pendente, mesmo fora da janela biológica"],
                      ["notificar", "Notificar urgência", "Fecha em N dias — alerta antes de sair"],
                    ] as const).map(([v, lblTxt, desc]) => (
                      <button key={v} type="button" onClick={() => sf({ ...f, acaoForaJanela: v })}
                        style={{ textAlign: "left", padding: "0.55rem 0.65rem", borderRadius: 8, cursor: "pointer",
                          border: "1.5px solid " + (f.acaoForaJanela === v ? "var(--dourado)" : "var(--border)"),
                          background: f.acaoForaJanela === v ? "rgba(94,26,46,0.25)" : "transparent" }}>
                        <span style={{ display: "block", fontSize: "0.78rem", fontWeight: 700, color: f.acaoForaJanela === v ? "var(--dourado-light)" : "var(--text)" }}>{lblTxt}</span>
                        <span style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.1rem" }}>{desc}</span>
                      </button>
                    ))}
                  </div>
                </Campo>
                <Campo label="Teto etário (opcional)">
                  <div className="flex items-center gap-2">
                    <input type="number" min={0} style={inputStyle} value={f.tetoEtarioValor} onChange={(e) => sf({ ...f, tetoEtarioValor: e.target.value })} placeholder="8" />
                    <select style={inputStyle} value={f.tetoEtarioUnidade} onChange={(e) => sf({ ...f, tetoEtarioUnidade: e.target.value as "dias" | "meses" })}>
                      <option value="dias">dias</option><option value="meses">meses</option>
                    </select>
                  </div>
                </Campo>
              </>
            ) : (
              <>
                <Campo label="Frequência">
                  <div className="flex items-center gap-2">
                    <input type="number" min={1} style={inputStyle} value={f.freqValor} onChange={(e) => sf({ ...f, freqValor: e.target.value })} />
                    <select style={inputStyle} value={f.freqUnidade} onChange={(e) => sf({ ...f, freqUnidade: e.target.value })}>
                      {FREQUENCIA_UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}
                    </select>
                  </div>
                </Campo>
                <Campo label="Data do evento (referência)"><input type="date" style={inputStyle} value={f.dataEvento} onChange={(e) => sf({ ...f, dataEvento: e.target.value })} /></Campo>
              </>
            )}
            <Campo label="Veterinário padrão">
              <select style={inputStyle} value={f.veterinarioPadraoId} onChange={(e) => sf({ ...f, veterinarioPadraoId: e.target.value })}>
                <option value="">— (escolher na hora)</option>
                {veterinariosZootecnistas.map((p: any) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select>
            </Campo>
            <Campo label="Responsável">
              <select style={inputStyle} value={f.responsavel} onChange={(e) => sf({ ...f, responsavel: e.target.value })}>
                <option value="">Opcional</option>
                {pessoasAtivas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
              </select>
            </Campo>
            {ehExame ? (
              <Campo label="Veterinário (exame)">
                <select style={inputStyle} value={f.veterinario} onChange={(e) => sf({ ...f, veterinario: e.target.value })}>
                  <option value="">Opcional</option>
                  {veterinariosZootecnistas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
                </select>
              </Campo>
            ) : (
              <>
                <Campo label="Princípio ativo">
                  <select style={inputStyle} value={f.principioId} onChange={(e) => sf({ ...f, principioId: e.target.value })}>
                    <option value="">—</option>{principios.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                  </select>
                </Campo>
                <Campo label="Produto (item de estoque)">
                  <EstoquePicker itens={estoque} value={f.produto} onChange={(v) => sf({ ...f, produto: v })} />
                </Campo>
                <Campo label="Dosagem"><input style={inputStyle} value={f.dosagem} onChange={(e) => sf({ ...f, dosagem: e.target.value })} placeholder="ex.: 2 mL a 5 mL (conforme bula)" /></Campo>
                <Campo label="Unidade">
                  <select style={inputStyle} value={f.unidade} onChange={(e) => sf({ ...f, unidade: e.target.value })}>
                    <option value="">—</option>
                    {unidadesCompativeis(estoque.find((e) => e.nome === f.produto)?.unidade).map((u) => <option key={u}>{u}</option>)}
                  </select>
                </Campo>
              </>
            )}
            <Campo label="Serviço financeiro (opcional)">
              <select style={inputStyle} value={f.servicoFinanceiro} onChange={(e) => sf({ ...f, servicoFinanceiro: e.target.value })}>
                <option value="">— (sem botão "Lançar financeiro" no calendário)</option>
                {servicos.map((s) => <option key={s.id} value={s.nome}>{s.nome}</option>)}
              </select>
            </Campo>
            <Campo label="Observação" full><input style={inputStyle} value={f.observacao} onChange={(e) => sf({ ...f, observacao: e.target.value })} /></Campo>
            {f.modoFreq === "periodica" && (
              <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", gridColumn: "1 / -1" }}>
                <input type="checkbox" checked={f.realizado} onChange={(e) => sf({ ...f, realizado: e.target.checked })} /> Já foi realizado (não entra como pendência na Agenda)
              </label>
            )}
          </div>
        );
      },
    },
    {
      id: "checklist", titulo: "Checklist",
      render: ({ form: f, setForm: sf }) => (
        <PassoChecklist f={f} sf={sf} onTocado={() => setChecklistTocado(true)} />
      ),
    },
    {
      id: "revisao", titulo: "Revisão",
      render: ({ form: f }) => {
        const nomeEvento = f.modoEvento === "novo" ? f.nomeNovoEvento : eventos.find((e) => String(e.id) === f.eventoId)?.nome;
        return (
          <div>
            <p style={{ fontSize: "0.82rem", marginBottom: "0.6rem" }}><strong>{nomeEvento || "(sem evento)"}</strong></p>
            <ul style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: 1.9, paddingLeft: "1.1rem" }}>
              <li>Tipo: {ehExame ? "Exame" : f.categoriaPreventiva === "tratamento" ? "Tratamento" : "Vacina"}</li>
              <li>Categoria(s) alvo: {f.categoriaAlvoSel.join(", ") || "—"}</li>
              <li>Doença: {doencas.find((d) => String(d.id) === f.doencaId)?.nome || "—"}</li>
              <li>Repete por: {f.modoFreq === "periodica" ? `a cada ${f.freqValor} ${FREQUENCIA_UNIDADES.find((u) => u.v === f.freqUnidade)?.l}` : `evento de vida (${gatilhosVida.find((g) => g.gatilho === f.gatilho)?.rotulo || f.gatilho})`}</li>
              <li>Veterinário padrão: {veterinariosZootecnistas.find((p: any) => String(p.id) === f.veterinarioPadraoId)?.nome || "—"}</li>
              <li>Serviço financeiro: {f.servicoFinanceiro || "—"}</li>
              <li>Itens do checklist: {f.checklistItens.length}</li>
            </ul>
          </div>
        );
      },
    },
  ];

  if (tela === "lista") {
    return (
      <ListaEntradaCadastroSanitario
        eventos={eventos} regras={regras} ordEventos={ordEventos} ordRegras={ordRegras}
        tipoFiltroRegras={tipoFiltroRegras} setTipoFiltroRegras={setTipoFiltroRegras}
        onNovo={novaRegra} onEditarEvento={(ev) => {
          limpar(); setChecklistTocado(false); setWizardAberturaId((n) => n + 1);
          setForm((f) => ({ ...f, tipoBucket: ev.categoria_preventiva === "exame" ? "exame" : "vacina_tratamento", eventoId: String(ev.id) }));
          setTela("wizard");
        }}
        onEditarRegra={abrirEdicao} onExcluirRegra={excluir}
      />
    );
  }

  return (
    <>
      <WizardProtocolo<CalendarioForm>
        key={editando ?? "novo"}
        chaveRascunho={editando === null ? "wizard-protocolo:sanitario-preventivo" : null}
        form={form} setForm={setForm}
        ehVazio={(f) => f.modoEvento === "existente" && !f.eventoId && !f.nomeNovoEvento.trim()}
        passos={passos}
        onCancelar={() => { limpar(); setChecklistTocado(false); setTela("lista"); }}
        onConcluir={salvar}
        salvando={salvando}
        rotuloConcluir={editando ? "Salvar alterações" : "Salvar"}
        erro={erro}
        tituloTopo={editando ? "Editando regra do calendário sanitário" : "Nova regra do calendário sanitário"}
      />
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
    </>
  );
}

// Extraído para não redeclarar o componente de multi-seleção de categorias a
// cada render do passo "Critérios" (mesma lógica do wizard antigo).
function MultiFiltroCategorias({ categoriasVida, f, sf }: { categoriasVida: string[]; f: CalendarioForm; sf: (f: CalendarioForm) => void }) {
  return (
    <MultiFiltro
      label="Categorias" opcoes={Array.from(new Set([...categoriasVida, ...f.categoriaAlvoSel]))}
      selecionados={f.categoriaAlvoSel} onChange={(v: string[]) => sf({ ...f, categoriaAlvoSel: v })}
      permitirNovo placeholderNovo="+ outra categoria…"
      onAdicionarNovo={(v: string) => sf({ ...f, categoriaAlvoSel: Array.from(new Set([...f.categoriaAlvoSel, v])) })}
    />
  );
}

/**
 * Seletor de evento preventivo com a pergunta "vacina ou exame" na frente —
 * usado no lançamento de Aplicações (FormPreventivoAplicacao) para o fluxo
 * "Avulso" (aplicação sem uma regra do calendário por trás). O wizard de
 * Cadastro (acima) não usa mais este componente — ele tem seu próprio passo
 * "Tipo"/"Identificação" com o fix do bug de sobrescrita silenciosa — mas ele
 * continua aqui, inalterado, porque outras telas dependem dele.
 * Ao escolher um exame que ainda não tem um evento sanitário vinculado, cria
 * esse vínculo na hora (transparente para o usuário) para que o exame
 * cadastrado (Central de Protocolos > Cadastro > Sanitário > Exames) fique
 * selecionável aqui sem precisar de um cadastro de evento à parte.
 */
export function SeletorEventoPreventivo({ eventos, exames, eventoId, onEventoId, onEventosRecarregados }: {
  eventos: { id: number; nome: string }[]; exames: ExameDef[]; eventoId: string;
  onEventoId: (id: string) => void; onEventosRecarregados: () => void;
}) {
  const [tipo, setTipo] = useState<"" | "vacina" | "exame">("");
  const [vinculando, setVinculando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const ev = eventos.find((e) => String(e.id) === eventoId) as any;
    if (ev) setTipo(ev.categoria_preventiva === "exame" ? "exame" : "vacina");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventoId]);

  const eventosVacina = eventos.filter((e) => (e as any).categoria_preventiva !== "exame");
  const eventoAtual = eventos.find((e) => String(e.id) === eventoId) as any;
  const exameSelId = eventoAtual?.exame_definicao_id ? String(eventoAtual.exame_definicao_id) : "";

  async function escolherExame(exameDefId: string) {
    setErro(null);
    if (!exameDefId) { onEventoId(""); return; }
    const jaVinculado = eventos.find((e) => String((e as any).exame_definicao_id) === exameDefId);
    if (jaVinculado) { onEventoId(String(jaVinculado.id)); return; }
    const ex = exames.find((x) => String(x.id) === exameDefId);
    if (!ex) return;
    setVinculando(true);
    try {
      const novo = await criarEventoSanitario({ nome: ex.nome, categoria_preventiva: "exame", exame_definicao_id: ex.id, tipo_agendamento: "nenhum" });
      onEventosRecarregados();
      onEventoId(String(novo.id));
    } catch (e: any) {
      setErro(e.message || "Erro ao vincular este exame a um evento sanitário");
    } finally {
      setVinculando(false);
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <button type="button" className={tipo === "vacina" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.78rem" }}
          onClick={() => { setTipo("vacina"); if (eventoAtual?.categoria_preventiva === "exame") onEventoId(""); }}>Vacina</button>
        <button type="button" className={tipo === "exame" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.78rem" }}
          onClick={() => { setTipo("exame"); if (eventoAtual && eventoAtual.categoria_preventiva !== "exame") onEventoId(""); }}>Exame</button>
        <button type="button" className={tipo === "" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.78rem" }}
          onClick={() => setTipo("")}>Avulso / outro</button>
      </div>
      {tipo === "exame" ? (
        <select style={inputStyle} value={exameSelId} onChange={(e) => escolherExame(e.target.value)} disabled={vinculando}>
          <option value="">{vinculando ? "Vinculando…" : "Selecione…"}</option>
          {exames.map((ex) => <option key={ex.id} value={ex.id}>{ex.nome}</option>)}
        </select>
      ) : (
        <select style={inputStyle} value={eventos.some((e) => String(e.id) === eventoId) && (tipo !== "vacina" || eventosVacina.some((e) => String(e.id) === eventoId)) ? eventoId : ""}
          onChange={(e) => onEventoId(e.target.value)}>
          <option value="">Selecione…</option>
          {(tipo === "vacina" ? eventosVacina : eventos).map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
        </select>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.72rem", marginTop: "0.25rem" }}>{erro}</p>}
    </div>
  );
}

// Passo 4 — Checklist (seção 3.7.0/3.7.3): lista editável nascida do template
// do tipo, ajustável só para esta regra (adicionar/remover item), sem afetar
// o template nem outras regras.
function PassoChecklist({ f, sf, onTocado }: { f: CalendarioForm; sf: (f: CalendarioForm) => void; onTocado: () => void }) {
  const [novoNome, setNovoNome] = useState("");
  const remover = (idx: number) => {
    onTocado();
    sf({ ...f, checklistItens: f.checklistItens.filter((_, i) => i !== idx) });
  };
  const adicionar = () => {
    if (!novoNome.trim()) return;
    onTocado();
    const ordem = f.checklistItens.length ? Math.max(...f.checklistItens.map((i) => i.ordem)) + 1 : 1;
    sf({ ...f, checklistItens: [...f.checklistItens, { chave: "custom", nome: novoNome.trim(), ordem }] });
    setNovoNome("");
  };
  return (
    <div>
      <p style={nota}>Nasce do template padrão deste tipo — ajuste só para esta regra (não afeta o template nem outras regras).</p>
      <ul style={{ marginTop: "0.6rem", padding: 0, listStyle: "none" }}>
        {f.checklistItens.map((item, idx) => (
          <li key={`${item.chave}-${idx}`} className="flex items-center justify-between" style={{ padding: "0.4rem 0.6rem", borderBottom: "1px solid var(--border)", fontSize: "0.82rem" }}>
            <span>{item.nome}</span>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => remover(idx)}>Remover</button>
          </li>
        ))}
        {!f.checklistItens.length && <li style={{ padding: "0.6rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhum item — a Ocorrência nascerá sem checklist.</li>}
      </ul>
      <div className="flex items-center gap-2 mt-3">
        <input style={inputStyle} placeholder="Novo item…" value={novoNome} onChange={(e) => setNovoNome(e.target.value)} />
        <button type="button" className="btn-secondary" style={{ fontSize: "0.78rem", whiteSpace: "nowrap" }} onClick={adicionar}>+ Adicionar</button>
      </div>
    </div>
  );
}

// Ponto de entrada antes do wizard (seção 3.7.0) — duas tabelas: Eventos
// cadastrados e Regras cadastradas, e o botão que abre o wizard no passo 1.
function ListaEntradaCadastroSanitario({
  eventos, regras, ordEventos, ordRegras, tipoFiltroRegras, setTipoFiltroRegras, onNovo, onEditarEvento, onEditarRegra, onExcluirRegra,
}: {
  eventos: EventoSanitarioDTO[]; regras: RegraCalendario[] | null;
  ordEventos: ReturnType<typeof useOrdenacao<EventoSanitarioDTO>>;
  ordRegras: ReturnType<typeof useOrdenacao<RegraCalendario>>;
  tipoFiltroRegras: "todos" | "vacina" | "tratamento" | "exame" | "avulso";
  setTipoFiltroRegras: (v: "todos" | "vacina" | "tratamento" | "exame" | "avulso") => void;
  onNovo: () => void; onEditarEvento: (ev: EventoSanitarioDTO) => void;
  onEditarRegra: (r: RegraCalendario) => void; onExcluirRegra: (r: RegraCalendario) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p style={nota}>Cadastro de vacina/tratamento/exame e das regras que geram o calendário sanitário.</p>
        <button type="button" className="btn-primary" style={{ fontSize: "0.8rem", whiteSpace: "nowrap" }} onClick={onNovo}>
          <Plus size={14} /> Nova regra do calendário sanitário
        </button>
      </div>

      <SecaoRecolhivel titulo="Eventos cadastrados" defaultAberta={false}
        descricao="Vacinas, tratamentos e exames já cadastrados" badge={<span style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700 }}>{eventos.length}</span>}>
        <div className="overflow-x-auto" style={{ maxHeight: "320px" }}>
          <table className="fazenda-table" style={{ margin: 0 }}>
            <thead><tr>
              <ThOrdenavel label="Nome" campo="nome" coluna={ordEventos.coluna} dir={ordEventos.dir} ordenar={ordEventos.ordenar} />
              <ThOrdenavel label="Tipo" campo="categoria_preventiva" coluna={ordEventos.coluna} dir={ordEventos.dir} ordenar={ordEventos.ordenar} />
              <ThOrdenavel label="Doença" campo="doenca_nome" coluna={ordEventos.coluna} dir={ordEventos.dir} ordenar={ordEventos.ordenar} />
              <th>Produto padrão / exame vinculado</th>
              <ThOrdenavel label="Veterinário padrão" campo="veterinario_padrao_nome" coluna={ordEventos.coluna} dir={ordEventos.dir} ordenar={ordEventos.ordenar} />
              <th></th>
            </tr></thead>
            <tbody>
              {ordEventos.linhasOrdenadas.filter((e) => e.ativo).map((ev) => (
                <tr key={ev.id}>
                  <td style={{ fontWeight: 700 }}>{ev.nome}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    {ev.categoria_preventiva === "exame" ? "Exame" : ev.categoria_preventiva === "tratamento" ? "Tratamento" : "Vacina"}
                  </td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{ev.doenca_nome || "—"}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{ev.exame_definicao_nome || ev.produto_padrao || "—"}</td>
                  <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{ev.veterinario_padrao_nome || "—"}</td>
                  <td style={{ textAlign: "right" }}><button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => onEditarEvento(ev)}>Editar</button></td>
                </tr>
              ))}
              {!eventos.filter((e) => e.ativo).length && (
                <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum evento cadastrado ainda.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </SecaoRecolhivel>

      {regras && (
        <div className="mt-4">
          <SecaoRecolhivel titulo="Regras cadastradas" defaultAberta
            descricao="Regras recorrentes já cadastradas no calendário sanitário"
            badge={<span style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700 }}>{regras.length}</span>}>
            <div className="flex items-center gap-2 mb-2">
              {TIPOS_REGRA_FILTRO.map((t) => (
                <button key={t.v} type="button" className={tipoFiltroRegras === t.v ? "btn-primary" : "btn-secondary"}
                  style={{ fontSize: "0.72rem" }} onClick={() => setTipoFiltroRegras(t.v)}>{t.l}</button>
              ))}
            </div>
            <div className="overflow-x-auto" style={{ maxHeight: "320px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <ThOrdenavel label="Evento" campo="evento_sanitario_nome" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} />
                  <ThOrdenavel label="Categoria alvo" campo="categoria_alvo" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} />
                  <ThOrdenavel label="Disparo" campo="frequencia_valor" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} />
                  <ThOrdenavel label="Próxima ocorrência" campo="proxima_ocorrencia" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} />
                  <th></th>
                </tr></thead>
                <tbody>
                  {ordRegras.linhasOrdenadas.map((r) => (
                    <tr key={r.id}>
                      <td style={{ fontWeight: 700 }}>{r.evento_sanitario_nome}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.categoria_alvo || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>
                        {r.proxima_ocorrencia_por_animal ? "Por evento de vida" : `a cada ${r.frequencia_valor} ${FREQUENCIA_UNIDADES.find((u) => u.v === r.frequencia_unidade)?.l}`}
                      </td>
                      <td style={{ fontSize: "0.78rem" }}>
                        {r.proxima_ocorrencia_por_animal ? "Calculado por animal" : formatDate(r.proxima_ocorrencia)}
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => onEditarRegra(r)}>Editar</button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => onExcluirRegra(r)}>Excluir</button>
                      </td>
                    </tr>
                  ))}
                  {!regras.length && (
                    <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma regra cadastrada ainda.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>
        </div>
      )}
    </div>
  );
}
