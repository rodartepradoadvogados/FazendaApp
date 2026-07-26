"use client";
// Barra de abas estilo navegador (Chrome) — duplo clique num link da Sidebar
// abre o destino numa aba nova, sem perder a aba atual exatamente onde
// estava. Cada aba extra é um <iframe> independente (própria Sidebar, próprio
// estado, própria rolagem — nunca desmontado ao trocar de aba, só escondido).
// A 1ª aba ("nativa") continua sendo a página real renderizada pelo Next.js,
// sem iframe — zero mudança de comportamento/performance para quem nunca usa
// o recurso. Limite de 5 abas simultâneas (nativa + até 4 extras); ao tentar
// abrir a 6ª, avisa e bloqueia (decisão do usuário, não fecha nada sozinho).
//
// Só a JANELA DE CIMA desenha a barra — se este componente estiver rodando
// dentro de um <iframe> de aba (ver estaDentroDeAba), ele só repassa
// {children} direto, sem desenhar nada, para nunca aninhar uma barra de abas
// dentro de outra.
import { useEffect, useRef, useState } from "react";
import { X, Plus } from "lucide-react";
import { MENSAGEM_ABRIR_ABA, estaDentroDeAba } from "@/lib/tabs";

const LIMITE_ABAS = 5;

type AbaExtra = { id: string; url: string; titulo: string };

