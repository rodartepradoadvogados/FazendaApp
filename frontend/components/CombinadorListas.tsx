"use client";
import { useEffect, useMemo, useState } from "react";
import { Combine, RefreshCw, AlertTriangle } from "lucide-react";
import { fetchCombinadorListas, fetchAgenda, type AnimalCombinador, type CombinadorListasData } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

/**
 * Combinador de Listas — Insights > Listas > Combinador de Listas.
 *
 * Substitui a versão anterior (~12 listas pré-prontas combináveis) por um
 * construtor de PARÂMETROS configuráveis: lote, faixas numéricas (peso,
 * produção, idade, DEL, faltando p/ parto, dias de gestação, dias desde o
 * último serviço), situação produtiva/reprodutiva, categoria etária
 * (vaca/novilha/bezerra), categoria cadastrada (Configurações > Cadastro >
 * Categorias, dinâmica por fazenda) e BST (aptas/a incluir/inaptas).
 *
 * Cada parâmetro ATIVO vira um conjunto de números de animal; a escolha de
 * União/Interseção/Diferença cruza esses conjuntos — mesmo modelo da versão
 * anterior, só que os conjuntos agora são configuráveis em vez de fixos.
 *
 * Fonte dos dados: GET /relatorios/combinador-listas traz os atributos de
 * cada animal (peso, produção, situação etc. — ver
 * fazenda/rules/combinador_listas.py) já prontos, sem recálculo nenhum
 * aqui. O BST continua vindo de GET /agenda/ (bst_elegiveis/
 * bst_nunca_aplicados/bst_excluidos), exatamente como a versão anterior já
 * fazia — não duplicamos o motor da Agenda só para 3 listas que já existem.
 *
 * Resultado vazio NÃO é tratado como erro (o usuário pode legitimamente não
 * achar ninguém), mas o sistema sempre explica qual filtro é o suspeito —
 * ver `diagnosticoVazio()` abaixo e as notas em combinador_listas.py.
 */

type Filtro = { chave: string; rotulo: string; grupo: string; match: (a: AnimalCombinador) => boolean };
type ResultadoUnico = { escolhidos: Filtro[]; linhas: { numero: string; presente_em: string }[] };
type ResultadoDiferenca = { filtro: Filtro; linhas: { numero: string }[] };

const card: React.CSSProperties = { background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem 1.1rem" };
const chip = (ativo: boolean): React.CSSProperties => ({
  display: "inline-flex", alignItems: "center", gap: "0.35rem", padding: "0.35rem 0.7rem", borderRadius: 999,
  border: "1px solid var(--border)", background: ativo ? "var(--pill-active-bg)" : "var(--surface-2)",
  color: ativo ? "var(--pill-active-fg)" : "var(--text)", fontSize: "0.8rem", cursor: "pointer",
});
const label: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: "0.3rem" };
const numInput: React.CSSProperties = { width: 84, padding: "0.3rem 0.45rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--text)", fontSize: "0.8rem" };

