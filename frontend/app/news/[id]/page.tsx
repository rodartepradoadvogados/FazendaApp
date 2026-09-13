"use client";
// Página de artigo — rota que não existia antes (manchetes eram texto morto
// fora da matéria em destaque). Não há endpoint de matéria única no backend;
// busca o feed já paginado e localiza pelo id, mesma fonte de dados da
// listagem (docs/agents/design-implementation.md §5, a-materia-completa.html).
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, ArrowRight, CalendarDays, Link as LinkIcon, Newspaper } from "lucide-react";
import { fetchNoticias, type NoticiaNews } from "@/lib/api";
import { imagemMateria } from "@/lib/newsVisual";

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "long", year: "numeric" });
}
function dominio(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

export default function ArtigoNews() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [materias, setMaterias] = useState<NoticiaNews[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  function carregar() {
    setErro(null);
    fetchNoticias(true)
      .then((feed) => {
        const todas = feed.fontes.flatMap((f) => f.noticias);
        todas.sort((a, b) => (b.data_publicacao || b.capturado_em).localeCompare(a.data_publicacao || a.capturado_em));
        setMaterias(todas);
      })
      .catch(() => setErro("Não conseguimos carregar esta matéria agora."));
  }
  useEffect(carregar, [id]);

  if (materias === null && !erro) {
    return <div className="p-6"><p style={{ color: "var(--text-muted)" }}>Carregando…</p></div>;
  }
  if (erro) {
    return (
      <div className="p-6">
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", background: "color-mix(in srgb, var(--red) 8%, var(--surface))", border: "1px dashed var(--red)", borderRadius: "var(--r)", padding: "0.9rem 1.1rem", maxWidth: "40rem" }}>
          <p style={{ color: "var(--text)", fontSize: "0.9rem", flex: 1, margin: 0 }}>{erro}</p>
          <button onClick={carregar} className="btn-ghost" style={{ fontSize: "0.8rem" }}>↻ Tentar novamente</button>
        </div>
      </div>
    );
  }

  const materia = materias!.find((m) => m.id === id);
  const indice = materias!.findIndex((m) => m.id === id);
  const proxima = indice >= 0 ? materias![indice + 1] : undefined;

  if (!materia) {
    return (
      <div className="p-6">
        <p style={{ color: "var(--text-muted)" }}>Matéria não encontrada. <Link href="/news" style={{ color: "var(--dourado-light)" }}>Voltar pro Milk News</Link>.</p>
      </div>
    );
  }

  return (
    <div className="p-6 animate-in">
      <Link href="/news" style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", color: "var(--text-muted)", fontSize: "0.85rem", textDecoration: "none", marginBottom: "1.4rem" }}>
        <ArrowLeft size={15} /> Milk News
      </Link>

      <div style={{ maxWidth: "44rem", margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "1rem", marginBottom: "1.6rem", paddingBottom: "1rem", borderBottom: "2px solid var(--vinho)" }}>
          <span style={{ fontFamily: "var(--font-sora), sans-serif", fontWeight: 800, fontSize: "1.2rem", color: "var(--vinho)" }}>
            Milk<span style={{ color: "var(--dourado)" }}>News</span>
          </span>
          <span style={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)" }}>CowData · Blog de pecuária leiteira</span>
        </div>

        {materia.categoria && (
          <span style={{ display: "inline-block", fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--dourado)", background: "color-mix(in srgb, var(--dourado) 14%, transparent)", padding: "0.2rem 0.6rem", borderRadius: "999px", marginBottom: "0.9rem" }}>
            {materia.categoria}
          </span>
        )}
        <h1 style={{ fontFamily: "var(--font-sora), sans-serif", fontWeight: 800, fontSize: "1.9rem", lineHeight: 1.18, margin: "0 0 0.8rem" }}>
          {materia.manchete}
        </h1>
        {/* Assinatura — sem isso, nada aqui identificava quem escreveu ou
            revisou a matéria (achado P1 da crítica, ver
            docs/agents/design-implementation.md §5, a-materia-completa.html). */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "1.5rem" }}>
          <span style={{ width: "2rem", height: "2rem", borderRadius: "50%", background: "var(--vinho)", color: "var(--dourado-light)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: "0.8rem", flexShrink: 0 }}>
            <Newspaper size={15} />
          </span>
          <span>
            <strong style={{ color: "var(--text)" }}>{materia.revisado_final_por || "Equipe CowData"}</strong>
            {formatarData(materia.data_publicacao) && <> · {formatarData(materia.data_publicacao)}</>}
          </span>
        </div>

        <img src={imagemMateria(materia, 0)} alt="" style={{ width: "100%", maxHeight: "22rem", objectFit: "cover", borderRadius: "var(--r-sm)", marginBottom: "1.6rem" }} />

        {/* Coluna de leitura de verdade — corpo maior, entrelinha generosa,
            medida confortável (~68ch), separada da metáfora de card usada na
            listagem (achado P3 da crítica). */}
        <div style={{ maxWidth: "68ch", fontSize: "1.06rem", lineHeight: 1.75, color: "var(--text)" }}>
          {(materia.materia || materia.resumo || "").split(/\n+/).filter(Boolean).map((p, i) => (
            <p key={i} style={{ margin: "0 0 1.2rem" }}>{p}</p>
          ))}
          {!materia.materia && !materia.resumo && (
            <p style={{ color: "var(--text-muted)" }}>Resumo não disponível para esta matéria.</p>
          )}
        </div>

        {!!(materia.fontes || []).length && (
          <div style={{ marginTop: "1.6rem", padding: "1rem 1.2rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", fontSize: "0.8rem" }}>
            <div style={{ fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", fontSize: "0.68rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>Fontes desta matéria</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1rem" }}>
              {materia.fontes!.map((url, i) => (
                <a key={i} href={url} target="_blank" rel="noopener noreferrer" style={{ display: "flex", alignItems: "center", gap: "0.25rem", color: "var(--dourado)", textDecoration: "none" }}>
                  <LinkIcon size={11} /> {dominio(url)}
                </a>
              ))}
            </div>
          </div>
        )}

        {proxima && (
          <div style={{ marginTop: "2rem", paddingTop: "1.2rem", borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: "0.7rem" }}>Continue lendo</div>
            <Link href={`/news/${proxima.id}`} style={{ display: "block", padding: "0.8rem 1rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", textDecoration: "none", color: "var(--text)", fontWeight: 600, fontSize: "0.92rem" }}>
              {proxima.manchete} <ArrowRight size={14} style={{ display: "inline", marginLeft: "0.3rem" }} />
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
