"use client";
// Tela REBANHO › aba "Lotes": duas sub-abas — Composição (animais de cada
// lote, como "Fêmeas por Grupo" no site) e Indicadores (métricas agregadas
// por lote, calculadas aqui mesmo a partir da mesma lista de animais — não
// existe endpoint dedicado no backend para isso).
import { useEffect, useMemo, useState } from "react";
import { Rows3, Gauge } from "lucide-react";
import { fetchAnimais } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { MobCard, MobVoltar } from "@/components/mobile/ui";
import { GradeAcoes } from "@/components/mobile/lancar/comum";

type AnimalLote = {
  numero: string;
  nome?: string | null;
  grupo_primario?: string | null;
  categoria_abrev?: string | null;
  categoria_completa?: string | null;
  raca?: string | null;
  sit_rep?: string | null;
  del_dias?: number | null;
  ult_cl_kg?: number | null;
};

// Cor por situação reprodutiva (sit_rep) — valores reais vindos do backend.
const SIT_COR: Record<string, string> = {
  "Ges.": "var(--mob-azul)",
  "Ins.": "var(--mob-dourado)",
  "Vaz. pev": "var(--mob-amarelo)",
  "Vaz. apt.": "var(--mob-verde)",
  "Vaz. atr.": "var(--mob-vinho)",
};

// Cor do "quadro" de cada lote, pelo tipo indicado no nome do grupo.
function corLote(lote: string): string {
  const t = lote.toLowerCase();
  if (t.includes("novilh")) return "var(--mob-verde)";
  if (t.includes("seca")) return "var(--mob-laranja)";
  if (t.includes("pré-parto") || t.includes("pre-parto")) return "var(--mob-roxo)";
  if (t.includes("bezerr")) return "var(--mob-azul)";
  return "var(--mob-vinho)";
}

function useAnimaisPorLote() {
  const [animais, setAnimais] = useState<AnimalLote[]>([]);
  const [carregando, setCarregando] = useState(true);
  useEffect(() => {
    let vivo = true;
    fetchComCache<AnimalLote[]>("animais", () => fetchAnimais()).then(({ dados }) => {
      if (vivo) { setAnimais(dados || []); setCarregando(false); }
    });
    return () => { vivo = false; };
  }, []);

  const porLote = useMemo(() => {
    const mapa = new Map<string, AnimalLote[]>();
    animais.forEach((a) => {
      const chave = a.grupo_primario || "(sem lote)";
      if (!mapa.has(chave)) mapa.set(chave, []);
      mapa.get(chave)!.push(a);
    });
    return Array.from(mapa.entries()).sort((a, b) => a[0].localeCompare(b[0], "pt-BR"));
  }, [animais]);

  return { porLote, carregando, total: animais.length };
}

