"use client";
// Caixa dos funcionários — Fase 1 (caixa individual). Controle Financeiro > Ações.
// Saldo a favor de cada colaborador (CLT, empreita, contrato, diária): a fazenda
// lança entradas (depósito, bonificação, comissão, outro), registra retiradas com
// recibo e corrige por estorno. Só administrador.
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Receipt, Undo2, Trash2, Plus, Wallet, ShieldCheck, Pause, Play, Ban } from "lucide-react";
import { Modal } from "@/components/Modal";
import { CampoMoeda } from "@/components/CampoMoeda";
import { Dropzone } from "@/components/Dropzone";
import CaixaTimesView from "@/components/CaixaTimesView";
import { ReciboModal } from "@/components/ReciboModal";
import {
  fetchCaixasFuncionarios, fetchCaixaFuncionario, lancarEntradaCaixa, registrarRetiradaCaixa, fetchReciboCaixa,
  estornarMovimentoCaixa, excluirMovimentoCaixa, fetchOpcoesFinanceiro,
  fetchExtratoCaixa, fetchRetencaoCaixa, fetchRetencoesCaixa, salvarRetencaoCaixa, pausarRetencaoCaixa, revogarRetencaoCaixa, anexarArquivoPessoa,
  formatBRL, formatDate, ehAdmin,
  type CaixaPessoaLinha, type CaixaDetalhe, type CaixaMovimentoItem, type CaixaGrupo, type CaixaRecibo,
  type CaixaRetencaoDados,
} from "@/lib/api";
import { exportarFichaPDF, type LancamentoRecibo } from "@/lib/export";

const GRUPOS: { id: CaixaGrupo | "todos"; label: string }[] = [
  { id: "todos", label: "Todos" }, { id: "clt", label: "CLT" }, { id: "empreita", label: "Empreita" },
  { id: "contrato", label: "Contrato" }, { id: "diaria", label: "Diária" },
];
const ROTULO_GRUPO: Record<string, string> = { clt: "CLT", empreita: "Empreita", contrato: "Contrato", diaria: "Diária" };
const TIPOS_ENTRADA: { id: string; label: string }[] = [
  { id: "deposito", label: "Depósito da fazenda" }, { id: "bonificacao", label: "Bonificação por produtividade" },
  { id: "comissao", label: "Comissão" }, { id: "outro", label: "Outro tipo (sem especificar)" },
];
const ROTULO_TIPO: Record<string, string> = {
  deposito: "Depósito", bonificacao: "Bonificação", comissao: "Comissão", outro: "Outro", retirada: "Retirada", estorno: "Estorno", retencao: "Retenção na folha", rateio: "Rateio do PL",
};
const FORMAS = [
  { id: "pix", label: "Pix" }, { id: "dinheiro", label: "Dinheiro" }, { id: "transferencia", label: "Transferência" },
  { id: "debito", label: "Débito" }, { id: "credito", label: "Crédito" }, { id: "boleto", label: "Boleto" },
];

const lbl = { display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem" } as const;
const campo = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.82rem",
} as const;
const hojeISO = () => new Date().toISOString().slice(0, 10);
const CATEGORIA_TERMO = "Termo de retenção do caixa";

function resumoRetencao(d?: CaixaRetencaoDados) {
  const c = d?.config;
  if (!c) return "—";
  const v = c.forma === "percentual" ? `${c.valor}%` : formatBRL(c.valor);
  const estado = !c.autorizada ? "sem autorização" : c.revogada_em ? "revogada" : c.pausada ? "pausada" : "ativa";
  return `${v}/mês · ${estado}`;
}

function rotuloGrupos(grupos: string[]) { return grupos.map((g) => ROTULO_GRUPO[g] || g).join(", ") || "—"; }

