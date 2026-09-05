"use client";
// Cards 100% configuráveis da Agenda Reprodutiva, no app móvel — o MESMO
// motor do site (useCardsAgendaReprodutivaConfiguraveis, POST
// /agenda-reprodutiva/card, ver components/CardsAgendaReprodutivaConfiguraveis.tsx
// e fazenda.rules.agenda_reprodutiva_configuravel), só que em layout mobile:
// cada card é um <details> recolhível (mesmo padrão visual das listas fixas
// de AgendaVet.tsx), com nome + contagem no resumo e editar/remover como
// ícones à direita; "+ Novo card" abre uma gaveta inferior (MobGaveta) com o
// mesmo formulário do site (categoria/lote/situação/período/atrasadas),
// empilhado em vez de lado a lado. Antes desta tela, o app só tinha a busca
// avulsa "Buscar por parâmetro" (que continua existindo, ver
// FiltroAgendaReprodutiva.tsx) — sem forma de SALVAR uma combinação como
// card reaproveitável, e sem o padrão de card múltiplo do site (#570/#591 só
// levaram a capacidade de buscar, não a de configurar cards fixos). Cards
// ficam salvos em localStorage (mesma chave do site — useCardsAgendaReprodutivaConfiguraveis),
// então o conjunto configurado é por navegador/instalação, não por servidor.
import { useState } from "react";
import { ChevronRight, Plus, Settings, Trash2, X } from "lucide-react";
import {
  useCardsAgendaReprodutivaConfiguraveis,
  type CardsAgendaReprodutivaConfiguraveisState,
} from "@/components/CardsAgendaReprodutivaConfiguraveis";
import { formatDate } from "@/lib/api";
import type { CardAgendaReprodutivaConfig, ItemCardAgendaReprodutiva, SituacaoCard } from "@/lib/api";
import { MobGaveta, MobCampo } from "@/components/mobile/ui";
import { NumAnimal } from "@/components/mobile/menu/comum";
import { GrupoLotePicker } from "@/components/GrupoLotePicker";

// Mesmas opções/rótulos do site (ver CardsAgendaReprodutivaConfiguraveis.tsx
// e FiltroAgendaReprodutiva.tsx) — duplicado de propósito, seguindo o mesmo
// padrão já usado entre aquelas duas telas, em vez de criar uma dependência
// cruzada só por causa de uma constante pequena.
const SITUACOES: { valor: SituacaoCard; rotulo: string }[] = [
  { valor: "pev", rotulo: "PEV" },
  { valor: "inseminada", rotulo: "Inseminadas" },
  { valor: "gestante", rotulo: "Gestantes" },
  { valor: "vazia", rotulo: "Vazias" },
  { valor: "vazia_atrasada", rotulo: "Vazias atrasadas" },
  { valor: "a_descartar", rotulo: "A descartar" },
];

// Cor por situação (05/09/2026, "selo sólido + espinha") — mesmo vocabulário
// de cor das 10 listas fixas de AgendaVet.tsx e de Rebanho > Lotes, pra um
// card configurado pelo usuário (ex.: "Vazias do Lote 3") pintar igual à
// lista fixa equivalente, não uma cor à parte.
const COR_SITUACAO: Record<SituacaoCard, string> = {
  pev: "var(--mob-amarelo)", inseminada: "var(--mob-dourado)", gestante: "var(--mob-azul)",
  vazia: "var(--mob-verde)", vazia_atrasada: "var(--mob-vinho)", a_descartar: "var(--mob-laranja)",
};

const EIXO_DIAS_POR_SITUACAO: Record<SituacaoCard, string | null> = {
  pev: "dias desde o parto",
  inseminada: "dias desde a última inseminação",
  gestante: "dias de gestação",
  vazia: null,
  vazia_atrasada: null,
  a_descartar: null,
};

function detalheItem(situacao: SituacaoCard, it: ItemCardAgendaReprodutiva): string {
  const partes: string[] = [];
  if (it.lote_atual) partes.push(it.lote_atual);
  if (situacao === "pev" && it.del_dias != null) partes.push(`${it.del_dias} dias desde o parto`);
  if (situacao === "inseminada" && it.dias_desde_servico != null) partes.push(`${it.dias_desde_servico} dias inseminada`);
  if (situacao === "gestante" && it.dias_gestacao != null) partes.push(`${it.dias_gestacao} dias de gestação`);
  if (it.parto_previsto) partes.push(`parto previsto ${formatDate(it.parto_previsto)}`);
  return partes.join(" · ") || "—";
}

const linhaEstilo: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: "0.5rem", width: "100%", padding: "0.5rem 0",
  borderBottom: "1px solid var(--mob-border)", background: "none", border: "none",
  cursor: "pointer", color: "inherit", textAlign: "left", font: "inherit",
};

