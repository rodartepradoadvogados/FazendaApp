"use client";
// Configurações > Parâmetros > Alertas de indicador — "avise-me se o
// indicador X passar de Y". Cada alerta é do próprio usuário logado (não é
// configuração compartilhada da fazenda, ao contrário das faixas de
// bonificação) — por isso não tem gate de admin.
import { Fragment, useEffect, useState } from "react";
import { BellRing, Pencil, Check, X, Plus, AlertTriangle } from "lucide-react";
import {
  fetchCatalogoIndicadores, fetchAlertasIndicador, criarAlertaIndicador, editarAlertaIndicador, excluirAlertaIndicador,
  type IndicadorCatalogo, type AlertaIndicador,
} from "@/lib/api";

const OPERADORES: { value: string; label: string }[] = [
  { value: "<", label: "abaixo de" },
  { value: "<=", label: "no máximo" },
  { value: ">", label: "acima de" },
  { value: ">=", label: "no mínimo" },
];
const labelOperador = (v: string) => OPERADORES.find((o) => o.value === v)?.label ?? v;

type Form = { indicador_chave: string; operador: string; valor_limite: string };

export default function AlertasIndicador() {
  const [catalogo, setCatalogo] = useState<IndicadorCatalogo[]>([]);
  const [alertas, setAlertas] = useState<AlertaIndicador[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>({ indicador_chave: "", operador: "<", valor_limite: "" });
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = () => {
    fetchCatalogoIndicadores().then((c) => { setCatalogo(c); setForm((f) => ({ ...f, indicador_chave: f.indicador_chave || c[0]?.chave || "" })); }).catch(() => {});
    fetchAlertasIndicador().then(setAlertas).catch((e) => setError(e.message));
  };
  useEffect(() => { carregar(); }, []);

  const abrirNovo = () => { setForm({ indicador_chave: catalogo[0]?.chave || "", operador: "<", valor_limite: "" }); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (a: AlertaIndicador) => { setForm({ indicador_chave: a.indicador_chave, operador: a.operador, valor_limite: String(a.valor_limite) }); setEditando(a.id); setMsg(null); };
  const cancelar = () => { setEditando(null); setMsg(null); };

  async function salvar() {
    if (form.valor_limite.trim() === "" || isNaN(Number(form.valor_limite))) {
      setMsg("Informe o valor-limite.");
      return;
    }
    setSalvando(true); setMsg(null);
    try {
      if (editando === "novo") {
        await criarAlertaIndicador({ indicador_chave: form.indicador_chave, operador: form.operador, valor_limite: Number(form.valor_limite) });
      } else if (editando !== null) {
        await editarAlertaIndicador(editando, { operador: form.operador, valor_limite: Number(form.valor_limite) });
      }
      setEditando(null);
      carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function alternarAtivo(a: AlertaIndicador) {
    try { await editarAlertaIndicador(a.id, { ativo: !a.ativo }); carregar(); } catch { /* mantém a lista anterior */ }
  }

  async function excluir(a: AlertaIndicador) {
    if (!confirm(`Excluir o alerta de "${a.indicador_label}"?`)) return;
    try { await excluirAlertaIndicador(a.id); carregar(); } catch (e: any) { setError(e.message || "Erro ao excluir"); }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
  };

  const FormAlerta = (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div>
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Indicador</label>
          <select style={inputStyle} value={form.indicador_chave} disabled={editando !== "novo"} onChange={(e) => setForm({ ...form, indicador_chave: e.target.value })}>
            {catalogo.map((c) => <option key={c.chave} value={c.chave}>{c.label}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Avisar quando estiver…</label>
          <select style={inputStyle} value={form.operador} onChange={(e) => setForm({ ...form, operador: e.target.value })}>
            {OPERADORES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Valor-limite</label>
          <input type="number" step="0.1" style={inputStyle} value={form.valor_limite} onChange={(e) => setForm({ ...form, valor_limite: e.target.value })} />
        </div>
      </div>
      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={cancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><BellRing size={16} /> Meus alertas de indicador</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo alerta
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Escolha um indicador, uma condição e um valor-limite — quando a condição for atendida, você recebe um aviso na central de notificações (sino) e via push, até resolver.
      </p>

      {/* A taxa de concepção mudou de base de cálculo (virou a do motor de
          ciclos de 21 dias). O limiar salvo é o mesmo número de antes, mas
          agora é comparado com outra conta — quem já tinha alerta precisa
          reconferir o valor. */}
      <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.8rem", borderLeft: "2px solid var(--amber)", paddingLeft: "0.6rem" }}>
        <strong>Mudou o cálculo da taxa de concepção:</strong> ela passou a ser apurada por ciclos de 21 dias
        (com a regra dos 28 dias para o diagnóstico), a mesma conta da tela de Ciclos de 21 Dias. O valor-limite
        que você salvou continua o mesmo número — mas o indicador comparado com ele é outro. Se você já tinha um
        alerta de taxa de concepção, vale reconferir o limite.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!alertas && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && FormAlerta}

      {alertas && (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Indicador</th><th>Condição</th><th>Valor atual</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {alertas.map((a) => (
                <Fragment key={a.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{a.indicador_label}{!a.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ fontSize: "0.82rem" }}>{labelOperador(a.operador)} {a.valor_limite}</td>
                    <td style={{ fontSize: "0.82rem" }}>{a.valor_atual ?? "—"}</td>
                    <td>
                      {a.ativo && a.disparado
                        ? <span style={{ color: "var(--amber)", fontWeight: 600, fontSize: "0.78rem" }}>Disparado</span>
                        : <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{a.ativo ? "Dentro do esperado" : "—"}</span>}
                    </td>
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => alternarAtivo(a)}>
                        {a.ativo ? "Desativar" : "Ativar"}
                      </button>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", marginLeft: "0.5rem" }} onClick={() => abrirEdicao(a)}>
                        <Pencil size={13} /> Editar
                      </button>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", color: "var(--red)", marginLeft: "0.5rem" }} onClick={() => excluir(a)}>
                        <X size={13} /> Excluir
                      </button>
                    </td>
                  </tr>
                  {editando === a.id && (
                    <tr><td colSpan={5} style={{ padding: 0 }}>{FormAlerta}</td></tr>
                  )}
                </Fragment>
              ))}
              {!alertas.length && (
                <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  Nenhum alerta cadastrado ainda.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
