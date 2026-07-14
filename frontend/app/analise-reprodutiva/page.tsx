"use client";
import { useEffect, useMemo, useState } from "react";
import { HeartPulse, AlertTriangle, Filter } from "lucide-react";
import { fetchServicosAnalise, fetchInseminadores, ehAdmin } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { SecaoRecolhivel, MultiFiltro } from "@/components/ui";
import AnaliseInterativa from "@/components/AnaliseInterativa";

function comparaNumero(a: string, b: string) {
  return isNaN(+a) || isNaN(+b) ? a.localeCompare(b) : +a - +b;
}

const COLUNAS_SERVICOS = [
  { header: "Nº", key: "numero" }, { header: "Raça", key: "raca" }, { header: "Categoria", key: "categoria" },
  { header: "Data", key: "data" }, { header: "Tipo", key: "tipo_servico" }, { header: "Método", key: "metodo_ia" },
  { header: "Touro", key: "touro" }, { header: "Inseminador", key: "inseminador" }, { header: "Protocolo", key: "protocolo" },
  { header: "Ordem parto", key: "ordem_parto" }, { header: "Ordem tentativa", key: "ordem_tentativa" },
  { header: "DEL serviço", key: "del_servico" }, { header: "Diagnóstico", key: "diagnostico" },
];

type Reg = {
  numero: string; raca: string; categoria: string;
  ordem_parto: number | null; ordem_tentativa: number | null;
  tipo_servico: string; protocolo: string; touro: string; inseminador: string; metodo_ia: string;
  ano: number | null; mes: string | null; data: string | null; del_servico: number | null;
  diagnostico: string | null; diagnosticado: boolean; positivo: boolean; perda: boolean;
  usuario_nome?: string | null;
};

// Dimensões que o usuário pode usar para filtrar e para quebrar os gráficos.
// Há período de/até, então não há filtro de "ano". Sem filtros de raça (por ora).
const DIMENSOES: { key: keyof Reg; label: string }[] = [
  { key: "tipo_servico", label: "Tipo de serviço" },
  { key: "metodo_ia", label: "Método (IATF / cio)" },
  { key: "touro", label: "Touro / sêmen" },
  { key: "inseminador", label: "Inseminador" },
  { key: "ordem_parto", label: "Ordem de parto" },
  { key: "ordem_tentativa", label: "Ordem de tentativa" },
];

function opcoes(regs: Reg[], key: keyof Reg): string[] {
  const s = new Set<string>();
  regs.forEach((r) => { const v = r[key]; if (v !== null && v !== undefined && v !== "") s.add(String(v)); });
  return Array.from(s).sort((a, b) => (isNaN(+a) || isNaN(+b) ? a.localeCompare(b) : +a - +b));
}

function taxa(regs: Reg[]) {
  const diag = regs.filter((r) => r.diagnosticado).length;
  const pos = regs.filter((r) => r.positivo).length;
  return { diag, pos, pct: diag ? Math.round((1000 * pos) / diag) / 10 : null };
}

