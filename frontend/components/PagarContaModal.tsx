"use client";
// Janela ÚNICA de pagamento de uma conta a pagar (ContaGerencial), usada no
// Fechamento da folha (contrato, empreita, diária), na Agenda ("Contas a
// pagar") e em Ações > Pagamento — o pagamento fica igual em todo lugar.
// Baixa pelo mesmo endpoint de "Ações > Pagamento" (PUT /financeiro/
// lancamentos/{id}/pagar), com comprovante anexado à própria conta.
import { useEffect, useState } from "react";
import { Receipt, X } from "lucide-react";
import { Modal } from "@/components/Modal";
import { CampoMoeda } from "@/components/CampoMoeda";
import { Dropzone } from "@/components/Dropzone";
import { RetencaoCaixaCampos } from "@/components/RetencaoCaixaCampos";
import {
  anexarArquivoLancamentoPorId, fetchOpcoesFinanceiro, formatBRL, formatDate, marcarPagoFinanceiro, type RetencaoCaixaIn,
} from "@/lib/api";

const FORMAS = [
  { value: "pix", label: "Pix" }, { value: "transferencia", label: "Transferência" }, { value: "debito", label: "Débito" },
  { value: "credito", label: "Crédito" }, { value: "dinheiro", label: "Dinheiro" }, { value: "boleto", label: "Boleto" },
];

const lbl = { display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: "0.2rem" } as const;
const campo = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.82rem",
} as const;

export type ContaParaPagar = {
  /** id da ContaGerencial (o `lancamento_id` das linhas). */
  lancamentoId: number;
  titulo: string;
  /** Linha de contexto sob o título (ex.: "Contrato: Cerca · vence em 07/10/2026"). */
  detalhe?: string;
  valorPrevisto: number;
  dataVencimento?: string | null;
};

