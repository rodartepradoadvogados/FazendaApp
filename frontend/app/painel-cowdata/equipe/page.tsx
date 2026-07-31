"use client";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2, UserPlus } from "lucide-react";
import {
  fetchCargosCowData, fetchEquipeCowData, criarMembroEquipeCowData, editarMembroEquipeCowData, excluirMembroEquipeCowData,
  fetchFolhaMembroCowData, lancarFolhaMembroCowData, excluirFolhaCowData,
  type PessoaCowData, type FolhaCowData,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", dourado: "#e8c256", verde: "#3ecf8e", vermelho: "#e05c5c", texto: "#e8ecf5" };
const inputStyle: React.CSSProperties = {
  background: "#0a0e1a", border: `1px solid ${COR.borda}`, borderRadius: "6px", padding: "0.45rem 0.6rem",
  color: COR.texto, fontSize: "0.82rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: COR.mudo, marginBottom: "0.25rem", display: "block" };

function mesAtual(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function EquipeCowData() {
  const [cargos, setCargos] = useState<string[]>([]);
  const [equipe, setEquipe] = useState<PessoaCowData[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mostrarForm, setMostrarForm] = useState(false);
  const [expandidoId, setExpandidoId] = useState<number | null>(null);

  const [novo, setNovo] = useState({ nome: "", cargo: "", telefone: "", email: "", cpf_cnpj: "", salario_base: "" });

  function carregar() {
    fetchEquipeCowData().then(setEquipe).catch((e) => setErro(e.message));
  }
  useEffect(() => {
    fetchCargosCowData().then((c) => { setCargos(c); setNovo((n) => ({ ...n, cargo: n.cargo || c[0] || "" })); }).catch((e) => setErro(e.message));
    carregar();
  }, []);

  async function salvarNovo() {
    if (!novo.nome.trim() || !novo.cargo) { setErro("Nome e cargo são obrigatórios."); return; }
    setErro(null);
    try {
      await criarMembroEquipeCowData({
        nome: novo.nome.trim(), cargo: novo.cargo,
        telefones: novo.telefone ? [novo.telefone] : [], emails: novo.email ? [novo.email] : [],
        cpf_cnpj: novo.cpf_cnpj || null, salario_base: novo.salario_base ? Number(novo.salario_base) : null,
      });
      setNovo({ nome: "", cargo: cargos[0] || "", telefone: "", email: "", cpf_cnpj: "", salario_base: "" });
      setMostrarForm(false);
      carregar();
    } catch (e: any) { setErro(e.message); }
  }

  async function alternarAtivo(p: PessoaCowData) {
    try {
      await editarMembroEquipeCowData(p.id, {
        nome: p.nome, cargo: p.cargo, telefones: p.telefones, emails: p.emails,
        cpf_cnpj: p.cpf_cnpj, cep: p.cep, salario_base: p.salario_base, data_admissao: p.data_admissao,
        observacoes: p.observacoes, ativo: !p.ativo,
      });
      carregar();
    } catch (e: any) { setErro(e.message); }
  }

  async function excluir(id: number) {
    if (!confirm("Excluir este membro da equipe? Isso não pode ser desfeito.")) return;
    try { await excluirMembroEquipeCowData(id); carregar(); } catch (e: any) { setErro(e.message); }
  }

  const ord = useOrdenacao(equipe ?? []);

  return (
    <div className="animate-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.2rem" }}>
        <h1 style={{ fontSize: "1.4rem", fontWeight: 700 }}>Equipe CowData</h1>
        <button onClick={() => setMostrarForm((v) => !v)}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.78rem", padding: "0.4rem 0.8rem", borderRadius: "6px", border: `1px solid ${COR.dourado}`, background: "transparent", color: COR.dourado, cursor: "pointer" }}>
          <UserPlus size={14} /> Novo membro
        </button>
      </div>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1rem", maxWidth: "42rem" }}>
        Time da própria CowData (sócios, comercial, T.I., financeiro, marketing, suporte) — totalmente separado do
        cadastro de Pessoas/funcionários de qualquer fazenda-cliente.
      </p>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

      {mostrarForm && (
        <div style={{ background: COR.cartao, border: `1px solid ${COR.dourado}`, borderRadius: "12px", padding: "1rem 1.2rem", marginBottom: "1.2rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "0.7rem" }}>
            <div>
              <label style={labelStyle}>Nome</label>
              <input style={inputStyle} value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Cargo</label>
              <select style={inputStyle} value={novo.cargo} onChange={(e) => setNovo({ ...novo, cargo: e.target.value })}>
                {cargos.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Telefone</label>
              <input style={inputStyle} value={novo.telefone} onChange={(e) => setNovo({ ...novo, telefone: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>E-mail</label>
              <input style={inputStyle} value={novo.email} onChange={(e) => setNovo({ ...novo, email: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>CPF</label>
              <input style={inputStyle} value={novo.cpf_cnpj} onChange={(e) => setNovo({ ...novo, cpf_cnpj: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Salário base (R$)</label>
              <input style={inputStyle} type="number" value={novo.salario_base} onChange={(e) => setNovo({ ...novo, salario_base: e.target.value })} />
            </div>
          </div>
          <div style={{ marginTop: "0.8rem", display: "flex", gap: "0.5rem" }}>
            <button onClick={salvarNovo}
              style={{ fontSize: "0.78rem", padding: "0.4rem 0.9rem", borderRadius: "6px", border: "none", background: COR.dourado, color: "#0a0e1a", fontWeight: 700, cursor: "pointer" }}>
              Cadastrar
            </button>
            <button onClick={() => setMostrarForm(false)}
              style={{ fontSize: "0.78rem", padding: "0.4rem 0.9rem", borderRadius: "6px", border: `1px solid ${COR.borda}`, background: "transparent", color: COR.mudo, cursor: "pointer" }}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", overflowX: "auto", overflowY: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem", minWidth: "40rem" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COR.borda}`, color: COR.mudo, textAlign: "left" }}>
              <th style={{ padding: "0.6rem 1rem", width: "1.5rem" }}></th>
              <ThOrdenavel label="Nome" campo="nome" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Cargo" campo="cargo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Salário base" campo="salario_base" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Status" campo="ativo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <th style={{ padding: "0.6rem 1rem" }}></th>
            </tr>
          </thead>
          <tbody>
            {equipe === null && <tr><td colSpan={6} style={{ padding: "1rem", color: COR.mudo }}>Carregando…</td></tr>}
            {equipe?.length === 0 && <tr><td colSpan={6} style={{ padding: "1rem", color: COR.mudo }}>Nenhum membro cadastrado ainda.</td></tr>}
            {equipe && ord.linhasOrdenadas.map((p) => (
              <FichaLinha key={p.id} pessoa={p} expandido={expandidoId === p.id}
                onToggle={() => setExpandidoId(expandidoId === p.id ? null : p.id)}
                onAlternarAtivo={() => alternarAtivo(p)} onExcluir={() => excluir(p.id)} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FichaLinha({ pessoa, expandido, onToggle, onAlternarAtivo, onExcluir }: {
  pessoa: PessoaCowData; expandido: boolean; onToggle: () => void; onAlternarAtivo: () => void; onExcluir: () => void;
}) {
  const [folhas, setFolhas] = useState<FolhaCowData[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [novaFolha, setNovaFolha] = useState({ competencia: mesAtual(), valor_bruto: String(pessoa.salario_base || ""), descontos: "0", status: "pendente" as "pendente" | "pago" });

  useEffect(() => { if (expandido && folhas === null) fetchFolhaMembroCowData(pessoa.id).then(setFolhas).catch((e) => setErro(e.message)); }, [expandido]);

  async function lancar() {
    const bruto = Number(novaFolha.valor_bruto || 0);
    const descontos = Number(novaFolha.descontos || 0);
    try {
      await lancarFolhaMembroCowData(pessoa.id, {
        competencia: novaFolha.competencia, valor_bruto: bruto, descontos, valor_liquido: bruto - descontos,
        status: novaFolha.status, data_pagamento: novaFolha.status === "pago" ? new Date().toISOString().slice(0, 10) : null,
      });
      setFolhas(await fetchFolhaMembroCowData(pessoa.id));
    } catch (e: any) { setErro(e.message); }
  }

  async function excluirFolha(id: number) {
    try { await excluirFolhaCowData(id); setFolhas(await fetchFolhaMembroCowData(pessoa.id)); } catch (e: any) { setErro(e.message); }
  }

  const ordFolhas = useOrdenacao(folhas ?? []);

  return (
    <>
      <tr style={{ borderBottom: `1px solid ${COR.borda}`, cursor: "pointer" }} onClick={onToggle}>
        <td style={{ padding: "0.6rem 1rem", color: COR.mudo }}>{expandido ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</td>
        <td style={{ padding: "0.6rem 1rem" }}>{pessoa.nome}</td>
        <td style={{ padding: "0.6rem 1rem" }}>{pessoa.cargo}</td>
        <td style={{ padding: "0.6rem 1rem", fontVariantNumeric: "tabular-nums" }}>{pessoa.salario_base != null ? `R$ ${pessoa.salario_base.toFixed(2)}` : "—"}</td>
        <td style={{ padding: "0.6rem 1rem" }}>
          <span onClick={(e) => { e.stopPropagation(); onAlternarAtivo(); }}
            style={{ color: pessoa.ativo ? COR.verde : COR.mudo, fontWeight: 700, fontSize: "0.72rem", cursor: "pointer" }}>
            {pessoa.ativo ? "Ativo" : "Inativo"}
          </span>
        </td>
        <td style={{ padding: "0.6rem 1rem", textAlign: "right" }}>
          <button onClick={(e) => { e.stopPropagation(); onExcluir(); }}
            style={{ background: "transparent", border: "none", color: COR.vermelho, cursor: "pointer", padding: "0.2rem" }}>
            <Trash2 size={14} />
          </button>
        </td>
      </tr>
      {expandido && (
        <tr>
          <td colSpan={6} style={{ padding: "0.9rem 1.2rem", background: "#0a0e1a", borderBottom: `1px solid ${COR.borda}` }}>
            {erro && <p style={{ color: COR.vermelho, fontSize: "0.78rem", marginBottom: "0.6rem" }}>{erro}</p>}
            <div style={{ fontSize: "0.75rem", color: COR.mudo, marginBottom: "0.6rem" }}>
              {pessoa.telefones.join(", ") || "sem telefone"} · {pessoa.emails.join(", ") || "sem e-mail"} · {pessoa.cpf_cnpj || "sem CPF"}
            </div>

            <div style={{ display: "flex", gap: "0.6rem", alignItems: "flex-end", flexWrap: "wrap", marginBottom: "0.8rem" }}>
              <div>
                <label style={labelStyle}>Competência</label>
                <input style={{ ...inputStyle, width: "8rem" }} value={novaFolha.competencia} onChange={(e) => setNovaFolha({ ...novaFolha, competencia: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Valor bruto</label>
                <input style={{ ...inputStyle, width: "8rem" }} type="number" value={novaFolha.valor_bruto} onChange={(e) => setNovaFolha({ ...novaFolha, valor_bruto: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Descontos</label>
                <input style={{ ...inputStyle, width: "7rem" }} type="number" value={novaFolha.descontos} onChange={(e) => setNovaFolha({ ...novaFolha, descontos: e.target.value })} />
              </div>
              <div>
                <label style={labelStyle}>Status</label>
                <select style={{ ...inputStyle, width: "7rem" }} value={novaFolha.status} onChange={(e) => setNovaFolha({ ...novaFolha, status: e.target.value as "pendente" | "pago" })}>
                  <option value="pendente">Pendente</option>
                  <option value="pago">Pago</option>
                </select>
              </div>
              <button onClick={lancar}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", padding: "0.45rem 0.7rem", borderRadius: "6px", border: "none", background: COR.dourado, color: "#0a0e1a", fontWeight: 700, cursor: "pointer" }}>
                <Plus size={12} /> Lançar folha
              </button>
            </div>

            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
              <thead>
                <tr style={{ color: COR.mudo, textAlign: "left" }}>
                  <ThOrdenavel label="Competência" campo="competencia" coluna={ordFolhas.coluna} dir={ordFolhas.dir} ordenar={ordFolhas.ordenar} />
                  <ThOrdenavel label="Bruto" campo="valor_bruto" coluna={ordFolhas.coluna} dir={ordFolhas.dir} ordenar={ordFolhas.ordenar} />
                  <ThOrdenavel label="Descontos" campo="descontos" coluna={ordFolhas.coluna} dir={ordFolhas.dir} ordenar={ordFolhas.ordenar} />
                  <ThOrdenavel label="Líquido" campo="valor_liquido" coluna={ordFolhas.coluna} dir={ordFolhas.dir} ordenar={ordFolhas.ordenar} />
                  <ThOrdenavel label="Status" campo="status" coluna={ordFolhas.coluna} dir={ordFolhas.dir} ordenar={ordFolhas.ordenar} />
                  <th style={{ padding: "0.3rem 0.5rem" }}></th>
                </tr>
              </thead>
              <tbody>
                {folhas === null && <tr><td colSpan={6} style={{ padding: "0.5rem", color: COR.mudo }}>Carregando…</td></tr>}
                {folhas?.length === 0 && <tr><td colSpan={6} style={{ padding: "0.5rem", color: COR.mudo }}>Nenhum lançamento ainda.</td></tr>}
                {folhas && ordFolhas.linhasOrdenadas.map((f) => (
                  <tr key={f.id} style={{ borderTop: `1px solid ${COR.borda}` }}>
                    <td style={{ padding: "0.4rem 0.5rem" }}>{f.competencia}</td>
                    <td style={{ padding: "0.4rem 0.5rem", fontVariantNumeric: "tabular-nums" }}>R$ {f.valor_bruto.toFixed(2)}</td>
                    <td style={{ padding: "0.4rem 0.5rem", fontVariantNumeric: "tabular-nums" }}>R$ {f.descontos.toFixed(2)}</td>
                    <td style={{ padding: "0.4rem 0.5rem", fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>R$ {f.valor_liquido.toFixed(2)}</td>
                    <td style={{ padding: "0.4rem 0.5rem", color: f.status === "pago" ? COR.verde : COR.dourado }}>{f.status}</td>
                    <td style={{ padding: "0.4rem 0.5rem", textAlign: "right" }}>
                      <button onClick={() => excluirFolha(f.id)} style={{ background: "transparent", border: "none", color: COR.vermelho, cursor: "pointer" }}>
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}
