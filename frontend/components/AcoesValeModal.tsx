"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, X } from "lucide-react";
import {
  fetchAcoesVale, executarAcaoVale, formatBRL,
  type ValeAcao, type ValeAcaoContexto, type ValeAcaoResultado,
} from "@/lib/api";
import { competenciaAlvoDoVale, previaEstorno, valorDaReversao } from "@/lib/desfazerValeRegras";
import { Modal } from "@/components/Modal";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

/**
 * As ações do dono sobre um vale — as mesmas do backend
 * (`POST /cadastro/vales/{id}/acoes`), nem uma a mais: reparcelar o saldo,
 * abater um valor, desconsiderar o vale DAQUELE mês, cancelar o vale inteiro,
 * e as três voltas atrás — estornar um abatimento lançado por engano, voltar
 * a descontar um mês desconsiderado e desfazer o cancelamento do vale.
 *
 * AS VOLTAS SÓ APARECEM QUANDO O SERVIDOR DIZ QUE SÃO POSSÍVEIS
 * (`acoes_disponiveis`): estornar exige abatimento lançado e parcela pendente
 * onde devolver o valor; reverter exige mês assumido com folha em aberto E um
 * lado do Financeiro que tenha volta segura (assunção que partiu um item de
 * nota não tem — ver `_desfazer_assuncao_no_financeiro`). Oferecer uma opção
 * que vai voltar 400 é pior que não oferecer: o dono clica achando que tem
 * saída e continua sem saber o que fazer. Quando a volta do cancelamento é
 * impossível, a tela diz POR QUE (`impedimento_reverter_cancelamento`) em vez
 * de ficar muda diante da ação mais destrutiva das seis.
 *
 * Desconsiderar e cancelar dizem, na própria tela, o que acontece do outro lado — o
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
   *  "Desconsiderar este mês" usa, sem o dono precisar escolher de novo.
   *
   *  OPCIONAL porque o modal também é aberto pelo card "Vales de funcionário",
   *  onde a linha é o vale INTEIRO e não um mês. Sem ela, o mês alvo vem do
   *  contexto do servidor: a primeira competência ainda PENDENTE do vale (ver
   *  `competenciaAlvo`) — nunca deduzida aqui, senão a tela escolheria um mês
   *  que o POST recusaria. */
  competencia?: string;
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
  // Estado próprio do estorno (não reaproveita `valor`, do abatimento): os
  // dois campos convivem na mesma tela e trocar de ação não pode carregar um
  // número que era de outra conta.
  const [valorEstorno, setValorEstorno] = useState("");
  const [competenciaReverter, setCompetenciaReverter] = useState("");
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    setCarregando(true);
    fetchAcoesVale(valeId)
      .then((ctx) => {
        setContexto(ctx);
        // Campos das voltas atrás já preenchidos com o caso inteiro — desfazer
        // um clique errado não pode exigir que o dono refaça a conta de
        // cabeça (o valor abatido, e o mês assumido, são o que ele quer
        // desfazer por completo).
        setValorEstorno(ctx.valor_abatido > 0 ? String(ctx.valor_abatido) : "");
        setCompetenciaReverter(ctx.competencias_revertiveis[0] || "");
        // Vale cancelado só tem uma ação possível — a volta do próprio
        // cancelamento —, então a tela já nasce nela em vez de num select de
        // uma opção só.
        if (ctx.status === "cancelado") setAcao("reverter_cancelamento");
      })
      .catch((e: any) => setErro(e.message || "Erro ao carregar o vale"))
      .finally(() => setCarregando(false));
  }, [valeId]);

  const saldo = contexto?.saldo_pendente ?? 0;
  // O mês que "Desconsiderar" vai marcar — regra pura, testada em
  // lib/desfazerValeRegras: da linha da folha quando o modal veio de lá, e da
  // primeira parcela PENDENTE segundo o servidor quando veio do card de vales.
  const competenciaAlvo = contexto ? competenciaAlvoDoVale(contexto, competencia) : (competencia || "");
  const previa = contexto ? previaEstorno(contexto, valorEstorno) : null;
  const valorRevertido = contexto ? valorDaReversao(contexto, competenciaReverter) : 0;
  const pode = (a: ValeAcao) => !!contexto?.acoes_disponiveis.includes(a);

  async function confirmar(confirmarTeto = false) {
    setErro(null);
    setSalvando(true);
    try {
      const corpo: any = { acao, motivo: motivo.trim() || undefined, confirmar: confirmarTeto || undefined };
      if (acao === "reparcelar") {
        corpo.parcelas = Number(parcelas) || 0;
        if (competenciaInicio) corpo.competencia_inicio = competenciaInicio;
      } else if (acao === "abater") {
        corpo.valor = Number(valor) || 0;
        if (contaCorrenteId) corpo.conta_corrente_id = Number(contaCorrenteId);
      } else if (acao === "desconsiderar_mes") {
        corpo.competencia = competenciaAlvo;
      } else if (acao === "estornar_abatimento") {
        // Em branco = o abatimento inteiro, que é o padrão do servidor —
        // mandar 0 seria pedir um estorno de nada e levar 400.
        if (valorEstorno.trim() !== "") corpo.valor = Number(valorEstorno) || 0;
      } else if (acao === "reverter_desconsideracao") {
        corpo.competencia = competenciaReverter;
      }
      const resultado = await executarAcaoVale(valeId, corpo);
      onFeito(resultado);
    } catch (e: any) {
      // O teto de 40% do salário: reparcelar em 1x era a forma mais direta de
      // empilhar o saldo inteiro num mês, e esta porta não avisava nada. O
      // aviso é confirmável — o dono pode ter motivo —, mas ele precisa
      // existir. Mesmo padrão de confirmação de criar/editar vale.
      if (e?.status === 409 && e?.detail?.competencias_excedidas) {
        const lista = e.detail.competencias_excedidas.map((c: any) => `${c.competencia} (${formatBRL(c.total)})`).join(", ");
        if (window.confirm(`${e.detail.mensagem}\n\nCompetências afetadas: ${lista}\n\nDeseja reparcelar mesmo assim?`)) {
          await confirmar(true);
          return;
        }
        setErro(null);
      } else {
        setErro(e.message || "Erro ao executar a ação");
      }
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
            /* Vale cancelado: nenhuma das outras ações o alcança (o saldo já
               virou despesa da fazenda), e a única saída é desfazer o próprio
               cancelamento. Quando nem essa é possível, a tela DIZ o motivo em
               vez de só sumir com o botão — era essa a diferença entre "não dá"
               e "não sei o que fazer". */
            <div className="space-y-2">
              <div style={{ fontSize: "0.82rem", color: "var(--amber)" }}>
                Este vale foi cancelado — o saldo deixou de ser cobrado e virou despesa da fazenda.
              </div>
              {pode("reverter_cancelamento") ? (
                <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                  Desfazer o cancelamento devolve o vale a ativo: {formatBRL(contexto.valor_assumido_fazenda)} voltam
                  a ser cobrados de {pessoaNome} nas competências que o cancelamento varreu, e o lançamento do vale
                  volta a ser vale no Financeiro. Mês que já estava desconsiderado antes do cancelamento continua
                  desconsiderado — cada um se desfaz pela sua própria ação.
                </div>
              ) : (
                <div style={{ fontSize: "0.78rem", color: "var(--red)" }}>
                  {contexto.impedimento_reverter_cancelamento
                    || "Não há como desfazer este cancelamento automaticamente."}
                </div>
              )}
            </div>
          ) : (
            <>
              <div>
                <label style={lbl}>O que fazer com este vale?</label>
                <select style={inputStyle} value={acao} onChange={(e) => { setAcao(e.target.value as ValeAcao); setErro(null); }}>
                  <option value="reparcelar">Reparcelar o saldo</option>
                  <option value="abater">Lançar desconto/abatimento</option>
                  <option value="desconsiderar_mes">Desconsiderar o vale em {competenciaAlvo}</option>
                  <option value="cancelar">Cancelar o vale inteiro</option>
                  {pode("estornar_abatimento") && (
                    <option value="estornar_abatimento">Estornar o abatimento lançado</option>
                  )}
                  {pode("reverter_desconsideracao") && (
                    <option value="reverter_desconsideracao">Voltar a descontar o mês desconsiderado</option>
                  )}
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

              {acao === "estornar_abatimento" && previa && (
                <div className="space-y-2">
                  <div>
                    <label style={lbl}>Valor a estornar (R$)</label>
                    <input type="number" min={0} step="0.01" style={inputStyle} value={valorEstorno}
                      onChange={(e) => setValorEstorno(e.target.value)} />
                  </div>
                  {/* O efeito EXATO antes de confirmar. Foi confirmar sem ver o
                      número que criou o problema que este estorno desfaz. */}
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Volta ao saldo a descontar {formatBRL(previa.valor)} — o saldo passa de{" "}
                    {formatBRL(previa.saldoAtual)} para {formatBRL(previa.saldoNovo)}, rateado entre as
                    parcelas pendentes na mesma proporção de hoje:
                    <table style={{ width: "100%", marginTop: "0.3rem" }}>
                      <tbody>
                        {previa.linhas.map((l) => (
                          <tr key={l.competencia}>
                            <td style={{ padding: "0.05rem 0.5rem 0.05rem 0" }}>{l.competencia}</td>
                            <td style={{ textAlign: "right" }}>{formatBRL(l.de)}</td>
                            <td style={{ paddingLeft: "0.5rem", color: "var(--text)" }}>→ {formatBRL(l.para)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--amber)" }}>
                    Se o abatimento foi lançado com devolução em conta bancária, aquele recebimento continua
                    no Financeiro e precisa ser excluído à mão — o vale não guarda qual lançamento é o dele.
                  </div>
                  {previa.impedimento && (
                    <div style={{ fontSize: "0.75rem", color: "var(--red)" }}>{previa.impedimento}</div>
                  )}
                </div>
              )}

              {acao === "reverter_desconsideracao" && (
                <div className="space-y-2">
                  <div>
                    <label style={lbl}>Mês que volta a ser descontado</label>
                    <select style={inputStyle} value={competenciaReverter}
                      onChange={(e) => setCompetenciaReverter(e.target.value)}>
                      {contexto.competencias_revertiveis.map((comp) => (
                        <option key={comp} value={comp}>{comp}</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {formatBRL(valorRevertido)} deixam de ser despesa da fazenda e voltam a ser descontados de{" "}
                    {pessoaNome} em {competenciaReverter}. O lançamento do vale no Financeiro volta a ser vale.
                  </div>
                </div>
              )}

              {(acao === "desconsiderar_mes" || acao === "cancelar") && (
                <div style={{ fontSize: "0.8rem", color: "var(--amber)", background: "rgba(217,119,6,0.1)", border: "1px solid var(--amber)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.75rem" }}>
                  <AlertTriangle size={14} style={{ display: "inline", marginRight: "0.3rem", verticalAlign: "-2px" }} />
                  {acao === "desconsiderar_mes"
                    ? `${pessoaNome} não será descontado em ${competenciaAlvo}: esse valor passa a ser despesa da fazenda no Financeiro.`
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
        {contexto && (contexto.status !== "cancelado" || pode("reverter_cancelamento")) && (
          <button type="button" className="btn-primary" disabled={salvando} onClick={() => confirmar()}>
            <Check size={14} />{" "}
            {salvando
              ? "Salvando…"
              : acao === "reverter_cancelamento" ? "Reverter o cancelamento" : "Confirmar"}
          </button>
        )}
        <button type="button" className="btn-ghost" onClick={onFechar}><X size={14} /> Fechar</button>
      </div>
    </Modal>
  );
}
