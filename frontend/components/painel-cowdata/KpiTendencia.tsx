"use client";
// Sparkline + seta de tendência dos cartões de KPI do Cockpit (Painel
// CowData) — ver app/painel-cowdata/page.tsx e lib/painelCowDataHistorico.ts
// (fonte dos dados e a limitação de histórico documentada lá).
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { TendenciaKpi } from "@/lib/painelCowDataHistorico";
import type { CoresPainelCowData } from "@/lib/painelCowDataTema";

/** Mini-gráfico de linha (SVG) com a evolução recente de um KPI — sem eixo,
 * só a forma da curva. Com menos de 2 pontos mostra uma linha reta neutra
 * (nada para desenhar ainda). */
export function Sparkline({ valores, cor, largura = 76, altura = 26 }: { valores: number[]; cor: string; largura?: number; altura?: number }) {
  if (valores.length < 2) {
    return (
      <svg width={largura} height={altura} viewBox={`0 0 ${largura} ${altura}`} aria-hidden="true">
        <line x1={2} y1={altura / 2} x2={largura - 2} y2={altura / 2} stroke={cor} strokeOpacity={0.35} strokeWidth={1.5} strokeDasharray="2 3" />
      </svg>
    );
  }
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const amplitude = max - min || 1;
  const passo = (largura - 4) / (valores.length - 1);
  const pontos = valores.map((v, i) => {
    const x = 2 + i * passo;
    const y = altura - 2 - ((v - min) / amplitude) * (altura - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const ultimo = pontos[pontos.length - 1].split(",");
  return (
    <svg width={largura} height={altura} viewBox={`0 0 ${largura} ${altura}`} aria-hidden="true">
      <polyline points={pontos.join(" ")} fill="none" stroke={cor} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={ultimo[0]} cy={ultimo[1]} r={1.8} fill={cor} />
    </svg>
  );
}

/** Seta + variação, comparando com a leitura anterior (ver calcularTendencia).
 * `favoravelSeSobe=false` inverte as cores (ex.: "Aguardando aprovação" — um
 * número maior é uma fila crescendo, não uma boa notícia). */
export function SetaTendencia({ tendencia, favoravelSeSobe = true, cor, sufixo = "" }: {
  tendencia: TendenciaKpi; favoravelSeSobe?: boolean; cor: CoresPainelCowData; sufixo?: string;
}) {
  if (tendencia.direcao === "sem_dado") {
    return <span style={{ fontSize: "0.68rem", color: cor.mudo }}>coletando histórico…</span>;
  }
  const boa = tendencia.direcao === "estavel" ? null : (tendencia.direcao === "alta") === favoravelSeSobe;
  const tom = boa === null ? cor.mudo : boa ? cor.verde : cor.vermelho;
  const Icone = tendencia.direcao === "alta" ? ArrowUpRight : tendencia.direcao === "baixa" ? ArrowDownRight : Minus;
  const deltaAbs = Math.abs(tendencia.delta);
  const deltaTxt = Number.isInteger(deltaAbs) ? String(deltaAbs) : deltaAbs.toFixed(2);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.15rem", fontSize: "0.7rem", fontWeight: 700, color: tom }}>
      <Icone size={12} />
      {tendencia.direcao === "estavel" ? "estável" : `${deltaTxt}${sufixo}`}
      {tendencia.percentual != null && ` (${tendencia.percentual > 0 ? "+" : ""}${tendencia.percentual.toFixed(0)}%)`}
      <span style={{ color: cor.mudo, fontWeight: 400 }}>vs. última leitura</span>
    </span>
  );
}
