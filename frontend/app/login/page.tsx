"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogIn, Loader2, Newspaper, ArrowRight, ChevronRight } from "lucide-react";
import { login, fetchNoticias, type NoticiaNews } from "@/lib/api";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { CwdMilkMark } from "@/components/CwdMilkMark";
import { LoginWatermark } from "@/components/LoginWatermark";
import FeatureShowcase from "@/components/login/FeatureShowcase";
import MilkPriceExplainer from "@/components/login/MilkPriceExplainer";

// Tokens locais fixos para esta página — a página de entrada é uma vitrine
// pública, não a área logada (que segue o tema claro/escuro/misto escolhido
// pelo usuário em Aparência). Ela assume sempre o visual de marca (fundo
// vinho escuro, texto claro), sobrescrevendo --surface/--text/etc. só dentro
// desta árvore para que .card e os componentes de login/* (que já usam essas
// variáveis) apareçam certos aqui mesmo se o tema salvo for "misto"/"claro".
const marcaVars = {
  "--surface": "rgba(255,255,255,0.05)",
  "--surface-2": "rgba(255,255,255,0.045)",
  "--border": "rgba(255,255,255,0.14)",
  "--text": "#F5EEF1",
  "--text-muted": "rgba(245,238,241,0.68)",
} as React.CSSProperties;

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

function Header() {
  const linkStyle: React.CSSProperties = { color: "rgba(245,238,241,0.8)", textDecoration: "none", fontSize: "0.85rem", fontWeight: 600 };
  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 20, display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0.9rem 1.5rem", background: "rgba(20,10,14,0.55)", backdropFilter: "blur(10px)",
      borderBottom: "1px solid rgba(255,255,255,0.08)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.55rem" }}>
        <CwdMilkMark size={30} color="#F5EEF1" />
        <div>
          <CowDataWordmark size="1rem" cowColor="#F5EEF1" />
          <p style={{ margin: 0, fontSize: "0.65rem", color: "rgba(245,238,241,0.6)" }}>Estreito Ponte de Pedra · Jairo Nasser</p>
        </div>
      </div>
      <nav style={{ display: "flex", alignItems: "center", gap: "1.4rem" }}>
        <a href="#recursos" style={linkStyle} className="login-nav-link">Recursos</a>
        <a href="#simulador" style={linkStyle} className="login-nav-link">Simulador</a>
        <Link href="/news" style={{ ...linkStyle, color: "#FFE066" }} className="login-nav-link">Milk News</Link>
      </nav>
    </header>
  );
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
        position: "relative", zIndex: 1, maxWidth: "1080px", margin: "0 auto",
        display: "grid", gridTemplateColumns: "minmax(0,1.15fr) minmax(320px,0.85fr)", gap: "2.5rem", alignItems: "center",
      }} className="login-hero-grid">
        <div>
          <span style={{
            display: "inline-block", padding: "0.3rem 0.75rem", borderRadius: "999px", fontSize: "0.72rem", fontWeight: 700,
            letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--dourado-light)",
            background: "rgba(212,160,23,0.14)", border: "1px solid rgba(212,160,23,0.3)", marginBottom: "1.1rem",
          }}>
            Gestão de pecuária leiteira
          </span>
          <h1 style={{ fontSize: "clamp(1.8rem, 3.4vw, 2.7rem)", fontWeight: 800, lineHeight: 1.12, margin: "0 0 0.9rem", color: "#fff" }}>
            Do cio ao litro: sua fazenda inteira,{" "}
            <span style={{ color: "var(--dourado-light)" }}>em um só lugar.</span>
          </h1>
          <p style={{ fontSize: "1rem", color: "rgba(245,238,241,0.78)", maxWidth: "34rem", margin: "0 0 1.6rem", lineHeight: 1.55 }}>
            O CowData acompanha reprodução, produção, sanidade, estoque e financeiro do rebanho —
            substituindo planilhas soltas por um painel só, pensado para o dia a dia de quem
            toca a fazenda.
          </p>
          <a href="#recursos" className="btn-primary" style={{ display: "inline-flex" }}>
            Ver o que o sistema faz <ChevronRight size={16} />
          </a>
        </div>

        <div className="card" style={{ boxShadow: "0 20px 50px rgba(0,0,0,0.4)" }}>
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
    <div style={{ ...marcaVars, minHeight: "100vh", background: "linear-gradient(180deg, #2a1219 0%, #1c0d12 45%, #150a0e 100%)" }}>
      <Header />
      <Hero />
      <Secao id="recursos" titulo="Tudo que a fazenda precisa, em um painel só" subtitulo="Seis frentes cobertas de ponta a ponta — sem planilha solta, sem informação perdida.">
        <FeatureShowcase />
      </Secao>
      <Secao id="simulador" titulo="Entenda o preço do seu leite" subtitulo="Um exemplo de como qualidade e volume pesam no preço final — e uma referência geral de como esse preço costuma ser montado.">
        <MilkPriceExplainer />
      </Secao>
      <MilkNewsCallout />
      <footer style={{ padding: "1.5rem", textAlign: "center", color: "rgba(245,238,241,0.45)", fontSize: "0.75rem", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
        CowData · Estreito Ponte de Pedra · Jairo Nasser
      </footer>
      <style>{`
        .login-nav-link { transition: color 0.15s ease; }
        .login-nav-link:hover { color: #ffffff !important; }
        @media (max-width: 860px) {
          .login-hero-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
}
