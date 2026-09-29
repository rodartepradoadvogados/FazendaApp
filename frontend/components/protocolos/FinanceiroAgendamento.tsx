"use client";
// Cruzamento do agendamento preventivo com Compras, Estoque e Financeiro
// (fatia 9; mockup fluxo-completo, proto-montar.js: drCompra/drFin).
//
// Três itens do checklist, sempre sem bloquear nada:
//   Compra ............ "Comunicar compra": cotação ou pedido do insumo que falta
//                       (quantidade = dose × animais), ou "Já comprei".
//   Pagamento ......... "Vincular pagamento já realizado": escolhe um lançamento
//                       já pago do Financeiro, sem duplicar.
//   Conta a pagar ..... honorário do veterinário ou produtos (custo × dose).
//
// Dois modos com a MESMA tela: `FinanceiroVivo` (agendamento já existe: cada ação
// grava na hora) e `FinanceiroRascunho` (passo Checklist do assistente: o agendamento
// ainda não existe; a escolha vai junto no "Criar agendamento").
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Ban, Check, ExternalLink, Link2, Receipt, ShoppingCart, SkipForward, Unlink, Wallet, X } from "lucide-react";
import {
  comunicarCompraAgendamento, editarChecklistAgendamento, encerrarVinculoAgendamento, fetchFinanceiroAgendamento,
  fetchFornecedoresSugeridos, fetchPagamentosCandidatos, fetchPreviaFinanceiro, lancarContaPagarAgendamento,
  vincularPagamentoAgendamento, type BlocoFinanceiro, type CompraPayload, type ContaPagarPayload, type EstadoItemFin,
  type FinanceiroChecklistPayload, type NecessidadeInsumo, type PagamentoCandidato, type ResumoFinanceiroAg, type VinculoAg,
} from "@/lib/api";
import {
  brl, Chips, dataCurta, inputStyle, labelStyle, maisDiasIso, notaStyle, num, Pill, plural, textoMotivo,
} from "./preventivoComum";

const CATEGORIA_COTACAO = "Medicamentos e produtos veterinários";
const MOTIVOS_DESVINCULAR = ["Vinculei o pagamento errado", "Mudança de plano", "Outro motivo"] as const;
const MOTIVOS_CANCELAR_CONTA = ["Lançada por engano", "Mudança de plano", "Outro motivo"] as const;
const MOTIVOS_DESCONSIDERAR_FIN = ["Não haverá cobrança neste agendamento", "Já lançado em outro lugar", "Outro"] as const;

// ─────────────────────────── rascunho (assistente) ───────────────────────────
export type FinanceiroDraft = {
  compra: (CompraPayload & { rotulo: string }) | null;
  pagamento: { pagamento_id: number; modo: "proporcional" | "inteiro"; rotulo: string; valor: number | null } | null;
  contas: (ContaPagarPayload & { rotulo: string })[];
};
export const financeiroVazio = (): FinanceiroDraft => ({ compra: null, pagamento: null, contas: [] });

export function financeiroParaPayload(d: FinanceiroDraft): FinanceiroChecklistPayload | undefined {
  const p: FinanceiroChecklistPayload = {};
  if (d.compra) { const { rotulo: _r, ...c } = d.compra; p.compra = c; }
  if (d.pagamento) p.pagamento = { pagamento_id: d.pagamento.pagamento_id, modo: d.pagamento.modo };
  if (d.contas.length) p.contas = d.contas.map(({ rotulo: _r, ...c }) => c);
  return Object.keys(p).length ? p : undefined;
}

// ─────────────────────────── apresentação enxuta (Conferir, pós-aplicação, Concluídos) ───────────────────────────
/** Custo previsto (ou "a informar" + por quê) e o que existe de conta a pagar, pagamento e compra. */
export function ResumoCustoFinanceiro({ bloco, rotuloCusto = "Custo previsto", custo, className }: {
  bloco: BlocoFinanceiro | undefined | null; rotuloCusto?: string; custo?: number | null; className?: string;
}) {
  if (!bloco) return null;
  const valor = custo !== undefined ? custo : bloco.custo_previsto;
  const informar = valor == null;
  const ativas = bloco.contas.filter((c) => c.estado === "ativo");
  const canceladas = bloco.contas.filter((c) => c.estado === "cancelado");
  const pagos = bloco.pagamentos.filter((p) => p.estado === "ativo");
  return (
    <div className={className} style={{ display: "flex", flexDirection: "column", gap: "0.35rem", fontSize: "0.84rem" }}>
      <span>
        <b>{rotuloCusto}:</b> {informar ? <span style={{ color: "var(--amber)", fontWeight: 700 }}>a informar</span> : <b>{brl(valor)}</b>}
        {informar && bloco.custo_motivo && <span style={notaStyle}> · {bloco.custo_motivo}</span>}
      </span>
      {ativas.map((c) => (
        <span key={c.id}>
          <b>Conta a pagar:</b> {c.rotulo || "—"} · {brl(c.valor)}{c.vencimento ? ` · vence ${dataCurta(c.vencimento)}` : ""}{c.numero_lancamento ? ` · ${c.numero_lancamento}` : ""}
          {c.alvo?.paga ? <Pill cor="var(--green-light)"><Check size={11} />paga</Pill> : null}
        </span>
      ))}
      {canceladas.map((c) => (
        <span key={c.id} style={{ color: "var(--text-muted)" }}>
          <s>Conta a pagar: {c.rotulo || "—"} · {brl(c.valor)}</s> · Cancelada{c.motivo_encerramento ? ` (${c.motivo_encerramento})` : ""}, fora de A pagar
        </span>
      ))}
      {pagos.map((p) => <span key={p.id}><b>Pagamento já realizado:</b> {p.rotulo || "—"} · vinculado {brl(p.valor)}{p.numero_lancamento ? ` · ${p.numero_lancamento}` : ""}</span>)}
      {bloco.compras.filter((c) => c.estado === "ativo").map((c) => (
        <span key={c.id}><b>{c.tipo === "cotacao" ? "Cotação" : "Pedido"}:</b> {c.numero_lancamento || c.alvo?.numero} · {c.descricao}</span>
      ))}
      {!ativas.length && !pagos.length && !canceladas.length && (
        <span style={notaStyle}>Sem conta a pagar nem pagamento vinculado: lance em Contas a pagar ou vincule pelo checklist.</span>
      )}
      <a href={bloco.link_contas_a_pagar} className="lnk" style={{ color: "var(--dourado-light)", textDecoration: "underline", display: "inline-flex", alignItems: "center", gap: 4, width: "fit-content" }}>
        <ExternalLink size={12} />Ver contas a pagar
      </a>
    </div>
  );
}

