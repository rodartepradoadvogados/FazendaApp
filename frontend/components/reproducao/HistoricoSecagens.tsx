"use client";
// Histórico de secagens (Reprodução) — GET /reproducao/secagens, com os
// filtros aplicáveis da sub-aba Reprodução (animal, data/ciclo) + motivo,
// análogo ao MultiFiltro de Diagnóstico/Motivo das outras abas.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Filter, Search } from "lucide-react";
import { fetchSecagensHistorico } from "@/lib/api";
import { TabBar, MultiFiltro } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

type SecagemReg = {
  numero: string; data: string | null; motivo: string; escore_condicao_corporal: number | null; observacao: string | null;
};

const MOTIVO_LABEL: Record<string, string> = {
  doente: "Doente", baixa_producao: "Baixa produção", comportamento: "Comportamento",
  mastite: "Mastite", casco: "Casco", rotina: "Rotina", outros: "Outros",
};

const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
const isoOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ddmm = (d: Date) => d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

export default function HistoricoSecagens() {
  const [regs, setRegs] = useState<SecagemReg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [animal, setAnimal] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [motivo, setMotivo] = useState<string[]>([]);
  const [modo, setModo] = useState<"data" | "ciclo">("data");
  const [cicloSel, setCicloSel] = useState<"1" | "2" | "3" | "esp">("1");
  const [cicloIdx, setCicloIdx] = useState(0);

  useEffect(() => { fetchSecagensHistorico().then((d) => setRegs(d.secagens)).catch((e) => setError(e.message)); }, []);

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

  const opcMotivo = useMemo(() => {
    const set = new Set<string>(); (regs ?? []).forEach((s) => { if (s.motivo) set.add(s.motivo); });
    return Array.from(set).sort();
  }, [regs]);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((s) =>
      (!animal || s.numero.toLowerCase().includes(animal.toLowerCase())) &&
      (modo === "data"
        ? (!ini || (s.data ? s.data >= ini : false)) && (!fim || (s.data ? s.data <= fim : false))
        : (!janelas || (s.data ? janelas.some(([a, b]) => s.data! >= a && s.data! <= b) : false))) &&
      (!motivo.length || motivo.includes(s.motivo))
    );
  }, [regs, animal, ini, fim, motivo, modo, janelas]);

  const ordSecagens = useOrdenacao(filtrados);

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-bold">Histórico de secagens</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Todas as secagens do rebanho — filtre por animal, data/ciclo reprodutivo e motivo.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!regs && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {regs && <>
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
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
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
            <MultiFiltro label="Motivo" opcoes={opcMotivo} selecionados={motivo} onChange={setMotivo} formatar={(m) => MOTIVO_LABEL[m] || m} />
          </div>
        </div>

        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between"><span>Secagens</span><span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span></div>
          <div className="overflow-x-auto" style={{ maxHeight: "560px" }}>
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Matriz" campo="numero" coluna={ordSecagens.coluna} dir={ordSecagens.dir} ordenar={ordSecagens.ordenar} />
                <ThOrdenavel label="Data" campo="data" coluna={ordSecagens.coluna} dir={ordSecagens.dir} ordenar={ordSecagens.ordenar} />
                <ThOrdenavel label="Motivo" campo="motivo" coluna={ordSecagens.coluna} dir={ordSecagens.dir} ordenar={ordSecagens.ordenar} />
                <ThOrdenavel label="Escore corporal" campo="escore_condicao_corporal" coluna={ordSecagens.coluna} dir={ordSecagens.dir} ordenar={ordSecagens.ordenar} alinhar="right" />
                <th style={{ textAlign: "left" }}>Observação</th>
              </tr></thead>
              <tbody>
                {ordSecagens.linhasOrdenadas.slice(0, 500).map((s, i) => (
                  <tr key={`${s.numero}-${s.data}-${i}`}>
                    <td style={{ fontWeight: 700 }}>{s.numero}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(s.data)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{MOTIVO_LABEL[s.motivo] || s.motivo}</td>
                    <td style={{ textAlign: "right" }}>{s.escore_condicao_corporal ?? "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.observacao || "—"}</td>
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
