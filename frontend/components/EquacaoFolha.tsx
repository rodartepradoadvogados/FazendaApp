"use client";
import { formatBRL } from "@/lib/api";
import type { EquacaoFolha as Equacao, ResumoTipo } from "@/lib/folhaCompetencia";

/*
 * A faixa da equação — o total do mês decomposto.
 *
 * POR QUE ELA EXISTE. O topo da tela eram três KPIs soltos (Lançamentos,
 * Pendente, Pago) que não formavam conta nenhuma: não havia identidade a
 * conferir, então um total errado não tinha como saltar aos olhos. Aqui os
 * números são lidos da esquerda para a direita COMO UMA CONTA, com os
 * operadores desenhados entre eles:
 *
 *     Vencimentos − Retenções − Vales [− Outros] = A pagar
 *
 * Cada parcela vem da MESMA discriminação que o recibo imprime (`detalhe`),
 * nunca de um segundo cálculo parecido — é isso que impede a faixa e o papel
 * de divergirem.
 *
 * "Fora da conta" fica FORA da identidade, à direita e em vermelho: uma folha
 * cujos descontos passam os vencimentos tem líquido negativo e, somada, REDUZIA
 * o total a pagar do mês — o erro se disfarçava de bom número.
 *
 * A coluna "Outros descontos" só aparece quando existe: `FolhaPagamento.
 * descontos` é um float solto, sem itemização possível (não há modelo filho
 * nem FK), e uma célula fixa em R$ 0,00 gastaria espaço para não dizer nada.
 */

const LABEL_TIPO: Record<string, string> = {
  empreita: "Empreitas", contrato: "Contratos", diaria: "Diárias", ferias_decimo: "Férias e 13º",
};

const rotulo: React.CSSProperties = {
  fontSize: "0.64rem", fontWeight: 700, letterSpacing: "0.06em",
  textTransform: "uppercase", color: "var(--text-muted)",
};
const numero: React.CSSProperties = {
  fontSize: "1.15rem", fontWeight: 700, fontVariantNumeric: "tabular-nums", marginTop: "0.15rem",
};
const nota: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.05rem" };

function Operador({ sinal }: { sinal: string }) {
  return (
    <div
      aria-hidden
      style={{
        display: "flex", alignItems: "center", padding: "0 0.7rem",
        fontSize: "1.1rem", color: "var(--border-strong, var(--border))",
      }}
    >
      {sinal}
    </div>
  );
}

function Parcela({ titulo, valor, sub, cor }: { titulo: string; valor: number; sub: string; cor?: string }) {
  return (
    <div style={{ flexGrow: 1, minWidth: "8rem" }}>
      <div style={{ ...rotulo, color: cor || rotulo.color }}>{titulo}</div>
      <div style={{ ...numero, color: cor }}>{formatBRL(valor)}</div>
      <div style={{ ...nota, color: cor || nota.color }}>{sub}</div>
    </div>
  );
}

