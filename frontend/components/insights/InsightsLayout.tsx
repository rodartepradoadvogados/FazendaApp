"use client";
// Casca dos portais "Insights" e "Administração" — dois atalhos SEPARADOS na
// Sidebar da fazenda (ver Sidebar.tsx), cada um abrindo numa aba nova de
// verdade do navegador, mas que compartilham esta mesma casca porque o
// desenho visual é idêntico — só o CONJUNTO de abas mostrado na barra do
// topo muda, conforme o grupo a que a rota atual pertence (ver ABAS_POR_MODO
// abaixo). Antes os dois viviam misturados num único portal "Insights e
// Administração"; a mistura confundia (um serve para ENXERGAR a fazenda, o
// outro para CONFIGURAR/GERENCIAR acesso) — separados, cada atalho leva
// direto ao conjunto de telas que o rótulo promete.
//
// Insights: Indicadores, Listas, Relatórios — leitura/análise, sem nenhuma
// tela de configuração.
// Administração: Controle de Acesso, Painel CowData, Painel do Contador
// (os dois últimos entram como atalhos, mas mantêm a própria casca bespoke
// já existente), Portal, Configurações.
//
// Layout INVERTIDO em relação ao resto do site: aqui os módulos (o que na
// Sidebar é a lista vertical) viram uma barra de abas no TOPO, e a
// sub-navegação de cada um (o que na Sidebar aparece acima da lista) desce
// para um rail na LATERAL ESQUERDA — pedido explícito do usuário para
// diferenciar visualmente estes portais do resto do site.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, FileSpreadsheet, FileText, Loader2, ChevronDown } from "lucide-react";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { rotuloDaPagina } from "@/components/Sidebar";
import { SubNavTree } from "@/components/SubNavTree";
import { useSubNav } from "@/components/SubNavContext";
import { useExportAtual } from "@/components/ExportContext";
import { exportarExcel, exportarPDF } from "@/lib/export";
import { getFazendaAtual, getUsuario, podeModulo, ehDono, ROTA_MODULO } from "@/lib/api";

type Aba = { href: string; label: string; donoOnly?: boolean; requerConfig?: boolean };

const ABAS_INSIGHTS: Aba[] = [
  { href: "/indicadores", label: "Indicadores" },
  { href: "/relatorios", label: "Listas" },
  { href: "/analise-relatorios", label: "Relatórios" },
];

const ABAS_ADMINISTRACAO: Aba[] = [
  { href: "/usuarios", label: "Controle de Acesso", donoOnly: true },
  { href: "/painel-cowdata", label: "Painel CowData", donoOnly: true },
  { href: "/contador", label: "Painel do Contador", donoOnly: true },
  { href: "/portal", label: "Portal" },
  // A assinatura independente de consultor foi removida (backlog #122) — o
  // consultor passa a existir só dentro da própria fazenda (vínculo
  // UsuarioFazenda.consultor) e como Consultor CowData (Equipe CowData).
  { href: "/configuracoes", label: "Configurações", requerConfig: true },
];

// Qual dos dois grupos a rota ATUAL pertence — decide tanto o conjunto de
// abas mostrado quanto o título do cabeçalho. Rota que não está em nenhum
// dos dois (não deveria acontecer, todo consumidor desta casca está numa
// das duas listas) cai em "insights" por segurança.
function modoDaRota(path: string): "insights" | "administracao" {
  return ABAS_ADMINISTRACAO.some((a) => path === a.href || path.startsWith(`${a.href}/`))
    ? "administracao"
    : "insights";
}

