"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, X } from "lucide-react";
import {
  fetchAcoesVale, executarAcaoVale, formatBRL,
  type ValeAcao, type ValeAcaoContexto, type ValeAcaoResultado,
} from "@/lib/api";
import { Modal } from "@/components/Modal";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

/**
 * As quatro ações do dono sobre um vale que aparece na folha — as mesmas
 * quatro do backend (`POST /cadastro/vales/{id}/acoes`), nem uma a mais:
 * reparcelar o saldo, abater um valor, desconsiderar o vale DAQUELE mês e
 * cancelar o vale inteiro.
 *
 * As duas últimas dizem, na própria tela, o que acontece do outro lado — o
 * valor deixa de ser cobrança do funcionário e vira despesa da fazenda. Isso
 * não é enfeite: é a decisão que o dono tomou em palavras ("faz a conta
 * passar a ser da fazenda... e comunicar com o financeiro completo") e quem
 * clica precisa ver que é isso mesmo que vai acontecer, porque nenhuma das
 * duas se desfaz sozinha depois.
 *
 * O contexto (saldo, quais parcelas ainda dá para mexer, quais já estão
 * travadas por folha paga) vem do servidor no GET — a tela não recalcula
 * "pendente" por conta própria, senão discordaria da recusa que o POST daria.
 */
