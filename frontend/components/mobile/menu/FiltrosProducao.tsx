"use client";
// Filtros comuns das 5 telas de Menu › Produção (Controles, Qualidade,
// Secagens, BST, Pesagens) — espec aprovada pelo dono em out/2026:
//  - período padrão = últimos 60 dias; início > fim avisa e NÃO consulta;
//  - escopo: rebanho todo / lote(s) (pílulas de seleção múltipla, as mesmas
//    de Rebanho › Movimentar) / animal(is) por número EXATO (antes a busca
//    era por substring: "12" trazia 112, 120…);
//  - os filtros vão para o SERVIDOR (lib/api.ts::qsFiltrosProducao) — o lote é
//    o do animal NA DATA do registro (backend rules/lote_historico.py);
//  - `rotulo` descreve os filtros em texto, para o cabeçalho do Excel/PDF;
//  - agrupamento por lote (bloco com nº de vacas e média no topo) quando a
//    pessoa escolhe lote(s).
import { useMemo, useState, type ReactNode } from "react";
import { Search, X } from "lucide-react";
import { MobCard } from "@/components/mobile/ui";
import { FiltroPeriodo, periodoInvertido } from "@/components/mobile/menu/comum";
import { PilulaLote, PilulasLote } from "@/components/mobile/lancar/lote/SelecaoLote";
import { useCache } from "@/components/mobile/lancar/comum";
import { diasAtras, fetchAnimais, fetchLotes, formatDate, today } from "@/lib/api";
import { comparaNumero, rotuloDoLote, type AnimalMovivel, type LoteBasico } from "@/lib/lancamentoLote";
import { normalizarBusca } from "@/lib/busca";

export const DIAS_PERIODO_PADRAO = 60;

export type Escopo = "rebanho" | "lotes" | "animais";

type LoteCadastro = LoteBasico & { ativo?: boolean };

/** Código do lote a partir do rótulo "01 - Alta" (mesma regra do backend). */
export function codigoDoLote(rotulo: string | null | undefined): string {
  return (rotulo || "").split(" - ")[0].trim();
}

export function useFiltrosProducao(opcoes?: { escopoInicial?: Escopo; rotuloRebanho?: string }) {
  const [inicio, setInicio] = useState(() => diasAtras(DIAS_PERIODO_PADRAO));
  const [fim, setFim] = useState(today);
  const [escopo, setEscopo] = useState<Escopo>(opcoes?.escopoInicial ?? "rebanho");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [animaisSel, setAnimaisSel] = useState<string[]>([]);
  // Mesmas chaves de cache de Rebanho › Movimentar — funcionam offline com a última cópia.
  const { dados: lotesCadastro } = useCache<LoteCadastro[]>("lotes", () => fetchLotes(), []);
  const { dados: animaisCadastro } = useCache<AnimalMovivel[]>("animais_todos", () => fetchAnimais({ incluirMachos: true }), []);

  const periodoValido = !periodoInvertido(inicio, fim);
  const lotesAplicados = escopo === "lotes" ? [...lotesSel].sort(comparaNumero) : [];
  const animaisAplicados = escopo === "animais" ? [...animaisSel].sort(comparaNumero) : [];
  // "Lote(s)" ou "Animal(is)" sem nada marcado = ainda escolhendo: não consulta.
  const escopoPronto = escopo === "rebanho" || (escopo === "lotes" ? lotesSel.length > 0 : animaisSel.length > 0);

  const params = {
    data_inicio: inicio || undefined,
    data_fim: fim || undefined,
    lotes: lotesAplicados.length ? lotesAplicados : undefined,
    numeros: animaisAplicados.length ? animaisAplicados : undefined,
  };

  const nomeLote = (codigo: string) => {
    const l = (Array.isArray(lotesCadastro) ? lotesCadastro : []).find((x) => x.codigo === codigo);
    return l ? rotuloDoLote(l) : codigo;
  };
  const partesRotulo = [
    inicio || fim ? `Período: ${inicio ? formatDate(inicio) : "início"} a ${fim ? formatDate(fim) : "hoje"}` : "Período: todo o histórico",
    escopo === "rebanho" ? (opcoes?.rotuloRebanho ?? "Rebanho todo")
      : escopo === "lotes" ? `Lote${lotesAplicados.length > 1 ? "s" : ""}: ${lotesAplicados.map(nomeLote).join(", ") || "—"} (lote na data do registro)`
        : `Anima${animaisAplicados.length > 1 ? "is" : "l"}: ${animaisAplicados.join(", ") || "—"}`,
  ];

  return {
    inicio, setInicio, fim, setFim, escopo, setEscopo, lotesSel, setLotesSel, animaisSel, setAnimaisSel,
    lotesCadastro: Array.isArray(lotesCadastro) ? lotesCadastro : [],
    animaisCadastro: Array.isArray(animaisCadastro) ? animaisCadastro : [],
    periodoValido, escopoPronto, params, partesRotulo,
    agrupar: escopo === "lotes",
  };
}

