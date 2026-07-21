"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogIn, Loader2, Newspaper, ArrowRight } from "lucide-react";
import { login, fetchNoticias, type NoticiaNews } from "@/lib/api";
import { LoginWatermark } from "@/components/LoginWatermark";
import { PublicPage } from "@/components/institucional/PublicShell";
import { BannerCarousel } from "@/components/login/BannerCarousel";
import FeatureShowcase from "@/components/login/FeatureShowcase";
import BannerGrid from "@/components/login/BannerGrid";
import MilkPriceExplainer from "@/components/login/MilkPriceExplainer";

function useUltimaNoticia() {
  const [noticia, setNoticia] = useState<NoticiaNews | null | undefined>(undefined);
  useEffect(() => {
    fetchNoticias(false)
      .then((feed) => {
        const todas = feed.fontes.flatMap((f) => f.noticias);
        todas.sort((a, b) => (b.data_publicacao || b.capturado_em).localeCompare(a.data_publicacao || a.capturado_em));
        setNoticia(todas[0] ?? null);
      })
      .catch(() => setNoticia(null));
  }, []);
  return noticia;
}

function Hero() {
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
    <section style={{ position: "relative", overflow: "hidden", padding: "3.5rem 1.5rem 4rem" }}>
      <LoginWatermark />
      <div style={{
        position: "relative", zIndex: 1, maxWidth: "1140px", margin: "0 auto",
        display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(340px,0.85fr)", gap: "3.2rem", alignItems: "center",
      }} className="login-hero-grid">
        <BannerCarousel />

        {/* Cartão de login: largura fixa e ancorado à direita da coluna —
            não se move quando o carrossel troca de banner ao lado. */}
        <div className="card" style={{ boxShadow: "0 20px 50px rgba(0,0,0,0.4)", justifySelf: "end", width: "100%", maxWidth: "380px" }}>
          <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem", margin: "0 0 1.1rem", fontWeight: 600 }}>
            Entre com seu usuário e senha
          </p>
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
    </section>
  );
}

function Secao({ id, titulo, subtitulo, children }: { id: string; titulo: string; subtitulo?: string; children: React.ReactNode }) {
  return (
    <section id={id} style={{ padding: "3rem 1.5rem" }}>
      <div style={{ maxWidth: "1080px", margin: "0 auto" }}>
        <h2 style={{ fontSize: "1.5rem", fontWeight: 800, color: "#fff", margin: "0 0 0.4rem", textAlign: "center" }}>{titulo}</h2>
        {subtitulo && <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.9rem", maxWidth: "36rem", margin: "0 auto 2rem" }}>{subtitulo}</p>}
        {!subtitulo && <div style={{ marginBottom: "2rem" }} />}
        {children}
      </div>
    </section>
  );
}

function MilkNewsCallout() {
  const noticia = useUltimaNoticia();
  return (
    <section id="milknews" style={{ padding: "3rem 1.5rem 4rem" }}>
      <div style={{ maxWidth: "1080px", margin: "0 auto" }}>
        <Link href="/news" style={{
          display: "flex", flexWrap: "wrap", alignItems: "center", gap: "1.2rem", textDecoration: "none",
          padding: "1.6rem 1.8rem", borderRadius: "16px",
          background: "linear-gradient(135deg, var(--vinho), var(--vinho-dark))",
          border: "1px solid var(--vinho-light)", boxShadow: "0 12px 32px rgba(0,0,0,0.35)",
        }}>
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: "3.2rem", height: "3.2rem", borderRadius: "999px",
            background: "rgba(255,224,102,0.15)", flexShrink: 0,
          }}>
            <Newspaper size={26} style={{ color: "#FFE066" }} />
          </span>
          <span style={{ flex: 1, minWidth: "16rem" }}>
            <span style={{ display: "block", color: "#FFE066", fontWeight: 800, fontSize: "1.15rem" }}>Milk News — nosso blog de pecuária leiteira</span>
            <span style={{ display: "block", color: "rgba(255,255,255,0.8)", fontSize: "0.85rem", marginTop: "0.2rem" }}>
              {noticia === undefined && "Carregando a última matéria…"}
              {noticia === null && "Cotação do leite, mercado, genética e manejo — aberto a qualquer visitante, sem precisar de login."}
              {noticia && <>Última matéria: <strong>{noticia.manchete}</strong></>}
            </span>
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", color: "#FFE066", fontWeight: 700, fontSize: "0.9rem", flexShrink: 0 }}>
            Ler o blog <ArrowRight size={18} />
          </span>
        </Link>
      </div>
    </section>
  );
}

export default function LoginPage() {
  return (
    <PublicPage variant="login">
      <Hero />
      <Secao id="recursos" titulo="Tudo que a fazenda precisa, em um painel só" subtitulo="Seis frentes cobertas de ponta a ponta — sem planilha solta, sem informação perdida.">
        <FeatureShowcase />
        <BannerGrid />
      </Secao>
      <Secao id="simulador" titulo="Entenda o preço do seu leite" subtitulo="Um exemplo de como qualidade e volume pesam no preço final — e uma referência geral de como esse preço costuma ser montado.">
        <MilkPriceExplainer />
      </Secao>
      <MilkNewsCallout />
    </PublicPage>
  );
}
