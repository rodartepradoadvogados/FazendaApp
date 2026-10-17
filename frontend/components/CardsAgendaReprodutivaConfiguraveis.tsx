"use client";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Settings, Trash2, X } from "lucide-react";
import { fetchAgendaReprodutivaCards, fetchLotes, type CardAgendaReprodutivaConfig, type ItemCardAgendaReprodutiva, type ParametrosToque, type SituacaoCard } from "@/lib/api";
import { GrupoLotePicker } from "@/components/GrupoLotePicker";
import { CelulaExame, ChipFase, LegendaToque, SeloAindaNao } from "@/components/reproducao/FaseToque";
import { FASES, ROTULO_FASE_PLURAL, contarPorFase, filtrarPorFases, ordenarNoPrazoPrimeiro, seloBreve, type FaseToque } from "@/lib/fasesToque";

export type CardDef = { id: string; nome: string; config: CardAgendaReprodutivaConfig };

const CHAVE_STORAGE = "agendaReprodutivaCardsV1";

const SITUACOES: { valor: SituacaoCard; rotulo: string }[] = [
  { valor: "pev", rotulo: "PEV" },
  { valor: "inseminada", rotulo: "Inseminadas" },
  { valor: "gestante", rotulo: "Gestantes" },
  { valor: "vazia", rotulo: "Vazias" },
  { valor: "vazia_atrasada", rotulo: "Vazias atrasadas" },
  { valor: "a_descartar", rotulo: "A descartar" },
];

const EIXO_DIAS_POR_SITUACAO: Record<SituacaoCard, string | null> = {
  pev: "dias desde o parto",
  inseminada: "dias desde a última inseminação",
  gestante: "dias de gestação",
  vazia: null,
  vazia_atrasada: null,
  a_descartar: null,
};

export function cardsPadrao(): CardDef[] {
  const base = (situacao: SituacaoCard, periodos: [number, number][] = []): CardAgendaReprodutivaConfig => ({
    categoria: "todas", lotes: [], situacao, periodos, somente_atrasadas: false, exceto_atrasadas: false,
  });
  return [
    { id: "pev", nome: "PEV", config: base("pev") },
    { id: "insem-1-29", nome: "Inseminadas 1–29 dias", config: base("inseminada", [[1, 29]]) },
    { id: "insem-30-59", nome: "Inseminadas 30–59 dias", config: base("inseminada", [[30, 59]]) },
    { id: "insem-60-mais", nome: "Inseminadas 60+ dias", config: base("inseminada", [[60, 999]]) },
    { id: "gestantes", nome: "Gestantes", config: base("gestante") },
    { id: "vazias", nome: "Vazias", config: base("vazia") },
    { id: "vazias-atrasadas", nome: "Vazias atrasadas", config: base("vazia_atrasada") },
    { id: "a-descartar", nome: "A descartar", config: base("a_descartar") },
  ];
}

export function carregarCards(): CardDef[] {
  if (typeof window === "undefined") return cardsPadrao();
  try {
    const bruto = window.localStorage.getItem(CHAVE_STORAGE);
    if (!bruto) return cardsPadrao();
    const salvos = JSON.parse(bruto);
    if (Array.isArray(salvos) && salvos.length > 0) return salvos;
  } catch { /* ignora storage corrompido, cai no padrão */ }
  return cardsPadrao();
}

const selStyle: React.CSSProperties = {
  background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem",
};
const chipStyle: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: "0.35rem", background: "var(--surface)",
  border: "1px solid var(--border)", borderRadius: "999px", padding: "0.25rem 0.6rem", fontSize: "0.78rem",
};

function PainelPeriodos({ periodos, onChange }: { periodos: [number, number][]; onChange: (v: [number, number][]) => void }) {
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const adicionar = () => {
    const d = Number(de), a = Number(ate);
    if (!Number.isFinite(d) || !Number.isFinite(a) || d > a) return;
    onChange([...periodos, [d, a]]);
    setDe(""); setAte("");
  };
  return (
    <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
      {periodos.map((p, i) => (
        <span key={i} style={chipStyle}>
          {p[0]} a {p[1]}
          <X size={12} style={{ cursor: "pointer" }} onClick={() => onChange(periodos.filter((_, j) => j !== i))} />
        </span>
      ))}
      <input type="number" placeholder="de" value={de} onChange={(e) => setDe(e.target.value)} style={{ ...selStyle, width: "4.5rem" }} />
      <span style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>a</span>
      <input type="number" placeholder="até" value={ate} onChange={(e) => setAte(e.target.value)} style={{ ...selStyle, width: "4.5rem" }} />
      <button onClick={adicionar} style={{ ...selStyle, display: "flex", alignItems: "center", gap: "0.25rem", cursor: "pointer", color: "var(--dourado-light)", borderColor: "var(--dourado)" }}>
        <Plus size={13} /> adicionar período
      </button>
    </div>
  );
}

