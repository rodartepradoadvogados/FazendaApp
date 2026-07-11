"use client";
// Tela MENU do app de campo: lista curada (não é o menu inteiro do site) com
// atalhos para o site completo, a fila de sincronização offline e o rodapé com
// o usuário logado. Itens são filtrados por permissão (podeModulo).
import { useEffect, useState } from "react";
import {
  Stethoscope, Syringe, CalendarDays, Baby, Wheat, FileBarChart, Gauge, ListChecks,
  Globe, LogOut, CloudUpload, Trash2,
} from "lucide-react";
import { getUsuario, logout, podeModulo, ROTA_MODULO } from "@/lib/api";
import { usePendentes, useOnline, sincronizar, descartarPendente } from "@/lib/offline";
import { MobTitulo, MobLinha } from "@/components/mobile/ui";

type Item = { titulo: string; rota: string; icone: React.ReactNode };
type Grupo = { secao: string; itens: Item[] };

const GRUPOS: Grupo[] = [
  { secao: "Reprodução", itens: [
    { titulo: "Agenda do Veterinário", rota: "/reproducao", icone: <Stethoscope size={18} /> },
    { titulo: "Protocolos IATF", rota: "/reproducao", icone: <Syringe size={18} /> },
  ] },
  { secao: "Sanidade", itens: [
    { titulo: "Calendário Sanitário", rota: "/sanidade", icone: <CalendarDays size={18} /> },
    { titulo: "Relatório de Bezerras", rota: "/sanidade", icone: <Baby size={18} /> },
  ] },
  { secao: "Alimentação", itens: [
    { titulo: "Plano por Lote", rota: "/alimentacao", icone: <Wheat size={18} /> },
  ] },
  { secao: "Gestão", itens: [
    { titulo: "Relatórios Gerenciais", rota: "/relatorios", icone: <FileBarChart size={18} /> },
    { titulo: "Indicadores", rota: "/indicadores", icone: <Gauge size={18} /> },
    { titulo: "Lançamentos completos", rota: "/lancamentos", icone: <ListChecks size={18} /> },
  ] },
];

export default function Pagina() {
  const [montado, setMontado] = useState(false);
  const fila = usePendentes();
  const online = useOnline();
  const [sincronizando, setSincronizando] = useState(false);

  useEffect(() => { setMontado(true); }, []);

  async function enviarAgora() {
    setSincronizando(true);
    try { await sincronizar(); } finally { setSincronizando(false); }
  }

  const usuario = montado ? getUsuario() : null;
  // No servidor / antes de montar não sabemos as permissões — só renderiza os
  // grupos após montar para não vazar itens sem permissão.
  const grupos = montado
    ? GRUPOS.map((g) => ({ ...g, itens: g.itens.filter((i) => podeModulo(ROTA_MODULO[i.rota] || i.rota)) })).filter((g) => g.itens.length)
    : [];

  return (
    <div>
      <MobTitulo>Menu</MobTitulo>

      {grupos.map((g) => (
        <div key={g.secao}>
          <div className="mob-secao">{g.secao}</div>
          {g.itens.map((i, idx) => (
            <MobLinha key={`${i.rota}-${idx}`} icone={i.icone} titulo={i.titulo} subtitulo="Abre o site completo" href={i.rota} />
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
      <MobLinha icone={<Globe size={18} />} titulo="Abrir site completo" subtitulo="Versão completa no navegador" href="/" />
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
