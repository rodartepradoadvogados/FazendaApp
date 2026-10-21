import { Syringe } from "lucide-react";

/**
 * Ponto de encaixe do Sanitário Preventivo v2 (vacinas e exames).
 *
 * O módulo preventivo antigo (calendário sanitário, cronogramas, lista de
 * espera, ocorrências, gavetas Aplicar/Exame) foi removido na fase F2 do plano
 * "Sanitário Preventivo v2". Cada lugar onde o módulo novo vai entrar mostra
 * este aviso até a tela definitiva ser criada (fases F6/F7). Não chama nenhuma
 * API de propósito: é só um marcador honesto, para ser substituído.
 */
export default function EmConstrucao({
  titulo,
  descricao,
  compacto = false,
}: {
  /** Nome da tela que vai ocupar este lugar (ex.: "Calendário sanitário"). */
  titulo: string;
  /** Uma frase opcional sobre o que a tela nova vai fazer. */
  descricao?: string;
  /** Versão de uma linha, para cards e menus pequenos. */
  compacto?: boolean;
}) {
  if (compacto) {
    return (
      <div className="empty-state" data-sanitario-em-construcao={titulo}>
        <Syringe size={18} />
        <div>
          <strong>{titulo}</strong> — Módulo novo em implantação.
        </div>
      </div>
    );
  }
  return (
    <div className="card" data-sanitario-em-construcao={titulo}>
      <div className="empty-state">
        <Syringe size={22} />
        <div>
          <strong>{titulo}</strong>
          <div>Módulo novo em implantação.</div>
          {descricao && (
            <div style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: "0.3rem" }}>{descricao}</div>
          )}
        </div>
      </div>
    </div>
  );
}
