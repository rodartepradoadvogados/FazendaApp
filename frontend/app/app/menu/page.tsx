"use client";
// Tela MENU do app de campo. NADA remete ao site: cada item abre a informação
// GERENCIAL (só leitura, enxuta) dentro do próprio app, numa SUB-TELA com botão
// voltar (estado interno, sem navegar de rota). Itens filtrados por permissão.
// Mantém a fila de sincronização offline e o rodapé com o usuário logado.
import { useEffect, useState } from "react";
import {
  Stethoscope, Syringe, CalendarDays, Wheat, FileBarChart, Gauge,
  LogOut, CloudUpload, Trash2, ChevronRight, CheckCheck,
} from "lucide-react";
import { getUsuario, logout, podeModulo, ehAdmin, ROTA_MODULO } from "@/lib/api";
import { usePendentes, useOnline, sincronizar, descartarPendente } from "@/lib/offline";
import { MobTitulo } from "@/components/mobile/ui";
import AgendaVet from "@/components/mobile/menu/AgendaVet";
import ProtocolosIatf from "@/components/mobile/menu/ProtocolosIatf";
import CalendarioSanitario from "@/components/mobile/menu/CalendarioSanitario";
import PlanoAlimentacao from "@/components/mobile/menu/PlanoAlimentacao";
import RelatoriosManejo from "@/components/mobile/menu/RelatoriosManejo";
import Indicadores from "@/components/mobile/menu/Indicadores";
import Aprovacoes from "@/components/mobile/menu/Aprovacoes";

type SubKey = "agendaVet" | "iatf" | "calendario" | "plano" | "manejo" | "indicadores" | "aprovacoes";
type Item = { chave: SubKey; titulo: string; subtitulo: string; rota: string; icone: React.ReactNode; soAdmin?: boolean };
type Grupo = { secao: string; itens: Item[] };

const GRUPOS: Grupo[] = [
  { secao: "Reprodução", itens: [
    { chave: "agendaVet", titulo: "Agenda do Veterinário", subtitulo: "Listas do rebanho para a visita", rota: "/reproducao", icone: <Stethoscope size={18} /> },
    { chave: "iatf", titulo: "Protocolos IATF", subtitulo: "Vacas em andamento (D0/D7/D9/D11)", rota: "/reproducao", icone: <Syringe size={18} /> },
  ] },
  { secao: "Sanidade", itens: [
    { chave: "calendario", titulo: "Calendário Sanitário", subtitulo: "Próximos eventos (90 dias)", rota: "/sanidade", icone: <CalendarDays size={18} /> },
  ] },
  { secao: "Alimentação", itens: [
    { chave: "plano", titulo: "Plano por Lote", subtitulo: "Consumo por lote e ingrediente", rota: "/alimentacao", icone: <Wheat size={18} /> },
  ] },
  { secao: "Gestão", itens: [
    { chave: "manejo", titulo: "Relatórios de Manejo", subtitulo: "Listas do que fazer, por semáforo", rota: "/relatorios", icone: <FileBarChart size={18} /> },
    { chave: "indicadores", titulo: "Indicadores", subtitulo: "8 números de consulta rápida", rota: "/indicadores", icone: <Gauge size={18} /> },
    { chave: "aprovacoes", titulo: "Aprovações", subtitulo: "Lançamentos do Telegram a aprovar", rota: "/aprovacoes", icone: <CheckCheck size={18} />, soAdmin: true },
  ] },
];

const SUBTELAS: Record<SubKey, (props: { onVoltar: () => void }) => React.ReactNode> = {
  agendaVet: AgendaVet,
  iatf: ProtocolosIatf,
  calendario: CalendarioSanitario,
  plano: PlanoAlimentacao,
  manejo: RelatoriosManejo,
  indicadores: Indicadores,
  aprovacoes: Aprovacoes,
};

export default function Pagina() {
  const [montado, setMontado] = useState(false);
  const [sub, setSub] = useState<SubKey | null>(null);
  const fila = usePendentes();
  const online = useOnline();
  const [sincronizando, setSincronizando] = useState(false);

  useEffect(() => { setMontado(true); }, []);

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

  return (
    <div>
      <MobTitulo>Menu</MobTitulo>

      {grupos.map((g) => (
        <div key={g.secao}>
          <div className="mob-secao">{g.secao}</div>
          {g.itens.map((i) => (
            <button key={i.chave} type="button" className="mob-linha" style={{ marginBottom: "0.6rem" }} onClick={() => setSub(i.chave)}>
              <span style={{ width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(184,134,11,0.12)", color: "var(--mob-dourado-2)", flexShrink: 0 }}>{i.icone}</span>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontWeight: 700, fontSize: "0.95rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.titulo}</span>
                <span style={{ display: "block", fontSize: "0.78rem", color: "var(--mob-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{i.subtitulo}</span>
              </span>
              <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
            </button>
          ))}
        </div>
      ))}

      {/* Sincronização offline */}
      <div id="pendentes" style={{ scrollMarginTop: "5rem" }}>
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

      {/* Sistema */}
      <div className="mob-secao">Sistema</div>
      <button type="button" className="mob-btn-2" onClick={logout} style={{ marginTop: "0.4rem" }}>
        <LogOut size={17} /> Sair / trocar de usuário
      </button>

      {/* Rodapé */}
      <p style={{ textAlign: "center", color: "var(--mob-muted)", fontSize: "0.78rem", margin: "1.6rem 0 0.5rem" }}>
        {montado && usuario ? `${usuario.nome || usuario.username || "Usuário"} · ` : ""}v1.0 · App de campo
      </p>
    </div>
  );
}
