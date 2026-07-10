"use client";
import { useEffect, useMemo, useState } from "react";
import { Package, AlertTriangle, Filter, Search } from "lucide-react";
import { fetchEstoque, fetchAgenda, formatBRL } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { ExportarBotoes } from "@/components/ExportarBotoes";

const COLUNAS_ESTOQUE = [
  { header: "Produto", key: "nome" }, { header: "Categoria", key: "categoria" },
  { header: "Qtd", key: "quantidade" }, { header: "Unidade", key: "unidade" },
  { header: "Mínimo", key: "estoque_minimo" }, { header: "Valor unit.", key: "valor_unitario" },
  { header: "Valor total", key: "valor_total" }, { header: "Status", key: "status" },
];

type Item = {
  categoria: string | null; nome: string; quantidade: number | null;
  estoque_minimo: number | null; unidade: string | null;
  valor_unitario: number | null; valor_total: number | null; abaixo_minimo: boolean | null;
};

const brk = (v: number) => `R$${(v / 1000).toFixed(0)}k`;
const CORES = ["var(--vinho-light, #8B3A56)", "var(--dourado)", "var(--blue)", "var(--amber)", "var(--green-light)"];

export default function EstoquePage() {
  const [itens, setItens] = useState<Item[] | null>(null);
  const [horm, setHorm] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fCat, setFCat] = useState("");
  const [busca, setBusca] = useState("");
  const [soAbaixo, setSoAbaixo] = useState(false);

  useEffect(() => {
    fetchEstoque().then((d) => setItens(d.itens)).catch((e) => setError(e.message));
    fetchAgenda().then((a) => setHorm(a.hormonios_check || [])).catch(() => {});
  }, []);

  const categorias = useMemo(() => {
    const s = new Set<string>(); (itens ?? []).forEach((i) => { if (i.categoria) s.add(i.categoria); });
    return Array.from(s).sort();
  }, [itens]);

  const filtrados = useMemo(() => {
    if (!itens) return [];
    return itens.filter((i) =>
      (!fCat || i.categoria === fCat) &&
      (!busca || i.nome.toLowerCase().includes(busca.toLowerCase())) &&
      (!soAbaixo || i.abaixo_minimo === true)
    );
  }, [itens, fCat, busca, soAbaixo]);

  const valorTotal = filtrados.reduce((a, i) => a + (i.valor_total || 0), 0);
  const abaixo = filtrados.filter((i) => i.abaixo_minimo === true).length;

  const porCategoria = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((i) => { const c = i.categoria || "(sem categoria)"; by.set(c, (by.get(c) ?? 0) + (i.valor_total || 0)); });
    return Array.from(by.entries()).map(([cat, valor]) => ({ cat, valor })).sort((a, b) => b.valor - a.valor).slice(0, 8);
  }, [filtrados]);

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Package size={22} style={{ color: "var(--dourado)" }} /> Estoque</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Inventário de insumos e medicamentos — filtre por categoria, busque ou veja só o que está abaixo do mínimo.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o ESTOQUE.csv</a>.</span></div>}
      {!itens && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {/* Hormônios IATF (necessidade vs estoque) */}
      {horm.length > 0 && (
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><AlertTriangle size={14} /> Hormônios IATF — Necessidade vs. Estoque</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {horm.map((h: any, i: number) => (
              <div key={i} className="p-3 rounded-lg" style={{ background: h.suficiente ? "rgba(46,125,82,0.1)" : "rgba(192,57,43,0.15)", border: `1px solid ${h.suficiente ? "var(--green)" : "var(--red)"}` }}>
                <div className="flex items-center justify-between mb-1">
                  <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{h.nome}</span>
                  <span style={{ color: h.suficiente ? "var(--green-light)" : "var(--red)", fontWeight: 800, fontSize: "0.8rem" }}>{h.suficiente ? "OK" : `FALTA ${Math.ceil(h.falta)} ${h.unidade}`}</span>
                </div>
                <div style={{ display: "flex", gap: "1.5rem", fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  <span>Estoque: <strong style={{ color: "var(--text)" }}>{h.estoque_atual?.toFixed(2)} {h.unidade}</strong></span>
                  <span>Necessário: <strong style={{ color: "var(--text)" }}>{h.necessidade?.toFixed(1)} {h.unidade}</strong></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {itens && (
        <>
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
                <select title="Filtrar itens por categoria" style={selStyle} value={fCat} onChange={(e) => setFCat(e.target.value)}><option value="">Todas</option>{categorias.map((c) => <option key={c}>{c}</option>)}</select></div>
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Buscar produto</label>
                <div style={{ position: "relative" }}>
                  <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
                  <input title="Buscar item pelo nome" style={{ ...selStyle, paddingLeft: "1.6rem" }} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: Sincrogest" />
                </div></div>
              <label title="Mostrar apenas itens com quantidade abaixo do estoque mínimo" style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", cursor: "pointer", paddingBottom: "0.35rem" }}>
                <input type="checkbox" checked={soAbaixo} onChange={(e) => setSoAbaixo(e.target.checked)} /> Só abaixo do mínimo
              </label>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="kpi-card"><p className="kpi-value">{filtrados.length}</p><p className="kpi-label">Itens (filtro)</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ fontSize: "1.25rem", color: "var(--dourado-light)" }}>{formatBRL(valorTotal)}</p><p className="kpi-label">Valor em estoque</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ color: abaixo ? "var(--red)" : "var(--green-light)" }}>{abaixo}</p><p className="kpi-label">Abaixo do mínimo</p></div>
            <div className="kpi-card"><p className="kpi-value">{categorias.length}</p><p className="kpi-label">Categorias</p></div>
          </div>

          <div className="card mb-4">
            <div className="card-header mb-3">Valor em Estoque por Categoria</div>
            <ResponsiveContainer width="100%" height={Math.max(180, porCategoria.length * 36)}>
              <BarChart data={porCategoria} layout="vertical" margin={{ left: 8 }}>
                <XAxis type="number" tickFormatter={brk} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
                <YAxis type="category" dataKey="cat" tick={{ fill: "var(--text-muted)", fontSize: 9 }} width={180} />
                <Tooltip formatter={(v: any) => formatBRL(Number(v))} contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="valor" name="Valor" radius={[0, 3, 3, 0]}>
                  {porCategoria.map((_, i) => <Cell key={i} fill={CORES[i % CORES.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between">
              <span>Itens</span>
              <div className="flex items-center gap-3">
                <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length} no filtro</span>
                <ExportarBotoes titulo="Estoque" nomeArquivoBase="estoque" colunas={COLUNAS_ESTOQUE}
                  linhas={filtrados.map((i) => ({ ...i, status: i.abaixo_minimo ? "ABAIXO DO MÍNIMO" : "OK" }))} />
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr><th>Produto</th><th>Categoria</th><th style={{ textAlign: "right" }}>Qtd</th><th style={{ textAlign: "right" }}>Mín.</th><th style={{ textAlign: "right" }}>Valor</th><th>Status</th></tr></thead>
                <tbody>
                  {filtrados.slice(0, 200).map((i, idx) => (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600, fontSize: "0.82rem" }}>{i.nome}</td>
                      <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{i.categoria || "—"}</td>
                      <td style={{ textAlign: "right" }}>{i.quantidade ?? "—"} {i.unidade || ""}</td>
                      <td style={{ textAlign: "right", color: "var(--text-muted)" }}>{i.estoque_minimo ?? "—"}</td>
                      <td style={{ textAlign: "right", fontWeight: 600 }}>{i.valor_total != null ? formatBRL(i.valor_total) : "—"}</td>
                      <td>{i.abaixo_minimo === true ? <span style={{ color: "var(--red)", fontWeight: 700, fontSize: "0.75rem" }}>ABAIXO</span> : <span style={{ color: "var(--green-light)", fontSize: "0.75rem" }}>OK</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtrados.length > 200 && <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>Mostrando 200 de {filtrados.length}.</p>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
