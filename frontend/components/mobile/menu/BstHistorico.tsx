"use client";
// Sub-tela Produção: BST — histórico de aplicações (só leitura), mais recente
// primeiro. As tabelas de aptas/incluir no próximo/inaptas já aparecem no
// cartão do dia na Agenda; aplicar, agendar ou marcar inapta continua em
// Lançar > Produção > BST.
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchRelatorioBst, formatDate, firstDayOfMonth, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, FiltroPeriodo } from "@/components/mobile/menu/comum";

type AplicacaoBst = {
  numero_matriz: string; data_aplicacao: string | null; produto: string; dose: number | null;
  unidade: string | null; responsavel: string | null; lote: string | null; categoria: string | null;
};

export default function BstHistorico({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<{ aplicacoes: AplicacaoBst[] }>("menu_producao_bst", fetchRelatorioBst);
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());

  const regs = dados?.aplicacoes || [];
  const filtrados = useMemo(
    () => regs.filter((r) => !r.data_aplicacao || (r.data_aplicacao >= inicio && r.data_aplicacao <= fim))
      .sort((a, b) => (a.data_aplicacao || "") < (b.data_aplicacao || "") ? 1 : -1),
    [regs, inicio, fim]
  );
  const vacasDistintas = useMemo(() => new Set(filtrados.map((r) => r.numero_matriz)).size, [filtrados]);

  return (
    <div>
      <MobVoltar titulo="BST — aplicações" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_producao_bst" mostrar={doCache} />

      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : filtrados.length === 0 ? (
        <Vazio>Nenhuma aplicação no período.</Vazio>
      ) : (
        <>
          <MobCard style={{ marginBottom: "0.8rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--mob-muted)", fontWeight: 700 }}>{filtrados.length} {filtrados.length !== 1 ? "aplicações" : "aplicação"}</span>
            <span style={{ fontSize: "0.85rem", color: "var(--mob-muted)", fontWeight: 700 }}>{vacasDistintas} vaca{vacasDistintas !== 1 ? "s" : ""}</span>
          </MobCard>
          {filtrados.map((r, i) => (
            <MobCard key={`${r.numero_matriz}-${r.data_aplicacao}-${i}`} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Nº {r.numero_matriz}</span>
                <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{r.data_aplicacao ? formatDate(r.data_aplicacao) : "—"}</span>
              </div>
              <div style={{ fontSize: "0.82rem", marginTop: "0.3rem" }}>
                {r.produto}{r.dose != null ? ` — ${r.dose} ${r.unidade || ""}` : ""}
              </div>
              <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                {r.lote ? `Lote ${r.lote}` : "—"}{r.responsavel ? ` · ${r.responsavel}` : ""}
              </div>
            </MobCard>
          ))}
        </>
      )}
    </div>
  );
}
