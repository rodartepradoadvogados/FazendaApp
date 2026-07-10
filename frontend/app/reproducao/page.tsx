"use client";
import { useEffect, useMemo, useState } from "react";
import { Heart, PieChart, Stethoscope, AlertTriangle, Filter, Search } from "lucide-react";
import { fetchServicosAnalise, podeModulo } from "@/lib/api";
import { TabBar } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import AnaliseReprodutivaPage from "@/app/analise-reprodutiva/page";
import AgendaVeterinarioPage from "@/app/reproducao/AgendaVeterinario";

type Serv = {
  numero: string; raca: string; categoria: string;
  ordem_parto: number | null; ordem_tentativa: number | null;
  tipo_servico: string; touro: string; metodo_ia?: string;
  data: string | null; del_servico: number | null;
  diagnostico: string | null; diagnosticado: boolean; positivo: boolean; perda: boolean;
};

const DIAG_COR: Record<string, string> = { POSITIVO: "var(--green-light)", NEGATIVO: "var(--red)", ABERTO: "var(--amber)" };
const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
const isoOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ddmm = (d: Date) => d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

function ReproducaoVisaoGeral() {
  const [regs, setRegs] = useState<Serv[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [animal, setAnimal] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [ordemParto, setOrdemParto] = useState("");
  const [tipo, setTipo] = useState("");
  const [diag, setDiag] = useState("");
  // Filtro por DATA (de/até) OU por CICLO reprodutivo (janelas de 21 dias).
  const [modo, setModo] = useState<"data" | "ciclo">("data");
  const [cicloSel, setCicloSel] = useState<"1" | "2" | "3" | "esp">("1");
  const [cicloIdx, setCicloIdx] = useState(0);

  useEffect(() => { fetchServicosAnalise().then((d) => setRegs(d.servicos)).catch((e) => setError(e.message)); }, []);

  // Ciclos de 21 dias ancorados na data de serviço mais recente (proxy da última
  // visita reprodutiva/implante, até termos as datas de implante lançadas).
  const ciclos = useMemo(() => {
    const datas = (regs ?? []).map((s) => s.data).filter(Boolean).sort() as string[];
    if (!datas.length) return [] as { idx: number; ini: Date; fim: Date }[];
    const anchor = new Date(datas[datas.length - 1] + "T00:00:00");
    const primeiro = new Date(datas[0] + "T00:00:00");
    const arr: { idx: number; ini: Date; fim: Date }[] = [];
    for (let i = 0; i < 80; i++) {
      const fimC = new Date(anchor); fimC.setDate(fimC.getDate() - 21 * i);
      const iniC = new Date(fimC); iniC.setDate(iniC.getDate() - 20);
      arr.push({ idx: i, ini: iniC, fim: fimC });
      if (iniC <= primeiro) break;
    }
    return arr;
  }, [regs]);

  const janelas = useMemo(() => {
    if (modo !== "ciclo" || !ciclos.length) return null;
    const sel = cicloSel === "1" ? ciclos.slice(0, 1)
      : cicloSel === "2" ? ciclos.slice(0, 2)
      : cicloSel === "3" ? ciclos.slice(0, 3)
      : ciclos.filter((c) => c.idx === cicloIdx);
    return sel.map((c) => [isoOf(c.ini), isoOf(c.fim)] as [string, string]);
  }, [modo, ciclos, cicloSel, cicloIdx]);

  const opc = (f: (s: Serv) => string | null) => {
    const set = new Set<string>(); (regs ?? []).forEach((s) => { const v = f(s); if (v) set.add(v); });
    return Array.from(set).sort((a, b) => (isNaN(+a) || isNaN(+b) ? a.localeCompare(b) : +a - +b));
  };

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((s) =>
      (!animal || s.numero.toLowerCase().includes(animal.toLowerCase())) &&
      (modo === "data"
        ? (!ini || (s.data ? s.data >= ini : false)) && (!fim || (s.data ? s.data <= fim : false))
        : (!janelas || (s.data ? janelas.some(([a, b]) => s.data! >= a && s.data! <= b) : false))) &&
      (!ordemParto || String(s.ordem_parto) === ordemParto) &&
      (!tipo || s.tipo_servico === tipo) &&
      (!diag || (s.diagnostico || "ABERTO") === diag)
    ).sort((a, b) => ((a.data || "") < (b.data || "") ? 1 : -1));
  }, [regs, animal, ini, fim, ordemParto, tipo, diag, modo, janelas]);

  const diagnosticados = filtrados.filter((s) => s.diagnosticado).length;
  const positivos = filtrados.filter((s) => s.positivo).length;
  const taxa = diagnosticados ? Math.round((1000 * positivos) / diagnosticados) / 10 : null;
  const perdas = filtrados.filter((s) => s.perda).length;

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

  const ordServ = useOrdenacao(filtrados);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Heart size={22} style={{ color: "var(--dourado)" }} /> Reprodução</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Serviços por animal — filtre por data ou por ciclo reprodutivo (21 dias), ordem de parto/tentativa, tipo e diagnóstico.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o reprodutivo</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && <>
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          {/* Alternância: por data (de/até) OU por ciclo reprodutivo (21 dias). */}
          <TabBar
            abas={[
              { id: "data", label: "Por data", title: "Filtrar os serviços por intervalo de datas (de/até)" },
              { id: "ciclo", label: "Por ciclo (21 dias)", title: "Filtrar por ciclo reprodutivo — janelas de 21 dias ancoradas na data de serviço mais recente" },
            ] as const}
            ativa={modo}
            onChange={setModo}
          />
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal</label>
              <div style={{ position: "relative" }}><Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} /><input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={animal} onChange={(e) => setAnimal(e.target.value)} placeholder="ex.: 068" /></div></div>
            {modo === "data" ? (
              <>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label><input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label><input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
              </>
            ) : (
              <>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ciclo</label>
                  <select style={selStyle} value={cicloSel} onChange={(e) => setCicloSel(e.target.value as any)}>
                    <option value="1">Último ciclo</option>
                    <option value="2">Últimos 2 ciclos</option>
                    <option value="3">Últimos 3 ciclos</option>
                    <option value="esp">Ciclo específico</option>
                  </select></div>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Qual ciclo</label>
                  <select style={selStyle} value={cicloIdx} disabled={cicloSel !== "esp"} onChange={(e) => setCicloIdx(Number(e.target.value))}>
                    {ciclos.map((c) => <option key={c.idx} value={c.idx}>{c.idx === 0 ? "Atual" : `${c.idx + 1}º`} ({ddmm(c.ini)}–{ddmm(c.fim)})</option>)}
                  </select></div>
              </>
            )}
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Ordem de parto</label>
              <select style={selStyle} value={ordemParto} onChange={(e) => setOrdemParto(e.target.value)}><option value="">Todas</option>{opc((s) => s.ordem_parto === null ? null : String(s.ordem_parto)).map((o) => <option key={o}>{o}</option>)}</select></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Tipo</label>
              <select style={selStyle} value={tipo} onChange={(e) => setTipo(e.target.value)}><option value="">Todos</option>{opc((s) => s.tipo_servico).map((o) => <option key={o}>{o}</option>)}</select></div>
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Diagnóstico</label>
              <select style={selStyle} value={diag} onChange={(e) => setDiag(e.target.value)}><option value="">Todos</option>{["POSITIVO", "NEGATIVO", "ABERTO"].map((o) => <option key={o}>{o}</option>)}</select></div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="kpi-card"><p className="kpi-value">{filtrados.length}</p><p className="kpi-label">Serviços</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{positivos}</p><p className="kpi-label">Prenhezes</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--blue)" }}>{taxa === null ? "—" : `${taxa}%`}</p><p className="kpi-label">Concepção / serviço</p></div>
          <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--amber)" }}>{perdas}</p><p className="kpi-label">Perdas de prenhez</p></div>
        </div>

        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between"><span>Serviços</span><span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span></div>
          <div className="overflow-x-auto" style={{ maxHeight: "560px" }}>
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Matriz" campo="numero" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Data serviço" campo="data" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Tipo" campo="tipo_servico" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Método" campo="metodo_ia" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Diagnóstico" campo="diagnostico" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Ord. parto" campo="ordem_parto" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} alinhar="right" />
                <ThOrdenavel label="Tentativa" campo="ordem_tentativa" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} alinhar="right" />
                <ThOrdenavel label="DEL" campo="del_servico" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} alinhar="right" />
                <ThOrdenavel label="Touro" campo="touro" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
              </tr></thead>
              <tbody>
                {ordServ.linhasOrdenadas.slice(0, 500).map((s) => (
                  <tr key={`${s.numero}-${s.data}`}>
                    <td style={{ fontWeight: 700 }}>{s.numero}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(s.data)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{s.tipo_servico}</td>
                    <td style={{ fontSize: "0.78rem" }}>{s.metodo_ia || "—"}</td>
                    <td><span style={{ color: DIAG_COR[s.diagnostico || "ABERTO"] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{s.diagnostico || "ABERTO"}</span></td>
                    <td style={{ textAlign: "right" }}>{s.ordem_parto ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{s.ordem_tentativa ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{s.del_servico ?? "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.touro}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtrados.length > 500 && <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.5rem" }}>Mostrando 500 de {filtrados.length} — refine os filtros.</p>}
          </div>
        </div>
      </>}
    </div>
  );
}

export default function ReproducaoPage() {
  const [aba, setAba] = useState<"visao" | "analise" | "vet">("visao");
  const [temAnalise, setTemAnalise] = useState(false);
  const [temVet, setTemVet] = useState(false);
  // Cada usuário logado tem suas próprias permissões — reavalia sempre que a
  // página monta (evita mostrar abas de uma sessão anterior de outro usuário).
  useEffect(() => { setTemAnalise(podeModulo("analise")); setTemVet(podeModulo("vet")); }, []);

  if (!temAnalise && !temVet) return <ReproducaoVisaoGeral />;

  const abas = [
    { id: "visao" as const, label: "Reprodução", icon: Heart, title: "Visão geral dos serviços reprodutivos por animal" },
    ...(temAnalise ? [{ id: "analise" as const, label: "Análise reprodutiva", icon: PieChart, title: "Taxa de concepção e perda de prenhez, com quebras por dimensão" }] : []),
    ...(temVet ? [{ id: "vet" as const, label: "Agenda do veterinário", icon: Stethoscope, title: "Roteiro da visita reprodutiva: toques, reconfirmações e classificações" }] : []),
  ];
  const abaAtiva = abas.some((a) => a.id === aba) ? aba : "visao";

  return (
    <div className="px-6 pt-6">
      <TabBar abas={abas} ativa={abaAtiva} onChange={setAba} />
      <div style={{ margin: "0 -1.5rem" }}>
        {abaAtiva === "visao" ? <ReproducaoVisaoGeral /> : abaAtiva === "analise" ? <AnaliseReprodutivaPage /> : <div className="px-6"><AgendaVeterinarioPage /></div>}
      </div>
    </div>
  );
}