function Composicao() {
  const { porLote, carregando, total } = useAnimaisPorLote();
  if (carregando) return <p style={{ color: "var(--mob-muted)" }}>Carregando…</p>;
  if (!total) return <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal encontrado.</p>;

  return (
    <div>
      {porLote.map(([lote, lista]) => (
        <details key={lote} style={{ marginBottom: "0.7rem" }}>
          <summary className="mob-tint" style={{ ["--tint-cor" as any]: corLote(lote), cursor: "pointer", fontWeight: 700, fontSize: "0.95rem", padding: "0.85rem 1rem", border: "1px solid var(--mob-border)", borderRadius: 14, listStyle: "none", display: "flex", justifyContent: "space-between", alignItems: "center", boxShadow: "var(--mob-sombra)" }}>
            <span>{lote}</span>
            <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", fontWeight: 700 }}>{lista.length} animal{lista.length !== 1 ? "is" : ""}</span>
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
            {lista.map((a) => (
              <MobCard key={a.numero} className="mob-tint" style={{ ["--tint-cor" as any]: SIT_COR[a.sit_rep || ""] || "var(--mob-muted)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontWeight: 800 }}>{a.numero}{a.nome ? ` · ${a.nome}` : ""}</span>
                  <span style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>{a.categoria_abrev || a.categoria_completa || "—"}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem 0.9rem", marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--mob-muted)" }}>
                  <span>Raça: {a.raca || "—"}</span>
                  <span style={{ color: SIT_COR[a.sit_rep || ""] || "var(--mob-muted)", fontWeight: 600 }}>{a.sit_rep || "Sit. Rep. —"}</span>
                  <span>DEL: {a.del_dias ?? "—"}</span>
                  <span>Últ. CL: {a.ult_cl_kg != null ? `${a.ult_cl_kg.toFixed(1)} kg` : "—"}</span>
                </div>
              </MobCard>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

function Indicadores() {
  const { porLote, carregando, total } = useAnimaisPorLote();
  if (carregando) return <p style={{ color: "var(--mob-muted)" }}>Carregando…</p>;
  if (!total) return <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal encontrado.</p>;

  return (
    <div>
      {porLote.map(([lote, lista]) => {
        const comDel = lista.filter((a) => a.del_dias != null);
        const delMedio = comDel.length ? Math.round(comDel.reduce((s, a) => s + (a.del_dias || 0), 0) / comDel.length) : null;
        const comCl = lista.filter((a) => a.ult_cl_kg != null);
        const clMedio = comCl.length ? comCl.reduce((s, a) => s + (a.ult_cl_kg || 0), 0) / comCl.length : null;
        const porSit = new Map<string, number>();
        lista.forEach((a) => {
          const sit = a.sit_rep || "Sem situação";
          porSit.set(sit, (porSit.get(sit) || 0) + 1);
        });

        return (
          <MobCard key={lote} className="mob-tint" style={{ ["--tint-cor" as any]: corLote(lote), marginBottom: "0.7rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.6rem" }}>
              <span style={{ fontWeight: 800, fontSize: "1rem" }}>{lote}</span>
              <span style={{ fontSize: "0.8rem", color: "var(--mob-muted)", fontWeight: 700 }}>{lista.length} animal{lista.length !== 1 ? "is" : ""}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem 1rem", marginBottom: "0.6rem" }}>
              <div>
                <span style={{ fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 }}>DEL médio</span>
                <div style={{ fontSize: "0.95rem", fontWeight: 700 }}>{delMedio != null ? `${delMedio} dias` : "—"}</div>
              </div>
              <div>
                <span style={{ fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 }}>Últ. CL médio</span>
                <div style={{ fontSize: "0.95rem", fontWeight: 700 }}>{clMedio != null ? `${clMedio.toFixed(1)} kg` : "—"}</div>
              </div>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
              {Array.from(porSit.entries()).map(([sit, n]) => (
                <span key={sit} style={{
                  fontSize: "0.75rem", fontWeight: 700, padding: "0.25rem 0.6rem", borderRadius: 999,
                  color: SIT_COR[sit] || "var(--mob-muted)",
                  background: `color-mix(in srgb, ${SIT_COR[sit] || "var(--mob-muted)"} 14%, transparent)`,
                }}>
                  {sit}: {n}
                </span>
              ))}
            </div>
          </MobCard>
        );
      })}
    </div>
  );
}

type Sub = "composicao" | "indicadores";
const TITULOS: Record<Sub, string> = { composicao: "Composição", indicadores: "Indicadores" };

export default function Lotes() {
  const [sub, setSub] = useState<Sub | null>(null);

  if (!sub) {
    return (
      <GradeAcoes
        opcoes={[
          { id: "composicao", label: "Composição", icone: <Rows3 size={28} />, cor: "var(--mob-verde)" },
          { id: "indicadores", label: "Indicadores", icone: <Gauge size={28} />, cor: "var(--mob-laranja)" },
        ]}
        onEscolher={(id) => setSub(id as Sub)}
      />
    );
  }

  return (
    <div>
      <MobVoltar titulo={TITULOS[sub]} onVoltar={() => setSub(null)} />
      {sub === "composicao" && <Composicao />}
      {sub === "indicadores" && <Indicadores />}
    </div>
  );
}
