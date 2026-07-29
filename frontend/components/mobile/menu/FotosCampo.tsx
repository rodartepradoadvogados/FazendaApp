"use client";
// Sub-tela: Fotos do campo — tira foto com a câmera do celular (ou escolhe
// da galeria) e envia para o Supabase Storage (ver backend/fazenda/api/
// routers/fotos.py). Ainda SEM fila offline própria (ver lib/offline.ts —
// só lançamentos JSON entram na fila hoje; fotos exigem um outbox binário
// próprio, item futuro do roadmap): se cair o sinal no meio da captura, a
// foto fica guardada na tela (não se perde) até o usuário conseguir enviar.
import { useEffect, useRef, useState } from "react";
import { Camera, Trash2, Upload, ImageOff } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import { useOnline } from "@/lib/offline";
import {
  enviarFotoCampo, excluirFotoCampo, fetchFotosCampo, fetchFotoCampoUrl, type FotoCampo,
} from "@/lib/api";
import { Carregando, Vazio } from "@/components/mobile/menu/comum";

export default function FotosCampo({ onVoltar }: { onVoltar: () => void }) {
  const online = useOnline();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [identificacao, setIdentificacao] = useState("");
  const [descricao, setDescricao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const [fotos, setFotos] = useState<FotoCampo[] | null>(null);
  const [carregando, setCarregando] = useState(true);

  async function recarregar() {
    setCarregando(true);
    try { setFotos(await fetchFotosCampo()); } catch { /* offline ou erro — mantém lista anterior */ }
    finally { setCarregando(false); }
  }
  useEffect(() => { recarregar(); }, []);

  // Libera a URL do preview local ao trocar de foto ou desmontar (evita
  // vazamento de memória — URL.createObjectURL fica viva até revogada).
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function aoEscolherArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = ""; // permite escolher o mesmo arquivo de novo depois
    if (!f) return;
    if (preview) URL.revokeObjectURL(preview);
    setArquivo(f);
    setPreview(URL.createObjectURL(f));
    setErro(null);
  }

  function descartarPreview() {
    if (preview) URL.revokeObjectURL(preview);
    setArquivo(null); setPreview(null); setIdentificacao(""); setDescricao(""); setErro(null);
  }

  async function enviar() {
    if (!arquivo) return;
    setEnviando(true); setErro(null);
    try {
      await enviarFotoCampo({ file: arquivo, identificacaoAnimal: identificacao || undefined, descricao: descricao || undefined });
      descartarPreview();
      await recarregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Erro ao enviar foto");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div>
      <MobVoltar titulo="Fotos do campo" onVoltar={onVoltar} />

      <input ref={inputRef} type="file" accept="image/*" capture="environment" style={{ display: "none" }} onChange={aoEscolherArquivo} />

      {!preview ? (
        <button type="button" className="mob-btn" onClick={() => inputRef.current?.click()} style={{ marginBottom: "1.1rem" }}>
          <Camera size={19} /> Tirar foto
        </button>
      ) : (
        <div className="mob-card" style={{ padding: "0.9rem", marginBottom: "1.1rem" }}>
          {/* Preview local — ainda não subiu, por isso <img> direto (sem passar pelo backend). */}
          <img src={preview} alt="Prévia da foto" style={{ width: "100%", borderRadius: 10, display: "block", marginBottom: "0.7rem", maxHeight: 260, objectFit: "cover" }} />
          <input type="text" placeholder="Identificação do animal (opcional)" value={identificacao} onChange={(e) => setIdentificacao(e.target.value)}
            className="mob-input" style={{ marginBottom: "0.5rem" }} />
          <input type="text" placeholder="Descrição (opcional)" value={descricao} onChange={(e) => setDescricao(e.target.value)}
            className="mob-input" style={{ marginBottom: "0.7rem" }} />
          {erro && <div style={{ color: "var(--mob-vermelho)", fontSize: "0.82rem", fontWeight: 600, marginBottom: "0.6rem" }}>{erro}</div>}
          {!online && <div style={{ color: "var(--mob-ambar)", fontSize: "0.82rem", fontWeight: 600, marginBottom: "0.6rem" }}>Sem internet — a foto fica aqui até você conseguir enviar.</div>}
          <div style={{ display: "flex", gap: "0.6rem" }}>
            <button type="button" className="mob-btn" onClick={enviar} disabled={!online || enviando} style={{ flex: 1 }}>
              <Upload size={17} /> {enviando ? "Enviando…" : "Enviar"}
            </button>
            <button type="button" onClick={descartarPreview} disabled={enviando}
              style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.85rem", fontWeight: 600, color: "var(--mob-vermelho)", background: "transparent", border: "1px solid var(--mob-vermelho)", borderRadius: 10, padding: "0 0.9rem", cursor: "pointer" }}>
              <Trash2 size={15} /> Descartar
            </button>
          </div>
        </div>
      )}

      <div className="mob-secao">Enviadas</div>
      {carregando && !fotos ? <Carregando /> : !fotos || !fotos.length ? (
        <Vazio icon={ImageOff}>Nenhuma foto enviada ainda.</Vazio>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
          {fotos.map((f) => <CartaoFoto key={f.id} foto={f} onExcluida={recarregar} />)}
        </div>
      )}
    </div>
  );
}

function CartaoFoto({ foto, onExcluida }: { foto: FotoCampo; onExcluida: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [excluindo, setExcluindo] = useState(false);

  useEffect(() => {
    let cancelado = false;
    let urlLocal: string | null = null;
    fetchFotoCampoUrl(foto.id).then((u) => { if (!cancelado) { urlLocal = u; setUrl(u); } }).catch(() => {});
    return () => { cancelado = true; if (urlLocal) URL.revokeObjectURL(urlLocal); };
  }, [foto.id]);

  async function excluir() {
    if (!confirm("Excluir esta foto? Não pode ser desfeito.")) return;
    setExcluindo(true);
    try { await excluirFotoCampo(foto.id); onExcluida(); } catch { setExcluindo(false); }
  }

  return (
    <div className="mob-card" style={{ padding: "0.5rem", position: "relative" }}>
      {url ? (
        <img src={url} alt={foto.descricao || "Foto do campo"} style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: 8, display: "block" }} />
      ) : (
        <div style={{ width: "100%", height: 130, borderRadius: 8, background: "var(--mob-surface-2)" }} />
      )}
      <div style={{ marginTop: "0.4rem", fontSize: "0.76rem", color: "var(--mob-muted)" }}>
        {new Date(foto.data_captura).toLocaleDateString("pt-BR")}
        {foto.identificacao_animal ? ` · Nº ${foto.identificacao_animal}` : ""}
      </div>
      {foto.descricao && <div style={{ fontSize: "0.78rem", fontWeight: 600 }}>{foto.descricao}</div>}
      <button type="button" onClick={excluir} disabled={excluindo} aria-label="Excluir foto"
        style={{ position: "absolute", top: 8, right: 8, background: "rgba(0,0,0,0.55)", border: "none", borderRadius: "50%", width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", cursor: "pointer" }}>
        <Trash2 size={14} />
      </button>
    </div>
  );
}
