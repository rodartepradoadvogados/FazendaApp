"use client";
import { useState } from "react";
import { AlertTriangle, Check, X } from "lucide-react";
import { Modal } from "@/components/Modal";
import { CampoMoeda } from "@/components/CampoMoeda";
import { formatBRL, pagarFolhaComVerbas, type LinhaHolerite, type PagarFolhaResultado } from "@/lib/api";
import { passoMes } from "@/lib/folhaCompetencia";
import {
  decisoesDisponiveis, diferencaPagamento, erroDoPagamento, liquidoComDiferenca, temDiferenca,
  verbasPagaveis, type DecisaoDiferenca,
} from "@/lib/pagamentoFolhaRegras";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
const th: React.CSSProperties = {
  fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.05em",
  color: "var(--text-muted)", fontWeight: 600, textAlign: "left", padding: "0.3rem 0.5rem 0.3rem 0",
};
const td: React.CSSProperties = { padding: "0.4rem 0.5rem 0.4rem 0", borderTop: "1px solid var(--border)", fontSize: "0.8rem" };

/** Os três destinos da diferença, com as palavras do desenho aprovado pelo
 *  dono — a descrição de cada um diz o que acontece do OUTRO lado (saldo,
 *  Financeiro, competências seguintes), porque nenhuma das três se desfaz
 *  sozinha depois que a folha vira recibo. */
const OPCOES: { tipo: DecisaoDiferenca; titulo: string; descricao: string }[] = [
  {
    tipo: "abater",
    titulo: "Lançar como desconto",
    descricao: "abate do saldo devedor do funcionário; se houver conta corrente, entra como devolução no caixa",
  },
  {
    tipo: "desconsiderar",
    titulo: "Desconsiderar — a fazenda assume",
    descricao: "deixa de ser cobrança do funcionário e vira despesa normal, comunicada ao financeiro",
  },
  {
    tipo: "reparcelar",
    titulo: "Reparcelar o saldo",
    descricao: "redistribui a diferença nas competências seguintes",
  },
];

/**
 * Pagar a folha lançando, no ATO, valor distinto do previsto numa verba —
 * pedido literal do dono, repetido duas vezes: "no ato do pagamento, deve ser
 * possível clicar no vale ou outra verba, lançar valor distinto e a diferença,
 * em pop up, decidir se é desconto, desconsiderar, re-parcelar".
 *
 * POR QUE NO ATO, E NÃO DEPOIS. Folha paga é fotografia: a discriminação é
 * congelada no pagamento e nada nela pode ser editado. Se a decisão viesse
 * depois, o holerite já teria sido emitido cobrando um desconto que não
 * aconteceu. Por isso este pop-up substitui o antigo "só a data" — a decisão
 * roda no servidor antes do congelamento, na mesma requisição.
 *
 * AS TRÊS DECISÕES SÃO AS DO VALE (PR #708), não uma segunda implementação: o
 * servidor chama as mesmas funções de `rh_vale_acoes.py`. O que muda aqui é o
 * gatilho — quem define a diferença é o valor efetivamente descontado agora.
 *
 * SÓ PARCELA DE VALE É EDITÁVEL (ver `verbasPagaveis`): é a única verba que é
 * dívida da pessoa. Salário, INSS, IR e rubricas aparecem na lista, com a
 * referência, mas em leitura — corrigi-los é editar o lançamento, o que se faz
 * antes de pagar e tem o próprio aviso de líquido diferente.
 */
