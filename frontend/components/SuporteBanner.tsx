"use client";
// Faixa fixa no topo do conteúdo, visível em toda a fazenda, enquanto a
// sessão foi aberta a partir do Painel CowData como suporte (ver
// lib/api.ts::entrarComoSuporte e backend/main.py::_bloquear_modo_suporte).
// Nunca aparece pra quem entrou direto na fazenda como administrador.
//
// Layout em 2 linhas dentro da mesma faixa vermelha, pedido explícito do
// usuário (ago/2026): linha 1 = símbolo de atenção + "Suporte CowData
// ativo: [membro] entrou às [hora]. Motivo: [motivo]" com o timer mm:ss e o
// botão "Encerrar agora" à direita; linha 2 = "Você está atuando como
// [fazenda]". ~3-5cm de altura no desktop (aprox. 4.2rem no total).
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle } from "lucide-react";
import { getModoSuporte, encerrarModoSuporte, LABEL_NIVEL_SIGILO_EQUIPE_COWDATA, type ModoSuporte } from "@/lib/api";

const VERMELHO = "#7A1F1F";
const VERMELHO_ESCURO = "#5C1717";

function mmss(segundos: number): string {
  const s = Math.max(0, Math.round(segundos));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export function SuporteBanner() {
  const router = useRouter();
  const [modo, setModo] = useState<ModoSuporte | null>(null);
  const [agora, setAgora] = useState<number>(0);
  const [encerrando, setEncerrando] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setModo(getModoSuporte());
    setAgora(Date.now());
    // A cada segundo — é um cronômetro de verdade ("expira em mm:ss"), não
    // um contador aproximado em minutos como antes.
    const t = setInterval(() => setAgora(Date.now()), 1_000);
    return () => clearInterval(t);
  }, []);

  // Publica a altura real da faixa (varia com quebra de linha do texto) em
  // uma CSS var global, para que todo elemento fixed do resto do app
  // (botões do topo, cabeçalho mobile) e o padding-top do body saibam
  // quanto empurrar o conteúdo pra baixo — ver app/globals.css. Zera ao
  // desmontar (fim do modo suporte) para não deixar espaço fantasma.
  useEffect(() => {
    if (!modo) {
      document.documentElement.style.setProperty("--suporte-banner-h", "0px");
      return;
    }
    const el = ref.current;
    if (!el) return;
    const publicar = () => document.documentElement.style.setProperty("--suporte-banner-h", `${el.offsetHeight}px`);
    publicar();
    const ro = new ResizeObserver(publicar);
    ro.observe(el);
    return () => {
      ro.disconnect();
      document.documentElement.style.setProperty("--suporte-banner-h", "0px");
    };
  }, [modo]);

  if (!modo) return null;

  const segundosRestantes = (new Date(modo.expiraEm).getTime() - agora) / 1000;
  const horaEntrada = new Date(modo.entradaEm).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  async function encerrar() {
    setEncerrando(true);
    await encerrarModoSuporte();
    router.replace("/painel-cowdata");
  }

  return (
    <div ref={ref} style={{
      position: "fixed", top: 0, left: 0, right: 0, zIndex: 100, background: VERMELHO, color: "#FCEBEB",
      padding: "0.6rem 1rem", display: "flex", flexDirection: "column", gap: "0.4rem",
      minHeight: "3.6rem", justifyContent: "center", boxShadow: "0 2px 6px rgba(0,0,0,0.35)",
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.8rem", flexWrap: "wrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.82rem", fontWeight: 700 }}>
          <AlertTriangle size={17} />
          Suporte CowData ativo: {modo.membroNome} entrou às {horaEntrada}. Motivo: {modo.motivo}.
          {modo.protocolo && <span style={{ fontWeight: 400, opacity: 0.85 }}> Protocolo {modo.protocolo}.</span>}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "0.68rem", opacity: 0.85 }}>expira em</div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
              {segundosRestantes > 0 ? mmss(segundosRestantes) : "00:00"}
            </div>
          </div>
          <button type="button" onClick={encerrar} disabled={encerrando}
            style={{
              fontSize: "0.78rem", fontWeight: 700, padding: "0.4rem 0.8rem", borderRadius: "var(--r-sm)",
              border: "1px solid #FCEBEB", background: VERMELHO_ESCURO, color: "#FCEBEB", cursor: "pointer", whiteSpace: "nowrap",
            }}>
            {encerrando ? "Encerrando…" : "Encerrar agora"}
          </button>
        </div>
      </div>
      <p style={{ margin: 0, fontSize: "0.78rem", fontWeight: 600 }}>
        Você está atuando como {modo.fazendaNome}.
        {/* Rótulo amigável, nunca "basico/tecnico/total" cru — mesmo texto
            usado ao configurar o nível em Painel CowData > Equipe. Avisa
            ANTES de um 403 de "não alcança X" surpreender o suporte. */}
        {modo.nivelSigilo && <span style={{ fontWeight: 400, opacity: 0.85 }}> Nível de acesso: {LABEL_NIVEL_SIGILO_EQUIPE_COWDATA[modo.nivelSigilo]}.</span>}
      </p>
    </div>
  );
}
