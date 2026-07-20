"use client";
import { useEffect, useState } from "react";
import { Sun, Moon, Columns2, Wine, Leaf, Mail } from "lucide-react";
import { TabBar } from "@/components/ui";
import { aplicarTema, aplicarPaleta, type Paleta } from "@/components/ThemeSwitcher";
import { ehAdmin, ehDono, salvarMeuEmail } from "@/lib/api";

type Tema = "claro" | "misto" | "escuro";

const TEMAS_SITE = [
  { id: "claro" as Tema, label: "Claro", icon: Sun },
  { id: "misto" as Tema, label: "Misto", icon: Columns2, title: "Tema misto (barra vinho)" },
  { id: "escuro" as Tema, label: "Escuro", icon: Moon },
];
const TEMAS_APP = [
  { id: "claro" as Tema, label: "Claro", icon: Sun },
  { id: "escuro" as Tema, label: "Escuro", icon: Moon },
];
const PALETAS = [
  { id: "vinho" as Paleta, label: "Vinho", icon: Wine, title: "Paleta Vinho (padrão)" },
  { id: "verde" as Paleta, label: "Verde", icon: Leaf, title: "Paleta Verde" },
];

/**
 * Seletor de Aparência — usado em Configurações (site, variant="site") e no
 * Menu do app (variant="app", sem opção "Misto"). Tema e paleta são
 * independentes: trocar uma não mexe na outra.
 */
