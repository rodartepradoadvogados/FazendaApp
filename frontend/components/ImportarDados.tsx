"use client";
import { useCallback, useEffect, useState } from "react";
import { Upload as UploadIcon, Download, CheckCircle, XCircle, FileText, Loader2, FileSpreadsheet, Wand2 } from "lucide-react";
import { fetchModelosImportar, importarCSV, uploadCSV, backfillFornecedoresEstoque } from "@/lib/api";

type Modelo = { label: string; colunas?: string[]; colunas_csv?: string[]; exemplo?: string[]; tipo_upload?: string; precisa_data_controle?: boolean; aceita_excel?: boolean };
type Status = "idle" | "uploading" | "ok" | "error";
type Estado = { status: Status; msg: string };

// Mesma convenção de todo CSV do site: separador ";", Windows-1252. Os
// caracteres acentuados usados aqui (é, ã, ç, º…) têm o mesmo valor de byte
// em Windows-1252 e em Unicode/Latin-1, então basta truncar em 1 byte.
function baixarModeloCSV(nomeArquivo: string, colunas: string[], exemplo?: string[]) {
  const linhas = [colunas.join(";")];
  if (exemplo?.length) linhas.push(exemplo.join(";"));
  const texto = linhas.join("\r\n") + "\r\n";
  const bytes = new Uint8Array(texto.length);
  for (let i = 0; i < texto.length; i++) bytes[i] = texto.charCodeAt(i) & 0xff;
  const blob = new Blob([bytes], { type: "text/csv;charset=windows-1252" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function ImportarDados() {
  const [modelos, setModelos] = useState<{ novas: Record<string, Modelo>; existentes: Record<string, Modelo> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [estados, setEstados] = useState<Record<string, Estado>>({});
  const [dragging, setDragging] = useState<string | null>(null);
  const [datasControle, setDatasControle] = useState<Record<string, string>>({});
  // Campos extras por modalidade (ex.: fonte/rodada do catálogo de touros).
  const [extras, setExtras] = useState<Record<string, Record<string, string>>>({});
  const [backfill, setBackfill] = useState<{ status: "idle" | "rodando" | "ok" | "error"; msg: string; detalhe?: { fornecedores: string[]; estoque: string[] } }>({ status: "idle", msg: "" });

  useEffect(() => { fetchModelosImportar().then(setModelos).catch((e) => setError(e.message)); }, []);

  const rodarBackfill = useCallback(async () => {
    setBackfill({ status: "rodando", msg: "Analisando dados já importados…" });
    try {
      const r = await backfillFornecedoresEstoque();
      setBackfill({
        status: "ok",
        msg: `${r.total_fornecedores_criados} fornecedor(es) e ${r.total_estoque_criados} item(ns) de estoque cadastrados automaticamente.`,
        detalhe: { fornecedores: r.fornecedores_criados, estoque: r.estoque_criados },
      });
    } catch (e: any) {
      setBackfill({ status: "error", msg: e.message });
    }
  }, []);

  const handleNova = useCallback(async (categoria: string, file: File, precisaData?: boolean) => {
    if (precisaData && !datasControle[categoria]) {
      setEstados((p) => ({ ...p, [categoria]: { status: "error", msg: "Escolha a data do controle antes de enviar o arquivo." } }));
      return;
    }
    setEstados((p) => ({ ...p, [categoria]: { status: "uploading", msg: "Enviando…" } }));
    try {
      const extra = precisaData ? { data_controle: datasControle[categoria] } : (extras[categoria] || undefined);
      const res = await importarCSV(categoria, file, extra);
      const partes: string[] = [];
      if (res.criados !== undefined) partes.push(`${res.criados} criados`);
      if (res.atualizados !== undefined) partes.push(`${res.atualizados} atualizados`);
      if (res.erros?.length) partes.push(`${res.erros.length} linha(s) com erro`);
      setEstados((p) => ({ ...p, [categoria]: { status: res.erros?.length ? "error" : "ok", msg: partes.join(" · ") || "Importado com sucesso" } }));
    } catch (e: any) {
      setEstados((p) => ({ ...p, [categoria]: { status: "error", msg: e.message } }));
    }
  }, [datasControle]);

  const handleExistente = useCallback(async (categoria: string, tipoUpload: string, file: File) => {
    setEstados((p) => ({ ...p, [categoria]: { status: "uploading", msg: "Enviando…" } }));
    try {
      const res = await uploadCSV(tipoUpload, file);
      const partes: string[] = [];
      if (res.total !== undefined) partes.push(`${res.total} registros`);
      if (res.inseridos !== undefined) partes.push(`${res.inseridos} inseridos`);
      if (res.atualizados !== undefined) partes.push(`${res.atualizados} atualizados`);
      if (res.servicos !== undefined) partes.push(`${res.servicos} serviços`);
      if (res.partos !== undefined) partes.push(`${res.partos} partos`);
      if (res.registros !== undefined) partes.push(`${res.registros} registros`);
      setEstados((p) => ({ ...p, [categoria]: { status: "ok", msg: partes.join(" · ") || "Importado com sucesso" } }));
    } catch (e: any) {
      setEstados((p) => ({ ...p, [categoria]: { status: "error", msg: e.message } }));
    }
  }, []);

  const Dropzone = ({ id, onFile, accept = ".csv" }: { id: string; onFile: (f: File) => void; accept?: string }) => {
    const estado = estados[id] ?? { status: "idle" as Status, msg: "" };
    return (
      <>
        <label className={`dropzone ${dragging === id ? "active" : ""}`} style={{ cursor: "pointer", display: "block" }}
          onDragOver={(e) => { e.preventDefault(); setDragging(id); }}
          onDragLeave={() => setDragging(null)}
          onDrop={(e) => { e.preventDefault(); setDragging(null); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}>
          <input type="file" accept={accept} style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
          {estado.status === "uploading" ? (
            <div className="flex flex-col items-center gap-2">
              <Loader2 size={24} style={{ color: "var(--vinho-light)", animation: "spin 1s linear infinite" }} />
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Processando…</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2">
              <UploadIcon size={20} style={{ color: "var(--text-muted)" }} />
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                Arraste o CSV ou <span style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>clique para selecionar</span>
              </p>
            </div>
          )}
        </label>
        {estado.status !== "idle" && estado.status !== "uploading" && (
          <div className="flex items-center gap-2 mt-2 p-2 rounded-lg"
            style={{ background: estado.status === "ok" ? "rgba(46,125,82,0.15)" : "rgba(192,57,43,0.15)",
              border: `1px solid ${estado.status === "ok" ? "var(--green)" : "var(--red)"}`, fontSize: "0.78rem" }}>
            {estado.status === "ok" ? <CheckCircle size={15} style={{ color: "var(--green-light)", flexShrink: 0 }} /> : <XCircle size={15} style={{ color: "var(--red)", flexShrink: 0 }} />}
            <span style={{ color: estado.status === "ok" ? "var(--green-light)" : "#E07070" }}>{estado.msg}</span>
          </div>
        )}
      </>
    );
  };

  return (
    <div className="p-6 animate-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2"><FileSpreadsheet size={22} style={{ color: "var(--dourado)" }} /> Importar dados</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Importação manual de dados por CSV — grava direto nas mesmas tabelas usadas no resto do site (nada fica
          isolado). Use quando não tiver o relatório completo do Ideagri, só uma planilha simples com essas colunas.
        </p>
      </div>

      <div className="card mb-6" style={{ borderLeft: "3px solid var(--dourado)" }}>
        <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
          <div>
            <p style={{ fontWeight: 700, fontSize: "0.9rem" }} className="flex items-center gap-2"><Wand2 size={16} style={{ color: "var(--dourado)" }} /> Cadastro automático a partir do que já foi importado</p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginTop: "0.2rem" }}>
              Procura fornecedores e itens de estoque citados em lançamentos financeiros, curva ABC, dieta e sanidade
              que ainda não têm cadastro próprio, e cria o cadastro básico deles automaticamente. Não duplica nada
              que já existe — pode rodar quantas vezes quiser.
            </p>
          </div>
          <button className="btn-primary" style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.4rem", flexShrink: 0 }}
            onClick={rodarBackfill} disabled={backfill.status === "rodando"}>
            {backfill.status === "rodando" ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <Wand2 size={14} />}
            {backfill.status === "rodando" ? "Analisando…" : "Detectar e cadastrar"}
          </button>
        </div>
        {backfill.status !== "idle" && backfill.status !== "rodando" && (
          <div className="flex items-start gap-2 mt-3 p-2 rounded-lg"
            style={{ background: backfill.status === "ok" ? "rgba(46,125,82,0.15)" : "rgba(192,57,43,0.15)",
              border: `1px solid ${backfill.status === "ok" ? "var(--green)" : "var(--red)"}`, fontSize: "0.78rem" }}>
            {backfill.status === "ok" ? <CheckCircle size={15} style={{ color: "var(--green-light)", flexShrink: 0, marginTop: "1px" }} /> : <XCircle size={15} style={{ color: "var(--red)", flexShrink: 0, marginTop: "1px" }} />}
            <div>
              <span style={{ color: backfill.status === "ok" ? "var(--green-light)" : "#E07070" }}>{backfill.msg}</span>
              {backfill.detalhe && (backfill.detalhe.fornecedores.length > 0 || backfill.detalhe.estoque.length > 0) && (
                <p style={{ color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  {backfill.detalhe.fornecedores.length > 0 && <>Fornecedores: {backfill.detalhe.fornecedores.join(", ")}. </>}
                  {backfill.detalhe.estoque.length > 0 && <>Estoque: {backfill.detalhe.estoque.join(", ")}.</>}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {error && <div className="alert-critico mb-4"><span>Sem dados: {error}.</span></div>}
      {!modelos && !error && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {modelos && (
        <>
          <p className="card-header mb-2" style={{ background: "none", padding: 0, fontSize: "0.78rem" }}>Modalidades simplificadas (novas)</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            {Object.entries(modelos.novas).map(([id, m]) => (
              <div key={id} className="card">
                <div className="flex items-start gap-3 mb-2">
                  <FileText size={18} style={{ color: "var(--dourado)", flexShrink: 0, marginTop: "2px" }} />
                  <div>
                    <p style={{ fontWeight: 700, fontSize: "0.9rem" }}>{m.label}</p>
                    <p style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>Colunas: {(m.colunas || []).join(", ")}</p>
                  </div>
                </div>
                {m.colunas_csv && (
                  <button onClick={() => baixarModeloCSV(`modelo_${id}.csv`, m.colunas_csv!, m.exemplo)}
                    className="flex items-center gap-1 mb-3" style={{ fontSize: "0.75rem", color: "var(--dourado-light)", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                    <Download size={13} /> Baixar modelo (com exemplo)
                  </button>
                )}
                {m.precisa_data_controle && (
                  <div className="mb-2">
                    <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>
                      Data do controle (uma só para todo o arquivo)
                    </label>
                    <input type="date" value={datasControle[id] || ""} onChange={(e) => setDatasControle((p) => ({ ...p, [id]: e.target.value }))}
                      style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" }} />
                  </div>
                )}
                {m.aceita_excel && (
                  <div className="grid grid-cols-2 gap-2 mb-2">
                    <div>
                      <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Central (fonte)</label>
                      <input value={extras[id]?.fonte || ""} placeholder="Ex.: Select Sires"
                        onChange={(e) => setExtras((p) => ({ ...p, [id]: { ...(p[id] || {}), fonte: e.target.value } }))}
                        style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" }} />
                    </div>
                    <div>
                      <label style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Rodada da prova</label>
                      <input value={extras[id]?.rodada || ""} placeholder="Ex.: Abr/2026"
                        onChange={(e) => setExtras((p) => ({ ...p, [id]: { ...(p[id] || {}), rodada: e.target.value } }))}
                        style={{ width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem" }} />
                    </div>
                  </div>
                )}
                <Dropzone id={id} accept={m.aceita_excel ? ".csv,.xlsx,.xlsm" : ".csv"} onFile={(f) => handleNova(id, f, m.precisa_data_controle)} />
              </div>
            ))}
          </div>

          <p className="card-header mb-2" style={{ background: "none", padding: 0, fontSize: "0.78rem" }}>Relatórios completos do Ideagri (mesmo parser do Upload CSV)</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(modelos.existentes).map(([id, m]) => (
              <div key={id} className="card">
                <div className="flex items-start gap-3 mb-2">
                  <FileText size={18} style={{ color: "var(--dourado)", flexShrink: 0, marginTop: "2px" }} />
                  <p style={{ fontWeight: 700, fontSize: "0.9rem" }}>{m.label}</p>
                </div>
                {m.colunas_csv && (
                  <button onClick={() => baixarModeloCSV(`modelo_${id}.csv`, m.colunas_csv!, m.exemplo)}
                    className="flex items-center gap-1 mb-3" style={{ fontSize: "0.75rem", color: "var(--dourado-light)", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                    <Download size={13} /> Baixar modelo (com exemplo)
                  </button>
                )}
                <Dropzone id={id} onFile={(f) => handleExistente(id, m.tipo_upload!, f)} />
              </div>
            ))}
          </div>

          <div className="card mt-6" style={{ borderLeft: "3px solid var(--dourado)" }}>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: 1.7 }}>
              <strong style={{ color: "var(--dourado-light)" }}>Formato do arquivo:</strong> mesma convenção do site — separador ponto-e-vírgula (;),
              decimal com vírgula, datas DD/MM/AAAA. Erros de linha não travam o restante do arquivo — o resumo mostra quantas linhas
              deram problema, para você corrigir e reenviar só essas.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
