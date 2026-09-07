"use client";
import { useState } from "react";
import { AlertTriangle, Check, Lock, Pencil, X } from "lucide-react";
import { Modal } from "@/components/Modal";
import { CampoMoeda } from "@/components/CampoMoeda";
import { formatBRL, pagarFolhaComVerbas, type LinhaHolerite, type PagarFolhaResultado } from "@/lib/api";
import { passoMes } from "@/lib/folhaCompetencia";
import {
  alteracoesDoPagamento, decisoesDisponiveis, diferencaPagamento, direcaoDoSalario, erroDasAlteracoes,
  erroDoPagamento, liquidoComAlteracoes, temDiferenca, verbaDaLinha, verbasPagaveis,
  MENSAGEM_SALARIO_MENOR, NOTA_SALARIO_MENOR,
  type DecisaoDiferenca, type VerbaDaFolha,
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
/** O botão da coluna de edição — "Editar" e o cadeado usam o MESMO desenho de
 *  propósito: os dois são a mesma ação (abrir a verba para valor distinto), e
 *  o que muda entre eles é só o aviso que aparece antes. */
const botaoEdicao: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.74rem", padding: "0.2rem 0.45rem",
};

/** Os destinos da diferença de uma parcela de vale, com as palavras do desenho
 *  aprovado pelo dono — a descrição de cada um diz o que acontece do OUTRO
 *  lado (saldo, Financeiro, competências seguintes), porque nenhuma das quatro
 *  se desfaz sozinha depois que a folha vira recibo. */
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
  {
    tipo: "acrescimo_avulso",
    titulo: "Lançar acréscimo avulso",
    descricao: "o excedente vira uma linha própria deste holerite e o vale fica com o mesmo saldo e o mesmo prazo",
  },
];

