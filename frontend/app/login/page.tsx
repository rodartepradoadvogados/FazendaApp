"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogIn, Loader2, Newspaper, ArrowRight, Eye, EyeOff, X } from "lucide-react";
import { login, fetchNoticias, verificarLoginParaResetSenha, enviarResetSenha, type NoticiaNews } from "@/lib/api";
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

// Fluxo "Esqueci minha senha", em etapas:
//  - "pedirLogin": usuário ainda não digitou o login no formulário — pergunta qual é.
//  - "confirmar": login existe — mostra o e-mail mascarado e pergunta se quer redefinir por e-mail.
//  - "enviado": e-mail de redefinição disparado com sucesso.
//  - "erro": login não encontrado, sem e-mail cadastrado, ou falha ao enviar.
type EtapaEsqueci = "pedirLogin" | "confirmar" | "enviado" | "erro" | null;

function EsqueciSenhaModal({
  etapa, loginDigitado, emailMascarado, erro, carregando,
  onMudarLogin, onContinuar, onConfirmarSim, onConfirmarNao, onFechar,
}: {
  etapa: EtapaEsqueci; loginDigitado: string; emailMascarado: string | null; erro: string | null; carregando: boolean;
  onMudarLogin: (v: string) => void; onContinuar: () => void; onConfirmarSim: () => void; onConfirmarNao: () => void; onFechar: () => void;
}) {
  if (!etapa) return null;
  const input: React.CSSProperties = {
    width: "100%", background: "var(--surface-2)", color: "var(--text)",
    border: "1px solid var(--border)", borderRadius: "8px", padding: "0.6rem 0.8rem", fontSize: "0.95rem",
  };
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 200,
      display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
    }} onClick={onFechar}>
      <div className="card" style={{ maxWidth: "26rem", width: "100%", position: "relative" }} onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={onFechar} aria-label="Fechar"
          style={{ position: "absolute", top: "0.8rem", right: "0.8rem", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}>
          <X size={18} />
        </button>

        {etapa === "pedirLogin" && (
          <>
            <h3 style={{ margin: "0 0 0.6rem", fontSize: "1.05rem", fontWeight: 700 }}>Esqueci minha senha</h3>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: "0 0 0.9rem" }}>Qual é o seu usuário de login?</p>
            <input style={input} value={loginDigitado} onChange={(e) => onMudarLogin(e.target.value)} autoFocus
              onKeyDown={(e) => e.key === "Enter" && onContinuar()} placeholder="Usuário" />
            {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginTop: "0.6rem" }}>{erro}</p>}
            <button type="button" className="btn-primary" style={{ width: "100%", justifyContent: "center", marginTop: "1rem" }}
              disabled={carregando || !loginDigitado.trim()} onClick={onContinuar}>
              {carregando ? <Loader2 size={16} className="animate-spin" /> : null} Continuar
            </button>
          </>
        )}

        {etapa === "confirmar" && (
          <>
            <h3 style={{ margin: "0 0 0.6rem", fontSize: "1.05rem", fontWeight: 700 }}>Redefinir senha por e-mail?</h3>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: "0 0 0.9rem" }}>
              Vamos enviar um link de redefinição para <strong style={{ color: "var(--text)" }}>{emailMascarado}</strong>. Deseja continuar?
            </p>
            <div style={{ display: "flex", gap: "0.6rem" }}>
              <button type="button" className="btn-ghost" style={{ flex: 1, justifyContent: "center" }} onClick={onConfirmarNao}>Não</button>
              <button type="button" className="btn-primary" style={{ flex: 1, justifyContent: "center" }} disabled={carregando} onClick={onConfirmarSim}>
                {carregando ? <Loader2 size={16} className="animate-spin" /> : null} Sim, enviar
              </button>
            </div>
          </>
        )}

        {etapa === "enviado" && (
          <>
            <h3 style={{ margin: "0 0 0.6rem", fontSize: "1.05rem", fontWeight: 700 }}>E-mail enviado</h3>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", margin: 0 }}>
              Enviamos um link para redefinir sua senha. Ele vale por 1 hora — confira sua caixa de entrada (e o spam).
            </p>
            <button type="button" className="btn-primary" style={{ width: "100%", justifyContent: "center", marginTop: "1rem" }} onClick={onFechar}>Entendi</button>
          </>
        )}

        {etapa === "erro" && (
          <>
            <h3 style={{ margin: "0 0 0.6rem", fontSize: "1.05rem", fontWeight: 700 }}>Não foi possível continuar</h3>
            <p style={{ fontSize: "0.85rem", color: "var(--red)", margin: 0 }}>{erro}</p>
            <button type="button" className="btn-primary" style={{ width: "100%", justifyContent: "center", marginTop: "1rem" }} onClick={onFechar}>Fechar</button>
          </>
        )}
      </div>
    </div>
  );
}

