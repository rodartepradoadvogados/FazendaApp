import type { CSSProperties } from "react";
import type { NoticiaNews } from "@/lib/api";

// Visual compartilhado das matérias do News (site + app): fundo fotográfico
// alternado entre TODAS as fotos temáticas do site (as 5 de
// components/SectionBackground.tsx + a do login) e cor de destaque alternada
// entre vinho e verde — uma foto e uma cor por matéria, em sequência, sempre
// a mesma combinação para o mesmo índice (não depende da paleta escolhida
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

export function fundoMateria(index: number): string {
  return FUNDOS_MATERIA[index % FUNDOS_MATERIA.length];
}

export function corMateria(index: number): { cor: string; borda: string } {
  return CORES_MATERIA[index % CORES_MATERIA.length];
}

/** Ilustração de uma matéria (#news-redesign): foto do banco de imagens
 * quando a matéria tem `imagem`; senão cai no fundo temático rotativo
 * (mesma foto por índice, sempre a mesma combinação). Compartilhado entre
 * a página pública (app/news/page.tsx), o admin do site (NewsAdmin.tsx) e o
 * admin do app (mobile/menu/News.tsx) para as três telas ficarem consistentes. */
export function imagemMateria(n: NoticiaNews, index: number): string {
  return n.imagem || fundoMateria(index);
}

/** Estilo completo do cartão de matéria (site e app): foto + camada de cor
 * alternadas por índice. */
export function estiloCardMateria(index: number): CSSProperties {
  const { cor, borda } = corMateria(index);
  return {
    backgroundImage:
      `linear-gradient(color-mix(in srgb, ${cor} 76%, transparent), color-mix(in srgb, ${cor} 76%, transparent)), url('${fundoMateria(index)}')`,
    backgroundSize: "cover",
    backgroundPosition: "center 55%",
    border: `1px solid ${borda}`,
  };
}
