"use client";
import { useState } from "react";
import { AlertTriangle, Check } from "lucide-react";
import { Modal } from "@/components/Modal";
import { formatBRL } from "@/lib/api";

const inp: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

function arred2(n: number): number {
  return Math.round(n * 100) / 100;
}

export type ItemRedistribuivel = { id: number; label: string; valor: number };
export type AcaoDivergencia = "conceder" | "redistribuir_igual" | "redistribuir_livre";

/**
 * Popup mostrado quando o valor editado de um vale/parcela diverge do valor
 * calculado — pergunta se a diferença é concessão gratuita ou se deve ser
 * redistribuída entre as demais parcelas/etapas pendentes (igualmente, ou com
 * valores lançados livremente). No modo livre, digitar um valor recalcula
 * automaticamente os campos ainda não tocados para a soma continuar batendo.
 */
export function ModalDivergenciaVale({
  valorCalculado, valorInformado, itensPendentes, permiteRedistribuir, onCancelar, onConfirmar, salvando,
}: {
  valorCalculado: number;
  valorInformado: number;
  /** Lista das demais parcelas/etapas pendentes — só é obrigatória pra
   * habilitar "redistribuir com valores livres" (precisa mostrar cada
   * campo). "Redistribuir igualmente" não precisa da lista (o backend já
   * calcula sozinho) — controlado por `permiteRedistribuir`. */
  itensPendentes: ItemRedistribuivel[];
  permiteRedistribuir?: boolean;
  onCancelar: () => void;
  onConfirmar: (acao: AcaoDivergencia, valoresItens?: Record<number, number>) => void;
  salvando?: boolean;
}) {
  const [modo, setModo] = useState<"escolha" | "livre">("escolha");
  const [valores, setValores] = useState<Record<number, string>>({});
  const [tocados, setTocados] = useState<Set<number>>(new Set());

  const diferenca = arred2(valorInformado - valorCalculado);
  const totalAlvo = arred2(itensPendentes.reduce((s, i) => s + i.valor, 0) - diferenca);

  function aoDigitar(id: number, valorStr: string) {
    const novosTocados = new Set(tocados);
    novosTocados.add(id);
    const novosValores = { ...valores, [id]: valorStr };
    const naoTocados = itensPendentes.filter((i) => !novosTocados.has(i.id)).map((i) => i.id);
    const somaTocados = Array.from(novosTocados).reduce((s, tid) => s + (parseFloat(novosValores[tid]) || 0), 0);
    const restante = arred2(totalAlvo - somaTocados);
    if (naoTocados.length) {
      const cada = arred2(restante / naoTocados.length);
      let sobra = restante;
      naoTocados.forEach((iid, idx) => {
        const v = idx < naoTocados.length - 1 ? cada : arred2(sobra);
        sobra = arred2(sobra - v);
        novosValores[iid] = String(Math.max(0, v));
      });
    }
    setTocados(novosTocados);
    setValores(novosValores);
  }

  const confirmarLivre = () => {
    const finais: Record<number, number> = {};
    for (const item of itensPendentes) {
      finais[item.id] = parseFloat(valores[item.id] ?? String(item.valor)) || 0;
    }
    onConfirmar("redistribuir_livre", finais);
  };

  return (
    <Modal title="Valor diferente do calculado" onClose={onCancelar} width="560px">
      <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
        <div className="flex items-start gap-2" style={{ background: "var(--surface-2)", borderRadius: "8px", padding: "0.7rem 0.9rem" }}>
          <AlertTriangle size={16} style={{ color: "var(--dourado)", flexShrink: 0, marginTop: "0.1rem" }} />
          <div style={{ fontSize: "0.85rem" }}>
            <p style={{ marginBottom: "0.3rem" }}>O valor informado é diferente do valor calculado.</p>
            <p>Valor calculado: <b>{formatBRL(valorCalculado)}</b></p>
            <p>Valor informado: <b>{formatBRL(valorInformado)}</b></p>
            <p>Diferença: <b style={{ color: diferenca >= 0 ? "var(--green-light)" : "var(--red)" }}>{formatBRL(diferenca)}</b></p>
          </div>
        </div>

        {modo === "escolha" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <button className="btn-ghost" style={{ textAlign: "left", padding: "0.6rem 0.8rem" }}
              disabled={salvando} onClick={() => onConfirmar("conceder")}>
              <b>Concessão gratuita</b>
              <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                Só esta parcela muda — a diferença fica perdoada, sem afetar as demais.
              </div>
            </button>
            {(permiteRedistribuir ?? itensPendentes.length > 0) && (
              <button className="btn-ghost" style={{ textAlign: "left", padding: "0.6rem 0.8rem" }}
                disabled={salvando} onClick={() => onConfirmar("redistribuir_igual")}>
                <b>Redistribuir igualmente</b>
                <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                  {itensPendentes.length > 0
                    ? `Divide a diferença entre as ${itensPendentes.length} parcela(s) pendente(s), em partes iguais.`
                    : "Divide a diferença entre as demais parcelas/etapas pendentes, em partes iguais."}
                </div>
              </button>
            )}
            {itensPendentes.length > 0 && (
              <button className="btn-ghost" style={{ textAlign: "left", padding: "0.6rem 0.8rem" }}
                disabled={salvando} onClick={() => setModo("livre")}>
                <b>Redistribuir com valores livres</b>
                <div style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                  Você escolhe o valor de cada parcela pendente.
                </div>
              </button>
            )}
          </div>
        )}

        {modo === "livre" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Ao digitar o valor de uma parcela, as demais ainda não editadas se recalculam automaticamente.
            </p>
            {itensPendentes.map((item) => (
              <div key={item.id}>
                <label style={lbl}>{item.label}</label>
                <input type="number" inputMode="decimal" style={inp}
                  value={valores[item.id] ?? String(item.valor)}
                  onChange={(e) => aoDigitar(item.id, e.target.value)} />
              </div>
            ))}
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.3rem" }}>
              <button className="btn-primary" disabled={salvando} onClick={confirmarLivre}>
                <Check size={14} /> {salvando ? "Salvando…" : "Confirmar"}
              </button>
              <button className="btn-ghost" onClick={() => setModo("escolha")}>Voltar</button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

/** Popup final — mostrado quando, depois da edição, a soma das
 * parcelas/abatimentos fica diferente do valor efetivamente pago no vale. */
export function ModalResultadoDivergenciaVale({
  valorPago, valorDesconto, onFechar,
}: { valorPago: number; valorDesconto: number; onFechar: () => void }) {
  const diferenca = arred2(valorDesconto - valorPago);
  return (
    <Modal title="Valor do vale diferente do desconto" onClose={onFechar} width="440px">
      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.85rem" }}>
        <p>O valor total dos descontos ficou diferente do valor efetivamente pago no vale.</p>
        <p>Valor do vale: <b>{formatBRL(valorPago)}</b></p>
        <p>Valor do desconto: <b>{formatBRL(valorDesconto)}</b></p>
        <p>Diferença: <b style={{ color: diferenca >= 0 ? "var(--green-light)" : "var(--red)" }}>{formatBRL(diferenca)}</b></p>
        <button className="btn-primary" style={{ alignSelf: "flex-start", marginTop: "0.3rem" }} onClick={onFechar}>Entendi</button>
      </div>
    </Modal>
  );
}
