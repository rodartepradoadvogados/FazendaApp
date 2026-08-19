"use client";
// Tela REBANHO › aba "Lotes": duas sub-abas — Composição (animais de cada
// lote, como "Fêmeas por Grupo" no site) e Indicadores (métricas agregadas
// por lote, calculadas aqui mesmo a partir da mesma lista de animais — não
// existe endpoint dedicado no backend para isso).
import { useEffect, useMemo, useState } from "react";
import { PieChart, Gauge } from "lucide-react";
import { fetchAnimais, type AnimalProducaoAoVivo } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { MobCard, MobVoltar } from "@/components/mobile/ui";
import { GradeAcoes } from "@/components/mobile/lancar/comum";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { producaoDe, origemDe } from "@/lib/producaoAnimal";

// `ult_cl_kg` é o campo congelado do CSV do Ideagri (parser aposentado);
// `producao_kg`/`producao_origem` vêm ao vivo de fetchAnimais(). Partial
// porque o backend desta etapa pode ainda não mandar os campos novos.
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
} & Partial<AnimalProducaoAoVivo>;


// Cor por situação reprodutiva ao vivo (rótulos de ROTULO_ESTADO).
const SIT_COR: Record<string, string> = {
  "Ges.": "var(--mob-azul)",
  "Ins.": "var(--mob-dourado)",
  "Vaz. pev": "var(--mob-amarelo)",
  "Vaz. apt.": "var(--mob-verde)",
  "Vaz. atr.": "var(--mob-vinho)",
  Gestante: "var(--mob-azul)", Inseminada: "var(--mob-dourado)", "Em protocolo (IA atual)": "var(--mob-dourado)",
  PEV: "var(--mob-amarelo)", Apta: "var(--mob-verde)", Atrasada: "var(--mob-vinho)", "Não apta": "var(--mob-muted)", Vazia: "var(--mob-verde)",
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
  const { rotuloDe } = useEstadosReprodutivos();
  if (carregando) return <p style={{ color: "var(--mob-muted)" }}>Carregando…</p>;
  if (!total) return <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal encontrado.</p>;
  const algumCongelado = porLote.some(([, lista]) => lista.some((a) => producaoDe(a) != null && origemDe(a) === "congelado"));

  return (
    <div>
      {porLote.map(([lote, lista]) => (
        <details key={lote} style={{ marginBottom: "0.7rem" }}>
          <summary className="mob-tint" style={{ ["--tint-cor" as any]: corLote(lote), cursor: "pointer", fontWeight: 700, fontSize: "0.95rem", padding: "0.85rem 1rem", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", listStyle: "none", display: "flex", justifyContent: "space-between", alignItems: "center", boxShadow: "var(--mob-sombra)" }}>
            <span>{lote}</span>
            <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", fontWeight: 700 }}>{lista.length} animal(is)</span>
          </summary>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
            {lista.map((a) => (
              <MobCard key={a.numero} className="mob-tint" style={{ ["--tint-cor" as any]: SIT_COR[rotuloDe(a.numero)] || "var(--mob-muted)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontWeight: 800 }}>{a.numero}{a.nome ? ` · ${a.nome}` : ""}</span>
                  <span style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>{a.categoria_abrev || a.categoria_completa || "—"}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem 0.9rem", marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--mob-muted)" }}>
                  <span>Raça: {a.raca || "—"}</span>
                  <span style={{ color: SIT_COR[rotuloDe(a.numero)] || "var(--mob-muted)", fontWeight: 600 }}>{rotuloDe(a.numero) !== "—" ? rotuloDe(a.numero) : "Sit. Rep. —"}</span>
                  <span>DEL: {a.del_dias ?? "—"}</span>
                  <span>
                    Últ. CL: {producaoDe(a) != null ? `${producaoDe(a)!.toFixed(1)} kg` : "—"}
                    {origemDe(a) === "congelado" && <span> *</span>}
                  </span>
                </div>
              </MobCard>
            ))}
          </div>
        </details>
      ))}
      {algumCongelado && (
        <p style={{ fontSize: "0.72rem", color: "var(--mob-muted)", marginTop: "0.3rem" }}>
          * sem controle leiteiro lançado no app ainda — valor parado da última importação.
        </p>
      )}
    </div>
  );
}

function Indicadores() {
  const { porLote, carregando, total } = useAnimaisPorLote();
  const { rotuloDe } = useEstadosReprodutivos();
  if (carregando) return <p style={{ color: "var(--mob-muted)" }}>Carregando…</p>;
  if (!total) return <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal encontrado.</p>;

  return (
    <div>
      {porLote.map(([lote, lista]) => {
        const comDel = lista.filter((a) => a.del_dias != null);
        const delMedio = comDel.length ? Math.round(comDel.reduce((s, a) => s + (a.del_dias || 0), 0) / comDel.length) : null;
        const comCl = lista.filter((a) => producaoDe(a) != null);
        const clMedio = comCl.length ? comCl.reduce((s, a) => s + (producaoDe(a) || 0), 0) / comCl.length : null;
        // Se algum animal do lote entrou com valor congelado, a média mistura
        // dado ao vivo com dado parado — o lote precisa avisar isso, senão dá
        // pra comparar dois lotes achando que os números são igualmente recentes.
        const clTemCongelado = comCl.some((a) => origemDe(a) === "congelado");
        const porSit = new Map<string, number>();
        lista.forEach((a) => {
          const sit = rotuloDe(a.numero) !== "—" ? rotuloDe(a.numero) : "Sem situação";
          porSit.set(sit, (porSit.get(sit) || 0) + 1);
        });

        return (
          <MobCard key={lote} className="mob-tint" style={{ ["--tint-cor" as any]: corLote(lote), marginBottom: "0.7rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "0.6rem" }}>
              <span style={{ fontWeight: 800, fontSize: "1rem" }}>{lote}</span>
              <span style={{ fontSize: "0.8rem", color: "var(--mob-muted)", fontWeight: 700 }}>{lista.length} animal(is)</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem 1rem", marginBottom: "0.6rem" }}>
              <div>
                <span style={{ fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 }}>DEL médio</span>
                <div style={{ fontSize: "0.95rem", fontWeight: 700 }}>{delMedio != null ? `${delMedio} dias` : "—"}</div>
              </div>
              <div>
                <span style={{ fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 }}>Últ. CL médio</span>
                <div style={{ fontSize: "0.95rem", fontWeight: 700 }}>
                  {clMedio != null ? `${clMedio.toFixed(1)} kg` : "—"}
                  {clTemCongelado && <span style={{ fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 }}> * mistura dado parado</span>}
                </div>
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
          { id: "composicao", label: "Composição", icone: <PieChart size={28} />, cor: "var(--mob-verde)" },
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
