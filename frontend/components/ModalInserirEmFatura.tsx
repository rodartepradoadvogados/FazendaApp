"use client";
// "Inserir em fatura…": notas JÁ lançadas (despesa em aberto, sem parcela paga) entram numa fatura ABERTA do mesmo
// fornecedor. O vencimento/parcelas próprios das notas são substituídos pelo cronograma da fatura.
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, X } from "lucide-react";
import { fetchFaturas, formatBRL, inserirNotasNaFatura, previaInserirNotasNaFatura, type FaturaResumo } from "@/lib/api";
import { Modal } from "@/components/Modal";

export type NotaParaFatura = {
  id: number; numero_lancamento: string | null; fornecedor: string; tipo: string; valor: number;
  tipo_documento: string | null; numero_documento: string | null; data_pagamento: string | null; fatura_id?: number | null;
};

const br = (d: string | null | undefined) => (d ? d.split("-").reverse().join("/") : "—");
const lbl = { display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem" } as const;

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
      {faturas === null ? <p style={{ fontSize: "0.82rem" }}>Carregando…</p> : faturas.length === 0 ? (
        <div>
          <p style={{ fontSize: "0.84rem", marginBottom: "0.8rem" }}>Não há fatura aberta de <strong>{nota.fornecedor}</strong>. Abra uma em Contas › Faturas de fornecedor e volte aqui.</p>
          {onAbrirFaturas && <button type="button" className="btn-primary" onClick={() => { onClose(); onAbrirFaturas(); }}>Ir para Faturas</button>}
        </div>
      ) : (
        <>
          <label style={lbl} htmlFor="ins-fat">Fatura</label>
          <select id="ins-fat" className="input" style={{ width: "100%", padding: "0.35rem 0.5rem", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}
            value={faturaId ?? ""} onChange={(e) => setFaturaId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Selecione…</option>
            {faturas.map((f) => <option key={f.id} value={f.id}>{f.rotulo} — {br(f.data_abertura)} a {br(f.data_fechamento_prevista)} ({f.notas} nota(s))</option>)}
          </select>
          <p style={{ ...lbl, marginTop: "0.9rem" }}>Notas deste fornecedor, em aberto e fora de fatura</p>
          <div style={{ maxHeight: "180px", overflowY: "auto", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.6rem" }}>
            {notas.map((n) => (
              <label key={n.numero} style={{ display: "flex", gap: "0.5rem", alignItems: "center", fontSize: "0.8rem", margin: "0.25rem 0" }}>
                <input type="checkbox" checked={marcadas.has(n.numero)} onChange={() => alternar(n.numero)} />
                <span>{n.numero}</span><span style={{ color: "var(--text-muted)" }}>{n.documento}</span>
                <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums" }}>{formatBRL(n.valor)}</span>
              </label>))}
          </div>
          {previa && (
            <div style={{ marginTop: "0.8rem", fontSize: "0.8rem" }}>
              <p style={{ marginBottom: "0.3rem" }}>Depois de inserir, cada nota segue o cronograma da fatura: {(previa.vencimentos_da_fatura as (string | null)[]).map((v, i, a) => `${a.length > 1 ? `${i + 1}ª ` : ""}${br(v)}`).join(" · ")}.</p>
              <ul style={{ paddingLeft: "1rem", color: "var(--text-muted)" }}>
                {previa.notas.map((n: any) => <li key={n.numero_lancamento}>{n.numero_lancamento}: hoje {n.parcelas_atuais.map((p: any) => `${br(p.vencimento)} ${formatBRL(p.valor)}`).join(", ")}</li>)}
              </ul>
            </div>
          )}
        </>
      )}
      {erro && <div className="alert-critico mt-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {faturas && faturas.length > 0 && (
        <div className="flex gap-3 mt-4">
          <button type="button" className="btn-primary" disabled={salvando || !faturaId || !numeros.length} onClick={inserir}><Check size={14} /> {salvando ? "Inserindo…" : `Inserir ${numeros.length} nota(s)`}</button>
          <button type="button" className="btn-ghost" onClick={onClose}><X size={14} /> Cancelar</button>
        </div>
      )}
    </Modal>
  );
}