const configVazia = (): CardAgendaReprodutivaConfig => ({
  categoria: "todas", lotes: [], situacao: "vazia", periodos: [], somente_atrasadas: false, exceto_atrasadas: false,
});

/** Painel "de/até" com chips dos períodos já adicionados — mesma ideia de
 * PainelPeriodos (site), com toque maior e empilhado em vez de inline. */
function PainelPeriodosMobile({ periodos, onChange }: { periodos: [number, number][]; onChange: (v: [number, number][]) => void }) {
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const adicionar = () => {
    const d = Number(de), a = Number(ate);
    if (!Number.isFinite(d) || !Number.isFinite(a) || d > a) return;
    onChange([...periodos, [d, a]]);
    setDe(""); setAte("");
  };
  return (
    <div>
      {periodos.length > 0 && (
        <div className="flex items-center gap-2 mb-2" style={{ flexWrap: "wrap" }}>
          {periodos.map((p, i) => (
            <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", borderRadius: 999, padding: "0.3rem 0.7rem", fontSize: "0.82rem" }}>
              {p[0]} a {p[1]}
              <X size={13} style={{ cursor: "pointer" }} onClick={() => onChange(periodos.filter((_, j) => j !== i))} />
            </span>
          ))}
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <input type="number" inputMode="numeric" className="mob-input" placeholder="de" value={de} onChange={(e) => setDe(e.target.value)} />
        <span style={{ color: "var(--mob-muted)", fontSize: "0.85rem", flexShrink: 0 }}>a</span>
        <input type="number" inputMode="numeric" className="mob-input" placeholder="até" value={ate} onChange={(e) => setAte(e.target.value)} />
      </div>
      <button type="button" onClick={adicionar} className="mob-btn-2" style={{ marginTop: "0.5rem", minHeight: 44 }}>
        <Plus size={15} /> Adicionar período
      </button>
    </div>
  );
}

/** Gaveta inferior de criar/editar card — mesmos campos de PainelEdicao
 * (site), um embaixo do outro. */
function GavetaEdicao({
  aberto, cardId, nomeInicial, configInicial, opcoesLote, onSalvar, onFechar,
}: {
  aberto: boolean; cardId: string | null; nomeInicial: string; configInicial: CardAgendaReprodutivaConfig; opcoesLote: string[];
  onSalvar: (nome: string, config: CardAgendaReprodutivaConfig) => void; onFechar: () => void;
}) {
  const [nome, setNome] = useState(nomeInicial);
  const [config, setConfig] = useState<CardAgendaReprodutivaConfig>(configInicial);

  // Reabrir a gaveta (novo card ou editar outro card) parte sempre do valor
  // recebido — sem isto, o formulário ficaria "preso" no que foi editado da
  // última vez que a gaveta abriu.
  const [ultimoAberto, setUltimoAberto] = useState(false);
  if (aberto && !ultimoAberto) {
    setUltimoAberto(true);
    if (nome !== nomeInicial) setNome(nomeInicial);
    if (config !== configInicial) setConfig(configInicial);
  } else if (!aberto && ultimoAberto) {
    setUltimoAberto(false);
  }

  const eixo = EIXO_DIAS_POR_SITUACAO[config.situacao];

  return (
    <MobGaveta aberto={aberto} titulo={cardId ? "Editar card" : "Novo card"} onFechar={onFechar}>
      <MobCampo label="Nome do card">
        <input className="mob-input" value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Nome do card" />
      </MobCampo>

      <MobCampo label="Categoria">
        <select className="mob-input" value={config.categoria} onChange={(e) => setConfig({ ...config, categoria: e.target.value as any })}>
          <option value="todas">Todas</option>
          <option value="vaca">Vaca</option>
          <option value="novilha">Novilha</option>
        </select>
      </MobCampo>

      <MobCampo label="Lote">
        <GrupoLotePicker label="Lote" opcoes={opcoesLote} selecionados={config.lotes} onChange={(v) => setConfig({ ...config, lotes: v })} />
      </MobCampo>

      <MobCampo label="Situação reprodutiva">
        <select className="mob-input" value={config.situacao}
          onChange={(e) => setConfig({ ...config, situacao: e.target.value as SituacaoCard, periodos: [], somente_atrasadas: false, exceto_atrasadas: false })}>
          {SITUACOES.map((s) => <option key={s.valor} value={s.valor}>{s.rotulo}</option>)}
        </select>
      </MobCampo>

      {eixo && (
        <MobCampo label={`Períodos (${eixo}) — vazio mostra todos`}>
          <PainelPeriodosMobile periodos={config.periodos} onChange={(v) => setConfig({ ...config, periodos: v })} />
        </MobCampo>
      )}

      {config.situacao === "vazia" && (
        <div className="flex items-center gap-4 mb-3" style={{ fontSize: "0.85rem" }}>
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
        <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginBottom: "0.8rem" }}>Atalho de "Vazias" com "somente atrasadas" já marcado — sem sub-filtro próprio.</p>
      )}
      {config.situacao === "a_descartar" && (
        <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginBottom: "0.8rem" }}>Sem sub-filtro — traz quem está marcado "A descartar" (Rebanho).</p>
      )}

      <button type="button" className="mob-btn" onClick={() => onSalvar(nome.trim() || "Card sem nome", config)}>
        Salvar card
      </button>
    </MobGaveta>
  );
}

