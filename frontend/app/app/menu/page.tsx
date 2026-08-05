"use client";
// Tela MENU do app de campo. NADA remete ao site: cada item abre a informação
// GERENCIAL (só leitura, enxuta) dentro do próprio app, numa SUB-TELA com botão
// voltar (estado interno, sem navegar de rota). Itens filtrados por permissão.
// Única exceção deliberada: "Painel CowData" (dono-only) navega mesmo pra
// rota /painel-cowdata — é a administração da EMPRESA de software, já
// isolada visualmente do app da fazenda (paleta própria, ver
// app/painel-cowdata/layout.tsx, agora responsivo), não uma tela de campo.
//
// Navegação em grade de 2 níveis (mesmo padrão lúdico já usado em Lançar e
// Rebanho > Lotes, via GradeAcoes): 1º nível = sessões (quadrados grandes e
// coloridos); ao tocar numa sessão, abre um 2º nível com os itens daquela
// sessão (também em quadrados); ao tocar num item, abre a sub-tela real.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Stethoscope, Syringe, CalendarDays, Wheat, FileBarChart, Gauge,
  LogOut, CloudUpload, Trash2, CheckCheck, Heart, ShieldPlus, Landmark,
  Wallet, FileText, BarChart3, Receipt, Palette, Boxes, NotebookPen, ClipboardList, Baby, Users, CalendarClock, MessageSquare, Building2, Sparkles, Monitor,
  Milk, FlaskConical, Droplet, Droplets, Scale, ListChecks,
} from "lucide-react";
import { getUsuario, logout, podeModulo, ehAdmin, ehDono, ROTA_MODULO } from "@/lib/api";
import { usePendentes, sincronizar, descartarPendente } from "@/lib/offline";
import { MobTitulo, MobVoltar } from "@/components/mobile/ui";
import { GradeAcoes, type OpcaoAcao } from "@/components/mobile/lancar/comum";
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

type SubKey = "agendaVet" | "iatf" | "calendario" | "aplicacoes" | "remedios" | "plano" | "lancarDieta" | "consultarDietas" | "necessidadeMensal" | "manejo" | "indicadores" | "aprovacoes"
  | "fluxoCaixa" | "dre" | "rmca" | "extrato" | "ultimosControles" | "qualidadeLeite" | "secagens" | "bstHistorico" | "pesagemHistorico";
type SecaoKey = "reproducao" | "sanidade" | "alimentacao" | "producao" | "gestao" | "financeiro";
type Item = { chave: SubKey; titulo: string; subtitulo: string; rota: string; icone: React.ReactNode; soAdmin?: boolean; cor?: string };
type Grupo = { secao: SecaoKey; titulo: string; cor: string; iconeSecao: React.ReactNode; itens: Item[] };

