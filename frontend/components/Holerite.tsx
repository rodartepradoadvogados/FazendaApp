"use client";
import { useEffect, useState } from "react";
import { ExternalLink, Printer } from "lucide-react";
import { formatBRL, type LinhaHolerite } from "@/lib/api";
import {
  FORMA_PAGAMENTO_VALE, bloqueioDeImpressao, dataBR, ehOrigemRetencao, ehOrigemRubrica, ehOrigemVale,
  imprimirHolerite, linhasDoCorpo, seloDocumento, type Holerite as DocHolerite,
} from "@/lib/holerite";

/*
 * O documento — as quatro colunas do recibo de papel da fazenda:
 * Descrição · Referência · Vencimentos · Descontos.
 *
 * A coluna que faltava é a REFERÊNCIA, e é ela que muda a leitura: `155,68`
 * vira "INSS 7,78% sobre R$ 2.000,00", e `985,00` vira "Parcela 3 de 13 ·
 * vale de 12/03/2026". Antes disso, sete linhas de vale saíam escritas só
 * "Vale" e o total de −R$ 1.680,54 não dizia a que se referia.
 *
 * O que a tela acrescenta ao papel é a única coisa que o papel não pode ter:
 * cada linha é clicável e conta a própria história — de onde veio, quando,
 * qual documento, qual parcela de quantas, e o caminho até o lançamento no
 * extrato. A identificação é por `vale_id`, nunca pelo valor: dois vales com
 * parcela de mesmo valor no mesmo mês eram justamente o caso em que a busca
 * antiga terminava num palpite.
 *
 * A coluna `Cod.` do papel NÃO é reproduzida: é rubrica do sistema da
 * contabilidade e não existe tabela de verbas neste projeto. Numerar as
 * linhas produziria um código que ninguém consegue conferir contra nada —
 * pior, num documento de aparência oficial, do que não ter a coluna.
 */

const GRADE = "minmax(0, 2.4fr) minmax(0, 2.1fr) minmax(0, 1fr) minmax(0, 1fr)";

const cabecalhoCol: React.CSSProperties = {
  fontSize: "0.68rem", fontWeight: 700, color: "var(--thead-fg, var(--vinho))",
  letterSpacing: "0.02em", textTransform: "uppercase",
};

function Celula({ children, alinhar, cor, forte }: {
  children: React.ReactNode; alinhar?: "right"; cor?: string; forte?: boolean;
}) {
  return (
    <div style={{
      fontSize: "0.8rem", textAlign: alinhar, color: cor,
      fontWeight: forte ? 700 : undefined, fontVariantNumeric: "tabular-nums",
    }}>{children}</div>
  );
}

/**
 * "No extrato" — o número do lançamento vira o CAMINHO até ele.
 *
 * O componente existia e ninguém o chamava: o cartão de origem escrevia o
 * número como texto solto, e quem quisesse conferir o lançamento tinha que
 * decorá-lo, sair do holerite, abrir o extrato e digitar de novo. O destino é
 * o mesmo endereço que a Agenda e o sino de notificações já usam
 * (`/financeiro?ir=…&ref=…`), agora apontando para o extrato completo, que é
 * onde um lançamento já pago aparece.
 */
export function LinkExtrato({ numero }: { numero: string | null }) {
  if (!numero) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  return (
    <a
      href={`/financeiro?ir=extrato&ref=${encodeURIComponent(numero)}`}
      className="flex items-center gap-1"
      style={{ fontSize: "0.8rem", color: "var(--dourado-light)" }}
      title={`Abrir o lançamento ${numero} no extrato completo`}
    >
      <ExternalLink size={11} /> {numero}
    </a>
  );
}

