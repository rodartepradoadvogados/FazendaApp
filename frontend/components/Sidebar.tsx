"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Calendar,
  Heart,
  BarChart3,
  Package,
  Home,
  Beef,
  LineChart,
  Milk,
  Wheat,
  Syringe,
  Settings,
  ClipboardList,
  Menu,
  X,
} from "lucide-react";
import { checkHealth, getUsuario, logout, podeModulo, ehAdmin, ROTA_MODULO } from "@/lib/api";
import { LogOut, UserCircle } from "lucide-react";
import { BullLogo } from "@/components/BullLogo";

const links = [
  { href: "/",            label: "Capa",        icon: Home },
  { href: "/indicadores", label: "Indicadores",  icon: LineChart },
  { href: "/agenda",      label: "Agenda",       icon: Calendar },
  { href: "/lancamentos", label: "Lançamentos",  icon: ClipboardList },
  { href: "/reproducao",  label: "Reprodução",   icon: Heart },
  { href: "/rebanho",     label: "Rebanho",      icon: Beef },
  { href: "/producao",    label: "Produção",     icon: Milk },
  { href: "/alimentacao", label: "Alimentação",  icon: Wheat },
  { href: "/sanidade",    label: "Sanidade",     icon: Syringe },
  { href: "/financeiro",  label: "Financeiro",   icon: BarChart3 },
  { href: "/estoque",     label: "Sanidade/Estoque", icon: Package },
];

export function Sidebar() {
  const path = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);
  const [aberto, setAberto] = useState(false); // drawer no mobile
  const [visiveis, setVisiveis] = useState(links);
  const [admin, setAdmin] = useState(false);

  const [temConfiguracoes, setTemConfiguracoes] = useState(false);

  useEffect(() => {
    // Filtra o menu conforme as permissões do usuário logado.
    setVisiveis(links.filter((l) => podeModulo(ROTA_MODULO[l.href] || l.href)));
    setAdmin(ehAdmin());
    setTemConfiguracoes(podeModulo("parametros") || podeModulo("upload") || ehAdmin());
  }, [path]);

  useEffect(() => {
    let ativo = true;
    const ping = () => checkHealth().then((ok) => ativo && setOnline(ok));
    ping();
    const id = setInterval(ping, 30000);
    return () => {
      ativo = false;
      clearInterval(id);
    };
  }, []);

  // Fecha o menu ao trocar de página (no mobile).
  useEffect(() => { setAberto(false); }, [path]);

  const statusLabel =
    online === null ? "Verificando..." : online ? "API conectada" : "API offline";
  const statusColor =
    online === null ? "var(--text-muted)" : online ? "var(--green-light)" : "var(--red)";

  return (
    <>
      {/* Barra superior — só no mobile */}
      <div className="md:hidden flex items-center gap-3 px-4 py-3 sticky top-0 z-30"
        style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
        <button onClick={() => setAberto(true)} aria-label="Abrir menu"
          style={{ background: "none", border: "none", color: "var(--text)", cursor: "pointer", display: "flex" }}>
          <Menu size={22} />
        </button>
        <BullLogo size={18} />
        <span style={{ color: "var(--dourado-light)", fontSize: "0.8rem", fontWeight: 800, letterSpacing: "0.05em" }}>FAZENDA</span>
        <span style={{ color: "var(--text-muted)", fontSize: "0.7rem" }}>· Jairo Nasser</span>
      </div>

      {/* Fundo escuro atrás do drawer aberto (mobile) */}
      {aberto && <div className="md:hidden fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.55)" }} onClick={() => setAberto(false)} />}

      <aside
        style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }}
        className={`w-56 flex flex-col flex-shrink-0 h-full fixed md:static inset-y-0 left-0 z-50 transform transition-transform duration-200 ${aberto ? "translate-x-0" : "-translate-x-full"} md:translate-x-0`}
      >
      {/* Botão fechar — só no mobile */}
      <button onClick={() => setAberto(false)} aria-label="Fechar menu"
        className="md:hidden"
        style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}>
        <X size={20} />
      </button>
      {/* Logo */}
      <div
        className="p-4 border-b"
        style={{ borderColor: "var(--border)" }}
      >
        <div
          className="flex items-center gap-2 px-2 py-2 rounded-lg"
          style={{ background: "linear-gradient(135deg, var(--vinho), var(--vinho-dark))" }}
        >
          <BullLogo size={22} />
          <div>
            <p style={{ color: "var(--dourado-light)", fontSize: "0.7rem", fontWeight: 800, letterSpacing: "0.05em", lineHeight: 1.2 }}>
              FAZENDA
            </p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.6rem", lineHeight: 1.2 }}>
              Jairo Nasser
            </p>
          </div>
        </div>
      </div>

      {/* Nav links */}
      <nav className="flex-1 p-3 space-y-1" style={{ overflowY: "auto" }}>
        {[...visiveis, ...(temConfiguracoes ? [{ href: "/configuracoes", label: "Configurações", icon: Settings }] : [])].map(({ href, label, icon: Icon }) => {
          const active = path === href || (href !== "/" && path.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150"
              style={{
                background: active ? "rgba(94,26,46,0.4)" : "transparent",
                color: active ? "var(--dourado-light)" : "var(--text-muted)",
                borderLeft: active ? "3px solid var(--dourado)" : "3px solid transparent",
              }}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div
        className="p-4 border-t text-center"
        style={{ borderColor: "var(--border)", fontSize: "0.65rem", color: "var(--text-muted)" }}
      >
        <div className="flex items-center justify-center gap-1.5" style={{ color: statusColor }}>
          <span
            className={online === false ? "" : "pulse-dot"}
            style={
              online === false
                ? { width: 8, height: 8, borderRadius: "50%", background: "var(--red)", display: "inline-block" }
                : undefined
            }
          />
          {statusLabel}
        </div>
        <UsuarioLogado />
        <p className="mt-1">v1.0.0 · Sprint 1</p>
      </div>
      </aside>
    </>
  );
}

function UsuarioLogado() {
  const [nome, setNome] = useState<string | null>(null);
  useEffect(() => { const u = getUsuario(); setNome(u?.nome || u?.username || null); }, []);
  if (!nome) return null;
  return (
    <div className="mt-2" style={{ fontSize: "0.68rem" }}>
      <div className="flex items-center justify-center gap-1.5 mb-1.5" style={{ color: "var(--text)" }}>
        <UserCircle size={13} /> {nome}
      </div>
      <button onClick={logout} title="Encerra a sessão — a próxima pessoa faz login com o próprio usuário"
        className="flex items-center justify-center gap-1.5 mx-auto"
        style={{ background: "none", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.3rem 0.6rem", color: "var(--text-muted)", cursor: "pointer" }}>
        <LogOut size={12} /> Sair / trocar de usuário
      </button>
    </div>
  );
}
