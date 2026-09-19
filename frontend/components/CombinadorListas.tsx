"use client";
import { useEffect, useMemo, useState } from "react";
import { Combine, RefreshCw, AlertTriangle, ChevronDown, Search, X } from "lucide-react";
import { fetchCombinadorListas, fetchAgenda, type AnimalCombinador, type CombinadorListasData } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";

/**
 * Combinador de Listas — Insights > Listas > Combinador de Listas.
 *
 * Construtor de PARÂMETROS configuráveis: lote, faixas numéricas (peso,
 * produção, idade, DEL, faltando p/ parto, dias de gestação, dias desde o
 * último serviço), situação produtiva/reprodutiva, categoria etária
 * (vaca/novilha/bezerra), categoria cadastrada (Configurações > Cadastro >
 * Categorias, dinâmica por fazenda) e BST (aptas/a incluir/inaptas).
 *
 * Cada parâmetro ATIVO vira um conjunto de números de animal; a escolha de
 * União/Interseção/Diferença cruza esses conjuntos. Layout em 2 colunas
 * (filtros à esquerda, resultado fixo à direita) — proposta aprovada em
 * artefato de design antes da implementação (redesign de layout, não muda
 * nenhuma regra de negócio).
 *
 * Fonte dos dados: GET /relatorios/combinador-listas traz os atributos de
 * cada animal (peso, produção, situação etc. — ver
 * fazenda/rules/combinador_listas.py) já prontos, sem recálculo nenhum
 * aqui. O BST continua vindo de GET /agenda/ (bst_elegiveis/
 * bst_nunca_aplicados/bst_excluidos) — não duplicamos o motor da Agenda só
 * para 3 listas que já existem.
 *
 * Colunas dinâmicas no resultado: cada parâmetro ativo pode acrescentar UMA
 * coluna derivada à tabela (nunca duplicada — vários parâmetros que
 * representam o mesmo dado, ex. o chip "Pós-parto - PEV" e a faixa de DEL,
 * caem na MESMA coluna "DEL"). Ver `useColunasDinamicas` abaixo.
 *
 * Resultado vazio NÃO é tratado como erro (o usuário pode legitimamente não
 * achar ninguém), mas o sistema sempre explica qual filtro é o suspeito —
 * ver `diagnostico` abaixo.
 */

type Filtro = { chave: string; grupo: string; rotulo: string; match: (a: AnimalCombinador) => boolean; onRemover: () => void };
type Celula = { texto: string; temBadge?: boolean; badge?: string };
type Coluna = { id: string; label: string; get: (a: AnimalCombinador) => Celula };
type Linha = { numero: string; celulas: Celula[]; presenteEm?: string };