export type FiltrosProducao = ReturnType<typeof useFiltrosProducao>;

const ROTULO_ESCOPO: Record<Escopo, string> = { rebanho: "Rebanho", lotes: "Lote(s)", animais: "Animal(is)" };

/** Painel de filtros: período + escopo (rebanho / lotes / animais) + extras da tela. */
export function PainelFiltros({ f, rotuloRebanho = "Rebanho todo", mostrarEscopo = true, children }: {
  f: FiltrosProducao; rotuloRebanho?: string; mostrarEscopo?: boolean; children?: ReactNode;
}) {
  const lotesAtivos = useMemo(
    () => f.lotesCadastro.filter((l) => l.ativo !== false).sort((a, b) => comparaNumero(a.codigo, b.codigo)),
    [f.lotesCadastro],
  );
  return (
    <div className="lote" style={{ paddingBottom: 0, marginBottom: "0.4rem" }}>
      <FiltroPeriodo inicio={f.inicio} fim={f.fim} onInicio={f.setInicio} onFim={f.setFim} />
      {children && <div style={{ marginBottom: "0.2rem" }}>{children}</div>}
      {mostrarEscopo && (<>
      <div role="group" aria-label="Escopo" className="lote-seg" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        {(Object.keys(ROTULO_ESCOPO) as Escopo[]).map((e) => (
          <button key={e} type="button" className="lote-btn-ft" aria-pressed={f.escopo === e} onClick={() => f.setEscopo(e)}
            style={{ minHeight: 48 }}>
            {e === "rebanho" ? rotuloRebanho : ROTULO_ESCOPO[e]}
          </button>
        ))}
      </div>
      {f.escopo === "lotes" && (
        lotesAtivos.length ? (
          <PilulasLote>
            {lotesAtivos.map((l) => (
              <PilulaLote key={l.codigo} ativa={f.lotesSel.includes(l.codigo)}
                onClick={() => f.setLotesSel((p) => (p.includes(l.codigo) ? p.filter((c) => c !== l.codigo) : [...p, l.codigo]))}>
                {rotuloDoLote(l)}
              </PilulaLote>
            ))}
          </PilulasLote>
        ) : <p className="lote-nota">Nenhum lote cadastrado (ou ainda sem cópia offline).</p>
      )}
      {f.escopo === "animais" && (
        <SeletorAnimais animais={f.animaisCadastro} selecionados={f.animaisSel} onChange={f.setAnimaisSel} />
      )}
      {f.escopo !== "rebanho" && !f.escopoPronto && (
        <p className="lote-nota">Escolha {f.escopo === "lotes" ? "ao menos um lote" : "ao menos um animal"} para ver o relatório.</p>
      )}
      </>)}
    </div>
  );
}

