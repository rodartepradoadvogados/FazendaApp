"use client";
// "Definir nova data da visita": o MESMO diálogo na Agenda (comunicado da visita reprodutiva) e na Agenda Reprodutiva
// do Insights (nota "Cenário projetado"). Grava o parâmetro único da visita (backend rules/visita_reprodutiva.py) —
// por isso Agenda, projeção, candidatas de IATF e Configurações > Parâmetros passam a mostrar a mesma data.
import { useId, useState } from "react";
import { CalendarPlus } from "lucide-react";
import { Modal } from "@/components/Modal";
import { definirVisitaReprodutiva, today } from "@/lib/api";

const fmtDia = (iso: string | null | undefined) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

export function DefinirDataVisitaModal({ dataAtual, origem, intervalo, onClose, onSalvo }: {
  /** Próxima visita hoje (definida ou calculada); null = sem visita. */
  dataAtual: string | null;
  origem: "definida" | "calculada" | null;
  /** Intervalo automático em dias (Parâmetros), só para explicar o cálculo. */
  intervalo?: number | null;
  onClose: () => void;
  /** Recebe a data vigente depois de salvar (a definida, ou a calculada quando o usuário voltou ao automático). */
  onSalvo: (proxima: string | null, origem: "definida" | "calculada" | null) => void;
}) {
  const id = useId();
  const hoje = today();
  const [data, setData] = useState(dataAtual && dataAtual >= hoje ? dataAtual : "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function salvar(novaData: string | null) {
    setSalvando(true); setErro(null);
    try {
      const r = await definirVisitaReprodutiva(novaData);
      onSalvo(r.proxima_visita_reprodutiva, r.origem_visita_reprodutiva);
      onClose();
    } catch (e) { setErro(e instanceof Error ? e.message : "Erro ao salvar."); } finally { setSalvando(false); }
  }

  return (
    <Modal title="Definir nova data da visita reprodutiva" onClose={onClose} width="460px">
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
        {dataAtual
          ? <>Hoje a próxima visita está para <strong style={{ color: "var(--text)" }}>{fmtDia(dataAtual)}</strong>{" "}
              ({origem === "definida" ? "data definida por você" : `calculada: último serviço do rebanho + ${intervalo ?? "N"} dias`}).</>
          : "Não há próxima visita reprodutiva agendada."}
      </p>
      <label htmlFor={id} style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Nova data da visita</label>
      <input id={id} type="date" min={hoje} value={data} onChange={(e) => setData(e.target.value)}
        style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.88rem" }} />
      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", margin: "0.5rem 0 0.8rem" }}>
        Vale para a Agenda (aviso na véspera e no dia), a projeção da Agenda Reprodutiva e as candidatas de IATF — e aparece em
        Configurações › Parâmetros. Passada essa data, a próxima volta a ser calculada até você definir outra.
      </p>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.5rem" }}>{erro}</p>}
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        <button type="button" className="btn-primary" disabled={salvando || !data || data < hoje} onClick={() => salvar(data)}>
          <CalendarPlus size={14} /> {salvando ? "Salvando…" : "Salvar nova data"}
        </button>
        {origem === "definida" && (
          <button type="button" className="btn-ghost" disabled={salvando} onClick={() => salvar(null)}>Voltar ao cálculo automático</button>
        )}
        <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
      </div>
    </Modal>
  );
}
