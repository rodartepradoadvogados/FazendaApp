"use client";
// Fornecedores da PRÓPRIA CowData — cada um pode atender uma ou mais
// classificações e uma ou mais finalidades (pedido do usuário), usadas para
// sugerir quem convidar numa cotação por classificação/finalidade.
import { useEffect, useState } from "react";
import { Pencil, Plus, X } from "lucide-react";
import {
  fetchFornecedoresCowData, criarFornecedorCowData, editarFornecedorCowData,
  fetchClassificacoesCowData, fetchFinalidadesCowData,
  type FornecedorCowData, type ClassificacaoCowData, type FinalidadeCowData,
} from "@/lib/api";
import { usePainelCowDataEstilos } from "@/lib/painelCowDataTema";
import SeletorMultiploComBusca from "@/components/SeletorMultiploComBusca";

function msgErro(e: unknown): string {
  return e instanceof Error ? e.message : "Erro inesperado";
}

const VAZIO = { nome: "", cnpj_cpf: "", telefone: "", email: "", observacoes: "", classificacao_ids: [] as number[], finalidade_ids: [] as number[] };

export default function CotacoesCowDataFornecedores() {
  const { cor: COR, inputStyle, labelStyle, btnPrimario, btnGhost } = usePainelCowDataEstilos();
  const [fornecedores, setFornecedores] = useState<FornecedorCowData[] | null>(null);
  const [classificacoes, setClassificacoes] = useState<ClassificacaoCowData[]>([]);
  const [finalidades, setFinalidades] = useState<FinalidadeCowData[]>([]);
  const [editando, setEditando] = useState<number | null>(null);
  const [form, setForm] = useState(VAZIO);
  const [aberto, setAberto] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function carregar() {
    const [f, c, fin] = await Promise.all([fetchFornecedoresCowData(), fetchClassificacoesCowData(), fetchFinalidadesCowData()]);
    setFornecedores(f); setClassificacoes(c); setFinalidades(fin);
  }
  useEffect(() => { carregar(); }, []);

  function abrirNovo() { setEditando(null); setForm(VAZIO); setAberto(true); setErro(null); }
  function abrirEdicao(f: FornecedorCowData) {
    setEditando(f.id);
    setForm({
      nome: f.nome, cnpj_cpf: f.cnpj_cpf || "", telefone: f.telefone || "", email: f.email || "", observacoes: f.observacoes || "",
      classificacao_ids: f.classificacoes.map((c) => c.id), finalidade_ids: f.finalidades.map((x) => x.id),
    });
    setAberto(true); setErro(null);
  }

  async function salvar() {
    if (!form.nome.trim()) { setErro("Nome é obrigatório"); return; }
    setSalvando(true); setErro(null);
    try {
      if (editando) await editarFornecedorCowData(editando, form);
      else await criarFornecedorCowData(form);
      setAberto(false);
      await carregar();
    } catch (e) { setErro(msgErro(e)); } finally { setSalvando(false); }
  }

  if (!fornecedores) return <p style={{ fontSize: "0.85rem" }}>Carregando…</p>;

  return (
    <div>
      <button style={{ ...btnPrimario, marginBottom: "1rem" }} onClick={abrirNovo}><Plus size={14} /> Novo fornecedor</button>

      <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", overflow: "hidden" }}>
        <table className="fazenda-table" style={{ width: "100%" }}>
          <thead>
            <tr style={{ color: COR.mudo }}>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Nome</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Classificações</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Finalidades</th>
              <th style={{ textAlign: "left", padding: "0.6rem" }}>Contato</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {fornecedores.map((f) => (
              <tr key={f.id} style={{ borderTop: `1px solid ${COR.borda}`, opacity: f.ativo ? 1 : 0.5 }}>
                <td style={{ padding: "0.6rem", color: COR.texto, fontWeight: 600, fontSize: "0.85rem" }}>{f.nome}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>{f.classificacoes.map((c) => c.nome).join(", ") || "—"}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>{f.finalidades.map((x) => x.nome).join(", ") || "—"}</td>
                <td style={{ padding: "0.6rem", fontSize: "0.78rem", color: COR.mudo }}>{f.telefone || f.email || "—"}</td>
                <td style={{ padding: "0.6rem" }}>
                  <button style={btnGhost} onClick={() => abrirEdicao(f)}><Pencil size={13} /></button>
                </td>
              </tr>
            ))}
            {fornecedores.length === 0 && (
              <tr><td colSpan={5} style={{ padding: "1.5rem", textAlign: "center", color: COR.mudo, fontSize: "0.82rem" }}>Nenhum fornecedor ainda.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {aberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}
          onClick={() => setAberto(false)}>
          <div style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r)", padding: "1.4rem", width: "min(520px, 92vw)", maxHeight: "88vh", overflowY: "auto" }}
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
              <div>
                <label style={labelStyle}>E-mail</label>
                <input style={{ ...inputStyle, width: "100%" }} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
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
              {erro && <p style={{ color: "var(--red)", fontSize: "0.78rem" }}>{erro}</p>}
              <button style={btnPrimario} disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
