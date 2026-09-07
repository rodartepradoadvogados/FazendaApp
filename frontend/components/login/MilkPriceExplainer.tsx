"use client";
import { useMemo, useState } from "react";
import { Calculator, Milk, Info } from "lucide-react";
import { formatBRL } from "@/lib/api";

// Fontes oficiais que embasam os parâmetros usados no simulador (CCS, CBT/CPP,
// gordura, proteína) — checadas em dupla (2 fontes independentes) pelo robô
// Milknews toda segunda-feira (ver Routine "Milknews: checar fonte do
// simulador de preço do leite"). A rotina reescreve FONTES_BONIFICACAO e
// FONTES_ATUALIZADO_EM automaticamente ao validar; nunca edite os links aqui
// sem checar as duas fontes de novo.
//
// Checagem de 24/08/2026: a IN 76/2018 CONTINUA vigente como regulamento
// técnico de identidade e qualidade do leite cru refrigerado — nenhuma norma
// a revogou. Achado da rodada: a IN 55/2020 alterou pontos da IN 76/2018, mas
// só os parâmetros de TEMPERATURA de conservação/expedição (para 5 °C); não
// mexeu nos limites de CCS/CBT nem nos critérios de bonificação que este card
// explica, por isso o rótulo visível segue citando só a IN 76/2018. Se numa
// próxima rodada aparecer alteração que toque CCS/CBT/gordura/proteína, aí sim
// o rótulo precisa passar a citar a norma alteradora.
//
// Reconfirmações posteriores (31/08/2026 e 07/09/2026): as duas mesmas fontes
// independentes (MAPA IN 76/2018 e Embrapa Ater+ Digital) seguem se
// corroborando e nada mudou. A IN 76/2018 continua vigente e nenhuma norma
// posterior — incluindo a IN 55/2020, já registrada acima — alterou os limites
// de CCS (500.000 CS/mL), CBT/CPP (300.000 UFC/mL) nem os teores mínimos de
// gordura/proteína usados como base de bonificação. A página da Embrapa
// continua descrevendo os mesmos indicadores (CCS, CBT, gordura, proteína)
// remetendo à IN 76. Nenhuma divergência entre as fontes; rótulo mantido sem
// alteração — só a data de checagem avança.
const FONTES_BONIFICACAO = [
  {
    nome: "MAPA — Instrução Normativa nº 76/2018",
    url: "https://www.in.gov.br/materia/-/asset_publisher/Kujrw0TZC2Mb/content/id/52750137/do1-2018-11-30-instrucao-normativa-n-76-de-26-de-novembro-de-2018-52749894IN%2076",
  },
  {
    nome: "Embrapa — Indicadores de qualidade do leite",
    url: "https://www.atermaisdigital.cnptia.embrapa.br/web/bovino-de-leite/indicadores-de-qualidade-do-leite",
  },
] as const;
const FONTES_ATUALIZADO_EM = "07/09/2026";

/* ─────────────────────────────────────────────────────────────────────────
   Simulador ILUSTRATIVO de preço do leite — para a página pública de login.

   Importante: não existe uma tabela nacional única de bonificação/penalização
   de leite no Brasil — cada laticínio define suas próprias faixas de CCS,
   CBT/CPP, gordura e proteína (ver backend/fazenda/rules/bonificacao_qualidade.py,
   que por isso nunca hardcoda valores reais e deixa as faixas 100%
   configuráveis pelo usuário). As faixas abaixo são só um EXEMPLO didático
   para mostrar como esse tipo de cálculo costuma funcionar na prática — não
   são números reais de nenhum laticínio específico e não devem ser usadas
   como referência de contrato. */
const FAIXAS_CCS = [
  { limite: 200, ajuste: 0.04, texto: "< 200 mil/mL" },
  { limite: 400, ajuste: 0.02, texto: "200–400 mil/mL" },
  { limite: 600, ajuste: 0.0, texto: "400–600 mil/mL" },
  { limite: Infinity, ajuste: -0.03, texto: "> 600 mil/mL" },
] as const;

const FAIXAS_CBT = [
  { limite: 100, ajuste: 0.03, texto: "< 100 mil UFC/mL" },
  { limite: 300, ajuste: 0.0, texto: "100–300 mil UFC/mL" },
  { limite: Infinity, ajuste: -0.04, texto: "> 300 mil UFC/mL" },
] as const;

