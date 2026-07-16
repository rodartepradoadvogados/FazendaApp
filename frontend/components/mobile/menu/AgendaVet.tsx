"use client";
// Sub-tela: Agenda do Veterinário (só leitura, dentro do app).
// Abre APENAS as listas da classificação do rebanho fêmea — cada lista é uma
// seção recolhível (<details>) com nome amigável + contagem; dentro, os
// animais, clicáveis — abrem a ficha do animal aqui mesmo (estado local),
// com seta de voltar para esta mesma tela.
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import { fetchAgendaVeterinario, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, NumAnimal } from "@/components/mobile/menu/comum";
import { FichaDetalhe } from "@/components/mobile/rebanho/Ficha";

type Animal = {
  numero_matriz: string;
  categoria?: string;
  peso?: number | null;
  dias_inseminada?: number | null;
  data_servico?: string | null;
  tocada?: boolean;
  reconfirmada?: boolean;
  atrasada?: boolean;
  dias_para_parto?: number | null;
  motivo?: string | null;
};
type Resposta = { data_referencia: string; listas: Record<string, Animal[]>; totais: Record<string, number> };

// Ordem e rótulos amigáveis das 10 listas (ver fazenda/rules/agenda_veterinario.py).
const LISTAS: { chave: string; rotulo: string }[] = [
  { chave: "inseminadas_1_29", rotulo: "Inseminadas 1–29 dias (aguardar toque)" },
  { chave: "inseminadas_30_59", rotulo: "Inseminadas 30–59 dias (tocar)" },
  { chave: "inseminadas_60_mais", rotulo: "Inseminadas 60+ dias (reconfirmar)" },
  { chave: "novilhas_aptas_vazias", rotulo: "Novilhas aptas e vazias (inseminar)" },
  { chave: "novilhas_gestantes", rotulo: "Novilhas gestantes" },
  { chave: "verificar_aptidao", rotulo: "Verificar aptidão (≥280 kg, nunca servida)" },
  { chave: "verificar_pre_parto", rotulo: "Pré-parto (verificar)" },
  { chave: "vacas_gestantes", rotulo: "Vacas gestantes" },
  { chave: "vazias_por_diagnostico", rotulo: "Vazias por diagnóstico (novo serviço)" },
  { chave: "pendentes_classificacao", rotulo: "Pendentes de classificação" },
  // Só aparece quando o parâmetro "usa_adesivo_deteccao_cio" está ativo.
  { chave: "observacao_cio", rotulo: "Observação de cio — adesivo de repasse" },
];

function detalhe(chave: string, a: Animal): string {
  if (a.motivo) return a.motivo;
  const partes: string[] = [];
  if (a.dias_para_parto != null) partes.push(`parto em ${a.dias_para_parto} dias`);
  if (a.dias_inseminada != null) partes.push(`${a.dias_inseminada} dias inseminada`);
  if (a.peso != null) partes.push(`${a.peso} kg`);
  if (a.atrasada) partes.push("atrasada");
  if (!partes.length && a.data_servico) partes.push(`serviço ${formatDate(a.data_servico)}`);
  return partes.join(" · ");
}

export default function AgendaVet({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Resposta>("menu_agenda_vet", fetchAgendaVeterinario);
  const [fichaAberta, setFichaAberta] = useState<string | null>(null);

  const total = dados ? Object.values(dados.totais || {}).reduce((s, n) => s + n, 0) : 0;

  if (fichaAberta) return <FichaDetalhe numero={fichaAberta} onVoltar={() => setFichaAberta(null)} />;

  return (
    <div>
      <MobVoltar titulo="Agenda do Veterinário" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_agenda_vet" mostrar={doCache} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : total === 0 ? (
        <Vazio>Nenhum animal a acompanhar no momento 🎉</Vazio>
      ) : (
        LISTAS.map(({ chave, rotulo }) => {
          const animais = dados.listas[chave] || [];
          if (!animais.length) return null;
          return (
            <details key={chave} className="mob-card mob-card-vet" style={{ padding: "0.4rem 0.9rem", marginBottom: "0.6rem" }}>
              <summary style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem", cursor: "pointer", padding: "0.55rem 0", fontWeight: 700, fontSize: "0.95rem", listStyle: "none" }}>
                <span style={{ flex: 1, minWidth: 0 }}>{rotulo}</span>
                <span style={{ fontSize: "0.78rem", fontWeight: 800, padding: "0.2rem 0.6rem", borderRadius: 999, background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", color: "var(--mob-muted)", flexShrink: 0 }}>
                  {animais.length}
                </span>
              </summary>
              <div style={{ borderTop: "1px solid var(--mob-border)", paddingTop: "0.4rem" }}>
                {animais.map((a) => (
                  <button key={a.numero_matriz} onClick={() => setFichaAberta(a.numero_matriz)}
                    style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "100%", background: "none", border: "none", padding: "0.5rem 0", borderBottom: "1px solid var(--mob-border)", cursor: "pointer", color: "inherit", textAlign: "left", font: "inherit" }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <NumAnimal>Nº {a.numero_matriz}</NumAnimal>
                      <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>{detalhe(chave, a)}</div>
                    </div>
                    <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
                  </button>
                ))}
              </div>
            </details>
          );
        })
      )}
    </div>
  );
}
