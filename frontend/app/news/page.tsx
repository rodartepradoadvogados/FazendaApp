"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Newspaper, Link as LinkIcon, AlertTriangle, Loader2, RefreshCw, CalendarDays, ArrowRight } from "lucide-react";
import { fetchNoticias, type NoticiaNews } from "@/lib/api";
import { imagemMateria } from "@/lib/newsVisual";

function formatarData(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function dominio(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

// Categoria da matéria é texto livre (cotação/mercado, notícia, técnico...) —
// não é a mesma taxonomia dos módulos do sistema. Quando o texto bate com um
// módulo (ex.: matéria de manejo taggeada "Sanidade"), usa a cor de categoria
// da marca; nos demais casos (mercado, notícia internacional...) cai no vinho
// padrão. Escurecida com color-mix para manter texto branco legível por cima
// da foto, igual ao badge original.
const COR_CATEGORIA_MODULO: Record<string, string> = {
  "reprodução": "var(--cat-reproducao)", "reproducao": "var(--cat-reproducao)",
  "sanidade": "var(--cat-sanidade)",
  "alimentação": "var(--cat-alimentacao)", "alimentacao": "var(--cat-alimentacao)",
  "financeiro": "var(--cat-financeiro)",
};
function corBadgeCategoria(categoria?: string | null): string {
  const cor = categoria ? COR_CATEGORIA_MODULO[categoria.trim().toLowerCase()] : undefined;
  return cor ? `color-mix(in srgb, ${cor} 60%, #000)` : "var(--vinho)";
}

// A maioria das matérias do robô /milknews não vem com `categoria` marcada —
// para dar hierarquia visual ao restante da lista mesmo sem essa marcação
// manual, deriva uma seção por palavra-chave da manchete/resumo. É só um
// agrupamento de exibição (nunca sobrescreve o campo categoria real).
type SecaoNews = { chave: string; label: string; cor: string };
// Paleta própria do Milk News — antes reaproveitava --cat-financeiro/
// --cat-sanidade/--cat-gestao/--cat-estoque com outro significado, colidindo
// com a regra de cores fixas de categoria do DESIGN.md (achado da crítica,
// ver docs/agents/design-implementation.md §5, milk-news-editorial.html).
// --dourado fica (é o acento da marca, não uma categoria fixa de módulo).
const SECOES_NEWS: SecaoNews[] = [
  { chave: "mercado", label: "Mercado e cotação", cor: "var(--dourado)" },
  { chave: "regulacao", label: "Regulação e política agrícola", cor: "#3E6B8F" },
  { chave: "manejo", label: "Manejo e clima", cor: "#5C6B3E" },
  { chave: "tecnico", label: "Conteúdo técnico", cor: "#7A5C3E" },
  { chave: "geral", label: "Notícias do setor", cor: "#6B5C7A" },
];
const REGRAS_SECAO: [RegExp, string][] = [
  [/cota[çc][ãa]o|leil[ãa]o|gdt|cepea|pre[çc]o|mercado|export|import|d[óo]lar|commodit/i, "mercado"],
  [/\blei\b|\bpl\b|proje[t]?o de lei|tarifa|imposto|camex|c[âa]mara dos deputados|senado|decreto|regula/i, "regulacao"],
  [/calor|clima|estresse t[ée]rmico|ver[ãa]o|inverno|chuva|seca\b/i, "manejo"],
  [/vacina|doen[çc]a|sanit[áa]rio|mastite|surto/i, "manejo"],
  [/gen[ée]tica|reprodu[çc][ãa]o|nutri[çc][ãa]o|manejo|compost barn|free stall/i, "tecnico"],
];
function secaoDaMateria(n: NoticiaNews): SecaoNews {
  const alvo = n.categoria?.trim();
  if (alvo) {
    const chave = alvo.toLowerCase();
    const conhecida = SECOES_NEWS.find((s) => s.chave === chave || s.label.toLowerCase() === chave);
    if (conhecida) return conhecida;
  }
  const texto = `${n.manchete} ${n.resumo || n.materia || ""}`;
  for (const [regex, chave] of REGRAS_SECAO) {
    if (regex.test(texto)) return SECOES_NEWS.find((s) => s.chave === chave)!;
  }
  return SECOES_NEWS[SECOES_NEWS.length - 1];
}

export default function NewsPage() {
  const [materias, setMaterias] = useState<NoticiaNews[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [verTudo, setVerTudo] = useState(true);

  const carregar = useCallback((tudo: boolean) => {
    setCarregando(true);
    setErro(null);
    fetchNoticias(tudo)
      .then((feed) => {
        const todas = feed.fontes.flatMap((f) => f.noticias);
        todas.sort((a, b) => (b.data_publicacao || b.capturado_em).localeCompare(a.data_publicacao || a.capturado_em));
        setMaterias(todas);
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => { carregar(verTudo); }, [carregar, verTudo]);

  const destaque = materias && materias.length ? materias[0] : null;
  const restantes = materias && materias.length > 1 ? materias.slice(1) : [];

  const grupos: { secao: SecaoNews; itens: NoticiaNews[] }[] = [];
  for (const n of restantes) {
    const secao = secaoDaMateria(n);
    let grupo = grupos.find((g) => g.secao.chave === secao.chave);
    if (!grupo) { grupo = { secao, itens: [] }; grupos.push(grupo); }
    grupo.itens.push(n);
  }
  const mostrarCabecalhoSecao = grupos.length > 1;

  function cardPequeno(n: NoticiaNews, i: number, cor: string) {
    return (
      <Link key={n.id} href={`/news/${n.id}`} className="rounded-xl overflow-hidden flex flex-col" style={{ border: "1px solid var(--border)", background: "var(--surface)", textDecoration: "none", color: "inherit" }}>
        <div className="relative" style={{ height: "148px" }}>
          <img src={imagemMateria(n, i)} alt="" className="w-full h-full object-cover" />
          <div className="absolute left-0 right-0 bottom-0" style={{ height: "3px", background: cor }} />
        </div>
        <div className="p-4 flex flex-col flex-1">
          <div className="flex items-center gap-1 mb-1" style={{ fontSize: "0.64rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: cor }}>
            <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: cor, flexShrink: 0 }} />
            {secaoDaMateria(n).label}
          </div>
          <h3 className="font-bold mb-2" style={{ fontSize: "0.92rem", color: "var(--dourado-light)", lineHeight: 1.35, fontFamily: "var(--font-sora), sans-serif" }}>
            {n.manchete}
          </h3>
          <div className="pt-3 mt-auto flex items-center justify-between" style={{ borderTop: "1px solid var(--border)", fontSize: "0.68rem", color: "var(--text-muted)" }}>
            <span className="flex items-center gap-1"><CalendarDays size={11} /> {formatarData(n.data_publicacao)}</span>
            {!!(n.fontes || []).length && (
              <span style={{ display: "flex", alignItems: "center", gap: "0.2rem" }}>
                <LinkIcon size={10} /> {dominio(n.fontes![0])}
              </span>
            )}
          </div>
        </div>
      </Link>
    );
  }

  return (
    <div className="p-6 animate-in">
      <div className="mb-6 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" style={{ fontFamily: "var(--font-sora), sans-serif" }}>
            <Newspaper size={22} style={{ color: "var(--dourado)" }} /> Milk News — Nosso blog de Pecuária Leiteira
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Matérias escritas por nós sobre leite, produtor de leite, pecuária leiteira, ordenha, Compost Barn e Free Stall.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
            onClick={() => carregar(verTudo)} disabled={carregando}>
            {carregando ? <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} /> : <RefreshCw size={14} />}
            Atualizar
          </button>
          <button className={verTudo ? "btn-ghost" : "btn-primary"} style={{ fontSize: "0.78rem" }}
            onClick={() => setVerTudo((v) => !v)}>
            {verTudo ? "Ver última semana" : "Ver tudo"}
          </button>
        </div>
      </div>

      <div className="card mb-6">
        {/* Rótulo curto — a frase inteira em maiúsculo (32 caracteres) era o
            único achado do detector aqui (`call-caps-body`); .card-header
            maiúsculo é a regra do produto pra RÓTULOS curtos (DESIGN.md,
            All-Caps Label Rule), não pra frase de explicação — que já existe
            no parágrafo abaixo. Ver
            docs/agents/design-implementation.md §5, milk-news-editorial.html. */}
        <div className="card-header mb-3" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <LinkIcon size={14} /> Fontes
        </div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem", marginBottom: "0.8rem" }}>
          As matérias daqui são escritas por nós a partir destas referências de mercado, notícia e conteúdo técnico — o acesso direto está sempre no rodapé de cada matéria.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px,1fr))", gap: "0.5rem" }}>
          {[
            { nome: "Cepea/Esalq — cotação do leite", url: "https://www.cepea.esalq.usp.br/br/indicador/leite.aspx" },
            { nome: "MilkPoint", url: "https://www.milkpoint.com.br/" },
            { nome: "Notícias Agrícolas", url: "https://www.noticiasagricolas.com.br/cotacoes/leite" },
            { nome: "Canal Rural", url: "https://www.canalrural.com.br/pecuaria/" },
            { nome: "DairyReporter", url: "https://www.dairyreporter.com/" },
            { nome: "DairyNews.today", url: "https://dairynews.today/" },
            { nome: "USDA/AMS Dairy Market News", url: "https://www.ams.usda.gov/mnreports/dywweeklyreport.pdf" },
          ].map((f) => (
            <a key={f.url} href={f.url} target="_blank" rel="noopener noreferrer"
              style={{ fontSize: "0.8rem", color: "var(--dourado-light)", textDecoration: "none", display: "flex", alignItems: "center", gap: "0.3rem" }}>
              <ArrowRight size={12} style={{ flexShrink: 0 }} /> {f.nome}
            </a>
          ))}
        </div>
      </div>

      {erro && (
        <div className="mb-4" style={{ display: "flex", alignItems: "center", gap: "0.6rem", background: "color-mix(in srgb, var(--red) 8%, var(--surface))", border: "1px solid var(--red)", borderRadius: "var(--r)", padding: "0.8rem 1rem" }}>
          <AlertTriangle size={18} style={{ color: "var(--red)", flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <p style={{ margin: 0, fontWeight: 700, fontSize: "0.9rem", color: "var(--text)" }}>Não conseguimos carregar as notícias agora.</p>
            <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-muted)" }}>Pode ser instabilidade temporária — tente de novo em instantes.</p>
          </div>
          <button onClick={() => carregar(verTudo)} className="btn-ghost" style={{ fontSize: "0.8rem", flexShrink: 0 }}>↻ Tentar novamente</button>
        </div>
      )}
      {carregando && !materias && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {materias && materias.length === 0 && (
        <div className="empty-state">
          <Newspaper size={22} />
          <div>Nenhuma matéria publicada ainda. Voltamos em breve com as próximas notícias do setor.</div>
        </div>
      )}

      <div className="max-w-6xl mx-auto flex flex-col gap-6">
        {destaque && (
          <article
            className="rounded-2xl overflow-hidden flex flex-col md:flex-row"
            style={{ border: "1px solid var(--border)", background: "var(--surface)" }}
          >
            <div className="md:w-3/5 relative" style={{ minHeight: "260px" }}>
              <img src={imagemMateria(destaque, 0)} alt="" className="w-full h-full object-cover" style={{ minHeight: "260px", maxHeight: "420px" }} />
              {destaque.categoria && (
                <span className="absolute top-4 left-4" style={{
                  fontSize: "0.68rem", fontWeight: 700, padding: "0.3rem 0.75rem", borderRadius: "999px",
                  textTransform: "uppercase", letterSpacing: "0.03em", background: corBadgeCategoria(destaque.categoria),
                  color: "#fff", backdropFilter: "blur(4px)",
                }}>
                  {destaque.categoria}
                </span>
              )}
            </div>
            <div className="md:w-2/5 p-6 md:p-8 flex flex-col justify-center">
              <div className="flex items-center gap-2 mb-3" style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
                <CalendarDays size={12} /> Publicado em {formatarData(destaque.data_publicacao)}
              </div>
              <Link href={`/news/${destaque.id}`} style={{ textDecoration: "none" }}>
                <h2 className="text-2xl font-bold mb-3" style={{ color: "var(--dourado-light)", lineHeight: 1.25, fontFamily: "var(--font-sora), sans-serif" }}>
                  {destaque.manchete}
                </h2>
              </Link>
              {(destaque.materia || destaque.resumo) && (
                <p className="line-clamp-3" style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: 1.6, marginBottom: "1rem" }}>
                  {destaque.materia || destaque.resumo}
                </p>
              )}
              <Link href={`/news/${destaque.id}`} className="self-start mb-3" style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--dourado-light)", display: "flex", alignItems: "center", gap: "0.35rem", textDecoration: "none" }}>
                Ler artigo completo <ArrowRight size={14} />
              </Link>
              {!!(destaque.fontes || []).length && (
                <div className="flex flex-wrap gap-2 mt-auto">
                  {(destaque.fontes || []).map((url, i) => (
                    <a key={i} href={url} target="_blank" rel="noopener noreferrer" style={{
                      display: "flex", alignItems: "center", gap: "0.25rem", fontSize: "0.7rem",
                      color: "var(--text-muted)", border: "1px solid var(--border)", borderRadius: "999px",
                      padding: "0.15rem 0.6rem", textDecoration: "none",
                    }}>
                      <LinkIcon size={10} /> {dominio(url)}
                    </a>
                  ))}
                </div>
              )}
            </div>
          </article>
        )}

        {grupos.map((grupo, gi) => {
          const [primeira, ...resto] = grupo.itens;
          return (
            <section key={grupo.secao.chave}>
              {mostrarCabecalhoSecao && (
                <div className="flex items-baseline gap-3 mb-4" style={{ marginTop: gi === 0 ? 0 : "1rem" }}>
                  <h2 style={{ fontFamily: "var(--font-sora), sans-serif", fontWeight: 700, fontSize: "1.05rem", margin: 0 }}>{grupo.secao.label}</h2>
                  <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{grupo.itens.length} matéria{grupo.itens.length > 1 ? "s" : ""}</span>
                  <div style={{ flex: 1, height: "1px", background: "var(--border)" }} />
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                {resto.length > 0 ? (
                  <>
                    <article className="rounded-xl overflow-hidden flex flex-col md:col-span-2" style={{ border: "1px solid var(--border)", background: "var(--surface)" }}>
                      <div className="relative" style={{ height: "220px" }}>
                        <img src={imagemMateria(primeira, gi)} alt="" className="w-full h-full object-cover" />
                        <div className="absolute left-0 right-0 bottom-0" style={{ height: "3px", background: grupo.secao.cor }} />
                      </div>
                      <div className="p-5 flex flex-col flex-1">
                        <div className="flex items-center gap-1 mb-1" style={{ fontSize: "0.66rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: grupo.secao.cor }}>
                          <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: grupo.secao.cor, flexShrink: 0 }} />
                          {grupo.secao.label}
                        </div>
                        <Link href={`/news/${primeira.id}`} style={{ textDecoration: "none" }}>
                          <h3 className="font-bold mb-2" style={{ fontSize: "1.15rem", color: "var(--dourado-light)", lineHeight: 1.3, fontFamily: "var(--font-sora), sans-serif" }}>
                            {primeira.manchete}
                          </h3>
                        </Link>
                        {(primeira.materia || primeira.resumo) && (
                          <p className="line-clamp-2 flex-1" style={{ color: "var(--text-muted)", fontSize: "0.85rem", lineHeight: 1.55, marginBottom: "0.75rem" }}>
                            {primeira.materia || primeira.resumo}
                          </p>
                        )}
                        <div className="pt-3 mt-auto flex items-center justify-between" style={{ borderTop: "1px solid var(--border)", fontSize: "0.7rem", color: "var(--text-muted)" }}>
                          <span className="flex items-center gap-1"><CalendarDays size={11} /> {formatarData(primeira.data_publicacao)}</span>
                          {!!(primeira.fontes || []).length && (
                            <a href={primeira.fontes![0]} target="_blank" rel="noopener noreferrer" style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "var(--text-muted)", textDecoration: "none" }}>
                              <LinkIcon size={10} /> {dominio(primeira.fontes![0])}
                            </a>
                          )}
                        </div>
                      </div>
                    </article>
                    <div className="flex flex-col gap-5">
                      {resto.slice(0, 2).map((n, i) => cardPequeno(n, gi * 10 + i + 1, grupo.secao.cor))}
                    </div>
                    {resto.slice(2).map((n, i) => cardPequeno(n, gi * 10 + i + 3, grupo.secao.cor))}
                  </>
                ) : (
                  cardPequeno(primeira, gi, grupo.secao.cor)
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
