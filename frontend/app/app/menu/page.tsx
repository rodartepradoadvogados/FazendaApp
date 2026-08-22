"use client";
// Tela MENU do app de campo. NADA remete ao site: cada item abre a informação
// GERENCIAL (só leitura, enxuta) dentro do próprio app, numa SUB-TELA com botão
// voltar (estado interno, sem navegar de rota). Itens filtrados por permissão.
// Única exceção deliberada: "Painel CowData" (dono-only) navega mesmo pra
// rota /painel-cowdata — é a administração da EMPRESA de software, já
// isolada visualmente do app da fazenda (paleta própria, ver
// app/painel-cowdata/layout.tsx, agora responsivo), não uma tela de campo.
//
// Fase 5 do redesign mobile ("1B"): lista plana, um toque só, em seções —
// substitui a antiga grade de 2 níveis (sessão → item, ambos em quadrados
// coloridos). Cada seção é um título discreto (.mob-secao) seguido de linhas
// de lista (LinhaMenu, abaixo). O ícone de cada linha mantém a cor CHEIA da
// categoria — "discreto" aqui é o tamanho contido do ícone e o espaço em
// branco generoso, não a cor apagada (confirmado com o stakeholder que
// aprovou a proposta 1B).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Stethoscope, Syringe, CalendarDays, CalendarRange, Wheat, FileBarChart, Gauge,
  LogOut, CheckCheck, Heart, ShieldPlus, Landmark,
  Wallet, FileText, BarChart3, Receipt, Palette, Boxes, NotebookPen, ClipboardList, Baby, Users, CalendarClock, MessageSquare, Building2, Sparkles, Monitor, WifiOff,
  Milk, FlaskConical, Droplet, Droplets, Scale, ListChecks, ChevronRight, ChevronDown, Sun,
} from "lucide-react";
import { getUsuario, logout, podeModulo, ehAdmin, ehDono, ehOperadorRestrito, ROTA_MODULO } from "@/lib/api";
import { usePendentes, descartarPendente, lerCache } from "@/lib/offline";
import { MobTitulo, MobVoltar, MobConfirmModal } from "@/components/mobile/ui";
import { AparenciaSelector } from "@/components/AparenciaSelector";
import AgendaVet from "@/components/mobile/menu/AgendaVet";
import ProtocolosIatf from "@/components/mobile/menu/ProtocolosIatf";
import CalendarioSanitario from "@/components/mobile/menu/CalendarioSanitario";
import AplicacoesSanidade from "@/components/mobile/menu/AplicacoesSanidade";
import PlanoAlimentacao from "@/components/mobile/menu/PlanoAlimentacao";
import LancarDieta from "@/components/mobile/menu/LancarDieta";
import ConsultarDietas from "@/components/mobile/menu/ConsultarDietas";
import NecessidadeMensal from "@/components/mobile/menu/NecessidadeMensal";
import UltimosControles from "@/components/mobile/menu/UltimosControles";
import QualidadeLeite from "@/components/mobile/menu/QualidadeLeite";
import Secagens from "@/components/mobile/menu/Secagens";
import BstHistorico from "@/components/mobile/menu/BstHistorico";
import PesagemHistorico from "@/components/mobile/menu/PesagemHistorico";
import RelatoriosManejo from "@/components/mobile/menu/RelatoriosManejo";
import Indicadores from "@/components/mobile/menu/Indicadores";
import Aprovacoes from "@/components/mobile/menu/Aprovacoes";
import FluxoCaixa from "@/components/mobile/menu/FluxoCaixa";
import Dre from "@/components/mobile/menu/Dre";
import Rmca from "@/components/mobile/menu/Rmca";
import ExtratoCompleto from "@/components/mobile/menu/ExtratoCompleto";
import Estoque from "@/components/mobile/menu/Estoque";
import Recria from "@/components/mobile/menu/Recria";
import Protocolos from "@/components/mobile/menu/Protocolos";
import ControleAcesso from "@/components/mobile/menu/ControleAcesso";
import Portal from "@/components/mobile/menu/Portal";
import News from "@/components/mobile/menu/News";
import Assistente from "@/components/mobile/menu/Assistente";
import RemediosPorDoenca from "@/components/mobile/menu/RemediosPorDoenca";
import Sincronizacao from "@/components/mobile/menu/Sincronizacao";
import Ciclos21Dias from "@/components/mobile/menu/Ciclos21Dias";