const GRUPOS: Grupo[] = [
  { secao: "reproducao", titulo: "Reprodução", cor: "var(--cat-reproducao)", iconeSecao: <Heart size={26} />, itens: [
    { chave: "agendaVet", titulo: "Agenda Reprodutiva", subtitulo: "Listas do rebanho para a visita", rota: "/relatorios", icone: <Stethoscope size={26} /> },
    { chave: "iatf", titulo: "Protocolos IATF", subtitulo: "Vacas em andamento (D0/D7/D9/D11)", rota: "/reproducao", icone: <Syringe size={26} /> },
  ] },
  { secao: "sanidade", titulo: "Sanidade", cor: "var(--cat-sanidade)", iconeSecao: <ShieldPlus size={26} />, itens: [
    { chave: "calendario", titulo: "Calendário Sanitário", subtitulo: "Próximos eventos (90 dias)", rota: "/sanidade", icone: <CalendarDays size={26} /> },
    { chave: "aplicacoes", titulo: "Aplicações", subtitulo: "Medicamentos aplicados — editar/excluir", rota: "/sanidade", icone: <Syringe size={26} />, soAdmin: true },
    { chave: "remedios", titulo: "Remédios por Doença", subtitulo: "Consulta rápida + substitutos indicados", rota: "/sanidade", icone: <FlaskConical size={26} /> },
  ] },
  { secao: "alimentacao", titulo: "Alimentação", cor: "var(--cat-alimentacao)", iconeSecao: <Wheat size={26} />, itens: [
    { chave: "plano", titulo: "Plano por Lote", subtitulo: "Consumo por lote e ingrediente", rota: "/alimentacao", icone: <Wheat size={26} />, cor: "var(--mob-laranja)" },
    { chave: "lancarDieta", titulo: "Lançar nova dieta", subtitulo: "Cadastrar dieta do lote (produtos, datas)", rota: "/alimentacao", icone: <NotebookPen size={26} />, cor: "var(--mob-verde)" },
    { chave: "consultarDietas", titulo: "Consultar dietas", subtitulo: "Dietas por lote, com datas de início e fim", rota: "/alimentacao", icone: <ClipboardList size={26} />, cor: "var(--mob-azul)" },
    { chave: "necessidadeMensal", titulo: "Necessidade Mensal", subtitulo: "Consumo do mês em quilos e em sacas", rota: "/alimentacao", icone: <CalendarClock size={26} />, cor: "var(--mob-roxo)" },
  ] },
  { secao: "producao", titulo: "Produção", cor: "var(--mob-azul)", iconeSecao: <Milk size={26} />, itens: [
    { chave: "ultimosControles", titulo: "Últimos controles leiteiros", subtitulo: "Produção por controle, mais recente primeiro", rota: "/producao", icone: <Milk size={26} /> },
    { chave: "qualidadeLeite", titulo: "Qualidade do leite", subtitulo: "CCS, CBT, gordura, proteína — por período", rota: "/producao", icone: <FlaskConical size={26} /> },
    { chave: "secagens", titulo: "Secagens", subtitulo: "Histórico de secagens, motivo e ECC", rota: "/reproducao", icone: <Droplet size={26} /> },
    { chave: "bstHistorico", titulo: "BST — aplicações", subtitulo: "Histórico de aplicações de BST", rota: "/producao", icone: <Droplets size={26} /> },
    { chave: "pesagemHistorico", titulo: "Pesagens", subtitulo: "Crescimento (GMD/GPD) por animal, lote ou rebanho", rota: "/producao", icone: <Scale size={26} /> },
  ] },
  { secao: "gestao", titulo: "Gestão", cor: "var(--cat-gestao)", iconeSecao: <FileBarChart size={26} />, itens: [
    { chave: "manejo", titulo: "Relatórios de Manejo", subtitulo: "Listas do que fazer, por semáforo", rota: "/relatorios", icone: <FileBarChart size={26} /> },
    { chave: "indicadores", titulo: "Indicadores", subtitulo: "8 números de consulta rápida", rota: "/indicadores", icone: <Gauge size={26} /> },
    { chave: "aprovacoes", titulo: "Aprovações", subtitulo: "Lançamentos do Telegram a aprovar", rota: "/aprovacoes", icone: <CheckCheck size={26} />, soAdmin: true },
  ] },
  { secao: "financeiro", titulo: "Financeiro", cor: "var(--cat-financeiro)", iconeSecao: <Landmark size={26} />, itens: [
    { chave: "fluxoCaixa", titulo: "Fluxo de caixa", subtitulo: "Entradas e saídas por mês", rota: "/financeiro", icone: <Wallet size={26} /> },
    { chave: "dre", titulo: "DRE", subtitulo: "Receita, despesa e resultado por conta", rota: "/financeiro", icone: <FileText size={26} /> },
    { chave: "rmca", titulo: "RMCA", subtitulo: "Receita menos custo com alimentação", rota: "/financeiro", icone: <BarChart3 size={26} /> },
    { chave: "extrato", titulo: "Extrato completo", subtitulo: "Todos os lançamentos, pagos e em aberto", rota: "/financeiro", icone: <Receipt size={26} /> },
  ] },
];

