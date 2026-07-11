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
        {/* Aplica o tema salvo ANTES de pintar a tela (evita "piscar" o tema
            errado no carregamento). Padrão: misto. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('tema');if(t!=='claro'&&t!=='misto'&&t!=='escuro')t='misto';document.documentElement.setAttribute('data-theme',t);}catch(e){document.documentElement.setAttribute('data-theme','misto');}})();`,
          }}
        />
      </head>
      <body className={inter.className}>
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
