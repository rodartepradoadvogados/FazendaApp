"use client";
// Paginação client-side (página anterior/próxima + "X de Y") — mesmo espírito
// de useOrdenacao/ThOrdenavel em Ordenavel.tsx: um hook que fatia o array que
// a tela já tem em memória (já filtrado/ordenado) e um componente de rodapé
// para navegar entre as páginas. Substitui os `.slice(0, N)` espalhados pelo
// app, que hoje escondem dado sem nenhum aviso de como ver o resto.
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

const TAMANHOS_PADRAO = [25, 50, 100, 200] as const;

export function usePaginacao<T>(linhas: T[], tamanhoPaginaInicial = 50) {
  const [pagina, setPagina] = useState(1);
  const [tamanhoPagina, setTamanhoPagina] = useState(tamanhoPaginaInicial);

  // Novo filtro/ordenação troca o array (tamanho ou conteúdo) — volta para a
  // página 1 para não deixar o usuário "preso" numa página que ficou vazia.
  useEffect(() => {
    setPagina(1);
  }, [linhas.length]);

  const totalLinhas = linhas.length;
  const totalPaginas = Math.max(1, Math.ceil(totalLinhas / tamanhoPagina));
  const paginaAtual = Math.min(Math.max(1, pagina), totalPaginas);
  const inicio = (paginaAtual - 1) * tamanhoPagina;
  const linhasPagina = linhas.slice(inicio, inicio + tamanhoPagina);

  return {
    linhasPagina,
    pagina: paginaAtual,
    totalPaginas,
    totalLinhas,
    setPagina,
    tamanhoPagina,
    setTamanhoPagina: (n: number) => { setTamanhoPagina(n); setPagina(1); },
  };
}

export function Paginacao({
  pagina, totalPaginas, totalLinhas, tamanhoPagina, onMudarPagina, onMudarTamanho, tamanhos,
}: {
  pagina: number;
  totalPaginas: number;
  totalLinhas: number;
  tamanhoPagina?: number;
  onMudarPagina: (p: number) => void;
  onMudarTamanho?: (n: number) => void;
  tamanhos?: readonly number[];
}) {
  if (totalLinhas === 0) return null;
  return (
    <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem", marginTop: "0.6rem" }}>
      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
        Página {pagina} de {totalPaginas} ({totalLinhas} registro{totalLinhas === 1 ? "" : "s"})
      </span>
      <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
        {onMudarTamanho && (
          <select
            value={tamanhoPagina}
            onChange={(e) => onMudarTamanho(Number(e.target.value))}
            title="Registros por página"
            style={{ background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.25rem 0.4rem", fontSize: "0.72rem" }}
          >
            {(tamanhos || TAMANHOS_PADRAO).map((n) => <option key={n} value={n}>{n} / página</option>)}
          </select>
        )}
        <button
          type="button"
          className="btn-ghost"
          style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.2rem" }}
          onClick={() => onMudarPagina(pagina - 1)}
          disabled={pagina <= 1}
          title="Página anterior"
        >
          <ChevronLeft size={13} /> Anterior
        </button>
        <button
          type="button"
          className="btn-ghost"
          style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem", display: "flex", alignItems: "center", gap: "0.2rem" }}
          onClick={() => onMudarPagina(pagina + 1)}
          disabled={pagina >= totalPaginas}
          title="Próxima página"
        >
          Próxima <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}
