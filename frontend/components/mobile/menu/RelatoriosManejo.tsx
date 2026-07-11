"use client";
// Sub-tela: Relatórios de Manejo (só leitura). Abas em pílula, uma por lista
// semaforizada (o que fazer). Cada aba mostra animal + motivo + cor do semáforo.
// Só as listas de manejo — sem os relatórios gerenciais com gráficos.
import { useState } from "react";
import { MobVoltar } from "@/components/mobile/ui";
import { fetchRelatoriosManejo } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, Bolinha, NumAnimal } from "@/components/mobile/menu/comum";

type Item = {
  numero: string; grupo?: string | null; cor?: string | null;
  dias_pos_parto?: number | null; dias_inseminada?: number | null; dias_gestacao?: number | null;
  dias_para_secagem?: number | null; dias_para_parto?: number | null; situacao?: string | null; touro?: string | null;
};
type Resposta = Record<string, Item[]>;

// As 8 listas de manejo (fazenda/rules/relatorios_gerenciais.py::relatorios_manejo).
const ABAS: { chave: string; rotulo: string; detalhe: (i: Item) => string }[] = [
  { chave: "pev", rotulo: "PEV", detalhe: (i) => (i.dias_pos_parto != null ? `${i.dias_pos_parto} dias pós-parto` : "no PEV") },
  { chave: "a_inseminar", rotulo: "A inseminar", detalhe: (i) => [i.situacao, i.dias_pos_parto != null ? `${i.dias_pos_parto} DPP` : null].filter(Boolean).join(" · ") || "a inseminar" },
  { chave: "inseminados", rotulo: "Inseminados", detalhe: (i) => [i.dias_inseminada != null ? `${i.dias_inseminada} dias inseminada` : null, i.touro].filter(Boolean).join(" · ") || "inseminada" },
  { chave: "a_tocar", rotulo: "A tocar", detalhe: (i) => (i.dias_inseminada != null ? `tocar · ${i.dias_inseminada} dias inseminada` : "tocar") },
  { chave: "a_reconfirmar", rotulo: "A reconfirmar", detalhe: (i) => (i.dias_inseminada != null ? `reconfirmar · ${i.dias_inseminada} dias` : "reconfirmar") },
  { chave: "prenhes", rotulo: "Prenhes", detalhe: (i) => (i.dias_gestacao != null ? `${i.dias_gestacao} dias de gestação` : "prenhe") },
  { chave: "secagem", rotulo: "Secagem", detalhe: (i) => (i.dias_para_secagem != null ? `secar em ${i.dias_para_secagem} dias` : "secar") },
  { chave: "previsao_partos", rotulo: "Partos", detalhe: (i) => (i.dias_para_parto != null ? `parir em ${i.dias_para_parto} dias` : "previsão de parto") },
];

export default function RelatoriosManejo({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Resposta>("menu_relatorios_manejo", fetchRelatoriosManejo);
  const [aba, setAba] = useState(ABAS[0].chave);

  const cfg = ABAS.find((a) => a.chave === aba) || ABAS[0];
  const itens = (dados?.[aba] as Item[] | undefined) || [];

  return (
    <div>
      <MobVoltar titulo="Relatórios de Manejo" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_relatorios_manejo" mostrar={doCache} />

      {/* Abas roláveis — cada uma com a contagem da sua lista. */}
      <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", paddingBottom: "0.4rem", marginBottom: "0.8rem", WebkitOverflowScrolling: "touch" }}>
        {ABAS.map((a) => {
          const n = (dados?.[a.chave] as Item[] | undefined)?.length ?? 0;
          return (
            <button key={a.chave} type="button" className={`mob-pill${aba === a.chave ? " ativa" : ""}`}
              style={{ whiteSpace: "nowrap", flexShrink: 0, padding: "0.55rem 0.85rem" }} onClick={() => setAba(a.chave)}>
              {a.rotulo} {n > 0 ? `(${n})` : ""}
            </button>
          );
        })}
      </div>

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : itens.length === 0 ? (
        <Vazio>Nenhum animal nesta lista 🎉</Vazio>
      ) : (
        itens.map((i) => (
          <div key={i.numero} className="mob-card" style={{ padding: "0.7rem 1rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.7rem" }}>
            <Bolinha cor={i.cor} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <NumAnimal>Nº {i.numero}</NumAnimal>
              <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
                {cfg.detalhe(i)}{i.grupo ? ` · ${i.grupo}` : ""}
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