const SUBTELAS: Record<SubKey, (props: { onVoltar: () => void }) => React.ReactNode> = {
  agendaVet: AgendaVet,
  iatf: ProtocolosIatf,
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

export default function Pagina() {
  const router = useRouter();
  const [montado, setMontado] = useState(false);
  const [secaoAberta, setSecaoAberta] = useState<SecaoKey | "aparencia" | "estoque" | "recria" | "protocolos" | "controleAcesso" | "portal" | "news" | "assistente" | null>(null);
  const [sub, setSub] = useState<SubKey | null>(null);
  const fila = usePendentes();
  const [sincronizando, setSincronizando] = useState(false);

  useEffect(() => { setMontado(true); }, []);

  // Botão News do cabeçalho (app/layout.tsx) navega para /app/menu#news —
  // como é a mesma rota, o Next não remonta a página, então escutamos o hash
  // (no load e em hashchange) e abrimos a sub-tela por estado.
  useEffect(() => {
    const abrirSeHashNews = () => { if (window.location.hash === "#news") setSecaoAberta("news"); };
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
    if (window.location.hash === "#calendario-sanitario") { setSecaoAberta("sanidade"); setSub("calendario"); }
  }, []);

  async function enviarAgora() {
    setSincronizando(true);
    try { await sincronizar(); } finally { setSincronizando(false); }
  }

  const usuario = montado ? getUsuario() : null;

  // Sub-tela aberta: mostra só ela (com o próprio botão voltar).
  if (sub) {
    const Sub = SUBTELAS[sub];
    return <Sub onVoltar={() => setSub(null)} />;
  }

  // No servidor / antes de montar não sabemos as permissões — só renderiza os
  // grupos após montar para não vazar itens sem permissão.
  const grupos = montado
    ? GRUPOS.map((g) => ({ ...g, itens: g.itens.filter((i) => (i.soAdmin ? ehAdmin() : podeModulo(ROTA_MODULO[i.rota] || i.rota))) })).filter((g) => g.itens.length)
    : [];

  if (secaoAberta === "news") {
    return <News onVoltar={() => {
      setSecaoAberta(null);
      if (window.location.hash === "#news") history.replaceState(null, "", window.location.pathname + window.location.search);
    }} />;
  }

  if (secaoAberta === "estoque") {
    return <Estoque onVoltar={() => setSecaoAberta(null)} />;
  }

  if (secaoAberta === "recria") {
    return <Recria onVoltar={() => setSecaoAberta(null)} />;
  }

  if (secaoAberta === "protocolos") {
    return <Protocolos onVoltar={() => setSecaoAberta(null)} />;
  }

  // Qualquer admin (ver ehAdmin()) — mesmo gate do site (/usuarios via AuthShell).
  if (secaoAberta === "controleAcesso") {
    return <ControleAcesso onVoltar={() => setSecaoAberta(null)} />;
  }

  // Portal (comunicação interna + Fotos do campo) — sem gate de módulo, igual
  // ao site (qualquer usuário logado pode mandar mensagem/e-mail/foto;
  // "Exportar" já é admin-only dentro do próprio PortalView).
  if (secaoAberta === "portal") {
    return <Portal onVoltar={() => setSecaoAberta(null)} />;
  }

  if (secaoAberta === "assistente") {
    return <Assistente onVoltar={() => setSecaoAberta(null)} />;
  }

  // 2º nível: itens da sessão escolhida, em quadrados.
  if (secaoAberta === "aparencia") {
    return (
      <div>
        <MobVoltar titulo="Aparência" onVoltar={() => setSecaoAberta(null)} />
        <AparenciaSelector variant="app" />
      </div>
    );
  }
  const grupoAberto = grupos.find((g) => g.secao === secaoAberta);
  if (grupoAberto) {
    const opcoes: OpcaoAcao[] = grupoAberto.itens.map((i) => ({ id: i.chave, label: i.titulo, icone: i.icone, cor: i.cor || grupoAberto.cor }));
    return (
      <div>
        <MobVoltar titulo={grupoAberto.titulo} onVoltar={() => setSecaoAberta(null)} />
        <GradeAcoes opcoes={opcoes} onEscolher={(id) => setSub(id as SubKey)} />
      </div>
    );
  }

  // 1º nível: sessões, em quadrados coloridos. "Estoque" fica ao lado de
  // "Financeiro" (mesma permissão do módulo /estoque do site). "Controle de
  // Acesso" só aparece para o proprietário (ver ehDono()) — já reúne últimos
  // acessos + auditoria de atividade, então não há uma aba separada para isso.
  const secoesOpcoes: OpcaoAcao[] = [
    ...grupos.map((g) => ({ id: g.secao as string, label: g.titulo, icone: g.iconeSecao, cor: g.cor })),
    ...(montado && podeModulo("estoque") ? [{ id: "estoque", label: "Estoque", icone: <Boxes size={26} />, cor: "var(--cat-estoque)" }] : []),
    ...(montado && podeModulo("recria") ? [{ id: "recria", label: "Recria", icone: <Baby size={26} />, cor: "var(--cat-recria)" }] : []),
    { id: "protocolos", label: "Protocolos", icone: <ListChecks size={26} />, cor: "var(--mob-roxo)" },
    ...(montado && ehDono() ? [{ id: "controleAcesso", label: "Controle de Acesso", icone: <Users size={26} />, cor: "var(--cat-acesso)" }] : []),
    ...(montado && ehDono() ? [{ id: "painelCowData", label: "Painel CowData", icone: <Building2 size={26} />, cor: "var(--mob-dourado)" }] : []),
    ...(montado && ehAdmin() ? [{ id: "assistente", label: "Assistente Virtual", icone: <Sparkles size={26} />, cor: "var(--mob-dourado)" }] : []),
    { id: "portal", label: "Portal", icone: <MessageSquare size={26} />, cor: "var(--mob-roxo)" },
    { id: "aparencia", label: "Aparência", icone: <Palette size={26} />, cor: "var(--mob-dourado)" },
    // Escape hatch para as áreas que só existem no site (Configurações,
    // Consultor, Painel do Contador, Pedidos, Histórico, Análise/Relatórios
    // avançados etc.) — mesma sessão (localStorage é da mesma origem), sem
    // precisar logar de novo. Sai da casca do app (header/nav de baixo) e
    // mostra a navegação normal do site, em "modo desktop" espremido na
    // tela do celular — aceitável para uso ocasional/administrativo.
    { id: "siteCompleto", label: "Site completo", icone: <Monitor size={26} />, cor: "var(--mob-azul)" },
    { id: "sair", label: "Sair / trocar de usuário", icone: <LogOut size={26} />, cor: "var(--mob-vermelho)" },
  ];

  return (
    <div>
      <MobTitulo>Menu</MobTitulo>

      <GradeAcoes
        opcoes={secoesOpcoes}
        onEscolher={(id) => {
          if (id === "sair") { logout(); return; }
          if (id === "painelCowData") { router.push("/painel-cowdata"); return; }
          if (id === "siteCompleto") { router.push("/"); return; }
          setSecaoAberta(id as SecaoKey | "aparencia" | "estoque" | "recria" | "protocolos" | "controleAcesso");
        }}
      />

      {/* Sincronização offline — sempre visível, independente das sessões acima. */}
      <div id="pendentes" style={{ scrollMarginTop: "5rem", marginTop: "1.2rem" }}>
        <div className="mob-secao">Sincronização</div>
        {fila.length === 0 && <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem", marginBottom: "0.6rem" }}>Nada aguardando envio ✓</p>}

        {fila.map((item) => (
          <div key={item.id} className="mob-card" style={{ padding: "0.85rem 1rem", marginBottom: "0.6rem" }}>
            <div style={{ fontWeight: 700, fontSize: "0.92rem" }}>{item.descricao}</div>
            <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)" }}>{new Date(item.criadoEm).toLocaleString("pt-BR")}</div>
            {!item.erro && (
              <div style={{ marginTop: "0.35rem", fontSize: "0.78rem", color: "var(--mob-muted)" }}>
                {(item.tentativas || 0) > 0 ? `Aguardando envio (tentativa ${item.tentativas})…` : "Aguardando envio…"}
                {item.debugUltimoErro && (
                  <div style={{ marginTop: "0.2rem", color: "var(--mob-ambar)", fontSize: "0.72rem" }}>
                    Última falha: {item.debugUltimoErro}
                  </div>
                )}
              </div>
            )}
            {item.erro && (
              <div style={{ marginTop: "0.5rem", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
                <span style={{ color: "var(--mob-vermelho)", fontSize: "0.8rem", fontWeight: 600, flex: 1, minWidth: 0 }}>{item.erro}</span>
                <button type="button" onClick={() => descartarPendente(item.id)}
                  style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", fontWeight: 600, color: "var(--mob-vermelho)", background: "transparent", border: "1px solid var(--mob-vermelho)", borderRadius: 10, padding: "0.35rem 0.6rem", cursor: "pointer", flexShrink: 0 }}>
                  <Trash2 size={14} /> Descartar
                </button>
              </div>
            )}
          </div>
        ))}

        {fila.length > 0 && (
          // Não trava no estado `online` (React, só atualiza via evento
          // 'online'/'offline' — pode ficar desatualizado se o WebView não
          // disparar o evento) — sempre permite tentar; sincronizar() já
          // lida bem com estar realmente offline (falha rápido, tenta depois).
          <button type="button" className="mob-btn-2" onClick={enviarAgora} disabled={sincronizando} style={{ marginTop: "0.2rem" }}>
            <CloudUpload size={17} /> {sincronizando ? "Enviando…" : "Enviar agora"}
          </button>
        )}
      </div>

      {/* Rodapé */}
      <p style={{ textAlign: "center", color: "var(--mob-muted)", fontSize: "0.78rem", margin: "1.6rem 0 0.5rem" }}>
        {montado && usuario ? `${usuario.nome || usuario.username || "Usuário"} · ` : ""}v1.0 · App de campo
      </p>
    </div>
  );
}
