"use client";
// Sub-tela Produção: Últimos controles leiteiros (só leitura) — mesmo dado do
// site (Produção > Produção leiteira), filtrado por período, mais recente
// primeiro. Lançar um controle novo continua em Lançar > Produção > Controle leiteiro.
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchControles, formatDate, firstDayOfMonth, today } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, FiltroPeriodo } from "@/components/mobile/menu/comum";
import { useOrdenacao } from "@/components/Ordenavel";
import { SeletorOrdenacao, type CampoOrdenacao } from "@/components/mobile/SeletorOrdenacao";
import { casaBusca } from "@/lib/busca";

const CAMPOS_ORDENACAO: CampoOrdenacao[] = [
  { chave: "data", rotulo: "Data" },
  { chave: "numero", rotulo: "Animal" },
  { chave: "producao_kg", rotulo: "Produção (kg)" },
  { chave: "del", rotulo: "DEL" },
];

type ControleRow = {
  numero: string; data: string | null; producao_kg: number | null; del: number | null;
  ordenha1_kg: number | null; ordenha2_kg: number | null; ordenha3_kg: number | null; grupo_primario: string | null;
};

function num(v?: number | null, casas = 1): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}

export default function UltimosControles({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<{ controles: ControleRow[] }>("menu_producao_controles", fetchControles);
  const [inicio, setInicio] = useState(firstDayOfMonth());
  const [fim, setFim] = useState(today());
  const [busca, setBusca] = useState("");

  const regs = dados?.controles || [];
  const filtrados = useMemo(() => {
    return regs
      .filter((r) => !r.data || (r.data >= inicio && r.data <= fim))
      .filter((r) => casaBusca(r.numero, busca))
      .sort((a, b) => (a.data || "") < (b.data || "") ? 1 : -1);
  }, [regs, inicio, fim, busca]);
  // useOrdenacao assume o controle só depois que o usuário escolhe um campo em
  // SeletorOrdenacao; até lá, `filtrados` já vem em ordem (data desc).
  const ord = useOrdenacao(filtrados);

  return (
    <div>
      <MobVoltar titulo="Últimos controles leiteiros" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_producao_controles" mostrar={doCache} />

      <FiltroPeriodo inicio={inicio} fim={fim} onInicio={setInicio} onFim={setFim} />
      <input className="mob-input" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por nº do animal…" style={{ marginBottom: "0.8rem" }} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : filtrados.length === 0 ? (
        <Vazio>Nenhum controle no período/filtro.</Vazio>
      ) : (
        <>
          <SeletorOrdenacao campos={CAMPOS_ORDENACAO} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.6rem" }}>{filtrados.length} controle{filtrados.length !== 1 ? "s" : ""}</p>
          {ord.linhasOrdenadas.map((r, i) => {
            const ordenhas = [r.ordenha1_kg, r.ordenha2_kg, r.ordenha3_kg].filter((v) => v != null);
            return (
              <MobCard key={`${r.numero}-${r.data}-${i}`} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Nº {r.numero}</span>
                  <strong style={{ color: "var(--mob-verde)", fontSize: "0.95rem" }}>{num(r.producao_kg)} kg</strong>
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.25rem", display: "flex", justifyContent: "space-between" }}>
                  <span>{r.data ? formatDate(r.data) : "—"}{r.grupo_primario ? ` · Lote ${r.grupo_primario}` : ""}</span>
                  <span>DEL {r.del ?? "—"}</span>
                </div>
                {ordenhas.length > 1 && (
                  <div style={{ fontSize: "0.74rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                    Ordenhas: {[r.ordenha1_kg, r.ordenha2_kg, r.ordenha3_kg].map((v) => num(v)).join(" + ")}
                  </div>
                )}
              </MobCard>
            );
          })}
        </>
      )}
    </div>
  );
}
