"use client";
// Pop-up "Carência: o que fazer com o leite?" (§12). Abre quando a carência é
// desconhecida (produto sem estoque, produto trocado sem carência) ou a caixa
// está sem aceite. Só o administrador decide; a decisão vale para o dia (ou o
// lançamento) e fica no registro.
import { useState } from "react";
import { Modal } from "@/components/Modal";
import { AJUDA_MODO_LEITE, MODOS_LEITE, ROTULO_MODO_LEITE, intOuNulo, type CarenciaDecisaoIn, type ModoLeite } from "@/lib/sanitarioTipos";

export function ModalCarencia({ nome, motivo, sugestao, salvando = false, erro, onDecidir, onCancelar }: {
  /** Nome curto da vacina (ex.: "Tifopasteurina"). */
  nome: string;
  /** Por que o sistema está perguntando (texto do back). */
  motivo?: string | null;
  sugestao?: CarenciaDecisaoIn | null;
  salvando?: boolean;
  erro?: string | null;
  onDecidir: (d: { modo: ModoLeite; leite_dias: number | null; carne_dias: number | null }) => void;
  onCancelar: () => void;
}) {
  const [modo, setModo] = useState<ModoLeite>((sugestao?.modo as ModoLeite) || "descarte");
  const [leite, setLeite] = useState(sugestao?.leite_dias != null ? String(sugestao.leite_dias) : "");
  const [carne, setCarne] = useState(sugestao?.carne_dias != null ? String(sugestao.carne_dias) : "");
  return (
    <Modal title={`Carência de ${nome}: o que fazer com o leite?`} onClose={onCancelar} width="580px" zIndex={120}>
      <div className="san-modal-corpo">
        <p className="san-modal-sub">{motivo ? `${motivo} ` : ""}A decisão vale para este dia e fica no registro.</p>
        <div className="san-opcs lista" role="radiogroup" aria-label="Modo do leite">
          {MODOS_LEITE.map((m) => (
            <label key={m} className="san-opc">
              <input type="radio" name="carModo" checked={modo === m} onChange={() => setModo(m)} />
              <span><b>{ROTULO_MODO_LEITE[m]}</b><small>{AJUDA_MODO_LEITE[m]}</small></span>
            </label>
          ))}
        </div>
        <div className="san-linha">
          <div className="san-campo curto">
            <label htmlFor="carL">Leite (dias)</label>
            <input id="carL" className="san-input" type="number" min={0} inputMode="numeric" value={leite}
              onChange={(e) => setLeite(e.target.value)} placeholder="não sei" />
          </div>
          <div className="san-campo curto">
            <label htmlFor="carC">Carne (dias)</label>
            <input id="carC" className="san-input" type="number" min={0} inputMode="numeric" value={carne}
              onChange={(e) => setCarne(e.target.value)} placeholder="não sei" />
          </div>
        </div>
        {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onCancelar}>Cancelar</button>
        <button type="button" className="btn-primary-gold" disabled={salvando}
          onClick={() => onDecidir({ modo, leite_dias: intOuNulo(leite), carne_dias: intOuNulo(carne) })}>
          {salvando ? "Gravando…" : "Decidir e continuar"}
        </button>
      </div>
    </Modal>
  );
}
