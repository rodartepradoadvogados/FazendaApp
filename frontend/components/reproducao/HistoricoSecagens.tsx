"use client";
// Histórico de secagens (Reprodução) — GET /reproducao/secagens, com os
// filtros aplicáveis da sub-aba Reprodução (animal, data/ciclo) + motivo,
// análogo ao MultiFiltro de Diagnóstico/Motivo das outras abas.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Filter, Pencil, Trash2, X } from "lucide-react";
import { fetchSecagensHistorico, atualizarSecagem, fetchAnimais, confirmarExclusao, ehAdmin } from "@/lib/api";
import { TabBar, MultiFiltro, TelaSkeleton } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import type { AnimalRow } from "@/components/AnimalModal";

type SecagemReg = {
  id: number;
  numero: string; data: string | null; motivo: string; escore_condicao_corporal: number | null; observacao: string | null;
};

const MOTIVOS_SECAGEM = ["doente", "baixa_producao", "comportamento", "mastite", "casco", "rotina", "outros"] as const;

const MOTIVO_LABEL: Record<string, string> = {
  doente: "Doente", baixa_producao: "Baixa produção", comportamento: "Comportamento",
  mastite: "Mastite", casco: "Casco", rotina: "Rotina", outros: "Outros",
};

const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
const isoOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ddmm = (d: Date) => d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

