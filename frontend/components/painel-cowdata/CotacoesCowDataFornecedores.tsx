"use client";
// Fornecedores da PRÓPRIA CowData — cada um pode atender uma ou mais
// classificações e uma ou mais finalidades (pedido do usuário), usadas para
// sugerir quem convidar numa cotação por classificação/finalidade.
//
// Fan-out (pedido do dono, set/2026, mesmo padrão da Farmácia): todo
// fornecedor cadastrado aqui passa a existir também no cadastro de
// Fornecedor de cada fazenda-cliente ativa, sempre INATIVO — a fazenda
// decide se/quando ativar. Isso NÃO tem relação com a muralha de preço
// (PrecoBaseSugerido nunca revela fornecedor a nenhuma fazenda) — é só o
// cadastro do fornecedor em si (nome/CNPJ/telefone/e-mail) que passa a
// poder ser conhecido/ativado por qualquer fazenda-cliente.
import { useEffect, useState } from "react";
import { Pencil, Plus, RefreshCw, Trash2, X } from "lucide-react";
import {
  fetchFornecedoresCowData, criarFornecedorCowData, editarFornecedorCowData, reexecutarFanoutFornecedorCowData,
  criarContatoFornecedorCowData, editarContatoFornecedorCowData, excluirContatoFornecedorCowData,
  fetchClassificacoesCowData, fetchFinalidadesCowData,
  type FornecedorCowData, type FornecedorCowDataContato, type ClassificacaoCowData, type FinalidadeCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";
import SeletorMultiploComBusca from "@/components/SeletorMultiploComBusca";

function msgErro(e: unknown): string {
  return e instanceof Error ? e.message : "Erro inesperado";
}

const VAZIO = {
  nome: "", cnpj_cpf: "", telefone: "", email: "", site: "", endereco: "", cidade: "", estado: "", cep: "",
  observacoes: "", ativo: true, classificacao_ids: [] as number[], finalidade_ids: [] as number[],
};
const CONTATO_VAZIO = { nome: "", cargo: "", telefone: "", email: "" };

export default function CotacoesCowDataFornecedores() {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [fornecedores, setFornecedores] = useState<FornecedorCowData[] | null>(null);
  const [classificacoes, setClassificacoes] = useState<ClassificacaoCowData[]>([]);
  const [finalidades, setFinalidades] = useState<FinalidadeCowData[]>([]);
  const [editando, setEditando] = useState<FornecedorCowData | null>(null);
  const [form, setForm] = useState(VAZIO);
  const [aberto, setAberto] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [reexecutando, setReexecutando] = useState<number | null>(null);
  const [avisoFanout, setAvisoFanout] = useState<string | null>(null);

  async function carregar() {
    const [f, c, fin] = await Promise.all([fetchFornecedoresCowData(), fetchClassificacoesCowData(), fetchFinalidadesCowData()]);
    setFornecedores(f); setClassificacoes(c); setFinalidades(fin);
    return f;
  }
  useEffect(() => { carregar(); }, []);

  function abrirNovo() { setEditando(null); setForm(VAZIO); setAberto(true); setErro(null); }
  function abrirEdicao(f: FornecedorCowData) {
    setEditando(f);
    setForm({
      nome: f.nome, cnpj_cpf: f.cnpj_cpf || "", telefone: f.telefone || "", email: f.email || "",
      site: f.site || "", endereco: f.endereco || "", cidade: f.cidade || "", estado: f.estado || "", cep: f.cep || "",
      observacoes: f.observacoes || "", ativo: f.ativo,
      classificacao_ids: f.classificacoes.map((c) => c.id), finalidade_ids: f.finalidades.map((x) => x.id),
    });
    setAberto(true); setErro(null);
  }

  async function salvar() {
    if (!form.nome.trim()) { setErro("Nome é obrigatório"); return; }
    setSalvando(true); setErro(null);
    try {
      if (editando) await editarFornecedorCowData(editando.id, form);
      else await criarFornecedorCowData(form);
      const lista = await carregar();
      if (editando) {
        setEditando(lista.find((f) => f.id === editando.id) || null);
      } else {
        setAberto(false);
      }
    } catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  async function reexecutarFanout(f: FornecedorCowData) {
    setReexecutando(f.id); setAvisoFanout(null);
    try {
      const r = await reexecutarFanoutFornecedorCowData(f.id);
      setAvisoFanout(`"${f.nome}": ${r.criados} fazenda(s) nova(s) alcançada(s), ${r.ja_existiam} já tinham.`);
      await carregar();
    } catch (e) {
      setAvisoFanout(msgErro(e));
    } finally {
      setReexecutando(null);
    }
  }

  if (!fornecedores) return <p style={{ fontSize: "0.85rem" }}>Carregando…</p>;

  return (
    <div>
      <button style={{ ...btnPrimario, marginBottom: "1rem" }} onClick={abrirNovo}><Plus size={14} /> Novo fornecedor</button>
      {avisoFanout && (
        <p style={{ fontSize: "0.78rem", color: COR.mudo, marginBottom: "0.6rem" }}>{avisoFanout}</p>
      )}

      <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", overflow: "hidden" }}>
        <table className="fazenda-table" style={{ width: "100%" }}>
          <thead>
            <tr style={{ color: COR.mudo }}>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Nome</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Classificações</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Cidade/UF</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Contato</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }} title="Quantas fazendas-cliente já têm este fornecedor no próprio cadastro (fan-out), e quantas já ativaram">
                Fazendas
              </th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {fornecedores.map((f) => (
              <tr key={f.id} style={{ borderTop: `1px solid ${COR.borda}`, opacity: f.ativo ? 1 : 0.5 }}>
                <td style={{ padding: "0.6rem", color: COR.texto, fontWeight: 600, fontSize: "0.85rem" }}>{f.nome}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>{f.classificacoes.map((c) => c.nome).join(", ") || "—"}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>{[f.cidade, f.estado].filter(Boolean).join("/") || "—"}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>{f.telefone || f.email || "—"}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>
                  {f.fan_out_fazendas_ativas}/{f.fan_out_total_fazendas} ativa(s)
                </td>
                <td style={{ padding: "0.6rem", display: "flex", gap: "0.3rem" }}>
                  <button style={btnGhost} onClick={() => abrirEdicao(f)} title="Editar"><Pencil size={13} /></button>
                  <button style={btnGhost} onClick={() => reexecutarFanout(f)} disabled={reexecutando === f.id} title="Reexecutar fan-out (alcança fazenda nova/não alcançada)">
                    <RefreshCw size={13} />
                  </button>
                </td>
              </tr>
            ))}
            {fornecedores.length === 0 && (
              <tr><td colSpan={6} style={{ padding: "1.5rem", textAlign: "center", color: COR.mudo, fontSize: "0.82rem" }}>Nenhum fornecedor ainda.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {aberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
          onClick={() => setAberto(false)}>
          <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1.4rem", width: "min(560px, 92vw)", maxHeight: "88vh", overflowY: "auto" }}
            onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 style={{ color: COR.texto, fontWeight: 700 }}>{editando ? "Editar fornecedor" : "Novo fornecedor"}</h3>
              <button style={btnGhost} onClick={() => setAberto(false)}><X size={14} /></button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
              <div>
                <label style={labelStyle}>Nome</label>
                <input style={{ ...inputStyle, width: "100%" }} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} />
              </div>
              <div className="flex gap-2">
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>CNPJ/CPF</label>
                  <input style={{ ...inputStyle, width: "100%" }} value={form.cnpj_cpf} onChange={(e) => setForm({ ...form, cnpj_cpf: e.target.value })} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Telefone</label>
                  <input style={{ ...inputStyle, width: "100%" }} value={form.telefone} onChange={(e) => setForm({ ...form, telefone: e.target.value })} />
                </div>
              </div>
              <div className="flex gap-2">
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>E-mail</label>
                  <input style={{ ...inputStyle, width: "100%" }} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Site</label>
                  <input style={{ ...inputStyle, width: "100%" }} value={form.site} onChange={(e) => setForm({ ...form, site: e.target.value })} placeholder="www.exemplo.com.br" />
                </div>
              </div>
              <div>
                <label style={labelStyle}>Endereço</label>
                <input style={{ ...inputStyle, width: "100%" }} value={form.endereco} onChange={(e) => setForm({ ...form, endereco: e.target.value })} />
              </div>
              <div className="flex gap-2">
                <div style={{ flex: 2 }}>
                  <label style={labelStyle}>Cidade</label>
                  <input style={{ ...inputStyle, width: "100%" }} value={form.cidade} onChange={(e) => setForm({ ...form, cidade: e.target.value })} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>Estado (UF)</label>
                  <input style={{ ...inputStyle, width: "100%" }} value={form.estado} maxLength={2} onChange={(e) => setForm({ ...form, estado: e.target.value.toUpperCase() })} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={labelStyle}>CEP</label>
                  <input style={{ ...inputStyle, width: "100%" }} value={form.cep} onChange={(e) => setForm({ ...form, cep: e.target.value })} />
                </div>
              </div>
              <SeletorMultiploComBusca label="Classificações (uma ou mais)" opcoes={classificacoes.map((c) => ({ id: c.id, nome: c.nome }))}
                selecionados={form.classificacao_ids} onChange={(ids) => setForm({ ...form, classificacao_ids: ids })}
                cor={{ bg: COR.bg, borda: COR.borda, texto: COR.texto, mudo: COR.mudo, dourado: COR.dourado, painelAlt: COR.painelAlt }} />
              <SeletorMultiploComBusca label="Finalidades (uma ou mais)" opcoes={finalidades.map((f) => ({ id: f.id, nome: f.nome }))}
                selecionados={form.finalidade_ids} onChange={(ids) => setForm({ ...form, finalidade_ids: ids })}
                cor={{ bg: COR.bg, borda: COR.borda, texto: COR.texto, mudo: COR.mudo, dourado: COR.dourado, painelAlt: COR.painelAlt }} />
              <div>
                <label style={labelStyle}>Observações</label>
                <textarea style={{ ...inputStyle, width: "100%", minHeight: "60px" }} value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} />
              </div>
              <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", color: COR.texto, cursor: "pointer" }}>
                <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} />
                Ativo
              </label>
              {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem" }}>{erro}</p>}
              <button style={btnPrimario} disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>

              {editando ? (
                <ContatosFornecedor fornecedor={editando} cor={COR} inputStyle={inputStyle} labelStyle={labelStyle} btnGhost={btnGhost} btnPrimario={btnPrimario}
                  onMudou={async () => { const lista = await carregar(); setEditando(lista.find((f) => f.id === editando.id) || null); }} />
              ) : (
                <p style={{ fontSize: "0.75rem", color: COR.mudo }}>Salve o fornecedor primeiro para poder acrescentar vendedores/representantes.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ContatosFornecedor({ fornecedor, cor: COR, inputStyle, labelStyle, btnGhost, btnPrimario, onMudou }: {
  fornecedor: FornecedorCowData;
  cor: any; inputStyle: React.CSSProperties; labelStyle: React.CSSProperties; btnGhost: React.CSSProperties; btnPrimario: React.CSSProperties;
  onMudou: () => Promise<void>;
}) {
  const [novoContato, setNovoContato] = useState(CONTATO_VAZIO);
  const [editandoContatoId, setEditandoContatoId] = useState<number | null>(null);
  const [formContato, setFormContato] = useState(CONTATO_VAZIO);
  const [salvandoContato, setSalvandoContato] = useState(false);
  const [erroContato, setErroContato] = useState<string | null>(null);

  async function adicionar() {
    if (!novoContato.nome.trim()) { setErroContato("Nome é obrigatório"); return; }
    setSalvandoContato(true); setErroContato(null);
    try {
      await criarContatoFornecedorCowData(fornecedor.id, novoContato);
      setNovoContato(CONTATO_VAZIO);
      await onMudou();
    } catch (e) { setErroContato(msgErro(e)); } finally { setSalvandoContato(false); }
  }

  function abrirEdicaoContato(c: FornecedorCowDataContato) {
    setEditandoContatoId(c.id);
    setFormContato({ nome: c.nome, cargo: c.cargo || "", telefone: c.telefone || "", email: c.email || "" });
  }

  async function salvarEdicaoContato() {
    if (editandoContatoId == null) return;
    if (!formContato.nome.trim()) { setErroContato("Nome é obrigatório"); return; }
    setSalvandoContato(true); setErroContato(null);
    try {
      await editarContatoFornecedorCowData(fornecedor.id, editandoContatoId, formContato);
      setEditandoContatoId(null);
      await onMudou();
    } catch (e) { setErroContato(msgErro(e)); } finally { setSalvandoContato(false); }
  }

  async function excluir(contatoId: number) {
    if (!window.confirm("Excluir este contato?")) return;
    try {
      await excluirContatoFornecedorCowData(fornecedor.id, contatoId);
      await onMudou();
    } catch (e) { setErroContato(msgErro(e)); }
  }

  return (
    <div style={{ borderTop: `1px solid ${COR.borda}`, paddingTop: "0.8rem", marginTop: "0.4rem" }}>
      <p style={{ fontSize: "0.8rem", fontWeight: 700, color: COR.texto, marginBottom: "0.5rem" }}>Vendedores / representantes</p>
      {fornecedor.contatos.length === 0 && <p style={{ fontSize: "0.78rem", color: COR.mudo, marginBottom: "0.5rem" }}>Nenhum contato ainda.</p>}
      {fornecedor.contatos.map((c) => (
        <div key={c.id} style={{ background: COR.painelAlt, borderRadius: "var(--r-sm)", padding: "0.5rem", marginBottom: "0.4rem" }}>
          {editandoContatoId === c.id ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              <div className="flex gap-2">
                <input style={{ ...inputStyle, flex: 1 }} placeholder="Nome" value={formContato.nome} onChange={(e) => setFormContato({ ...formContato, nome: e.target.value })} />
                <input style={{ ...inputStyle, flex: 1 }} placeholder="Cargo (ex.: Vendedor)" value={formContato.cargo} onChange={(e) => setFormContato({ ...formContato, cargo: e.target.value })} />
              </div>
              <div className="flex gap-2">
                <input style={{ ...inputStyle, flex: 1 }} placeholder="Telefone" value={formContato.telefone} onChange={(e) => setFormContato({ ...formContato, telefone: e.target.value })} />
                <input style={{ ...inputStyle, flex: 1 }} placeholder="E-mail" value={formContato.email} onChange={(e) => setFormContato({ ...formContato, email: e.target.value })} />
              </div>
              <div className="flex gap-2">
                <button style={btnPrimario} disabled={salvandoContato} onClick={salvarEdicaoContato}>Salvar contato</button>
                <button style={btnGhost} onClick={() => setEditandoContatoId(null)}>Cancelar</button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <div style={{ fontSize: "0.8rem", color: COR.texto }}>
                <strong>{c.nome}</strong>{c.cargo && <span style={{ color: COR.mudo }}> — {c.cargo}</span>}
                <br />
                <span style={{ fontSize: "0.75rem", color: COR.mudo }}>{[c.telefone, c.email].filter(Boolean).join(" · ") || "—"}</span>
              </div>
              <div className="flex gap-1">
                <button style={btnGhost} onClick={() => abrirEdicaoContato(c)} title="Editar"><Pencil size={12} /></button>
                <button style={btnGhost} onClick={() => excluir(c.id)} title="Excluir"><Trash2 size={12} /></button>
              </div>
            </div>
          )}
        </div>
      ))}
      <div className="flex gap-2" style={{ marginTop: "0.4rem" }}>
        <input style={{ ...inputStyle, flex: 1 }} placeholder="Nome do novo contato" value={novoContato.nome} onChange={(e) => setNovoContato({ ...novoContato, nome: e.target.value })} />
        <input style={{ ...inputStyle, flex: 1 }} placeholder="Cargo" value={novoContato.cargo} onChange={(e) => setNovoContato({ ...novoContato, cargo: e.target.value })} />
        <input style={{ ...inputStyle, flex: 1 }} placeholder="Telefone" value={novoContato.telefone} onChange={(e) => setNovoContato({ ...novoContato, telefone: e.target.value })} />
        <input style={{ ...inputStyle, flex: 1 }} placeholder="E-mail" value={novoContato.email} onChange={(e) => setNovoContato({ ...novoContato, email: e.target.value })} />
        <button style={btnGhost} disabled={salvandoContato} onClick={adicionar} title="Adicionar contato"><Plus size={14} /></button>
      </div>
      {erroContato && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.3rem" }}>{erroContato}</p>}
    </div>
  );
}