type SubKey = "agendaVet" | "iatf" | "ciclos21" | "calendario" | "aplicacoes" | "remedios" | "plano" | "lancarDieta" | "consultarDietas" | "necessidadeMensal" | "manejo" | "indicadores" | "aprovacoes"
  | "fluxoCaixa" | "dre" | "rmca" | "extrato" | "ultimosControles" | "qualidadeLeite" | "secagens" | "bstHistorico" | "pesagemHistorico";
type SecaoKey = "reproducao" | "sanidade" | "alimentacao" | "producao" | "gestao" | "financeiro";
type Item = { chave: SubKey; titulo: string; subtitulo: string; rota: string; icone: React.ReactNode; soAdmin?: boolean; cor?: string };
type Grupo = { secao: SecaoKey; titulo: string; cor: string; iconeSecao: React.ReactNode; itens: Item[] };

// Inventário autoritativo dos itens do Menu, por seção — não alterar chave/
// rota/permissão daqui (só restilizar). Tamanho do ícone reduzido (20, antes
// 26) porque agora ilustra uma linha de lista, não mais um quadrado grande.
const GRUPOS: Grupo[] = [
  { secao: "reproducao", titulo: "Reprodução", cor: "var(--cat-reproducao)", iconeSecao: <Heart size={26} />, itens: [
    { chave: "agendaVet", titulo: "Agenda Reprodutiva", subtitulo: "Listas do rebanho para a visita", rota: "/relatorios", icone: <Stethoscope size={20} /> },
    { chave: "iatf", titulo: "Protocolos IATF", subtitulo: "Vacas em andamento (D0/D7/D9/D11)", rota: "/reproducao", icone: <Syringe size={20} /> },
    // Entra em Reprodução, primeiro nível, e não pendurado dentro de Gestão >
    // Indicadores: é a medida de eficiência reprodutiva do padrão da área
    // (BREDSUM\E), não mais um número de consulta rápida. Quem está no curral
    // procura isto por "reprodução".
    { chave: "ciclos21", titulo: "Ciclos de 21 dias", subtitulo: "Eficiência reprodutiva ciclo a ciclo", rota: "/ciclos-21-dias", icone: <CalendarRange size={20} /> },
  ] },
  { secao: "sanidade", titulo: "Sanidade", cor: "var(--cat-sanidade)", iconeSecao: <ShieldPlus size={26} />, itens: [
    { chave: "calendario", titulo: "Calendário Sanitário", subtitulo: "Próximos eventos (90 dias)", rota: "/sanidade", icone: <CalendarDays size={20} /> },
    { chave: "aplicacoes", titulo: "Aplicações", subtitulo: "Medicamentos aplicados — editar/excluir", rota: "/sanidade", icone: <Syringe size={20} />, soAdmin: true },
    { chave: "remedios", titulo: "Remédios por Doença", subtitulo: "Consulta rápida + substitutos indicados", rota: "/sanidade", icone: <FlaskConical size={20} /> },
  ] },
  { secao: "alimentacao", titulo: "Alimentação", cor: "var(--cat-alimentacao)", iconeSecao: <Wheat size={26} />, itens: [
    { chave: "plano", titulo: "Plano por Lote", subtitulo: "Consumo por lote e ingrediente", rota: "/alimentacao", icone: <Wheat size={20} />, cor: "var(--mob-laranja)" },
    { chave: "lancarDieta", titulo: "Lançar nova dieta", subtitulo: "Cadastrar dieta do lote (produtos, datas)", rota: "/alimentacao", icone: <NotebookPen size={20} />, cor: "var(--mob-verde)" },
    { chave: "consultarDietas", titulo: "Consultar dietas", subtitulo: "Dietas por lote, com datas de início e fim", rota: "/alimentacao", icone: <ClipboardList size={20} />, cor: "var(--mob-azul)" },
    { chave: "necessidadeMensal", titulo: "Necessidade Mensal", subtitulo: "Consumo do mês em quilos e em sacas", rota: "/alimentacao", icone: <CalendarClock size={20} />, cor: "var(--mob-roxo)" },
  ] },
  { secao: "producao", titulo: "Produção", cor: "var(--mob-azul)", iconeSecao: <Milk size={26} />, itens: [
    { chave: "ultimosControles", titulo: "Últimos controles leiteiros", subtitulo: "Produção por controle, mais recente primeiro", rota: "/producao", icone: <Milk size={20} /> },
    { chave: "qualidadeLeite", titulo: "Qualidade do leite", subtitulo: "CCS, CBT, gordura, proteína — por período", rota: "/producao", icone: <FlaskConical size={20} /> },
    { chave: "secagens", titulo: "Secagens", subtitulo: "Histórico de secagens, motivo e ECC", rota: "/reproducao", icone: <Droplet size={20} /> },
    { chave: "bstHistorico", titulo: "BST — aplicações", subtitulo: "Histórico de aplicações de BST", rota: "/producao", icone: <Droplets size={20} /> },
    { chave: "pesagemHistorico", titulo: "Pesagens", subtitulo: "Crescimento (GMD/GPD) por animal, lote ou rebanho", rota: "/producao", icone: <Scale size={20} /> },
  ] },
  { secao: "gestao", titulo: "Gestão", cor: "var(--cat-gestao)", iconeSecao: <FileBarChart size={26} />, itens: [
    { chave: "manejo", titulo: "Relatórios de Manejo", subtitulo: "Listas do que fazer, por semáforo", rota: "/relatorios", icone: <FileBarChart size={20} /> },
    { chave: "indicadores", titulo: "Indicadores", subtitulo: "8 números de consulta rápida", rota: "/indicadores", icone: <Gauge size={20} /> },
    { chave: "aprovacoes", titulo: "Aprovações", subtitulo: "Lançamentos do Telegram a aprovar", rota: "/aprovacoes", icone: <CheckCheck size={20} />, soAdmin: true },
  ] },
  { secao: "financeiro", titulo: "Financeiro", cor: "var(--cat-financeiro)", iconeSecao: <Landmark size={26} />, itens: [
    { chave: "fluxoCaixa", titulo: "Fluxo de caixa", subtitulo: "Entradas e saídas por mês", rota: "/financeiro", icone: <Wallet size={20} /> },
    { chave: "dre", titulo: "DRE", subtitulo: "Receita, despesa e resultado por conta", rota: "/financeiro", icone: <FileText size={20} /> },
    { chave: "rmca", titulo: "RMCA", subtitulo: "Receita menos custo com alimentação", rota: "/financeiro", icone: <BarChart3 size={20} /> },
    { chave: "extrato", titulo: "Extrato completo", subtitulo: "Todos os lançamentos, pagos e em aberto", rota: "/financeiro", icone: <Receipt size={20} /> },
  ] },
];

