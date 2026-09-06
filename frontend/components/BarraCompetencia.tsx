"use client";
import { ChevronLeft, ChevronRight, CalendarRange } from "lucide-react";
import { competenciaExtenso } from "@/lib/holerite";
import { passoMes, type SituacaoMes } from "@/lib/folhaCompetencia";

/*
 * A barra do mês — o objeto da tela de fechamento.
 *
 * POR QUE ELA EXISTE. A tela abria sem mês nenhum: dois campos de data soltos
 * ("Vencimento — de/até") governando três KPIs que somavam o que passasse
 * pelo filtro. A pergunta que o dono faz todo mês ("posso fechar setembro?")
 * não tinha onde ser feita, porque não havia mês na tela — havia um filtro.
 *
 * O mês aqui é o mês em que o dinheiro SAI (pago: o mês do pagamento;
 * pendente: o do vencimento), que é o único critério que os cinco tipos
 * sustentam. A competência (mês trabalhado) é coisa só do funcionário e vem
 * escrita embaixo, com as que realmente caem no mês — nunca "mês anterior"
 * por dedução, porque o dia de vencimento é configurável por lançamento.
 *
 * O que esta barra NÃO tem, de propósito: um botão "Fechar o mês". Não existe
 * fechamento de competência no banco (nenhum campo em FolhaPagamento marca um
 * mês como fechado) — o botão seria um enfeite que não fecha nada.
 */

const rotuloBotao: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "center",
  width: "1.9rem", height: "1.9rem", borderRadius: "var(--r-sm)",
  border: "1px solid color-mix(in srgb, var(--card-header-fg) 30%, transparent)",
  background: "transparent", color: "var(--card-header-fg)", cursor: "pointer",
};

export function BarraCompetencia({
  mes, mesesComLancamento, competencias, situacao, quantidade, onMes,
}: {
  /** null = "todos os meses" (a barra não está governando). */
  mes: string | null;
  mesesComLancamento: string[];
  competencias: string[];
  situacao: SituacaoMes;
  quantidade: number;
  onMes: (mes: string | null) => void;
}) {
  const corSituacao = {
    vazio: "var(--text-muted)", pago: "var(--green-light)",
    aberto: "var(--amber)", bloqueado: "var(--red)",
  }[situacao.estado];

  return (
    <div
      className="flex items-center gap-3 mb-3"
      style={{
        background: "var(--card-header-bg)", color: "var(--card-header-fg)",
        borderRadius: "var(--r-md, 8px)", padding: "0.7rem 0.9rem", flexWrap: "wrap",
      }}
    >
      <button
        type="button" style={rotuloBotao} title="Mês anterior"
        onClick={() => onMes(passoMes(mes || mesesComLancamento[0] || "", -1))}
        disabled={!mes && !mesesComLancamento.length}
      >
        <ChevronLeft size={16} />
      </button>

      <div style={{ minWidth: "11rem" }}>
        <div style={{ fontSize: "1rem", fontWeight: 700, letterSpacing: "-0.01em" }}>
          {mes ? competenciaExtenso(mes) : "Todos os meses"}
        </div>
        <div style={{ fontSize: "0.7rem", opacity: 0.72, marginTop: "0.05rem" }}>
          {mes
            ? (competencias.length
                // As competências REAIS das folhas do mês, não uma dedução.
                ? `${competencias.length === 1 ? "competência" : "competências"} ${competencias.join(", ")}`
                : "sem folha de funcionário neste mês")
            : `${mesesComLancamento.length} ${mesesComLancamento.length === 1 ? "mês" : "meses"} com lançamento`}
        </div>
      </div>

      <button
        type="button" style={rotuloBotao} title="Próximo mês"
        onClick={() => onMes(passoMes(mes || mesesComLancamento[0] || "", 1))}
        disabled={!mes && !mesesComLancamento.length}
      >
        <ChevronRight size={16} />
      </button>

      <span
        className="flex items-center gap-2"
        title={situacao.detalhe}
        style={{
          padding: "0.25rem 0.6rem", borderRadius: "999px",
          background: `color-mix(in srgb, ${corSituacao} 18%, transparent)`,
          border: `1px solid color-mix(in srgb, ${corSituacao} 45%, transparent)`,
        }}
      >
        <span style={{ width: "0.45rem", height: "0.45rem", borderRadius: "50%", background: corSituacao }} />
        <span style={{ fontSize: "0.75rem", fontWeight: 600 }}>{situacao.texto}</span>
      </span>

      <span style={{ flexGrow: 1 }} />

      <span style={{ fontSize: "0.72rem", opacity: 0.72 }}>
        {quantidade} {quantidade === 1 ? "lançamento" : "lançamentos"}
      </span>

      {/* Salto longo e escape: `<input type="month">` para ir direto a um mês
          distante, e "Todos" para voltar ao comportamento antigo da tela (ver
          tudo de uma vez) sem ter que caçar mês a mês. */}
      <input
        type="month" aria-label="Ir para um mês" value={mes || ""}
        onChange={(e) => onMes(e.target.value || null)}
        style={{
          fontSize: "0.74rem", padding: "0.25rem 0.4rem", borderRadius: "var(--r-sm)",
          border: "1px solid color-mix(in srgb, var(--card-header-fg) 30%, transparent)",
          background: "transparent", color: "var(--card-header-fg)", colorScheme: "dark",
        }}
      />
      <button
        type="button" className="flex items-center gap-1"
        title="Ver todos os meses de uma vez, sem a barra do mês"
        onClick={() => onMes(null)}
        style={{
          ...rotuloBotao, width: "auto", padding: "0 0.6rem", gap: "0.3rem",
          fontSize: "0.74rem", fontWeight: 600,
          background: mes ? "transparent" : "color-mix(in srgb, var(--card-header-fg) 16%, transparent)",
        }}
      >
        <CalendarRange size={13} /> Todos
      </button>
    </div>
  );
}