export default function HistoricoSecagens() {
  const [regs, setRegs] = useState<SecagemReg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [animaisSel, setAnimaisSel] = useState<Set<string>>(new Set());
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  useEffect(() => { fetchAnimais().then(setAnimais).catch(() => {}); }, []);
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [motivo, setMotivo] = useState<string[]>([]);
  const [modo, setModo] = useState<"data" | "ciclo">("data");
  const [cicloSel, setCicloSel] = useState<"1" | "2" | "3" | "esp">("1");
  const [cicloIdx, setCicloIdx] = useState(0);
  const admin = ehAdmin();

  const carregar = () => fetchSecagensHistorico().then((d) => setRegs(d.secagens)).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const [editando, setEditando] = useState<SecagemReg | null>(null);
  const [editVals, setEditVals] = useState({ data: "", motivo: "rotina", escore: "", observacao: "" });
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);
  const [erroEdicao, setErroEdicao] = useState<string | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);

  const abrirEdicao = (s: SecagemReg) => {
    setEditando(s);
    setEditVals({ data: s.data || "", motivo: s.motivo || "rotina", escore: s.escore_condicao_corporal != null ? String(s.escore_condicao_corporal) : "", observacao: s.observacao || "" });
    setErroEdicao(null);
  };
  const salvarEdicao = async () => {
    if (!editando) return;
    setSalvandoEdicao(true); setErroEdicao(null);
    try {
      await atualizarSecagem(editando.id, {
        data_secagem: editVals.data || undefined, motivo: editVals.motivo || undefined,
        escore_condicao_corporal: editVals.escore.trim() === "" ? null : Number(editVals.escore),
        observacao: editVals.observacao || undefined,
      });
      setEditando(null);
      carregar();
    } catch (e: any) {
      setErroEdicao(e.message || "Erro ao salvar");
    } finally {
      setSalvandoEdicao(false);
    }
  };

  // Mesmo padrão de frontend/app/sanidade/page.tsx: passa pelo fluxo central
  // e auditado de exclusão (POST /exclusoes/confirmar) — excluir uma secagem
  // também devolve ao estoque o(s) produto(s) de secagem/vacina pré-parto já
  // aplicados e remove aplicações ainda programadas na Agenda (ver
  // rules/exclusao_tipos/rebanho.py::_alvos_secagem).
  const excluirSecagem = async (s: SecagemReg) => {
    const msg = admin
      ? `Excluir a secagem de "${s.numero}" em ${fmtDia(s.data)}? Isso também devolve ao estoque o(s) produto(s) já aplicados e remove aplicações programadas na Agenda. Não pode ser desfeito.`
      : `Solicitar a exclusão da secagem de "${s.numero}" em ${fmtDia(s.data)}? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setSalvandoEdicao(true); setErroEdicao(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("secagem", String(s.id));
      if (r.status === "excluido") {
        setEditando(null);
        carregar();
      } else {
        setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) {
      setErroEdicao(e.message || "Erro ao excluir");
    } finally {
      setSalvandoEdicao(false);
    }
  };

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
      (animaisSel.size === 0 || animaisSel.has(s.numero)) &&
      (modo === "data"
        ? (!ini || (s.data ? s.data >= ini : false)) && (!fim || (s.data ? s.data <= fim : false))
        : (!janelas || (s.data ? janelas.some(([a, b]) => s.data! >= a && s.data! <= b) : false))) &&
      (!motivo.length || motivo.includes(s.motivo))
    );
  }, [regs, animaisSel, ini, fim, motivo, modo, janelas]);

  const ordSecagens = useOrdenacao(filtrados);
  const pagSecagens = usePaginacao(ordSecagens.linhasOrdenadas);

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-bold">Histórico de secagens</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Todas as secagens do rebanho — filtre por animal, data/ciclo reprodutivo e motivo.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {avisoExclusao && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{avisoExclusao}</p>}
      {!regs && !error && <TelaSkeleton kpis={0} />}

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
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal(is)</label>
              <AnimalPickerModal
                animais={animais} selecionados={animaisSel}
                onToggle={(n) => setAnimaisSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; })}
                placeholder="Todos" titulo="Filtrar por animal(is) — inclui seleção por lote"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
                ]}
              /></div>
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
                {pagSecagens.linhasPagina.map((s, i) => (
                  <tr key={`${s.numero}-${s.data}-${i}`} onClick={() => abrirEdicao(s)} style={{ cursor: "pointer" }} title="Clique para editar">
                    <td style={{ fontWeight: 700 }}>{s.numero}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(s.data)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{MOTIVO_LABEL[s.motivo] || s.motivo}</td>
                    <td style={{ textAlign: "right" }}>{s.escore_condicao_corporal ?? "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.observacao || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Paginacao pagina={pagSecagens.pagina} totalPaginas={pagSecagens.totalPaginas} totalLinhas={pagSecagens.totalLinhas}
              tamanhoPagina={pagSecagens.tamanhoPagina} onMudarPagina={pagSecagens.setPagina} onMudarTamanho={pagSecagens.setTamanhoPagina} />
          </div>
        </div>
      </>}

      {editando && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "400px", maxWidth: "95vw" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0, display: "flex", alignItems: "center", gap: "0.4rem" }}><Pencil size={15} /> Editar secagem — matriz {editando.numero}</div>
              <button onClick={() => setEditando(null)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-1 gap-3">
              <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Data da secagem</label>
                <input type="date" style={selStyle} value={editVals.data} onChange={(e) => setEditVals((v) => ({ ...v, data: e.target.value }))} /></div>
              <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Motivo</label>
                <select style={selStyle} value={editVals.motivo} onChange={(e) => setEditVals((v) => ({ ...v, motivo: e.target.value }))}>
                  {MOTIVOS_SECAGEM.map((m) => <option key={m} value={m}>{MOTIVO_LABEL[m]}</option>)}
                </select></div>
              <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Escore de condição corporal</label>
                <input type="number" step="0.25" min="1" max="5" style={selStyle} value={editVals.escore} onChange={(e) => setEditVals((v) => ({ ...v, escore: e.target.value }))} /></div>
              <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Observação</label>
                <input style={selStyle} value={editVals.observacao} onChange={(e) => setEditVals((v) => ({ ...v, observacao: e.target.value }))} /></div>
            </div>
            {erroEdicao && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erroEdicao}</p>}
            <div className="flex items-center justify-between gap-3 mt-4">
              <div className="flex items-center gap-3">
                <button className="btn-primary" onClick={salvarEdicao} disabled={salvandoEdicao}>{salvandoEdicao ? "Salvando…" : "Salvar"}</button>
                <button className="btn-ghost" onClick={() => setEditando(null)}>Cancelar</button>
              </div>
              <button
                className="btn-ghost"
                style={{ color: "var(--red)", display: "flex", alignItems: "center", gap: "0.3rem" }}
                onClick={() => excluirSecagem(editando)}
                disabled={salvandoEdicao}
              >
                <Trash2 size={14} /> Excluir secagem
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
