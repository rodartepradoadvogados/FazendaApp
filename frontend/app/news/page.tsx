"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Newspaper, Link as LinkIcon, AlertTriangle, Loader2, RefreshCw, CalendarDays, ArrowRight, TrendingUp } from "lucide-react";
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
// manual, deriva um assunto por palavra-chave da manchete/resumo. É só um
// agrupamento de exibição (nunca sobrescreve o campo categoria real), e é a
// mesma taxonomia usada tanto no filtro por assunto (item 3 do DoD, T9)
// quanto na faixa de cotação: "mercado" cobre exatamente as matérias que a
// skill /milknews classifica como Mercado, Mercado Internacional ou Custo de
// Produção (ver backend/fazenda/seed_data/milknews_lotes/*.json).
type SecaoNews = { chave: string; label: string; cor: string };
const SECOES_NEWS: SecaoNews[] = [
  { chave: "mercado", label: "Cotação e mercado", cor: "var(--dourado)" },
  { chave: "regulacao", label: "Regulação e política agrícola", cor: "var(--cat-financeiro)" },
  { chave: "manejo", label: "Manejo e clima", cor: "var(--cat-sanidade)" },
  { chave: "tecnico", label: "Genética e técnica", cor: "var(--cat-gestao)" },
  { chave: "geral", label: "Notícia setorial", cor: "var(--cat-estoque)" },
];
const REGRAS_SECAO: [RegExp, string][] = [
  [/cota[çc][ãa]o|leil[ãa]o|gdt|cepea|pre[çc]o|mercado|export|import|d[óo]lar|commodit/i, "mercado"],
  [/\blei\b|\bpl\b|proje[t]?o de lei|tarifa|imposto|camex|c[âa]mara dos deputados|senado|decreto|regula/i, "regulacao"],
  [/calor|clima|estresse t[ée]rmico|ver[ãa]o|inverno|chuva|seca\b/i, "manejo"],
  [/vacina|doen[çc]a|sanit[áa]rio|mastite|surto/i, "manejo"],
  [/gen[ée]tica|reprodu[çc][ãa]o|nutri[çc][ãa]o|manejo|compost barn|free stall|ci[êe]ncia|journal/i, "tecnico"],
];
function secaoDaMateria(n: NoticiaNews): SecaoNews {
  const alvo = n.categoria?.trim();
  if (alvo) {
    const chave = alvo.toLowerCase();
    // Rótulos reais gravados pela skill /milknews: "Mercado", "Mercado
    // Internacional" e "Custo de Produção" caem no mesmo balde de
    // cotação/mercado do filtro; "Genética" no de genética/técnica.
    if (/mercado|custo de produ[çc][ãa]o/.test(chave)) return SECOES_NEWS[0];
    if (/gen[ée]tica|ci[êe]ncia/.test(chave)) return SECOES_NEWS[3];
    const conhecida = SECOES_NEWS.find((s) => s.chave === chave || s.label.toLowerCase() === chave);
    if (conhecida) return conhecida;
  }
  const texto = `${n.manchete} ${n.resumo || n.materia || ""}`;
  for (const [regex, chave] of REGRAS_SECAO) {
    if (regex.test(texto)) return SECOES_NEWS.find((s) => s.chave === chave)!;
  }
  return SECOES_NEWS[SECOES_NEWS.length - 1];
}

// Extrai o primeiro número "de cotação" (R$/US$/NZ$ por unidade, ou
// percentual) do texto da matéria, para a faixa de cotação (item 1 do DoD,
// T9). Não é uma fonte de dado nova: é só um recorte do que a própria matéria
// já escreveu (que por sua vez já teve seus números conferidos em duas
// fontes independentes — ver regra 1 de .claude/skills/milknews/SKILL.md).
// Quando nada bate no texto, a matéria não entra na faixa (nunca inventa
// número).
const REGEX_NUMERO_COTACAO = /(?:R\$|US\$|NZ\$|AU\$|€)\s?[\d.,]+(?:\/\w+)?|[\d.,]+\s?%/;
function numeroCotacao(n: NoticiaNews): string | null {
  const texto = `${n.manchete} ${n.resumo || ""}`;
  const m = texto.match(REGEX_NUMERO_COTACAO);
  return m ? m[0].trim() : null;
}

