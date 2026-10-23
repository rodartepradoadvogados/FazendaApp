"use client";
// Painel de RISCOS de marcar numa data diferente da prevista (§4.3): o back
// simula os animais na nova data (POST /sanitario/dias/simular) e devolve
// quem sai da janela, quem passa da idade, quem pare antes e quem ENTRA até a
// nova data. A pessoa decide: manter a nova data, ajustar os animais ou
// dividir em dois dias. A decisão vai no corpo (`decisao_riscos`) e fica no log.
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { fmtData, diaSemana, type DecisaoRiscos, type Simulacao } from "@/lib/sanitarioTipos";

export type EscolhaRiscos = DecisaoRiscos["decisao"];
const OPCOES: { id: EscolhaRiscos; titulo: string; ajuda: (prev: string) => string }[] = [
  { id: "manter", titulo: "Manter a nova data", ajuda: () => "Os riscos ficam registrados." },
  { id: "ajustar", titulo: "Ajustar os animais", ajuda: () => "Tira da lista quem sai da janela; inclui quem entra, se marcar." },
  { id: "dividir", titulo: "Dividir em dois dias", ajuda: (p) => `Quem sai fica num dia na data prevista (${fmtData(p, true)}).` },
];

/** Há algo para decidir nesta simulação? */
export function temRiscos(sim: Simulacao | null | undefined): boolean {
  return !!sim && (sim.riscos.length > 0 || sim.entram.length > 0);
}
/** Animais em risco (saem da janela na nova data). */
export function idsEmRisco(sim: Simulacao | null | undefined): Set<number> {
  return new Set((sim?.riscos || []).flatMap((r) => r.animal_ids));
}
/** Texto curto da decisão para o log. */
export function textoDecisao(sim: Simulacao, escolha: EscolhaRiscos, incluirEntrantes: boolean): string {
  const base = escolha === "manter" ? "manter a nova data" : escolha === "ajustar" ? "ajustar os animais" : "dividir em dois dias";
  const r = sim.riscos.map((x) => x.texto).join(" ");
  const txt = `${base}${incluirEntrantes && sim.entram.length ? `, incluindo ${sim.entram.length} que entram` : ""}`
    + ` · prevista ${fmtData(sim.data_prevista, true)}${r ? ` · riscos: ${r}` : ""}`;
  return txt.slice(0, 900);
}

export function PainelRiscos({ sim, escolha, onEscolha, incluirEntrantes, onIncluirEntrantes, onVoltarPrevista, carregando }: {
  sim: Simulacao | null;
  escolha: EscolhaRiscos;
  onEscolha: (e: EscolhaRiscos) => void;
  incluirEntrantes: boolean;
  onIncluirEntrantes: (v: boolean) => void;
  onVoltarPrevista?: () => void;
  carregando?: boolean;
}) {
  if (carregando) return <div className="skeleton" style={{ height: "4.5rem" }} role="status" aria-label="Simulando a nova data" />;
  if (!sim) return null;
  if (sim.data === sim.data_prevista) return null;
  if (!temRiscos(sim)) {
    return (
      <div className="san-faixa ok" role="status">
        <CheckCircle2 size={16} aria-hidden="true" />
        <div>Nova data simulada ({fmtData(sim.data, true)} em vez de {fmtData(sim.data_prevista, true)}): ninguém sai e ninguém entra.</div>
      </div>
    );
  }
  return (
    <div className="san-faixa atencao" role="status">
      <AlertTriangle size={16} aria-hidden="true" />
      <div style={{ flex: 1, minWidth: 0 }}>
        <b>Riscos de marcar em {diaSemana(sim.data)} {fmtData(sim.data, true)} em vez de {diaSemana(sim.data_prevista)} {fmtData(sim.data_prevista, true)}</b>
        <span className="san-nota"> (simulação dos animais na nova data)</span>
        <ul>
          {sim.riscos.map((r, i) => <li key={i}>{r.texto}</li>)}
          {sim.entram.length > 0 && (
            <li>
              {sim.entram.length} {sim.entram.length > 1 ? "animais entram" : "animal entra"} na janela até a nova data
              ({sim.entram.slice(0, 12).map((e) => e.numero).join(", ")}{sim.entram.length > 12 ? "…" : ""}).{" "}
              <label style={{ display: "inline-flex", gap: 6, alignItems: "center", fontWeight: 700 }}>
                <input type="checkbox" checked={incluirEntrantes} onChange={(e) => onIncluirEntrantes(e.target.checked)} /> Incluir
              </label>
            </li>
          )}
        </ul>
        <div className="san-opcs" role="radiogroup" aria-label="Decisão sobre a data" style={{ marginTop: "0.5rem" }}>
          {OPCOES.map((o) => (
            <label key={o.id} className="san-opc">
              <input type="radio" name="decRiscos" checked={escolha === o.id} onChange={() => onEscolha(o.id)} />
              <span><b>{o.titulo}</b><small>{o.ajuda(sim.data_prevista)}</small></span>
            </label>
          ))}
        </div>
        {onVoltarPrevista && (
          <button type="button" className="san-link" style={{ marginTop: "0.5rem" }} onClick={onVoltarPrevista}>
            Voltar para a data prevista ({fmtData(sim.data_prevista, true)})
          </button>
        )}
      </div>
    </div>
  );
}