// Botão "Exportar" do cabeçalho — só aparece quando a página atual registrou
// dados (ver ExportContext/ExportarBotoes); mesmo PDF/Excel de sempre
// (lib/export.ts), já na paleta Institucional.
function ExportarCabecalho() {
  const dados = useExportAtual();
  const [aberto, setAberto] = useState(false);
  const [gerando, setGerando] = useState<"excel" | "pdf" | null>(null);
  useEffect(() => { setAberto(false); }, [dados?.nomeArquivoBase]);
  if (!dados) return null;

  async function rodar(formato: "excel" | "pdf") {
    if (!dados) return;
    setGerando(formato);
    setAberto(false);
    try {
      if (formato === "excel") await exportarExcel(dados.titulo, dados.colunas, dados.linhas, dados.nomeArquivoBase);
      else await exportarPDF(dados.titulo, dados.colunas, dados.linhas, dados.nomeArquivoBase);
    } catch {
      // erro já mostrado ao usuário dentro de exportarExcel/exportarPDF
    } finally {
      setGerando(null);
    }
  }

  return (
    <div style={{ position: "relative" }}>
      <button type="button" onClick={() => setAberto((a) => !a)} disabled={gerando !== null || dados.linhas.length === 0}
        title="Exportar esta tela em PDF ou Excel"
        style={{
          display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)",
          border: "1px solid rgba(255,255,255,0.22)", background: "rgba(255,255,255,0.08)", color: "#F5EEF1",
          fontSize: "0.8rem", fontWeight: 600, cursor: dados.linhas.length === 0 ? "not-allowed" : "pointer",
          opacity: dados.linhas.length === 0 ? 0.5 : 1,
        }}>
        {gerando ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />}
        Exportar <ChevronDown size={13} />
      </button>
      {aberto && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 29 }} onClick={() => setAberto(false)} />
          <div style={{
            position: "absolute", top: "calc(100% + 0.4rem)", right: 0, zIndex: 30, minWidth: "10rem",
            background: "#0E2A47", border: "1px solid rgba(255,255,255,0.16)", borderRadius: "var(--r-sm)",
            boxShadow: "0 12px 28px rgba(0,0,0,0.35)", overflow: "hidden",
          }}>
            <button type="button" onClick={() => rodar("excel")}
              style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "100%", padding: "0.55rem 0.8rem", background: "none", border: "none", color: "#F5EEF1", fontSize: "0.82rem", cursor: "pointer", textAlign: "left" }}>
              <FileSpreadsheet size={14} /> Excel (.xlsx)
            </button>
            <button type="button" onClick={() => rodar("pdf")}
              style={{ display: "flex", alignItems: "center", gap: "0.5rem", width: "100%", padding: "0.55rem 0.8rem", background: "none", border: "none", color: "#F5EEF1", fontSize: "0.82rem", cursor: "pointer", textAlign: "left", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
              <FileText size={14} /> PDF (identidade CowData)
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export function InsightsLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const subNav = useSubNav();
  const [fazendaNome, setFazendaNome] = useState("Jairo Nasser");
  const [admin, setAdmin] = useState(false);
  const [dono, setDono] = useState(false);
  const [temConfiguracoes, setTemConfiguracoes] = useState(false);

  useEffect(() => {
    setFazendaNome(getFazendaAtual()?.nome || "Jairo Nasser");
    setDono(ehDono());
    setTemConfiguracoes(podeModulo("parametros") || podeModulo("upload") || ehDono());
  }, [path]);

  const modo = modoDaRota(path);
  const titulo = modo === "administracao" ? "Administração" : "Insights";
  const abasVisiveis = (modo === "administracao" ? ABAS_ADMINISTRACAO : ABAS_INSIGHTS).filter((a) => {
    if (a.donoOnly) return dono;
    if (a.requerConfig) return temConfiguracoes;
    const mod = ROTA_MODULO[a.href];
    if (mod) return podeModulo(mod);
    return true; // /portal — liberado para todo logado
  });

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <header style={{ background: "linear-gradient(135deg, #0E2A47, #0A1F36)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", padding: "0.9rem 1.4rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
            <CowDataMark size={34} />
            <div>
              <CowDataWordmark size="1rem" cowColor="#F5EEF1" dataColor="#C9A44C" />
              <p style={{ margin: 0, fontSize: "0.68rem", color: "rgba(245,238,241,0.65)" }}>
                {titulo} · {fazendaNome}
              </p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
            <ExportarCabecalho />
            <button type="button" onClick={() => router.push("/")} title="Voltar à Capa da fazenda, nesta mesma aba"
              style={{
                display: "flex", alignItems: "center", gap: "0.4rem", padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)",
                border: "1px solid #8A6D2F", background: "transparent", color: "#C9A44C", fontSize: "0.8rem", fontWeight: 700, cursor: "pointer",
              }}>
              <ArrowLeft size={14} /> Voltar
            </button>
          </div>
        </div>
        {/* Barra de abas — os módulos que na Sidebar da fazenda seriam uma
            lista vertical viram, aqui, uma faixa horizontal no topo. */}
        <nav style={{ display: "flex", gap: "0.2rem", padding: "0 1rem", overflowX: "auto", borderTop: "1px solid rgba(255,255,255,0.1)" }}>
          {abasVisiveis.map((a) => {
            const ativo = path === a.href || (a.href !== "/" && path.startsWith(a.href));
            return (
              <Link key={a.href} href={a.href} style={{
                padding: "0.65rem 0.9rem", fontSize: "0.82rem", fontWeight: 600, textDecoration: "none", whiteSpace: "nowrap",
                color: ativo ? "#F5EEF1" : "rgba(245,238,241,0.62)",
                borderBottom: ativo ? "2px solid #C9A44C" : "2px solid transparent",
              }}>
                {a.label}
              </Link>
            );
          })}
        </nav>
      </header>

      {/* Corpo: rail de sub-navegação à ESQUERDA (quando a página registrou
          uma árvore de sub-abas — ver useSubNavRegister) + conteúdo. No resto
          do site esse rail fica em cima, dentro da Sidebar — aqui é o
          inverso, por pedido explícito do usuário para este portal. */}
      <div style={{ display: "flex", alignItems: "flex-start" }}>
        {subNav && (
          <aside style={{
            width: "15rem", flexShrink: 0, padding: "1rem 0.8rem", borderRight: "1px solid var(--border)",
            minHeight: "calc(100vh - 6.5rem)",
          }}>
            <SubNavTree nodes={subNav.tree} activeId={subNav.activeId} onSelect={subNav.onSelect}
              raiz={subNav.tree} pathname={path} paginaLabel={rotuloDaPagina(path)}
              recolhidos={new Set()} onToggleRecolhido={() => {}} />
          </aside>
        )}
        <main style={{ flex: 1, minWidth: 0, padding: "1.4rem" }}>{children}</main>
      </div>
    </div>
  );
}
