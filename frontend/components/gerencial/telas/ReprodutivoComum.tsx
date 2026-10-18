"use client";
// Peças e dados de exemplo COMUNS às três telas de Lançamentos › Reprodutivo (Inseminação, Protocolo IATF, Parto).
// Só apresentação: nada aqui chama API. Quando a versão ligada a dados for feita, cada peça vira leitura de:
//   · TabelaMatrizes  → animais (AnimalRow), motivosInaptidao (Map número→motivo), idadeMinServico, useEstadosReprodutivos().rotuloDe,
//                       fetchProtocolosIatfAtivos (coluna "Protocolo"/pronta_para_inseminar) e a última IA/cobertura do animal.
//   · EstiloRepro     → classes .rp-* abaixo; podem migrar para o fim de .gv-* do globals.css (só tokens, sem hex).
import React from "react";
import { Search } from "lucide-react";
import { Selo } from "@/components/gerencial/kit";

/* ───────────────────────────── estilos (só tokens) ───────────────────────────── */
const CSS_REPRO = `
.rp-input, .rp-select { background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm);
  padding: 0.42rem 0.6rem; font-size: 0.85rem; min-width: 0; font-family: inherit; }
.rp-input:focus, .rp-select:focus { outline: 2px solid var(--ft-ouro); outline-offset: -1px; }
.rp-input:disabled, .rp-select:disabled { opacity: 0.55; cursor: not-allowed; }
.rp-cel { width: 100%; background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm);
  padding: 0.28rem 0.45rem; font-size: 0.82rem; min-width: 0; font-family: inherit; }
.rp-cel:focus { outline: 2px solid var(--ft-ouro); outline-offset: -1px; }
.rp-cel:disabled { opacity: 0.5; cursor: not-allowed; }
.rp-cel[data-erro="true"] { border-color: var(--ft-verm); background: color-mix(in srgb, var(--ft-verm) 9%, var(--surface)); }
.rp-erro-txt { display: block; margin-top: 0.15rem; font-size: 0.66rem; font-weight: 700; color: var(--ft-verm); letter-spacing: 0.02em; white-space: normal; }
.rp-ferr { display: flex; flex-wrap: wrap; align-items: center; gap: 0.6rem; }
.rp-busca { position: relative; flex: 1 1 14rem; max-width: 24rem; }
.rp-busca svg { position: absolute; left: 0.55rem; top: 50%; transform: translateY(-50%); color: var(--text-muted); pointer-events: none; }
.rp-busca input { width: 100%; padding-left: 1.9rem; }
.rp-contagem { font-size: 0.8rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.rp-bloco { border: 1px solid var(--border); background: var(--surface-2); padding: 0.75rem 0.9rem; border-radius: var(--r-sm); display: flex; flex-direction: column; gap: 0.6rem; }
.rp-bloco-t { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); }
.rp-grade-2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr); gap: 1.25rem; align-items: start; }
.rp-grade-2e { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.25rem; align-items: start; }
.rp-grade-4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; }
.rp-grade-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.75rem; }
.rp-col { display: flex; flex-direction: column; gap: 0.6rem; min-width: 0; }
.rp-abas { display: flex; border-bottom: 1px solid var(--border); margin: 0 0 0.9rem; }
.rp-aba { background: none; border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px; padding: 0.55rem 1.1rem; font: inherit; font-size: 0.82rem;
  font-weight: 700; letter-spacing: 0.04em; color: var(--text-muted); cursor: pointer; }
.rp-aba[aria-selected="true"] { color: var(--text); border-bottom-color: var(--ft-ouro); }
.rp-aba b { margin-left: 0.45rem; font-variant-numeric: tabular-nums; color: var(--ft-ouro-txt); }
.rp-pilula-x[disabled] { opacity: 0.5; cursor: not-allowed; }
.rp-motivo { margin-left: 0.5rem; font-size: 0.74rem; color: var(--text-muted); white-space: nowrap; }
.rp-motivo-conf { color: var(--ft-ouro-txt); font-weight: 700; }
.rp-tab input[type="radio"] { width: 1.05rem; height: 1.05rem; accent-color: var(--ft-ouro); vertical-align: middle; }
.rp-tab .rp-sub { display: block; font-size: 0.7rem; color: var(--text-muted); font-weight: 400; }
.rp-recolher { border: 1px solid var(--border-strong, var(--border)); background: var(--surface); border-radius: var(--r-sm); }
.rp-recolher > button.rp-recolher-topo { width: 100%; display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 0.8rem; background: none; border: 0; font: inherit;
  color: var(--text); cursor: pointer; text-align: left; font-size: 0.82rem; font-weight: 700; }
.rp-recolher > button.rp-recolher-topo:disabled { color: var(--text-muted); cursor: default; }
.rp-recolher-topo .rp-recolher-sub { font-weight: 400; color: var(--text-muted); font-size: 0.76rem; }
.rp-recolher-corpo { padding: 0.8rem; border-top: 1px solid var(--border); display: flex; flex-direction: column; gap: 0.75rem; }
.rp-retorno-linha { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; width: 100%; }
.rp-ok { color: var(--ft-verde); font-weight: 600; }
.rp-err { color: var(--ft-verm); font-weight: 600; }
.rp-mudo { color: var(--text-muted); }
.rp-linha-tempo { display: flex; padding: 0.4rem 0 0.2rem; }
.rp-etapa { position: relative; flex: 1 1 0; min-width: 0; text-align: center; padding: 0 0.5rem; }
.rp-etapa::before { content: ""; position: absolute; top: 0.95rem; left: 0; right: 0; height: 2px; background: var(--border-strong, var(--border)); }
.rp-etapa:first-child::before { left: 50%; }
.rp-etapa:last-child::before { right: 50%; }
.rp-no { position: relative; z-index: 1; display: inline-flex; align-items: center; justify-content: center; min-width: 2.1rem; height: 1.9rem; padding: 0 0.4rem;
  border-radius: 999px; background: var(--surface); border: 2px solid var(--ft-ouro); color: var(--ft-ouro-txt); font-size: 0.78rem; font-weight: 800; font-variant-numeric: tabular-nums; }
.rp-no[data-fim="true"] { background: var(--ft-verde); border-color: var(--ft-verde); color: var(--surface); }
.rp-etapa-data { display: block; margin-top: 0.35rem; font-size: 0.85rem; font-weight: 800; font-variant-numeric: tabular-nums; }
.rp-etapa-dow { display: block; font-size: 0.66rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); }
.rp-etapa-txt { display: block; margin-top: 0.3rem; font-size: 0.74rem; line-height: 1.4; color: var(--text); }
.rp-etapa-txt i { display: block; font-style: normal; color: var(--text-muted); }
.rp-etapa-fim .rp-etapa-txt { color: var(--ft-verde); font-weight: 700; }
.rp-tarja { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; font-size: 0.78rem; color: var(--text-muted); }
.rp-chip { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.15rem 0.55rem; border: 1px solid var(--border-strong, var(--border)); border-radius: 999px;
  background: var(--surface); color: var(--text); font-size: 0.78rem; font-weight: 700; font-variant-numeric: tabular-nums; }
button.rp-chip { cursor: pointer; font-family: inherit; }
button.rp-chip:hover { border-color: var(--ft-ouro); }
.rp-chip small { font-weight: 400; color: var(--text-muted); font-size: 0.7rem; }
.rp-linha-detalhe > td { background: var(--surface-2) !important; white-space: normal !important; }
.rp-linha-aborto > td { background: color-mix(in srgb, var(--ft-ouro) 7%, var(--surface)) !important; white-space: normal !important; }
.rp-tab-vazia td { text-align: center; color: var(--text-muted); padding: 1.1rem; white-space: normal; }
.rp-seta { background: none; border: 0; padding: 0.15rem; color: var(--text-muted); cursor: pointer; display: inline-flex; border-radius: var(--r-sm); }
.rp-seta:hover { color: var(--text); }
.rp-lista { margin: 0; padding-left: 1.1rem; list-style: disc; font-size: 0.76rem; line-height: 1.5; color: var(--text-muted); }
.rp-sug { display: flex; flex-direction: column; gap: 0.1rem; padding: 0.5rem 0.7rem; border: 1px solid var(--border); background: var(--surface); border-radius: var(--r-sm);
  cursor: pointer; text-align: left; font: inherit; color: var(--text); width: 100%; }
.rp-sug:hover { border-color: var(--ft-ouro); }
.rp-sug[data-alerta="true"] { border-color: var(--ft-verm); background: color-mix(in srgb, var(--ft-verm) 7%, var(--surface)); }
.rp-sug-topo { display: flex; justify-content: space-between; gap: 0.6rem; align-items: baseline; font-size: 0.82rem; font-weight: 700; }
.rp-sug-topo span:last-child { font-weight: 400; font-size: 0.74rem; color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.rp-sug p { margin: 0; display: flex; gap: 0.3rem; align-items: flex-start; font-size: 0.74rem; color: var(--text-muted); }
.rp-sug[data-alerta="true"] p { color: var(--ft-verm); }
.rp-sug[aria-pressed="true"] { border-color: var(--ft-ouro); box-shadow: inset 0 0 0 1px var(--ft-ouro); }
@media (prefers-reduced-motion: no-preference) {
  .rp-aba, .rp-sug, .rp-chip { transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease; }
}
`;
export function EstiloRepro() {
  return <style>{CSS_REPRO}</style>;
}