const card: React.CSSProperties = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1.1rem 1.25rem" };
const cardTitulo: React.CSSProperties = { fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", color: "var(--text)" };
const badgeContagem: React.CSSProperties = { display: "inline-flex", alignItems: "center", padding: "0.1rem 0.45rem", borderRadius: "var(--r-sm)", background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-muted)", fontSize: "0.68rem", fontWeight: 700 };
const chip = (ativo: boolean, compacto?: boolean): React.CSSProperties => ({
  display: "inline-flex", alignItems: "center", gap: "0.3rem", padding: compacto ? "0.28rem 0.6rem" : "0.4rem 0.8rem",
  borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: ativo ? "var(--pill-active-bg)" : "var(--surface-2)",
  color: ativo ? "var(--pill-active-fg)" : "var(--text)", fontSize: compacto ? "0.72rem" : "0.79rem", fontWeight: ativo ? 700 : 500, cursor: "pointer",
  whiteSpace: "nowrap",
});
const label: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700, marginBottom: "0.5rem", display: "block" };
const numInput: React.CSSProperties = { width: 78, padding: "0.35rem 0.5rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.8rem" };
const faixaLabel: React.CSSProperties = { flex: "0 0 210px", fontSize: "0.8rem", color: "var(--text)" };
const faixaRow: React.CSSProperties = { display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.5rem 0.6rem", borderRadius: "var(--r-sm)", background: "var(--surface-2)", flexWrap: "wrap" };

function num(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function dentroFaixa(valor: number | null, min: string, max: string): boolean {
  const mn = num(min), mx = num(max);
  if (mn === null && mx === null) return true; // não filtra
  if (valor === null) return false; // filtro ativo, animal sem o dado -> não entra
  if (mn !== null && valor < mn) return false;
  if (mx !== null && valor > mx) return false;
  return true;
}
function formatarData(diasAtras: number | null | undefined): string | null {
  if (diasAtras === null || diasAtras === undefined) return null;
  const d = new Date(Date.now() - diasAtras * 86400000);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}`;
}
function formatarDataRelativa(diasAtras: number | null | undefined): string | null {
  const data = formatarData(diasAtras);
  return data ? `${data} · ${diasAtras}d` : null;
}
function labelCategoriaEtaria(v: AnimalCombinador["categoria_etaria"]): string {
  return v === "vaca" ? "Vaca" : v === "novilha" ? "Novilha" : v === "bezerra" ? "Bezerra" : "—";
}
function labelReprodutivaCurta(v: AnimalCombinador["situacao_reprodutiva"]): string {
  return v === "vazia" ? "Vazia" : v === "vazia_atrasada" ? "Vazia atrasada" : v === "inseminada" ? "Inseminada" : v === "prenha" ? "Prenha" : "—";
}

const OPCOES_SITUACAO_REPRODUTIVA = [
  { v: "vazia", label: "Vazia (todas)" },
  { v: "vazia_atrasada", label: "Vazia em atraso" },
  { v: "inseminada", label: "Inseminada" },
  { v: "prenha", label: "Prenha" },
] as const;
const OPCOES_CATEGORIA_ETARIA = [
  { v: "vaca", label: "Vaca" },
  { v: "novilha", label: "Novilha" },
  { v: "bezerra", label: "Bezerra" },
] as const;
const OPCOES_PRODUTIVA = [
  { v: "todas", label: "Ambas" },
  { v: "lactacao", label: "Em lactação" },
  { v: "seca", label: "Seca" },
] as const;
const OPCOES_BST = [
  { v: "apta", label: "Aptas à aplicação" },
  { v: "incluir", label: "A incluir no próximo lote" },
  { v: "inapta", label: "Inaptas" },
] as const;

// Colunas cujo dado é o MESMO que outro parâmetro já cobre (ver docstring):
// "Pós-parto - PEV" reaproveita a coluna DEL; "Pré-parto" reaproveita
// "Faltando p/ parto"; "Prenha" reaproveita "Dias de gestação"; "Inseminada"
// e "Vazia atrasada" reaproveitam "Última IA/serviço"; "Novilha vazia em
// atraso" e "Liberada/apta" reaproveitam "Apta desde".

function ChipComContagem({ label, ativo, contagem, compacto, onClick }: {
  label: string; ativo: boolean; contagem: number; compacto?: boolean; onClick: () => void;
}) {
  return (
    <button type="button" style={chip(ativo, compacto)} onClick={onClick}>
      {label} <span style={{ opacity: 0.7 }}>({contagem})</span>
    </button>
  );
}

function CabecalhoCartao({ titulo, ativos, colapsado, onToggle }: {
  titulo: string; ativos: number; colapsado: boolean; onToggle: () => void;
}) {
  return (
    <button type="button" onClick={onToggle} className="flex items-center justify-between" style={{ width: "100%", background: "none", border: "none", cursor: "pointer", padding: 0, textAlign: "left" }}>
      <div className="flex items-center gap-2">
        <span style={cardTitulo}>{titulo}</span>
        {ativos > 0 && <span style={badgeContagem}>{ativos} ativo(s)</span>}
      </div>
      <ChevronDown size={16} style={{ color: "var(--text-muted)", transform: colapsado ? "rotate(-90deg)" : "rotate(0deg)", transition: "transform .15s ease" }} />
    </button>
  );
}

export default function CombinadorListas() {
  const [dados, setDados] = useState<CombinadorListasData | null>(null);
  const [agenda, setAgenda] = useState<any>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [operacao, setOperacao] = useState<"uniao" | "intersecao" | "diferenca">("intersecao");

  // ── Estado dos parâmetros ──
  const [lotes, setLotes] = useState<string[]>([]);
  const [delMin, setDelMin] = useState(""); const [delMax, setDelMax] = useState("");
  const [prodMin, setProdMin] = useState(""); const [prodMax, setProdMax] = useState("");
  const [faltaMin, setFaltaMin] = useState(""); const [faltaMax, setFaltaMax] = useState("");
  const [pesoMin, setPesoMin] = useState(""); const [pesoMax, setPesoMax] = useState("");
  const [gestMin, setGestMin] = useState(""); const [gestMax, setGestMax] = useState("");
  const [servMin, setServMin] = useState(""); const [servMax, setServMax] = useState("");
  const [idadeUnidade, setIdadeUnidade] = useState<"dias" | "meses">("meses");
  const [idadeMin, setIdadeMin] = useState(""); const [idadeMax, setIdadeMax] = useState("");
  const [situacaoProdutiva, setSituacaoProdutiva] = useState<"todas" | "lactacao" | "seca">("todas");
  const [situacaoReprodutiva, setSituacaoReprodutiva] = useState<string[]>([]);
  const [categoriaEtaria, setCategoriaEtaria] = useState<string[]>([]);
  const [categoriaCadastro, setCategoriaCadastro] = useState<string[]>([]);
  const [bst, setBst] = useState<string[]>([]);

  // ── Busca/"mostrar mais" nos dois grupos com muitos chips ──
  const [loteQuery, setLoteQuery] = useState("");
  const [cadastroQuery, setCadastroQuery] = useState("");
  const [loteExpandido, setLoteExpandido] = useState(false);
  const [cadastroExpandido, setCadastroExpandido] = useState(false);

  // ── Colapso dos cartões de parâmetros ──
  const [colapsado, setColapsado] = useState({ rebanho: false, faixas: false, situacao: false, bst: false });
  const toggleColapso = (k: keyof typeof colapsado) => setColapsado((s) => ({ ...s, [k]: !s[k] }));

  const carregar = () => {
    setCarregando(true); setErro(null);
    Promise.all([fetchCombinadorListas(), fetchAgenda()])
      .then(([d, a]) => { setDados(d); setAgenda(a); })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  };
  useEffect(() => { carregar(); }, []);

  const toggleEm = (lista: string[], set: (v: string[]) => void, v: string) =>
    set(lista.includes(v) ? lista.filter((x) => x !== v) : [...lista, v]);

  const limparTudo = () => {
    setLotes([]); setDelMin(""); setDelMax(""); setProdMin(""); setProdMax(""); setFaltaMin(""); setFaltaMax("");
    setPesoMin(""); setPesoMax(""); setGestMin(""); setGestMax(""); setServMin(""); setServMax("");
    setIdadeMin(""); setIdadeMax(""); setSituacaoProdutiva("todas"); setSituacaoReprodutiva([]);
    setCategoriaEtaria([]); setCategoriaCadastro([]); setBst([]); setOperacao("intersecao");
  };

  const animais = dados?.animais ?? [];
  const animaisPorNumero = useMemo(() => new Map(animais.map((a) => [a.numero, a])), [animais]);
  const contarSe = (pred: (a: AnimalCombinador) => boolean) => animais.filter(pred).length;

  // Conjuntos BST — reaproveitados de GET /agenda/, sem recalcular nada aqui.
  const bstConjuntos = useMemo(() => {
    if (!agenda) return { apta: new Set<string>(), incluir: new Set<string>(), inapta: new Set<string>() };
    return {
      apta: new Set((agenda.bst_elegiveis || []).map((r: any) => String(r.numero_matriz))),
      incluir: new Set((agenda.bst_nunca_aplicados || []).map((r: any) => String(r.numero_matriz))),
      inapta: new Set((agenda.bst_excluidos || []).map((r: any) => String(r.numero_matriz))),
    };
  }, [agenda]);
  const bstDoAnimal = (numero: string): "apta" | "incluir" | "inapta" | null =>
    bstConjuntos.apta.has(numero) ? "apta" : bstConjuntos.incluir.has(numero) ? "incluir" : bstConjuntos.inapta.has(numero) ? "inapta" : null;

  // ── Cada parâmetro ativo vira um Filtro (conjunto de números) ──
  const filtros: Filtro[] = useMemo(() => {
    if (!dados) return [];
    const f: Filtro[] = [];

    if (lotes.length) f.push({
      chave: "lote", grupo: "Rebanho", rotulo: `Lote: ${lotes.join(", ")}`,
      match: (a) => !!a.lote && lotes.includes(a.lote), onRemover: () => setLotes([]),
    });
    if (delMin || delMax) f.push({
      chave: "del", grupo: "Faixas", rotulo: `Dias pós-parto ${delMin || "…"}–${delMax || "…"}`,
      match: (a) => dentroFaixa(a.dias_pos_parto, delMin, delMax), onRemover: () => { setDelMin(""); setDelMax(""); },
    });
    if (prodMin || prodMax) f.push({
      chave: "producao", grupo: "Faixas", rotulo: `Produção ${prodMin || "…"}–${prodMax || "…"} kg`,
      match: (a) => dentroFaixa(a.producao_kg, prodMin, prodMax), onRemover: () => { setProdMin(""); setProdMax(""); },
    });
    if (faltaMin || faltaMax) f.push({
      chave: "falta_parto", grupo: "Faixas", rotulo: `Faltando p/ parto ${faltaMin || "…"}–${faltaMax || "…"}d`,
      match: (a) => dentroFaixa(a.dias_para_parto, faltaMin, faltaMax), onRemover: () => { setFaltaMin(""); setFaltaMax(""); },
    });
    if (pesoMin || pesoMax) f.push({
      chave: "peso", grupo: "Faixas", rotulo: `Peso ${pesoMin || "…"}–${pesoMax || "…"} kg`,
      match: (a) => dentroFaixa(a.peso_kg, pesoMin, pesoMax), onRemover: () => { setPesoMin(""); setPesoMax(""); },
    });
    if (gestMin || gestMax) f.push({
      chave: "gestacao", grupo: "Faixas", rotulo: `Dias de gestação ${gestMin || "…"}–${gestMax || "…"}`,
      match: (a) => dentroFaixa(a.dias_gestacao, gestMin, gestMax), onRemover: () => { setGestMin(""); setGestMax(""); },
    });
    if (servMin || servMax) f.push({
      chave: "servico", grupo: "Faixas", rotulo: `Dias desde o último serviço ${servMin || "…"}–${servMax || "…"}`,
      match: (a) => dentroFaixa(a.dias_desde_servico, servMin, servMax), onRemover: () => { setServMin(""); setServMax(""); },
    });
    if (idadeMin || idadeMax) {
      const fator = idadeUnidade === "meses" ? 30 : 1;
      const mn = idadeMin ? String(Number(idadeMin) * fator) : "";
      const mx = idadeMax ? String(Number(idadeMax) * fator) : "";
      f.push({
        chave: "idade", grupo: "Faixas", rotulo: `Idade ${idadeMin || "…"}–${idadeMax || "…"} ${idadeUnidade}`,
        match: (a) => dentroFaixa(a.idade_dias, mn, mx), onRemover: () => { setIdadeMin(""); setIdadeMax(""); },
      });
    }
    if (situacaoProdutiva !== "todas") f.push({
      chave: "sit_produtiva", grupo: "Situação", rotulo: `Situação produtiva: ${situacaoProdutiva === "lactacao" ? "Em lactação" : "Seca"}`,
      match: (a) => a.situacao_produtiva === situacaoProdutiva, onRemover: () => setSituacaoProdutiva("todas"),
    });
    if (situacaoReprodutiva.length) f.push({
      chave: "sit_reprodutiva", grupo: "Situação",
      rotulo: `Situação reprodutiva: ${situacaoReprodutiva.map((v) => OPCOES_SITUACAO_REPRODUTIVA.find((o) => o.v === v)?.label).join(", ")}`,
      match: (a) => {
        if (!a.situacao_reprodutiva) return false;
        return situacaoReprodutiva.some((v) => v === a.situacao_reprodutiva || (v === "vazia" && a.situacao_reprodutiva === "vazia_atrasada"));
      },
      onRemover: () => setSituacaoReprodutiva([]),
    });
    if (categoriaEtaria.length) f.push({
      chave: "cat_etaria", grupo: "Rebanho", rotulo: `Categoria: ${categoriaEtaria.map((v) => OPCOES_CATEGORIA_ETARIA.find((o) => o.v === v)?.label).join(", ")}`,
      match: (a) => !!a.categoria_etaria && categoriaEtaria.includes(a.categoria_etaria), onRemover: () => setCategoriaEtaria([]),
    });
    if (categoriaCadastro.length) f.push({
      chave: "cat_cadastro", grupo: "Rebanho", rotulo: `Categoria cadastrada: ${categoriaCadastro.join(", ")}`,
      match: (a) => !!a.categoria_cadastro && categoriaCadastro.includes(a.categoria_cadastro), onRemover: () => setCategoriaCadastro([]),
    });
    if (bst.length) {
      const conjuntos = bst.map((v) => (v === "apta" ? bstConjuntos.apta : v === "incluir" ? bstConjuntos.incluir : bstConjuntos.inapta));
      f.push({
        chave: "bst", grupo: "BST",
        rotulo: `BST: ${bst.map((v) => v === "apta" ? "Aptas à aplicação" : v === "incluir" ? "A incluir no próximo lote" : "Inaptas").join(", ")}`,
        match: (a) => conjuntos.some((c) => c.has(a.numero)), onRemover: () => setBst([]),
      });
    }
    return f;
  }, [dados, lotes, delMin, delMax, prodMin, prodMax, faltaMin, faltaMax, pesoMin, pesoMax, gestMin, gestMax,
      servMin, servMax, idadeMin, idadeMax, idadeUnidade, situacaoProdutiva, situacaoReprodutiva,
      categoriaEtaria, categoriaCadastro, bst, bstConjuntos]);

  // ── Colunas dinâmicas do resultado ao vivo — uma lista só, reaproveitada
  // nas 3 visões (filtro único, união/interseção, diferença). ──
  const colunasDinamicas: Coluna[] = useMemo(() => {
    const defs: Coluna[] = [];
    if (lotes.length) defs.push({ id: "lote", label: "Lote", get: (a) => ({ texto: a.lote || "—" }) });
    if (categoriaEtaria.length) defs.push({ id: "categoria", label: "Categoria", get: (a) => ({ texto: labelCategoriaEtaria(a.categoria_etaria) }) });

    const temDel = !!(delMin || delMax) || categoriaCadastro.includes("Pós-parto - PEV");
    if (temDel) defs.push({ id: "del", label: "DEL", get: (a) => ({ texto: a.dias_pos_parto != null ? `${a.dias_pos_parto}d` : "—" }) });

    const temFalta = !!(faltaMin || faltaMax) || categoriaCadastro.includes("Pré-parto");
    if (temFalta) defs.push({ id: "falta", label: "Faltando p/ parto", get: (a) => ({ texto: a.dias_para_parto != null ? `${a.dias_para_parto}d` : "—" }) });

    const temGestacao = !!(gestMin || gestMax) || categoriaCadastro.includes("Prenha");
    if (temGestacao) defs.push({ id: "gestacao", label: "Dias de gestação", get: (a) => ({ texto: a.dias_gestacao != null ? `${a.dias_gestacao}d` : "—" }) });

    const temServico = !!(servMin || servMax) || categoriaCadastro.includes("Inseminada") || categoriaCadastro.includes("Vazia atrasada");
    if (temServico) defs.push({ id: "servico", label: "Última IA/serviço", get: (a) => ({ texto: formatarDataRelativa(a.dias_desde_servico) ?? "—" }) });

    if (pesoMin || pesoMax) defs.push({ id: "peso", label: "Peso", get: (a) => {
      if (a.peso_kg == null) return { texto: "—" };
      const data = formatarData(a.dias_desde_pesagem);
      return { texto: data ? `${a.peso_kg}kg · ${data}` : `${a.peso_kg}kg` };
    } });

    if (prodMin || prodMax) defs.push({ id: "producao", label: "Produção", get: (a) => {
      if (a.producao_kg == null) return { texto: "—" };
      const data = formatarData(a.dias_desde_producao);
      return { texto: data ? `${a.producao_kg}kg · ${data}` : `${a.producao_kg}kg` };
    } });

    if (idadeMin || idadeMax) {
      const labelIdade = idadeUnidade === "meses" ? "Idade (meses)" : "Idade (dias)";
      defs.push({ id: "idade", label: labelIdade, get: (a) => {
        if (a.idade_dias == null) return { texto: "—" };
        return { texto: idadeUnidade === "meses" ? `${Math.round(a.idade_dias / 30)}m` : `${a.idade_dias}d` };
      } });
    }

    if (situacaoProdutiva === "todas") defs.push({ id: "sit_produtiva", label: "Situação produtiva", get: (a) => ({
      texto: a.situacao_produtiva === "lactacao" ? "Em lactação" : a.situacao_produtiva === "seca" ? "Seca" : "—",
    }) });

    if (situacaoReprodutiva.length >= 2) defs.push({ id: "sit_reprodutiva", label: "Situação reprodutiva", get: (a) => ({ texto: labelReprodutivaCurta(a.situacao_reprodutiva) }) });

    if (bst.length >= 2) defs.push({ id: "bst", label: "BST", get: (a) => {
      const b = bstDoAnimal(a.numero);
      return { texto: b === "apta" ? "Apta" : b === "incluir" ? "A incluir" : b === "inapta" ? "Inapta" : "—" };
    } });

    const temApta = categoriaCadastro.includes("Novilha vazia em atraso") || categoriaCadastro.includes("Liberada/apta");
    if (temApta) defs.push({ id: "apta", label: "Apta desde", get: (a) => {
      const data = formatarData(a.dias_desde_aptidao);
      if (!data) return { texto: "—" };
      if (a.apta === false) return { texto: data, temBadge: true, badge: "Inapto" };
      return { texto: data };
    } });

    return defs;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lotes, categoriaEtaria, delMin, delMax, categoriaCadastro, faltaMin, faltaMax, gestMin, gestMax, servMin, servMax,
      pesoMin, pesoMax, prodMin, prodMax, idadeMin, idadeMax, idadeUnidade, situacaoProdutiva, situacaoReprodutiva, bst, bstConjuntos]);

  const linhaComColunas = (numero: string): Linha => {
    const animal = animaisPorNumero.get(numero)!;
    return { numero, celulas: colunasDinamicas.map((c) => c.get(animal)) };
  };
  const celulasParaExport = (linha: Linha): Record<string, unknown> => {
    const rec: Record<string, unknown> = { numero: linha.numero };
    colunasDinamicas.forEach((c, i) => {
      const cel = linha.celulas[i];
      rec[c.id] = cel.temBadge ? `${cel.texto} (${cel.badge})` : cel.texto;
    });
    if (linha.presenteEm !== undefined) rec.presente_em = linha.presenteEm;
    return rec;
  };
  const colunasParaExport = (comPresenteEm: boolean) => [
    { header: "Número", key: "numero" },
    ...colunasDinamicas.map((c) => ({ header: c.label, key: c.id })),
    ...(comPresenteEm ? [{ header: "Presente em", key: "presente_em" }] : []),
  ];

  // Conjunto de números por filtro (calculado 1x, reaproveitado no cruzamento e no diagnóstico).
  const conjuntosPorFiltro = useMemo(() => {
    const m = new Map<string, Set<string>>();
    filtros.forEach((f) => m.set(f.chave, new Set(animais.filter(f.match).map((a) => a.numero))));
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animais, filtros]);

  const cabecalhoExport = filtros.length ? `Combinador de Listas — ${filtros.map((f) => f.rotulo).join(" · ")}` : "Combinador de Listas";

  // ── Resultado: só 1 filtro ativo -> mostra ele direto, sem cruzamento ──
  const resultadoUnicoFiltro = useMemo(() => {
    if (filtros.length !== 1) return null;
    const f = filtros[0];
    const ids = Array.from(conjuntosPorFiltro.get(f.chave) || []).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    return { filtro: f, linhas: ids.map(linhaComColunas) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros, conjuntosPorFiltro, colunasDinamicas]);

  // ── União/Interseção: 2+ filtros ──
  const resultadoUnico = useMemo(() => {
    if (filtros.length < 2 || operacao === "diferenca") return null;
    const conjuntos = filtros.map((f) => conjuntosPorFiltro.get(f.chave) || new Set<string>());
    const idsResultado = operacao === "uniao"
      ? new Set(conjuntos.flatMap((c) => Array.from(c)))
      : new Set(Array.from(conjuntos[0]).filter((id) => conjuntos.every((c) => c.has(id))));
    const linhas: Linha[] = Array.from(idsResultado).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map((id) => ({
      ...linhaComColunas(id),
      presenteEm: filtros.filter((f) => (conjuntosPorFiltro.get(f.chave) || new Set()).has(id)).map((f) => f.rotulo).join(", "),
    }));
    return { linhas };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros, operacao, conjuntosPorFiltro, colunasDinamicas]);

  // ── Diferença: uma lista por filtro, exclusiva ──
  const resultadosDiferenca = useMemo(() => {
    if (filtros.length < 2 || operacao !== "diferenca") return null;
    return filtros.map((alvo, idx) => {
      const idsAlvo = conjuntosPorFiltro.get(alvo.chave) || new Set<string>();
      const idsOutras = new Set(filtros.filter((_, i) => i !== idx).flatMap((f) => Array.from(conjuntosPorFiltro.get(f.chave) || [])));
      const linhas = Array.from(idsAlvo).filter((id) => !idsOutras.has(id))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map(linhaComColunas);
      return { filtro: alvo, linhas };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros, operacao, conjuntosPorFiltro, colunasDinamicas]);

  // ── Diagnóstico de resultado vazio (só faz sentido em união/interseção) ──
  const diagnostico = useMemo(() => {
    if (operacao === "diferenca" || filtros.length < 2) return null;
    if (!resultadoUnico || resultadoUnico.linhas.length > 0) return null;
    const semAnimais = filtros.filter((f) => (conjuntosPorFiltro.get(f.chave)?.size ?? 0) === 0);
    if (semAnimais.length) {
      return `Sozinho(s), ${semAnimais.length > 1 ? "estes filtros" : "este filtro"} já não encontra(m) nenhum animal: `
        + semAnimais.map((f) => `"${f.rotulo}"`).join(", ")
        + ". Confira se os valores/opções estão corretos.";
    }
    for (let i = 0; i < filtros.length; i++) {
      for (let j = i + 1; j < filtros.length; j++) {
        const a = conjuntosPorFiltro.get(filtros[i].chave) || new Set();
        const b = conjuntosPorFiltro.get(filtros[j].chave) || new Set();
        const temComum = Array.from(a).some((id) => b.has(id));
        if (!temComum) {
          return `Nenhum animal está ao mesmo tempo em "${filtros[i].rotulo}" e em "${filtros[j].rotulo}" — são critérios incompatíveis entre si `
            + `(ex.: situação produtiva/reprodutiva ou categoria cadastrada apontando para status diferentes). `
            + `Tente combinar outros filtros, ou use União para ver os dois grupos separadamente.`;
        }
      }
    }
    return `Cada filtro tem animais isoladamente, mas não há nenhum em comum entre todos os ${filtros.length} selecionados ao mesmo tempo. `
      + `Tente remover um filtro por vez para descobrir qual está sobrando, ou use União.`;
  }, [operacao, filtros, resultadoUnico, conjuntosPorFiltro]);

  if (carregando) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;
  if (erro) return <p style={{ color: "var(--red)" }}>{erro}</p>;
  if (!dados) return null;

  // ── Lote / Categoria cadastrada: chips com busca + "mostrar mais" ──
  const loteChipsTodos = dados.lotes.map((l) => ({ valor: l, contagem: contarSe((a) => a.lote === l) }));
  const loteFiltrados = loteQuery ? loteChipsTodos.filter((l) => l.valor.toLowerCase().includes(loteQuery.toLowerCase())) : loteChipsTodos;
  const loteLimite = loteExpandido ? loteFiltrados.length : Math.min(8, loteFiltrados.length);
  const loteVisiveis = loteFiltrados.slice(0, loteLimite);
  const loteRestantes = loteFiltrados.length - loteLimite;

  const cadastroChipsTodos = dados.categorias_cadastro.map((c) => ({ valor: c.nome, contagem: contarSe((a) => a.categoria_cadastro === c.nome) }));
  const cadastroFiltrados = cadastroQuery ? cadastroChipsTodos.filter((c) => c.valor.toLowerCase().includes(cadastroQuery.toLowerCase())) : cadastroChipsTodos;
  const cadastroLimite = cadastroExpandido ? cadastroFiltrados.length : Math.min(8, cadastroFiltrados.length);
  const cadastroVisiveis = cadastroFiltrados.slice(0, cadastroLimite);
  const cadastroRestantes = cadastroFiltrados.length - cadastroLimite;

  const renderCelula = (cel: Celula, key: string) => (
    <td key={key}>
      {cel.texto}
      {cel.temBadge && (
        <>
          <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--red, #C0392B)", marginLeft: 7, marginRight: 3, verticalAlign: "middle" }} />
          <span style={{ color: "var(--red, #C0392B)", fontSize: "0.7rem", fontWeight: 700, verticalAlign: "middle" }}>{cel.badge}</span>
        </>
      )}
    </td>
  );

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1.6fr_1fr] gap-6 items-start">
      {/* ───────── Coluna esquerda: parâmetros ───────── */}
      <div style={{ display: "grid", gap: "1rem" }}>
        <div style={card}>
          <div className="flex items-center justify-between" style={{ marginBottom: "0.6rem", flexWrap: "wrap", gap: "0.5rem" }}>
            <div className="flex items-center gap-2" style={{ fontWeight: 700, fontSize: "0.95rem" }}>
              <Combine size={16} style={{ color: "var(--accent-icon)" }} /> Combinador de listas
            </div>
            <div className="flex items-center gap-2">
              <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", fontWeight: 600 }}>
                {filtros.length ? `${filtros.length} parâmetro${filtros.length > 1 ? "s" : ""} ativo${filtros.length > 1 ? "s" : ""}` : "Nenhum parâmetro ativo"}
              </span>
              <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={limparTudo}><X size={13} /> Limpar tudo</button>
              <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={carregar}><RefreshCw size={13} /> Atualizar</button>
            </div>
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Configure um ou mais parâmetros abaixo. Cada chip mostra, entre parênteses, quantos animais atendem a ele sozinho.
          </p>
        </div>

        {/* ── Rebanho ── */}
        <div style={card}>
          <CabecalhoCartao titulo="Rebanho" ativos={filtros.filter((f) => f.grupo === "Rebanho").length} colapsado={colapsado.rebanho} onToggle={() => toggleColapso("rebanho")} />
          {!colapsado.rebanho && (
            <div style={{ display: "grid", gap: "1rem", marginTop: "1rem" }}>
              <div>
                <div className="flex items-center justify-between" style={{ marginBottom: "0.5rem", flexWrap: "wrap", gap: "0.5rem" }}>
                  <span style={label}>Lote</span>
                  <div className="flex items-center gap-2" style={{ padding: "0.35rem 0.6rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", background: "var(--surface-2)", width: 210 }}>
                    <Search size={13} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                    <input type="text" placeholder="Buscar lote…" value={loteQuery} onChange={(e) => setLoteQuery(e.target.value)}
                      style={{ border: "none", background: "transparent", outline: "none", fontSize: "0.78rem", width: "100%", color: "var(--text)" }} />
                  </div>
                </div>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  {loteVisiveis.map((l) => (
                    <ChipComContagem key={l.valor} label={l.valor} ativo={lotes.includes(l.valor)} contagem={l.contagem} compacto onClick={() => toggleEm(lotes, setLotes, l.valor)} />
                  ))}
                  {(loteExpandido || loteRestantes > 0) && loteFiltrados.length > 8 && (
                    <button type="button" style={{ ...chip(false, true), border: "1px dashed var(--border)" }} onClick={() => setLoteExpandido((v) => !v)}>
                      {loteExpandido ? "Mostrar menos" : `Mostrar mais (${loteRestantes})`}
                    </button>
                  )}
                  {loteFiltrados.length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Nenhum lote encontrado para "{loteQuery}".</span>}
                </div>
              </div>

              <div>
                <span style={label}>Categoria (marque uma ou mais)</span>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  {OPCOES_CATEGORIA_ETARIA.map((o) => (
                    <ChipComContagem key={o.v} label={o.label} ativo={categoriaEtaria.includes(o.v)} contagem={contarSe((a) => a.categoria_etaria === o.v)} onClick={() => toggleEm(categoriaEtaria, setCategoriaEtaria, o.v)} />
                  ))}
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between" style={{ marginBottom: "0.3rem", flexWrap: "wrap", gap: "0.5rem" }}>
                  <span style={label}>Categoria cadastrada (opcional, marque uma ou mais)</span>
                  <div className="flex items-center gap-2" style={{ padding: "0.35rem 0.6rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", background: "var(--surface-2)", width: 210 }}>
                    <Search size={13} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                    <input type="text" placeholder="Buscar categoria…" value={cadastroQuery} onChange={(e) => setCadastroQuery(e.target.value)}
                      style={{ border: "none", background: "transparent", outline: "none", fontSize: "0.78rem", width: "100%", color: "var(--text)" }} />
                  </div>
                </div>
                <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: "0 0 0.5rem" }}>Configurações &gt; Cadastro &gt; Categorias — não altera como cada animal é classificado, só limita a busca.</p>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  {cadastroVisiveis.map((c) => (
                    <ChipComContagem key={c.valor} label={c.valor} ativo={categoriaCadastro.includes(c.valor)} contagem={c.contagem} compacto onClick={() => toggleEm(categoriaCadastro, setCategoriaCadastro, c.valor)} />
                  ))}
                  {(cadastroExpandido || cadastroRestantes > 0) && cadastroFiltrados.length > 8 && (
                    <button type="button" style={{ ...chip(false, true), border: "1px dashed var(--border)" }} onClick={() => setCadastroExpandido((v) => !v)}>
                      {cadastroExpandido ? "Mostrar menos" : `Mostrar mais (${cadastroRestantes})`}
                    </button>
                  )}
                  {cadastroFiltrados.length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Nenhuma categoria encontrada para "{cadastroQuery}".</span>}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── Faixas numéricas ── */}
        <div style={card}>
          <CabecalhoCartao titulo="Faixas numéricas" ativos={filtros.filter((f) => f.grupo === "Faixas").length} colapsado={colapsado.faixas} onToggle={() => toggleColapso("faixas")} />
          {!colapsado.faixas && (
            <div style={{ display: "grid", gap: "0.5rem", marginTop: "1rem" }}>
              {[
                { titulo: "Dias pós-parto (DEL)", min: delMin, max: delMax, onMin: setDelMin, onMax: setDelMax },
                { titulo: "Produção", unidade: "kg", min: prodMin, max: prodMax, onMin: setProdMin, onMax: setProdMax },
                { titulo: "Faltando p/ parto", unidade: "dias", min: faltaMin, max: faltaMax, onMin: setFaltaMin, onMax: setFaltaMax },
                { titulo: "Peso", unidade: "kg", min: pesoMin, max: pesoMax, onMin: setPesoMin, onMax: setPesoMax },
                { titulo: "Dias de gestação", min: gestMin, max: gestMax, onMin: setGestMin, onMax: setGestMax },
                { titulo: "Dias desde o último serviço/IA/monta", min: servMin, max: servMax, onMin: setServMin, onMax: setServMax },
              ].map((f) => (
                <div key={f.titulo} style={faixaRow}>
                  <span style={faixaLabel}>{f.titulo}{f.unidade ? ` (${f.unidade})` : ""}</span>
                  <input type="number" placeholder="de" value={f.min} onChange={(e) => f.onMin(e.target.value)} style={numInput} />
                  <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>até</span>
                  <input type="number" placeholder="até" value={f.max} onChange={(e) => f.onMax(e.target.value)} style={numInput} />
                </div>
              ))}
              <div style={faixaRow}>
                <span style={faixaLabel}>Idade</span>
                <div className="flex items-center gap-1">
                  {(["dias", "meses"] as const).map((u) => (
                    <button key={u} type="button" style={{ ...chip(idadeUnidade === u, true) }} onClick={() => setIdadeUnidade(u)}>{u}</button>
                  ))}
                </div>
                <input type="number" placeholder="de" value={idadeMin} onChange={(e) => setIdadeMin(e.target.value)} style={numInput} />
                <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>até</span>
                <input type="number" placeholder="até" value={idadeMax} onChange={(e) => setIdadeMax(e.target.value)} style={numInput} />
              </div>
            </div>
          )}
        </div>

        {/* ── Situação ── */}
        <div style={card}>
          <CabecalhoCartao titulo="Situação" ativos={filtros.filter((f) => f.grupo === "Situação").length} colapsado={colapsado.situacao} onToggle={() => toggleColapso("situacao")} />
          {!colapsado.situacao && (
            <div style={{ display: "grid", gap: "1rem", marginTop: "1rem" }}>
              <div>
                <span style={label}>Situação produtiva</span>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  {OPCOES_PRODUTIVA.map((o) => (
                    <ChipComContagem key={o.v} label={o.label} ativo={situacaoProdutiva === o.v} contagem={o.v === "todas" ? animais.length : contarSe((a) => a.situacao_produtiva === o.v)} onClick={() => setSituacaoProdutiva(o.v)} />
                  ))}
                </div>
              </div>
              <div>
                <span style={label}>Situação reprodutiva (marque uma ou mais)</span>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  {OPCOES_SITUACAO_REPRODUTIVA.map((o) => (
                    <ChipComContagem key={o.v} label={o.label} ativo={situacaoReprodutiva.includes(o.v)}
                      contagem={contarSe((a) => a.situacao_reprodutiva === o.v || (o.v === "vazia" && a.situacao_reprodutiva === "vazia_atrasada"))}
                      onClick={() => toggleEm(situacaoReprodutiva, setSituacaoReprodutiva, o.v)} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ── BST ── */}
        <div style={card}>
          <CabecalhoCartao titulo="BST" ativos={filtros.filter((f) => f.grupo === "BST").length} colapsado={colapsado.bst} onToggle={() => toggleColapso("bst")} />
          {!colapsado.bst && (
            <div style={{ marginTop: "1rem" }}>
              <span style={label}>Marque uma ou mais</span>
              <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                {OPCOES_BST.map((o) => (
                  <ChipComContagem key={o.v} label={o.label} ativo={bst.includes(o.v)} contagem={bstConjuntos[o.v].size} onClick={() => toggleEm(bst, setBst, o.v)} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ───────── Coluna direita: resultado (fixa) ───────── */}
      <div className="xl:sticky xl:top-4" style={{ display: "grid", gap: "1rem" }}>
        {filtros.length >= 2 && (
          <div style={card}>
            <span style={{ ...cardTitulo, display: "block", marginBottom: "0.6rem" }}>Cruzamento</span>
            <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
              {([
                { v: "uniao", label: "União" },
                { v: "intersecao", label: "Interseção" },
                { v: "diferenca", label: "Diferença" },
              ] as const).map((op) => (
                <button key={op.v} type="button" style={chip(operacao === op.v)} onClick={() => setOperacao(op.v)}>{op.label}</button>
              ))}
            </div>
            <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
              {operacao === "uniao" ? "Está em qualquer um dos parâmetros selecionados."
                : operacao === "intersecao" ? "Está em todos os parâmetros selecionados ao mesmo tempo."
                : "Uma tabela por parâmetro: quem está só nele e em nenhum dos outros."}
            </p>
          </div>
        )}

        <div style={card}>
          <div className="flex items-center justify-between" style={{ marginBottom: "0.85rem" }}>
            <span style={cardTitulo}>Resultado</span>
          </div>

          {filtros.length > 0 && (
            <>
              <div className="flex items-center gap-2" style={{ flexWrap: "wrap", marginBottom: "0.6rem" }}>
                {filtros.map((f) => (
                  <span key={f.chave} className="flex items-center gap-2" style={{ padding: "0.28rem 0.6rem 0.28rem 0.7rem", borderRadius: "var(--r-sm)", background: "var(--surface-2)", border: "1px solid var(--border)", fontSize: "0.72rem", fontWeight: 600, color: "var(--text)" }}>
                    {f.rotulo}
                    <button type="button" onClick={f.onRemover} aria-label={`Remover filtro ${f.rotulo}`}
                      style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 15, height: 15, borderRadius: "var(--r-sm)", border: "none", background: "var(--border)", color: "var(--text-muted)", cursor: "pointer", padding: 0 }}>
                      <X size={9} />
                    </button>
                  </span>
                ))}
              </div>
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "1rem" }}>Cabeçalho do arquivo exportado: "{cabecalhoExport}"</p>
            </>
          )}

          {filtros.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2" style={{ padding: "2.5rem 1.5rem", border: "1.5px dashed var(--border)", borderRadius: "var(--r-sm)", background: "var(--surface-2)", textAlign: "center" }}>
              <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", maxWidth: "32ch", margin: 0 }}>Configure ao menos 1 parâmetro à esquerda para ver o resultado aqui.</p>
            </div>
          ) : resultadoUnicoFiltro ? (
            <div style={{ display: "grid", gap: "0.9rem" }}>
              <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem", paddingLeft: "0.9rem", borderLeft: "3px solid var(--accent-icon)" }}>
                  <span style={{ fontSize: "2rem", fontWeight: 800, color: "var(--text)", lineHeight: 1 }}>{resultadoUnicoFiltro.linhas.length}</span>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>animal(is) — {resultadoUnicoFiltro.filtro.rotulo}</span>
                </div>
                <ExportarBotoes
                  titulo={cabecalhoExport}
                  colunas={colunasParaExport(false)}
                  linhas={resultadoUnicoFiltro.linhas.map(celulasParaExport)}
                  nomeArquivoBase="combinador_listas"
                />
              </div>
              {resultadoUnicoFiltro.linhas.length === 0 ? (
                <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Nenhum animal atende a este parâmetro. Confira se o valor/opção está correto.</p>
              ) : (
                <div style={{ overflowX: "auto", maxHeight: 420, overflowY: "auto" }}>
                  <table className="fazenda-table">
                    <thead><tr>
                      <th>Número</th>
                      {colunasDinamicas.map((c) => <th key={c.id}>{c.label}</th>)}
                    </tr></thead>
                    <tbody>
                      {resultadoUnicoFiltro.linhas.map((l) => (
                        <tr key={l.numero}>
                          <td>{l.numero}</td>
                          {l.celulas.map((cel, i) => renderCelula(cel, colunasDinamicas[i].id))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : operacao === "diferenca" && resultadosDiferenca ? (
            <div style={{ display: "grid", gap: "1rem", maxHeight: "60vh", overflowY: "auto", paddingRight: 2 }}>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                Diferença calcula, para cada parâmetro selecionado, quem está só nele e em nenhum dos outros. Um
                resultado com 0 aqui é normal: significa que os animais desse filtro também aparecem em outro
                filtro selecionado.
              </p>
              {resultadosDiferenca.map((r) => (
                <div key={r.filtro.chave} style={{ borderTop: "1px solid var(--border)", paddingTop: "0.85rem" }}>
                  <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <span style={{ fontWeight: 700, fontSize: "0.82rem" }}>
                      Só em "{r.filtro.rotulo}" ({r.linhas.length})
                    </span>
                    <ExportarBotoes
                      titulo={`${cabecalhoExport} — Só em "${r.filtro.rotulo}"`}
                      colunas={colunasParaExport(false)}
                      linhas={r.linhas.map(celulasParaExport)}
                      nomeArquivoBase={`combinador_diferenca_${r.filtro.chave}`}
                    />
                  </div>
                  {r.linhas.length === 0 ? (
                    <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: 0 }}>Nenhum animal exclusivo deste filtro.</p>
                  ) : (
                    <div style={{ overflowX: "auto", maxHeight: 220, overflowY: "auto" }}>
                      <table className="fazenda-table">
                        <thead><tr>
                          <th>Número</th>
                          {colunasDinamicas.map((c) => <th key={c.id}>{c.label}</th>)}
                        </tr></thead>
                        <tbody>
                          {r.linhas.map((l) => (
                            <tr key={l.numero}>
                              <td>{l.numero}</td>
                              {l.celulas.map((cel, i) => renderCelula(cel, colunasDinamicas[i].id))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : resultadoUnico ? (
            <div style={{ display: "grid", gap: "0.9rem" }}>
              {resultadoUnico.linhas.length === 0 ? (
                <div className="flex items-start gap-2" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.75rem 0.9rem" }}>
                  <AlertTriangle size={16} style={{ color: "var(--amber, #b45309)", flexShrink: 0, marginTop: 2 }} />
                  <p style={{ fontSize: "0.82rem", margin: 0 }}>Nenhum animal atende ao cruzamento escolhido. {diagnostico}</p>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem", paddingLeft: "0.9rem", borderLeft: "3px solid var(--accent-icon)" }}>
                      <span style={{ fontSize: "2rem", fontWeight: 800, color: "var(--text)", lineHeight: 1 }}>{resultadoUnico.linhas.length}</span>
                      <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>animal(is) no resultado</span>
                    </div>
                    <ExportarBotoes
                      titulo={cabecalhoExport}
                      colunas={colunasParaExport(true)}
                      linhas={resultadoUnico.linhas.map(celulasParaExport)}
                      nomeArquivoBase="combinador_listas"
                    />
                  </div>
                  <div style={{ overflowX: "auto", maxHeight: 420, overflowY: "auto" }}>
                    <table className="fazenda-table">
                      <thead><tr>
                        <th>Número</th>
                        {colunasDinamicas.map((c) => <th key={c.id}>{c.label}</th>)}
                        <th>Presente em</th>
                      </tr></thead>
                      <tbody>
                        {resultadoUnico.linhas.map((l) => (
                          <tr key={l.numero}>
                            <td>{l.numero}</td>
                            {l.celulas.map((cel, i) => renderCelula(cel, colunasDinamicas[i].id))}
                            <td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{l.presenteEm}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
