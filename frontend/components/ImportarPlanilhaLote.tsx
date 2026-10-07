"use client";
// Importa notas de uma planilha (.xlsx/.csv) para o Lançamento em lote: lê, agrupa em notas, mostra a prévia
// com erros e avisos e só então carrega no formulário (nada é gravado aqui).
import { useState } from "react";
import { AlertTriangle, Download, FileSpreadsheet, Check, X } from "lucide-react";
import { formatBRL } from "@/lib/api";
import { Modal } from "@/components/Modal";
import { baixarModeloPlanilha, interpretarLinhas, lerArquivoPlanilha, type ContaRef, type ResultadoImportacao } from "@/lib/planilhaLote";

const br = (d: string) => d.split("-").reverse().join("/");

export function ImportarPlanilhaLote({ contas, produtos, formularioVazio, onClose, onCarregar }: {
  contas: ContaRef[]; produtos: string[]; formularioVazio: boolean; onClose: () => void;
  onCarregar: (r: ResultadoImportacao, substituir: boolean) => void;
}) {
  const [res, setRes] = useState<ResultadoImportacao | null>(null);
  const [nomeArquivo, setNomeArquivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [lendo, setLendo] = useState(false);
  const [substituir, setSubstituir] = useState(formularioVazio);

  async function escolher(f: File | undefined) {
    if (!f) return;
    setErro(null); setRes(null); setNomeArquivo(f.name); setLendo(true);
    try { setRes(interpretarLinhas(await lerArquivoPlanilha(f), contas, produtos)); }
    catch (e: any) { setErro(e.message || "Não consegui ler o arquivo."); } finally { setLendo(false); }
  }
  const total = (r: ResultadoImportacao) => r.notas.reduce((s, n) => s + n.itens.reduce((a, i) => a + (Number(i.qtd.replace(",", ".")) || 0) * i.unit, 0) - n.desconto + n.acrescimo, 0);

  return (
    <Modal title="Importar planilha de notas" onClose={onClose} width="760px">
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>
        Uma linha por item; as linhas da mesma nota ficam juntas. Nada é lançado agora: as notas entram no formulário para você revisar.
      </p>
      <div className="flex flex-wrap gap-3 items-center">
        <button type="button" className="btn-secondary" onClick={() => baixarModeloPlanilha()}><Download size={14} /> Baixar modelo (.xlsx)</button>
        <label className="btn-primary" style={{ cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
          <FileSpreadsheet size={14} /> Escolher arquivo (.xlsx ou .csv)
          <input type="file" accept=".xlsx,.csv,.txt" aria-label="Arquivo da planilha" style={{ display: "none" }} onChange={(e) => { escolher(e.target.files?.[0]); e.target.value = ""; }} />
        </label>
        {nomeArquivo && <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{nomeArquivo}</span>}
      </div>
      {lendo && <p style={{ fontSize: "0.8rem", marginTop: "0.7rem" }}>Lendo…</p>}
      {erro && <div className="alert-critico mt-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {res && (
        <div className="mt-3">
          {res.erros.length > 0 && (
            <div className="alert-critico" style={{ display: "block" }}>
              <strong style={{ fontSize: "0.82rem" }}>Corrija na planilha e escolha o arquivo de novo ({res.erros.length}):</strong>
              <ul style={{ paddingLeft: "1rem", marginTop: "0.3rem", fontSize: "0.8rem", maxHeight: "140px", overflowY: "auto" }}>
                {res.erros.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </div>
          )}
          {res.avisos.length > 0 && (
            <div style={{ border: "1px solid var(--amber)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem", fontSize: "0.78rem", marginTop: "0.6rem" }}>
              <strong>Atenção ({res.avisos.length}) — dá para ajustar na tela depois:</strong>
              <ul style={{ paddingLeft: "1rem", marginTop: "0.25rem", maxHeight: "110px", overflowY: "auto" }}>{res.avisos.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </div>
          )}
          {res.notas.length > 0 && (
            <>
              <p style={{ fontSize: "0.82rem", margin: "0.7rem 0 0.3rem" }}><strong>{res.notas.length}</strong> nota(s), <strong>{formatBRL(total(res))}</strong> no total</p>
              <div style={{ maxHeight: "200px", overflowY: "auto", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
                <table style={{ width: "100%", fontSize: "0.78rem" }}>
                  <thead><tr style={{ textAlign: "left", color: "var(--text-muted)" }}><th style={{ padding: "0.3rem 0.5rem" }}>Documento</th><th>Data</th><th>Itens</th><th style={{ textAlign: "right", paddingRight: "0.5rem" }}>Valor</th></tr></thead>
                  <tbody>{res.notas.map((n, i) => {
                    const v = n.itens.reduce((a, it) => a + (Number(it.qtd.replace(",", ".")) || 0) * it.unit, 0) - n.desconto + n.acrescimo;
                    return <tr key={i} style={{ borderTop: "1px solid var(--border)" }}><td style={{ padding: "0.3rem 0.5rem" }}>{n.tipoDoc} {n.numero || "s/n"}</td><td>{br(n.data)}</td><td>{n.itens.length}</td><td style={{ textAlign: "right", paddingRight: "0.5rem", fontVariantNumeric: "tabular-nums" }}>{formatBRL(v)}</td></tr>;
                  })}</tbody>
                </table>
              </div>
              {!formularioVazio && (
                <div className="flex gap-4 mt-2" style={{ fontSize: "0.8rem" }}>
                  <label style={{ display: "flex", gap: "0.3rem", alignItems: "center", margin: 0 }}><input type="radio" name="imp-modo" checked={!substituir} onChange={() => setSubstituir(false)} /> Acrescentar às notas do formulário</label>
                  <label style={{ display: "flex", gap: "0.3rem", alignItems: "center", margin: 0 }}><input type="radio" name="imp-modo" checked={substituir} onChange={() => setSubstituir(true)} /> Substituir as notas do formulário</label>
                </div>
              )}
            </>
          )}
        </div>
      )}
      <div className="flex gap-3 mt-4">
        <button type="button" className="btn-primary" disabled={!res || res.erros.length > 0 || res.notas.length === 0} onClick={() => res && onCarregar(res, substituir)}>
          <Check size={14} /> Carregar no formulário</button>
        <button type="button" className="btn-ghost" onClick={onClose}><X size={14} /> Cancelar</button>
      </div>
    </Modal>
  );
}
