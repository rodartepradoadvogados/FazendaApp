"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, CircleAlert } from "lucide-react";
import { formatBRL } from "@/lib/api";
import type { Excecao } from "@/lib/folhaCompetencia";

/*
 * "Resolver antes de fechar" — o painel de exceções do mês.
 *
 * POR QUE ELE EXISTE. O que estava errado na folha só aparecia como cor: a
 * folha estourada era um número vermelho no meio da tabela, o vencido era um
 * fundo vinho, e o recibo que não fecha com o valor pago não aparecia em lugar
 * nenhum. Nada disso subia ao topo, nada dizia o que fazer, e o mais grave dos
 * três era invisível. Aqui cada exceção é uma linha com gravidade, frase de
 * uma linha e a ação que a resolve.
 *
 * O QUE ESTE PAINEL DELIBERADAMENTE NÃO TEM. O desenho aprovado trazia três
 * cartões, e dois deles descreviam bugs JÁ CORRIGIDOS no backend — folha
 * recorrente nascendo sem INSS/IR (hoje consertada a cada listagem por
 * `_corrigir_folha_gerada_sem_retencao`) e retenção sem percentual sumindo da
 * discriminação (hoje `_detalhe_folha` testa o VALOR, não o percentual).
 * Construí-los mostraria ao dono um problema que ele não tem, e o custo disso
 * não é estético: é ensinar a ignorar o painel — e o painel só serve enquanto
 * cada linha dele for verdade. Quais exceções sobraram, e por quê, está em
 * `excecoesDoMes` (lib/folhaCompetencia.ts), com a linha de código que
 * sustenta cada uma.
 */

// Tokens de situação (--st-*): texto legível nas 3 paletas e nos 3 temas;
// a linha (filete/borda) usa o tom -line, o texto o tom -fg.
const CORES: Record<Excecao["gravidade"], { cor: string; linha: string; classe: string; titulo: string }> = {
  bloqueia: { cor: "var(--st-venc-fg)", linha: "var(--st-venc-line)", classe: "venc", titulo: "Impede o fechamento" },
  conferir: { cor: "var(--st-logo-fg)", linha: "var(--st-logo-line)", classe: "logo", titulo: "Confira antes de pagar" },
};

export function ExcecoesFolha({ excecoes, onResolver }: {
  excecoes: Excecao[];
  /** Leva o usuário até o lançamento — a tela abre a linha e rola até ela. */
  onResolver: (excecao: Excecao) => void;
}) {
  // Monta fechado e abre no quadro seguinte, para o CSS ter um estado inicial
  // real de onde animar (mesma técnica do cartão de origem do holerite).
  // Reaproveita `.linha-colapsavel`, que já cresce a partir da linha-mãe e
  // recolhe o espaço em vez de deixar buraco quando a exceção some.
  const [montado, setMontado] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => requestAnimationFrame(() => setMontado(true)));
    return () => cancelAnimationFrame(id);
  }, []);

  if (!excecoes.length) {
    return (
      <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
        Nenhuma pendência de conferência neste mês.
      </p>
    );
  }

  const bloqueios = excecoes.filter((e) => e.gravidade === "bloqueia").length;

  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2" style={{ flexWrap: "wrap" }}>
        <span style={{
          fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.06em",
          textTransform: "uppercase", color: "var(--text-muted)",
        }}>
          Resolver antes de fechar
        </span>
        <span className={`st-pill ${bloqueios ? "venc" : "logo"}`}>
          {bloqueios ? <CircleAlert size={12} aria-hidden /> : <AlertTriangle size={12} aria-hidden />}
          {excecoes.length}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {excecoes.map((e) => {
          const { cor, linha, classe, titulo } = CORES[e.gravidade];
          const Icone = e.gravidade === "bloqueia" ? CircleAlert : AlertTriangle;
          return (
            <div
              key={e.id}
              className={`linha-colapsavel${montado ? "" : " linha-entrando"}`}
            >
              <div>
                <div
                  className="flex items-start gap-3"
                  style={{
                    background: "var(--surface)", border: "1px solid var(--border)",
                    borderLeft: `3px solid ${linha}`, borderRadius: "var(--r-sm)",
                    padding: "0.7rem 0.85rem", flexWrap: "wrap",
                  }}
                >
                  <Icone size={16} aria-hidden style={{ color: cor, flexShrink: 0, marginTop: "0.1rem" }} />
                  <div style={{ flexGrow: 1, minWidth: "min(16rem, 100%)" }}>
                    <div className="flex items-baseline gap-2" style={{ flexWrap: "wrap" }}>
                      <span style={{ fontSize: "0.84rem", fontWeight: 600 }}>{e.titulo}</span>
                      <span className={`st-pill ${classe}`}>
                        <Icone size={12} aria-hidden />{titulo}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem", lineHeight: 1.45 }}>
                      {e.frase}
                    </div>
                  </div>
                  <div className="flex items-center gap-3" style={{ flexShrink: 0 }}>
                    <span style={{ fontSize: "0.86rem", fontWeight: 700, fontVariantNumeric: "tabular-nums", color: cor }}>
                      {formatBRL(e.valor)}
                    </span>
                    <button
                      type="button" className="btn-ghost"
                      title="Abrir o lançamento envolvido, com a discriminação à vista"
                      style={{ fontSize: "0.75rem", borderColor: linha, color: cor, whiteSpace: "nowrap", minHeight: 36 }}
                      onClick={() => onResolver(e)}
                    >
                      {e.acao}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