export default function CaixaFuncionariosView() {
  const admin = ehAdmin();
  const [linhas, setLinhas] = useState<CaixaPessoaLinha[] | null>(null);
  const [totalDevido, setTotalDevido] = useState(0);
  const [erro, setErro] = useState<string | null>(null);
  const [grupo, setGrupo] = useState<CaixaGrupo | "todos">("todos");
  const [soComSaldo, setSoComSaldo] = useState(false);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [pessoaAberta, setPessoaAberta] = useState<number | null>(null);
  const [entrada, setEntrada] = useState<{ pessoaIds: number[] } | null>(null);
  const [aba, setAba] = useState<"individual" | "time">("individual");
  const [retencoes, setRetencoes] = useState<Record<number, CaixaRetencaoDados>>({});

  const carregar = () => {
    fetchRetencoesCaixa().then((d) => setRetencoes(Object.fromEntries(d.retencoes.map((r) => [r.pessoa.id, r])))).catch(() => {});
    return fetchCaixasFuncionarios()
      .then((d) => { setLinhas(d.pessoas); setTotalDevido(d.total_devido); setErro(null); })
      .catch((e) => setErro(e.message));
  };
  useEffect(() => { carregar(); }, []);

  const visiveis = useMemo(() => (linhas || []).filter((l) =>
    (grupo === "todos" || l.grupos.includes(grupo)) && (!soComSaldo || l.saldo > 0)), [linhas, grupo, soComSaldo]);

  if (!admin) return <p style={{ color: "var(--text-muted)" }}>O caixa dos funcionários é restrito ao administrador.</p>;

  if (pessoaAberta != null) {
    return <CaixaIndividual pessoaId={pessoaAberta} onVoltar={() => { setPessoaAberta(null); carregar(); }} onEntrada={() => setEntrada({ pessoaIds: [pessoaAberta] })} />;
  }

  const alternar = (id: number) => setSelecionados((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const todosVisiveisMarcados = visiveis.length > 0 && visiveis.every((l) => selecionados.has(l.pessoa_id));

  return (
    <div>
      <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.6rem", marginBottom: "0.8rem" }}>
        <div>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Controle Financeiro · Ações</div>
          <h2 style={{ margin: 0, fontSize: "1.05rem" }}>Caixa dos funcionários</h2>
        </div>
        <button type="button" className="btn-primary" onClick={() => setEntrada({ pessoaIds: Array.from(selecionados) })}>
          <Plus size={14} /> Lançar entrada
        </button>
      </div>
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", maxWidth: "75ch", marginBottom: "0.8rem" }}>
        Saldo a favor de cada colaborador, que a fazenda guarda para ele. A entrada vira despesa de pessoal no Financeiro; a retirada
        gera recibo. Erro se corrige por estorno.
      </p>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}

      <div className="flex" style={{ gap: "0.4rem", marginBottom: "0.8rem" }} role="tablist">
        {([["individual", "Caixas individuais"], ["time", "Caixas do time (PL)"]] as const).map(([id, rot]) => (
          <button key={id} type="button" role="tab" aria-selected={aba === id} onClick={() => setAba(id)}
            style={{ padding: "0.25rem 0.9rem", borderRadius: 999, fontSize: "0.8rem", cursor: "pointer",
              border: `1px solid ${aba === id ? "var(--dourado)" : "var(--border)"}`, background: aba === id ? "var(--dourado)" : "var(--surface)",
              color: aba === id ? "var(--vinho-dark, #0A1F36)" : "var(--text-muted)" }}>{rot}</button>
        ))}
      </div>
      {aba === "time" ? <CaixaTimesView /> : (<>
      <div className="card" style={{ display: "inline-block", marginBottom: "0.8rem", padding: "0.6rem 0.9rem" }}>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Devido aos funcionários</div>
        <strong style={{ fontSize: "1.15rem" }}>{formatBRL(totalDevido)}</strong>
      </div>

      <div className="flex" style={{ gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.7rem", alignItems: "center" }}>
        {GRUPOS.map((g) => (
          <button key={g.id} type="button" aria-pressed={grupo === g.id} onClick={() => setGrupo(g.id)}
            style={{ padding: "0.2rem 0.75rem", borderRadius: 999, fontSize: "0.78rem", cursor: "pointer",
              border: `1px solid ${grupo === g.id ? "var(--dourado)" : "var(--border)"}`,
              background: grupo === g.id ? "var(--dourado)" : "var(--surface)",
              color: grupo === g.id ? "var(--vinho-dark, #0A1F36)" : "var(--text-muted)" }}>{g.label}</button>
        ))}
        <label style={{ display: "flex", gap: "0.3rem", alignItems: "center", fontSize: "0.78rem", color: "var(--text-muted)", margin: 0 }}>
          <input type="checkbox" checked={soComSaldo} onChange={(e) => setSoComSaldo(e.target.checked)} /> Só com saldo
        </label>
      </div>

      {selecionados.size > 0 && (
        <div className="card" style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", padding: "0.5rem 0.8rem", marginBottom: "0.7rem", border: "1px solid var(--dourado)" }}>
          <span style={{ fontSize: "0.82rem" }}><b>{selecionados.size}</b> selecionado{selecionados.size > 1 ? "s" : ""}</span>
          <button type="button" className="btn-primary" style={{ fontSize: "0.78rem" }} onClick={() => setEntrada({ pessoaIds: Array.from(selecionados) })}>Depositar para selecionados</button>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={() => setSelecionados(new Set())}>Limpar seleção</button>
        </div>
      )}

      {linhas === null ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : (
        <div style={{ overflowX: "auto" }}>
          <table className="fazenda-table" style={{ minWidth: 640 }}>
            <thead>
              <tr>
                <th style={{ width: 28 }}><input type="checkbox" aria-label="Selecionar todos os visíveis" checked={todosVisiveisMarcados}
                  onChange={() => setSelecionados(todosVisiveisMarcados ? new Set() : new Set(visiveis.map((l) => l.pessoa_id)))} /></th>
                <th>Pessoa</th><th>Tipo</th><th style={{ textAlign: "right" }}>Saldo</th><th>Retenção na folha</th><th>Termo</th><th>Último movimento</th><th></th>
              </tr>
            </thead>
            <tbody>
              {visiveis.map((l) => (
                <tr key={l.pessoa_id}>
                  <td><input type="checkbox" aria-label={`Selecionar ${l.nome}`} checked={selecionados.has(l.pessoa_id)} onChange={() => alternar(l.pessoa_id)} /></td>
                  <td>{l.nome}</td>
                  <td style={{ color: "var(--text-muted)" }}>{rotuloGrupos(l.grupos)}</td>
                  <td style={{ textAlign: "right", fontWeight: 700 }}>{formatBRL(l.saldo)}</td>
                  <td style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>{resumoRetencao(retencoes[l.pessoa_id])}</td>
                  <td style={{ fontSize: "0.78rem", color: retencoes[l.pessoa_id]?.termo_pendente ? "var(--amber)" : "var(--text-muted)" }}>
                    {!retencoes[l.pessoa_id]?.config ? "—" : retencoes[l.pessoa_id].termo_anexado ? "anexado" : retencoes[l.pessoa_id].termo_pendente ? "pendente" : "—"}
                  </td>
                  <td style={{ color: "var(--text-muted)" }}>{l.ultimo_movimento ? formatDate(l.ultimo_movimento) : "—"}</td>
                  <td style={{ textAlign: "right" }}><button type="button" className="btn-primary" style={{ fontSize: "0.72rem", padding: "0.15rem 0.6rem" }} onClick={() => setPessoaAberta(l.pessoa_id)}>Abrir caixa</button></td>
                </tr>
              ))}
              {!visiveis.length && <tr><td colSpan={8} style={{ color: "var(--text-muted)" }}>Nenhum colaborador neste filtro. O caixa vale para CLT, empreita, contrato e diária cadastrados em Pessoas.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {entrada && (
        <EntradaModal
          pessoas={linhas || []} inicial={entrada.pessoaIds} onClose={() => setEntrada(null)}
          onFeito={() => { setEntrada(null); setSelecionados(new Set()); carregar(); }} />
      )}
      </>)}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Caixa de uma pessoa: saldo, extrato, estorno/exclusão, retirada e recibo.
// ---------------------------------------------------------------------------
function CaixaIndividual({ pessoaId, onVoltar, onEntrada }: { pessoaId: number; onVoltar: () => void; onEntrada: () => void }) {
  const [det, setDet] = useState<CaixaDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [retirando, setRetirando] = useState(false);
  const [estornando, setEstornando] = useState<CaixaMovimentoItem | null>(null);
  const [recibo, setRecibo] = useState<LancamentoRecibo | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregar = () => fetchCaixaFuncionario(pessoaId).then((d) => { setDet(d); setErro(null); }).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, [pessoaId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function abrirRecibo(m: CaixaMovimentoItem) {
    try { setRecibo(reciboDe(await fetchReciboCaixa(pessoaId, m.id))); }
    catch (e: any) { setErro(e.message); }
  }
  async function extratoPdf() {
    const mes = window.prompt("Mês do extrato (AAAA-MM):", hojeISO().slice(0, 7));
    if (!mes) return;
    try {
      const e = await fetchExtratoCaixa(pessoaId, mes.trim());
      const linhas: Record<string, unknown>[] = [{ data: "", descricao: "Saldo anterior", valor: "", saldo: formatBRL(e.saldo_anterior) }];
      let corrente = e.saldo_anterior;
      for (const m of e.movimentos) {
        corrente = Math.round((corrente + m.valor) * 100) / 100;
        linhas.push({ data: formatDate(m.data), descricao: `${ROTULO_TIPO[m.tipo] || m.tipo} · ${m.motivo}${m.estornado ? " (estornado)" : ""}`,
          valor: `${m.valor >= 0 ? "+" : "−"} ${formatBRL(Math.abs(m.valor))}`, saldo: formatBRL(corrente) });
      }
      linhas.push({ data: "", descricao: "Saldo final do mês", valor: "", saldo: formatBRL(e.saldo_final) });
      for (const t of e.times) linhas.push({ data: "", descricao: `Caixa do time ${t.time}: sua parte estimada (de ${formatBRL(t.saldo)} no caixa)`, valor: "", saldo: formatBRL(t.parte_estimada) });
      await exportarFichaPDF("Extrato do caixa do funcionário", `${e.pessoa.nome} — ${e.mes}`, [{
        titulo: `${e.pessoa.nome} — ${e.mes}`,
        colunas: [{ header: "Data", key: "data" }, { header: "Movimento", key: "descricao" }, { header: "Valor", key: "valor" }, { header: "Saldo", key: "saldo" }],
        linhas,
      }], `extrato_caixa_${e.pessoa.nome}_${e.mes}`.replace(/[^\w-]+/g, "_").toLowerCase());
    } catch (err: any) { setErro(err.message); }
  }
  async function excluir(m: CaixaMovimentoItem) {
    if (!window.confirm("Excluir este movimento? Só é possível por ser o último e não ter sido usado. Isto não pode ser desfeito.")) return;
    try { await excluirMovimentoCaixa(pessoaId, m.id); await carregar(); }
    catch (e: any) { setErro(e.message); }
  }

  if (!det) return <div>{erro ? <p role="alert" style={{ color: "var(--red)" }}>{erro}</p> : <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}<button type="button" className="btn-ghost" onClick={onVoltar}>Voltar</button></div>;

  return (
    <div>
      <button type="button" className="btn-ghost" onClick={onVoltar} style={{ marginBottom: "0.5rem", fontSize: "0.78rem" }}><ArrowLeft size={13} /> Todos os caixas</button>
      <div className="flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.6rem", marginBottom: "0.8rem" }}>
        <div>
          <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>Caixa dos funcionários · {rotuloGrupos(det.pessoa.grupos)}</div>
          <h2 style={{ margin: 0, fontSize: "1.05rem" }}>{det.pessoa.nome}</h2>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-primary" onClick={onEntrada}><Plus size={14} /> Entrada</button>
          <button type="button" className="btn-ghost" onClick={() => setRetirando(true)} disabled={det.saldo <= 0}><Wallet size={14} /> Retirada</button>
          <button type="button" className="btn-ghost" onClick={extratoPdf}><Receipt size={14} /> Extrato PDF</button>
        </div>
      </div>
      <div className="card" style={{ display: "inline-block", padding: "0.6rem 0.9rem", marginBottom: "0.8rem" }}>
        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Saldo individual ({rotuloGrupos(det.pessoa.grupos)})</div>
        <strong style={{ fontSize: "1.15rem" }}>{formatBRL(det.saldo)}</strong>
      </div>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.82rem" }}>{erro}</p>}
      {aviso && <p style={{ color: "var(--green-light, #3ecf8e)", fontSize: "0.82rem" }}>{aviso}</p>}

      <RetencaoPainel pessoaId={pessoaId} onMudou={carregar} />

      <div style={{ overflowX: "auto" }}>
        <table className="fazenda-table" style={{ minWidth: 720 }}>
          <thead><tr><th>Data</th><th>Tipo</th><th>Motivo</th><th style={{ textAlign: "right" }}>Valor</th><th style={{ textAlign: "right" }}>Saldo</th><th>Lançamento</th><th></th></tr></thead>
          <tbody>
            {det.movimentos.map((m) => {
              const cor = m.estornado ? "var(--text-muted)" : m.valor >= 0 ? "var(--green-light, #3ecf8e)" : "var(--red)";
              const riscado = m.estornado ? { textDecoration: "line-through", color: "var(--text-muted)" } : {};
              return (
                <tr key={m.id}>
                  <td style={riscado}>{formatDate(m.data)}</td>
                  <td style={riscado}>{ROTULO_TIPO[m.tipo] || m.tipo}{m.estornado && <span style={{ marginLeft: 6, fontSize: "0.68rem", color: "var(--amber)", textDecoration: "none", display: "inline-block" }}>estornada</span>}</td>
                  <td style={{ ...riscado, maxWidth: 320 }}>{m.motivo}{m.forma_pagamento ? ` · ${FORMAS.find((f) => f.id === m.forma_pagamento)?.label || m.forma_pagamento}` : ""}{m.numero_documento_pagamento ? ` · comprovante ${m.numero_documento_pagamento}` : ""}</td>
                  <td style={{ textAlign: "right", color: cor, ...riscado, fontWeight: 700 }}>{m.valor >= 0 ? "+ " : "− "}{formatBRL(Math.abs(m.valor))}</td>
                  <td style={{ textAlign: "right" }}>{formatBRL(m.saldo_depois)}</td>
                  <td style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>{m.numero_lancamento || m.numero_recibo || "—"}</td>
                  <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
                    {m.tipo === "retirada" && <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => abrirRecibo(m)}><Receipt size={12} /> Recibo</button>}
                    {m.pode_estornar && <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setEstornando(m)}><Undo2 size={12} /> Estornar</button>}
                    {m.pode_excluir && <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} title="Excluir o último movimento" onClick={() => excluir(m)}><Trash2 size={12} /></button>}
                  </td>
                </tr>
              );
            })}
            {!det.movimentos.length && <tr><td colSpan={7} style={{ color: "var(--text-muted)" }}>Ainda sem movimentos. Use "Entrada" para colocar dinheiro neste caixa.</td></tr>}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Excluir só aparece no último movimento, se ninguém usou o saldo depois. O erro mais antigo se corrige por estorno.</p>

      {retirando && (
        <RetiradaModal pessoaNome={det.pessoa.nome} grupos={det.pessoa.grupos} saldo={det.saldo} pessoaId={pessoaId}
          onClose={() => setRetirando(false)}
          onFeita={(r) => { setRetirando(false); setAviso(`Retirada registrada · recibo ${r.movimento.numero_recibo}`); setRecibo(reciboDe(r)); carregar(); }} />
      )}
      {estornando && (
        <EstornoModal movimento={estornando} onClose={() => setEstornando(null)}
          onFeito={() => { setEstornando(null); setAviso("Estorno registrado."); carregar(); }} pessoaId={pessoaId} />
      )}
      {recibo && <ReciboModal lanc={recibo} onClose={() => setRecibo(null)} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Retenção na folha: combinado por pessoa, autorização interna e termo anexado.
// ---------------------------------------------------------------------------
function RetencaoPainel({ pessoaId, onMudou }: { pessoaId: number; onMudou: () => void }) {
  const [dados, setDados] = useState<CaixaRetencaoDados | null>(null);
  const [editando, setEditando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [forma, setForma] = useState<"fixo" | "percentual">("fixo");
  const [valor, setValor] = useState("");
  const [teto, setTeto] = useState("");
  const [inicio, setInicio] = useState(hojeISO().slice(0, 7) + "-01");
  const [fim, setFim] = useState("");
  const [autorizada, setAutorizada] = useState(false);

  const carregar = () => fetchRetencaoCaixa(pessoaId).then((d) => { setDados(d); setErro(null); }).catch((e) => setErro(e.message));
  useEffect(() => { carregar(); }, [pessoaId]); // eslint-disable-line react-hooks/exhaustive-deps

  function abrirEdicao() {
    const c = dados?.config;
    setForma(c?.forma || "fixo"); setValor(c ? String(c.valor) : ""); setTeto(c?.teto != null ? String(c.teto) : "");
    setInicio(c?.inicio || hojeISO().slice(0, 7) + "-01"); setFim(c?.fim || ""); setAutorizada(!!c?.autorizada);
    setEditando(true);
  }
  async function executar(fn: () => Promise<CaixaRetencaoDados>) {
    setOcupado(true); setErro(null);
    try { setDados(await fn()); onMudou(); } catch (e: any) { setErro(e.message); }
    setOcupado(false);
  }
  async function salvar() {
    if (!(Number(valor) > 0)) { setErro("Informe o valor da retenção."); return; }
    await executar(() => salvarRetencaoCaixa(pessoaId, {
      forma, valor: Number(valor), inicio, fim: fim || null, teto: teto ? Number(teto) : null, autorizada,
    }));
    setEditando(false);
  }
  async function anexarTermo(file: File) {
    setOcupado(true); setErro(null);
    try { await anexarArquivoPessoa(pessoaId, file, CATEGORIA_TERMO); await carregar(); onMudou(); }
    catch (e: any) { setErro(e.message); }
    setOcupado(false);
  }

  const c = dados?.config;
  const vigente = !!c && c.autorizada && !c.pausada && !c.revogada_em;
  return (
    <div className="card" style={{ padding: "0.7rem 0.9rem", marginBottom: "0.9rem" }}>
      <div className="flex items-center justify-between" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
        <strong style={{ fontSize: "0.88rem" }}><ShieldCheck size={14} style={{ display: "inline", marginRight: 5 }} />Retenção na folha</strong>
        <div className="flex gap-2" style={{ flexWrap: "wrap" }}>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={abrirEdicao} disabled={ocupado}>{c ? "Editar combinado" : "Combinar retenção"}</button>
          {c && c.autorizada && !c.revogada_em && (
            <>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.74rem" }} disabled={ocupado} onClick={() => executar(() => pausarRetencaoCaixa(pessoaId, !c.pausada))}>
                {c.pausada ? <><Play size={12} /> Retomar</> : <><Pause size={12} /> Pausar</>}
              </button>
              <button type="button" className="btn-ghost" style={{ fontSize: "0.74rem", color: "var(--red)" }} disabled={ocupado}
                onClick={() => { if (window.confirm("Revogar a autorização? Vale a partir do mês seguinte; o que já foi retido continua no caixa.")) executar(() => revogarRetencaoCaixa(pessoaId)); }}>
                <Ban size={12} /> Revogar
              </button>
            </>
          )}
        </div>
      </div>
      {!c ? (
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", margin: "0.4rem 0 0" }}>Sem retenção combinada. A folha só retém com valor combinado, autorização marcada e vigência aberta.</p>
      ) : (
        <p style={{ fontSize: "0.8rem", margin: "0.4rem 0 0" }}>
          {c.forma === "percentual" ? `${c.valor}% do salário-base` : `${formatBRL(c.valor)} por mês`}
          {c.teto != null ? ` · teto ${formatBRL(c.teto)}` : ""} · desde {formatDate(c.inicio)}{c.fim ? ` até ${formatDate(c.fim)}` : ""}
          {" · "}<b style={{ color: vigente ? "var(--green-light, #3ecf8e)" : "var(--amber)" }}>
            {!c.autorizada ? "sem autorização" : c.revogada_em ? `revogada (vale até ${formatDate(c.revogada_em)})` : c.pausada ? "pausada" : "ativa"}
          </b>
          {" · "}já retido {formatBRL(dados?.acumulado || 0)}
        </p>
      )}
      {c && c.autorizada && (
        <div style={{ marginTop: "0.5rem" }}>
          {dados?.termo_anexado ? (
            <p style={{ fontSize: "0.78rem", color: "var(--green-light, #3ecf8e)", margin: 0 }}>Termo de autorização anexado (documentos da pessoa).</p>
          ) : (
            <>
              <p style={{ fontSize: "0.78rem", color: "var(--amber)", margin: "0 0 0.35rem" }}>Termo pendente: anexe o documento assinado. Enquanto isso, a pendência aparece na Agenda e no Fechamento da folha.</p>
              <Dropzone accept="application/pdf,image/jpeg,image/png" label="Arraste o termo assinado ou clique para selecionar" hint="PDF, JPG ou PNG" onFiles={(f) => f[0] && anexarTermo(f[0])} />
            </>
          )}
        </div>
      )}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.78rem", margin: "0.4rem 0 0" }}>{erro}</p>}

      {editando && (
        <Modal title="Combinado de retenção na folha" onClose={() => setEditando(false)} width="520px">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><label style={lbl} htmlFor="rn-forma">Forma</label>
              <select id="rn-forma" style={campo} value={forma} onChange={(e) => setForma(e.target.value as "fixo" | "percentual")}>
                <option value="fixo">Valor fixo por mês</option><option value="percentual">Percentual do salário-base</option>
              </select></div>
            <div><label style={lbl}>{forma === "percentual" ? "Percentual (%)" : "Valor por mês (R$)"}</label>
              {forma === "percentual"
                ? <input type="number" min="0" max="100" step="0.01" style={campo} value={valor} onChange={(e) => setValor(e.target.value)} />
                : <CampoMoeda style={campo} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} />}</div>
            <div><label style={lbl} htmlFor="rn-ini">Início da vigência</label><input id="rn-ini" type="date" style={campo} value={inicio} onChange={(e) => setInicio(e.target.value)} /></div>
            <div><label style={lbl} htmlFor="rn-fim">Fim (opcional)</label><input id="rn-fim" type="date" style={campo} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
            <div style={{ gridColumn: "1 / -1" }}><label style={lbl}>Teto acumulado (opcional)</label>
              <CampoMoeda style={campo} value={Number(teto) || 0} onChange={(v) => setTeto(v ? String(v) : "")} /></div>
          </div>
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", fontSize: "0.8rem", marginTop: "0.8rem", color: "var(--text)" }}>
            <input type="checkbox" checked={autorizada} onChange={(e) => setAutorizada(e.target.checked)} style={{ marginTop: 3 }} />
            <span>O colaborador autorizou esta retenção (CLT art. 462). Sem esta marca a folha não retém. O termo assinado deve ser anexado depois.</span>
          </label>
          {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
          <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "0.9rem" }}>
            <button type="button" className="btn-ghost" onClick={() => setEditando(false)} disabled={ocupado}>Cancelar</button>
            <button type="button" className="btn-primary" onClick={salvar} disabled={ocupado}>{ocupado ? "Salvando…" : "Salvar combinado"}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/** Recibo de retirada no formato do ReciboModal (PDF/e-mail), com o saldo antes e depois na descrição. */
function reciboDe(r: CaixaRecibo): LancamentoRecibo {
  return {
    numero_lancamento: r.movimento.numero_recibo, tipo: "despesa", fornecedor: r.pessoa.nome,
    descricao: `Retirada do caixa do colaborador (${r.pessoa.tipo}). Saldo anterior ${formatBRL(r.saldo_anterior)}; saldo após a retirada ${formatBRL(r.saldo_depois)}.`
      + `${r.movimento.numero_documento_pagamento ? ` Comprovante ${r.movimento.numero_documento_pagamento}.` : ""}`,
    valor: Math.abs(r.movimento.valor), valor_pago: Math.abs(r.movimento.valor),
    data_pagamento: r.movimento.data, data_vencimento: r.movimento.data,
  } as LancamentoRecibo;
}

// ---------------------------------------------------------------------------
function EntradaModal({ pessoas, inicial, onClose, onFeito }: {
  pessoas: CaixaPessoaLinha[]; inicial: number[]; onClose: () => void; onFeito: () => void;
}) {
  const [tipo, setTipo] = useState("deposito");
  const [escolhidos, setEscolhidos] = useState<Set<number>>(new Set(inicial));
  const [filtro, setFiltro] = useState<CaixaGrupo | "todos">("todos");
  const [valor, setValor] = useState("");
  const [data, setData] = useState(hojeISO());
  const [motivo, setMotivo] = useState("");
  const [base, setBase] = useState("");
  const [percentual, setPercentual] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const lista = pessoas.filter((p) => filtro === "todos" || p.grupos.includes(filtro));
  const valorCalculado = tipo === "comissao" && Number(base) > 0 && Number(percentual) > 0 ? Math.round(Number(base) * Number(percentual)) / 100 : null;
  const valorPorPessoa = valorCalculado ?? (Number(valor) || 0);
  const total = Math.round(valorPorPessoa * escolhidos.size * 100) / 100;

  const marcarFiltro = () => setEscolhidos((p) => { const n = new Set(p); lista.forEach((l) => n.add(l.pessoa_id)); return n; });

  async function lancar() {
    setErro(null);
    if (!escolhidos.size) { setErro("Escolha ao menos uma pessoa."); return; }
    if (!motivo.trim()) { setErro("Informe o motivo."); return; }
    if (!(valorPorPessoa > 0)) { setErro("Informe um valor maior que zero."); return; }
    setSalvando(true);
    try {
      await lancarEntradaCaixa({
        pessoa_ids: Array.from(escolhidos), tipo, data, motivo: motivo.trim(),
        valor: valorCalculado == null ? Number(valor) : undefined,
        base_valor: tipo === "comissao" && base ? Number(base) : undefined,
        percentual: tipo === "comissao" && percentual ? Number(percentual) : undefined,
      });
      onFeito();
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  }

  return (
    <Modal title="Lançar entrada no caixa" onClose={onClose} width="640px">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div><label style={lbl} htmlFor="ce-tipo">Tipo de entrada</label>
          <select id="ce-tipo" style={campo} value={tipo} onChange={(e) => setTipo(e.target.value)}>
            {TIPOS_ENTRADA.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select></div>
        <div><label style={lbl} htmlFor="ce-data">Data</label><input id="ce-data" type="date" style={campo} value={data} onChange={(e) => setData(e.target.value)} /></div>
        {tipo === "comissao" ? (
          <>
            <div><label style={lbl} htmlFor="ce-base">Base (R$)</label><input id="ce-base" type="number" min="0" step="0.01" style={campo} value={base} onChange={(e) => setBase(e.target.value)} placeholder="Ex.: 40000" /></div>
            <div><label style={lbl} htmlFor="ce-pct">Percentual (%)</label><input id="ce-pct" type="number" min="0" step="0.01" style={campo} value={percentual} onChange={(e) => setPercentual(e.target.value)} placeholder="Ex.: 1" /></div>
          </>
        ) : (
          <div><label style={lbl}>Valor por pessoa (R$)</label><CampoMoeda style={campo} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} /></div>
        )}
        <div style={{ gridColumn: "1 / -1" }}><label style={lbl} htmlFor="ce-motivo">Motivo{tipo === "comissao" ? " / base (ex.: venda do lote 14)" : ""} (obrigatório)</label>
          <input id="ce-motivo" style={campo} value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder={tipo === "outro" ? "Ex.: ajuda de custo" : ""} /></div>
      </div>
      {tipo === "outro" && <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", margin: "0.4rem 0 0" }}>Em "Outro tipo" só o motivo é obrigatório: não há base nem percentual.</p>}

      <div style={{ marginTop: "0.8rem" }}>
        <label style={lbl}>Quem recebe</label>
        <div className="flex" style={{ gap: "0.35rem", flexWrap: "wrap", marginBottom: "0.4rem" }}>
          {GRUPOS.map((g) => (
            <button key={g.id} type="button" aria-pressed={filtro === g.id} onClick={() => setFiltro(g.id)}
              style={{ padding: "0.15rem 0.65rem", borderRadius: 999, fontSize: "0.75rem", cursor: "pointer", border: `1px solid ${filtro === g.id ? "var(--dourado)" : "var(--border)"}`,
                background: filtro === g.id ? "var(--dourado)" : "var(--surface)", color: filtro === g.id ? "var(--vinho-dark, #0A1F36)" : "var(--text-muted)" }}>{g.label}</button>
          ))}
          <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={marcarFiltro}>Marcar todos deste filtro</button>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setEscolhidos(new Set())}>Limpar</button>
        </div>
        <div style={{ maxHeight: 190, overflowY: "auto", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem" }}>
          {lista.map((p) => (
            <label key={p.pessoa_id} style={{ display: "flex", gap: "0.5rem", alignItems: "center", fontSize: "0.82rem", margin: "0.15rem 0", color: "var(--text)" }}>
              <input type="checkbox" checked={escolhidos.has(p.pessoa_id)}
                onChange={() => setEscolhidos((s) => { const n = new Set(s); n.has(p.pessoa_id) ? n.delete(p.pessoa_id) : n.add(p.pessoa_id); return n; })} />
              {p.nome} <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>{rotuloGrupos(p.grupos)}</span>
            </label>
          ))}
          {!lista.length && <span style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Ninguém neste filtro.</span>}
        </div>
      </div>

      <p style={{ marginTop: "0.7rem", fontSize: "0.82rem" }}>
        <b>{escolhidos.size}</b> pessoa{escolhidos.size === 1 ? "" : "s"} × {formatBRL(valorPorPessoa)} = <b>{formatBRL(total)}</b>.
        <span style={{ color: "var(--text-muted)" }}> Cada entrada vira uma despesa de pessoal já baixada no Financeiro, com número de lançamento.</span>
      </p>
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}
      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "0.8rem" }}>
        <button type="button" className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
        <button type="button" className="btn-primary" onClick={lancar} disabled={salvando}>{salvando ? "Lançando…" : `Lançar ${escolhidos.size || ""} entrada${escolhidos.size === 1 ? "" : "s"}`}</button>
      </div>
    </Modal>
  );
}

function RetiradaModal({ pessoaId, pessoaNome, grupos, saldo, onClose, onFeita }: {
  pessoaId: number; pessoaNome: string; grupos: string[]; saldo: number; onClose: () => void; onFeita: (r: CaixaRecibo) => void;
}) {
  const [valor, setValor] = useState("");
  const [data, setData] = useState(hojeISO());
  const [forma, setForma] = useState("pix");
  const [conta, setConta] = useState("");
  const [numero, setNumero] = useState("");
  const [contas, setContas] = useState<string[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  useEffect(() => { fetchOpcoesFinanceiro().then((d) => setContas(d.contas_bancarias || [])).catch(() => {}); }, []);
  const acima = Number(valor) > saldo;

  async function confirmar() {
    setErro(null);
    if (!(Number(valor) > 0)) { setErro("Informe o valor."); return; }
    if (acima) { setErro(`Valor acima do saldo de ${formatBRL(saldo)}. Para adiantar, use o Vale.`); return; }
    setSalvando(true);
    try {
      const r = await registrarRetiradaCaixa(pessoaId, {
        valor: Number(valor), data, forma_pagamento: forma, conta_bancaria: conta || undefined,
        numero_documento_pagamento: numero.trim() || undefined,
      });
      onFeita(r);
    } catch (e: any) { setErro(e.message); setSalvando(false); }
  }

  return (
    <Modal title="Retirada do caixa" onClose={onClose} width="520px">
      <p style={{ margin: "0 0 0.15rem", fontWeight: 600 }}>{pessoaNome}</p>
      <p style={{ margin: "0 0 0.8rem", color: "var(--text-muted)", fontSize: "0.8rem" }}>
        Colaborador: {rotuloGrupos(grupos)} · saldo individual disponível: <b style={{ color: "var(--text)" }}>{formatBRL(saldo)}</b>
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div><label style={lbl}>Valor (R$)</label><CampoMoeda style={campo} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} /></div>
        <div><label style={lbl} htmlFor="rt-data">Data</label><input id="rt-data" type="date" style={campo} value={data} onChange={(e) => setData(e.target.value)} /></div>
        <div><label style={lbl} htmlFor="rt-forma">Forma de pagamento</label>
          <select id="rt-forma" style={campo} value={forma} onChange={(e) => setForma(e.target.value)}>{FORMAS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</select></div>
        <div><label style={lbl} htmlFor="rt-conta">Conta bancária</label>
          <select id="rt-conta" style={campo} value={conta} onChange={(e) => setConta(e.target.value)}><option value="">Não informar</option>{contas.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
        <div style={{ gridColumn: "1 / -1" }}><label style={lbl} htmlFor="rt-num">Nº do comprovante (opcional)</label>
          <input id="rt-num" style={campo} value={numero} onChange={(e) => setNumero(e.target.value)} placeholder="Ex.: código da transação Pix" /></div>
      </div>
      <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", margin: "0.5rem 0 0" }}>Ao confirmar, o recibo é gerado para o colaborador assinar, com o saldo antes e depois da retirada.</p>
      {acima && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>Valor acima do saldo de {formatBRL(saldo)}. Para adiantar, use o Vale.</p>}
      {erro && !acima && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}
      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "0.9rem" }}>
        <button type="button" className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
        <button type="button" className="btn-primary" onClick={confirmar} disabled={salvando || acima}>{salvando ? "Registrando…" : "Confirmar retirada"}</button>
      </div>
    </Modal>
  );
}

function EstornoModal({ pessoaId, movimento, onClose, onFeito }: {
  pessoaId: number; movimento: CaixaMovimentoItem; onClose: () => void; onFeito: () => void;
}) {
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  async function confirmar() {
    if (!motivo.trim()) { setErro("Informe o motivo do estorno."); return; }
    setSalvando(true); setErro(null);
    try { await estornarMovimentoCaixa(pessoaId, movimento.id, motivo.trim()); onFeito(); }
    catch (e: any) { setErro(e.message); setSalvando(false); }
  }
  return (
    <Modal title={`Estornar ${ROTULO_TIPO[movimento.tipo]?.toLowerCase() || "movimento"} de ${formatDate(movimento.data)}`} onClose={onClose} width="480px">
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", margin: "0 0 0.7rem" }}>
        Cria um movimento contrário de {formatBRL(Math.abs(movimento.valor))}, com a data de hoje. O original continua visível, riscado.
        {movimento.numero_lancamento && movimento.valor > 0 ? " O Financeiro recebe o lançamento contrário." : ""}
      </p>
      <label style={lbl} htmlFor="es-motivo">Motivo do estorno (obrigatório)</label>
      <input id="es-motivo" style={campo} value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ex.: valor lançado em duplicidade" />
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}
      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "0.9rem" }}>
        <button type="button" className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
        <button type="button" className="btn-primary" style={{ background: "var(--red)" }} onClick={confirmar} disabled={salvando}>{salvando ? "Estornando…" : "Confirmar estorno"}</button>
      </div>
    </Modal>
  );
}