export default function AnaliseReprodutivaPage() {
  const [regs, setRegs] = useState<Reg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filtros, setFiltros] = useState<Record<string, string[]>>({});
  const [dimensao, setDimensao] = useState<keyof Reg>("tipo_servico");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [inseminadoresCadastrados, setInseminadoresCadastrados] = useState<string[]>([]);
  const admin = ehAdmin();

  useEffect(() => {
    fetchServicosAnalise()
      .then((d) => setRegs(d.servicos))
      .catch((e) => setError(e.message));
    fetchInseminadores().then(setInseminadoresCadastrados).catch(() => setInseminadoresCadastrados([]));
  }, []);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((r) =>
      (!ini || (r.data ? r.data >= ini : false)) &&
      (!fim || (r.data ? r.data <= fim : false)) &&
      DIMENSOES.every(({ key }) => {
        const f = filtros[key as string];
        return !f || f.length === 0 || f.includes(String(r[key]));
      }));
  }, [regs, filtros, ini, fim]);

  const kpi = taxa(filtrados);
  const perdas = filtrados.filter((r) => r.perda).length;

  const filtradosOrdenadosBase = useMemo(() => [...filtrados].sort((a, b) => comparaNumero(a.numero, b.numero)), [filtrados]);
  const ordFiltrados = useOrdenacao(filtradosOrdenadosBase);

  const quebra = useMemo(() => {
    const by = new Map<string, Reg[]>();
    filtrados.forEach((r) => {
      const k = String(r[dimensao] ?? "—");
      (by.get(k) ?? by.set(k, []).get(k)!).push(r);
    });
    return Array.from(by.entries())
      .map(([k, arr]) => ({ k, ...taxa(arr), n: arr.length }))
      .filter((x) => x.diag > 0)
      .sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0));
  }, [filtrados, dimensao]);

  const selStyle: React.CSSProperties = {
    background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
    borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%",
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <HeartPulse size={22} style={{ color: "var(--dourado-light)" }} />
          Análise Reprodutiva
        </h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Taxa de concepção e perda de prenhez — filtre e cruze por qualquer dimensão.
        </p>
      </div>

      {error && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Faça o upload do reprodutivo</a>.</span>
        </div>
      )}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && (
        <>
          {/* Filtros */}
          <div className="card mb-4">
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              <div>
                <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Período — de</label>
                <input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} />
              </div>
              <div>
                <label style={{ fontSize: "0.7rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>até</label>
                <input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} />
              </div>
              {DIMENSOES.map(({ key, label }) => {
                const opcoesBase = opcoes(regs, key);
                const opcoesFinais = key === "inseminador"
                  ? Array.from(new Set([...opcoesBase, ...inseminadoresCadastrados])).sort()
                  : opcoesBase;
                return (
                  <MultiFiltro key={key as string} label={label} opcoes={opcoesFinais}
                    selecionados={filtros[key as string] ?? []}
                    onChange={(v) => setFiltros((p) => ({ ...p, [key as string]: v }))} />
                );
              })}
            </div>
            {Object.values(filtros).some((v) => v && v.length) && (
              <button onClick={() => setFiltros({})} className="btn-ghost" title="Remover todos os filtros de dimensão aplicados" style={{ marginTop: "0.75rem", fontSize: "0.75rem" }}>
                Limpar filtros
              </button>
            )}
          </div>

          {/* KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{kpi.pct === null ? "—" : `${kpi.pct}%`}</p><p className="kpi-label">Taxa de concepção</p></div>
            <div className="kpi-card"><p className="kpi-value">{kpi.diag}</p><p className="kpi-label">Serviços diagnosticados</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--blue)" }}>{kpi.pos}</p><p className="kpi-label">Positivos</p></div>
            <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--amber)" }}>{perdas}</p><p className="kpi-label">Perdas de prenhez</p></div>
          </div>

          {/* Análise interativa configurável (cruzamento de métricas) */}
          <div className="flex justify-end mb-2">
            <ExportarBotoes titulo="Análise Reprodutiva — Serviços" nomeArquivoBase="analise_reprodutiva" colunas={COLUNAS_SERVICOS} linhas={filtrados} />
          </div>
          <AnaliseInterativa />

          {/* Quebra por dimensão */}
          <div className="card">
            <div className="card-header mb-3 flex items-center gap-2" style={{ flexWrap: "wrap" }}>
              <span>Concepção por</span>
              <select title="Escolha a dimensão para quebrar a taxa de concepção (tipo de serviço, método, touro, ordem de parto ou tentativa)" style={{ ...selStyle, width: "auto" }} value={dimensao as string} onChange={(e) => setDimensao(e.target.value as keyof Reg)}>
                {DIMENSOES.map((d) => <option key={d.key as string} value={d.key as string}>{d.label}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              {quebra.map((row) => (
                <div key={row.k} className="flex items-center gap-3">
                  <span style={{ fontSize: "0.78rem", minWidth: "9rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{row.k}</span>
                  <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: "4px", height: "18px", overflow: "hidden" }}>
                    <div style={{ width: `${row.pct ?? 0}%`, height: "100%", background: "var(--green-light)", minWidth: "2px" }} />
                  </div>
                  <span style={{ fontSize: "0.78rem", fontWeight: 700, minWidth: "8.5rem", textAlign: "right" }}>
                    {row.pct}% <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>({row.pos}/{row.diag})</span>
                  </span>
                </div>
              ))}
              {!quebra.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem dados diagnosticados no filtro atual.</p>}
            </div>
          </div>

          {/* Registros filtrados — mostra o touro/sêmen usado em cada serviço/IA */}
          <SecaoRecolhivel
            titulo="Registros filtrados"
            badge={<span style={{ fontSize: "0.7rem", color: "var(--text-muted)", background: "var(--surface-2)", borderRadius: "999px", padding: "0.1rem 0.55rem", whiteSpace: "nowrap" }}>{filtrados.length} registros</span>}
            descricao="Lista serviço a serviço com método, touro/sêmen, protocolo e diagnóstico dos registros que atendem aos filtros.">
            <div className="flex items-center justify-end mb-3">
              <ExportarBotoes titulo="Análise Reprodutiva — Registros filtrados" nomeArquivoBase="analise_reprodutiva_registros" colunas={COLUNAS_SERVICOS} linhas={filtradosOrdenadosBase} />
            </div>
            <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
              <table className="fazenda-table" style={{ margin: 0 }}>
                <thead><tr>
                  <ThOrdenavel label="Nº" campo="numero" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Raça" campo="raca" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Data" campo="data" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Tipo" campo="tipo_servico" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Método" campo="metodo_ia" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Touro / sêmen" campo="touro" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Inseminador" campo="inseminador" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Protocolo" campo="protocolo" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  <ThOrdenavel label="Diagnóstico" campo="diagnostico" coluna={ordFiltrados.coluna} dir={ordFiltrados.dir} ordenar={ordFiltrados.ordenar} />
                  {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
                </tr></thead>
                <tbody>
                  {ordFiltrados.linhasOrdenadas.map((r, i) => (
                    <tr key={`${r.numero}-${r.data}-${i}`}>
                      <td style={{ fontWeight: 700 }}>{r.numero}</td>
                      <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{r.raca}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.data ? new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.tipo_servico || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.metodo_ia || "—"}</td>
                      <td style={{ fontWeight: 600 }}>{r.touro || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.inseminador && r.inseminador !== "(sem inseminador)" ? r.inseminador : "—"}</td>
                      <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.protocolo || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{r.diagnostico || "—"}</td>
                      {admin && <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.usuario_nome ?? "—"}</td>}
                    </tr>
                  ))}
                  {!filtrados.length && <tr><td colSpan={admin ? 10 : 9} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhum registro no filtro atual.</td></tr>}
                </tbody>
              </table>
            </div>
          </SecaoRecolhivel>
        </>
      )}
    </div>
  );
}
