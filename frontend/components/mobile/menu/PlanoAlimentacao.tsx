"use client";
// Sub-tela: Plano de Alimentação por Lote (só leitura, gerencial).
// Mostra o plano já aberto: por lote, o efetivo e o consumo/dia de cada
// ingrediente (por cabeça e total do lote). Sem gráficos.
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchAlimentacao } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { TRATOS_PADRAO, dividirPorTrato } from "@/lib/tratos";

type Item = { ingrediente?: string | null; por_cabeca?: number | null; unidade?: string | null; efetivo?: number; consumo_dia?: number };
// `tratos_pct`: % de cada trato da dieta ativa do lote (cadastro por dieta);
// cópia antiga do cache, sem o campo, cai nos 2 tratos 50/50 de antes.
type Lote = { lote: number; categoria?: string | null; efetivo: number; itens: Item[]; tratos_pct?: number[] };
type Resposta = { por_lote: Lote[]; consumo_total: unknown[] };

function num(v?: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

export default function PlanoAlimentacao({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Resposta>("menu_plano_alimentacao", fetchAlimentacao);
  const lotes = dados?.por_lote || [];

  return (
    <div>
      <MobVoltar titulo="Plano por Lote" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_plano_alimentacao" mostrar={doCache} />
      <p style={{ fontSize: "0.75rem", color: "var(--mob-muted)", margin: "0 0 0.6rem" }}>
        <strong style={{ color: "var(--mob-verde)" }}>T1, T2…</strong> = quantidade de cada trato (fornecimento), pelo % cadastrado na dieta do lote.
      </p>

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : lotes.length === 0 ? (
        <Vazio>Nenhuma dieta aberta no momento.</Vazio>
      ) : (
        lotes.map((l) => (
          <MobCard key={l.lote} style={{ marginBottom: "0.7rem" }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.5rem" }}>
              <span style={{ fontWeight: 800, fontSize: "1.05rem" }}>
                Lote {l.lote}{l.categoria ? ` · ${l.categoria}` : ""}
              </span>
              <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", flexShrink: 0 }}>
                {l.efetivo} {l.efetivo === 1 ? "animal" : "animais"} · {(l.tratos_pct ?? TRATOS_PADRAO).length} tratos ({(l.tratos_pct ?? TRATOS_PADRAO).map((p) => `${num(p)}%`).join("/")})
              </span>
            </div>
            {l.itens.length === 0 ? (
              <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>Sem ingredientes lançados.</div>
            ) : (
              l.itens.map((it, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", padding: "0.45rem 0", borderTop: "1px solid var(--mob-border)" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.92rem", flex: 1, minWidth: 0 }}>{it.ingrediente || "—"}</span>
                  <span style={{ textAlign: "right", flexShrink: 0 }}>
                    <span style={{ display: "block", fontWeight: 800, fontSize: "1rem", color: "var(--mob-verde)" }}>
                      {dividirPorTrato(it.consumo_dia, l.tratos_pct ?? TRATOS_PADRAO).map((v, j) => `T${j + 1} ${num(v)}`).join(" · ")} {it.unidade || ""}
                    </span>
                    <span style={{ display: "block", fontWeight: 700, fontSize: "0.85rem", color: "var(--mob-ambar)" }}>
                      {num(it.consumo_dia)} {it.unidade || ""}/dia
                    </span>
                    <span style={{ display: "block", fontSize: "0.74rem", color: "var(--mob-muted)" }}>
                      {num(it.por_cabeca)} {it.unidade || ""}/cab
                    </span>
                  </span>
                </div>
              ))
            )}
          </MobCard>
        ))
      )}
    </div>
  );
}
