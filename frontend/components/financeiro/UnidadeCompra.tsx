"use client";
// Unidade de compra de um produto do estoque: "direto na unidade do estoque" (ml, kg, saca…) ou numa
// embalagem cadastrada (frasco de 50/100 ml, saca de 30 kg…). Compartilhado pelo lançamento financeiro
// (FormFinanceiro) e pelo lançamento de notas em fatura/lote (FormLancamentoLote): as duas telas mandam
// o mesmo `apresentacao_id` e o backend converte nº de embalagens → unidade do estoque e abre o lote.
import { useCallback, useId, useRef, useState } from "react";
import { fetchEmbalagensEstoque, formatBRL, type ApresentacaoEmbalagemEstoque } from "@/lib/api";
import type { EstoqueItemPicker } from "@/components/EstoquePicker";

/** "frasco" → "frascos", "galão" → "galões", sem nome cadastrado → "embalagens". */
export const pluralEmbalagem = (nome?: string | null) => {
  const n = (nome || "").trim();
  if (!n) return "embalagens";
  return /ão$/i.test(n) ? n.replace(/ão$/i, "ões") : /[sz]$/i.test(n) ? n : n + "s";
};

/** Embalagens ativas por item de estoque (id do estoque → lista), buscadas sob demanda e só uma vez por item. */
export function useEmbalagensEstoque() {
  const [porEstoque, setPorEstoque] = useState<Record<number, ApresentacaoEmbalagemEstoque[]>>({});
  const buscadas = useRef<Set<number>>(new Set());
  const garantir = useCallback((estoqueId: number | null | undefined) => {
    if (!estoqueId || buscadas.current.has(estoqueId)) return;
    buscadas.current.add(estoqueId);
    fetchEmbalagensEstoque(estoqueId)
      .then((l) => setPorEstoque((m) => ({ ...m, [estoqueId]: (l || []).filter((e) => e.ativa !== false).sort((a, b) => a.quantidade - b.quantidade) })))
      .catch(() => { buscadas.current.delete(estoqueId); });
  }, []);
  return { porEstoque, garantir };
}

/** Estoque + embalagens + embalagem escolhida (null = não é produto do estoque). */
export function infoUnidadeCompra(
  est: (EstoqueItemPicker & { id?: number | null }) | undefined | null,
  porEstoque: Record<number, ApresentacaoEmbalagemEstoque[]>,
  apresentacaoId: string,
) {
  if (!est) return null;
  const embs = est.id ? (porEstoque[est.id] || []) : [];
  const emb = embs.find((e) => String(e.id) === apresentacaoId) || null;
  return { est, embs, emb };
}

const campo: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.4rem 0.5rem", fontSize: "0.84rem", minWidth: 0,
};

export function SeletorUnidadeCompra({ info, apresentacaoId, onChange, quantidade, valorTotal, testId }: {
  info: NonNullable<ReturnType<typeof infoUnidadeCompra>>;
  apresentacaoId: string; onChange: (apresentacaoId: string) => void;
  quantidade: number; valorTotal: number; testId?: string;
}) {
  const id = useId();
  const { est, embs, emb } = info;
  const unidEst = est.unidade || "unidade do estoque";
  const nomeEmb = est.unidade_embalagem || "embalagem";
  const medida = (est.medida_embalagem || "").split("/")[0] || unidEst;
  const entra = emb ? quantidade * emb.quantidade : quantidade;
  const saldo = Number(est.quantidade) || 0;
  return (
    <div data-testid={testId} style={{ padding: "0.6rem 0.75rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
      <label htmlFor={id} style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" }}>Comprado em (unidade do produto)</label>
      <select id={id} style={campo} value={apresentacaoId} onChange={(e) => onChange(e.target.value)}
        title="Escolha em que embalagem você comprou. Com embalagem, a quantidade é o número de embalagens e o sistema converte para a unidade do estoque.">
        <option value="">Direto em {unidEst}</option>
        {embs.map((e) => <option key={e.id} value={e.id}>{nomeEmb} de {e.quantidade} {medida}</option>)}
      </select>
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0.35rem 0 0" }}>
        Estoque deste produto em <b>{unidEst}</b> · saldo atual {saldo.toLocaleString("pt-BR")} {unidEst}
        {!embs.length && est.unidade_embalagem && est.quantidade_embalagem
          ? <> · embalagem padrão: {nomeEmb} de {est.quantidade_embalagem} {medida} (nenhum tamanho cadastrado para compra — cadastre em Estoque)</>
          : null}
      </p>
      {emb && (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0.25rem 0 0" }}>
          Digite a quantidade em {pluralEmbalagem(nomeEmb)} e o valor de 1 {nomeEmb}.
        </p>
      )}
      {quantidade > 0 && (
        <p style={{ fontSize: "0.78rem", margin: "0.25rem 0 0" }}>
          {emb
            ? <>{quantidade.toLocaleString("pt-BR")} {nomeEmb}(s) × {emb.quantidade} {medida} = <b>{entra.toLocaleString("pt-BR")} {unidEst}</b> entram no estoque</>
            : <><b>{entra.toLocaleString("pt-BR")} {unidEst}</b> entram no estoque</>}
          {" "}· saldo vai de {saldo.toLocaleString("pt-BR")} para <b>{(saldo + entra).toLocaleString("pt-BR")} {unidEst}</b>
          {entra > 0 && valorTotal > 0 ? <> · custo {formatBRL(valorTotal / entra)}/{unidEst}</> : null}
        </p>
      )}
    </div>
  );
}
