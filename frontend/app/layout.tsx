import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";

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
    <html lang="pt-BR">
      <body className={inter.className}>
        {/* Coluna no mobile (barra + conteúdo empilhados); linha no desktop (menu à esquerda). */}
        <div className="md:flex md:h-screen bg-fazenda-bg md:overflow-hidden">
          <Sidebar />
          <main className="flex-1 md:overflow-y-auto app-main">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
