"use client";
import React, { useEffect, useMemo, useState } from "react";
import { Check } from "lucide-react";
import {
  cadastrarPreventivo, fetchCalendarioSanitario, fetchEventosSanitarios, fetchExames, fetchPessoas, formatDate,
  marcarEventoRealizado, previewCriteriosLote,
} from "@/lib/api";
import { PopupVinculoFinanceiro, type OrigemPopupVinculo } from "@/components/lancamentos/PopupVinculoFinanceiro";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { EstoquePicker } from "@/components/EstoquePicker";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, nota, type EstoqueItem, codigoGrupo, unidadesCompativeis } from "@/components/lancamentos/comumForms";
import { CATEGORIAS_ANIMAIS, FREQUENCIA_UNIDADES, type ExameDef } from "@/components/lancamentos/_shared";
import { SeletorEventoPreventivo } from "@/components/lancamentos/FormCalendarioSanitario";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";

// ─────────────────────── Preventivo — aplicação (vacina/exame) ───────────────────────
type EventoPrev = {
  id: number; nome: string; categoria_preventiva: string | null; doenca_nome: string | null;
  produto_padrao: string | null; dose_padrao: number | null; unidade_padrao: string | null;
  exame_definicao_id: number | null;
};
const LABEL_RESULTADO_EXAME: Record<string, string> = { positivo: "Positivo", negativo: "Negativo", indefinido: "Indefinido" };