export function PagarContaModal({ conta, onClose, onPago }: {
  conta: ContaParaPagar; onClose: () => void; onPago: () => void;
}) {
  const hoje = new Date().toISOString().slice(0, 10);
  const [data, setData] = useState(hoje);
  const [valor, setValor] = useState(String(conta.valorPrevisto));
  const [forma, setForma] = useState("");
  const [contaBancaria, setContaBancaria] = useState("");
  const [vencCartao, setVencCartao] = useState("");
  const [numero, setNumero] = useState("");
  const [comprovante, setComprovante] = useState<File | null>(null);
  const [contas, setContas] = useState<string[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [retencao, setRetencao] = useState<RetencaoCaixaIn | null>(null);

  useEffect(() => {
    fetchOpcoesFinanceiro().then((d) => setContas(d.contas_bancarias || [])).catch(() => {});
  }, []);

  const diferenca = Math.round((Number(valor) - conta.valorPrevisto) * 100) / 100;

  async function confirmar() {
    setErro(null);
    if (!data) { setErro("Informe a data do pagamento."); return; }
    if (!(Number(valor) > 0)) { setErro("Informe o valor pago."); return; }
    if (forma === "credito" && !vencCartao) { setErro("Informe o vencimento do cartão."); return; }
    setSalvando(true);
    try {
      const corpo = {
        data_pagamento: data, valor_pago: Number(valor),
        conta_bancaria: contaBancaria || undefined, forma_pagamento: forma || undefined,
        numero_documento_pagamento: numero.trim() || undefined,
        data_vencimento_cartao: forma === "credito" ? vencCartao : undefined,
      };
      try {
        await marcarPagoFinanceiro(conta.lancamentoId, { ...corpo, retencao_caixa: retencao || undefined });
      } catch (e: any) {
        // Retenção acima do teto combinado: pergunta e, se confirmado, repete (a baixa ainda não foi gravada).
        if (e.status === 409 && e.detail?.codigo === "acima_do_teto" && retencao && window.confirm(`${e.detail.mensagem}`)) {
          await marcarPagoFinanceiro(conta.lancamentoId, { ...corpo, retencao_caixa: { ...retencao, confirmar_acima_teto: true } });
        } else throw e;
      }
    } catch (e: any) {
      setErro(e.message || "Não foi possível registrar o pagamento.");
      setSalvando(false);
      return;
    }
    // O pagamento já está gravado. Falha no anexo NUNCA o desfaz: avisa e fecha.
    if (comprovante) {
      try {
        await anexarArquivoLancamentoPorId(conta.lancamentoId, comprovante, "Comprovante de pagamento", numero.trim() || null, data);
      } catch (e: any) {
        window.alert(`Pagamento registrado, mas o comprovante não foi anexado (${e.message || "erro"}). Anexe pelo lançamento em Contas a pagar.`);
      }
    }
    setSalvando(false);
    onPago();
  }

  return (
    <Modal title="Registrar pagamento" onClose={onClose} width="520px">
      <p style={{ margin: "0 0 0.15rem", fontWeight: 600, fontSize: "0.92rem" }}>{conta.titulo}</p>
      <p style={{ margin: "0 0 0.8rem", color: "var(--text-muted)", fontSize: "0.78rem" }}>
        {conta.detalhe ? `${conta.detalhe} · ` : ""}
        {conta.dataVencimento ? `vence em ${formatDate(conta.dataVencimento)} · ` : ""}valor previsto {formatBRL(conta.valorPrevisto)}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div><label style={lbl} htmlFor="pc-data">Data do pagamento</label>
          <input id="pc-data" type="date" style={campo} value={data} onChange={(e) => setData(e.target.value)} /></div>
        <div><label style={lbl} htmlFor="pc-valor">Valor pago (R$)</label>
          <CampoMoeda style={campo} value={Number(valor) || 0} onChange={(v) => setValor(v ? String(v) : "")} /></div>
        <div><label style={lbl} htmlFor="pc-forma">Forma de pagamento</label>
          <select id="pc-forma" style={campo} value={forma} onChange={(e) => setForma(e.target.value)}>
            <option value="">Não informar</option>
            {FORMAS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
          </select></div>
        <div><label style={lbl} htmlFor="pc-conta">Conta bancária</label>
          <select id="pc-conta" style={campo} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
            <option value="">Não informar</option>
            {contas.map((c) => <option key={c} value={c}>{c}</option>)}
          </select></div>
        {forma === "credito" && (
          <div><label style={lbl} htmlFor="pc-cartao">Vencimento do cartão</label>
            <input id="pc-cartao" type="date" style={campo} value={vencCartao} onChange={(e) => setVencCartao(e.target.value)} /></div>
        )}
        <div><label style={lbl} htmlFor="pc-num">Nº do comprovante (opcional)</label>
          <input id="pc-num" style={campo} value={numero} onChange={(e) => setNumero(e.target.value)} placeholder="Ex.: código da transação Pix" /></div>
      </div>

      <div style={{ marginTop: "0.8rem" }}>
        <label style={lbl}>Comprovante de pagamento (opcional)</label>
        {comprovante ? (
          <div className="card" style={{ border: "1px solid var(--border)", padding: "0.55rem", display: "flex", alignItems: "center", gap: "0.5rem", justifyContent: "space-between" }}>
            <span style={{ fontSize: "0.78rem", wordBreak: "break-all" }}><Receipt size={13} style={{ display: "inline", marginRight: 4 }} />{comprovante.name}</span>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => setComprovante(null)}>
              <X size={12} /> Remover
            </button>
          </div>
        ) : (
          <Dropzone
            accept="application/pdf,image/jpeg,image/png"
            label="Arraste o comprovante aqui ou clique para selecionar"
            hint="PDF, JPG ou PNG"
            onFiles={(files) => setComprovante(files[0] || null)}
          />
        )}
      </div>

      <RetencaoCaixaCampos lancamentoId={conta.lancamentoId} bruto={Number(valor) || 0} data={data} onChange={setRetencao} />

      {diferenca !== 0 && (
        <p style={{ marginTop: "0.7rem", fontSize: "0.78rem", color: diferenca < 0 ? "var(--green-light)" : "var(--amber)" }}>
          {diferenca < 0 ? `Desconto de ${formatBRL(Math.abs(diferenca))}` : `Acréscimo de ${formatBRL(diferenca)}`} em relação ao previsto: fica registrado na própria conta.
        </p>
      )}
      {erro && <p role="alert" style={{ marginTop: "0.6rem", fontSize: "0.8rem", color: "var(--red)" }}>{erro}</p>}

      <div className="flex gap-2" style={{ justifyContent: "flex-end", marginTop: "1rem", flexWrap: "wrap" }}>
        <button type="button" className="btn-ghost" onClick={onClose} disabled={salvando}>Cancelar</button>
        <button type="button" className="btn-primary" onClick={confirmar} disabled={salvando}>
          {salvando ? "Registrando…" : "Confirmar pagamento"}
        </button>
      </div>
    </Modal>
  );
}