const SUBTELAS: Record<SubKey, (props: { onVoltar: () => void }) => React.ReactNode> = {
  agendaVet: AgendaVet,
  iatf: ProtocolosIatf,
  ciclos21: Ciclos21Dias,
  calendario: CalendarioSanitario,
  aplicacoes: AplicacoesSanidade,
  remedios: RemediosPorDoenca,
  plano: PlanoAlimentacao,
  lancarDieta: LancarDieta,
  consultarDietas: ConsultarDietas,
  necessidadeMensal: NecessidadeMensal,
  ultimosControles: UltimosControles,
  qualidadeLeite: QualidadeLeite,
  secagens: Secagens,
  bstHistorico: BstHistorico,
  pesagemHistorico: PesagemHistorico,
  manejo: RelatoriosManejo,
  indicadores: Indicadores,
  aprovacoes: Aprovacoes,
  fluxoCaixa: FluxoCaixa,
  dre: Dre,
  rmca: Rmca,
  extrato: ExtratoCompleto,
};

// Chaves de cache (mob_cache_<chave>, ver lib/offline.ts) reaproveitadas para
// mostrar uma estatística ao vivo no lugar do subtítulo estático — cada uma é
// escrita pela PRÓPRIA sub-tela na 1ª visita (useCarregar, em
// components/mobile/menu/comum.tsx); aqui só LEMOS o que já está salvo (via
// lerCache), nunca buscamos de novo — contrato implícito entre arquivos,
// documentado aqui para não apodrecer em silêncio se o formato mudar lá.
const CHAVES_STAT = {
  iatf: "menu_iatf_ativos", // components/mobile/menu/ProtocolosIatf.tsx — Protocolo[] (protocolos IATF ativos)
  ultimosControles: "menu_producao_controles", // components/mobile/menu/UltimosControles.tsx — { controles: ControleRow[] }
  calendario: "menu_calendario_sanitario_visao", // components/mobile/menu/CalendarioSanitario.tsx — { janelas: JanelaCalendario[] }
  indicadores: "menu_indicadores_animais", // components/mobile/menu/Indicadores.tsx — Animal[] (fetchAnimais, usado no drill-down)
  estoque: "menu_estoque", // components/mobile/menu/Estoque.tsx — { itens: ItemEstoque[] }
} as const;

