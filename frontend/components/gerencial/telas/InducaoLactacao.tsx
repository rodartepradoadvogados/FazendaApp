"use client";
// Lançamentos › Produção › Indução de lactação — PROPOSTA de tela (variante desktop, só apresentação, dados de exemplo).
// Fonte atual: components/FormInducaoLactacao.tsx (também roda no app de campo com a prop `salvarInducao`).
//
// O QUE A VERSÃO LIGADA A DADOS PRECISA PRESERVAR
//  • Protocolos: GET /producao/protocolos-inducao-lactacao (nome, duracao_dias, dia_inicial 0|1, observacao, etapas[dia, tipo
//    "medicamento"|"dispositivo"|"manejo", produto, dose, unidade, acao_dispositivo "colocar"|"retirar"]). A linha do tempo é montada
//    das etapas (uma linha por produto); o rótulo "D0"/"D1" e a data do passo 2 vêm de `dia_inicial`.
//  • POST /producao/inducao-lactacao via `salvarInducao` (prop de injeção offline): { protocolo_id, animais[], data_d0, responsavel?, observacao? }.
//    Resposta: { criado, aviso, animais, eventos_criados, enviado }. `enviado:false` = "Sem internet — guardado";
//    `criado:false` = o servidor reaproveitou um lançamento idêntico (duplo clique/retry offline) → mostrar `aviso`, nunca "0 eventos".
//  • Obrigatórios: protocolo, data do D0/D1 e ao menos 1 animal (animal ou lote; lote já vem com todos marcados e dá para desmarcar).
//    Responsável (pessoas ativas, usePessoasAtivas) e observação são opcionais. Depois de salvar: limpa a seleção e recarrega "Em andamento".
//  • Em andamento: GET /inducao-lactacao/ativos ({lancamento_id, nome_protocolo, data_d0, animais[{numero_matriz, etapa_atual, data_etapa_atual}]}).
//  • Aviso de elegibilidade: hoje NÃO existe filtro nem regra no backend. Os avisos desta proposta (em lactação, prenha, já em outra
//    indução) são SUGESTÕES a confirmar com o dono e só INFORMAM — nunca bloqueiam. Exigem campos novos por animal (situação reprodutiva,
//    idade, indução ativa) que a lista de animais já tem ou o endpoint de candidatas teria de devolver.
//  • "gera N eventos na Agenda": o número aqui é ilustrativo; a contagem real só o servidor sabe (eventos_criados) — a implementação
//    precisa de uma prévia no backend ou deve trocar por "os eventos do cronograma vão para a Agenda" antes de salvar.
//  • CSS: as classes `.gi-*` estão num <style> local só para a proposta; na implementação sobem para o fim de `.gv-*` em globals.css.
import React, { useMemo, useState } from "react";
import { CalendarClock, Search } from "lucide-react";
import { Ajuda, Aviso, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, QuadroGaveta, Selo } from "@/components/gerencial/kit";

type Etapa = { dia: number; tipo: "medicamento" | "dispositivo" | "manejo"; produto: string; dose?: number; unidade?: string; acao?: "colocar" | "retirar" };
type Protocolo = {
  id: string; nome: string; curto: string; duracao: number; diaInicial: 0 | 1; resumo: string; observacao: string;
  inicioOrdenha: number; eventosAgenda: number; etapas: Etapa[];
};

const BST = "Somatotropina Bovina (bST)", E2 = "Benzoato de Estradiol", P4 = "Implante de Progesterona", CLO = "Cloprostenol Sódico / D-Cloprostenol", DEX = "Dexametasona", ADAPT = "Adaptação na ordenha";
const med = (dia: number, produto: string, dose?: number, unidade?: string): Etapa => ({ dia, tipo: "medicamento", produto, dose, unidade });
const impl = (dia: number, acao: "colocar" | "retirar"): Etapa => ({ dia, tipo: "dispositivo", produto: P4, acao });
const man = (dia: number, produto: string): Etapa => ({ dia, tipo: "manejo", produto });
const faixaDias = (de: number, ate: number) => Array.from({ length: ate - de + 1 }, (_, k) => de + k);

