"use client";
// Grade de seleção de seção da Ficha do Animal — substitui o scroll único
// (Identificação → Curva → Colostro → GTAs → Compra/Venda/Baixa → 16
// acordeões) por uma navegação em 6 cartões, inspirada no Ideagri mas na
// identidade visual do CowData: cabeçalho marinho (nunca verde — isso fica
// no MobVoltar do chamador), cantos retos, e cada botão na cor --cat-* já
// fixa por módulo em todo o produto (mesmos tokens do Menu/Lançar — ver
// components/mobile/ui.tsx). Resumo e Dados Gerais não são "módulos" de
// verdade — usam --cat-gestao, o mesmo tom neutro/institucional que
// Relatórios de Manejo já usa, para não competir por cor de módulo.
// Movimentações também não é um módulo — usa --mob-dourado-2, o mesmo
// tratamento que "Protocolos"/"Portal" já recebem no Menu (app/app/menu/page.tsx).
import type { ComponentType } from "react";
import { ClipboardList, Info, Heart, Milk, ShieldPlus, Truck } from "lucide-react";

export type SecaoChave = "resumo" | "dados_gerais" | "reproducao" | "producao" | "sanidade" | "movimentacoes";

export const TITULO_SECAO: Record<SecaoChave, string> = {
  resumo: "Resumo",
  dados_gerais: "Dados Gerais",
  reproducao: "Reprodução",
  producao: "Produção",
  sanidade: "Sanidade",
  movimentacoes: "Movimentações",
};

const ITENS: { chave: SecaoChave; subtitulo: string; icone: ComponentType<{ size?: number }>; cor: string }[] = [
  { chave: "resumo", subtitulo: "Situação atual + histórico por parto", icone: ClipboardList, cor: "var(--cat-gestao)" },
  { chave: "dados_gerais", subtitulo: "Identificação, origem, genealogia", icone: Info, cor: "var(--cat-gestao)" },
  { chave: "reproducao", subtitulo: "Serviços, IATF, partos, gestação", icone: Heart, cor: "var(--cat-reproducao)" },
  { chave: "producao", subtitulo: "Curva, Equiv. Maduro, controles", icone: Milk, cor: "var(--cat-producao)" },
  { chave: "sanidade", subtitulo: "Colostro, rastreabilidade, aplicações", icone: ShieldPlus, cor: "var(--cat-sanidade)" },
  { chave: "movimentacoes", subtitulo: "GTA, compra, venda, lotes", icone: Truck, cor: "var(--mob-dourado-2)" },
];

export function SeletorSecaoFicha({ onEscolher }: { onEscolher: (chave: SecaoChave) => void }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
      {ITENS.map((item) => {
        const Icone = item.icone;
        return (
          <button
            key={item.chave}
            type="button"
            onClick={() => onEscolher(item.chave)}
            style={{
              display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "0.55rem",
              padding: "1rem 0.9rem", border: "1px solid var(--mob-border)", borderLeft: `4px solid ${item.cor}`,
              background: "var(--mob-surface)", boxShadow: "var(--mob-sombra)", borderRadius: "var(--r-app)",
              textAlign: "left", cursor: "pointer", color: "var(--mob-text)",
            }}
          >
            <span style={{
              width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
              background: `color-mix(in srgb, ${item.cor} 16%, transparent)`, color: item.cor, flexShrink: 0,
            }}>
              <Icone size={19} />
            </span>
            <span style={{ fontSize: "0.86rem", fontWeight: 800 }}>{TITULO_SECAO[item.chave]}</span>
            <span style={{ fontSize: "0.68rem", color: "var(--mob-muted)", lineHeight: 1.3 }}>{item.subtitulo}</span>
          </button>
        );
      })}
    </div>
  );
}