/** Seleção EXATA de um ou mais animais: a busca só filtra a lista; só o toque
 * num animal o seleciona (nunca texto livre). */
export function SeletorAnimais({ animais, selecionados, onChange }: {
  animais: AnimalMovivel[]; selecionados: string[]; onChange: (v: string[]) => void;
}) {
  const [q, setQ] = useState("");
  const lista = useMemo(() => {
    const termo = normalizarBusca(q);
    return animais
      .filter((a) => !a.eh_semen && !selecionados.includes(a.numero))
      .filter((a) => !termo || normalizarBusca(`${a.numero} ${a.nome || ""}`).includes(termo))
      .sort((a, b) => {
        // Número exato digitado vem primeiro ("12" antes de "112").
        if (termo && normalizarBusca(a.numero) === termo) return -1;
        if (termo && normalizarBusca(b.numero) === termo) return 1;
        return comparaNumero(a.numero, b.numero);
      })
      .slice(0, 20);
  }, [animais, q, selecionados]);
  return (
    <div style={{ marginTop: "0.6rem" }}>
      {selecionados.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.5rem" }}>
          {selecionados.map((n) => (
            <button key={n} type="button" className="mob-pill ativa" onClick={() => onChange(selecionados.filter((x) => x !== n))}
              aria-label={`Tirar o animal ${n}`} style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
              Nº {n} <X size={14} aria-hidden="true" />
            </button>
          ))}
        </div>
      )}
      <div style={{ position: "relative" }}>
        <Search size={17} aria-hidden="true" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)", pointerEvents: "none" }} />
        <input className="mob-input" value={q} onChange={(e) => setQ(e.target.value)} inputMode="search"
          placeholder="Buscar nº do animal e tocar para escolher…" aria-label="Buscar animal" style={{ paddingLeft: "2.5rem" }} />
      </div>
      {q && (
        <div style={{ marginTop: "0.4rem", display: "grid", gap: "0.35rem", maxHeight: "40vh", overflowY: "auto" }}>
          {lista.map((a) => (
            <button key={a.numero} type="button" className="mob-btn-2" style={{ justifyContent: "flex-start", textAlign: "left", padding: "0.6rem 0.9rem" }}
              onClick={() => { onChange([...selecionados, a.numero]); setQ(""); }}>
              <span><strong>{a.numero}</strong>{a.grupo_primario ? ` · ${a.grupo_primario}` : ""}</span>
            </button>
          ))}
          {lista.length === 0 && <p style={{ color: "var(--mob-muted)", fontSize: "0.88rem" }}>Nenhum animal com esse número.</p>}
        </div>
      )}
    </div>
  );
}

