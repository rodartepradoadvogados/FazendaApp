"use client";
import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Settings, Trash2, X } from "lucide-react";
import { fetchAgendaReprodutivaCard, fetchLotes, type CardAgendaReprodutivaConfig, type ItemCardAgendaReprodutiva, type SituacaoCard } from "@/lib/api";
import { GrupoLotePicker } from "@/components/GrupoLotePicker";

type CardDef = { id: string; nome: string; config: CardAgendaReprodutivaConfig };

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

function cardsPadrao(): CardDef[] {
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

function carregarCards(): CardDef[] {
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

function TabelaResultado({ itens }: { itens: ItemCardAgendaReprodutiva[] }) {
  const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
  if (itens.length === 0) return <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", padding: "0.5rem 0" }}>Nenhum animal nesta combinação.</p>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="table-clean" style={{ fontSize: "0.8rem" }}>
        <thead>
          <tr>
            <th>Matriz</th><th>Categoria</th><th>Lote</th><th>DEL</th><th>Dias gestação</th><th>Dias desde serviço</th><th>Parto previsto</th>
          </tr>
        </thead>
        <tbody>
          {itens.map((it) => (
            <tr key={it.numero_matriz}>
              <td>{it.numero_matriz}</td><td>{it.categoria ?? "—"}</td><td>{it.lote_atual ?? "—"}</td>
              <td>{it.del_dias ?? "—"}</td><td>{it.dias_gestacao ?? "—"}</td><td>{it.dias_desde_servico ?? "—"}</td>
              <td>{fmtDia(it.parto_previsto)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Cards 100% configuráveis da Agenda Reprodutiva — vivem ao lado das listas
 * fixas (que continuam com as ações de reconfirmação/toque/lançar, não
 * reproduzidas aqui). Definição de cada card fica em localStorage (por
 * navegador) — sem persistência no servidor nesta primeira entrega. */
export function CardsAgendaReprodutivaConfiguraveis({ dataRef }: { dataRef?: string }) {
  const [cards, setCards] = useState<CardDef[]>(carregarCards);
  const [opcoesLote, setOpcoesLote] = useState<string[]>([]);
  const [contagens, setContagens] = useState<Record<string, number>>({});
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const [itensAbertos, setItensAbertos] = useState<Record<string, ItemCardAgendaReprodutiva[]>>({});
  const [editando, setEditando] = useState<string | null | "novo">(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchLotes().then((lotes: any[]) => setOpcoesLote(lotes.map((l) => `${l.codigo} - ${l.nome}`))).catch(() => {});
  }, []);

  useEffect(() => {
    try { window.localStorage.setItem(CHAVE_STORAGE, JSON.stringify(cards)); } catch { /* storage indisponível — não impede o uso da tela */ }
  }, [cards]);

  useEffect(() => {
    let cancelado = false;
    setErro(null);
    Promise.all(cards.map((c) =>
      fetchAgendaReprodutivaCard(c.config, dataRef).then((r) => [c.id, r.total] as const).catch(() => [c.id, null] as const),
    )).then((pares) => {
      if (cancelado) return;
      const novo: Record<string, number> = {};
      let algumErro = false;
      for (const [id, total] of pares) { if (total === null) algumErro = true; else novo[id] = total; }
      setContagens(novo);
      if (algumErro) setErro("Alguns cards não puderam ser calculados agora.");
    });
    return () => { cancelado = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cards, dataRef]);

  const toggle = (id: string) => {
    setAbertos((s) => {
      const n = new Set(s);
      if (n.has(id)) { n.delete(id); } else {
        n.add(id);
        const card = cards.find((c) => c.id === id);
        if (card) fetchAgendaReprodutivaCard(card.config, dataRef).then((r) => setItensAbertos((v) => ({ ...v, [id]: r.itens }))).catch(() => {});
      }
      return n;
    });
  };

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
          return (
            <div key={c.id} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", background: "var(--surface-2)" }}>
              <div className="flex items-center gap-2" style={{ padding: "0.4rem 0.6rem" }}>
                <button onClick={() => toggle(c.id)} className="flex items-center gap-2" style={{ background: "transparent", border: "none", color: "var(--text)", cursor: "pointer", fontSize: "0.82rem" }}>
                  {aberto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  <span style={{ fontWeight: 700 }}>{n ?? "…"}</span> {c.nome}
                </button>
                <button onClick={() => setEditando(c.id)} title="Editar card" style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><Settings size={13} /></button>
                <button onClick={() => removerCard(c.id)} title="Remover card" style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><Trash2 size={13} /></button>
              </div>
              {aberto && (
                <div style={{ borderTop: "1px solid var(--border)", padding: "0.5rem 0.6rem" }}>
                  <TabelaResultado itens={itensAbertos[c.id] ?? []} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
