import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthShell } from "@/components/AuthShell";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Fazenda Estreito Ponte de Pedra",
  description: "Painel gerencial de pecuária leiteira — Jairo Nasser",
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
            errado no carregamento). Padrão: escuro. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=localStorage.getItem('tema');if(t!=='claro'&&t!=='misto'&&t!=='escuro')t='escuro';document.documentElement.setAttribute('data-theme',t);}catch(e){document.documentElement.setAttribute('data-theme','escuro');}})();`,
          }}
        />
      </head>
      <body className={inter.className}>
        <AuthShell>{children}</AuthShell>
      </body>
    </html>
  );
}