export default function AcoesValeModal({
  valeId, pessoaNome, competencia, contasCorrentes, onFeito, onFechar,
}: {
  valeId: number;
  pessoaNome: string;
  /** Competência da linha da folha de onde o modal foi aberto — é ela que
   *  "Desconsiderar este mês" usa, sem o dono precisar escolher de novo. */
  competencia: string;
  contasCorrentes: { id: number; rotulo: string }[];
  onFeito: (resultado: ValeAcaoResultado) => void;
  onFechar: () => void;
}) {
  const [contexto, setContexto] = useState<ValeAcaoContexto | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [acao, setAcao] = useState<ValeAcao>("reparcelar");
  const [parcelas, setParcelas] = useState("2");
  const [competenciaInicio, setCompetenciaInicio] = useState("");
  const [valor, setValor] = useState("");
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    setCarregando(true);
    fetchAcoesVale(valeId)
      .then(setContexto)
      .catch((e: any) => setErro(e.message || "Erro ao carregar o vale"))
      .finally(() => setCarregando(false));
  }, [valeId]);

  const saldo = contexto?.saldo_pendente ?? 0;

  async function confirmar() {
    setErro(null);
    setSalvando(true);
    try {
      const corpo: any = { acao, motivo: motivo.trim() || undefined };
      if (acao === "reparcelar") {
        corpo.parcelas = Number(parcelas) || 0;
        if (competenciaInicio) corpo.competencia_inicio = competenciaInicio;
      } else if (acao === "abater") {
        corpo.valor = Number(valor) || 0;
        if (contaCorrenteId) corpo.conta_corrente_id = Number(contaCorrenteId);
      } else if (acao === "desconsiderar_mes") {
        corpo.competencia = competencia;
      }
      const resultado = await executarAcaoVale(valeId, corpo);
      onFeito(resultado);
    } catch (e: any) {
      setErro(e.message || "Erro ao executar a ação");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal title={`Vale de ${pessoaNome}`} onClose={onFechar} width="560px">
      {carregando && (
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <Loader2 size={14} className="animate-spin" /> Carregando o vale…
        </p>
      )}

      {contexto && (
        <div className="space-y-3">
          <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
            Vale de {formatBRL(contexto.valor_total)} · saldo a descontar {formatBRL(saldo)}
            {contexto.valor_abatido > 0 && ` · já abatido ${formatBRL(contexto.valor_abatido)}`}
            {contexto.valor_assumido_fazenda > 0 && ` · assumido pela fazenda ${formatBRL(contexto.valor_assumido_fazenda)}`}
          </div>

          {contexto.status === "cancelado" ? (
            <div style={{ fontSize: "0.82rem", color: "var(--amber)" }}>
              Este vale já foi cancelado — o saldo virou despesa da fazenda e não há mais ações sobre ele.
            </div>
          ) : (
            <>
              <div>
                <label style={lbl}>O que fazer com este vale?</label>
                <select style={inputStyle} value={acao} onChange={(e) => { setAcao(e.target.value as ValeAcao); setErro(null); }}>
                  <option value="reparcelar">Reparcelar o saldo</option>
                  <option value="abater">Lançar desconto/abatimento</option>
                  <option value="desconsiderar_mes">Desconsiderar o vale em {competencia}</option>
                  <option value="cancelar">Cancelar o vale inteiro</option>
                </select>
              </div>

              {acao === "reparcelar" && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label style={lbl}>Em quantas parcelas</label>
                    <input type="number" min={1} style={inputStyle} value={parcelas} onChange={(e) => setParcelas(e.target.value)} />
                  </div>
                  <div>
                    <label style={lbl}>A partir da competência</label>
                    <input type="month" style={inputStyle} value={competenciaInicio}
                      onChange={(e) => setCompetenciaInicio(e.target.value)} />
                  </div>
                  <p style={{ gridColumn: "1 / -1", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Redistribui {formatBRL(saldo)} (o que ainda não foi descontado). Em branco, começa na primeira
                    competência ainda pendente. O que já caiu em folha paga não é mexido.
                  </p>
                </div>
              )}

              {acao === "abater" && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label style={lbl}>Valor a abater (R$)</label>
                    <input type="number" min={0} step="0.01" style={inputStyle} value={valor}
                      onChange={(e) => setValor(e.target.value)} />
                  </div>
                  <div>
                    <label style={lbl}>Devolveu em dinheiro? Conta que recebeu</label>
                    <select style={inputStyle} value={contaCorrenteId} onChange={(e) => setContaCorrenteId(e.target.value)}>
                      <option value="">Não houve devolução (perdão/concessão)</option>
                      {contasCorrentes.map((c) => <option key={c.id} value={c.id}>{c.rotulo}</option>)}
                    </select>
                  </div>
                  <p style={{ gridColumn: "1 / -1", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    O abatimento é rateado entre as parcelas pendentes, sem mudar o prazo. Com a conta informada,
                    entra também um recebimento no caixa — senão o dinheiro devolvido não apareceria em lugar nenhum.
                  </p>
                </div>
              )}

              {(acao === "desconsiderar_mes" || acao === "cancelar") && (
                <div style={{ fontSize: "0.8rem", color: "var(--amber)", background: "rgba(217,119,6,0.1)", border: "1px solid var(--amber)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.75rem" }}>
                  <AlertTriangle size={14} style={{ display: "inline", marginRight: "0.3rem", verticalAlign: "-2px" }} />
                  {acao === "desconsiderar_mes"
                    ? `${pessoaNome} não será descontado em ${competencia}: esse valor passa a ser despesa da fazenda no Financeiro.`
                    : `Todo o saldo de ${formatBRL(saldo)} deixa de ser cobrado de ${pessoaNome} e vira despesa da fazenda no Financeiro. O que já foi descontado em folha paga continua descontado.`}
                </div>
              )}

              <div>
                <label style={lbl}>Motivo (opcional, fica no histórico)</label>
                <input style={inputStyle} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
              </div>
            </>
          )}

          {contexto.parcelas.length > 0 && (
            <table style={{ width: "100%", fontSize: "0.76rem" }}>
              <tbody>
                {contexto.parcelas.map((p) => (
                  <tr key={p.id}>
                    <td style={{ padding: "0.1rem 0.5rem 0.1rem 0" }}>{p.competencia}</td>
                    <td style={{ textAlign: "right" }}>{formatBRL(p.valor)}</td>
                    <td style={{ paddingLeft: "0.5rem", color: "var(--text-muted)" }}>
                      {p.assumida_pela_fazenda
                        ? `assumida pela fazenda${p.motivo_assuncao ? ` — ${p.motivo_assuncao}` : ""}`
                        : p.competencia_paga ? "já descontada (folha paga)" : "pendente"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.5rem" }}>{erro}</p>}

      <div className="flex items-center gap-3 mt-3">
        {contexto && contexto.status !== "cancelado" && (
          <button type="button" className="btn-primary" disabled={salvando} onClick={confirmar}>
            <Check size={14} /> {salvando ? "Salvando…" : "Confirmar"}
          </button>
        )}
        <button type="button" className="btn-ghost" onClick={onFechar}><X size={14} /> Fechar</button>
      </div>
    </Modal>
  );
}
