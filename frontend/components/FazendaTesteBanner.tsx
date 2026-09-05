"use client";
// Tarja fixa, permanente e SEM botão de fechar no topo de toda tela (site e
// app móvel) enquanto a fazenda atual é a "Fazenda Teste" — cópia-sandbox da
// fazenda real Jairo Nasser (ver eh_teste em FazendaAtual, lib/api.ts). Existe
// para tornar impossível confundir as duas: quem está aqui precisa VER isso
// sem precisar rolar a tela, em qualquer módulo do sistema.
//
// Mesmo padrão de "publica a própria altura numa CSS var" do SuporteBanner.tsx
// (fixed não reserva espaço sozinho) — só que numa var PRÓPRIA
// (--fazenda-teste-banner-h) porque as duas tarjas podem aparecer juntas (um
// membro da Equipe CowData pode entrar em modo suporte justamente NA Fazenda
// Teste): esta fica por cima (mais fundamental — "em que ambiente eu estou"
// nunca muda durante a sessão), a de suporte desce pra baixo dela (ver seu
// `top`), e todo consumidor do offset antigo (--suporte-banner-h) em
// globals.css/Sidebar.tsx/TabsShell.tsx/app/app/layout.tsx/InsightsLayout.tsx
// passou a somar as duas variáveis.
import { useEffect, useRef, useState } from "react";
import { FlaskConical } from "lucide-react";
import { ehFazendaTeste, getFazendaAtual, temAreaPainelCowData } from "@/lib/api";
import { SincronizarFazendaTesteModal } from "@/components/SincronizarFazendaTesteModal";

const VERMELHO_ESCURO = "color-mix(in srgb, var(--red) 70%, black)";

export function FazendaTesteBanner() {
  const [ehTeste, setEhTeste] = useState(false);
  // Só quem administra fazendas no Painel CowData vê (e consegue disparar) o
  // botão de sincronizar — ver temAreaPainelCowData("fazendas"), a mesma
  // trava usada em Painel CowData > Fazendas (clientes).
  const [podeSincronizar, setPodeSincronizar] = useState(false);
  const [fazendaId, setFazendaId] = useState<number | null>(null);
  const [modalAberto, setModalAberto] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setEhTeste(ehFazendaTeste());
    setPodeSincronizar(temAreaPainelCowData("fazendas"));
    setFazendaId(getFazendaAtual()?.id ?? null);
  }, []);

  // Publica a altura real (varia com quebra de linha no celular) — mesma
  // técnica do SuporteBanner.tsx, ver comentário no topo deste arquivo.
  useEffect(() => {
    if (!ehTeste) {
      document.documentElement.style.setProperty("--fazenda-teste-banner-h", "0px");
      return;
    }
    const el = ref.current;
    if (!el) return;
    const publicar = () => document.documentElement.style.setProperty("--fazenda-teste-banner-h", `${el.offsetHeight}px`);
    publicar();
    const ro = new ResizeObserver(publicar);
    ro.observe(el);
    return () => {
      ro.disconnect();
      document.documentElement.style.setProperty("--fazenda-teste-banner-h", "0px");
    };
  }, [ehTeste]);

  if (!ehTeste) return null;

  return (
    <>
      <div ref={ref} style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 101, background: "var(--red)", color: "#fff",
        padding: "0.55rem 1rem", display: "flex", alignItems: "center", justifyContent: "center",
        gap: "0.8rem", flexWrap: "wrap", boxShadow: "0 2px 6px rgba(0,0,0,0.35)", textAlign: "center",
      }}>
        <span style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", fontWeight: 700 }}>
          <FlaskConical size={16} />
          AMBIENTE DE TESTE — cópia da fazenda real Jairo Nasser. Nada aqui é dado de produção.
        </span>
        {podeSincronizar && fazendaId != null && (
          // Rótulo longo de propósito (pedido explícito, não abreviar) — sem
          // whiteSpace:nowrap pra poder quebrar em 2 linhas num celular
          // estreito em vez de estourar a largura da tela.
          <button type="button" onClick={() => setModalAberto(true)}
            style={{
              fontSize: "0.72rem", fontWeight: 700, padding: "0.4rem 0.7rem", borderRadius: "var(--r-sm)",
              border: "1px solid #fff", background: VERMELHO_ESCURO, color: "#fff", cursor: "pointer",
              maxWidth: "min(92vw, 26rem)", lineHeight: 1.3,
            }}>
            SINCRONIZAR FAZENDA JAIRO NASSER COM FAZENDA TESTE
          </button>
        )}
      </div>
      {modalAberto && fazendaId != null && (
        <SincronizarFazendaTesteModal fazendaTesteId={fazendaId} onClose={() => setModalAberto(false)} />
      )}
    </>
  );
}
