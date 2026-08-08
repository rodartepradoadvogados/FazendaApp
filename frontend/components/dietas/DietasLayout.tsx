"use client";
// Casca do portal "Formulação de Dietas" (/dietas) — mesmo padrão estrutural
// do InsightsLayout (cabeçalho com marca + faixa de navegação, casca própria
// fora da Sidebar da fazenda, aberta numa aba nova de verdade do navegador —
// ver Sidebar.tsx), mas com identidade própria: preto + branco + azul
// petróleo, com ouro reservado só para BOTÕES (pedido explícito do usuário,
// ago/2026 — trocou o vinho/dourado institucional original só aqui;
// InsightsLayout continua vinho/dourado, ninguém pediu mexer nele ainda).
// Era musgo (verde) na primeira versão; trocado para azul petróleo a pedido
// do usuário logo em seguida. Azul petróleo é para navegação/estrutura (aba
// ativa, "Data" do wordmark); ouro é para ação (Voltar, Criar e continuar,
// os círculos de etapa do WizardStepper, Importar/Adicionar/Biblioteca em
// GradeAlimentos) — nunca os dois com o mesmo papel.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import { ArrowLeft, FlaskConical } from "lucide-react";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { getFazendaAtual } from "@/lib/api";

const PETROLEO = "#1F6F7D";

// Todo token que os componentes do portal (DietasLayout, WizardStepper,
// GradeAlimentos, PainelBalanco etc. — ver grep feito antes de escrever isto)
// realmente consomem, redeclarado aqui, escopado a esta subárvore — nunca
// herda o tema (claro/escuro) nem a paleta pessoal (vinho/verde/azul) de
// quem está logado, mesmo raciocínio do Painel CowData (ver painel-cowdata/
// layout.tsx). --dourado*/--vinho* (não usados pelos componentes do portal
// diretamente, mas SIM por .btn-primary-gold/.btn-secondary, globais, usados
// aqui dentro) também precisam de valor próprio — na paleta "verde"/"azul"
// pessoal do usuário logado eles são hex literal, não derivam de --gold*, e
// vazariam a cor errada sem isto.
const tokensDietas: CSSProperties = {
  "--bg": "#FFFFFF", "--surface": "#FFFFFF", "--surface-2": "#F4F5F3",
  "--border": "#E1E4E0", "--border-strong": "#C7CBC5",
  "--text": "#14171A", "--text-muted": "#5B6360",
  "--thead-bg": "#F4F5F3", "--thead-fg": "#14171A",
  "--cream": "#F5F6F4",
  "--wine": "#0A0C0B", "--wine-2": "#0A0C0B", "--wine-lt": "#1B1F1C",
  "--gold": "#C9A23A", "--gold-deep": "#A9822A", "--gold-pale": "#E4C979",
  // --dourado é quem realmente pinta o fundo de .btn-primary-gold ("Criar e
  // continuar") — vai direto no #C9A23A pedido, não no tom mais escuro que
  // --dourado herdaria de --gold-deep por padrão (ver .btn-primary-gold em
  // globals.css: background: var(--dourado)).
  "--dourado": "#C9A23A", "--dourado-light": "#E4C979", "--dourado-fixo": "#C9A23A",
} as CSSProperties;

export function DietasLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [fazendaNome, setFazendaNome] = useState("");

  useEffect(() => {
    setFazendaNome(getFazendaAtual()?.nome || "");
  }, [path]);

  const emSimulacao = /^\/dietas\/\d+/.test(path || "");
  const idSimulacao = emSimulacao ? path!.split("/")[2] : null;

  return (
    <div className="dietas-portal" style={{ minHeight: "100vh", background: "var(--bg)", ...tokensDietas }}>
      <header style={{ background: "var(--wine)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", padding: "0.9rem 1.4rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
            <CowDataMark size={34} />
            <div>
              <CowDataWordmark size="1rem" cowColor="var(--cream)" dataColor={PETROLEO} />
              <p style={{ margin: 0, fontSize: "0.68rem", color: "rgba(243,231,211,0.7)", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                <FlaskConical size={11} /> Formulação de Dietas{fazendaNome ? ` · ${fazendaNome}` : ""}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => router.push("/")}
            title="Voltar à Capa da fazenda, nesta mesma aba"
            style={{
              display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)",
              border: "1px solid var(--gold-deep)", background: "transparent", color: "var(--gold-pale)",
              fontSize: "0.8rem", fontWeight: 700, cursor: "pointer",
            }}
          >
            <ArrowLeft size={14} /> Voltar
          </button>
        </div>
        <nav style={{ display: "flex", gap: "0.2rem", padding: "0 1rem", overflowX: "auto", borderTop: "1px solid rgba(243,231,211,0.14)" }}>
          <Link href="/dietas" style={{
            padding: "0.65rem 0.9rem", fontSize: "0.82rem", fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap",
            color: path === "/dietas" ? "var(--cream)" : "rgba(243,231,211,0.62)",
            borderBottom: path === "/dietas" ? `2px solid ${PETROLEO}` : "2px solid transparent",
          }}>
            Simulações
          </Link>
          <Link href="/dietas/nova" style={{
            padding: "0.65rem 0.9rem", fontSize: "0.82rem", fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap",
            color: path === "/dietas/nova" ? "var(--cream)" : "rgba(243,231,211,0.62)",
            borderBottom: path === "/dietas/nova" ? `2px solid ${PETROLEO}` : "2px solid transparent",
          }}>
            Nova simulação
          </Link>
          {emSimulacao && (
            <span style={{
              padding: "0.65rem 0.9rem", fontSize: "0.82rem", fontWeight: 600, whiteSpace: "nowrap",
              color: "var(--cream)", borderBottom: `2px solid ${PETROLEO}`,
            }}>
              Simulação #{idSimulacao}
            </span>
          )}
        </nav>
      </header>
      <main style={{ padding: "1.4rem" }}>{children}</main>
    </div>
  );
}
