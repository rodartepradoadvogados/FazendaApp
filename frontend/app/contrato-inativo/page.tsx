"use client";
// Tela de contrato AGUARDANDO APROVAÇÃO ou SUSPENSO (Plano Financeiro F2.3).
// Casca própria e mínima — sem Sidebar, sem menu: não há nada a navegar até o
// contrato voltar a ficar ativo (ver AuthShell.tsx, que manda para cá quem é
// barrado por lib/modulos.ts::contratoBloqueia e, ao contrato ativar, leva
// daqui à página inicial). Tom neutro, sem culpar. Dono, equipe CowData e
// sessão de suporte nunca chegam aqui (são isentos). Escuta o evento de
// contrato atualizado: aprovado no Painel CowData, a tela se resolve sozinha
// na próxima releitura (ao reabrir a aba) ou no botão "Verificar novamente".
import { useEffect, useState } from "react";
import { Loader2, RefreshCw, LogOut, Repeat } from "lucide-react";
import { useRouter } from "next/navigation";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { EVENTO_CONTRATO, getFazendaAtual, logout, renovarContrato } from "@/lib/api";
import { mensagemContrato } from "@/lib/modulos";

export default function ContratoInativoPage() {
  const router = useRouter();
  const [status, setStatus] = useState<string | null>(null);
  const [fazendaNome, setFazendaNome] = useState("");
  const [verificando, setVerificando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    const ler = () => {
      const f = getFazendaAtual();
      setStatus(f?.contrato_status ?? null);
      setFazendaNome(f?.nome || "");
    };
    ler();
    window.addEventListener(EVENTO_CONTRATO, ler);
    return () => window.removeEventListener(EVENTO_CONTRATO, ler);
  }, []);

  const verificar = async () => {
    setVerificando(true); setAviso(null);
    const mudou = await renovarContrato(true);
    setVerificando(false);
    if (!mudou) setAviso("Ainda sem novidades. Tente novamente em alguns minutos.");
  };

  const { titulo, texto } = mensagemContrato(status);
  const botao = { display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.4rem", minHeight: 44, width: "100%", cursor: "pointer" } as const;

  return (
    <section style={{ minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center", padding: "3rem 1rem", background: "var(--bg)" }}>
      <div className="card" style={{ width: "100%", maxWidth: "380px", textAlign: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem", marginBottom: "1.2rem" }}>
          <CowDataMark size={46} />
          <CowDataWordmark size="1.3rem" />
        </div>
        {fazendaNome && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", margin: "0 0 0.4rem" }}>{fazendaNome}</p>}
        <h1 style={{ fontSize: "1.15rem", fontWeight: 700, margin: "0 0 0.6rem" }}>{titulo}</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", lineHeight: 1.5, margin: "0 0 1.2rem" }}>{texto}</p>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <button type="button" className="btn-primary" style={botao} onClick={verificar} disabled={verificando}>
            {verificando ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />} Verificar novamente
          </button>
          <button type="button" className="btn-secondary" style={botao} onClick={() => router.push("/escolher-conta")}>
            <Repeat size={16} /> Trocar de conta
          </button>
          <button type="button" className="btn-secondary" style={botao} onClick={() => logout()}>
            <LogOut size={16} /> Sair
          </button>
        </div>
        <p role="status" aria-live="polite" style={{ color: "var(--text-muted)", fontSize: "0.8rem", margin: aviso ? "0.8rem 0 0" : 0 }}>{aviso}</p>
      </div>
    </section>
  );
}
