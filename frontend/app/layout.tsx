import type { Metadata } from "next";
import { Inter, Dancing_Script, Sora } from "next/font/google";
import "./globals.css";
import { AuthShell } from "@/components/AuthShell";
import { TabsShell } from "@/components/TabsShell";
import { COR_TOPO } from "@/lib/themeColorTopo";

const inter = Inter({ subsets: ["latin"] });
// Só para o "milk" cursivo da marca d'água da tela de login (ver LoginWatermark).
const dancingScript = Dancing_Script({ subsets: ["latin"], weight: "700", variable: "--font-script" });
// Tipografia de marca (manual de identidade CowData) para nome e títulos —
// hoje só aplicada no Milk News (ver NewsShell/app/news/page.tsx); disponível
// em toda a árvore via var(--font-sora) para uso futuro.
const sora = Sora({ subsets: ["latin"], weight: ["700", "800"], variable: "--font-sora" });

export const metadata: Metadata = {
  title: "Fazenda Estreito Ponte de Pedra",
  description: "Painel gerencial de pecuária leiteira — Jairo Nasser",
  // PWA / iPhone: ícone da tela inicial e modo tela-cheia ao instalar o /app.
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "Fazenda" },
  icons: { apple: "/icons/icone-180.png" },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
  themeColor: COR_TOPO.vinho.clara,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <head>
        {/* Aplica o tema e a paleta salvos ANTES de pintar a tela (evita
            "piscar" o tema/cor errado no carregamento). Padrão: misto/vinho.
            Também sincroniza a <meta name="theme-color"> (a faixa do topo do
            navegador/app instalado) com o cabeçalho do app — sem isso, ela
            ficava sempre vinho mesmo com a paleta verde escolhida. */}
        <script
          dangerouslySetInnerHTML={{
            // Cores geradas a partir de COR_TOPO (lib/themeColorTopo.ts) — fonte
            // única também usada por manifest.ts e ThemeSwitcher.tsx.
            __html: `(function(){try{var t=localStorage.getItem('tema');if(t!=='claro'&&t!=='misto'&&t!=='escuro')t='misto';document.documentElement.setAttribute('data-theme',t);}catch(e){t='misto';document.documentElement.setAttribute('data-theme','misto');}try{var p=localStorage.getItem('paleta');if(p!=='vinho'&&p!=='verde'&&p!=='azul')p='vinho';document.documentElement.setAttribute('data-paleta',p);}catch(e){p='vinho';document.documentElement.setAttribute('data-paleta','vinho');}try{var m=document.querySelector('meta[name="theme-color"]');if(m){var escuro=t==='escuro';var CT={vinho:{clara:'${COR_TOPO.vinho.clara}',escura:'${COR_TOPO.vinho.escura}'},verde:{clara:'${COR_TOPO.verde.clara}',escura:'${COR_TOPO.verde.escura}'},azul:{clara:'${COR_TOPO.azul.clara}',escura:'${COR_TOPO.azul.escura}'}};var paleta=CT[p]||CT.vinho;m.setAttribute('content',escuro?paleta.escura:paleta.clara);}}catch(e){}})();`,
          }}
        />
      </head>
      <body className={`${inter.className} ${dancingScript.variable} ${sora.variable}`}>
        <TabsShell>
          <AuthShell>{children}</AuthShell>
        </TabsShell>
      </body>
    </html>
  );
}
