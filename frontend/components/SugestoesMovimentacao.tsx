"use client";
import { useEffect, useState } from "react";
import { Sparkles, AlertTriangle, Check, X } from "lucide-react";
import { fetchSugestoesMovimentacao, criarMovimentacao, fetchMotivosMovimentacao, fetchAnimais } from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";

type LoteSugerido = { codigo: string; nome: string; rotulo: string; motivo: string | null };
type Sugestao = { numero_matriz: string; lote_atual: string | null; lotes_sugeridos: LoteSugerido[]; motivo: string | null };

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.3rem 0.5rem", fontSize: "0.78rem",
};
const hoje = () => new Date().toISOString().split("T")[0];

function FormMover({ sugestao, motivos, onFeito, onCancelar }: { sugestao: Sugestao; motivos: string[]; onFeito: () => void; onCancelar: () => void }) {
  const [destino, setDestino] = useState(sugestao.lotes_sugeridos[0]?.codigo ?? "");
  const [motivo, setMotivo] = useState(motivos.includes("Aptidão") ? "Aptidão" : (motivos[0] ?? ""));
  const [responsavel, setResponsavel] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function confirmar() {
    setSalvando(true); setErro(null);
    try {
      await criarMovimentacao({
        data_movimento: hoje(), motivo, responsavel: responsavel || undefined,
        lote_destino_codigo: destino, animais: [sugestao.numero_matriz],
      });
      onFeito();
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
      <select style={selStyle} value={destino} onChange={(e) => setDestino(e.target.value)}>
        {sugestao.lotes_sugeridos.map((l) => <option key={l.codigo} value={l.codigo}>{l.rotulo}</option>)}
      </select>
      <select style={selStyle} value={motivo} onChange={(e) => setMotivo(e.target.value)}>
        {motivos.map((m) => <option key={m}>{m}</option>)}
      </select>
      <select style={selStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
        <option value="">Responsável…</option>
        {RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
      </select>
      <button onClick={confirmar} disabled={salvando} className="btn-primary" title="Confirmar a movimentação deste animal" style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
        <Check size={13} /> {salvando ? "Movendo…" : "Confirmar"}
      </button>
      <button onClick={onCancelar} title="Cancelar" style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", border: "1px solid var(--border)", borderRadius: "6px", background: "transparent", color: "var(--text-muted)", cursor: "pointer" }}>
        <X size={13} />
      </button>
      {erro && <span style={{ color: "var(--red)", fontSize: "0.75rem" }}>{erro}</span>}
    </div>
  );
}

export default function SugestoesMovimentacao() {
  const [dados, setDados] = useState<{ sugestoes: Sugestao[]; total: number; lotes_com_criterio: number } | null>(null);
  const [motivos, setMotivos] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [movendo, setMovendo] = useState<string | null>(null);
  const [categoriaPorAnimal, setCategoriaPorAnimal] = useState<Record<string, string>>({});
  const [fAnimal, setFAnimal] = useState("");
  const [fLote, setFLote] = useState("");
  const [fCategoria, setFCategoria] = useState("");

  function carregar() {
    fetchSugestoesMovimentacao().then(setDados).catch((e) => setError(e.message));
    fetchMotivosMovimentacao().then(setMotivos).catch(() => {});
    fetchAnimais().then((animais: any[]) => {
      const mapa: Record<string, string> = {};
      animais.forEach((a) => { mapa[a.numero] = a.categoria_abrev || a.categoria_completa || ""; });
      setCategoriaPorAnimal(mapa);
    }).catch(() => {});
  }
  useEffect(carregar, []);

  if (error) return <div className="alert-critico"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>;
  if (!dados) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;

  const opcoesLote = Array.from(new Set(dados.sugestoes.map((s) => s.lote_atual).filter(Boolean))) as string[];
  const opcoesCategoria = Array.from(new Set(dados.sugestoes.map((s) => categoriaPorAnimal[s.numero_matriz]).filter(Boolean)));
  const sugestoesFiltradas = dados.sugestoes.filter((s) =>
    (!fAnimal || s.numero_matriz.toLowerCase().includes(fAnimal.toLowerCase())) &&
    (!fLote || s.lote_atual === fLote) &&
    (!fCategoria || categoriaPorAnimal[s.numero_matriz] === fCategoria)
  );

  return (
    <div className="card">
      <div className="card-header mb-2 flex items-center gap-2"><Sparkles size={16} style={{ color: "var(--dourado)" }} /> Sugestões de movimentação</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Compara cada animal com os critérios já cadastrados por lote (Configurações {"›"} Cadastro {"›"} Lotes) e aponta quem está
        num lote diferente do que atende hoje. {dados.lotes_com_criterio === 0
          ? "Nenhum lote tem critério definido ainda — cadastre ao menos um critério por lote para começar a receber sugestões."
          : `${dados.lotes_com_criterio} lote(s) com critério configurado.`}
      </p>

      {dados.sugestoes.length === 0 && dados.lotes_com_criterio > 0 && (
        <p style={{ color: "var(--green-light)", fontSize: "0.85rem" }}>Nenhuma movimentação sugerida — o rebanho está nos lotes certos hoje.</p>
      )}

      {dados.sugestoes.length > 0 && (
        <>
          <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
            <input style={{ ...selStyle, width: "140px" }} value={fAnimal} onChange={(e) => setFAnimal(e.target.value)} placeholder="Buscar animal…" />
            <select style={selStyle} value={fLote} onChange={(e) => setFLote(e.target.value)}>
              <option value="">Todos os lotes</option>
              {opcoesLote.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
            <select style={selStyle} value={fCategoria} onChange={(e) => setFCategoria(e.target.value)}>
              <option value="">Todas as categorias</option>
              {opcoesCategoria.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          {sugestoesFiltradas.length === 0 && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma sugestão para esse filtro.</p>
          )}
          {sugestoesFiltradas.length > 0 && (
        <table className="fazenda-table">
          <thead><tr><th>Matriz</th><th>Lote atual</th><th>Lote(s) sugerido(s)</th><th>Motivo</th><th></th></tr></thead>
          <tbody>
            {sugestoesFiltradas.map((s) => (
              <tr key={s.numero_matriz}>
                <td style={{ fontWeight: 700 }}>{s.numero_matriz}</td>
                <td style={{ fontSize: "0.8rem" }}>{s.lote_atual || "—"}</td>
                <td style={{ fontSize: "0.8rem", color: "var(--dourado-light)" }}>{s.lotes_sugeridos.map((l) => l.rotulo).join(" ou ")}</td>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{s.motivo || "—"}</td>
                <td>
                  {movendo === s.numero_matriz ? (
                    <FormMover sugestao={s} motivos={motivos} onFeito={() => { setMovendo(null); carregar(); }} onCancelar={() => setMovendo(null)} />
                  ) : (
                    <button onClick={() => setMovendo(s.numero_matriz)} title={`Mover ${s.numero_matriz} para o lote sugerido`}
                      style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem", borderRadius: "6px", border: "1px solid var(--dourado)", background: "transparent", color: "var(--dourado-light)", cursor: "pointer" }}>
                      Mover
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
          )}
        </>
      )}
    </div>
  );
}