export default function NewsPage() {
  const [materias, setMaterias] = useState<NoticiaNews[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [verTudo, setVerTudo] = useState(true);
  const [expandida, setExpandida] = useState<number | null>(null);

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
  const restantes = useMemo(
    () => (materias && materias.length > 1 ? materias.slice(1) : []),
    [materias]
  );

  // Faixa de cotação (item 1 do DoD, T9): as matérias mais recentes já
  // classificadas como "mercado" (cotação/leilão/preço/GDT/Cepea...) pela
  // seção derivada acima.
  const materiasCotacao = useMemo(
    () => (materias || []).filter((n) => secaoDaMateria(n).chave === "mercado").slice(0, 8),
    [materias]
  );

  // Filtro por assunto (item 3 do DoD, T9) — null = "todos". Antes os
  // assuntos só serviam para agrupar a lista em seções sempre visíveis; agora
  // viram pílulas clicáveis que filtram a grade abaixo, e o agrupamento fixo
  // sai (a grade de 3 colunas do item 4 substitui as seções empilhadas). O
  // destaque editorial continua sempre visível, independente do filtro — só
  // a grade é filtrada, como em qualquer portal de notícia (manchete do dia
  // fixa, feed abaixo filtrável).
  const [filtro, setFiltro] = useState<string | null>(null);
  const secoesComItens = useMemo(
    () => SECOES_NEWS.filter((s) => restantes.some((n) => secaoDaMateria(n).chave === s.chave)),
    [restantes]
  );
  const restantesFiltradas = useMemo(
    () => (filtro ? restantes.filter((n) => secaoDaMateria(n).chave === filtro) : restantes),
    [restantes, filtro]
  );

  function cardGrade(n: NoticiaNews, i: number) {
    const cor = secaoDaMateria(n).cor;
    return (
      <article key={n.id} className="rounded-xl overflow-hidden flex flex-col" style={{ border: "1px solid var(--border)", background: "var(--surface)", transition: "transform 0.15s ease" }}>
        <div className="relative" style={{ height: "160px" }}>
          <img src={imagemMateria(n, i)} alt="" className="w-full h-full object-cover" />
          <div className="absolute left-0 right-0 bottom-0" style={{ height: "3px", background: cor }} />
        </div>
        <div className="p-4 flex flex-col flex-1">
          <div className="flex items-center gap-1 mb-1" style={{ fontSize: "0.64rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: cor }}>
            <span style={{ width: "5px", height: "5px", borderRadius: "50%", background: cor, flexShrink: 0 }} />
            {secaoDaMateria(n).label}
          </div>
          <h3 className="font-bold mb-2" style={{ fontSize: "0.95rem", color: "var(--dourado-light)", lineHeight: 1.35, fontFamily: "var(--font-sora), sans-serif" }}>
            {n.manchete}
          </h3>
          {(n.materia || n.resumo) && (
            <p className="line-clamp-2 flex-1" style={{ color: "var(--text-muted)", fontSize: "0.82rem", lineHeight: 1.5, marginBottom: "0.6rem" }}>
              {n.materia || n.resumo}
            </p>
          )}
          <div className="pt-3 mt-auto flex items-center justify-between" style={{ borderTop: "1px solid var(--border)", fontSize: "0.68rem", color: "var(--text-muted)" }}>
            <span className="flex items-center gap-1"><CalendarDays size={11} /> {formatarData(n.data_publicacao)}</span>
            {!!(n.fontes || []).length && (
              <a href={n.fontes![0]} target="_blank" rel="noopener noreferrer" style={{ display: "flex", alignItems: "center", gap: "0.2rem", color: "var(--text-muted)", textDecoration: "none" }}>
                <LinkIcon size={10} /> {dominio(n.fontes![0])}
              </a>
            )}
          </div>
        </div>
      </article>
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

      {materiasCotacao.length > 0 && (
        <div className="card mb-6">
          <div className="card-header mb-3" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <TrendingUp size={14} /> Faixa de cotação e mercado
          </div>
          <div style={{ display: "flex", gap: "0.75rem", overflowX: "auto", paddingBottom: "0.2rem" }}>
            {materiasCotacao.map((n) => {
              const numero = numeroCotacao(n);
              return (
                <div key={`cot-${n.id}`} style={{
                  flex: "0 0 auto", minWidth: "190px", maxWidth: "230px",
                  border: "1px solid var(--border)", borderRadius: "10px", padding: "0.65rem 0.85rem",
                  background: "var(--surface-2)",
                }}>
                  {numero && (
                    <div style={{ fontSize: "1.05rem", fontWeight: 800, color: "var(--dourado-light)", marginBottom: "0.2rem" }}>
                      {numero}
                    </div>
                  )}
                  <div className="line-clamp-2" style={{ fontSize: "0.76rem", color: "var(--text)", lineHeight: 1.35 }}>
                    {n.manchete}
                  </div>
                  <div style={{ fontSize: "0.64rem", color: "var(--text-muted)", marginTop: "0.35rem" }}>
                    {formatarData(n.data_publicacao)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="card mb-6">
        <div className="card-header mb-3" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <LinkIcon size={14} /> Fontes que acompanhamos todo dia
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

      {erro && <div className="alert-critico mb-4"><AlertTriangle size={16} /> <span>Não foi possível carregar as notícias: {erro}.</span></div>}
      {carregando && !materias && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {materias && materias.length === 0 && (
        <p style={{ color: "var(--text-muted)" }}>Nenhuma matéria publicada ainda.</p>
      )}

      <div className="max-w-6xl mx-auto flex flex-col gap-6">
        {destaque && (
          <article
            className="rounded-2xl overflow-hidden flex flex-col md:flex-row"
            style={{ border: "1px solid var(--border)", background: "var(--surface)" }}
          >
            <div className="md:w-3/5 relative" style={{ minHeight: "260px" }}>
              <img src={imagemMateria(destaque, 0)} alt="" className="w-full h-full object-cover" style={{ minHeight: "260px", maxHeight: "420px" }} />
              {/* Selo "Destaque de hoje" (item 2 do DoD, T9) — separa
                  visualmente a matéria mais recente da grade comum abaixo,
                  além do próprio tamanho maior que o hero já tinha. */}
              <span className="absolute top-4 left-4" style={{
                fontSize: "0.62rem", fontWeight: 700, padding: "0.28rem 0.7rem", borderRadius: "999px",
                textTransform: "uppercase", letterSpacing: "0.05em", background: "rgba(0,0,0,0.55)",
                color: "#fff", backdropFilter: "blur(4px)",
              }}>
                Destaque de hoje
              </span>
              {destaque.categoria && (
                <span className="absolute top-4 right-4" style={{
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
              <h2 className="text-2xl font-bold mb-3" style={{ color: "var(--dourado-light)", lineHeight: 1.25, fontFamily: "var(--font-sora), sans-serif" }}>
                {destaque.manchete}
              </h2>
              {(destaque.materia || destaque.resumo) && (
                <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: 1.6, marginBottom: "1rem" }}
                  className={expandida === destaque.id ? "" : "line-clamp-3"}>
                  {destaque.materia || destaque.resumo}
                </p>
              )}
              {(destaque.materia || destaque.resumo) && (destaque.materia || destaque.resumo)!.length > 220 && (
                <button className="self-start mb-3" style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--dourado-light)", display: "flex", alignItems: "center", gap: "0.35rem" }}
                  onClick={() => setExpandida(expandida === destaque.id ? null : destaque.id)}>
                  {expandida === destaque.id ? "Mostrar menos" : "Ler artigo completo"} <ArrowRight size={14} />
                </button>
              )}
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

        {restantes.length > 0 && (
          <section>
            {/* Filtro por assunto (item 3 do DoD, T9) — só aparece quando há
                mais de um assunto na lista (senão seria uma pílula sozinha,
                sem função). */}
            {secoesComItens.length > 1 && (
              <div className="flex flex-wrap items-center gap-2 mb-4">
                <button
                  onClick={() => setFiltro(null)}
                  className={filtro === null ? "btn-primary" : "btn-ghost"}
                  style={{ fontSize: "0.76rem" }}
                >
                  Todos os assuntos ({restantes.length})
                </button>
                {secoesComItens.map((s) => {
                  const count = restantes.filter((n) => secaoDaMateria(n).chave === s.chave).length;
                  const ativo = filtro === s.chave;
                  return (
                    <button
                      key={s.chave}
                      onClick={() => setFiltro(ativo ? null : s.chave)}
                      className={ativo ? "btn-primary" : "btn-ghost"}
                      style={{ fontSize: "0.76rem", display: "flex", alignItems: "center", gap: "0.35rem" }}
                    >
                      <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: s.cor, flexShrink: 0 }} />
                      {s.label} ({count})
                    </button>
                  );
                })}
              </div>
            )}

            {/* Grade de 3 colunas (item 4 do DoD, T9), responsiva — substitui
                o antigo empilhamento fixo de "1 grande + 2 pequenas" por
                seção; o assunto de cada matéria agora é filtrável (acima) em
                vez de forçar um agrupamento sempre visível. */}
            {restantesFiltradas.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma matéria neste assunto ainda.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {restantesFiltradas.map((n, i) => cardGrade(n, i))}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
