"use client";
// Configurações › Cadastro › Central de Sêmen › Estoque mínimo — os 2
// parâmetros agregados por TIPO (convencional/sexado) que substituem o antigo
// MINIMO_SEMEN hardcoded; consumidos por cadastro.semen_disponivel e pelo
// alerta diário de sêmen abaixo do mínimo na Agenda.
import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, Pencil, SlidersHorizontal } from "lucide-react";
import { atualizarParametro, ehAdmin, fetchParametros } from "@/lib/api";

type Item = { chave: string; label: string; valor: number | string | boolean | null; unidade: string | null; tipo?: string };
type Grupo = { titulo: string; itens: Item[] };

export default function CadastroSemenMinimo() {
  const [grupo, setGrupo] = useState<Grupo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState(false);
  const [valores, setValores] = useState<Record<string, number>>({});
  const [salvando, setSalvando] = useState(false);
  const [salvoOk, setSalvoOk] = useState(false);
  const podeEditar = ehAdmin();

  const carregar = () =>
    fetchParametros()
      .then((d) => setGrupo(d.grupos?.estoque_semen ?? null))
      .catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const concluirEdicao = async () => {
    if (!grupo) return;
    const alterados = grupo.itens.filter((it) => it.chave in valores && valores[it.chave] !== it.valor);
    setEditando(false);
    if (!alterados.length) return;
    setSalvando(true);
    try {
      for (const it of alterados) await atualizarParametro(it.chave, valores[it.chave]);
      await carregar();
      setSalvoOk(true);
      setTimeout(() => setSalvoOk(false), 2000);
    } catch (e: any) {
      setError(e.message || "Erro ao salvar parâmetro");
    } finally {
      setSalvando(false);
    }
  };

  const inputStyle = {
    width: "5rem", textAlign: "right" as const, background: "var(--surface-2)", color: "var(--text)",
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.2rem 0.4rem", fontSize: "0.82rem",
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <SlidersHorizontal size={18} style={{ color: "var(--dourado-light)" }} /> Estoque mínimo de sêmen
        </h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
          Mínimo agregado por tipo (não por touro) — usado no alerta de estoque baixo na Agenda e nos cadastros/listagens de sêmen da fazenda.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{error}</span></div>}
      {!grupo && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {grupo && (
        <div className="card" style={{ maxWidth: "24rem" }}>
          <div className="card-header mb-3 flex items-center justify-between">
            <span>{grupo.titulo}</span>
            {podeEditar && (
              <button
                onClick={() => (editando ? concluirEdicao() : setEditando(true))}
                disabled={salvando}
                title={editando ? "Concluir" : "Editar"}
                style={{ background: "none", border: "none", color: "var(--dourado-light)", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem" }}>
                {salvando ? <><Loader2 size={13} className="animate-spin" /> Salvando…</>
                  : editando ? <><Check size={13} /> Concluir</> : <><Pencil size={13} /> Editar</>}
              </button>
            )}
          </div>
          <table className="fazenda-table">
            <tbody>
              {grupo.itens.map((it) => {
                const valorAtual = valores[it.chave] ?? it.valor;
                return (
                  <tr key={it.chave}>
                    <td style={{ fontSize: "0.82rem" }}>{it.label}</td>
                    <td style={{ textAlign: "right", fontWeight: 700, whiteSpace: "nowrap" }}>
                      {editando ? (
                        <input type="number" min={0} defaultValue={Number(valorAtual)}
                          onChange={(e) => setValores((p) => ({ ...p, [it.chave]: Number(e.target.value) }))}
                          style={inputStyle} />
                      ) : (
                        <>{String(valorAtual)}</>
                      )}
                      {it.unidade && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem", marginLeft: "0.25rem" }}>{it.unidade}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {salvoOk && <p style={{ fontSize: "0.68rem", color: "var(--verde, #2f9e5c)", marginTop: "0.5rem" }}>Salvo — já vale para agenda, cadastros e listagens de sêmen.</p>}
        </div>
      )}
    </div>
  );
}
