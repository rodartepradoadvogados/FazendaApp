"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogIn, Loader2, Newspaper, ArrowRight } from "lucide-react";
import { login } from "@/lib/api";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { LoginWatermark } from "@/components/LoginWatermark";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const entrar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro(null); setCarregando(true);
    try {
      await login(username.trim(), senha);
      // Volta para onde a pessoa estava tentando entrar (ex.: /app no celular).
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next && next.startsWith("/") ? next : "/");
    } catch (err: any) {
      setErro(err.message || "Falha no login");
    } finally {
      setCarregando(false);
    }
  };

  const input: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: "var(--text)",
    border: "1px solid var(--border)", borderRadius: "8px", padding: "0.6rem 0.8rem", fontSize: "0.95rem",
  };

  return (
    <div style={{ position: "relative", minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem", background: "var(--bg)", overflow: "hidden" }}>
      <LoginWatermark />
      <div style={{ position: "relative", zIndex: 1, width: "380px", maxWidth: "100%", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div className="card">
          <div className="mb-1" style={{ textAlign: "center" }}>
            <CowDataWordmark size="1.6rem" />
            <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.2rem" }}>Estreito Ponte de Pedra · Jairo Nasser</p>
          </div>
          <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.82rem", margin: "0.75rem 0 1.25rem" }}>Entre com seu usuário e senha.</p>

          <form onSubmit={entrar} className="space-y-3">
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Usuário</label>
              <input style={input} value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" />
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Senha</label>
              <input style={input} type="password" value={senha} onChange={(e) => setSenha(e.target.value)} autoComplete="current-password" />
            </div>
            {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
            <button type="submit" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={carregando || !username || !senha}>
              {carregando ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />} Entrar
            </button>
          </form>
        </div>

        {/* Não precisa de login para ler o blog — aberto a qualquer visitante. */}
        <Link href="/news" style={{
          display: "flex", alignItems: "center", gap: "0.7rem", textDecoration: "none",
          padding: "0.85rem 1.1rem", borderRadius: "12px",
          background: "var(--vinho)", border: "1px solid var(--vinho-light)",
          boxShadow: "0 4px 14px rgba(0,0,0,0.28)",
        }}>
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: "2.1rem", height: "2.1rem", borderRadius: "999px",
            background: "rgba(255,224,102,0.15)", flexShrink: 0,
          }}>
            <Newspaper size={17} style={{ color: "#FFE066" }} />
          </span>
          <span style={{ flex: 1 }}>
            <span style={{ display: "block", color: "#FFE066", fontWeight: 700, fontSize: "0.85rem" }}>News Milk — nosso blog de pecuária leiteira</span>
            <span style={{ display: "block", color: "rgba(255,255,255,0.75)", fontSize: "0.74rem" }}>Aberto a qualquer visitante, sem precisar de login</span>
          </span>
          <ArrowRight size={16} style={{ color: "#FFE066", flexShrink: 0 }} />
        </Link>
      </div>
    </div>
  );
}
