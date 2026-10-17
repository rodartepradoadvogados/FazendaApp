"use client";
// Lançamentos › Produção › Venda mensal do leite — PROPOSTA de tela (variante desktop, só apresentação, dados de exemplo).
// Fonte atual: components/FormEntregaLeite.tsx (também roda no app de campo com a prop `salvarEntrega`).
//
// O QUE A VERSÃO LIGADA A DADOS PRECISA PRESERVAR
//  • POST /producao/entrega-leite via `salvarEntrega` (prop de injeção offline): { competencia "AAAA-MM", quantidade_litros, unidade "kg"|"L", observacao? }.
//    `quantidade_litros` é só o NOME do campo: guarda o número na unidade escolhida (por isso a coluna se chama "Quantidade", com a unidade junto).
//    Retorno `{ enviado: false }` = "Sem internet — guardado" e NÃO recarrega a lista (offline apagaria a lista já carregada).
//  • Obrigatórios: mês e quantidade > 0. Vírgula decimal aceita (`Number(v.replace(",", "."))`); o campo é type="text" inputMode="decimal" e NÃO aceita
//    ponto de milhar ("12.480" viraria 12,48) — por isso a tela confirma o número formatado ao lado ("= 12.480 kg").
//  • Conversão: o controle leiteiro é sempre em kg; entrega em L converte 1 L = 1,029 kg antes de comparar (mostrada em "≈ kg").
//  • Lista: GET /producao/entrega-leite (registros[{id, competencia, quantidade_litros, unidade, observacao, usuario_nome}]); editar inline = PUT
//    /producao/entrega-leite/{id} (competencia, quantidade_litros, unidade, observacao|null); `unidade` ausente = "kg".
//  • Excluir: SEMPRE por confirmarExclusao("entrega_leite", String(id)) (POST /exclusoes/confirmar) — admin (ehAdmin()) exclui na hora, operador
//    SOLICITA e aguarda aprovação ("Solicitação de exclusão enviada — aguardando aprovação de um administrador."). A confirmação passa a ser o Modal do app
//    (components/Modal.tsx), não window.confirm; aqui o modal é só uma imitação dentro da gaveta.
//  • Estados da lista: carregando (skeleton) ≠ vazio ≠ erro. Hoje o erro vira lista vazia ("Nenhuma entrega lançada ainda") — a proposta separa os três.
//  • Faixa de números: controle do mês = fetchRelatorioControleEntrega (kg projetados/produzidos no período) e receita recebida = Financeiro; hoje a tela
//    só comenta isso na descrição. Se a API não devolver o mês pedido, os campos mostram "—" (nunca 0).
//  • Campo `usuario_nome` já vinha da API e não era exibido: aqui vira a coluna "Lançado por".
//  • CSS: as classes `.gm-*` estão num <style> local só para a proposta; na implementação sobem para o fim de `.gv-*` em globals.css.
import React, { useEffect, useState } from "react";
import { Check, Pencil, Trash2, TrendingUp, X } from "lucide-react";
import { Ajuda, Aviso, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, QuadroGaveta } from "@/components/gerencial/kit";

type Unidade = "kg" | "L";
type Registro = { id: number; competencia: string; quantidade: number; unidade: Unidade; observacao: string | null; usuario: string };
type EstadoLista = "carregando" | "ok" | "vazio" | "erro";

const KG_POR_L = 1.029;
const REGISTROS: Registro[] = [
  { id: 9, competencia: "2026-08", quantidade: 13054, unidade: "kg", observacao: "Soma das notinhas do laticínio", usuario: "Jairo" },
  { id: 8, competencia: "2026-07", quantidade: 12130, unidade: "L", observacao: "Total do app do laticínio (em litros)", usuario: "Jairo" },
  { id: 7, competencia: "2026-06", quantidade: 12318, unidade: "kg", observacao: null, usuario: "Marcelo" },
  { id: 6, competencia: "2026-05", quantidade: 11902, unidade: "kg", observacao: null, usuario: "Marcelo" },
  { id: 5, competencia: "2026-04", quantidade: 11476, unidade: "kg", observacao: "Mês com 2 dias sem coleta", usuario: "Jairo" },
  { id: 4, competencia: "2026-03", quantidade: 12044, unidade: "kg", observacao: null, usuario: "Jairo" },
];
// Exemplos do que a tela buscaria do controle leiteiro (kg produzidos) e do financeiro (receita recebida) por mês.
const CONTROLE_KG: Record<string, number> = { "2026-09": 13150, "2026-08": 13620, "2026-07": 13010, "2026-06": 12790 };
const RECEITA: Record<string, number> = { "2026-09": 28704, "2026-08": 30024.2, "2026-07": 28712.4 };

