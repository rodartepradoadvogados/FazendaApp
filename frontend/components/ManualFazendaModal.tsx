"use client";
// Manual da Fazenda — botão (só na Capa, ver AuthShell.tsx) que abre janela
// suspensa com a rotina automática (BST, visita reprodutiva, sanitário,
// compras), o resultado atual (KPIs), insights (comparativo com o período
// anterior) e sugestões (customizadas + automáticas). Ver Configurações >
// Parâmetros > Manual da Fazenda para o envio semanal por e-mail e o
// cadastro de sugestões. Posicionamento (fixed no topo, ao lado do News) é
// do container pai — ver .site-top-actions em globals.css.
import { useEffect, useState } from "react";
import { BookOpen, Download, Share2, TrendingUp, TrendingDown, Activity, Sparkles, AlertTriangle, X } from "lucide-react";
import { fetchManualFazenda, baixarPdfManualFazenda, type ManualFazenda } from "@/lib/api";
import { ehApp } from "@/lib/nativo";

const fmtDia = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("pt-BR");

type Aba = "rotina" | "resultado" | "insights" | "sugestoes";
const ABAS: { id: Aba; label: string }[] = [
  { id: "rotina", label: "Sua rotina" },
  { id: "resultado", label: "Resultado" },
  { id: "insights", label: "Insights" },
  { id: "sugestoes", label: "Preditivo e sugestões" },
];

export function ManualFazendaButton() {
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <button
        onClick={() => setAberto(true)}
        title="Manual da Fazenda — sua rotina automática e resultados"
        style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem",
          background: "linear-gradient(135deg, var(--vinho, #0E2A47), var(--vinho-light, #416180))",
          color: "var(--dourado-light)", border: "none", borderRadius: "999px",
          padding: "0.55rem 1.1rem", fontSize: "0.82rem", fontWeight: 600, cursor: "pointer",
          boxShadow: "0 4px 14px rgba(58,15,26,0.35)", whiteSpace: "nowrap",
        }}>
        <BookOpen size={15} /> Manual da Fazenda
      </button>
      {aberto && <ManualFazendaModal onClose={() => setAberto(false)} />}
    </>
  );
}

