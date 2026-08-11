"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Users, Plus, Pencil, Trash2, AlertTriangle, Check, X, Search } from "lucide-react";
import { fetchPessoas, criarPessoa, atualizarPessoa, excluirPessoa, fetchTiposPessoa, criarTipoPessoa } from "@/lib/api";
import { Modal } from "@/components/Modal";
import { maskTelefone, maskCpfCnpj, maskCep } from "@/lib/masks";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { CampoMoeda } from "@/components/CampoMoeda";
import { normalizarBusca as normalizar } from "@/lib/busca";

type Pessoa = {
  id: number; nome: string; tipos: string[]; telefones: string[]; emails: string[];
  cpf_cnpj: string | null; cep: string | null;
  observacoes: string | null; ativo: boolean; salario_base: number | null; data_admissao: string | null;
  rg: string | null; data_nascimento: string | null; genero: string | null; estado_civil: string | null;
  endereco_rua: string | null; endereco_numero: string | null; endereco_bairro: string | null;
  endereco_cidade: string | null; endereco_uf: string | null;
};
type Form = {
  nome: string; tipos: string[]; telefones: string[]; emails: string[]; cpfCnpj: string; cep: string; observacoes: string; ativo: boolean;
  salarioBase: string; dataAdmissao: string;
  rg: string; dataNascimento: string; genero: string; estadoCivil: string;
  enderecoRua: string; enderecoNumero: string; enderecoBairro: string; enderecoCidade: string; enderecoUf: string;
};
const formVazio: Form = {
  nome: "", tipos: ["Funcionário"], telefones: [], emails: [], cpfCnpj: "", cep: "", observacoes: "", ativo: true, salarioBase: "", dataAdmissao: "",
  rg: "", dataNascimento: "", genero: "", estadoCivil: "",
  enderecoRua: "", enderecoNumero: "", enderecoBairro: "", enderecoCidade: "", enderecoUf: "",
};

// Obrigatórios para cadastrar (decisão jul/2026): nome, CPF e endereço
// completo. RG/data de nascimento/estado civil são coletados aqui mas só
// exigidos na hora de assinar um contrato — gênero nunca é obrigatório.
const ESTADOS_CIVIS = ["Solteiro(a)", "Casado(a)", "Divorciado(a)", "Viúvo(a)", "União estável"];
const UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];