function Hero() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  const [etapaEsqueci, setEtapaEsqueci] = useState<EtapaEsqueci>(null);
  const [loginEsqueci, setLoginEsqueci] = useState("");
  const [emailMascarado, setEmailMascarado] = useState<string | null>(null);
  const [erroEsqueci, setErroEsqueci] = useState<string | null>(null);
  const [carregandoEsqueci, setCarregandoEsqueci] = useState(false);

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

  const abrirEsqueciSenha = () => {
    setErroEsqueci(null);
    if (username.trim()) {
      setLoginEsqueci(username.trim());
      verificarLogin(username.trim());
    } else {
      setLoginEsqueci("");
      setEtapaEsqueci("pedirLogin");
    }
  };

  const verificarLogin = async (loginDigitado: string) => {
    setCarregandoEsqueci(true); setErroEsqueci(null);
    try {
      const r = await verificarLoginParaResetSenha(loginDigitado);
      if (!r.existe) {
        setErroEsqueci("Login não encontrado."); setEtapaEsqueci("erro");
      } else if (!r.tem_email) {
        setErroEsqueci("Esse usuário não tem e-mail cadastrado. Peça a um administrador para cadastrar um e-mail em Configurações > Usuários.");
        setEtapaEsqueci("erro");
      } else {
        setLoginEsqueci(loginDigitado); setEmailMascarado(r.email_mascarado || null); setEtapaEsqueci("confirmar");
      }
    } catch (err: any) {
      setErroEsqueci(err.message || "Não foi possível verificar o login."); setEtapaEsqueci("erro");
    } finally {
      setCarregandoEsqueci(false);
    }
  };

  const confirmarEnvioEmail = async () => {
    setCarregandoEsqueci(true); setErroEsqueci(null);
    try {
      await enviarResetSenha(loginEsqueci);
      setEtapaEsqueci("enviado");
    } catch (err: any) {
      setErroEsqueci(err.message || "Não foi possível enviar o e-mail."); setEtapaEsqueci("erro");
    } finally {
      setCarregandoEsqueci(false);
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
        position: "relative", zIndex: 1, maxWidth: "1320px", margin: "0 auto",
        display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(340px,0.85fr)", gap: "3.2rem", alignItems: "center",
      }} className="login-hero-grid">
        <BannerCarousel />

        {/* Cartão de login: largura fixa e ancorado à direita da coluna —
            não se move quando o carrossel troca de banner ao lado. */}
        <div
          className="card login-card-offset"
          style={{
            boxShadow: "0 20px 50px rgba(0,0,0,0.4)", justifySelf: "end", width: "100%", maxWidth: "380px",
            // 2,5cm para a direita — mas nunca mais do que o espaço livre até a
            // borda da seção, senão o cartão vaza para fora da tela em telas menores.
            transform: "translateX(min(2.5cm, max(0px, calc((100vw - 1320px) / 2 - 12px))))",
          }}
        >
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
              <div style={{ position: "relative" }}>
                <input style={{ ...input, paddingRight: "2.4rem" }} type={mostrarSenha ? "text" : "password"} value={senha}
                  onChange={(e) => setSenha(e.target.value)} autoComplete="current-password" />
                <button type="button" onClick={() => setMostrarSenha((v) => !v)} aria-label={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
                  style={{
                    position: "absolute", right: "0.6rem", top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex",
                  }}>
                  {mostrarSenha ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
              <button type="button" onClick={abrirEsqueciSenha}
                style={{ background: "none", border: "none", padding: 0, marginTop: "0.4rem", color: "var(--dourado-light)", fontSize: "0.78rem", cursor: "pointer" }}>
                Esqueci minha senha
              </button>
            </div>
            {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
            <button type="submit" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={carregando || !username || !senha}>
              {carregando ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />} Entrar
            </button>
          </form>
        </div>
      </div>

      <EsqueciSenhaModal
        etapa={etapaEsqueci}
        loginDigitado={loginEsqueci}
        emailMascarado={emailMascarado}
        erro={erroEsqueci}
        carregando={carregandoEsqueci}
        onMudarLogin={setLoginEsqueci}
        onContinuar={() => verificarLogin(loginEsqueci.trim())}
        onConfirmarSim={confirmarEnvioEmail}
        onConfirmarNao={() => setEtapaEsqueci(null)}
        onFechar={() => setEtapaEsqueci(null)}
      />
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