export function FormPreventivoAplicacao({ animais, lotes, estoque }: { animais: AnimalRow[]; lotes: string[]; estoque: EstoqueItem[] }) {
  const { rotuloDe } = useEstadosReprodutivos();
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [eventoId, setEventoId] = useState("");
  const [dataEvento, setDataEvento] = useState("");
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [veterinario, setVeterinario] = useState("");
  const [vinculo, setVinculo] = useState<"animal" | "lote" | "categoria">("animal");
  const [animaisSel, setAnimaisSel] = useState<Set<string>>(new Set());

  const [pessoas, setPessoas] = useState<any[]>([]);
  useEffect(() => { fetchPessoas().then(setPessoas).catch(() => setPessoas([])); }, []);
  const veterinariosZootecnistas = useMemo(
    () => pessoas.filter((p) => p.ativo !== false && (p.tipos || []).some((t: string) => ["Veterinário", "Zootecnista", "Vet/Zootec."].includes(t)))
      .sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    [pessoas]
  );

  // Lote: pode selecionar mais de um — janela suspensa mostra só os animais
  // dos lotes escolhidos, com "selecionar todos" (mesmo padrão da Inseminação).
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const codigosLotesTodos = useMemo(
    () => Array.from(new Set(animais.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [animais]
  );
  const animaisDosLotesSel = useMemo(() => {
    const cods = new Set(lotesSelecionados);
    return animais.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [animais, lotesSelecionados]);
  const [selDosLotes, setSelDosLotes] = useState<Set<string>>(new Set());
  const toggleDosLotes = (n: string) => setSelDosLotes((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelDosLotes(new Set(animaisDosLotesSel.map((a) => a.numero)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lotesSelecionados.join("|")]);

  // Categoria: pode escolher mais de uma — ao concluir, abre janela suspensa
  // com a união dos animais de todas as categorias marcadas.
  const [categoriasSel, setCategoriasSel] = useState<Set<string>>(new Set());
  const toggleCategoria = (id: string) => setCategoriasSel((p) => { const s = new Set(p); s.has(id) ? s.delete(id) : s.add(id); return s; });
  const [animaisCategoriasUniao, setAnimaisCategoriasUniao] = useState<string[]>([]);
  useEffect(() => {
    if (!categoriasSel.size) { setAnimaisCategoriasUniao([]); return; }
    Promise.all(Array.from(categoriasSel).map((id) => {
      const cat = CATEGORIAS_ANIMAIS.find((c) => c.id === id);
      if (!cat) return Promise.resolve([] as string[]);
      return previewCriteriosLote(cat.criterios).then((r: any) => r.animais || []).catch(() => [] as string[]);
    })).then((listas) => setAnimaisCategoriasUniao(Array.from(new Set(listas.flat()))));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Array.from(categoriasSel).sort().join("|")]);
  const animaisDasCategoriasSel = useMemo(() => {
    const nums = new Set(animaisCategoriasUniao);
    return animais.filter((a) => nums.has(a.numero));
  }, [animais, animaisCategoriasUniao]);
  const [selDasCategorias, setSelDasCategorias] = useState<Set<string>>(new Set());
  const toggleDasCategorias = (n: string) => setSelDasCategorias((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelDasCategorias(new Set(animaisCategoriasUniao));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animaisCategoriasUniao.join("|")]);

  const [realizado, setRealizado] = useState(false);
  // "Já foi aplicado?" — só para vacina/tratamento (exame usa o checkbox "realizado" abaixo,
  // já que não existe uma aplicação de produto para exame). Não aplicado ainda vira
  // pendência (AplicacaoAgendada) em vez de Sanidade — mesmo padrão de FormSanidade.
  const [aplicado, setAplicado] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "erro"; txt: string } | null>(null);
  // Vindo da Agenda ("Dar baixa" de um evento/regra sanitária preventiva): ao
  // salvar, marca a pendência original como realizada para sumir da Agenda.
  const [eventoAgenda, setEventoAgenda] = useState<string | null>(null);
  // Vindo da Agenda para uma pendência de uma regra do calendário sanitário JÁ
  // existente (tipo "calendario_sanitario") — nesse caso não se cria uma regra
  // nova nem se redefine frequência: é a baixa de uma ocorrência da regra
  // apontada por este id (ver calendario_id em CadastrarPreventivoIn).
  const [calendarioIdAgenda, setCalendarioIdAgenda] = useState<number | null>(null);

  // Diagnóstico do exame (positivo/negativo/indefinido) ou resultado numérico
  // — só para eventos categoria_preventiva == "exame". Nunca gera aplicação
  // de medicamento; positivo marca "A descartar" automaticamente.
  const [exames, setExames] = useState<ExameDef[]>([]);
  const [diagnostico, setDiagnostico] = useState<"" | "positivo" | "negativo" | "indefinido">("");
  const [resultadoNumerico, setResultadoNumerico] = useState("");
  // Popup de vínculo financeiro — só para vacina/exame (não avulso/tratamento),
  // disparado após salvar com sucesso (ver PopupVinculoFinanceiro).
  const [popupOrigem, setPopupOrigem] = useState<OrigemPopupVinculo | null>(null);

  useEffect(() => { fetchEventosSanitarios().then((d) => setEventos(d.filter((e: any) => e.ativo))).catch(() => {}); }, []);
  useEffect(() => { fetchExames().then(setExames).catch(() => {}); }, []);
  useEffect(() => { setDiagnostico(""); setResultadoNumerico(""); }, [eventoId]);

  // Pré-preenche a partir da Agenda — evento, data e (se for por animal) o
  // número da matriz já vêm prontos; o restante (categoria/lote, se for um
  // lembrete de rebanho) o usuário escolhe na hora.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get("ir") !== "preventivo_aplicacao") return;
    const evId = qs.get("evento_sanitario_id");
    if (evId) setEventoId(evId);
    const data = qs.get("data"); if (data) setDataEvento(data);
    const numero = qs.get("numero_matriz");
    if (numero) { setVinculo("animal"); setAnimaisSel(new Set([numero])); }
    setEventoAgenda(qs.get("evento_agenda"));
    const calId = qs.get("calendario_id");
    if (calId) setCalendarioIdAgenda(Number(calId));
  }, []);

  const evento = eventos.find((e) => String(e.id) === eventoId);
  const ehExame = evento?.categoria_preventiva === "exame";
  const exameDef = evento?.exame_definicao_id ? exames.find((x) => x.id === evento.exame_definicao_id) : undefined;
  const modoNumerico = ehExame && exameDef?.tipo_resultado === "numerico";

  // Medicamento aplicado — sempre perguntado para vacina/tratamento (não para
  // exame). Pré-preenche com o produto/dose/unidade padrão do evento quando
  // existirem; o usuário pode trocar (é o fluxo normal, não uma exceção).
  const estoquePorNome = useMemo(() => new Map(estoque.map((e) => [e.nome, e])), [estoque]);
  const itemPadrao = evento?.produto_padrao ? estoquePorNome.get(evento.produto_padrao) : undefined;
  const produtoPadraoBaixo = !!itemPadrao && ((itemPadrao.quantidade ?? 0) <= 0 || (itemPadrao.estoque_minimo != null && (itemPadrao.quantidade ?? 0) < itemPadrao.estoque_minimo));
  const [produto, setProduto] = useState("");
  const [dose, setDose] = useState("");
  const [unidade, setUnidade] = useState("");
  useEffect(() => {
    const nomePadrao = evento?.produto_padrao || "";
    const compativeis = unidadesCompativeis(nomePadrao ? estoquePorNome.get(nomePadrao)?.unidade : undefined);
    setProduto(nomePadrao);
    setDose(evento?.dose_padrao != null ? String(evento.dose_padrao) : "");
    setUnidade(evento?.unidade_padrao && compativeis.includes(evento.unidade_padrao) ? evento.unidade_padrao : (compativeis[0] || ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventoId]);
  const compativeisProduto = useMemo(() => unidadesCompativeis(produto ? estoquePorNome.get(produto)?.unidade : undefined), [produto, estoquePorNome]);
  const escolherProduto = (nome: string) => {
    setProduto(nome);
    const compativeis = unidadesCompativeis(estoquePorNome.get(nome)?.unidade);
    setUnidade((u) => (compativeis.includes(u) ? u : (compativeis[0] || "")));
  };

  const numeros = useMemo(() => {
    if (vinculo === "animal") return Array.from(animaisSel);
    if (vinculo === "lote") return Array.from(selDosLotes);
    return Array.from(selDasCategorias);
  }, [vinculo, animaisSel, selDosLotes, selDasCategorias]);

  // Regra já existente no calendário sanitário para o mesmo evento preventivo
  // — pergunta se o usuário quer lançar o próximo evento já agendado (puxa
  // data/frequência dela) ou se é mesmo um lançamento avulso/novo.
  const [regraExistente, setRegraExistente] = useState<any | null>(null);
  const [decisaoRegra, setDecisaoRegra] = useState<"existente" | "ultimo" | "novo" | null>(null);
  useEffect(() => {
    setRegraExistente(null);
    setDecisaoRegra(null);
    if (!eventoId) return;
    // Vindo da Agenda para uma pendência de uma regra já existente — não
    // pergunta nada (a decisão já foi tomada ao clicar em "Dar baixa" na
    // Agenda), só busca a regra para exibir a frequência real dela aqui.
    if (calendarioIdAgenda != null) {
      fetchCalendarioSanitario({ eventoSanitarioId: Number(eventoId) })
        .then((regras: any[]) => {
          const r = regras.find((x) => x.id === calendarioIdAgenda);
          if (r) { setFreqValor(String(r.frequencia_valor)); setFreqUnidade(r.frequencia_unidade); }
        })
        .catch(() => {});
      return;
    }
    if (eventoAgenda) return;
    fetchCalendarioSanitario({ eventoSanitarioId: Number(eventoId) })
      .then((regras: any[]) => { if (regras.length) setRegraExistente(regras[0]); })
      .catch(() => {});
  }, [eventoId, eventoAgenda, calendarioIdAgenda]);
  const usarRegraExistente = () => {
    if (!regraExistente) return;
    setDataEvento(regraExistente.proxima_ocorrencia || regraExistente.data_evento);
    setFreqValor(String(regraExistente.frequencia_valor));
    setFreqUnidade(regraExistente.frequencia_unidade);
    if (regraExistente.veterinario) setVeterinario(regraExistente.veterinario);
    setDecisaoRegra("existente");
  };

  const alvoLabel = vinculo === "lote" ? lotesSelecionados.join(", ")
    : vinculo === "categoria" ? Array.from(categoriasSel).map((id) => CATEGORIAS_ANIMAIS.find((c) => c.id === id)?.label).filter(Boolean).join(", ")
    : "";

  const toggle = (n: string) => setAnimaisSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleTodos = () => setAnimaisSel((p) => p.size === animais.length ? new Set() : new Set(animais.map((a) => a.numero)));

  async function salvar() {
    setMsg(null);
    if (!eventoId) { setMsg({ tipo: "erro", txt: "Escolha o evento preventivo." }); return; }
    if (!dataEvento) { setMsg({ tipo: "erro", txt: "Informe a data de referência." }); return; }
    if (!ehExame && (!produto || dose.trim() === "" || !(Number(dose) > 0) || !unidade)) {
      setMsg({ tipo: "erro", txt: "Escolha o medicamento aplicado, a dose e a unidade." }); return;
    }
    // "Repetir a cada" aceita 0 — 0 significa "não repetir", isto é, um
    // lançamento avulso que não entra no calendário sanitário (cadastrar-
    // Preventivo do backend já cuida disso quando frequencia_valor == 0).
    const freqValorNum = freqValor.trim() === "" ? 1 : Number(freqValor);
    setSalvando(true);
    try {
      // "Já existe uma regra agendada" → Realizar/aplicar o próximo evento: é a
      // baixa de UMA OCORRÊNCIA da regra existente, não um novo cadastro — não
      // se redefine frequência agora (calendario_id faz o backend ignorar
      // frequencia_valor/unidade e só marcar a ocorrência como realizada, sem
      // duplicar a regra recorrente).
      const regraEscolhida = decisaoRegra === "existente" && regraExistente ? regraExistente.id : (calendarioIdAgenda ?? undefined);
      const r = await cadastrarPreventivo({
        evento_sanitario_id: Number(eventoId), categoria_alvo: alvoLabel || null, data_evento: dataEvento,
        frequencia_valor: freqValorNum, frequencia_unidade: freqUnidade,
        animais: numeros, aplicar: !ehExame, aplicado, veterinario: veterinario || null,
        produto: !ehExame ? produto : undefined, dose: !ehExame ? Number(dose) : undefined, unidade: !ehExame ? unidade : undefined,
        resultado_exame: ehExame && !modoNumerico && diagnostico ? diagnostico : undefined,
        resultado_numerico: ehExame && modoNumerico && resultadoNumerico !== "" ? Number(resultadoNumerico) : undefined,
        calendario_id: regraEscolhida,
      });
      // Para vacina/tratamento, "aplicado" já diz se aconteceu (some da Agenda) ou
      // não (continua pendente); exame usa o checkbox "realizado" independente.
      const marcarOcorrenciaFeita = ehExame ? realizado : aplicado;
      if (marcarOcorrenciaFeita && r?.regra?.id) {
        await marcarEventoRealizado(`calendario_sanitario_${r.regra.id}__${dataEvento}`).catch(() => {});
      }
      // Veio da Agenda (link "Dar baixa") — marca a pendência de origem como
      // realizada só se de fato foi feito, senão ela deve continuar aparecendo.
      if (eventoAgenda && marcarOcorrenciaFeita) {
        await marcarEventoRealizado(eventoAgenda).catch(() => {});
        setEventoAgenda(null);
      }
      const nApl = r?.aplicacao ? (r.aplicacao.criados || r.aplicacao.agendadas || 0) : 0;
      const agendado = !ehExame && !aplicado && nApl > 0;
      let txtDiagnostico = "";
      if (r?.resultado_exame) {
        const { resultado, banda, animais: nDiag } = r.resultado_exame;
        if (resultado === "positivo") txtDiagnostico = ` · ${nDiag} animal(is) positivo(s) — marcado(s) automaticamente "A descartar".`;
        else if (resultado === "negativo") txtDiagnostico = ` · ${nDiag} animal(is) negativo(s) (liberada).`;
        else if (resultado === "indefinido") txtDiagnostico = ` · ${nDiag} animal(is) indefinido(s) — marcado(s) para repetir o exame.`;
        else if (banda) txtDiagnostico = ` · resultado numérico: ${banda === "abaixo" ? "abaixo da faixa" : banda === "acima" ? "acima da faixa" : "dentro da faixa"}.`;
      }
      setMsg({ tipo: "ok", txt: `Preventivo registrado no calendário${nApl ? ` · ${nApl} aplicação(ões)${agendado ? " programada(s) na Agenda" : ""}` : ""}${ehExame ? " (exame — sem baixa de estoque)" : ""}${txtDiagnostico}.` });
      // Vínculo financeiro — só se aplica a vacina/exame (não avulso/tratamento).
      if (evento?.categoria_preventiva === "vacina" && r?.aplicacao?.sanidade_ids?.length) {
        setPopupOrigem({ tipo: "sanidade", ids: r.aplicacao.sanidade_ids, produto: `Vacina — ${evento.nome}`, data: dataEvento, responsavel: veterinario || null });
      } else if (ehExame && r?.resultado_exame?.ids?.length) {
        setPopupOrigem({ tipo: "exame", ids: r.resultado_exame.ids, produto: `Exame — ${evento?.nome}`, data: dataEvento, responsavel: veterinario || null });
      }
      setAnimaisSel(new Set()); setLotesSelecionados([]); setCategoriasSel(new Set());
      setDiagnostico(""); setResultadoNumerico("");
    } catch (e: any) { setMsg({ tipo: "erro", txt: e.message }); }
    finally { setSalvando(false); }
  }

  return (
    <>
      <p style={nota}>Registra um preventivo (vacina/exame/tratamento) mirando animais, categoria ou lote — grava a regra no calendário e, para vacina/tratamento, a aplicação com baixa de estoque. Exame não baixa estoque; permite vincular o veterinário.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
        <Campo label="Evento preventivo">
          <SeletorEventoPreventivo eventos={eventos} exames={exames} eventoId={eventoId} onEventoId={setEventoId}
            onEventosRecarregados={() => fetchEventosSanitarios().then((d) => setEventos(d.filter((e: any) => e.ativo))).catch(() => {})} />
        </Campo>
        <Campo label="Data de referência"><input type="date" style={inputStyle} value={dataEvento} onChange={(e) => setDataEvento(e.target.value)} /></Campo>
        {decisaoRegra === "existente" || calendarioIdAgenda != null ? (
          <Campo label="Repetir a cada">
            <p style={{ fontSize: "0.82rem", marginTop: "0.4rem" }}>
              A cada {freqValor} {FREQUENCIA_UNIDADES.find((u) => u.v === freqUnidade)?.l.toLowerCase() || freqUnidade} — herdado da regra já agendada.
            </p>
            <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>Esta é a baixa de uma ocorrência já agendada — não redefine a frequência da regra.</p>
          </Campo>
        ) : (
          <Campo label="Repetir a cada">
            <div className="flex items-center gap-2">
              <input type="number" min={0} style={inputStyle} value={freqValor} onChange={(e) => setFreqValor(e.target.value)} />
              <select style={inputStyle} value={freqUnidade} onChange={(e) => setFreqUnidade(e.target.value)}>
                {FREQUENCIA_UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}
              </select>
            </div>
            <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>0 = não repetir — evento avulso, não entra no calendário sanitário.</p>
          </Campo>
        )}
        {ehExame && (
          <Campo label="Veterinário (exame)">
            <select style={inputStyle} value={veterinario} onChange={(e) => setVeterinario(e.target.value)}>
              <option value="">Opcional</option>
              {veterinariosZootecnistas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
            </select>
          </Campo>
        )}
      </div>

      {evento && evento.doenca_nome && (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
          Previne: <strong>{evento.doenca_nome}</strong>.
          {ehExame && <span style={{ color: "var(--blue)" }}> Exame — sem baixa de estoque, só agendamento.</span>}
        </p>
      )}
      {ehExame && !evento?.doenca_nome && (
        <p style={{ fontSize: "0.75rem", color: "var(--blue)", marginTop: "0.5rem" }}>Exame — sem baixa de estoque, só agendamento.</p>
      )}

      {!ehExame && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-2">
          <Campo label="Medicamento aplicado">
            <EstoquePicker itens={estoque} value={produto} onChange={escolherProduto} placeholder="Selecionar produto…" />
            {produtoPadraoBaixo && produto === evento?.produto_padrao && (
              <p style={{ fontSize: "0.72rem", color: "var(--amber)", marginTop: "0.3rem" }}>⚠ Estoque de "{evento?.produto_padrao}" zerado, negativo ou no mínimo — considere trocar o produto.</p>
            )}
          </Campo>
          <Campo label="Dose"><input type="number" inputMode="decimal" style={inputStyle} value={dose} onChange={(e) => setDose(e.target.value)} /></Campo>
          <Campo label="Unidade">
            <select style={inputStyle} value={unidade} onChange={(e) => setUnidade(e.target.value)}>
              <option value="">Selecione…</option>
              {compativeisProduto.map((u) => <option key={u}>{u}</option>)}
            </select>
          </Campo>
        </div>
      )}

      {regraExistente && decisaoRegra === null && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 75, padding: "1rem" }}>
          <div className="card" style={{ width: "480px", maxWidth: "95vw" }}>
            <div className="card-header mb-2">Já existe uma regra agendada para este evento</div>
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>Você deseja:</p>
            <div className="flex flex-col gap-2">
              {regraExistente.ultimo_evento_data && regraExistente.ultimo_evento_id && (
                <a className="btn-secondary" style={{ textAlign: "left" }}
                  href={`/sanidade?editar_aplicacao_id=${regraExistente.ultimo_evento_id}`}>
                  Editar/dar baixa no último evento lançado? ({formatDate(regraExistente.ultimo_evento_data)})
                </a>
              )}
              <button className="btn-primary" style={{ textAlign: "left" }} onClick={usarRegraExistente}>
                Realizar/aplicar o próximo evento? ({formatDate(regraExistente.proxima_ocorrencia)})
              </button>
              <button className="btn-ghost" style={{ textAlign: "left" }} onClick={() => setDecisaoRegra("novo")}>É um novo evento avulso</button>
            </div>
          </div>
        </div>
      )}

      {ehExame && (
        <div style={{ marginTop: "0.9rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "10px", padding: "0.9rem 1rem" }}>
          <p style={{ fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.6rem" }}>Diagnóstico do exame{exameDef ? ` — ${exameDef.nome}` : ""}</p>
          {!modoNumerico ? (
            <>
              <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                {(["positivo", "negativo", "indefinido"] as const).map((r) => (
                  <button key={r} type="button" onClick={() => setDiagnostico((d) => (d === r ? "" : r))}
                    style={{ fontSize: "0.8rem", padding: "0.4rem 1rem", borderRadius: "999px", cursor: "pointer",
                      border: "1px solid " + (diagnostico === r ? "var(--dourado)" : "var(--border)"),
                      background: diagnostico === r ? "rgba(94,26,46,0.4)" : "transparent",
                      color: diagnostico === r ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: diagnostico === r ? 700 : 500 }}>
                    {LABEL_RESULTADO_EXAME[r]}
                  </button>
                ))}
              </div>
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                Aplica-se aos animais marcados abaixo. <strong>Positivo</strong> marca automaticamente "A descartar";
                {" "}<strong>negativo</strong> fica liberada; <strong>indefinido</strong> marca para repetir o exame — para fins de relatório.
              </p>
            </>
          ) : (
            <>
              <div style={{ maxWidth: 220 }}>
                <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Valor lançado</label>
                <input type="number" inputMode="decimal" style={inputStyle} value={resultadoNumerico} onChange={(e) => setResultadoNumerico(e.target.value)} />
              </div>
              {exameDef?.faixa_min != null && exameDef?.faixa_max != null && (
                <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                  Faixa cadastrada: {exameDef.faixa_min} a {exameDef.faixa_max}.
                  {exameDef.acao_abaixo && <> Abaixo: {exameDef.acao_abaixo}.</>}
                  {exameDef.acao_dentro && <> Dentro: {exameDef.acao_dentro}.</>}
                  {exameDef.acao_acima && <> Acima: {exameDef.acao_acima}.</>}
                </p>
              )}
            </>
          )}
        </div>
      )}

      <div style={{ marginTop: "0.85rem" }}>
        <TabBar<"animal" | "lote" | "categoria">
          abas={[{ id: "animal", label: "Animais" }, { id: "lote", label: "Lote" }, { id: "categoria", label: "Categoria" }]}
          ativa={vinculo} onChange={setVinculo}
        />
      </div>

      {vinculo === "animal" && (
        <div className="mt-2">
          <AnimalPickerModal
            animais={animais} selecionados={animaisSel} onToggle={toggle}
            titulo="Selecionar animal(is)"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
              { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
              { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
            ]}
          />
        </div>
      )}
      {vinculo === "lote" && (
        <div className="mt-2">
          <LotePicker opcoes={opcoesLoteDeAnimais(animais, codigosLotesTodos)} selecionados={lotesSelecionados} onChange={setLotesSelecionados} placeholder="Selecionar lote(s)…" />
          {lotesSelecionados.length > 0 && (
            <div style={{ marginTop: "0.6rem" }}>
              <AnimalPickerModal
                animais={animaisDosLotesSel} selecionados={selDosLotes} onToggle={toggleDosLotes}
                titulo="Ajustar animais do(s) lote(s) selecionado(s)"
                placeholder="Ajustar animais do(s) lote(s)…"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
                  { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
                ]}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {selDosLotes.size} de {animaisDosLotesSel.length} animal(is) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir algum.
              </p>
            </div>
          )}
        </div>
      )}
      {vinculo === "categoria" && (
        <div className="mt-2">
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Selecione uma ou mais categorias:</p>
          <div className="flex flex-wrap gap-3">
            {CATEGORIAS_ANIMAIS.map((c) => (
              <label key={c.id} className="flex items-center gap-2" style={{ fontSize: "0.8rem", cursor: "pointer" }}>
                <input type="checkbox" checked={categoriasSel.has(c.id)} onChange={() => toggleCategoria(c.id)} /> {c.label}
              </label>
            ))}
          </div>
          {categoriasSel.size > 0 && (
            <div style={{ marginTop: "0.6rem" }}>
              <AnimalPickerModal
                animais={animaisDasCategoriasSel} selecionados={selDasCategorias} onToggle={toggleDasCategorias}
                titulo="Ajustar animais das categorias selecionadas"
                placeholder="Ajustar animais das categorias…"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
                  { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
                ]}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {selDasCategorias.size} de {animaisDasCategoriasSel.length} animal(is) na(s) categoria(s) selecionada(s) — desmarque na janela acima para excluir algum.
              </p>
            </div>
          )}
        </div>
      )}

      {ehExame ? (
        <label className="flex items-center gap-2 mt-3" style={{ fontSize: "0.8rem" }}>
          <input type="checkbox" checked={realizado} onChange={(e) => setRealizado(e.target.checked)} /> Já foi realizado (não entra como pendência na Agenda)
        </label>
      ) : (
        <Campo label="Já foi aplicado?" full>
          <div className="flex items-center gap-4 mt-1">
            <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={aplicado} onChange={() => setAplicado(true)} /> Sim — aplicar e baixar o estoque agora</label>
            <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={!aplicado} onChange={() => setAplicado(false)} /> Não — só programar na Agenda</label>
          </div>
        </Campo>
      )}

      {msg && <p style={{ fontSize: "0.8rem", marginTop: "0.6rem", color: msg.tipo === "ok" ? "var(--green-light)" : "var(--red)" }}>{msg.txt}</p>}
      <div className="flex items-center gap-3 mt-3">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : `Registrar preventivo${numeros.length ? ` (${numeros.length} animais)` : ""}`}
        </button>
      </div>

      {popupOrigem && <PopupVinculoFinanceiro origem={popupOrigem} onFechar={() => setPopupOrigem(null)} />}
    </>
  );
}
