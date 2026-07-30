"use client";
// Barra de abas estilo navegador (Chrome) — duplo clique num link da Sidebar
// abre o destino numa aba nova, sem perder a aba atual exatamente onde
// estava. Cada aba extra é um <iframe> independente (própria Sidebar, próprio
// estado, própria rolagem — nunca desmontado ao trocar de aba, só escondido).
// A 1ª aba ("nativa") continua sendo a página real renderizada pelo Next.js,
// sem iframe — zero mudança de comportamento/performance para quem nunca usa
// o recurso. Limite de 5 abas simultâneas (nativa + até 4 extras); ao tentar
// abrir a 6ª, avisa e bloqueia (decisão do usuário, não fecha nada sozinho).
// Botão direito numa guia abre um menu: Fechar / Dividir tela (escolhe outra
// guia aberta pra mostrar lado a lado) / Desfazer divisão / Cancelar.
//
// Só a JANELA DE CIMA desenha a barra — se este componente estiver rodando
// dentro de um <iframe> de aba (ver estaDentroDeAba), ele só repassa
// {children} direto, sem desenhar nada, para nunca aninhar uma barra de abas
// dentro de outra.
import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { X, Plus } from "lucide-react";
import { MENSAGEM_ABRIR_ABA, MENSAGEM_TITULO_ABA, avisarTituloAba, estaDentroDeAba } from "@/lib/tabs";
import { rotuloDaPagina, caminhoLabels } from "@/components/Sidebar";
import { useSubNav } from "@/components/SubNavContext";

const LIMITE_ABAS = 5;

type AbaExtra = { id: string; url: string; titulo: string };
type MenuContexto = { id: string; x: number; y: number };

const itemMenu: React.CSSProperties = {
  display: "block", width: "100%", textAlign: "left", padding: "0.4rem 0.7rem",
  border: "none", background: "transparent", cursor: "pointer", fontSize: "0.8rem",
  color: "var(--text)", borderRadius: "5px",
};

