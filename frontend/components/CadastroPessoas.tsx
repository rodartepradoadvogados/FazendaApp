"use client";
import { Fragment, useEffect, useState } from "react";
import { Users, Plus, Pencil, AlertTriangle, Check, X, Search } from "lucide-react";
import { fetchPessoas, criarPessoa, atualizarPessoa, fetchTiposPessoa, criarTipoPessoa } from "@/lib/api";
import { Modal } from "@/components/Modal";
import { maskTelefone, maskCpfCnpj, maskCep } from "@/lib/masks";

type Pessoa = {
  id: number; nome: string; tipos: string[]; telefone: string | null; email: string | null;
  cpf_cnpj: string | null; cep: string | null;
  observacoes: string | null; ativo: boolean; salario_base: number | null; data_admissao: string | null;
};
type Form = {
  nome: string; tipos: string[]; telefone: string; email: string; cpfCnpj: string; cep: string; observacoes: string; ativo: boolean;
  salarioBase: string; dataAdmissao: string;
};
const formVazio: Form = {
  nome: "", tipos: ["Funcionário"], telefone: "", email: "", cpfCnpj: "", cep: "", observacoes: "", ativo: true, salarioBase: "", dataAdmissao: "",
};

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

// Normaliza texto para busca insensível a maiúsculas e acentos.
const normalizar = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

function paraPayload(f: Form) {
  const s = (v: string) => (v.trim() === "" ? undefined : v.trim());
  return {
    nome: f.nome.trim(), tipos: f.tipos, telefone: s(f.telefone), email: s(f.email), cpf_cnpj: s(f.cpfCnpj), cep: s(f.cep), observacoes: s(f.observacoes),
    ativo: f.ativo, salario_base: f.salarioBase.trim() === "" ? undefined : parseFloat(f.salarioBase),
    data_admissao: s(f.dataAdmissao),
  };
}

