"use client";
// Painel CowData — administração da EMPRESA de software (isolado da Fazenda
// Jairo Nasser, ver AuthShell.tsx::ehPainelCowData). Paleta e estrutura
// deliberadamente distintas do app da fazenda (navy + dourado, à parte da
// paleta vinho/verde do resto do sistema) para que nunca pareça "mais uma
// tela da fazenda" — reforça visualmente a separação de dados/negócio.
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutGrid, CreditCard, Building2, Wallet, Users, Bot, Lock, ShieldCheck, ArrowLeft,
} from "lucide-react";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";

const COR = {
  bg: "#0a0e1a", painel: "#0d1220", borda: "#1c2438", texto: "#e8ecf5",
  mudo: "#7c8aa8", dourado: "#d4a017", doradoClaro: "#e8c256",
};

const GRUPOS = [
  {
    titulo: "Negócio",
    itens: [
      { href: "/painel-cowdata", label: "Cockpit", icon: LayoutGrid },
      { href: "/painel-cowdata/assinaturas", label: "Assinaturas", icon: CreditCard },
      { href: "/painel-cowdata/fazendas", label: "Fazendas (clientes)", icon: Building2 },
    ],
  },
  {
    titulo: "Administração",
    itens: [
      { href: "/painel-cowdata/financeiro", label: "Financeiro CowData", icon: Wallet },
      { href: "/painel-cowdata/equipe", label: "Equipe CowData", icon: Users },
    ],
  },
  {
    titulo: "Operação",
    itens: [
      { href: "/painel-cowdata/produto", label: "Produto e robôs", icon: Bot },
      { href: "/painel-cowdata/cofre", label: "Cofre de acesso", icon: Lock },
      { href: "/painel-cowdata/confianca", label: "Confiança e LGPD", icon: ShieldCheck },
    ],
  },
];

export default function PainelCowDataLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: COR.bg, color: COR.texto, fontFamily: "system-ui, sans-serif" }}>
      <aside style={{ width: "15rem", flexShrink: 0, background: COR.painel, borderRight: `1px solid ${COR.borda}`, display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "1.1rem 1.1rem 0.9rem" }}>
          <Link href="/" style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", color: COR.mudo, textDecoration: "none", marginBottom: "0.9rem" }}>
            <ArrowLeft size={13} /> Voltar à fazenda
          </Link>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            <CowDataMark size={40} />
            <CowDataWordmark size="1.1rem" cowColor={COR.texto} dataColor={COR.doradoClaro} />
          </div>
          <p style={{ fontSize: "0.62rem", color: COR.mudo, textTransform: "uppercase", letterSpacing: "0.08em", marginTop: "0.4rem" }}>
            Painel da empresa
          </p>
        </div>
        <nav style={{ flex: 1, padding: "0.4rem 0.8rem", overflowY: "auto" }}>
          {GRUPOS.map((g) => (
            <div key={g.titulo} style={{ marginBottom: "1.1rem" }}>
              <p style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: COR.mudo, margin: "0 0 0.4rem 0.5rem" }}>
                {g.titulo}
              </p>
              {g.itens.map((item) => {
                const ativo = item.href === "/painel-cowdata" ? path === item.href : path.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link key={item.href} href={item.href}
                    style={{
                      display: "flex", alignItems: "center", gap: "0.55rem", padding: "0.45rem 0.6rem", borderRadius: "8px",
                      fontSize: "0.8rem", textDecoration: "none", marginBottom: "0.15rem",
                      color: ativo ? COR.doradoClaro : "#c3cbde",
                      background: ativo ? "rgba(212,160,23,0.12)" : "transparent",
                      borderLeft: ativo ? `2px solid ${COR.dourado}` : "2px solid transparent",
                    }}>
                    <Icon size={15} /> {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>
      <main style={{ flex: 1, padding: "2rem 2.5rem", overflowY: "auto" }}>{children}</main>
    </div>
  );
}
