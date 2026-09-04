"use client";
// MODO CURRAL — tela nova do redesign (T6), pensada para o momento em que o
// aparelho está sendo usado DENTRO do curral: sol forte, uma mão só (a outra
// segura o animal/a corda), possivelmente com luva. Não é uma tela a mais
// entre várias, é uma visão DELIBERADAMENTE mais simples e maior que o resto
// do app:
//   - "Fazer agora": um quadrado grande e único — maior que qualquer outro
//     bloco da tela — que ABRE numa sub-tela a lista de tarefas de hoje (e
//     atrasadas) da Agenda, em cartões bem maiores, com o mínimo de texto e o
//     alvo de toque do check MAIOR que o piso geral de 56px do app (72px
//     aqui). O quadrado nunca precisa ser aberto pra dizer o que importa: um
//     contador ("N pendências hoje" / "Tudo em dia") e, se houver algo
//     atrasado, um acento --mob-vermelho — é o sinal que mais pesa pra quem
//     está no curral decidir se toca ali primeiro. Antes essa lista ficava
//     sempre aberta na tela principal; virou sub-tela porque competia direto
//     com "Lançar rápido" por espaço e transformava a tela num scroll único.
//   - "Lançar rápido": 3 quadrados coloridos por módulo (Reprodução/Produção/
//     Sanitário — mesmos 3 já priorizados em Lançar, ver
//     components/mobile/lancar/LancarTela.tsx, blocos "grande"), cada um
//     restrito às opções de maior frequência de uso real do curral (o
//     formulário completo, com todas as sub-opções, continua em Lançar).
//
// Deliberadamente NÃO reimplementa aqui os fluxos ricos de confirmação da
// Agenda completa (protocolo em lote, "qual frasco?", dar baixa com
// dose/veterinário etc.) — isso duplicaria uma lógica grande e delicada
// (estoque, backend) fora do lugar que já a mantém corretamente. Uma
// pendência que exige esses passos aparece aqui do mesmo jeito (nada
// escondido), só que o toque nela leva para a Agenda completa em vez de um
// check direto — ver `ehSimples`, abaixo.
import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Sun, Check, ChevronRight, Heart, Milk, ShieldPlus, ListChecks, CheckCircle2 } from "lucide-react";
import { MobVoltar, corCategoria, iconeCategoria } from "@/components/mobile/ui";
import { fetchAgenda, today, fetchAnimais } from "@/lib/api";
import { fetchComCache, enviarOuEnfileirar, useOnline } from "@/lib/offline";
import { useCache, type Animal } from "@/components/mobile/lancar/comum";
import { CurralSanitario } from "@/components/mobile/CurralSanitario";

const FormReprodutivo = dynamic(() => import("@/components/mobile/lancar/FormReprodutivo").then((m) => m.FormReprodutivo), { ssr: false });
const FormProducao = dynamic(() => import("@/components/mobile/lancar/FormProducao").then((m) => m.FormProducao), { ssr: false });

// Só os campos que esta tela realmente lê — o formato completo (com todos os
// campos de protocolo/cronograma/BST) vive em app/app/page.tsx (Agenda).
type Evento = {
  id: string; data: string; categoria: string; descricao: string;
  numero_animal?: string | null; lote?: string | null; observacao?: string | null;
  tipo?: string | null;
};
type Agenda = { eventos?: Evento[] };

// Tipos que exigem um painel de confirmação rico (dose, produto, veterinário,
// "lote ou individual" etc.) — ver app/app/page.tsx para o tratamento
// completo de cada um. Qualquer evento com um destes `tipo` some do toque
// direto aqui e vira "abrir na Agenda completa".
const TIPOS_COMPLEXOS = new Set([
  "protocolo_iatf", "protocolo_inducao", "protocolo_sanitario", "protocolo_customizado",
  "cronograma_sanitario_animal", "cronograma_sanitario_modo", "cronograma_sanitario_urgente", "cronograma_sanitario_aplicar",
  "bst_aplicacao", "sugestao_movimentacao", "colostragem_pendente", "igg_pendente",
  "evento_sanitario", "calendario_sanitario", "aplicacao_agendada",
  // Diária de diarista: 3 decisões (Confirmar/Meia diária/Não teve), não um
  // check único — o check simples marcaria "realizado" sem perguntar nada,
  // silenciosamente virando "dia cheio" sem o usuário escolher (ver o cartão
  // completo em app/app/page.tsx::renderCartao e decidirDiaria).
  "diaria_trabalho",
]);
function ehSimples(e: Evento): boolean {
  return !e.tipo || !TIPOS_COMPLEXOS.has(e.tipo);
}

function tituloEvento(e: Evento): string {
  if (e.numero_animal) return `Nº ${e.numero_animal}`;
  if (e.lote) return `Lote ${e.lote}`;
  return e.descricao;
}