function PainelEdicao({
  cardId, nomeInicial, configInicial, opcoesLote, onSalvar, onCancelar,
}: {
  cardId: string | null; nomeInicial: string; configInicial: CardAgendaReprodutivaConfig; opcoesLote: string[];
  onSalvar: (nome: string, config: CardAgendaReprodutivaConfig) => void; onCancelar: () => void;
}) {
  const [nome, setNome] = useState(nomeInicial);
  const [config, setConfig] = useState<CardAgendaReprodutivaConfig>(configInicial);
  const eixo = EIXO_DIAS_POR_SITUACAO[config.situacao];

  return (
    <div className="card mb-3" style={{ padding: "0.9rem 1rem" }}>
      <div className="flex items-center justify-between mb-3">
        <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{cardId ? "Editar card" : "Novo card"}</span>
        <button onClick={onCancelar} title="Fechar" style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={16} /></button>
      </div>

      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        <input value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome do card"
          style={{ ...selStyle, minWidth: "12rem", flex: 1 }} />
      </div>

      <div className="flex items-start gap-3 mb-3" style={{ flexWrap: "wrap" }}>
        <div>
          <label style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "0.25rem" }}>Categoria</label>
          <select style={selStyle} value={config.categoria} onChange={(e) => setConfig({ ...config, categoria: e.target.value as any })}>
            <option value="todas">Todas</option>
            <option value="vaca">Vaca</option>
            <option value="novilha">Novilha</option>
          </select>
        </div>
        <div>
          <label style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "0.25rem" }}>Lote</label>
          <GrupoLotePicker label="Lote" opcoes={opcoesLote} selecionados={config.lotes} onChange={(v) => setConfig({ ...config, lotes: v })} />
        </div>
        <div>
          <label style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "0.25rem" }}>Situação reprodutiva</label>
          <select style={selStyle} value={config.situacao} onChange={(e) => setConfig({ ...config, situacao: e.target.value as SituacaoCard, periodos: [], somente_atrasadas: false, exceto_atrasadas: false })}>
            {SITUACOES.map((s) => <option key={s.valor} value={s.valor}>{s.rotulo}</option>)}
          </select>
        </div>
      </div>

      <div className="mb-3" style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.7rem 0.8rem" }}>
        {eixo && (
          <>
            <label style={{ display: "block", fontSize: "0.68rem", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: "0.4rem" }}>
              Períodos ({eixo}) — vazio mostra todos
            </label>
            <PainelPeriodos periodos={config.periodos} onChange={(v) => setConfig({ ...config, periodos: v })} />
          </>
        )}
        {config.situacao === "vazia" && (
          <div className="flex items-center gap-4" style={{ fontSize: "0.82rem" }}>
            <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
              <input type="checkbox" checked={config.somente_atrasadas}
                onChange={(e) => setConfig({ ...config, somente_atrasadas: e.target.checked, exceto_atrasadas: e.target.checked ? false : config.exceto_atrasadas })} />
              Somente atrasadas
            </label>
            <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
              <input type="checkbox" checked={config.exceto_atrasadas}
                onChange={(e) => setConfig({ ...config, exceto_atrasadas: e.target.checked, somente_atrasadas: e.target.checked ? false : config.somente_atrasadas })} />
              Exceto atrasadas
            </label>
          </div>
        )}
        {config.situacao === "vazia_atrasada" && (
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Atalho de "Vazias" com "somente atrasadas" já marcado — sem sub-filtro próprio.</p>
        )}
        {config.situacao === "a_descartar" && (
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Sem sub-filtro — traz quem está marcado "A descartar" (Rebanho).</p>
        )}
      </div>

      <button onClick={() => onSalvar(nome.trim() || "Card sem nome", config)} className="btn-primary" style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem" }}>
        Salvar card
      </button>
    </div>
  );
}

