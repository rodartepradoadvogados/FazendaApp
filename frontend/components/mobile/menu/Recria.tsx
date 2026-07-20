"use client";
// Sub-tela: Recria — Dossiê Zootécnico (só leitura). Versão de campo do
// módulo do site (frontend/app/recria/page.tsx): KPIs de capa, ponto crítico
// de doenças por idade, peso real × peso-alvo e os últimos casos lançados.
// Fluxos de escritório do site (importar planilha DairyComp 305, exportar o
// Dossiê em PDF) ficam de fora — não são tarefas de campo.
import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import {
  fetchRecriaDossie, fetchRecriaDoencas, fetchRecriaCurva, fetchRecriaPesoAlvoResumo, fetchRecriaOcorrencias,
  type RecriaDossie, type RecriaCurva, type RecriaOcorrencia,
} from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

type Aba = "resumo" | "saude" | "crescimento" | "casos";
const ABAS: { chave: Aba; rotulo: string }[] = [
  { chave: "resumo", rotulo: "Resumo" },
  { chave: "saude", rotulo: "Saúde" },
  { chave: "crescimento", rotulo: "Crescimento" },
  { chave: "casos", rotulo: "Casos recentes" },
];

// Sufixo de exibição por KPI (mesmos rótulos do site, sem casas decimais extras).
const KPI_ROTULOS: Record<string, string> = {
  meta_idade_parto: "Meta idade ao 1º parto",
  idade_media_1o_parto: "Idade média ao 1º parto",
  desvio_idade_parto: "Desvio-padrão",
  n_animais_1o_parto: "Novilhas com 1º parto",
  custo_excedente_total: "Custo de recria excedente",
  dias_excedentes_medios: "Dias excedentes/novilha",
  total_recria: "Animais na recria",
};
function fmtKpi(chave: string, v: number): string {
  if (chave === "custo_excedente_total") return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  if (chave.includes("idade") || chave.includes("desvio")) return `${v} m`;
  if (chave === "dias_excedentes_medios") return `${v} d`;
  return `${v}`;
}

export default function Recria({ onVoltar }: { onVoltar: () => void }) {
  const { dados: dossie, doCache, carregando } = useCarregar<RecriaDossie>("menu_recria_dossie", fetchRecriaDossie);
  const [aba, setAba] = useState<Aba>("resumo");

  const kpis = Object.entries(dossie?.kpis || {}).filter(([, v]) => v != null && v !== undefined) as [string, number][];

  return (
    <div>
      <MobVoltar titulo="Recria" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_recria_dossie" mostrar={doCache} />

      <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", paddingBottom: "0.4rem", marginBottom: "0.9rem", WebkitOverflowScrolling: "touch" }}>
        {ABAS.map((a) => (
          <button key={a.chave} type="button" className={`mob-pill${aba === a.chave ? " ativa" : ""}`}
            style={{ whiteSpace: "nowrap", flexShrink: 0, padding: "0.55rem 0.85rem" }} onClick={() => setAba(a.chave)}>
            {a.rotulo}
          </button>
        ))}
      </div>

      {carregando && !dossie ? (
        <Carregando />
      ) : !dossie ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : (
        <>
          {aba === "resumo" && (
            !kpis.length ? <Vazio>Ainda não há indicadores suficientes para o resumo.</Vazio> : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
                {kpis.map(([chave, v]) => (
                  <div key={chave} className="mob-card" style={{ padding: "1rem 0.9rem", textAlign: "center" }}>
                    <div style={{ fontSize: "1.35rem", fontWeight: 800, lineHeight: 1.1, color: "var(--mob-text)" }}>{fmtKpi(chave, v)}</div>
                    <div style={{ fontSize: "0.74rem", color: "var(--mob-muted)", marginTop: "0.35rem", fontWeight: 600 }}>{KPI_ROTULOS[chave] || chave}</div>
                  </div>
                ))}
              </div>
            )
          )}
          {aba === "saude" && <AbaSaude />}
          {aba === "crescimento" && <AbaCrescimento />}
          {aba === "casos" && <AbaCasos />}
        </>
      )}
    </div>
  );
}

