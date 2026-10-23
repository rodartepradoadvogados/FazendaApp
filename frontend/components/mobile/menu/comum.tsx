"use client";
// Peças compartilhadas pelas sub-telas do Menu (todas SÓ LEITURA):
//  - useCarregar: leitura com cache offline (fetchComCache) + estados prontos.
//  - AvisoCopia: aviso discreto "Cópia de <data>" quando os dados vieram do cache.
//  - Carregando / Vazio: estados simpáticos.
//  - Bolinha/corSemaforo: semáforo (vermelho/amarelo/verde/branco) dos relatórios.
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { BarChart3, ChevronLeft, ChevronRight, CircleAlert, type LucideIcon } from "lucide-react";
import { fetchComCache, cacheEm } from "@/lib/offline";
export { usePaginacao } from "@/components/Paginacao";

export function fmtCacheEm(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** Resposta que chegou depois de uma busca mais nova já ter saído — descartada (ver useCarregar). */
class RespostaAntiga extends Error {}

/** Marcas que useCarregar grava junto da resposta quando a tela tem filtros:
 * a cópia offline é UMA por tela (chave fixa), então ela precisa dizer de
 * quais filtros é — senão, offline, a tela mostraria dados de outro filtro
 * como se fossem do filtro escolhido. */
export type MarcaFiltros = { _assinatura?: string; _rotuloFiltros?: string };

/** Leitura com cache: online atualiza; offline devolve a última cópia salva.
 *
 * `opcoes` (telas com filtro no servidor, ex.: Menu › Produção):
 *  - `assinatura`: muda quando os filtros mudam → busca de novo, mantendo a
 *    MESMA chave de cache (só o último resultado da tela fica guardado — antes
 *    a tela de Pesagens criava uma chave por período e nunca apagava nenhuma);
 *  - `habilitado: false` não consulta (ex.: período invertido);
 *  - `rotulo`: texto dos filtros, guardado junto da cópia offline.
 * Resposta que chega fora de ordem (o usuário trocou o filtro antes da
 * anterior voltar) é DESCARTADA — nem aparece na tela nem sobrescreve o cache.
 * `mensagemErro` traz o motivo real da falha online (antes a tela engolia). */
export function useCarregar<T>(
  chave: string, buscar: () => Promise<T>,
  opcoes?: { assinatura?: string; habilitado?: boolean; rotulo?: string },
) {
  const [dados, setDados] = useState<(T & MarcaFiltros) | null>(null);
  const [doCache, setDoCache] = useState(false);
  // Qual leitura (chave + assinatura) terminou por último — "carregando" é
  // derivado disso, sem setState síncrono dentro do efeito.
  const [concluida, setConcluida] = useState<string | null>(null);
  const [erro, setErro] = useState(false);
  const [mensagemErro, setMensagemErro] = useState<string | null>(null);
  const sequencia = useRef(0);
  const assinatura = opcoes?.assinatura;
  const habilitado = opcoes?.habilitado ?? true;
  const rotulo = opcoes?.rotulo;

  const carregar = useCallback(async () => {
    const minha = ++sequencia.current;
    // Desabilitado (ex.: período invertido): só invalida a busca em voo; o
    // `carregando` devolvido abaixo já sai falso.
    if (!habilitado) return;
    const leitura = `${chave}|${assinatura ?? ""}`;
    let falha: string | null = null;
    const r = await fetchComCache<T & MarcaFiltros>(chave, async () => {
      let resposta: T;
      try {
        resposta = await buscar();
      } catch (e) {
        falha = e instanceof Error ? e.message : "erro desconhecido";
        throw e;
      }
      if (minha !== sequencia.current) throw new RespostaAntiga();
      return (assinatura !== undefined && resposta && typeof resposta === "object" && !Array.isArray(resposta)
        ? { ...resposta, _assinatura: assinatura, _rotuloFiltros: rotulo }
        : resposta) as T & MarcaFiltros;
    });
    if (minha !== sequencia.current) return;
    setDados(r.dados);
    setDoCache(r.doCache);
    // fetchComCache engole o erro e cai no cache; se falhou ONLINE é erro real
    // (servidor fora / 403 / filtro recusado), não "offline".
    const online = typeof navigator !== "undefined" && navigator.onLine;
    setErro(r.doCache && online);
    setMensagemErro(r.doCache && online ? (falha || "Não foi possível atualizar agora.") : null);
    setConcluida(leitura);
    // buscar muda a cada render; a chave + a assinatura identificam a leitura.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave, assinatura, habilitado]);

  useEffect(() => { carregar(); }, [carregar]);
  // Cópia offline de OUTROS filtros (a chave é fixa por tela).
  const copiaDeOutroFiltro = doCache && !!dados && assinatura !== undefined && dados._assinatura !== assinatura;
  return { dados, doCache, carregando: habilitado && concluida !== `${chave}|${assinatura ?? ""}`, erro, mensagemErro, copiaDeOutroFiltro, recarregar: carregar };
}

/** Erro visível (antes `erro` do useCarregar existia e nenhuma tela mostrava). */
export function ErroCarga({ mensagem, onTentar }: { mensagem: string; onTentar?: () => void }) {
  return (
    <div role="alert" style={{
      display: "flex", gap: "0.55rem", alignItems: "flex-start", margin: "0 0 0.9rem", padding: "0.7rem 0.8rem",
      borderRadius: "var(--r-app)", border: "1px solid var(--mob-vermelho)", color: "var(--mob-vermelho)",
      background: "color-mix(in srgb, var(--mob-vermelho) 8%, transparent)", fontSize: "0.86rem", fontWeight: 600,
    }}>
      <CircleAlert size={18} style={{ flexShrink: 0, marginTop: 1 }} aria-hidden="true" />
      <div style={{ flex: 1 }}>
        {mensagem}
        {onTentar && (
          <button type="button" onClick={onTentar} style={{
            display: "block", marginTop: "0.35rem", background: "none", border: "none", padding: 0,
            color: "inherit", textDecoration: "underline", fontWeight: 700, fontSize: "0.84rem", cursor: "pointer",
          }}>Tentar de novo</button>
        )}
      </div>
    </div>
  );
}

/** Aviso discreto de que os dados exibidos são uma cópia local (offline). */
export function AvisoCopia({ chave, mostrar }: { chave: string; mostrar: boolean }) {
  const iso = mostrar ? cacheEm(chave) : null;
  if (!iso) return null;
  return (
    <p style={{ fontSize: "0.78rem", color: "var(--mob-muted)", margin: "0 0 0.9rem" }}>
      Cópia de {fmtCacheEm(iso)}
    </p>
  );
}

export function Carregando() {
  return <p style={{ color: "var(--mob-muted)", padding: "1.5rem 0" }}>Carregando…</p>;
}

export function Vazio({ children, icon }: { children: ReactNode; icon?: LucideIcon }) {
  const Icon = icon || BarChart3;
  return (
    <div style={{ textAlign: "center", padding: "2.5rem 1rem", color: "var(--mob-muted)" }}>
      <Icon size={28} style={{ margin: "0 auto 0.5rem", opacity: 0.7, display: "block" }} />
      <p style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--mob-text)" }}>{children}</p>
    </div>
  );
}

const COR_SEMAFORO: Record<string, string> = {
  vermelho: "var(--mob-vermelho)",
  amarelo: "var(--mob-ambar)",
  verde: "var(--mob-verde)",
  branco: "var(--mob-muted)",
};
export function corSemaforo(c?: string | null): string {
  return COR_SEMAFORO[(c || "").toLowerCase()] || "var(--mob-muted)";
}

/** Bolinha do semáforo. */
export function Bolinha({ cor }: { cor?: string | null }) {
  return (
    <span style={{ width: 12, height: 12, borderRadius: "50%", background: corSemaforo(cor), flexShrink: 0, display: "inline-block" }} />
  );
}

/** Número grande do animal (ou rótulo curto) usado nas listas. */
export function NumAnimal({ children }: { children: ReactNode }) {
  return <span style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--mob-text)" }}>{children}</span>;
}

/** Formata em Real — usado nas telas de Financeiro (Fluxo/DRE/RMCA/Extrato). */
export function brl(v?: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

/** Rodapé de paginação (versão mobile, cores --mob-*) — usar com usePaginacao. */
export function PaginacaoMob({
  pagina, totalPaginas, totalLinhas, onMudarPagina,
}: { pagina: number; totalPaginas: number; totalLinhas: number; onMudarPagina: (p: number) => void }) {
  if (totalLinhas === 0) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem", marginTop: "0.7rem" }}>
      <span style={{ fontSize: "0.74rem", color: "var(--mob-muted)" }}>
        Página {pagina} de {totalPaginas} ({totalLinhas})
      </span>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
        <button
          type="button"
          onClick={() => onMudarPagina(pagina - 1)}
          disabled={pagina <= 1}
          style={{
            display: "flex", alignItems: "center", gap: "0.15rem", fontSize: "0.74rem", padding: "0.3rem 0.55rem",
            borderRadius: "var(--r-app)", border: "1px solid var(--mob-border)", background: "var(--mob-surface-2)",
            color: "var(--mob-text)", opacity: pagina <= 1 ? 0.5 : 1,
          }}
        >
          <ChevronLeft size={13} /> Anterior
        </button>
        <button
          type="button"
          onClick={() => onMudarPagina(pagina + 1)}
          disabled={pagina >= totalPaginas}
          style={{
            display: "flex", alignItems: "center", gap: "0.15rem", fontSize: "0.74rem", padding: "0.3rem 0.55rem",
            borderRadius: "var(--r-app)", border: "1px solid var(--mob-border)", background: "var(--mob-surface-2)",
            color: "var(--mob-text)", opacity: pagina >= totalPaginas ? 0.5 : 1,
          }}
        >
          Próxima <ChevronRight size={13} />
        </button>
      </div>
    </div>
  );
}

/** Período invertido (início depois do fim) — as telas avisam e não consultam. */
export function periodoInvertido(inicio: string, fim: string): boolean {
  return !!inicio && !!fim && inicio > fim;
}

/** Par de datas Início/Até — filtro de período obrigatório das telas de
 * Financeiro do app (Fluxo de caixa, DRE, RMCA, Extrato completo) e de
 * Produção. Avisa na hora quando o início fica depois do fim. */
export function FiltroPeriodo({ inicio, fim, onInicio, onFim }: { inicio: string; fim: string; onInicio: (v: string) => void; onFim: (v: string) => void }) {
  return (
    <>
    <div style={{ display: "flex", gap: "0.6rem", marginBottom: "0.8rem" }}>
      <label style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" }}>De</span>
        <input type="date" className="mob-input" value={inicio} onChange={(e) => onInicio(e.target.value)} />
      </label>
      <label style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" }}>Até</span>
        <input type="date" className="mob-input" value={fim} onChange={(e) => onFim(e.target.value)} />
      </label>
    </div>
    {periodoInvertido(inicio, fim) && (
      <p role="alert" style={{ margin: "-0.4rem 0 0.8rem", fontSize: "0.82rem", fontWeight: 700, color: "var(--mob-vermelho)" }}>
        A data inicial é depois da final — ajuste o período.
      </p>
    )}
    </>
  );
}
