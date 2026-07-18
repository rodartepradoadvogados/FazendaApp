"use client";
// Base compartilhada dos 4 históricos derivados de /reproducao/servicos
// (Serviços, IAs, Diagnósticos, Perda de prenhez) — mesmos filtros da antiga
// sub-aba única "Reprodução" (animal, data/ciclo, ordem de parto/tentativa,
// método, diagnóstico), cada foco pré-filtrando/ajustando o que faz sentido.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Filter, Plus, Search } from "lucide-react";
import { fetchServicosAnalise, registrarPerdaPrenhez, ehAdmin } from "@/lib/api";
import { TabBar, MultiFiltro } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { estiloSexado } from "@/lib/constants";

export type Serv = {
  numero: string; raca: string; categoria: string;
  ordem_parto: number | null; ordem_tentativa: number | null;
  tipo_servico: string; touro: string; metodo_ia?: string;
  tipo_semen?: string | null;
  data: string | null; del_servico: number | null;
  diagnostico: string | null; diagnosticado: boolean; positivo: boolean; perda: boolean;
  data_perda: string | null; motivo_perda: string | null;
  usuario_nome?: string | null;
};

export type Foco = "todos" | "ias" | "diagnosticos" | "perdas";

const DIAG_COR: Record<string, string> = { POSITIVO: "var(--green-light)", NEGATIVO: "var(--red)", ABERTO: "var(--amber)" };
const MOTIVO_LABEL: Record<string, string> = { aborto: "Aborto", natimorto: "Natimorto", outros: "Outros" };
const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
const isoOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ddmm = (d: Date) => d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

