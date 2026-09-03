"use client";
import { useEffect, useRef, useState } from "react";
import { FolderPlus, Folder, Upload, Trash2, Check, ImageOff } from "lucide-react";
import {
  fetchPastasFotosNews, criarPastaFotosNews, excluirPastaFotosNews,
  fetchFotosNews, enviarFotoNews, excluirFotoNews,
  type PastaFotoNews, type FotoNews,
} from "@/lib/api";
import { Modal } from "@/components/Modal";

const inp: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", fontSize: "0.82rem",
};

/**
 * Banco de fotos do Milknews — pastas + fotos guardadas no Supabase Storage
 * (bucket público, ver backend/fazenda/api/routers/fotos_news.py), gerido
 * direto na aba Aprovações. Dois modos, mesmo componente:
 *  - gestão pura (onSelecionar ausente): criar/excluir pasta, enviar/excluir foto;
 *  - seletor (onSelecionar presente): mesma UI + botão "Usar esta foto" em
 *    cada card, chamado ao escolher a ilustração de uma matéria pendente.
 */
export function BancoFotosNews({ onClose, onSelecionar }: { onClose: () => void; onSelecionar?: (url: string) => void }) {
  const [pastas, setPastas] = useState<PastaFotoNews[] | null>(null);
  const [pastaAtiva, setPastaAtiva] = useState<number | "todas" | null>("todas");
  const [fotos, setFotos] = useState<FotoNews[] | null>(null);
  const [novaPasta, setNovaPasta] = useState("");
  const [criandoPasta, setCriandoPasta] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [excluindoFoto, setExcluindoFoto] = useState<number | null>(null);
  const [excluindoPasta, setExcluindoPasta] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const inputArquivoRef = useRef<HTMLInputElement>(null);

  const carregarPastas = () => fetchPastasFotosNews().then(setPastas).catch((e) => setErro(e.message));
  const carregarFotos = () => {
    const pastaId = pastaAtiva === "todas" ? undefined : pastaAtiva;
    fetchFotosNews(pastaId).then(setFotos).catch((e) => setErro(e.message));
  };

  useEffect(() => { carregarPastas(); }, []);
  useEffect(() => { setFotos(null); carregarFotos(); }, [pastaAtiva]); // eslint-disable-line react-hooks/exhaustive-deps

  const criarPasta = async () => {
    const nome = novaPasta.trim();
    if (!nome) return;
    setCriandoPasta(true); setErro(null);
    try {
      const p = await criarPastaFotosNews(nome);
      setPastas((s) => [...(s || []), p].sort((a, b) => a.nome.localeCompare(b.nome)));
      setNovaPasta("");
    } catch (e: any) { setErro(e.message); }
    finally { setCriandoPasta(false); }
  };

  const excluirPasta = async (p: PastaFotoNews) => {
    if (p.quantidade_fotos > 0) { setErro(`A pasta "${p.nome}" não está vazia — mova ou exclua as fotos antes.`); return; }
    if (!window.confirm(`Excluir a pasta "${p.nome}"?`)) return;
    setExcluindoPasta(p.id); setErro(null);
    try {
      await excluirPastaFotosNews(p.id);
      setPastas((s) => (s || []).filter((x) => x.id !== p.id));
      if (pastaAtiva === p.id) setPastaAtiva("todas");
    } catch (e: any) { setErro(e.message); }
    finally { setExcluindoPasta(null); }
  };

  const enviarArquivos = async (arquivos: FileList | null) => {
    if (!arquivos || !arquivos.length) return;
    setEnviando(true); setErro(null);
    const pastaId = pastaAtiva === "todas" ? null : pastaAtiva;
    try {
      for (const file of Array.from(arquivos)) {
        await enviarFotoNews(file, pastaId);
      }
      carregarFotos();
      carregarPastas();
    } catch (e: any) { setErro(e.message); }
    finally {
      setEnviando(false);
      if (inputArquivoRef.current) inputArquivoRef.current.value = "";
    }
  };

  const excluirFoto = async (f: FotoNews) => {
    if (!window.confirm("Excluir esta foto do banco?")) return;
    setExcluindoFoto(f.id); setErro(null);
    try {
      await excluirFotoNews(f.id);
      setFotos((s) => (s || []).filter((x) => x.id !== f.id));
      carregarPastas();
    } catch (e: any) { setErro(e.message); }
    finally { setExcluindoFoto(null); }
  };

  return (
    <Modal title={onSelecionar ? "Escolher foto do banco" : "Banco de fotos — Milknews"} onClose={onClose} width="900px">
      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginBottom: "0.6rem" }}>{erro}</p>}

      <div className="flex gap-4" style={{ alignItems: "flex-start" }}>
        {/* Pastas */}
        <div style={{ width: 200, flexShrink: 0 }}>
          <button
            className="btn-ghost"
            style={{ width: "100%", justifyContent: "flex-start", fontSize: "0.82rem", fontWeight: pastaAtiva === "todas" ? 700 : 500 }}
            onClick={() => setPastaAtiva("todas")}
          >
            <Folder size={14} /> Todas as fotos
          </button>
          <button
            className="btn-ghost"
            style={{ width: "100%", justifyContent: "flex-start", fontSize: "0.82rem", fontWeight: pastaAtiva === null ? 700 : 500 }}
            onClick={() => setPastaAtiva(null)}
          >
            <Folder size={14} /> Sem pasta
          </button>
          <div style={{ marginTop: "0.3rem" }}>
            {(pastas || []).map((p) => (
              <div key={p.id} className="flex items-center gap-1" style={{ width: "100%" }}>
                <button
                  className="btn-ghost"
                  style={{ flex: 1, justifyContent: "flex-start", fontSize: "0.82rem", fontWeight: pastaAtiva === p.id ? 700 : 500, minWidth: 0 }}
                  onClick={() => setPastaAtiva(p.id)}
                  title={p.nome}
                >
                  <Folder size={14} />
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.nome}</span>
                  <span style={{ color: "var(--text-muted)", fontSize: "0.68rem" }}>({p.quantidade_fotos})</span>
                </button>
                <button
                  className="btn-ghost" style={{ padding: "0.25rem" }} title="Excluir pasta"
                  disabled={excluindoPasta === p.id} onClick={() => excluirPasta(p)}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-1 mt-3">
            <input
              style={{ ...inp, flex: 1, minWidth: 0 }} placeholder="Nova pasta"
              value={novaPasta} onChange={(e) => setNovaPasta(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") criarPasta(); }}
            />
            <button className="btn-ghost" style={{ padding: "0.35rem" }} disabled={criandoPasta || !novaPasta.trim()} onClick={criarPasta} title="Criar pasta">
              <FolderPlus size={14} />
            </button>
          </div>
        </div>

        {/* Fotos */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="flex items-center justify-between mb-2">
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              {fotos ? `${fotos.length} foto${fotos.length === 1 ? "" : "s"}` : "Carregando…"}
            </span>
            <label className="btn-primary" style={{ fontSize: "0.78rem", cursor: "pointer" }}>
              <Upload size={13} /> {enviando ? "Enviando…" : "Enviar fotos"}
              <input
                ref={inputArquivoRef} type="file" accept="image/*" multiple hidden
                disabled={enviando} onChange={(e) => enviarArquivos(e.target.files)}
              />
            </label>
          </div>

          {fotos && !fotos.length && (
            <div style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--text-muted)" }}>
              <ImageOff size={26} style={{ marginBottom: "0.5rem", opacity: 0.6 }} />
              <p style={{ fontSize: "0.85rem" }}>Nenhuma foto aqui ainda.</p>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: "0.7rem" }}>
            {(fotos || []).map((f) => (
              <div key={f.id} className="card" style={{ padding: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                <div style={{ aspectRatio: "4/3", borderRadius: "var(--r-sm)", overflow: "hidden", background: "var(--surface-2)" }}>
                  <img src={f.url} alt={f.nome_arquivo} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                </div>
                <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={f.nome_arquivo}>
                  {f.nome_arquivo}
                </p>
                <div className="flex items-center gap-1">
                  {onSelecionar && (
                    <button className="btn-primary" style={{ flex: 1, fontSize: "0.72rem", padding: "0.3rem" }} onClick={() => onSelecionar(f.url)}>
                      <Check size={12} /> Usar
                    </button>
                  )}
                  <button
                    className="btn-ghost" style={{ padding: "0.3rem" }} title="Excluir foto"
                    disabled={excluindoFoto === f.id} onClick={() => excluirFoto(f)}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
