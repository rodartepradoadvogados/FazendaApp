import type { Metadata } from "next";
import { Inter, Barlow, Barlow_Condensed, Dancing_Script, Sora } from "next/font/google";
import "./globals.css";
import { AuthShell } from "@/components/AuthShell";
import { TabsShell } from "@/components/TabsShell";
import { SubNavProvider } from "@/components/SubNavContext";
import { COR_TOPO } from "@/lib/themeColorTopo";

// Nenhuma dessas quatro usa .className — só .variable (expõe uma CSS custom
// property, não aplica a fonte sozinha). Quem decide qual fonte cada parte
// da árvore usa é o globals.css, via --font-body/--font-heading (ver ali):
// o site (fora de .mob) usa Barlow/Barlow Condensed; o app de campo (dentro
// de .mob) continua em Inter, sem nenhuma mudança — o redesign visual desta
// rodada é só do site.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
// Corpo do site — proposta de redesign "Institucional".
const barlow = Barlow({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-barlow" });
// Títulos, rótulos e números do site — a mesma proposta.
const barlowCondensed = Barlow_Condensed({ subsets: ["latin"], weight: ["400", "500", "600", "700"], variable: "--font-barlow-condensed" });
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
  themeColor: COR_TOPO.azul.clara,
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
            "piscar" o tema/cor errado no carregamento). Padrão de fábrica:
            claro/azul (redesign "Institucional") — era misto/vinho; quem já
            tem preferência salva em localStorage não é afetado, só o usuário
            novo/sem escolha feita passa a cair no novo padrão.
            Também sincroniza a <meta name="theme-color"> (a faixa do topo do
            navegador/app instalado) com o cabeçalho do app — sem isso, ela
            ficava sempre vinho mesmo com a paleta verde escolhida. */}
        <script
          dangerouslySetInnerHTML={{
            // Cores geradas a partir de COR_TOPO (lib/themeColorTopo.ts) — fonte
            // única também usada por manifest.ts e ThemeSwitcher.tsx.
            __html: `(function(){try{var t=localStorage.getItem('tema');if(t!=='claro'&&t!=='misto'&&t!=='escuro')t='claro';document.documentElement.setAttribute('data-theme',t);}catch(e){t='claro';document.documentElement.setAttribute('data-theme','claro');}try{var p=localStorage.getItem('paleta');if(p!=='vinho'&&p!=='verde'&&p!=='azul')p='azul';document.documentElement.setAttribute('data-paleta',p);}catch(e){p='azul';document.documentElement.setAttribute('data-paleta','azul');}try{var m=document.querySelector('meta[name="theme-color"]');if(m){var escuro=t==='escuro';var CT={vinho:{clara:'${COR_TOPO.vinho.clara}',escura:'${COR_TOPO.vinho.escura}'},verde:{clara:'${COR_TOPO.verde.clara}',escura:'${COR_TOPO.verde.escura}'},azul:{clara:'${COR_TOPO.azul.clara}',escura:'${COR_TOPO.azul.escura}'}};var paleta=CT[p]||CT.azul;m.setAttribute('content',escuro?paleta.escura:paleta.clara);}}catch(e){}})();`,
          }}
        />
      </head>
      <body className={`${inter.variable} ${barlow.variable} ${barlowCondensed.variable} ${dancingScript.variable} ${sora.variable}`}>
        <SubNavProvider>
          <TabsShell>
            <AuthShell>{children}</AuthShell>
          </TabsShell>
        </SubNavProvider>
      </body>
    </html>
  );
}
