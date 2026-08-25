import type { CSSProperties } from "react";
import type { NoticiaNews } from "@/lib/api";

// Visual compartilhado das matérias do News (site + app): fundo fotográfico
// escolhido por CATEGORIA (ver categoriaVisual/FUNDOS_POR_CATEGORIA abaixo)
// entre TODAS as fotos temáticas do site (as 5 de
// components/SectionBackground.tsx + a do login) e cor de destaque alternada
// entre vinho e verde — uma foto e uma cor por matéria, sempre a mesma
// combinação para o mesmo índice+categoria (não depende da paleta escolhida
// pelo usuário, para as duas cores aparecerem sempre lado a lado).
export const FUNDOS_MATERIA = [
  "/images/login-fundo.webp",
  "/images/bg-rebanho.webp",
  "/images/bg-ciclo-diario.webp",
  "/images/bg-insumos-sanidade.webp",
  "/images/bg-administracao.webp",
  "/images/bg-analise.webp",
];

// O blog é a exceção "branca com tons de azul" da área pública (ver
// NewsShell.tsx) — duas tonalidades de azul institucional, fixas aqui, para
// alternar por matéria (não depende da paleta vinho/verde/azul escolhida
// pelo usuário no resto do sistema).
const CORES_MATERIA = [
  { cor: "#0E2A47", borda: "#2563EB" }, // marinho
  { cor: "#2E5D8A", borda: "#5B94C7" }, // azul-aço
];

// ── Categoria visual (assunto) da matéria ───────────────────────────────────
// Mesma classificação usada em app/news/page.tsx para as pílulas de assunto e
// a faixa de cotação — centralizada aqui (single source of truth) para que a
// escolha de imagem abaixo NUNCA fique dessincronizada da classificação que
// aparece na tela: uma matéria classificada como "mercado" nas pílulas tem
// que cair exatamente na mesma categoria aqui. app/news/page.tsx importa
// `categoriaVisual` em vez de reimplementar as regras.
export type ChaveSecaoNews = "mercado" | "regulacao" | "manejo" | "tecnico" | "geral";

const LABEL_POR_CHAVE: Record<ChaveSecaoNews, string> = {
  mercado: "cotação e mercado",
  regulacao: "regulação e política agrícola",
  manejo: "manejo e clima",
  tecnico: "genética e técnica",
  geral: "notícia setorial",
};

const REGRAS_SECAO_VISUAL: [RegExp, ChaveSecaoNews][] = [
  [/cota[çc][ãa]o|leil[ãa]o|gdt|cepea|pre[çc]o|mercado|export|import|d[óo]lar|commodit/i, "mercado"],
  [/\blei\b|\bpl\b|proje[t]?o de lei|tarifa|imposto|camex|c[âa]mara dos deputados|senado|decreto|regula/i, "regulacao"],
  [/calor|clima|estresse t[ée]rmico|ver[ãa]o|inverno|chuva|seca\b/i, "manejo"],
  [/vacina|doen[çc]a|sanit[áa]rio|mastite|surto/i, "manejo"],
  [/gen[ée]tica|reprodu[çc][ãa]o|nutri[çc][ãa]o|manejo|compost barn|free stall|ci[êe]ncia|journal/i, "tecnico"],
];

/** Deriva a chave de assunto de uma matéria (categoria gravada manualmente,
 * quando existe; senão por palavra-chave da manchete/resumo). É só um
 * agrupamento de exibição — nunca sobrescreve o campo `categoria` real. */
export function categoriaVisual(n: NoticiaNews): ChaveSecaoNews {
  const alvo = n.categoria?.trim();
  if (alvo) {
    const chave = alvo.toLowerCase();
    // Rótulos reais gravados pela skill /milknews: "Mercado", "Mercado
    // Internacional" e "Custo de Produção" caem no mesmo balde de
    // cotação/mercado; "Genética"/"Ciência" no de genética/técnica.
    if (/mercado|custo de produ[çc][ãa]o/.test(chave)) return "mercado";
    if (/gen[ée]tica|ci[êe]ncia/.test(chave)) return "tecnico";
    const direta = (Object.keys(LABEL_POR_CHAVE) as ChaveSecaoNews[])
      .find((c) => c === chave || LABEL_POR_CHAVE[c] === chave);
    if (direta) return direta;
  }
  const texto = `${n.manchete} ${n.resumo || n.materia || ""}`;
  for (const [regex, chave] of REGRAS_SECAO_VISUAL) {
    if (regex.test(texto)) return chave;
  }
  return "geral";
}

