"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Filter, Search, ChevronDown, ChevronRight, ChevronsDown, ChevronsUp, ArrowRightLeft, Sparkles, Skull, ShoppingCart, FileText, Dna, BarChart3 } from "lucide-react";
import { CowIcon } from "@/components/CowIcon";
import { IndicadoresGerais } from "@/app/indicadores/page";
import { fetchAnimais, fetchEstratificacaoRebanho, fetchEstadosReprodutivos, marcarADescartar, type Estratificacao, type EstadosReprodutivos, type EstadoReprodutivoAnimal } from "@/lib/api";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { AnimalModal, AnimalRow } from "@/components/AnimalModal";
import MovimentarAnimais from "@/components/MovimentarAnimais";
import SugestoesMovimentacao from "@/components/SugestoesMovimentacao";
import BaixarAnimal from "@/components/BaixarAnimal";
import FichaAnimal from "@/components/FichaAnimal";
import RebanhoTouros from "@/components/RebanhoTouros";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { MultiFiltro, Indicador, TelaSkeleton } from "@/components/ui";
import { GrupoLotePicker } from "@/components/GrupoLotePicker";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { casaBusca } from "@/lib/busca";
import { producaoDe, origemDe } from "@/lib/producaoAnimal";

const COLUNAS_REBANHO = [
  { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo_primario" },
  { header: "Categoria", key: "categoria" }, { header: "Raça", key: "raca" },
  { header: "Sit. Rep.", key: "sit_rep" }, { header: "DEL", key: "del_dias" },
  { header: "Últ. CL (kg)", key: "ult_cl_kg" }, { header: "Origem da produção", key: "origem_producao" },
];

type Animal = {
  numero: string; grupo_primario: string | null; categoria_abrev: string | null;
  categoria_completa: string | null; raca: string | null; sit_rep: string | null;
  del_dias: number | null;
  /** @deprecated Campo congelado do CSV do Ideagri — prefira `producao_kg`. */
  ult_cl_kg: number | null;
  diagnostico: string | null;
  // Produção AO VIVO (AnimalProducaoAoVivo, lib/api.ts) — cai para `ult_cl_kg`
  // enquanto o backend novo não estiver publicado.
  producao_kg?: number | null; producao_data?: string | null; producao_origem?: "controle" | "congelado" | null;
  a_descartar?: boolean; sexo?: string | null; observacoes?: string | null;
};


const SIT_CORES: Record<string, string> = {
  "Ges.": "var(--green-light)", "Vaz. apt.": "var(--blue)", "Vaz. atr.": "var(--red)",
  "Vaz. pev": "var(--amber)", "Ins.": "var(--dourado-light)",
  // Rótulos do estado reprodutivo AO VIVO (ver ROTULO_ESTADO) — somados aos
  // códigos antigos do CSV acima para não quebrar as cores já em uso.
  "Gestante": "var(--green-light)", "Inseminada": "var(--dourado-light)",
  "Em protocolo (IA atual)": "var(--vinho-light)", "PEV": "var(--amber)",
  "Apta": "var(--blue)", "Atrasada": "var(--red)", "Não apta": "#8A6a3a", "Vazia": "var(--text-muted)",
};
// Estado reprodutivo AO VIVO (GET /indicadores/estados-reprodutivos) — substitui
// o Animal.sit_rep congelado do último CSV importado. Ver EstadoReprodutivoAnimal em lib/api.ts.
const ROTULO_ESTADO: Record<string, string> = {
  gestante: "Gestante", inseminada: "Inseminada", em_protocolo: "Em protocolo (IA atual)",
  pev: "PEV", apta: "Apta", atrasada: "Atrasada", nao_apta: "Não apta", vazia: "Vazia",
};
// Cores do donut de Situação Reprodutiva — as mesmas 6 fatias e cores da Capa
// (app/page.tsx, SIT_CORES), à parte da paleta acima (que é por rótulo de
// estado ao vivo cru, usada nas tabelas desta página).
const SIT_CORES_DONUT: Record<string, string> = {
  Prenhes: "var(--green-light)", Inseminadas: "var(--dourado-light)",
  "Em protocolo": "var(--vinho-light, #416180)",
  PEV: "var(--amber)", "A inseminar": "var(--blue)", Vazias: "var(--red)",
};
// Rótulo do estado ao vivo de um animal a partir do mapa numero→estado — animal
// sem estado (ex.: macho) devolve undefined, que os chamadores tratam como "—".
function rotuloEstadoDoAnimal(numero: string, porNumero: Map<string, EstadoReprodutivoAnimal>): string | undefined {
  const e = porNumero.get(numero);
  return e ? ROTULO_ESTADO[e.estado] : undefined;
}
const LACTACAO = ["01", "02", "03"];
const cod = (g: string | null) => (g && g.length >= 2 && /\d\d/.test(g.slice(0, 2)) ? g.slice(0, 2) : null);

// Estratificação do rebanho por faixa etária + composição das vacas adultas,
// com o indicador de % de vacas em lactação sobre o total.
const ESTRATOS_ROTULO: [string, string, string][] = [
  ["aleitamento_0_3m", "Aleitamento (0–3 m)", "#C6A24A"],
  ["recria_4_11m", "Recria (4–11 m)", "#A9791F"],
  ["recria_12_24m", "Recria (12–24 m)", "#8A6a3a"],
  ["novilhas_acima_24m", "Novilhas (>24 m)", "#7C2740"],
  ["vacas_lactacao", "Vacas em lactação", "#4C7A3C"],
  ["vacas_secas", "Vacas secas", "#B47C1E"],
  ["vacas_pre_parto", "Vacas pré-parto", "#2E5A7C"],
];

function EstratificacaoRebanho({ animais }: { animais: Animal[] }) {
  const [d, setD] = useState<Estratificacao | null>(null);
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);
  useEffect(() => { fetchEstratificacaoRebanho().then(setD).catch(() => setD(null)); }, []);
  if (!d || !d.total) return null;

  const porNumero = new Map(animais.map((a) => [a.numero, a]));
  const listaDe = (numeros: string[] | undefined): AnimalRow[] =>
    (numeros || []).map((n) => porNumero.get(n)).filter((a): a is Animal => !!a);
  const abrir = (title: string, numeros: string[] | undefined) => setModal({ title, list: listaDe(numeros) });

  const dados = ESTRATOS_ROTULO
    .map(([k, label, cor]) => ({ k, label, cor, n: d.estratos[k] || 0, pct: d.percentuais[k] || 0 }))
    .filter((x) => x.n > 0);

  return (
    <div className="card mb-4">
      <div className="card-header mb-3 flex items-center gap-2"><CowIcon size={14} /> Composição do rebanho ({d.total} fêmeas)</div>
      {/* % de vacas em lactação já era o único KPI marcado em verde — vira
          métrica-âncora. Os outros 3 continuam, só menores, e todos seguem
          clicáveis (mesmas listas de animais de antes). */}
      <div style={{ padding: "0 0 .9rem", display: "flex", alignItems: "center", gap: "2rem", flexWrap: "wrap" }}>
        <div onClick={() => abrir("Vacas em lactação", d.numeros?.vacas_lactacao)} style={{ cursor: "pointer" }}>
          <div style={{ fontSize: ".68rem", fontWeight: 700, letterSpacing: ".13em", textTransform: "uppercase", color: "var(--text-muted)" }}>% de vacas em lactação</div>
          <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.6rem", fontWeight: 800, lineHeight: 1, color: "var(--green-light)", marginTop: ".25rem", fontVariantNumeric: "tabular-nums" }}>
            {d.pct_lactacao_sobre_vacas}%
          </div>
        </div>
        <div style={{ flex: 1, display: "flex", justifyContent: "flex-end", gap: "1.8rem", flexWrap: "wrap" }}>
          <div onClick={() => abrir("Vacas em lactação", d.numeros?.vacas_lactacao)} style={{ cursor: "pointer", textAlign: "right" }}>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{d.pct_lactacao_sobre_total}%</div>
            <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>% em relação ao rebanho</div>
          </div>
          <div onClick={() => abrir("Vacas em lactação", d.numeros?.vacas_lactacao)} style={{ cursor: "pointer", textAlign: "right" }}>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{d.estratos.vacas_lactacao}</div>
            <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>Vacas em lactação</div>
          </div>
          <div onClick={() => abrir("Vacas (adultas)", d.numeros_vacas_total)} style={{ cursor: "pointer", textAlign: "right" }}>
            <div style={{ fontSize: "1.1rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{d.vacas_total}</div>
            <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em" }}>Vacas (adultas)</div>
          </div>
        </div>
      </div>
      {/* Barra empilhada 100% — cada fatia clicável abre os animais daquela categoria */}
      <div style={{ display: "flex", height: 26, borderRadius: 8, overflow: "hidden", border: "1px solid var(--border)" }}>
        {dados.map((x) => (
          <div key={x.label} title={`${x.label}: ${x.n} (${x.pct}%) — clique para ver os animais`}
            style={{ width: `${x.pct}%`, background: x.cor, minWidth: x.pct > 0 ? 2 : 0, cursor: "pointer" }}
            onClick={() => abrir(x.label, d.numeros?.[x.k])} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2" style={{ fontSize: "0.74rem" }}>
        {dados.map((x) => (
          <span key={x.label} className="flex items-center gap-1" style={{ cursor: "pointer" }}
            title="Clique para ver os animais" onClick={() => abrir(x.label, d.numeros?.[x.k])}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: x.cor, display: "inline-block" }} /> {x.label}: <strong>{x.n}</strong> ({x.pct}%)
          </span>
        ))}
      </div>
      {(d.estratos as any).sem_data_nasc > 0 && (
        <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>{(d.estratos as any).sem_data_nasc} animal(is) sem data de nascimento não entraram nas faixas etárias.</p>
      )}
      {modal && <AnimalModal title={modal.title} animais={modal.list} onClose={() => setModal(null)} />}
    </div>
  );
}

// Caixa de animais marcados "A descartar" (Animal.a_descartar=true): seguem
// ativos no rebanho, mas fora das ações reprodutivas. Permite desmarcar em
// lote direto daqui (sem precisar voltar em Lançamentos > Baixar animal).
function CaixaADescartar({ animais, aoAtualizar, estadosPorNumero }: { animais: Animal[]; aoAtualizar: () => void; estadosPorNumero: Map<string, EstadoReprodutivoAnimal> }) {
  const marcados = useMemo(() => animais.filter((a) => a.a_descartar), [animais]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const toggle = (numero: string) => setSel((p) => { const n = new Set(p); n.has(numero) ? n.delete(numero) : n.add(numero); return n; });
  const toggleTodos = () => setSel((p) => (p.size === marcados.length && marcados.length ? new Set() : new Set(marcados.map((a) => a.numero))));

  const desmarcar = async () => {
    if (!sel.size) return;
    setSalvando(true); setMsg(null);
    try {
      await marcarADescartar({ animais: Array.from(sel), descartar: false });
      setMsg(`${sel.size} animal(is) desmarcado(s).`);
      setSel(new Set());
      aoAtualizar();
    } catch (e: any) {
      setMsg(e.message || "Erro ao desmarcar.");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="card mb-4">
      <div className="card-header mb-3 flex items-center justify-between">
        <span className="flex items-center gap-2"><Skull size={14} style={{ color: "var(--red)" }} /> Marcados para descarte ({marcados.length})</span>
        {marcados.length > 0 && (
          <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={toggleTodos}>
            {sel.size === marcados.length && marcados.length ? "Limpar seleção" : "Selecionar todos"}
          </button>
        )}
      </div>
      {marcados.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Nenhum animal marcado para descarte no momento.</p>
      ) : (
        <>
          <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
            Seguem ativos no rebanho (ordenha, sanidade, movimentação), mas fora das ações reprodutivas. Desmarque aqui para voltarem às ações reprodutivas.
          </p>
          <div className="overflow-x-auto" style={{ maxHeight: "420px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><th></th><th>Nº</th><th>Grupo</th><th>Categoria</th><th>Sit. Rep.</th><th>Motivo</th></tr></thead>
              <tbody>
                {marcados.map((a) => (
                  <tr key={a.numero} style={{ cursor: "pointer" }} onClick={() => toggle(a.numero)}>
                    <td><input type="checkbox" checked={sel.has(a.numero)} onChange={() => toggle(a.numero)} onClick={(e) => e.stopPropagation()} /></td>
                    <td style={{ fontWeight: 700 }}>{a.numero}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.grupo_primario || "—"}</td>
                    <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
                    <td><span style={{ color: SIT_CORES[rotuloEstadoDoAnimal(a.numero, estadosPorNumero) || ""] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{rotuloEstadoDoAnimal(a.numero, estadosPorNumero) || "—"}</span></td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.observacoes || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {msg && <p style={{ fontSize: "0.78rem", color: "var(--dourado-light)", marginTop: "0.6rem" }}>{msg}</p>}
          <button className="btn-primary" style={{ marginTop: "0.7rem", fontSize: "0.8rem" }} onClick={desmarcar} disabled={salvando || !sel.size}>
            {salvando ? "Salvando…" : `Desmarcar ${sel.size || ""} selecionado(s)`}
          </button>
        </>
      )}
    </div>
  );
}

// Página própria de Rebanho > Animais a descartar — antes vivia dentro da
// aba "Rebanho" (visão geral); virou sub-aba independente para não poluir
// a visão geral e para trazer todos os animais (inclusive machos), já que
// aqui a lista é fim em si mesma, não um recorte do filtro de fêmeas.
function RebanhoDescarte() {
  const [regs, setRegs] = useState<Animal[] | null>(null);
  const [estados, setEstados] = useState<EstadosReprodutivos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const carregar = useCallback(() => {
    fetchAnimais({ incluirMachos: true }).then(setRegs).catch((e) => setError(e.message));
    fetchEstadosReprodutivos().then(setEstados).catch(() => setEstados(null));
  }, []);
  useEffect(carregar, [carregar]);
  const estadosPorNumero = useMemo(() => new Map((estados?.animais ?? []).map((e) => [e.numero, e])), [estados]);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Skull size={22} style={{ color: "var(--red)" }} /> Animais a descartar</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Animais marcados para descarte, com o motivo (quando informado).</p>
      </div>
      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}.</span></div>}
      {!regs && !error && <TelaSkeleton kpis={0} />}
      {regs && <CaixaADescartar animais={regs} aoAtualizar={carregar} estadosPorNumero={estadosPorNumero} />}
    </div>
  );
}

// Tabela de um grupo/lote da lista "Fêmeas/Animais por Grupo" — extraída à
// parte para poder ordenar por coluna (clique no cabeçalho) de forma
// independente em cada grupo (cada instância deste componente tem seu
// próprio estado de ordenação via useOrdenacao).
function TabelaGrupoAnimais({ lista, femeasApenas, estadosPorNumero }: { lista: Animal[]; femeasApenas: boolean; estadosPorNumero: Map<string, EstadoReprodutivoAnimal> }) {
  // Enriquece com o rótulo do estado ao vivo e a produção ao vivo (com
  // fallback) só para poder ordenar pelas colunas "Sit. Rep." e "Últ. CL" —
  // useOrdenacao ordena por um campo do próprio objeto.
  const comRotulo = useMemo(
    () => lista.map((a) => ({ ...a, sitRepAoVivo: rotuloEstadoDoAnimal(a.numero, estadosPorNumero) ?? null, producaoAoVivo: producaoDe(a) })),
    [lista, estadosPorNumero]
  );
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(comRotulo);
  return (
    <table className="fazenda-table" style={{ margin: 0 }}>
      <thead><tr>
        <ThOrdenavel label="Nº" campo="numero" coluna={coluna} dir={dir} ordenar={ordenar} />
        <ThOrdenavel label="Categoria" campo="categoria_abrev" coluna={coluna} dir={dir} ordenar={ordenar} />
        {!femeasApenas && <ThOrdenavel label="Sexo" campo="sexo" coluna={coluna} dir={dir} ordenar={ordenar} />}
        <ThOrdenavel label="Raça" campo="raca" coluna={coluna} dir={dir} ordenar={ordenar} />
        <ThOrdenavel label="Sit. Rep." campo="sitRepAoVivo" coluna={coluna} dir={dir} ordenar={ordenar} />
        <ThOrdenavel label="DEL" campo="del_dias" coluna={coluna} dir={dir} ordenar={ordenar} alinhar="right" />
        <ThOrdenavel label="Últ. CL" campo="producaoAoVivo" coluna={coluna} dir={dir} ordenar={ordenar} alinhar="right" />
      </tr></thead>
      <tbody>
        {linhasOrdenadas.map((a) => (
          <tr key={a.numero}>
            <td style={{ fontWeight: 700 }}>{a.numero}</td>
            <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
            {!femeasApenas && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.sexo || "—"}</td>}
            <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.raca || "—"}</td>
            <td><span style={{ color: SIT_CORES[a.sitRepAoVivo || ""] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{a.sitRepAoVivo || "—"}</span></td>
            <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
            <td style={{ textAlign: "right", fontWeight: 600, color: a.producao_origem === "congelado" ? "var(--text-muted)" : undefined }}
              title={a.producao_origem === "congelado" ? "Valor do último CSV importado — nenhum controle leiteiro lançado no app para este animal" : undefined}>
              {a.producaoAoVivo ? `${a.producaoAoVivo.toFixed(1)}${a.producao_origem === "congelado" ? " *" : ""}` : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RebanhoVisaoGeral() {
  const [regs, setRegs] = useState<Animal[] | null>(null);
  const [estados, setEstados] = useState<EstadosReprodutivos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fGrupo, setFGrupo] = useState<string[]>([]);
  const [fSit, setFSit] = useState<string[]>([]);
  const [busca, setBusca] = useState("");
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const toggle = (g: string) => setAbertos((p) => { const n = new Set(p); n.has(g) ? n.delete(g) : n.add(g); return n; });
  const [modal, setModal] = useState<{ title: string; list: AnimalRow[] } | null>(null);

  // "Animais por grupo" (inclui machos) × "Fêmeas por Grupo" (padrão) — e,
  // cumulativa ou isoladamente, "somente fêmeas" (força só fêmeas mesmo com
  // machos incluídos) e "ordenar por numeração" (inverte a tabela: em vez de
  // agrupar por lote, lista tudo num só bloco ordenado pelo nº do animal).
  const [incluirMachos, setIncluirMachos] = useState(false);
  const [somenteFemeas, setSomenteFemeas] = useState(false);
  const [ordenarPorNumeracao, setOrdenarPorNumeracao] = useState(false);
  const femeasApenas = !incluirMachos || somenteFemeas;

  const carregar = useCallback(() => {
    fetchAnimais({ incluirMachos }).then(setRegs).catch((e) => setError(e.message));
    fetchEstadosReprodutivos().then(setEstados).catch(() => setEstados(null));
  }, [incluirMachos]);
  useEffect(carregar, [carregar]);

  // Estado reprodutivo AO VIVO por número (substitui o Animal.sit_rep
  // congelado do CSV) — animal sem entrada aqui (ex.: macho) fica sem estado.
  const estadosPorNumero = useMemo(() => new Map((estados?.animais ?? []).map((e) => [e.numero, e])), [estados]);
  const estadoDe = (numero: string) => estadosPorNumero.get(numero)?.estado;
  const rotuloDe = (numero: string) => rotuloEstadoDoAnimal(numero, estadosPorNumero);

  const opc = (f: (a: Animal) => string | null) => {
    const s = new Set<string>(); (regs ?? []).forEach((a) => { const v = f(a); if (v) s.add(v); });
    return Array.from(s).sort();
  };

  const filtrados = useMemo(() => {
    if (!regs) return [];
    return regs.filter((a) => {
      const rotulo = rotuloEstadoDoAnimal(a.numero, estadosPorNumero);
      return (fGrupo.length === 0 || (a.grupo_primario ? fGrupo.includes(a.grupo_primario) : false)) &&
        (fSit.length === 0 || (rotulo ? fSit.includes(rotulo) : false)) &&
        casaBusca(a.numero, busca) &&
        (!somenteFemeas || a.sexo !== "M");
    });
  }, [regs, estadosPorNumero, fGrupo, fSit, busca, somenteFemeas]);

  const porNumero = useMemo(
    () => [...filtrados].sort((a, b) => a.numero.localeCompare(b.numero, undefined, { numeric: true })),
    [filtrados]
  );
  const pagPorNumero = usePaginacao(porNumero);

  const total = filtrados.length;
  const gestantes = filtrados.filter((a) => estadoDe(a.numero) === "gestante").length;
  // "vazias" antes contava tudo que começava com "Vaz." no sit_rep congelado
  // (o que incluía pev, apta e atrasada) — somamos os quatro estados ao vivo
  // equivalentes para manter o mesmo significado do card.
  const vazias = filtrados.filter((a) => ["vazia", "apta", "atrasada", "pev"].includes(estadoDe(a.numero) || "")).length;
  const inseminadas = filtrados.filter((a) => estadoDe(a.numero) === "inseminada").length;
  const vacasPev = filtrados.filter((a) => estadoDe(a.numero) === "pev").length;
  const aDescartar = filtrados.filter((a) => a.a_descartar).length;
  const delLact = filtrados.filter((a) => LACTACAO.includes(cod(a.grupo_primario) || "") && a.del_dias).map((a) => a.del_dias!);
  const delMedio = delLact.length ? Math.round(delLact.reduce((x, y) => x + y, 0) / delLact.length) : null;

  const porGrupo = useMemo(() => {
    const by = new Map<string, number>();
    filtrados.forEach((a) => { const g = a.grupo_primario || "(sem grupo)"; by.set(g, (by.get(g) ?? 0) + 1); });
    return Array.from(by.entries()).map(([grupo, n]) => ({ grupo, n })).sort((a, b) => a.grupo.localeCompare(b.grupo));
  }, [filtrados]);

  // Situação Reprodutiva (donut) — mesmo gráfico da Capa (app/page.tsx),
  // repetido aqui: mesma partição em 6 fatias, mesmas cores, mesmo alternador
  // Todas/Vacas/Novilhas. A diferença é a base: aqui parte de `filtrados`
  // (já filtrado por grupo/situação/busca desta página), não do rebanho
  // inteiro — por isso respeita a mesma regra do banner acima ("este filtro
  // comanda os resultados de toda a página abaixo").
  const [catRepChart, setCatRepChart] = useState<"todas" | "vaca" | "novilha">("todas");
  const filtradosParaChartRep = useMemo(
    () => catRepChart === "todas" ? filtrados : filtrados.filter((a) => (a.categoria_abrev || "").toLowerCase() === catRepChart),
    [filtrados, catRepChart]
  );
  const donutRep = useMemo(() => {
    // Mesmo agrupamento que o backend usa para o donut da Capa (ver
    // `_reproducao_categorias` em backend/fazenda/rules/indicadores.py):
    // pev/em_protocolo/gestante/inseminada mantêm o nome; apta+atrasada
    // viram "A inseminar"; vazia+nao_apta viram "Vazias". Sem estado (ex.:
    // macho, se incluído) não entra em fatia nenhuma — mesma regra de lá.
    const BUCKET_DE_ESTADO: Record<string, string> = {
      gestante: "Prenhes", inseminada: "Inseminadas", em_protocolo: "Em protocolo",
      pev: "PEV", apta: "A inseminar", atrasada: "A inseminar", vazia: "Vazias", nao_apta: "Vazias",
    };
    const por = new Map<string, Animal[]>();
    filtradosParaChartRep.forEach((a) => {
      const estado = estadoDe(a.numero);
      const bucket = estado ? BUCKET_DE_ESTADO[estado] : undefined;
      if (!bucket) return;
      (por.get(bucket) ?? por.set(bucket, []).get(bucket)!).push(a);
    });
    return ["Prenhes", "Inseminadas", "Em protocolo", "PEV", "A inseminar", "Vazias"]
      .map((nome) => ({ nome, v: por.get(nome)?.length ?? 0, animais: por.get(nome) ?? [] }))
      .filter((x) => x.v > 0);
  }, [filtradosParaChartRep, estadosPorNumero]);

  const grupoLista = useMemo(() => {
    const by = new Map<string, Animal[]>();
    filtrados.forEach((a) => { const g = a.grupo_primario || "(sem grupo)"; (by.get(g) ?? by.set(g, []).get(g)!).push(a); });
    return Array.from(by.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtrados]);

  // Exporta na mesma ordem exibida na tela — número (modo "Ordenar por
  // numeração") ou agrupado por lote (modo "por Grupo") — nunca a ordem crua
  // pré-filtro/ordenação de `filtrados`. "sit_rep" exportado é o rótulo do
  // estado ao vivo, não mais o texto cru do CSV.
  const linhasParaExportar = useMemo(
    () => (ordenarPorNumeracao ? porNumero : grupoLista.flatMap(([, lista]) => lista))
      .map((a) => ({
        ...a, categoria: a.categoria_abrev || a.categoria_completa, sit_rep: rotuloEstadoDoAnimal(a.numero, estadosPorNumero) || null,
        // `ult_cl_kg` fica sobrescrito pelo valor AO VIVO (com fallback) para a
        // planilha exportada não perder a distinção do congelado.
        ult_cl_kg: producaoDe(a),
        origem_producao: a.producao_origem === "congelado" ? "CSV importado (congelado)" : a.producao_origem === "controle" ? "Controle leiteiro" : "",
      })),
    [ordenarPorNumeracao, porNumero, grupoLista, estadosPorNumero]
  );

  const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };
  const tip = { background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", color: "var(--text)", fontSize: "0.8rem" };

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><CowIcon size={22} color="var(--dourado)" /> Rebanho</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Fêmeas do rebanho — filtre por grupo, situação reprodutiva ou número.</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importar dados</a>.</span></div>}
      {!regs && !error && <TelaSkeleton kpis={0} />}

      {regs && (
        <>
          <div className="card mb-4" style={{
            background: "color-mix(in srgb, var(--dourado) 14%, var(--surface))",
            border: "1px solid var(--dourado)",
          }}>
            <div className="card-header mb-3 flex items-center gap-2"><Filter size={14} style={{ color: "var(--dourado)" }} /> Filtros</div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <GrupoLotePicker label="Grupo / lote" opcoes={opc((a) => a.grupo_primario)} selecionados={fGrupo} onChange={setFGrupo} />
              <MultiFiltro label="Situação rep." opcoes={opc((a) => rotuloDe(a.numero) ?? null)} selecionados={fSit} onChange={setFSit} />
              <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Buscar nº</label>
                <div style={{ position: "relative" }}>
                  <Search size={13} style={{ position: "absolute", left: 8, top: 9, color: "var(--text-muted)" }} />
                  <input style={{ ...selStyle, paddingLeft: "1.6rem" }} value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 068" />
                </div></div>
            </div>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.7rem" }}>
              Este filtro comanda os resultados de toda a página abaixo: indicadores, gráficos e a lista de animais por grupo/número mudam conforme o filtro. (A composição do rebanho logo abaixo é uma referência fixa do rebanho inteiro e não muda com o filtro.)
            </p>
          </div>

          <EstratificacaoRebanho animais={regs} />

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4 mb-4">
            <Indicador categoria="geral" valor={total} rotulo={femeasApenas ? "Fêmeas (filtro)" : "Animais (filtro)"}
              onClick={() => setModal({ title: femeasApenas ? "Fêmeas (filtro)" : "Animais (filtro)", list: filtrados })} />
            <Indicador categoria="reprodutivo" valor={gestantes} cor="var(--green-light)" rotulo="Gestantes"
              onClick={() => setModal({ title: "Gestantes", list: filtrados.filter((a) => estadoDe(a.numero) === "gestante") })} />
            <Indicador categoria="reprodutivo" valor={vazias} cor="var(--amber)" rotulo="Vazias"
              onClick={() => setModal({ title: "Vazias", list: filtrados.filter((a) => ["vazia", "apta", "atrasada", "pev"].includes(estadoDe(a.numero) || "")) })} />
            <Indicador categoria="reprodutivo" valor={inseminadas} cor="var(--dourado-light)" rotulo="Inseminadas"
              onClick={() => setModal({ title: "Inseminadas", list: filtrados.filter((a) => estadoDe(a.numero) === "inseminada") })} />
            <Indicador categoria="reprodutivo" valor={vacasPev} cor="var(--blue)" rotulo="Vacas no PEV"
              onClick={() => setModal({ title: "Vacas no PEV", list: filtrados.filter((a) => estadoDe(a.numero) === "pev") })} />
            <Indicador categoria="geral" icon={Skull} valor={aDescartar} cor="var(--red)" rotulo="A descartar"
              onClick={() => setModal({ title: "A descartar", list: filtrados.filter((a) => a.a_descartar) })} />
            <Indicador categoria="producao" valor={delMedio ?? "—"} rotulo="DEL médio (lactação)"
              podeClicar={!!delMedio}
              onClick={() => setModal({ title: "DEL médio (lactação)", list: filtrados.filter((a) => LACTACAO.includes(cod(a.grupo_primario) || "") && a.del_dias) })} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div className="card">
              <div className="card-header mb-3">Composição por Grupo <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para ver os animais)</span></div>
              <ResponsiveContainer width="100%" height={Math.max(200, porGrupo.length * 26)}>
                <BarChart data={porGrupo} layout="vertical" margin={{ left: 8 }}>
                  <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 10 }} allowDecimals={false} />
                  <YAxis type="category" dataKey="grupo" tick={{ fill: "var(--text-muted)", fontSize: 9 }} width={150} />
                  <Tooltip contentStyle={tip} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                  <Bar dataKey="n" name="Fêmeas" fill="var(--vinho-light, #416180)" radius={[0, 3, 3, 0]} style={{ cursor: "pointer" }}
                    onClick={(e: any) => e?.grupo && setModal({ title: e.grupo, list: filtrados.filter((a) => (a.grupo_primario || "(sem grupo)") === e.grupo) })} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="card">
              <div className="card-header mb-2 flex flex-wrap items-center gap-2">
                Situação Reprodutiva <span style={{ fontWeight: 400, fontSize: "0.7rem", color: "var(--text-muted)" }}>(clique para ver os animais)</span>
                <div style={{ marginLeft: "auto", display: "flex", gap: "0.25rem" }}>
                  {([["todas", "Todas"], ["vaca", "Vacas"], ["novilha", "Novilhas"]] as const).map(([k, lbl]) => (
                    <button key={k} onClick={() => setCatRepChart(k)} title={`Ver situação reprodutiva — ${lbl}`}
                      style={{ fontSize: "0.7rem", padding: "0.2rem 0.6rem", borderRadius: "999px", cursor: "pointer",
                        border: "1px solid " + (catRepChart === k ? "var(--dourado)" : "var(--border)"),
                        background: catRepChart === k ? "var(--dourado)" : "transparent",
                        color: catRepChart === k ? "#1a1a1a" : "var(--text-muted)", fontWeight: catRepChart === k ? 700 : 400 }}>
                      {lbl}
                    </button>
                  ))}
                </div>
              </div>
              {donutRep.length ? (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie data={donutRep} dataKey="v" nameKey="nome" cx="50%" cy="50%" innerRadius={45} outerRadius={80} label={(e: any) => `${e.nome} (${e.v})`} labelLine={false} fontSize={10}
                      style={{ cursor: "pointer" }}
                      onClick={(e: any) => {
                        const nome = e?.name; if (!nome) return;
                        const grupo = donutRep.find((s) => s.nome === nome);
                        if (grupo) setModal({ title: nome, list: grupo.animais });
                      }}>
                      {donutRep.map((s, i) => <Cell key={i} fill={SIT_CORES_DONUT[s.nome]} />)}
                    </Pie>
                    <Tooltip contentStyle={tip} />
                  </PieChart>
                </ResponsiveContainer>
              ) : <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem dados reprodutivos para esse filtro.</p>}
            </div>
          </div>

          <div className="card">
            <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <span>{ordenarPorNumeracao ? (femeasApenas ? "Fêmeas por Número" : "Animais por Número") : (femeasApenas ? "Fêmeas por Grupo" : "Animais por Grupo")}</span>
              <div className="flex items-center gap-3" style={{ flexWrap: "wrap" }}>
                <label className="flex items-center gap-2" style={{ fontSize: "0.78rem", color: "var(--text)", cursor: "pointer" }} title="Inclui também os machos do rebanho">
                  <input type="checkbox" checked={incluirMachos} onChange={(e) => setIncluirMachos(e.target.checked)} /> Animais por grupo (incluir machos)
                </label>
                <label className="flex items-center gap-2" style={{ fontSize: "0.78rem", color: "var(--text)", cursor: "pointer" }}>
                  <input type="checkbox" checked={somenteFemeas} onChange={(e) => setSomenteFemeas(e.target.checked)} disabled={!incluirMachos} /> Somente fêmeas
                </label>
                <label className="flex items-center gap-2" style={{ fontSize: "0.78rem", color: "var(--text)", cursor: "pointer" }}>
                  <input type="checkbox" checked={ordenarPorNumeracao} onChange={(e) => setOrdenarPorNumeracao(e.target.checked)} /> Ordenar por numeração
                </label>
                <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{total} no filtro</span>
                <ExportarBotoes titulo="Rebanho" nomeArquivoBase="rebanho"
                  colunas={COLUNAS_REBANHO}
                  linhas={linhasParaExportar} />
                {!ordenarPorNumeracao && (() => {
                  const todosAbertos = abertos.size === grupoLista.length && grupoLista.length > 0;
                  return (
                    <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }}
                      title={todosAbertos ? "Recolher todos os grupos" : "Expandir todos os grupos"}
                      onClick={() => setAbertos((p) => p.size === grupoLista.length ? new Set() : new Set(grupoLista.map(([g]) => g)))}>
                      {todosAbertos ? <ChevronsUp size={14} /> : <ChevronsDown size={14} />}
                      {todosAbertos ? "Recolher tudo" : "Expandir tudo"}
                    </button>
                  );
                })()}
              </div>
            </div>

            {ordenarPorNumeracao ? (
              <div className="overflow-x-auto">
                <table className="fazenda-table" style={{ margin: 0 }}>
                  <thead><tr>
                    <th>Nº</th><th>Grupo</th><th>Categoria</th>
                    {!femeasApenas && <th>Sexo</th>}
                    <th>Raça</th><th>Sit. Rep.</th><th style={{ textAlign: "right" }}>DEL</th><th style={{ textAlign: "right" }}>Últ. CL</th>
                  </tr></thead>
                  <tbody>
                    {pagPorNumero.linhasPagina.map((a) => (
                      <tr key={a.numero}>
                        <td style={{ fontWeight: 700 }}>{a.numero}</td>
                        <td style={{ fontSize: "0.75rem" }}>{a.grupo_primario || "—"}</td>
                        <td style={{ fontSize: "0.75rem" }}>{a.categoria_abrev || a.categoria_completa || "—"}</td>
                        {!femeasApenas && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.sexo || "—"}</td>}
                        <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{a.raca || "—"}</td>
                        <td><span style={{ color: SIT_CORES[rotuloDe(a.numero) || ""] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{rotuloDe(a.numero) || "—"}</span></td>
                        <td style={{ textAlign: "right" }}>{a.del_dias ?? "—"}</td>
                        <td style={{ textAlign: "right", fontWeight: 600, color: a.producao_origem === "congelado" ? "var(--text-muted)" : undefined }}
                          title={a.producao_origem === "congelado" ? "Valor do último CSV importado — nenhum controle leiteiro lançado no app para este animal" : undefined}>
                          {producaoDe(a) ? `${(producaoDe(a) as number).toFixed(1)}${a.producao_origem === "congelado" ? " *" : ""}` : "—"}
                        </td>
                      </tr>
                    ))}
                    {!porNumero.length && <tr><td colSpan={femeasApenas ? 7 : 8} style={{ color: "var(--text-muted)", fontSize: "0.85rem", padding: "0.75rem" }}>Nenhum animal no filtro.</td></tr>}
                  </tbody>
                </table>
                <Paginacao pagina={pagPorNumero.pagina} totalPaginas={pagPorNumero.totalPaginas} totalLinhas={pagPorNumero.totalLinhas}
                  tamanhoPagina={pagPorNumero.tamanhoPagina} onMudarPagina={pagPorNumero.setPagina} onMudarTamanho={pagPorNumero.setTamanhoPagina} />
              </div>
            ) : (
              <div className="space-y-2">
                {grupoLista.map(([grupo, lista]) => {
                  const aberto = abertos.has(grupo);
                  return (
                    <div key={grupo} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
                      <button onClick={() => toggle(grupo)} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.55rem 0.9rem", background: "var(--surface-2)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                        {aberto ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        <span style={{ flex: 1, fontSize: "0.85rem" }}>{grupo}</span>
                        <span style={{ fontSize: "0.8rem", color: "var(--dourado-light)" }}>{lista.length} {femeasApenas ? (lista.length !== 1 ? "fêmeas" : "fêmea") : (lista.length !== 1 ? "animais" : "animal")}</span>
                      </button>
                      {aberto && (
                        <div className="overflow-x-auto">
                          <TabelaGrupoAnimais lista={lista} femeasApenas={femeasApenas} estadosPorNumero={estadosPorNumero} />
                        </div>
                      )}
                    </div>
                  );
                })}
                {!grupoLista.length && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum animal no filtro.</p>}
              </div>
            )}
          </div>
        </>
      )}

      {modal && <AnimalModal title={modal.title} animais={modal.list} onClose={() => setModal(null)} />}
    </div>
  );
}

// Movimentar/Comprar/Baixar ficam apenas em Lançamentos › Animais — aqui o
// Rebanho é só consulta (visão, ficha e sugestões).
type Aba = "visao" | "descarte" | "sugestoes" | "ficha" | "touros" | "indicadores";
const ABAS_VALIDAS: Aba[] = ["visao", "descarte", "sugestoes", "ficha", "touros", "indicadores"];

const ABAS_REBANHO = [
  { id: "visao", label: "Rebanho", icon: CowIcon, title: "Visão geral do rebanho por grupo" },
  { id: "descarte", label: "Animais a descartar", icon: Skull, title: "Animais marcados para descarte, com o motivo" },
  { id: "ficha", label: "Ficha do animal", icon: FileText, title: "Ficha completa e editável de um animal" },
  { id: "touros", label: "Touros", icon: Dna, title: "Filtro de touros: fazenda, estoque de sêmen ou banco NAAB" },
  { id: "sugestoes", label: "Sugestões de movimentação", icon: Sparkles, title: "Sugestões automáticas de movimentação" },
  { id: "indicadores", label: "Indicadores", icon: BarChart3, title: "Indicadores do rebanho: composição, eficiência reprodutiva e produção" },
] as const satisfies readonly { id: Aba; label: string; icon: any; title: string }[];

export default function RebanhoPage() {
  const [aba, setAba] = useState<Aba>("visao");
  // key da visão geral: incrementa ao (re)entrar na aba "visao" para refazer o fetch e evitar dados velhos.
  const [visaoKey, setVisaoKey] = useState(0);
  // Número pré-selecionado ao abrir a ficha a partir de Touros (clique num touro da fazenda que também é um Animal cadastrado).
  const [fichaNumeroInicial, setFichaNumeroInicial] = useState<string | undefined>(undefined);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const abaParam = params.get("aba") as Aba | null;
    if (abaParam && ABAS_VALIDAS.includes(abaParam)) setAba(abaParam);
    const numeroParam = params.get("numero");
    if (numeroParam) { setFichaNumeroInicial(numeroParam); setAba("ficha"); }
  }, []);

  const trocarAba = useCallback((k: Aba) => { if (k === "visao") setVisaoKey((v) => v + 1); setAba(k); }, []);
  const subNavTree: SubNavNode[] = useMemo(() => ABAS_REBANHO.map((a) => ({ id: a.id, label: a.label, icon: a.icon })), []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: aba, onSelect: trocarAba as (id: string) => void }), [subNavTree, aba, trocarAba]));

  return (
    <div className="px-6 pt-6">
      <div style={{ margin: "0 -1.5rem" }}>
        {aba === "visao" && <RebanhoVisaoGeral key={visaoKey} />}
        {aba === "descarte" && <RebanhoDescarte />}
        {aba === "sugestoes" && <div className="p-6"><SugestoesMovimentacao /></div>}
        {aba === "ficha" && <FichaAnimal numeroInicial={fichaNumeroInicial} />}
        {aba === "touros" && <RebanhoTouros onAbrirFicha={(numero) => { setFichaNumeroInicial(numero); trocarAba("ficha"); }} />}
        {aba === "indicadores" && <IndicadoresGerais />}
      </div>
    </div>
  );
}