// Cronogramas das duas planilhas do produtor (seed do cadastro).
const ETAPAS_28: Etapa[] = [
  med(0, BST, undefined, "dose"), ...faixaDias(0, 6).map((d) => med(d, E2, 30, "ml")), impl(0, "colocar"),
  med(7, BST, undefined, "dose"), impl(7, "retirar"), ...faixaDias(7, 14).map((d) => med(d, E2, 20, "ml")),
  med(14, BST, undefined, "dose"), med(15, CLO, 3, "ml"),
  ...faixaDias(16, 20).map((d) => man(d, ADAPT)), ...faixaDias(18, 20).map((d) => med(d, DEX, 20, "ml")),
  med(20, BST, undefined, "dose"), man(21, "COMEÇAR A ORDENHA"), med(27, BST, undefined, "dose"),
];
const ETAPAS_18: Etapa[] = [
  med(0, BST, undefined, "dose"), impl(0, "colocar"), ...[0, 2, 4, 6, 8, 10, 12, 14, 15, 16, 17].map((d) => med(d, E2, 2, "ml")),
  med(8, BST, undefined, "dose"), med(14, BST, undefined, "dose"), med(15, CLO, undefined, "dose"), impl(15, "retirar"),
  ...[15, 16, 17].map((d) => med(d, DEX, 10, "ml")), man(18, "INICIAR A ORDENHA"),
];

const PROTOCOLOS: Protocolo[] = [
  {
    id: "28", nome: "Protocolo de Indução de Lactação — 28 dias (Ativos 1)", curto: "Ativos 1", duracao: 28, diaInicial: 0, inicioOrdenha: 21, eventosAgenda: 7, etapas: ETAPAS_28,
    resumo: "bST, estradiol, implante de progesterona, cloprostenol e dexametasona · a ordenha começa no D21",
    observacao: "Manter a bST (Somatotropina Bovina) a cada 12 dias até o final da lactação — a partir do D27 a vaca entra no ciclo normal de aplicação de bST do rebanho (Sanidade › Preventiva › BST).",
  },
  {
    id: "18", nome: "Protocolo de Indução de Lactação — 18 dias (Ativos 2)", curto: "Ativos 2", duracao: 18, diaInicial: 0, inicioOrdenha: 18, eventosAgenda: 6, etapas: ETAPAS_18,
    resumo: "Protocolo intensivo, aplicações em dias alternados · a ordenha começa no D18",
    observacao: "Protocolo intensivo (63 animais) — aplicações em dias alternados; nos dias de INTERVALO não há nenhuma etapa.",
  },
];