// ── Fundo por categoria ──────────────────────────────────────────────────
// Antes o fundo caía num rodízio cego por posição na lista
// (FUNDOS_MATERIA[index % 6]), sem nenhuma relação com o ASSUNTO da matéria —
// por isso fotos de mercado, manejo e genética se misturavam sem critério.
// Agora cada categoria usa um sub-conjunto de FUNDOS_MATERIA escolhido por
// afinidade temática com o banco de imagens pequeno que já existe hoje.
// IMPORTANTE: as 6 fotos do banco são todas de curral/vaca em ângulos
// diferentes — nenhuma delas mostra literalmente "gráfico", "papelada" ou
// "DNA" (conferido foto a foto antes de decidir este mapeamento). A
// associação abaixo é por NOME/tema do arquivo (o nome que já foi dado a
// cada foto quando foi criada para outras seções do site, ver
// components/SectionBackground.tsx), não pela cena retratada no pixel — é o
// melhor critério disponível com um banco de imagens só de vaca/curral, e o
// mesmo critério que o pedido original sugeriu (ex.: "bg-analise" para
// mercado, mesmo sendo uma foto de bezerros deitados):
//   - mercado (cotação/leilão/preço): bg-analise.webp — nome remete a
//     análise/dado.
//   - regulação e política agrícola: bg-administracao.webp — nome remete a
//     administração/gestão institucional (o pedido original já citava esta
//     foto como opção para genética/técnica; aqui ela cobre a categoria que
//     o pedido não endereçou explicitamente).
//   - manejo e clima: bg-ciclo-diario.webp — nome remete à rotina diária da
//     fazenda.
//   - genética e técnica: bg-insumos-sanidade.webp — nome remete a
//     insumo/técnica (sugestão explícita do pedido original).
//   - notícia setorial (geral, catch-all): bg-rebanho.webp (sugestão
//     explícita do pedido original) e login-fundo.webp, alternadas por
//     índice — as duas fotos mais genéricas do banco, coerente com "geral"
//     ser o balde que recebe o que não é nenhuma das quatro acima.
// Dentro de cada categoria, quando há mais de uma imagem associável, alterna
// por índice para não repetir sempre a primeira.
//
// BLOQUEIO DE CONTEÚDO (não é bug de código): o pedido original também
// queria fotos de fazenda/pasto e de pessoas/famílias desfocadas trabalhando
// na fazenda, para dar mais variedade e "cara de fazenda" às matérias — essas
// fotos NÃO existem em /public/images/ hoje, e esta correção não tem acesso a
// banco de imagens externo para gerar ou baixar novas. Quando o usuário
// fornecer/aprovar fotos desse tipo, adicione os arquivos em
// /public/images/ e distribua-os pelos buckets abaixo (fazenda/pasto e
// pessoas trabalhando encaixam bem em "geral" e "manejo"; ver pedido
// original do usuário no card do News).
const FUNDOS_POR_CATEGORIA: Record<ChaveSecaoNews, string[]> = {
  mercado: ["/images/bg-analise.webp"],
  regulacao: ["/images/bg-administracao.webp"],
  manejo: ["/images/bg-ciclo-diario.webp"],
  tecnico: ["/images/bg-insumos-sanidade.webp"],
  geral: ["/images/bg-rebanho.webp", "/images/login-fundo.webp"],
};

export function fundoMateria(index: number, categoria: ChaveSecaoNews = "geral"): string {
  const bucket = FUNDOS_POR_CATEGORIA[categoria] || FUNDOS_MATERIA;
  return bucket[index % bucket.length];
}

export function corMateria(index: number): { cor: string; borda: string } {
  return CORES_MATERIA[index % CORES_MATERIA.length];
}

/** Ilustração de uma matéria (#news-redesign): foto do banco de imagens
 * quando a matéria tem `imagem`; senão cai no fundo temático da sua
 * categoria (`categoriaVisual` + `fundoMateria`, mesma foto por
 * índice+categoria, sempre a mesma combinação). Compartilhado entre a página
 * pública (app/news/page.tsx), a landing pública (LandingPublica.tsx), o
 * admin do site (NewsAdmin.tsx) e o admin do app (mobile/menu/News.tsx) para
 * as telas ficarem consistentes — todas chamam com a mesma assinatura
 * (n, index); a categoria é derivada de `n` aqui dentro. */
export function imagemMateria(n: NoticiaNews, index: number): string {
  return n.imagem || fundoMateria(index, categoriaVisual(n));
}

/** Estilo completo do cartão de matéria (site e app): foto + camada de cor
 * alternadas por índice. */
export function estiloCardMateria(index: number, categoria: ChaveSecaoNews = "geral"): CSSProperties {
  const { cor, borda } = corMateria(index);
  return {
    backgroundImage:
      `linear-gradient(color-mix(in srgb, ${cor} 76%, transparent), color-mix(in srgb, ${cor} 76%, transparent)), url('${fundoMateria(index, categoria)}')`,
    backgroundSize: "cover",
    backgroundPosition: "center 55%",
    border: `1px solid ${borda}`,
  };
}
