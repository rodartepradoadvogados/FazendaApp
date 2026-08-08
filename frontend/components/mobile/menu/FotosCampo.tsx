"use client";
// Sub-tela: Fotos do campo — tira foto com a câmera do celular (ou escolhe
// da galeria) e envia para o Supabase Storage (ver backend/fazenda/api/
// routers/fotos.py). Sem internet, a foto entra na fila offline do
// IndexedDB (ver lib/offline.ts::enviarOuEnfileirarArquivo) e é enviada
// sozinha quando a conexão voltar — igual a um lançamento de campo comum.
import { useEffect, useRef, useState } from "react";
import { Camera, Trash2, Upload, ImageOff, CloudUpload } from "lucide-react";
import {
  useOnline, usePendentesDe, descartarPendente, lerArquivoPendente,
  enviarOuEnfileirarArquivo, ErroCotaOutbox, type ItemOutbox,
} from "@/lib/offline";
import {
  excluirFotoCampo, fetchFotosCampo, fetchFotoCampoUrl, fetchAnimais, fetchLotes,
  fetchPortalDestinatarios, type FotoCampo, type PortalDestinatario,
} from "@/lib/api";
import { Carregando, Vazio } from "@/components/mobile/menu/comum";
import { useCache, SeletorAnimal, BotoesEscolha, MobPill, LinhaPills, type Animal as AnimalTipo } from "@/components/mobile/lancar/comum";
import { PortalMencaoInput } from "@/components/PortalMencaoInput";
import { redimensionarFoto } from "@/lib/imagem";

const CAMINHO_UPLOAD = "/fotos/upload";

type LoteRow = { codigo: string; nome?: string | null; rotulo?: string; qtd_animais?: number };
type TipoAssunto = "" | "animal" | "lote" | "outro";

const ASSUNTOS_FIXOS: { valor: string; label: string }[] = [
  { valor: "reproducao", label: "Reprodução" },
  { valor: "producao", label: "Produção" },
  { valor: "sanidade", label: "Sanidade" },
  { valor: "alimentacao", label: "Alimentação" },
  { valor: "estoque", label: "Estoque" },
  { valor: "outro", label: "Outro assunto" },
];