/* ───────────────────────────── datas ───────────────────────────── */
export const HOJE_ISO = "2026-10-17";
export function somaDias(iso: string, dias: number): string {
  if (!iso) return "";
  const [a, m, d] = iso.split("-").map(Number);
  const dt = new Date(Date.UTC(a, m - 1, d + dias));
  return dt.toISOString().slice(0, 10);
}
export function fmtData(iso: string, curto = false): string {
  if (!iso) return "—";
  const [a, m, d] = iso.split("-");
  return curto ? `${d}/${m}` : `${d}/${m}/${a}`;
}
export function diaSemana(iso: string): string {
  if (!iso) return "";
  const [a, m, d] = iso.split("-").map(Number);
  return ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"][new Date(Date.UTC(a, m - 1, d)).getUTCDay()];
}

/* ───────────────────────────── pílulas com opção travada ───────────────────────────── */
export function PilulasX<T extends string>({ rotulo, opcoes, valor, onChange }: {
  rotulo: string; opcoes: { id: T; nome: string; n?: number; titulo?: string; travada?: boolean }[]; valor: T; onChange?: (id: T) => void;
}) {
  return (
    <div className="gv-linha" role="group" aria-label={rotulo}>
      {opcoes.map((o) => (
        <button key={o.id} type="button" className="ft-pilula rp-pilula-x" aria-pressed={valor === o.id} title={o.titulo} disabled={o.travada}
          onClick={() => onChange?.(o.id)}>
          {o.nome}{o.n != null && <b>{o.n}</b>}
        </button>
      ))}
    </div>
  );
}