export function TabsShell({ children }: { children: React.ReactNode }) {
  const [dentroDeAba, setDentroDeAba] = useState<boolean | null>(null);
  const [abas, setAbas] = useState<AbaExtra[]>([]);
  const [ativaId, setAtivaId] = useState<"nativa" | string>("nativa");
  const [aviso, setAviso] = useState<string | null>(null);
  // Divisão de tela: duas guias (ids) mostradas lado a lado — null fora do
  // modo dividido. Ver menu de contexto (botão direito numa guia).
  const [divisao, setDivisao] = useState<[string, string] | null>(null);
  const [menu, setMenu] = useState<MenuContexto | null>(null);
  const [escolhendoParceiro, setEscolhendoParceiro] = useState(false);
  const proximoId = useRef(1);
  // Referências aos elementos <iframe> de cada aba extra — usadas para casar
  // o `event.source` de uma MENSAGEM_TITULO_ABA com o id da aba que a enviou
  // (o postMessage não carrega o id da aba, só o titulo; quem sabe reconhecer
  // "quem" mandou é o contentWindow do próprio iframe).
  const iframeRefs = useRef<Map<string, HTMLIFrameElement>>(new Map());
  const path = usePathname();
  const subNav = useSubNav();
  // Rótulo da 1ª aba (a página real, sem iframe): página + sub-aba(s) atuais
  // — mesmo formato ("Página › Sub › Sub-sub") usado ao abrir uma aba nova em
  // duplo clique (ver Sidebar.tsx::SubNavItem), em vez do "Principal" fixo.
  const labelNativa = useMemo(() => {
    const base = rotuloDaPagina(path);
    const labels = subNav ? caminhoLabels(subNav.tree, subNav.activeId) : null;
    return labels ? [base, ...labels].join(" › ") : base;
  }, [path, subNav]);

  useEffect(() => {
    setDentroDeAba(estaDentroDeAba());
  }, []);

  useEffect(() => {
    if (dentroDeAba) return; // só a janela de cima escuta pedidos de abertura/título
    function aoReceberMensagem(e: MessageEvent) {
      if (e.origin !== window.location.origin) return;
      if (e.data?.tipo === MENSAGEM_ABRIR_ABA) {
        abrirAba(e.data.url as string, e.data.titulo as string);
        return;
      }
      if (e.data?.tipo === MENSAGEM_TITULO_ABA) {
        const novoTitulo = e.data.titulo as string;
        setAbas((atuais) => atuais.map((a) => {
          const el = iframeRefs.current.get(a.id);
          return el?.contentWindow === e.source && a.titulo !== novoTitulo ? { ...a, titulo: novoTitulo } : a;
        }));
      }
    }
    window.addEventListener("message", aoReceberMensagem);
    return () => window.removeEventListener("message", aoReceberMensagem);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dentroDeAba, abas.length]);

  // Repassa o próprio rótulo (página + sub-aba atuais) para a janela de cima
  // quando esta instância está rodando DENTRO de uma aba extra (iframe) — é o
  // que mantém o nome da aba em sincronia ao navegar lá dentro, em vez de
  // ficar congelado no título de quando a aba foi aberta.
  useEffect(() => {
    if (dentroDeAba) avisarTituloAba(labelNativa);
  }, [dentroDeAba, labelNativa]);

  // Título real da guia do navegador (não o rótulo da barra de abas interna)
  // — reflete a aba/painel em uso no momento: nativa ou uma das abas extras,
  // cujo título agora chega atualizado pela mensagem acima.
  useEffect(() => {
    if (dentroDeAba) return; // dentro de um iframe de aba não há guia própria do navegador
    const tituloAtivo = ativaId === "nativa" ? labelNativa : (abas.find((a) => a.id === ativaId)?.titulo ?? labelNativa);
    document.title = `${tituloAtivo} · Fazenda`;
  }, [dentroDeAba, ativaId, labelNativa, abas]);

  function abrirAba(url: string, titulo: string) {
    // Decide fora do updater do setAbas — nunca gerar o id nem chamar outro
    // setState (setAtivaId) de dentro da função passada a setAbas: em Strict
    // Mode (dev) o React invoca essa função duas vezes para detectar
    // impurezas, e como proximoId.current é uma ref mutável, cada chamada
    // gerava um id DIFERENTE ("aba-1" na 1ª, "aba-2" na 2ª) — o array de abas
    // ficava com um id e ativaId apontava pro outro, então nenhuma aba batia
    // no id === ativaId de estiloPainel() e o painel novo nunca aparecia
    // (display: none permanente, tela em branco na 2ª guia).
    const existente = abas.find((a) => a.url === url);
    if (existente) {
      setAtivaId(existente.id);
      return;
    }
    if (abas.length + 1 >= LIMITE_ABAS) {
      setAviso(`Limite de ${LIMITE_ABAS} abas atingido — feche alguma aba antes de abrir outra.`);
      return;
    }
    const id = `aba-${proximoId.current++}`;
    setAtivaId(id);
    setAbas((atuais) => [...atuais, { id, url, titulo }]);
  }

  function fecharAba(id: string) {
    setAbas((atuais) => atuais.filter((a) => a.id !== id));
    setAtivaId((atual) => (atual === id ? "nativa" : atual));
    setDivisao((atual) => (atual && atual.includes(id) ? null : atual));
  }

  function fecharMenu() {
    setMenu(null);
    setEscolhendoParceiro(false);
  }

  function abrirMenu(e: React.MouseEvent, id: string) {
    e.preventDefault();
    e.stopPropagation();
    setEscolhendoParceiro(false);
    setMenu({ id, x: e.clientX, y: e.clientY });
  }

  // Ainda não sabemos se estamos numa aba (1º render, antes do useEffect) —
  // repassa direto para nunca piscar/aninhar a barra por engano.
  if (dentroDeAba !== false) return <>{children}</>;

  const temAbasExtras = abas.length > 0;
  const todasAbas: { id: string; titulo: string }[] = [{ id: "nativa", titulo: labelNativa }, ...abas.map((a) => ({ id: a.id, titulo: a.titulo }))];

  // Posição/visibilidade de cada painel (a guia nativa ou um iframe) — sempre
  // montado, só escondido (display: none), tanto no modo normal (1 guia
  // visível) quanto no modo dividido (2 guias lado a lado).
  function estiloPainel(id: string): React.CSSProperties {
    const base: React.CSSProperties = { border: "none" };
    if (divisao) {
      // Modo dividido: 2 painéis lado a lado — aí sim precisa de position:
      // absolute (pra sobrepor um sobre o outro, escondendo os que não fazem
      // parte da divisão) com altura explícita (top:0 + height:100%, não só
      // top/bottom — iframe é elemento substituído e não calcula altura de
      // forma confiável só com top+bottom sem height).
      const idx = divisao.indexOf(id);
      if (idx === -1) return { ...base, display: "none" };
      return { ...base, display: "block", position: "absolute", top: 0, height: "100%", left: idx === 0 ? 0 : "50%", width: "50%", borderLeft: idx === 1 ? "1px solid var(--border)" : undefined };
    }
    // Modo normal: mesmo comportamento de sempre (width/height 100% do
    // container flex pai, sem position:absolute) — evita depender de
    // top/bottom pra calcular altura, que cortava o conteúdo de guias novas.
    return { ...base, display: id === ativaId ? "block" : "none", width: "100%", height: "100%" };
  }

  return (
    // A faixa de abas continua fixed (começando em left-56, mesma largura da
    // Sidebar, w-56, pra nunca cobrir o logotipo/menu — a Sidebar segue
    // intocada em y=0), mas agora o conteúdo NUNCA fica embaixo dela: o
    // espaçador abaixo reserva a mesma altura da faixa (2.2rem) só quando ela
    // aparece, empurrando o conteúdo pra baixo em vez de deixar a faixa
    // sobrepor o topo da página (título, "Configurações", "News" etc.).
    <div style={{ height: "100vh", position: "relative", display: "flex", flexDirection: "column" }}>
      {temAbasExtras && <div className="hidden md:block" style={{ height: "2.2rem", flexShrink: 0 }} aria-hidden="true" />}
      <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
        <div style={estiloPainel("nativa")}>
          {children}
        </div>
        {abas.map((aba) => (
          <iframe
            key={aba.id}
            ref={(el) => { if (el) iframeRefs.current.set(aba.id, el); else iframeRefs.current.delete(aba.id); }}
            src={aba.url}
            title={aba.titulo}
            style={estiloPainel(aba.id)}
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
            type="button" onClick={() => setAtivaId("nativa")} onContextMenu={(e) => abrirMenu(e, "nativa")}
            title={labelNativa}
            style={{
              display: "flex", alignItems: "center", gap: "0.35rem", padding: "0 0.9rem", border: "none",
              borderRight: "1px solid var(--border)",
              borderBottom: ativaId === "nativa" ? "2px solid var(--sidebar-active-border)" : "2px solid transparent",
              cursor: "pointer", fontSize: "0.76rem", fontWeight: 700,
              // Preenchimento na cor de "ativo" da paleta/tema atuais (mesma
              // variável usada no item ativo da Sidebar — já muda sozinha com
              // claro/misto/escuro e vinho/verde/azul), pra ficar óbvio qual
              // guia está em uso ao navegar entre elas.
              background: ativaId === "nativa" ? "var(--sidebar-active-bg)" : "transparent",
              color: ativaId === "nativa" ? "var(--sidebar-active-fg)" : "var(--text-muted)", whiteSpace: "nowrap",
              maxWidth: "12rem", overflow: "hidden", textOverflow: "ellipsis",
            }}
          >
            {labelNativa}
          </button>
          {abas.map((aba) => (
            <div
              key={aba.id}
              // Contorno na cor da paleta escolhida (var(--dourado) — muda com
              // vinho/verde/azul) em toda aba aberta por duplo clique, pra
              // diferenciar de cara da aba Principal e não confundir quando
              // há várias abertas. O preenchimento (var(--sidebar-active-bg)/
              // --sidebar-active-fg — mesmas variáveis do item ativo da
              // Sidebar, já sensíveis a tema e paleta) só aparece na guia em
              // uso, pra distinguir de cara qual está ativa ao navegar.
              style={{
                display: "flex", alignItems: "center", gap: "0.35rem", padding: "0 0.5rem 0 0.9rem",
                margin: "0.25rem 0.3rem", borderRadius: "6px",
                border: `1.5px solid ${ativaId === aba.id ? "var(--sidebar-active-border)" : "var(--dourado)"}`,
                cursor: "pointer", fontSize: "0.76rem", fontWeight: 700,
                background: ativaId === aba.id ? "var(--sidebar-active-bg)" : "transparent",
                color: ativaId === aba.id ? "var(--sidebar-active-fg)" : "var(--text-muted)", whiteSpace: "nowrap",
              }}
              onClick={() => setAtivaId(aba.id)}
              onContextMenu={(e) => abrirMenu(e, aba.id)}
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

      {menu && (
        <>
          <div onClick={fecharMenu} style={{ position: "fixed", inset: 0, zIndex: 70 }} />
          <div
            style={{
              position: "fixed", top: menu.y, left: menu.x, zIndex: 71, minWidth: "13rem",
              background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px",
              boxShadow: "0 4px 16px rgba(0,0,0,0.25)", padding: "0.3rem",
            }}
          >
            {!escolhendoParceiro ? (
              <>
                <button type="button" style={{ ...itemMenu, opacity: menu.id === "nativa" ? 0.4 : 1, cursor: menu.id === "nativa" ? "not-allowed" : "pointer" }}
                  disabled={menu.id === "nativa"}
                  title={menu.id === "nativa" ? "A guia principal não pode ser fechada" : undefined}
                  onClick={() => { fecharAba(menu.id); fecharMenu(); }}>
                  Fechar
                </button>
                <button type="button" style={{ ...itemMenu, opacity: abas.length === 0 ? 0.4 : 1, cursor: abas.length === 0 ? "not-allowed" : "pointer" }}
                  disabled={abas.length === 0}
                  title={abas.length === 0 ? "Abra outra guia antes de dividir a tela" : undefined}
                  onClick={() => setEscolhendoParceiro(true)}>
                  Dividir tela
                </button>
                <button type="button" style={{ ...itemMenu, opacity: divisao ? 1 : 0.4, cursor: divisao ? "pointer" : "not-allowed" }}
                  disabled={!divisao}
                  onClick={() => { setDivisao(null); fecharMenu(); }}>
                  Desfazer divisão de telas
                </button>
                <button type="button" style={itemMenu} onClick={fecharMenu}>Cancelar</button>
              </>
            ) : (
              <>
                <div style={{ padding: "0.3rem 0.7rem", color: "var(--text-muted)", fontSize: "0.7rem", fontWeight: 700, textTransform: "uppercase" }}>
                  Dividir com qual guia?
                </div>
                {todasAbas.filter((a) => a.id !== menu.id).map((a) => (
                  <button key={a.id} type="button" style={itemMenu}
                    onClick={() => { setDivisao([menu.id, a.id]); setAtivaId(menu.id); fecharMenu(); }}>
                    {a.titulo}
                  </button>
                ))}
                <button type="button" style={itemMenu} onClick={fecharMenu}>Cancelar</button>
              </>
            )}
          </div>
        </>
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
