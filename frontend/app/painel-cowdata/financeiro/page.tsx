"use client";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Plus, Trash2, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import {
  fetchCategoriasFinanceiroCowData, fetchLancamentosCowData, criarLancamentoCowData, excluirLancamentoCowData,
  fetchResumoFinanceiroCowData, fetchLivroCaixaCowData, fetchFluxoCaixaCowData, fetchDreCowData,
  type LancamentoCowData, type ResumoFinanceiroCowData, type MovimentoCowData, type FluxoCaixaCowDataMes, type DreCowData,
} from "@/lib/api";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", dourado: "#e8c256", verde: "#3ecf8e", vermelho: "#e05c5c", texto: "#e8ecf5" };
const inputStyle: React.CSSProperties = {
  background: "#0a0e1a", border: `1px solid ${COR.borda}`, borderRadius: "6px", padding: "0.45rem 0.6rem", color: COR.texto, fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: COR.mudo, marginBottom: "0.25rem", display: "block" };
const ABAS = ["lancamentos", "dre", "fluxo", "livro"] as const;
type Aba = typeof ABAS[number];
const LABEL_ABA: Record<Aba, string> = { lancamentos: "Lançamentos", dre: "DRE", fluxo: "Fluxo de Caixa", livro: "Livro Caixa" };

function moeda(v: number): string {
  return `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function primeiroDiaMes(ano: number, mes: number): string { return `${ano}-${String(mes + 1).padStart(2, "0")}-01`; }
function ultimoDiaMes(ano: number, mes: number): string {
  const d = new Date(ano, mes + 1, 0);
  return `${ano}-${String(mes + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function FinanceiroCowData() {
  const hoje = new Date();
  const [ano, setAno] = useState(hoje.getFullYear());
  const [mes, setMes] = useState(hoje.getMonth());
  const [aba, setAba] = useState<Aba>("lancamentos");
  const [resumo, setResumo] = useState<ResumoFinanceiroCowData | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const de = primeiroDiaMes(ano, mes);
  const ate = ultimoDiaMes(ano, mes);

  function carregarResumo() {
    fetchResumoFinanceiroCowData(de, ate).then(setResumo).catch((e) => setErro(e.message));
  }
  useEffect(carregarResumo, [ano, mes]);

  function mudarMes(delta: number) {
    let novoMes = mes + delta, novoAno = ano;
    if (novoMes < 0) { novoMes = 11; novoAno--; } else if (novoMes > 11) { novoMes = 0; novoAno++; }
    setMes(novoMes); setAno(novoAno);
  }

  const nomeMes = new Date(ano, mes, 1).toLocaleDateString("pt-BR", { month: "long", year: "numeric" });

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Financeiro CowData</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.2rem" }}>
        Livro-caixa independente da própria empresa CowData — receita de assinatura das fazendas-clientes, receitas
        avulsas, despesas e folha da Equipe CowData.
      </p>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1rem" }}>
        <button onClick={() => mudarMes(-1)} style={{ background: "transparent", border: `1px solid ${COR.borda}`, borderRadius: "6px", color: COR.mudo, cursor: "pointer", padding: "0.3rem" }}><ChevronLeft size={16} /></button>
        <span style={{ fontSize: "0.85rem", fontWeight: 700, textTransform: "capitalize", minWidth: "9rem", textAlign: "center" }}>{nomeMes}</span>
        <button onClick={() => mudarMes(1)} style={{ background: "transparent", border: `1px solid ${COR.borda}`, borderRadius: "6px", color: COR.mudo, cursor: "pointer", padding: "0.3rem" }}><ChevronRight size={16} /></button>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", marginBottom: "1.8rem" }}>
        <Kpi icone={<TrendingUp size={13} />} label="Receita do mês" valor={resumo ? moeda(resumo.receita) : "—"} cor={COR.verde} />
        <Kpi icone={<TrendingDown size={13} />} label="Despesa do mês" valor={resumo ? moeda(resumo.despesa) : "—"} cor={COR.vermelho} />
        <Kpi icone={<Wallet size={13} />} label="Resultado do mês" valor={resumo ? moeda(resumo.resultado) : "—"} cor={resumo && resumo.resultado < 0 ? COR.vermelho : COR.dourado} />
      </div>

      <div style={{ display: "flex", gap: "0.4rem", marginBottom: "1rem", borderBottom: `1px solid ${COR.borda}` }}>
        {ABAS.map((a) => (
          <button key={a} onClick={() => setAba(a)}
            style={{
              padding: "0.5rem 0.9rem", fontSize: "0.8rem", background: "transparent", border: "none", cursor: "pointer",
              color: aba === a ? COR.dourado : COR.mudo, fontWeight: aba === a ? 700 : 400,
              borderBottom: aba === a ? `2px solid ${COR.dourado}` : "2px solid transparent",
            }}>
            {LABEL_ABA[a]}
          </button>
        ))}
      </div>

      {aba === "lancamentos" && <AbaLancamentos de={de} ate={ate} onMudou={carregarResumo} />}
      {aba === "dre" && <AbaDre ano={ano} />}
      {aba === "fluxo" && <AbaFluxoCaixa de={de} ate={ate} />}
      {aba === "livro" && <AbaLivroCaixa de={de} ate={ate} />}
    </div>
  );
}

function Kpi({ icone, label, valor, cor }: { icone: React.ReactNode; label: string; valor: string; cor: string }) {
  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "1.1rem 1.3rem", flex: "1 1 12rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em", color: COR.mudo, marginBottom: "0.5rem" }}>
        {icone} {label}
      </div>
      <div style={{ fontSize: "1.5rem", fontWeight: 700, color: cor, fontVariantNumeric: "tabular-nums" }}>{valor}</div>
    </div>
  );
}

