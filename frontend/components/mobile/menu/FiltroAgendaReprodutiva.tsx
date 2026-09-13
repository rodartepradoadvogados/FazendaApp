"use client";
// Filtro configurável da Agenda Reprodutiva, no app móvel — a mesma
// CAPACIDADE do site (frontend/app/reproducao/AgendaVeterinario.tsx +
// components/CardsAgendaReprodutivaConfiguraveis.tsx: escolher situação
// reprodutiva/período/categoria e ver os animais que casam com a combinação),
// só que sem a grade de edição de cards do desktop — aqui é um único
// formulário simples que devolve uma lista, no mesmo padrão visual
// (<details> recolhível) das 10 listas fixas de AgendaVet.tsx. Reaproveita o
// MESMO endpoint POST /agenda-reprodutiva/card (motor compartilhado com o
// site — ver fazenda.rules.agenda_reprodutiva_configuravel), sem "lote" nem
// múltiplos períodos por card: o zootecnista no curral quer uma pergunta de
// cada vez, não uma grade editável.
import { useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { fetchAgendaReprodutivaCard, formatDate } from "@/lib/api";
import type { CardAgendaReprodutivaConfig, ItemCardAgendaReprodutiva, SituacaoCard } from "@/lib/api";
import { MobCampo } from "@/components/mobile/ui";
import { NumAnimal } from "@/components/mobile/menu/comum";
import { useOrdenacao } from "@/components/Ordenavel";
import { SeletorOrdenacao, type CampoOrdenacao } from "@/components/mobile/SeletorOrdenacao";
import { ExportarBotoes } from "@/components/ExportarBotoes";

const SITUACOES: { valor: SituacaoCard; rotulo: string }[] = [
  { valor: "pev", rotulo: "PEV (período de espera voluntário)" },
  { valor: "inseminada", rotulo: "Inseminadas" },
  { valor: "gestante", rotulo: "Gestantes" },
  { valor: "vazia", rotulo: "Vazias" },
  { valor: "vazia_atrasada", rotulo: "Vazias atrasadas" },
  { valor: "a_descartar", rotulo: "A descartar" },
];

// Eixo do período (dias) muda conforme a situação — igual ao site (ver
// EIXO_DIAS_POR_SITUACAO em CardsAgendaReprodutivaConfiguraveis.tsx).
const EIXO_DIAS_POR_SITUACAO: Record<SituacaoCard, string | null> = {
  pev: "dias desde o parto",
  inseminada: "dias desde a última inseminação",
  gestante: "dias de gestação",
  vazia: null,
  vazia_atrasada: null,
  a_descartar: null,
};

const CAMPOS_ORDENACAO: CampoOrdenacao[] = [
  { chave: "numero_matriz", rotulo: "Matriz" },
  { chave: "del_dias", rotulo: "DEL" },
  { chave: "dias_gestacao", rotulo: "Dias gestação" },
  { chave: "dias_desde_servico", rotulo: "Dias inseminada" },
];

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

/**
 * Painel de busca por parâmetro — situação reprodutiva, categoria e período
 * (dias), com "somente/exceto atrasadas" quando a situação é "vazia". Fica
 * como um <details> a mais, no topo da Agenda Reprodutiva do app, antes das
 * 10 listas fixas. O resultado da busca aparece logo abaixo do formulário,
 * dentro do mesmo painel — sem grade, sem cards múltiplos lado a lado.
 */
export function FiltroAgendaReprodutiva({ onFichaAberta }: { onFichaAberta: (numero: string) => void }) {
  const [situacao, setSituacao] = useState<SituacaoCard>("pev");
  const [categoria, setCategoria] = useState<"todas" | "vaca" | "novilha">("todas");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [somenteAtrasadas, setSomenteAtrasadas] = useState(false);
  const [excetoAtrasadas, setExcetoAtrasadas] = useState(false);
  const [buscando, setBuscando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<{ situacao: SituacaoCard; itens: ItemCardAgendaReprodutiva[] } | null>(null);

  const eixo = EIXO_DIAS_POR_SITUACAO[situacao];
  const ord = useOrdenacao(resultado?.itens ?? []);
  const colunasExport = [
    { header: "Matriz", key: "numero_matriz" }, { header: "Categoria", key: "categoria" },
    { header: "Lote", key: "lote_atual" }, { header: "DEL", key: "del_dias" },
    { header: "Dias gestação", key: "dias_gestacao" }, { header: "Dias inseminada", key: "dias_desde_servico" },
    { header: "Parto previsto", key: "parto_previsto_fmt" },
  ];
  const linhasExport = ord.linhasOrdenadas.map((it) => ({ ...it, parto_previsto_fmt: it.parto_previsto ? formatDate(it.parto_previsto) : "—" }));

  function mudarSituacao(v: SituacaoCard) {
    setSituacao(v);
    setDe(""); setAte("");
    setSomenteAtrasadas(false); setExcetoAtrasadas(false);
  }

  async function buscar() {
    setBuscando(true); setErro(null);
    const periodos: [number, number][] = [];
    const d = Number(de), a = Number(ate);
    if (de.trim() !== "" && ate.trim() !== "" && Number.isFinite(d) && Number.isFinite(a) && d <= a) {
      periodos.push([d, a]);
    }
    const config: CardAgendaReprodutivaConfig = {
      categoria, lotes: [], situacao, periodos,
      somente_atrasadas: situacao === "vazia" && somenteAtrasadas,
      exceto_atrasadas: situacao === "vazia" && excetoAtrasadas,
    };
    try {
      const r = await fetchAgendaReprodutivaCard(config);
      setResultado({ situacao, itens: r.itens });
    } catch (e: any) {
      setErro(e.message); setResultado(null);
    } finally {
      setBuscando(false);
    }
  }

  return (
    <details className="mob-card" style={{ padding: "0.4rem 0.9rem", marginBottom: "0.6rem" }}>
      <summary style={{ display: "flex", alignItems: "center", gap: "0.6rem", cursor: "pointer", padding: "0.55rem 0", fontWeight: 700, fontSize: "0.95rem", listStyle: "none" }}>
        <Search size={17} />
        <span style={{ flex: 1, minWidth: 0 }}>Buscar por parâmetro</span>
      </summary>
      <div style={{ borderTop: "1px solid var(--mob-border)", paddingTop: "0.6rem" }}>
        <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.7rem" }}>
          Escolha uma situação reprodutiva e, se quiser, um período (em dias) e a categoria — mesmos parâmetros de aptidão do site.
        </p>

        <MobCampo label="Situação reprodutiva">
          <select className="mob-input" value={situacao} onChange={(e) => mudarSituacao(e.target.value as SituacaoCard)}>
            {SITUACOES.map((s) => <option key={s.valor} value={s.valor}>{s.rotulo}</option>)}
          </select>
        </MobCampo>

        <MobCampo label="Categoria">
          <select className="mob-input" value={categoria} onChange={(e) => setCategoria(e.target.value as any)}>
            <option value="todas">Todas</option>
            <option value="vaca">Vaca</option>
            <option value="novilha">Novilha</option>
          </select>
        </MobCampo>

        {eixo && (
          <MobCampo label={`Período (${eixo}) — vazio mostra todos`}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <input type="number" inputMode="numeric" className="mob-input" placeholder="de" value={de} onChange={(e) => setDe(e.target.value)} />
              <span style={{ color: "var(--mob-muted)", fontSize: "0.85rem", flexShrink: 0 }}>a</span>
              <input type="number" inputMode="numeric" className="mob-input" placeholder="até" value={ate} onChange={(e) => setAte(e.target.value)} />
            </div>
          </MobCampo>
        )}

        {situacao === "vazia" && (
          <div className="flex items-center gap-4 mb-3" style={{ fontSize: "0.85rem" }}>
            <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
              <input type="checkbox" checked={somenteAtrasadas}
                onChange={(e) => { setSomenteAtrasadas(e.target.checked); if (e.target.checked) setExcetoAtrasadas(false); }} />
              Somente atrasadas
            </label>
            <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
              <input type="checkbox" checked={excetoAtrasadas}
                onChange={(e) => { setExcetoAtrasadas(e.target.checked); if (e.target.checked) setSomenteAtrasadas(false); }} />
              Exceto atrasadas
            </label>
          </div>
        )}

        <button onClick={buscar} disabled={buscando}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem", width: "100%", border: "none",
            background: "var(--mob-dourado-2)", color: "var(--mob-acao-fg)", borderRadius: "var(--r-app)", padding: "0.7rem", fontWeight: 700, fontSize: "0.9rem" }}>
          <Search size={16} /> {buscando ? "Buscando…" : "Buscar animais"}
        </button>

        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}

        {resultado && (
          <div style={{ marginTop: "0.9rem", borderTop: "1px solid var(--mob-border)", paddingTop: "0.6rem" }}>
            <div className="flex items-center justify-between mb-2" style={{ gap: "0.6rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.88rem" }}>
                Resultado — {resultado.itens.length} {resultado.itens.length === 1 ? "animal" : "animais"}
              </span>
            </div>
            {resultado.itens.length === 0 ? (
              <p style={{ fontSize: "0.85rem", color: "var(--mob-muted)", padding: "0.5rem 0" }}>Nenhum animal nesta combinação.</p>
            ) : (
              <>
                <SeletorOrdenacao campos={CAMPOS_ORDENACAO} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
                <div className="flex items-center justify-end mb-2">
                  <ExportarBotoes titulo="Agenda Reprodutiva — Busca por parâmetro" colunas={colunasExport} linhas={linhasExport} nomeArquivoBase="agenda_reprodutiva_filtro" />
                </div>
                {ord.linhasOrdenadas.map((it) => (
                  <button key={it.numero_matriz} onClick={() => onFichaAberta(it.numero_matriz)} style={linhaEstilo}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <NumAnimal>Nº {it.numero_matriz}</NumAnimal>
                      <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>{detalheItem(resultado.situacao, it)}</div>
                    </div>
                    <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
                  </button>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </details>
  );
}
