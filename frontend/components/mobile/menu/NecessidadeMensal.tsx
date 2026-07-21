"use client";
// Sub-tela: Necessidade Mensal de Alimentação (só leitura, gerencial).
// Mesma projeção do site (Lançamentos > Alimentação > Necessidade mensal):
// consumo diário × 30 dias, convertido em sacos quando o item de estoque
// vinculado é ensacado. Silagem é sempre a granel na fazenda (volumoso
// picado/armazenado, nunca ensacado) — por isso nunca mostra sacos aqui,
// mesmo que o vínculo de estoque esteja marcado como ensacado por engano.
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchNecessidadeMensal } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

type Item = {
  ingrediente: string;
  unidade?: string | null;
  necessidade_mes?: number | null;
  ensacado?: boolean;
  kg_por_saco?: number | null;
  sacos_mes?: number | null;
};
type Resposta = { itens: Item[] };

const EH_SILAGEM = (nome: string) => /silagem/i.test(nome);

function num(v?: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
}

export default function NecessidadeMensal({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Resposta>("menu_necessidade_mensal", fetchNecessidadeMensal);
  const itens = dados?.itens || [];

  return (
    <div>
      <MobVoltar titulo="Necessidade Mensal" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_necessidade_mensal" mostrar={doCache} />
      <p style={{ fontSize: "0.75rem", color: "var(--mob-muted)", margin: "0 0 0.6rem" }}>
        Projeção simples: consumo diário × 30 dias. Silagem não converte em sacas (sempre a granel).
      </p>

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : itens.length === 0 ? (
        <Vazio>Sem dieta carregada.</Vazio>
      ) : (
        itens.map((i) => {
          const silagem = EH_SILAGEM(i.ingrediente);
          const mostrarSacos = i.ensacado && !silagem;
          return (
            <MobCard key={i.ingrediente} style={{ marginBottom: "0.7rem" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem" }}>
                <span style={{ fontWeight: 700, fontSize: "0.92rem", flex: 1, minWidth: 0 }}>{i.ingrediente}</span>
                <span style={{ textAlign: "right", flexShrink: 0 }}>
                  <span style={{ display: "block", fontWeight: 800, fontSize: "1rem", color: "var(--mob-verde)" }}>
                    {num(i.necessidade_mes)} {i.unidade || ""}
                  </span>
                  {mostrarSacos && (
                    <span style={{ display: "block", fontSize: "0.8rem", color: "var(--mob-ambar)" }}>
                      {num(i.sacos_mes)} {i.sacos_mes === 1 ? "saca" : "sacas"}
                    </span>
                  )}
                </span>
              </div>
            </MobCard>
          );
        })
      )}
    </div>
  );
}
