"use client";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Trash2, UserPlus } from "lucide-react";
import {
  fetchCargosCowData, fetchEquipeCowData, criarMembroEquipeCowData, editarMembroEquipeCowData, excluirMembroEquipeCowData,
  fetchFolhaMembroCowData, lancarFolhaMembroCowData, excluirFolhaCowData, fetchTiposVinculoCowData,
  type PessoaCowData, type FolhaCowData,
} from "@/lib/api";

const UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];
const ESTADOS_CIVIS = ["Solteiro(a)", "Casado(a)", "União estável", "Divorciado(a)", "Viúvo(a)"];
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { CampoMoeda } from "@/components/CampoMoeda";

const COR = { cartao: "#262E39", borda: "#39424F", mudo: "#9CA6B4", dourado: "#6B7F99", verde: "#8faa7b", vermelho: "#b5544a", texto: "#F1F3F5" };
const inputStyle: React.CSSProperties = {
  background: "#1A2028", border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem",
  color: COR.texto, fontSize: "0.82rem", width: "100%",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: COR.mudo, marginBottom: "0.25rem", display: "block" };

function mesAtual(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const NOVO_VAZIO = {
  nome: "", cargo: "", telefone: "", email: "", cpf_cnpj: "",
  rg: "", genero: "", estado_civil: "",
  cep: "", endereco_rua: "", endereco_numero: "", endereco_bairro: "", endereco_cidade: "", endereco_uf: "",
  tipo_vinculo: "funcionario" as "funcionario" | "pj", subtipo_pj: "MEI",
  data_admissao: "", salario_base: "", pagamento_mensal: "",
};

export default function EquipeCowData() {
  const [cargos, setCargos] = useState<string[]>([]);
  const [subtiposPj, setSubtiposPj] = useState<string[]>([]);
  const [equipe, setEquipe] = useState<PessoaCowData[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mostrarForm, setMostrarForm] = useState(false);
  const [expandidoId, setExpandidoId] = useState<number | null>(null);

  const [novo, setNovo] = useState(NOVO_VAZIO);

  function carregar() {
    fetchEquipeCowData().then(setEquipe).catch((e) => setErro(e.message));
  }
  useEffect(() => {
    fetchCargosCowData().then((c) => { setCargos(c); setNovo((n) => ({ ...n, cargo: n.cargo || c[0] || "" })); }).catch((e) => setErro(e.message));
    fetchTiposVinculoCowData().then((d) => setSubtiposPj(d.subtipos_pj)).catch(() => {});
    carregar();
  }, []);

  async function salvarNovo() {
    if (!novo.nome.trim() || !novo.cargo) { setErro("Nome e cargo são obrigatórios."); return; }
    setErro(null);
    try {
      await criarMembroEquipeCowData({
        nome: novo.nome.trim(), cargo: novo.cargo,
        telefones: novo.telefone ? [novo.telefone] : [], emails: novo.email ? [novo.email] : [],
        cpf_cnpj: novo.cpf_cnpj || null,
        rg: novo.rg || null, genero: novo.genero || null, estado_civil: novo.estado_civil || null,
        cep: novo.cep || null, endereco_rua: novo.endereco_rua || null, endereco_numero: novo.endereco_numero || null,
        endereco_bairro: novo.endereco_bairro || null, endereco_cidade: novo.endereco_cidade || null, endereco_uf: novo.endereco_uf || null,
        tipo_vinculo: novo.tipo_vinculo, subtipo_pj: novo.tipo_vinculo === "pj" ? novo.subtipo_pj : null,
        data_admissao: novo.data_admissao || null,
        salario_base: novo.tipo_vinculo === "funcionario" && novo.salario_base ? Number(novo.salario_base) : null,
        pagamento_mensal: novo.tipo_vinculo === "pj" && novo.pagamento_mensal ? Number(novo.pagamento_mensal) : null,
      });
      setNovo({ ...NOVO_VAZIO, cargo: cargos[0] || "" });
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
        rg: p.rg, genero: p.genero, estado_civil: p.estado_civil,
        endereco_rua: p.endereco_rua, endereco_numero: p.endereco_numero, endereco_bairro: p.endereco_bairro,
        endereco_cidade: p.endereco_cidade, endereco_uf: p.endereco_uf,
        tipo_vinculo: p.tipo_vinculo, subtipo_pj: p.subtipo_pj, pagamento_mensal: p.pagamento_mensal,
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
          style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.78rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)", border: `1px solid ${COR.dourado}`, background: "transparent", color: COR.dourado, cursor: "pointer" }}>
          <UserPlus size={14} /> Novo membro
        </button>
      </div>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1rem", maxWidth: "42rem" }}>
        Time da própria CowData (sócios, comercial, T.I., financeiro, marketing, suporte) — totalmente separado do
        cadastro de Pessoas/funcionários de qualquer fazenda-cliente.
      </p>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

      {mostrarForm && (
        <div style={{ background: COR.cartao, border: `1px solid ${COR.dourado}`, borderRadius: "var(--r-sm)", padding: "1rem 1.2rem", marginBottom: "1.2rem" }}>
          <p style={{ fontSize: "0.72rem", color: COR.dourado, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "0.5rem" }}>Identificação</p>
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
              <label style={labelStyle}>RG</label>
              <input style={inputStyle} value={novo.rg} onChange={(e) => setNovo({ ...novo, rg: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Estado civil</label>
              <select style={inputStyle} value={novo.estado_civil} onChange={(e) => setNovo({ ...novo, estado_civil: e.target.value })}>
                <option value="">—</option>
                {ESTADOS_CIVIS.map((e) => <option key={e} value={e}>{e}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Gênero (opcional)</label>
              <input style={inputStyle} value={novo.genero} onChange={(e) => setNovo({ ...novo, genero: e.target.value })} />
            </div>
          </div>

          <p style={{ fontSize: "0.72rem", color: COR.dourado, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", margin: "0.9rem 0 0.5rem" }}>Endereço</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(9rem, 1fr))", gap: "0.7rem" }}>
            <div>
              <label style={labelStyle}>CEP</label>
              <input style={inputStyle} value={novo.cep} onChange={(e) => setNovo({ ...novo, cep: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Rua</label>
              <input style={inputStyle} value={novo.endereco_rua} onChange={(e) => setNovo({ ...novo, endereco_rua: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Número</label>
              <input style={inputStyle} value={novo.endereco_numero} onChange={(e) => setNovo({ ...novo, endereco_numero: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Bairro</label>
              <input style={inputStyle} value={novo.endereco_bairro} onChange={(e) => setNovo({ ...novo, endereco_bairro: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Cidade</label>
              <input style={inputStyle} value={novo.endereco_cidade} onChange={(e) => setNovo({ ...novo, endereco_cidade: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>UF</label>
              <select style={inputStyle} value={novo.endereco_uf} onChange={(e) => setNovo({ ...novo, endereco_uf: e.target.value })}>
                <option value="">—</option>
                {UFS.map((uf) => <option key={uf} value={uf}>{uf}</option>)}
              </select>
            </div>
          </div>

          <p style={{ fontSize: "0.72rem", color: COR.dourado, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", margin: "0.9rem 0 0.5rem" }}>Vínculo</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "0.7rem" }}>
            <div>
              <label style={labelStyle}>Tipo de vínculo</label>
              <select style={inputStyle} value={novo.tipo_vinculo} onChange={(e) => setNovo({ ...novo, tipo_vinculo: e.target.value as "funcionario" | "pj" })}>
                <option value="funcionario">Funcionário</option>
                <option value="pj">PJ</option>
              </select>
            </div>
            {novo.tipo_vinculo === "pj" && (
              <div>
                <label style={labelStyle}>Tipo de PJ</label>
                <select style={inputStyle} value={novo.subtipo_pj} onChange={(e) => setNovo({ ...novo, subtipo_pj: e.target.value })}>
                  {(subtiposPj.length ? subtiposPj : ["MEI", "ME", "EPP", "Outros"]).map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            )}
            <div>
              <label style={labelStyle}>Data de admissão</label>
              <input type="date" style={inputStyle} value={novo.data_admissao} onChange={(e) => setNovo({ ...novo, data_admissao: e.target.value })} />
            </div>
            {novo.tipo_vinculo === "funcionario" ? (
              <div>
                <label style={labelStyle}>Salário base (R$)</label>
                <CampoMoeda style={inputStyle} value={Number(novo.salario_base) || 0} onChange={(v) => setNovo({ ...novo, salario_base: v ? String(v) : "" })} />
              </div>
            ) : (
              <div>
                <label style={labelStyle}>Pagamento mensal (R$)</label>
                <CampoMoeda style={inputStyle} value={Number(novo.pagamento_mensal) || 0} onChange={(v) => setNovo({ ...novo, pagamento_mensal: v ? String(v) : "" })} />
              </div>
            )}
          </div>
          <p style={{ fontSize: "0.7rem", color: COR.mudo, marginTop: "0.6rem" }}>
            Contrato ({novo.tipo_vinculo === "pj" ? "prestação de serviços PJ" : "funcionário"}) para baixar: em preparação — ainda não disponível nesta tela.
          </p>

          <div style={{ marginTop: "0.8rem", display: "flex", gap: "0.5rem" }}>
            <button onClick={salvarNovo}
              style={{ fontSize: "0.78rem", padding: "0.4rem 0.9rem", borderRadius: "var(--r-sm)", border: "none", background: COR.dourado, color: "#1A2028", fontWeight: 700, cursor: "pointer" }}>
              Cadastrar
            </button>
            <button onClick={() => setMostrarForm(false)}
              style={{ fontSize: "0.78rem", padding: "0.4rem 0.9rem", borderRadius: "var(--r-sm)", border: `1px solid ${COR.borda}`, background: "transparent", color: COR.mudo, cursor: "pointer" }}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", overflowX: "auto", overflowY: "hidden" }}>
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
          <td colSpan={6} style={{ padding: "0.9rem 1.2rem", background: "#1A2028", borderBottom: `1px solid ${COR.borda}` }}>
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
                <CampoMoeda style={{ ...inputStyle, width: "8rem" }} value={Number(novaFolha.valor_bruto) || 0} onChange={(v) => setNovaFolha({ ...novaFolha, valor_bruto: v ? String(v) : "" })} />
              </div>
              <div>
                <label style={labelStyle}>Descontos</label>
                <CampoMoeda style={{ ...inputStyle, width: "7rem" }} value={Number(novaFolha.descontos) || 0} onChange={(v) => setNovaFolha({ ...novaFolha, descontos: v ? String(v) : "" })} />
              </div>
              <div>
                <label style={labelStyle}>Status</label>
                <select style={{ ...inputStyle, width: "7rem" }} value={novaFolha.status} onChange={(e) => setNovaFolha({ ...novaFolha, status: e.target.value as "pendente" | "pago" })}>
                  <option value="pendente">Pendente</option>
                  <option value="pago">Pago</option>
                </select>
              </div>
              <button onClick={lancar}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", padding: "0.45rem 0.7rem", borderRadius: "var(--r-sm)", border: "none", background: COR.dourado, color: "#1A2028", fontWeight: 700, cursor: "pointer" }}>
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
