"use client";
import React, { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Plus } from "lucide-react";
import {
  fetchEventosSanitarios, fetchDoencas, fetchPrincipiosAtivos, fetchCalendarioSanitario, criarCalendarioSanitario,
  atualizarCalendarioSanitario, excluirCalendarioSanitario, fetchExames, atualizarEventoSanitario, criarEventoSanitario,
  fetchEventosVidaVocabulario, fetchCategoriasManejo, formatDate,
} from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { EstoquePicker } from "@/components/EstoquePicker";
import { Modal } from "@/components/Modal";
import { SecaoRecolhivel, MultiFiltro } from "@/components/ui";
import { Campo, inputStyle, nota, type EstoqueItem, unidadesCompativeis } from "@/components/lancamentos/comumForms";
import { FREQUENCIA_UNIDADES, type ExameDef } from "@/components/lancamentos/_shared";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
const CadastroEventosSanitarios = dynamic(() => import("@/components/CadastroSanitario").then((m) => m.CadastroEventosSanitarios), { ssr: false });

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
};

// vacina | exame | avulso/outro (nada marcado nos dois primeiros) | todos.
const TIPOS_REGRA_FILTRO = [
  { v: "todos", l: "Todos" }, { v: "vacina", l: "Vacina" }, { v: "exame", l: "Exame" }, { v: "avulso", l: "Avulso/outro" },
] as const;
export function tipoRegra(r: { categoria_preventiva: string | null }): "vacina" | "exame" | "avulso" {
  if (r.categoria_preventiva === "exame") return "exame";
  if (r.categoria_preventiva === "vacina") return "vacina";
  return "avulso";
}
// Separador usado para guardar mais de uma categoria-alvo no mesmo campo
// (texto único no banco — cada regra continua com um único categoria_alvo).
const SEP_CATEGORIAS = ", ";

/**
 * Seletor de evento preventivo com a pergunta "vacina ou exame" na frente —
 * usado tanto no cadastro do Calendário sanitário quanto no lançamento de
 * Aplicações. "Avulso" (padrão, nada marcado) mantém o combinado tradicional
 * com todos os eventos, já que uma aplicação preventiva pode ser avulsa, sem
 * vínculo com uma vacina ou exame específico cadastrado.
 * Ao escolher um exame que ainda não tem um evento sanitário vinculado, cria
 * esse vínculo na hora (transparente para o usuário) para que o exame
 * cadastrado (Configurações > Cadastro > Sanitário > Exames) fique
 * selecionável aqui sem precisar de um cadastro de evento à parte.
 */
