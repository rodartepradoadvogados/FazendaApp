"use client";
// Cadastro dos TRATOS POR DIA de uma dieta (decisão do dono, 21/10/2026) —
// usado no "Lançar nova dieta" do site (CadastroAlimentacao.tsx) e do app
// (mobile/menu/LancarDieta.tsx). Três perguntas, na ordem em que o tratador
// pensa: quantos tratos (1 a 4), quanto % de cada um (soma 100%, identificados
// só por número) e entre quais tratos a sobra do cocho é lida (define o ciclo
// de 24h da sobra — com 1 trato não se pergunta). Regras em lib/tratos.ts,
// iguais às do backend (fazenda/rules/tratos.py), que valida de novo ao salvar.
import { MAX_TRATOS, opcoesPosicaoLeitura, tratosIguais, validarTratos } from "@/lib/tratos";

/** Estado do editor — % como texto (campo editável), posição como nº do trato. */
export type TratosForm = { pcts: string[]; posicao: number | null };

/** Dieta nova: 2 tratos 50/50, leitura da sobra entre o Trato 2 e o Trato 1
 * (de manhã, antes do 1º trato — a sobra se refere ao dia anterior, a mesma
 * regra que a tela de sobra do site já ensinava). Tudo editável. */
export const tratosFormPadrao = (): TratosForm => ({ pcts: ["50", "50"], posicao: 2 });

export function tratosDoForm(f: TratosForm): { tratos_pct: number[]; sobra_posicao_leitura: number | null } {
  const tratos_pct = f.pcts.map((p) => Number(String(p).replace(",", ".")));
  return { tratos_pct, sobra_posicao_leitura: tratos_pct.length === 1 ? 1 : f.posicao };
}

/** Erro do cadastro (para bloquear o salvar), ou null. */
export function erroTratosForm(f: TratosForm): string | null {
  const { tratos_pct, sobra_posicao_leitura } = tratosDoForm(f);
  const erro = validarTratos(tratos_pct);
  if (erro) return erro;
  if (tratos_pct.length > 1 && sobra_posicao_leitura == null) return "Informe entre quais tratos a sobra do cocho é lida.";
  return null;
}

type Variante = "site" | "app";
const TOKENS: Record<Variante, { muted: string; borda: string; fundo: string; ativo: string; erro: string; ok: string; texto: string }> = {
  site: { muted: "var(--text-muted)", borda: "var(--border)", fundo: "var(--surface-2)", ativo: "var(--dourado)", erro: "var(--red)", ok: "var(--green-light)", texto: "var(--text)" },
  app: { muted: "var(--mob-muted)", borda: "var(--mob-border)", fundo: "var(--mob-surface)", ativo: "var(--mob-vinho)", erro: "var(--mob-vermelho)", ok: "var(--mob-verde)", texto: "var(--mob-text)" },
};

export function EditorTratosDieta({ valor, onChange, variante, estiloInput, classeInput }: {
  valor: TratosForm; onChange: (v: TratosForm) => void; variante: Variante;
  estiloInput?: React.CSSProperties; classeInput?: string;
}) {
  const t = TOKENS[variante];
  const n = valor.pcts.length;
  const soma = valor.pcts.reduce((s, p) => s + (Number(String(p).replace(",", ".")) || 0), 0);
  const erro = validarTratos(tratosDoForm(valor).tratos_pct);
  const pilula = (ativo: boolean): React.CSSProperties => ({
    padding: variante === "app" ? "0.65rem 0.5rem" : "0.35rem 0.7rem", borderRadius: variante === "app" ? "var(--r-app)" : 999,
    fontSize: variante === "app" ? "0.95rem" : "0.78rem", fontWeight: 700, cursor: "pointer",
    border: `${variante === "app" ? 2 : 1}px solid ${ativo ? t.ativo : t.borda}`,
    background: ativo ? t.ativo : t.fundo, color: ativo ? "#FFFFFF" : t.texto,
  });
  const rotulo: React.CSSProperties = { display: "block", fontSize: variante === "app" ? "0.85rem" : "0.72rem", fontWeight: 700, color: t.muted, margin: "0.5rem 0 0.3rem" };

  function mudarQuantidade(novo: number) {
    if (novo === n) return;
    onChange({ pcts: tratosIguais(novo).map(String), posicao: novo === 1 ? 1 : novo });
  }

  return (
    <div style={{ border: `1px solid ${t.borda}`, borderRadius: variante === "app" ? "var(--r-app)" : 8, padding: "0.6rem 0.7rem", marginTop: "0.6rem" }}>
      <span style={{ ...rotulo, marginTop: 0 }}>Tratos por dia</span>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${MAX_TRATOS}, 1fr)`, gap: "0.4rem", maxWidth: variante === "site" ? "16rem" : undefined }}>
        {Array.from({ length: MAX_TRATOS }, (_, i) => i + 1).map((q) => (
          <button key={q} type="button" style={pilula(q === n)} onClick={() => mudarQuantidade(q)} aria-pressed={q === n}>{q}</button>
        ))}
      </div>

      <span style={rotulo}>% de cada trato (a mesma proporção vale para todos os alimentos)</span>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(n, 2)}, minmax(0, 1fr))`, gap: "0.4rem" }}>
        {valor.pcts.map((p, i) => (
          <label key={i} style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: variante === "app" ? "0.9rem" : "0.78rem", color: t.texto }}>
            <span style={{ whiteSpace: "nowrap", fontWeight: 700 }}>Trato {i + 1}</span>
            <input type="number" inputMode="decimal" min={0} max={100} className={classeInput} style={{ ...estiloInput, minWidth: 0 }}
              value={p} disabled={n === 1}
              onChange={(e) => onChange({ ...valor, pcts: valor.pcts.map((x, j) => (j === i ? e.target.value : x)) })} />
            <span style={{ color: t.muted }}>%</span>
          </label>
        ))}
      </div>
      <p style={{ fontSize: variante === "app" ? "0.8rem" : "0.7rem", margin: "0.35rem 0 0", color: erro ? t.erro : t.ok, fontWeight: 600 }}>
        {erro ?? `Soma: ${Math.round(soma * 100) / 100}%`}
      </p>

      {n > 1 && (
        <>
          <span style={rotulo}>A sobra do cocho é lida entre quais tratos?</span>
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(n, 2)}, minmax(0, 1fr))`, gap: "0.4rem" }}>
            {opcoesPosicaoLeitura(n).map((o) => (
              <button key={o.valor} type="button" style={pilula(valor.posicao === o.valor)} aria-pressed={valor.posicao === o.valor}
                onClick={() => onChange({ ...valor, posicao: o.valor })}>
                {o.rotulo}
              </button>
            ))}
          </div>
          <p style={{ fontSize: variante === "app" ? "0.78rem" : "0.68rem", margin: "0.35rem 0 0", color: t.muted }}>
            Define o ciclo de 24h a que cada sobra se refere (ex.: lida entre o Trato {n} e o Trato 1 = sobra dos tratos do dia anterior).
          </p>
        </>
      )}
    </div>
  );
}
