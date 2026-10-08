"use client";
// Faturas de fornecedor (modo contínuo): cadastro (fornecedor, abertura, fechamento, vencimento, parcelamento opcional),
// notas lançadas dentro da fatura aberta, fechamento (à vista ou parcelado), reabertura, pagamento por parcela e estorno.
// Visual do Financeiro v2: pílulas de situação (ícone + texto), cards de resumo, ciclo Aberta → Fechada → Paga,
// tabelas .fazenda-table com rolagem interna. Estilos em components/financeiro/faturaVisual.tsx (tudo em var(--…)).
import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  AlertTriangle, Check, CheckCircle2, ChevronLeft, Circle, Clock, FileText, History, Info, Layers, Lock, Pencil, Plus,
  RotateCcw, Trash2, Undo2, Wallet, X,
} from "lucide-react";
import {
  abrirFatura, anexarComprovanteEmLote, editarFatura, estornarParcelaFatura, excluirFatura, fecharFatura, fetchContasCorrentes,
  fetchCentrosCusto, fetchFatura, fetchFaturas, fetchFornecedores, fetchOpcoesFinanceiro, formatBRL, pagarParcelaFatura, reabrirFatura, tirarNotaDaFatura,
  type ContaCorrenteCadastro, type FaturaCadastroIn, type FaturaDetalhe, type FaturaParcela, type FaturaResumo, type FaturaStatus,
} from "@/lib/api";
import { CampoMoeda } from "@/components/CampoMoeda";
import { Modal } from "@/components/Modal";
import { EstiloFatura, PilulaFatura } from "@/components/financeiro/faturaVisual";

const FormLancamentoLote = dynamic(() => import("@/components/FormLancamentoLote").then((m) => m.FormLancamentoLote), { ssr: false });

const FORMAS = [
  { value: "pix", label: "Pix" }, { value: "transferencia", label: "Transferência" }, { value: "debito", label: "Débito" },
  { value: "credito", label: "Crédito" }, { value: "dinheiro", label: "Dinheiro" }, { value: "boleto", label: "Boleto" },
];
const hoje = () => new Date().toISOString().slice(0, 10);
const br = (d: string | null | undefined) => (d ? d.split("-").reverse().join("/") : "—");
const dm = (d: string | null | undefined) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}` : "—");
const ROTULO_STATUS: Record<FaturaStatus, string> = { aberta: "Aberta", fechada: "Fechada", paga: "Paga" };
const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`;
const msgErro = (e: unknown, padrao: string) => (e instanceof Error && e.message ? e.message : padrao);
type ErroApi = Error & { status?: number; detail?: { codigo?: string } };

function Erro({ texto, className = "mt-3" }: { texto: string; className?: string }) {
  return <div className={`alert-critico ${className}`} role="alert"><AlertTriangle size={16} aria-hidden /><span>{texto}</span></div>;
}

/** Situação da parcela: "Em aberto" ou "Paga em dd/mm" (ícone + texto). */
function PilulaParcela({ p }: { p: FaturaParcela }) {
  return p.pago
    ? <span className="st-pill pago"><CheckCircle2 size={12} aria-hidden />Paga em {dm(p.data_pagamento)}</span>
    : <span className="st-pill aberto"><Circle size={12} aria-hidden />Em aberto</span>;
}

/** Diferença entre o pago e o previsto (acréscimo/desconto) — com palavra, não só cor. */
function Delta({ valor }: { valor: number }) {
  if (!valor) return null;
  return <span className={`fv-delta${valor < 0 ? " desc" : ""}`}>{valor > 0 ? "acréscimo" : "desconto"} {formatBRL(Math.abs(valor))}</span>;
}

type Parc = { n: string; primeiro: string; intervalo: "mensal" | "30dias" };
const parcVazio = (): Parc => ({ n: "", primeiro: "", intervalo: "mensal" });
const parcOut = (p: Parc): FaturaCadastroIn["parcelamento"] =>
  Number(p.n) >= 2 && p.primeiro ? { n: Number(p.n), primeiro_vencimento: p.primeiro, intervalo: p.intervalo } : null;