function AbaLancamentos({ de, ate, onMudou }: { de: string; ate: string; onMudou: () => void }) {
  const [lancamentos, setLancamentos] = useState<LancamentoCowData[] | null>(null);
  const [categorias, setCategorias] = useState<{ receita: string[]; despesa: string[] }>({ receita: [], despesa: [] });
  const [erro, setErro] = useState<string | null>(null);
  const [mostrarForm, setMostrarForm] = useState(false);
  const [novo, setNovo] = useState({ tipo: "despesa" as "receita" | "despesa", categoria: "", descricao: "", contraparte: "", valor: "", data: new Date().toISOString().slice(0, 10) });

  function carregar() {
    fetchLancamentosCowData(de, ate).then(setLancamentos).catch((e) => setErro(e.message));
  }
  useEffect(() => {
    fetchCategoriasFinanceiroCowData().then((c) => { setCategorias(c); setNovo((n) => ({ ...n, categoria: c.despesa[0] || "" })); }).catch((e) => setErro(e.message));
  }, []);
  useEffect(carregar, [de, ate]);

  function mudarTipo(tipo: "receita" | "despesa") {
    setNovo({ ...novo, tipo, categoria: categorias[tipo][0] || "" });
  }

  async function salvar() {
    if (!novo.descricao.trim() || !novo.valor) { setErro("Descrição e valor são obrigatórios."); return; }
    try {
      await criarLancamentoCowData({
        tipo: novo.tipo, categoria: novo.categoria, descricao: novo.descricao.trim(),
        contraparte: novo.contraparte || null, valor: Number(novo.valor), data: novo.data,
      });
      setNovo({ ...novo, descricao: "", contraparte: "", valor: "" });
      setMostrarForm(false);
      carregar(); onMudou();
    } catch (e: any) { setErro(e.message); }
  }

  async function excluir(id: number) {
    if (!confirm("Excluir este lançamento?")) return;
    try { await excluirLancamentoCowData(id); carregar(); onMudou(); } catch (e: any) { setErro(e.message); }
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.8rem" }}>
        <button onClick={() => setMostrarForm((v) => !v)}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.78rem", padding: "0.4rem 0.8rem", borderRadius: "6px", border: `1px solid ${COR.dourado}`, background: "transparent", color: COR.dourado, cursor: "pointer" }}>
          <Plus size={14} /> Novo lançamento
        </button>
      </div>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "0.8rem" }}>{erro}</p>}

      {mostrarForm && (
        <div style={{ background: COR.cartao, border: `1px solid ${COR.dourado}`, borderRadius: "12px", padding: "1rem 1.2rem", marginBottom: "1.2rem" }}>
          <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.7rem" }}>
            <button onClick={() => mudarTipo("receita")}
              style={{ flex: 1, padding: "0.4rem", borderRadius: "6px", border: `1px solid ${novo.tipo === "receita" ? COR.verde : COR.borda}`, background: novo.tipo === "receita" ? "rgba(62,207,142,0.12)" : "transparent", color: novo.tipo === "receita" ? COR.verde : COR.mudo, cursor: "pointer", fontSize: "0.8rem", fontWeight: 700 }}>
              Receita
            </button>
            <button onClick={() => mudarTipo("despesa")}
              style={{ flex: 1, padding: "0.4rem", borderRadius: "6px", border: `1px solid ${novo.tipo === "despesa" ? COR.vermelho : COR.borda}`, background: novo.tipo === "despesa" ? "rgba(224,92,92,0.12)" : "transparent", color: novo.tipo === "despesa" ? COR.vermelho : COR.mudo, cursor: "pointer", fontSize: "0.8rem", fontWeight: 700 }}>
              Despesa
            </button>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "0.7rem" }}>
            <div>
              <label style={labelStyle}>Categoria</label>
              <select style={{ ...inputStyle, width: "100%" }} value={novo.categoria} onChange={(e) => setNovo({ ...novo, categoria: e.target.value })}>
                {categorias[novo.tipo].map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <label style={labelStyle}>Descrição</label>
              <input style={{ ...inputStyle, width: "100%" }} value={novo.descricao} onChange={(e) => setNovo({ ...novo, descricao: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>{novo.tipo === "despesa" ? "Fornecedor" : "Cliente"} (opcional)</label>
              <input style={{ ...inputStyle, width: "100%" }} value={novo.contraparte} onChange={(e) => setNovo({ ...novo, contraparte: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Valor (R$)</label>
              <input style={{ ...inputStyle, width: "100%" }} type="number" value={novo.valor} onChange={(e) => setNovo({ ...novo, valor: e.target.value })} />
            </div>
            <div>
              <label style={labelStyle}>Data</label>
              <input style={{ ...inputStyle, width: "100%" }} type="date" value={novo.data} onChange={(e) => setNovo({ ...novo, data: e.target.value })} />
            </div>
          </div>
          <div style={{ marginTop: "0.8rem", display: "flex", gap: "0.5rem" }}>
            <button onClick={salvar}
              style={{ fontSize: "0.78rem", padding: "0.4rem 0.9rem", borderRadius: "6px", border: "none", background: COR.dourado, color: "#0a0e1a", fontWeight: 700, cursor: "pointer" }}>
              Lançar
            </button>
            <button onClick={() => setMostrarForm(false)}
              style={{ fontSize: "0.78rem", padding: "0.4rem 0.9rem", borderRadius: "6px", border: `1px solid ${COR.borda}`, background: "transparent", color: COR.mudo, cursor: "pointer" }}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", overflowX: "auto", overflowY: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COR.borda}`, color: COR.mudo, textAlign: "left" }}>
              <th style={{ padding: "0.6rem 1rem" }}>Data</th>
              <th style={{ padding: "0.6rem 1rem" }}>Descrição</th>
              <th style={{ padding: "0.6rem 1rem" }}>Categoria</th>
              <th style={{ padding: "0.6rem 1rem" }}>Valor</th>
              <th style={{ padding: "0.6rem 1rem" }}></th>
            </tr>
          </thead>
          <tbody>
            {lancamentos === null && <tr><td colSpan={5} style={{ padding: "1rem", color: COR.mudo }}>Carregando…</td></tr>}
            {lancamentos?.length === 0 && <tr><td colSpan={5} style={{ padding: "1rem", color: COR.mudo }}>Nenhum lançamento manual neste mês.</td></tr>}
            {lancamentos?.map((l) => (
              <tr key={l.id} style={{ borderBottom: `1px solid ${COR.borda}` }}>
                <td style={{ padding: "0.6rem 1rem" }}>{new Date(l.data + "T00:00:00").toLocaleDateString("pt-BR")}</td>
                <td style={{ padding: "0.6rem 1rem" }}>{l.descricao}{l.contraparte ? ` — ${l.contraparte}` : ""}</td>
                <td style={{ padding: "0.6rem 1rem", color: COR.mudo, textTransform: "capitalize" }}>{l.categoria.replace(/_/g, " ")}</td>
                <td style={{ padding: "0.6rem 1rem", fontVariantNumeric: "tabular-nums", color: l.tipo === "receita" ? COR.verde : COR.vermelho, fontWeight: 700 }}>
                  {l.tipo === "receita" ? "+" : "−"} {moeda(l.valor)}
                </td>
                <td style={{ padding: "0.6rem 1rem", textAlign: "right" }}>
                  <button onClick={() => excluir(l.id)} style={{ background: "transparent", border: "none", color: COR.vermelho, cursor: "pointer" }}>
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AbaDre({ ano }: { ano: number }) {
  const [dre, setDre] = useState<DreCowData | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => { fetchDreCowData(ano).then(setDre).catch((e) => setErro(e.message)); }, [ano]);

  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", padding: "1.2rem 1.4rem" }}>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem" }}>{erro}</p>}
      {!dre && !erro && <p style={{ color: COR.mudo, fontSize: "0.85rem" }}>Carregando…</p>}
      {dre && (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
          <tbody>
            <tr><td style={{ padding: "0.4rem 0", color: COR.mudo }}>Receita total ({ano})</td><td style={{ padding: "0.4rem 0", textAlign: "right", color: COR.verde, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{moeda(dre.receita_total)}</td></tr>
            <tr><td colSpan={2} style={{ padding: "0.6rem 0 0.2rem", color: COR.mudo, fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>Despesas por categoria</td></tr>
            {Object.entries(dre.despesas_por_categoria).map(([cat, valor]) => (
              <tr key={cat}><td style={{ padding: "0.3rem 0 0.3rem 0.8rem", color: COR.texto, textTransform: "capitalize" }}>{cat.replace(/_/g, " ")}</td><td style={{ padding: "0.3rem 0", textAlign: "right", color: COR.vermelho, fontVariantNumeric: "tabular-nums" }}>{moeda(valor)}</td></tr>
            ))}
            <tr style={{ borderTop: `1px solid ${COR.borda}` }}><td style={{ padding: "0.5rem 0", fontWeight: 700 }}>Despesa total</td><td style={{ padding: "0.5rem 0", textAlign: "right", color: COR.vermelho, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{moeda(dre.despesa_total)}</td></tr>
            <tr style={{ borderTop: `1px solid ${COR.borda}` }}>
              <td style={{ padding: "0.5rem 0", fontWeight: 700 }}>Resultado do ano</td>
              <td style={{ padding: "0.5rem 0", textAlign: "right", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: dre.resultado >= 0 ? COR.dourado : COR.vermelho }}>{moeda(dre.resultado)}</td>
            </tr>
          </tbody>
        </table>
      )}
    </div>
  );
}

function AbaFluxoCaixa({ de, ate }: { de: string; ate: string }) {
  const [linhas, setLinhas] = useState<FluxoCaixaCowDataMes[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => {
    const dez = de.slice(0, 4) + "-01-01";
    fetchFluxoCaixaCowData(dez, ate).then(setLinhas).catch((e) => setErro(e.message));
  }, [de, ate]);

  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", overflowX: "auto", overflowY: "hidden" }}>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", padding: "1rem" }}>{erro}</p>}
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${COR.borda}`, color: COR.mudo, textAlign: "left" }}>
            <th style={{ padding: "0.6rem 1rem" }}>Mês</th>
            <th style={{ padding: "0.6rem 1rem" }}>Entradas</th>
            <th style={{ padding: "0.6rem 1rem" }}>Saídas</th>
            <th style={{ padding: "0.6rem 1rem" }}>Saldo do mês</th>
            <th style={{ padding: "0.6rem 1rem" }}>Saldo acumulado</th>
          </tr>
        </thead>
        <tbody>
          {linhas === null && <tr><td colSpan={5} style={{ padding: "1rem", color: COR.mudo }}>Carregando…</td></tr>}
          {linhas?.length === 0 && <tr><td colSpan={5} style={{ padding: "1rem", color: COR.mudo }}>Sem movimentos.</td></tr>}
          {linhas?.map((l) => (
            <tr key={l.competencia} style={{ borderBottom: `1px solid ${COR.borda}` }}>
              <td style={{ padding: "0.6rem 1rem" }}>{l.competencia}</td>
              <td style={{ padding: "0.6rem 1rem", color: COR.verde, fontVariantNumeric: "tabular-nums" }}>{moeda(l.entradas)}</td>
              <td style={{ padding: "0.6rem 1rem", color: COR.vermelho, fontVariantNumeric: "tabular-nums" }}>{moeda(l.saidas)}</td>
              <td style={{ padding: "0.6rem 1rem", fontVariantNumeric: "tabular-nums", color: l.saldo_mes >= 0 ? COR.dourado : COR.vermelho }}>{moeda(l.saldo_mes)}</td>
              <td style={{ padding: "0.6rem 1rem", fontVariantNumeric: "tabular-nums", fontWeight: 700, color: l.saldo_acumulado >= 0 ? COR.dourado : COR.vermelho }}>{moeda(l.saldo_acumulado)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AbaLivroCaixa({ de, ate }: { de: string; ate: string }) {
  const [linhas, setLinhas] = useState<MovimentoCowData[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => { fetchLivroCaixaCowData(de, ate).then(setLinhas).catch((e) => setErro(e.message)); }, [de, ate]);

  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", overflowX: "auto", overflowY: "hidden" }}>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", padding: "1rem" }}>{erro}</p>}
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${COR.borda}`, color: COR.mudo, textAlign: "left" }}>
            <th style={{ padding: "0.6rem 1rem" }}>Data</th>
            <th style={{ padding: "0.6rem 1rem" }}>Descrição</th>
            <th style={{ padding: "0.6rem 1rem" }}>Categoria</th>
            <th style={{ padding: "0.6rem 1rem" }}>Valor</th>
            <th style={{ padding: "0.6rem 1rem" }}>Saldo acumulado</th>
          </tr>
        </thead>
        <tbody>
          {linhas === null && <tr><td colSpan={5} style={{ padding: "1rem", color: COR.mudo }}>Carregando…</td></tr>}
          {linhas?.length === 0 && <tr><td colSpan={5} style={{ padding: "1rem", color: COR.mudo }}>Sem movimentos no período.</td></tr>}
          {linhas?.map((m, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${COR.borda}` }}>
              <td style={{ padding: "0.6rem 1rem" }}>{new Date(m.data + "T00:00:00").toLocaleDateString("pt-BR")}</td>
              <td style={{ padding: "0.6rem 1rem" }}>{m.descricao}</td>
              <td style={{ padding: "0.6rem 1rem", color: COR.mudo, textTransform: "capitalize" }}>{m.categoria.replace(/_/g, " ")}</td>
              <td style={{ padding: "0.6rem 1rem", fontVariantNumeric: "tabular-nums", color: m.tipo === "receita" ? COR.verde : COR.vermelho, fontWeight: 700 }}>
                {m.tipo === "receita" ? "+" : "−"} {moeda(m.valor)}
              </td>
              <td style={{ padding: "0.6rem 1rem", fontVariantNumeric: "tabular-nums", fontWeight: 700, color: m.saldo_acumulado >= 0 ? COR.dourado : COR.vermelho }}>{moeda(m.saldo_acumulado)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