export function SeletorEventoPreventivo({ eventos, exames, eventoId, onEventoId, onEventosRecarregados }: {
  eventos: { id: number; nome: string }[]; exames: ExameDef[]; eventoId: string;
  onEventoId: (id: string) => void; onEventosRecarregados: () => void;
}) {
  const [tipo, setTipo] = useState<"" | "vacina" | "exame">("");
  const [vinculando, setVinculando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  // Mantém a aba coerente com o evento carregado (edição de uma regra já
  // existente, ou pré-preenchimento vindo da Agenda).
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

export function FormCalendarioSanitario({ estoque }: { estoque: EstoqueItem[] }) {
  const [eventos, setEventos] = useState<OpcaoNomeAtivo[]>([]);
  const [exames, setExames] = useState<ExameDef[]>([]);
  const [doencas, setDoencas] = useState<OpcaoNomeAtivo[]>([]);
  const [principios, setPrincipios] = useState<OpcaoNomeAtivo[]>([]);
  // Categorias de vida (Configurações > Cadastro > Categorias) — a lista real
  // usada para "período de vida", nada a ver com CATEGORIAS_ANIMAIS (critérios
  // de lançamento em massa por status reprodutivo, usado mais abaixo neste arquivo).
  const [categoriasVida, setCategoriasVida] = useState<string[]>([]);
  const [regras, setRegras] = useState<RegraCalendario[] | null>(null);

  const [editando, setEditando] = useState<number | null>(null);
  const [eventoId, setEventoId] = useState("");
  const [categoriaAlvoSel, setCategoriaAlvoSel] = useState<string[]>([]);
  const [doencaId, setDoencaId] = useState("");
  const [produto, setProduto] = useState("");
  const [principioId, setPrincipioId] = useState("");
  const [dosagem, setDosagem] = useState("");
  const [unidade, setUnidade] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [veterinario, setVeterinario] = useState("");
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [dataEvento, setDataEvento] = useState("");
  const [observacao, setObservacao] = useState("");
  const [realizado, setRealizado] = useState(false);
  // Cronograma sanitário (ver fazenda/rules/cronograma_sanitario.py): em vez
  // de cobrar aplicação na hora, o animal que bate o critério entra numa
  // lista de espera até o usuário decidir veterinário/aplicação própria.
  const [usaCronograma, setUsaCronograma] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [tipoFiltroRegras, setTipoFiltroRegras] = useState<"todos" | "vacina" | "exame" | "avulso">("todos");
  const regrasFiltradas = useMemo(
    () => (regras ?? []).filter((r) => tipoFiltroRegras === "todos" || tipoRegra(r) === tipoFiltroRegras),
    [regras, tipoFiltroRegras]
  );
  const ordRegras = useOrdenacao(regrasFiltradas);

  const { pessoas: pessoasAtivas } = usePessoasAtivas();
  const veterinariosZootecnistas = useMemo(
    () => pessoasAtivas.filter((p) => (p.tipos || []).some((t: string) => ["Veterinário", "Zootecnista"].includes(t))),
    [pessoasAtivas]
  );

  // Frequência periódica (regra recorrente do calendário) OU por evento de
  // vida (desmama, aptidão, secagem…) — nesse 2º modo não cria regra nenhuma:
  // configura o EVENTO SANITÁRIO selecionado para agendar por animal (mesmo
  // mecanismo que já gera a Agenda por evento — ver eventos_sanitarios.py).
  const [modoFreq, setModoFreq] = useState<"periodica" | "evento_vida">("periodica");
  const [gatilhosVida, setGatilhosVida] = useState<{ gatilho: string; rotulo: string }[]>([]);
  const [gatilho, setGatilho] = useState("nascimento");
  const [gatilhoLote, setGatilhoLote] = useState("");
  const [gatilhoIdadeMeses, setGatilhoIdadeMeses] = useState("");
  const [offsetDias, setOffsetDias] = useState("0");

  useEffect(() => { fetchEventosVidaVocabulario().then(setGatilhosVida).catch(() => {}); }, []);

  const eventoSel = eventos.find((e) => String(e.id) === eventoId) as any;
  const ehExame = eventoSel?.categoria_preventiva === "exame";

  // Ao escolher um evento já cadastrado como "por evento" (tipo_agendamento
  // == evento), o modo já vem pré-selecionado e os campos de gatilho
  // preenchidos — só para uma regra NOVA (editando uma regra já existente,
  // abrirEdicao já fixou modoFreq="periodica" e não deve ser sobrescrito,
  // senão os campos da própria regra em edição somem da tela).
  useEffect(() => {
    if (editando !== null) return;
    if (!eventoSel) return;
    if (eventoSel.tipo_agendamento === "evento" && eventoSel.gatilho) {
      setModoFreq("evento_vida");
      setGatilho(eventoSel.gatilho);
      setGatilhoLote(eventoSel.gatilho_lote || "");
      setGatilhoIdadeMeses(eventoSel.gatilho_idade_meses ? String(eventoSel.gatilho_idade_meses) : "");
      setOffsetDias(eventoSel.offset_dias != null ? String(eventoSel.offset_dias) : "0");
      // Pré-preenche o cronograma já vinculado a este evento (se existir) —
      // permite revisar/ligar "usar cronograma sanitário" de um evento por
      // evento de vida (ex.: Brucelose B19) direto por aqui, sem precisar
      // achar a regra na lista "Regras cadastradas".
      const regraVinculada = (regras ?? []).find((r) => r.evento_sanitario_id === eventoSel.id);
      setUsaCronograma(regraVinculada?.usa_cronograma ?? false);
      setFreqValor(regraVinculada ? String(regraVinculada.frequencia_valor) : "30");
      setFreqUnidade(regraVinculada ? regraVinculada.frequencia_unidade : "dias");
      setDataEvento(regraVinculada ? regraVinculada.data_evento : new Date().toISOString().slice(0, 10));
    } else {
      setModoFreq("periodica");
      setUsaCronograma(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventoId, editando]);

  const carregarRegras = () => fetchCalendarioSanitario().then(setRegras).catch((e) => setErro(e.message));
  const carregarEventos = () => fetchEventosSanitarios().then((d) => setEventos(d.filter((e: OpcaoNomeAtivo) => e.ativo))).catch(() => {});
  useEffect(() => {
    carregarEventos();
    fetchExames().then(setExames).catch(() => {});
    fetchDoencas().then((d) => setDoencas(d.filter((e: OpcaoNomeAtivo) => e.ativo))).catch(() => {});
    fetchPrincipiosAtivos().then((d) => setPrincipios(d.filter((e: OpcaoNomeAtivo) => e.ativo !== false))).catch(() => {});
    fetchCategoriasManejo().then((d) => setCategoriasVida(d.filter((c) => c.ativo).map((c) => c.nome))).catch(() => {});
    carregarRegras();
  }, []);
  const [abrirNovoEvento, setAbrirNovoEvento] = useState(false);

  const limpar = () => {
    setEditando(null); setEventoId(""); setCategoriaAlvoSel([]); setDoencaId(""); setProduto("");
    setPrincipioId(""); setDosagem(""); setUnidade(""); setResponsavel(""); setVeterinario(""); setFreqValor("1"); setFreqUnidade("meses");
    setDataEvento(""); setObservacao(""); setRealizado(false); setUsaCronograma(false);
    setModoFreq("periodica"); setGatilho("nascimento"); setGatilhoLote(""); setGatilhoIdadeMeses(""); setOffsetDias("0");
  };

  const abrirEdicao = (r: RegraCalendario) => {
    setEditando(r.id); setEventoId(String(r.evento_sanitario_id));
    setCategoriaAlvoSel(r.categoria_alvo ? r.categoria_alvo.split(SEP_CATEGORIAS).map((c) => c.trim()).filter(Boolean) : []);
    setDoencaId(r.doenca_id ? String(r.doenca_id) : ""); setProduto(r.produto || "");
    setPrincipioId(r.principio_ativo_id ? String(r.principio_ativo_id) : ""); setDosagem(r.dosagem || "");
    setUnidade(r.unidade || "");
    setResponsavel(r.responsavel || "");
    setVeterinario((r as any).veterinario || "");
    setFreqValor(String(r.frequencia_valor)); setFreqUnidade(r.frequencia_unidade);
    setDataEvento(r.data_evento); setObservacao(r.observacao || ""); setRealizado(false);
    setUsaCronograma(r.usa_cronograma ?? false);
    // Está editando uma regra JÁ existente (linha real de CalendarioSanitario) —
    // o modo é sempre "periódica", mesmo que o evento vinculado também tenha
    // um agendamento "por evento de vida" configurado (ex.: Brucelose B19).
    // Sem isto, o efeito abaixo trocava de modo sozinho e escondia os campos
    // da própria regra que se está editando.
    setModoFreq("periodica");
  };

  const excluir = async (r: RegraCalendario) => {
    if (!window.confirm(`Excluir a regra do calendário "${r.evento_sanitario_nome}" de ${formatDate(r.data_evento)}?`)) return;
    try { await excluirCalendarioSanitario(r.id); carregarRegras(); }
    catch (e: any) { setErro(e.message); }
  };

  // Se marcar "usar cronograma sanitário", a janela do cronograma (frequência
  // + data de referência) precisa existir mesmo quando o modo é "evento de
  // vida" — é o que liga o gatilho por animal (ex.: Brucelose B19 aos 150
  // dias) à lista de espera em vez de cobrar aplicação na hora.
  const precisaCicloRegra = modoFreq === "periodica" || usaCronograma;
  const regraVinculadaEventoVida = modoFreq === "evento_vida" && eventoId
    ? (regras ?? []).find((r) => r.evento_sanitario_id === Number(eventoId))
    : undefined;

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!eventoId) { setErro("Selecione o evento sanitário."); return; }
    if (precisaCicloRegra && (!dataEvento || !freqValor)) { setErro("Selecione a frequência e a data do evento."); return; }
    if (modoFreq === "evento_vida" && gatilho === "entrada_lote" && !gatilhoLote.trim()) { setErro("Informe o lote do gatilho (entrada no lote)."); return; }
    if (modoFreq === "evento_vida" && gatilho === "novilha_apta" && !gatilhoIdadeMeses) { setErro("Informe a idade-alvo em meses (aptidão de novilha)."); return; }
    // Só se marca como realizado evento do dia corrente ou retroativo — nunca um evento futuro.
    if (modoFreq === "periodica" && realizado && dataEvento && dataEvento > new Date().toISOString().slice(0, 10)) {
      setErro("Só é possível marcar como realizado um evento de hoje ou retroativo — a data informada é futura.");
      return;
    }
    setSalvando(true);
    try {
      const montarDadosRegra = () => ({
        evento_sanitario_id: Number(eventoId), categoria_alvo: categoriaAlvoSel.length ? categoriaAlvoSel.join(SEP_CATEGORIAS) : undefined,
        doenca_id: doencaId ? Number(doencaId) : undefined,
        produto: ehExame ? undefined : (produto || undefined),
        principio_ativo_id: ehExame ? undefined : (principioId ? Number(principioId) : undefined),
        dosagem: ehExame ? undefined : (dosagem || undefined),
        unidade: ehExame ? undefined : (unidade || undefined),
        responsavel: responsavel || undefined,
        veterinario: veterinario || undefined,
        frequencia_valor: Number(freqValor), frequencia_unidade: freqUnidade, data_evento: dataEvento,
        observacao: observacao || undefined, realizado, usa_cronograma: usaCronograma,
      });

      if (modoFreq === "evento_vida") {
        // Configura o EVENTO SANITÁRIO selecionado para agendar por evento de
        // vida (por animal), preservando os demais campos já cadastrados nele.
        await atualizarEventoSanitario(Number(eventoId), {
          ...eventoSel, tipo_agendamento: "evento", gatilho,
          gatilho_lote: gatilho === "entrada_lote" ? gatilhoLote.trim() : null,
          gatilho_idade_meses: gatilho === "novilha_apta" ? Number(gatilhoIdadeMeses) : null,
          offset_dias: offsetDias ? Number(offsetDias) : 0,
        });
        // "Usar cronograma sanitário" marcado (ou já havia uma regra
        // vinculada a este evento) — cria/atualiza a regra que liga esse
        // gatilho por animal à lista de espera do cronograma.
        if (usaCronograma || regraVinculadaEventoVida) {
          const dadosRegra = montarDadosRegra();
          if (regraVinculadaEventoVida) await atualizarCalendarioSanitario(regraVinculadaEventoVida.id, dadosRegra);
          else await criarCalendarioSanitario(dadosRegra);
        }
        if (usaCronograma) {
          window.location.href = "/sanidade?ir=cronogramas";
          return;
        }
        setSucesso("Evento sanitário configurado para agendar por evento de vida.");
        limpar();
        carregarEventos();
        carregarRegras();
        setSalvando(false);
        return;
      }
      const dados = montarDadosRegra();
      if (editando) await atualizarCalendarioSanitario(editando, dados);
      else await criarCalendarioSanitario(dados);
      if (usaCronograma) {
        // "Registrar cronograma deste evento" marcado — leva direto para o
        // card Cronogramas (Sanidade > Preventiva > Calendário sanitário),
        // para confirmar o 1º ciclo (agendar com veterinário, aplicação
        // própria ou deixar em aberto), como pedido no momento do cadastro.
        window.location.href = "/sanidade?ir=cronogramas";
        return;
      }
      setSucesso(editando ? "Regra atualizada com sucesso." : "Regra do calendário sanitário criada com sucesso.");
      limpar();
      carregarRegras();
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar a regra do calendário sanitário");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <p style={nota}>
        Ex.: <strong>Vermífugo</strong> a cada 4 meses para bezerras (calendário sazonal), ou <strong>Brucelose B19</strong> uma
        vez, no nascimento (protocolo por fase fisiológica) — escolha o evento, a frequência e preencha a dosagem.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
        <Campo label="Evento sanitário">
          <div className="flex items-center gap-2">
            <div style={{ flex: 1 }}>
              <SeletorEventoPreventivo eventos={eventos} exames={exames} eventoId={eventoId} onEventoId={setEventoId} onEventosRecarregados={carregarEventos} />
            </div>
            <button type="button" className="btn-ghost" title="Cadastrar novo evento sanitário" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoEvento(true)}>
              <Plus size={13} /> Novo
            </button>
          </div>
          {abrirNovoEvento && (
            <Modal title="Novo evento sanitário" onClose={() => { setAbrirNovoEvento(false); carregarEventos(); }} width="900px">
              <CadastroEventosSanitarios />
            </Modal>
          )}
        </Campo>
        <Campo label="Categoria(s) alvo (período de vida)">
          <MultiFiltro
            label="Categorias" opcoes={Array.from(new Set([...categoriasVida, ...categoriaAlvoSel]))}
            selecionados={categoriaAlvoSel} onChange={setCategoriaAlvoSel}
            permitirNovo placeholderNovo="+ outra categoria…"
            onAdicionarNovo={(v) => setCategoriaAlvoSel((p) => Array.from(new Set([...p, v])))}
          />
        </Campo>
        <Campo label="Doença combatida">
          <select style={inputStyle} value={doencaId} onChange={(e) => setDoencaId(e.target.value)}>
            <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
          </select>
        </Campo>
        <Campo label="Responsável">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
            <option value="">Opcional</option>
            {pessoasAtivas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
          </select>
        </Campo>
        {ehExame ? (
          <Campo label="Veterinário (exame)">
            <select style={inputStyle} value={veterinario} onChange={(e) => setVeterinario(e.target.value)}>
              <option value="">Opcional</option>
              {veterinariosZootecnistas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
            </select>
          </Campo>
        ) : (
          <>
            <Campo label="Princípio ativo">
              <select style={inputStyle} value={principioId} onChange={(e) => setPrincipioId(e.target.value)}>
                <option value="">—</option>{principios.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select>
            </Campo>
            <Campo label="Produto (item de estoque)">
              <EstoquePicker itens={estoque} value={produto} onChange={setProduto} />
            </Campo>
            <Campo label="Dosagem recomendada">
              <input style={inputStyle} value={dosagem} onChange={(e) => setDosagem(e.target.value)} placeholder="ex.: 2 mL a 5 mL (conforme bula)" />
            </Campo>
            <Campo label="Unidade">
              <select style={inputStyle} value={unidade} onChange={(e) => setUnidade(e.target.value)}>
                <option value="">—</option>
                {unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade).map((u) => <option key={u}>{u}</option>)}
              </select>
            </Campo>
          </>
        )}
        <Campo label="Repetir por" full>
          <div className="flex items-center gap-4" style={{ fontSize: "0.85rem" }}>
            <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
              <input type="radio" checked={modoFreq === "periodica"} onChange={() => setModoFreq("periodica")} /> Frequência periódica
            </label>
            <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
              <input type="radio" checked={modoFreq === "evento_vida"} onChange={() => setModoFreq("evento_vida")} /> Evento de vida do animal
            </label>
          </div>
        </Campo>
        {modoFreq === "evento_vida" && (
          <>
            <Campo label="Evento de vida">
              <select style={inputStyle} value={gatilho} onChange={(e) => setGatilho(e.target.value)}>
                {gatilhosVida.map((g) => <option key={g.gatilho} value={g.gatilho}>{g.rotulo}</option>)}
              </select>
            </Campo>
            {gatilho === "entrada_lote" && (
              <Campo label="Lote do gatilho"><input style={inputStyle} value={gatilhoLote} onChange={(e) => setGatilhoLote(e.target.value)} placeholder="ex.: PRE_PARTO" /></Campo>
            )}
            {gatilho === "novilha_apta" && (
              <Campo label="Idade-alvo (meses)"><input type="number" min={1} style={inputStyle} value={gatilhoIdadeMeses} onChange={(e) => setGatilhoIdadeMeses(e.target.value)} placeholder="ex.: 13" /></Campo>
            )}
            <Campo label="Dias após o gatilho"><input type="number" style={inputStyle} value={offsetDias} onChange={(e) => setOffsetDias(e.target.value)} /></Campo>
            <div style={{ gridColumn: "1 / -1" }}>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Este modo por si só não cria uma regra de frequência — ele configura o evento sanitário selecionado para
                entrar na Agenda automaticamente quando cada animal atingir esse evento de vida (por animal, não por
                rebanho todo). Marque "Usar cronograma sanitário" abaixo para, em vez de cobrar aplicação na hora
                assim que o animal bater o critério, colocá-lo numa lista de espera por leva.
              </p>
            </div>
          </>
        )}
        {precisaCicloRegra && (
          <>
            <Campo label={modoFreq === "evento_vida" ? "Frequência da leva do cronograma" : "Frequência"}>
              <div className="flex items-center gap-2">
                <input type="number" min={1} style={inputStyle} value={freqValor} onChange={(e) => setFreqValor(e.target.value)} />
                <select style={inputStyle} value={freqUnidade} onChange={(e) => setFreqUnidade(e.target.value)}>
                  {FREQUENCIA_UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}
                </select>
              </div>
            </Campo>
            <Campo label="Data do evento (referência)"><input type="date" style={inputStyle} value={dataEvento} onChange={(e) => setDataEvento(e.target.value)} /></Campo>
          </>
        )}
        <Campo label="Observação" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>

      {ehExame && (
        <p style={{ fontSize: "0.75rem", color: "var(--blue)", marginTop: "0.5rem" }}>
          Exame — sem baixa de estoque, só o agendamento. Use o botão "Lançar financeiro" na aba Sanidade &gt; Preventivo para registrar o custo do exame.
        </p>
      )}
      {modoFreq === "periodica" && (
        <label className="flex items-center gap-2 mt-2" style={{ fontSize: "0.8rem" }}>
          <input type="checkbox" checked={realizado} onChange={(e) => setRealizado(e.target.checked)} /> Já foi realizado (não entra como pendência na Agenda)
        </label>
      )}
      {!!eventoId && (
        <div style={{ marginTop: "0.5rem", padding: "0.6rem 0.7rem", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface-2)" }}>
          <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", fontWeight: 700 }}>
            <input type="checkbox" checked={usaCronograma} onChange={(e) => setUsaCronograma(e.target.checked)} /> Usar cronograma sanitário
          </label>
          <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
            Em vez de cobrar aplicação na hora, os animais que baterem o critério entram numa lista de espera até você agendar
            com o veterinário ou confirmar aplicação própria. A Agenda mostra a lista de espera, a decisão de quem vai aplicar e,
            perto da data prevista sem decisão, cobra confirmação obrigatória. Funciona tanto para uma regra de frequência
            periódica quanto para um evento por evento de vida (ex.: uma vacina aplicada numa idade-alvo específica).
          </p>
        </div>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : editando ? "Salvar alterações" : "Salvar"}</button>
        {editando && <button className="btn-ghost" onClick={limpar}>Cancelar edição</button>}
      </div>

      {regras && (
        <div className="mt-4">
          <SecaoRecolhivel
            titulo="Regras cadastradas"
            defaultAberta={false}
            descricao="Regras recorrentes já cadastradas no calendário sanitário"
            badge={<span style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700 }}>{regras.length}</span>}
          >
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
                <ThOrdenavel label="Tipo" campo="categoria_preventiva" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} />
                <ThOrdenavel label="Responsável" campo="responsavel" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} />
                <ThOrdenavel label="Categoria alvo" campo="categoria_alvo" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} />
                <ThOrdenavel label="Frequência" campo="frequencia_valor" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} alinhar="right" />
                <ThOrdenavel label="Próxima ocorrência" campo="proxima_ocorrencia" coluna={ordRegras.coluna} dir={ordRegras.dir} ordenar={ordRegras.ordenar} />
                <th></th>
              </tr></thead>
              <tbody>
                {ordRegras.linhasOrdenadas.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 700 }}>
                      {r.evento_sanitario_nome}
                      {r.usa_cronograma && (
                        <span title="Usa cronograma sanitário" style={{ marginLeft: "0.4rem", fontSize: "0.62rem", fontWeight: 700, color: "var(--dourado-light)", background: "rgba(212,175,55,0.14)", padding: "0.05rem 0.4rem", borderRadius: 999 }}>
                          Cronograma
                        </span>
                      )}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {tipoRegra(r) === "vacina" ? "Vacina" : tipoRegra(r) === "exame" ? "Exame" : "Avulso/outro"}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.responsavel || r.veterinario || "—"}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.categoria_alvo || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>a cada {r.frequencia_valor} {FREQUENCIA_UNIDADES.find((u) => u.v === r.frequencia_unidade)?.l}</td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(r.proxima_ocorrencia)}</td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => abrirEdicao(r)}>Editar</button>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => excluir(r)}>Excluir</button>
                    </td>
                  </tr>
                ))}
                {!regrasFiltradas.length && (
                  <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma regra cadastrada ainda.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          </SecaoRecolhivel>
        </div>
      )}
    </>
  );
}

