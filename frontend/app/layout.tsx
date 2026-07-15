import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthShell } from "@/components/AuthShell";

const inter = Inter({ subsets: ["latin"] });

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
  themeColor: "#4A1525",
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
            __html: `(function(){try{var t=localStorage.getItem('tema');if(t!=='claro'&&t!=='misto'&&t!=='escuro')t='misto';document.documentElement.setAttribute('data-theme',t);}catch(e){t='misto';document.documentElement.setAttribute('data-theme','misto');}try{var p=localStorage.getItem('paleta');if(p!=='vinho'&&p!=='verde')p='vinho';document.documentElement.setAttribute('data-paleta',p);}catch(e){p='vinho';document.documentElement.setAttribute('data-paleta','vinho');}try{var m=document.querySelector('meta[name="theme-color"]');if(m){var escuro=t==='escuro';var cor=p==='verde'?(escuro?'#16402B':'#1F5C3D'):(escuro?'#340F1C':'#4A1525');m.setAttribute('content',cor);}}catch(e){}})();`,
          }}
        />
      </head>
      <body className={inter.className}>
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
