"use client";
// Histórico de partos (Reprodução) — GET /reproducao/partos, com os mesmos
// filtros aplicáveis da sub-aba Reprodução (animal, data/ciclo, ordem de
// parto). Ordem de tentativa/método/diagnóstico não fazem sentido aqui.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Filter, Pencil, Search, Trash2, X } from "lucide-react";
import { fetchPartosHistorico, atualizarParto, ehAdmin, confirmarExclusao } from "@/lib/api";
import { TabBar, MultiFiltro } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";

type PartoReg = {
  id: number;
  numero: string; data: string | null; ordem_parto: number | null; tipo_parto: string | null;
  sexo_cria_1: string | null; sexo_cria_2: string | null;
  numero_cria_1: string | null; numero_cria_2: string | null;
  gemelar: boolean | null; gemelar_sexo: string | null; retencao_placenta: boolean | null;
  usuario_nome?: string | null;
};

const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
const isoOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const ddmm = (d: Date) => d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

export default function HistoricoPartos() {
  const [regs, setRegs] = useState<PartoReg[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [animal, setAnimal] = useState("");
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [ordemParto, setOrdemParto] = useState<string[]>([]);
  const [modo, setModo] = useState<"data" | "ciclo">("data");
  const [cicloSel, setCicloSel] = useState<"1" | "2" | "3" | "esp">("1");
  const [cicloIdx, setCicloIdx] = useState(0);
  const admin = ehAdmin();

  const carregar = () => fetchPartosHistorico().then((d) => setRegs(d.partos)).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  const [editando, setEditando] = useState<PartoReg | null>(null);
  const [editVals, setEditVals] = useState({
    data: "", tipoParto: "", retencaoPlacenta: false,
    numeroCria1: "", numeroCria2: "", sexoCria1: "", sexoCria2: "",
  });
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);
  const [erroEdicao, setErroEdicao] = useState<string | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);

  const abrirEdicao = (p: PartoReg) => {
    setEditando(p);
    setEditVals({
      data: p.data || "", tipoParto: p.tipo_parto || "", retencaoPlacenta: !!p.retencao_placenta,
      numeroCria1: p.numero_cria_1 || "", numeroCria2: p.numero_cria_2 || "",
      sexoCria1: p.sexo_cria_1 || "", sexoCria2: p.sexo_cria_2 || "",
    });
    setErroEdicao(null);
  };
  const salvarEdicao = async () => {
    if (!editando) return;
    setSalvandoEdicao(true); setErroEdicao(null);
    try {
      await atualizarParto(editando.id, {
        data_parto: editVals.data || undefined, tipo_parto: editVals.tipoParto || undefined, retencao_placenta: editVals.retencaoPlacenta,
        numero_cria_1: editVals.numeroCria1 || null, numero_cria_2: editVals.numeroCria2 || null,
        sexo_cria_1: editVals.sexoCria1 || null, sexo_cria_2: editVals.sexoCria2 || null,
      });
      setEditando(null);
      carregar();
    } catch (e: any) {
      setErroEdicao(e.message || "Erro ao salvar");
    } finally {
      setSalvandoEdicao(false);
    }
  };

  // Passa pelo fluxo central e auditado de exclusão (POST /exclusoes/confirmar),
  // igual ao botão de frontend/app/sanidade/page.tsx:960-982 — admin exclui na
  // hora, operador vira uma solicitação pendente de aprovação. Excluir o
  // parto NÃO apaga a ficha da(s) cria(s) já cadastrada(s) — só o registro
  // do parto em si.
  const excluir = async (p: PartoReg) => {
    const msg = admin
      ? `Excluir o parto de "${p.numero}" em ${fmtDia(p.data)}? A ficha da(s) cria(s) já cadastrada(s) NÃO é apagada — só o registro do parto. Isso não pode ser desfeito.`
      : `Solicitar a exclusão do parto de "${p.numero}" em ${fmtDia(p.data)}? Um administrador precisa aprovar antes de ser excluído de fato.`;
    if (!window.confirm(msg)) return;
    setSalvandoEdicao(true); setErroEdicao(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("parto", String(p.id));
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

  const opcOrdemParto = useMemo(() => {
    const set = new Set<string>(); (regs ?? []).forEach((s) => { if (s.ordem_parto !== null) set.add(String(s.ordem_parto)); });
    return Array.from(set).sort((a, b) => +a - +b);
  }, [regs]);

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((s) =>
      (!animal || s.numero.toLowerCase().includes(animal.toLowerCase())) &&
      (modo === "data"
        ? (!ini || (s.data ? s.data >= ini : false)) && (!fim || (s.data ? s.data <= fim : false))
        : (!janelas || (s.data ? janelas.some(([a, b]) => s.data! >= a && s.data! <= b) : false))) &&
      (!ordemParto.length || ordemParto.includes(String(s.ordem_parto)))
    );
  }, [regs, animal, ini, fim, ordemParto, modo, janelas]);

  const ordPartos = useOrdenacao(filtrados);
  const pagPartos = usePaginacao(ordPartos.linhasOrdenadas);

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-bold">Histórico de partos</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Todos os partos do rebanho — filtre por animal, data/ciclo reprodutivo e ordem de parto.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {avisoExclusao && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{avisoExclusao}</p>}
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
            <MultiFiltro label="Ordem de parto" opcoes={opcOrdemParto} selecionados={ordemParto} onChange={setOrdemParto} />
          </div>
        </div>

        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between"><span>Partos</span><span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span></div>
          <div className="overflow-x-auto" style={{ maxHeight: "560px" }}>
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Matriz" campo="numero" coluna={ordPartos.coluna} dir={ordPartos.dir} ordenar={ordPartos.ordenar} />
                <ThOrdenavel label="Data" campo="data" coluna={ordPartos.coluna} dir={ordPartos.dir} ordenar={ordPartos.ordenar} />
                <ThOrdenavel label="Ord. parto" campo="ordem_parto" coluna={ordPartos.coluna} dir={ordPartos.dir} ordenar={ordPartos.ordenar} alinhar="right" />
                <ThOrdenavel label="Tipo" campo="tipo_parto" coluna={ordPartos.coluna} dir={ordPartos.dir} ordenar={ordPartos.ordenar} />
                <th style={{ textAlign: "left" }}>Cria(s)</th>
                <th style={{ textAlign: "left" }}>Retenção de placenta</th>
                {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
              </tr></thead>
              <tbody>
                {pagPartos.linhasPagina.map((p, i) => (
                  <tr key={`${p.numero}-${p.data}-${i}`} onClick={() => abrirEdicao(p)} style={{ cursor: "pointer" }} title="Clique para editar">
                    <td style={{ fontWeight: 700 }}>{p.numero}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(p.data)}</td>
                    <td style={{ textAlign: "right" }}>{p.ordem_parto ?? "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>{p.tipo_parto || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>
                      {[p.numero_cria_1 || (p.sexo_cria_1 ? `(${p.sexo_cria_1})` : null), p.numero_cria_2 || (p.sexo_cria_2 ? `(${p.sexo_cria_2})` : null)]
                        .filter(Boolean).join(", ") || "—"}
                      {p.gemelar && <span style={{ color: "var(--amber)", marginLeft: "0.3rem" }}>Gemelar{p.gemelar_sexo ? ` (${p.gemelar_sexo})` : ""}</span>}
                    </td>
                    <td style={{ fontSize: "0.78rem", color: p.retencao_placenta ? "var(--red)" : "var(--text-muted)" }}>{p.retencao_placenta ? "Sim" : "Não"}</td>
                    {admin && <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{p.usuario_nome ?? "—"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
            <Paginacao pagina={pagPartos.pagina} totalPaginas={pagPartos.totalPaginas} totalLinhas={pagPartos.totalLinhas}
              tamanhoPagina={pagPartos.tamanhoPagina} onMudarPagina={pagPartos.setPagina} onMudarTamanho={pagPartos.setTamanhoPagina} />
          </div>
        </div>
      </>}

      {editando && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "380px", maxWidth: "95vw" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0, display: "flex", alignItems: "center", gap: "0.4rem" }}><Pencil size={15} /> Editar parto — matriz {editando.numero}</div>
              <button onClick={() => setEditando(null)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-1 gap-3">
              <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Data do parto</label>
                <input type="date" style={selStyle} value={editVals.data} onChange={(e) => setEditVals((v) => ({ ...v, data: e.target.value }))} /></div>
              <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Tipo de parto</label>
                <input style={selStyle} value={editVals.tipoParto} onChange={(e) => setEditVals((v) => ({ ...v, tipoParto: e.target.value }))} placeholder="ex.: Normal, Distócico…" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Nº da cria 1</label>
                  <input style={selStyle} value={editVals.numeroCria1} onChange={(e) => setEditVals((v) => ({ ...v, numeroCria1: e.target.value }))} placeholder="ex.: 9001" /></div>
                <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Sexo da cria 1</label>
                  <select style={selStyle} value={editVals.sexoCria1} onChange={(e) => setEditVals((v) => ({ ...v, sexoCria1: e.target.value }))}>
                    <option value="">—</option><option value="F">Fêmea</option><option value="M">Macho</option>
                  </select></div>
              </div>
              {(editando.gemelar || editVals.numeroCria2 || editVals.sexoCria2) && (
                <div className="grid grid-cols-2 gap-3">
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Nº da cria 2 (gemelar)</label>
                    <input style={selStyle} value={editVals.numeroCria2} onChange={(e) => setEditVals((v) => ({ ...v, numeroCria2: e.target.value }))} placeholder="ex.: 9002" /></div>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Sexo da cria 2</label>
                    <select style={selStyle} value={editVals.sexoCria2} onChange={(e) => setEditVals((v) => ({ ...v, sexoCria2: e.target.value }))}>
                      <option value="">—</option><option value="F">Fêmea</option><option value="M">Macho</option>
                    </select></div>
                </div>
              )}
              <p style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                Editar o número da cria aqui só corrige o registro do parto — não move nem renomeia a ficha do animal da cria.
              </p>
              <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", cursor: "pointer" }}>
                <input type="checkbox" checked={editVals.retencaoPlacenta} onChange={(e) => setEditVals((v) => ({ ...v, retencaoPlacenta: e.target.checked }))} /> Retenção de placenta
              </label>
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
                onClick={() => excluir(editando)}
                disabled={salvandoEdicao}
              >
                <Trash2 size={14} /> Excluir
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