const nb = (v: number, casas = 0) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const mesBR = (c: string) => { const [a, m] = c.split("-"); return m && a ? `${m}/${a}` : c; };
const emKg = (q: number, u: Unidade) => (u === "L" ? q * KG_POR_L : q);
const casasDe = (q: number) => (Number.isInteger(q) ? 0 : 1);
const textoQtd = (q: number, u: Unidade) => `${nb(q, casasDe(q))} ${u}`;
/** Vazio = null; vírgula decimal; ponto de milhar NÃO é aceito (confirmado em tela). */
function ler(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v.replace(",", "."));
  return Number.isFinite(n) ? n : NaN;
}

const CSS = `
.gm-campos { display: grid; grid-template-columns: 11rem 17rem auto minmax(0, 1fr); gap: 0.75rem 1.1rem; align-items: start; }
.gm-campos .gv-campo input[type="text"], .gm-campos .gv-campo input[type="month"] { min-height: 2.35rem; }
.gm-grupo-un { display: flex; flex-direction: column; gap: 0.25rem; }
.gm-rot { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); }
.gm-conv { display: flex; flex-direction: column; gap: 0.15rem; padding-top: 0.15rem; }
.gm-conv b { font-size: 1.05rem; font-variant-numeric: tabular-nums; }
.gm-conv span { font-size: 0.74rem; color: var(--text-muted); }
.gm-obs { max-width: 52rem; }
.gm-btn { display: inline-flex; align-items: center; gap: 0.35rem; min-height: 2rem; padding: 0.25rem 0.7rem; font-size: 0.78rem; font-weight: 600; border-radius: var(--r-sm); cursor: pointer; font-family: inherit; }
.gm-btn.btn-ghost { padding: 0.25rem 0.7rem; }
.gm-perigo { background: transparent; color: var(--ft-verm); border: 1px solid var(--ft-verm); }
.gm-perigo:hover { background: color-mix(in srgb, var(--ft-verm) 9%, transparent); }
.gm-perigo-cheio { background: var(--ft-verm); color: var(--surface); border: 1px solid var(--ft-verm); }
.gm-perigo-cheio:hover { background: color-mix(in srgb, var(--ft-verm) 85%, black); }
.gm-acoes { display: inline-flex; gap: 0.4rem; justify-content: flex-end; }
.gm-tabela td.gm-obs-cel { white-space: normal; color: var(--text-muted); font-size: 0.78rem; }
.gm-tabela td .gv-celula-input, .gm-tabela td select, .gm-tabela td input[type="month"], .gm-tabela td input.gm-livre { min-height: 2rem; }
.gm-tabela td select { background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); padding: 0.28rem 0.4rem; font-size: 0.82rem; }
.gm-tabela td input[type="month"], .gm-tabela td input.gm-livre { background: var(--surface-2); color: var(--text); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); padding: 0.28rem 0.45rem; font-size: 0.82rem; }
.gm-tabela td input.gm-livre { width: 100%; }
.gm-qtd { display: inline-flex; gap: 0.4rem; align-items: center; }
.gm-muda { color: var(--text-muted); }
.gm-esq { text-align: left; }
.gm-esqueleto { display: block; height: 0.9rem; }
.gm-vazio { display: flex; flex-direction: column; align-items: center; gap: 0.25rem; padding: 1.6rem 1rem; border: 1px dashed var(--border-strong, var(--border)); border-radius: var(--r-sm); background: var(--surface-2); text-align: center; }
.gm-vazio b { font-size: 0.85rem; } .gm-vazio span { font-size: 0.78rem; color: var(--text-muted); }
.gm-raiz { position: relative; }
.gm-fundo { position: absolute; inset: 0; z-index: 5; display: flex; align-items: center; justify-content: center; padding: 1rem; background: color-mix(in srgb, var(--text) 55%, transparent); }
.gm-modal { width: 31rem; max-width: 100%; background: var(--surface); border: 1px solid var(--border-strong, var(--border)); border-radius: var(--r-sm); padding: 1rem 1.1rem 1.1rem; display: flex; flex-direction: column; gap: 0.75rem; }
.gm-modal h2 { margin: 0; font-size: 0.8rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text); }
.gm-modal p { margin: 0; font-size: 0.85rem; line-height: 1.5; color: var(--text); }
.gm-modal footer { display: flex; justify-content: flex-end; gap: 0.5rem; }
.gm-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
`;

