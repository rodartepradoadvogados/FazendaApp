"use client";
// "Inserir em fatura…": notas JÁ lançadas (despesa em aberto, sem parcela paga) entram numa fatura ABERTA do mesmo
// fornecedor. O vencimento/parcelas próprios das notas são substituídos pelo cronograma da fatura.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Info, Layers, X } from "lucide-react";
import { fetchFaturas, formatBRL, inserirNotasNaFatura, previaInserirNotasNaFatura, type FaturaResumo } from "@/lib/api";
import { Modal } from "@/components/Modal";
import { EstiloFatura } from "@/components/financeiro/faturaVisual";

export type NotaParaFatura = {
  id: number; numero_lancamento: string | null; fornecedor: string; tipo: string; valor: number;
  tipo_documento: string | null; numero_documento: string | null; data_pagamento: string | null; fatura_id?: number | null;
};

const br = (d: string | null | undefined) => (d ? d.split("-").reverse().join("/") : "—");

export function ModalInserirEmFatura({ nota, candidatas, onClose, onFeito, onAbrirFaturas }: {
  nota: NotaParaFatura; candidatas: NotaParaFatura[]; onClose: () => void; onFeito: () => void; onAbrirFaturas?: () => void;
}) {
  const [faturas, setFaturas] = useState<FaturaResumo[] | null>(null);
  const [faturaId, setFaturaId] = useState<number | null>(null);
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set([nota.numero_lancamento || ""]));
  const [previa, setPrevia] = useState<any | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  // Uma nota = um número de lançamento (as parcelas dela são linhas diferentes): agrupa por número.
  const notas = useMemo(() => {
    const m = new Map<string, { numero: string; documento: string; valor: number }>();
    const vistos = new Set<number>();
    for (const c of [nota, ...candidatas]) {
      if (vistos.has(c.id)) continue;
      vistos.add(c.id);
      if (!c.numero_lancamento || c.tipo !== "despesa" || c.fatura_id || c.data_pagamento) continue;
      if ((c.fornecedor || "").trim().toLowerCase() !== (nota.fornecedor || "").trim().toLowerCase()) continue;
      const x = m.get(c.numero_lancamento) || { numero: c.numero_lancamento, documento: `${c.tipo_documento || ""} ${c.numero_documento || "s/n"}`.trim(), valor: 0 };
      x.valor += c.valor; m.set(c.numero_lancamento, x);
    }
    return Array.from(m.values());
  }, [nota, candidatas]);

  useEffect(() => {
    fetchFaturas("aberta").then((l) => {
      const doForn = l.filter((f) => f.fornecedor.trim().toLowerCase() === (nota.fornecedor || "").trim().toLowerCase());
      setFaturas(doForn); if (doForn.length === 1) setFaturaId(doForn[0].id);
    }).catch((e) => setErro(e.message));
  }, [nota.fornecedor]);

  const numeros = Array.from(marcadas).filter(Boolean);
  useEffect(() => {
    setPrevia(null);
    if (!faturaId || !numeros.length) return;
    let vivo = true;
    previaInserirNotasNaFatura(faturaId, numeros).then((p) => { if (vivo) { setPrevia(p); setErro(null); } }).catch((e) => { if (vivo) setErro(e.message); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [faturaId, Array.from(marcadas).sort().join("|")]);

  async function inserir() {
    if (!faturaId || !numeros.length) return;
    setSalvando(true); setErro(null);
    try { await inserirNotasNaFatura(faturaId, numeros); onFeito(); onClose(); }
    catch (e: any) { setErro(e.message || "Erro ao inserir."); } finally { setSalvando(false); }
  }
  const alternar = (n: string) => setMarcadas((s) => { const t = new Set(s); if (t.has(n)) t.delete(n); else t.add(n); return t; });

  return (
    <Modal title={`Inserir em fatura — ${nota.fornecedor}`} onClose={onClose} width="680px">
      <EstiloFatura />
      <div className="fv-modal">
        {faturas === null ? <p className="fv-msg" role="status">Carregando…</p> : faturas.length === 0 ? (
          <div className="fv-vazio">
            <Layers size={22} aria-hidden />
            <span>Não há fatura aberta de <strong>{nota.fornecedor}</strong>. Abra uma em Contas › Faturas de fornecedor e volte aqui.</span>
            {onAbrirFaturas && <button type="button" className="btn-primary" style={{ marginTop: "0.4rem" }} onClick={() => { onClose(); onAbrirFaturas(); }}>Ir para Faturas</button>}
          </div>
        ) : (
          <>
            <label className="fv-lbl" htmlFor="ins-fat">Fatura</label>
            <select id="ins-fat" className="fv-in" value={faturaId ?? ""} onChange={(e) => setFaturaId(e.target.value ? Number(e.target.value) : null)}>
              <option value="">Selecione…</option>
              {faturas.map((f) => <option key={f.id} value={f.id}>{f.rotulo} — {br(f.data_abertura)} a {br(f.data_fechamento_prevista)} ({f.notas} nota(s))</option>)}
            </select>
            <fieldset style={{ border: 0, padding: 0, margin: "0.9rem 0 0", minWidth: 0 }}>
              <legend className="fv-lbl">Notas deste fornecedor, em aberto e fora de fatura</legend>
              <div className="fv-checks">
                {notas.map((n) => (
                  <label key={n.numero} className="fv-check">
                    <input type="checkbox" checked={marcadas.has(n.numero)} onChange={() => alternar(n.numero)} />
                    <span style={{ minWidth: 0 }}><span className="fv-num">{n.numero}</span><span className="fv-t2">{n.documento}</span></span>
                    <span className="fv-num fv-forte">{formatBRL(n.valor)}</span>
                  </label>))}
              </div>
            </fieldset>
            {previa && (
              <div className="fv-aviso" aria-live="polite">
                <Info size={16} aria-hidden />
                <div>
                  <b>Depois de inserir, cada nota segue o cronograma da fatura: {(previa.vencimentos_da_fatura as (string | null)[]).map((v, i, a) => `${a.length > 1 ? `${i + 1}ª ` : ""}${br(v)}`).join(" · ")}.</b>
                  <ul>
                    {previa.notas.map((n: any) => <li key={n.numero_lancamento}>{n.numero_lancamento}: hoje {n.parcelas_atuais.map((p: any) => `${br(p.vencimento)} ${formatBRL(p.valor)}`).join(", ")}</li>)}
                  </ul>
                </div>
              </div>
            )}
          </>
        )}
        {erro && <div className="alert-critico mt-3" role="alert"><AlertTriangle size={16} aria-hidden /><span>{erro}</span></div>}
        {faturas && faturas.length > 0 && (
          <div className="fv-rodape">
            <button type="button" className="btn-primary" disabled={salvando || !faturaId || !numeros.length} onClick={inserir}><Check size={14} aria-hidden /> {salvando ? "Inserindo…" : `Inserir ${numeros.length} nota(s)`}</button>
            <button type="button" className="btn-ghost fv-btn" onClick={onClose}><X size={14} aria-hidden /> Cancelar</button>
          </div>
        )}
      </div>
    </Modal>
  );
}