type Aviso = { texto: string } | null;
type Animal = { numero: string; categoria: string; lote: string; repro: string; idade: string; aviso: Aviso };
// Avisos de elegibilidade SUGERIDOS (a confirmar com o dono): em lactação · prenha · já em outra indução.
const ANIMAIS: Animal[] = [
  { numero: "11153", categoria: "Novilha", lote: "01 - Novilhas Alta", repro: "Vazia", idade: "27 meses", aviso: null },
  { numero: "3335", categoria: "Novilha", lote: "01 - Novilhas Alta", repro: "Vazia", idade: "29 meses", aviso: null },
  { numero: "075", categoria: "Novilha", lote: "01 - Novilhas Alta", repro: "Vazia", idade: "31 meses", aviso: null },
  { numero: "4417", categoria: "Novilha", lote: "01 - Novilhas Alta", repro: "Vazia", idade: "26 meses", aviso: null },
  { numero: "4802", categoria: "Novilha", lote: "01 - Novilhas Alta", repro: "Vazia", idade: "28 meses", aviso: { texto: "Já em indução (Ativos 1 · D11)" } },
  { numero: "9378", categoria: "Novilha", lote: "01 - Novilhas Alta", repro: "Prenha · DG+ 142 d", idade: "33 meses", aviso: { texto: "Prenha há 142 dias" } },
  { numero: "7781", categoria: "Novilha", lote: "13 - Novilhas Novas", repro: "Não coberta", idade: "14 meses", aviso: null },
  { numero: "7790", categoria: "Novilha", lote: "13 - Novilhas Novas", repro: "Não coberta", idade: "13 meses", aviso: null },
  { numero: "8120", categoria: "Novilha", lote: "13 - Novilhas Novas", repro: "Não coberta", idade: "15 meses", aviso: null },
  { numero: "8133", categoria: "Novilha", lote: "13 - Novilhas Novas", repro: "Não coberta", idade: "14 meses", aviso: null },
  { numero: "2290", categoria: "Vaca seca", lote: "05 - Secas", repro: "Vazia", idade: "6 anos", aviso: null },
  { numero: "2754", categoria: "Vaca seca", lote: "05 - Secas", repro: "Vazia", idade: "5 anos", aviso: null },
  { numero: "3318", categoria: "Vaca seca", lote: "05 - Secas", repro: "Prenha · DG+ 230 d", idade: "7 anos", aviso: { texto: "Prenha há 230 dias" } },
  { numero: "1024", categoria: "Vaca", lote: "02 - Vacas Alta", repro: "Inseminada · 61 d", idade: "4 anos", aviso: { texto: "Em lactação (118 DEL)" } },
  { numero: "1031", categoria: "Vaca", lote: "02 - Vacas Alta", repro: "Vazia", idade: "5 anos", aviso: { texto: "Em lactação (96 DEL)" } },
  { numero: "6150", categoria: "Vaca", lote: "04 - Pós-parto/Tratamento", repro: "Pós-parto", idade: "4 anos", aviso: { texto: "Em lactação (12 DEL)" } },
];
const LOTES = Array.from(new Set(ANIMAIS.map((a) => a.lote))).sort();

const HOJE = "2026-10-17";
const ATIVOS: { id: number; protocolo: string; d0: string; animais: string[] }[] = [
  { id: 1, protocolo: "28", d0: "2026-10-06", animais: ["4802", "4811", "4825"] },
  { id: 2, protocolo: "18", d0: "2026-10-12", animais: ["5532", "5540"] },
  { id: 3, protocolo: "28", d0: "2026-09-29", animais: ["4590", "4601"] },
];
const RESPONSAVEIS = ["Adriano", "Marcelo", "Paulo (veterinário)"];

const somar = (iso: string, dias: number) => new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10) + dias)).toISOString().slice(0, 10);
const entre = (a: string, b: string) => Math.round((Date.UTC(+b.slice(0, 4), +b.slice(5, 7) - 1, +b.slice(8, 10)) - Date.UTC(+a.slice(0, 4), +a.slice(5, 7) - 1, +a.slice(8, 10))) / 86400000);
const dataBR = (iso: string, curta = false) => { const [a, m, d] = iso.split("-"); return curta ? `${d}/${m}` : `${d}/${m}/${a}`; };
const ptNum = (n: number) => n.toLocaleString("pt-BR");

