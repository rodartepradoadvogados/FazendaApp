"use client";
// Faturas de fornecedor (modo contínuo): cadastro (fornecedor, abertura, fechamento, vencimento, parcelamento opcional),
// notas lançadas dentro da fatura aberta, fechamento (à vista ou parcelado), reabertura, pagamento por parcela e estorno.
import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { AlertTriangle, Check, History, Plus, RotateCcw, Trash2, X } from "lucide-react";
import {
  abrirFatura, anexarComprovanteEmLote, editarFatura, estornarParcelaFatura, excluirFatura, fecharFatura, fetchContasCorrentes,
  fetchCentrosCusto, fetchFatura, fetchFaturas, fetchFornecedores, fetchOpcoesFinanceiro, formatBRL, pagarParcelaFatura, reabrirFatura, tirarNotaDaFatura,
  type ContaCorrenteCadastro, type FaturaCadastroIn, type FaturaDetalhe, type FaturaResumo, type FaturaStatus,
} from "@/lib/api";
import { CampoMoeda } from "@/components/CampoMoeda";
import { Modal } from "@/components/Modal";

const FormLancamentoLote = dynamic(() => import("@/components/FormLancamentoLote").then((m) => m.FormLancamentoLote), { ssr: false });

const FORMAS = [
  { value: "pix", label: "Pix" }, { value: "transferencia", label: "Transferência" }, { value: "debito", label: "Débito" },
  { value: "credito", label: "Crédito" }, { value: "dinheiro", label: "Dinheiro" }, { value: "boleto", label: "Boleto" },
];
const ESTILO_TABELA = ".fat-tab th, .fat-tab td { padding: 0.35rem 0.7rem; }";
const lbl = { display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem" } as const;
const campo = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.82rem",
} as const;
const hoje = () => new Date().toISOString().slice(0, 10);
const br = (d: string | null | undefined) => (d ? d.split("-").reverse().join("/") : "—");
const ROTULO_STATUS: Record<FaturaStatus, string> = { aberta: "Aberta", fechada: "Fechada", paga: "Paga" };
const COR_STATUS: Record<FaturaStatus, string> = { aberta: "var(--amber)", fechada: "var(--blue, #5b8def)", paga: "var(--green-light)" };

function Selo({ s }: { s: FaturaStatus }) {
  return <span style={{ fontSize: "0.7rem", border: `1px solid ${COR_STATUS[s]}`, color: COR_STATUS[s], borderRadius: "999px", padding: "0.05rem 0.5rem" }}>{ROTULO_STATUS[s]}</span>;
}

type Parc = { n: string; primeiro: string; intervalo: "mensal" | "30dias" };
const parcVazio = (): Parc => ({ n: "", primeiro: "", intervalo: "mensal" });
const parcOut = (p: Parc): FaturaCadastroIn["parcelamento"] =>
  Number(p.n) >= 2 && p.primeiro ? { n: Number(p.n), primeiro_vencimento: p.primeiro, intervalo: p.intervalo } : null;

function CamposParcelamento({ p, set, desabilitado }: { p: Parc; set: (p: Parc) => void; desabilitado?: boolean }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <div><label style={lbl} htmlFor="fat-pn">Nº de parcelas</label>
        <input id="fat-pn" type="number" min={2} style={campo} value={p.n} disabled={desabilitado} onChange={(e) => set({ ...p, n: e.target.value })} /></div>
      <div><label style={lbl} htmlFor="fat-pp">Primeiro vencimento</label>
        <input id="fat-pp" type="date" style={campo} value={p.primeiro} disabled={desabilitado} onChange={(e) => set({ ...p, primeiro: e.target.value })} /></div>
      <div><label style={lbl} htmlFor="fat-pi">Intervalo</label>
        <select id="fat-pi" style={campo} value={p.intervalo} disabled={desabilitado} onChange={(e) => set({ ...p, intervalo: e.target.value as Parc["intervalo"] })}>
          <option value="mensal">Mensal</option><option value="30dias">A cada 30 dias</option></select></div>
    </div>
  );
}