const inputStyle: React.CSSProperties = { width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const buscaInputStyle: React.CSSProperties = { width: "100%", background: "var(--surface)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.75rem 0.5rem 2rem", fontSize: "0.85rem" };

function paraPayload(f: Form) {
  const s = (v: string) => (v.trim() === "" ? undefined : v.trim());
  return {
    nome: f.nome.trim(), tipos: f.tipos,
    telefones: f.telefones.map((t) => t.trim()).filter(Boolean),
    emails: f.emails.map((e) => e.trim()).filter(Boolean),
    cpf_cnpj: s(f.cpfCnpj), cep: s(f.cep), observacoes: s(f.observacoes),
    ativo: f.ativo, salario_base: f.salarioBase.trim() === "" ? undefined : parseFloat(f.salarioBase),
    data_admissao: s(f.dataAdmissao),
    rg: s(f.rg), data_nascimento: s(f.dataNascimento), genero: s(f.genero), estado_civil: s(f.estadoCivil),
    endereco_rua: s(f.enderecoRua), endereco_numero: s(f.enderecoNumero), endereco_bairro: s(f.enderecoBairro),
    endereco_cidade: s(f.enderecoCidade), endereco_uf: s(f.enderecoUf),
  };
}

export default function CadastroPessoas() {
  const [itens, setItens] = useState<Pessoa[] | null>(null);
  const [tipos, setTipos] = useState<{ id: number; nome: string; ativo: boolean }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [erroExclusao, setErroExclusao] = useState<string | null>(null);
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
      nome: p.nome, tipos: p.tipos.length ? p.tipos : ["Funcionário"], telefones: p.telefones ?? [], emails: p.emails ?? [],
      cpfCnpj: p.cpf_cnpj ?? "", cep: p.cep ?? "", observacoes: p.observacoes ?? "",
      ativo: p.ativo, salarioBase: p.salario_base != null ? String(p.salario_base) : "", dataAdmissao: p.data_admissao ?? "",
      rg: p.rg ?? "", dataNascimento: p.data_nascimento ?? "", genero: p.genero ?? "", estadoCivil: p.estado_civil ?? "",
      enderecoRua: p.endereco_rua ?? "", enderecoNumero: p.endereco_numero ?? "", enderecoBairro: p.endereco_bairro ?? "",
      enderecoCidade: p.endereco_cidade ?? "", enderecoUf: p.endereco_uf ?? "",
    });
    setEditando(p.id); setMsg(null);
  };
  const cancelar = () => { setEditando(null); setMsg(null); };

  // Exclusão de fato (não só desativar) — bloqueada pelo backend com 409
  // quando há folha/férias/13º/rescisão/vale/empreitada/contrato/diária ou
  // login de usuário vinculado (ver excluir_pessoa em cadastro/pessoas.py),
  // orientando a desativar em vez de excluir nesse caso.
  const excluir = async (p: Pessoa) => {
    if (!window.confirm(`Excluir "${p.nome}"? Isso não pode ser desfeito.`)) return;
    setErroExclusao(null);
    try {
      await excluirPessoa(p.id);
      await carregar();
    } catch (e: any) {
      setErroExclusao(e.message || "Erro ao excluir");
    }
  };

  const salvar = async () => {
    if (!form.nome.trim()) { setMsg("Nome é obrigatório."); return; }
    if (!form.tipos.length) { setMsg("Selecione ao menos um tipo."); return; }
    // CPF/endereço NÃO bloqueiam o cadastro — Pessoa é o cadastro de RH usado
    // para qualquer funcionário/veterinário/diarista/empreiteiro, não só o
    // contratante do contrato CowData. Os campos ficam disponíveis para quem
    // quiser preencher (ver pessoas.py:_exigir_campos_obrigatorios).
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
    !termoBusca || normalizar(`${p.nome} ${p.tipos.join(" ")} ${(p.telefones ?? []).join(" ")} ${(p.emails ?? []).join(" ")}`).includes(termoBusca)
  );

  // Colunas derivadas (nome do 1º tipo/telefone/email) só para permitir
  // ordenar por clique no cabeçalho — telefones/emails viram lista na tela.
  const linhasOrdenaveis = useMemo(() => filtrados.map((p) => ({
    ...p, tipoOrdenacao: p.tipos.join(", "), telefoneOrdenacao: (p.telefones ?? [])[0] ?? "", emailOrdenacao: (p.emails ?? [])[0] ?? "",
  })), [filtrados]);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(linhasOrdenaveis);

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
      {erroExclusao && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>{erroExclusao}</span></div>}
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
            <thead>
              <tr>
                <ThOrdenavel label="Nome" campo="nome" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Tipo" campo="tipoOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Telefone" campo="telefoneOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <ThOrdenavel label="Email" campo="emailOrdenacao" coluna={coluna} dir={dir} ordenar={ordenar} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {linhasOrdenadas.map((p) => (
                <Fragment key={p.id}>
                  <tr>
                    <td style={{ fontWeight: 700 }}>{p.nome}{!p.ativo && <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: "0.72rem" }}> (inativo)</span>}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.tipos.join(", ")}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.telefones.length ? p.telefones.join(", ") : "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.emails.length ? p.emails.join(", ") : "—"}</td>
                    <td style={{ textAlign: "right" }}>
                      <div className="flex items-center justify-end gap-1">
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => abrirEdicao(p)}>
                          <Pencil size={13} /> Editar
                        </button>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem", color: "var(--red)" }} onClick={() => excluir(p)}>
                          <Trash2 size={13} /> Excluir
                        </button>
                      </div>
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