// ─────────────────────────── peças ───────────────────────────
const PILL: Record<string, { txt: string; cor: string }> = {
  pendente: { txt: "Pendente", cor: "var(--amber)" }, ok: { txt: "Cumprido", cor: "var(--green-light)" },
  nao_necessaria: { txt: "Não necessária", cor: "var(--green-light)" }, desconsiderado: { txt: "Desconsiderado", cor: "var(--text-muted)" },
  pulado: { txt: "Desconsiderado", cor: "var(--text-muted)" },
};
function EstadoPillFin({ estado }: { estado: EstadoItemFin | string }) {
  const p = PILL[estado] || PILL.pendente;
  return <Pill cor={p.cor}>{estado === "pendente" ? <AlertTriangle size={11} /> : estado === "desconsiderado" || estado === "pulado" ? <SkipForward size={11} /> : <Check size={11} />}{p.txt}</Pill>;
}

function Linha({ icone, titulo, estado, children, acoes }: {
  icone: React.ReactNode; titulo: string; estado: string; children?: React.ReactNode; acoes?: React.ReactNode;
}) {
  return (
    <div style={{ borderBottom: "1px solid var(--border)", padding: "0.75rem 0", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <span style={{ color: "var(--dourado-light)", display: "inline-flex" }}>{icone}</span>
        <b style={{ fontSize: "0.9rem" }}>{titulo}</b>
        <EstadoPillFin estado={estado} />
      </div>
      {children}
      {acoes && <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>{acoes}</div>}
    </div>
  );
}

function Aviso({ cor = "var(--amber)", children }: { cor?: string; children: React.ReactNode }) {
  return (
    <p role="status" style={{ display: "flex", gap: 6, alignItems: "flex-start", fontSize: "0.82rem", margin: 0, color: cor }}>
      <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} /><span>{children}</span>
    </p>
  );
}

const numDe = (v: string): number | null => {
  const n = Number(String(v).replace(/\./g, "").replace(",", "."));
  return v.trim() !== "" && !isNaN(n) ? n : null;
};
const numDeSimples = (v: string): number | null => {
  const n = Number(String(v).replace(",", "."));
  return v.trim() !== "" && !isNaN(n) ? n : null;
};

type Fornecedor = { id: number; nome: string };

// ─────────────── formulário: comunicar compra ───────────────
function FormCompra({ nec, dataEvento, onSubmit, onCancelar, salvando, rotuloBotao }: {
  nec: NecessidadeInsumo; dataEvento: string; onSubmit: (p: CompraPayload, rotulo: string) => void; onCancelar: () => void;
  salvando?: boolean; rotuloBotao: string;
}) {
  const [modo, setModo] = useState<"cotacao" | "pedido">("cotacao");
  const [qtd, setQtd] = useState(String(nec.falta || nec.precisa || ""));
  const [ate, setAte] = useState(dataEvento);
  const [forn, setForn] = useState<Fornecedor[]>([]);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [nomePedido, setNomePedido] = useState("");
  const [enviar, setEnviar] = useState(false);
  const [tentou, setTentou] = useState(false);
  useEffect(() => { fetchFornecedoresSugeridos(CATEGORIA_COTACAO).then((l) => setForn(l.map((f: any) => ({ id: f.id, nome: f.nome })))).catch(() => setForn([])); }, []);
  const q = numDeSimples(qtd);
  const estimativa = q != null && nec.preco_unitario != null ? q * nec.preco_unitario : null;
  const un = nec.unidade_estoque || nec.unidade || "";
  const nomes = forn.filter((f) => sel.has(f.id)).map((f) => f.nome);
  const erro = q == null || q <= 0 ? "Informe a quantidade." : modo === "pedido" && !nomePedido.trim() && !sel.size ? "Escolha ou escreva o fornecedor do pedido." : null;

  function enviarForm() {
    setTentou(true);
    if (erro || q == null) return;
    const p: CompraPayload = { modo, quantidade: q, fornecedor_ids: Array.from(sel), necessario_ate: ate || null };
    if (modo === "pedido") p.fornecedor_nome = nomePedido.trim() || nomes[0] || null;
    if (modo === "cotacao" && enviar && sel.size) p.disparar = true;
    onSubmit(p, modo === "pedido" ? `Pedido · ${p.fornecedor_nome}` : `Cotação${nomes.length ? ` · ${nomes.join(", ")}` : " (fornecedores a escolher em Cotações)"}`);
  }
  return (
    <div className="card" role="group" aria-label="Comunicar compra" style={{ display: "flex", flexDirection: "column", gap: "0.7rem", borderLeft: "4px solid var(--dourado)" }}>
      <h4 className="card-header" style={{ margin: 0 }}>Comunicar compra</h4>
      {nec.falta > 0
        ? <Aviso>Precisa de {num(nec.precisa)} {un} · saldo {num(nec.saldo ?? 0)} · <b>faltam {num(nec.falta)} {un}</b>.</Aviso>
        : <p style={{ ...notaStyle, margin: 0 }}>{nec.precisa ? `O estoque cobre (${num(nec.saldo ?? 0)} ${un}). Comunique só se quiser repor.` : "Sem animais no agendamento ainda."}</p>}
      {nec.aproximada && <p style={{ ...notaStyle, margin: 0 }}>Quantidade aproximada: parte das doses vem do peso estimado do lote.</p>}
      <Chips idBase="fc-modo" rotulo="O que fazer" opcoes={["Pedir cotação", "Fazer o pedido direto"]} valor={modo === "cotacao" ? "Pedir cotação" : "Fazer o pedido direto"}
             onChange={(v) => setModo(v === "Pedir cotação" ? "cotacao" : "pedido")} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><label htmlFor="fc-q" style={labelStyle}>Quantidade ({un || "unidades"})</label><input id="fc-q" inputMode="decimal" style={inputStyle} value={qtd} onChange={(e) => setQtd(e.target.value)} aria-invalid={tentou && q == null ? true : undefined} /></div>
        <div><label htmlFor="fc-a" style={labelStyle}>Necessário até</label><input id="fc-a" type="date" style={inputStyle} value={ate} onChange={(e) => setAte(e.target.value)} /></div>
      </div>
      <div>
        <span style={labelStyle}>{modo === "cotacao" ? "Fornecedores para a cotação (opcional agora)" : "Fornecedor do pedido"}</span>
        {forn.length > 0 ? (
          <div role="group" aria-label="Fornecedores" style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
            {forn.map((f) => {
              const on = sel.has(f.id);
              return (
                <button key={f.id} type="button" aria-pressed={on} onClick={() => setSel((p) => { const s = new Set(modo === "pedido" ? [] : p); if (on) s.delete(f.id); else s.add(f.id); return s; })}
                        style={{ fontSize: "0.8rem", padding: "0.4rem 0.8rem", borderRadius: 999, cursor: "pointer", minHeight: 36, border: `1px solid ${on ? "var(--pill-active-border)" : "var(--border)"}`,
                                 background: on ? "var(--pill-active-bg)" : "transparent", color: on ? "var(--pill-active-fg)" : "var(--text)", fontWeight: on ? 700 : 500 }}>{f.nome}</button>
              );
            })}
          </div>
        ) : <p style={{ ...notaStyle, margin: 0 }}>Nenhum fornecedor de medicamentos cadastrado.{modo === "cotacao" ? " A cotação nasce em rascunho e você escolhe os fornecedores em Cotações." : ""}</p>}
        {modo === "pedido" && <input style={{ ...inputStyle, marginTop: "0.4rem" }} aria-label="Fornecedor do pedido (nome)" placeholder="ou escreva o nome do fornecedor" value={nomePedido} onChange={(e) => setNomePedido(e.target.value)} />}
      </div>
      {modo === "cotacao" && sel.size > 0 && (
        <label style={{ display: "flex", gap: "0.6rem", alignItems: "center", cursor: "pointer", fontSize: "0.85rem" }}>
          <input type="checkbox" checked={enviar} onChange={(e) => setEnviar(e.target.checked)} style={{ width: 18, height: 18 }} />
          <span>Enviar agora aos fornecedores escolhidos (e-mail/WhatsApp)</span>
        </label>
      )}
      <p style={{ ...notaStyle, margin: 0 }}>
        Estimativa: <b>{estimativa != null ? brl(estimativa) : "a informar"}</b>{estimativa != null ? ` (${num(q)} × ${brl(nec.preco_unitario)})` : " · produto sem preço cadastrado"}.
        {" "}Cria {modo === "cotacao" ? "a cotação em Cotações" : "o pedido em Pedidos"} e marca este item como cumprido. Nada bloqueia o agendamento.
      </p>
      {tentou && erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem", margin: 0 }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={enviarForm}><ShoppingCart size={14} /> {salvando ? "Enviando…" : rotuloBotao}</button>
        <button type="button" className="btn-ghost" onClick={onCancelar}>Voltar</button>
      </div>
    </div>
  );
}

// ─────────────── formulário: vincular pagamento ───────────────
function FormPagamento({ nec, candidatos, carregando, onSubmit, onCancelar, onLancarConta, salvando, rotuloBotao }: {
  nec: NecessidadeInsumo; candidatos: PagamentoCandidato[] | null; carregando: boolean; salvando?: boolean; rotuloBotao: string;
  onSubmit: (id: number, modo: "proporcional" | "inteiro", c: PagamentoCandidato) => void; onCancelar: () => void; onLancarConta: () => void;
}) {
  const [sel, setSel] = useState<number | null>(null);
  const [modo, setModo] = useState<"proporcional" | "inteiro">("proporcional");
  const c = (candidatos || []).find((x) => x.id === sel) || null;
  const prop = c?.proporcional ?? null;
  const proporcionalDisponivel = prop != null;
  const valor = c ? (modo === "inteiro" || prop == null ? c.resta : Math.min(prop, c.resta)) : null;
  const un = nec.unidade_estoque || nec.unidade || "";
  return (
    <div className="card" role="group" aria-label="Vincular pagamento já realizado" style={{ display: "flex", flexDirection: "column", gap: "0.7rem", borderLeft: "4px solid var(--dourado)" }}>
      <h4 className="card-header" style={{ margin: 0 }}>Vincular pagamento já realizado</h4>
      {carregando && <p style={notaStyle}>Procurando compras já pagas de {nec.produto || "este produto"}…</p>}
      {!carregando && candidatos && candidatos.length === 0 && (
        <div style={{ textAlign: "center", padding: "0.6rem 0" }}>
          <Wallet size={26} style={{ color: "var(--text-muted)", margin: "0 auto 0.4rem" }} />
          <p style={{ margin: 0 }}>Nenhuma compra paga encontrada para {nec.produto || "este produto"}.</p>
          <p style={{ ...notaStyle, margin: "0.3rem 0 0.6rem" }}>Se a compra ainda vai ser paga, lance uma conta a pagar.</p>
          <button type="button" className="btn-primary" onClick={onLancarConta}><Receipt size={14} /> Lançar conta a pagar</button>
        </div>
      )}
      {!!candidatos?.length && (
        <div role="radiogroup" aria-label="Compras já pagas do mesmo produto" style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {candidatos.map((p) => (
            <label key={p.id} style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", cursor: "pointer", padding: "0.5rem 0.7rem", border: `1px solid ${sel === p.id ? "var(--pill-active-border)" : "var(--border)"}`, borderRadius: "var(--r-sm)", background: sel === p.id ? "var(--pill-active-bg)" : "var(--surface-2)" }}>
              <input type="radio" name="fp-pg" checked={sel === p.id} onChange={() => setSel(p.id)} style={{ marginTop: 3 }} />
              <span style={{ flex: 1, fontSize: "0.85rem" }}>
                <b>{p.fornecedor || "Fornecedor"}</b> · {dataCurta(p.data_pagamento)} · {brl(p.valor)}{p.numero_lancamento ? ` · ${p.numero_lancamento}` : ""}
                <span style={{ ...notaStyle, display: "block" }}>{p.descricao}{p.doses ? ` · cobre ${num(p.doses)} ${un}` : ""}</span>
                {p.usado > 0 && <span style={{ ...notaStyle, display: "block" }}>Já vinculado a outros agendamentos: {brl(p.usado)} ({Math.round((p.usado / p.valor) * 100)}%) · resta {brl(p.resta)}</span>}
              </span>
              <Pill cor="var(--green-light)"><Check size={11} />pago</Pill>
            </label>
          ))}
        </div>
      )}
      {c && (
        <div className="card" style={{ padding: "0.6rem 0.8rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <p style={{ margin: 0, fontSize: "0.85rem" }}>
            {proporcionalDisponivel
              ? <>Este agendamento usa {num(nec.precisa)} {un} ({brl(prop)}, {Math.round(((prop || 0) / c.valor) * 100)}% do pagamento).</>
              : <>Não sei quantas doses este pagamento cobre: só dá para vincular o valor que resta.</>}
          </p>
          {proporcionalDisponivel && prop! > c.resta + 0.001 && <Aviso>O proporcional passa do que ainda resta neste pagamento ({brl(c.resta)}); vai vincular só o que resta.</Aviso>}
          {c.resta <= 0 && <Aviso cor="var(--red)">Este pagamento já está totalmente vinculado a outros agendamentos.</Aviso>}
          {proporcionalDisponivel && (
            <Chips idBase="fp-modo" rotulo="Como vincular" opcoes={[`Só o proporcional (${brl(Math.min(prop!, c.resta))})`, `O valor inteiro que resta (${brl(c.resta)})`]}
                   valor={modo === "proporcional" ? `Só o proporcional (${brl(Math.min(prop!, c.resta))})` : `O valor inteiro que resta (${brl(c.resta)})`}
                   onChange={(v) => setModo(v.startsWith("Só") ? "proporcional" : "inteiro")} />
          )}
        </div>
      )}
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" className="btn-primary-gold" disabled={!c || salvando || (c?.resta ?? 0) <= 0} onClick={() => c && onSubmit(c.id, proporcionalDisponivel ? modo : "inteiro", c)}>
          <Link2 size={14} /> {salvando ? "Vinculando…" : rotuloBotao}{valor != null ? ` (${brl(valor)})` : ""}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancelar}>Voltar</button>
      </div>
    </div>
  );
}

// ─────────────── formulário: conta a pagar ───────────────
function FormConta({ nec, dataEvento, vetNome, onSubmit, onCancelar, salvando, rotuloBotao }: {
  nec: NecessidadeInsumo; dataEvento: string; vetNome: string | null; salvando?: boolean; rotuloBotao: string;
  onSubmit: (p: ContaPagarPayload, rotulo: string) => void; onCancelar: () => void;
}) {
  const [subtipo, setSubtipo] = useState<"honorario" | "produto">(nec.custo_previsto == null ? "honorario" : "produto");
  const [forn, setForn] = useState("");
  const [valor, setValor] = useState("");
  const [desc, setDesc] = useState("");
  const [venc, setVenc] = useState(() => { const base = dataEvento && dataEvento >= maisDiasIso(0) ? dataEvento : maisDiasIso(0); return maisDiasIso(10, base); });
  const [tentou, setTentou] = useState(false);
  const fornSug = forn || (subtipo === "honorario" ? (vetNome || "") : "");
  const valorSug = valor !== "" ? valor : subtipo === "produto" && nec.custo_previsto != null ? String(nec.custo_previsto).replace(".", ",") : "";
  const v = numDe(valorSug);
  const erroValor = tentou && (v == null || v <= 0) ? (subtipo === "produto" && nec.custo_previsto == null ? "O custo do produto não é conhecido (frasco do veterinário ou sem preço): informe o valor." : "Informe o valor.") : null;
  const erroForn = tentou && !fornSug.trim() ? "Informe o fornecedor ou o serviço." : null;
  function enviar() {
    setTentou(true);
    if (v == null || v <= 0 || !fornSug.trim() || !venc) return;
    onSubmit({ subtipo, fornecedor: fornSug.trim(), valor: v, vencimento: venc, descricao: desc.trim() || null }, `${fornSug.trim()} · ${brl(v)} · vence ${dataCurta(venc)}`);
  }
  return (
    <div className="card" role="group" aria-label="Lançar conta a pagar" style={{ display: "flex", flexDirection: "column", gap: "0.7rem", borderLeft: "4px solid var(--dourado)" }}>
      <h4 className="card-header" style={{ margin: 0 }}>Lançar conta a pagar</h4>
      <Chips idBase="fcp-t" rotulo="O que lançar" opcoes={["Honorário do veterinário", "Produtos"]} valor={subtipo === "honorario" ? "Honorário do veterinário" : "Produtos"}
             onChange={(x) => { setSubtipo(x === "Produtos" ? "produto" : "honorario"); setForn(""); setValor(""); }} />
      {subtipo === "produto" && (
        nec.custo_previsto != null
          ? <p style={{ ...notaStyle, margin: 0 }}>Valor previsto: <b>{brl(nec.custo_previsto)}</b> ({num(nec.precisa)} {nec.unidade || ""} × {brl(nec.preco_unitario)}).</p>
          : <Aviso>Custo do produto a informar{nec.custo_motivo ? `: ${nec.custo_motivo}` : ""}. Digite o valor da conta.</Aviso>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><label htmlFor="fcp-f" style={labelStyle}>Fornecedor / serviço</label><input id="fcp-f" style={inputStyle} value={fornSug} onChange={(e) => setForn(e.target.value)} placeholder={subtipo === "honorario" ? "ex.: nome do veterinário" : "ex.: Agro Vet"} aria-invalid={erroForn ? true : undefined} />{erroForn && <span role="alert" style={{ color: "var(--red)", fontSize: "0.78rem" }}>{erroForn}</span>}</div>
        <div><label htmlFor="fcp-v" style={labelStyle}>Valor (R$)</label><input id="fcp-v" inputMode="decimal" style={inputStyle} value={valorSug} onChange={(e) => setValor(e.target.value)} aria-invalid={erroValor ? true : undefined} />{erroValor && <span role="alert" style={{ color: "var(--red)", fontSize: "0.78rem" }}>{erroValor}</span>}</div>
      </div>
      <div><label htmlFor="fcp-d" style={labelStyle}>Descrição (opcional)</label><input id="fcp-d" style={inputStyle} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={subtipo === "honorario" ? "Honorário — protocolo" : "Produto do protocolo"} /></div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div><label htmlFor="fcp-vn" style={labelStyle}>Vencimento</label><input id="fcp-vn" type="date" style={inputStyle} value={venc} onChange={(e) => setVenc(e.target.value)} /></div>
        <div><label htmlFor="fcp-cc" style={labelStyle}>Centro de custo</label><input id="fcp-cc" style={inputStyle} readOnly aria-readonly="true" value="Pecuária Leiteira" /></div>
      </div>
      <p style={{ ...notaStyle, margin: 0 }}>Entra em Financeiro › Contas a pagar como despesa em aberto (previsão): não dá entrada no estoque nem baixa nada.</p>
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={enviar}><Receipt size={14} /> {salvando ? "Lançando…" : rotuloBotao}</button>
        <button type="button" className="btn-ghost" onClick={onCancelar}>Voltar</button>
      </div>
    </div>
  );
}

// ─────────────── ações sobre vínculos existentes ───────────────
function EncerrarInline({ opcoes, rotulo, onConfirmar, onVoltar, ocupado, aviso }: {
  opcoes: readonly string[]; rotulo: string; onConfirmar: (motivo: string) => void; onVoltar: () => void; ocupado?: boolean; aviso?: string;
}) {
  const [m, setM] = useState("");
  const [o, setO] = useState("");
  const texto = textoMotivo(m, o);
  return (
    <div className="card" style={{ padding: "0.6rem 0.8rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {aviso && <Aviso>{aviso}</Aviso>}
      <Chips idBase={`enc-${rotulo}`} rotulo="Motivo (obrigatório)" opcoes={opcoes} valor={m} onChange={setM} />
      {(m === "Outro" || m === "Outro motivo") && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={o} onChange={(e) => setO(e.target.value)} />}
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <button type="button" className="btn-primary" disabled={!texto || ocupado} onClick={() => onConfirmar(texto)}>{rotulo}</button>
        <button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button>
      </div>
    </div>
  );
}

function VinculoLinha({ v, readOnly, onEncerrar, ocupado }: {
  v: VinculoAg; readOnly: boolean; ocupado?: boolean; onEncerrar?: (v: VinculoAg, motivo: string) => void;
}) {
  const [abrindo, setAbrindo] = useState(false);
  const morto = v.estado !== "ativo";
  const acao = v.tipo === "conta" ? "Cancelar conta" : v.tipo === "pagamento" ? "Desvincular" : v.tipo === "cotacao" ? "Cancelar cotação" : null;
  const opcoes = v.tipo === "pagamento" ? MOTIVOS_DESVINCULAR : MOTIVOS_CANCELAR_CONTA;
  const titulo = v.tipo === "conta" ? `${v.rotulo || "Conta"} · ${brl(v.valor)}${v.vencimento ? ` · vence ${dataCurta(v.vencimento)}` : ""}`
    : v.tipo === "pagamento" ? `${v.rotulo || "Pagamento"} · ${dataCurta(v.vencimento)} · vinculado ${brl(v.valor)}${v.modo === "inteiro" ? " (valor inteiro)" : v.modo === "proporcional" ? " (proporcional)" : ""}`
    : `${v.tipo === "cotacao" ? "Cotação" : "Pedido"} ${v.numero_lancamento || ""} · ${v.descricao || ""}`;
  const estadoTxt = v.estado === "cancelado" ? "Cancelada" : v.estado === "desvinculado" ? "Desvinculado" : null;
  const linkHref = v.tipo === "cotacao" ? "/cotacoes" : v.tipo === "pedido" ? "/pedidos" : "/financeiro";
  const linkTxt = v.tipo === "cotacao" ? "Abrir em Cotações" : v.tipo === "pedido" ? "Abrir em Pedidos" : v.tipo === "conta" ? "Ver em Contas a pagar" : "Ver lançamento";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap", fontSize: "0.85rem", color: morto ? "var(--text-muted)" : undefined }}>
        <span style={{ flex: "1 1 240px", textDecoration: morto ? "line-through" : undefined }}>{titulo}{v.numero_lancamento && v.tipo !== "cotacao" && v.tipo !== "pedido" ? ` · ${v.numero_lancamento}` : ""}</span>
        {estadoTxt && <Pill cor="var(--text-muted)"><Ban size={11} />{estadoTxt}</Pill>}
        {v.tipo === "conta" && !morto && v.alvo?.paga && <Pill cor="var(--green-light)"><Check size={11} />paga</Pill>}
        {(v.tipo === "cotacao" || v.tipo === "pedido") && v.alvo?.status && !morto && <Pill cor="var(--text-muted)">{v.alvo.status.replace("_", " ")}</Pill>}
        {!morto && <a href={linkHref} className="lnk" style={{ color: "var(--dourado-light)", textDecoration: "underline", fontSize: "0.8rem", display: "inline-flex", gap: 3, alignItems: "center" }}><ExternalLink size={12} />{linkTxt}</a>}
        {!morto && !readOnly && acao && onEncerrar && (
          <button type="button" className="btn-ghost" disabled={ocupado} onClick={() => setAbrindo(true)}>{v.tipo === "pagamento" ? <Unlink size={13} /> : <X size={13} />} {acao}…</button>
        )}
      </div>
      {morto && v.motivo_encerramento && <span style={notaStyle}>{estadoTxt} por {v.encerrado_por || "—"}: {v.motivo_encerramento}{v.tipo === "conta" ? " · fora de A pagar e dos totais" : ""}</span>}
      {abrindo && onEncerrar && (
        <EncerrarInline opcoes={opcoes} rotulo={acao || "Confirmar"} ocupado={ocupado} onVoltar={() => setAbrindo(false)}
                        aviso={v.tipo === "conta" ? "A conta sai de Contas a pagar e dos totais. Se já foi paga, estorne a baixa antes." : undefined}
                        onConfirmar={(m) => { onEncerrar(v, m); setAbrindo(false); }} />
      )}
    </div>
  );
}

// ─────────────────────────── modo VIVO (agendamento existe) ───────────────────────────
type Aberto = null | "compra" | "pagamento" | "conta" | "desconsiderar";

export function FinanceiroVivo({ cronogramaId, dataEvento, vetNome, readOnly, onMudou }: {
  cronogramaId: number; dataEvento: string; vetNome: string | null; readOnly?: boolean; onMudou?: () => void;
}) {
  const [r, setR] = useState<ResumoFinanceiroAg | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aberto, setAberto] = useState<Aberto>(null);
  const [cands, setCands] = useState<PagamentoCandidato[] | null>(null);
  const [carregandoC, setCarregandoC] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const carregar = useCallback(() => { fetchFinanceiroAgendamento(cronogramaId).then((d) => { setR(d); setErro(null); }).catch((e) => setErro(e.message || "Erro ao carregar o financeiro")); }, [cronogramaId]);
  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => {
    if (aberto !== "pagamento") return;
    setCarregandoC(true);
    fetchPagamentosCandidatos(cronogramaId).then((d) => setCands(d.pagamentos)).catch(() => setCands([])).finally(() => setCarregandoC(false));
  }, [aberto, cronogramaId]);

  async function executar(fn: () => Promise<ResumoFinanceiroAg | { resumo: ResumoFinanceiroAg }>, msg: string) {
    setOcupado(true); setErro(null); setOkMsg(null);
    try {
      const x: any = await fn();
      setR(x.resumo || x); setAberto(null); setOkMsg(msg); onMudou?.();
    } catch (e: any) { setErro(e.message || "Erro"); } finally { setOcupado(false); }
  }

  if (!r) return erro ? <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p> : <p style={notaStyle}>Carregando o financeiro…</p>;
  const nec = r.necessidade;
  const un = nec.unidade_estoque || nec.unidade || "";
  const compras = r.vinculos.filter((v) => v.tipo === "cotacao" || v.tipo === "pedido");
  const pagamentos = r.vinculos.filter((v) => v.tipo === "pagamento");
  const contas = r.vinculos.filter((v) => v.tipo === "conta");
  const encerrar = (v: VinculoAg, m: string) => executar(
    () => encerrarVinculoAgendamento(cronogramaId, v.id, v.tipo === "conta" ? "cancelar_conta" : v.tipo === "pagamento" ? "desvincular_pagamento" : "cancelar_cotacao", m),
    v.tipo === "conta" ? "Conta cancelada: saiu de Contas a pagar." : v.tipo === "pagamento" ? "Pagamento desvinculado (o lançamento continua no Financeiro)." : "Cotação cancelada.",
  );
  const compraOk = r.compra.estado === "ok";
  const finItemId = r.financeiro_item_id;

  return (
    <section aria-label="Financeiro do agendamento" style={{ display: "flex", flexDirection: "column" }}>
      <div className="card" style={{ padding: "0.6rem 0.9rem", marginBottom: "0.4rem" }}>
        <ResumoCustoFinanceiro bloco={r} />
      </div>
      {okMsg && <p role="status" style={{ color: "var(--green-light)", fontSize: "0.85rem", display: "flex", gap: 6, alignItems: "center", margin: "0.3rem 0" }}><Check size={14} />{okMsg}</p>}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem", margin: "0.3rem 0" }}>{erro}</p>}

      {/* Compra */}
      <Linha icone={<ShoppingCart size={16} />} titulo="Comunicação de compra/cotação" estado={r.compra.estado}
        acoes={!readOnly && aberto !== "compra" && (
          <>
            <button type="button" className={r.compra.estado === "pendente" ? "btn-primary" : "btn-ghost"} onClick={() => setAberto("compra")}><ShoppingCart size={14} /> {compraOk || r.compra.estado === "nao_necessaria" ? "Comunicar reposição" : "Comunicar compra"}</button>
            {r.compra.estado === "pendente" && <button type="button" className="btn-secondary" disabled={ocupado} onClick={() => executar(() => comunicarCompraAgendamento(cronogramaId, { modo: "ja_comprei" }), "Marcado: já comprei.")}><Check size={14} /> Já comprei</button>}
          </>
        )}>
        <p style={{ ...notaStyle, margin: 0 }}>
          {r.compra.estado === "nao_necessaria"
            ? (nec.estoque_desconsiderado ? "Não necessária: o estoque foi desconsiderado (frasco de fora)." : `Não necessária: o estoque cobre (saldo ${num(nec.saldo ?? 0)} ${un} para ${num(nec.precisa)} ${un}).`)
            : r.compra.estado === "ok" && !compras.length ? "Marcado como já comprado, sem cotação nem pedido no sistema."
            : <>Precisa de {num(nec.precisa)} {un} · saldo {nec.saldo == null ? "—" : `${num(nec.saldo)} ${un}`}{nec.falta > 0 ? <b style={{ color: "var(--amber)" }}> · faltam {num(nec.falta)} {un}</b> : ""}.</>}
        </p>
        {compras.map((v) => <VinculoLinha key={v.id} v={v} readOnly={!!readOnly} ocupado={ocupado} onEncerrar={v.tipo === "cotacao" ? encerrar : undefined} />)}
        {aberto === "compra" && (
          <FormCompra nec={nec} dataEvento={dataEvento} salvando={ocupado} rotuloBotao="Criar"
                      onCancelar={() => setAberto(null)}
                      onSubmit={(p) => executar(() => comunicarCompraAgendamento(cronogramaId, p), p.modo === "pedido" ? "Pedido criado em Pedidos." : p.disparar ? "Cotação enviada aos fornecedores." : "Cotação criada em rascunho, em Cotações.")} />
        )}
      </Linha>

      {/* Pagamento já realizado */}
      <Linha icone={<Wallet size={16} />} titulo="Pagamento já realizado" estado={r.pagamento.estado}
        acoes={!readOnly && aberto !== "pagamento" && (
          <button type="button" className={r.pagamento.estado === "pendente" ? "btn-primary" : "btn-ghost"} onClick={() => setAberto("pagamento")}><Link2 size={14} /> Vincular pagamento já realizado</button>
        )}>
        {!pagamentos.length && <p style={{ ...notaStyle, margin: 0 }}>Vincule a compra do produto que já foi paga, sem duplicar lançamento.</p>}
        {pagamentos.map((v) => <VinculoLinha key={v.id} v={v} readOnly={!!readOnly} ocupado={ocupado} onEncerrar={encerrar} />)}
        {aberto === "pagamento" && (
          <FormPagamento nec={nec} candidatos={cands} carregando={carregandoC} salvando={ocupado} rotuloBotao="Vincular"
                         onCancelar={() => setAberto(null)} onLancarConta={() => setAberto("conta")}
                         onSubmit={(id, modo) => executar(() => vincularPagamentoAgendamento(cronogramaId, id, modo), "Pagamento vinculado, sem duplicar o lançamento.")} />
        )}
      </Linha>

      {/* Conta a pagar */}
      <Linha icone={<Receipt size={16} />} titulo="Conta a pagar decorrente" estado={r.conta_pagar.estado}
        acoes={!readOnly && aberto !== "conta" && (
          <>
            <button type="button" className={r.conta_pagar.estado === "pendente" ? "btn-primary" : "btn-ghost"} onClick={() => setAberto("conta")}><Receipt size={14} /> {contas.some((c) => c.estado === "ativo") ? "Lançar outra conta" : "Lançar conta a pagar"}</button>
            {r.pagamento.estado === "pendente" && r.conta_pagar.estado === "pendente" && r.financeiro_item_id != null && (
              <button type="button" className="btn-ghost" onClick={() => setAberto("desconsiderar")}><SkipForward size={14} /> Desconsiderar o financeiro</button>
            )}
          </>
        )}>
        {!contas.length && <p style={{ ...notaStyle, margin: 0 }}>Honorário do veterinário e produtos: lance a conta a pagar deste protocolo.</p>}
        {contas.map((v) => <VinculoLinha key={v.id} v={v} readOnly={!!readOnly} ocupado={ocupado} onEncerrar={encerrar} />)}
        {aberto === "conta" && (
          <FormConta nec={nec} dataEvento={dataEvento} vetNome={vetNome} salvando={ocupado} rotuloBotao="Salvar e vincular"
                     onCancelar={() => setAberto(null)}
                     onSubmit={(p) => executar(() => lancarContaPagarAgendamento(cronogramaId, p), "Conta a pagar lançada em Financeiro.")} />
        )}
        {aberto === "desconsiderar" && finItemId != null && (
          <EncerrarInline opcoes={MOTIVOS_DESCONSIDERAR_FIN} rotulo="Desconsiderar" ocupado={ocupado} onVoltar={() => setAberto(null)}
                          onConfirmar={(m) => executar(async () => { await editarChecklistAgendamento(cronogramaId, { itens: [{ item_id: finItemId, acao: "pular", motivo: m }] }); return await fetchFinanceiroAgendamento(cronogramaId); }, "Financeiro desconsiderado.")} />
        )}
      </Linha>
      <p style={{ ...notaStyle, marginTop: "0.5rem" }}>Nada aqui bloqueia o agendamento nem a aplicação. Cada ação fica no Histórico, com quem fez e quando.</p>
    </section>
  );
}

// ─────────────────────────── modo RASCUNHO (assistente Criar agendamento) ───────────────────────────
export function FinanceiroRascunho({ calendarioId, animais, dataEvento, vetNome, draft, onChange }: {
  calendarioId: number; animais: string[]; dataEvento: string; vetNome: string | null; draft: FinanceiroDraft; onChange: (d: FinanceiroDraft) => void;
}) {
  const [previa, setPrevia] = useState<{ necessidade: NecessidadeInsumo; pagamentos: PagamentoCandidato[] } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aberto, setAberto] = useState<Aberto>(null);
  const chave = useMemo(() => animais.join(","), [animais]);
  useEffect(() => {
    let vivo = true;
    fetchPreviaFinanceiro(calendarioId, animais).then((d) => { if (vivo) { setPrevia(d); setErro(null); } }).catch((e) => { if (vivo) setErro(e.message || "Erro ao calcular a necessidade"); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calendarioId, chave]);
  if (!previa) return erro ? <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p> : <p style={notaStyle}>Calculando a necessidade do insumo…</p>;
  const nec = previa.necessidade;
  const un = nec.unidade_estoque || nec.unidade || "";
  const set = (p: Partial<FinanceiroDraft>) => onChange({ ...draft, ...p });
  const compraEstado: EstadoItemFin = draft.compra ? "ok" : nec.cobre || nec.estoque_desconsiderado ? "nao_necessaria" : "pendente";
  return (
    <section aria-label="Financeiro do agendamento" style={{ display: "flex", flexDirection: "column" }}>
      <div className="card" style={{ padding: "0.6rem 0.9rem", marginBottom: "0.4rem", fontSize: "0.84rem" }}>
        <b>Custo previsto:</b> {nec.custo_previsto != null ? <b>{brl(nec.custo_previsto)}</b> : <span style={{ color: "var(--amber)", fontWeight: 700 }}>a informar</span>}
        {nec.custo_previsto != null ? <span style={notaStyle}> · {num(nec.precisa)} {nec.unidade || ""} × {brl(nec.preco_unitario)}</span> : nec.custo_motivo ? <span style={notaStyle}> · {nec.custo_motivo}</span> : null}
        <span style={{ ...notaStyle, display: "block" }}>{nec.animais} {plural(nec.animais, "animal", "animais")} · saldo {nec.saldo == null ? "—" : `${num(nec.saldo)} ${un}`}{nec.falta > 0 ? ` · faltam ${num(nec.falta)} ${un}` : ""}</span>
      </div>

      <Linha icone={<ShoppingCart size={16} />} titulo="Comunicação de compra/cotação" estado={compraEstado}
        acoes={aberto !== "compra" && (
          <>
            <button type="button" className={compraEstado === "pendente" ? "btn-primary" : "btn-ghost"} onClick={() => setAberto("compra")}><ShoppingCart size={14} /> {draft.compra ? "Trocar" : compraEstado === "nao_necessaria" ? "Comunicar reposição" : "Comunicar compra"}</button>
            {!draft.compra && compraEstado === "pendente" && <button type="button" className="btn-secondary" onClick={() => set({ compra: { modo: "ja_comprei", rotulo: "Já comprei" } })}><Check size={14} /> Já comprei</button>}
            {draft.compra && <button type="button" className="btn-ghost" onClick={() => set({ compra: null })}><X size={14} /> Tirar</button>}
          </>
        )}>
        <p style={{ ...notaStyle, margin: 0 }}>
          {draft.compra ? <>Ao criar o agendamento: <b>{draft.compra.rotulo}</b>{draft.compra.quantidade ? ` · ${num(draft.compra.quantidade)} ${un}` : ""}.</>
            : compraEstado === "nao_necessaria" ? (nec.estoque_desconsiderado ? "Não necessária: o estoque foi desconsiderado." : `Não necessária: o estoque cobre (saldo ${num(nec.saldo ?? 0)} ${un}).`)
            : <>Precisa de {num(nec.precisa)} {un} · saldo {nec.saldo == null ? "—" : `${num(nec.saldo)} ${un}`}<b style={{ color: "var(--amber)" }}>{nec.falta > 0 ? ` · faltam ${num(nec.falta)} ${un}` : ""}</b>.</>}
        </p>
        {aberto === "compra" && (
          <FormCompra nec={nec} dataEvento={dataEvento} rotuloBotao="Usar esta compra" onCancelar={() => setAberto(null)}
                      onSubmit={(p, rotulo) => { set({ compra: { ...p, rotulo } }); setAberto(null); }} />
        )}
      </Linha>

      <Linha icone={<Wallet size={16} />} titulo="Pagamento já realizado" estado={draft.pagamento ? "ok" : "pendente"}
        acoes={aberto !== "pagamento" && (
          <>
            <button type="button" className={draft.pagamento ? "btn-ghost" : "btn-primary"} onClick={() => setAberto("pagamento")}><Link2 size={14} /> {draft.pagamento ? "Trocar pagamento" : "Vincular pagamento já realizado"}</button>
            {draft.pagamento && <button type="button" className="btn-ghost" onClick={() => set({ pagamento: null })}><X size={14} /> Tirar</button>}
          </>
        )}>
        <p style={{ ...notaStyle, margin: 0 }}>{draft.pagamento ? <>Ao criar o agendamento: vincular <b>{draft.pagamento.rotulo}</b>{draft.pagamento.valor != null ? ` (${brl(draft.pagamento.valor)})` : ""}.</> : "Vincule a compra do produto que já foi paga, sem duplicar lançamento."}</p>
        {aberto === "pagamento" && (
          <FormPagamento nec={nec} candidatos={previa.pagamentos} carregando={false} rotuloBotao="Usar este pagamento" onCancelar={() => setAberto(null)} onLancarConta={() => setAberto("conta")}
                         onSubmit={(id, modo, c) => { const prop = c.proporcional; const valor = modo === "inteiro" || prop == null ? c.resta : Math.min(prop, c.resta); set({ pagamento: { pagamento_id: id, modo, rotulo: `${c.fornecedor || "Pagamento"} · ${dataCurta(c.data_pagamento)} · ${brl(c.valor)}`, valor } }); setAberto(null); }} />
        )}
      </Linha>

      <Linha icone={<Receipt size={16} />} titulo="Conta a pagar decorrente" estado={draft.contas.length ? "ok" : "pendente"}
        acoes={aberto !== "conta" && <button type="button" className={draft.contas.length ? "btn-ghost" : "btn-primary"} onClick={() => setAberto("conta")}><Receipt size={14} /> {draft.contas.length ? "Lançar outra conta" : "Lançar conta a pagar"}</button>}>
        {!draft.contas.length && <p style={{ ...notaStyle, margin: 0 }}>Honorário do veterinário e produtos: lance a conta a pagar deste protocolo.</p>}
        {draft.contas.map((c, i) => (
          <div key={i} style={{ display: "flex", gap: "0.5rem", alignItems: "center", fontSize: "0.85rem", flexWrap: "wrap" }}>
            <span style={{ flex: "1 1 240px" }}>Ao criar o agendamento: lançar <b>{c.subtipo === "honorario" ? "honorário" : "produtos"}</b> · {c.rotulo}</span>
            <button type="button" className="btn-ghost" aria-label={`Tirar a conta ${i + 1}`} onClick={() => set({ contas: draft.contas.filter((_, j) => j !== i) })}><X size={13} /> Tirar</button>
          </div>
        ))}
        {aberto === "conta" && (
          <FormConta nec={nec} dataEvento={dataEvento} vetNome={vetNome} rotuloBotao="Usar esta conta" onCancelar={() => setAberto(null)}
                     onSubmit={(p, rotulo) => { set({ contas: [...draft.contas, { ...p, rotulo }] }); setAberto(null); }} />
        )}
      </Linha>
      <p style={{ ...notaStyle, marginTop: "0.5rem" }}>As escolhas daqui só viram cotação, vínculo ou conta a pagar quando você criar o agendamento. Nada bloqueia.</p>
    </section>
  );
}

// ─────────────────────────── Conferir (passo 4 do assistente) ───────────────────────────
/** Custo previsto e o que vai acontecer no financeiro ao criar o agendamento. */
export function ConferirFinanceiro({ calendarioId, animais, draft }: { calendarioId: number; animais: string[]; draft: FinanceiroDraft }) {
  const [nec, setNec] = useState<NecessidadeInsumo | null>(null);
  const chave = animais.join(",");
  useEffect(() => {
    let vivo = true;
    fetchPreviaFinanceiro(calendarioId, animais).then((d) => { if (vivo) setNec(d.necessidade); }).catch(() => { if (vivo) setNec(null); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calendarioId, chave]);
  const un = nec?.unidade_estoque || nec?.unidade || "";
  return (
    <div className="card mb-3" aria-label="Custo e financeiro">
      <h3 className="card-header mb-2">Custo e financeiro</h3>
      <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.85rem", lineHeight: 1.7 }}>
        <li>
          <b>Custo previsto:</b>{" "}
          {!nec ? "calculando…" : nec.custo_previsto != null ? <><b>{brl(nec.custo_previsto)}</b> ({num(nec.precisa)} {nec.unidade || ""} × {brl(nec.preco_unitario)})</>
            : <><b style={{ color: "var(--amber)" }}>a informar</b>{nec.custo_motivo ? ` · ${nec.custo_motivo}` : ""}</>}
        </li>
        {nec && <li>Estoque: saldo {nec.saldo == null ? "—" : `${num(nec.saldo)} ${un}`} para {num(nec.precisa)} {un}{nec.falta > 0 ? <b style={{ color: "var(--amber)" }}> · faltam {num(nec.falta)} {un}</b> : " · cobre"}.</li>}
        <li>Compra: {draft.compra ? draft.compra.rotulo : nec && (nec.cobre || nec.estoque_desconsiderado) ? "não necessária" : "pendente (resolva no Acompanhamento)"}.</li>
        <li>Pagamento já realizado: {draft.pagamento ? `vincular ${draft.pagamento.rotulo}${draft.pagamento.valor != null ? ` (${brl(draft.pagamento.valor)})` : ""}` : "nenhum vinculado"}.</li>
        <li>Conta a pagar: {draft.contas.length ? draft.contas.map((c) => `${c.subtipo === "honorario" ? "honorário" : "produtos"} · ${c.rotulo}`).join("; ") : "nenhuma a lançar"}.</li>
      </ul>
      <a href="/financeiro" className="lnk" style={{ color: "var(--dourado-light)", textDecoration: "underline", display: "inline-flex", alignItems: "center", gap: 4, fontSize: "0.82rem", marginTop: "0.4rem" }}>
        <ExternalLink size={12} />Ver contas a pagar
      </a>
    </div>
  );
}
