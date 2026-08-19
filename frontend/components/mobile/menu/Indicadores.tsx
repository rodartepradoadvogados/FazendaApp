"use client";
// Sub-tela: Indicadores (só leitura) — quadros de consulta rápida.
// Quatro deles abrem a LISTA de animais por trás do número:
//   • Fêmeas prenhas   • Vazias   • Vacas em lactação
//   • Média por vaca → relatório do último controle leiteiro (kg por vaca).
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import { fetchIndicadores, fetchAnimais, formatDate, type IndicadoresProducao, type AnimalProducaoAoVivo, type ProducaoOrigem } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";

type Resposta = {
  reproducao?: { prenhes?: number | null; taxa_concepcao_pct?: number | null; iep_meses?: number | null; vazias?: number | null };
  producao?: IndicadoresProducao;
  rebanho?: { vacas_lactacao?: number | null };
};

// `ult_cl_kg` é o campo congelado do CSV do Ideagri (parser aposentado — não
// muda mais); `producao_kg`/`producao_origem` vêm de fetchAnimais() ao vivo.
// Até o backend desta etapa subir, os campos novos podem não existir no JSON
// (por isso Partial aqui, e `??` em todo lugar que os lê).
type Animal = {
  numero: string; nome?: string | null; grupo_primario?: string | null;
  sit_rep?: string | null; del_dias?: number | null; ult_cl_kg?: number | null; categoria_abrev?: string | null;
} & Partial<AnimalProducaoAoVivo>;

// Produção do animal com fallback para o campo congelado, e a origem
// coerente com esse fallback (para telas rodando contra um backend antigo,
// que ainda não manda `producao_origem`).
function producaoDe(a: Animal): number | null {
  return a.producao_kg ?? a.ult_cl_kg ?? null;
}
function origemDe(a: Animal): ProducaoOrigem | null {
  if (a.producao_origem) return a.producao_origem;
  if (a.producao_kg != null) return "controle";
  if (a.ult_cl_kg != null) return "congelado";
  return null;
}
// "2026-08-18" → "18/08" — o card não precisa do ano, só do dia do controle.
function dataCurta(iso: string): string {
  return formatDate(iso).slice(0, 5);
}

// Mesmos critérios do backend (rules/indicadores.py).
const GRUPOS_LACTACAO = new Set(["01", "02", "03"]);
const codigoGrupo = (g?: string | null): string | null => {
  const s = (g || "").trim();
  return s.length >= 2 && /^\d\d/.test(s.slice(0, 2)) ? s.slice(0, 2) : null;
};
// Estados "vazia" ao vivo — equivalem ao antigo prefixo textual "Vaz.".
const ESTADOS_VAZIA = new Set(["pev", "apta", "atrasada", "nao_apta", "vazia"]);
const ehPrenhe = (estado?: string) => estado === "gestante";
const ehVazia = (estado?: string) => !!estado && ESTADOS_VAZIA.has(estado);
const ehLactacao = (a: Animal) => GRUPOS_LACTACAO.has(codigoGrupo(a.grupo_primario) || "");