const BASE_GORDURA_PCT = 3.0; // base de referência do exemplo: 3,0%
const BASE_PROTEINA_PCT = 3.0; // base de referência do exemplo: 3,0%
const AJUSTE_GORDURA_POR_DECIMO = 0.01; // R$/L a cada 0,1 ponto acima de 3,0%
const AJUSTE_PROTEINA_POR_DECIMO = 0.015; // R$/L a cada 0,1 ponto acima de 3,0%

function ajusteCcs(ccs: number): number {
  if (ccs < 200) return FAIXAS_CCS[0].ajuste;
  if (ccs <= 400) return FAIXAS_CCS[1].ajuste;
  if (ccs <= 600) return FAIXAS_CCS[2].ajuste;
  return FAIXAS_CCS[3].ajuste;
}

function ajusteCbt(cbt: number): number {
  if (cbt < 100) return FAIXAS_CBT[0].ajuste;
  if (cbt <= 300) return FAIXAS_CBT[1].ajuste;
  return FAIXAS_CBT[2].ajuste;
}

function ajusteSolido(pct: number, base: number, porDecimo: number): number {
  return ((pct - base) / 0.1) * porDecimo;
}

type Componente = { label: string; valor: number };

const REFERENCIA_COMPOSICAO = [
  {
    titulo: "1. Preço base negociado",
    texto: "Valor combinado em contrato com o laticínio, ponto de partida antes de qualquer bonificação.",
  },
  {
    titulo: "2. Bonificação por qualidade",
    texto: "CCS e CBT/CPP baixos (menos células somáticas e menos bactérias) costumam render um extra por litro.",
  },
  {
    titulo: "3. Bonificação por sólidos",
    texto: "Gordura e proteína acima da referência do laticínio também costumam agregar valor ao litro.",
  },
  {
    titulo: "4. Bonificação por volume/fidelidade",
    texto: "Regularidade de entrega e volume mínimo mensal podem gerar um adicional fixo ou percentual.",
  },
  {
    titulo: "5. Frete",
    texto: "Normalmente descontado do preço final; varia com a distância até o laticínio e o volume coletado.",
  },
];

const input: React.CSSProperties = {
  width: "100%",
  background: "var(--surface-2)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)",
  padding: "0.5rem 0.7rem",
  fontSize: "0.9rem",
};

const label: React.CSSProperties = {
  display: "block",
  fontSize: "0.72rem",
  color: "var(--text-muted)",
  marginBottom: "0.25rem",
};

function corAjuste(valor: number): string {
  if (valor > 0) return "var(--green-light)";
  if (valor < 0) return "var(--red)";
  return "var(--text-muted)";
}

function formatAjuste(valor: number): string {
  const sinal = valor > 0 ? "+" : valor < 0 ? "−" : "";
  return `${sinal}${formatBRL(Math.abs(valor))}/L`;
}