type Linha = { chave: string; rotulo: string; unid: string; tipo: Etapa["tipo"]; porDia: Map<number, Etapa> };
/** Uma linha por produto: implante e medicamentos primeiro (na ordem em que aparecem), manejo por último. */
function linhasDoCronograma(p: Protocolo): Linha[] {
  const m = new Map<string, Linha>();
  for (const e of p.etapas) {
    const chave = `${e.tipo}|${e.produto}`;
    if (!m.has(chave)) m.set(chave, { chave, rotulo: e.tipo === "dispositivo" ? "Implante de progesterona" : e.produto === BST ? "bST (somatotropina)" : e.produto === CLO ? "Cloprostenol" : e.produto, unid: "", tipo: e.tipo, porDia: new Map() });
    const l = m.get(chave) as Linha;
    l.porDia.set(e.dia, e);
    if (e.tipo === "medicamento" && e.unidade) l.unid = e.unidade;
  }
  const peso = { dispositivo: 0, medicamento: 1, manejo: 2 } as const;
  return [...m.values()].sort((a, b) => peso[a.tipo] - peso[b.tipo]);
}
function celula(l: Linha, e: Etapa): { texto: string; titulo: string } {
  if (e.tipo === "dispositivo") return { texto: e.acao === "colocar" ? "▼" : "▲", titulo: `D${e.dia} · ${e.acao === "colocar" ? "Colocar" : "Retirar"} implante de progesterona` };
  if (e.tipo === "manejo") return { texto: e.produto.toUpperCase() === e.produto ? "▶" : "●", titulo: `D${e.dia} · ${e.produto}` };
  return { texto: e.dose ? String(e.dose) : "●", titulo: `D${e.dia} · ${e.produto}${e.dose ? ` ${e.dose} ${e.unidade ?? ""}` : ""}` };
}
/** Etapa atual do animal em andamento: o último dia com etapa até hoje (texto como o da Agenda). */
function etapaAtual(p: Protocolo, d0: string) {
  const dia = p.diaInicial + entre(d0, HOJE);
  const dias = Array.from(new Set(p.etapas.map((e) => e.dia))).filter((d) => d <= dia).sort((a, b) => a - b);
  const d = dias[dias.length - 1] ?? p.diaInicial;
  const doDia = p.etapas.filter((e) => e.dia === d);
  const partes = doDia.map((e) => e.tipo === "dispositivo" ? (e.acao === "colocar" ? "Colocar implante de progesterona" : "Retirar implante de progesterona")
    : e.tipo === "manejo" ? e.produto : `${e.produto.replace(" (bST)", "")}${e.dose ? ` ${e.dose} ${e.unidade}` : ""}`);
  return { dia, d, texto: `D${d} · ${partes.join(" + ")}`, data: somar(d0, d - p.diaInicial) };
}

const CSS = `
.gi-topo { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 0.2rem; }
.gi-cartoes { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; }
.gi-cartoes .gv-cartao-opcao span { white-space: normal; }
.gi-linhatempo-moldura { border: 1px solid var(--border-strong, var(--border)); background: var(--surface); overflow-x: auto; }
.gi-tl { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 0.72rem; font-variant-numeric: tabular-nums; }
.gi-tl col.gi-rot { width: 16rem; }
.gi-tl thead th { background: var(--thead-bg); color: var(--thead-fg); font-size: 0.66rem; font-weight: 700; letter-spacing: 0.02em; padding: 0.3rem 0; text-align: center; border-left: 1px solid var(--border); }
.gi-tl thead tr:nth-child(2) th { font-weight: 400; padding-top: 0; padding-bottom: 0.3rem; font-size: 0.66rem; opacity: 0.85; border-bottom: 1px solid var(--border-strong, var(--border)); }
.gi-tl thead th:first-child { text-align: left; padding-left: 0.6rem; border-left: 0; letter-spacing: 0.08em; text-transform: uppercase; }
.gi-tl thead th.gi-ordenha { box-shadow: inset 0 -2px 0 var(--ft-ouro); }
.gi-tl tbody th { text-align: left; font-weight: 600; font-size: 0.78rem; padding: 0.3rem 0.6rem; border-bottom: 1px solid var(--border); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gi-tl tbody th small { font-weight: 400; color: var(--text-muted); font-size: 0.7rem; margin-left: 0.25rem; }
.gi-tl tbody td { text-align: center; padding: 0.3rem 0; border-bottom: 1px solid var(--border); border-left: 1px solid var(--border); height: 1.9rem; }
.gi-tl td[data-tipo="medicamento"] { color: var(--ft-aco); font-weight: 800; background: color-mix(in srgb, var(--ft-aco) 9%, transparent); }
.gi-tl td[data-tipo="dispositivo"] { color: var(--ft-ouro-txt); font-weight: 800; background: var(--ft-ouro-tint); }
.gi-tl td[data-tipo="manejo"] { color: var(--ft-ouro-txt); font-weight: 800; background: var(--ft-ouro-tint); }
.gi-legenda { display: flex; flex-wrap: wrap; gap: 0.3rem 1.2rem; font-size: 0.74rem; color: var(--text-muted); }
.gi-legenda b { font-weight: 800; color: var(--text); }
.gi-campos { display: grid; grid-template-columns: 19rem 15rem minmax(0, 1fr); gap: 0.75rem; align-items: start; }
.gi-busca { position: relative; display: flex; align-items: center; }
.gi-busca svg { position: absolute; left: 0.6rem; color: var(--text-muted); pointer-events: none; }
.gi-busca input { padding-left: 2rem; width: 17rem; background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); font-size: 0.85rem; min-height: 2.1rem; }
.gi-busca input:focus { outline: 2px solid var(--ft-ouro); outline-offset: -1px; }
.gi-avisotxt { font-size: 0.78rem; color: var(--ft-ouro-txt); margin-left: 0.4rem; }
.gi-botao-mini { min-height: 2.1rem; }
`;