function val(v?: number | null, sufixo = ""): string {
  if (v == null) return "—";
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}${sufixo}`;
}

type Drill = "prenhes" | "vazias" | "lactacao" | "media";
const TITULO_DRILL: Record<Drill, string> = {
  prenhes: "Fêmeas prenhas",
  vazias: "Vazias",
  lactacao: "Vacas em lactação",
  media: "Último controle leiteiro (por vaca)",
};

export default function Indicadores({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Resposta>("menu_indicadores", fetchIndicadores);
  const animaisReq = useCarregar<Animal[]>("menu_indicadores_animais", () => fetchAnimais() as Promise<Animal[]>);
  const [drill, setDrill] = useState<Drill | null>(null);

  const animais = animaisReq.dados || [];
  const { porNumero } = useEstadosReprodutivos();

  const listaDe = (d: Drill): Animal[] => {
    // Sem o estado ao vivo (ainda carregando ou falhou) cai no texto do CSV, para
    // o drill-down não abrir vazio.
    if (d === "prenhes") return porNumero.size
      ? animais.filter((a) => ehPrenhe(porNumero.get(a.numero)?.estado))
      : animais.filter((a) => (a.sit_rep || "").trim() === "Ges.");
    if (d === "vazias") return porNumero.size
      ? animais.filter((a) => ehVazia(porNumero.get(a.numero)?.estado))
      : animais.filter((a) => (a.sit_rep || "").trim().startsWith("Vaz."));
    if (d === "lactacao") return animais.filter(ehLactacao);
    // média por vaca → relatório do último controle leiteiro: vacas com produção
    // no último controle, da maior para a menor (ao vivo, com fallback pro
    // campo congelado para quem nunca teve controle lançado no app).
    return animais
      .filter((a) => (producaoDe(a) ?? 0) > 0)
      .sort((x, y) => (producaoDe(y) || 0) - (producaoDe(x) || 0));
  };

  // ── Sub-lista de um indicador ──────────────────────────────────────────────
  if (drill) {
    const lista = listaDe(drill);
    return (
      <div>
        <MobVoltar titulo={TITULO_DRILL[drill]} onVoltar={() => setDrill(null)} />
        {animaisReq.carregando && !animaisReq.dados ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>Nenhum animal nesta lista.</Vazio>
        ) : (
          <>
            <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.6rem" }}>
              {lista.length} animal(is)
            </p>
            {lista.map((a) => (
              <div key={a.numero} className="mob-card" style={{ padding: "0.75rem 0.9rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span style={{ fontWeight: 800, fontSize: "1.05rem", minWidth: "3rem" }}>{a.numero}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: "0.82rem", color: "var(--mob-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {a.grupo_primario || a.categoria_abrev || "—"}
                  {drill !== "media" && a.del_dias != null ? ` · DEL ${a.del_dias}` : ""}
                </span>
                {drill === "media" && (
                  <span style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--mob-dourado-2)" }}>
                    {val(producaoDe(a), " kg")}
                    {origemDe(a) === "congelado" && <span style={{ color: "var(--mob-muted)" }}> *</span>}
                  </span>
                )}
              </div>
            ))}
            {drill === "media" && lista.some((a) => origemDe(a) === "congelado") && (
              <p style={{ fontSize: "0.7rem", color: "var(--mob-muted)", marginTop: "0.4rem" }}>
                * sem controle leiteiro lançado no app ainda — valor parado da última importação.
              </p>
            )}
          </>
        )}
      </div>
    );
  }

  const r = dados?.reproducao || {};
  const p: Partial<IndicadoresProducao> = dados?.producao || {};
  const reb = dados?.rebanho || {};

  // `data_controle` é o dia do controle mais recente lançado — sem ele o
  // rótulo antigo ("últ. controle") mentia: o total somava o último controle
  // de CADA vaca em qualquer data, não a produção de um dia. Sem controle
  // nenhum lançado, o card avisa em vez de mostrar um número de outro dia.
  const diaControle = p.data_controle ? dataCurta(p.data_controle) : null;
  const cobertura = p.vacas_no_controle != null && p.vacas_lactacao != null
    ? `${p.vacas_no_controle} de ${p.vacas_lactacao} lactantes`
    : null;

  type Quadro = { rotulo: string; valor: string; drill?: Drill; legenda?: string };
  const quadros: Quadro[] = [
    { rotulo: "Fêmeas prenhas", valor: val(r.prenhes), drill: "prenhes" },
    { rotulo: "Concepção por serviço", valor: val(r.taxa_concepcao_pct, "%") },
    { rotulo: "IEP médio", valor: r.iep_meses != null ? `${val(r.iep_meses)} meses` : "—" },
    { rotulo: "Vazias", valor: val(r.vazias), drill: "vazias" },
    {
      rotulo: diaControle ? `Produção do dia · ${diaControle}` : "Produção do dia · sem controle",
      valor: diaControle ? val(p.producao_total_dia_kg, " kg") : "—",
      legenda: cobertura || undefined,
    },
    {
      rotulo: diaControle ? `Média por vaca · ${diaControle}` : "Média por vaca · sem controle",
      valor: diaControle ? val(p.producao_media_kg, " kg") : "—",
      drill: "media",
    },
    { rotulo: "DEL médio atual", valor: p.del_medio != null ? `${val(p.del_medio)} dias` : "—" },
    { rotulo: "Vacas em lactação", valor: val(reb.vacas_lactacao), drill: "lactacao" },
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
          {quadros.map((q) => {
            const conteudo = (
              <>
                <div style={{ fontSize: "1.7rem", fontWeight: 800, lineHeight: 1.1, color: "var(--mob-text)" }}>{q.valor}</div>
                <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.35rem", fontWeight: 600 }}>{q.rotulo}</div>
                {q.legenda && (
                  <div style={{ fontSize: "0.66rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>{q.legenda}</div>
                )}
                {q.drill && (
                  <div style={{ fontSize: "0.68rem", color: "var(--mob-dourado-2)", marginTop: "0.3rem", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center", gap: "0.15rem" }}>
                    ver lista <ChevronRight size={12} />
                  </div>
                )}
              </>
            );
            return q.drill ? (
              <button key={q.rotulo} type="button" onClick={() => setDrill(q.drill!)}
                className="mob-card" style={{ padding: "1rem 0.9rem", textAlign: "center", cursor: "pointer", border: "1px solid var(--mob-border)" }}>
                {conteudo}
              </button>
            ) : (
              <div key={q.rotulo} className="mob-card" style={{ padding: "1rem 0.9rem", textAlign: "center" }}>
                {conteudo}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
