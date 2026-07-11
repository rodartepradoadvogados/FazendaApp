"use client";
// Sub-tela: Indicadores (só leitura) — 8 quadros de consulta rápida.
// Cada quadro: número grande + rótulo pequeno. Valores nulos mostram "—".
import { MobVoltar } from "@/components/mobile/ui";
import { fetchIndicadores } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

type Resposta = {
  reproducao?: { prenhes?: number | null; taxa_concepcao_pct?: number | null; iep_meses?: number | null; vazias?: number | null };
  producao?: { producao_total_dia_kg?: number | null; producao_media_kg?: number | null; del_medio?: number | null };
  rebanho?: { vacas_lactacao?: number | null };
};

function val(v?: number | null, sufixo = ""): string {
  if (v == null) return "—";
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}${sufixo}`;
}

export default function Indicadores({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Resposta>("menu_indicadores", fetchIndicadores);

  const r = dados?.reproducao || {};
  const p = dados?.producao || {};
  const reb = dados?.rebanho || {};

  const quadros: { rotulo: string; valor: string }[] = [
    { rotulo: "Fêmeas prenhas", valor: val(r.prenhes) },
    { rotulo: "Concepção por serviço", valor: val(r.taxa_concepcao_pct, "%") },
    { rotulo: "IEP médio", valor: r.iep_meses != null ? `${val(r.iep_meses)} meses` : "—" },
    { rotulo: "Vazias", valor: val(r.vazias) },
    { rotulo: "Produção/dia (últ. controle)", valor: val(p.producao_total_dia_kg, " kg") },
    { rotulo: "Média por vaca (últ. controle)", valor: val(p.producao_media_kg, " kg") },
    { rotulo: "DEL médio atual", valor: p.del_medio != null ? `${val(p.del_medio)} dias` : "—" },
    { rotulo: "Vacas em lactação", valor: val(reb.vacas_lactacao) },
  ];

  return (
    <div>
      <MobVoltar titulo="Indicadores" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_indicadores" mostrar={doCache} />

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
          {quadros.map((q) => (
            <div key={q.rotulo} className="mob-card" style={{ padding: "1rem 0.9rem", textAlign: "center" }}>
              <div style={{ fontSize: "1.7rem", fontWeight: 800, lineHeight: 1.1, color: "var(--mob-text)" }}>{q.valor}</div>
              <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.35rem", fontWeight: 600 }}>{q.rotulo}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
