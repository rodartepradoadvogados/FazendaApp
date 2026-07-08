"use client";
import { useEffect, useMemo, useState } from "react";
import { ArrowRightLeft, AlertTriangle, Check } from "lucide-react";
import { fetchAnimais, fetchLotes, criarMovimentacao } from "@/lib/api";
import { RESPONSAVEIS, MOTIVOS_MOVIMENTACAO } from "@/lib/constants";

type Animal = { numero: string; grupo_primario: string | null; categoria_abrev: string | null; del_dias: number | null };
type Lote = { id: number; codigo: string; nome: string; rotulo: string };

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const hoje = () => new Date().toISOString().split("T")[0];
const agora = () => new Date().toTimeString().slice(0, 5);

export default function MovimentarAnimais() {
  const [animais, setAnimais] = useState<Animal[] | null>(null);
  const [lotes, setLotes] = useState<Lote[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [origemCodigo, setOrigemCodigo] = useState("");
  const [destinoCodigo, setDestinoCodigo] = useState("");
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [data, setData] = useState(hoje());
  const [hora, setHora] = useState(agora());
  const [motivo, setMotivo] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  const carregar = () => {
    fetchAnimais().then(setAnimais).catch((e) => setError(e.message));
    fetchLotes().then(setLotes).catch((e) => setError(e.message));
  };
  useEffect(carregar, []);

  const origemLote = lotes?.find((l) => l.codigo === origemCodigo) || null;
  const candidatos = useMemo(() => {
    if (!animais || !origemLote) return [];
    return animais.filter((a) => a.grupo_primario === origemLote.rotulo);
  }, [animais, origemLote]);

  const toggleAnimal = (numero: string) => setSelecionados((p) => {
    const n = new Set(p); n.has(numero) ? n.delete(numero) : n.add(numero); return n;
  });
  const toggleTodos = () => setSelecionados((p) =>
    p.size === candidatos.length ? new Set() : new Set(candidatos.map((a) => a.numero))
  );

  const limparSelecao = () => { setOrigemCodigo(""); setDestinoCodigo(""); setSelecionados(new Set()); setObservacao(""); };

  const salvar = async () => {
    setMsg(null);
    if (!origemCodigo || !destinoCodigo) { setMsg({ tipo: "erro", texto: "Selecione o lote de origem e o de destino." }); return; }
    if (origemCodigo === destinoCodigo) { setMsg({ tipo: "erro", texto: "O lote de destino deve ser diferente do de origem." }); return; }
    if (!selecionados.size) { setMsg({ tipo: "erro", texto: "Selecione ao menos um animal." }); return; }
    if (!motivo) { setMsg({ tipo: "erro", texto: "Selecione o motivo da movimentação." }); return; }

    setSalvando(true);
    try {
      const r = await criarMovimentacao({
        data_movimento: data, hora_movimento: hora, motivo, observacao: observacao || undefined,
        responsavel: responsavel || undefined, lote_destino_codigo: destinoCodigo, animais: Array.from(selecionados),
      });
      setMsg({ tipo: "sucesso", texto: `${r.movidos} animal(is) movido(s) com sucesso.` });
      limparSelecao();
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao mover animais" });
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><ArrowRightLeft size={22} style={{ color: "var(--dourado)" }} /> Movimentar animais</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Selecione o lote de origem, o de destino e os animais (individual ou em lote), com data, hora e motivo.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {(!animais || !lotes) && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {animais && lotes && (
        <div className="card">
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
            <div><label style={labelStyle}>Lote de origem</label>
              <select style={selStyle} value={origemCodigo} onChange={(e) => { setOrigemCodigo(e.target.value); setSelecionados(new Set()); }}>
                <option value="">Selecione...</option>
                {lotes.map((l) => <option key={l.id} value={l.codigo}>{l.rotulo}</option>)}
              </select></div>
            <div><label style={labelStyle}>Lote de destino</label>
              <select style={selStyle} value={destinoCodigo} onChange={(e) => setDestinoCodigo(e.target.value)}>
                <option value="">Selecione...</option>
                {lotes.filter((l) => l.codigo !== origemCodigo).map((l) => <option key={l.id} value={l.codigo}>{l.rotulo}</option>)}
              </select></div>
            <div><label style={labelStyle}>Data</label>
              <input type="date" style={selStyle} value={data} onChange={(e) => setData(e.target.value)} /></div>
            <div><label style={labelStyle}>Hora</label>
              <input type="time" style={selStyle} value={hora} onChange={(e) => setHora(e.target.value)} /></div>
            <div><label style={labelStyle}>Motivo</label>
              <select style={selStyle} value={motivo} onChange={(e) => setMotivo(e.target.value)}>
                <option value="">Selecione...</option>
                {MOTIVOS_MOVIMENTACAO.map((m) => <option key={m}>{m}</option>)}
              </select></div>
            <div><label style={labelStyle}>Responsável</label>
              <select style={selStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
                <option value="">Selecione...</option>
                {RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
              </select></div>
          </div>

          <div className="mb-4">
            <label style={labelStyle}>Observação (opcional)</label>
            <input style={selStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} placeholder="ex.: transferência após diagnóstico de prenhez" />
          </div>

          {origemLote && (
            <div style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden", marginBottom: "1rem" }}>
              <div style={{ background: "var(--surface-2)", padding: "0.55rem 0.9rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: "0.85rem" }}>Animais do lote {origemLote.rotulo} ({candidatos.length})</span>
                <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={toggleTodos}>
                  {selecionados.size === candidatos.length && candidatos.length ? "Limpar seleção" : "Selecionar todos"}
                </button>
              </div>
              <div className="overflow-x-auto" style={{ maxHeight: "360px" }}>
                <table className="fazenda-table" style={{ margin: 0 }}>
                  <thead><tr><th></th><th>Nº</th><th>Categoria</th><th style={{ textAlign: "right" }}>DEL</th></tr></thead>
                  <tbody>
                    {candidatos.map((a) => (
                      <tr key={a.numero} style={{ cursor: "pointer" }} onClick={() => toggleAnimal(a.numero)}>
                        <td><input type="checkbox" checked={selecionados.has(a.numero)} onChange={() => toggleAnimal(a.numero)} /></td>
                        <td style={{ fontWeight: 700 }}>{a.numero}</td>
                        <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || "—"}</td>
                        <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                      </tr>
                    ))}
                    {!candidatos.length && <tr><td colSpan={4} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum animal ativo neste lote.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {msg && (
            <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.85rem", marginBottom: "0.75rem" }}>{msg.texto}</p>
          )}
          <button className="btn-primary" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={salvar} disabled={salvando}>
            <Check size={14} /> {salvando ? "Movendo…" : `Mover ${selecionados.size || ""} animal(is)`}
          </button>
        </div>
      )}
    </div>
  );
}