function statIatf(): string | null {
  const dados = lerCache<{ animais: unknown[] }[]>(CHAVES_STAT.iatf);
  if (!dados) return null;
  return `${dados.length} em andamento`;
}

function statUltimosControles(): string | null {
  const dados = lerCache<{ controles: { data: string | null; producao_kg: number | null }[] }>(CHAVES_STAT.ultimosControles);
  const linhas = dados?.controles;
  if (!linhas || linhas.length === 0) return null;
  const maisRecente = [...linhas].sort((a, b) => ((a.data || "") < (b.data || "") ? 1 : -1))[0];
  if (maisRecente.producao_kg == null) return null;
  return `${maisRecente.producao_kg.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} kg no último`;
}

function statCalendario(): string | null {
  const dados = lerCache<{ janelas: { eventos: unknown[] }[] }>(CHAVES_STAT.calendario);
  if (!dados) return null;
  const total = dados.janelas.reduce((soma, j) => soma + (j.eventos?.length || 0), 0);
  return `${total} evento${total !== 1 ? "s" : ""} nos próx. 90 dias`;
}

function statIndicadores(): string | null {
  const dados = lerCache<unknown[]>(CHAVES_STAT.indicadores);
  if (!dados) return null;
  return `${dados.length} animais`;
}

function statEstoque(): string | null {
  const dados = lerCache<{ itens: unknown[] }>(CHAVES_STAT.estoque);
  if (!dados) return null;
  return `${dados.itens.length} itens`;
}

/** Linha de lista do Menu (layout "1B" — plano, um toque só). O ícone leva a
 *  cor CHEIA da categoria (só o fundo do círculo é tingido/translúcido; o
 *  próprio ícone NUNCA é apagado/dessaturado — instrução explícita do
 *  stakeholder). min-height 60px (acima do piso geral de 48px do app) foi a
 *  condição do próprio stakeholder para aprovar esta lista mais densa,
 *  mantendo o uso a uma mão no curral. A linha inteira é o alvo de toque.
 *  Sem moldura/fundo/margem próprios — vive dentro do card da seção
 *  (SecaoRetratil, abaixo), separada das vizinhas por um filete superior. */
function LinhaMenu({ icone, titulo, subtitulo, cor, onClick }: {
  icone: React.ReactNode; titulo: string; subtitulo?: string; cor?: string; onClick: () => void;
}) {
  const corIcone = cor || "var(--mob-dourado-2)";
  return (
    <button type="button" onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: "0.85rem", width: "100%",
        minHeight: 60, padding: "0.6rem 1rem",
        background: "transparent", border: "none", borderTop: "1px solid var(--mob-border)",
        color: "var(--mob-text)", textAlign: "left", cursor: "pointer",
      }}>
      <span style={{
        width: 40, height: 40, borderRadius: "50%", flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: `color-mix(in srgb, ${corIcone} 16%, transparent)`, color: corIcone,
      }}>
        {icone}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontWeight: 700, fontSize: "var(--mob-fs-body)" }}>{titulo}</span>
        {subtitulo && (
          <span style={{ display: "block", fontSize: "var(--mob-fs-apoio)", color: "var(--mob-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {subtitulo}
          </span>
        )}
      </span>
      <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
    </button>
  );
}

const CHAVE_SECOES_COLAPSADAS = "mob_menu_secoes_colapsadas";

// Todas as seções nascem RECOLHIDAS na 1ª visita (sem nada salvo ainda em
// localStorage) — antes o padrão era o conjunto vazio (tudo expandido de
// cara), o que fazia a tela inicial do Menu já nascer com todos os itens de
// todas as seções visíveis, exigindo bastante rolagem. Cada seção expandida
// pelo usuário continua salva entre visitas, como já era (ver alternarSecao).
const SECOES_PADRAO_COLAPSADAS = ["protocolos-restrito", "reproducao", "sanidade", "alimentacao", "producao", "gestao", "financeiro", "modulos", "administracao", "app"];

/** Card de seção, clicável e retrátil (layout "1B"): o rótulo em CAIXA ALTA
 *  de sempre agora é o cabeçalho de um card próprio — molduras/fundo iguais
 *  ao dos outros cards do app —, com os itens (LinhaMenu) dentro dele quando
 *  expandido, separados por um filete, não mais soltos em cards individuais.
 *  Lembra a escolha do usuário entre visitas (localStorage, chave
 *  CHAVE_SECOES_COLAPSADAS).
 *
 *  Quando `cor`/`icone` são passados (grupos de GRUPOS, que já carregam
 *  iconeSecao), o cabeçalho ganha um círculo de ícone de 52px na cor da
 *  categoria, a contagem de itens no lugar do rótulo em caixa alta, e o card
 *  inteiro reaproveita `.mob-tint` (mesma técnica já usada em Rebanho >
 *  Lotes) para o fundo/borda tingidos — sem inventar paleta nova. Seções sem
 *  cor própria (Módulos, Administração, App) continuam no cabeçalho neutro
 *  de sempre. */
