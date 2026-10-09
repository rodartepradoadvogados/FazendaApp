"use client";
// Peças comuns das telas de Registros (Fase C2): a busca (número do animal,
// documento, GTA, touro, vendedor) guardada na URL (?busca=, link
// compartilhável e Voltar funciona), a tabela ordenável e o selo da natureza.
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { ArrowDown, ArrowUp, Search, X } from "lucide-react";
import { seloNatureza, type BuscaRegistro, type Natureza } from "@/lib/relatorioRegistros";
import { useDetalheNaUrl } from "./useContextoRelatorio";

export function useBuscaNaUrl(): [BuscaRegistro, (b: BuscaRegistro) => void] {
  const [txt, abrir] = useDetalheNaUrl("busca");
  const busca = useMemo(() => Object.fromEntries(new URLSearchParams(txt)) as BuscaRegistro, [txt]);
  const mudar = (b: BuscaRegistro) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(b)) if (v && v.trim()) q.set(k, v.trim());
    abrir(q.toString());
  };
  return [busca, mudar];
}

export function FormBusca({ campos, valor, onBuscar, nota }: {
  campos: { chave: keyof BuscaRegistro; rotulo: string; dica?: string }[]; valor: BuscaRegistro; onBuscar: (b: BuscaRegistro) => void; nota: ReactNode;
}) {
  const [rasc, setRasc] = useState<BuscaRegistro>(valor);
  const [ultimo, setUltimo] = useState(valor);
  if (ultimo !== valor) { setUltimo(valor); setRasc(valor); } // a URL mudou (Voltar): o formulário acompanha
  const enviar = (e: FormEvent) => { e.preventDefault(); onBuscar(rasc); };
  const ativa = Object.values(valor).some((v) => v && v.trim());
  return (
    <form className="rl-painel rl-noprint" role="search" aria-label="Buscar nos registros" onSubmit={enviar}>
      <div className="rl-busca">
        {campos.map((c) => (
          <div key={c.chave} className="rl-campo">
            <label htmlFor={`rl-busca-${c.chave}`}>{c.rotulo}</label>
            <input id={`rl-busca-${c.chave}`} className="rl-in" value={rasc[c.chave] ?? ""} placeholder={c.dica}
              onChange={(e) => setRasc((r) => ({ ...r, [c.chave]: e.target.value }))} />
          </div>
        ))}
        <button type="submit" className="rl-btn"><Search size={14} aria-hidden /> Buscar</button>
        {ativa && <button type="button" className="rl-btn" onClick={() => { setRasc({}); onBuscar({}); }}><X size={14} aria-hidden /> Limpar a busca</button>}
      </div>
      <p className="rl-hint">{nota}</p>
    </form>
  );
}

export function SeloNatureza({ n, rotulo }: { n: Natureza | null; rotulo: string }) {
  const s = seloNatureza(n);
  return <span className={`rl-selo${s.investimento ? " inv" : ""}`} title={rotulo}>{s.texto}</span>;
}

export type Coluna<T> = { chave: string; rotulo: string; num?: boolean; opc?: boolean; valor: (l: T) => string | number; celula?: (l: T) => ReactNode };

/** Tabela ordenável (clique no cabeçalho: crescente → decrescente), com aria-sort. */
export function TabelaOrdenavel<T>({ titulo, colunas, linhas, chaveLinha, onAbrir, rotuloAbrir, rodape, vazio }: {
  titulo: string; colunas: Coluna<T>[]; linhas: T[]; chaveLinha: (l: T, i: number) => string;
  onAbrir?: (l: T) => void; rotuloAbrir?: (l: T) => string; rodape?: ReactNode; vazio: string;
}) {
  const [ordem, setOrdem] = useState<{ chave: string; dir: 1 | -1 } | null>(null);
  const ordenadas = useMemo(() => {
    if (!ordem) return linhas;
    const col = colunas.find((c) => c.chave === ordem.chave);
    if (!col) return linhas;
    return [...linhas].sort((a, b) => {
      const x = col.valor(a), y = col.valor(b);
      const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "pt-BR", { numeric: true, sensitivity: "base" });
      return c * ordem.dir;
    });
  }, [linhas, ordem, colunas]);
  return (
    <div className="rl-tw">
      <table className="fazenda-table rl-tab rl-nw">
        <caption className="rl-sr">{titulo}</caption>
        <thead><tr>{colunas.map((c) => {
          const ativa = ordem?.chave === c.chave;
          return (
            <th key={c.chave} scope="col" className={[c.num ? "r" : "", c.opc ? "rl-opc" : ""].filter(Boolean).join(" ") || undefined}
              aria-sort={ativa ? (ordem!.dir === 1 ? "ascending" : "descending") : "none"}>
              <button type="button" className="ord" onClick={() => setOrdem(ativa ? { chave: c.chave, dir: ordem!.dir === 1 ? -1 : 1 } : { chave: c.chave, dir: 1 })}>
                {c.rotulo}{ativa && (ordem!.dir === 1 ? <ArrowUp size={12} aria-hidden /> : <ArrowDown size={12} aria-hidden />)}
              </button>
            </th>
          );
        })}</tr></thead>
        <tbody>
          {ordenadas.map((l, i) => (
            <tr key={chaveLinha(l, i)} className={onAbrir ? "clic" : undefined}
              onClick={onAbrir ? (e) => { if (!(e.target as HTMLElement).closest("button")) onAbrir(l); } : undefined}>
              {colunas.map((c, j) => (
                <td key={c.chave} className={[c.num ? "r" : "", c.opc ? "rl-opc" : ""].filter(Boolean).join(" ") || undefined}>
                  {j === 0 && onAbrir ? (
                    <button type="button" className="rl-linkbtn" onClick={() => onAbrir(l)} aria-label={rotuloAbrir?.(l)}>{c.celula ? c.celula(l) : c.valor(l)}</button>
                  ) : c.celula ? c.celula(l) : c.valor(l)}
                </td>
              ))}
            </tr>
          ))}
          {!ordenadas.length && <tr><td colSpan={colunas.length} className="mut">{vazio}</td></tr>}
        </tbody>
        {rodape && <tfoot>{rodape}</tfoot>}
      </table>
    </div>
  );
}
