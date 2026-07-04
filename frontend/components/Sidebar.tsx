"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Calendar,
  Heart,
  BarChart3,
  Package,
  Users,
  Upload,
  Home,
  Beef,
} from "lucide-react";

const links = [
  { href: "/",            label: "Capa",        icon: Home },
  { href: "/agenda",      label: "Agenda",       icon: Calendar },
  { href: "/reproducao",  label: "Reprodução",   icon: Heart },
  { href: "/rebanho",     label: "Rebanho",      icon: Beef },
  { href: "/financeiro",  label: "Financeiro",   icon: BarChart3 },
  { href: "/estoque",     label: "Estoque",      icon: Package },
  { href: "/upload",      label: "Upload CSV",   icon: Upload },
];

export function Sidebar() {
  const path = usePathname();

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
        <div className="flex items-center justify-center gap-1.5">
          <span className="pulse-dot" />
          API conectada
        </div>
        <p className="mt-1">v1.0.0 · Sprint 1</p>
      </div>
    </aside>
  );
}