function ManualFazendaModal({ onClose }: { onClose: () => void }) {
  const [manual, setManual] = useState<ManualFazenda | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aba, setAba] = useState<Aba>("rotina");
  const [exportando, setExportando] = useState(false);
  const [compartilhando, setCompartilhando] = useState(false);
  // "Compartilhar" só existe dentro do app (folha nativa do Android) — no
  // navegador é idêntico a "Exportar PDF" (mesmo <a download>).
  const [mostrarCompartilhar, setMostrarCompartilhar] = useState(false);
  useEffect(() => { ehApp().then(setMostrarCompartilhar); }, []);

  useEffect(() => { fetchManualFazenda().then(setManual).catch((e) => setError(e.message)); }, []);

  const exportarPDF = async () => {
    setExportando(true);
    try { await baixarPdfManualFazenda("baixar"); } catch (e: any) { setError(e.message); } finally { setExportando(false); }
  };

  const compartilharPDF = async () => {
    setCompartilhando(true);
    try { await baixarPdfManualFazenda("compartilhar"); } catch (e: any) { setError(e.message); } finally { setCompartilhando(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 95, padding: "1rem" }}>
      <div onClick={(e) => e.stopPropagation()} className="card" role="dialog" aria-modal="true"
        style={{ width: "760px", maxWidth: "95vw", maxHeight: "88vh", display: "flex", flexDirection: "column", padding: 0, overflow: "hidden" }}>

        <div style={{ background: "linear-gradient(135deg, var(--vinho, #0E2A47), var(--vinho-light, #416180))", padding: "1.1rem 1.4rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
          <div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>Manual da Fazenda</div>
            <div style={{ fontSize: "0.72rem", color: "rgba(240,200,120,0.8)" }}>
              {manual ? `Atualizado em ${new Date(manual.gerado_em).toLocaleString("pt-BR")}` : "Calculado a partir dos seus parâmetros e indicadores"}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={exportarPDF} disabled={exportando || !manual} title="Baixar PDF"
              style={{ display: "flex", alignItems: "center", gap: "0.35rem", background: "rgba(255,255,255,0.14)", border: "1px solid rgba(255,255,255,0.28)", color: "var(--dourado-light)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", fontSize: "0.78rem", fontWeight: 600, cursor: exportando ? "wait" : "pointer" }}>
              <Download size={14} /> {exportando ? "Gerando…" : "Exportar PDF"}
            </button>
            {mostrarCompartilhar && (
              <button onClick={compartilharPDF} disabled={compartilhando || !manual} title="Compartilhar PDF"
                style={{ display: "flex", alignItems: "center", gap: "0.35rem", background: "rgba(255,255,255,0.14)", border: "1px solid rgba(255,255,255,0.28)", color: "var(--dourado-light)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.7rem", fontSize: "0.78rem", fontWeight: 600, cursor: compartilhando ? "wait" : "pointer" }}>
                <Share2 size={14} /> {compartilhando ? "Abrindo…" : "Compartilhar"}
              </button>
            )}
            <button onClick={onClose} aria-label="Fechar" style={{ background: "none", border: "none", color: "var(--dourado-light)", cursor: "pointer", padding: "0.3rem" }}>
              <X size={18} />
            </button>
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.2rem", padding: "0.6rem 1.4rem 0", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
          {ABAS.map((a) => (
            <button key={a.id} onClick={() => setAba(a.id)}
              style={{ fontSize: "0.8rem", fontWeight: 600, padding: "0.55rem 0.8rem", background: "none", border: "none", cursor: "pointer",
                color: aba === a.id ? "var(--dourado-light)" : "var(--text-muted)",
                borderBottom: aba === a.id ? "2px solid var(--dourado)" : "2px solid transparent" }}>
              {a.label}
            </button>
          ))}
        </div>

        <div style={{ padding: "1.3rem 1.4rem", overflowY: "auto" }}>
          {error && <div className="alert-critico mb-3"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
          {!manual && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
          {manual && aba === "rotina" && <AbaRotina manual={manual} />}
          {manual && aba === "resultado" && <AbaResultado manual={manual} />}
          {manual && aba === "insights" && <AbaInsights manual={manual} />}
          {manual && aba === "sugestoes" && <AbaSugestoes manual={manual} />}
        </div>
      </div>
    </div>
  );
}

function ItemRotina({ titulo, descricao, datas }: { titulo: string; descricao: string; datas: string[] }) {
  return (
    <div style={{ display: "flex", gap: "0.9rem", padding: "0.9rem 0", borderBottom: "1px solid var(--border)" }}>
      <div style={{ width: "38px", height: "38px", borderRadius: "var(--r-sm)", background: "rgba(224,166,60,0.16)", color: "var(--dourado-light)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <Activity size={18} />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: "0.88rem", marginBottom: "0.15rem" }}>{titulo}</div>
        <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.45rem" }}>{descricao}</div>
        <div className="flex flex-wrap gap-2">
          {datas.map((d, i) => (
            <span key={d} style={{ fontSize: "0.74rem", fontWeight: i === 0 ? 700 : 400, borderRadius: "999px", padding: "0.25rem 0.6rem",
              background: i === 0 ? "rgba(224,166,60,0.18)" : "var(--surface-2)", border: `1px solid ${i === 0 ? "rgba(224,166,60,0.45)" : "var(--border)"}`,
              color: i === 0 ? "var(--dourado-light)" : "var(--text-muted)" }}>
              {fmtDia(d)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function AbaRotina({ manual }: { manual: ManualFazenda }) {
  const { rotina } = manual;
  const nada = !rotina.bst && !rotina.visita_reprodutiva && !rotina.sanitario.proxima && !rotina.compras.length;
  return (
    <div>
      {rotina.bst && <ItemRotina titulo={rotina.bst.titulo} descricao={rotina.bst.descricao} datas={rotina.bst.proximas_datas} />}
      {rotina.visita_reprodutiva && <ItemRotina titulo={rotina.visita_reprodutiva.titulo} descricao={rotina.visita_reprodutiva.descricao} datas={rotina.visita_reprodutiva.proximas_datas} />}
      {rotina.sanitario.proxima && (
        <div style={{ display: "flex", gap: "0.9rem", padding: "0.9rem 0", borderBottom: "1px solid var(--border)" }}>
          <div style={{ width: "38px", height: "38px", borderRadius: "var(--r-sm)", background: "rgba(224,166,60,0.16)", color: "var(--dourado-light)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Activity size={18} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: "0.88rem", marginBottom: "0.15rem" }}>Calendário sanitário preventivo</div>
            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Próxima: {rotina.sanitario.proxima.protocolo} — animal {rotina.sanitario.proxima.animal} em {fmtDia(rotina.sanitario.proxima.data)}
              {rotina.sanitario.vencidas > 0 && <span style={{ color: "var(--red)", fontWeight: 700 }}> — {rotina.sanitario.vencidas} vencida(s)</span>}
            </div>
          </div>
        </div>
      )}
      {!!rotina.compras.length && (
        <div style={{ display: "flex", gap: "0.9rem", padding: "0.9rem 0" }}>
          <div style={{ width: "38px", height: "38px", borderRadius: "var(--r-sm)", background: "rgba(224,166,60,0.16)", color: "var(--dourado-light)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <Activity size={18} />
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: "0.88rem", marginBottom: "0.3rem" }}>Compras recorrentes previstas</div>
            <div className="flex flex-wrap gap-2">
              {rotina.compras.map((c) => (
                <span key={c.nome} style={{ fontSize: "0.74rem", borderRadius: "999px", padding: "0.25rem 0.6rem", background: "var(--surface-2)", border: "1px solid var(--border)" }}>
                  {c.nome} ({c.quantidade}/{c.estoque_minimo})
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
      {nada && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma rotina automática configurada ainda — cadastre BST, manejo reprodutivo e calendário sanitário para o manual projetar as próximas datas.</p>}
    </div>
  );
}

function CardResultado({ valor, label }: { valor: string | number | null; label: string }) {
  return (
    <div style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.7rem 0.9rem" }}>
      <div style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--dourado-light)" }}>{valor ?? "—"}</div>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{label}</div>
    </div>
  );
}

function AbaResultado({ manual }: { manual: ManualFazenda }) {
  const r = manual.resultado;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <CardResultado valor={r.total_animais} label="Total de animais" />
      <CardResultado valor={r.vacas_lactacao} label="Vacas em lactação" />
      {/* "Fêmeas prenhas", não "Taxa de prenhez": é inventário (% do rebanho
          apto prenhe hoje), não a taxa formal PREG/PG ELIG do BREDSUM — mesmo
          rótulo da Capa e das outras telas que mostram taxa_prenhez_pct. */}
      <CardResultado valor={r.taxa_prenhez_pct != null ? `${r.taxa_prenhez_pct}%` : null} label="Fêmeas prenhas" />
      <CardResultado valor={r.taxa_concepcao_pct != null ? `${r.taxa_concepcao_pct}%` : null} label="Taxa de concepção" />
      <CardResultado valor={r.taxa_servico_pct != null ? `${r.taxa_servico_pct}%` : null} label="Taxa de serviço" />
      <CardResultado valor={r.producao_media_kg != null ? `${r.producao_media_kg} kg` : null} label="Produção média/vaca" />
      <CardResultado valor={r.producao_total_dia_kg != null ? `${r.producao_total_dia_kg} kg` : null} label="Produção total/dia" />
      <CardResultado valor={r.del_medio} label="DEL médio" />
    </div>
  );
}

function AbaInsights({ manual }: { manual: ManualFazenda }) {
  if (!manual.insights.length) {
    return <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Ainda sem histórico suficiente para gerar insights — volte em alguns meses.</p>;
  }
  return (
    <div>
      {manual.insights.map((ins, i) => (
        <div key={i} style={{ display: "flex", gap: "0.8rem", padding: "0.85rem 0", borderBottom: i < manual.insights.length - 1 ? "1px solid var(--border)" : "none" }}>
          <div style={{ width: "34px", height: "34px", borderRadius: "var(--r-sm)", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center",
            background: ins.tendencia === "alta" ? "rgba(74,122,78,0.16)" : "rgba(179,120,31,0.16)",
            color: ins.tendencia === "alta" ? "var(--green-light)" : "var(--amber)" }}>
            {ins.tendencia === "alta" ? <TrendingUp size={17} /> : <TrendingDown size={17} />}
          </div>
          <div>
            <div style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.03em", color: "var(--text-muted)" }}>{ins.categoria}</div>
            <div style={{ fontSize: "0.85rem" }}>{ins.texto}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function AbaSugestoes({ manual }: { manual: ManualFazenda }) {
  if (!manual.sugestoes.length) {
    return <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma sugestão no momento.</p>;
  }
  return (
    <div className="space-y-2">
      {manual.sugestoes.map((s, i) => (
        <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.6rem", background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.65rem 0.85rem" }}>
          <Sparkles size={15} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
          <div style={{ fontSize: "0.83rem" }}>
            {s.texto}
            {s.origem === "automatica" && <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginLeft: "0.4rem" }}>(automática)</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
