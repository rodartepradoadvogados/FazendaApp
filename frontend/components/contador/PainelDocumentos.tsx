"use client";
// Arquivo fiscal-contábil — nota fiscal, CCIR, IRPF/IRPJ, inscrição estadual,
// matrícula, contratos... Contador pode arquivar livremente (sem cadeado,
// ver proposta aprovada) — conteúdo vive no Supabase Storage, ver
// backend/fazenda/api/routers/documentos.py.
import { useEffect, useState } from "react";
import { Download, Trash2, UploadCloud } from "lucide-react";
import {
  fetchCategoriasDocumento, fetchDocumentos, enviarDocumento, baixarDocumento, excluirDocumento,
  type DocumentoArquivado,
} from "@/lib/api";
import { CORES_CONTADOR } from "@/app/contador/layout";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { Dropzone } from "@/components/Dropzone";

const C = CORES_CONTADOR;
const estiloCard: React.CSSProperties = { background: C.painel, border: `1px solid ${C.borda}`, borderRadius: "4px", padding: "1.3rem" };
const estiloInput: React.CSSProperties = {
  background: C.painelAlt, color: C.texto, border: `1px solid ${C.borda}`, borderRadius: "3px",
  padding: "0.4rem 0.6rem", fontSize: "0.85rem", width: "100%",
};
const estiloLabel: React.CSSProperties = { fontSize: "0.68rem", color: C.mudo, display: "block", marginBottom: "0.2rem", textTransform: "uppercase", letterSpacing: "0.05em" };
const estiloTh: React.CSSProperties = {
  textAlign: "left", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em",
  color: C.mudo, borderBottom: `1px solid ${C.bordaClara}`, padding: "0.5rem 0.6rem", fontWeight: 700,
};
const estiloTd: React.CSSProperties = { fontSize: "0.82rem", padding: "0.5rem 0.6rem", borderBottom: `1px solid ${C.borda}` };

function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function PainelDocumentos() {
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

  const ord = useOrdenacao(documentos);

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
      <div style={estiloCard}>
        <p style={{ margin: "0 0 0.9rem", fontWeight: 700, fontSize: "0.85rem" }}>Arquivar novo documento</p>
        <form onSubmit={enviar} style={{ display: "grid", gap: "0.8rem", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))" }}>
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={estiloLabel}>Arquivo (PDF, XML, PNG, JPEG...)</label>
            <Dropzone
              compact
              label={arquivo ? arquivo.name : "Arraste o arquivo aqui, ou"}
              onFiles={(files) => setArquivo(files[0])}
              cores={{ borda: C.borda, bordaAtiva: C.cobre, fundo: C.painelAlt, fundoAtivo: C.painelAlt, texto: C.mudo, destaque: C.cobreClaro }}
            />
          </div>
          <div>
            <label style={estiloLabel}>Categoria</label>
            <select style={estiloInput} value={categoria} onChange={(e) => setCategoria(e.target.value)} required>
              <option value="">Selecione…</option>
              {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label style={estiloLabel}>Inserir no balanço?</label>
            <select style={estiloInput} value={inserirNoBalanco} onChange={(e) => setInserirNoBalanco(e.target.value as "sim" | "nao")}>
              <option value="nao">Não</option>
              <option value="sim">Sim</option>
            </select>
          </div>
          {inserirNoBalanco === "sim" ? (
            <div>
              <label style={estiloLabel}>Nº do lançamento (se já existir)</label>
              <input style={estiloInput} value={numeroLancamento} onChange={(e) => setNumeroLancamento(e.target.value)} placeholder="opcional" />
            </div>
          ) : (
            <div>
              <label style={estiloLabel}>Data do documento</label>
              <input type="date" style={estiloInput} value={dataDocumento} onChange={(e) => setDataDocumento(e.target.value)} />
            </div>
          )}
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={estiloLabel}>Descrição (opcional)</label>
            <input style={estiloInput} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <button type="submit" disabled={!arquivo || !categoria || enviando}
              style={{
                display: "flex", alignItems: "center", gap: "0.4rem", background: C.cobre, color: "#fff",
                border: "none", borderRadius: "3px", padding: "0.55rem 0.9rem", fontSize: "0.82rem", fontWeight: 700,
                cursor: "pointer", opacity: !arquivo || !categoria || enviando ? 0.6 : 1,
              }}>
              <UploadCloud size={14} /> {enviando ? "Arquivando…" : "Arquivar documento"}
            </button>
          </div>
        </form>
        {erro && <p style={{ color: C.negativo, fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      </div>

      <div style={{ ...estiloCard, overflowX: "auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.8rem" }}>
          <p style={{ margin: 0, fontWeight: 700, fontSize: "0.85rem" }}>Documentos arquivados</p>
          <select style={{ ...estiloInput, width: "auto" }} value={filtroCategoria} onChange={(e) => setFiltroCategoria(e.target.value)}>
            <option value="">Todas as categorias</option>
            {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        {carregando ? <p style={{ color: C.mudo, fontSize: "0.82rem" }}>Carregando…</p> : (
          <table className="contador-th" style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <ThOrdenavel label="Arquivo" campo="nome_original" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Categoria" campo="categoria" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Tamanho" campo="tamanho_bytes" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Enviado em" campo="data_upload" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <ThOrdenavel label="Balanço" campo="inserir_no_balanco" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <th style={estiloTh}></th>
              </tr>
            </thead>
            <tbody>
              {ord.linhasOrdenadas.map((d) => (
                <tr key={d.id}>
                  <td style={estiloTd}>{d.nome_original}{d.descricao && <span style={{ color: C.mudo }}> — {d.descricao}</span>}</td>
                  <td style={estiloTd}>{d.categoria}</td>
                  <td style={estiloTd}>{formatarTamanho(d.tamanho_bytes)}</td>
                  <td style={estiloTd}>{new Date(d.data_upload).toLocaleDateString("pt-BR")}</td>
                  <td style={{ ...estiloTd, color: d.inserir_no_balanco ? C.positivo : C.mudo }}>{d.inserir_no_balanco ? "Sim" : "Não"}</td>
                  <td style={{ ...estiloTd, display: "flex", gap: "0.6rem" }}>
                    <button type="button" onClick={() => baixarDocumento(d.id, d.nome_original)} title="Baixar"
                      style={{ background: "none", border: "none", color: C.cobreClaro, cursor: "pointer", display: "flex" }}>
                      <Download size={15} />
                    </button>
                    <button type="button" onClick={() => { if (confirm("Excluir este documento?")) excluirDocumento(d.id).then(recarregar); }} title="Excluir"
                      style={{ background: "none", border: "none", color: C.negativo, cursor: "pointer", display: "flex" }}>
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
              {documentos.length === 0 && <tr><td style={estiloTd} colSpan={6}>Nenhum documento arquivado.</td></tr>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
