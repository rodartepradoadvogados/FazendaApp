"use client";
// Tela MENU do app de campo. NADA remete ao site: cada item abre a informação
// GERENCIAL (só leitura, enxuta) dentro do próprio app, numa SUB-TELA com botão
// voltar (estado interno, sem navegar de rota). Itens filtrados por permissão.
//
// Navegação em grade de 2 níveis (mesmo padrão lúdico já usado em Lançar e
// Rebanho > Lotes, via GradeAcoes): 1º nível = sessões (quadrados grandes e
// coloridos); ao tocar numa sessão, abre um 2º nível com os itens daquela
// sessão (também em quadrados); ao tocar num item, abre a sub-tela real.
import { useEffect, useState } from "react";
import {
  Stethoscope, Syringe, CalendarDays, Wheat, FileBarChart, Gauge,
  LogOut, CloudUpload, Trash2, CheckCheck, Heart, ShieldPlus, Landmark,
  Wallet, FileText, BarChart3, Receipt, Palette,
} from "lucide-react";
import { getUsuario, logout, podeModulo, ehAdmin, ROTA_MODULO } from "@/lib/api";
import { usePendentes, useOnline, sincronizar, descartarPendente } from "@/lib/offline";
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
import RelatoriosManejo from "@/components/mobile/menu/RelatoriosManejo";
import Indicadores from "@/components/mobile/menu/Indicadores";
import Aprovacoes from "@/components/mobile/menu/Aprovacoes";
import FluxoCaixa from "@/components/mobile/menu/FluxoCaixa";
import Dre from "@/components/mobile/menu/Dre";
import Rmca from "@/components/mobile/menu/Rmca";
import ExtratoCompleto from "@/components/mobile/menu/ExtratoCompleto";
import News from "@/components/mobile/menu/News";

type SubKey = "agendaVet" | "iatf" | "calendario" | "aplicacoes" | "plano" | "lancarDieta" | "consultarDietas" | "manejo" | "indicadores" | "aprovacoes"
  | "fluxoCaixa" | "dre" | "rmca" | "extrato";
type SecaoKey = "reproducao" | "sanidade" | "alimentacao" | "gestao" | "financeiro";
type Item = { chave: SubKey; titulo: string; subtitulo: string; rota: string; icone: React.ReactNode; soAdmin?: boolean };
type Grupo = { secao: SecaoKey; titulo: string; cor: string; iconeSecao: React.ReactNode; itens: Item[] };

