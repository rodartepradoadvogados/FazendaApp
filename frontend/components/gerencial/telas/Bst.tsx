"use client";
// Lançamentos › Produção › BST — PROPOSTA (variante desktop de apresentação, dados de exemplo, sem fetch).
//
// Conceito: uma única PERGUNTA — "quem recebe BST na próxima visita?" — com a lista já respondida. Em vez de 3 tabelas lado a
// lado (cada uma com rolagem própria) há UMA tabela com 3 segmentos (Aptas | Incluir no próximo BST | Inaptas) e uma barra
// fixa no pé com os dados da aplicação, o resumo do estoque e o retorno da ação. As ações dependem do segmento, então a
// mistura inválida (aplicar + marcar inapta na mesma seleção) é impossível por construção.
//
// A VERSÃO LIGADA A DADOS (components/PainelLancarBst.tsx) PRECISA PRESERVAR:
//  · fonte: fetchAgenda() → bst_elegiveis (Aptas), bst_nunca_aplicados (Incluir; vem com requer_reanalise/origem_inducao_lactacao/
//    motivo_exclusao), bst_excluidos (Inaptas; motivo_exclusao existe em TODAS — hoje só aparece nas reanalisadas), proxima_visita_bst,
//    intervalo_bst. Colunas: caixa, Nº, "(ind.lact.)", Lote, DEL atual, DEL projetado, situação/obs; ordenação por coluna (useOrdenacao).
//  · props de injeção do app de campo: aplicarBst(dados) e marcarInapta(dados) — a barra chama SÓ elas (default aplicarBstLote /
//    marcarInaptaBst); onAtualizado() recarrega a agenda. aplicarBst devolve {aplicados, agendados, avisos[], proxima_aplicacao_calculada}:
//    é daí que sai o retorno na barra (hoje o resultado é descartado).
//  · POST /agenda/bst/aplicar {numeros_matriz, data_aplicacao, aplicado:true, produto, dose, unidade, responsavel, dose_por_animal}.
//    Data futura = agenda (nada baixa do estoque agora). Só baixa estoque se dose E unidade vierem preenchidas.
//  · POST /agenda/bst/marcar-inapta {numeros_matriz, inapta:true|false}. ATENÇÃO: o motor manda o animal retirado (inapta:true) e o
//    revertido (inapta:false) para "Incluir no próximo BST" com requer_reanalise — não para "Inaptas" (que é só por critério).
//  · produto: itens de estoque cujo nome casa MARCADORES_BST (padrão "Lactotropin"); unidade livre; "por animal | total do lote".
//  · ajuste da próxima aplicação: POST /producao/bst/ajustar-proxima-aplicacao {nova_data, modo:"intervalo"|"referencia"} (só admin).
//  · exportar PDF/Excel das 3 listas juntas (ExportarBotoes, coluna "Situação"); lote multi-filtro (MultiFiltro); Ver atual/projetado/ambos.
//  · Tabela NÃO pode ser declarada dentro do componente pai (remonta a cada clique) — aqui tudo é subcomponente de módulo.
import React, { useState } from "react";
import { Droplets, CalendarClock, Check, Ban, FileText, FileSpreadsheet, ChevronDown, ChevronUp, SlidersHorizontal } from "lucide-react";
import { QuadroGaveta, Passo, Selo, BotaoOuro } from "@/components/gerencial/kit";

type Seg = "aptas" | "incluir" | "inaptas";
type Animal = { n: string; lote: string; da: number; dp: number; obs?: string; re?: boolean; il?: boolean; nunca?: boolean };
type Ordem = { col: "n" | "lote" | "dp" | "da"; dir: 1 | -1 };

const LOTE: Record<string, string> = { A: "01 - Novilhas Alta", B: "02 - Vacas Alta", C: "03 - Média", D: "04 - Pós-parto/Tratamento" };
const HOJE = "2026-10-17";
const PROXIMA = "2026-10-27";
const ULTIMA = "2026-10-15";
const INTERVALO = 12;
const ESTOQUE = [{ nome: "Lactotropin", unidade: "unidade", quantidade: 50 }, { nome: "Boostin", unidade: "dose", quantidade: 20 }];
const RESPONSAVEIS = ["Jairo Nasser", "Edvaldo Souza", "Marta Lima"];
const SEGMENTOS: { id: Seg; nome: string; sub: string; tom: "ok" | "atencao" | "alerta" }[] = [
  { id: "aptas", nome: "Aptas", sub: "chegam aptas na data da próxima aplicação", tom: "ok" },
  { id: "incluir", nome: "Incluir no próximo BST", sub: "nunca aplicadas, indução de lactação ou retiradas", tom: "atencao" },
  { id: "inaptas", nome: "Inaptas p/ próxima aplicação", sub: "fora por critério (DEL, secagem)", tom: "alerta" },
];

