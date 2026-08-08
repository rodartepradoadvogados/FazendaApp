"use client";
// Casca do portal "Formulação de Dietas" (/dietas) — mesmo padrão estrutural
// do InsightsLayout (cabeçalho com marca + faixa de navegação, casca própria
// fora da Sidebar da fazenda, aberta numa aba nova de verdade do navegador —
// ver Sidebar.tsx), mas na paleta institucional real do site (var(--wine)/
// var(--gold)), não nos hex azuis legados do InsightsLayout.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, FlaskConical } from "lucide-react";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { getFazendaAtual } from "@/lib/api";

export function DietasLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [fazendaNome, setFazendaNome] = useState("");

  useEffect(() => {
    setFazendaNome(getFazendaAtual()?.nome || "");
  }, [path]);

  const emSimulacao = /^\/dietas\/\d+/.test(path || "");
  const idSimulacao = emSimulacao ? path!.split("/")[2] : null;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <header style={{ background: "linear-gradient(135deg, var(--wine-2), var(--wine))" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", padding: "0.9rem 1.4rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
            <CowDataMark size={34} />
            <div>
              <CowDataWordmark size="1rem" cowColor="var(--cream)" dataColor="var(--gold-pale)" />
              <p style={{ margin: 0, fontSize: "0.68rem", color: "rgba(243,231,211,0.7)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                <FlaskConical size={11} /> Formulação de Dietas{fazendaNome ? ` · ${fazendaNome}` : ""}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => router.push("/")}
            title="Voltar à Capa da fazenda, nesta mesma aba"
            style={{
              display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)",
              border: "1px solid var(--gold-deep)", background: "transparent", color: "var(--gold-pale)",
              fontSize: "0.8rem", fontWeight: 700, cursor: "pointer",
            }}
          >
            <ArrowLeft size={14} /> Voltar
          </button>
        </div>
        <nav style={{ display: "flex", gap: "0.2rem", padding: "0 1rem", overflowX: "auto", borderTop: "1px solid rgba(243,231,211,0.14)" }}>
          <Link href="/dietas" style={{
            padding: "0.65rem 0.9rem", fontSize: "0.82rem", fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap",
            color: path === "/dietas" ? "var(--cream)" : "rgba(243,231,211,0.62)",
            borderBottom: path === "/dietas" ? "2px solid var(--gold)" : "2px solid transparent",
          }}>
            Simulações
          </Link>
          <Link href="/dietas/nova" style={{
            padding: "0.65rem 0.9rem", fontSize: "0.82rem", fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap",
            color: path === "/dietas/nova" ? "var(--cream)" : "rgba(243,231,211,0.62)",
            borderBottom: path === "/dietas/nova" ? "2px solid var(--gold)" : "2px solid transparent",
          }}>
            Nova simulação
          </Link>
          {emSimulacao && (
            <span style={{
              padding: "0.65rem 0.9rem", fontSize: "0.82rem", fontWeight: 600, whiteSpace: "nowrap",
              color: "var(--cream)", borderBottom: "2px solid var(--gold)",
            }}>
              Simulação #{idSimulacao}
            </span>
          )}
        </nav>
      </header>
      <main style={{ padding: "1.4rem" }}>{children}</main>
    </div>
  );
}
