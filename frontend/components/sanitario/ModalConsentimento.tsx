"use client";
// Pop-up de AVISO E CONSENTIMENTO (§12: nunca trava). Lista quem não cumpre a
// regra e por quê (o motivo vem do back), deixa tirar algum da lista, pede o
// "Estou ciente" e — quando a vacina/exame não tem atestado configurado —
// pergunta "Quer fazer atestado destes animais?". O consentimento fica no
// registro (log) com o nome, a data e o motivo exibido.
import { useState } from "react";
import { Modal } from "@/components/Modal";
import type { ConsentimentoIn } from "@/lib/sanitarioTipos";

export type ItemConsentimento = {
  animal_id: number; numero: string | null; caixa_id?: number | null; caixa?: string | null; motivo: string;
};
export type RespostaConsentimento = {
  /** Consentimentos dados (vão no corpo do reenvio). */
  aceitos: ConsentimentoIn[];
  /** Pares que a pessoa tirou da lista (a tela remove da seleção). */
  recusados: { animal_id: number; caixa_id: number | null }[];
};

export function ModalConsentimento({ itens, perguntarAtestado = false, nomesSemAtestado, onConfirmar, onVoltar }: {
  itens: ItemConsentimento[];
  /** true quando alguma vacina/exame envolvida não tem atestado configurado. */
  perguntarAtestado?: boolean;
  nomesSemAtestado?: string;
  onConfirmar: (r: RespostaConsentimento) => void;
  onVoltar: () => void;
}) {
  const chave = (i: ItemConsentimento) => `${i.animal_id}|${i.caixa_id ?? ""}`;
  const [incluir, setIncluir] = useState<Set<string>>(() => new Set(itens.map(chave)));
  const [ciente, setCiente] = useState(false);
  const [atestado, setAtestado] = useState<"sim" | "nao">("nao");
  const [destinatario, setDestinatario] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const animais = new Set(itens.map((i) => i.animal_id)).size;
  const marcados = itens.filter((i) => incluir.has(chave(i)));

  function confirmar() {
    if (marcados.length && !ciente) { setErro("Marque “Estou ciente” para incluir. Ou desmarque esses animais."); return; }
    const quer = perguntarAtestado ? atestado === "sim" : null;
    onConfirmar({
      aceitos: marcados.map((i) => ({
        animal_id: i.animal_id, caixa_id: i.caixa_id ?? null, aceito: true, motivo_exibido: i.motivo,
        quer_atestado: quer, atestado_destinatario: quer && destinatario.trim() ? destinatario.trim() : null,
      })),
      recusados: itens.filter((i) => !incluir.has(chave(i))).map((i) => ({ animal_id: i.animal_id, caixa_id: i.caixa_id ?? null })),
    });
  }

  return (
    <Modal title={`${animais} ${animais > 1 ? "animais não cumprem" : "animal não cumpre"} a regra`} onClose={onVoltar} width="620px" zIndex={120}>
      <div className="san-modal-corpo">
        <p className="san-modal-sub">O sistema avisa e pede o seu consentimento. Não trava.</p>
        <div className="san-opcs lista" role="group" aria-label="Animais fora da regra">
          {itens.map((i) => (
            <label key={chave(i)} className="san-opc">
              <input type="checkbox" checked={incluir.has(chave(i))} onChange={(e) => {
                setIncluir((p) => { const n = new Set(p); if (e.target.checked) n.add(chave(i)); else n.delete(chave(i)); return n; });
              }} />
              <span><b className="san-num">{i.numero || `#${i.animal_id}`}</b>{i.caixa ? <> · {i.caixa}</> : null}
                <small>{i.motivo}</small></span>
            </label>
          ))}
        </div>
        {perguntarAtestado && marcados.length > 0 && (
          <div className="san-campo">
            <span className="san-rot">{nomesSemAtestado ? `${nomesSemAtestado} não tem atestado configurado. ` : ""}Quer fazer atestado destes animais?</span>
            <div className="san-linha">
              <div className="san-seg" role="group" aria-label="Quer atestado">
                <button type="button" aria-pressed={atestado === "sim"} onClick={() => setAtestado("sim")}>Sim</button>
                <button type="button" aria-pressed={atestado === "nao"} onClick={() => setAtestado("nao")}>Não</button>
              </div>
              {atestado === "sim" && (
                <div className="san-campo">
                  <label htmlFor="cDest">Para quem (opcional)</label>
                  <input id="cDest" className="san-input" value={destinatario} onChange={(e) => setDestinatario(e.target.value)}
                    placeholder="ex.: Agrodefesa, laticínio, comprador" />
                </div>
              )}
            </div>
          </div>
        )}
        {marcados.length > 0 && (
          <label className="san-liga">
            <input type="checkbox" checked={ciente} onChange={(e) => { setCiente(e.target.checked); setErro(null); }} />
            <span><b>Estou ciente e quero incluir mesmo assim.</b><small>O seu nome, a data e o motivo ficam no registro.</small></span>
          </label>
        )}
        {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button>
        <button type="button" className="btn-primary-gold" onClick={confirmar}>
          {marcados.length ? "Incluir com consentimento" : "Continuar sem eles"}
        </button>
      </div>
    </Modal>
  );
}
