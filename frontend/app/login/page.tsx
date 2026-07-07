"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogIn, Loader2 } from "lucide-react";
import { login } from "@/lib/api";
import { BullLogo } from "@/components/BullLogo";

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
      router.replace("/");
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
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem", background: "var(--bg)" }}>
      <div className="card" style={{ width: "380px", maxWidth: "100%" }}>
        <div className="flex items-center gap-2 mb-1" style={{ justifyContent: "center" }}>
          <BullLogo size={30} />
          <div style={{ textAlign: "center" }}>
            <p style={{ color: "var(--dourado-light)", fontWeight: 800, letterSpacing: "0.05em" }}>FAZENDA ESTREITO PONTE DE PEDRA</p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>Jairo Nasser</p>
          </div>
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
    </div>
  );
}
