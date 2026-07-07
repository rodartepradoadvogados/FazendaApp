"use client";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";

/**
 * Porta de entrada: só mostra o sistema para quem estiver logado.
 * A rota /login é aberta; qualquer outra sem token redireciona para o login.
 */
export function AuthShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [estado, setEstado] = useState<"checando" | "logado" | "deslogado">("checando");

  useEffect(() => {
    if (path === "/login") { setEstado("deslogado"); return; }
    if (getToken()) { setEstado("logado"); }
    else { setEstado("deslogado"); router.replace("/login"); }
  }, [path, router]);

  if (path === "/login") return <>{children}</>;

  if (estado !== "logado") {
    return <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>Carregando…</div>;
  }

  return (
    <div className="md:flex md:h-screen bg-fazenda-bg md:overflow-hidden">
      <Sidebar />
      <main className="flex-1 md:overflow-y-auto app-main">{children}</main>
    </div>
  );
}
