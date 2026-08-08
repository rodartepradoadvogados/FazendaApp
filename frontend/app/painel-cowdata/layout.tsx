"use client";
// Painel CowData — administração da EMPRESA de software (isolado da Fazenda
// Jairo Nasser, ver AuthShell.tsx::ehPainelCowData). Migrado para a paleta
// "Institucional" do redesign (mesma família marinho+ouro do resto do
// sistema), mas com uma variação própria — fundo creme em vez de branco no
// conteúdo, e o marinho mais profundo (#0A1F36, "marinho profundo" da
// marca) em vez do marinho padrão (#0E2A47) na navegação — para continuar
// se lendo como um painel à parte, nunca "mais uma tela da fazenda".

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutGrid, CreditCard, Building2, Wallet, Users, Bot, Lock, ShieldCheck, ArrowLeft, Menu, X,
} from "lucide-react";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { ehAppOuPwa } from "@/lib/nativo";

const COR = {
  // Conteúdo (fundo creme + texto escuro) — ver comentário no topo do arquivo.
  bg: "#F2E8D5", texto: "#1B2A3A",
  // Painel/navegação (marinho profundo + texto claro) e acentos em ouro,
  // mesma família de cor do resto do redesign (globals.css, paleta azul/claro).
  painel: "#0A1F36", borda: "#173049", textoPainel: "#FFFFFF",
  mudo: "#8DA2B8", dourado: "#8A6D2F", doradoClaro: "#C9A44C",
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
  const [aberto, setAberto] = useState(false);
  // Chegou aqui pelo item "Painel CowData" do Menu do app (ver
  // app/app/menu/page.tsx) — "voltar à fazenda" precisa cair no /app, nunca
  // no site desktop completo (mesma regra do AuthShell::destinoRaiz). Cobre
  // app nativo E PWA instalado (ver lib/nativo.ts::ehAppOuPwa).
  const [voltarHref, setVoltarHref] = useState("/");
  useEffect(() => { ehAppOuPwa().then((app) => { if (app) setVoltarHref("/app"); }); }, []);

  const navConteudo = (
    <>
      <div style={{ padding: "1.1rem 1.1rem 0.9rem" }}>
        <Link href={voltarHref} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", color: COR.mudo, textDecoration: "none", marginBottom: "0.9rem" }}>
          <ArrowLeft size={13} /> Voltar à fazenda
        </Link>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
          <CowDataMark size={40} />
          <CowDataWordmark size="1.1rem" cowColor={COR.textoPainel} dataColor={COR.doradoClaro} />
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
                <Link key={item.href} href={item.href} onClick={() => setAberto(false)}
                  style={{
                    display: "flex", alignItems: "center", gap: "0.55rem", padding: "0.45rem 0.6rem", borderRadius: "8px",
                    fontSize: "0.8rem", textDecoration: "none", marginBottom: "0.15rem",
                    color: ativo ? COR.doradoClaro : "#c3cbde",
                    background: ativo ? "rgba(201,164,76,0.14)" : "transparent",
                    borderLeft: ativo ? `2px solid ${COR.doradoClaro}` : "2px solid transparent",
                  }}>
                  <Icon size={15} /> {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </>
  );

  return (
    <div style={{ minHeight: "100vh", background: COR.bg, color: COR.texto, fontFamily: "system-ui, sans-serif" }} className="md:flex">
      {/* Barra superior — só no mobile. Mesmo padrão do Sidebar.tsx do site. */}
      <div className="md:hidden flex items-center gap-3 px-4 fixed top-0 left-0 right-0 z-30"
        style={{ height: "3.25rem", background: COR.painel, borderBottom: `1px solid ${COR.borda}` }}>
        <button onClick={() => setAberto(true)} aria-label="Abrir menu" title="Abrir o menu do Painel CowData"
          style={{ background: "none", border: "none", color: COR.textoPainel, cursor: "pointer", display: "flex" }}>
          <Menu size={22} />
        </button>
        <CowDataWordmark size="0.85rem" cowColor={COR.textoPainel} dataColor={COR.doradoClaro} />
        <span style={{ color: COR.mudo, fontSize: "0.7rem" }}>· Painel da empresa</span>
      </div>
      <div className="md:hidden" style={{ height: "3.25rem" }} aria-hidden="true" />

      {aberto && <div className="md:hidden fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.55)" }} onClick={() => setAberto(false)} />}

      <aside
        style={{ width: "15rem", flexShrink: 0, background: COR.painel, borderRight: `1px solid ${COR.borda}`, display: "flex", flexDirection: "column" }}
        className={`fixed md:static inset-y-0 left-0 z-50 transform transition-transform duration-200 ${aberto ? "translate-x-0" : "-translate-x-full"} md:translate-x-0`}
      >
        <button onClick={() => setAberto(false)} aria-label="Fechar menu" title="Fechar o menu do Painel CowData"
          className="md:hidden"
          style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", color: COR.mudo, cursor: "pointer" }}>
          <X size={20} />
        </button>
        {navConteudo}
      </aside>
      <main style={{ flex: 1, padding: "1.2rem 1rem", overflowY: "auto", overflowX: "hidden" }} className="md:py-8 md:px-10">{children}</main>
    </div>
  );
}
