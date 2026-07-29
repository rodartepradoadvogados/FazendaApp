"use client";
// Sub-tela: Fotos do campo — tira foto com a câmera do celular (ou escolhe
// da galeria) e envia para o Supabase Storage (ver backend/fazenda/api/
// routers/fotos.py). Sem internet, a foto entra na fila offline do
// IndexedDB (ver lib/offline.ts::enviarOuEnfileirarArquivo) e é enviada
// sozinha quando a conexão voltar — igual a um lançamento de campo comum.
import { useEffect, useRef, useState } from "react";
import { Camera, Trash2, Upload, ImageOff, CloudUpload } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import {
  useOnline, usePendentesDe, descartarPendente, lerArquivoPendente,
  enviarOuEnfileirarArquivo, ErroCotaOutbox, type ItemOutbox,
} from "@/lib/offline";
import { excluirFotoCampo, fetchFotosCampo, fetchFotoCampoUrl, type FotoCampo } from "@/lib/api";
import { Carregando, Vazio } from "@/components/mobile/menu/comum";
import { redimensionarFoto } from "@/lib/imagem";

const CAMINHO_UPLOAD = "/fotos/upload";

export default function FotosCampo({ onVoltar }: { onVoltar: () => void }) {
  const online = useOnline();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [arquivo, setArquivo] = useState<Blob | null>(null);
  const [nomeArquivo, setNomeArquivo] = useState("foto.jpg");
  const [preview, setPreview] = useState<string | null>(null);
  const [identificacao, setIdentificacao] = useState("");
  const [descricao, setDescricao] = useState("");
  const [preparando, setPreparando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [fotos, setFotos] = useState<FotoCampo[] | null>(null);
  const [carregando, setCarregando] = useState(true);
  const pendentesFotos = usePendentesDe("form", CAMINHO_UPLOAD);

  async function recarregar() {
    setCarregando(true);
    try { setFotos(await fetchFotosCampo()); } catch { /* offline ou erro — mantém lista anterior */ }
    finally { setCarregando(false); }
  }
  useEffect(() => { recarregar(); }, []);

  // Quando a fila de fotos pendentes esvazia (enviada pela sincronização em
  // segundo plano) e há internet, recarrega "Enviadas" pra foto aparecer lá.
  const qtdPendentesAnterior = useRef(pendentesFotos.length);
  useEffect(() => {
    if (pendentesFotos.length < qtdPendentesAnterior.current && online) recarregar();
    qtdPendentesAnterior.current = pendentesFotos.length;
  }, [pendentesFotos.length, online]);

  // Libera a URL do preview local ao trocar de foto ou desmontar (evita
  // vazamento de memória — URL.createObjectURL fica viva até revogada).
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  async function aoEscolherArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = ""; // permite escolher o mesmo arquivo de novo depois
    if (!f) return;
    setPreparando(true);
    try {
      // Reduz para até 1600px/JPEG q0.8 antes de guardar/enviar — cabe mais
      // fotos na fila offline e sobe bem mais rápido em 3G rural (ver
      // lib/imagem.ts). Nunca lança: se falhar, usa o arquivo original.
      const reduzido = await redimensionarFoto(f);
      if (preview) URL.revokeObjectURL(preview);
      setNomeArquivo(f.name || "foto.jpg");
      setArquivo(reduzido);
      setPreview(URL.createObjectURL(reduzido));
      setErro(null); setAviso(null);
    } finally {
      setPreparando(false);
    }
  }

  function descartarPreview() {
    if (preview) URL.revokeObjectURL(preview);
    setArquivo(null); setPreview(null); setIdentificacao(""); setDescricao(""); setErro(null); setAviso(null);
  }

  async function enviar() {
    if (!arquivo) return;
    setEnviando(true); setErro(null); setAviso(null);
    try {
      const { enviado } = await enviarOuEnfileirarArquivo({
        caminho: CAMINHO_UPLOAD,
        descricao: `Foto do campo${identificacao ? ` — nº ${identificacao}` : ""}`,
        arquivo, nomeArquivo,
        campos: { descricao: descricao || undefined, identificacao_animal: identificacao || undefined },
      });
      descartarPreview();
      if (enviado) await recarregar();
    } catch (e) {
      setErro(
        e instanceof ErroCotaOutbox
          ? "Sem espaço no aparelho para guardar a foto. Libere espaço ou tente novamente com internet."
          : e instanceof Error ? e.message : "Erro ao enviar foto",
      );
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div>
      <MobVoltar titulo="Fotos do campo" onVoltar={onVoltar} />

      <input ref={inputRef} type="file" accept="image/*" capture="environment" style={{ display: "none" }} onChange={aoEscolherArquivo} />

      {!preview ? (
        <button type="button" className="mob-btn" onClick={() => inputRef.current?.click()} disabled={preparando} style={{ marginBottom: "1.1rem" }}>
          <Camera size={19} /> {preparando ? "Preparando foto…" : "Tirar foto"}
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
          {aviso && <div style={{ color: "var(--mob-verde)", fontSize: "0.82rem", fontWeight: 600, marginBottom: "0.6rem" }}>{aviso}</div>}
          {!online && (
            <div style={{ color: "var(--mob-ambar)", fontSize: "0.82rem", fontWeight: 600, marginBottom: "0.6rem" }}>
              Sem internet — a foto entra na fila e é enviada sozinha quando conectar.
            </div>
          )}
          <div style={{ display: "flex", gap: "0.6rem" }}>
            <button type="button" className="mob-btn" onClick={enviar} disabled={enviando} style={{ flex: 1 }}>
              <Upload size={17} /> {enviando ? "Enviando…" : online ? "Enviar" : "Guardar para enviar depois"}
            </button>
            <button type="button" onClick={descartarPreview} disabled={enviando}
              style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.85rem", fontWeight: 600, color: "var(--mob-vermelho)", background: "transparent", border: "1px solid var(--mob-vermelho)", borderRadius: 10, padding: "0 0.9rem", cursor: "pointer" }}>
              <Trash2 size={15} /> Descartar
            </button>
          </div>
        </div>
      )}

      {pendentesFotos.length > 0 && (
        <>
          <div className="mob-secao">Aguardando envio ({pendentesFotos.length})</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem", marginBottom: "1.1rem" }}>
            {pendentesFotos.map((item) => <CartaoFotoPendente key={item.id} item={item} />)}
          </div>
        </>
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

function CartaoFotoPendente({ item }: { item: ItemOutbox }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    let urlLocal: string | null = null;
    lerArquivoPendente(item.id).then((blob) => {
      if (cancelado || !blob) return;
      urlLocal = URL.createObjectURL(blob);
      setUrl(urlLocal);
    });
    return () => { cancelado = true; if (urlLocal) URL.revokeObjectURL(urlLocal); };
  }, [item.id]);

  return (
    <div className="mob-card" style={{ padding: "0.5rem", position: "relative" }}>
      {url ? (
        <img src={url} alt="Foto aguardando envio" style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: 8, display: "block", opacity: 0.75 }} />
      ) : (
        <div style={{ width: "100%", height: 130, borderRadius: 8, background: "var(--mob-surface-2)" }} />
      )}
      <div style={{ marginTop: "0.4rem", display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", color: item.erro ? "var(--mob-vermelho)" : "var(--mob-ambar)", fontWeight: 600 }}>
        <CloudUpload size={13} />
        {item.erro || ((item.tentativas || 0) > 0 ? `Aguardando envio (tentativa ${item.tentativas})…` : "Aguardando envio…")}
      </div>
      {item.erro && (
        <button type="button" onClick={() => descartarPendente(item.id)}
          style={{ marginTop: "0.35rem", display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.74rem", fontWeight: 600, color: "var(--mob-vermelho)", background: "transparent", border: "1px solid var(--mob-vermelho)", borderRadius: 8, padding: "0.25rem 0.5rem", cursor: "pointer" }}>
          <Trash2 size={12} /> Descartar
        </button>
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
