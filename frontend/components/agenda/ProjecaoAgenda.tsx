"use client";

import React, { useMemo, useState } from "react";
import { CalendarRange } from "lucide-react";

export type ProjecaoDados = {
  de: string; ate: string; dias: number; semanas: string[];
  cards: Record<string, any>;
  linhas: { data: string; grupo: string; descricao: string; n: number; lote?: string | null }[];
};

export const HORIZONTES_PROJECAO = [7, 30, 60, 90] as const;

const ROTULO_GRUPO: Record<string, string> = {
  repasse: "Cio de repasse", iatf: "IATF", bst: "BST", vacinas: "Vacinas", exames: "Exames",
  pendencias: "Contas e gestão", estoque: "Estoque", reproducao: "Reprodução", outros: "Outros",
};

const fmtDia = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
const fmtDiaSemana = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });

/** Chips 7/30/60/90 dias (o mesmo seletor vale para os cartões e para a tabela). */
export function SeletorHorizonte({ valor, onChange }: { valor: number; onChange: (d: number) => void }) {
  return (
    <div className="ag2-chips" role="radiogroup" aria-label="Horizonte da projeção">
      {HORIZONTES_PROJECAO.map((d) => (
        <button key={d} type="button" role="radio" aria-checked={valor === d} className="ag2-chip" onClick={() => onChange(d)}>
          {d} dias
        </button>
      ))}
    </div>
  );
}

/**
 * Carga futura por semana (Repasse, BST, IATF, Vacinas, Exames, Contas) e
 * "Programação projetada" (tabela). Só números: a projeção nunca lista brinco
 * nem animal de lista de espera.
 */
export function ProjecaoAgenda({
  dados, carregando, erro, horizonte, onTentar,
}: { dados: ProjecaoDados | null; carregando: boolean; erro: string | null; horizonte: number; onTentar: () => void }) {
  const [filtro, setFiltro] = useState("");
  const linhasCarga = useMemo(() => {
    if (!dados) return [] as { chave: string; rotulo: string; pesos: number[]; unidade: string }[];
    const c = dados.cards;
    const l: { chave: string; rotulo: string; pesos: number[]; unidade: string }[] = [];
    if (c.repasse?.usar) l.push({ chave: "repasse", rotulo: "Cio de repasse", pesos: c.repasse.por_semana, unidade: "checagens" });
    if (c.bst) l.push({ chave: "bst", rotulo: "BST", pesos: c.bst.por_semana, unidade: "vacas" });
    if (c.iatf) l.push({ chave: "iatf", rotulo: "IATF", pesos: c.iatf.por_semana, unidade: "etapas" });
    if (c.vacinas) l.push({ chave: "vacinas", rotulo: "Vacinas", pesos: c.vacinas.por_semana, unidade: "aplicações" });
    if (c.exames) l.push({ chave: "exames", rotulo: "Exames", pesos: c.exames.por_semana, unidade: "exames" });
    if (c.pendencias) l.push({ chave: "contas", rotulo: "Contas a pagar", pesos: c.pendencias.por_semana, unidade: "contas" });
    return l;
  }, [dados]);
  const max = Math.max(1, ...linhasCarga.flatMap((l) => l.pesos));
  const linhasProg = useMemo(
    () => (dados?.linhas ?? []).filter((l) => !filtro || l.grupo === filtro),
    [dados, filtro],
  );
  const grupos = useMemo(() => Array.from(new Set((dados?.linhas ?? []).map((l) => l.grupo))), [dados]);

  if (erro && !dados) {
    return (
      <div className="card ag2-projecao" role="alert">
        <p>Não foi possível calcular a programação projetada: {erro}</p>
        <button type="button" className="btn-secondary" onClick={onTentar}>Tentar de novo</button>
      </div>
    );
  }
  return (
    <div className="ag2-projecao-bloco">
      <section className="card ag2-projecao" aria-label={`Carga futura, próximos ${horizonte} dias`} aria-busy={carregando}>
        <div className="ag2-secao-cab">
          <h2><CalendarRange size={16} aria-hidden="true" /> Carga futura <span className="ag2-mudo">próximos {horizonte} dias</span></h2>
          {carregando && <span className="ag2-mudo" role="status">Calculando…</span>}
        </div>
        {!dados ? (
          <p className="ag2-mudo" role="status">Calculando a programação dos próximos {horizonte} dias…</p>
        ) : linhasCarga.length === 0 ? (
          <p className="ag2-mudo">Nada programado neste período.</p>
        ) : (
          <div className="ag2-rolagem-x">
            <table className="ag2-carga">
              <thead>
                <tr>
                  <th scope="col">Semana de</th>
                  {dados.semanas.map((s) => <th key={s} scope="col">{fmtDia(s)}</th>)}
                  <th scope="col">Total</th>
                </tr>
              </thead>
              <tbody>
                {linhasCarga.map((l) => (
                  <tr key={l.chave}>
                    <th scope="row">{l.rotulo} <span className="ag2-mudo">{l.unidade}</span></th>
                    {l.pesos.map((n, i) => (
                      <td key={i} className={n > 0 ? "ag2-carga-tem" : ""}
                        style={n > 0 ? { background: `color-mix(in srgb, var(--dourado) ${Math.round(12 + (n / max) * 48)}%, var(--surface))` } : undefined}>
                        {n}
                      </td>
                    ))}
                    <td><strong>{l.pesos.reduce((a, b) => a + b, 0)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {dados && (
        <section className="card ag2-projecao" aria-label="Programação projetada">
          <div className="ag2-secao-cab">
            <h2>Programação projetada <span className="ag2-mudo">{linhasProg.length} {linhasProg.length === 1 ? "item" : "itens"}</span></h2>
            <label className="ag2-select-rot">
              <span className="ag2-sr">Filtrar por tipo</span>
              <select value={filtro} onChange={(e) => setFiltro(e.target.value)} className="ag2-select">
                <option value="">Todos os tipos</option>
                {grupos.map((g) => <option key={g} value={g}>{ROTULO_GRUPO[g] || g}</option>)}
              </select>
            </label>
          </div>
          {linhasProg.length === 0 ? (
            <p className="ag2-mudo">Nada programado para este filtro.</p>
          ) : (
            <div className="ag2-rolagem-x">
              <table className="fazenda-table ag2-tabela-prog">
                <thead><tr><th>Data</th><th>Tipo</th><th>O quê</th><th>Para quem</th></tr></thead>
                <tbody>
                  {linhasProg.map((l, i) => (
                    <tr key={`${l.data}-${l.grupo}-${i}`}>
                      <td data-rotulo="Data"><strong>{fmtDiaSemana(l.data)}</strong></td>
                      <td data-rotulo="Tipo">{ROTULO_GRUPO[l.grupo] || l.grupo}</td>
                      <td data-rotulo="O quê">{l.descricao}</td>
                      <td data-rotulo="Para quem">{l.n > 0 ? `${l.n} ${l.n === 1 ? "animal" : "animais"}` : "—"}{l.lote ? ` · ${l.lote}` : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