type Linha = [string, string, number, number, { obs?: string; re?: number; il?: number; nunca?: number }?];
const BRUTO: Record<Seg, Linha[]> = {
  aptas: [
    ["1274", "B", 91, 101],
    ["10987", "B", 157, 167],
    ["3284", "B", 167, 177],
    ["2681", "B", 83, 93],
    ["3928", "B", 103, 113],
    ["11044", "B", 117, 127],
    ["3598", "B", 150, 160],
    ["3265", "B", 170, 180],
    ["3209", "B", 153, 163],
    ["11636", "B", 68, 78],
    ["1589", "B", 63, 73],
    ["2987", "B", 80, 90],
    ["2102", "C", 204, 214],
    ["1712", "C", 161, 171],
    ["2277", "C", 196, 206],
    ["2473", "C", 154, 164],
    ["1583", "C", 193, 203],
    ["3074", "C", 159, 169],
    ["3800", "C", 191, 201],
    ["3382", "C", 191, 201],
    ["3100", "C", 170, 180],
    ["2507", "A", 76, 86],
    ["3065", "A", 106, 116],
    ["2964", "A", 77, 87],
    ["2797", "A", 108, 118],
    ["3841", "A", 98, 108],
  ],
  incluir: [
    ["1296", "B", 60, 70, {"nunca":1}],
    ["1302", "B", 55, 65, {"nunca":1}],
    ["11153", "C", 62, 72, {"nunca":1}],
    ["9378", "A", 51, 61, {"nunca":1}],
    ["3335", "A", 28, 38, {"obs":"Indução de lactação — protocolo já aplicou BST, incluída para a próxima aplicação","re":1,"il":1}],
    ["075", "B", 143, 153, {"obs":"Excluída manualmente do BST — revisar na próxima aplicação","re":1}],
  ],
  inaptas: [
    ["2574", "D", 26, 36, {"obs":"DEL 36 < 60 dias"}],
    ["3007", "D", 6, 16, {"obs":"DEL 16 < 60 dias"}],
    ["1542", "D", 18, 28, {"obs":"DEL 28 < 60 dias"}],
    ["3281", "D", 4, 14, {"obs":"DEL 14 < 60 dias"}],
    ["1278", "D", 26, 36, {"obs":"DEL 36 < 60 dias"}],
    ["2398", "D", 25, 35, {"obs":"DEL 35 < 60 dias"}],
    ["2105", "D", 10, 20, {"obs":"DEL 20 < 60 dias"}],
    ["2209", "D", 27, 37, {"obs":"DEL 37 < 60 dias"}],
    ["1770", "D", 24, 34, {"obs":"DEL 34 < 60 dias"}],
    ["3376", "D", 12, 22, {"obs":"DEL 22 < 60 dias"}],
    ["1793", "A", 21, 31, {"obs":"DEL 31 < 60 dias"}],
    ["2228", "A", 21, 31, {"obs":"DEL 31 < 60 dias"}],
    ["3023", "A", 35, 45, {"obs":"DEL 45 < 60 dias"}],
    ["1121", "A", 36, 46, {"obs":"DEL 46 < 60 dias"}],
    ["3937", "A", 37, 47, {"obs":"DEL 47 < 60 dias"}],
    ["2819", "A", 22, 32, {"obs":"DEL 32 < 60 dias"}],
    ["2296", "A", 33, 43, {"obs":"DEL 43 < 60 dias"}],
    ["10648", "B", 21, 31, {"obs":"DEL 31 < 60 dias"}],
    ["1513", "B", 30, 40, {"obs":"DEL 40 < 60 dias"}],
    ["3613", "B", 28, 38, {"obs":"DEL 38 < 60 dias"}],
    ["3005", "B", 35, 45, {"obs":"DEL 45 < 60 dias"}],
    ["1365", "C", 231, 241, {"obs":"Faltam apenas 4 dias para secar (mínimo 30)"}],
    ["2235", "C", 213, 223, {"obs":"Faltam apenas 22 dias para secar (mínimo 30)"}],
    ["3163", "C", 221, 231, {"obs":"Faltam apenas 14 dias para secar (mínimo 30)"}],
    ["3893", "B", 212, 222, {"obs":"Faltam apenas 23 dias para secar (mínimo 30)"}],
    ["3032", "B", 220, 230, {"obs":"Faltam apenas 15 dias para secar (mínimo 30)"}],
  ],
};
const DADOS: Record<Seg, Animal[]> = {
  aptas: BRUTO.aptas.map(paraAnimal), incluir: BRUTO.incluir.map(paraAnimal), inaptas: BRUTO.inaptas.map(paraAnimal),
};
function paraAnimal([n, l, da, dp, ex]: Linha): Animal { return { n, lote: LOTE[l], da, dp, obs: ex?.obs, re: !!ex?.re, il: !!ex?.il, nunca: !!ex?.nunca }; }