export function CardsAgendaReprodutivaMobile({ onFichaAberta }: { onFichaAberta: (numero: string) => void }) {
  const estado: CardsAgendaReprodutivaConfiguraveisState = useCardsAgendaReprodutivaConfiguraveis();
  const { cards, opcoesLote, contagens, abertos, itensAbertos, editando, erro, setEditando, toggle, salvarCard, removerCard, cardEditando } = estado;

  return (
    <div className="mb-2">
      <div className="flex items-center justify-between mb-2">
        <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Cards configuráveis</span>
        <button type="button" onClick={() => setEditando("novo")} className="mob-btn-2" style={{ width: "auto", minHeight: 44, padding: "0.5rem 0.9rem" }}>
          <Plus size={15} /> Novo card
        </button>
      </div>
      {erro && <p style={{ fontSize: "0.8rem", color: "var(--mob-vermelho)", marginBottom: "0.5rem" }}>{erro}</p>}

      {cards.map((c) => {
        const n = contagens[c.id];
        const aberto = abertos.has(c.id);
        const itens = itensAbertos[c.id] ?? [];
        const cor = COR_SITUACAO[c.config.situacao];
        return (
          <details key={c.id} className="mob-card mob-tint" style={{ ["--tint-cor" as any]: cor, padding: "0.4rem 0.9rem", marginBottom: "0.6rem" }}
            open={aberto} onToggle={(e) => { if ((e.target as HTMLDetailsElement).open !== aberto) toggle(c.id); }}>
            <summary style={{ display: "flex", alignItems: "center", gap: "0.6rem", cursor: "pointer", padding: "0.55rem 0", listStyle: "none" }}>
              <span style={{ flex: 1, minWidth: 0, fontWeight: 700, fontSize: "0.95rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                <span style={{
                  fontSize: "0.78rem", fontWeight: 800, padding: "0.15rem 0.55rem", borderRadius: 999, marginRight: "0.5rem",
                  color: cor, background: `color-mix(in srgb, ${cor} 16%, transparent)`, border: `1px solid color-mix(in srgb, ${cor} 40%, transparent)`,
                }}>
                  {n ?? "…"}
                </span>
                {c.nome}
              </span>
              <button type="button" title="Editar card" onClick={(e) => { e.preventDefault(); e.stopPropagation(); setEditando(c.id); }}
                style={{ background: "transparent", border: "none", color: "var(--mob-muted)", cursor: "pointer", padding: "0.3rem" }}>
                <Settings size={17} />
              </button>
              <button type="button" title="Remover card" onClick={(e) => { e.preventDefault(); e.stopPropagation(); removerCard(c.id); }}
                style={{ background: "transparent", border: "none", color: "var(--mob-muted)", cursor: "pointer", padding: "0.3rem" }}>
                <Trash2 size={17} />
              </button>
            </summary>
            <div style={{ borderTop: "1px solid var(--mob-border)", paddingTop: "0.4rem" }}>
              {itens.length === 0 ? (
                <p style={{ fontSize: "0.85rem", color: "var(--mob-muted)", padding: "0.5rem 0" }}>Nenhum animal nesta combinação.</p>
              ) : (
                itens.map((it) => (
                  <button key={it.numero_matriz} type="button" onClick={() => onFichaAberta(it.numero_matriz)} style={linhaEstilo}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <NumAnimal>Nº {it.numero_matriz}</NumAnimal>
                      <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>{detalheItem(c.config.situacao, it)}</div>
                    </div>
                    <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
                  </button>
                ))
              )}
            </div>
          </details>
        );
      })}

      <GavetaEdicao
        aberto={editando !== null}
        cardId={editando === "novo" ? null : editando}
        nomeInicial={cardEditando?.nome ?? ""}
        configInicial={cardEditando?.config ?? configVazia()}
        opcoesLote={opcoesLote}
        onSalvar={salvarCard}
        onFechar={() => setEditando(null)}
      />
    </div>
  );
}
