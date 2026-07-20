"use client";
import React from "react";

/* ───────────────────────── Tipos e utilitários compartilhados pelos
   formulários de Lançamentos (site) — extraídos de app/lancamentos/page.tsx
   para permitir reuso (ex.: app móvel) sem duplicar lógica. ───────────────────────── */

export type EstoqueItem = {
  nome: string; quantidade?: number | null; unidade?: string | null; categoria?: string | null; estocavel?: boolean | null;
  estoque_minimo?: number | null; classificacao_medicamento?: string | null; principio_ativo?: string | null;
  finalidade?: string | null; conta_gerencial_despesa_padrao?: string | null; conta_gerencial_receita_padrao?: string | null;
  estoque_semen_id?: number | null; tipo_semen?: string | null;
};

export const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
export const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
export const nota: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: "0.35rem" };

export function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>;
}

// Subtítulo de seção dentro de um formulário.
export const Secao = ({ children }: { children: React.ReactNode }) => (
  <p style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--dourado-light)", margin: "1rem 0 0.5rem" }}>{children}</p>
);

const UNIDADES = ["ml", "kg", "L", "unidade", "dose", "saca 30kg", "saca 60kg"];

// Prévia do estoque restante após uma baixa de quantidade.
export function EstoqueRestante({ estoque, produto, quantidade }: { estoque: EstoqueItem[]; produto: string; quantidade: number }) {
  const item = estoque.find((e) => e.nome === produto);
  if (!item) return null;
  const atual = item.quantidade ?? 0;
  const restante = atual - (quantidade || 0);
  return (
    <p style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
      Estoque atual: <strong>{atual} {item.unidade || ""}</strong> → após a aplicação:{" "}
      <strong style={{ color: restante < 0 ? "var(--red)" : "var(--green-light)" }}>{restante} {item.unidade || ""}</strong>
      {restante < 0 && <span style={{ color: "var(--red)" }}> (estoque insuficiente!)</span>}
    </p>
  );
}

// Mesma regra do backend (fazenda.rules.unidades): unidade de aplicação
// precisa ser compatível com a unidade de estoque do produto — ex.: um
// produto guardado em "ml" pode ser aplicado em ml/unidade/dose, mas não em L.
export const GRUPOS_UNIDADE: string[][] = [["ml", "unidade", "dose"], ["L", "kg"]];
// Sinônimos/abreviações legadas (import de planilha, cadastro antigo) que
// precisam cair no mesmo grupo do valor canônico — senão o item some das
// opções de unidade compatível (ex.: "un" não batia com "unidade" e escondia "ml").
export const SINONIMOS_UNIDADE: Record<string, string> = { un: "unidade", und: "unidade", unid: "unidade", unidades: "unidade" };
export function unidadesCompativeis(unidadeEstoque: string | null | undefined): string[] {
  if (!unidadeEstoque) return UNIDADES;
  const normalizada = SINONIMOS_UNIDADE[unidadeEstoque.trim().toLowerCase()] || unidadeEstoque;
  const grupo = GRUPOS_UNIDADE.find((g) => g.includes(normalizada));
  return grupo || [unidadeEstoque];
}

export type ItemSanidade = { produto: string; via: string; quantidade: string; unidade: string; estoque_id?: number | null; definirPor: "medicamento" | "principio_ativo" | "doenca"; criterio: string };
export const itemSanidadeVazio = (): ItemSanidade => ({ produto: "", via: "", quantidade: "", unidade: "", estoque_id: null, definirPor: "medicamento", criterio: "" });

// Mesmo esquema de código de 2 dígitos usado em fazenda.rules.alimentacao._codigo_grupo,
// para expandir lote(s) selecionado(s) no número de matrículas correspondente.
export function codigoGrupo(grupo: string | null | undefined): string | null {
  if (!grupo) return null;
  const g = grupo.trim();
  return g.length >= 2 && /^\d\d/.test(g) ? g.slice(0, 2) : null;
}

// Códigos de lote (2 dígitos) considerados "em lactação" — mesmo esquema
// usado em indicadores/produção/rebanho (LACTACAO/LOTES_LACTACAO).
export const LOTES_LACTACAO = ["01", "02", "03"];

// Mesmo idioma usado em Controle leiteiro (app/lancamentos/page.tsx, FormControle):
// animal em lactação = está num lote de lactação (01/02/03) OU já tem DEL em curso (> 0).
// Serve para não misturar secas/novilhas/machos nas telas que só fazem sentido para
// quem está produzindo leite (ex.: Secagem).
export function animalEmLactacao(a: { grupo_primario?: string | null; del_dias?: number | null }): boolean {
  const cod = codigoGrupo(a.grupo_primario);
  return (!!cod && LOTES_LACTACAO.includes(cod)) || ((a.del_dias ?? 0) > 0);
}

export const MOTIVOS_SECAGEM = [
  { v: "doente", l: "Animal doente" },
  { v: "baixa_producao", l: "Baixa produção" },
  { v: "comportamento", l: "Comportamento" },
  { v: "mastite", l: "Mastite" },
  { v: "casco", l: "Problema de casco" },
  { v: "rotina", l: "Rotina parto" },
  { v: "outros", l: "Outros" },
];