/** Seletor compacto de opções exclusivas (ex.: Tanque/Individual, origem do BST). */
export function OpcoesFiltro<T extends string>({ rotulo, opcoes, valor, onChange }: {
  rotulo: string; opcoes: { v: T; l: string }[]; valor: T; onChange: (v: T) => void;
}) {
  return (
    <div style={{ marginBottom: "0.7rem" }}>
      <span style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" }}>{rotulo}</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
        {opcoes.map((o) => (
          <button key={o.v} type="button" className={`mob-pill${valor === o.v ? " ativa" : ""}`} aria-pressed={valor === o.v} onClick={() => onChange(o.v)}>
            {o.l}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Agrupamento por lote ─────────────────────────────────────────────────────
export type BlocoLote<T> = { lote: string; linhas: T[]; vacas: number; media: number | null };

/** Agrupa as linhas pelo lote NA DATA (bloco por lote), com nº de vacas
 * distintas e a média de `valorDe` no bloco. Ordem: código do lote. */
export function agruparPorLote<T>(
  linhas: T[], loteDe: (l: T) => string | null | undefined, numeroDe: (l: T) => string,
  valorDe?: (l: T) => number | null | undefined,
): BlocoLote<T>[] {
  const mapa = new Map<string, T[]>();
  for (const l of linhas) {
    const k = loteDe(l) || "Sem lote";
    (mapa.get(k) ?? mapa.set(k, []).get(k)!).push(l);
  }
  return [...mapa.entries()]
    .sort(([a], [b]) => comparaNumero(codigoDoLote(a), codigoDoLote(b)))
    .map(([lote, ls]) => {
      const valores = valorDe ? ls.map(valorDe).filter((v): v is number => v != null) : [];
      return {
        lote, linhas: ls, vacas: new Set(ls.map(numeroDe)).size,
        media: valores.length ? valores.reduce((s, v) => s + v, 0) / valores.length : null,
      };
    });
}

export function fmtNum(v?: number | null, casas = 1): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}

/** Cabeçalho do bloco de um lote: nome, nº de vacas e a média no topo. */
export function CabecalhoBloco({ lote, vacas, detalhe }: { lote: string; vacas: number; detalhe?: ReactNode }) {
  return (
    <MobCard style={{ margin: "0.9rem 0 0.5rem", display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem",
      borderLeft: "4px solid var(--mob-dourado-2, #8A6D2F)" }}>
      <span style={{ fontWeight: 800, fontSize: "0.98rem" }}>Lote {lote}</span>
      <span style={{ fontSize: "0.82rem", color: "var(--mob-muted)", fontWeight: 700, textAlign: "right" }}>
        {vacas} {vacas === 1 ? "vaca" : "vacas"}{detalhe ? <> · {detalhe}</> : null}
      </span>
    </MobCard>
  );
}

/** "Lote 01 - Alta" + aviso discreto quando é o lote ATUAL (sem histórico da época). */
export function LoteNaData({ lote, fonte }: { lote?: string | null; fonte?: string | null }) {
  if (!lote) return <>Sem lote</>;
  return (
    <>
      Lote {lote}
      {fonte === "atual" && <span title="Sem histórico de movimentação — mostrando o lote de hoje" style={{ opacity: 0.75, fontStyle: "italic" }}> (lote atual)</span>}
    </>
  );
}

/** Rótulo de lote para Excel/PDF (com a mesma marca de "lote atual"). */
export function textoLote(lote?: string | null, fonte?: string | null): string {
  if (!lote) return "Sem lote";
  return fonte === "atual" ? `${lote} (lote atual)` : lote;
}

/** Lista plana ou em blocos por lote (quando a pessoa escolheu lote(s)). */
export function ListaPorLote<T>({ agrupar, linhas, loteDe, numeroDe, valorDe, detalheBloco, render }: {
  agrupar: boolean; linhas: T[];
  loteDe: (l: T) => string | null | undefined; numeroDe: (l: T) => string;
  valorDe?: (l: T) => number | null | undefined;
  detalheBloco?: (b: BlocoLote<T>) => ReactNode;
  render: (l: T, i: number) => ReactNode;
}) {
  if (!agrupar) return <>{linhas.map(render)}</>;
  return (
    <>
      {agruparPorLote(linhas, loteDe, numeroDe, valorDe).map((b) => (
        <section key={b.lote} aria-label={`Lote ${b.lote}`}>
          <CabecalhoBloco lote={b.lote} vacas={b.vacas} detalhe={detalheBloco?.(b)} />
          {b.linhas.map(render)}
        </section>
      ))}
    </>
  );
}

/** Aviso de cópia offline que é de OUTROS filtros (a cópia é uma por tela). */
export function AvisoCopiaOutroFiltro({ rotulo }: { rotulo?: string }) {
  return (
    <p role="status" style={{ fontSize: "0.8rem", color: "var(--mob-ambar)", fontWeight: 700, margin: "0 0 0.8rem" }}>
      Sem conexão: mostrando a última cópia salva, que é de outros filtros{rotulo ? ` (${rotulo})` : ""}.
    </p>
  );
}
