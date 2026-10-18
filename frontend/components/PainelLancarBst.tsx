"use client";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Ban, CalendarClock, Check, ChevronDown, ChevronUp, Droplets, SlidersHorizontal } from "lucide-react";
import { aplicarBstLote, marcarInaptaBst, ajustarProximaAplicacaoBst, fetchEstoqueAtivos, formatDate, ehAdmin } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";
import { Aviso, BotaoOuro, Passo, Selo } from "@/components/gerencial/kit";
import { CSS_RAIZ } from "@/components/gerencial/producaoCss";
import { dataBR, diasEntre, hojeLocal, mensagemDe, plural } from "@/lib/producaoGerencial";
import {
  SEGMENTOS, alvoDaAcao, doseTotal, filtrarAnimais, interpretarRetornoAplicar, itensParaBst, montarPayloadAplicar, ordenarAnimais, preverEstoque,
  reanalisadasMarcadas, segmentosDaAgenda, textoPrevisao, textoRetornoMarcar,
  type AgendaBst, type AnimalBst, type DadosAplicarBst, type ItemEstoque, type ItemEstoqueCadastro, type Marcadas, type Ordem, type ParamsAplicacao, type Seg,
} from "@/lib/bstLote";

const th: React.CSSProperties = { textAlign: "left", padding: "0.4rem 0.6rem", fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" };
const td: React.CSSProperties = { padding: "0.4rem 0.6rem", fontSize: "0.82rem", borderBottom: "1px solid var(--border)" };

/**
 * Tabelas de status do BST (Aptas / Incluir no próximo BST / Inaptas) — só
 * leitura, sem checkbox nem ação. Usada em Produção › Relatórios de BST
 * (que não lança mais aplicação, só reporta) e reaproveitada como miolo de
 * `PainelLancarBst` (que adiciona a seleção/ações por cima).
 */
export function TabelasStatusBst({ agenda, selecionados, onToggle }: { agenda: any; selecionados?: Set<string>; onToggle?: (numero: string) => void }) {
  const aptas: any[] = agenda?.bst_elegiveis ?? [];
  const nuncaAplicadas: any[] = agenda?.bst_nunca_aplicados ?? [];
  const inaptas: any[] = agenda?.bst_excluidos ?? [];
  // Filtro "ver DEL de hoje / DEL projetado" (pedido do usuário — antes as
  // duas colunas ficavam sempre lado a lado, sem opção de focar só numa).
  // "ambos" (padrão) mantém o comportamento anterior.
  const [verDel, setVerDel] = useState<"ambos" | "atual" | "projetado">("ambos");

  const Tabela = ({ titulo, lista, cor }: { titulo: string; lista: any[]; cor: string }) => {
    const ord = useOrdenacao(lista);
    return (
    <div className="card">
      <div className="card-header mb-2 flex items-center gap-2" style={{ color: cor }}><Droplets size={14} /> {titulo} ({lista.length})</div>
      {!lista.length ? <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nenhum animal nesta condição.</p> : (
        <div style={{ overflowX: "auto", maxHeight: "280px" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              {onToggle && <th style={th}></th>}
              <th style={th}></th>
              <ThOrdenavel label="Nº" campo="numero_matriz" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Lote" campo="grupo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              {verDel !== "projetado" && (
                <ThOrdenavel label="DEL atual" campo="del_atual" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
              )}
              {verDel !== "atual" && (
                <ThOrdenavel label="DEL projetado" campo="del_projetado" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
              )}
              <th style={th}>Obs.</th>
            </tr></thead>
            <tbody>{ord.linhasOrdenadas.map((b: any) => (
              <tr key={b.numero_matriz}>
                {onToggle && <td style={td}><input type="checkbox" checked={!!selecionados?.has(b.numero_matriz)} onChange={() => onToggle(b.numero_matriz)} /></td>}
                <td style={td}>
                  {b.requer_reanalise && (
                    <span title="Retirada do BST — revisar antes de incluir de novo" style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: "var(--amber)" }} />
                  )}
                </td>
                <td style={{ ...td, fontWeight: 700 }}>
                  {b.numero_matriz}
                  {b.origem_inducao_lactacao && (
                    <span title="Entrou no BST pelo protocolo de indução de lactação" style={{ marginLeft: 4, fontWeight: 400, fontSize: "0.72rem", color: "var(--blue)" }}>
                      (ind.lact.)
                    </span>
                  )}
                </td>
                <td style={td}>{b.grupo || "—"}</td>
                {verDel !== "projetado" && <td style={{ ...td, textAlign: "right" }}>{b.del_atual ?? "—"}</td>}
                {verDel !== "atual" && <td style={{ ...td, textAlign: "right" }}>{b.del_projetado ?? "—"}</td>}
                <td style={{ ...td, color: "var(--text-muted)", fontSize: "0.75rem" }}>
                  {b.requer_reanalise ? (b.motivo_exclusao || "Retirada do BST — revisar") : lista === nuncaAplicadas ? "Nunca aplicada — apta na próxima" : "—"}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
    );
  };

  const opcoesVerDel: [typeof verDel, string][] = [
    ["ambos", "Ambos"], ["atual", "Só DEL atual"], ["projetado", "Só DEL projetado"],
  ];

  // Exportação (PDF/Excel) das 3 listas juntas — mesma tabela usada tanto na
  // Agenda (card de BST) quanto em Lançamentos > Produção > BST e em
  // Produção > Relatórios de BST, já que todas renderizam via este
  // componente. "Situação" identifica de qual das 3 tabelas a linha veio.
  const colunasExport: ColunaExport[] = [
    { header: "Nº", key: "numero_matriz" },
    { header: "Lote", key: "grupo" },
    { header: "DEL atual", key: "del_atual" },
    { header: "DEL projetado", key: "del_projetado" },
    { header: "Situação", key: "situacao" },
    { header: "Obs.", key: "obs" },
  ];
  const linhasExport = useMemo(() => [
    ...aptas.map((b) => ({ ...b, situacao: "Apta", obs: "" })),
    ...nuncaAplicadas.map((b) => ({ ...b, situacao: "Incluir no próximo BST", obs: "Nunca aplicada — apta na próxima" })),
    ...inaptas.map((b) => ({ ...b, situacao: "Inapta", obs: b.requer_reanalise ? (b.motivo_exclusao || "Retirada do BST — revisar") : "" })),
  ], [aptas, nuncaAplicadas, inaptas]);

  return (
    <div className="space-y-2">
      <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
        "DEL atual" é o DEL de hoje; "DEL projetado" é o DEL que o animal terá na data da próxima aplicação de BST
        {agenda?.proxima_visita_bst ? <> (<strong>{formatDate(agenda.proxima_visita_bst)}</strong>)</> : null} — é essa
        projeção que decide se a vaca chega apta na hora certa.
      </p>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Ver:</span>
          <div className="flex gap-1">
            {opcoesVerDel.map(([valor, rotulo]) => (
              <button key={valor} type="button" onClick={() => setVerDel(valor)}
                className={verDel === valor ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem" }}>
                {rotulo}
              </button>
            ))}
          </div>
        </div>
        <ExportarBotoes titulo="BST — DEL atual e projetado" colunas={colunasExport} linhas={linhasExport} nomeArquivoBase="bst_del" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Tabela titulo="BST — Aptas" lista={aptas} cor="var(--green-light)" />
        <Tabela titulo="BST — Incluir no próximo BST" lista={nuncaAplicadas} cor="var(--amber)" />
        <Tabela titulo="BST — Inaptas p/ próxima aplicação" lista={inaptas} cor="var(--red)" />
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
// PainelLancarBst — tela gerencial "Quem recebe BST na próxima visita?" (kit components/gerencial/kit.tsx).
//
// UMA tabela com 3 segmentos (Aptas | Incluir no próximo BST | Inaptas) em vez de 3 tabelas lado a lado; uma barra fixa no pé com os
// dados da aplicação, a previsão do estoque e o retorno da ação. As ações dependem do segmento, então a mistura inválida (aplicar +
// marcar inapta na mesma seleção) é impossível por construção. Regras puras (segmentos, filtro, alvo, estoque, payload, retorno)
// em lib/bstLote.ts, com testes.
//  · Fonte: `agenda` (fetchAgenda) → bst_elegiveis (Aptas), bst_nunca_aplicados (Incluir; traz requer_reanalise/origem_inducao_lactacao/
//    motivo_exclusao), bst_excluidos (Inaptas), proxima_visita_bst, intervalo_bst. `onAtualizado()` recarrega a agenda.
//  · Props de injeção do app de campo: `aplicarBst` (POST /agenda/bst/aplicar) e `marcarInapta` (POST /agenda/bst/marcar-inapta) —
//    a barra chama SÓ elas. Retorno `{ enviado: false }` = "guardado, sem internet".
//  · "Marcar inapta" (inapta:true) e "Marcar como apta" (inapta:false) levam o animal para "Incluir no próximo BST" com o selo
//    Reanalisar; só voltam a aptas depois de uma nova aplicação. Dose em branco = BST registrado sem baixar estoque; data futura = agenda.
//  · Ajuste da próxima aplicação (POST /producao/bst/ajustar-proxima-aplicacao) é só de administrador.
// ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
type DadosMarcarInaptaBst = { numeros_matriz: string[]; inapta?: boolean };
type FiltroDel = "ambos" | "projetado" | "atual";
type AcaoBst = "aplicar" | "inapta" | "apta";
type ConfirmacaoBst = { tipo: AcaoBst; alvo: AnimalBst[] };
type RetornoBst = { tipo: "ok" | "erro"; texto: string; avisos?: string[]; tentar?: ConfirmacaoBst; verIncluir?: boolean };

const CSS_BST = `
.bst-topo { display: flex; align-items: baseline; justify-content: space-between; gap: 0.3rem 1rem; flex-wrap: wrap; margin-bottom: 0.7rem; }
.bst-pergunta { margin: 0; font-size: 1.1rem; font-weight: 800; letter-spacing: -0.01em; color: var(--text); }
.bst-prox { display: flex; align-items: center; gap: 0.5rem 1rem; padding: 0.55rem 0.9rem; border: 1px solid var(--border); background: var(--surface-2); margin-bottom: 0.7rem; flex-wrap: wrap; }
.bst-prox-data { display: block; font-size: 1.3rem; font-weight: 800; font-variant-numeric: tabular-nums; color: var(--text); line-height: 1.1; }
.bst-prox-rot { display: block; font-size: 0.66rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); }
.bst-prox-txt { font-size: 0.8rem; color: var(--text-muted); }
.bst-prox-txt b { color: var(--text); font-variant-numeric: tabular-nums; }
.bst-prox-ok { font-size: 0.8rem; color: var(--ft-verde); font-weight: 600; }
.bst-ajuste { padding: 0.8rem 0.9rem; border: 1px solid var(--border); background: var(--surface); margin: -0.35rem 0 0.7rem; display: flex; flex-direction: column; gap: 0.7rem; }
.bst-ajuste-grade { display: grid; gap: 0.75rem; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.bst-segs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--border); background: var(--surface); margin-bottom: 0.9rem; }
.bst-seg { text-align: left; font: inherit; color: var(--text); background: var(--surface); border: 0; border-right: 1px solid var(--border); border-bottom: 3px solid transparent;
  padding: 0.55rem 0.9rem; cursor: pointer; min-width: 0; display: flex; flex-direction: column; gap: 0.1rem; }
.bst-seg:last-child { border-right: 0; }
.bst-seg:hover { background: var(--surface-2); }
.bst-seg[aria-pressed="true"] { background: var(--ft-ouro-tint); border-bottom-color: var(--ft-ouro); }
.bst-seg-linha { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; }
.bst-seg-v { font-size: 1.35rem; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; }
.bst-seg[data-tom="ok"] .bst-seg-v { color: var(--ft-verde); }
.bst-seg[data-tom="atencao"] .bst-seg-v { color: var(--ft-ambar); }
.bst-seg[data-tom="alerta"] .bst-seg-v { color: var(--ft-verm); }
.bst-seg-n { font-size: 0.66rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); }
.bst-seg[aria-pressed="true"] .bst-seg-n { color: var(--text); }
.bst-seg-sub { font-size: 0.72rem; color: var(--text-muted); }
.bst-marc { margin-left: auto; font-size: 0.7rem; font-weight: 800; color: var(--ft-ouro-txt); font-variant-numeric: tabular-nums; }
.bst-tool { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.bst-btn { display: inline-flex; align-items: center; gap: 0.35rem; min-height: 2rem; padding: 0.3rem 0.7rem; font: inherit; font-size: 0.78rem; font-weight: 600; cursor: pointer;
  color: var(--text); background: var(--surface); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); }
.bst-btn:hover:not(:disabled) { background: var(--surface-2); }
.bst-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.bst-btn:focus-visible, .bst-seg:focus-visible, .bst-th:focus-visible, .bst-mini button:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: -1px; }
.bst-lotes { position: relative; }
.bst-lotes > summary { list-style: none; }
.bst-lotes > summary::-webkit-details-marker { display: none; }
.bst-lotes-painel { position: absolute; z-index: 6; top: calc(100% + 2px); left: 0; min-width: 17rem; max-height: 18rem; overflow: auto; padding: 0.4rem; background: var(--surface); border: 1px solid var(--border-strong, var(--border)); box-shadow: var(--shadow-sm); }
.bst-lotes-painel label { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.4rem; font-size: 0.82rem; cursor: pointer; }
.bst-lotes-painel label:hover { background: var(--surface-2); }
.bst-lotes-painel input { accent-color: var(--ft-ouro); width: 1.05rem; height: 1.05rem; }
.bst-lotes-painel i { margin-left: auto; font-style: normal; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.bst-lotes-painel .gp-link { margin: 0.2rem 0.4rem 0.1rem; }
.bst-mini { display: inline-flex; border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); overflow: hidden; }
.bst-mini button { min-height: 2rem; padding: 0.25rem 0.65rem; font: inherit; font-size: 0.76rem; font-weight: 600; color: var(--text-muted); background: var(--surface); border: 0; border-right: 1px solid var(--border); cursor: pointer; white-space: nowrap; }
.bst-mini button:last-child { border-right: 0; }
.bst-mini button[aria-pressed="true"] { background: var(--ft-ouro-tint); color: var(--ft-ouro-txt); box-shadow: inset 0 -2px 0 var(--ft-ouro); }
.bst-rot { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); }
.bst-busca { min-height: 2rem; padding: 0.3rem 0.6rem; font: inherit; font-size: 0.82rem; color: var(--text); background: var(--surface-2); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); min-width: 0; width: 9.5rem; }
.bst-busca:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: -1px; }
.bst-th { display: inline-flex; align-items: center; gap: 0.25rem; padding: 0; margin: 0; font: inherit; letter-spacing: inherit; text-transform: inherit; color: inherit; background: none; border: 0; cursor: pointer; }
.bst-tab { table-layout: fixed; min-width: 640px; }
.bst-tab thead th.bst-dp { border-bottom: 2px solid var(--ft-ouro); }
.bst-tab td.bst-sit { white-space: normal; }
.bst-dp-v { font-size: 0.95rem; font-weight: 800; font-variant-numeric: tabular-nums; color: var(--text); }
.bst-da-v { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.bst-obs { margin-left: 0.5rem; font-size: 0.78rem; color: var(--text-muted); }
.bst-il { margin-left: 0.4rem; font-size: 0.72rem; font-weight: 400; color: var(--ft-aco); }
.bst-vazio { padding: 1.6rem; text-align: center; color: var(--text-muted); white-space: normal !important; }
.bst-params { display: flex; align-items: flex-end; gap: 0.7rem; flex-wrap: wrap; padding: 0.6rem 0.9rem 0.7rem; border-bottom: 1px solid var(--border); }
.bst-params .gv-campo input, .bst-params .gv-campo select { min-height: 2rem; padding: 0.3rem 0.5rem; }
.bst-params-tit { align-self: center; display: flex; align-items: center; gap: 0.55rem; margin-right: 0.3rem; }
.bst-resumo-linha { font-size: 0.78rem; color: var(--text-muted); }
.bst-resumo-linha strong { color: var(--text); font-variant-numeric: tabular-nums; }
.bst-resumo-linha em { font-style: normal; font-weight: 700; color: var(--ft-ambar); }
.bst-resumo { flex: 1 1 22rem; }
.bst-ret { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; padding: 0.5rem 0.9rem; border-bottom: 1px solid var(--border); font-size: 0.8rem; background: var(--surface); }
.bst-ret-txt { flex: 1 1 18rem; min-width: 0; }
.bst-ret-txt ul { margin: 0.2rem 0 0; padding-left: 1.1rem; color: var(--ft-ambar); font-weight: 600; }
.bst-conf { display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap; flex: 1 1 30rem; justify-content: flex-end; }
.bst-conf p { margin: 0; flex: 1 1 18rem; font-size: 0.82rem; }
.bst-perigo { color: var(--ft-verm); }
@media (max-width: 899px) {
  .bst-segs { grid-template-columns: 1fr; }
  .bst-seg { border-right: 0; border-bottom: 1px solid var(--border); }
  .bst-seg[aria-pressed="true"] { border-bottom: 3px solid var(--ft-ouro); }
  .bst-ajuste-grade { grid-template-columns: 1fr; }
}
`;

const br = (iso: string | null | undefined) => dataBR(iso);

function Proxima({ proxima, intervalo, aberto, podeAjustar, mensagem, onAjustar }: {
  proxima: string | null; intervalo: number | null; aberto: boolean; podeAjustar: boolean; mensagem: string; onAjustar: () => void;
}) {
  const d = proxima ? diasEntre(hojeLocal(), proxima) : null;
  return (
    <div className="bst-prox">
      <CalendarClock size={18} aria-hidden="true" style={{ color: "var(--ft-ouro-txt)" }} />
      <div><span className="bst-prox-rot">Próxima aplicação</span><span className="bst-prox-data">{proxima ? br(proxima) : "—"}</span></div>
      <span className="bst-prox-txt">
        {d === null ? null : d > 0 ? <>em <b>{d} {plural(d, "dia", "dias")}</b></> : d === 0 ? <b>hoje</b> : <>há <b>{-d} {plural(-d, "dia", "dias")}</b></>}
        {d !== null && " · "}intervalo entre aplicações: <b>{intervalo ?? "—"} dias</b>
      </span>
      {mensagem && <span className="bst-prox-ok" role="status">✓ {mensagem}</span>}
      <span style={{ flex: 1 }} />
      <button type="button" className="bst-btn" aria-expanded={aberto} disabled={!podeAjustar} onClick={onAjustar}
        title={podeAjustar ? "Ajustar a data da próxima aplicação" : "Só administrador pode ajustar a próxima aplicação"}>
        <SlidersHorizontal size={14} aria-hidden="true" /> Ajustar
      </button>
    </div>
  );
}

function PainelAjuste({ proxima, intervalo, onFechar, onAjustado }: {
  proxima: string | null; intervalo: number | null; onFechar: () => void; onAjustado: (msg: string) => void;
}) {
  const [nova, setNova] = useState(proxima || "");
  const [modo, setModo] = useState<"intervalo" | "referencia" | "">("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const mudou = !!nova && nova !== proxima;

  async function salvar() {
    if (!mudou || !modo) return;
    setOcupado(true); setErro(null);
    try {
      const r = await ajustarProximaAplicacaoBst(nova, modo);
      onAjustado(modo === "intervalo" ? `Pronto — o intervalo entre aplicações agora é de ${r.novo_intervalo} dias.` : `Pronto — a contagem passa a valer a partir de ${br(nova)}.`);
    } catch (e) {
      setErro(mensagemDe(e, "Não foi possível ajustar a próxima aplicação."));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="bst-ajuste">
      <div className="gv-linha" style={{ gap: "1rem", alignItems: "flex-end" }}>
        <div className="gv-campo" style={{ width: "12rem" }}>
          <label htmlFor="bst-nova">Nova data da próxima aplicação</label>
          <input id="bst-nova" type="date" value={nova} onChange={(e) => { setNova(e.target.value); setModo(""); setErro(null); }} />
        </div>
        <p className="gv-ajuda" style={{ maxWidth: "46rem" }}>É uma decisão do rebanho inteiro, não de um animal. Ao mudar a data, diga como o sistema deve entender essa mudança (só administrador pode ajustar).</p>
      </div>
      {mudou && (
        <div className="bst-ajuste-grade" role="group" aria-label="Como entender a mudança">
          <button type="button" className="gv-cartao-opcao" aria-pressed={modo === "intervalo"} onClick={() => setModo("intervalo")}>
            <b>Novo intervalo entre aplicações</b>
            <span>Recalcula o intervalo (hoje {intervalo ?? "—"} dias) a partir da última aplicação até {br(nova)}. O novo número aparece quando você salvar.</span>
          </button>
          <button type="button" className="gv-cartao-opcao" aria-pressed={modo === "referencia"} onClick={() => setModo("referencia")}>
            <b>Nova referência de contagem</b>
            <span>Mantém {intervalo ?? "—"} dias e passa a contar os próximos ciclos a partir de {br(nova)}.</span>
          </button>
        </div>
      )}
      {erro && <Aviso tom="erro">{erro}</Aviso>}
      <div className="gv-linha">
        <BotaoOuro desabilitado={!mudou || !modo || ocupado} onClick={salvar}>{ocupado ? "Salvando…" : "Salvar ajuste"}</BotaoOuro>
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
      </div>
    </div>
  );
}

function Segmentos({ seg, onTrocar, contagens, marcadas }: { seg: Seg; onTrocar: (s: Seg) => void; contagens: Record<Seg, number>; marcadas: Record<Seg, number> }) {
  return (
    <div className="bst-segs" role="group" aria-label="Quem entra na próxima aplicação">
      {SEGMENTOS.map((s) => (
        <button key={s.id} type="button" className="bst-seg" data-tom={s.tom} aria-pressed={seg === s.id} onClick={() => onTrocar(s.id)}>
          <span className="bst-seg-linha">
            <span className="bst-seg-v">{contagens[s.id]}</span><span className="bst-seg-n">{s.nome}</span>
            {marcadas[s.id] > 0 && <span className="bst-marc">{marcadas[s.id]} {plural(marcadas[s.id], "marcada", "marcadas")}</span>}
          </span>
          <span className="bst-seg-sub">{s.sub}</span>
        </button>
      ))}
    </div>
  );
}

function FiltroLotes({ lotes, contagem, marcados, onChange }: { lotes: string[]; contagem: Record<string, number>; marcados: string[]; onChange: (l: string[]) => void }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const fora = (e: MouseEvent) => { if (ref.current?.open && !ref.current.contains(e.target as Node)) ref.current.open = false; };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape" && ref.current?.open) { ref.current.open = false; } };
    document.addEventListener("mousedown", fora); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fora); document.removeEventListener("keydown", esc); };
  }, []);
  return (
    <details className="bst-lotes" ref={ref}>
      <summary className="bst-btn" aria-label="Filtrar por lote">Lote: {marcados.length ? `${marcados.length} ${plural(marcados.length, "marcado", "marcados")}` : "todos"} <ChevronDown size={13} aria-hidden="true" /></summary>
      <div className="bst-lotes-painel">
        {lotes.map((l) => (
          <label key={l}>
            <input type="checkbox" checked={marcados.includes(l)} onChange={() => onChange(marcados.includes(l) ? marcados.filter((x) => x !== l) : [...marcados, l])} />
            {l}<i>{contagem[l] ?? 0}</i>
          </label>
        ))}
        {marcados.length > 0 && <button type="button" className="gp-link" onClick={() => onChange([])}>Mostrar todos os lotes</button>}
      </div>
    </details>
  );
}

function Cab({ col, rotulo, ordem, onOrdenar, dir, classe, titulo, largura }: {
  col: Ordem["col"]; rotulo: string; ordem: Ordem; onOrdenar: (c: Ordem["col"]) => void; dir?: boolean; classe?: string; titulo?: string; largura?: string;
}) {
  const ativo = ordem.col === col;
  return (
    <th scope="col" className={[dir ? "gv-dir" : "", classe ?? ""].join(" ").trim()} aria-sort={ativo ? (ordem.dir === 1 ? "ascending" : "descending") : "none"} title={titulo} style={{ width: largura }}>
      <button type="button" className="bst-th" onClick={() => onOrdenar(col)}>
        {rotulo}{ativo && (ordem.dir === 1 ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronUp size={12} aria-hidden="true" />)}
      </button>
    </th>
  );
}

function SituacaoBst({ a }: { a: AnimalBst }) {
  if (a.seg === "aptas") return <Selo tom="ok">Apta</Selo>;
  if (a.seg === "inaptas") return <><Selo tom="bloqueio">Inapta</Selo>{a.motivo && <span className="bst-obs">{a.motivo}</span>}</>;
  if (a.reanalise) return <><Selo tom="atencao" titulo="Retirada do BST — revisar antes de incluir de novo">Reanalisar</Selo><span className="bst-obs">{a.motivo || "Retirada do BST — revisar"}</span></>;
  return <><Selo tom="info">Nunca aplicada</Selo><span className="bst-obs">apta na próxima aplicação</span></>;
}

function TabelaBst({ linhas, carregando, filtrando, marcadas, onToggle, onTodas, verDel, ordem, onOrdenar, proxima }: {
  linhas: AnimalBst[]; carregando: boolean; filtrando: boolean; marcadas: Set<string>; onToggle: (n: string) => void; onTodas: () => void;
  verDel: FiltroDel; ordem: Ordem; onOrdenar: (c: Ordem["col"]) => void; proxima: string | null;
}) {
  const todas = linhas.length > 0 && linhas.every((l) => marcadas.has(l.numero));
  return (
    <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "24rem" }} tabIndex={0} aria-label="Lista de animais">
      <table className="gv-tabela bst-tab">
        <thead>
          <tr>
            <th scope="col" style={{ width: "2.6rem" }}>
              <input type="checkbox" checked={todas} onChange={onTodas} aria-label="Marcar todas as linhas visíveis deste segmento" disabled={!linhas.length} />
            </th>
            <Cab col="n" rotulo="Nº" ordem={ordem} onOrdenar={onOrdenar} largura="9rem" />
            <Cab col="lote" rotulo="Lote" ordem={ordem} onOrdenar={onOrdenar} largura="16rem" />
            {verDel !== "atual" && <Cab col="dp" rotulo="DEL projetado" ordem={ordem} onOrdenar={onOrdenar} dir classe="bst-dp" largura="9.5rem" titulo={proxima ? `DEL que a vaca terá em ${br(proxima)} — é ele que decide se chega apta` : "DEL que a vaca terá na próxima aplicação"} />}
            {verDel !== "projetado" && <Cab col="da" rotulo="DEL atual" ordem={ordem} onOrdenar={onOrdenar} dir largura="8rem" titulo={`DEL de hoje (${br(hojeLocal())})`} />}
            <th scope="col">Situação</th>
          </tr>
        </thead>
        <tbody>
          {linhas.length === 0 && <tr><td colSpan={6} className="bst-vazio">{carregando ? "Carregando a lista de BST…" : filtrando ? "Nenhum animal bate com o filtro." : "Nenhum animal nesta condição."}</td></tr>}
          {linhas.map((a) => (
            <tr key={a.numero} className={marcadas.has(a.numero) ? "gv-linha-marcada" : undefined}>
              <td><input type="checkbox" checked={marcadas.has(a.numero)} onChange={() => onToggle(a.numero)} aria-label={`Marcar ${a.numero}`} /></td>
              <td className="gv-forte gv-num">{a.numero}{a.inducao && <span className="bst-il" title="Entrou no BST pelo protocolo de indução de lactação">(ind.lact.)</span>}</td>
              <td>{a.lote}</td>
              {verDel !== "atual" && <td className="gv-dir"><span className="bst-dp-v">{a.delProjetado ?? "—"}</span></td>}
              {verDel !== "projetado" && <td className="gv-dir"><span className="bst-da-v">{a.delAtual ?? "—"}</span></td>}
              <td className="bst-sit"><SituacaoBst a={a} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ParametrosLinha({ p, onChange, produtos, itens, responsaveis, incluirSemEstoque, onIncluirSemEstoque }: {
  p: ParamsAplicacao; onChange: (n: Partial<ParamsAplicacao>) => void; produtos: string[]; itens: ItemEstoque[]; responsaveis: string[];
  incluirSemEstoque: boolean; onIncluirSemEstoque: (v: boolean) => void;
}) {
  return (
    <div className="bst-params" role="group" aria-label="Dose e produto">
      <div className="bst-params-tit gv-rotulo"><span className="gv-n" aria-hidden="true">2</span>Dados da aplicação</div>
      <div className="gv-campo" style={{ width: "9.5rem" }}><label htmlFor="bst-data">Data</label><input id="bst-data" type="date" value={p.data} onChange={(e) => onChange({ data: e.target.value })} /></div>
      <div className="gv-campo" style={{ width: "13rem" }}>
        <label htmlFor="bst-produto">Produto</label>
        <select id="bst-produto" value={p.produto} disabled={!produtos.length} onChange={(e) => onChange({ produto: e.target.value, unidade: itens.find((i) => i.nome === e.target.value)?.unidade || p.unidade })}>
          {!produtos.length && <option value="">Nenhum produto disponível</option>}
          {produtos.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <label className="gv-ajuda" style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginTop: "0.25rem", cursor: "pointer" }}
          title="Mostra também os produtos ativos que estão com saldo zerado. Produtos inativos nunca aparecem.">
          <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => onIncluirSemEstoque(e.target.checked)} />
          Incluir produtos sem estoque
        </label>
      </div>
      <div className="gv-campo" style={{ width: "5.5rem" }}><label htmlFor="bst-dose">Dose</label><input id="bst-dose" type="text" inputMode="decimal" autoComplete="off" value={p.dose} placeholder="opc." onChange={(e) => onChange({ dose: e.target.value })} /></div>
      <div className="gv-campo" style={{ width: "6.5rem" }}><label htmlFor="bst-un">Unidade</label><input id="bst-un" value={p.unidade} placeholder="unidade" onChange={(e) => onChange({ unidade: e.target.value })} /></div>
      <div className="gv-campo">
        <span className="bst-rot" id="bst-lbl-dose">A dose é</span>
        <div className="bst-mini" role="group" aria-labelledby="bst-lbl-dose">
          <button type="button" aria-pressed={p.porAnimal} onClick={() => onChange({ porAnimal: true })}>Por animal</button>
          <button type="button" aria-pressed={!p.porAnimal} onClick={() => onChange({ porAnimal: false })} title="A dose é o total já aplicado no grupo: o sistema divide pelo nº de animais antes de baixar do estoque.">Total do lote selecionado</button>
        </div>
      </div>
      <div className="gv-campo" style={{ width: "10rem" }}>
        <label htmlFor="bst-resp">Responsável</label>
        <select id="bst-resp" value={p.resp} onChange={(e) => onChange({ resp: e.target.value })}>
          <option value="">Opcional</option>
          {responsaveis.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <p className="gv-ajuda" style={{ flex: "1 1 14rem", alignSelf: "center" }}>
        Sem dose, o BST é registrado mas o estoque não baixa. Data futura = agenda (nada baixa agora).
        {!produtos.length && <> Só aparecem produtos ativos com finalidade Medicamento e conta gerencial padrão 3.01.04.02 - BST{incluirSemEstoque ? "" : ", com saldo em estoque"}.</>}
      </p>
    </div>
  );
}

function BarraBst({ seg, n, nAptas, nIncluir, nRe, ocultas, p, previsao, paramsAberto, onParams, onAbrirParams, conf, ocupado, retorno, produtos, itens, responsaveis,
  incluirSemEstoque, onIncluirSemEstoque, onPedir, onCancelar, onConfirmar, onLimpar, onFecharRetorno, onVerIncluir }: {
  seg: Seg; n: number; nAptas: number; nIncluir: number; nRe: number; ocultas: number; p: ParamsAplicacao; previsao: string; paramsAberto: boolean;
  onParams: (x: Partial<ParamsAplicacao>) => void; onAbrirParams: () => void; conf: ConfirmacaoBst | null; ocupado: boolean; retorno: RetornoBst | null;
  produtos: string[]; itens: ItemEstoque[]; responsaveis: string[]; incluirSemEstoque: boolean; onIncluirSemEstoque: (v: boolean) => void;
  onPedir: (t: AcaoBst) => void; onCancelar: () => void; onConfirmar: (c: ConfirmacaoBst) => void; onLimpar: () => void; onFecharRetorno: () => void; onVerIncluir: () => void;
}) {
  const inaptas = seg === "inaptas";
  const futura = p.data > hojeLocal();
  const confRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (conf) confRef.current?.focus(); }, [conf]);
  useEffect(() => {
    if (!conf || ocupado) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onCancelar(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [conf, ocupado, onCancelar]);

  let textoConf: React.ReactNode = null; let rotuloConf = "";
  if (conf) {
    const k = conf.alvo.length;
    const animais = `${k} ${plural(k, "animal", "animais")}`;
    if (conf.tipo === "aplicar") {
      rotuloConf = futura ? "Confirmar agendamento" : doseTotal(p, k) !== null && p.unidade.trim() ? "Confirmar e baixar estoque" : "Confirmar aplicação";
      textoConf = <>{futura ? <>Agendar BST para <strong>{br(p.data)}</strong> em {animais}? </> : <>Aplicar BST em <strong>{animais}</strong> em {br(p.data)}? </>}{previsao}</>;
    } else if (conf.tipo === "inapta") {
      rotuloConf = `Marcar ${k} como ${plural(k, "inapta", "inaptas")}`;
      textoConf = <>Marcar <strong>{animais}</strong> como {plural(k, "inapta", "inaptas")}? Não lança aplicação nem mexe no estoque; {plural(k, "passa", "passam")} para “Incluir no próximo BST” com o selo Reanalisar.</>;
    } else {
      rotuloConf = `Marcar ${k} como ${plural(k, "apta", "aptas")}`;
      textoConf = <>Marcar <strong>{animais}</strong> como {plural(k, "apta", "aptas")}? {plural(k, "Ela fica", "Elas ficam")} em “Incluir no próximo BST” e só {plural(k, "conta", "contam")} como {plural(k, "apta", "aptas")} de novo depois de uma nova aplicação.</>;
    }
  }

  return (
    <div className="gv-barra">
      {retorno && (
        <div className="bst-ret" role={retorno.tipo === "erro" ? "alert" : "status"}>
          {retorno.tipo === "ok" ? <span className="gp-ok">✓</span> : <span className="gp-erro">Não deu certo.</span>}
          <span className="bst-ret-txt">
            {retorno.texto}
            {retorno.avisos && retorno.avisos.length > 0 && <ul>{retorno.avisos.map((a, k) => <li key={k}>{a}</li>)}</ul>}
          </span>
          {retorno.tentar && <button type="button" className="gp-link" onClick={() => onConfirmar(retorno.tentar as ConfirmacaoBst)}>Tentar de novo</button>}
          {retorno.verIncluir && <button type="button" className="gp-link" onClick={onVerIncluir}>Ver em Incluir</button>}
          <button type="button" className="gp-link" onClick={onFecharRetorno} aria-label="Fechar aviso">Fechar</button>
        </div>
      )}
      {!inaptas && paramsAberto && !conf && (
        <ParametrosLinha p={p} onChange={onParams} produtos={produtos} itens={itens} responsaveis={responsaveis}
          incluirSemEstoque={incluirSemEstoque} onIncluirSemEstoque={onIncluirSemEstoque} />
      )}
      <div className="gv-barra-miolo">
        {conf ? (
          <div className="bst-conf" role="alertdialog" aria-label="Confirmação">
            <p>{textoConf}</p>
            <button type="button" className="btn-ghost" disabled={ocupado} onClick={onCancelar}>Cancelar</button>
            <button type="button" ref={confRef} className={conf.tipo === "inapta" ? "btn-ghost bst-perigo" : "btn-primary-gold"} disabled={ocupado} onClick={() => onConfirmar(conf)}>
              {ocupado ? "Enviando…" : rotuloConf}
            </button>
          </div>
        ) : (
          <>
            <div className="gv-barra-resumo bst-resumo" aria-live="polite">
              {n === 0 ? <b>Nenhuma selecionada</b> : (
                <b>{n} {plural(n, "selecionada", "selecionadas")}
                  {!inaptas && <span style={{ fontWeight: 400 }}> ({nAptas} {plural(nAptas, "apta", "aptas")} · {nIncluir} a incluir)</span>}
                  {ocultas > 0 && <span style={{ fontWeight: 400, color: "var(--ft-ambar)" }}> · {ocultas} {plural(ocultas, "oculta", "ocultas")} pelo filtro</span>}
                </b>
              )}
              <span className="bst-resumo-linha">
                {n === 0 ? "Marque os animais na tabela para aplicar, agendar ou marcar inapta."
                  : inaptas ? "Voltam para “Incluir no próximo BST” com o selo Reanalisar; só viram aptas de novo depois de uma nova aplicação."
                  : previsao}
                {n > 0 && <> <button type="button" className="gp-link" onClick={onLimpar}>Limpar seleção</button></>}
              </span>
            </div>
            {!inaptas && !paramsAberto && (
              <span className="bst-resumo-linha">{br(p.data)} · {p.produto || "sem produto"} · {p.dose ?`${p.dose} ${p.unidade} ${p.porAnimal ? "por animal" : "no total"}` : "sem dose"}</span>
            )}
            {!inaptas && (
              <button type="button" className="bst-btn" aria-expanded={paramsAberto} onClick={onAbrirParams}>
                Dose e produto {paramsAberto ? <ChevronUp size={13} aria-hidden="true" /> : <ChevronDown size={13} aria-hidden="true" />}
              </button>
            )}
            {inaptas ? (
              <BotaoOuro desabilitado={n === 0 || ocupado} onClick={() => onPedir("apta")}><Check size={14} aria-hidden="true" /> Marcar como apta</BotaoOuro>
            ) : (
              <>
                {seg === "incluir" && nRe > 0 && (
                  <button type="button" className="btn-ghost" disabled={ocupado} onClick={() => onPedir("apta")}
                    title="Só para as marcadas com selo Reanalisar: tira a retirada; voltam a aptas depois de uma nova aplicação">Marcar como apta ({nRe})</button>
                )}
                <button type="button" className="btn-ghost bst-perigo" disabled={n === 0 || ocupado} onClick={() => onPedir("inapta")}><Ban size={14} aria-hidden="true" /> Marcar inapta</button>
                <BotaoOuro desabilitado={n === 0 || ocupado} onClick={() => onPedir("aplicar")}><Check size={14} aria-hidden="true" /> {futura ? "Agendar BST" : "Aplicar BST"}</BotaoOuro>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function PainelLancarBst({
  agenda, onAtualizado, aplicarBst = aplicarBstLote, marcarInapta: marcarInaptaFn = marcarInaptaBst,
}: {
  // Payload cru de fetchAgenda() (cada chamador tem seu próprio tipo de agenda); a tela só lê as listas bst_* e as datas.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  agenda: any; onAtualizado: () => void;
  aplicarBst?: (dados: DadosAplicarBst) => Promise<unknown>;
  marcarInapta?: (dados: DadosMarcarInaptaBst) => Promise<unknown>;
}) {
  const [seg, setSeg] = useState<Seg>("aptas");
  const [marcadas, setMarcadas] = useState<Marcadas>({ aptas: new Set(), incluir: new Set(), inaptas: new Set() });
  const [lotes, setLotes] = useState<string[]>([]);
  const [busca, setBusca] = useState("");
  const [verDel, setVerDel] = useState<FiltroDel>("ambos");
  const [ordem, setOrdem] = useState<Ordem>({ col: "lote", dir: 1 });
  const [ajusteAberto, setAjusteAberto] = useState(false);
  const [ajusteMsg, setAjusteMsg] = useState("");
  const [paramsAberto, setParamsAberto] = useState(true);
  // Produto começa vazio: o painel escolhe o primeiro item elegível assim que o estoque carrega (nada de nome fixo).
  const [paramsBase, setParams] = useState<ParamsAplicacao>(() => ({ data: hojeLocal(), produto: "", dose: "", unidade: "unidade", porAnimal: true, resp: "" }));
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [conf, setConf] = useState<ConfirmacaoBst | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [retorno, setRetorno] = useState<RetornoBst | null>(null);
  const [estoqueItens, setEstoqueItens] = useState<ItemEstoqueCadastro[]>([]);
  const { pessoas: pessoasAtivas } = usePessoasAtivas();
  const admin = ehAdmin();

  // Mesma chave de cache da aba Secagem do app de campo: sem internet, usa a última lista de estoque baixada.
  const carregarEstoque = useCallback(() => {
    fetchComCache<{ itens: ItemEstoqueCadastro[] }>("estoque_itens_completo", () => fetchEstoqueAtivos())
      .then(({ dados }) => setEstoqueItens(dados?.itens || []));
  }, []);
  useEffect(carregarEstoque, [carregarEstoque]);

  // Produtos selecionáveis: finalidade Medicamento + conta gerencial padrão 3.01.04.02 (BST) + item ativo, só com saldo — a menos que
  // "Incluir produtos sem estoque" esteja marcado (inativos nunca entram). Independe do nome (ver itensParaBst em lib/bstLote.ts).
  const itensBst: ItemEstoque[] = useMemo(() => itensParaBst(estoqueItens, incluirSemEstoque), [estoqueItens, incluirSemEstoque]);
  const produtos = useMemo(() => Array.from(new Set(itensBst.map((i) => i.nome))), [itensBst]);
  // O produto usado é sempre um da lista: ao carregar o estoque, ao desmarcar "sem estoque" ou se o item escolhido deixou de ser elegível,
  // cai no primeiro elegível (e na unidade dele) — sem nome fixo e sem efeito.
  const params = useMemo<ParamsAplicacao>(() => {
    if (produtos.includes(paramsBase.produto)) return paramsBase;
    const primeiro = itensBst[0];
    return { ...paramsBase, produto: primeiro?.nome ?? "", unidade: primeiro?.unidade || paramsBase.unidade };
  }, [paramsBase, produtos, itensBst]);
  const responsaveis = useMemo(() => pessoasAtivas.map((p) => p.nome).filter(Boolean), [pessoasAtivas]);

  const agendaBst: AgendaBst = agenda;
  const segs = useMemo(() => segmentosDaAgenda(agendaBst), [agendaBst]);
  const carregando = agendaBst == null;
  const proxima: string | null = agendaBst?.proxima_visita_bst ?? null;
  const intervalo: number | null = typeof agendaBst?.intervalo_bst === "number" ? agendaBst.intervalo_bst : null;

  const visiveis = useMemo(() => ordenarAnimais(filtrarAnimais(segs[seg], lotes, busca), ordem), [segs, seg, lotes, busca, ordem]);
  const contagemLote = useMemo(() => {
    const c: Record<string, number> = {};
    segs[seg].forEach((a) => { c[a.lote] = (c[a.lote] ?? 0) + 1; });
    return c;
  }, [segs, seg]);
  const todosLotes = useMemo(() => Array.from(new Set([...segs.aptas, ...segs.incluir, ...segs.inaptas].map((a) => a.lote))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })), [segs]);

  // Só vale a marcação de quem ainda está na lista (depois de aplicar, a agenda recarrega e quem saiu some).
  const marcadasValidas = useMemo<Marcadas>(() => {
    const v = (s: Seg) => new Set(segs[s].filter((a) => marcadas[s].has(a.numero)).map((a) => a.numero));
    return { aptas: v("aptas"), incluir: v("incluir"), inaptas: v("inaptas") };
  }, [segs, marcadas]);
  const alvo = useMemo(() => alvoDaAcao(seg, marcadasValidas, segs), [seg, marcadasValidas, segs]);
  const nRe = useMemo(() => reanalisadasMarcadas(marcadasValidas, segs).length, [marcadasValidas, segs]);
  const nAptas = marcadasValidas.aptas.size, nIncluir = marcadasValidas.incluir.size;
  const ocultas = alvo.filter((a) => filtrarAnimais([a], lotes, busca).length === 0).length;

  const todasMarcadas = visiveis.length > 0 && visiveis.every((a) => marcadasValidas[seg].has(a.numero));
  const toggle = (n: string) => setMarcadas((m) => { const s = new Set(m[seg]); if (s.has(n)) s.delete(n); else s.add(n); return { ...m, [seg]: s }; });
  const alternarTodas = () => setMarcadas((m) => { const s = new Set(m[seg]); visiveis.forEach((a) => (todasMarcadas ? s.delete(a.numero) : s.add(a.numero))); return { ...m, [seg]: s }; });
  const limpar = () => setMarcadas((m) => (seg === "inaptas" ? { ...m, inaptas: new Set() } : { ...m, aptas: new Set(), incluir: new Set() }));
  const trocarSeg = (s: Seg) => { setSeg(s); setConf(null); };
  const ordenar = (col: Ordem["col"]) => setOrdem((o) => (o.col === col ? { col, dir: o.dir === 1 ? -1 : 1 } : { col, dir: 1 }));

  const nAcao = alvo.length;
  const previsaoTxt = textoPrevisao(preverEstoque(params, nAcao, hojeLocal(), itensBst));
  const rotTodas = SEGMENTOS.find((s) => s.id === seg)?.todas ?? "";

  const pedir = (tipo: AcaoBst) => {
    const quem = tipo === "apta" && seg === "incluir" ? reanalisadasMarcadas(marcadasValidas, segs) : alvo;
    if (!quem.length) return;
    setRetorno(null); setConf({ tipo, alvo: quem });
  };

  const executar = async (c: ConfirmacaoBst) => {
    if (ocupado) return;
    setOcupado(true); setRetorno(null); setConf(c);
    const numeros = c.alvo.map((a) => a.numero);
    try {
      let novo: RetornoBst;
      if (c.tipo === "aplicar") {
        const p = montarPayloadAplicar(params, numeros);
        if ("erro" in p) { setRetorno({ tipo: "erro", texto: p.erro }); setConf(null); return; }
        const r = await aplicarBst(p.dados);
        const lido = interpretarRetornoAplicar(r, numeros.length, params, hojeLocal(), itensBst);
        novo = { tipo: "ok", texto: lido.texto, avisos: lido.avisos };
        if (lido.tipo === "ok" && !lido.agendou) setParamsAberto(false);
        carregarEstoque();
      } else {
        const inapta = c.tipo === "inapta";
        const r = await marcarInaptaFn({ numeros_matriz: numeros, inapta });
        const lido = textoRetornoMarcar(r, numeros.length, inapta);
        novo = { tipo: "ok", texto: lido.texto, verIncluir: seg === "inaptas" || inapta };
      }
      setMarcadas((m) => {
        const tirar = (s: Set<string>) => { const x = new Set(s); numeros.forEach((n) => x.delete(n)); return x; };
        return { aptas: tirar(m.aptas), incluir: tirar(m.incluir), inaptas: tirar(m.inaptas) };
      });
      setRetorno(novo); setConf(null);
      onAtualizado();
    } catch (e) {
      setRetorno({ tipo: "erro", texto: `${mensagemDe(e, "Falha ao enviar.")} Nada foi gravado — a seleção continua marcada.`, tentar: c });
      setConf(null);
    } finally {
      setOcupado(false);
    }
  };

  // Exportação (PDF/Excel) das 3 listas juntas — a coluna "Situação" identifica de qual lista a linha veio.
  const colunasExport: ColunaExport[] = [
    { header: "Nº", key: "numero_matriz" }, { header: "Lote", key: "grupo" }, { header: "DEL atual", key: "del_atual" },
    { header: "DEL projetado", key: "del_projetado" }, { header: "Situação", key: "situacao" }, { header: "Obs.", key: "obs" },
  ];
  const linhasExport = useMemo(() => [
    ...segs.aptas.map((a) => ({ numero_matriz: a.numero, grupo: a.lote, del_atual: a.delAtual, del_projetado: a.delProjetado, situacao: "Apta", obs: "" })),
    ...segs.incluir.map((a) => ({ numero_matriz: a.numero, grupo: a.lote, del_atual: a.delAtual, del_projetado: a.delProjetado, situacao: "Incluir no próximo BST", obs: a.reanalise ? (a.motivo || "Retirada do BST — revisar") : "Nunca aplicada — apta na próxima" })),
    ...segs.inaptas.map((a) => ({ numero_matriz: a.numero, grupo: a.lote, del_atual: a.delAtual, del_projetado: a.delProjetado, situacao: "Inapta", obs: a.motivo })),
  ], [segs]);

  const nomeSeg = SEGMENTOS.find((s) => s.id === seg)?.nome ?? "";

  return (
    <div className="gp-raiz">
      <style>{CSS_RAIZ + CSS_BST}</style>
      <div className="bst-topo">
        <h2 className="bst-pergunta">Quem recebe BST na próxima visita?</h2>
        <span className="gv-ajuda">Somatotropina bovina — marque quem recebe e aplique, agende ou marque inapta.</span>
      </div>
      <Proxima proxima={proxima} intervalo={intervalo} aberto={ajusteAberto} podeAjustar={admin} mensagem={ajusteMsg} onAjustar={() => { setAjusteAberto((v) => !v); setAjusteMsg(""); }} />
      {ajusteAberto && (
        <PainelAjuste key={proxima ?? "sem"} proxima={proxima} intervalo={intervalo} onFechar={() => setAjusteAberto(false)}
          onAjustado={(msg) => { setAjusteMsg(msg); setAjusteAberto(false); onAtualizado(); }} />
      )}
      <Segmentos seg={seg} onTrocar={trocarSeg}
        contagens={{ aptas: segs.aptas.length, incluir: segs.incluir.length, inaptas: segs.inaptas.length }}
        marcadas={{ aptas: nAptas, incluir: nIncluir, inaptas: marcadasValidas.inaptas.size }} />

      <Passo n={1} id="bst-p1" titulo={`Marque quem recebe — ${nomeSeg}`}
        direita={<span className="gp-contagem" aria-live="polite">{visiveis.filter((a) => marcadasValidas[seg].has(a.numero)).length} de {visiveis.length} marcadas</span>}>
        <div className="bst-tool">
          <FiltroLotes lotes={todosLotes} contagem={contagemLote} marcados={lotes} onChange={setLotes} />
          <input type="search" className="bst-busca" aria-label="Buscar animal pelo número" placeholder="Buscar nº" value={busca} onChange={(e) => setBusca(e.target.value)} />
          <button type="button" className="bst-btn" disabled={!visiveis.length} onClick={alternarTodas}>{todasMarcadas ? "Desmarcar" : "Marcar todas"} {rotTodas} ({visiveis.length})</button>
          <span style={{ flex: 1 }} />
          <span className="bst-rot" id="bst-lbl-del">DEL</span>
          <div className="bst-mini" role="group" aria-labelledby="bst-lbl-del">
            {([["ambos", "Ambos"], ["projetado", "Projetado"], ["atual", "Atual"]] as const).map(([v, r]) => <button key={v} type="button" aria-pressed={verDel === v} onClick={() => setVerDel(v)}>{r}</button>)}
          </div>
          <span className="bst-rot" style={{ marginLeft: "0.6rem" }}>Exportar as 3 listas</span>
          <ExportarBotoes titulo="BST — DEL atual e projetado" colunas={colunasExport} linhas={linhasExport} nomeArquivoBase="bst_del" />
        </div>
        <TabelaBst linhas={visiveis} carregando={carregando} filtrando={lotes.length > 0 || busca.trim() !== ""} marcadas={marcadasValidas[seg]} onToggle={toggle} onTodas={alternarTodas}
          verDel={verDel} ordem={ordem} onOrdenar={ordenar} proxima={proxima} />
        <p className="gv-ajuda">
          <b>DEL projetado</b> é o DEL que a vaca terá {proxima ? `em ${br(proxima)}, data da próxima aplicação` : "na data da próxima aplicação"} — é ele que decide se chega apta na hora certa. <b>DEL atual</b> é o de hoje.
          {seg === "incluir" && <> <b>Reanalisar</b>: foi retirada do BST ou entrou por indução de lactação — revise antes de incluir de novo.</>}
        </p>
      </Passo>

      <BarraBst seg={seg} n={nAcao} nAptas={nAptas} nIncluir={nIncluir} nRe={nRe} ocultas={ocultas} p={params} previsao={previsaoTxt} paramsAberto={paramsAberto}
        onParams={(x) => { setParams((p) => ({ ...p, ...x })); setRetorno(null); }} onAbrirParams={() => setParamsAberto((v) => !v)}
        conf={conf} ocupado={ocupado} retorno={retorno} produtos={produtos} itens={itensBst} responsaveis={responsaveis}
        incluirSemEstoque={incluirSemEstoque} onIncluirSemEstoque={(v) => { setIncluirSemEstoque(v); setRetorno(null); }}
        onPedir={pedir} onCancelar={() => setConf(null)} onConfirmar={executar} onLimpar={limpar} onFecharRetorno={() => setRetorno(null)}
        onVerIncluir={() => { trocarSeg("incluir"); setRetorno(null); }} />
    </div>
  );
}