function Esqueleto({ linhas = 5 }: { linhas?: number }) {
  return (
    <>
      {Array.from({ length: linhas }, (_, k) => (
        <tr key={k} aria-hidden="true">
          <td><span className="skeleton gm-esqueleto" style={{ width: "4.5rem" }} /></td>
          <td className="gv-dir"><span className="skeleton gm-esqueleto" style={{ width: "6rem", marginLeft: "auto" }} /></td>
          <td className="gv-dir"><span className="skeleton gm-esqueleto" style={{ width: "5rem", marginLeft: "auto" }} /></td>
          <td><span className="skeleton gm-esqueleto" style={{ width: "60%" }} /></td>
          <td><span className="skeleton gm-esqueleto" style={{ width: "4rem" }} /></td>
          <td><span className="skeleton gm-esqueleto" style={{ width: "9rem", marginLeft: "auto" }} /></td>
        </tr>
      ))}
    </>
  );
}

function ConfirmaExclusao({ r, admin, aoCancelar, aoConfirmar }: { r: Registro; admin: boolean; aoCancelar: () => void; aoConfirmar: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") aoCancelar(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [aoCancelar]);
  const alvo = `${mesBR(r.competencia)} (${textoQtd(r.quantidade, r.unidade)})`;
  return (
    <div className="gm-fundo">
      <div className="gm-modal" role="dialog" aria-modal="true" aria-labelledby="gm-conf-t">
        <h2 id="gm-conf-t">{admin ? "Excluir entrega" : "Solicitar exclusão da entrega"}</h2>
        <p>
          {admin
            ? <>Excluir a entrega de <strong>{alvo}</strong>? Isso não pode ser desfeito.</>
            : <>Solicitar a exclusão da entrega de <strong>{alvo}</strong>? Um administrador precisa aprovar antes de ela ser excluída de fato.</>}
        </p>
        <footer>
          <button type="button" className="btn-ghost gm-btn" onClick={aoCancelar} autoFocus>Cancelar</button>
          <button type="button" className="gm-btn gm-perigo-cheio" onClick={aoConfirmar}><Trash2 size={14} aria-hidden="true" /> {admin ? "Excluir entrega" : "Solicitar exclusão"}</button>
        </footer>
      </div>
    </div>
  );
}

export function VendaLeite({ admin = true, estadoInicial = "ok", editandoInicial = null, confirmarInicial = null }: {
  admin?: boolean; estadoInicial?: EstadoLista; editandoInicial?: number | null; confirmarInicial?: number | null;
}) {
  const [mes, setMes] = useState("2026-09");
  const [qtd, setQtd] = useState("12480");
  const [un, setUn] = useState<Unidade>("kg");
  const [obs, setObs] = useState("");
  const [lista, setLista] = useState<Registro[]>(REGISTROS);
  const [estado, setEstado] = useState<EstadoLista>(estadoInicial);
  const [retorno, setRetorno] = useState<string | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);
  const [erroEdicao, setErroEdicao] = useState<string | null>(null);
  const [editId, setEditId] = useState<number | null>(editandoInicial);
  const base = REGISTROS.find((r) => r.id === editandoInicial);
  const [ev, setEv] = useState({ competencia: base?.competencia ?? "", quantidade: base ? String(base.quantidade) : "", unidade: (base?.unidade ?? "kg") as Unidade, observacao: base?.observacao ?? "" });
  const [confirmar, setConfirmar] = useState<number | null>(confirmarInicial);

  const q = ler(qtd);
  const qtdValida = q !== null && !Number.isNaN(q) && q > 0;
  const qtdInvalida = q !== null && (Number.isNaN(q) || q <= 0);
  const jaExiste = lista.find((r) => r.competencia === mes);
  const faltaMes = !mes;
  const semSalvar = faltaMes || !qtdValida;

  // Faixa de números do mês escolhido: o que se digita (ou o já lançado) × o controle leiteiro × a receita.
  const entregueKg = qtdValida ? emKg(q as number, un) : jaExiste ? emKg(jaExiste.quantidade, jaExiste.unidade) : null;
  const controle = CONTROLE_KG[mes] ?? null;
  const receita = RECEITA[mes] ?? null;
  const dif = entregueKg !== null && controle !== null ? controle - entregueKg : null;
  const difPct = dif !== null && controle ? (dif / controle) * 100 : null;
  const faixa = [
    { rotulo: `Entregue em ${mes ? mesBR(mes) : "—"} · kg`, valor: entregueKg !== null ? nb(entregueKg, entregueKg % 1 ? 1 : 0) : "—" },
    { rotulo: "Produzido no controle leiteiro · kg", valor: controle !== null ? nb(controle) : "—" },
    {
      rotulo: dif !== null && dif < 0 ? "Entregue acima do controle — confira" : "Diferença (não entregue)",
      valor: dif !== null && difPct !== null ? `${nb(Math.abs(dif), Math.abs(dif) % 1 ? 1 : 0)} kg · ${nb(Math.abs(difPct), 1)}%` : "—",
      tom: dif !== null && dif < 0 ? ("alerta" as const) : undefined,
    },
    { rotulo: `Receita recebida${receita !== null && entregueKg ? ` · ${brl(receita / entregueKg)}/kg` : ""}`, valor: receita !== null ? brl(receita) : "—" },
  ];

  const resumo = faltaMes ? "Falta escolher o mês" : qtdValida
    ? `Entrega de ${mesBR(mes)} · ${textoQtd(q as number, un)}${un === "L" ? ` (≈ ${nb(emKg(q as number, un), 1)} kg)` : ""}`
    : `Entrega de ${mesBR(mes)} · sem quantidade`;
  const detalhe = faltaMes ? "O mês é obrigatório."
    : qtdInvalida ? "A quantidade precisa ser um número maior que zero."
    : !qtdValida ? "Falta a quantidade entregue (maior que zero)."
    : jaExiste ? `Já existe entrega em ${mesBR(mes)} (${textoQtd(jaExiste.quantidade, jaExiste.unidade)}) — para corrigir, use Editar na tabela.`
    : "Entra no balanço Controle × Entregue (Histórico › Produção).";

  function salvar() {
    if (semSalvar) return;
    const novo: Registro = { id: Date.now(), competencia: mes, quantidade: q as number, unidade: un, observacao: obs.trim() || null, usuario: "Jairo" };
    setLista((l) => [novo, ...l].sort((a, b) => b.competencia.localeCompare(a.competencia)));
    setRetorno(`Entrega de ${mesBR(mes)} lançada — ${textoQtd(q as number, un)} · já está na tabela abaixo.`);
    setQtd(""); setObs("");
  }
  function iniciarEdicao(r: Registro) {
    setEditId(r.id); setErroEdicao(null);
    setEv({ competencia: r.competencia, quantidade: String(r.quantidade), unidade: r.unidade, observacao: r.observacao ?? "" });
  }
  function salvarEdicao(r: Registro) {
    const n = ler(ev.quantidade);
    if (!ev.competencia || n === null || Number.isNaN(n) || n <= 0) { setErroEdicao("Informe o mês e uma quantidade maior que zero."); return; }
    setLista((l) => l.map((x) => (x.id === r.id ? { ...x, competencia: ev.competencia, quantidade: n, unidade: ev.unidade, observacao: ev.observacao.trim() || null } : x)).sort((a, b) => b.competencia.localeCompare(a.competencia)));
    setEditId(null); setErroEdicao(null);
  }
  function confirmarExclusao() {
    const r = lista.find((x) => x.id === confirmar);
    setConfirmar(null);
    if (!r) return;
    if (admin) { setLista((l) => l.filter((x) => x.id !== r.id)); setAvisoExclusao(`Entrega de ${mesBR(r.competencia)} excluída.`); }
    else setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
  }

  const alvoConfirmar = lista.find((x) => x.id === confirmar);
  const vazio = estado === "ok" && lista.length === 0;
  const evQ = ler(ev.quantidade);

  return (
    <div className="gm-raiz">
      <style>{CSS}</style>
      <QuadroGaveta titulo="Venda mensal do leite" icone={TrendingUp} largura={1320}>
        <Faixa itens={faixa} />

        <Passo n={1} id="vl-p1" titulo="Entrega do mês">
          <div className="gm-campos">
            <Campo rotulo="Mês (obrigatório)" id="vl-mes"><input type="month" value={mes} onChange={(e) => setMes(e.target.value)} /></Campo>
            <Campo rotulo="Quantidade (maior que zero)" id="vl-qtd">
              <input type="text" inputMode="decimal" autoComplete="off" value={qtd} placeholder="ex.: 12480" aria-invalid={qtdInvalida}
                onChange={(e) => setQtd(e.target.value)} />
            </Campo>
            <div className="gm-grupo-un">
              <span className="gm-rot" id="vl-un-r">Unidade</span>
              <Pilulas<Unidade> rotulo="Unidade da entrega" valor={un} onChange={setUn}
                opcoes={[{ id: "kg", nome: "Quilo (kg)", titulo: "Como o laticínio mede a entrega no contrato" }, { id: "L", nome: "Litro (L)", titulo: "Como o laticínio mede a entrega no contrato" }]} />
            </div>
            <div className="gm-conv" aria-live="polite">
              <span className="gm-rot">Na conta do balanço</span>
              {qtdValida
                ? <><b>{nb(emKg(q as number, un), un === "L" ? 1 : casasDe(q as number))} kg</b><span>{un === "L" ? `${textoQtd(q as number, un)} × 1,029 kg/L` : "já está em quilos"}</span></>
                : <><b className="gm-muda">—</b><span>{qtdInvalida ? "Use só números (12480 ou 12480,5), sem ponto de milhar." : "Digite a quantidade do mês."}</span></>}
            </div>
          </div>
          <div className="gm-obs gv-campo">
            <label htmlFor="vl-obs">Observação (opcional)</label>
            <input id="vl-obs" type="text" value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Ex.: soma das notinhas, total do app do laticínio" />
          </div>
          <Ajuda>
            Some as notinhas de entrega (ou o total do app do laticínio) do mês inteiro e lance <strong>uma vez por mês</strong>. O controle leiteiro é sempre em kg:
            lançando em litro, o sistema converte (1 L = 1,029 kg) antes de comparar. O relatório de Produção usa este número contra o controle projetado e a receita recebida.
          </Ajuda>
          {qtdInvalida && <Aviso tom="erro">Quantidade inválida: informe um número maior que zero.</Aviso>}
        </Passo>

        <Passo n={2} id="vl-p2" titulo="Entregas lançadas" direita={
          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">
            {estado === "carregando" ? "Carregando…" : estado === "ok" ? `${lista.length} ${lista.length === 1 ? "mês lançado" : "meses lançados"}` : ""}
          </span>
        }>
          {avisoExclusao && <Aviso>{avisoExclusao}</Aviso>}
          {erroEdicao && <Aviso tom="erro">{erroEdicao}</Aviso>}
          {estado === "erro" ? (
            <div className="gm-vazio" role="alert">
              <b>Não foi possível carregar as entregas</b>
              <span>Confira a conexão e tente de novo — as entregas já lançadas continuam guardadas.</span>
              <button type="button" className="btn-ghost gm-btn" onClick={() => setEstado("ok")}>Tentar de novo</button>
            </div>
          ) : vazio || estado === "vazio" ? (
            <div className="gm-vazio"><b>Nenhuma entrega lançada ainda</b><span>Lance a primeira no passo 1: uma entrega por mês.</span></div>
          ) : (
            <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "22rem" }} aria-busy={estado === "carregando"}>
              <table className="gv-tabela gm-tabela">
                <thead>
                  <tr>
                    <th scope="col" style={{ width: "9.5rem" }}>Mês</th>
                    <th scope="col" className="gv-dir" title="Valor lançado, na unidade do contrato (kg ou L)">Quantidade</th>
                    <th scope="col" className="gv-dir" title="Normalizado em quilos para o balanço (1 L = 1,029 kg)">≈ kg</th>
                    <th scope="col">Observação</th>
                    <th scope="col">Lançado por</th>
                    <th scope="col" className="gv-dir">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {estado === "carregando" ? <Esqueleto /> : lista.map((r) => {
                    const editando = editId === r.id;
                    const kgReg = emKg(r.quantidade, r.unidade);
                    if (editando) {
                      return (
                        <tr key={r.id} className="gv-linha-marcada">
                          <td><input type="month" aria-label="Mês" value={ev.competencia} onChange={(e) => setEv((s) => ({ ...s, competencia: e.target.value }))} /></td>
                          <td className="gv-dir">
                            <span className="gm-qtd">
                              <input className="gv-celula-input" type="text" inputMode="decimal" aria-label="Quantidade" value={ev.quantidade} onChange={(e) => setEv((s) => ({ ...s, quantidade: e.target.value }))} />
                              <select aria-label="Unidade" value={ev.unidade} onChange={(e) => setEv((s) => ({ ...s, unidade: e.target.value as Unidade }))}>
                                <option value="kg">kg</option><option value="L">L</option>
                              </select>
                            </span>
                          </td>
                          <td className="gv-dir gv-num gm-muda">{evQ !== null && !Number.isNaN(evQ) && evQ > 0 ? `${nb(emKg(evQ, ev.unidade), 1)} kg` : "—"}</td>
                          <td><input className="gm-livre" type="text" aria-label="Observação" value={ev.observacao} placeholder="Opcional" onChange={(e) => setEv((s) => ({ ...s, observacao: e.target.value }))} /></td>
                          <td className="gm-muda">{r.usuario}</td>
                          <td>
                            <span className="gm-acoes">
                              <button type="button" className="btn-primary-gold gm-btn" onClick={() => salvarEdicao(r)}><Check size={14} aria-hidden="true" /> Salvar</button>
                              <button type="button" className="btn-ghost gm-btn" onClick={() => { setEditId(null); setErroEdicao(null); }}><X size={14} aria-hidden="true" /> Cancelar</button>
                            </span>
                          </td>
                        </tr>
                      );
                    }
                    return (
                      <tr key={r.id}>
                        <td className="gv-forte gv-num">{mesBR(r.competencia)}</td>
                        <td className="gv-dir gv-num gv-forte">{textoQtd(r.quantidade, r.unidade)}</td>
                        <td className={`gv-dir gv-num${r.unidade === "kg" ? " gm-muda" : ""}`}>{nb(kgReg, kgReg % 1 ? 1 : 0)} kg</td>
                        <td className="gm-obs-cel">{r.observacao || "—"}</td>
                        <td className="gm-muda">{r.usuario}</td>
                        <td>
                          <span className="gm-acoes">
                            <button type="button" className="btn-ghost gm-btn" onClick={() => iniciarEdicao(r)} aria-label={`Editar a entrega de ${mesBR(r.competencia)}`}><Pencil size={14} aria-hidden="true" /> Editar</button>
                            <button type="button" className="gm-btn gm-perigo" onClick={() => setConfirmar(r.id)} aria-label={`${admin ? "Excluir" : "Solicitar exclusão d"}${admin ? " a" : "a"} entrega de ${mesBR(r.competencia)}`}><Trash2 size={14} aria-hidden="true" /> {admin ? "Excluir" : "Solicitar exclusão"}</button>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {estado === "carregando" && <span className="gm-sr" role="status">Carregando as entregas lançadas…</span>}
            </div>
          )}
          <Ajuda>
            {admin ? "Excluir é imediato para administradores e fica registrado." : "Operador não exclui direto: a exclusão vira uma solicitação que um administrador aprova."} A coluna “≈ kg” é o que entra no balanço (litro × 1,029).
          </Ajuda>
        </Passo>

        <BarraAcao
          resumo={resumo}
          detalhe={detalhe}
          retorno={retorno ? <span role="status" style={{ color: "var(--ft-verde)", fontWeight: 700 }}>✓ {retorno}</span> : undefined}
          acao={<BotaoOuro desabilitado={semSalvar} onClick={salvar}>Salvar entrega do mês</BotaoOuro>}
        />
      </QuadroGaveta>
      {alvoConfirmar && <ConfirmaExclusao r={alvoConfirmar} admin={admin} aoCancelar={() => setConfirmar(null)} aoConfirmar={confirmarExclusao} />}
    </div>
  );
}