/** O cartão de origem — o que o clique numa linha abre. Um por vez. */
function CartaoOrigem({ linha }: { linha: LinhaHolerite }) {
  // Monta fechado e abre no quadro seguinte, para o CSS ter um estado inicial
  // real de onde animar (mesma técnica do formulário inline de Pessoas).
  const [aberto, setAberto] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => requestAnimationFrame(() => setAberto(true)));
    return () => cancelAnimationFrame(id);
  }, []);

  const origem = linha.origem;
  const campos: { rotulo: string; valor: React.ReactNode }[] = [];
  let titulo = linha.descricao;
  let sub = linha.referencia;

  if (ehOrigemVale(origem)) {
    titulo = `${linha.descricao} — ${formatBRL(origem.valor_total)}`;
    sub = origem.parcelas_total > 1
      ? `parcela ${origem.parcela} de ${origem.parcelas_total}`
      : "parcela única";
    campos.push({ rotulo: "Tirado em", valor: dataBR(origem.data_pagamento) });
    campos.push({ rotulo: "Forma", valor: FORMA_PAGAMENTO_VALE[origem.forma_pagamento] || origem.forma_pagamento });
    campos.push({ rotulo: "Observação", valor: origem.observacao || "—" });
    if (origem.origem_lancamento) {
      const o = origem.origem_lancamento;
      campos.push({ rotulo: "Nota", valor: [o.numero_documento, o.fornecedor_cliente].filter(Boolean).join(" — ") || "—" });
      campos.push({ rotulo: "Produto", valor: o.produto || "—" });
    }
    if (origem.numero_documento_pagamento) {
      campos.push({ rotulo: "Documento", valor: origem.numero_documento_pagamento });
    }
    campos.push({
      rotulo: "No extrato",
      // NULL por desenho quando a forma é `desconto_integral_folha`: não houve
      // saída de caixa. Dizer isso é o único jeito honesto de explicar a
      // ausência do link — sem inventar um lançamento que não existe.
      valor: origem.sem_saida_de_caixa
        ? <span style={{ color: "var(--text-muted)" }}>sem saída de caixa</span>
        : <LinkExtrato numero={origem.numero_lancamento_gerado || null} />,
    });
  } else if (ehOrigemRubrica(origem)) {
    // O enquadramento por extenso — é ele que explica por que esta linha
    // mexeu (ou não mexeu) no INSS logo acima, e o fundamento legal fica à
    // vista para o dono conferir com a contabilidade.
    titulo = `${origem.rotulo} — ${formatBRL(linha.provento || linha.desconto || 0)}`;
    sub = origem.especie === "vencimento" ? "vencimento acrescentado" : "desconto acrescentado";
    if (origem.especie === "vencimento") {
      campos.push({
        rotulo: "Natureza",
        valor: origem.natureza === "salarial" ? "Salarial" : "Indenizatória",
      });
      campos.push({
        rotulo: "Incidências",
        valor: origem.incide_inss
          ? "INSS, IRRF e FGTS"
          : <span style={{ color: "var(--text-muted)" }}>nenhuma</span>,
      });
      if (origem.incorpora_base && origem.competencia_incorporacao) {
        campos.push({ rotulo: "Vira salário-base em", valor: origem.competencia_incorporacao });
      }
    }
    if (origem.compra) {
      const co = origem.compra;
      campos.push({ rotulo: "Compra", valor: co.descricao || "—" });
      campos.push({ rotulo: "Fornecedor", valor: co.fornecedor_cliente || "—" });
      campos.push({ rotulo: "Nota", valor: co.numero_nota || "—" });
      campos.push({ rotulo: "Valor da compra", valor: formatBRL(co.valor_total) });
      campos.push({ rotulo: "No extrato", valor: <LinkExtrato numero={co.numero_lancamento || null} /> });
    }
    if (origem.fundamento) campos.push({ rotulo: "Fundamento", valor: origem.fundamento });
  } else if (ehOrigemRetencao(origem)) {
    titulo = `Retenção de ${linha.descricao} — ${formatBRL(linha.desconto || 0)}`;
    if (origem.percentual == null) {
      sub = "valor digitado direto no lançamento";
      campos.push({ rotulo: "Percentual", valor: "não informado" });
      campos.push({ rotulo: "Base", valor: "não declarada" });
      campos.push({ rotulo: "Confere?", valor: "sem base, não há o que conferir" });
    } else {
      sub = "conferida contra o bruto desta competência";
      campos.push({ rotulo: "Percentual", valor: `${String(origem.percentual).replace(".", ",")}%` });
      campos.push({ rotulo: "Sobre", valor: formatBRL(origem.base || 0) });
      campos.push({
        rotulo: "Confere?",
        valor: origem.confere
          ? "Sim — diferença de R$ 0,00"
          : <span style={{ color: "var(--amber)" }}>Não — {formatBRL(Math.abs(origem.diferenca || 0))} de diferença</span>,
      });
    }
  }

  return (
    <div className={`painel-expansivel${aberto ? " painel-expansivel-aberto" : ""}`}>
      <div>
        <div className="flash-localizado" style={{
          marginTop: "0.6rem", padding: "0.75rem 0.9rem", background: "var(--surface)",
          border: "1px solid var(--border)", borderLeft: "3px solid var(--dourado-light)",
          borderRadius: "var(--r-sm)",
        }}>
          <div className="flex items-baseline gap-2" style={{ flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--vinho)" }}>{titulo}</span>
            <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{sub}</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ marginTop: "0.6rem" }}>
            {campos.map((c) => (
              <div key={c.rotulo}>
                <div style={{ fontSize: "0.64rem", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                  {c.rotulo}
                </div>
                <div style={{ fontSize: "0.8rem", marginTop: "0.1rem" }}>{c.valor}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function Holerite({
  documento, compacto = false, cabecalho = true, acoes = true,
}: {
  documento: DocHolerite;
  /** Prévia dentro da linha da tabela (tela de Ações) — sem a folha de papel. */
  compacto?: boolean;
  cabecalho?: boolean;
  acoes?: boolean;
}) {
  // A linha aberta pertence a UM documento: guardamos a chave junto do estado
  // e zeramos durante a renderização quando o documento muda (padrão de
  // "ajustar estado quando a prop muda"). Fazer isso num efeito causaria uma
  // renderização em cascata — e, pior, um quadro em que o cartão de origem de
  // outra pessoa ainda aparece sob o nome novo.
  const [aberta, setAberta] = useState<{ chave: string; linha: string | null }>(
    { chave: documento.chave, linha: null },
  );
  const [formatoAberto, setFormatoAberto] = useState(false);
  const [exportando, setExportando] = useState(false);
  const linhaAberta = aberta.chave === documento.chave ? aberta.linha : null;
  if (aberta.chave !== documento.chave) setAberta({ chave: documento.chave, linha: null });
  const setLinhaAberta = (linha: string | null) => setAberta({ chave: documento.chave, linha });

  const corpo = linhasDoCorpo(documento.linhas);
  const selo = seloDocumento(documento);
  const bloqueio = bloqueioDeImpressao(documento);

  async function imprimir(formato: "pdf" | "excel") {
    setExportando(true);
    try {
      await imprimirHolerite(documento, formato);
    } catch {
      // erro já mostrado ao usuário dentro de lib/export.ts
    } finally {
      setExportando(false);
      setFormatoAberto(false);
    }
  }

  return (
    <div>
      {cabecalho && (
        <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
          <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--vinho)" }}>
            {documento.especie === "holerite" ? "Recibo de pagamento" : "Recibo"} — {documento.pessoaNome}
          </span>
          <span style={{
            padding: "0.1rem 0.45rem", borderRadius: "var(--r-sm)", background: selo.fundo, color: selo.cor,
            fontSize: "0.66rem", fontWeight: 700, letterSpacing: "0.04em",
          }}>{selo.texto}</span>
          <span style={{ flexGrow: 1 }} />
          {acoes && (
            <span style={{ position: "relative" }}>
              <button
                className="btn-ghost" type="button" style={{ fontSize: "0.75rem" }}
                disabled={!!bloqueio}
                title={bloqueio || `Imprimir o recibo de ${documento.pessoaNome}`}
                onClick={() => setFormatoAberto((v) => !v)}
              >
                <Printer size={13} /> Imprimir
              </button>
              {formatoAberto && !bloqueio && (
                <span className="flex items-center gap-1" style={{
                  position: "absolute", top: "100%", right: 0, zIndex: 5, background: "var(--surface-2)",
                  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem", whiteSpace: "nowrap",
                }}>
                  <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginRight: "0.2rem" }}>Formato:</span>
                  <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={exportando} onClick={() => imprimir("pdf")}>PDF</button>
                  <button className="btn-ghost" style={{ fontSize: "0.68rem" }} disabled={exportando} onClick={() => imprimir("excel")}>Excel</button>
                </span>
              )}
            </span>
          )}
        </div>
      )}

      <div style={{
        background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-md, 8px)",
        padding: compacto ? "0.75rem 0.9rem" : "1.25rem 1.4rem",
      }}>
        {!compacto && (
          <>
            <div style={{ textAlign: "center", fontSize: "0.95rem", fontWeight: 700, marginBottom: "0.8rem" }}>
              {documento.especie === "holerite" ? "Recibo de Pagamento Mensal" : "Recibo de Pagamento"}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1" style={{ paddingBottom: "0.6rem", borderBottom: "1px solid var(--border-strong, var(--border))" }}>
              <div style={{ fontSize: "0.82rem", fontWeight: 600 }}>{documento.pessoaNome}</div>
              <div style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>{documento.competenciaLabel}</div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                {documento.numeroLancamento ? `Lançamento ${documento.numeroLancamento}` : "Sem lançamento no extrato"}
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                {documento.status === "pago"
                  ? `Pago em ${dataBR(documento.dataPagamento)}`
                  : `Vencimento em ${dataBR(documento.dataVencimento)}`}
              </div>
            </div>
          </>
        )}

        <div style={{
          display: "grid", gridTemplateColumns: GRADE, gap: "0.5rem",
          padding: "0.5rem 0 0.4rem", borderBottom: "1px solid var(--border-strong, var(--border))",
        }}>
          <div style={cabecalhoCol}>Descrição</div>
          <div style={cabecalhoCol}>Referência</div>
          <div style={{ ...cabecalhoCol, textAlign: "right" }}>Vencimentos</div>
          <div style={{ ...cabecalhoCol, textAlign: "right" }}>Descontos</div>
        </div>

        {corpo.map((l, i) => {
          const chave = `${l.tipo}-${i}`;
          const clicavel = !!l.origem;
          const aberta = linhaAberta === chave;
          return (
            <div key={chave}>
              <div
                className={clicavel ? "row-clickable" : undefined}
                onClick={clicavel ? () => setLinhaAberta(aberta ? null : chave) : undefined}
                title={clicavel ? "Clique para ver de onde veio este valor" : undefined}
                style={{
                  display: "grid", gridTemplateColumns: GRADE, gap: "0.5rem",
                  padding: "0.45rem 0", borderBottom: "1px dotted var(--border)",
                  alignItems: "center", cursor: clicavel ? "pointer" : undefined,
                }}
              >
                <Celula>{l.descricao}</Celula>
                <Celula cor="var(--text-muted)">{l.referencia}</Celula>
                <Celula alinhar="right">{l.provento ? formatBRL(l.provento) : ""}</Celula>
                <Celula alinhar="right" cor={l.desconto ? "var(--red)" : undefined}>
                  {l.desconto ? formatBRL(l.desconto) : ""}
                </Celula>
              </div>
              {aberta && <CartaoOrigem linha={l} />}
            </div>
          );
        })}

        <div style={{
          display: "grid", gridTemplateColumns: GRADE, gap: "0.5rem",
          padding: "0.5rem 0", borderTop: "1px solid var(--border-strong, var(--border))", marginTop: "0.15rem",
        }}>
          <Celula forte>Totais</Celula>
          <div />
          <Celula alinhar="right" forte>{formatBRL(documento.totais.total_proventos)}</Celula>
          <Celula alinhar="right" forte cor="var(--red)">{formatBRL(documento.totais.total_descontos)}</Celula>
        </div>

        {/* Nunca "Líquido: −1.680,54" em vermelho: um número negativo ali tem
            aparência de resultado válido. O que existe é um excedente. */}
        <div className="flex items-baseline gap-3" style={{
          justifyContent: "flex-end", padding: "0.55rem 0.6rem",
          background: documento.totais.liquido_negativo
            ? "color-mix(in srgb, var(--red) 8%, transparent)" : "var(--surface-2)",
          borderRadius: "var(--r-sm)", marginTop: "0.4rem", flexWrap: "wrap",
        }}>
          <span style={{
            fontSize: "0.8rem", fontWeight: 600,
            color: documento.totais.liquido_negativo ? "var(--red)" : "var(--vinho)",
          }}>
            {documento.totais.liquido_negativo ? "Os descontos excedem os vencimentos em" : "Líquido"}
          </span>
          <span style={{
            fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums",
            color: documento.totais.liquido_negativo ? "var(--red)" : "var(--vinho)",
          }}>
            {formatBRL(documento.totais.liquido_negativo ? documento.totais.excedente : documento.totais.liquido)}
          </span>
        </div>

        {bloqueio && (
          <p style={{ fontSize: "0.75rem", color: "var(--red)", marginTop: "0.5rem" }}>{bloqueio}</p>
        )}

        {/* O MÊS QUE A FAZENDA ASSUMIU — explicação, não linha do documento.
            Fica DEPOIS do líquido, fora das quatro colunas e fora de
            `corpo`/`linhasDoCorpo`, porque nenhum centavo daqui é desconto de
            ninguém: entrar no corpo seria entrar nos totais, no líquido e no
            PDF. Está aqui porque, sem isso, quem abre o holerite nesta tela
            (só consulta, sem o painel de ações do fechamento da folha) via o
            desconto de vale simplesmente sumir do mês, sem uma palavra.
            Nenhum botão de ação: desfazer é decisão que se toma em Ações >
            Fechamento da folha, ou no card "Vales de funcionário". */}
        {documento.valeAssumido.length > 0 && (
          <div style={{
            marginTop: "0.6rem", padding: "0.5rem 0.65rem", borderRadius: "var(--r-sm)",
            background: "var(--surface-2)", border: "1px dotted var(--border)",
          }}>
            <div style={{ fontSize: "0.72rem", fontWeight: 700, color: "var(--text-muted)", marginBottom: "0.25rem" }}>
              Vale assumido pela fazenda — não descontado nesta folha
            </div>
            {documento.valeAssumido.map((v, i) => (
              <div key={`assumido-${i}`} className="flex items-baseline gap-2" style={{ flexWrap: "wrap" }}>
                <span style={{ fontSize: "0.78rem" }}>{v.descricao}</span>
                <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
                  {v.referencia}{v.motivo ? ` · ${v.motivo}` : ""}
                </span>
                <span style={{ flexGrow: 1 }} />
                <span
                  title="A fazenda assumiu este valor: ele não foi descontado do funcionário e não entra em nenhum total deste recibo."
                  style={{
                    fontSize: "0.78rem", color: "var(--text-muted)", textDecoration: "line-through",
                    fontVariantNumeric: "tabular-nums",
                  }}
                >{formatBRL(v.valor_assumido)}</span>
              </div>
            ))}
            <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
              Este valor virou despesa da fazenda no Financeiro e por isso não aparece entre os descontos acima.
            </div>
          </div>
        )}

        {/* Rodapé: só o que o banco sustenta. As bases de contribuição do
            holerite de papel (Sal. Cont. INSS, Base Calc. FGTS, Base Calc.
            IRRF) NÃO são reproduzidas — não são armazenadas, e a de IRRF é
            inderivável (falta dependentes na pessoa e a tabela progressiva).
            Campo vazio num documento de aparência oficial lê como zero. */}
        {!compacto && documento.bases && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3" style={{
            paddingTop: "0.7rem", marginTop: "0.7rem", borderTop: "1px solid var(--border)",
          }}>
            <div>
              <div style={{ fontSize: "0.64rem", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                Salário base da folha
              </div>
              <div style={{ fontSize: "0.82rem", fontVariantNumeric: "tabular-nums" }}>{formatBRL(documento.bases.salario_base)}</div>
            </div>
            {documento.bases.base_inss != null && (
              <div>
                <div style={{ fontSize: "0.64rem", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                  Base do INSS informada
                </div>
                <div style={{ fontSize: "0.82rem", fontVariantNumeric: "tabular-nums" }}>{formatBRL(documento.bases.base_inss)}</div>
              </div>
            )}
            {documento.bases.fgts_projetado != null && (
              <div>
                <div style={{ fontSize: "0.64rem", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                  FGTS projetado
                </div>
                <div style={{ fontSize: "0.82rem", fontVariantNumeric: "tabular-nums" }}>
                  {formatBRL(documento.bases.fgts_projetado)}
                  {documento.bases.percentual_fgts ? ` (${String(documento.bases.percentual_fgts).replace(".", ",")}%)` : ""}
                </div>
              </div>
            )}
          </div>
        )}

        {documento.observacao && (
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>Obs.: {documento.observacao}</p>
        )}

        {!compacto && (
          <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", lineHeight: 1.5, marginTop: "0.7rem", paddingTop: "0.55rem", borderTop: "1px dotted var(--border)" }}>
            Recibo interno de controle da fazenda. Não substitui o holerite emitido pela contabilidade e não apura
            bases fiscais — os valores de INSS, IR e FGTS são os informados no lançamento, conferidos contra o
            salário desta competência quando há percentual.
          </p>
        )}
      </div>

      {/* O painel de rubricas NÃO mora mais aqui. Ele é o único jeito de
          acrescentar vencimento/desconto a um holerite, e por isso passou a
          viver na tela onde se FECHA a folha (Ações > Fechamento da folha),
          composto ao lado do documento — ver FolhaPagamentoView.tsx. Em
          Contas > Holerites e recibos o documento é só leitura. */}

      {!linhaAberta && corpo.some((l) => !!l.origem) && (
        <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
          Clique em qualquer linha para ver de onde ela veio — a data, o documento e o caminho até o lançamento no extrato.
        </p>
      )}
    </div>
  );
}