const GRUPOS: Grupo[] = [
  { secao: "reproducao", titulo: "Reprodução", cor: "var(--mob-roxo)", iconeSecao: <Heart size={26} />, itens: [
    { chave: "agendaVet", titulo: "Agenda do Veterinário", subtitulo: "Listas do rebanho para a visita", rota: "/reproducao", icone: <Stethoscope size={26} /> },
    { chave: "iatf", titulo: "Protocolos IATF", subtitulo: "Vacas em andamento (D0/D7/D9/D11)", rota: "/reproducao", icone: <Syringe size={26} /> },
  ] },
  { secao: "sanidade", titulo: "Sanidade", cor: "var(--mob-verde)", iconeSecao: <ShieldPlus size={26} />, itens: [
    { chave: "calendario", titulo: "Calendário Sanitário", subtitulo: "Próximos eventos (90 dias)", rota: "/sanidade", icone: <CalendarDays size={26} /> },
    { chave: "aplicacoes", titulo: "Aplicações", subtitulo: "Medicamentos aplicados — editar/excluir", rota: "/sanidade", icone: <Syringe size={26} />, soAdmin: true },
  ] },
  { secao: "alimentacao", titulo: "Alimentação", cor: "var(--mob-laranja)", iconeSecao: <Wheat size={26} />, itens: [
    { chave: "plano", titulo: "Plano por Lote", subtitulo: "Consumo por lote e ingrediente", rota: "/alimentacao", icone: <Wheat size={26} /> },
    { chave: "lancarDieta", titulo: "Lançar nova dieta", subtitulo: "Cadastrar dieta do lote (produtos, datas)", rota: "/alimentacao", icone: <Wheat size={26} /> },
    { chave: "consultarDietas", titulo: "Consultar dietas", subtitulo: "Dietas por lote, com datas de início e fim", rota: "/alimentacao", icone: <Wheat size={26} /> },
  ] },
  { secao: "gestao", titulo: "Gestão", cor: "var(--mob-azul)", iconeSecao: <FileBarChart size={26} />, itens: [
    { chave: "manejo", titulo: "Relatórios de Manejo", subtitulo: "Listas do que fazer, por semáforo", rota: "/relatorios", icone: <FileBarChart size={26} /> },
    { chave: "indicadores", titulo: "Indicadores", subtitulo: "8 números de consulta rápida", rota: "/indicadores", icone: <Gauge size={26} /> },
    { chave: "aprovacoes", titulo: "Aprovações", subtitulo: "Lançamentos do Telegram a aprovar", rota: "/aprovacoes", icone: <CheckCheck size={26} />, soAdmin: true },
  ] },
  { secao: "financeiro", titulo: "Financeiro", cor: "var(--mob-vinho)", iconeSecao: <Landmark size={26} />, itens: [
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
  plano: PlanoAlimentacao,
  lancarDieta: LancarDieta,
  consultarDietas: ConsultarDietas,
  manejo: RelatoriosManejo,
  indicadores: Indicadores,
  aprovacoes: Aprovacoes,
  fluxoCaixa: FluxoCaixa,
  dre: Dre,
  rmca: Rmca,
  extrato: ExtratoCompleto,
};

export default function Pagina() {
  const [montado, setMontado] = useState(false);
  const [secaoAberta, setSecaoAberta] = useState<SecaoKey | "aparencia" | "news" | null>(null);
  const [sub, setSub] = useState<SubKey | null>(null);
  const fila = usePendentes();
  const online = useOnline();
  const [sincronizando, setSincronizando] = useState(false);

  useEffect(() => { setMontado(true); }, []);

  // Atalho do ícone "News" no cabeçalho do app (/app/menu#news) — abre a
  // sub-tela direto, sem passar pela grade de sessões.
  useEffect(() => {
    const verificarHash = () => { if (window.location.hash === "#news" && ehAdmin()) setSecaoAberta("news"); };
    verificarHash();
    window.addEventListener("hashchange", verificarHash);
    return () => window.removeEventListener("hashchange", verificarHash);
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

  // News é uma tela única (sem 2º nível de itens), igual "Aparência". Limpa o
  // hash ao voltar, senão um 2º clique no ícone do cabeçalho (mesmo href) não
  // dispara "hashchange" e a sub-tela não reabre.
  if (secaoAberta === "news") {
    return (
      <News
        onVoltar={() => {
          if (window.location.hash === "#news") history.replaceState(null, "", "/app/menu");
          setSecaoAberta(null);
        }}
      />
    );
  }

  // 2º nível: itens da sessão escolhida, em quadrados.
  if (secaoAberta === "aparencia") {
    return (
      <div>
        <MobVoltar titulo="Aparência" onVoltar={() => setSecaoAberta(null)} />
        <div className="mob-card" style={{ padding: "0.9rem 1rem" }}>
          <AparenciaSelector variant="app" />
        </div>
      </div>
    );
  }
  const grupoAberto = grupos.find((g) => g.secao === secaoAberta);
  if (grupoAberto) {
    const opcoes: OpcaoAcao[] = grupoAberto.itens.map((i) => ({ id: i.chave, label: i.titulo, icone: i.icone, cor: grupoAberto.cor }));
    return (
      <div>
        <MobVoltar titulo={grupoAberto.titulo} onVoltar={() => setSecaoAberta(null)} />
        <GradeAcoes opcoes={opcoes} onEscolher={(id) => setSub(id as SubKey)} />
      </div>
    );
  }

  // 1º nível: sessões, em quadrados coloridos.
  const secoesOpcoes: OpcaoAcao[] = [
    ...grupos.map((g) => ({ id: g.secao as string, label: g.titulo, icone: g.iconeSecao, cor: g.cor })),
    { id: "aparencia", label: "Aparência", icone: <Palette size={26} />, cor: "var(--mob-dourado)" },
    { id: "sair", label: "Sair / trocar de usuário", icone: <LogOut size={26} />, cor: "var(--mob-vermelho)" },
  ];

  return (
    <div>
      <MobTitulo>Menu</MobTitulo>

      <GradeAcoes
        opcoes={secoesOpcoes}
        onEscolher={(id) => id === "sair" ? logout() : setSecaoAberta(id as SecaoKey | "aparencia" | "news")}
      />

      {/* Sincronização offline — sempre visível, independente das sessões acima. */}
      <div id="pendentes" style={{ scrollMarginTop: "5rem", marginTop: "1.2rem" }}>
        <div className="mob-secao">Sincronização</div>
        {fila.length === 0 && <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem", marginBottom: "0.6rem" }}>Nada aguardando envio ✓</p>}

        {fila.map((item) => (
          <div key={item.id} className="mob-card" style={{ padding: "0.85rem 1rem", marginBottom: "0.6rem" }}>
            <div style={{ fontWeight: 700, fontSize: "0.92rem" }}>{item.descricao}</div>
            <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)" }}>{new Date(item.criadoEm).toLocaleString("pt-BR")}</div>
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
          <button type="button" className="mob-btn-2" onClick={enviarAgora} disabled={!online || sincronizando} style={{ marginTop: "0.2rem" }}>
            <CloudUpload size={17} /> {sincronizando ? "Enviando…" : online ? "Enviar agora" : "Sem internet"}
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
