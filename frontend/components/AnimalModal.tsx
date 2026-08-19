"use client";
import { X } from "lucide-react";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

export type AnimalRow = {
  numero: string;
  grupo_primario?: string | null;
  categoria_abrev?: string | null;
  categoria_completa?: string | null;
  raca?: string | null;
  sit_rep?: string | null;
  del_dias?: number | null;
  /** @deprecated Campo congelado do CSV do Ideagri — prefira `producao_kg`. */
  ult_cl_kg?: number | null;
  // Produção AO VIVO (ver AnimalProducaoAoVivo em lib/api.ts): do último
  // ControleLeiteiro lançado no app, caindo para `ult_cl_kg` só enquanto o
  // backend novo não estiver publicado.
  producao_kg?: number | null;
  producao_data?: string | null;
  producao_origem?: "controle" | "congelado" | null;
  data_ult_servico_pos?: string | null;
  data_ult_parto?: string | null;
  a_descartar?: boolean;
};

const SIT_CORES: Record<string, string> = {
  "Ges.": "var(--green-light)", "Vaz. apt.": "var(--blue)", "Vaz. atr.": "var(--red)",
  "Vaz. pev": "var(--amber)", "Ins.": "var(--dourado-light)",
  Gestante: "var(--green-light)", Inseminada: "var(--dourado-light)", "Em protocolo (IA atual)": "var(--dourado-light)",
  PEV: "var(--amber)", Apta: "var(--blue)", Atrasada: "var(--red)", "Não apta": "var(--text-muted)", Vazia: "var(--blue)",
};

// Estados "vazia" ao vivo — equivalem ao antigo prefixo textual "Vaz." usado
// para decidir se calcula PEV (dias desde o último parto).
const ESTADOS_VAZIA = new Set(["pev", "apta", "atrasada", "nao_apta", "vazia"]);

const GESTACAO = 280;
const diasEntre = (aIso: string, bIso: string) =>
  Math.round((new Date(bIso + "T00:00:00").getTime() - new Date(aIso + "T00:00:00").getTime()) / 86400000);

// Indicadores reprodutivos por animal, calculados das datas de serviço/parto.
// `estado` é o estado reprodutivo AO VIVO (chave do backend, não o rótulo).
function repro(a: AnimalRow, estado: string | undefined) {
  const hoje = new Date().toISOString().slice(0, 10);
  let gestacao: number | null = null, paraParto: number | null = null, partoData: string | null = null, pev: number | null = null;
  if (estado === "gestante" && a.data_ult_servico_pos) {
    gestacao = diasEntre(a.data_ult_servico_pos, hoje);
    const p = new Date(a.data_ult_servico_pos + "T00:00:00"); p.setDate(p.getDate() + GESTACAO);
    partoData = p.toLocaleDateString("pt-BR");
    paraParto = Math.round((p.getTime() - new Date(hoje + "T00:00:00").getTime()) / 86400000);
  }
  if (estado && ESTADOS_VAZIA.has(estado) && a.data_ult_parto) pev = diasEntre(a.data_ult_parto, hoje);
  return { gestacao, paraParto, partoData, pev };
}

/** Modal que lista os animais por trás de um número (drill-down). */
export function AnimalModal({ title, animais, onClose }: { title: string; animais: AnimalRow[]; onClose: () => void }) {
  const temRepro = animais.some((a) => a.data_ult_servico_pos || a.data_ult_parto);
  // Só aparece quando a lista traz produção (nem todo drill-down é sobre
  // vacas em lactação) — quando aparece, aproveita para já vir com a origem:
  // "*" marca quem ainda está no valor congelado do CSV, sem controle no app.
  const temProducao = animais.some((a) => a.producao_kg != null);
  const { porNumero, rotuloDe } = useEstadosReprodutivos();
  const ord = useOrdenacao(animais);
  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }}
    >
      <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: temRepro ? "820px" : "640px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>{title} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({animais.length})</span></div>
          <button onClick={onClose} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
        </div>
        <div style={{ overflowY: "auto" }}>
          {animais.length ? (
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Nº" campo="numero" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Grupo" campo="grupo_primario" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Categoria" campo="categoria_abrev" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <th>Sit. Rep.</th>
                <ThOrdenavel label="DEL" campo="del_dias" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
                {temProducao && <ThOrdenavel label="Produção (kg)" campo="producao_kg" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />}
                {temRepro && <><th style={{ textAlign: "right" }}>Gest.</th><th style={{ textAlign: "right" }}>P/ parto</th><th>Parto prov.</th><th style={{ textAlign: "right" }}>PEV</th></>}
              </tr></thead>
              <tbody>
                {ord.linhasOrdenadas.map((a) => {
                  const r = repro(a, porNumero.get(a.numero)?.estado);
                  const congelado = a.producao_origem === "congelado";
                  return (
                    <tr key={a.numero}>
                      <td style={{ fontWeight: 700 }}>{a.numero}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.grupo_primario || "—"}</td>
                      <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
                      <td><span style={{ color: SIT_CORES[rotuloDe(a.numero)] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{rotuloDe(a.numero)}</span></td>
                      <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                      {temProducao && (
                        <td style={{ textAlign: "right", fontWeight: 600, color: congelado ? "var(--text-muted)" : undefined }}
                          title={congelado ? "Valor do último CSV importado — nenhum controle leiteiro lançado no app para este animal" : undefined}>
                          {a.producao_kg != null ? `${a.producao_kg.toFixed(1)}${congelado ? " *" : ""}` : "—"}
                        </td>
                      )}
                      {temRepro && <>
                        <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{r.gestacao != null ? `${r.gestacao}d` : "—"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.78rem", color: r.paraParto != null && r.paraParto <= 30 ? "var(--green-light)" : undefined }}>{r.paraParto != null ? `${r.paraParto}d` : "—"}</td>
                        <td style={{ fontSize: "0.75rem" }}>{r.partoData || "—"}</td>
                        <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{r.pev != null ? `${r.pev}d` : "—"}</td>
                      </>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", padding: "1rem" }}>Nenhum animal.</p>}
        </div>
      </div>
    </div>
  );
}