const br = (iso: string) => iso.split("-").reverse().join("/");
const comparar = (o: Ordem) => (a: Animal, b: Animal) => {
  const c = o.col === "n" || o.col === "lote" ? a[o.col].localeCompare(b[o.col], undefined, { numeric: true }) : a[o.col] - b[o.col];
  return c * o.dir || a.n.localeCompare(b.n, undefined, { numeric: true });
};

const CSS = `
.bst-topo { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin-bottom: 0.7rem; }
.bst-pergunta { margin: 0; font-size: 1.1rem; font-weight: 800; letter-spacing: -0.01em; color: var(--text); }
.bst-prox { display: flex; align-items: center; gap: 1rem; padding: 0.55rem 0.9rem; border: 1px solid var(--border); background: var(--surface-2); margin-bottom: 0.7rem; flex-wrap: wrap; }
.bst-prox-data { font-size: 1.3rem; font-weight: 800; font-variant-numeric: tabular-nums; color: var(--text); line-height: 1.1; }
.bst-prox-rot { display: block; font-size: 0.66rem; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); }
.bst-prox-txt { font-size: 0.8rem; color: var(--text-muted); }
.bst-prox-txt b { color: var(--text); font-variant-numeric: tabular-nums; }
.bst-ajuste { padding: 0.8rem 0.9rem; border: 1px solid var(--border); background: var(--surface); margin: -0.35rem 0 0.7rem; display: flex; flex-direction: column; gap: 0.6rem; }
.bst-segs { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--border); background: var(--surface); margin-bottom: 0.9rem; }
.bst-seg { text-align: left; font: inherit; color: var(--text); background: var(--surface); border: 0; border-right: 1px solid var(--border); border-bottom: 3px solid transparent;
  padding: 0.55rem 0.9rem; cursor: pointer; min-width: 0; display: flex; flex-direction: column; gap: 0.1rem; }
.bst-seg:last-child { border-right: 0; }
.bst-seg:hover { background: var(--surface-2); }
.bst-seg[aria-pressed="true"] { background: var(--ft-ouro-tint); border-bottom-color: var(--ft-ouro); }
.bst-seg-linha { display: flex; align-items: baseline; gap: 0.6rem; }
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
.bst-btn:hover { background: var(--surface-2); }
.bst-in { min-height: 2rem; padding: 0.3rem 0.6rem; font: inherit; font-size: 0.82rem; color: var(--text); background: var(--surface-2); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); min-width: 0; }
.bst-in:focus-visible, .bst-btn:focus-visible, .bst-seg:focus-visible, .bst-th:focus-visible { outline: 2px solid var(--ft-ouro); outline-offset: -1px; }
.bst-lotes { position: relative; }
.bst-lotes > summary { list-style: none; }
.bst-lotes > summary::-webkit-details-marker { display: none; }
.bst-lotes-painel { position: absolute; z-index: 3; top: calc(100% + 2px); left: 0; min-width: 17rem; padding: 0.4rem; background: var(--surface); border: 1px solid var(--border-strong, var(--border)); box-shadow: var(--shadow-sm); }
.bst-lotes-painel label { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.4rem; font-size: 0.82rem; cursor: pointer; }
.bst-lotes-painel label:hover { background: var(--surface-2); }
.bst-lotes-painel input { accent-color: var(--ft-ouro); width: 1.05rem; height: 1.05rem; }
.bst-lotes-painel i { margin-left: auto; font-style: normal; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.bst-mini { display: inline-flex; border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); overflow: hidden; }
.bst-mini button { min-height: 2rem; padding: 0.25rem 0.65rem; font: inherit; font-size: 0.76rem; font-weight: 600; color: var(--text-muted); background: var(--surface); border: 0; border-right: 1px solid var(--border); cursor: pointer; white-space: nowrap; }
.bst-mini button:last-child { border-right: 0; }
.bst-mini button[aria-pressed="true"] { background: var(--ft-ouro-tint); color: var(--ft-ouro-txt); box-shadow: inset 0 -2px 0 var(--ft-ouro); }
.bst-rot { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); }
.bst-th { display: inline-flex; align-items: center; gap: 0.25rem; padding: 0; margin: 0; font: inherit; letter-spacing: inherit; text-transform: inherit; color: inherit; background: none; border: 0; cursor: pointer; }
.bst-tab { table-layout: fixed; }
.bst-tab thead th.bst-dp { border-bottom: 2px solid var(--ft-ouro); }
.bst-dp-v { font-size: 0.95rem; font-weight: 800; font-variant-numeric: tabular-nums; color: var(--text); }
.bst-da-v { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.bst-obs { margin-left: 0.5rem; font-size: 0.78rem; color: var(--text-muted); }
.bst-il { margin-left: 0.4rem; font-size: 0.72rem; font-weight: 400; color: var(--ft-aco); }
.bst-params { display: flex; align-items: flex-end; gap: 0.7rem; flex-wrap: wrap; padding: 0.6rem 0.9rem 0.7rem; border-bottom: 1px solid var(--border); }
.bst-params .gv-campo input, .bst-params .gv-campo select { min-height: 2rem; padding: 0.3rem 0.5rem; }
.bst-params-tit { align-self: center; display: flex; align-items: center; gap: 0.55rem; margin-right: 0.3rem; }
.bst-resumo-linha { font-size: 0.78rem; color: var(--text-muted); }
.bst-resumo-linha strong { color: var(--text); font-variant-numeric: tabular-nums; }
.bst-resumo-linha em { font-style: normal; font-weight: 700; color: var(--ft-ambar); }
`;