export default function PagarFolhaModal({
  registro, contasCorrentes, onPago, onFechar,
}: {
  registro: {
    id: number; pessoa_nome: string; competencia: string; valor_liquido: number; detalhe: LinhaHolerite[];
  };
  contasCorrentes: { id: number; rotulo: string }[];
  onPago: (resultado: PagarFolhaResultado) => void;
  onFechar: () => void;
}) {
  const verbas = verbasPagaveis(registro.detalhe);
  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  const [valores, setValores] = useState<Record<number, number>>(
    () => Object.fromEntries(verbas.map((v) => [v.parcelaId, v.previsto])),
  );
  const [decisao, setDecisao] = useState<DecisaoDiferenca | null>(null);
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [parcelas, setParcelas] = useState("2");
  const [competenciaInicio, setCompetenciaInicio] = useState(() => passoMes(registro.competencia, 1));
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const diferenca = diferencaPagamento(verbas, valores);
  const ha = temDiferenca(diferenca);
  const disponiveis = decisoesDisponiveis(diferenca);
  const liquido = liquidoComDiferenca(registro.valor_liquido, diferenca);
  const nParcelas = Number(parcelas) || 0;

  function escolher(tipo: DecisaoDiferenca) {
    setDecisao(decisao === tipo ? null : tipo);
    setErro(null);
  }

  async function confirmar() {
    const problema = erroDoPagamento(diferenca, decisao, { parcelas: nParcelas, dataPagamento });
    if (problema) { setErro(problema); return; }
    setErro(null);
    setSalvando(true);
    try {
      const resultado = await pagarFolhaComVerbas(registro.id, {
        data_pagamento: dataPagamento,
        verbas: verbas.map((v) => ({ parcela_id: v.parcelaId, valor_pago: valores[v.parcelaId] ?? v.previsto })),
        decisao: ha && decisao ? {
          tipo: decisao,
          conta_corrente_id: decisao === "abater" && contaCorrenteId ? Number(contaCorrenteId) : undefined,
          parcelas: decisao === "reparcelar" ? nParcelas : undefined,
          competencia_inicio: decisao === "reparcelar" ? competenciaInicio : undefined,
          motivo: motivo.trim() || undefined,
        } : undefined,
      });
      onPago(resultado);
    } catch (e) {
      setErro(e instanceof Error && e.message ? e.message : "Erro ao registrar o pagamento da folha");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal title={`Pagar — ${registro.pessoa_nome} · ${registro.competencia}`} onClose={onFechar} width="760px">
      <div className="space-y-3">
        <div style={{ maxWidth: 220 }}>
          <label style={lbl}>Data do pagamento</label>
          <input type="date" style={inputStyle} value={dataPagamento}
            onChange={(e) => { setDataPagamento(e.target.value); setErro(null); }} />
        </div>

        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
          {verbas.length
            ? "Clique no valor do vale para pagar diferente do previsto. As demais verbas são do lançamento — para mudá-las, use “Editar lançamento” antes de pagar."
            : "Esta folha não tem vale a descontar — não há verba com valor a ajustar no pagamento."}
        </p>

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}>Verba</th>
                <th style={th}>Referência</th>
                <th style={{ ...th, textAlign: "right" }}>Previsto</th>
                <th style={{ ...th, textAlign: "right", width: 150 }}>Pago agora</th>
              </tr>
            </thead>
            <tbody>
              {registro.detalhe.filter((d) => d.tipo !== "liquido").map((d, i) => {
                const verba = verbas.find(
                  (v) => d.origem && "parcela_id" in d.origem && v.parcelaId === d.origem.parcela_id,
                );
                const previsto = d.desconto ?? d.provento ?? Math.abs(d.valor);
                return (
                  <tr key={i}>
                    <td style={td}>
                      {d.descricao || d.label}
                      {d.desconto ? <span style={{ color: "var(--text-muted)" }}> (desconto)</span> : null}
                    </td>
                    <td style={{ ...td, color: "var(--text-muted)", fontSize: "0.74rem" }}>{d.referencia || "—"}</td>
                    <td style={{ ...td, textAlign: "right" }}>{formatBRL(previsto)}</td>
                    <td style={{ ...td, textAlign: "right" }}>
                      {verba ? (
                        <CampoMoeda
                          value={valores[verba.parcelaId] ?? verba.previsto}
                          onChange={(v) => { setValores((a) => ({ ...a, [verba.parcelaId]: v })); setErro(null); }}
                          style={{ ...inputStyle, textAlign: "right" }}
                        />
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div style={{ fontSize: "0.82rem", fontWeight: 600, textAlign: "right" }}>
          Líquido a pagar: {formatBRL(liquido)}
          {ha && (
            <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>
              {" "}(previsto {formatBRL(registro.valor_liquido)})
            </span>
          )}
        </div>

        {ha && (
          <div style={{
            border: "1px solid var(--amber)", background: "rgba(217,119,6,0.1)",
            borderRadius: "var(--r-sm)", padding: "0.7rem 0.85rem",
          }}>
            <p style={{ fontWeight: 700, fontSize: "0.85rem" }}>
              <AlertTriangle size={14} style={{ display: "inline", marginRight: "0.3rem", verticalAlign: "-2px" }} />
              Diferença de {formatBRL(Math.abs(diferenca))}
            </p>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
              {diferenca > 0
                ? "Está sendo descontado menos vale do que o previsto. Falta decidir o destino do que não foi descontado."
                : "Está sendo descontado mais vale do que o previsto — o excedente antecipa o saldo, e o que resta do vale precisa de novo prazo."}
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {OPCOES.filter((o) => disponiveis.includes(o.tipo)).map((o) => (
                <button key={o.tipo} type="button" className="btn-ghost" aria-pressed={decisao === o.tipo}
                  style={{
                    textAlign: "left", padding: "0.5rem 0.7rem",
                    borderLeft: decisao === o.tipo ? "3px solid var(--dourado)" : "3px solid transparent",
                    background: decisao === o.tipo ? "var(--surface-2)" : undefined,
                  }}
                  onClick={() => escolher(o.tipo)}>
                  <b style={{ fontSize: "0.82rem" }}>{o.titulo}</b>
                  <div style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "0.1rem" }}>{o.descricao}</div>
                </button>
              ))}
            </div>

            {decisao === "abater" && (
              <div style={{ marginTop: "0.6rem", maxWidth: 340 }}>
                <label style={lbl}>Devolveu em dinheiro? Conta que recebeu</label>
                <select style={inputStyle} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
                  <option value="">Não houve devolução (perdão/concessão)</option>
                  {contasCorrentes.map((cc) => <option key={cc.id} value={cc.id}>{cc.rotulo}</option>)}
                </select>
              </div>
            )}

            {decisao === "reparcelar" && (
              <div className="flex items-end gap-3" style={{ marginTop: "0.6rem", flexWrap: "wrap" }}>
                <div style={{ width: 150 }}>
                  <label style={lbl}>Em quantas parcelas</label>
                  <input type="number" min={1} style={inputStyle} value={parcelas}
                    onChange={(e) => { setParcelas(e.target.value); setErro(null); }} />
                </div>
                <div style={{ width: 180 }}>
                  <label style={lbl}>A partir da competência</label>
                  <input type="month" style={inputStyle} value={competenciaInicio}
                    onChange={(e) => setCompetenciaInicio(e.target.value)} />
                </div>
                {nParcelas >= 1 && (
                  <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", paddingBottom: "0.5rem" }}>
                    {nParcelas} × {formatBRL(Math.abs(diferenca) / nParcelas)} da diferença, somados ao saldo que restava
                  </span>
                )}
              </div>
            )}

            {decisao === "desconsiderar" && (
              <div style={{ marginTop: "0.6rem" }}>
                <p style={{ fontSize: "0.78rem", marginBottom: "0.4rem" }}>
                  {formatBRL(Math.abs(diferenca))} deixam de ser cobrados de {registro.pessoa_nome} e viram despesa da
                  fazenda no Financeiro. Não se desfaz sozinho depois.
                </p>
                <label style={lbl}>Motivo (opcional, fica no histórico)</label>
                <input style={{ ...inputStyle, maxWidth: 420 }} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
              </div>
            )}
          </div>
        )}

        {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}

        <div className="flex items-center gap-3">
          <button type="button" className="btn-primary" disabled={salvando} onClick={confirmar}>
            <Check size={14} /> {salvando ? "Pagando…" : "Confirmar pagamento"}
          </button>
          <button type="button" className="btn-ghost" onClick={onFechar}><X size={14} /> Cancelar</button>
        </div>
      </div>
    </Modal>
  );
}
