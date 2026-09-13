"use client";
// Blocos reaproveitados pelas telas mobile-nativas do Painel CowData
// (Fazendas/Cadastros/Usuários/Parâmetros/Cofre) — mesmos 3 padrões de
// navegação do estudo /design aprovado em 05/09/2026 (grade → lista →
// detalhe em acordeão + seletor "aplicar em"), pra não duplicar
// cabeçalho/acordeão/seletor de fazendas-alvo em cada arquivo. Cores sempre
// de usePainelCowDataCor()/usePainelCowDataEstilos() — nunca hex fixo — pra
// herdar automaticamente o tema (escuro/misto/claro) escolhido no seletor do
// menu (ver app/painel-cowdata/layout.tsx). Mesma convenção de 100% inline
// style (sem Tailwind/CSS modules) já usada em InicioMobilePainelCowData.tsx
// e CockpitMobile.tsx.
import Link from "next/link";
import { useState, type CSSProperties, type ReactNode } from "react";
import { ArrowLeft, ChevronDown, ChevronRight, Search } from "lucide-react";
import type { CoresPainelCowData, usePainelCowDataEstilos } from "@/lib/painelCowDataTema";

type Estilos = ReturnType<typeof usePainelCowDataEstilos>;

export function CabecalhoMobilePainelCowData({
  titulo, subtitulo, voltarHref = "/painel-cowdata", voltarLabel = "Painel CowData", onVoltar, cor, acao,
}: {
  titulo: string; subtitulo?: string; voltarHref?: string; voltarLabel?: string;
  // Navegação interna (lista → detalhe dentro da MESMA tela, sem trocar de
  // rota) usa `onVoltar` (botão); a raiz de cada seção (voltar ao Início do
  // Painel CowData) usa `voltarHref` (Link), o padrão default.
  onVoltar?: () => void; cor: CoresPainelCowData; acao?: ReactNode;
}) {
  const estiloVoltar: CSSProperties = { display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", color: cor.mudo, textDecoration: "none", marginBottom: "0.9rem", background: "none", border: "none", padding: 0, cursor: "pointer" };
  return (
    <div style={{ padding: "calc(1.1rem + env(safe-area-inset-top, 0px)) 1.1rem 0.9rem", borderBottom: `1px solid ${cor.borda}`, flexShrink: 0 }}>
      {onVoltar ? (
        <button onClick={onVoltar} style={estiloVoltar}><ArrowLeft size={13} /> {voltarLabel}</button>
      ) : (
        <Link href={voltarHref} style={estiloVoltar}><ArrowLeft size={13} /> {voltarLabel}</Link>
      )}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.6rem" }}>
        <h1 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>{titulo}</h1>
        {acao}
      </div>
      {subtitulo && <p style={{ color: cor.mudo, fontSize: "0.78rem", marginTop: "0.25rem" }}>{subtitulo}</p>}
    </div>
  );
}

export function CorpoMobilePainelCowData({ children }: { children: ReactNode }) {
  return <div style={{ flex: 1, overflowY: "auto", padding: "1rem 1.1rem 2rem", display: "flex", flexDirection: "column", gap: "1rem" }}>{children}</div>;
}

export function CampoBuscaMobile({ valor, onChange, placeholder, cor }: { valor: string; onChange: (v: string) => void; placeholder: string; cor: CoresPainelCowData }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", background: cor.bg, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}>
      <Search size={15} style={{ color: cor.mudo, flexShrink: 0 }} />
      <input value={valor} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        style={{ flex: 1, minWidth: 0, background: "none", border: "none", outline: "none", color: cor.texto, fontSize: "0.85rem" }} />
    </div>
  );
}

export function LinhaListaMobile({ onClick, titulo, subtitulo, direita, cor }: {
  onClick: () => void; titulo: string; subtitulo?: ReactNode; direita?: ReactNode; cor: CoresPainelCowData;
}) {
  return (
    <button onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: "0.6rem", width: "100%", textAlign: "left",
      background: cor.painelAlt, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)",
      padding: "0.75rem 0.9rem", color: cor.texto, cursor: "pointer",
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "0.88rem", fontWeight: 700 }}>{titulo}</div>
        {subtitulo && <div style={{ fontSize: "0.74rem", color: cor.mudo, marginTop: "0.15rem" }}>{subtitulo}</div>}
      </div>
      {direita}
      <ChevronRight size={16} style={{ color: cor.mudo, flexShrink: 0 }} />
    </button>
  );
}

