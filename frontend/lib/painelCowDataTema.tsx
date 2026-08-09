"use client";
// Aparência do Painel CowData — 3 modos (escuro/misto/claro), independente
// do tema do site (ver components/ThemeSwitcher.tsx: aquele mexe em
// data-theme/CSS vars no <html>; este painel usa um objeto COR fixo por
// componente — ver histórico de app/painel-cowdata/layout.tsx — então
// precisa do próprio mecanismo). Escuro é o padrão, pedido explícito do
// usuário ("mantendo o escuro, como já está, como padrão"), e seus valores
// abaixo são EXATAMENTE os que já existiam antes deste arquivo (derivados
// de CORES_CONTADOR em app/contador/layout.tsx) — trocar de aparência não
// muda nada pra quem nunca abrir o seletor.
import { createContext, useContext, useEffect, useState, type CSSProperties, type ReactNode } from "react";

export type TemaPainelCowData = "escuro" | "misto" | "claro";

export type CoresPainelCowData = {
  bg: string; painel: string; painelAlt: string; cartao: string; borda: string; bordaClara: string;
  texto: string; textoPainel: string; mudo: string; dourado: string; doradoClaro: string;
  verde: string; vermelho: string;
};

const CHAVE_LOCALSTORAGE = "tema_painel_cowdata";

const PALETAS: Record<TemaPainelCowData, CoresPainelCowData> = {
  // Idêntico ao que já era hardcoded em cada page.tsx antes desta mudança.
  escuro: {
    bg: "#1A2028", painel: "#212832", painelAlt: "#262E39", cartao: "#262E39",
    borda: "#39424F", bordaClara: "#4B5563",
    texto: "#F1F3F5", textoPainel: "#F1F3F5", mudo: "#9CA6B4",
    dourado: "#6B7F99", doradoClaro: "#8FA0B5",
    verde: "#8faa7b", vermelho: "#b5544a",
  },
  // Meio-termo: chrome ainda escuro, superfícies um pouco mais claras — menos
  // contraste que o escuro padrão, sem ir para fundo branco.
  misto: {
    bg: "#262C34", painel: "#2E3540", painelAlt: "#363E4A", cartao: "#363E4A",
    borda: "#4B5563", bordaClara: "#5C6572",
    texto: "#F1F3F5", textoPainel: "#F1F3F5", mudo: "#AEB6C2",
    dourado: "#7C93AD", doradoClaro: "#9AB0C7",
    verde: "#8faa7b", vermelho: "#c06860",
  },
  claro: {
    bg: "#F4F6F8", painel: "#FFFFFF", painelAlt: "#F1F3F6", cartao: "#F1F3F6",
    borda: "#DDE2E8", bordaClara: "#C6CDD6",
    texto: "#1F2530", textoPainel: "#1F2530", mudo: "#5B6472",
    dourado: "#3D5A80", doradoClaro: "#5D7A9E",
    verde: "#3F6B31", vermelho: "#A23B32",
  },
};

const PainelCowDataTemaContext = createContext<{
  tema: TemaPainelCowData; setTema: (t: TemaPainelCowData) => void; cor: CoresPainelCowData;
} | null>(null);

export function PainelCowDataTemaProvider({ children }: { children: ReactNode }) {
  const [tema, setTemaState] = useState<TemaPainelCowData>("escuro");

  useEffect(() => {
    const salvo = localStorage.getItem(CHAVE_LOCALSTORAGE) as TemaPainelCowData | null;
    if (salvo && PALETAS[salvo]) setTemaState(salvo);
  }, []);

  const setTema = (t: TemaPainelCowData) => {
    setTemaState(t);
    localStorage.setItem(CHAVE_LOCALSTORAGE, t);
  };

  return (
    <PainelCowDataTemaContext.Provider value={{ tema, setTema, cor: PALETAS[tema] }}>
      {children}
    </PainelCowDataTemaContext.Provider>
  );
}

export function usePainelCowDataTema() {
  const ctx = useContext(PainelCowDataTemaContext);
  if (!ctx) throw new Error("usePainelCowDataTema precisa estar dentro de <PainelCowDataTemaProvider>");
  return ctx;
}

// Atalho para as telas que só precisam da paleta atual (mesmo objeto COR
// que cada page.tsx já montava na mão, agora reativo à aparência escolhida).
export function usePainelCowDataCor(): CoresPainelCowData {
  return usePainelCowDataTema().cor;
}

// Os 4 estilos repetidos em quase toda tela do Painel CowData (input, label,
// botão primário/ghost) — mesma forma que cada page.tsx montava na mão com
// hex fixo antes desta mudança, agora reativos à aparência escolhida.
export function usePainelCowDataEstilos() {
  const cor = usePainelCowDataCor();
  const inputStyle: CSSProperties = {
    background: cor.bg, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem",
    color: cor.texto, fontSize: "0.82rem",
  };
  const labelStyle: CSSProperties = { fontSize: "0.7rem", color: cor.mudo, marginBottom: "0.25rem", display: "block" };
  const btnPrimario: CSSProperties = {
    background: cor.dourado, color: cor.bg, border: "none", borderRadius: "var(--r-sm)", padding: "0.5rem 1rem",
    fontSize: "0.82rem", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: "0.4rem",
  };
  const btnGhost: CSSProperties = {
    background: "transparent", color: cor.mudo, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)",
    padding: "0.35rem 0.6rem", fontSize: "0.75rem", cursor: "pointer",
  };
  return { cor, inputStyle, labelStyle, btnPrimario, btnGhost };
}