export default function MilkPriceExplainer() {
  const [precoBase, setPrecoBase] = useState(2.2);
  const [volume, setVolume] = useState(45000);
  const [ccs, setCcs] = useState(300);
  const [cbt, setCbt] = useState(80);
  const [gordura, setGordura] = useState(3.4);
  const [proteina, setProteina] = useState(3.2);

  const { componentes, ajusteTotal, precoFinal, valorMensal } = useMemo(() => {
    const comps: Componente[] = [
      { label: "CCS (qualidade celular)", valor: ajusteCcs(ccs) },
      { label: "CBT/CPP (qualidade bacteriológica)", valor: ajusteCbt(cbt) },
      { label: "Gordura", valor: ajusteSolido(gordura, BASE_GORDURA_PCT, AJUSTE_GORDURA_POR_DECIMO) },
      { label: "Proteína", valor: ajusteSolido(proteina, BASE_PROTEINA_PCT, AJUSTE_PROTEINA_POR_DECIMO) },
    ];
    const total = comps.reduce((acc, c) => acc + c.valor, 0);
    const final = precoBase + total;
    return {
      componentes: comps,
      ajusteTotal: total,
      precoFinal: final,
      valorMensal: final * volume,
    };
  }, [precoBase, volume, ccs, cbt, gordura, proteina]);

  const numInput = (
    value: number,
    onChange: (v: number) => void,
    step = 0.01,
  ) => (
    <input
      type="number"
      step={step}
      value={Number.isFinite(value) ? value : ""}
      onChange={(e) => onChange(e.target.value === "" ? 0 : parseFloat(e.target.value))}
      style={input}
    />
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {/* ── Parte 1: simulador interativo ── */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.6rem", marginBottom: "0.15rem", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <Calculator size={18} style={{ color: "var(--dourado-light)" }} />
            <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "var(--text)" }}>
              Simulador de preço do leite
            </h2>
          </div>
          <div style={{ textAlign: "right", fontSize: "0.66rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
            <div>
              Fontes:{" "}
              {FONTES_BONIFICACAO.map((f, i) => (
                <span key={f.url}>
                  {i > 0 && " · "}
                  <a href={f.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>
                    {f.nome}
                  </a>
                </span>
              ))}
            </div>
            <div>Atualizado em {FONTES_ATUALIZADO_EM}</div>
          </div>
        </div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0 0 1rem" }}>
          Simulação ilustrativa — cada laticínio define suas próprias faixas de bonificação.
          Não representa um contrato real.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: "0.7rem" }}>
          <div>
            <label style={label}>Preço base (R$/litro)</label>
            {numInput(precoBase, setPrecoBase, 0.01)}
          </div>
          <div>
            <label style={label}>Volume mensal (litros)</label>
            {numInput(volume, setVolume, 100)}
          </div>
          <div>
            <label style={label}>CCS (mil cél./mL)</label>
            {numInput(ccs, setCcs, 10)}
          </div>
          <div>
            <label style={label}>CPP/CBT (mil UFC/mL)</label>
            {numInput(cbt, setCbt, 10)}
          </div>
          <div>
            <label style={label}>Gordura (%)</label>
            {numInput(gordura, setGordura, 0.1)}
          </div>
          <div>
            <label style={label}>Proteína (%)</label>
            {numInput(proteina, setProteina, 0.1)}
          </div>
        </div>

        <div
          style={{
            marginTop: "1.1rem",
            padding: "0.9rem 1rem",
            borderRadius: "var(--r-sm)",
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: "0.8rem", marginBottom: "0.9rem" }}>
            <div>
              <div style={label}>Ajuste total por litro</div>
              <div style={{ fontSize: "1.15rem", fontWeight: 800, color: corAjuste(ajusteTotal) }}>
                {formatAjuste(ajusteTotal)}
              </div>
            </div>
            <div>
              <div style={label}>Preço final por litro</div>
              <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--dourado-light)" }}>
                {formatBRL(precoFinal)}
              </div>
            </div>
            <div>
              <div style={label}>Valor mensal estimado</div>
              <div style={{ fontSize: "1.4rem", fontWeight: 800, color: "var(--dourado-light)" }}>
                {formatBRL(valorMensal)}
              </div>
            </div>
          </div>

          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.4rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            De onde vem o ajuste
          </div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            {componentes.map((c) => (
              <li key={c.label} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.82rem" }}>
                <span style={{ color: "var(--text)" }}>{c.label}</span>
                <span style={{ color: corAjuste(c.valor), fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  {formatAjuste(c.valor)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ── Parte 2: referência geral (não ligada aos números do simulador) ── */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.15rem" }}>
          <Milk size={18} style={{ color: "var(--dourado-light)" }} />
          <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "var(--text)" }}>
            Como o preço do leite costuma ser composto
          </h2>
        </div>
        <p style={{ display: "flex", alignItems: "flex-start", gap: "0.4rem", color: "var(--text-muted)", fontSize: "0.78rem", margin: "0 0 1rem" }}>
          <Info size={13} style={{ marginTop: "2px", flexShrink: 0 }} />
          Referência geral do mercado — os componentes e pesos variam por laticínio e região.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          {REFERENCIA_COMPOSICAO.map((item) => (
            <div
              key={item.titulo}
              style={{
                padding: "0.65rem 0.85rem",
                borderRadius: "var(--r-sm)",
                background: "var(--surface-2)",
                borderLeft: "3px solid var(--dourado)",
              }}
            >
              <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text)" }}>{item.titulo}</div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>{item.texto}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
