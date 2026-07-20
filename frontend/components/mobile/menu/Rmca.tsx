"use client";
// Sub-tela Financeiro: RMCA (Receita Menos Custo com Alimentação) — igual ao
// site (financeiro/page.tsx, RmcaView): endpoint dedicado, único filtro é o
// período (competência). Mostra gerencial e físico empilhados (no site ficam
// lado a lado; no celular a tela é estreita demais para isso).
import { useEffect, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchRmca, firstDayOfMonth, today } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { FiltroPeriodo, AvisoCopia, Carregando, Vazio, brl } from "@/components/mobile/menu/comum";

type RmcaResp = {
  configurado: boolean;
  contas_receita: string[];
  contas_custo: string[];
  gerencial: { receita_leite: number; custo_alimentacao: number; rmca: number };
  fisico: { receita_leite: number; custo_alimentacao: number; rmca: number };
};

function BlocoRmca({ titulo, v }: { titulo: string; v: { receita_leite: number; custo_alimentacao: number; rmca: number } }) {
  return (
    <MobCard style={{ marginBottom: "0.7rem" }}>
      <div style={{ fontWeight: 800, marginBottom: "0.6rem" }}>{titulo}</div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.88rem", marginBottom: "0.3rem" }}>
        <span style={{ color: "var(--mob-muted)" }}>Receita do leite</span>
        <strong style={{ color: "var(--mob-verde)" }}>{brl(v.receita_leite)}</strong>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.88rem", marginBottom: "0.3rem" }}>
        <span style={{ color: "var(--mob-muted)" }}>Custo de alimentação</span>
        <strong style={{ color: "var(--mob-vermelho)" }}>{brl(v.custo_alimentacao)}</strong>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.95rem", borderTop: "1px solid var(--mob-border)", paddingTop: "0.4rem", marginTop: "0.3rem" }}>
        <span style={{ fontWeight: 700 }}>RMCA</span>
        <strong style={{ color: v.rmca >= 0 ? "var(--mob-verde)" : "var(--mob-vermelho)" }}>{brl(v.rmca)}</strong>
      </div>
    </MobCard>
  );
}

export default function Rmca({ onVoltar }: { onVoltar: () => void }) {
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());
  const [dados, setDados] = useState<RmcaResp | null>(null);
  const [doCache, setDoCache] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState(false);

  // Cada período (início/fim) tem sua própria cópia local — igual à visão de
  // calendário da Agenda: sem internet, mostra o último cálculo já visto para
  // esse mesmo período; períodos nunca abertos antes ficam sem dado offline.
  useEffect(() => {
    let vivo = true;
    setCarregando(true);
    const chave = `menu_rmca_${inicio}_${fim}`;
    fetchComCache<RmcaResp>(chave, () => fetchRmca(inicio, fim)).then((r) => {
      if (!vivo) return;
      setDados(r.dados);
      setDoCache(r.doCache);
      setErro(r.doCache && typeof navigator !== "undefined" && navigator.onLine);
      setCarregando(false);
    });
    return () => { vivo = false; };
  }, [inicio, fim]);

  return (
    <div>
      <MobVoltar titulo="RMCA" onVoltar={onVoltar} />
      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />
      <AvisoCopia chave={`menu_rmca_${inicio}_${fim}`} mostrar={doCache} />

      {carregando && !dados ? (
        <Carregando />
      ) : erro && !dados ? (
        <Vazio>Sem internet para calcular o RMCA agora.</Vazio>
      ) : !dados ? (
        <Vazio>Sem dados salvos para este período. Conecte-se uma vez para baixar.</Vazio>
      ) : !dados.configurado ? (
        <Vazio>Configure as contas gerenciais de RMCA no site (Configurações › Parâmetros financeiros) para ver este relatório.</Vazio>
      ) : (
        <>
          <BlocoRmca titulo="RMCA gerencial" v={dados.gerencial} />
          <BlocoRmca titulo="RMCA físico" v={dados.fisico} />
          <p style={{ fontSize: "0.75rem", color: "var(--mob-muted)" }}>
            Contas de receita: {dados.contas_receita.join(", ") || "—"}<br />
            Contas de custo: {dados.contas_custo.join(", ") || "—"}
          </p>
        </>
      )}
    </div>
  );
}
