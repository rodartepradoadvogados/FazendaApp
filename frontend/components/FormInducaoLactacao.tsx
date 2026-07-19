"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  fetchProtocolosInducaoLactacao, lancarInducaoLactacao, fetchInducaoLactacaoAtivos, formatDate, fetchPessoas,
} from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, nota, codigoGrupo } from "@/components/lancamentos/comumForms";

function InducaoLactacaoAtivos({ recarregarRef }: { recarregarRef: React.MutableRefObject<() => void> }) {
  const [ativos, setAtivos] = useState<any[] | null>(null);
  const [abertos, setAbertos] = useState<Set<number>>(new Set());
  const toggle = (id: number) => setAbertos((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const carregar = () => fetchInducaoLactacaoAtivos().then(setAtivos).catch(() => setAtivos([]));
  useEffect(() => { carregar(); recarregarRef.current = carregar; }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ativos || !ativos.length) return null;
  return (
    <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
      <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
        Induções de lactação em andamento ({ativos.length})
      </div>
      <div className="space-y-2">
        {ativos.map((p) => {
          const aberto = abertos.has(p.lancamento_id);
          return (
            <div key={p.lancamento_id} style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
              <button onClick={() => toggle(p.lancamento_id)} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.8rem", background: "var(--surface)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                {aberto ? <ChevronDown size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} /> : <ChevronRight size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />}
                <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{p.nome_protocolo}</span>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Início {formatDate(p.data_d0)} — {p.animais.length} animal(is)</span>
              </button>
              {aberto && (
                <table className="fazenda-table" style={{ margin: 0 }}>
                  <thead><tr><th>Nº</th><th>Etapa atual</th><th>Data</th></tr></thead>
                  <tbody>
                    {p.animais.map((a: any) => (
                      <tr key={a.numero_matriz}>
                        <td style={{ fontWeight: 700 }}>{a.numero_matriz}</td>
                        <td>{a.etapa_atual}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{a.data_etapa_atual ? formatDate(a.data_etapa_atual) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function FormInducaoLactacao({ animais }: { animais: AnimalRow[] }) {
  const [protocolos, setProtocolos] = useState<any[]>([]);
  const [protocoloId, setProtocoloId] = useState("");
  // Animal(is) ou lote(s) — mesmo padrão do Diagnóstico/Secagem.
  const [vinculo, setVinculo] = useState<"animal" | "lote">("animal");
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
  const numerosAlvo = vinculo === "lote" ? selLote : sel;

  const [dataD0, setDataD0] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const recarregarAtivosRef = useRef(() => {});
  const [pessoas, setPessoas] = useState<any[]>([]);

  useEffect(() => { fetchProtocolosInducaoLactacao().then(setProtocolos).catch(() => setProtocolos([])); }, []);
  useEffect(() => { fetchPessoas().then(setPessoas).catch(() => setPessoas([])); }, []);
  const protocolo = protocolos.find((p) => String(p.id) === protocoloId);
  const pessoasAtivas = useMemo(
    () => pessoas.filter((p) => p.ativo !== false).sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    [pessoas]
  );

  async function salvar() {
    setErro(null); setSucesso(null);
    const animaisAlvo = Array.from(numerosAlvo);
    if (!protocoloId) { setErro("Selecione o protocolo de indução."); return; }
    if (!animaisAlvo.length) { setErro("Selecione ao menos uma matriz (ou lote)."); return; }
    if (!dataD0) { setErro(`Informe a data do ${protocolo?.dia_inicial === 0 ? "D0" : "D1"}.`); return; }
    setSalvando(true);
    try {
      const r = await lancarInducaoLactacao({
        protocolo_id: Number(protocoloId), animais: animaisAlvo, data_d0: dataD0,
        responsavel: responsavel || undefined, observacao: observacao || undefined,
      });
      setSucesso(`Protocolo "${protocolo?.nome}" lançado para ${r.animais} animal(is) — ${r.eventos_criados} eventos na Agenda.`);
      setSel(new Set()); setLotesSelecionados([]);
      recarregarAtivosRef.current();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar indução de lactação");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Protocolo" full>
          <select style={inputStyle} value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
            <option value="">Selecione o protocolo…</option>
            {protocolos.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.duracao_dias} dias)</option>)}
          </select>
        </Campo>
        <Campo label={`Data do ${protocolo?.dia_inicial === 0 ? "D0" : "D1"} (1º dia do cronograma)`}>
          <input type="date" style={inputStyle} value={dataD0} onChange={(e) => setDataD0(e.target.value)} />
        </Campo>
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

      <Campo label="Matriz(es) — animal(is) ou lote(s)" full>
        <TabBar<"animal" | "lote">
          abas={[
            { id: "animal", label: "Animal(is)", title: "Selecionar matrizes individualmente" },
            { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes" },
          ]}
          ativa={vinculo}
          onChange={setVinculo}
        />
        {vinculo === "animal" ? (
          <AnimalPickerModal
            animais={animais} selecionados={sel} onToggle={toggle}
            titulo="Escolher matriz(es) para indução de lactação"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
            ]}
          />
        ) : (
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
                  titulo="Ajustar matrizes do(s) lote(s) selecionado(s)"
                  placeholder="Ajustar matrizes do(s) lote(s)…"
                  colunas={[
                    { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                    { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  ]}
                />
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  {selLote.size} de {animaisDoLoteSel.length} matriz(es) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir alguma.
                </p>
              </div>
            )}
          </div>
        )}
      </Campo>

      {protocolo && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
            Cronograma — vai para a Agenda
          </div>
          {protocolo.observacao && <p style={nota}>{protocolo.observacao}</p>}
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Dia</th><th>Medicamento(s)</th><th>Manejo</th></tr></thead>
              <tbody>
                {Array.from(new Set((protocolo.etapas || []).map((e: any) => e.dia))).sort((a: any, b: any) => a - b).map((dia: any) => {
                  const doDia = (protocolo.etapas || []).filter((e: any) => e.dia === dia);
                  const meds = doDia.filter((e: any) => e.tipo === "medicamento")
                    .map((e: any) => `${e.dose ? `${e.dose}${e.unidade ? ` ${e.unidade}` : ""} ` : ""}${e.produto}`).join(" + ") || "—";
                  const manejo = doDia.filter((e: any) => e.tipo !== "medicamento")
                    .map((e: any) => e.tipo === "dispositivo" ? (e.acao_dispositivo === "colocar" ? "Colocar Implante de Progesterona" : "Retirar o Implante de Progesterona") : e.produto)
                    .join(" + ") || "—";
                  return (
                    <tr key={dia}>
                      <td style={{ fontWeight: 700 }}>D{dia}</td>
                      <td>{meds}</td>
                      <td style={{ color: manejo !== "—" ? "var(--amber)" : undefined }}>{manejo}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <InducaoLactacaoAtivos recarregarRef={recarregarAtivosRef} />
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando || !numerosAlvo.size}>
          {salvando ? "Salvando…" : `Salvar (${numerosAlvo.size || 0} animal${numerosAlvo.size !== 1 ? "is" : ""})`}
        </button>
      </div>
    </>
  );
}
