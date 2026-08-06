"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import {
  fetchLidasParaLancar, lancarLida, fetchLidasAtivas, cancelarProtocolo, formatDate, fetchPessoas,
  type Lida,
} from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, nota, codigoGrupo } from "@/components/lancamentos/comumForms";

function LidasAtivas({ recarregarRef }: { recarregarRef: React.MutableRefObject<() => void> }) {
  const [ativos, setAtivos] = useState<any[] | null>(null);
  const [abertos, setAbertos] = useState<Set<number>>(new Set());
  const [cancelando, setCancelando] = useState<number | null>(null);
  const toggle = (id: number) => setAbertos((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const carregar = () => fetchLidasAtivas().then(setAtivos).catch(() => setAtivos([]));
  useEffect(() => { carregar(); recarregarRef.current = carregar; }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const cancelar = async (lancamentoId: number) => {
    if (!window.confirm("Cancelar esta lida? As pendências saem da Agenda; o que já foi confirmado permanece no histórico.")) return;
    setCancelando(lancamentoId);
    try { await cancelarProtocolo("lida", lancamentoId); await carregar(); }
    finally { setCancelando(null); }
  };

  if (!ativos || !ativos.length) return null;
  return (
    <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
      <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
        Lidas em andamento ({ativos.length})
      </div>
      <div className="space-y-2">
        {ativos.map((p) => {
          const aberto = abertos.has(p.lancamento_id);
          return (
            <div key={p.lancamento_id} style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", background: "var(--surface)" }}>
                <button onClick={() => toggle(p.lancamento_id)} style={{ flex: 1, display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.8rem", background: "none", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                  {aberto ? <ChevronDown size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} /> : <ChevronRight size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />}
                  <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{p.nome_protocolo}</span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Início {formatDate(p.data_inicio)} — {p.animais.length ? `${p.animais.length} animal(is)` : p.alvo_tipo === "lote" ? "lote" : "tarefa da fazenda"}
                    {p.lote ? ` — ${p.lote}` : ""} — {p.pendentes} de {p.total_etapas} pendente(s)
                  </span>
                </button>
                <button
                  onClick={() => cancelar(p.lancamento_id)} disabled={cancelando === p.lancamento_id}
                  className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem", marginRight: "0.6rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                  title="Cancelar lançamento — remove as pendências da Agenda"
                >
                  <X size={13} /> {cancelando === p.lancamento_id ? "Cancelando…" : "Cancelar"}
                </button>
              </div>
              {aberto && (
                <div style={{ padding: "0.6rem 0.8rem", fontSize: "0.8rem" }}>
                  <p style={{ color: "var(--text-muted)", marginBottom: "0.3rem" }}>
                    Próxima: <strong style={{ color: "var(--text)" }}>{p.proxima_etapa}</strong> em {formatDate(p.proxima_data)}
                    {p.proxima_foto_obrigatoria ? " — foto obrigatória" : ""}
                    {p.responsavel ? ` — responsável: ${p.responsavel}` : ""}
                  </p>
                  {!!p.animais.length && (
                    <p style={{ color: "var(--text-muted)" }}>Animais: {p.animais.join(", ")}</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function FormLida({ animais }: { animais: AnimalRow[] }) {
  const [lidas, setLidas] = useState<Lida[]>([]);
  const [lidaId, setLidaId] = useState("");
  const [vinculo, setVinculo] = useState<"animal" | "lote" | "fazenda">("fazenda");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const codigosLotes = useMemo(
    () => Array.from(new Set(animais.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [animais]
  );
  const animaisDoLoteSel = useMemo(() => {
    const cods = new Set(lotesSelecionados);
    return animais.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [animais, lotesSelecionados]);
  const [selLote, setSelLote] = useState<Set<string>>(new Set());
  const toggleLote = (n: string) => setSelLote((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelLote(new Set(animaisDoLoteSel.map((a) => a.numero)));
  }, [lotesSelecionados.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  const numerosAlvo = vinculo === "lote" ? selLote : vinculo === "fazenda" ? new Set<string>() : sel;

  const [rotuloTarefa, setRotuloTarefa] = useState("");
  const [dataInicio, setDataInicio] = useState("");
  const [dataFim, setDataFim] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const recarregarAtivosRef = useRef(() => {});
  const [pessoas, setPessoas] = useState<any[]>([]);

  useEffect(() => { fetchLidasParaLancar().then(setLidas).catch(() => setLidas([])); }, []);
  useEffect(() => { fetchPessoas().then(setPessoas).catch(() => setPessoas([])); }, []);
  const lida = lidas.find((l) => String(l.id) === lidaId);
  const pessoasAtivas = useMemo(
    () => pessoas.filter((p) => p.ativo !== false).sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    [pessoas]
  );

  async function salvar() {
    setErro(null); setSucesso(null);
    const animaisAlvo = Array.from(numerosAlvo);
    if (!lidaId) { setErro("Selecione a lida."); return; }
    if (vinculo !== "fazenda" && !animaisAlvo.length) { setErro("Selecione ao menos uma matriz (ou lote), ou escolha \"Tarefa da fazenda\"."); return; }
    if (!dataInicio) { setErro(lida?.modo === "frequencia" ? "Informe a data de início." : `Informe a data do ${lida?.dia_inicial === 0 ? "D0" : "D1"}.`); return; }
    if (lida?.modo === "frequencia" && !dataFim) { setErro("Informe até quando esta lida se repete."); return; }
    setSalvando(true);
    try {
      const lote = vinculo === "lote" ? lotesSelecionados.join(", ") : vinculo === "fazenda" ? (rotuloTarefa || undefined) : undefined;
      const r = await lancarLida({
        lida_id: Number(lidaId), animais: animaisAlvo, lote, data_inicio: dataInicio,
        data_fim: lida?.modo === "frequencia" ? dataFim : undefined,
        responsavel: responsavel || undefined, observacao: observacao || undefined,
      });
      // `criado: false` = o backend achou um lançamento ativo idêntico (mesma
      // lida, mesma data, mesmo período gerado e mesmo(s) animal(is) ou mesma
      // tarefa/lote) e reaproveitou em vez de duplicar — duplo clique ou
      // retry da fila offline. Sem este ramo a tela dizia "lançada ... — 0
      // ocorrência(s) na Agenda", que parece defeito (mesmo padrão de
      // FormInducaoLactacao).
      setSucesso(r.criado === false
        ? (r.aviso || "Esta lida já estava lançada para este alvo nesta data — nada foi duplicado.")
        : vinculo === "fazenda"
          ? `Lida "${lida?.nome}" lançada como tarefa da fazenda — ${r.eventos_criados} ocorrência(s) na Agenda.`
          : `Lida "${lida?.nome}" lançada para ${r.animais} animal(is) — ${r.eventos_criados} ocorrência(s) na Agenda.`
      );
      setSel(new Set()); setLotesSelecionados([]); setRotuloTarefa("");
      recarregarAtivosRef.current();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar a lida");
    } finally {
      setSalvando(false);
    }
  }

  const podeSalvar = vinculo === "fazenda" ? true : numerosAlvo.size > 0;

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Lida" full>
          <select style={inputStyle} value={lidaId} onChange={(e) => setLidaId(e.target.value)}>
            <option value="">Selecione a lida…</option>
            {lidas.map((l) => <option key={l.id} value={l.id}>{l.nome} ({l.modo === "frequencia" ? `a cada ${l.frequencia_dias}d` : `${l.duracao_dias ?? "?"} dias`})</option>)}
          </select>
        </Campo>
        <Campo label={lida?.modo === "frequencia" ? "De" : `Data do ${lida?.dia_inicial === 0 ? "D0" : "D1"} (1º dia)`}>
          <input type="date" style={inputStyle} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} />
        </Campo>
        {lida?.modo === "frequencia" && (
          <Campo label="Até">
            <input type="date" style={inputStyle} value={dataFim} onChange={(e) => setDataFim(e.target.value)} />
          </Campo>
        )}
        <Campo label="Responsável">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
            <option value="">Opcional</option>
            {pessoasAtivas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
          </select>
        </Campo>
        <Campo label="Observação" full>
          <input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} placeholder="Opcional" />
        </Campo>
      </div>

      <Campo label="Alvo do lançamento" full>
        <TabBar<"animal" | "lote" | "fazenda">
          abas={[
            { id: "fazenda", label: "Tarefa da fazenda", title: "Sem animal específico — a maioria das lidas é assim" },
            { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes" },
            { id: "animal", label: "Animal(is)", title: "Selecionar matrizes individualmente" },
          ]}
          ativa={vinculo}
          onChange={setVinculo}
        />
        {vinculo === "animal" ? (
          <AnimalPickerModal
            animais={animais} selecionados={sel} onToggle={toggle}
            titulo="Escolher animal(is) para a lida"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
            ]}
          />
        ) : vinculo === "lote" ? (
          <div style={{ marginTop: "0.5rem" }}>
            <LotePicker
              opcoes={opcoesLoteDeAnimais(animais, codigosLotes)}
              selecionados={lotesSelecionados}
              onChange={setLotesSelecionados}
              placeholder="Selecionar lote(s)…"
            />
            {lotesSelecionados.length > 0 && (
              <div style={{ marginTop: "0.6rem" }}>
                <AnimalPickerModal
                  animais={animaisDoLoteSel} selecionados={selLote} onToggle={toggleLote}
                  titulo="Ajustar animais do(s) lote(s) selecionado(s)"
                  placeholder="Ajustar animais do(s) lote(s)…"
                  colunas={[
                    { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                    { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  ]}
                />
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  {selLote.size} de {animaisDoLoteSel.length} animal(is) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir algum.
                </p>
              </div>
            )}
          </div>
        ) : (
          <div style={{ marginTop: "0.5rem" }}>
            <p style={nota}>
              Cria uma pendência sem vincular a nenhum animal — ex.: limpar um cocho, acompanhar uma obra, manutenção
              de equipamento.
            </p>
            <Campo label="Rótulo (opcional)">
              <input style={inputStyle} value={rotuloTarefa} onChange={(e) => setRotuloTarefa(e.target.value)} placeholder="ex.: Curral 2" />
            </Campo>
          </div>
        )}
      </Campo>

      {lida && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
            {lida.modo === "frequencia" ? `Repete a cada ${lida.frequencia_dias} dias` : "Etapas — vai para a Agenda"}
          </div>
          {lida.observacao && <p style={nota}>{lida.observacao}</p>}
          {lida.modo === "frequencia" ? (
            <p style={{ fontSize: "0.82rem" }}>{lida.descricao_evento}{lida.insumo_padrao ? ` — ${lida.insumo_padrao}${lida.insumo_dose ? ` (${lida.insumo_dose} ${lida.insumo_unidade || ""})` : ""}` : ""}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr><th>Dia</th><th>O que fazer</th><th>Insumo</th></tr></thead>
                <tbody>
                  {lida.etapas.map((e, i) => (
                    <tr key={i}>
                      <td style={{ fontWeight: 700 }}>D{e.dia_inicio - lida.dia_inicial}{e.dia_fim != null ? ` a D${e.dia_fim - lida.dia_inicial}` : ""}</td>
                      <td>{e.descricao_evento}{e.foto_obrigatoria ? " (foto obrigatória)" : ""}</td>
                      <td>{e.insumo_padrao ? `${e.insumo_padrao}${e.insumo_dose ? ` (${e.insumo_dose} ${e.insumo_unidade || ""})` : ""}` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      <LidasAtivas recarregarRef={recarregarAtivosRef} />
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando || !podeSalvar}>
          {salvando ? "Salvando…" : vinculo === "fazenda" ? "Salvar (tarefa da fazenda)" : `Salvar (${numerosAlvo.size || 0} ${numerosAlvo.size !== 1 ? "animais" : "animal"})`}
        </button>
      </div>
    </>
  );
}
