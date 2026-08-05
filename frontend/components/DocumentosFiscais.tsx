"use client";
// Arquivo fiscal-contábil — versão para o site normal (dono/admin), reaproveitando
// os mesmos endpoints /documentos usados no Painel do Contador (ver
// backend/fazenda/api/routers/documentos.py e components/contador/PainelDocumentos.tsx,
// que é a versão com a casca visual própria do contador).
import { useEffect, useState } from "react";
import { Download, Trash2, UploadCloud } from "lucide-react";
import {
  fetchCategoriasDocumento, fetchDocumentos, enviarDocumento, baixarDocumento, excluirDocumento,
  type DocumentoArquivado,
} from "@/lib/api";
import { Dropzone } from "@/components/Dropzone";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "6px", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};
const labelStyle: React.CSSProperties = {
  fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem",
  textTransform: "uppercase", letterSpacing: "0.05em",
};

function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentosFiscais() {
  const [categorias, setCategorias] = useState<string[]>([]);
  const [documentos, setDocumentos] = useState<DocumentoArquivado[]>([]);
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const [arquivo, setArquivo] = useState<File | null>(null);
  const [categoria, setCategoria] = useState("");
  const [inserirNoBalanco, setInserirNoBalanco] = useState<"sim" | "nao">("nao");
  const [numeroLancamento, setNumeroLancamento] = useState("");
  const [dataDocumento, setDataDocumento] = useState("");
  const [descricao, setDescricao] = useState("");
  const [enviando, setEnviando] = useState(false);

  const recarregar = () => {
    setCarregando(true);
    fetchDocumentos(filtroCategoria ? { categoria: filtroCategoria } : undefined)
      .then(setDocumentos).catch((e) => setErro(e.message)).finally(() => setCarregando(false));
  };

  useEffect(() => { fetchCategoriasDocumento().then(setCategorias).catch(() => setCategorias([])); }, []);
  useEffect(recarregar, [filtroCategoria]);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!arquivo || !categoria) return;
    setEnviando(true); setErro(null);
    try {
      await enviarDocumento({
        file: arquivo, categoria, inserirNoBalanco: inserirNoBalanco === "sim",
        numeroLancamento: numeroLancamento || undefined, dataDocumento: dataDocumento || undefined,
        descricao: descricao || undefined,
      });
      setArquivo(null); setCategoria(""); setInserirNoBalanco("nao"); setNumeroLancamento(""); setDataDocumento(""); setDescricao("");
      recarregar();
    } catch (e: any) {
      setErro(e.message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={{ display: "grid", gap: "1.2rem" }}>
      <div className="card">
        <p style={{ margin: "0 0 0.9rem", fontWeight: 700, fontSize: "0.9rem" }}>Arquivar novo documento</p>
        <form onSubmit={enviar} style={{ display: "grid", gap: "0.8rem", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))" }}>
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={labelStyle}>Arquivo (PDF, XML, PNG, JPEG...)</label>
            <Dropzone
              compact
              label={arquivo ? arquivo.name : "Arraste o arquivo aqui, ou"}
              onFiles={(files) => setArquivo(files[0])}
            />
          </div>
          <div>
            <label style={labelStyle}>Categoria</label>
            <select style={inputStyle} value={categoria} onChange={(e) => setCategoria(e.target.value)} required>
              <option value="">Selecione…</option>
              {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label style={labelStyle}>Inserir no balanço?</label>
            <select style={inputStyle} value={inserirNoBalanco} onChange={(e) => setInserirNoBalanco(e.target.value as "sim" | "nao")}>
              <option value="nao">Não</option>
              <option value="sim">Sim</option>
            </select>
          </div>
          {inserirNoBalanco === "sim" ? (
            <div>
              <label style={labelStyle}>Nº do lançamento (se já existir)</label>
              <input style={inputStyle} value={numeroLancamento} onChange={(e) => setNumeroLancamento(e.target.value)} placeholder="opcional" />
            </div>
          ) : (
            <div>
              <label style={labelStyle}>Data do documento</label>
              <input type="date" style={inputStyle} value={dataDocumento} onChange={(e) => setDataDocumento(e.target.value)} />
            </div>
          )}
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={labelStyle}>Descrição (opcional)</label>
            <input style={inputStyle} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <button type="submit" className="btn-primary" disabled={!arquivo || !categoria || enviando}
              style={{ opacity: !arquivo || !categoria || enviando ? 0.6 : 1 }}>
              <UploadCloud size={14} /> {enviando ? "Arquivando…" : "Arquivar documento"}
            </button>
          </div>
        </form>
        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      </div>

      <div className="card" style={{ overflowX: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.8rem" }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: "0.9rem" }}>Documentos arquivados</p>
          <select style={{ ...inputStyle, width: "auto" }} value={filtroCategoria} onChange={(e) => setFiltroCategoria(e.target.value)}>
            <option value="">Todas as categorias</option>
            {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {carregando ? <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Carregando…</p> : (
          <table className="fazenda-table">
            <thead>
              <tr>
                <th>Arquivo</th><th>Categoria</th><th>Tamanho</th>
                <th>Enviado em</th><th>Balanço</th><th></th>
              </tr>
            </thead>
            <tbody>
              {documentos.map((d) => (
                <tr key={d.id}>
                  <td>{d.nome_original}{d.descricao && <span style={{ color: "var(--text-muted)" }}> — {d.descricao}</span>}</td>
                  <td>{d.categoria}</td>
                  <td>{formatarTamanho(d.tamanho_bytes)}</td>
                  <td>{new Date(d.data_upload).toLocaleDateString("pt-BR")}</td>
                  <td style={{ color: d.inserir_no_balanco ? "var(--green-light)" : "var(--text-muted)" }}>{d.inserir_no_balanco ? "Sim" : "Não"}</td>
                  <td style={{ display: "flex", gap: "0.6rem" }}>
                    <button type="button" onClick={() => baixarDocumento(d.id, d.nome_original)} title="Baixar"
                      style={{ background: "none", border: "none", color: "var(--dourado)", cursor: "pointer", display: "flex" }}>
                      <Download size={15} />
                    </button>
                    <button type="button" onClick={() => { if (confirm("Excluir este documento?")) excluirDocumento(d.id).then(recarregar); }} title="Excluir"
                      style={{ background: "none", border: "none", color: "var(--red)", cursor: "pointer", display: "flex" }}>
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
              {documentos.length === 0 && <tr><td colSpan={6}>Nenhum documento arquivado.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