/** Abas de uma mesma tela (ex.: Lançar | Em andamento) — ARIA tablist, sublinhado ouro. */
export function Abas<T extends string>({ rotulo, abas, ativa, onChange }: {
  rotulo: string; abas: { id: T; nome: string; n?: number }[]; ativa: T; onChange: (id: T) => void;
}) {
  return (
    <div className="rp-abas" role="tablist" aria-label={rotulo}>
      {abas.map((a) => (
        <button key={a.id} type="button" role="tab" id={`aba-${a.id}`} className="rp-aba" aria-selected={ativa === a.id} onClick={() => onChange(a.id)}>
          {a.nome}{a.n != null && <b>{a.n}</b>}
        </button>
      ))}
    </div>
  );
}

/* ───────────────────────────── matrizes de exemplo (Fazenda Estreito Ponte de Pedra) ───────────────────────────── */
export type Aptidao = "apta" | "inapta" | "confirmar";
export type Matriz = {
  n: string; lote: string; cat: string; del: string; sit: string; ultima: string;
  apt: Aptidao; motivo?: string; diag?: boolean; protocolo?: string;
};
export const MATRIZES: Matriz[] = [
  { n: "11153", lote: "02 - Vacas Alta", cat: "Vaca", del: "DEL 96", sit: "Vazia", ultima: "IA 05/08/2026", apt: "apta", diag: true },
  { n: "3335", lote: "02 - Vacas Alta", cat: "Vaca", del: "DEL 121", sit: "Vazia", ultima: "IA 18/07/2026", apt: "apta", diag: true },
  { n: "075", lote: "02 - Vacas Alta", cat: "Vaca", del: "DEL 143", sit: "Vazia · em observação", ultima: "IA 21/06/2026", apt: "apta", diag: true },
  { n: "9378", lote: "02 - Vacas Alta", cat: "Vaca", del: "DEL 88", sit: "Vazia", ultima: "IA 25/07/2026", apt: "apta", diag: true },
  { n: "7120", lote: "02 - Vacas Alta", cat: "Vaca", del: "DEL 74", sit: "Vazia", ultima: "—", apt: "apta", protocolo: "IATF 06/10" },
  { n: "8012", lote: "02 - Vacas Alta", cat: "Vaca", del: "DEL 187", sit: "Gestante", ultima: "IA 10/05/2026", apt: "confirmar", motivo: "Consta gestante" },
  { n: "4821", lote: "04 - Pós-parto/Tratamento", cat: "Vaca", del: "DEL 31", sit: "Vazia · em PEV", ultima: "—", apt: "apta" },
  { n: "4790", lote: "04 - Pós-parto/Tratamento", cat: "Vaca", del: "DEL 52", sit: "Vazia", ultima: "—", apt: "apta", protocolo: "IATF 06/10" },
  { n: "4802", lote: "04 - Pós-parto/Tratamento", cat: "Vaca", del: "DEL 60", sit: "Vazia", ultima: "IA 02/09/2026", apt: "inapta", motivo: "Marcada a descartar" },
  { n: "1087", lote: "01 - Novilhas Alta", cat: "Novilha", del: "17 meses", sit: "Novilha", ultima: "—", apt: "apta", protocolo: "IATF 06/10" },
  { n: "1092", lote: "01 - Novilhas Alta", cat: "Novilha", del: "16 meses", sit: "Novilha", ultima: "—", apt: "apta", protocolo: "IATF 06/10" },
  { n: "1110", lote: "01 - Novilhas Alta", cat: "Novilha", del: "16 meses", sit: "Novilha", ultima: "—", apt: "apta" },
  { n: "1055", lote: "01 - Novilhas Alta", cat: "Novilha", del: "19 meses", sit: "Novilha", ultima: "—", apt: "inapta", motivo: "Marcada a descartar" },
  { n: "13180", lote: "13 - Novilhas Novas", cat: "Novilha", del: "14 meses", sit: "Novilha", ultima: "—", apt: "apta", protocolo: "IATF 06/10" },
  { n: "13204", lote: "13 - Novilhas Novas", cat: "Novilha", del: "11 meses", sit: "Novilha", ultima: "—", apt: "inapta", motivo: "Idade mínima 14 meses (tem 11)" },
  { n: "13211", lote: "13 - Novilhas Novas", cat: "Novilha", del: "12 meses", sit: "Novilha", ultima: "—", apt: "inapta", motivo: "Idade mínima 14 meses (tem 12)" },
];
export const IDADE_MIN_SERVICO = 14;