// Seção de acordeão (1 aberta por vez, ver useAcordeaoUnico) — mesmo truque
// visual de grid-template-rows 0fr→1fr já usado por Farmácia/Pessoas
// (.painel-expansivel, ver globals.css), reaproveitado aqui em vez de
// inventar outra transição.
export function SecaoAcordeaoMobile({ titulo, aberta, onToggle, cor, children, badge }: {
  titulo: string; aberta: boolean; onToggle: () => void; cor: CoresPainelCowData; children: ReactNode; badge?: ReactNode;
}) {
  return (
    <div style={{ background: cor.painelAlt, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", overflow: "hidden" }}>
      <button onClick={onToggle} style={{
        display: "flex", alignItems: "center", gap: "0.6rem", width: "100%", background: "none", border: "none",
        padding: "0.8rem 0.9rem", color: cor.texto, cursor: "pointer", textAlign: "left",
      }}>
        <span style={{ flex: 1, fontSize: "0.86rem", fontWeight: 700 }}>{titulo}</span>
        {badge}
        <ChevronDown size={16} style={{ color: cor.mudo, transform: aberta ? "rotate(180deg)" : "none", transition: "transform 0.2s", flexShrink: 0 }} />
      </button>
      <div className={`painel-expansivel${aberta ? " painel-expansivel-aberto" : ""}`}>
        <div style={{ borderTop: `1px solid ${cor.borda}` }}>
          <div style={{ padding: "0.9rem" }}>{children}</div>
        </div>
      </div>
    </div>
  );
}

export function useAcordeaoUnico(inicial: string | null = null) {
  const [aberta, setAberta] = useState<string | null>(inicial);
  return { aberta, alternar: (chave: string) => setAberta((a) => (a === chave ? null : chave)) };
}

// Mecânica "aplicar em todas as fazendas ativas OU só nas selecionadas" —
// idêntica em Cadastros globais e Parâmetros no desktop (fazenda_ids: null
// = todas as ativas; ver relatório de investigação). Reaproveitada aqui tal
// e qual, só com layout vertical em vez do card horizontal do desktop.
export function SeletorAlvoFazendas({
  fazendas, alvoTodas, setAlvoTodas, selecionadas, toggleSelecionada, mostrarSeletor, setMostrarSeletor, cor,
}: {
  fazendas: { id: number; nome: string; ativa?: boolean }[];
  alvoTodas: boolean; setAlvoTodas: (v: boolean) => void;
  selecionadas: Set<number>; toggleSelecionada: (id: number) => void;
  mostrarSeletor: boolean; setMostrarSeletor: (v: boolean) => void;
  cor: CoresPainelCowData;
}) {
  const ativas = fazendas.filter((f) => f.ativa !== false);
  return (
    <div style={{ background: cor.painelAlt, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.9rem" }}>
      <p style={{ fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: cor.mudo, margin: "0 0 0.6rem" }}>Aplicar em</p>
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", marginBottom: "0.5rem", cursor: "pointer" }}>
        <input type="radio" checked={alvoTodas} onChange={() => setAlvoTodas(true)} />
        Todas as fazendas ativas ({ativas.length})
      </label>
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", cursor: "pointer" }}>
        <input type="radio" checked={!alvoTodas} onChange={() => setAlvoTodas(false)} />
        Selecionar fazendas específicas ({selecionadas.size})
      </label>
      {!alvoTodas && (
        <>
          <button onClick={() => setMostrarSeletor(!mostrarSeletor)} style={{ marginTop: "0.6rem", background: "none", border: "none", color: cor.doradoClaro, fontSize: "0.78rem", cursor: "pointer", padding: 0 }}>
            {mostrarSeletor ? "Esconder lista" : "Escolher fazendas"}
          </button>
          {mostrarSeletor && (
            <div style={{ marginTop: "0.6rem", maxHeight: "12rem", overflowY: "auto", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {fazendas.map((f) => (
                <label key={f.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", cursor: "pointer" }}>
                  <input type="checkbox" checked={selecionadas.has(f.id)} onChange={() => toggleSelecionada(f.id)} />
                  {f.nome}
                </label>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function CampoMobile({ label, children, estilos }: { label: string; children: ReactNode; estilos: Estilos }) {
  return (
    <div style={{ marginBottom: "0.7rem" }}>
      <label style={estilos.labelStyle}>{label}</label>
      {children}
    </div>
  );
}

export function BotaoMobile({
  variante = "primario", estilos, disabled, children, style, ...props
}: { variante?: "primario" | "ghost"; estilos: Estilos } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const base = variante === "primario" ? estilos.btnPrimario : estilos.btnGhost;
  const estiloFinal: CSSProperties = { ...base, width: "100%", justifyContent: "center", opacity: disabled ? 0.6 : 1, ...style };
  return <button {...props} disabled={disabled} style={estiloFinal}>{children}</button>;
}

export function inputEstilo(estilos: Estilos, extra?: CSSProperties): CSSProperties {
  return { ...estilos.inputStyle, width: "100%", ...extra };
}
