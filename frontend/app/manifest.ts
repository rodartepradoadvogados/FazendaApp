import type { MetadataRoute } from "next";

// Manifesto PWA — permite "Adicionar à tela inicial" com ícone e tela cheia.
// O app do campo mora em /app; o site completo continua em /.
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Fazenda Estreito Ponte de Pedra",
    short_name: "Fazenda",
    description: "App de campo da fazenda — agenda, lançamentos e rebanho, com trabalho offline.",
    start_url: "/app",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#4A1525",
    theme_color: "#4A1525",
    icons: [
      { src: "/icons/icone-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icone-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icons/icone-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
