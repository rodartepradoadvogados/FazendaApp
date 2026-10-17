"use client";
// "Definir nova data da visita": o MESMO diálogo na Agenda (comunicado da visita reprodutiva) e na Agenda Reprodutiva
// do Insights (nota "Cenário projetado"). Grava os parâmetros únicos da visita (backend rules/visita_reprodutiva.py) —
// por isso Agenda, projeção, candidatas de IATF e Administração › Parâmetros passam a mostrar as mesmas datas.
import { Modal } from "@/components/Modal";
import { CamposVisitaReprodutiva } from "@/components/reproducao/CamposVisitaReprodutiva";

export function DefinirDataVisitaModal({ dataAtual, origem, intervalo, ultimaVisita, ultimoServico, onClose, onSalvo }: {
  /** Próxima visita hoje (definida ou calculada); null = sem visita. */
  dataAtual: string | null;
  origem: "definida" | "calculada" | null;
  /** Intervalo automático em dias (Parâmetros), só para explicar o cálculo. */
  intervalo?: number | null;
  /** Última visita informada por você, se houver. */
  ultimaVisita?: string | null;
  ultimoServico?: string | null;
  onClose: () => void;
  /** Recebe a data vigente depois de salvar (a definida, ou a calculada quando o usuário voltou ao automático). */
  onSalvo: (proxima: string | null, origem: "definida" | "calculada" | null) => void;
}) {
  return (
    <Modal title="Visita reprodutiva — última e próxima data" onClose={onClose} width="520px">
      <CamposVisitaReprodutiva
        ultimaInformada={ultimaVisita ?? null} proximaDefinida={origem === "definida" ? dataAtual : null}
        proximaAtual={dataAtual} origem={origem} intervalo={intervalo} ultimoServico={ultimoServico}
        onCancelar={onClose}
        onSalvo={(r) => { onSalvo(r.proxima_visita_reprodutiva, r.origem_visita_reprodutiva); onClose(); }} />
    </Modal>
  );
}