export default function HistoricoServicos({ foco, titulo, descricao }: { foco: Foco; titulo: string; descricao: string }) {
  const [regs, setRegs] = useState<Serv[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [animal, setAnimal] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [ordemParto, setOrdemParto] = useState<string[]>([]);
  const [ordemTentativa, setOrdemTentativa] = useState<string[]>([]);
  const [metodo, setMetodo] = useState<string[]>([]);
  const [diag, setDiag] = useState<string[]>([]);
  const [motivo, setMotivo] = useState<string[]>([]);
  const [modo, setModo] = useState<"data" | "ciclo">("data");
  const [cicloSel, setCicloSel] = useState<"1" | "2" | "3" | "esp">("1");
  const [cicloIdx, setCicloIdx] = useState(0);
  const admin = ehAdmin();

  const carregar = () => fetchServicosAnalise().then((d) => setRegs(d.servicos)).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  // Base do foco — aplicada ANTES dos filtros do usuário (não é opção, é o
  // recorte que define a aba: "IAs" nunca mostra monta natural, "Diagnósticos"
  // só mostra o que já foi diagnosticado, "Perda de prenhez" só as perdas.
  const base = useMemo(() => {
    if (!regs) return [];
    if (foco === "ias") return regs.filter((s) => s.metodo_ia !== "Monta natural");
    if (foco === "diagnosticos") return regs.filter((s) => s.diagnosticado);
    if (foco === "perdas") return regs.filter((s) => s.perda);
    return regs;
  }, [regs, foco]);

  const ciclos = useMemo(() => {
    const datas = base.map((s) => s.data).filter(Boolean).sort() as string[];
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
  }, [base]);

  const janelas = useMemo(() => {
    if (modo !== "ciclo" || !ciclos.length) return null;
    const sel = cicloSel === "1" ? ciclos.slice(0, 1)
      : cicloSel === "2" ? ciclos.slice(0, 2)
      : cicloSel === "3" ? ciclos.slice(0, 3)
      : ciclos.filter((c) => c.idx === cicloIdx);
    return sel.map((c) => [isoOf(c.ini), isoOf(c.fim)] as [string, string]);
  }, [modo, ciclos, cicloSel, cicloIdx]);

  const opc = (f: (s: Serv) => string | null) => {
    const set = new Set<string>(); base.forEach((s) => { const v = f(s); if (v) set.add(v); });
    return Array.from(set).sort((a, b) => (isNaN(+a) || isNaN(+b) ? a.localeCompare(b) : +a - +b));
  };

  const filtrados = useMemo(() => {
    return base.filter((s) =>
      (!animal || s.numero.toLowerCase().includes(animal.toLowerCase())) &&
      (modo === "data"
        ? (!ini || (s.data ? s.data >= ini : false)) && (!fim || (s.data ? s.data <= fim : false))
        : (!janelas || (s.data ? janelas.some(([a, b]) => s.data! >= a && s.data! <= b) : false))) &&
      (!ordemParto.length || ordemParto.includes(String(s.ordem_parto))) &&
      (!ordemTentativa.length || ordemTentativa.includes(String(s.ordem_tentativa))) &&
      (foco === "ias" || !metodo.length || metodo.includes(s.metodo_ia || "")) &&
      (foco !== "diagnosticos" || !diag.length || diag.includes(s.diagnostico || "")) &&
      (foco !== "perdas" || !motivo.length || motivo.includes(s.motivo_perda || "(sem motivo)"))
    ).sort((a, b) => ((a.data || "") < (b.data || "") ? 1 : -1));
  }, [base, animal, ini, fim, ordemParto, ordemTentativa, metodo, diag, motivo, modo, janelas, foco]);

  const diagnosticados = filtrados.filter((s) => s.diagnosticado).length;
  const positivos = filtrados.filter((s) => s.positivo).length;
  const taxa = diagnosticados ? Math.round((1000 * positivos) / diagnosticados) / 10 : null;
  const perdas = filtrados.filter((s) => s.perda).length;

  const ordServ = useOrdenacao(filtrados);

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-bold">{titulo}</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>{descricao}</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/upload" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Suba o reprodutivo</a>.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && <>
        {foco === "perdas" && <LancarPerdaPrenhez onSalvo={carregar} />}

        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} /> Filtros</div>
          <TabBar
            abas={[
              { id: "data", label: "Por data", title: "Filtrar por intervalo de datas (de/até)" },
              { id: "ciclo", label: "Por ciclo (21 dias)", title: "Filtrar por ciclo reprodutivo — janelas de 21 dias" },
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
            <MultiFiltro label="Ordem de parto" opcoes={opc((s) => s.ordem_parto === null ? null : String(s.ordem_parto))} selecionados={ordemParto} onChange={setOrdemParto} />
            <MultiFiltro label="Ordem de tentativa" opcoes={opc((s) => s.ordem_tentativa === null ? null : String(s.ordem_tentativa))} selecionados={ordemTentativa} onChange={setOrdemTentativa} />
            {foco !== "ias" && <MultiFiltro label="Método" opcoes={opc((s) => s.metodo_ia || null)} selecionados={metodo} onChange={setMetodo} />}
            {foco === "diagnosticos" && <MultiFiltro label="Diagnóstico" opcoes={["POSITIVO", "NEGATIVO"]} selecionados={diag} onChange={setDiag} />}
            {foco === "perdas" && <MultiFiltro label="Motivo" opcoes={opc((s) => s.motivo_perda || "(sem motivo)")} selecionados={motivo} onChange={setMotivo} />}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="kpi-card"><p className="kpi-value">{filtrados.length}</p><p className="kpi-label">{foco === "perdas" ? "Perdas" : "Registros"}</p></div>
          {foco !== "perdas" && <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--green-light)" }}>{positivos}</p><p className="kpi-label">Prenhezes</p></div>}
          {foco !== "perdas" && <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--blue)" }}>{taxa === null ? "—" : `${taxa}%`}</p><p className="kpi-label">Concepção / serviço</p></div>}
          {foco === "todos" && <div className="kpi-card"><p className="kpi-value" style={{ color: "var(--amber)" }}>{perdas}</p><p className="kpi-label">Perdas de prenhez</p></div>}
        </div>

        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between"><span>{titulo}</span><span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span></div>
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
                {foco === "perdas" && <><th style={{ textAlign: "left" }}>Data da perda</th><th style={{ textAlign: "left" }}>Motivo</th></>}
                {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
              </tr></thead>
              <tbody>
                {ordServ.linhasOrdenadas.slice(0, 500).map((s) => (
                  <tr key={`${s.numero}-${s.data}`} style={estiloSexado(s.tipo_semen)} title={s.tipo_semen === "sexado" ? "Inseminação com sêmen sexado" : undefined}>
                    <td style={{ fontWeight: 700 }}>{s.numero}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(s.data)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{s.tipo_servico}</td>
                    <td style={{ fontSize: "0.78rem" }}>{s.metodo_ia || "—"}</td>
                    <td><span style={{ color: DIAG_COR[s.diagnostico || "ABERTO"] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{s.diagnostico || "ABERTO"}</span></td>
                    <td style={{ textAlign: "right" }}>{s.ordem_parto ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{s.ordem_tentativa ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{s.del_servico ?? "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.touro}</td>
                    {foco === "perdas" && <>
                      <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(s.data_perda)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{s.motivo_perda ? (MOTIVO_LABEL[s.motivo_perda] || s.motivo_perda) : "—"}</td>
                    </>}
                    {admin && <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.usuario_nome ?? "—"}</td>}
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

/** Formulário mínimo para registrar a perda de prenhez com motivo — antes só
 * existia via importação de CSV, sem classificação nenhuma. */
function LancarPerdaPrenhez({ onSalvo }: { onSalvo: () => void }) {
  const [aberto, setAberto] = useState(false);
  const [numeroMatriz, setNumeroMatriz] = useState("");
  const [data, setData] = useState(() => new Date().toISOString().slice(0, 10));
  const [motivo, setMotivo] = useState<"aborto" | "natimorto" | "outros">("aborto");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);

  async function salvar() {
    setMsg(null);
    if (!numeroMatriz.trim()) { setMsg({ tipo: "erro", texto: "Informe o número da matriz." }); return; }
    setSalvando(true);
    try {
      await registrarPerdaPrenhez({ numero_matriz: numeroMatriz.trim(), data_perda_prenhez: data, motivo });
      setMsg({ tipo: "sucesso", texto: "Perda de prenhez registrada." });
      setNumeroMatriz("");
      onSalvo();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || "Erro ao registrar perda de prenhez" });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="card mb-4">
      <div className="card-header mb-2 flex items-center justify-between">
        <span>Registrar perda de prenhez</span>
        <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setAberto((v) => !v)}>
          <Plus size={13} /> {aberto ? "Fechar" : "Lançar"}
        </button>
      </div>
      {aberto && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Matriz</label>
            <input style={selStyle} value={numeroMatriz} onChange={(e) => setNumeroMatriz(e.target.value)} placeholder="ex.: 068" /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Data da perda</label>
            <input type="date" style={selStyle} value={data} onChange={(e) => setData(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Motivo</label>
            <select style={selStyle} value={motivo} onChange={(e) => setMotivo(e.target.value as any)}>
              <option value="aborto">Aborto</option>
              <option value="natimorto">Natimorto</option>
              <option value="outros">Outros</option>
            </select></div>
          <div style={{ display: "flex", alignItems: "flex-end" }}>
            <button className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
          </div>
          {msg && <p style={{ gridColumn: "1 / -1", color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.8rem", margin: 0 }}>{msg.texto}</p>}
        </div>
      )}
    </div>
  );
}