/**
 * Pagar a folha lançando, no ATO, valor distinto do previsto nas verbas —
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
 * A COLUNA DE EDIÇÃO (segunda rodada do pedido). Toda verba passou a ter um
 * dos dois estados: **Editar** nas medidas no mês (vale, bonificação,
 * gueltas, vale-transporte, desconto em folha, outros descontos) e um
 * **cadeado** nas determinadas pela lei ou pelo contrato (salário, INSS, IR,
 * aumento incorporado, indenização, reembolso, desconto de compra). O cadeado
 * NÃO bloqueia: avisa que a alteração vale daquele momento em diante e, se
 * confirmada, libera o campo. Quem classifica cada verba é
 * `lib/pagamentoFolhaRegras.ts` (com a classe das rubricas vindo do catálogo
 * do servidor) — esta tela só pinta.
 *
 * O SALÁRIO TEM DOIS POP-UPS PRÓPRIOS. Para MAIOR, o aviso de que aquele passa
 * a ser o novo salário daquele momento em diante (o servidor grava a diferença
 * como "aumento na folha" e ela sobe para `Pessoa.salario_base` — CLT,
 * art. 468). Para MENOR, a recusa, com um único botão Fechar: alteração
 * contratual lesiva ao empregado é NULA, então não existe "confirmar mesmo
 * assim" a oferecer.
 *
 * AS DECISÕES DE DIFERENÇA CONTINUAM SÓ NO VALE, e continuam sendo as do
 * PR #708 (o servidor chama as mesmas funções de `rh_vale_acoes.py`): é a
 * única verba que representa dívida da pessoa. Nas demais não há dívida — o
 * valor novo é simplesmente o valor novo.
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
  // A tabela continua mostrando TODAS as linhas do discriminado (menos o
  // líquido, que é o total e não uma verba); `verbaDaLinha` devolve null para
  // a que este sistema não sabe editar, e essa fica só de leitura.
  const linhas = registro.detalhe
    .filter((d) => d.tipo !== "liquido")
    .map((d) => ({ linha: d, verba: verbaDaLinha(d) }));
  const verbas = linhas.map((l) => l.verba).filter((v): v is VerbaDaFolha => v !== null);
  const verbasVale = verbasPagaveis(registro.detalhe);

  const [dataPagamento, setDataPagamento] = useState(() => new Date().toISOString().slice(0, 10));
  // Chaveado pela CHAVE da verba (ver `VerbaDaFolha.chave`), nunca pelo índice
  // da linha: reordenar o discriminado faria o valor digitado numa verba pular
  // para outra.
  const [valores, setValores] = useState<Record<string, number>>(
    () => Object.fromEntries(verbas.map((v) => [v.chave, v.previsto])),
  );
  // As verbas cujo cadeado já foi confirmado nesta sessão do pop-up. Viaja
  // junto no POST: o servidor exige a mesma marca (a trava não pode existir
  // só na tela).
  const [confirmadas, setConfirmadas] = useState<Set<string>>(() => new Set());
  const [avisoCadeado, setAvisoCadeado] = useState<VerbaDaFolha | null>(null);
  const [avisoSalario, setAvisoSalario] = useState<{ verba: VerbaDaFolha; valor: number } | null>(null);
  const [recusaSalario, setRecusaSalario] = useState(false);
  const [decisao, setDecisao] = useState<DecisaoDiferenca | null>(null);
  const [contaCorrenteId, setContaCorrenteId] = useState("");
  const [parcelas, setParcelas] = useState("2");
  const [competenciaInicio, setCompetenciaInicio] = useState(() => passoMes(registro.competencia, 1));
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  // A diferença que abre as decisões é SÓ a do vale — as demais verbas não são
  // dívida de ninguém, e "abater"/"a fazenda assume" não significam nada sobre
  // elas. O mapa por id de parcela é montado aqui porque é o contrato de
  // `diferencaPagamento`, que é a mesma função testada do PR #718.
  const valoresVale: Record<number, number> = {};
  for (const v of verbasVale) {
    const valor = valores[`vale:${v.parcelaId}`];
    if (valor !== undefined) valoresVale[v.parcelaId] = valor;
  }
  const diferenca = diferencaPagamento(verbasVale, valoresVale);
  const ha = temDiferenca(diferenca);
  const disponiveis = decisoesDisponiveis(diferenca);
  const liquido = liquidoComAlteracoes(registro.valor_liquido, verbas, valores);
  const nParcelas = Number(parcelas) || 0;
  const editavel = (v: VerbaDaFolha) => v.classe === "livre" || confirmadas.has(v.chave);

  function escolher(tipo: DecisaoDiferenca) {
    setDecisao(decisao === tipo ? null : tipo);
    setErro(null);
  }

  function confirmarCadeado(verba: VerbaDaFolha) {
    setConfirmadas((a) => new Set(a).add(verba.chave));
    setAvisoCadeado(null);
    setErro(null);
  }

  /** Volta a verba ao previsto — usado quando um aviso do salário é recusado. */
  function desfazer(verba: VerbaDaFolha) {
    setValores((a) => ({ ...a, [verba.chave]: verba.previsto }));
  }

  /**
   * Conferência do salário na SAÍDA do campo (ver `CampoMoeda.onBlur`): para
   * menor abre a recusa e devolve o valor anterior; para maior abre o aviso do
   * novo salário. Nunca a cada tecla — o campo digita pela direita e todo
   * valor intermediário é menor que o previsto.
   */
  function conferirSalario(verba: VerbaDaFolha, valor: number) {
    const direcao = direcaoDoSalario(verba.previsto, valor);
    if (direcao === "menor") { setRecusaSalario(true); desfazer(verba); return; }
    if (direcao === "maior") setAvisoSalario({ verba, valor });
  }

  async function confirmar(confirmarTeto = false) {
    const problema =
      erroDasAlteracoes(verbas, valores, confirmadas)
      || erroDoPagamento(diferenca, decisao, { parcelas: nParcelas, dataPagamento });
    if (problema) { setErro(problema); return; }
    setErro(null);
    setSalvando(true);
    try {
      const alteracoes = alteracoesDoPagamento(verbas, valores, confirmadas);
      const resultado = await pagarFolhaComVerbas(registro.id, {
        data_pagamento: dataPagamento,
        verbas: verbasVale.map((v) => ({
          parcela_id: v.parcelaId, valor_pago: valores[`vale:${v.parcelaId}`] ?? v.previsto,
        })),
        ...alteracoes,
        decisao: ha && decisao ? {
          tipo: decisao,
          conta_corrente_id: decisao === "abater" && contaCorrenteId ? Number(contaCorrenteId) : undefined,
          parcelas: decisao === "reparcelar" ? nParcelas : undefined,
          competencia_inicio: decisao === "reparcelar" ? competenciaInicio : undefined,
          motivo: motivo.trim() || undefined,
          confirmar: confirmarTeto || undefined,
        } : undefined,
      });
      onPago(resultado);
    } catch (e) {
      // O teto de 40% do salário ao REPARCELAR a diferença: "reparcelar em 1x"
      // no mês seguinte empilhava ali o saldo inteiro, sem aviso nenhum — esta
      // era uma das três portas que não conferiam o limite. Confirmável, como
      // nas demais portas do vale.
      const err = e as any;
      if (err?.status === 409 && err?.detail?.competencias_excedidas) {
        const lista = err.detail.competencias_excedidas
          .map((c: any) => `${c.competencia} (${formatBRL(c.total)})`).join(", ");
        if (window.confirm(`${err.detail.mensagem}\n\nCompetências afetadas: ${lista}\n\nDeseja reparcelar mesmo assim?`)) {
          setSalvando(false);
          await confirmar(true);
          return;
        }
        setErro(null);
      } else {
        setErro(e instanceof Error && e.message ? e.message : "Erro ao registrar o pagamento da folha");
      }
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal title={`Pagar — ${registro.pessoa_nome} · ${registro.competencia}`} onClose={onFechar} width="820px">
      <div className="space-y-3">
        <div style={{ maxWidth: 220 }}>
          <label style={lbl}>Data do pagamento</label>
          <input type="date" style={inputStyle} value={dataPagamento}
            onChange={(e) => { setDataPagamento(e.target.value); setErro(null); }} />
        </div>

        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
          As verbas marcadas <b>Editar</b> já aceitam valor distinto do previsto — o campo está aberto. As
          marcadas com{" "}
          <Lock size={11} style={{ display: "inline", verticalAlign: "-1px" }} /> são determinadas pela lei ou
          pelo contrato: também podem ser alteradas, mas a alteração vale daquele momento em diante — clique no
          cadeado e o aviso pergunta antes de liberar o campo.
        </p>

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={th}>Verba</th>
                <th style={th}>Referência</th>
                <th style={{ ...th, textAlign: "right" }}>Previsto</th>
                <th style={{ ...th, width: 110 }}>Edição</th>
                <th style={{ ...th, textAlign: "right", width: 150 }}>Pago agora</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map(({ linha: d, verba }, i) => {
                const previsto = d.desconto ?? d.provento ?? Math.abs(d.valor);
                const liberada = verba ? editavel(verba) : false;
                return (
                  <tr key={verba ? verba.chave : `linha:${i}`}>
                    <td style={td}>
                      {d.descricao || d.label}
                      {d.desconto ? <span style={{ color: "var(--text-muted)" }}> (desconto)</span> : null}
                    </td>
                    <td style={{ ...td, color: "var(--text-muted)", fontSize: "0.74rem" }}>{d.referencia || "—"}</td>
                    <td style={{ ...td, textAlign: "right" }}>{formatBRL(previsto)}</td>
                    <td style={td}>
                      {!verba ? (
                        <span style={{ color: "var(--text-muted)" }}>—</span>
                      ) : verba.classe === "livre" ? (
                        // Verba medida no mês: nada a avisar, o campo já está
                        // aberto e a palavra existe para o dono saber que pode.
                        <span style={{ ...botaoEdicao, color: "var(--text-muted)" }}
                          title="Verba medida no mês — o campo ao lado já está aberto">
                          <Pencil size={12} /> Editar
                        </span>
                      ) : liberada ? (
                        <span style={{ ...botaoEdicao, color: "var(--amber)" }} title="Alteração confirmada">
                          <Pencil size={12} /> Editar
                        </span>
                      ) : (
                        <button type="button" className="btn-ghost" style={botaoEdicao}
                          aria-label={`Alterar ${verba.descricao} — pede confirmação`}
                          onClick={() => setAvisoCadeado(verba)}>
                          <Lock size={12} />
                        </button>
                      )}
                    </td>
                    <td style={{ ...td, textAlign: "right" }}>
                      {verba ? (
                        <CampoMoeda
                          value={valores[verba.chave] ?? verba.previsto}
                          disabled={!liberada}
                          onChange={(v) => { setValores((a) => ({ ...a, [verba.chave]: v })); setErro(null); }}
                          onBlur={verba.classe === "salario" ? (v) => conferirSalario(verba, v) : undefined}
                          style={{ ...inputStyle, textAlign: "right", opacity: liberada ? 1 : 0.55 }}
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
          {Math.abs(liquido - registro.valor_liquido) > 0.005 && (
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
                : "Está sendo descontado mais vale do que o previsto — falta dizer o que é o excedente: antecipação do saldo ou cobrança própria deste mês."}
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

            {decisao === "acrescimo_avulso" && (
              <div style={{ marginTop: "0.6rem" }}>
                <p style={{ fontSize: "0.78rem", marginBottom: "0.4rem" }}>
                  {formatBRL(Math.abs(diferenca))} entram como <b>desconto avulso</b> neste holerite (CLT, art. 462
                  — desconto autorizado pelo empregado). O vale de {registro.competencia} continua com o mesmo
                  saldo e o mesmo prazo.
                </p>
                <label style={lbl}>Do que se trata (opcional, vai na linha do recibo)</label>
                <input style={{ ...inputStyle, maxWidth: 420 }} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
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
          <button type="button" className="btn-primary" disabled={salvando} onClick={() => confirmar()}>
            <Check size={14} /> {salvando ? "Pagando…" : "Confirmar pagamento"}
          </button>
          <button type="button" className="btn-ghost" onClick={onFechar}><X size={14} /> Cancelar</button>
        </div>
      </div>

      {/* O cadeado: avisa e pergunta — nunca bloqueia. */}
      {avisoCadeado && (
        <Modal title="Alterar esta verba?" onClose={() => setAvisoCadeado(null)} width="480px" zIndex={95}>
          <div className="space-y-3" style={{ fontSize: "0.85rem" }}>
            <p>
              <b>{avisoCadeado.descricao}</b> é uma verba determinada pela lei ou pelo contrato de trabalho.
              Alterar este valor <b>será tido como alteração daquele momento em diante</b>.
            </p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
              Previsto nesta competência: {formatBRL(avisoCadeado.previsto)}.
            </p>
            <p>Tem certeza?</p>
            <div className="flex items-center gap-3">
              <button type="button" className="btn-primary" onClick={() => confirmarCadeado(avisoCadeado)}>
                <Check size={14} /> Tenho certeza, quero alterar
              </button>
              <button type="button" className="btn-ghost" onClick={() => setAvisoCadeado(null)}>
                <X size={14} /> Cancelar
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* Salário para MAIOR: informa que aquele passa a ser o novo salário. */}
      {avisoSalario && (
        <Modal title="Novo salário do funcionário" onClose={() => { desfazer(avisoSalario.verba); setAvisoSalario(null); }}
          width="500px" zIndex={95}>
          <div className="space-y-3" style={{ fontSize: "0.85rem" }}>
            <p>
              O valor informado ({formatBRL(avisoSalario.valor)}) é superior ao salário atual de{" "}
              {registro.pessoa_nome} ({formatBRL(avisoSalario.verba.previsto)}). Ele{" "}
              <b>passará a ser o novo salário daquele momento em diante</b>.
            </p>
            <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
              A diferença de {formatBRL(avisoSalario.valor - avisoSalario.verba.previsto)} entra como
              “Aumento na folha” nesta competência e passa a integrar o salário-base do cadastro (CLT, art. 468 —
              alteração benéfica ao empregado, que não se desfaz sozinha no mês seguinte). As competências já
              pagas não são alteradas.
            </p>
            <div className="flex items-center gap-3">
              <button type="button" className="btn-primary" onClick={() => setAvisoSalario(null)}>
                <Check size={14} /> Entendi, é um aumento
              </button>
              <button type="button" className="btn-ghost"
                onClick={() => { desfazer(avisoSalario.verba); setAvisoSalario(null); }}>
                <X size={14} /> Cancelar
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/*
        Salário para MENOR: SÓ o botão Fechar, e a frase é a que o dono ditou.
        Não há "confirmar mesmo assim" a oferecer — alteração contratual lesiva
        ao empregado é NULA (CLT, art. 468), e um botão de confirmar ofereceria
        um ato que a lei não reconhece. A nota em itálico e letra menor diz onde
        a redução PODE ser feita quando ela é legítima.
      */}
      {recusaSalario && (
        <Modal title="Alteração não permitida" onClose={() => setRecusaSalario(false)} width="520px" zIndex={95}>
          <div className="space-y-3">
            <p style={{ fontSize: "0.88rem" }}>{MENSAGEM_SALARIO_MENOR}</p>
            <p style={{ fontSize: "0.74rem", fontStyle: "italic", color: "var(--text-muted)" }}>
              {NOTA_SALARIO_MENOR}
            </p>
            <div className="flex items-center gap-3">
              <button type="button" className="btn-ghost" onClick={() => setRecusaSalario(false)}>
                <X size={14} /> Fechar
              </button>
            </div>
          </div>
        </Modal>
      )}
    </Modal>
  );
}