export function AparenciaSelector({ variant = "site" }: { variant?: "site" | "app" }) {
  const [tema, setTema] = useState<Tema>("misto");
  const [paleta, setPaleta] = useState<Paleta>("vinho");

  useEffect(() => {
    const el = document.documentElement;
    const t = (el.getAttribute("data-theme") as Tema) || "misto";
    const p = (el.getAttribute("data-paleta") as Paleta) || "vinho";
    setTema(variant === "app" && t === "misto" ? "claro" : t);
    setPaleta(p === "verde" ? "verde" : "vinho");
  }, [variant]);

  function mudarTema(t: Tema) {
    setTema(t);
    aplicarTema(t);
  }
  function mudarPaleta(p: Paleta) {
    setPaleta(p);
    aplicarPaleta(p);
  }

  if (variant === "app") {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1.6rem", minHeight: "calc(100dvh - 150px)" }}>
        <TileGroup titulo="Tema" opcoes={TEMAS_APP} ativa={tema} onEscolher={mudarTema} />
        <TileGroup titulo="Paleta" opcoes={PALETAS} ativa={paleta} onEscolher={mudarPaleta}
          swatch={{ vinho: "var(--mob-vinho-fixo)", verde: "var(--mob-verde-fixo)" }} />
        <ReivindicarProprietario variant="app" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-start sm:gap-8">
      <div>
        <p style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Tema</p>
        <TabBar abas={TEMAS_SITE} ativa={tema} onChange={mudarTema} />
      </div>
      <div>
        <p style={{ fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Paleta</p>
        <TabBar abas={PALETAS} ativa={paleta} onChange={mudarPaleta} />
      </div>
      <ReivindicarProprietario variant="site" />
    </div>
  );
}

/**
 * Autopromoção a proprietário — self-service: um administrador sem e-mail
 * cadastrado nunca vê Controle de Acesso/Acessos e Auditoria (dependem de
 * eh_dono == e-mail do proprietário) e, sem isso, só um ajuste manual no
 * banco resolvia. Qualquer admin ainda não-dono pode se cadastrar aqui — o
 * backend (PUT /auth/preferencias) só aceita quando ninguém mais já é dono.
 * Some sozinho assim que eh_dono virar true (não precisa mais aparecer).
 */
function ReivindicarProprietario({ variant }: { variant: "site" | "app" }) {
  const [pode, setPode] = useState(false);
  const [aberto, setAberto] = useState(false);
  const [email, setEmail] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { setPode(ehAdmin() && !ehDono()); }, []);
  if (!pode) return null;

  async function confirmar() {
    setErro(null);
    if (!email.trim()) { setErro("Informe o e-mail."); return; }
    setSalvando(true);
    try {
      await salvarMeuEmail(email.trim());
      location.reload(); // reflete eh_dono/menu na hora, sem precisar sair e entrar
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar e-mail");
      setSalvando(false);
    }
  }

  const corMuted = variant === "app" ? "var(--mob-muted)" : "var(--text-muted)";
  const corBorda = variant === "app" ? "var(--mob-border)" : "var(--border)";
  const corTexto = variant === "app" ? "var(--mob-text)" : "var(--text)";
  const corSurface = variant === "app" ? "var(--mob-surface)" : "var(--surface)";

  return (
    <div style={{ borderTop: `1px solid ${corBorda}`, paddingTop: "1rem", marginTop: variant === "app" ? 0 : "0.5rem" }}>
      <p style={{ fontSize: "0.72rem", textTransform: "uppercase", color: corMuted, marginBottom: "0.4rem" }}>Proprietário</p>
      {!aberto ? (
        <button type="button" onClick={() => setAberto(true)}
          title="Cadastre o e-mail do proprietário para liberar Controle de Acesso e Acessos e Auditoria"
          className="flex items-center gap-2"
          style={{ background: "none", border: `1px dashed ${corBorda}`, borderRadius: "10px", padding: "0.5rem 0.8rem", color: corMuted, cursor: "pointer", fontSize: "0.82rem" }}>
          <Mail size={15} /> Sou o proprietário — cadastrar meu e-mail
        </button>
      ) : (
        <div className="flex flex-col gap-2" style={{ maxWidth: 320 }}>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="seu e-mail de proprietário" autoFocus
            style={{ fontSize: "0.85rem", padding: "0.45rem 0.6rem", borderRadius: "8px", border: `1px solid ${corBorda}`, background: corSurface, color: corTexto }} />
          {erro && <span style={{ color: "var(--red, #d33)", fontSize: "0.78rem" }}>{erro}</span>}
          <div className="flex items-center gap-2">
            <button onClick={confirmar} disabled={salvando} className={variant === "app" ? "mob-btn-2" : "btn-primary"} style={{ fontSize: "0.82rem" }}>
              {salvando ? "Salvando…" : "Confirmar"}
            </button>
            <button onClick={() => { setAberto(false); setErro(null); }} className="btn-ghost" style={{ fontSize: "0.82rem" }}>
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// Versão "cheia" (app): cada grupo (Tema/Paleta) ocupa metade da altura
// disponível entre o título "Aparência" e a barra inferior, com blocos
// grandes e tocáveis — em vez das pequenas abas compactas do site.
function TileGroup<T extends string>({ titulo, opcoes, ativa, onEscolher, swatch }: {
  titulo: string; opcoes: { id: T; label: string; icon: any; title?: string }[]; ativa: T; onEscolher: (id: T) => void;
  swatch?: Record<string, string>;
}) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <p style={{ fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.03em", color: "var(--mob-muted)", marginBottom: "0.6rem", fontWeight: 700 }}>{titulo}</p>
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
        {opcoes.map((o) => {
          const Icon = o.icon;
          const ativo = ativa === o.id;
          const cor = swatch?.[o.id];
          return (
            <button key={o.id} type="button" onClick={() => onEscolher(o.id)} title={o.title}
              style={{
                display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "0.7rem",
                borderRadius: "20px", cursor: "pointer", padding: "1rem",
                border: ativo ? `2px solid ${cor || "var(--mob-dourado-2)"}` : "1px solid var(--mob-border)",
                background: ativo ? `color-mix(in srgb, ${cor || "var(--mob-dourado-2)"} 16%, var(--mob-surface))` : "var(--mob-surface)",
                color: "var(--mob-text)", fontWeight: 700, fontSize: "1rem",
              }}>
              {cor ? (
                <span style={{ width: 40, height: 40, borderRadius: "50%", background: cor, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff" }}>
                  <Icon size={20} />
                </span>
              ) : (
                <Icon size={34} style={{ color: ativo ? (cor || "var(--mob-dourado-2)") : "var(--mob-muted)" }} />
              )}
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