// ── Saúde: doença por botões + ponto crítico + incidência por fase ─────────
function AbaSaude() {
  const { dados: doencas, carregando: carregandoDoencas } = useCarregar<{ doenca: string; casos: number }[]>("menu_recria_doencas", fetchRecriaDoencas);
  const [sel, setSel] = useState<string>("");
  useEffect(() => { if (doencas && doencas.length && !sel) setSel(doencas[0].doenca); }, [doencas, sel]);

  const { dados: curva, carregando: carregandoCurva } = useCarregar<RecriaCurva | null>(
    sel ? `menu_recria_curva_${sel}` : "menu_recria_curva_nenhuma",
    () => (sel ? fetchRecriaCurva(sel) : Promise.resolve(null)),
  );

  if (carregandoDoencas && !doencas) return <Carregando />;
  if (!doencas || !doencas.length) return <Vazio icon={AlertTriangle}>Nenhum caso de doença registrado ainda.</Vazio>;

  const pc = curva?.ponto_critico;
  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.9rem" }}>
        {doencas.map((d) => (
          <button key={d.doenca} type="button" className={`mob-pill${sel === d.doenca ? " ativa" : ""}`} onClick={() => setSel(d.doenca)}>
            {d.doenca} ({d.casos})
          </button>
        ))}
      </div>

      {carregandoCurva && !curva ? <Carregando /> : !curva ? null : (
        <>
          <MobCard style={{ marginBottom: "0.7rem" }}>
            <div style={{ fontSize: "0.7rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--mob-muted)", fontWeight: 700 }}>Volume analisado</div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800 }}>{curva.total_casos} <span style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--mob-muted)" }}>caso(s)</span></div>
          </MobCard>
          {pc && (
            <MobCard style={{ marginBottom: "0.9rem", borderColor: "var(--mob-vermelho)", background: "color-mix(in srgb, var(--mob-vermelho) 8%, transparent)" }}>
              <div style={{ fontSize: "0.7rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--mob-vermelho)", fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
                <AlertTriangle size={13} /> Ponto crítico
              </div>
              <div style={{ fontSize: "1.3rem", fontWeight: 800 }}>{pc.dia_pico}º dia de vida</div>
              <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>
                Janela {pc.dia_min}–{pc.dia_max} dias concentra <strong>{pc.pct_na_janela}%</strong> dos casos.
              </div>
            </MobCard>
          )}

          {curva.incidencia_por_fase.some((f) => f.casos > 0) && (
            <>
              <div style={{ fontWeight: 700, fontSize: "0.88rem", marginBottom: "0.5rem" }}>Incidência por fase</div>
              {curva.incidencia_por_fase.map((f) => {
                const inc = f.incidencia_pct;
                const cor = inc == null ? "var(--mob-muted)" : inc >= 20 ? "var(--mob-vermelho)" : inc >= 8 ? "var(--mob-ambar)" : "var(--mob-verde)";
                return (
                  <div key={f.fase} className="mob-card" style={{ padding: "0.65rem 0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem" }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{f.fase}</div>
                      <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)" }}>{f.casos} caso(s) · {f.animais_afetados}/{f.animais_em_risco} animais</div>
                    </div>
                    <span style={{ fontWeight: 800, fontSize: "1.05rem", color: cor, flexShrink: 0 }}>{inc == null ? "—" : `${inc}%`}</span>
                  </div>
                );
              })}
            </>
          )}
        </>
      )}
    </div>
  );
}

// ── Crescimento: peso real médio × peso-alvo por mês de idade ──────────────
function AbaCrescimento() {
  const { dados, carregando } = useCarregar<{ linhas: any[] }>("menu_recria_peso_alvo", fetchRecriaPesoAlvoResumo);
  const linhas = dados?.linhas || [];
  if (carregando && !dados) return <Carregando />;
  if (!linhas.length) return <Vazio>Ainda não há pesagens ou faixas de peso-alvo cadastradas.</Vazio>;

  return (
    <div>
      {linhas.map((l) => {
        const st = l.dentro_do_alvo;
        const cor = st == null ? "var(--mob-muted)" : st ? "var(--mob-verde)" : "var(--mob-vermelho)";
        const txt = st == null ? "sem faixa/pesagem" : st ? "Dentro do alvo" : (l.peso_medio_real < (l.peso_min_alvo ?? 0) ? "Abaixo do alvo" : "Acima do alvo");
        return (
          <div key={l.mes} className="mob-card" style={{ padding: "0.7rem 0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem" }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: "0.92rem" }}>{l.mes}º mês</div>
              <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>
                {l.peso_medio_real != null ? `${l.peso_medio_real} kg real` : "sem pesagem"}
                {l.peso_min_alvo != null ? ` · alvo ${l.peso_min_alvo}–${l.peso_max_alvo} kg` : ""}
              </div>
            </div>
            <span style={{ fontWeight: 700, fontSize: "0.82rem", color: cor, textAlign: "right", flexShrink: 0, maxWidth: "38%" }}>{txt}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Casos recentes — últimas ocorrências lançadas (site + app) ─────────────
function AbaCasos() {
  const { dados, carregando } = useCarregar<RecriaOcorrencia[]>("menu_recria_ocorrencias", () => fetchRecriaOcorrencias());
  const lista = (dados || []).slice(0, 20);
  if (carregando && !dados) return <Carregando />;
  if (!lista.length) return <Vazio>Nenhum caso registrado ainda.</Vazio>;

  return (
    <div>
      {lista.map((o) => (
        <div key={o.id} className="mob-card" style={{ padding: "0.7rem 0.9rem", marginBottom: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem" }}>
            <span style={{ fontWeight: 800, fontSize: "1rem" }}>Nº {o.numero_matriz}</span>
            <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", flexShrink: 0 }}>{o.data_ocorrencia.split("-").reverse().join("/")}</span>
          </div>
          <div style={{ fontSize: "0.85rem", fontWeight: 600, marginTop: "0.15rem" }}>{o.doenca}</div>
          {o.observacao && <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>{o.observacao}</div>}
        </div>
      ))}
    </div>
  );
}