function CamposParcelamento({ p, set, desabilitado }: { p: Parc; set: (p: Parc) => void; desabilitado?: boolean }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <div><label className="fv-lbl" htmlFor="fat-pn">Nº de parcelas</label>
        <input id="fat-pn" type="number" min={2} inputMode="numeric" className="fv-in" value={p.n} disabled={desabilitado} onChange={(e) => set({ ...p, n: e.target.value })} /></div>
      <div><label className="fv-lbl" htmlFor="fat-pp">Primeiro vencimento</label>
        <input id="fat-pp" type="date" className="fv-in" value={p.primeiro} disabled={desabilitado} onChange={(e) => set({ ...p, primeiro: e.target.value })} /></div>
      <div><label className="fv-lbl" htmlFor="fat-pi">Intervalo</label>
        <select id="fat-pi" className="fv-in" value={p.intervalo} disabled={desabilitado} onChange={(e) => set({ ...p, intervalo: e.target.value as Parc["intervalo"] })}>
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

/** Prévia do rateio (só exibição): mesma conta do servidor — diferença em centavos, proporcional à parte de cada nota na parcela, sobra na última. */
function previaRateio(f: FaturaDetalhe, parcela: number, valorPago: number) {
  const linhas = f.lista_notas
    .map((n) => ({ n, partes: n.parcelas.filter((x) => (x.parcela ?? 1) === parcela) }))
    .filter((x) => x.partes.length > 0)
    .map(({ n, partes }) => ({ n, parte: Math.round(partes.reduce((s, x) => s + (x.valor || 0), 0) * 100) }));
  const soma = linhas.reduce((s, l) => s + l.parte, 0);
  if (!soma || !(valorPago > 0)) return [];
  const dif = Math.round(valorPago * 100) - soma;
  const cotas = linhas.map((l) => (dif >= 0 ? Math.floor((dif * l.parte) / soma) : -Math.floor((-dif * l.parte) / soma)));
  cotas[cotas.length - 1] += dif - cotas.reduce((s, c) => s + c, 0);
  return linhas.map((l, i) => ({ nota: l.n, parte: l.parte / 100, rateio: cotas[i] / 100, pago: (l.parte + cotas[i]) / 100 }));
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
    Promise.all([fetchFornecedores().catch(() => []), fetchOpcoesFinanceiro().catch(() => ({} as { fornecedores?: string[] })), fetchContasCorrentes().catch(() => []), fetchCentrosCusto().catch(() => [])])
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .then(([cad, op, cc, ce]: any[]) => {
        setFornecedores(Array.from(new Set<string>([...(op.fornecedores || []), ...(cad || []).map((f: { nome: string }) => f.nome)])).sort((a, b) => a.localeCompare(b, "pt-BR")));
        setContas((cc || []).filter((c: ContaCorrenteCadastro) => c.ativo));
        setCentros((ce || []).filter((c: { ativo?: boolean }) => c.ativo !== false));
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
    } catch (e) { setErro(msgErro(e, "Erro ao salvar.")); } finally { setSalvando(false); }
  }
  return (
    <Modal title={fatura ? "Editar cadastro da fatura" : "Nova fatura"} onClose={onClose} width="680px">
      <div className="fv-modal">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div><label className="fv-lbl" htmlFor="fat-forn">Fornecedor</label>
            <select id="fat-forn" className="fv-in" value={fornecedor} disabled={!!fatura && fatura.notas > 0} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Selecione…</option>{fornecedores.map((f) => <option key={f} value={f}>{f}</option>)}</select></div>
          <div><label className="fv-lbl" htmlFor="fat-rot">Identificação (opcional)</label>
            <input id="fat-rot" className="fv-in" value={rotulo} placeholder="Ex.: Coop. Regional — 09/2026" onChange={(e) => setRotulo(e.target.value)} /></div>
          <div><label className="fv-lbl" htmlFor="fat-ab">Data de abertura</label>
            <input id="fat-ab" type="date" className="fv-in" value={abertura} onChange={(e) => setAbertura(e.target.value)} /></div>
          <div><label className="fv-lbl" htmlFor="fat-fe">Fechamento previsto</label>
            <input id="fat-fe" type="date" className="fv-in" value={fechamento} onChange={(e) => setFechamento(e.target.value)} /></div>
          <div><label className="fv-lbl" htmlFor="fat-ve">Vencimento (pagamento)</label>
            <input id="fat-ve" type="date" className="fv-in" value={venc} onChange={(e) => setVenc(e.target.value)} /></div>
          <div><label className="fv-lbl" htmlFor="fat-co">Conta bancária</label>
            <select id="fat-co" className="fv-in" value={conta} onChange={(e) => setConta(e.target.value)}>
              <option value="">Selecione…</option>{contas.map((c) => <option key={c.id} value={c.rotulo}>{c.rotulo}</option>)}</select></div>
          <div><label className="fv-lbl" htmlFor="fat-cc">Centro de custo</label>
            <select id="fat-cc" className="fv-in" value={centro} onChange={(e) => setCentro(e.target.value)}>
              <option value="">Selecione…</option>{centros.map((c) => <option key={c.nome} value={c.nome}>{c.nome}</option>)}</select></div>
        </div>
        <p className="fv-grupo">Parcelamento da fatura (opcional — se ficar em branco, define no fechamento)</p>
        <CamposParcelamento p={parc} set={setParc} />
        {erro && <Erro texto={erro} />}
        <div className="fv-rodape">
          <button type="button" className="btn-primary" disabled={salvando} onClick={salvar}><Check size={14} aria-hidden /> {salvando ? "Salvando…" : fatura ? "Salvar" : "Abrir fatura"}</button>
          <button type="button" className="btn-ghost fv-btn" onClick={onClose}><X size={14} aria-hidden /> Cancelar</button>
        </div>
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
    } catch (e) {
      const x = e as ErroApi;
      if (x.status === 409 && x.detail?.codigo === "divergencia_total") setDiverge(true); else setErro(msgErro(e, "Erro ao fechar."));
    } finally { setSalvando(false); }
  }
  return (
    <Modal title={`Fechar fatura — ${fatura.rotulo}`} onClose={onClose} width="640px">
      <div className="fv-modal">
        <dl className="fv-fatos">
          <div><dt>Notas</dt><dd>{fatura.notas}</dd></div>
          <div><dt>Soma das notas</dt><dd>{formatBRL(soma)}</dd></div>
        </dl>
        <div className="mt-3" style={{ maxWidth: "300px" }}>
          <label className="fv-lbl" htmlFor="fec-tf">Total da fatura informado pelo fornecedor (opcional)</label>
          <CampoMoeda id="fec-tf" className="fv-in dir" value={totalForn} onChange={setTotalForn} />
        </div>
        {dif !== null && (
          <p className={dif === 0 ? "fv-ok" : "fv-ruim"} style={{ marginTop: "0.45rem" }} aria-live="polite">
            {dif === 0 ? <CheckCircle2 size={14} aria-hidden /> : <AlertTriangle size={14} aria-hidden />}
            {dif === 0 ? "Confere com a fatura do fornecedor." : `Diferença de ${formatBRL(Math.abs(dif))}${dif > 0 ? " a menos nas notas" : " a mais nas notas"}.`}</p>
        )}
        <fieldset style={{ border: 0, padding: 0, margin: "0.9rem 0 0" }}>
          <legend className="fv-lbl">Como fechar</legend>
          <div className="fv-opcoes">
            {([["vista", "À vista (vencimento único)"], ["parcelar", "Parcelar a fatura"]] as const).map(([v, r]) => (
              <label key={v} className="fv-opcao">
                <input type="radio" name="fec-modo" checked={modo === v} disabled={doCadastro && v === "vista"} onChange={() => setModo(v)} /> {r}</label>
            ))}
          </div>
        </fieldset>
        {doCadastro && <p className="fv-nota">O parcelamento foi definido no cadastro da fatura e não pode ser alterado aqui. Para mudar, edite o cadastro.</p>}
        <div className="mt-3">
          {modo === "vista"
            ? <div style={{ maxWidth: "240px" }}><label className="fv-lbl" htmlFor="fec-v">Vencimento</label><input id="fec-v" type="date" className="fv-in" value={venc} onChange={(e) => setVenc(e.target.value)} /></div>
            : <CamposParcelamento p={parc} set={setParc} desabilitado={doCadastro} />}
        </div>
        {modo === "parcelar" && previa.length > 0 && (
          <div className="fv-tw mt-3">
            <table className="fazenda-table" aria-label="Prévia das parcelas">
              <thead><tr><th>Parcela</th><th>Vencimento</th><th className="r">Valor</th></tr></thead>
              <tbody>{previa.map((x) => <tr key={x.n}><td>Parcela {x.n}</td><td className="fv-num">{br(x.venc)}</td><td className="r fv-num">{formatBRL(x.valor)}</td></tr>)}</tbody>
            </table>
          </div>
        )}
        {erro && <Erro texto={erro} />}
        {diverge && (
          <div className="fv-aviso venc" role="alert">
            <AlertTriangle size={16} aria-hidden />
            <div>
              <p style={{ color: "inherit", marginBottom: "0.5rem" }}>O total das notas não confere com o total do fornecedor. Fechar mesmo assim?</p>
              <button type="button" className="btn-primary" disabled={salvando} onClick={() => fechar(true)}>Fechar mesmo assim</button>
            </div>
          </div>
        )}
        <div className="fv-rodape">
          <button type="button" className={diverge ? "btn-secondary" : "btn-primary"} disabled={salvando} onClick={() => fechar()}><Lock size={14} aria-hidden /> {salvando ? "Fechando…" : "Fechar fatura"}</button>
          <button type="button" className="btn-ghost fv-btn" onClick={onClose}><X size={14} aria-hidden /> Cancelar</button>
        </div>
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
    try { await onConfirmar(motivo.trim()); } catch (e) { setErro(msgErro(e, "Erro.")); } finally { setSalvando(false); }
  }
  return (
    <Modal title={titulo} onClose={onClose} width="520px">
      <div className="fv-modal">
        <div className="fv-aviso logo" style={{ marginTop: 0, marginBottom: "0.8rem" }}><Info size={16} aria-hidden /><span>{aviso}</span></div>
        <label className="fv-lbl" htmlFor="mot-t">Motivo (obrigatório)</label>
        <textarea id="mot-t" className="fv-in" style={{ minHeight: "80px" }} value={motivo} aria-invalid={!!erro} aria-describedby={erro ? "mot-erro" : undefined} onChange={(e) => setMotivo(e.target.value)} />
        {erro && <div id="mot-erro"><Erro texto={erro} /></div>}
        <div className="fv-rodape">
          <button type="button" className="btn-primary" disabled={salvando} onClick={ok}><Check size={14} aria-hidden /> {salvando ? "Aguarde…" : rotuloBotao}</button>
          <button type="button" className="btn-ghost fv-btn" onClick={onClose}><X size={14} aria-hidden /> Cancelar</button>
        </div>
      </div>
    </Modal>
  );
}