function SecaoRetratil({ chave, titulo, colapsada, onAlternar, children, cor, icone, contagem }: {
  chave: string; titulo: string; colapsada: boolean; onAlternar: (chave: string) => void; children: React.ReactNode;
  cor?: string; icone?: React.ReactNode; contagem?: number;
}) {
  return (
    <div className={cor ? "mob-secao-card mob-tint" : "mob-secao-card"} style={cor ? { ["--tint-cor" as any]: cor } : undefined}>
      <button type="button" aria-expanded={!colapsada} onClick={() => onAlternar(chave)}
        style={cor ? {
          width: "100%", display: "flex", alignItems: "center", gap: "0.9rem",
          padding: "1rem 1.1rem", minHeight: 76, background: "transparent", border: "none", cursor: "pointer", textAlign: "left",
        } : {
          width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem",
          padding: "0.85rem 1rem", background: "transparent", border: "none", cursor: "pointer", textAlign: "left",
          fontSize: "var(--mob-fs-rotulo)", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
          color: "var(--mob-muted)",
        }}>
        {cor ? (
          <>
            <span style={{
              width: 52, height: 52, borderRadius: "50%", flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: `color-mix(in srgb, ${cor} 20%, transparent)`, color: cor,
            }}>
              {icone}
            </span>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span style={{ display: "block", fontWeight: 800, fontSize: "1.02rem", color: "var(--mob-text)" }}>{titulo}</span>
              {typeof contagem === "number" && (
                <span style={{ display: "block", fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
                  {contagem} {contagem === 1 ? "item" : "itens"}
                </span>
              )}
            </span>
            {colapsada ? <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} /> : <ChevronDown size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />}
          </>
        ) : (
          <>
            <span>{titulo}</span>
            {colapsada ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          </>
        )}
      </button>
      {!colapsada && children}
    </div>
  );
}

export default function Pagina() {
  const router = useRouter();
  const montado = typeof window !== "undefined";
  const [secoesColapsadas, setSecoesColapsadas] = useState<Set<string>>(() => {
    if (typeof window === "undefined") return new Set(SECOES_PADRAO_COLAPSADAS);
    try {
      const salvo = window.localStorage.getItem(CHAVE_SECOES_COLAPSADAS);
      return salvo ? new Set(JSON.parse(salvo)) : new Set(SECOES_PADRAO_COLAPSADAS);
    } catch {
      return new Set(SECOES_PADRAO_COLAPSADAS);
    }
  });
  // Telas de tela cheia fora do inventário SUBTELAS (módulos, administração,
  // Aparência, News, sincronização) — mesmo mecanismo de estado interno
  // (sem navegar de rota), só que sem passar pelo mapa SUBTELAS/SubKey.
  const [tela, setTela] = useState<"news" | "estoque" | "recria" | "protocolos" | "controleAcesso" | "portal" | "assistente" | "aparencia" | "sincronizacao" | null>(null);
  const [sub, setSub] = useState<SubKey | null>(() => {
    if (typeof window === "undefined") return null;
    return window.location.hash === "#calendario-sanitario" ? "calendario" : null;
  });
  const fila = usePendentes();
  const [confirmarSair, setConfirmarSair] = useState(false);
  const [confirmarDescartarId, setConfirmarDescartarId] = useState<string | null>(null);

  function alternarSecao(chave: string) {
    setSecoesColapsadas((atual) => {
      const novo = new Set(atual);
      if (novo.has(chave)) novo.delete(chave); else novo.add(chave);
      try { localStorage.setItem(CHAVE_SECOES_COLAPSADAS, JSON.stringify([...novo])); } catch { /* melhor esforço — não impede o uso */ }
      return novo;
    });
  }

  // Botão News do cabeçalho (app/layout.tsx) navega para /app/menu#news —
  // como é a mesma rota, o Next não remonta a página, então escutamos o hash
  // (no load e em hashchange) e abrimos a sub-tela por estado.
  useEffect(() => {
    const abrirSeHashNews = () => { if (window.location.hash === "#news") setTela("news"); };
    abrirSeHashNews();
    window.addEventListener("hashchange", abrirSeHashNews);
    // Clique no botão News do cabeçalho enquanto já se está em /app/menu —
    // pushState não dispara 'hashchange', então o cabeçalho avisa por este
    // evento customizado (ver app/app/layout.tsx).
    window.addEventListener("app-abrir-news", abrirSeHashNews);
    return () => {
      window.removeEventListener("hashchange", abrirSeHashNews);
      window.removeEventListener("app-abrir-news", abrirSeHashNews);
    };
  }, []);

  // Atalho pós-salvar de Lançar > Sanidade (regra com "Registrar cronograma"
  // marcado): navega para /app/menu#calendario-sanitario. Vindo de outra
  // rota a página monta do zero, então o hash já está certo no 1º render;
  // sem 'hashchange' aqui porque não há como cair já em /app/menu antes.
  useEffect(() => {
    const abrirSeHashCalendario = () => {
      if (window.location.hash === "#calendario-sanitario") setSub("calendario");
    };

    abrirSeHashCalendario();
    window.addEventListener("hashchange", abrirSeHashCalendario);
    return () => window.removeEventListener("hashchange", abrirSeHashCalendario);
  }, []);

  const usuario = montado ? getUsuario() : null;

  // Sub-tela aberta: mostra só ela (com o próprio botão voltar).
  if (sub) {
    const Sub = SUBTELAS[sub];
    return <Sub onVoltar={() => setSub(null)} />;
  }

  // Operador vinculado a uma Pessoa do tipo empreiteiro/prestador/diarista/
  // funcionário (ver ehOperadorRestrito, lib/api.ts) — menu restrito do app
  // de campo: sem Financeiro, sem "Lançar nova dieta", e Protocolos vira a
  // 1ª seção do menu. Admin e operador não vinculado (ou vinculado a outro
  // tipo de Pessoa) não são afetados por nenhuma checagem `restrito` abaixo.
  const restrito = montado && ehOperadorRestrito();

  // No servidor / antes de montar não sabemos as permissões — só renderiza os
  // grupos após montar para não vazar itens sem permissão.
  const grupos = montado
    ? GRUPOS
        // Financeiro fica de fora do menu restrito mesmo que o módulo esteja
        // liberado para o usuário (restrição do TIPO de Pessoa, adicional à
        // permissão de módulo — não substitui a checagem de podeModulo abaixo).
        .filter((g) => !(restrito && g.secao === "financeiro"))
        .map((g) => ({
          ...g,
          itens: g.itens
            .filter((i) => (i.soAdmin ? ehAdmin() : podeModulo(ROTA_MODULO[i.rota] || i.rota)))
            .filter((i) => !(restrito && i.chave === "lancarDieta")),
        }))
        .filter((g) => g.itens.length)
    : [];

  // Estatísticas ao vivo (cache já escrito pela própria sub-tela) — só depois
  // de montar (localStorage não existe no servidor); null = ainda sem cache
  // (1ª visita) → cai no subtítulo estático de cada item, mais abaixo.
  const statsSub: Partial<Record<SubKey, string>> = montado ? {
    ...(statIatf() ? { iatf: statIatf()! } : {}),
    ...(statUltimosControles() ? { ultimosControles: statUltimosControles()! } : {}),
    ...(statCalendario() ? { calendario: statCalendario()! } : {}),
    ...(statIndicadores() ? { indicadores: statIndicadores()! } : {}),
  } : {};
  const statEstoqueValor = montado ? statEstoque() : null;

  if (tela === "news") {
    return <News onVoltar={() => {
      setTela(null);
      if (window.location.hash === "#news") history.replaceState(null, "", window.location.pathname + window.location.search);
    }} />;
  }

  if (tela === "estoque") return <Estoque onVoltar={() => setTela(null)} />;
  if (tela === "recria") return <Recria onVoltar={() => setTela(null)} />;
  if (tela === "protocolos") return <Protocolos onVoltar={() => setTela(null)} />;

  // Qualquer admin (ver ehAdmin()) — mesmo gate do site (/usuarios via AuthShell).
  if (tela === "controleAcesso") return <ControleAcesso onVoltar={() => setTela(null)} />;

  // Portal (comunicação interna + Fotos do campo) — sem gate de módulo, igual
  // ao site (qualquer usuário logado pode mandar mensagem/e-mail/foto;
  // "Exportar" já é admin-only dentro do próprio PortalView).
  if (tela === "portal") return <Portal onVoltar={() => setTela(null)} />;

  if (tela === "assistente") return <Assistente onVoltar={() => setTela(null)} />;

  if (tela === "sincronizacao") {
    return <Sincronizacao onVoltar={() => setTela(null)} />;
  }

  if (tela === "aparencia") {
    return (
      <div>
        <MobVoltar titulo="Aparência" onVoltar={() => setTela(null)} />
        <AparenciaSelector variant="app" />
      </div>
    );
  }

  // Módulos — mesmo gate de permissão do site ("Estoque" ao lado de
  // "Financeiro" segue a permissão do módulo /estoque; Recria idem).
  // Item "Protocolos" definido à parte porque, para o operador restrito (ver
  // `restrito` acima), ele sai daqui e vira a 1ª seção do menu inteiro —
  // para todo mundo mais, fica exatamente onde sempre esteve, dentro de Módulos.
  const itemProtocolos = { id: "protocolos" as const, titulo: "Protocolos", subtitulo: "Protocolos sanitários e reprodutivos", icone: <ListChecks size={20} />, cor: "var(--mob-roxo)" };
  const modulosOpcoes = [
    ...(montado && podeModulo("estoque") ? [{ id: "estoque" as const, titulo: "Estoque", subtitulo: statEstoqueValor || "Alimentação, medicamentos, sêmen…", icone: <Boxes size={20} />, cor: "var(--cat-estoque)" }] : []),
    ...(montado && podeModulo("recria") ? [{ id: "recria" as const, titulo: "Recria", subtitulo: "Bezerras e novilhas em recria", icone: <Baby size={20} />, cor: "var(--cat-recria)" }] : []),
    ...(!restrito ? [itemProtocolos] : []),
    { id: "portal" as const, titulo: "Portal", subtitulo: "Comunicação interna e fotos do campo", icone: <MessageSquare size={20} />, cor: "var(--mob-roxo)" },
  ];

  // Administração — "Controle de Acesso" só para o proprietário (ver
  // ehDono()); já reúne últimos acessos + auditoria de atividade, então não
  // há uma aba separada para isso. "Painel CowData" é a exceção que navega
  // de verdade (ver comentário no topo do arquivo).
  const administracaoOpcoes = [
    ...(montado && ehDono() ? [{ id: "controleAcesso" as const, titulo: "Controle de Acesso", subtitulo: "Usuários, acessos e auditoria", icone: <Users size={20} />, cor: "var(--cat-acesso)" }] : []),
    ...(montado && ehDono() ? [{ id: "painelCowData" as const, titulo: "Painel CowData", subtitulo: "Administração da CowData (proprietário)", icone: <Building2 size={20} />, cor: "var(--mob-dourado)" }] : []),
    ...(montado && ehAdmin() ? [{ id: "assistente" as const, titulo: "Assistente Virtual", subtitulo: "Assistente com IA para dúvidas rápidas", icone: <Sparkles size={20} />, cor: "var(--mob-dourado)" }] : []),
  ];

  function aoEscolherModulo(id: (typeof modulosOpcoes)[number]["id"] | (typeof administracaoOpcoes)[number]["id"]) {
    if (id === "painelCowData") { router.push("/painel-cowdata"); return; }
    setTela(id as "estoque" | "recria" | "protocolos" | "controleAcesso" | "portal" | "assistente");
  }

  return (
    <div>
      <MobTitulo>Menu</MobTitulo>

      {/* Operador restrito (ver `restrito` acima): Protocolos vira a 1ª seção
          do menu, antes até de Reprodução — para todo mundo mais, o item
          continua dentro de Módulos, mais abaixo, sem nenhuma mudança. */}
      {restrito && (
        <SecaoRetratil chave="protocolos-restrito" titulo={itemProtocolos.titulo} colapsada={secoesColapsadas.has("protocolos-restrito")} onAlternar={alternarSecao}>
          <LinhaMenu icone={itemProtocolos.icone} titulo={itemProtocolos.titulo} subtitulo={itemProtocolos.subtitulo}
            cor={itemProtocolos.cor} onClick={() => aoEscolherModulo(itemProtocolos.id)} />
        </SecaoRetratil>
      )}

      {grupos.map((g) => (
        <SecaoRetratil key={g.secao} chave={g.secao} titulo={g.titulo} colapsada={secoesColapsadas.has(g.secao)} onAlternar={alternarSecao}
          cor={g.cor} icone={g.iconeSecao} contagem={g.itens.length}>
          {g.itens.map((i) => (
            <LinhaMenu key={i.chave} icone={i.icone} titulo={i.titulo} subtitulo={statsSub[i.chave] || i.subtitulo}
              cor={i.cor || g.cor} onClick={() => setSub(i.chave)} />
          ))}
        </SecaoRetratil>
      ))}

      {modulosOpcoes.length > 0 && (
        <SecaoRetratil chave="modulos" titulo="Módulos" colapsada={secoesColapsadas.has("modulos")} onAlternar={alternarSecao}>
          {modulosOpcoes.map((o) => (
            <LinhaMenu key={o.id} icone={o.icone} titulo={o.titulo} subtitulo={o.subtitulo} cor={o.cor} onClick={() => aoEscolherModulo(o.id)} />
          ))}
        </SecaoRetratil>
      )}

      {administracaoOpcoes.length > 0 && (
        <SecaoRetratil chave="administracao" titulo="Administração" colapsada={secoesColapsadas.has("administracao")} onAlternar={alternarSecao}>
          {administracaoOpcoes.map((o) => (
            <LinhaMenu key={o.id} icone={o.icone} titulo={o.titulo} subtitulo={o.subtitulo} cor={o.cor} onClick={() => aoEscolherModulo(o.id)} />
          ))}
        </SecaoRetratil>
      )}

      <SecaoRetratil chave="app" titulo="App" colapsada={secoesColapsadas.has("app")} onAlternar={alternarSecao}>
        <LinhaMenu icone={<Sun size={20} />} titulo="Modo Curral" subtitulo="Telas grandes e alto contraste para o curral" cor="var(--mob-dourado)" onClick={() => router.push("/app/curral")} />
        <LinhaMenu icone={<Palette size={20} />} titulo="Aparência" subtitulo="Tema claro ou escuro" cor="var(--mob-dourado)" onClick={() => setTela("aparencia")} />
        <LinhaMenu icone={<WifiOff size={20} />} titulo="Sincronização" subtitulo={fila.length > 0 ? `${fila.length} pendente${fila.length > 1 ? "s" : ""}` : "Fila em dia"} cor={fila.length > 0 ? "var(--mob-ambar)" : "var(--mob-dourado)"} onClick={() => setTela("sincronizacao")} />
        {/* Escape hatch para as áreas que só existem no site (Configurações,
            Consultor, Painel do Contador, Pedidos, Histórico, Análise/Relatórios
            avançados etc.) — mesma sessão (localStorage é da mesma origem), sem
            precisar logar de novo. Sai da casca do app (header/nav de baixo) e
            mostra a navegação normal do site, em "modo desktop" espremido na
            tela do celular — aceitável para uso ocasional/administrativo. */}
        <LinhaMenu icone={<Monitor size={20} />} titulo="Site completo" subtitulo="Abrir a versão completa do site" cor="var(--mob-azul)" onClick={() => router.push("/")} />
        <LinhaMenu icone={<LogOut size={20} />} titulo="Sair / trocar de usuário" subtitulo="Encerrar a sessão neste aparelho" cor="var(--mob-vermelho)" onClick={() => setConfirmarSair(true)} />
      </SecaoRetratil>

      {/* Rodapé */}
      <p style={{ textAlign: "center", color: "var(--mob-muted)", fontSize: "0.78rem", margin: "1.6rem 0 0.5rem" }}>
        {montado && usuario ? `${usuario.nome || usuario.username || "Usuário"} · ` : ""}v1.0 · App de campo
      </p>

      {/* Descartar pendência — ação destrutiva e permanente (perde um
          lançamento de campo ainda não enviado), exige confirmação explícita. */}
      {confirmarDescartarId && (
        <MobConfirmModal
          titulo="Descartar pendência?"
          textoConfirmar="Descartar"
          onCancelar={() => setConfirmarDescartarId(null)}
          onConfirmar={() => { descartarPendente(confirmarDescartarId); setConfirmarDescartarId(null); }}
        >
          Este lançamento ainda não foi enviado ao servidor. Descartar apaga o registro para sempre — não é possível desfazer.
        </MobConfirmModal>
      )}

      {/* Sair — também destrutivo o bastante (encerra a sessão no aparelho)
          para pedir confirmação antes de agir. */}
      {confirmarSair && (
        <MobConfirmModal
          titulo="Sair do app?"
          textoConfirmar="Sair"
          onCancelar={() => setConfirmarSair(false)}
          onConfirmar={() => logout()}
        >
          Você vai precisar entrar de novo para continuar usando o app neste aparelho.
        </MobConfirmModal>
      )}
    </div>
  );
}
