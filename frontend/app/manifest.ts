import type { MetadataRoute } from "next";
import { COR_TOPO } from "@/lib/themeColorTopo";

// Manifesto PWA — permite "Adicionar à tela inicial" com ícone e tela cheia.
// Existe UM só (o Next serve /manifest.webmanifest a partir deste arquivo,
// ver node_modules/next/dist/docs/.../metadata/manifest.md) e ele vale tanto
// para quem instala do site quanto para quem instala de dentro do /app.
//
// CORRIGIDO (06/09/2026) — `start_url` era "/app". Consequência: quem
// instalava o atalho no NOTEBOOK abria sempre o app de campo (barra inferior,
// telas de celular) e precisava ir no menu do navegador em "acessar site
// completo" toda vez. O padrão certo é o inverso: o app instalado abre o
// SITE COMPLETO, e quem estiver num aparelho de campo é redirecionado para
// /app na hora (ver app/page.tsx::Home e lib/nativo.ts::ehAppDeCampo) — a
// mesma regra "app nativo sempre, PWA instalado só em tela pequena" que já
// valia no Painel CowData.
//
// Por que `id` continua "/app": o id de um PWA instalado, quando não é
// declarado, é DERIVADO da start_url. Os atalhos que já existem hoje foram
// instalados com start_url "/app", então o id deles é "/app". Declarar
// `id: "/app"` aqui é o que faz o navegador reconhecer este manifesto como
// sendo do MESMO app já instalado e atualizar a start_url dele — sem isso,
// o atalho do notebook continuaria abrindo /app para sempre e só instalações
// novas seriam corrigidas. O id não é uma URL que abre; é só a identidade.
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/app",
    name: "Fazenda Estreito Ponte de Pedra",
    short_name: "Fazenda",
    description: "Sistema de gestão da fazenda — rebanho, produção, financeiro e agenda, com app de campo offline.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    // Era "portrait" (herança de quando o manifesto era só do app de campo) —
    // num notebook isso é ou ignorado ou, pior, uma janela em pé. "any" deixa
    // o aparelho decidir; o app de campo continua sendo usado em pé de
    // qualquer forma.
    orientation: "any",
    background_color: COR_TOPO.azul.clara,
    theme_color: COR_TOPO.azul.clara,
    icons: [
      { src: "/icons/icone-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icone-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icone-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    // Atalho para quem usa o mesmo ícone instalado nos dois papéis (ex.: o
    // dono, que abre o site no escritório e o app no curral): segurar o ícone
    // do app abre direto o app de campo, sem passar pelo site.
    shortcuts: [
      { name: "App de campo", short_name: "Campo", url: "/app", description: "Agenda, lançamentos e rebanho na tela do celular" },
    ],
  };
}
