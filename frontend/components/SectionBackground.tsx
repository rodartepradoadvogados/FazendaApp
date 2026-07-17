"use client";
import { usePathname } from "next/navigation";

// Fundo temático leve por área do site — mesmo tratamento visual do login e
// da página News (baixa opacidade, tons de cinza, mixBlendMode luminosity),
// só que trocando a foto conforme a seção. Preenche só a área de conteúdo
// (o <main> à direita da barra lateral), nunca a própria barra lateral.
const SECOES: { prefixos: string[]; imagem: string }[] = [
  { prefixos: ["/rebanho", "/reproducao", "/producao"], imagem: "/images/bg-rebanho.webp" },
  { prefixos: ["/sanidade", "/alimentacao", "/estoque"], imagem: "/images/bg-insumos-sanidade.webp" },
  { prefixos: ["/indicadores", "/financeiro", "/pedidos", "/relatorios"], imagem: "/images/bg-analise.webp" },
  { prefixos: ["/aprovacoes", "/configuracoes"], imagem: "/images/bg-administracao.webp" },
  { prefixos: ["/agenda", "/lancamentos"], imagem: "/images/bg-ciclo-diario.webp" },
];

function imagemPara(pathname: string): string | null {
  if (pathname === "/") return "/images/bg-ciclo-diario.webp"; // Capa
  for (const { prefixos, imagem } of SECOES) {
    if (prefixos.some((p) => pathname.startsWith(p))) return imagem;
  }
  return null;
}

export function SectionBackground() {
  const pathname = usePathname() || "/";
  // News já tem o próprio fundo (ícone de jornal, tratamento específico).
  if (pathname.startsWith("/news")) return null;
  const imagem = imagemPara(pathname);
  if (!imagem) return null;
  return (
    <div aria-hidden="true" style={{ position: "fixed", inset: 0, zIndex: 0, overflow: "hidden", pointerEvents: "none" }}>
      <img
        key={imagem}
        src={imagem}
        alt=""
        style={{
          position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: "center 55%",
          opacity: 0.08, filter: "grayscale(1) contrast(1.08) brightness(0.95)", mixBlendMode: "luminosity",
        }}
      />
    </div>
  );
}