// ───────────────────────── Pagar parcela ─────────────────────────
function ModalPagar({ fatura, parcela, onClose, onFeita }: { fatura: FaturaDetalhe; parcela: number; onClose: () => void; onFeita: (f: FaturaDetalhe, aviso?: string) => void }) {
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
  const rateio = useMemo(() => previaRateio(fatura, parcela, valorPago), [fatura, parcela, valorPago]);
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
        catch (e) { aviso = ` A parcela foi paga, mas o comprovante não subiu (${msgErro(e, "erro")}). Anexe pelas notas.`; }
      }
      onFeita(r, aviso ? aviso.trim() : undefined);
    } catch (e) { setErro(msgErro(e, "Erro ao pagar.")); } finally { setSalvando(false); }
  }
  return (
    <Modal title={`Pagar parcela ${parcela}/${fatura.parcelas.length} — ${fatura.rotulo}`} onClose={onClose} width="680px">
      <div className="fv-modal">
        <p style={{ marginBottom: "0.8rem" }}>Vencimento {br(p.vencimento)} · valor <strong className="fv-num">{formatBRL(p.valor)}</strong>. O pagamento baixa a parcela de todas as {fatura.notas} notas.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div><label className="fv-lbl" htmlFor="pg-v">Valor pago</label><CampoMoeda id="pg-v" className="fv-in dir" value={valorPago} onChange={setValorPago} /></div>
          <div><label className="fv-lbl" htmlFor="pg-d">Data do pagamento</label><input id="pg-d" type="date" className="fv-in" value={data} onChange={(e) => setData(e.target.value)} /></div>
          <div><label className="fv-lbl" htmlFor="pg-c">Conta bancária</label>
            <select id="pg-c" className="fv-in" value={conta} onChange={(e) => setConta(e.target.value)}>
              <option value="">Selecione…</option>{contas.map((c) => <option key={c.id} value={c.rotulo}>{c.rotulo}</option>)}</select></div>
          <div><label className="fv-lbl" htmlFor="pg-f">Forma de pagamento</label>
            <select id="pg-f" className="fv-in" value={forma} onChange={(e) => setForma(e.target.value)}>{FORMAS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}</select></div>
          <div><label className="fv-lbl" htmlFor="pg-n">Nº do comprovante (opcional)</label><input id="pg-n" className="fv-in" value={doc} onChange={(e) => setDoc(e.target.value)} /></div>
          <div><label className="fv-lbl" htmlFor="pg-a">Comprovante (um arquivo para todas as notas)</label>
            <input id="pg-a" type="file" accept="image/*,application/pdf" className="fv-in" onChange={(e) => setArquivo(e.target.files?.[0] || null)} /></div>
        </div>
        <div className="fv-aviso">
          <Info size={16} aria-hidden />
          <div><b>Comprovante único, anexado às {fatura.notas} notas.</b>
            <p>Se o envio do comprovante falhar, o pagamento continua registrado; você anexa depois pelas notas.</p></div>
        </div>

        <section aria-labelledby="pg-rateio" style={{ marginTop: "0.9rem" }}>
          <div className="fv-sec-topo" style={{ marginBottom: "0.35rem" }}>
            <h3 id="pg-rateio" className="fv-tit">Prévia por nota</h3>
            {dif !== 0 && <Delta valor={dif} />}
          </div>
          {dif !== 0
            ? <p className="fv-nota" style={{ color: "var(--st-logo-fg)", marginTop: 0, marginBottom: "0.4rem" }} aria-live="polite">
                Valor {dif > 0 ? "acima" : "abaixo"} em {formatBRL(Math.abs(dif))}: a diferença será rateada proporcionalmente entre as notas.</p>
            : <p className="fv-nota" style={{ marginTop: 0, marginBottom: "0.4rem" }}>Sem diferença: cada nota recebe a sua parte da parcela.</p>}
          {rateio.length > 0 && (
            <div className="fv-tw">
              <table className="fazenda-table" aria-label="Rateio do pagamento por nota">
                <thead><tr><th>Nota</th><th className="r">Parte da parcela</th><th className="r">{dif < 0 ? "Desconto" : "Acréscimo"}</th><th className="r">Pago</th></tr></thead>
                <tbody>{rateio.map((x) => (
                  <tr key={x.nota.numero_lancamento || x.nota.numero_documento}>
                    <td>{x.nota.tipo_documento} {x.nota.numero_documento || "s/n"}<span className="fv-t2">{x.nota.numero_lancamento}</span></td>
                    <td className="r fv-num">{formatBRL(x.parte)}</td>
                    <td className="r fv-num">{x.rateio ? `${x.rateio > 0 ? "+" : "−"}${formatBRL(Math.abs(x.rateio))}` : "—"}</td>
                    <td className="r fv-num fv-forte">{formatBRL(x.pago)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </section>
        {erro && <Erro texto={erro} />}
        <div className="fv-rodape">
          <button type="button" className="btn-primary" disabled={salvando} onClick={pagar}><Check size={14} aria-hidden /> {salvando ? "Pagando…" : "Confirmar pagamento"}</button>
          <button type="button" className="btn-ghost fv-btn" onClick={onClose}><X size={14} aria-hidden /> Cancelar</button>
        </div>
      </div>
    </Modal>
  );
}

// ───────────────────────── Histórico ─────────────────────────
const EVENTO: Record<string, { rotulo: string; classe: string; icone: typeof Clock }> = {
  aberta: { rotulo: "Fatura aberta", classe: "fat", icone: Layers },
  editada: { rotulo: "Cadastro editado", classe: "", icone: Pencil },
  notas_lancadas: { rotulo: "Notas lançadas na fatura", classe: "fat", icone: FileText },
  notas_inseridas: { rotulo: "Notas inseridas na fatura", classe: "fat", icone: FileText },
  lote_lancado: { rotulo: "Notas lançadas em lote", classe: "fat", icone: FileText },
  nota_retirada: { rotulo: "Nota tirada da fatura", classe: "", icone: X },
  fechada: { rotulo: "Fatura fechada", classe: "aberto", icone: Lock },
  reaberta: { rotulo: "Fatura reaberta", classe: "fat", icone: RotateCcw },
  parcela_paga: { rotulo: "Parcela paga", classe: "pago", icone: CheckCircle2 },
  pagamento_estornado: { rotulo: "Pagamento estornado", classe: "venc", icone: Undo2 },
};
const quando = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

function ListaHistorico({ eventos }: { eventos: FaturaDetalhe["eventos"] }) {
  if (eventos.length === 0) return <p className="fv-msg">Sem eventos.</p>;
  return (
    <ul className="fv-hist">{eventos.map((e, i) => {
      const t = EVENTO[e.acao] || { rotulo: e.acao.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), classe: "", icone: Clock };
      const Icone = t.icone;
      return (
        <li key={i}>
          <span className={`ic ${t.classe}`}><Icone size={14} aria-hidden /></span>
          <div><b>{t.rotulo}</b>{e.detalhe && <span className="det">{e.detalhe}</span>}
            <small>{quando(e.em)}{e.usuario ? ` · ${e.usuario}` : ""}</small></div>
        </li>);
    })}</ul>
  );
}

// ───────────────────────── Ciclo Aberta → Fechada → Paga ─────────────────────────
function Ciclo({ f }: { f: FaturaDetalhe }) {
  const idx = { aberta: 0, fechada: 1, paga: 2 }[f.status];
  const fechouEm = f.eventos.find((e) => e.acao === "fechada")?.em?.slice(0, 10);
  const datas = [
    br(f.data_abertura),
    f.status === "aberta" ? (f.data_fechamento_prevista ? `previsto ${br(f.data_fechamento_prevista)}` : "—") : fechouEm ? br(fechouEm) : "—",
    f.status === "paga" ? br(f.paga_em) : "—",
  ];
  return (
    <ol className="fv-ciclo" aria-label="Ciclo da fatura">
      {(["Aberta", "Fechada", "Paga"] as const).map((n, i) => {
        const feito = i < idx || (i === idx && f.status === "paga");
        const atual = i === idx && !feito;
        return (
          <li key={n} className={`fv-passo${feito ? " feito" : ""}${atual ? " atual" : ""}`} aria-current={i === idx ? "step" : undefined}>
            <span className="fv-bola" aria-hidden>{feito ? <Check size={16} strokeWidth={3} /> : i + 1}</span>
            <span className="fv-rot">{n}</span>
            <span className="fv-dt">{datas[i]}</span>
            {atual && <span className="fv-agora">Etapa atual</span>}
            <span className="sr-only">{feito ? "(concluída)" : atual ? "(etapa atual)" : "(próxima)"}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ───────────────────────── Detalhe ─────────────────────────
type Acao = null | { t: "editar" } | { t: "fechar" } | { t: "reabrir" } | { t: "pagar"; parcela: number } | { t: "estornar"; parcela: number }
  | { t: "historico" } | { t: "excluir" } | { t: "tirar"; numero: string };

function Detalhe({ id, onVoltar, onMudou }: { id: number; onVoltar: () => void; onMudou: () => void }) {
  const [f, setF] = useState<FaturaDetalhe | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [acao, setAcao] = useState<Acao>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [lancando, setLancando] = useState(false);
  const carregar = useCallback(() => fetchFatura(id).then(setF).catch((e) => setErro(e.message)), [id]);
  useEffect(() => { carregar(); }, [carregar]);
  const atualizar = (nova: FaturaDetalhe) => { setF(nova); setAcao(null); onMudou(); };
  const voltar = <button type="button" className="btn-ghost fv-voltar" onClick={onVoltar}><ChevronLeft size={15} aria-hidden /> Faturas</button>;
  if (erro) return <div className="fv"><EstiloFatura />{voltar}<Erro texto={erro} className="" /></div>;
  if (!f) return <div className="fv"><EstiloFatura />{voltar}<p className="fv-msg" role="status">Carregando…</p></div>;
  const aberta = f.status === "aberta";
  const nenhumaPaga = f.parcelas.every((p) => !p.pago);
  const proxima = f.parcelas.find((p) => !p.pago);
  const pagoTotal = f.parcelas.reduce((s, p) => s + (p.pago ? p.valor_pago : 0), 0);
  const previstoPago = f.parcelas.reduce((s, p) => s + (p.pago ? p.valor : 0), 0);
  const difPago = Math.round((pagoTotal - previstoPago) * 100) / 100;
  const nPagas = f.parcelas.filter((p) => p.pago).length;
  const confere = f.total_fornecedor == null ? null : Math.abs(f.total_fornecedor - f.valor_total) < 0.005;
  async function tirar(numero: string) {
    try { atualizar(await tirarNotaDaFatura(id, numero)); } catch (e) { setErro(msgErro(e, "Erro ao tirar a nota da fatura.")); }
  }
  return (
    <div className="fv">
      <EstiloFatura />
      {voltar}
      <div className="fv-head">
        <div style={{ minWidth: 0 }}>
          <h2>{f.rotulo} <PilulaFatura s={f.status} /></h2>
          <p className="fv-sub">{f.fornecedor} · abertura {br(f.data_abertura)} · fechamento previsto {br(f.data_fechamento_prevista)} · {f.conta_bancaria || "sem conta"} · {f.centro_custo || "sem centro de custo"}</p>
        </div>
        <div className="fv-acoes">
          {aberta && <button type="button" className="btn-ghost fv-btn" onClick={() => setAcao({ t: "editar" })}><Pencil size={13} aria-hidden /> Editar cadastro</button>}
          {f.status === "fechada" && (nenhumaPaga
            ? <button type="button" className="btn-secondary" onClick={() => setAcao({ t: "reabrir" })}><RotateCcw size={13} aria-hidden /> Reabrir</button>
            : <button type="button" className="btn-secondary" disabled aria-describedby="fv-reabrir-dica" title="Há parcela paga: estorne antes de reabrir" style={{ opacity: 0.55, cursor: "not-allowed" }}><RotateCcw size={13} aria-hidden /> Reabrir</button>)}
          <button type="button" className="btn-ghost fv-btn" onClick={() => setAcao({ t: "historico" })}><History size={13} aria-hidden /> Histórico</button>
          {aberta && <button type="button" className="btn-ghost fv-btn fv-perigo" onClick={() => setAcao({ t: "excluir" })}><Trash2 size={13} aria-hidden /> Excluir</button>}
          {aberta && <button type="button" className="btn-primary" onClick={() => setAcao({ t: "fechar" })} disabled={f.notas === 0} title={f.notas === 0 ? "Lance ao menos uma nota para fechar" : undefined}><Lock size={13} aria-hidden /> Fechar fatura</button>}
        </div>
      </div>
      {f.status === "fechada" && !nenhumaPaga && <span id="fv-reabrir-dica" className="sr-only">Há parcela paga: estorne antes de reabrir.</span>}

      <section className="fv-pan" aria-label="Situação da fatura">
        <Ciclo f={f} />
        <hr className="fv-sep" />
        <dl className="fv-fatos">
          <div><dt>Notas</dt><dd>{f.notas}</dd></div>
          <div><dt>Soma das notas</dt><dd>{formatBRL(f.valor_total)}</dd></div>
          <div><dt>Total do fornecedor</dt>
            {f.total_fornecedor == null
              ? <dd className="fraco">{aberta ? "informar ao fechar" : "não informado"}</dd>
              : <dd>{formatBRL(f.total_fornecedor)} {confere
                  ? <span className="fv-ok"><CheckCircle2 size={13} aria-hidden /> confere</span>
                  : <span className="fv-ruim"><AlertTriangle size={13} aria-hidden /> diverge {formatBRL(Math.abs(f.total_fornecedor - f.valor_total))}</span>}</dd>}
          </div>
          {!aberta && <div><dt>Pago</dt><dd>{formatBRL(pagoTotal)} <Delta valor={difPago} /></dd></div>}
          {!aberta && f.parcelas.length > 0 && <div><dt>Parcelas</dt><dd>{nPagas} de {f.parcelas.length} {f.parcelas.length === 1 ? "paga" : "pagas"}</dd></div>}
          {aberta && <div><dt>Parcelamento</dt><dd className="fraco">{f.parcelas_n && f.parcelamento_origem === "cadastro" ? `${f.parcelas_n}x (definido no cadastro)` : "definido no fechamento"}</dd></div>}
        </dl>
      </section>

      {f.parcelas.length > 0 && !aberta && (
        <section aria-labelledby="fv-h-parc">
          <div className="fv-sec-topo"><h3 id="fv-h-parc" className="fv-tit">Parcelas</h3></div>
          <div className="fv-tw">
            <table className="fazenda-table">
              <thead><tr><th>#</th><th>Vencimento</th><th className="r">Valor</th><th>Situação</th><th className="r">Ação</th></tr></thead>
              <tbody>{f.parcelas.map((p) => (
                <tr key={p.parcela}>
                  <td className="fv-num">{p.parcela}/{f.parcelas.length}</td>
                  <td className="fv-num">{br(p.vencimento)}</td>
                  <td className="r fv-num fv-forte">{formatBRL(p.pago ? p.valor_pago : p.valor)}</td>
                  <td><span className="fv-sit"><PilulaParcela p={p} />{p.pago && <Delta valor={Math.round((p.valor_pago - p.valor) * 100) / 100} />}</span></td>
                  <td className="r">{p.pago
                    ? <button type="button" className="btn-ghost fv-btn fv-perigo fv-mini" onClick={() => setAcao({ t: "estornar", parcela: p.parcela })}><Undo2 size={12} aria-hidden /> Estornar</button>
                    : <button type="button" className={`${p === proxima ? "btn-primary" : "btn-secondary"} fv-mini`} onClick={() => setAcao({ t: "pagar", parcela: p.parcela })}><Wallet size={12} aria-hidden /> Pagar</button>}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </section>
      )}

      <section aria-labelledby="fv-h-notas">
        <div className="fv-sec-topo">
          <h3 id="fv-h-notas" className="fv-tit">Notas da fatura</h3>
          {aberta && !lancando && <button type="button" className="btn-secondary fv-mini" onClick={() => setLancando(true)}><Plus size={13} aria-hidden /> Lançar notas nesta fatura</button>}
        </div>
        {f.lista_notas.length === 0 ? <div className="fv-vazio"><FileText size={22} aria-hidden /><b>Nenhuma nota ainda.</b></div> : (
          <div className="fv-tw">
            <table className="fazenda-table">
              <thead><tr><th>Lançamento</th><th>Documento</th><th>Emissão</th><th className="r">Valor</th><th style={{ minWidth: 150 }}>Peso na fatura</th>{aberta && <th className="r">Ação</th>}</tr></thead>
              <tbody>{f.lista_notas.map((n) => {
                const peso = f.valor_total > 0 ? Math.max(0, Math.min(100, (n.valor / f.valor_total) * 100)) : 0;
                return (
                  <tr key={n.numero_lancamento || n.numero_documento}>
                    <td className="fv-num">{n.numero_lancamento}</td>
                    <td>{n.tipo_documento} {n.numero_documento || "s/n"}</td>
                    <td className="fv-num">{br(n.data_emissao)}</td>
                    <td className="r fv-num fv-forte">{formatBRL(n.valor)}</td>
                    <td><div className="fv-barra"><span aria-hidden><i style={{ width: `${peso}%` }} /></span><small>{Math.round(peso)}%</small></div></td>
                    {aberta && <td className="r">{n.numero_lancamento && <button type="button" className="btn-ghost fv-btn fv-mini" onClick={() => setAcao({ t: "tirar", numero: n.numero_lancamento! })}>Tirar da fatura</button>}</td>}
                  </tr>);
              })}</tbody>
            </table>
          </div>
        )}
      </section>

      {aberta && lancando && (
        <section className="fv-pan" aria-labelledby="fv-h-lancar">
          <div className="fv-sec-topo">
            <h3 id="fv-h-lancar" className="fv-tit">Lançar notas na fatura</h3>
            <button type="button" className="btn-ghost fv-btn fv-mini" onClick={() => setLancando(false)}><X size={13} aria-hidden /> Fechar formulário</button>
          </div>
          <FormLancamentoLote fatura={f} onLancado={() => { carregar(); onMudou(); }} />
        </section>
      )}

      {acao?.t === "editar" && <ModalCadastro fatura={f} onClose={() => setAcao(null)} onSalvo={atualizar} />}
      {acao?.t === "fechar" && <ModalFechar fatura={f} onClose={() => setAcao(null)} onFeita={atualizar} />}
      {acao?.t === "pagar" && <ModalPagar fatura={f} parcela={acao.parcela} onClose={() => setAcao(null)} onFeita={(nova, av) => { atualizar(nova); if (av) setAviso(av); }} />}
      {acao?.t === "reabrir" && <ModalMotivo titulo="Reabrir fatura" rotuloBotao="Reabrir" aviso="A fatura volta para aberta: as parcelas geradas no fechamento são desfeitas e novas notas podem entrar."
        onClose={() => setAcao(null)} onConfirmar={async (m) => atualizar(await reabrirFatura(id, m))} />}
      {acao?.t === "estornar" && <ModalMotivo titulo={`Estornar pagamento da parcela ${acao.parcela}`} rotuloBotao="Estornar" aviso="A parcela volta para 'a pagar' em todas as notas da fatura."
        onClose={() => setAcao(null)} onConfirmar={async (m) => atualizar(await estornarParcelaFatura(id, acao.parcela, m))} />}
      {acao?.t === "tirar" && (
        <Modal title="Tirar nota da fatura" onClose={() => setAcao(null)} width="520px">
          <div className="fv-modal">
            <p>Tirar a nota <strong>{acao.numero}</strong> da fatura? Ela continua lançada, só deixa de fazer parte da fatura.</p>
            <div className="fv-rodape">
              <button type="button" className="btn-primary" onClick={() => tirar(acao.numero)}><Check size={14} aria-hidden /> Tirar da fatura</button>
              <button type="button" className="btn-ghost fv-btn" onClick={() => setAcao(null)}><X size={14} aria-hidden /> Cancelar</button>
            </div>
          </div>
        </Modal>
      )}
      {acao?.t === "excluir" && (
        <Modal title="Excluir fatura" onClose={() => setAcao(null)} width="520px">
          <div className="fv-modal">
            <p>{f.notas > 0 ? `Esta fatura tem ${f.notas} nota(s). Você pode soltá-las (continuam lançadas, sem fatura) e excluir a fatura.` : "Excluir a fatura vazia?"}</p>
            <div className="fv-rodape">
              <button type="button" className="btn-ghost fv-perigo-cheio" onClick={async () => { try { await excluirFatura(id, f.notas > 0); onMudou(); onVoltar(); } catch (e) { setErro(msgErro(e, "Erro ao excluir a fatura.")); setAcao(null); } }}>
                <Trash2 size={14} aria-hidden /> {f.notas > 0 ? "Soltar notas e excluir" : "Excluir"}</button>
              <button type="button" className="btn-ghost fv-btn" onClick={() => setAcao(null)}><X size={14} aria-hidden /> Cancelar</button>
            </div>
          </div>
        </Modal>
      )}
      {acao?.t === "historico" && (
        <Modal title="Histórico da fatura" onClose={() => setAcao(null)} width="600px">
          <div className="fv-modal"><ListaHistorico eventos={f.eventos} /></div>
        </Modal>
      )}
      {aviso && (
        <Modal title="Comprovante não anexado" onClose={() => setAviso(null)} width="520px">
          <div className="fv-modal">
            <div className="fv-aviso logo" role="alert" style={{ marginTop: 0 }}><AlertTriangle size={16} aria-hidden /><span>{aviso}</span></div>
            <div className="fv-rodape"><button type="button" className="btn-primary" onClick={() => setAviso(null)}><Check size={14} aria-hidden /> Entendi</button></div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ───────────────────────── Lista ─────────────────────────
const FILTROS = [["aberta", "Abertas"], ["fechada", "Fechadas"], ["paga", "Pagas"], ["", "Todas"]] as const;

export function FaturasView() {
  const [todas, setTodas] = useState<FaturaResumo[] | null>(null);
  const [filtro, setFiltro] = useState<"" | FaturaStatus>("aberta");
  const [aberta, setAberta] = useState<number | null>(null);
  const [nova, setNova] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  // Uma leitura só (mesmo endpoint, sem filtro): a lista filtra na tela e os cards de resumo contam todas as situações.
  const carregar = useCallback(() => fetchFaturas().then((l) => { setTodas(l); setErro(null); }).catch((e) => setErro(e.message)), []);
  useEffect(() => { carregar(); }, [carregar]);
  const lista = useMemo(() => (todas ? todas.filter((x) => !filtro || x.status === filtro) : null), [todas, filtro]);
  const resumo = useMemo(() => {
    const por = (s: FaturaStatus) => (todas || []).filter((x) => x.status === s);
    const soma = (xs: FaturaResumo[]) => xs.reduce((t, x) => t + (x.valor_total || 0), 0);
    const ab = por("aberta"), fe = por("fechada"), pg = por("paga");
    return { ab, fe, pg, somaAb: soma(ab), somaFe: soma(fe), somaPg: soma(pg) };
  }, [todas]);
  const contagem = (v: "" | FaturaStatus) => (v === "" ? (todas || []).length : (todas || []).filter((x) => x.status === v).length);
  if (aberta !== null) return <Detalhe id={aberta} onVoltar={() => { setAberta(null); carregar(); }} onMudou={carregar} />;
  return (
    <div className="fv">
      <EstiloFatura />
      <div className="fv-head">
        <div style={{ minWidth: 0 }}>
          <h2>Gestão de faturas</h2>
          <p className="fv-sub">
            Cadastre a fatura do fornecedor (abertura, fechamento, vencimento) e lance as notas dentro dela ao longo do período. No fechamento ela vira à vista ou parcelada; o pagamento é por parcela.
          </p>
        </div>
        <div className="fv-acoes" style={{ width: "auto" }}>
          <button type="button" className="btn-primary" onClick={() => setNova(true)}><Plus size={14} aria-hidden /> Nova fatura</button>
        </div>
      </div>

      {todas && (
        <div className="fv-kpis" role="group" aria-label="Resumo das faturas">
          <div className={`st-kpi fv-k-fat${resumo.ab.length ? "" : " zero"}`}>
            <div className="l"><Layers size={13} aria-hidden /> Abertas</div>
            <div className="v">{resumo.ab.length ? formatBRL(resumo.somaAb) : "—"}</div>
            <div className="s">{plural(resumo.ab.length, "fatura", "faturas")} · recebendo notas</div>
          </div>
          <div className={`st-kpi aberto fv-k-aberto${resumo.fe.length ? "" : " zero"}`}>
            <div className="l"><Lock size={13} aria-hidden /> Fechadas</div>
            <div className="v">{resumo.fe.length ? formatBRL(resumo.somaFe) : "—"}</div>
            <div className="s">{plural(resumo.fe.length, "fatura", "faturas")} · pagas por parcela</div>
          </div>
          <div className={`st-kpi pago fv-k-pago${resumo.pg.length ? "" : " zero"}`}>
            <div className="l"><CheckCircle2 size={13} aria-hidden /> Pagas</div>
            <div className="v">{resumo.pg.length ? formatBRL(resumo.somaPg) : "—"}</div>
            <div className="s">{plural(resumo.pg.length, "fatura quitada", "faturas quitadas")}</div>
          </div>
          <div className="st-kpi">
            <div className="l"><Clock size={13} aria-hidden /> Em curso</div>
            <div className="v">{formatBRL(resumo.somaAb + resumo.somaFe)}</div>
            <div className="s">abertas + fechadas</div>
          </div>
        </div>
      )}

      <div className="fv-seg" role="group" aria-label="Filtrar por situação">
        {FILTROS.map(([v, r]) => (
          <button key={v} type="button" aria-pressed={filtro === v} onClick={() => setFiltro(v)}>{r}{todas && <span className="n"> · {contagem(v)}</span>}</button>))}
      </div>

      {erro && <Erro texto={erro} className="" />}
      {lista === null ? (!erro && <p className="fv-msg" role="status">Carregando…</p>) : lista.length === 0 ? (
        <div className="fv-vazio"><Layers size={22} aria-hidden />
          <span>Nenhuma fatura {filtro ? ROTULO_STATUS[filtro].toLowerCase() : ""}. Use &quot;Nova fatura&quot; para cadastrar a primeira.</span></div>
      ) : (
        <div className="fv-tw">
          <table className="fazenda-table">
            <thead><tr><th>Situação</th><th>Fatura</th><th>Período</th><th className="r">Notas</th><th className="r">Total</th><th className="r"><span className="sr-only">Ação</span></th></tr></thead>
            <tbody>{lista.map((x) => (
              <tr key={x.id} className="row-clickable" onClick={() => setAberta(x.id)}>
                <td><PilulaFatura s={x.status} /></td>
                <td className="fv-col-fat"><button type="button" className="fv-lk" onClick={(e) => { e.stopPropagation(); setAberta(x.id); }}>{x.rotulo}</button>
                  <span className="fv-t2">{x.fornecedor}</span></td>
                <td className="fv-num">{br(x.data_abertura)} → {br(x.data_fechamento_prevista)}</td>
                <td className="r fv-num">{x.notas}</td>
                <td className="r fv-num fv-forte">{formatBRL(x.valor_total)}</td>
                <td className="r"><button type="button" className="btn-ghost fv-btn fv-mini" aria-label={`Abrir a fatura ${x.rotulo}`} onClick={(e) => { e.stopPropagation(); setAberta(x.id); }}>Abrir</button></td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      {nova && <ModalCadastro onClose={() => setNova(false)} onSalvo={(f) => { setNova(false); carregar(); setAberta(f.id); }} />}
    </div>
  );
}