// ── subcomponentes (todos fora do componente da tela) ──────────────────────────────────────────────────────────────

function Proxima({ aberto, onAjustar }: { aberto: boolean; onAjustar: () => void }) {
  return (
    <div className="bst-prox">
      <CalendarClock size={18} aria-hidden="true" style={{ color: "var(--ft-ouro-txt)" }} />
      <div><span className="bst-prox-rot">Próxima aplicação</span><span className="bst-prox-data">{br(PROXIMA)}</span></div>
      <span className="bst-prox-txt">em <b>10 dias</b> · intervalo entre aplicações: <b>{INTERVALO} dias</b></span>
      <span style={{ flex: 1 }} />
      <button type="button" className="bst-btn" aria-expanded={aberto} onClick={onAjustar}><SlidersHorizontal size={14} aria-hidden="true" /> Ajustar</button>
    </div>
  );
}

function PainelAjuste({ onFechar }: { onFechar: () => void }) {
  const [nova, setNova] = useState("2026-10-30");
  const [modo, setModo] = useState<"intervalo" | "referencia" | "">("");
  const mudou = nova !== PROXIMA;
  const dias = Math.round((Date.parse(nova) - Date.parse(ULTIMA)) / 86400000);
  return (
    <div className="bst-ajuste">
      <div className="gv-linha">
        <div className="gv-campo" style={{ width: "11rem" }}>
          <label htmlFor="bst-nova">Nova data da próxima aplicação</label>
          <input id="bst-nova" type="date" value={nova} onChange={(e) => { setNova(e.target.value); setModo(""); }} />
        </div>
        <p className="gv-ajuda" style={{ maxWidth: "46rem" }}>É uma decisão do rebanho inteiro, não de um animal. Ao mudar a data, diga como o sistema deve entender essa mudança:</p>
      </div>
      {mudou && (
        <div className="gv-grade" style={{ gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
          <button type="button" className="gv-cartao-opcao" aria-pressed={modo === "intervalo"} onClick={() => setModo("intervalo")}>
            <b>Novo intervalo entre aplicações</b>
            <span>O intervalo passa de {INTERVALO} para {dias} dias (da última aplicação, {br(ULTIMA)}, até {br(nova)}).</span>
          </button>
          <button type="button" className="gv-cartao-opcao" aria-pressed={modo === "referencia"} onClick={() => setModo("referencia")}>
            <b>Nova referência de contagem</b>
            <span>Mantém {INTERVALO} dias e passa a contar os próximos ciclos a partir de {br(nova)}.</span>
          </button>
        </div>
      )}
      <div className="gv-linha">
        <BotaoOuro desabilitado={!mudou || !modo}>Salvar ajuste</BotaoOuro>
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
            {marcadas[s.id] > 0 && <span className="bst-marc">{marcadas[s.id]} marcada{marcadas[s.id] > 1 ? "s" : ""}</span>}
          </span>
          <span className="bst-seg-sub">{s.sub}</span>
        </button>
      ))}
    </div>
  );
}

