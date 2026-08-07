"use client";
import { Fragment, useEffect, useState } from "react";
import { Sprout, Plus, Pencil, Trash2, AlertTriangle, Check, X } from "lucide-react";
import { fetchSafras, criarSafra, atualizarSafra, confirmarExclusao, ehAdmin } from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type Safra = {
  id: number; nome: string; centro_custo: string;
  data_inicio: string; data_fim: string;
  hectares: number; toneladas_produzidas: number;
  observacao: string | null; ativo: boolean;
};

type Form = {
  nome: string; centro_custo: string; data_inicio: string; data_fim: string;
  hectares: string; toneladas_produzidas: string; observacao: string; ativo: boolean;
};

const formVazio: Form = {
  nome: "", centro_custo: "Agricultura", data_inicio: "", data_fim: "",
  hectares: "", toneladas_produzidas: "", observacao: "", ativo: true,
};

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

function paraPayload(form: Form) {
  return {
    nome: form.nome.trim(),
    centro_custo: form.centro_custo.trim() || "Agricultura",
    data_inicio: form.data_inicio,
    data_fim: form.data_fim,
    hectares: Number(form.hectares) || 0,
    toneladas_produzidas: Number(form.toneladas_produzidas) || 0,
    observacao: form.observacao.trim() || null,
    ativo: form.ativo,
  };
}

export default function CadastroSafra() {
  const [safras, setSafras] = useState<Safra[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState<number | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);
  const admin = ehAdmin();

  const carregar = () => fetchSafras().then(setSafras).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(safras ?? []);

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (s: Safra) => {
    setForm({
      nome: s.nome, centro_custo: s.centro_custo, data_inicio: s.data_inicio, data_fim: s.data_fim,
      hectares: String(s.hectares), toneladas_produzidas: String(s.toneladas_produzidas),
      observacao: s.observacao ?? "", ativo: s.ativo,
    });
    setEditando(s.id);
    setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  // Passa pelo fluxo central e auditado de exclusão (POST /exclusoes/confirmar,
  // tipo "safra" — G11) em vez de um DELETE direto: admin exclui na hora,
  // operador vira uma SolicitacaoExclusao pendente de aprovação, mesmo
  // padrão de app/sanidade/page.tsx.
  const excluir = async (s: Safra) => {
    const msg = admin
      ? `Excluir a safra "${s.nome}"? Isso não pode ser desfeito. Os lançamentos financeiros do centro de custo não são apagados.`
      : `Solicitar a exclusão da safra "${s.nome}"? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setExcluindo(s.id); setMsg(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("safra", String(s.id));
      if (r.status === "excluido") {
        await carregar();
      } else {
        setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) {
      setMsg(e.message || "Erro ao excluir safra");
    } finally {
      setExcluindo(null);
    }
  };

  const salvar = async () => {
    if (!form.nome.trim() || !form.data_inicio || !form.data_fim) { setMsg("Nome e período são obrigatórios."); return; }
    if (!Number(form.hectares) || !Number(form.toneladas_produzidas)) { setMsg("Hectares e toneladas produzidas devem ser maiores que zero."); return; }
    const dados = paraPayload(form);
    setSalvando(true);
    setMsg(null);
    try {
      if (editando === "novo") await criarSafra(dados);
      else if (typeof editando === "number") await atualizarSafra(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar safra");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Sprout size={22} style={{ color: "var(--dourado)" }} /> Cadastro de safra</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Cada safra (ex.: silagem de milho) reúne hectares plantados e toneladas produzidas — usados no relatório
          <strong> Financeiro &gt; Relatórios &gt; Custo por safra</strong> para apurar R$/hectare e R$/tonelada a
          partir dos lançamentos do centro de custo e período informados abaixo.
        </p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {avisoExclusao && <p style={{ color: "var(--dourado-light)", fontSize: "0.85rem", marginBottom: "0.8rem" }}>{avisoExclusao}</p>}
      {!safras && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {safras && (
        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between">
            <span>Safras cadastradas</span>
            <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
              <Plus size={14} /> Nova safra
            </button>
          </div>

          {editando === "novo" && (
            <FormSafra form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
          )}

          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead>
                <tr>
                  <ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                  <ThOrdenavel label="Centro de custo" campo="centro_custo" coluna={coluna} dir={dir} ordenar={ordenar} />
                  <ThOrdenavel label="Período" campo="data_inicio" coluna={coluna} dir={dir} ordenar={ordenar} />
                  <ThOrdenavel label="Hectares" campo="hectares" coluna={coluna} dir={dir} ordenar={ordenar} alinhar="right" />
                  <ThOrdenavel label="Toneladas" campo="toneladas_produzidas" coluna={coluna} dir={dir} ordenar={ordenar} alinhar="right" />
                  <ThOrdenavel label="Ativa" campo="ativo" coluna={coluna} dir={dir} ordenar={ordenar} />
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {linhasOrdenadas.map((s) => (
                  <Fragment key={s.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{s.nome}</td>
                      <td>{s.centro_custo}</td>
                      <td style={{ fontSize: "0.78rem" }}>{s.data_inicio.split("-").reverse().join("/")} – {s.data_fim.split("-").reverse().join("/")}</td>
                      <td style={{ textAlign: "right" }}>{s.hectares.toLocaleString("pt-BR")}</td>
                      <td style={{ textAlign: "right" }}>{s.toneladas_produzidas.toLocaleString("pt-BR")}</td>
                      <td style={{ fontSize: "0.78rem" }}>{s.ativo ? "Sim" : "Não"}</td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(s)}>
                          <Pencil size={13} /> Editar
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.3rem", color: "var(--red)", marginLeft: "0.4rem" }}
                          onClick={() => excluir(s)} disabled={excluindo === s.id} title="Excluir safra">
                          <Trash2 size={13} /> {excluindo === s.id ? "Excluindo…" : "Excluir"}
                        </button>
                      </td>
                    </tr>
                    {editando === s.id && (
                      <tr>
                        <td colSpan={7} style={{ padding: 0 }}>
                          <FormSafra form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {!safras.length && !editando && (
                  <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma safra cadastrada ainda.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function FormSafra({ form, setForm, onSalvar, onCancelar, salvando, msg }: {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
}) {
  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-3">
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Nome</label>
          <input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="ex.: Silagem Milho 2026" /></div>
        <div><label style={labelStyle}>Centro de custo</label>
          <input style={inputStyle} value={form.centro_custo} onChange={(e) => setForm({ ...form, centro_custo: e.target.value })} placeholder="Agricultura" /></div>
        <div><label style={labelStyle}>Período — início</label>
          <input type="date" style={inputStyle} value={form.data_inicio} onChange={(e) => setForm({ ...form, data_inicio: e.target.value })} /></div>
        <div><label style={labelStyle}>Período — fim</label>
          <input type="date" style={inputStyle} value={form.data_fim} onChange={(e) => setForm({ ...form, data_fim: e.target.value })} /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativa</label></div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-3">
        <div><label style={labelStyle}>Hectares</label>
          <input type="number" style={inputStyle} value={form.hectares} onChange={(e) => setForm({ ...form, hectares: e.target.value })} /></div>
        <div><label style={labelStyle}>Toneladas produzidas</label>
          <input type="number" style={inputStyle} value={form.toneladas_produzidas} onChange={(e) => setForm({ ...form, toneladas_produzidas: e.target.value })} /></div>
        <div style={{ gridColumn: "span 3" }}><label style={labelStyle}>Observação</label>
          <input style={inputStyle} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} /></div>
      </div>

      {msg && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{msg}</p>}
      <div className="flex items-center gap-2">
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onSalvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}