export default function CadastroPessoas() {
  const [itens, setItens] = useState<Pessoa[] | null>(null);
  const [tipos, setTipos] = useState<{ id: number; nome: string; ativo: boolean }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<number | "novo" | null>(null);
  const [form, setForm] = useState<Form>(formVazio);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [novoTipoAberto, setNovoTipoAberto] = useState(false);

  const carregar = () => fetchPessoas().then(setItens).catch((e) => setError(e.message));
  const carregarTipos = () => fetchTiposPessoa().then(setTipos).catch(() => {});
  useEffect(() => { carregar(); carregarTipos(); }, []);

  const abrirNovo = () => { setForm(formVazio); setEditando("novo"); setMsg(null); };
  const abrirEdicao = (p: Pessoa) => {
    setForm({
      nome: p.nome, tipos: p.tipos.length ? p.tipos : ["Funcionário"], telefone: p.telefone ?? "", email: p.email ?? "",
      cpfCnpj: p.cpf_cnpj ?? "", cep: p.cep ?? "", observacoes: p.observacoes ?? "",
      ativo: p.ativo, salarioBase: p.salario_base != null ? String(p.salario_base) : "", dataAdmissao: p.data_admissao ?? "",
    });
    setEditando(p.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (!form.tipos.length) { setMsg("Selecione ao menos um tipo."); return; }
    setSalvando(true); setMsg(null);
    try {
      const dados = paraPayload(form);
      if (editando === "novo") await criarPessoa(dados);
      else if (typeof editando === "number") await atualizarPessoa(editando, dados);
      setEditando(null);
      await carregar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  };

  const termoBusca = normalizar(busca.trim());
  const filtrados = (itens ?? []).filter((p) =>
    !termoBusca || normalizar(`${p.nome} ${p.tipos.join(" ")} ${p.telefone ?? ""} ${p.email ?? ""}`).includes(termoBusca)
  );

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Users size={16} /> Pessoas</span>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={abrirNovo}>
          <Plus size={14} /> Novo
        </button>
      </div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Funcionários, veterinários, zootecnistas, diaristas e prestadores de serviço ligados à fazenda — diferente de
        Fornecedores, pois entram na folha de pagamento, não em nota de compra. O salário base é usado para calcular
        o limite de 40% de desconto de vale.
      </p>

      {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {editando === "novo" && (
        <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
          tipos={tipos} onNovoTipo={() => setNovoTipoAberto(true)} />
      )}

      {itens && (
        <>
          <div style={{ position: "relative", marginBottom: "0.8rem" }}>
            <Search size={14} style={{ position: "absolute", left: "0.65rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input style={buscaInputStyle} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar pessoa…" title="Buscar por nome, tipo, telefone ou email" />
          </div>
          <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Nome</th><th>Tipo</th><th>Telefone</th><th>Email</th><th></th></tr></thead>
            <tbody>
              {filtrados.map((p) => (
                <Fragment key={p.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.tipos.join(", ")}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.telefone || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.email || "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(p)}>
                        <Pencil size={13} /> Editar
                      </button>
                    </td>
                  </tr>
                  {editando === p.id && (
                    <tr><td colSpan={5} style={{ padding: 0 }}>
                      <FormItem form={form} setForm={setForm} onSalvar={salvar} onCancelar={cancelar} salvando={salvando} msg={msg}
                        tipos={tipos} onNovoTipo={() => setNovoTipoAberto(true)} />
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {!itens.length && !editando && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma pessoa cadastrada ainda.</td></tr>}
              {!!itens.length && !filtrados.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum resultado para “{busca}”.</td></tr>}
            </tbody>
          </table>
          </div>
        </>
      )}

      {novoTipoAberto && (
        <Modal title="Adicionar tipo de pessoa" onClose={() => setNovoTipoAberto(false)} width="380px">
          <NovoTipoPessoa
            onCriado={(tipo) => {
              setForm((f) => ({ ...f, tipos: [...f.tipos, tipo.nome] }));
              carregarTipos();
              setNovoTipoAberto(false);
            }}
            onCancelar={() => setNovoTipoAberto(false)}
          />
        </Modal>
      )}
    </div>
  );
}

function NovoTipoPessoa({ onCriado, onCancelar }: { onCriado: (tipo: { id: number; nome: string }) => void; onCancelar: () => void }) {
  const [nome, setNome] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const salvar = async () => {
    if (!nome.trim()) { setErro("Nome é obrigatório."); return; }
    setSalvando(true); setErro(null);
    try {
      const tipo = await criarTipoPessoa(nome.trim());
      onCriado(tipo);
    } catch (e: any) {
      setErro(e.message || "Erro ao criar tipo");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div>
      <label style={labelStyle}>Nome do novo tipo</label>
      <input style={inputStyle} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Empreiteiro, Consultor…" autoFocus />
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2" style={{ marginTop: "1rem" }}>
        <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : "Salvar"}
        </button>
        <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={onCancelar}>
          <X size={14} /> Cancelar
        </button>
      </div>
    </div>
  );
}

function FormItem({ form, setForm, onSalvar, onCancelar, salvando, msg, tipos, onNovoTipo }: {
  form: Form; setForm: (f: Form) => void; onSalvar: () => void; onCancelar: () => void; salvando: boolean; msg: string | null;
  tipos: { id: number; nome: string; ativo: boolean }[]; onNovoTipo: () => void;
}) {
  const toggleTipo = (t: string) =>
    setForm({ ...form, tipos: form.tipos.includes(t) ? form.tipos.filter((x) => x !== t) : [...form.tipos, t] });
  const tiposAtivos = tipos.filter((t) => t.ativo);

  return (
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "1rem", marginBottom: "1rem" }}>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-3">
        <div><label style={labelStyle}>Nome</label><input style={inputStyle} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} /></div>
        <div style={{ gridColumn: "span 2" }}>
          <label style={labelStyle}>Tipo(s) — pode marcar mais de um</label>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1" style={{ marginTop: "0.2rem" }}>
            {tiposAtivos.map((t) => (
              <label key={t.id} className="flex items-center gap-1" style={{ fontSize: "0.78rem" }}>
                <input type="checkbox" checked={form.tipos.includes(t.nome)} onChange={() => toggleTipo(t.nome)} /> {t.nome}
              </label>
            ))}
            <button type="button" className="btn-ghost" title="Adicionar novo tipo de pessoa"
              style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.2rem", padding: "0.1rem 0.4rem" }}
              onClick={onNovoTipo}>
              <Plus size={12} /> Novo tipo
            </button>
          </div>
        </div>
        <div><label style={labelStyle}>Telefone</label>
          <input style={inputStyle} value={form.telefone} onChange={(e) => setForm({ ...form, telefone: maskTelefone(e.target.value) })} /></div>
        <div><label style={labelStyle}>Email</label><input style={inputStyle} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
        <div><label style={labelStyle}>CPF/CNPJ</label>
          <input style={inputStyle} value={form.cpfCnpj} onChange={(e) => setForm({ ...form, cpfCnpj: maskCpfCnpj(e.target.value) })} /></div>
        <div><label style={labelStyle}>CEP</label>
          <input style={inputStyle} value={form.cep} onChange={(e) => setForm({ ...form, cep: maskCep(e.target.value) })} /></div>
        <div><label style={labelStyle}>Salário base (R$)</label>
          <input type="number" inputMode="decimal" style={inputStyle} value={form.salarioBase} onChange={(e) => setForm({ ...form, salarioBase: e.target.value })} /></div>
        <div><label style={labelStyle}>Data de admissão</label>
          <input type="date" style={inputStyle} value={form.dataAdmissao} onChange={(e) => setForm({ ...form, dataAdmissao: e.target.value })}
            title="Usada para calcular a folha proporcional do 1º mês de trabalho" /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
        <div style={{ gridColumn: "1 / -1" }}><label style={labelStyle}>Observações</label>
          <textarea style={{ ...inputStyle, minHeight: "2.4rem" }} value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} /></div>
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