function FiltroLotes({ lotes, contagem, marcados, onChange }: { lotes: string[]; contagem: Record<string, number>; marcados: string[]; onChange: (l: string[]) => void }) {
  return (
    <details className="bst-lotes">
      <summary className="bst-btn" aria-label="Filtrar por lote">Lote: {marcados.length ? `${marcados.length} marcado${marcados.length > 1 ? "s" : ""}` : "todos"} <ChevronDown size={13} aria-hidden="true" /></summary>
      <div className="bst-lotes-painel">
        {lotes.map((l) => (
          <label key={l}>
            <input type="checkbox" checked={marcados.includes(l)} onChange={() => onChange(marcados.includes(l) ? marcados.filter((x) => x !== l) : [...marcados, l])} />
            {l}<i>{contagem[l] ?? 0}</i>
          </label>
        ))}
      </div>
    </details>
  );
}

function Cab({ col, rotulo, ordem, onOrdenar, dir, classe, titulo, largura }: { col: Ordem["col"]; rotulo: string; ordem: Ordem; onOrdenar: (c: Ordem["col"]) => void; dir?: "dir"; classe?: string; titulo?: string; largura?: string }) {
  const ativo = ordem.col === col;
  return (
    <th scope="col" className={[dir ? "gv-dir" : "", classe ?? ""].join(" ").trim()} aria-sort={ativo ? (ordem.dir === 1 ? "ascending" : "descending") : "none"} title={titulo} style={{ width: largura }}>
      <button type="button" className="bst-th" onClick={() => onOrdenar(col)}>
        {rotulo}{ativo && (ordem.dir === 1 ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronUp size={12} aria-hidden="true" />)}
      </button>
    </th>
  );
}

function Situacao({ a, seg }: { a: Animal; seg: Seg }) {
  if (seg === "aptas") return <Selo tom="ok">Apta</Selo>;
  if (seg === "inaptas") return <><Selo tom="bloqueio">Inapta</Selo><span className="bst-obs">{a.obs}</span></>;
  if (a.re) return <><Selo tom="atencao" titulo="Retirada do BST — revisar antes de incluir de novo">Reanalisar</Selo><span className="bst-obs">{a.obs}</span></>;
  return <><Selo tom="info">Nunca aplicada</Selo><span className="bst-obs">apta na próxima aplicação</span></>;
}

