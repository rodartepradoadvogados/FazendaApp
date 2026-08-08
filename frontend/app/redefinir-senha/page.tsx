"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, Eye, EyeOff, KeyRound, Loader2 } from "lucide-react";
import { redefinirSenha } from "@/lib/api";
import { PublicPage } from "@/components/institucional/PublicShell";

function Formulario() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";

  const [novaSenha, setNovaSenha] = useState("");
  const [confirmar, setConfirmar] = useState("");
  const [mostrar, setMostrar] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [sucesso, setSucesso] = useState(false);

  const input: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: "var(--text)",
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem", fontSize: "0.95rem",
  };

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro(null);
    if (novaSenha.length < 4) { setErro("A senha deve ter ao menos 4 caracteres."); return; }
    if (novaSenha !== confirmar) { setErro("As senhas não coincidem."); return; }
    setCarregando(true);
    try {
      await redefinirSenha(token, novaSenha);
      setSucesso(true);
    } catch (err: any) {
      setErro(err.message || "Não foi possível redefinir a senha.");
    } finally {
      setCarregando(false);
    }
  };

  return (
    <section style={{ padding: "4.5rem 1.5rem", minHeight: "70vh", display: "flex", justifyContent: "center", alignItems: "flex-start" }}>
      <div className="card" style={{ maxWidth: "26rem", width: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.4rem" }}>
          <KeyRound size={20} style={{ color: "var(--dourado-light)" }} />
          <h1 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>Definir nova senha</h1>
        </div>

        {!token && (
          <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>
            Link inválido — faltou o token de redefinição. Peça um novo link na tela de login.
          </p>
        )}

        {token && sucesso && (
          <div style={{ textAlign: "center", padding: "1rem 0" }}>
            <CheckCircle2 size={40} style={{ color: "var(--green-light)", marginBottom: "0.6rem" }} />
            <p style={{ fontSize: "0.9rem", color: "var(--text-muted)", margin: "0 0 1rem" }}>
              Senha redefinida com sucesso. Você já pode entrar com a nova senha.
            </p>
            <button type="button" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} onClick={() => router.replace("/login")}>
              Ir para o login
            </button>
          </div>
        )}

        {token && !sucesso && (
          <form onSubmit={enviar} className="space-y-3">
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Nova senha</label>
              <div style={{ position: "relative" }}>
                <input style={{ ...input, paddingRight: "2.4rem" }} type={mostrar ? "text" : "password"} value={novaSenha}
                  onChange={(e) => setNovaSenha(e.target.value)} autoFocus autoComplete="new-password" />
                <button type="button" onClick={() => setMostrar((v) => !v)} aria-label={mostrar ? "Ocultar senha" : "Mostrar senha"}
                  style={{ position: "absolute", right: "0.6rem", top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex" }}>
                  {mostrar ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>
            <div>
              <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Confirmar nova senha</label>
              <input style={input} type={mostrar ? "text" : "password"} value={confirmar} onChange={(e) => setConfirmar(e.target.value)} autoComplete="new-password" />
            </div>
            {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
            <button type="submit" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={carregando || !novaSenha || !confirmar}>
              {carregando ? <Loader2 size={16} className="animate-spin" /> : null} Salvar nova senha
            </button>
          </form>
        )}

        <p style={{ marginTop: "1.2rem", textAlign: "center", fontSize: "0.8rem" }}>
          <Link href="/login" style={{ color: "var(--dourado-light)" }}>Voltar para o login</Link>
        </p>
      </div>
    </section>
  );
}

export default function RedefinirSenhaPage() {
  return (
    <PublicPage variant="institucional">
      <Suspense fallback={null}>
        <Formulario />
      </Suspense>
    </PublicPage>
  );
}
