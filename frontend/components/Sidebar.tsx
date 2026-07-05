"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Calendar,
  Heart,
  BarChart3,
  Package,
  Upload,
  Home,
  Beef,
  LineChart,
} from "lucide-react";
import { checkHealth } from "@/lib/api";

const links = [
  { href: "/",            label: "Capa",        icon: Home },
  { href: "/indicadores", label: "Indicadores",  icon: LineChart },
  { href: "/agenda",      label: "Agenda",       icon: Calendar },
  { href: "/reproducao",  label: "Reprodução",   icon: Heart },
  { href: "/rebanho",     label: "Rebanho",      icon: Beef },
  { href: "/financeiro",  label: "Financeiro",   icon: BarChart3 },
  { href: "/estoque",     label: "Estoque",      icon: Package },
  { href: "/upload",      label: "Upload CSV",   icon: Upload },
];

export function Sidebar() {
  const path = usePathname();
  const [online, setOnline] = useState<boolean | null>(null);

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

  const statusLabel =
    online === null ? "Verificando..." : online ? "API conectada" : "API offline";
  const statusColor =
    online === null ? "var(--text-muted)" : online ? "var(--green-light)" : "var(--red)";

  return (
    <aside
      style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }}
      className="w-56 flex flex-col flex-shrink-0 h-full"
    >
      {/* Logo */}
      <div
        className="p-4 border-b"
        style={{ borderColor: "var(--border)" }}
      >
        <div
          className="flex items-center gap-2 px-2 py-2 rounded-lg"
          style={{ background: "linear-gradient(135deg, var(--vinho), var(--vinho-dark))" }}
        >
          <Beef size={20} color="var(--dourado-light)" />
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
      <nav className="flex-1 p-3 space-y-1">
        {links.map(({ href, label, icon: Icon }) => {
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
        <p className="mt-1">v1.0.0 · Sprint 1</p>
      </div>
    </aside>
  );
}