function TabelaBst({ seg, linhas, marcadas, onToggle, onTodas, verDel, ordem, onOrdenar }: {
  seg: Seg; linhas: Animal[]; marcadas: Set<string>; onToggle: (n: string) => void; onTodas: () => void; verDel: "ambos" | "atual" | "projetado"; ordem: Ordem; onOrdenar: (c: Ordem["col"]) => void;
}) {
  const todas = linhas.length > 0 && linhas.every((l) => marcadas.has(l.n));
  return (
    <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "24rem" }}>
      <table className="gv-tabela bst-tab">
        <thead>
          <tr>
            <th scope="col" style={{ width: "2.6rem" }}>
              <input type="checkbox" checked={todas} onChange={onTodas} aria-label="Marcar todas as linhas visíveis deste segmento" disabled={!linhas.length} />
            </th>
            <Cab col="n" rotulo="Nº" ordem={ordem} onOrdenar={onOrdenar} largura="9rem" />
            <Cab col="lote" rotulo="Lote" ordem={ordem} onOrdenar={onOrdenar} largura="16rem" />
            {verDel !== "atual" && <Cab col="dp" rotulo="DEL projetado" ordem={ordem} onOrdenar={onOrdenar} dir="dir" classe="bst-dp" largura="9.5rem" titulo={`DEL que a vaca terá em ${br(PROXIMA)} — é ele que decide se chega apta`} />}
            {verDel !== "projetado" && <Cab col="da" rotulo="DEL atual" ordem={ordem} onOrdenar={onOrdenar} dir="dir" largura="8rem" titulo="DEL de hoje (17/10/2026)" />}
            <th scope="col">Situação</th>
          </tr>
        </thead>
        <tbody>
          {linhas.length === 0 && <tr><td colSpan={6} style={{ padding: "1.4rem", textAlign: "center", color: "var(--text-muted)" }}>Nenhum animal nesta condição.</td></tr>}
          {linhas.map((a) => (
            <tr key={a.n} className={marcadas.has(a.n) ? "gv-linha-marcada" : undefined}>
              <td><input type="checkbox" checked={marcadas.has(a.n)} onChange={() => onToggle(a.n)} aria-label={`Marcar ${a.n}`} /></td>
              <td className="gv-forte gv-num">{a.n}{a.il && <span className="bst-il" title="Entrou no BST pelo protocolo de indução de lactação">(ind.lact.)</span>}</td>
              <td>{a.lote}</td>
              {verDel !== "atual" && <td className="gv-dir"><span className="bst-dp-v">{a.dp}</span></td>}
              {verDel !== "projetado" && <td className="gv-dir"><span className="bst-da-v">{a.da}</span></td>}
              <td><Situacao a={a} seg={seg} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Params = { data: string; produto: string; dose: string; unidade: string; porAnimal: boolean; resp: string };

function ParametrosLinha({ p, onChange }: { p: Params; onChange: (n: Partial<Params>) => void }) {
  return (
    <div className="bst-params" role="group" aria-label="Dose e produto">
      <div className="bst-params-tit gv-rotulo"><span className="gv-n" aria-hidden="true">2</span>Dados da aplicação</div>
      <div className="gv-campo" style={{ width: "9.5rem" }}><label htmlFor="bst-data">Data</label><input id="bst-data" type="date" value={p.data} onChange={(e) => onChange({ data: e.target.value })} /></div>
      <div className="gv-campo" style={{ width: "11rem" }}>
        <label htmlFor="bst-produto">Produto</label>
        <select id="bst-produto" value={p.produto} onChange={(e) => onChange({ produto: e.target.value, unidade: ESTOQUE.find((i) => i.nome === e.target.value)?.unidade ?? p.unidade })}>
          {ESTOQUE.map((i) => <option key={i.nome} value={i.nome}>{i.nome}</option>)}
        </select>
      </div>
      <div className="gv-campo" style={{ width: "5.5rem" }}><label htmlFor="bst-dose">Dose</label><input id="bst-dose" type="number" step="0.01" min="0" value={p.dose} placeholder="opc." onChange={(e) => onChange({ dose: e.target.value })} /></div>
      <div className="gv-campo" style={{ width: "6.5rem" }}><label htmlFor="bst-un">Unidade</label><input id="bst-un" value={p.unidade} onChange={(e) => onChange({ unidade: e.target.value })} /></div>
      <div className="gv-campo">
        <span className="bst-rot" id="bst-lbl-dose">A dose é</span>
        <div className="bst-mini" role="group" aria-labelledby="bst-lbl-dose">
          <button type="button" aria-pressed={p.porAnimal} onClick={() => onChange({ porAnimal: true })}>Por animal</button>
          <button type="button" aria-pressed={!p.porAnimal} onClick={() => onChange({ porAnimal: false })} title="A dose é o total já aplicado no grupo: o sistema divide pelo nº de animais antes de baixar do estoque.">Total do lote</button>
        </div>
      </div>
      <div className="gv-campo" style={{ width: "10rem" }}>
        <label htmlFor="bst-resp">Responsável</label>
        <select id="bst-resp" value={p.resp} onChange={(e) => onChange({ resp: e.target.value })}>
          <option value="">Opcional</option>
          {RESPONSAVEIS.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </div>
      <p className="gv-ajuda" style={{ flex: "1 1 14rem", alignSelf: "center" }}>Sem dose, o BST é registrado mas o estoque não baixa. Data futura = agenda (nada baixa agora).</p>
    </div>
  );
}

function resumoEstoque(p: Params, n: number): React.ReactNode {
  const futura = p.data > HOJE;
  if (futura) return <>Vai <strong>agendar {n} aplicações</strong> para {br(p.data)} — ficam pendentes na Agenda; nada baixa do estoque agora.</>;
  const dose = Number(p.dose);
  if (!dose || !p.unidade) return <>Vai <strong>registrar {n} aplicações</strong> em {br(p.data)} — sem dose informada, o estoque não baixa.</>;
  const total = p.porAnimal ? dose * n : dose;
  const item = ESTOQUE.find((i) => i.nome === p.produto);
  const resta = item && item.unidade === p.unidade ? item.quantidade - total : null;
  return <>Vai baixar <strong>{total} {p.unidade}</strong> de {p.produto} do estoque{resta != null && (resta >= 0 ? <> (restam {resta})</> : <> — <em>o estoque tem só {item!.quantidade}</em></>)}.</>;
}

function Barra({ seg, n, nAptas, nIncluir, nRe, p, aberto, onAbrir, onParams }: {
  seg: Seg; n: number; nAptas: number; nIncluir: number; nRe: number; p: Params; aberto: boolean; onAbrir: () => void; onParams: (x: Partial<Params>) => void;
}) {
  const futura = p.data > HOJE;
  const inaptas = seg === "inaptas";
  return (
    <div className="gv-barra">
      {!inaptas && aberto && <ParametrosLinha p={p} onChange={onParams} />}
      <div className="gv-barra-miolo">
        <div className="gv-barra-resumo" aria-live="polite">
          {n === 0 ? <b>Nenhuma selecionada</b> : <b>{n} selecionada{n > 1 ? "s" : ""}{!inaptas && <span style={{ fontWeight: 400 }}> ({nAptas} apta{nAptas === 1 ? "" : "s"} · {nIncluir} a incluir)</span>}</b>}
          <span className="bst-resumo-linha">
            {n === 0 ? "Marque os animais na tabela para aplicar, agendar ou marcar inapta."
              : inaptas ? <>Vão para “Incluir no próximo BST” com o selo Reanalisar; só voltam a aptas depois de uma nova aplicação.</>
              : resumoEstoque(p, n)}
          </span>
        </div>
        <span className="gv-espaco" />
        {!inaptas && !aberto && <span className="bst-resumo-linha">{br(p.data)} · {p.produto} · {p.dose ? `${p.dose} ${p.unidade} ${p.porAnimal ? "por animal" : "no total"}` : "sem dose"}</span>}
        {!inaptas && <button type="button" className="bst-btn" aria-expanded={aberto} onClick={onAbrir}>Dose e produto {aberto ? <ChevronUp size={13} aria-hidden="true" /> : <ChevronDown size={13} aria-hidden="true" />}</button>}
        {inaptas ? (
          <BotaoOuro desabilitado={n === 0}><Check size={14} aria-hidden="true" /> Marcar como apta</BotaoOuro>
        ) : (
          <>
            {seg === "incluir" && nRe > 0 && <button type="button" className="btn-ghost" title="Só para as marcadas com selo Reanalisar: tira a retirada; voltam a aptas depois de uma nova aplicação">Marcar como apta ({nRe})</button>}
            <button type="button" className="btn-ghost" disabled={n === 0} style={{ color: "var(--ft-verm)", borderColor: "var(--border-strong, var(--border))", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}><Ban size={14} aria-hidden="true" /> Marcar inapta</button>
            <BotaoOuro desabilitado={n === 0}><Check size={14} aria-hidden="true" /> {futura ? "Agendar BST" : "Aplicar BST"}</BotaoOuro>
          </>
        )}
      </div>
    </div>
  );
}

// ── a tela ──────────────────────────────────────────────────────────────────────────────────────────────────────────

export function Bst() {
  const [seg, setSeg] = useState<Seg>("aptas");
  const [sel, setSel] = useState<Record<Seg, Set<string>>>(() => ({
    aptas: new Set(DADOS.aptas.map((a) => a.n)), incluir: new Set(), inaptas: new Set(),
  }));
  const [lotes, setLotes] = useState<string[]>([]);
  const [verDel, setVerDel] = useState<"ambos" | "atual" | "projetado">("ambos");
  const [ordem, setOrdem] = useState<Ordem>({ col: "lote", dir: 1 });
  const [ajuste, setAjuste] = useState(false);
  const [aberto, setAberto] = useState(true);
  const [params, setParams] = useState<Params>({ data: HOJE, produto: "Lactotropin", dose: "1", unidade: "unidade", porAnimal: true, resp: "" });

  const ordenar = (col: Ordem["col"]) => setOrdem((o) => (o.col === col ? { col, dir: o.dir === 1 ? -1 : 1 } : { col, dir: 1 }));
  const ord = (a: Animal, b: Animal) => (ordem.col === "lote" ? a.lote.localeCompare(b.lote, undefined, { numeric: true }) * ordem.dir || a.n.localeCompare(b.n, undefined, { numeric: true }) : comparar(ordem)(a, b));
  const visiveis = DADOS[seg].filter((a) => !lotes.length || lotes.includes(a.lote)).sort(ord);
  const contagemLote: Record<string, number> = {};
  DADOS[seg].forEach((a) => { contagemLote[a.lote] = (contagemLote[a.lote] ?? 0) + 1; });
  const todosLotes = Array.from(new Set(Object.values(DADOS).flat().map((a) => a.lote))).sort();

  const marcadas = sel[seg];
  const toggle = (n: string) => setSel((s) => { const novo = new Set(s[seg]); novo.has(n) ? novo.delete(n) : novo.add(n); return { ...s, [seg]: novo }; });
  const todasMarcadas = visiveis.length > 0 && visiveis.every((a) => marcadas.has(a.n));
  const alternarTodas = () => setSel((s) => { const novo = new Set(s[seg]); visiveis.forEach((a) => (todasMarcadas ? novo.delete(a.n) : novo.add(a.n))); return { ...s, [seg]: novo }; });

  const nAptas = sel.aptas.size, nIncluir = sel.incluir.size;
  const nAcao = seg === "inaptas" ? sel.inaptas.size : nAptas + nIncluir;
  const rotTodas = seg === "aptas" ? "as aptas" : seg === "incluir" ? "as para incluir" : "as inaptas";

  return (
    <>
      <style>{CSS}</style>
      <QuadroGaveta titulo="BST" icone={Droplets} largura={1320}>
        <div className="bst-topo">
          <h2 className="bst-pergunta">Quem recebe BST na próxima visita?</h2>
          <span className="gv-ajuda">Somatotropina bovina — marque quem recebe e aplique, agende ou marque inapta.</span>
        </div>
        <Proxima aberto={ajuste} onAjustar={() => setAjuste((v) => !v)} />
        {ajuste && <PainelAjuste onFechar={() => setAjuste(false)} />}
        <Segmentos seg={seg} onTrocar={setSeg} contagens={{ aptas: DADOS.aptas.length, incluir: DADOS.incluir.length, inaptas: DADOS.inaptas.length }} marcadas={{ aptas: nAptas, incluir: nIncluir, inaptas: sel.inaptas.size }} />

        <Passo n={1} id="bst-p1" titulo={`Marque quem recebe — ${SEGMENTOS.find((s) => s.id === seg)!.nome}`}
          direita={<span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">{visiveis.filter((a) => marcadas.has(a.n)).length} de {visiveis.length} marcadas</span>}>
          <div className="bst-tool">
            <FiltroLotes lotes={todosLotes} contagem={contagemLote} marcados={lotes} onChange={setLotes} />
            <button type="button" className="bst-btn" disabled={!visiveis.length} onClick={alternarTodas}>{todasMarcadas ? "Desmarcar" : "Marcar todas"} {rotTodas} ({visiveis.length})</button>
            <span style={{ flex: 1 }} />
            <span className="bst-rot" id="bst-lbl-del">DEL</span>
            <div className="bst-mini" role="group" aria-labelledby="bst-lbl-del">
              {([["ambos", "Ambos"], ["projetado", "Projetado"], ["atual", "Atual"]] as const).map(([v, r]) => <button key={v} type="button" aria-pressed={verDel === v} onClick={() => setVerDel(v)}>{r}</button>)}
            </div>
            <span className="bst-rot" style={{ marginLeft: "0.6rem" }}>Exportar as 3 listas</span>
            <button type="button" className="bst-btn" title="PDF com Aptas, Incluir e Inaptas (coluna Situação)"><FileText size={14} aria-hidden="true" /> PDF</button>
            <button type="button" className="bst-btn" title="Excel com Aptas, Incluir e Inaptas (coluna Situação)"><FileSpreadsheet size={14} aria-hidden="true" /> Excel</button>
          </div>
          <TabelaBst seg={seg} linhas={visiveis} marcadas={marcadas} onToggle={toggle} onTodas={alternarTodas} verDel={verDel} ordem={ordem} onOrdenar={ordenar} />
          <p className="gv-ajuda">
            <b>DEL projetado</b> é o DEL que a vaca terá em {br(PROXIMA)}, data da próxima aplicação — é ele que decide se chega apta na hora certa. <b>DEL atual</b> é o de hoje.
            {seg === "incluir" && <> <b>Reanalisar</b>: foi retirada do BST ou entrou por indução de lactação — revise antes de incluir de novo.</>}
          </p>
        </Passo>

        <Barra seg={seg} n={nAcao} nAptas={nAptas} nIncluir={nIncluir} nRe={DADOS.incluir.filter((a) => a.re && sel.incluir.has(a.n)).length} p={params} aberto={aberto} onAbrir={() => setAberto((v) => !v)} onParams={(x) => setParams((p) => ({ ...p, ...x }))} />
      </QuadroGaveta>
    </>
  );
}