type TelaRapida = "reprodutivo" | "producao" | "sanidade" | null;

function reduzirMovimento(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Um card da lista de "Fazer agora" — tap no check sempre funciona; em
 * cards `simples` (que têm o check), deslizar o card inteiro faz a mesma
 * coisa: pra direita conclui, pra esquerda só tira da vista por agora (ver
 * `ocultarPorAgora`, no componente pai — não é uma decisão salva em lugar
 * nenhum). O deslocamento é aplicado direto no DOM (`front.style.transform`)
 * em vez de guardar `dx` em estado — um `setState` por pixel arrastado
 * recriaria a lista inteira a cada frame do gesto. */
function CardCurral({ e, simples, atrasado, cor, Icon, transicao, onConcluir, onOcultar }: {
  e: Evento; simples: boolean; atrasado: boolean; cor: string; Icon: any;
  transicao?: "concluindo" | "saindo-d" | "saindo-e";
  onConcluir: () => void; onOcultar: () => void;
}) {
  const frontRef = useRef<HTMLDivElement | null>(null);
  const bgDRef = useRef<HTMLDivElement | null>(null);
  const bgERef = useRef<HTMLDivElement | null>(null);
  const arrasto = useRef<{ inicioX: number; largura: number } | null>(null);

  function aoPressionar(ev: ReactPointerEvent<HTMLDivElement>) {
    if (!simples || transicao || reduzirMovimento()) return;
    const front = frontRef.current;
    if (!front) return;
    arrasto.current = { inicioX: ev.clientX, largura: front.offsetWidth };
    front.setPointerCapture(ev.pointerId);
    front.style.transition = "none";
  }
  function aoMover(ev: ReactPointerEvent<HTMLDivElement>) {
    const front = frontRef.current;
    if (!arrasto.current || !front) return;
    const dx = ev.clientX - arrasto.current.inicioX;
    front.style.transform = `translateX(${dx}px)`;
    if (bgDRef.current) bgDRef.current.style.opacity = String(Math.min(1, Math.max(0, dx) / 90));
    if (bgERef.current) bgERef.current.style.opacity = String(Math.min(1, Math.max(0, -dx) / 90));
  }
  function aoSoltar(ev: ReactPointerEvent<HTMLDivElement>) {
    const front = frontRef.current;
    const estado = arrasto.current;
    if (!estado || !front) return;
    arrasto.current = null;
    const dx = ev.clientX - estado.inicioX;
    const limiar = estado.largura * 0.32;
    front.style.transition = "transform 0.22s cubic-bezier(0.2, 0.9, 0.3, 1.2)";
    if (dx > limiar) { front.style.transform = "translateX(140%)"; onConcluir(); }
    else if (dx < -limiar) { front.style.transform = "translateX(-140%)"; onOcultar(); }
    else {
      front.style.transform = "translateX(0)";
      if (bgDRef.current) bgDRef.current.style.opacity = "0";
      if (bgERef.current) bgERef.current.style.opacity = "0";
    }
  }

  return (
    <div className={"linha-colapsavel" + (transicao === "saindo-d" || transicao === "saindo-e" ? " linha-saindo" : "")}>
      <div style={{ position: "relative" }}>
        {simples && <div ref={bgDRef} className="curral-swipe-fundo curral-swipe-fundo-d" aria-hidden="true"><Check size={26} /></div>}
        {simples && <div ref={bgERef} className="curral-swipe-fundo curral-swipe-fundo-e" aria-hidden="true">Depois</div>}
        <div
          ref={frontRef}
          className={"curral-card" + (simples ? " curral-swipe-front" : "") + (transicao === "concluindo" ? " flash-sucesso" : "")}
          style={{ borderLeftColor: atrasado ? "var(--mob-vermelho)" : cor }}
          onPointerDown={aoPressionar} onPointerMove={aoMover} onPointerUp={aoSoltar} onPointerCancel={aoSoltar}
        >
          <span className="curral-card-icone" style={{ background: `color-mix(in srgb, ${cor} 18%, transparent)`, color: cor }}>
            <Icon size={26} />
          </span>
          <span className="curral-card-texto">
            <span className="curral-card-titulo">{tituloEvento(e)}</span>
            <span className="curral-card-sub">{e.descricao !== tituloEvento(e) ? e.descricao : (atrasado ? "Atrasado" : "Hoje")}</span>
          </span>
          {simples ? (
            <button type="button" className="curral-check" aria-label={`Concluir: ${tituloEvento(e)}`} onClick={onConcluir}>
              <Check size={30} strokeWidth={3} />
            </button>
          ) : (
            <Link href="/app" className="curral-abrir" aria-label="Abrir na Agenda completa" title="Precisa de mais informação — abrir na Agenda completa">
              <ChevronRight size={26} />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

export function ModoCurral({ onVoltar }: { onVoltar: () => void }) {
  const online = useOnline();
  const hoje = today();
  // MESMA chave de cache que a Agenda (app/app/page.tsx) usa — se a Agenda já
  // foi aberta hoje, o Modo Curral aproveita a cópia sem gastar uma requisição
  // extra; e o inverso também vale (o que este componente busca serve à
  // Agenda depois, se ela abrir primeiro fora de ordem).
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [carregando, setCarregando] = useState(true);
  useEffect(() => {
    let vivo = true;
    fetchComCache<Agenda>(`agenda_mob_${hoje}`, () => fetchAgenda(hoje))
      .then(({ dados }) => { if (vivo) { setAgenda(dados); setCarregando(false); } })
      .catch(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [hoje]);

  const [feitos, setFeitos] = useState<Set<string>>(new Set());
  const [erro, setErro] = useState<string | null>(null);
  const [fazerAberto, setFazerAberto] = useState(false);
  const [telaRapida, setTelaRapida] = useState<TelaRapida>(null);

  const animais = useCache<Animal[]>("animais", () => fetchAnimais() as Promise<Animal[]>, []);

  // Deslizar pra concluir/ocultar (04/09/2026) — `feitos` continua sendo o que
  // de fato tira o evento da lista (persistido/tentando persistir no
  // servidor, ver `concluir`); `ocultos` é só local e não persiste nada — é o
  // "pular por agora" de quem deslizou pra esquerda, some da sub-tela até ela
  // ser remontada. `transicoes` só existe pra segurar o item na tela um
  // instante a mais, tocando o flash verde/colapso, antes de cair em
  // `feitos`/`ocultos` de verdade.
  const [ocultos, setOcultos] = useState<Set<string>>(new Set());
  const [transicoes, setTransicoes] = useState<Record<string, "concluindo" | "saindo-d" | "saindo-e">>({});
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>[]>>({});
  useEffect(() => () => { Object.values(timersRef.current).flat().forEach(clearTimeout); }, []);

  const pendentesHoje = useMemo(() => {
    const evs = (agenda?.eventos || []).filter((e) => e.data <= hoje && !feitos.has(e.id) && !ocultos.has(e.id));
    // Atrasadas primeiro, hoje depois — mesmo critério da Agenda completa.
    return evs.sort((a, b) => (a.data < b.data ? -1 : a.data > b.data ? 1 : 0));
  }, [agenda, hoje, feitos, ocultos]);
  const temAtrasado = useMemo(() => pendentesHoje.some((e) => e.data < hoje), [pendentesHoje, hoje]);

  function limparTransicao(id: string) {
    (timersRef.current[id] || []).forEach(clearTimeout);
    delete timersRef.current[id];
    setTransicoes((p) => { const n = { ...p }; delete n[id]; return n; });
  }

  async function concluir(e: Evento) {
    setErro(null);
    setTransicoes((p) => ({ ...p, [e.id]: "concluindo" }));
    try { navigator.vibrate?.(20); } catch { /* sem suporte — segue sem vibrar */ }
    timersRef.current[e.id] = [
      setTimeout(() => setTransicoes((p) => ({ ...p, [e.id]: "saindo-d" })), 300),
      setTimeout(() => { setFeitos((p) => new Set(p).add(e.id)); limparTransicao(e.id); }, 560),
    ];
    try {
      await enviarOuEnfileirar("/agenda/realizados", { evento_id: e.id }, `Concluir: ${tituloEvento(e)}`, "POST");
    } catch (err) {
      limparTransicao(e.id);
      setErro(err instanceof Error ? err.message : "Não foi possível salvar.");
    }
  }

  // Não chama o backend — "pular" aqui é só deixar de olhar pra isso agora
  // (ver comentário de `ocultos` acima), não uma decisão registrada em lugar
  // nenhum. Reaparece na próxima vez que "Fazer agora" for aberto do zero.
  function ocultarPorAgora(id: string) {
    setTransicoes((p) => ({ ...p, [id]: "saindo-e" }));
    timersRef.current[id] = [
      setTimeout(() => { setOcultos((p) => new Set(p).add(id)); limparTransicao(id); }, 260),
    ];
  }

  // ── Fazer agora: sub-tela com a lista de pendências de hoje ─────────────
  if (fazerAberto) {
    return (
      <div className="curral-alvo">
        <MobVoltar titulo="Fazer agora" onVoltar={() => setFazerAberto(false)} />
        {erro && <div className="curral-aviso curral-aviso-erro">{erro}</div>}
        {carregando && <p style={{ color: "var(--mob-muted)", padding: "1rem 0" }}>Carregando…</p>}
        {!carregando && pendentesHoje.length === 0 && (
          <div className="curral-vazio">
            <Check size={30} />
            <p>Nada pendente para hoje. 🎉</p>
          </div>
        )}
        <div style={{ display: "grid", gap: "0.7rem" }}>
          {pendentesHoje.map((e) => (
            <CardCurral
              key={e.id} e={e} simples={ehSimples(e)} atrasado={e.data < hoje}
              cor={corCategoria(e.categoria)} Icon={iconeCategoria(e.categoria)}
              transicao={transicoes[e.id]}
              onConcluir={() => concluir(e)} onOcultar={() => ocultarPorAgora(e.id)}
            />
          ))}
        </div>
      </div>
    );
  }

  // ── Lançar rápido: sub-formulário aberto ────────────────────────────────
  if (telaRapida) {
    const titulos: Record<Exclude<TelaRapida, null>, string> = { reprodutivo: "Reprodução", producao: "Produção (leite)", sanidade: "Sanitário" };
    return (
      <div className="curral-alvo">
        <MobVoltar titulo={titulos[telaRapida]} onVoltar={() => setTelaRapida(null)} />
        {/* Reprodução/Produção: mesmo componente completo de Lançar, só que
            com `restringirA` filtrando a grade inicial para as opções de
            maior uso no curral — sem o prop, LancarTela.tsx continua vendo
            as 4/7 opções de sempre. Sanitário: FormSanidade.tsx não recebe
            esse prop (o onVoltar dele fica confuso de adaptar sem regredir o
            fluxo completo) — usa CurralSanitario, que pula direto pra
            Curativa (única modalidade aqui) e reaproveita CurativaForm. */}
        {telaRapida === "reprodutivo" && <FormReprodutivo animais={animais.dados} animalFixado={null} restringirA={["inseminacao", "parto"]} />}
        {telaRapida === "producao" && <FormProducao animais={animais.dados} animalFixado={null} restringirA={["controle", "pesagem", "secagem", "bst"]} />}
        {telaRapida === "sanidade" && <CurralSanitario animais={animais.dados} />}
      </div>
    );
  }

  const estadoFazer = carregando ? undefined : pendentesHoje.length === 0 ? "vazio" : temAtrasado ? "atrasado" : undefined;
  const IconeFazer = pendentesHoje.length === 0 && !carregando ? CheckCircle2 : ListChecks;

  return (
    <div className="curral-alvo">
      <MobVoltar titulo="Modo Curral" onVoltar={onVoltar} />

      <p style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-muted)", margin: "0 0 1rem" }}>
        <Sun size={16} /> Textos grandes, alto contraste — pensado para uso com luva e sol forte
      </p>

      {!online && (
        <div className="curral-aviso curral-aviso-offline">Sem conexão agora — os toques abaixo ficam guardados e são enviados sozinhos depois.</div>
      )}

      <div className="curral-secao">Fazer agora</div>
      <button type="button" className="curral-fazer" data-estado={estadoFazer} onClick={() => setFazerAberto(true)}>
        <span className="curral-fazer-icone">
          <IconeFazer size={30} />
        </span>
        <span className="curral-fazer-texto">
          <span className="curral-fazer-titulo">Fazer agora</span>
          <span className="curral-fazer-contador">
            {carregando
              ? "Carregando…"
              : pendentesHoje.length === 0
                ? "Tudo em dia"
                : `${pendentesHoje.length} pendência${pendentesHoje.length > 1 ? "s" : ""} hoje${temAtrasado ? " — tem atrasada" : ""}`}
          </span>
        </span>
        <ChevronRight size={22} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
      </button>

      <div className="curral-secao">Lançar rápido</div>
      <div className="curral-modulos-grid">
        <button type="button" className="curral-modulo" style={{ "--tint-cor": "var(--cat-reproducao)" } as CSSProperties} onClick={() => setTelaRapida("reprodutivo")}>
          <span className="curral-modulo-icone"><Heart size={26} /></span>
          Reprodução
        </button>
        <button type="button" className="curral-modulo" style={{ "--tint-cor": "var(--cat-producao)" } as CSSProperties} onClick={() => setTelaRapida("producao")}>
          <span className="curral-modulo-icone"><Milk size={26} /></span>
          Produção
        </button>
        <button type="button" className="curral-modulo" style={{ "--tint-cor": "var(--cat-sanidade)" } as CSSProperties} onClick={() => setTelaRapida("sanidade")}>
          <span className="curral-modulo-icone"><ShieldPlus size={26} /></span>
          Sanitário
        </button>
      </div>

      <Link href="/app/lancar" className="curral-mais">
        Ver todos os lançamentos <ChevronRight size={18} />
      </Link>
    </div>
  );
}