function FaixaFiltro({ titulo, unidade, min, max, onMin, onMax }: {
  titulo: string; unidade?: string; min: string; max: string; onMin: (v: string) => void; onMax: (v: string) => void;
}) {
  return (
    <div>
      <p style={label}>{titulo}{unidade ? ` (${unidade})` : ""}</p>
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        <input type="number" placeholder="de" value={min} onChange={(e) => onMin(e.target.value)} style={numInput} />
        <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>até</span>
        <input type="number" placeholder="até" value={max} onChange={(e) => onMax(e.target.value)} style={numInput} />
      </div>
    </div>
  );
}

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

  // Conjuntos BST — reaproveitados de GET /agenda/, sem recalcular nada aqui.
  const bstConjuntos = useMemo(() => {
    if (!agenda) return { apta: new Set<string>(), incluir: new Set<string>(), inapta: new Set<string>() };
    return {
      apta: new Set((agenda.bst_elegiveis || []).map((r: any) => String(r.numero_matriz))),
      incluir: new Set((agenda.bst_nunca_aplicados || []).map((r: any) => String(r.numero_matriz))),
      inapta: new Set((agenda.bst_excluidos || []).map((r: any) => String(r.numero_matriz))),
    };
  }, [agenda]);

  // ── Cada parâmetro ativo vira um Filtro (conjunto de números) ──
  const filtros: Filtro[] = useMemo(() => {
    if (!dados) return [];
    const animais = dados.animais;
    const f: Filtro[] = [];

    if (lotes.length) f.push({
      chave: "lote", grupo: "Lote", rotulo: `Lote: ${lotes.join(", ")}`,
      match: (a) => !!a.lote && lotes.includes(a.lote),
    });
    if (delMin || delMax) f.push({
      chave: "del", grupo: "Faixas", rotulo: `Dias pós-parto ${delMin || "…"}–${delMax || "…"}`,
      match: (a) => dentroFaixa(a.dias_pos_parto, delMin, delMax),
    });
    if (prodMin || prodMax) f.push({
      chave: "producao", grupo: "Faixas", rotulo: `Produção ${prodMin || "…"}–${prodMax || "…"} kg`,
      match: (a) => dentroFaixa(a.producao_kg, prodMin, prodMax),
    });
    if (faltaMin || faltaMax) f.push({
      chave: "falta_parto", grupo: "Faixas", rotulo: `Faltando p/ parto ${faltaMin || "…"}–${faltaMax || "…"}d`,
      match: (a) => dentroFaixa(a.dias_para_parto, faltaMin, faltaMax),
    });
    if (pesoMin || pesoMax) f.push({
      chave: "peso", grupo: "Faixas", rotulo: `Peso ${pesoMin || "…"}–${pesoMax || "…"} kg`,
      match: (a) => dentroFaixa(a.peso_kg, pesoMin, pesoMax),
    });
    if (gestMin || gestMax) f.push({
      chave: "gestacao", grupo: "Faixas", rotulo: `Dias de gestação ${gestMin || "…"}–${gestMax || "…"}`,
      match: (a) => dentroFaixa(a.dias_gestacao, gestMin, gestMax),
    });
    if (servMin || servMax) f.push({
      chave: "servico", grupo: "Faixas", rotulo: `Dias desde o último serviço ${servMin || "…"}–${servMax || "…"}`,
      match: (a) => dentroFaixa(a.dias_desde_servico, servMin, servMax),
    });
    if (idadeMin || idadeMax) {
      const fator = idadeUnidade === "meses" ? 30 : 1;
      const mn = idadeMin ? String(Number(idadeMin) * fator) : "";
      const mx = idadeMax ? String(Number(idadeMax) * fator) : "";
      f.push({
        chave: "idade", grupo: "Faixas", rotulo: `Idade ${idadeMin || "…"}–${idadeMax || "…"} ${idadeUnidade}`,
        match: (a) => dentroFaixa(a.idade_dias, mn, mx),
      });
    }
    if (situacaoProdutiva !== "todas") f.push({
      chave: "sit_produtiva", grupo: "Situação", rotulo: `Situação produtiva: ${situacaoProdutiva === "lactacao" ? "Em lactação" : "Seca"}`,
      match: (a) => a.situacao_produtiva === situacaoProdutiva,
    });
    if (situacaoReprodutiva.length) f.push({
      chave: "sit_reprodutiva", grupo: "Situação",
      rotulo: `Situação reprodutiva: ${situacaoReprodutiva.map((v) => OPCOES_SITUACAO_REPRODUTIVA.find((o) => o.v === v)?.label).join(", ")}`,
      match: (a) => {
        if (!a.situacao_reprodutiva) return false;
        return situacaoReprodutiva.some((v) => v === a.situacao_reprodutiva || (v === "vazia" && a.situacao_reprodutiva === "vazia_atrasada"));
      },
    });
    if (categoriaEtaria.length) f.push({
      chave: "cat_etaria", grupo: "Categoria", rotulo: `Categoria: ${categoriaEtaria.map((v) => OPCOES_CATEGORIA_ETARIA.find((o) => o.v === v)?.label).join(", ")}`,
      match: (a) => !!a.categoria_etaria && categoriaEtaria.includes(a.categoria_etaria),
    });
    if (categoriaCadastro.length) f.push({
      chave: "cat_cadastro", grupo: "Categoria", rotulo: `Categoria cadastrada: ${categoriaCadastro.join(", ")}`,
      match: (a) => !!a.categoria_cadastro && categoriaCadastro.includes(a.categoria_cadastro),
    });
    if (bst.length) {
      const conjuntos = bst.map((v) => (v === "apta" ? bstConjuntos.apta : v === "incluir" ? bstConjuntos.incluir : bstConjuntos.inapta));
      f.push({
        chave: "bst", grupo: "BST",
        rotulo: `BST: ${bst.map((v) => v === "apta" ? "Aptas à aplicação" : v === "incluir" ? "A incluir no próximo lote" : "Inaptas").join(", ")}`,
        match: (a) => conjuntos.some((c) => c.has(a.numero)),
      });
    }
    return f;
  }, [dados, lotes, delMin, delMax, prodMin, prodMax, faltaMin, faltaMax, pesoMin, pesoMax, gestMin, gestMax,
      servMin, servMax, idadeMin, idadeMax, idadeUnidade, situacaoProdutiva, situacaoReprodutiva,
      categoriaEtaria, categoriaCadastro, bst, bstConjuntos]);

  // Conjunto de números por filtro (calculado 1x, reaproveitado no cruzamento e no diagnóstico).
  const conjuntosPorFiltro = useMemo(() => {
    if (!dados) return new Map<string, Set<string>>();
    const m = new Map<string, Set<string>>();
    filtros.forEach((f) => m.set(f.chave, new Set(dados.animais.filter(f.match).map((a) => a.numero))));
    return m;
  }, [dados, filtros]);

  // ── Resultado: só 1 filtro ativo -> mostra ele direto, sem cruzamento ──
  const resultadoUnicoFiltro = useMemo(() => {
    if (filtros.length !== 1) return null;
    const f = filtros[0];
    const ids = Array.from(conjuntosPorFiltro.get(f.chave) || []).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    return { filtro: f, linhas: ids.map((numero) => ({ numero })) };
  }, [filtros, conjuntosPorFiltro]);

  // ── União/Interseção: 2+ filtros ──
  const resultadoUnico: ResultadoUnico | null = useMemo(() => {
    if (filtros.length < 2 || operacao === "diferenca") return null;
    const conjuntos = filtros.map((f) => conjuntosPorFiltro.get(f.chave) || new Set<string>());
    const idsResultado = operacao === "uniao"
      ? new Set(conjuntos.flatMap((c) => Array.from(c)))
      : new Set(Array.from(conjuntos[0]).filter((id) => conjuntos.every((c) => c.has(id))));
    const linhas = Array.from(idsResultado).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map((id) => ({
      numero: id,
      presente_em: filtros.filter((f) => (conjuntosPorFiltro.get(f.chave) || new Set()).has(id)).map((f) => f.rotulo).join(", "),
    }));
    return { escolhidos: filtros, linhas };
  }, [filtros, operacao, conjuntosPorFiltro]);
  const ordResultado = useOrdenacao(resultadoUnico?.linhas ?? []);

  // ── Diferença: uma lista por filtro, exclusiva ──
  const resultadosDiferenca: ResultadoDiferenca[] | null = useMemo(() => {
    if (filtros.length < 2 || operacao !== "diferenca") return null;
    return filtros.map((alvo, idx) => {
      const idsAlvo = conjuntosPorFiltro.get(alvo.chave) || new Set<string>();
      const idsOutras = new Set(filtros.filter((_, i) => i !== idx).flatMap((f) => Array.from(conjuntosPorFiltro.get(f.chave) || [])));
      const linhas = Array.from(idsAlvo).filter((id) => !idsOutras.has(id))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map((id) => ({ numero: id }));
      return { filtro: alvo, linhas };
    });
  }, [filtros, operacao, conjuntosPorFiltro]);

  // ── Diagnóstico de resultado vazio (só faz sentido em união/interseção) ──
  const diagnostico = useMemo(() => {
    if (operacao === "diferenca" || filtros.length < 2) return null;
    if (!resultadoUnico || resultadoUnico.linhas.length > 0) return null;
    // 1) algum filtro, sozinho, já não acha ninguém?
    const semAnimais = filtros.filter((f) => (conjuntosPorFiltro.get(f.chave)?.size ?? 0) === 0);
    if (semAnimais.length) {
      return `Sozinho(s), ${semAnimais.length > 1 ? "estes filtros" : "este filtro"} já não encontra(m) nenhum animal: `
        + semAnimais.map((f) => `"${f.rotulo}"`).join(", ")
        + ". Confira se os valores/opções estão corretos.";
    }
    // 2) união também vazia (bizarro, mas possível se algum filtro conflitasse consigo)
    // 3) interseção: achar o primeiro par cuja interseção pareada já é vazia.
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

  return (
    <div style={{ display: "grid", gap: "1rem" }}>
      <div style={card}>
        <div className="flex items-center justify-between" style={{ marginBottom: "0.7rem" }}>
          <div className="flex items-center gap-2" style={{ fontWeight: 700, fontSize: "0.95rem" }}>
            <Combine size={16} style={{ color: "var(--accent-icon)" }} /> Combinador de listas
          </div>
          <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={carregar}><RefreshCw size={13} /> Atualizar</button>
        </div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.9rem" }}>
          Configure um ou mais parâmetros para filtrar o rebanho. Com 2 ou mais parâmetros ativos, escolha como cruzá-los.
        </p>

        <div style={{ display: "grid", gap: "0.9rem", gridTemplateColumns: "repeat(auto-fill, minmax(232px, 1fr))" }}>
          <div>
            <p style={label}>Lote</p>
            <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
              {dados.lotes.map((l) => (
                <button key={l} type="button" style={chip(lotes.includes(l))} onClick={() => toggleEm(lotes, setLotes, l)}>{l}</button>
              ))}
              {dados.lotes.length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Nenhum lote cadastrado.</span>}
            </div>
          </div>
          <FaixaFiltro titulo="Dias pós-parto (DEL)" min={delMin} max={delMax} onMin={setDelMin} onMax={setDelMax} />
          <FaixaFiltro titulo="Produção" unidade="kg" min={prodMin} max={prodMax} onMin={setProdMin} onMax={setProdMax} />
          <FaixaFiltro titulo="Faltando para o parto" unidade="dias" min={faltaMin} max={faltaMax} onMin={setFaltaMin} onMax={setFaltaMax} />
          <FaixaFiltro titulo="Peso" unidade="kg" min={pesoMin} max={pesoMax} onMin={setPesoMin} onMax={setPesoMax} />
          <FaixaFiltro titulo="Dias de gestação" min={gestMin} max={gestMax} onMin={setGestMin} onMax={setGestMax} />
          <FaixaFiltro titulo="Dias desde o último serviço/IA/monta" min={servMin} max={servMax} onMin={setServMin} onMax={setServMax} />
          <div>
            <p style={label}>Idade</p>
            <div className="flex items-center gap-2" style={{ marginBottom: "0.3rem" }}>
              {(["dias", "meses"] as const).map((u) => (
                <button key={u} type="button" style={{ ...chip(idadeUnidade === u), fontSize: "0.72rem", padding: "0.2rem 0.5rem" }} onClick={() => setIdadeUnidade(u)}>{u}</button>
              ))}
            </div>
            <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
              <input type="number" placeholder="de" value={idadeMin} onChange={(e) => setIdadeMin(e.target.value)} style={numInput} />
              <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>até</span>
              <input type="number" placeholder="até" value={idadeMax} onChange={(e) => setIdadeMax(e.target.value)} style={numInput} />
            </div>
          </div>
        </div>

        <div style={{ marginTop: "0.9rem" }}>
          <p style={label}>Situação produtiva</p>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            {([["todas", "Ambas"], ["lactacao", "Em lactação"], ["seca", "Seca"]] as const).map(([v, l]) => (
              <button key={v} type="button" style={chip(situacaoProdutiva === v)} onClick={() => setSituacaoProdutiva(v)}>{l}</button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: "0.9rem" }}>
          <p style={label}>Situação reprodutiva (marque uma ou mais)</p>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            {OPCOES_SITUACAO_REPRODUTIVA.map((o) => (
              <button key={o.v} type="button" style={chip(situacaoReprodutiva.includes(o.v))} onClick={() => toggleEm(situacaoReprodutiva, setSituacaoReprodutiva, o.v)}>{o.label}</button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: "0.9rem" }}>
          <p style={label}>Categoria (marque uma ou mais)</p>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            {OPCOES_CATEGORIA_ETARIA.map((o) => (
              <button key={o.v} type="button" style={chip(categoriaEtaria.includes(o.v))} onClick={() => toggleEm(categoriaEtaria, setCategoriaEtaria, o.v)}>{o.label}</button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: "0.9rem" }}>
          <p style={label}>Categoria cadastrada — Configurações &gt; Cadastro &gt; Categorias (opcional, marque uma ou mais)</p>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            {dados.categorias_cadastro.map((c) => (
              <button key={c.id} type="button" style={chip(categoriaCadastro.includes(c.nome))} onClick={() => toggleEm(categoriaCadastro, setCategoriaCadastro, c.nome)}>{c.nome}</button>
            ))}
            {dados.categorias_cadastro.length === 0 && <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Nenhuma categoria cadastrada.</span>}
          </div>
        </div>

        <div style={{ marginTop: "0.9rem" }}>
          <p style={label}>BST (marque uma ou mais)</p>
          <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
            {([["apta", "Aptas à aplicação"], ["incluir", "A incluir no próximo lote"], ["inapta", "Inaptas"]] as const).map(([v, l]) => (
              <button key={v} type="button" style={chip(bst.includes(v))} onClick={() => toggleEm(bst, setBst, v)}>{l}</button>
            ))}
          </div>
        </div>

        {filtros.length >= 2 && (
          <div className="flex items-center gap-3 mt-3" style={{ flexWrap: "wrap", marginTop: "1rem" }}>
            <label style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Cruzamento:</label>
            {([
              { v: "uniao", label: "União (está em qualquer um)" },
              { v: "intersecao", label: "Interseção (está em todos)" },
              { v: "diferenca", label: "Diferença (exclusivo de cada filtro)" },
            ] as const).map((op) => (
              <button key={op.v} type="button" style={chip(operacao === op.v)} onClick={() => setOperacao(op.v)}>{op.label}</button>
            ))}
          </div>
        )}
      </div>

      {filtros.length === 0 ? (
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Configure ao menos 1 parâmetro para ver o resultado.</p>
      ) : filtros.length === 1 && resultadoUnicoFiltro ? (
        <div style={card}>
          <div className="flex items-center justify-between mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{resultadoUnicoFiltro.linhas.length} animal(is) — {resultadoUnicoFiltro.filtro.rotulo}</span>
            <ExportarBotoes
              titulo={`Combinador de listas — ${resultadoUnicoFiltro.filtro.rotulo}`}
              colunas={[{ header: "Número", key: "numero" }]}
              linhas={resultadoUnicoFiltro.linhas}
              nomeArquivoBase="combinador_listas"
            />
          </div>
          {resultadoUnicoFiltro.linhas.length === 0 ? (
            <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Nenhum animal atende a este parâmetro. Confira se o valor/opção está correto.</p>
          ) : (
            <div style={{ overflowX: "auto", maxHeight: 360, overflowY: "auto" }}>
              <table className="fazenda-table">
                <thead><tr><th>Número</th></tr></thead>
                <tbody>{resultadoUnicoFiltro.linhas.map((l) => <tr key={l.numero}><td>{l.numero}</td></tr>)}</tbody>
              </table>
            </div>
          )}
        </div>
      ) : operacao === "diferenca" ? (
        resultadosDiferenca && (
          <div style={{ display: "grid", gap: "1rem" }}>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Diferença calcula, para cada parâmetro selecionado, quem está só nele e em nenhum dos outros —
              {resultadosDiferenca.length} tabela(s) abaixo, uma por parâmetro. Um resultado com 0 aqui é normal:
              significa que os animais desse filtro também aparecem em outro filtro selecionado.
            </p>
            {resultadosDiferenca.map((r) => (
              <div key={r.filtro.chave} style={card}>
                <div className="flex items-center justify-between mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>
                    Só em "{r.filtro.rotulo}" ({r.linhas.length}) <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>— não está em nenhum dos outros selecionados</span>
                  </span>
                  <ExportarBotoes
                    titulo={`Diferença — só em ${r.filtro.rotulo}`}
                    colunas={[{ header: "Número", key: "numero" }]}
                    linhas={r.linhas}
                    nomeArquivoBase={`combinador_diferenca_${r.filtro.chave}`}
                  />
                </div>
                {r.linhas.length === 0 ? (
                  <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Nenhum animal exclusivo deste filtro.</p>
                ) : (
                  <div style={{ overflowX: "auto", maxHeight: 260, overflowY: "auto" }}>
                    <table className="fazenda-table">
                      <thead><tr><th>Número</th></tr></thead>
                      <tbody>{r.linhas.map((l) => <tr key={l.numero}><td>{l.numero}</td></tr>)}</tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
          </div>
        )
      ) : (
        resultadoUnico && (
          <div style={card}>
            <div className="flex items-center justify-between mb-2" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
              <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{resultadoUnico.linhas.length} animal(is) no resultado</span>
              <ExportarBotoes
                titulo={`Combinador de listas — ${operacao}`}
                colunas={[{ header: "Número", key: "numero" }, { header: "Presente em", key: "presente_em" }]}
                linhas={resultadoUnico.linhas}
                nomeArquivoBase="combinador_listas"
              />
            </div>
            {resultadoUnico.linhas.length === 0 ? (
              <div className="flex items-start gap-2" style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.7rem 0.85rem" }}>
                <AlertTriangle size={16} style={{ color: "var(--amber, #b45309)", flexShrink: 0, marginTop: 2 }} />
                <p style={{ fontSize: "0.82rem" }}>
                  Nenhum animal atende ao cruzamento escolhido. {diagnostico}
                </p>
              </div>
            ) : (
              <div style={{ overflowX: "auto", maxHeight: 360, overflowY: "auto" }}>
                <table className="fazenda-table">
                  <thead><tr>
                    <ThOrdenavel label="Número" campo="numero" coluna={ordResultado.coluna} dir={ordResultado.dir} ordenar={ordResultado.ordenar} />
                    <ThOrdenavel label="Presente em" campo="presente_em" coluna={ordResultado.coluna} dir={ordResultado.dir} ordenar={ordResultado.ordenar} />
                  </tr></thead>
                  <tbody>
                    {ordResultado.linhasOrdenadas.map((r) => (
                      <tr key={r.numero}><td>{r.numero}</td><td style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>{r.presente_em}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )
      )}
    </div>
  );
}