function previaParcelas(total: number, p: Parc): { n: number; venc: string; valor: number }[] {
  const n = Number(p.n);
  if (!(n >= 2) || !p.primeiro || !(total > 0)) return [];
  const cent = Math.round(total * 100), base = Math.floor(cent / n), [y, m, d] = p.primeiro.split("-").map(Number);
  return Array.from({ length: n }, (_, i) => {
    let venc: string;
    if (p.intervalo === "30dias") { const dt = new Date(Date.UTC(y, m - 1, d + 30 * i)); venc = dt.toISOString().slice(0, 10); }
    else { const alvo = new Date(Date.UTC(y, m - 1 + i, 1)); const ult = new Date(Date.UTC(alvo.getUTCFullYear(), alvo.getUTCMonth() + 1, 0)).getUTCDate();
      venc = new Date(Date.UTC(alvo.getUTCFullYear(), alvo.getUTCMonth(), Math.min(d, ult))).toISOString().slice(0, 10); }
    return { n: i + 1, venc, valor: (i === n - 1 ? cent - base * (n - 1) : base) / 100 };
  });
}

// ───────────────────────── Cadastro (nova / editar) ─────────────────────────
function ModalCadastro({ fatura, onClose, onSalvo }: { fatura?: FaturaDetalhe; onClose: () => void; onSalvo: (f: FaturaDetalhe) => void }) {
  const [fornecedores, setFornecedores] = useState<string[]>([]);
  const [contas, setContas] = useState<ContaCorrenteCadastro[]>([]);
  const [centros, setCentros] = useState<{ nome: string }[]>([]);
  const [fornecedor, setFornecedor] = useState(fatura?.fornecedor || "");
  const [rotulo, setRotulo] = useState(fatura?.rotulo || "");
  const [abertura, setAbertura] = useState(fatura?.data_abertura || hoje());
  const [fechamento, setFechamento] = useState(fatura?.data_fechamento_prevista || "");
  const [venc, setVenc] = useState(fatura?.data_vencimento || "");
  const [conta, setConta] = useState(fatura?.conta_bancaria || "");
  const [centro, setCentro] = useState(fatura?.centro_custo || "");
  const [parc, setParc] = useState<Parc>(fatura?.parcelas_n && fatura.parcelamento_origem === "cadastro"
    ? { n: String(fatura.parcelas_n), primeiro: fatura.parcelas_primeiro || "", intervalo: fatura.parcelas_intervalo || "mensal" } : parcVazio());
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  useEffect(() => {
    Promise.all([fetchFornecedores().catch(() => []), fetchOpcoesFinanceiro().catch(() => ({} as any)), fetchContasCorrentes().catch(() => []), fetchCentrosCusto().catch(() => [])])
      .then(([cad, op, cc, ce]: any[]) => {
        setFornecedores(Array.from(new Set<string>([...(op.fornecedores || []), ...(cad || []).map((f: any) => f.nome)])).sort((a, b) => a.localeCompare(b, "pt-BR")));
        setContas((cc || []).filter((c: ContaCorrenteCadastro) => c.ativo));
        setCentros((ce || []).filter((c: any) => c.ativo !== false));
      });
  }, []);
  async function salvar() {
    setErro(null);
    if (!fornecedor) { setErro("Escolha o fornecedor."); return; }
    if (!abertura) { setErro("Informe a data de abertura."); return; }
    if (fechamento && fechamento < abertura) { setErro("O fechamento previsto não pode ser anterior à abertura."); return; }
    if ((parc.n || parc.primeiro) && !parcOut(parc)) { setErro("Para parcelar, informe 2 ou mais parcelas e o primeiro vencimento — ou deixe tudo em branco."); return; }
    setSalvando(true);
    try {
      const corpo: FaturaCadastroIn = {
        fornecedor, rotulo: rotulo.trim() || null, data_abertura: abertura, data_fechamento_prevista: fechamento || null,
        data_vencimento: venc || null, conta_bancaria: conta || null, centro_custo: centro || null, parcelamento: parcOut(parc),
      };
      onSalvo(fatura ? await editarFatura(fatura.id, corpo) : await abrirFatura(corpo));
    } catch (e: any) { setErro(e.message || "Erro ao salvar."); } finally { setSalvando(false); }
  }
  return (
    <Modal title={fatura ? "Editar cadastro da fatura" : "Nova fatura"} onClose={onClose} width="680px">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div><label style={lbl} htmlFor="fat-forn">Fornecedor</label>
          <select id="fat-forn" style={campo} value={fornecedor} disabled={!!fatura && fatura.notas > 0} onChange={(e) => setFornecedor(e.target.value)}>
            <option value="">Selecione…</option>{fornecedores.map((f) => <option key={f} value={f}>{f}</option>)}</select></div>
        <div><label style={lbl} htmlFor="fat-rot">Identificação (opcional)</label>
          <input id="fat-rot" style={campo} value={rotulo} placeholder="Ex.: Coop. Regional — 09/2026" onChange={(e) => setRotulo(e.target.value)} /></div>
        <div><label style={lbl} htmlFor="fat-ab">Data de abertura</label>
          <input id="fat-ab" type="date" style={campo} value={abertura} onChange={(e) => setAbertura(e.target.value)} /></div>
        <div><label style={lbl} htmlFor="fat-fe">Fechamento previsto</label>
          <input id="fat-fe" type="date" style={campo} value={fechamento} onChange={(e) => setFechamento(e.target.value)} /></div>
        <div><label style={lbl} htmlFor="fat-ve">Vencimento (pagamento)</label>
          <input id="fat-ve" type="date" style={campo} value={venc} onChange={(e) => setVenc(e.target.value)} /></div>
        <div><label style={lbl} htmlFor="fat-co">Conta bancária</label>
          <select id="fat-co" style={campo} value={conta} onChange={(e) => setConta(e.target.value)}>
            <option value="">Selecione…</option>{contas.map((c) => <option key={c.id} value={c.rotulo}>{c.rotulo}</option>)}</select></div>
        <div><label style={lbl} htmlFor="fat-cc">Centro de custo</label>
          <select id="fat-cc" style={campo} value={centro} onChange={(e) => setCentro(e.target.value)}>
            <option value="">Selecione…</option>{centros.map((c) => <option key={c.nome} value={c.nome}>{c.nome}</option>)}</select></div>
      </div>
      <p style={{ ...lbl, marginTop: "0.9rem" }}>Parcelamento da fatura (opcional — se ficar em branco, define no fechamento)</p>
      <CamposParcelamento p={parc} set={setParc} />
      {erro && <div className="alert-critico mt-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      <div className="flex gap-3 mt-4">
        <button type="button" className="btn-primary" disabled={salvando} onClick={salvar}><Check size={14} /> {salvando ? "Salvando…" : fatura ? "Salvar" : "Abrir fatura"}</button>
        <button type="button" className="btn-ghost" onClick={onClose}><X size={14} /> Cancelar</button>
      </div>
    </Modal>
  );
}

// ───────────────────────── Fechar ─────────────────────────
function ModalFechar({ fatura, onClose, onFeita }: { fatura: FaturaDetalhe; onClose: () => void; onFeita: (f: FaturaDetalhe) => void }) {
  const doCadastro = fatura.parcelamento_origem === "cadastro" && !!fatura.parcelas_n;
  const soma = fatura.valor_total;
  const [totalForn, setTotalForn] = useState(fatura.total_fornecedor || 0);
  const [modo, setModo] = useState<"vista" | "parcelar">(doCadastro ? "parcelar" : "vista");
  const [venc, setVenc] = useState(fatura.data_vencimento || "");
  const [parc, setParc] = useState<Parc>(doCadastro ? { n: String(fatura.parcelas_n), primeiro: fatura.parcelas_primeiro || "", intervalo: fatura.parcelas_intervalo || "mensal" } : parcVazio());
  const [erro, setErro] = useState<string | null>(null);
  const [diverge, setDiverge] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const dif = totalForn > 0 ? Math.round((totalForn - soma) * 100) / 100 : null;
  const previa = previaParcelas(soma, parc);
  async function fechar(confirmar = false) {
    setErro(null);
    if (modo === "vista" && !venc) { setErro("Informe o vencimento."); return; }
    if (modo === "parcelar" && !parcOut(parc)) { setErro("Informe 2 ou mais parcelas e o primeiro vencimento."); return; }
    setSalvando(true);
    try {
      onFeita(await fecharFatura(fatura.id, {
        total_fornecedor: totalForn > 0 ? totalForn : null, confirmar_divergencia: confirmar, modo,
        parcelamento: modo === "parcelar" ? parcOut(parc) : null, data_vencimento: modo === "vista" ? venc : null,
      }));
    } catch (e: any) {
      if (e.status === 409 && e.detail?.codigo === "divergencia_total") setDiverge(true); else setErro(e.message || "Erro ao fechar.");
    } finally { setSalvando(false); }
  }
  return (
    <Modal title={`Fechar fatura — ${fatura.rotulo}`} onClose={onClose} width="640px">
      <div className="flex flex-wrap gap-x-8 gap-y-1" style={{ fontSize: "0.85rem" }}>
        <span>Notas: <strong>{fatura.notas}</strong></span>
        <span>Soma das notas: <strong style={{ fontVariantNumeric: "tabular-nums" }}>{formatBRL(soma)}</strong></span>
      </div>
      <div className="mt-3" style={{ maxWidth: "280px" }}>
        <label style={lbl} htmlFor="fec-tf">Total da fatura informado pelo fornecedor (opcional)</label>
        <CampoMoeda id="fec-tf" style={{ ...campo, textAlign: "right" }} value={totalForn} onChange={setTotalForn} />
      </div>
      {dif !== null && <p style={{ fontSize: "0.8rem", marginTop: "0.4rem", color: dif === 0 ? "var(--green-light)" : "var(--red)" }}>
        {dif === 0 ? "Confere com a fatura do fornecedor." : `Diferença de ${formatBRL(Math.abs(dif))}${dif > 0 ? " a menos nas notas" : " a mais nas notas"}.`}</p>}
      <div className="flex gap-2 flex-wrap mt-3">
        {([["vista", "À vista (vencimento único)"], ["parcelar", "Parcelar a fatura"]] as const).map(([v, r]) => (
          <label key={v} style={{ display: "flex", gap: "0.35rem", alignItems: "center", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.65rem", fontSize: "0.82rem", margin: 0, background: modo === v ? "var(--surface-2)" : undefined, opacity: doCadastro && v === "vista" ? 0.5 : 1 }}>
            <input type="radio" name="fec-modo" checked={modo === v} disabled={doCadastro && v === "vista"} onChange={() => setModo(v)} /> {r}</label>
        ))}
      </div>
      {doCadastro && <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>O parcelamento foi definido no cadastro da fatura e não pode ser alterado aqui. Para mudar, edite o cadastro.</p>}
      <div className="mt-3">
        {modo === "vista"
          ? <div style={{ maxWidth: "220px" }}><label style={lbl} htmlFor="fec-v">Vencimento</label><input id="fec-v" type="date" style={campo} value={venc} onChange={(e) => setVenc(e.target.value)} /></div>
          : <CamposParcelamento p={parc} set={setParc} desabilitado={doCadastro} />}
      </div>
      {modo === "parcelar" && previa.length > 0 && (
        <table className="fat-tab" style={{ fontSize: "0.8rem", marginTop: "0.7rem", width: "100%" }}><tbody>
          {previa.map((x) => <tr key={x.n}><td>Parcela {x.n}</td><td>{br(x.venc)}</td><td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{formatBRL(x.valor)}</td></tr>)}
        </tbody></table>
      )}
      {erro && <div className="alert-critico mt-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {diverge && (
        <div className="alert-critico mt-3" style={{ display: "block" }}>
          <p style={{ marginBottom: "0.5rem" }}>O total das notas não confere com o total do fornecedor. Fechar mesmo assim?</p>
          <button type="button" className="btn-primary" disabled={salvando} onClick={() => fechar(true)}>Fechar mesmo assim</button>
        </div>
      )}
      <div className="flex gap-3 mt-4">
        <button type="button" className="btn-primary" disabled={salvando} onClick={() => fechar()}><Check size={14} /> {salvando ? "Fechando…" : "Fechar fatura"}</button>
        <button type="button" className="btn-ghost" onClick={onClose}><X size={14} /> Cancelar</button>
      </div>
    </Modal>
  );
}

// ───────────────────────── Motivo (reabrir / estornar) ─────────────────────────
function ModalMotivo({ titulo, aviso, rotuloBotao, onClose, onConfirmar }: { titulo: string; aviso: string; rotuloBotao: string; onClose: () => void; onConfirmar: (motivo: string) => Promise<void> }) {
  const [motivo, setMotivo] = useState(""); const [erro, setErro] = useState<string | null>(null); const [salvando, setSalvando] = useState(false);
  async function ok() {
    if (motivo.trim().length < 3) { setErro("Informe o motivo."); return; }
    setSalvando(true); setErro(null);
    try { await onConfirmar(motivo.trim()); } catch (e: any) { setErro(e.message || "Erro."); } finally { setSalvando(false); }
  }
  return (
    <Modal title={titulo} onClose={onClose} width="520px">
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>{aviso}</p>
      <label style={lbl} htmlFor="mot-t">Motivo</label>
      <textarea id="mot-t" style={{ ...campo, minHeight: "70px" }} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
      {erro && <div className="alert-critico mt-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      <div className="flex gap-3 mt-4">
        <button type="button" className="btn-primary" disabled={salvando} onClick={ok}><Check size={14} /> {salvando ? "Aguarde…" : rotuloBotao}</button>
        <button type="button" className="btn-ghost" onClick={onClose}><X size={14} /> Cancelar</button>
      </div>
    </Modal>
  );
}

// ───────────────────────── Pagar parcela ─────────────────────────
function ModalPagar({ fatura, parcela, onClose, onFeita }: { fatura: FaturaDetalhe; parcela: number; onClose: () => void; onFeita: (f: FaturaDetalhe) => void }) {
  const p = fatura.parcelas.find((x) => x.parcela === parcela)!;
  const [contas, setContas] = useState<ContaCorrenteCadastro[]>([]);
  const [data, setData] = useState(hoje());
  const [forma, setForma] = useState("pix");
  const [conta, setConta] = useState(fatura.conta_bancaria || "");
  const [doc, setDoc] = useState("");
  const [valorPago, setValorPago] = useState(p.valor);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  useEffect(() => { fetchContasCorrentes().then((c) => setContas(c.filter((x) => x.ativo))).catch(() => {}); }, []);
  const dif = Math.round((valorPago - p.valor) * 100) / 100;
  async function pagar() {
    setErro(null);
    if (!data) { setErro("Informe a data do pagamento."); return; }
    if (!conta) { setErro("Escolha a conta bancária."); return; }
    if (!(valorPago > 0)) { setErro("Informe o valor pago."); return; }
    setSalvando(true);
    try {
      const r = await pagarParcelaFatura(fatura.id, {
        parcela, data_pagamento: data, forma_pagamento: forma, conta_bancaria: conta,
        numero_documento_pagamento: doc.trim() || null, valor_pago: dif !== 0 ? valorPago : null,
      });
      let aviso = "";
      if (arquivo && r.ids_contas_pagas?.length) {
        try { await anexarComprovanteEmLote(r.ids_contas_pagas, [arquivo], "Comprovante de pagamento"); }
        catch (e: any) { aviso = ` A parcela foi paga, mas o comprovante não subiu (${e.message || "erro"}). Anexe pelas notas.`; }
      }
      onFeita(r); if (aviso) window.alert(aviso.trim());
    } catch (e: any) { setErro(e.message || "Erro ao pagar."); } finally { setSalvando(false); }
  }
  return (
    <Modal title={`Pagar parcela ${parcela}/${fatura.parcelas.length} — ${fatura.rotulo}`} onClose={onClose} width="600px">
      <p style={{ fontSize: "0.84rem", marginBottom: "0.7rem" }}>Vencimento {br(p.vencimento)} · valor <strong>{formatBRL(p.valor)}</strong>. O pagamento baixa a parcela de todas as {fatura.notas} notas.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div><label style={lbl} htmlFor="pg-d">Data do pagamento</label><input id="pg-d" type="date" style={campo} value={data} onChange={(e) => setData(e.target.value)} /></div>
        <div><label style={lbl} htmlFor="pg-f">Forma de pagamento</label>
          <select id="pg-f" style={campo} value={forma} onChange={(e) => setForma(e.target.value)}>{FORMAS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></div>
        <div><label style={lbl} htmlFor="pg-c">Conta bancária</label>
          <select id="pg-c" style={campo} value={conta} onChange={(e) => setConta(e.target.value)}>
            <option value="">Selecione…</option>{contas.map((c) => <option key={c.id} value={c.rotulo}>{c.rotulo}</option>)}</select></div>
        <div><label style={lbl} htmlFor="pg-n">Nº do comprovante (opcional)</label><input id="pg-n" style={campo} value={doc} onChange={(e) => setDoc(e.target.value)} /></div>
        <div><label style={lbl} htmlFor="pg-v">Valor pago</label><CampoMoeda id="pg-v" style={{ ...campo, textAlign: "right" }} value={valorPago} onChange={setValorPago} /></div>
        <div><label style={lbl} htmlFor="pg-a">Comprovante (um arquivo para todas as notas)</label>
          <input id="pg-a" type="file" accept="image/*,application/pdf" style={campo} onChange={(e) => setArquivo(e.target.files?.[0] || null)} /></div>
      </div>
      {dif !== 0 && <p style={{ fontSize: "0.78rem", marginTop: "0.6rem", color: "var(--amber)" }}>
        Valor {dif > 0 ? "acima" : "abaixo"} em {formatBRL(Math.abs(dif))}: a diferença será rateada proporcionalmente entre as notas.</p>}
      {erro && <div className="alert-critico mt-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      <div className="flex gap-3 mt-4">
        <button type="button" className="btn-primary" disabled={salvando} onClick={pagar}><Check size={14} /> {salvando ? "Pagando…" : "Confirmar pagamento"}</button>
        <button type="button" className="btn-ghost" onClick={onClose}><X size={14} /> Cancelar</button>
      </div>
    </Modal>
  );
}

// ───────────────────────── Detalhe ─────────────────────────
type Acao = null | { t: "editar" } | { t: "fechar" } | { t: "reabrir" } | { t: "pagar"; parcela: number } | { t: "estornar"; parcela: number } | { t: "historico" } | { t: "excluir" };

function Detalhe({ id, onVoltar, onMudou }: { id: number; onVoltar: () => void; onMudou: () => void }) {
  const [f, setF] = useState<FaturaDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [acao, setAcao] = useState<Acao>(null);
  const [lancando, setLancando] = useState(false);
  const carregar = useCallback(() => fetchFatura(id).then(setF).catch((e) => setErro(e.message)), [id]);
  useEffect(() => { carregar(); }, [carregar]);
  const atualizar = (nova: FaturaDetalhe) => { setF(nova); setAcao(null); onMudou(); };
  if (erro) return <div className="alert-critico"><AlertTriangle size={16} /><span>{erro}</span></div>;
  if (!f) return <p style={{ color: "var(--text-muted)" }}>Carregando…</p>;
  const aberta = f.status === "aberta";
  const nenhumaPaga = f.parcelas.every((p) => !p.pago);
  async function tirar(numero: string) {
    if (!window.confirm(`Tirar a nota ${numero} da fatura? Ela continua lançada, só deixa de fazer parte da fatura.`)) return;
    try { atualizar(await tirarNotaDaFatura(id, numero)); } catch (e: any) { setErro(e.message); }
  }
  return (
    <div>
      <style>{ESTILO_TABELA}</style>
      <button type="button" className="btn-ghost mb-3" onClick={onVoltar}>← Faturas</button>
      <div className="card">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><strong style={{ fontSize: "1rem" }}>{f.rotulo}</strong> <Selo s={f.status} />
            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
              {f.fornecedor} · abertura {br(f.data_abertura)} · fechamento previsto {br(f.data_fechamento_prevista)} · {f.conta_bancaria || "sem conta"} · {f.centro_custo || "sem centro de custo"}</div></div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{f.notas} nota(s)</div>
            <strong style={{ fontVariantNumeric: "tabular-nums", fontSize: "1.1rem" }}>{formatBRL(f.valor_total)}</strong></div>
        </div>
        <div className="flex flex-wrap gap-2 mt-3">
          {aberta && <button type="button" className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={() => setAcao({ t: "fechar" })} disabled={f.notas === 0}>Fechar fatura</button>}
          {aberta && <button type="button" className="btn-secondary" style={{ fontSize: "0.8rem" }} onClick={() => setAcao({ t: "editar" })}>Editar cadastro</button>}
          {f.status === "fechada" && nenhumaPaga && <button type="button" className="btn-secondary" style={{ fontSize: "0.8rem" }} onClick={() => setAcao({ t: "reabrir" })}><RotateCcw size={13} /> Reabrir</button>}
          {aberta && <button type="button" className="btn-ghost" style={{ fontSize: "0.8rem", color: "var(--red)" }} onClick={() => setAcao({ t: "excluir" })}><Trash2 size={13} /> Excluir</button>}
          <button type="button" className="btn-ghost" style={{ fontSize: "0.8rem" }} onClick={() => setAcao({ t: "historico" })}><History size={13} /> Histórico</button>
        </div>
      </div>

      {f.parcelas.length > 0 && !aberta && (
        <div className="card mt-3">
          <p className="card-header mb-2">Parcelas</p>
          <table className="fat-tab" style={{ width: "100%", fontSize: "0.82rem" }}>
            <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}><th>#</th><th>Vencimento</th><th style={{ textAlign: "right" }}>Valor</th><th>Situação</th><th /></tr></thead>
            <tbody>{f.parcelas.map((p) => (
              <tr key={p.parcela}>
                <td>{p.parcela}</td><td>{br(p.vencimento)}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{formatBRL(p.pago ? p.valor_pago : p.valor)}</td>
                <td>{p.pago ? `Paga em ${br(p.data_pagamento)}` : "A pagar"}</td>
                <td style={{ textAlign: "right" }}>{p.pago
                  ? <button type="button" className="btn-ghost" style={{ fontSize: "0.76rem" }} onClick={() => setAcao({ t: "estornar", parcela: p.parcela })}>Estornar</button>
                  : <button type="button" className="btn-primary" style={{ fontSize: "0.76rem" }} onClick={() => setAcao({ t: "pagar", parcela: p.parcela })}>Pagar</button>}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}

      <div className="card mt-3">
        <p className="card-header mb-2">Notas da fatura</p>
        {f.lista_notas.length === 0 ? <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>Nenhuma nota ainda.</p> : (
          <table className="fat-tab" style={{ width: "100%", fontSize: "0.82rem" }}>
            <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}><th>Lançamento</th><th>Documento</th><th>Emissão</th><th style={{ textAlign: "right" }}>Valor</th><th /></tr></thead>
            <tbody>{f.lista_notas.map((n) => (
              <tr key={n.numero_lancamento || n.numero_documento}>
                <td>{n.numero_lancamento}</td><td>{n.tipo_documento} {n.numero_documento || "s/n"}</td><td>{br(n.data_emissao)}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{formatBRL(n.valor)}</td>
                <td style={{ textAlign: "right" }}>{aberta && n.numero_lancamento && <button type="button" className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={() => tirar(n.numero_lancamento!)}>Tirar da fatura</button>}</td>
              </tr>))}</tbody>
          </table>
        )}
      </div>

      {aberta && (
        <div className="mt-3">
          {!lancando ? <button type="button" className="btn-primary" onClick={() => setLancando(true)}><Plus size={14} /> Lançar notas nesta fatura</button> : (
            <div>
              <div className="flex justify-between items-center mb-2"><strong style={{ fontSize: "0.9rem" }}>Lançar notas na fatura</strong>
                <button type="button" className="btn-ghost" onClick={() => setLancando(false)}><X size={14} /> Fechar formulário</button></div>
              <FormLancamentoLote fatura={f} onLancado={() => { carregar(); onMudou(); }} />
            </div>
          )}
        </div>
      )}

      {acao?.t === "editar" && <ModalCadastro fatura={f} onClose={() => setAcao(null)} onSalvo={atualizar} />}
      {acao?.t === "fechar" && <ModalFechar fatura={f} onClose={() => setAcao(null)} onFeita={atualizar} />}
      {acao?.t === "pagar" && <ModalPagar fatura={f} parcela={acao.parcela} onClose={() => setAcao(null)} onFeita={atualizar} />}
      {acao?.t === "reabrir" && <ModalMotivo titulo="Reabrir fatura" rotuloBotao="Reabrir" aviso="A fatura volta para aberta: as parcelas geradas no fechamento são desfeitas e novas notas podem entrar."
        onClose={() => setAcao(null)} onConfirmar={async (m) => atualizar(await reabrirFatura(id, m))} />}
      {acao?.t === "estornar" && <ModalMotivo titulo={`Estornar pagamento da parcela ${acao.parcela}`} rotuloBotao="Estornar" aviso="A parcela volta para 'a pagar' em todas as notas da fatura."
        onClose={() => setAcao(null)} onConfirmar={async (m) => atualizar(await estornarParcelaFatura(id, acao.parcela, m))} />}
      {acao?.t === "excluir" && (
        <Modal title="Excluir fatura" onClose={() => setAcao(null)} width="520px">
          <p style={{ fontSize: "0.84rem", marginBottom: "0.8rem" }}>{f.notas > 0 ? `Esta fatura tem ${f.notas} nota(s). Você pode soltá-las (continuam lançadas, sem fatura) e excluir a fatura.` : "Excluir a fatura vazia?"}</p>
          <div className="flex gap-3">
            <button type="button" className="btn-primary" onClick={async () => { try { await excluirFatura(id, f.notas > 0); onMudou(); onVoltar(); } catch (e: any) { setErro(e.message); setAcao(null); } }}>
              <Trash2 size={14} /> {f.notas > 0 ? "Soltar notas e excluir" : "Excluir"}</button>
            <button type="button" className="btn-ghost" onClick={() => setAcao(null)}><X size={14} /> Cancelar</button>
          </div>
        </Modal>
      )}
      {acao?.t === "historico" && (
        <Modal title="Histórico da fatura" onClose={() => setAcao(null)} width="600px">
          {f.eventos.length === 0 ? <p style={{ fontSize: "0.82rem" }}>Sem eventos.</p> : (
            <ul style={{ fontSize: "0.82rem", paddingLeft: "1rem" }}>{f.eventos.map((e, i) => (
              <li key={i} style={{ marginBottom: "0.35rem" }}><strong>{e.acao}</strong> — {e.detalhe || ""} <span style={{ color: "var(--text-muted)" }}>({new Date(e.em).toLocaleString("pt-BR")}{e.usuario ? ` · ${e.usuario}` : ""})</span></li>))}</ul>
          )}
        </Modal>
      )}
    </div>
  );
}

// ───────────────────────── Lista ─────────────────────────
export function FaturasView() {
  const [lista, setLista] = useState<FaturaResumo[] | null>(null);
  const [filtro, setFiltro] = useState<"" | FaturaStatus>("aberta");
  const [aberta, setAberta] = useState<number | null>(null);
  const [nova, setNova] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const carregar = useCallback(() => fetchFaturas(filtro || undefined).then(setLista).catch((e) => setErro(e.message)), [filtro]);
  useEffect(() => { carregar(); }, [carregar]);
  if (aberta !== null) return <Detalhe id={aberta} onVoltar={() => { setAberta(null); carregar(); }} onMudou={carregar} />;
  return (
    <div>
      <style>{ESTILO_TABELA}</style>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "1rem" }}>
        Cadastre a fatura do fornecedor (abertura, fechamento, vencimento) e lance as notas dentro dela ao longo do período. No fechamento ela vira à vista ou parcelada; o pagamento é por parcela.
      </p>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {([["aberta", "Abertas"], ["fechada", "Fechadas"], ["paga", "Pagas"], ["", "Todas"]] as const).map(([v, r]) => (
          <button key={v} type="button" className={filtro === v ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.78rem" }} onClick={() => setFiltro(v)}>{r}</button>))}
        <span style={{ flex: 1 }} />
        <button type="button" className="btn-primary" style={{ fontSize: "0.8rem" }} onClick={() => setNova(true)}><Plus size={14} /> Nova fatura</button>
      </div>
      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {lista === null ? <p style={{ color: "var(--text-muted)" }}>Carregando…</p> : lista.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Nenhuma fatura {filtro ? ROTULO_STATUS[filtro].toLowerCase() : ""}. Use "Nova fatura" para cadastrar a primeira.</p>
      ) : (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="fat-tab" style={{ width: "100%", fontSize: "0.82rem" }}>
            <thead><tr style={{ color: "var(--text-muted)", textAlign: "left" }}><th>Fatura</th><th>Fornecedor</th><th>Período</th><th>Situação</th><th style={{ textAlign: "right" }}>Notas</th><th style={{ textAlign: "right" }}>Total</th></tr></thead>
            <tbody>{lista.map((x) => (
              <tr key={x.id} style={{ cursor: "pointer", borderTop: "1px solid var(--border)" }} onClick={() => setAberta(x.id)}>
                <td><button type="button" className="btn-ghost" style={{ padding: 0 }} onClick={() => setAberta(x.id)}>{x.rotulo}</button></td>
                <td>{x.fornecedor}</td><td>{br(x.data_abertura)} → {br(x.data_fechamento_prevista)}</td><td><Selo s={x.status} /></td>
                <td style={{ textAlign: "right" }}>{x.notas}</td>
                <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{formatBRL(x.valor_total)}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      {nova && <ModalCadastro onClose={() => setNova(false)} onSalvo={(f) => { setNova(false); carregar(); setAberta(f.id); }} />}
    </div>
  );
}