const normaliza = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
export function filtraBusca(ms: Matriz[], busca: string): Matriz[] {
  const q = normaliza(busca.trim());
  return q ? ms.filter((m) => normaliza(`${m.n} ${m.lote} ${m.cat} ${m.sit}`).includes(q)) : ms;
}

/* ───────────────────────────── tabela de matrizes (seleção com caixas, por lote, com aptidão) ───────────────────────────── */
export function BuscaMatrizes({ valor, onChange, rotulo = "Buscar matriz ou lote" }: { valor: string; onChange: (v: string) => void; rotulo?: string }) {
  return (
    <div className="rp-busca">
      <Search size={14} aria-hidden="true" />
      <input type="search" className="rp-input" value={valor} onChange={(e) => onChange(e.target.value)} placeholder={rotulo} aria-label={rotulo} />
    </div>
  );
}

export function TabelaMatrizes({ matrizes, sel, onToggle, onToggleLote, onToggleAptas, mostrarProtocolo, altura = "36rem", vazio }: {
  matrizes: Matriz[]; sel: ReadonlySet<string>;
  onToggle: (n: string) => void; onToggleLote: (lote: string, itens: Matriz[]) => void; onToggleAptas: () => void;
  mostrarProtocolo?: boolean; altura?: string; vazio?: string;
}) {
  const grupos = new Map<string, Matriz[]>();
  for (const m of matrizes) grupos.set(m.lote, [...(grupos.get(m.lote) ?? []), m]);
  const ordenados = [...grupos.entries()].sort(([a], [b]) => a.localeCompare(b, "pt-BR", { numeric: true }));
  const aptas = matrizes.filter((m) => m.apt === "apta");
  const todasAptas = aptas.length > 0 && aptas.every((m) => sel.has(m.n));
  const colunas = mostrarProtocolo ? 8 : 7;
  return (
    <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: altura }}>
      <table className="gv-tabela">
        <thead>
          <tr>
            <th scope="col" style={{ width: "2.4rem" }}>
              <input type="checkbox" checked={todasAptas} onChange={onToggleAptas} disabled={!aptas.length} aria-label="Selecionar todas as aptas da lista" />
            </th>
            <th scope="col">Nº</th><th scope="col">Categoria</th><th scope="col" title="Dias em lactação (vacas) ou idade (novilhas)">DEL · idade</th>
            <th scope="col">Situação reprodutiva</th><th scope="col" title="Última inseminação ou cobertura registrada">Última IA / cobertura</th>
            {mostrarProtocolo && <th scope="col">Protocolo</th>}
            <th scope="col">Aptidão para servir</th>
          </tr>
        </thead>
        <tbody>
          {ordenados.length === 0 && <tr className="rp-tab-vazia"><td colSpan={colunas}>{vazio ?? "Nenhuma fêmea na lista."}</td></tr>}
          {ordenados.map(([lote, itens]) => {
            const aptasDoLote = itens.filter((m) => m.apt === "apta");
            const loteMarcado = aptasDoLote.length > 0 && aptasDoLote.every((m) => sel.has(m.n));
            return (
              <React.Fragment key={lote}>
                <tr className="gv-grupo">
                  <th scope="rowgroup" colSpan={colunas}>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
                      <input type="checkbox" checked={loteMarcado} disabled={!aptasDoLote.length} onChange={() => onToggleLote(lote, itens)} aria-label={`Marcar as aptas do lote ${lote}`} />
                      {lote} · {itens.length} {itens.length === 1 ? "fêmea" : "fêmeas"} · {aptasDoLote.length} {aptasDoLote.length === 1 ? "apta" : "aptas"}
                    </label>
                  </th>
                </tr>
                {itens.map((m) => {
                  const marcada = sel.has(m.n);
                  const cls = marcada ? "gv-linha-marcada" : m.apt === "inapta" ? "gv-linha-fora" : undefined;
                  return (
                    <tr key={m.n} className={cls}>
                      <td><input type="checkbox" checked={marcada} onChange={() => onToggle(m.n)} aria-label={`Selecionar ${m.n}`} /></td>
                      <td className="gv-forte">
                        {m.n}{m.diag && <> <Selo tom="info" titulo="Já veio marcada (diagnóstico negativo ou Agenda)">Pré-marcada</Selo></>}
                      </td>
                      <td>{m.cat}</td>
                      <td className="gv-num">{m.del}</td>
                      <td>{m.sit}</td>
                      <td className="gv-num">{m.ultima}</td>
                      {mostrarProtocolo && <td>{m.protocolo ? <Selo tom="info">{m.protocolo}</Selo> : "—"}</td>}
                      <td>
                        {m.apt === "apta" && <Selo tom="ok">Apta</Selo>}
                        {m.apt === "inapta" && <><Selo tom="neutro">Inapta</Selo><span className="rp-motivo">{m.motivo}{marcada && <span className="rp-motivo-conf"> · pede confirmação</span>}</span></>}
                        {m.apt === "confirmar" && <><Selo tom="atencao">Confirmar</Selo><span className="rp-motivo">{m.motivo}{marcada && <span className="rp-motivo-conf"> · pede confirmação</span>}</span></>}
                      </td>
                    </tr>
                  );
                })}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Alterna um número num Set imutável. */
export function alterna(set: ReadonlySet<string>, v: string): Set<string> {
  const s = new Set(set);
  if (s.has(v)) s.delete(v); else s.add(v);
  return s;
}
/** Marca/desmarca as aptas de um conjunto de matrizes (inaptas nunca entram sozinhas, só por clique). */
export function alternaAptas(sel: ReadonlySet<string>, itens: Matriz[]): Set<string> {
  const aptas = itens.filter((m) => m.apt === "apta");
  const todas = aptas.length > 0 && aptas.every((m) => sel.has(m.n));
  const s = new Set(sel);
  aptas.forEach((m) => (todas ? s.delete(m.n) : s.add(m.n)));
  return s;
}