export default function FotosCampo() {
  const online = useOnline();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [arquivo, setArquivo] = useState<Blob | null>(null);
  const [nomeArquivo, setNomeArquivo] = useState("foto.jpg");
  const [preview, setPreview] = useState<string | null>(null);
  const [descricao, setDescricao] = useState("");
  const [preparando, setPreparando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const [destinatarios, setDestinatarios] = useState<number[]>([]);
  const [destinatariosOpcoes, setDestinatariosOpcoes] = useState<PortalDestinatario[]>([]);
  const [tipoAssunto, setTipoAssunto] = useState<TipoAssunto>("");
  const [numeroAnimal, setNumeroAnimal] = useState("");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [assuntoFixo, setAssuntoFixo] = useState("");

  const animais = useCache<AnimalTipo[]>("animais", () => fetchAnimais() as Promise<AnimalTipo[]>, []);
  const lotes = useCache<LoteRow[]>("lotes", () => fetchLotes() as Promise<LoteRow[]>, []);
  useEffect(() => { fetchPortalDestinatarios().then(setDestinatariosOpcoes).catch(() => {}); }, []);

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
    setArquivo(null); setPreview(null); setDescricao(""); setErro(null); setAviso(null);
    setDestinatarios([]); setTipoAssunto(""); setNumeroAnimal(""); setLotesSel([]); setAssuntoFixo("");
  }

  function resumoAssunto(): string {
    if (tipoAssunto === "animal" && numeroAnimal) return `Animal ${numeroAnimal}`;
    if (tipoAssunto === "lote" && lotesSel.length) return `Lotes ${lotesSel.join(", ")}`;
    if (tipoAssunto === "outro" && assuntoFixo) return ASSUNTOS_FIXOS.find((a) => a.valor === assuntoFixo)?.label || "";
    return "";
  }

  async function enviar() {
    if (!arquivo) return;
    setEnviando(true); setErro(null); setAviso(null);
    try {
      const resumo = resumoAssunto();
      const { enviado } = await enviarOuEnfileirarArquivo({
        caminho: CAMINHO_UPLOAD,
        descricao: `Foto do campo${resumo ? ` — ${resumo}` : ""}`,
        arquivo, nomeArquivo,
        campos: {
          descricao: descricao || undefined,
          tipo_assunto: tipoAssunto || undefined,
          identificacao_animal: tipoAssunto === "animal" ? (numeroAnimal || undefined) : undefined,
          lotes: tipoAssunto === "lote" && lotesSel.length ? lotesSel.join(",") : undefined,
          assunto_fixo: tipoAssunto === "outro" ? (assuntoFixo || undefined) : undefined,
          destinatarios_usuario_id: destinatarios.length ? destinatarios.join(",") : undefined,
        },
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

  function alternarLote(codigo: string) {
    setLotesSel((sel) => sel.includes(codigo) ? sel.filter((c) => c !== codigo) : [...sel, codigo]);
  }
  const todosLotesMarcados = lotes.dados.length > 0 && lotesSel.length === lotes.dados.length;

  return (
    <div>
      <input ref={inputRef} type="file" accept="image/*" capture="environment" style={{ display: "none" }} onChange={aoEscolherArquivo} />

      {!preview ? (
        <button type="button" className="mob-btn" onClick={() => inputRef.current?.click()} disabled={preparando} style={{ marginBottom: "1.1rem" }}>
          <Camera size={19} /> {preparando ? "Preparando foto…" : "Tirar foto"}
        </button>
      ) : (
        <div className="mob-card" style={{ padding: "0.9rem", marginBottom: "1.1rem" }}>
          {/* Preview local — ainda não subiu, por isso <img> direto (sem passar pelo backend). */}
          <img src={preview} alt="Prévia da foto" style={{ width: "100%", borderRadius: "var(--r-app)", display: "block", marginBottom: "0.7rem", maxHeight: 260, objectFit: "cover" }} />

          <div style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: "0.3rem", color: "var(--mob-muted)" }}>Para (opcional)</div>
          <PortalMencaoInput opcoes={destinatariosOpcoes} selecionados={destinatarios} onChange={setDestinatarios} placeholder="Ninguém marcado = todos" />
          <div style={{ fontSize: "0.72rem", color: "var(--mob-muted)", marginTop: "0.25rem", marginBottom: "0.8rem" }}>
            Sem ninguém marcado, a foto vai para todos.
          </div>

          <div style={{ fontSize: "0.78rem", fontWeight: 600, marginBottom: "0.4rem", color: "var(--mob-muted)" }}>Sobre o quê? (opcional)</div>
          <div style={{ marginBottom: "0.8rem" }}>
            <BotoesEscolha
              opcoes={[
                { valor: "animal", label: "Animal" },
                { valor: "lote", label: "Lote" },
                { valor: "outro", label: "Outro assunto" },
              ]}
              valor={tipoAssunto}
              onChange={(v) => setTipoAssunto(v === tipoAssunto ? "" : v)}
            />
          </div>

          {tipoAssunto === "animal" && (
            <div style={{ marginBottom: "0.8rem" }}>
              <SeletorAnimal animais={animais.dados} valor={numeroAnimal} onChange={setNumeroAnimal} />
            </div>
          )}

          {tipoAssunto === "lote" && (
            <LinhaPills>
              <MobPill ativa={todosLotesMarcados} onClick={() => setLotesSel(todosLotesMarcados ? [] : lotes.dados.map((l) => l.codigo))}>
                Todos os lotes
              </MobPill>
              {lotes.dados.map((l) => (
                <MobPill key={l.codigo} ativa={lotesSel.includes(l.codigo)} onClick={() => alternarLote(l.codigo)}>
                  {l.rotulo || `${l.codigo} · ${l.nome || ""}`}
                </MobPill>
              ))}
            </LinhaPills>
          )}

          {tipoAssunto === "outro" && (
            <select className="mob-input" value={assuntoFixo} onChange={(e) => setAssuntoFixo(e.target.value)} style={{ marginBottom: "0.8rem" }}>
              <option value="">Selecione o assunto…</option>
              {ASSUNTOS_FIXOS.map((a) => <option key={a.valor} value={a.valor}>{a.label}</option>)}
            </select>
          )}

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
              style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.85rem", fontWeight: 600, color: "var(--mob-vermelho)", background: "transparent", border: "1px solid var(--mob-vermelho)", borderRadius: "var(--r-app)", padding: "0 0.9rem", cursor: "pointer" }}>
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
        <img src={url} alt="Foto aguardando envio" style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: "var(--r-app)", display: "block", opacity: 0.75 }} />
      ) : (
        <div style={{ width: "100%", height: 130, borderRadius: "var(--r-app)", background: "var(--mob-surface-2)" }} />
      )}
      <div style={{ marginTop: "0.4rem", display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", color: item.erro ? "var(--mob-vermelho)" : "var(--mob-ambar)", fontWeight: 600 }}>
        <CloudUpload size={13} />
        {item.erro || ((item.tentativas || 0) > 0 ? `Aguardando envio (tentativa ${item.tentativas})…` : "Aguardando envio…")}
      </div>
      {item.erro && (
        <button type="button" onClick={() => descartarPendente(item.id)}
          style={{ marginTop: "0.35rem", display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.74rem", fontWeight: 600, color: "var(--mob-vermelho)", background: "transparent", border: "1px solid var(--mob-vermelho)", borderRadius: "var(--r-app)", padding: "0.25rem 0.5rem", cursor: "pointer" }}>
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
        <img src={url} alt={foto.descricao || "Foto do campo"} style={{ width: "100%", height: 130, objectFit: "cover", borderRadius: "var(--r-app)", display: "block" }} />
      ) : (
        <div style={{ width: "100%", height: 130, borderRadius: "var(--r-app)", background: "var(--mob-surface-2)" }} />
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
