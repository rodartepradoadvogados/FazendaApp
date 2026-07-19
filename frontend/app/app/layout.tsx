"use client";
// Casca do APP MÓVEL (/app): cabeçalho (vinho ou verde) com status online/offline,
// alternador claro/escuro, badge de pendências e navegação inferior fixa
// (Agenda · Lançar · Rebanho · Menu). Registra o service worker (abre sem
// internet) e liga a sincronização automática da fila offline.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CalendarCheck, PlusCircle, Beef, Menu as MenuIcon, Sun, Moon, CloudUpload } from "lucide-react";
import { aplicarTema } from "@/components/ThemeSwitcher";
import { iniciarSincronizacaoAutomatica, useOnline, usePendentes } from "@/lib/offline";
import { InstalarApp } from "@/components/mobile/InstalarApp";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { NewsIcon } from "@/components/mobile/NewsIcon";
import { ehAdmin } from "@/lib/api";

const ABAS = [
  { href: "/app", label: "Agenda", icon: CalendarCheck },
  { href: "/app/lancar", label: "Lançar", icon: PlusCircle },
  { href: "/app/rebanho", label: "Rebanho", icon: Beef },
  { href: "/app/menu", label: "Menu", icon: MenuIcon },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const online = useOnline();
  const fila = usePendentes();
  const [escuro, setEscuro] = useState(false);
  // Cabeçalho FIXO (não some ao rolar). Medimos a altura real — que varia com a
  // faixa de segurança do topo (notch) — para reservar o mesmo espaço abaixo.
  const headerRef = useRef<HTMLElement | null>(null);
  const [alturaHeader, setAlturaHeader] = useState(64);

  // Tema: no app só existe claro (alto contraste) e escuro (OLED); o "misto"
  // do site é tratado como claro aqui.
  useEffect(() => {
    setEscuro(document.documentElement.getAttribute("data-theme") === "escuro");
  }, []);
  function alternarTema() {
    const novo = escuro ? "claro" : "escuro";
    setEscuro(!escuro);
    aplicarTema(novo as "claro" | "escuro");
  }

  // Mede a altura do cabeçalho fixo e mantém o espaçador sincronizado.
  useEffect(() => {
    const medir = () => { if (headerRef.current) setAlturaHeader(headerRef.current.offsetHeight); };
    medir();
    window.addEventListener("resize", medir);
    return () => window.removeEventListener("resize", medir);
  }, [fila.length]);

  // Service worker (abrir offline) + sincronização automática da fila.
  useEffect(() => {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    }
    return iniciarSincronizacaoAutomatica();
  }, []);

  return (
    <div className="mob">
      {/* Cabeçalho (vinho ou verde, conforme a paleta) — FIXO no topo (não some ao rolar no celular). */}
      <header ref={headerRef} style={{ background: "var(--mob-header)", color: "var(--mob-header-fg)", padding: "calc(0.9rem + env(safe-area-inset-top)) 1.1rem 0.9rem", borderRadius: "0 0 18px 18px", position: "fixed", top: 0, left: 0, right: 0, zIndex: 40 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", maxWidth: 560, margin: "0 auto" }}>
          <div>
            <p style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
              <CowDataWordmark size="1rem" cowColor="var(--mob-header-fg)" dataColor="var(--mob-dourado-2)" />
              {/* Bolinha de conexão: verde luminoso online, vermelha offline */}
              <span
                title={online ? "Conectado à internet" : "Sem internet — os lançamentos ficam guardados e serão enviados quando conectar"}
                style={{
                  width: 9, height: 9, borderRadius: "50%", display: "inline-block",
                  background: online ? "var(--mob-verde-neon)" : "#FF4D4D",
                  boxShadow: online ? "0 0 7px rgba(0,255,157,0.8)" : "0 0 7px rgba(255,77,77,0.8)",
                }}
              />
            </p>
            <p style={{ fontSize: "0.68rem", opacity: 0.85 }}>Estreito Ponte de Pedra</p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {fila.length > 0 && (
              <Link href="/app/menu#pendentes" title={`${fila.length} lançamento(s) aguardando internet para enviar`}
                style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.72rem", fontWeight: 700, color: "#F8E9B0", background: "rgba(255,255,255,0.12)", borderRadius: 999, padding: "0.3rem 0.6rem", textDecoration: "none" }}>
                <CloudUpload size={14} /> {fila.length}
              </Link>
            )}
            {ehAdmin() && (
              <Link href="/app/menu#news" title="News — notícias de pecuária leiteira" aria-label="Abrir News"
                style={{ width: 44, height: 44, borderRadius: "50%", background: "rgba(255,255,255,0.12)", color: "var(--mob-header-fg)", display: "flex", alignItems: "center", justifyContent: "center", textDecoration: "none" }}>
                <NewsIcon size={19} color="var(--mob-header-fg)" />
              </Link>
            )}
            <button type="button" onClick={alternarTema} aria-label={escuro ? "Mudar para tema claro" : "Mudar para tema escuro"}
              style={{ width: 44, height: 44, borderRadius: "50%", border: "none", cursor: "pointer", background: "rgba(255,255,255,0.12)", color: "var(--mob-header-fg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              {escuro ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </div>
      </header>

      {/* Espaçador da altura do cabeçalho fixo — evita que o conteúdo comece por baixo dele. */}
      <div aria-hidden="true" style={{ height: alturaHeader }} />

      {/* Conteúdo da aba */}
      <main className="mob-conteudo">
        <InstalarApp />
        {children}
      </main>

      {/* Navegação inferior (zona do polegar) */}
      <nav className="mob-nav">
        {ABAS.map(({ href, label, icon: Icon }) => {
          const ativo = href === "/app" ? path === "/app" : path.startsWith(href);
          return (
            <Link key={href} href={href} className={ativo ? "ativo" : ""}>
              <span className="mob-nav-icone"><Icon size={21} strokeWidth={ativo ? 2.4 : 1.8} /></span>
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