// Editor de lista de contatos (telefones ou emails) — uma linha por valor,
// com botão de remover e "+ adicionar" — usado dentro do FormItem abaixo.
function ListaContatoInput({ label, valores, onChange, mask, placeholder }: {
  label: string; valores: string[]; onChange: (v: string[]) => void; mask?: (v: string) => string; placeholder?: string;
}) {
  const atualizar = (i: number, v: string) => onChange(valores.map((x, idx) => (idx === i ? (mask ? mask(v) : v) : x)));
  const remover = (i: number) => onChange(valores.filter((_, idx) => idx !== i));
  const adicionar = () => onChange([...valores, ""]);

  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <div className="space-y-1">
        {valores.map((v, i) => (
          <div key={i} className="flex items-center gap-1">
            <input style={inputStyle} value={v} placeholder={placeholder} onChange={(e) => atualizar(i, e.target.value)} />
            <button type="button" className="btn-ghost" title={`Remover ${label.toLowerCase()}`} style={{ padding: "0.3rem" }} onClick={() => remover(i)}>
              <X size={13} />
            </button>
          </div>
        ))}
        <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.2rem", padding: "0.1rem 0.4rem" }} onClick={adicionar}>
          <Plus size={12} /> Adicionar {label.toLowerCase()}
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
    <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", marginBottom: "1rem" }}>
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
        <ListaContatoInput label="Telefones" valores={form.telefones} onChange={(v) => setForm({ ...form, telefones: v })} mask={maskTelefone} />
        <ListaContatoInput label="Emails" valores={form.emails} onChange={(v) => setForm({ ...form, emails: v })} placeholder="nome@exemplo.com" />
        <div><label style={labelStyle}>CPF/CNPJ</label>
          <input style={inputStyle} value={form.cpfCnpj} onChange={(e) => setForm({ ...form, cpfCnpj: maskCpfCnpj(e.target.value) })} /></div>
        <div><label style={labelStyle}>RG</label>
          <input style={inputStyle} value={form.rg} onChange={(e) => setForm({ ...form, rg: e.target.value })} /></div>
        <div><label style={labelStyle}>Data de nascimento</label>
          <input type="date" style={inputStyle} value={form.dataNascimento} onChange={(e) => setForm({ ...form, dataNascimento: e.target.value })} /></div>
        <div><label style={labelStyle}>Gênero</label>
          <select style={inputStyle} value={form.genero} onChange={(e) => setForm({ ...form, genero: e.target.value })}>
            <option value="">Prefere não informar</option>
            <option value="Feminino">Feminino</option>
            <option value="Masculino">Masculino</option>
            <option value="Outro">Outro</option>
          </select></div>
        <div><label style={labelStyle}>Estado civil</label>
          <select style={inputStyle} value={form.estadoCivil} onChange={(e) => setForm({ ...form, estadoCivil: e.target.value })}>
            <option value="">—</option>
            {ESTADOS_CIVIS.map((e) => <option key={e} value={e}>{e}</option>)}
          </select></div>
        <div style={{ gridColumn: "span 2" }}><label style={labelStyle}>Rua</label>
          <input style={inputStyle} value={form.enderecoRua} onChange={(e) => setForm({ ...form, enderecoRua: e.target.value })} /></div>
        <div><label style={labelStyle}>Número</label>
          <input style={inputStyle} value={form.enderecoNumero} onChange={(e) => setForm({ ...form, enderecoNumero: e.target.value })} /></div>
        <div><label style={labelStyle}>Bairro</label>
          <input style={inputStyle} value={form.enderecoBairro} onChange={(e) => setForm({ ...form, enderecoBairro: e.target.value })} /></div>
        <div><label style={labelStyle}>Cidade</label>
          <input style={inputStyle} value={form.enderecoCidade} onChange={(e) => setForm({ ...form, enderecoCidade: e.target.value })} /></div>
        <div><label style={labelStyle}>UF</label>
          <select style={inputStyle} value={form.enderecoUf} onChange={(e) => setForm({ ...form, enderecoUf: e.target.value })}>
            <option value="">—</option>
            {UFS.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
          </select></div>
        <div><label style={labelStyle}>CEP</label>
          <input style={inputStyle} value={form.cep} onChange={(e) => setForm({ ...form, cep: maskCep(e.target.value) })} /></div>
        <div><label style={labelStyle}>Salário base (R$)</label>
          <CampoMoeda style={inputStyle} value={Number(form.salarioBase) || 0} onChange={(v) => setForm({ ...form, salarioBase: v ? String(v) : "" })} /></div>
        <div><label style={labelStyle}>Data de admissão</label>
          <input type="date" style={inputStyle} value={form.dataAdmissao} onChange={(e) => setForm({ ...form, dataAdmissao: e.target.value })}
            title="Usada para calcular a folha proporcional do 1º mês de trabalho" /></div>
        <div className="flex items-end"><label className="flex items-center gap-2" style={{ fontSize: "0.78rem" }}>
          <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label></div>
        <div style={{ gridColumn: "1 / -1" }}><label style={labelStyle}>Observações</label>
          <textarea style={{ ...inputStyle, minHeight: "2.4rem" }} value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} /></div>
      </div>
      <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "-0.4rem", marginBottom: "0.6rem" }}>
        CPF, RG, data de nascimento, estado civil e endereço não bloqueiam o cadastro — ficam disponíveis para preencher agora e valem para o contrato mais tarde.
      </p>
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
