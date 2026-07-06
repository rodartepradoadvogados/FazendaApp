"use client";
import { useEffect, useMemo, useState } from "react";
import { Syringe, AlertTriangle, Filter, Search } from "lucide-react";
import { fetchSanidade } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from "recharts";

type Aplic = {
  numero: string; raca: string; produto: string; categoria: string;
  dose: number | null; atividade: string | null; obs: string | null;
  data: string | null; ano: number | null; mes: string | null;
};

const CORES = ["var(--vinho-light, #8B3A56)", "var(--dourado)", "var(--blue)", "var(--amber)", "var(--green-light)", "var(--red)", "#7A5C99", "#4C9AA8"];

export default function SanidadePage() {
  const [regs, setRegs] = useState<Aplic[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fCat, setFCat] = useState("");
  const [fAno, setFAno] = useState("");
  const [buscaProd, setBuscaProd] = useState("");
  const [buscaAnimal, setBuscaAnimal] = useState("");

  useEffect(() => { fetchSanidade().then((d) => setRegs(d.aplicacoes)).catch((e) => setError(e.message)); }, []);

  const opc = (f: (a: Aplic) => string | null) => {
    const s = new Set<string>(); (regs ?? []).forEach((a) => { const v = f(a); if (v) s.add(v); });
    return Array.from(s).sort();
  };

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((a) =>
      (!fCat || a.categoria === fCat) &&
      (!fAno || String(a.ano) === fAno) &&
      (!buscaProd || a.produto.toLowerCase().includes(buscaProd.toLowerCase())) &&
      (!buscaAnimal || a.numero.toLowerCase().includes(buscaAnimal.toLowerCase()))
    );
  }, [regs, fCat, fAno, buscaProd, buscaAnimal]);

  const porCategoria = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => by.set(a.categoria, (by.get(a.categoria) ?? 0) + 1));
    return Array.from(by.entries()).map(([cat, n]) => ({ cat, n })).sort((a, b) => b.n - a.n);
  }, [filtrados]);

  const porMes = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => { if (a.mes) by.set(a.mes, (by.get(a.mes) ?? 0) + 1); });
    return Array.from(by.keys()).sort().map((mes) => ({ mes, n: by.get(mes)! }));
  }, [filtrados]);

  const topProdutos = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => by.set(a.produto, (by.get(a.produto) ?? 0) + 1));
    return Array.from(by.entries()).map(([produto, n]) => ({ produto, n })).sort((a, b) => b.n - a.n).slice(0, 10);
  }, [filtrados]);

  const animaisTratados = new Set(filtrados.map((a) => a.numero)).size;
  const produtos = new Set(filtrados.map((a) => a.produto)).size;
  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Syringe size={22} style={{ color: "var(--dourado)" }} /> Sanidade</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Medicamentos aplicados — filtre por categoria, ano, produto ou animal.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o SANIDADE.csv</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && <>
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
              <select style={selStyle} value={fCat} onChange={(e) => setFCat(e.target.value)}><option value="">Todas</option>{opc((a) => a.categoria).map((o) => <option key={o}>{o}</option>)}</select></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ano</label>
              <select style={selStyle} value={fAno} onChange={(e) => setFAno(e.target.value)}><option value="">Todos</option>{opc((a) => a.ano === null ? null : String(a.ano)).map((o) => <option key={o}>{o}</option>)}</select></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Produto</label>
              <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={buscaProd} onChange={(e) => setBuscaProd(e.target.value)} placeholder="ex.: Ivermectina" /></div></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
              <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={buscaAnimal} onChange={(e) => setBuscaAnimal(e.target.value)} placeholder="ex.: 068" /></div></div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="kpi-card"><p className="kpi-value">{filtrados.length}</p><p className="kpi-label">Aplicações</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{animaisTratados}</p><p className="kpi-label">Animais tratados</p></div>
          <div className="kpi-card"><p className="kpi-value">{produtos}</p><p className="kpi-label">Produtos distintos</p></div>
          <div className="kpi-card"><p className="kpi-value">{porCategoria.length}</p><p className="kpi-label">Categorias</p></div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div className="card">
            <div className="card-header mb-3">Aplicações por Categoria <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para filtrar)</span></div>
            <ResponsiveContainer width="100%" height={Math.max(180, porCategoria.length * 34)}>
              <BarChart data={porCategoria} layout="vertical" margin={{ left: 8 }}>
                <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 10 }} allowDecimals={false} />
                <YAxis type="category" dataKey="cat" tick={{ fill: "var(--text-muted)", fontSize: 10 }} width={130} />
                <Tooltip contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="n" name="Aplicações" radius={[0, 3, 3, 0]} style={{ cursor: "pointer" }} onClick={(e: any) => e?.cat && setFCat((c) => c === e.cat ? "" : e.cat)}>
                  {porCategoria.map((_, i) => <Cell key={i} fill={CORES[i % CORES.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="card">
            <div className="card-header mb-3">Aplicações por Mês</div>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={porMes}>
                <XAxis dataKey="mes" tick={{ fill: "var(--text-muted)", fontSize: 9 }} tickFormatter={(m) => m.slice(2)} />
                <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} allowDecimals={false} width={30} />
                <Tooltip contentStyle={tip} />
                <Line type="monotone" dataKey="n" name="Aplicações" stroke="var(--dourado-light)" strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card">
            <div className="card-header mb-3">Top Produtos</div>
            <table className="fazenda-table">
              <thead><tr><th>Produto</th><th style={{ textAlign: "right" }}>Aplic.</th></tr></thead>
              <tbody>{topProdutos.map((p) => <tr key={p.produto}><td style={{ fontSize: "0.8rem" }}>{p.produto}</td><td style={{ textAlign: "right", fontWeight: 700 }}>{p.n}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between"><span>Aplicações</span><span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span></div>
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table">
                <thead><tr><th>Data</th><th>Animal</th><th>Produto</th><th>Categoria</th><th style={{ textAlign: "right" }}>Dose</th></tr></thead>
                <tbody>
                  {filtrados.slice(0, 300).map((a, i) => (
                    <tr key={i}>
                      <td style={{ whiteSpace: "nowrap", fontSize: "0.75rem" }}>{a.data ? new Date(a.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.produto}</td>
                      <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{a.categoria}</td>
                      <td style={{ textAlign: "right" }}>{a.dose ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtrados.length > 300 && <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>Mostrando 300 de {filtrados.length} — refine os filtros.</p>}
            </div>
          </div>
        </div>
      </>}
    </div>
  );
}
