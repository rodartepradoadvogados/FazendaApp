"use client";
// Painel CowData — administração da EMPRESA de software (isolado da Fazenda
// Jairo Nasser, ver AuthShell.tsx::ehPainelCowData). Mesma paleta do Painel
// do Contador (CORES_CONTADOR, ver app/contador/layout.tsx) — pedido
// explícito do usuário: os dois painéis administrativos "à parte" da
// fazenda devem se ler como a mesma família visual entre si (cinza-azulado
// neutro sobre grafite), não duas identidades diferentes.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import {
  LayoutGrid, CreditCard, Building2, Wallet, Users, Bot, Lock, ShieldCheck, ArrowLeft, Menu, X,
} from "lucide-react";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { ehAppOuPwa } from "@/lib/nativo";
import { CORES_CONTADOR } from "@/app/contador/layout";

const COR = {
  bg: CORES_CONTADOR.bg, texto: CORES_CONTADOR.texto,
  painel: CORES_CONTADOR.painel, borda: CORES_CONTADOR.borda, textoPainel: CORES_CONTADOR.texto,
  mudo: CORES_CONTADOR.mudo, dourado: CORES_CONTADOR.cobre, doradoClaro: CORES_CONTADOR.cobreClaro,
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
                    display: "flex", alignItems: "center", gap: "0.55rem", padding: "0.45rem 0.6rem", borderRadius: "var(--r-sm)",
                    fontSize: "0.8rem", textDecoration: "none", marginBottom: "0.15rem",
                    color: ativo ? COR.doradoClaro : "#c3cbde",
                    background: ativo ? "rgba(143,160,181,0.14)" : "transparent",
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

  // FazendasAdmin.tsx (única tela daqui que reaproveita .card/.card-header do
  // site) herdava --surface/--text do TEMA DO SITE (claro/escuro/misto,
  // configurável em Aparência) em vez da paleta fixa deste painel — com o
  // site em tema claro, o texto (quase branco, pensado pra fundo escuro)
  // ficava ilegível sobre o card branco. Redefinindo os tokens aqui, escopados
  // a esta subárvore, qualquer coisa que use .card/.card-header sempre lê
  // certo, independente do tema do site logado.
  const tokensPainel = {
    "--surface": COR.painel, "--surface-2": CORES_CONTADOR.painelAlt,
    "--border": COR.borda, "--border-strong": CORES_CONTADOR.bordaClara,
    "--text": COR.texto, "--text-muted": COR.mudo,
    "--card-header-bg": CORES_CONTADOR.painelAlt, "--card-header-fg": COR.dourado,
    "--pill-active-bg": COR.dourado, "--pill-active-fg": COR.bg,
  } as CSSProperties;

  return (
    <div style={{ minHeight: "100vh", background: COR.bg, color: COR.texto, fontFamily: "system-ui, sans-serif", ...tokensPainel }} className="md:flex">
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