/** Tabela de resultado de um card configurável — usada na área de tabelas abertas (ver TabelasCardsConfiguraveis).
 * Estilo compacto (classe .tabela-compacta, ver app/globals.css) para caber numa coluna de ~50% da tela quando duas
 * tabelas estão lado a lado; cabeçalhos abreviados com o nome completo no atributo title.
 * Inseminadas e gestantes ganham as colunas Toque/confirmação e Retoque/reconfirmação (data + P/V/I, "–" se ainda não
 * houve) e a Situação (a tocar / a reconfirmar / reconfirmada, com o selo AINDA NÃO em ouro quando está no prazo). */
function TabelaResultado({ itens, situacao }: { itens: ItemCardAgendaReprodutiva[]; situacao: SituacaoCard }) {
  const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
  if (itens.length === 0) return <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", padding: "0.5rem 0" }}>Nenhum animal nesta combinação.</p>;
  const comExames = situacao === "inseminada" || situacao === "gestante";
  const gestante = situacao === "gestante";
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="tabela-compacta">
        <thead>
          <tr>
            <th scope="col">Matriz</th><th scope="col">Categoria</th><th scope="col">Lote</th><th scope="col">DEL</th>
            {gestante && <th scope="col" title="Dias de gestação">D. gest.</th>}
            <th scope="col" title="Dias desde o serviço">{comExames ? "Dias da IA" : "D. serviço"}</th>
            {gestante && <th scope="col" title="Parto previsto">Parto prev.</th>}
            {comExames && <th scope="col" title="Data e resultado do toque">Toque / confirmação</th>}
            {comExames && <th scope="col" title="Data e resultado do retoque">Retoque / reconfirmação</th>}
            {comExames && <th scope="col">Situação</th>}
          </tr>
        </thead>
        <tbody>
          {itens.map((it) => {
            const ainda = !!it.ainda_nao;
            const reconfirmado = !!it.data_reconfirmacao || !!it.diagnostico_reconfirmacao;
            const classe = ainda ? `ft-linha-ainda${seloBreve(it.dias_para_prazo) ? " ft-linha-breve" : ""}` : undefined;
            return (
              <tr key={it.numero_matriz} className={classe}>
                <td style={{ fontWeight: 700 }}>{it.numero_matriz}</td><td>{it.categoria ?? "—"}</td><td>{it.lote_atual ?? "—"}</td>
                <td>{it.del_dias ?? "—"}</td>
                {gestante && <td>{it.dias_gestacao ?? "—"}</td>}
                <td>{it.dias_desde_servico ?? "—"}</td>
                {gestante && <td>{fmtDia(it.parto_previsto)}</td>}
                {comExames && <td><CelulaExame data={it.data_diagnostico} diagnostico={it.diagnostico} /></td>}
                {comExames && <td>{reconfirmado ? <CelulaExame data={it.data_reconfirmacao} diagnostico={it.diagnostico_reconfirmacao} /> : <CelulaExame data={null} diagnostico={null} />}</td>}
                {comExames && (
                  <td style={{ whiteSpace: "nowrap" }}>
                    <ChipFase fase={it.fase} />{ainda && <SeloAindaNao dias={it.dias_para_prazo} prazoTipo={it.prazo_tipo} />}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Estado + lógica dos cards 100% configuráveis da Agenda Reprodutiva —
 * extraído em hook para poder ser controlado a partir de AgendaVeterinario.tsx
 * e alimentar dois pedaços de UI que ficam em lugares diferentes da página:
 * a grade de chips (GradeCardsConfiguraveis, perto do topo) e a área de
 * tabelas abertas (TabelasCardsConfiguraveis, depois de "Outras pendências").
 * Definição de cada card fica em localStorage (por navegador) — sem
 * persistência no servidor nesta primeira entrega. */
export function useCardsAgendaReprodutivaConfiguraveis(dataRef?: string) {
  const [cards, setCards] = useState<CardDef[]>(carregarCards);
  const [opcoesLote, setOpcoesLote] = useState<string[]>([]);
  const [itensPorCard, setItensPorCard] = useState<Record<string, ItemCardAgendaReprodutiva[]>>({});
  const [parametros, setParametros] = useState<ParametrosToque | null>(null);
  const [fases, setFases] = useState<Set<FaseToque>>(new Set());
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const [editando, setEditando] = useState<string | null | "novo">(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchLotes().then((lotes: any[]) => setOpcoesLote(lotes.map((l) => `${l.codigo} - ${l.nome}`))).catch(() => {});
  }, []);

  useEffect(() => {
    try { window.localStorage.setItem(CHAVE_STORAGE, JSON.stringify(cards)); } catch { /* storage indisponível — não impede o uso da tela */ }
  }, [cards]);

  // Um POST só para todos os cards: o servidor calcula o estado do rebanho uma vez. As tabelas e as contagens
  // saem dos mesmos itens, então o filtro de situação atualiza tudo ao vivo, sem nova chamada.
  useEffect(() => {
    let cancelado = false;
    setErro(null);
    if (cards.length === 0) { setItensPorCard({}); return; }
    fetchAgendaReprodutivaCards(cards.map((c) => ({ id: c.id, config: c.config })), dataRef)
      .then((r) => {
        if (cancelado) return;
        const novo: Record<string, ItemCardAgendaReprodutiva[]> = {};
        for (const c of cards) novo[c.id] = r.resultados[c.id]?.itens ?? [];
        setItensPorCard(novo);
        setParametros(r.parametros);
      })
      .catch(() => { if (!cancelado) setErro("Os cards não puderam ser calculados agora."); });
    return () => { cancelado = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, dataRef]);

  const toggle = (id: string) => {
    setAbertos((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  };

  const alternarFase = (f: FaseToque) => setFases((s) => { const n = new Set(s); if (n.has(f)) n.delete(f); else n.add(f); return n; });
  const limparFases = () => setFases(new Set());

  const salvarCard = (nome: string, config: CardAgendaReprodutivaConfig) => {
    if (editando === "novo") {
      const id = `card-${Date.now()}`;
      setCards((cs) => [...cs, { id, nome, config }]);
    } else if (editando) {
      setCards((cs) => cs.map((c) => (c.id === editando ? { ...c, nome, config } : c)));
    }
    setEditando(null);
  };

  const removerCard = (id: string) => {
    setCards((cs) => cs.filter((c) => c.id !== id));
    setAbertos((s) => { const n = new Set(s); n.delete(id); return n; });
  };

  const cardEditando = useMemo(() => {
    if (editando === "novo" || editando === null) return null;
    return cards.find((c) => c.id === editando) ?? null;
  }, [editando, cards]);

  // Com o filtro de situação ligado, contagens e tabelas mostram só quem está naquela(s) fase(s); no prazo primeiro.
  const itensAbertos = useMemo(() => {
    const r: Record<string, ItemCardAgendaReprodutiva[]> = {};
    for (const [id, itens] of Object.entries(itensPorCard)) r[id] = ordenarNoPrazoPrimeiro(filtrarPorFases(itens, fases));
    return r;
  }, [itensPorCard, fases]);
  const contagens = useMemo(() => {
    const r: Record<string, number> = {};
    for (const [id, itens] of Object.entries(itensAbertos)) r[id] = itens.length;
    return r;
  }, [itensAbertos]);
  const contagensFase = useMemo(() => contarPorFase(itensPorCard), [itensPorCard]);
  const filtroAtivo = fases.size > 0;

  return {
    cards, opcoesLote, contagens, abertos, itensAbertos, editando, erro, parametros,
    fases, filtroAtivo, contagensFase, alternarFase, limparFases,
    setEditando, toggle, salvarCard, removerCard, cardEditando,
  };
}

export type CardsAgendaReprodutivaConfiguraveisState = ReturnType<typeof useCardsAgendaReprodutivaConfiguraveis>;

/** Leitura simples dos cards configuráveis — mesma origem (localStorage,
 * `carregarCards`) e mesma busca de itens (`fetchAgendaReprodutivaCard`) do
 * hook acima, mas sem os estados de edição/criação de card nem o controle de
 * "tabela aberta": para telas que só precisam oferecer os cards já
 * configurados pelo usuário como opção de seleção (ex.: FormDiagnostico —
 * "Agenda do veterinário" — ver #comunicação entre Insights e Lançamentos).
 * Busca os itens de TODOS os cards de uma vez (não só ao abrir), porque aqui
 * o que importa é a lista de matrizes de cada card, não a tabela de detalhe.
 * `habilitado=false` evita a chamada ao backend enquanto a aba não estiver
 * em uso (mesmo padrão do fetchAgendaVeterinario sob demanda ao lado). */
export function useCardsAgendaReprodutivaLeitura(dataRef?: string, habilitado: boolean = true) {
  const [cards] = useState<CardDef[]>(carregarCards);
  const [itensPorCard, setItensPorCard] = useState<Record<string, ItemCardAgendaReprodutiva[]>>({});
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!habilitado || cards.length === 0) return;
    let cancelado = false;
    setCarregando(true);
    setErro(null);
    fetchAgendaReprodutivaCards(cards.map((c) => ({ id: c.id, config: c.config })), dataRef)
      .then((r) => {
        if (cancelado) return;
        const novo: Record<string, ItemCardAgendaReprodutiva[]> = {};
        for (const c of cards) novo[c.id] = r.resultados[c.id]?.itens ?? [];
        setItensPorCard(novo);
        setCarregando(false);
      })
      .catch(() => { if (!cancelado) { setErro("Os cards não puderam ser calculados agora."); setCarregando(false); } });
    return () => { cancelado = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataRef, habilitado]);

  return { cards, itensPorCard, carregando, erro };
}

/** Grade de chips clicáveis dos cards configuráveis + painéis de criar/editar
 * card. Fica perto do topo da página (onde a grade sempre viveu). A tabela
 * de resultado de cada card, quando aberta, NÃO renderiza mais aqui dentro —
 * ver TabelasCardsConfiguraveis, que fica depois de "Outras pendências" e
 * recebe o mesmo estado (state lifting: quem guarda `abertos`/`itensAbertos`
 * é o hook acima, chamado uma única vez em AgendaVeterinario.tsx). */
export function GradeCardsConfiguraveis({ estado }: { estado: CardsAgendaReprodutivaConfiguraveisState }) {
  const { cards, opcoesLote, contagens, abertos, editando, erro, filtroAtivo, setEditando, toggle, salvarCard, removerCard, cardEditando } = estado;
  const remover = (id: string, nome: string) => {
    if (window.confirm(`Remover o card "${nome}"? A configuração dele será perdida neste navegador.`)) removerCard(id);
  };

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>Cards configuráveis</span>
        <button onClick={() => setEditando("novo")} className="btn-primary" style={{ fontSize: "0.78rem", padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
          <Plus size={14} /> Novo card
        </button>
      </div>
      {erro && <p style={{ fontSize: "0.78rem", color: "var(--red)", marginBottom: "0.5rem" }}>{erro}</p>}

      {editando === "novo" && (
        <PainelEdicao cardId={null} nomeInicial="" configInicial={{ categoria: "todas", lotes: [], situacao: "vazia", periodos: [], somente_atrasadas: false, exceto_atrasadas: false }}
          opcoesLote={opcoesLote} onSalvar={salvarCard} onCancelar={() => setEditando(null)} />
      )}
      {cardEditando && (
        <PainelEdicao cardId={cardEditando.id} nomeInicial={cardEditando.nome} configInicial={cardEditando.config}
          opcoesLote={opcoesLote} onSalvar={salvarCard} onCancelar={() => setEditando(null)} />
      )}

      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        {cards.map((c) => {
          const n = contagens[c.id];
          const aberto = abertos.has(c.id);
          // Com o filtro de situação ligado, um card sem ninguém naquela situação fica esmaecido (não some da grade).
          const vazioNoFiltro = filtroAtivo && n === 0;
          return (
            <div key={c.id} className="flex items-center gap-2" title={vazioNoFiltro ? "Sem animais nesta situação" : undefined}
              style={{ border: "1px " + (vazioNoFiltro ? "dashed " : "solid ") + (aberto ? "var(--dourado)" : "var(--border)"), borderRadius: "var(--r-sm)", background: "var(--surface-2)", padding: "0.4rem 0.6rem", opacity: vazioNoFiltro ? 0.5 : 1 }}>
              <button onClick={() => toggle(c.id)} aria-expanded={aberto} className="flex items-center gap-2" style={{ background: "transparent", border: "none", color: "var(--text)", cursor: "pointer", fontSize: "0.82rem" }}>
                {aberto ? <ChevronDown size={14} aria-hidden="true" /> : <ChevronRight size={14} aria-hidden="true" />}
                <span style={{ fontWeight: 700 }}>{n ?? "…"}</span> {c.nome}
              </button>
              <button onClick={() => setEditando(c.id)} title="Editar card" aria-label={`Editar card ${c.nome}`} style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><Settings size={13} aria-hidden="true" /></button>
              <button onClick={() => remover(c.id, c.nome)} title="Remover card" aria-label={`Remover card ${c.nome}`} style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><Trash2 size={13} aria-hidden="true" /></button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Área com as tabelas dos cards configuráveis que estão abertos no momento
 * — renderizada depois de "Outras pendências" em AgendaVeterinario.tsx.
 * Com 2 ou mais tabelas abertas, elas dividem a largura lado a lado (grid de
 * 2 colunas, caindo para 1 coluna em telas estreitas via `lg:grid-cols-2`).
 * Decisão minha (avaliar): com só 1 tabela aberta, ela ocupa a largura toda
 * em vez de ficar numa grid de 2 colunas com metade vazia — pareceu mais
 * natural que deixar um buraco na tela; se abrirem 3+, a última tabela
 * "sobra" sozinha numa coluna na última linha (não dá span-2) para manter a
 * grade simples e regular. */
export function TabelasCardsConfiguraveis({ estado }: { estado: CardsAgendaReprodutivaConfiguraveisState }) {
  const { cards, abertos, itensAbertos, toggle, parametros } = estado;
  const cardsAbertos = cards.filter((c) => abertos.has(c.id));
  if (cardsAbertos.length === 0) return null;
  // Tabelas com Toque/Retoque/Situação são largas: uma por linha, para a Situação (e o selo AINDA NÃO) nunca ficar
  // atrás de rolagem horizontal. As demais (PEV, vazias…) continuam em duas colunas.
  const comExames = cardsAbertos.some((c) => c.config.situacao === "inseminada" || c.config.situacao === "gestante");

  return (
    <div className="mb-4">
      <div className={cardsAbertos.length > 1 && !comExames ? "grid grid-cols-1 lg:grid-cols-2 gap-3" : "flex flex-col gap-3"}>
        {cardsAbertos.map((c) => (
          <div key={c.id} className="card">
            <div className="flex items-center justify-between mb-2">
              <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{c.nome}</span>
              <button onClick={() => toggle(c.id)} title="Fechar tabela" style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={15} /></button>
            </div>
            <TabelaResultado itens={itensAbertos[c.id] ?? []} situacao={c.config.situacao} />
          </div>
        ))}
      </div>
      {comExames && <LegendaToque parametros={parametros} />}
    </div>
  );
}

/** Filtro de situação do diagnóstico — A tocar / A reconfirmar / Reconfirmadas. Multi-seleção; sem nenhuma escolhida
 * vale "todos". Fica entre a grade de cards e as tabelas: muda as contagens dos cards e o que as tabelas mostram, ao
 * vivo (os itens já vieram de uma chamada só). Os números dos botões contam animais, não linhas. */
export function FiltroSituacaoDiagnostico({ estado }: { estado: CardsAgendaReprodutivaConfiguraveisState }) {
  const { fases, filtroAtivo, contagensFase, alternarFase, limparFases, itensAbertos, abertos } = estado;
  const linhasVisiveis = Object.entries(itensAbertos).filter(([id]) => abertos.has(id)).reduce((a, [, itens]) => a + itens.length, 0);
  const listas = abertos.size;
  return (
    <div className="flex items-center gap-3 mb-3" style={{ flexWrap: "wrap", padding: "0.5rem 0", borderBottom: "1px solid var(--border)" }} data-testid="filtro-situacao-diagnostico">
      <span style={{ fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.13em", textTransform: "uppercase", color: "var(--text-muted)" }}>Situação</span>
      <div className="flex items-center gap-2" role="group" aria-label="Filtrar por situação do diagnóstico" style={{ flexWrap: "wrap" }}>
        {FASES.map((f) => (
          <button key={f} type="button" className="ft-pilula" aria-pressed={fases.has(f)} onClick={() => alternarFase(f)}>
            {ROTULO_FASE_PLURAL[f]}<b>{contagensFase[f]}</b>
          </button>
        ))}
      </div>
      {filtroAtivo && <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }} onClick={limparFases}>Limpar filtro</button>}
      <span style={{ marginLeft: "auto", fontSize: "0.8rem", color: "var(--text-muted)" }} aria-live="polite">
        {filtroAtivo
          ? `Mostrando ${linhasVisiveis} animais em ${listas} ${listas === 1 ? "lista aberta" : "listas abertas"}`
          : "Escolha uma situação para filtrar os cards e as tabelas"}
      </span>
    </div>
  );
}
