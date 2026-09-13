"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { LogIn, Loader2, Newspaper, ArrowRight, Eye, EyeOff, X, ShieldCheck } from "lucide-react";
import { login, selecionarFazenda, fetchNoticias, verificarLoginParaResetSenha, enviarResetSenha, ehContador, type NoticiaNews, type FazendaAtual } from "@/lib/api";
import { ehAppOuPwa } from "@/lib/nativo";
import { Building2 } from "lucide-react";
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
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem", fontSize: "0.95rem",
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
  // "Manter conectado neste aparelho": token de validade longa (90 dias) em
  // vez das 12h padrão — só pede login de novo se sair (logout), desinstalar
  // o app/PWA (limpa o localStorage) ou desmarcar isso. Marcada por padrão
  // dentro do app Capacitor OU do PWA instalado (celular pessoal do
  // funcionário); desmarcada por padrão no site (pode ser um computador
  // compartilhado da fazenda).
  const [manterConectado, setManterConectado] = useState(false);
  // ehAppOuPwa() é assíncrona (import dinâmico do Capacitor) — se o usuário
  // digitar e submeter o formulário rápido demais (autofill + Enter), o
  // efeito abaixo pode não ter resolvido ainda e "manterConectado" ficaria
  // falso mesmo dentro do app. Só usamos esse estado como valor padrão pra
  // exibir a checkbox já marcada; o valor de verdade enviado no login (ver
  // `entrar`) é recalculado na hora, a menos que o usuário já tenha mexido
  // manualmente na checkbox (ver `tocouCheckbox`).
  const tocouCheckbox = useRef(false);
  useEffect(() => { ehAppOuPwa().then((app) => { if (!tocouCheckbox.current) setManterConectado(app); }); }, []);
  // Piloto conservador de multi-fazenda: só aparece quando o login devolve
  // mais de uma fazenda vinculada ao mesmo usuário (ver POST /auth/login).
  const [fazendasParaEscolher, setFazendasParaEscolher] = useState<FazendaAtual[] | null>(null);
  const [escolhendoFazenda, setEscolhendoFazenda] = useState(false);

  const [etapaEsqueci, setEtapaEsqueci] = useState<EtapaEsqueci>(null);
  const [loginEsqueci, setLoginEsqueci] = useState("");
  const [emailMascarado, setEmailMascarado] = useState<string | null>(null);
  const [erroEsqueci, setErroEsqueci] = useState<string | null>(null);
  const [carregandoEsqueci, setCarregandoEsqueci] = useState(false);

  const irParaDestino = async () => {
    // Vínculo de contador: não tem acesso ao resto do sistema (nem ao app
    // móvel) — vai direto para o Painel do Contador, ignorando "next".
    if (ehContador()) { router.replace("/contador"); return; }
    // Volta para onde a pessoa estava tentando entrar (ex.: /app no celular).
    const next = new URLSearchParams(window.location.search).get("next");
    if (next && next.startsWith("/")) { router.replace(next); return; }
    // Sem "next": dentro do app nativo OU do PWA instalado, a raiz é /app
    // (casca mobile) — nunca o site desktop completo (ver capacitor.config.ts
    // e app/manifest.ts). Só o botão proposital "Site completo" do Menu do
    // app deve levar ao "/" de verdade.
    router.replace((await ehAppOuPwa()) ? "/app" : "/");
  };

  const entrar = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro(null); setCarregando(true);
    try {
      // Recalcula na hora se o usuário nunca mexeu na checkbox — fecha a
      // corrida com o efeito assíncrono acima (ver comentário em manterConectado).
      const manter = tocouCheckbox.current ? manterConectado : await ehAppOuPwa();
      const data = await login(username.trim(), senha, manter);
      if (data.selecao_fazenda_necessaria) {
        setFazendasParaEscolher(data.fazendas_disponiveis || []);
        return;
      }
      await irParaDestino();
    } catch (err: any) {
      setErro(err.message || "Falha no login");
    } finally {
      setCarregando(false);
    }
  };

  const escolherFazenda = async (f: FazendaAtual) => {
    setEscolhendoFazenda(true); setErro(null);
    try {
      if (f.cowdata) {
        // "Painel CowData" é uma entrada sintética (id=0, sem fazenda de
        // verdade por trás) — o token do login() já serve (sem "fid"), só
        // falta navegar. Nada de /auth/selecionar-fazenda aqui.
        router.replace("/painel-cowdata");
        return;
      }
      await selecionarFazenda(f.id);
      await irParaDestino();
    } catch (err: any) {
      setErro(err.message || "Não foi possível selecionar a fazenda");
      setEscolhendoFazenda(false);
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
    border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem", fontSize: "0.95rem",
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
          {fazendasParaEscolher ? (
            <>
              <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem", margin: "0 0 1.1rem", fontWeight: 600 }}>
                {fazendasParaEscolher.some((f) => f.cowdata)
                  ? "Entrar como administrador de uma fazenda, ou no Painel CowData?"
                  : "Você tem acesso a mais de uma fazenda — qual delas?"}
              </p>
              <div className="space-y-2">
                {fazendasParaEscolher.map((f) => (
                  <button key={f.id} type="button" disabled={escolhendoFazenda} onClick={() => escolherFazenda(f)}
                    className="btn-ghost" style={{ width: "100%", justifyContent: "flex-start", gap: "0.6rem", border: "1px solid var(--border)", padding: "0.7rem 0.9rem" }}>
                    {f.cowdata
                      ? <ShieldCheck size={16} style={{ color: "var(--dourado-light)" }} />
                      : <Building2 size={16} style={{ color: "var(--dourado-light)" }} />}
                    <span style={{ textAlign: "left" }}>
                      <strong style={{ display: "block" }}>{f.nome}</strong>
                      {f.cowdata
                        ? <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Administração da CowData — acesso de suporte às fazendas-clientes</span>
                        : (f.cidade || f.uf) && <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{[f.cidade, f.uf].filter(Boolean).join(" · ")}</span>}
                    </span>
                  </button>
                ))}
              </div>
              {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginTop: "0.6rem" }}>{erro}</p>}
              <button type="button" onClick={() => setFazendasParaEscolher(null)}
                style={{ background: "none", border: "none", padding: 0, marginTop: "0.8rem", color: "var(--text-muted)", fontSize: "0.78rem", cursor: "pointer" }}>
                ← Voltar
              </button>
            </>
          ) : (
            <>
              <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem", margin: "0 0 1.1rem", fontWeight: 600 }}>
                Entre com seu usuário e senha
              </p>
              <form onSubmit={entrar} className="space-y-3">
                <div>
                  <label htmlFor="login-usuario" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Usuário</label>
                  <input id="login-usuario" style={input} value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" />
                </div>
                <div>
                  <label htmlFor="login-senha" style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Senha</label>
                  <div style={{ position: "relative" }}>
                    <input id="login-senha" style={{ ...input, paddingRight: "2.4rem" }} type={mostrarSenha ? "text" : "password"} value={senha}
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
                <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", color: "var(--text-muted)", cursor: "pointer" }}>
                  <input type="checkbox" checked={manterConectado} onChange={(e) => { tocouCheckbox.current = true; setManterConectado(e.target.checked); }} />
                  Manter conectado neste aparelho
                </label>
                {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
                <button type="submit" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={carregando || !username || !senha}>
                  {carregando ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />} Entrar
                </button>
              </form>
            </>
          )}
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
        {/* Hex fixo, não var(--vinho) — a área pública é uma vitrine de marca
            fixa (ver marcaVars em PublicShell.tsx), igual ao fundo em
            gradiente do PublicPage; --vinho segue a paleta escolhida na área
            logada (vinho/verde/azul) e fazia esse card mudar de cor sozinho
            pra um visitante com preferência salva. Achado da crítica, ver
            docs/agents/design-implementation.md §5, o-motor-nao-o-painel.html. */}
        <Link href="/news" style={{
          display: "flex", flexWrap: "wrap", alignItems: "center", gap: "1.2rem", textDecoration: "none",
          padding: "1.6rem 1.8rem", borderRadius: "var(--r-sm)",
          background: "linear-gradient(135deg, #0E2A47, #081A2C)",
          border: "1px solid #416180", boxShadow: "0 12px 32px rgba(0,0,0,0.35)",
        }}>
          <span style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: "3.2rem", height: "3.2rem", borderRadius: "999px",
            background: "rgba(201,164,76,0.15)", flexShrink: 0,
          }}>
            <Newspaper size={26} style={{ color: "#C9A44C" }} />
          </span>
          <span style={{ flex: 1, minWidth: "16rem" }}>
            <span style={{ display: "block", color: "#C9A44C", fontWeight: 800, fontSize: "1.15rem" }}>Milk News — nosso blog de pecuária leiteira</span>
            <span style={{ display: "block", color: "rgba(255,255,255,0.8)", fontSize: "0.85rem", marginTop: "0.2rem" }}>
              {noticia === undefined && "Carregando a última matéria…"}
              {noticia === null && "Cotação do leite, mercado, genética e manejo — aberto a qualquer visitante, sem precisar de login."}
              {noticia && <>Última matéria: <strong>{noticia.manchete}</strong></>}
            </span>
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", color: "#C9A44C", fontWeight: 700, fontSize: "0.9rem", flexShrink: 0 }}>
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