function Cronograma({ p, d0 }: { p: Protocolo; d0: string }) {
  const linhas = linhasDoCronograma(p);
  const dias = faixaDias(p.diaInicial, Math.max(...p.etapas.map((e) => e.dia)));
  return (
    <>
      <div className="gi-linhatempo-moldura">
        <table className="gi-tl">
          <colgroup><col className="gi-rot" />{dias.map((d) => <col key={d} />)}</colgroup>
          <thead>
            <tr>
              <th scope="col">Vai para a Agenda</th>
              {dias.map((d) => <th key={d} scope="col" className={d === p.inicioOrdenha ? "gi-ordenha" : undefined}>D{d}</th>)}
            </tr>
            <tr>
              <th scope="col" style={{ textTransform: "none", letterSpacing: 0, fontWeight: 400 }}>{d0 ? "Data de cada dia" : "Escolha a data do D0 para ver as datas"}</th>
              {dias.map((d) => <th key={d} scope="col">{d0 ? dataBR(somar(d0, d - p.diaInicial), true) : ""}</th>)}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => (
              <tr key={l.chave}>
                <th scope="row" title={l.rotulo}>{l.rotulo}{l.unid && <small>({l.unid})</small>}</th>
                {dias.map((d) => {
                  const e = l.porDia.get(d);
                  if (!e) return <td key={d} />;
                  const c = celula(l, e);
                  return <td key={d} data-tipo={e.tipo} title={c.titulo} aria-label={c.titulo}>{c.texto}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="gi-legenda">
        <span><b>30</b> número = dose em ml · <b>●</b> aplicação (uma dose)</span>
        <span><b>▼</b> colocar implante · <b>▲</b> retirar implante</span>
        <span><b>●</b> manejo · <b>▶</b> início da ordenha (sublinhado em ouro)</span>
      </div>
    </>
  );
}

function EmAndamento() {
  const total = ATIVOS.reduce((s, a) => s + a.animais.length, 0);
  return (
    <>
      <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "none" }}>
        <table className="gv-tabela">
          <thead>
            <tr><th scope="col">Nº</th><th scope="col">Etapa atual</th><th scope="col">Data da etapa</th><th scope="col">Dia do protocolo</th><th scope="col">Início da ordenha</th></tr>
          </thead>
          <tbody>
            {ATIVOS.map((a) => {
              const p = PROTOCOLOS.find((x) => x.id === a.protocolo) as Protocolo;
              const e = etapaAtual(p, a.d0);
              const ordenha = somar(a.d0, p.inicioOrdenha - p.diaInicial);
              return (
                <React.Fragment key={a.id}>
                  <tr className="gv-grupo"><th scope="rowgroup" colSpan={5}>{p.nome.replace("Protocolo de Indução de Lactação — ", "Indução ")} · D0 em {dataBR(a.d0)} · {a.animais.length} {a.animais.length === 1 ? "animal" : "animais"}</th></tr>
                  {a.animais.map((n) => (
                    <tr key={n}>
                      <td className="gv-forte gv-num">{n}</td>
                      <td>{e.texto}</td>
                      <td className="gv-num">{dataBR(e.data)}</td>
                      <td className="gv-num">D{e.dia} de {p.duracao}</td>
                      <td className="gv-num"><span style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>{dataBR(ordenha)}{ordenha <= HOJE ? <Selo tom="ok">Já começou</Selo> : ordenha === somar(HOJE, 3) ? <Selo tom="atencao">Em 3 dias</Selo> : null}</span></td>
                    </tr>
                  ))}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <Ajuda>{ATIVOS.length} induções em andamento, {total} animais. A etapa atual é a última do cronograma que já passou; o que vem a seguir está na Agenda.</Ajuda>
    </>
  );
}

export function InducaoLactacao({ abaInicial = "lancar" }: { abaInicial?: "lancar" | "andamento" }) {
  const [aba, setAba] = useState<"lancar" | "andamento">(abaInicial);
  const [protocoloId, setProtocoloId] = useState("28");
  const [d0, setD0] = useState("2026-10-19");
  const [resp, setResp] = useState("Marcelo");
  const [obs, setObs] = useState("");
  const [origem, setOrigem] = useState<"animal" | "lote">("lote");
  const [lotes, setLotes] = useState<Set<string>>(new Set(["01 - Novilhas Alta"]));
  const [sel, setSel] = useState<Set<string>>(new Set(ANIMAIS.filter((a) => a.lote === "01 - Novilhas Alta").map((a) => a.numero)));
  const [busca, setBusca] = useState("");
  const [retorno, setRetorno] = useState<{ tipo: "ok" | "repetido"; texto: string } | null>(null);
  const [cliques, setCliques] = useState(0);

  const protocolo = PROTOCOLOS.find((p) => p.id === protocoloId);
  const rotuloD = `D${protocolo?.diaInicial ?? 0}`;

  const visiveis = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return ANIMAIS.filter((a) => (origem === "animal" || lotes.has(a.lote)) && (!q || a.numero.toLowerCase().includes(q) || a.lote.toLowerCase().includes(q)));
  }, [origem, lotes, busca]);
  const grupos = useMemo(() => LOTES.map((l) => ({ lote: l, itens: visiveis.filter((a) => a.lote === l) })).filter((g) => g.itens.length), [visiveis]);

  const marcados = ANIMAIS.filter((a) => sel.has(a.numero));
  const comAviso = marcados.filter((a) => a.aviso).length;
  const semAviso = ANIMAIS.filter((a) => !a.aviso).length;
  const visSemAviso = visiveis.filter((a) => !a.aviso);
  const todosSemAvisoMarcados = visSemAviso.length > 0 && visSemAviso.every((a) => sel.has(a.numero));

  const alternar = (n: string) => setSel((p) => { const s = new Set(p); if (s.has(n)) s.delete(n); else s.add(n); return s; });
  const alternarLote = (lote: string) => {
    const doLote = ANIMAIS.filter((a) => a.lote === lote).map((a) => a.numero);
    const ativo = lotes.has(lote);
    setLotes((p) => { const s = new Set(p); if (ativo) s.delete(lote); else s.add(lote); return s; });
    setSel((p) => { const s = new Set(p); doLote.forEach((n) => (ativo ? s.delete(n) : s.add(n))); return s; });
  };
  const alternarTodosSemAviso = () => setSel((p) => { const s = new Set(p); visSemAviso.forEach((a) => (todosSemAvisoMarcados ? s.delete(a.numero) : s.add(a.numero))); return s; });

  // Faixa: estado das induções em andamento e do universo de candidatas.
  const emAnd = ATIVOS.reduce((s, a) => s + a.animais.length, 0);
  const proximas = ATIVOS.map((a) => { const p = PROTOCOLOS.find((x) => x.id === a.protocolo) as Protocolo; return somar(a.d0, p.inicioOrdenha - p.diaInicial); }).filter((d) => d >= HOJE).sort();

  const faltam = [!protocolo && "o protocolo", !d0 && `a data do ${rotuloD}`, marcados.length === 0 && "ao menos um animal"].filter(Boolean) as string[];
  const n = marcados.length;
  const resumo = n === 0 ? "Nenhum animal marcado" : `${n} ${n === 1 ? "animal" : "animais"} · protocolo ${protocolo?.duracao ?? "—"} dias · gera ${protocolo?.eventosAgenda ?? "—"} eventos na Agenda`;
  const detalhe = faltam.length ? `Falta escolher ${faltam.join(", ")}.`
    : `${rotuloD} em ${dataBR(d0)}${resp ? ` · responsável: ${resp}` : ""}${comAviso ? ` · ${comAviso} com aviso de elegibilidade — pode lançar mesmo assim` : ""}`;

  function salvar() {
    if (!protocolo) return;
    if (cliques === 0) {
      setRetorno({ tipo: "ok", texto: `Protocolo “${protocolo.curto}” lançado para ${n} ${n === 1 ? "animal" : "animais"} — ${protocolo.eventosAgenda} eventos na Agenda.` });
    } else {
      setRetorno({ tipo: "repetido", texto: "Este protocolo já estava lançado para estes animais nesta data — nada foi duplicado." });
    }
    setCliques((c) => c + 1);
  }

  return (
    <>
      <style>{CSS}</style>
      <QuadroGaveta titulo="Indução de lactação" icone={CalendarClock} largura={1320}>
        <Faixa itens={[
          { rotulo: "Induções em andamento", valor: ATIVOS.length },
          { rotulo: "Animais em indução", valor: emAnd },
          { rotulo: "Próxima ordenha a iniciar", valor: proximas[0] ? dataBR(proximas[0], true) : "—" },
          { rotulo: "Candidatas sem aviso", valor: `${semAviso} de ${ANIMAIS.length}` },
        ]} />
        <div className="gi-topo">
          <Pilulas<"lancar" | "andamento"> rotulo="Tela" valor={aba} onChange={setAba}
            opcoes={[{ id: "lancar", nome: "Lançar indução" }, { id: "andamento", nome: "Em andamento", n: ATIVOS.length }]} />
        </div>

        {aba === "andamento" ? (
          <Passo n={1} id="il-and" titulo="Induções em andamento">
            <EmAndamento />
          </Passo>
        ) : (
          <>
            <Passo n={1} id="il-p1" titulo="Protocolo">
              <div className="gi-cartoes" role="group" aria-label="Protocolo de indução">
                {PROTOCOLOS.map((p) => (
                  <button key={p.id} type="button" className="gv-cartao-opcao" aria-pressed={protocoloId === p.id} onClick={() => setProtocoloId(p.id)}>
                    <b>{p.curto} · {p.duracao} dias</b>
                    <span>{p.resumo}</span>
                  </button>
                ))}
              </div>
              {protocolo && (
                <>
                  <Cronograma p={protocolo} d0={d0} />
                  <Ajuda>{protocolo.observacao}</Ajuda>
                </>
              )}
            </Passo>

            <Passo n={2} id="il-p2" titulo={`Quando começa e quem aplica`}>
              <div className="gi-campos">
                <Campo rotulo={`Data do ${rotuloD} · 1º dia (obrigatória)`} id="il-d0">
                  <input type="date" value={d0} onChange={(e) => setD0(e.target.value)} />
                </Campo>
                <Campo rotulo="Responsável (opcional)" id="il-resp">
                  <select value={resp} onChange={(e) => setResp(e.target.value)}>
                    <option value="">Não informar</option>
                    {RESPONSAVEIS.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </Campo>
                <Campo rotulo="Observação (opcional)" id="il-obs">
                  <input type="text" value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Ex.: lote em piquete de adaptação" />
                </Campo>
              </div>
            </Passo>

            <Passo n={3} id="il-p3" titulo="Animais" direita={
              <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">
                {marcados.length} marcados · {visiveis.length} na lista
              </span>
            }>
              <div className="gv-linha" style={{ justifyContent: "space-between" }}>
                <Pilulas<"animal" | "lote"> rotulo="Escolher por" valor={origem} onChange={setOrigem}
                  opcoes={[{ id: "animal", nome: "Animal por animal", titulo: "Selecionar matrizes individualmente" }, { id: "lote", nome: "Lotes", titulo: "Selecionar um ou mais lotes — já vêm todos marcados" }]} />
                <div className="gi-busca">
                  <Search size={14} aria-hidden="true" />
                  <input type="search" aria-label="Buscar matriz ou lote" placeholder="Buscar matriz ou lote" value={busca} onChange={(e) => setBusca(e.target.value)} />
                </div>
              </div>
              {origem === "lote" && (
                <div className="gv-linha" role="group" aria-label="Lotes">
                  {LOTES.map((l) => (
                    <button key={l} type="button" className="ft-pilula" aria-pressed={lotes.has(l)} onClick={() => alternarLote(l)}>
                      {l}<b>{ANIMAIS.filter((a) => a.lote === l).length}</b>
                    </button>
                  ))}
                </div>
              )}
              {visiveis.length === 0 ? (
                <Ajuda>{origem === "lote" && lotes.size === 0 ? "Marque um ou mais lotes acima — os animais do lote já vêm marcados." : "Nenhum animal bate com a busca."}</Ajuda>
              ) : (
                <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "19rem" }}>
                  <table className="gv-tabela">
                    <thead>
                      <tr>
                        <th scope="col" style={{ width: "2.4rem" }}>
                          <input type="checkbox" checked={todosSemAvisoMarcados} onChange={alternarTodosSemAviso} disabled={visSemAviso.length === 0} aria-label="Selecionar todos os que estão sem aviso" />
                        </th>
                        <th scope="col">Nº</th><th scope="col">Categoria</th><th scope="col">Lote</th>
                        <th scope="col">Situação reprodutiva</th><th scope="col">Idade</th><th scope="col">Aviso de elegibilidade</th>
                      </tr>
                    </thead>
                    <tbody>
                      {grupos.map((g) => (
                        <React.Fragment key={g.lote}>
                          <tr className="gv-grupo"><th scope="rowgroup" colSpan={7}>{g.lote} · {g.itens.length}</th></tr>
                          {g.itens.map((a) => (
                            <tr key={a.numero} className={sel.has(a.numero) ? "gv-linha-marcada" : undefined}>
                              <td><input type="checkbox" checked={sel.has(a.numero)} onChange={() => alternar(a.numero)} aria-label={`Selecionar ${a.numero}`} /></td>
                              <td className="gv-forte gv-num">{a.numero}</td>
                              <td>{a.categoria}</td>
                              <td>{a.lote}</td>
                              <td>{a.repro}</td>
                              <td className="gv-num">{a.idade}</td>
                              <td>{a.aviso ? <><Selo tom="atencao">Atenção</Selo><span className="gi-avisotxt">{a.aviso.texto}</span></> : <Selo tom="neutro">Sem aviso</Selo>}</td>
                            </tr>
                          ))}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <Ajuda>
                Os avisos <strong>só informam</strong>: o animal marcado é lançado mesmo assim. Critérios sugeridos, a confirmar com o dono: em lactação, prenha ou já em outra indução.
                “Selecionar todos” marca só os que estão sem aviso.
              </Ajuda>
            </Passo>
          </>
        )}

        <BarraAcao
          resumo={aba === "andamento" ? `${ATIVOS.length} induções em andamento · ${emAnd} animais` : resumo}
          detalhe={aba === "andamento" ? "A Agenda mostra o que aplicar em cada dia." : detalhe}
          retorno={aba === "lancar" && retorno ? (
            retorno.tipo === "ok"
              ? <><span role="status" style={{ color: "var(--ft-verde)", fontWeight: 700 }}>✓ {retorno.texto}</span><button type="button" className="btn-ghost gi-botao-mini" onClick={() => setAba("andamento")}>Ver em andamento</button></>
              : <Aviso>{retorno.texto}</Aviso>
          ) : undefined}
          acao={aba === "andamento"
            ? <BotaoOuro onClick={() => setAba("lancar")}>Lançar nova indução</BotaoOuro>
            : <BotaoOuro desabilitado={faltam.length > 0} onClick={salvar}>Lançar indução</BotaoOuro>}
        />
      </QuadroGaveta>
    </>
  );
}
