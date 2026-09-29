"use client";
// Peças compartilhadas do fluxo preventivo (fatia 8): Acompanhamento, gaveta
// Aplicar, Concluídos e o passo Checklist do assistente "Criar agendamento".
// Vocabulário do fluxo aprovado: Aplicar, Desconsiderar, Agendamento.
import React from "react";
import { AlertTriangle, Check, Clock, Flag, X } from "lucide-react";
import type { EstadoVisualAg, ResumoChecklist } from "@/lib/api";

export const inputStyle: React.CSSProperties = {
  fontSize: "0.85rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", width: "100%",
};
export const labelStyle: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
export const notaStyle: React.CSSProperties = { fontSize: "0.78rem", color: "var(--text-muted)" };

export const plural = (n: number, um: string, varios: string) => (n === 1 ? um : varios);

export function hojeIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function maisDiasIso(dias: number, base?: string): string {
  const d = base ? new Date(base + "T00:00:00") : new Date();
  d.setDate(d.getDate() + dias);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const DIAS_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
export const diaSemana = (iso: string) => DIAS_SEMANA[new Date(iso + "T00:00:00").getDay()];
export function dataCurta(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${a}`;
}
export function dataHoraCurta(iso: string | null | undefined): string {
  if (!iso) return "—";
  const dt = new Date(iso.endsWith("Z") ? iso : iso + "Z");   // o servidor grava em UTC
  return `${dataCurta(hojeDe(dt))} ${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}`;
}
function hojeDe(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function num(n: number | null | undefined, casas = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}
export function brl(n: number | null | undefined): string {
  return n == null ? "a informar" : n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function Chips({ rotulo, opcoes, valor, onChange, idBase, erro }: {
  rotulo: string; opcoes: readonly string[]; valor: string; onChange: (v: string) => void; idBase: string; erro?: string | null;
}) {
  return (
    <div>
      <span id={`${idBase}-l`} style={labelStyle}>{rotulo}</span>
      <div role="radiogroup" aria-labelledby={`${idBase}-l`} style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
        {opcoes.map((o) => {
          const ativo = valor === o;
          return (
            <button
              key={o} type="button" role="radio" aria-checked={ativo} onClick={() => onChange(o)}
              style={{
                fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: 999, cursor: "pointer", minHeight: 36,
                border: `1px solid ${ativo ? "var(--pill-active-border)" : "var(--border)"}`,
                background: ativo ? "var(--pill-active-bg)" : "transparent",
                color: ativo ? "var(--pill-active-fg)" : "var(--text)", fontWeight: ativo ? 700 : 500,
              }}
            >{o}</button>
          );
        })}
      </div>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.78rem", marginTop: "0.35rem" }}>{erro}</p>}
    </div>
  );
}

export function Pill({ cor, children, title }: { cor: string; children: React.ReactNode; title?: string }) {
  return (
    <span title={title} style={{
      display: "inline-flex", alignItems: "center", gap: 4, fontSize: "0.72rem", fontWeight: 700, padding: "0.2rem 0.6rem",
      borderRadius: 999, color: cor, border: `1px solid ${cor}`, background: "var(--surface-2)", whiteSpace: "nowrap",
    }}>{children}</span>
  );
}

const ESTADO_AG: Record<EstadoVisualAg, { txt: string; cor: string }> = {
  em_montagem: { txt: "Em montagem", cor: "var(--amber)" },
  agendado: { txt: "Agendado", cor: "var(--dourado-light)" },
  hoje: { txt: "Hoje", cor: "var(--amber)" },
  atrasado: { txt: "Atrasado", cor: "var(--red)" },
  adiado: { txt: "Adiado", cor: "var(--text-muted)" },
};
export function EstadoAgPill({ estado }: { estado: EstadoVisualAg }) {
  const e = ESTADO_AG[estado];
  return <Pill cor={e.cor}>{estado === "atrasado" ? <AlertTriangle size={12} /> : <Clock size={12} />}{e.txt}</Pill>;
}

export function ForaJanelaBadge({ n }: { n: number }) {
  if (!n) return null;
  return (
    <span title="Incluídos por conta da fazenda, fora da janela de aplicação" style={{ color: "var(--amber)", fontSize: "0.72rem", fontWeight: 700, display: "inline-flex", gap: 3, alignItems: "center" }}>
      <Flag size={12} />{n} fora da janela
    </span>
  );
}

/** x/y do checklist com o ícone do pior caso (pendente = tracejado; Vet não confirmou = vermelho). */
export function ChecklistSelo({ ck }: { ck: ResumoChecklist }) {
  const pend = ck.total - ck.resolvidos;
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 2 }}>
      <span style={{ fontWeight: 700, fontSize: "0.82rem", color: pend ? "var(--amber)" : "var(--green-light)", display: "inline-flex", alignItems: "center", gap: 4 }}>
        {pend ? <AlertTriangle size={13} /> : <Check size={13} />}{ck.resolvidos}/{ck.total}
      </span>
      {pend > 0 && <span style={notaStyle}>{pend} {plural(pend, "pendente", "pendentes")}</span>}
      {ck.vet_nao_confirmou && <span style={{ color: "var(--red)", fontSize: "0.72rem", fontWeight: 700, display: "inline-flex", gap: 3, alignItems: "center" }}><X size={12} />Vet não confirmou</span>}
    </span>
  );
}

export const MOTIVOS_ADIAR = ["Chuva", "Veterinário não pode", "Falta de produto", "Falta de gente", "Outro"] as const;
export const MOTIVOS_CANCELAR = ["Mudança de plano", "Veterinário não pode", "Falta de estoque", "Outro motivo"] as const;
export const MOTIVOS_NAO_APLICADO = ["Vendido", "Doente", "Não localizado", "Outro"] as const;
export const MOTIVOS_ESTORNO = ["Errei o animal", "Errei o frasco ou o produto", "A aplicação não aconteceu", "Mudança de plano", "Outro motivo"] as const;
export const MOTIVOS_CIENCIA = ["Vou resolver depois", "Veterinário já combinou", "Não se aplica hoje"] as const;
export const MOTIVOS_ESTOQUE = ["Frasco do veterinário", "Produto já pago e entregue à parte", "Outro"] as const;
export const MOTIVOS_VET = ["Aplico eu mesmo (produtor)", "Aplicação da equipe própria", "Outro"] as const;

export function textoMotivo(escolha: string, outro: string): string {
  return escolha === "Outro" || escolha === "Outro motivo" ? outro.trim() : escolha;
}