export function EquacaoFolha({ eq }: { eq: Equacao }) {
  if (!eq.folhas) {
    return (
      <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
        Nenhuma folha de funcionário neste mês — a equação da competência (vencimentos, retenções, vales e
        líquido) só existe para folha mensal. Empreita, contrato, diária e férias/13º são pagamentos de valor
        único e aparecem abaixo.
      </p>
    );
  }

  const situacao = [
    eq.pagas ? `${eq.pagas} paga${eq.pagas > 1 ? "s" : ""}` : "",
    eq.aVencer ? `${eq.aVencer} a vencer` : "",
    eq.vencidas ? `${eq.vencidas} vencida${eq.vencidas > 1 ? "s" : ""}` : "",
  ].filter(Boolean).join(" · ");

  return (
    <div
      className="flex items-stretch mb-3"
      style={{
        background: "var(--surface)", border: "1px solid var(--border)",
        borderRadius: "var(--r-md, 8px)", padding: "0.85rem 1rem", flexWrap: "wrap", rowGap: "0.75rem",
      }}
    >
      <Parcela
        titulo="Vencimentos" valor={eq.vencimentos}
        sub={`${eq.folhas} folha${eq.folhas > 1 ? "s" : ""} de funcionário`}
      />
      <Operador sinal="−" />
      <Parcela titulo="Retenções" valor={eq.retencoes} sub="INSS e IR" />
      <Operador sinal="−" />
      <Parcela
        titulo="Vales" valor={eq.vales}
        sub={`${eq.parcelasVale} parcela${eq.parcelasVale === 1 ? "" : "s"}`}
      />
      {eq.outros > 0 && (
        <>
          <Operador sinal="−" />
          <Parcela titulo="Outros descontos" valor={eq.outros} sub="sem detalhamento gravado" />
        </>
      )}
      <Operador sinal="=" />
      <div style={{ flexGrow: 1.2, minWidth: "9rem", paddingLeft: "0.8rem", borderLeft: "3px solid var(--dourado)" }}>
        <div style={rotulo}>A pagar</div>
        <div style={{ ...numero, color: "var(--vinho)" }}>{formatBRL(eq.aPagar)}</div>
        <div style={nota}>{situacao || "—"}</div>
      </div>

      {eq.foraDaConta > 0 && (
        <div
          style={{
            flexGrow: 1, minWidth: "9rem", paddingLeft: "0.9rem", marginLeft: "0.9rem",
            borderLeft: "1px dashed var(--border-strong, var(--border))",
          }}
        >
          <div style={{ ...rotulo, color: "var(--red)" }}>Fora da conta</div>
          <div style={{ ...numero, color: "var(--red)" }}>{formatBRL(eq.foraDaConta)}</div>
          <div style={{ ...nota, color: "var(--red)" }}>
            {eq.folhasForaDaConta} folha{eq.folhasForaDaConta > 1 ? "s" : ""} em que os descontos passam os vencimentos
          </div>
        </div>
      )}
    </div>
  );
}

/*
 * "Também vence neste mês" — os quatro tipos que não têm competência.
 *
 * Ficam visualmente subordinados e NUNCA dividem coluna com a folha: é essa
 * separação que faz a coluna "Valor" parar de ter dois significados (ela
 * mostrava bruto para funcionário e líquido/parcela para os demais, e o total
 * somava o segundo). Empreita, contrato e diária não têm bruto e líquido
 * separados — o valor é o que se paga.
 */
export function OutrosPagamentosDoMes({ resumo }: { resumo: ResumoTipo[] }) {
  if (!resumo.length) return null;
  return (
    <>
      <div className="flex items-baseline gap-2 mb-2" style={{ flexWrap: "wrap" }}>
        <span style={rotulo}>Também vence neste mês</span>
        <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>
          pagamentos de valor único, sem composição mensal — aparecem na tabela abaixo junto das folhas
        </span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        {resumo.map((r) => (
          <div
            key={r.tipo}
            style={{
              background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: "var(--r-sm)", padding: "0.65rem 0.8rem",
            }}
          >
            <div style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{LABEL_TIPO[r.tipo] || r.tipo}</div>
            <div style={{ fontSize: "1rem", fontWeight: 700, fontVariantNumeric: "tabular-nums", marginTop: "0.1rem" }}>
              {formatBRL(r.total)}
            </div>
            <div style={{ fontSize: "0.7rem", color: r.vencidos ? "var(--red)" : "var(--text-muted)", marginTop: "0.05rem" }}>
              {r.quantidade} lançamento{r.quantidade > 1 ? "s" : ""}
              {r.pagos === r.quantidade ? " · todos pagos" : ` · ${r.quantidade - r.pagos} a pagar`}
              {r.vencidos ? ` · ${r.vencidos} vencido${r.vencidos > 1 ? "s" : ""}` : ""}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