export function TabsShell({ children }: { children: React.ReactNode }) {
  const [dentroDeAba, setDentroDeAba] = useState<boolean | null>(null);
  const [abas, setAbas] = useState<AbaExtra[]>([]);
  const [ativaId, setAtivaId] = useState<"nativa" | string>("nativa");
  const [aviso, setAviso] = useState<string | null>(null);
  const proximoId = useRef(1);

  useEffect(() => {
    setDentroDeAba(estaDentroDeAba());
  }, []);

  useEffect(() => {
    if (dentroDeAba) return; // só a janela de cima escuta pedidos de abertura
    function aoReceberMensagem(e: MessageEvent) {
      if (e.origin !== window.location.origin) return;
      if (e.data?.tipo !== MENSAGEM_ABRIR_ABA) return;
      abrirAba(e.data.url as string, e.data.titulo as string);
    }
    window.addEventListener("message", aoReceberMensagem);
    return () => window.removeEventListener("message", aoReceberMensagem);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dentroDeAba, abas.length]);

  function abrirAba(url: string, titulo: string) {
    setAbas((atuais) => {
      // Já existe uma aba com essa URL — só ativa ela em vez de duplicar.
      const existente = atuais.find((a) => a.url === url);
      if (existente) {
        setAtivaId(existente.id);
        return atuais;
      }
      if (atuais.length + 1 >= LIMITE_ABAS) {
        setAviso(`Limite de ${LIMITE_ABAS} abas atingido — feche alguma aba antes de abrir outra.`);
        return atuais;
      }
      const id = `aba-${proximoId.current++}`;
      setAtivaId(id);
      return [...atuais, { id, url, titulo }];
    });
  }

  function fecharAba(id: string) {
    setAbas((atuais) => atuais.filter((a) => a.id !== id));
    setAtivaId((atual) => (atual === id ? "nativa" : atual));
  }

  // Ainda não sabemos se estamos numa aba (1º render, antes do useEffect) —
  // repassa direto para nunca piscar/aninhar a barra por engano.
  if (dentroDeAba !== false) return <>{children}</>;

  const temAbasExtras = abas.length > 0;

  return (
    // Conteúdo sempre ocupa a tela inteira, do topo — a faixa de abas (e o
    // aviso) flutuam por cima como overlay (position: fixed), começando em
    // left-56 (mesma largura da Sidebar, w-56) para nunca cobrir o
    // logotipo/menu: a Sidebar (nativa ou dentro de cada iframe — cada aba
    // renderiza sua própria página completa) continua começando em y=0,
    // intocada; só a área de conteúdo à direita dela fica coberta pela faixa.
    <div style={{ height: "100vh", position: "relative" }}>
      <div style={{ height: "100%" }}>
        <div style={{ display: ativaId === "nativa" ? "block" : "none", height: "100%" }}>
          {children}
        </div>
        {abas.map((aba) => (
          <iframe
            key={aba.id}
            src={aba.url}
            title={aba.titulo}
            style={{ display: ativaId === aba.id ? "block" : "none", width: "100%", height: "100%", border: "none" }}
          />
        ))}
      </div>

      {temAbasExtras && (
        // Só no desktop (md+) — no mobile a Sidebar fica escondida atrás do
        // menu hambúrguer e já existe uma barra fixa própria no topo (ver
        // Sidebar.tsx); duplo clique também não é um gesto natural no touch.
        <div
          className="hidden md:flex left-0 md:left-56"
          style={{
            position: "fixed", top: 0, right: 0, zIndex: 65,
            alignItems: "stretch", height: "2.2rem",
            background: "var(--surface-2)", borderBottom: "1px solid var(--border)", overflowX: "auto",
            boxShadow: "0 1px 4px rgba(0,0,0,0.15)",
          }}
        >
          <button
            type="button" onClick={() => setAtivaId("nativa")}
            title="Aba principal"
            style={{
              display: "flex", alignItems: "center", gap: "0.35rem", padding: "0 0.9rem", border: "none",
              borderRight: "1px solid var(--border)", cursor: "pointer", fontSize: "0.76rem", fontWeight: 700,
              background: ativaId === "nativa" ? "var(--surface)" : "transparent",
              color: ativaId === "nativa" ? "var(--text)" : "var(--text-muted)", whiteSpace: "nowrap",
            }}
          >
            Principal
          </button>
          {abas.map((aba) => (
            <div
              key={aba.id}
              // Contorno na cor da paleta escolhida (var(--dourado) — muda com
              // vinho/verde/azul) em toda aba aberta por duplo clique, pra
              // diferenciar de cara da aba Principal e não confundir quando
              // há várias abertas.
              style={{
                display: "flex", alignItems: "center", gap: "0.35rem", padding: "0 0.5rem 0 0.9rem",
                margin: "0.25rem 0.3rem", borderRadius: "6px",
                border: "1.5px solid var(--dourado)",
                cursor: "pointer", fontSize: "0.76rem", fontWeight: 700,
                background: ativaId === aba.id ? "var(--surface)" : "transparent",
                color: ativaId === aba.id ? "var(--text)" : "var(--text-muted)", whiteSpace: "nowrap",
              }}
              onClick={() => setAtivaId(aba.id)}
              title={aba.titulo}
            >
              <span style={{ maxWidth: "9rem", overflow: "hidden", textOverflow: "ellipsis" }}>{aba.titulo}</span>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); fecharAba(aba.id); }}
                title="Fechar aba" aria-label={`Fechar aba ${aba.titulo}`}
                style={{ border: "none", background: "transparent", cursor: "pointer", color: "inherit", display: "flex", padding: "0.15rem" }}
              >
                <X size={12} />
              </button>
            </div>
          ))}
          <div style={{ display: "flex", alignItems: "center", padding: "0 0.7rem", color: "var(--text-muted)", fontSize: "0.7rem", gap: "0.3rem" }}>
            <Plus size={12} /> duplo clique num item da barra lateral abre aba nova
          </div>
        </div>
      )}

      {aviso && (
        <div
          role="alert"
          className="hidden md:flex left-0 md:left-56"
          style={{
            position: "fixed", right: 0, top: temAbasExtras ? "2.2rem" : 0, zIndex: 64,
            padding: "0.5rem 0.9rem", background: "var(--amber-bg, #F7EEDA)", color: "var(--amber, #B9831F)",
            fontSize: "0.78rem", fontWeight: 600, alignItems: "center", justifyContent: "space-between", gap: "0.6rem",
          }}
        >
          <span>{aviso}</span>
          <button type="button" onClick={() => setAviso(null)} style={{ border: "none", background: "transparent", cursor: "pointer", color: "inherit" }}>
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
