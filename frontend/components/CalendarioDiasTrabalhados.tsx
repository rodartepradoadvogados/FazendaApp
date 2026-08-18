"use client";
import { useMemo } from "react";
import { Lock } from "lucide-react";
import { type DiasDiariaResposta, formatBRL } from "@/lib/api";

// Mesma data-math do calendário mensal de app/agenda/page.tsx (isoLocal +
// blank-leading-cells via getDay()/último-dia-do-mês via new Date(ano, mes+1, 0))
// — copiada de propósito em vez de importada: agenda/page.tsx não exporta
// esses helpers, e são poucas linhas autocontidas.
const NOMES_MES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
const DIAS_SEMANA_ABREV = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

function isoLocal(ano: number, mes: number, dia: number): string {
  return `${ano}-${String(mes + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
}
function parseIso(iso: string): { ano: number; mes: number; dia: number } {
  const [ano, mes, dia] = iso.split("-").map(Number);
  return { ano, mes: mes - 1, dia };
}

type Props = {
  dados: DiasDiariaResposta;
  diasNaoTrabalhados: Set<string>;
  diasMeiaDiaria: Set<string>;
  // Um clique cicla o dia entre os 3 estados: trabalhado -> folga -> meia
  // diária -> trabalhado (a lógica de qual Set mexer mora em DiariaView.tsx,
  // que é quem já possui os dois Sets).
  onClickDia: (iso: string) => void;
  // Atalhos "marcar todos" — setam o estado direto (não simulam cliques),
  // para não depender da ordem do ciclo em cada atalho.
  onMarcarTodos: (alvo: "trabalhado" | "folga" | "meia") => void;
  somenteLeitura?: boolean;
};

export default function CalendarioDiasTrabalhados({ dados, diasNaoTrabalhados, diasMeiaDiaria, onClickDia, onMarcarTodos, somenteLeitura = false }: Props) {
  const diasPorData = useMemo(() => {
    const m = new Map<string, DiasDiariaResposta["dias"][number]>();
    dados.dias.forEach((d) => m.set(d.data, d));
    return m;
  }, [dados.dias]);

  // Um <section> por mês do calendário — o período quase sempre é curto
  // (modo=ultimo_periodo), mas modo=completo pode cobrir vários meses.
  const meses = useMemo(() => {
    const ini = parseIso(dados.periodo_inicio);
    const fim = parseIso(dados.periodo_fim);
    const lista: { ano: number; mes: number }[] = [];
    let ano = ini.ano, mes = ini.mes;
    while (ano < fim.ano || (ano === fim.ano && mes <= fim.mes)) {
      lista.push({ ano, mes });
      mes += 1;
      if (mes > 11) { mes = 0; ano += 1; }
    }
    return lista;
  }, [dados.periodo_inicio, dados.periodo_fim]);

  // Resumo AO VIVO da edição em curso (Sets locais), não `dados.resumo_periodo`
  // — que reflete o último estado salvo no servidor, não o rascunho na tela.
  const folgas = dados.dias.filter((d) => diasNaoTrabalhados.has(d.data)).length;
  const meias = dados.dias.filter((d) => diasMeiaDiaria.has(d.data)).length;
  const trabalhados = dados.dias.length - folgas - meias;
  const valor = trabalhados * dados.valor_diaria + meias * dados.valor_diaria * 0.5;

  return (
    <div>
      <div className="flex items-center gap-2 mb-3" style={{ flexWrap: "wrap" }}>
        <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} disabled={somenteLeitura} onClick={() => onMarcarTodos("trabalhado")}>
          Marcar todos como trabalhados
        </button>
        <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} disabled={somenteLeitura} onClick={() => onMarcarTodos("folga")}>
          Marcar todos como folga
        </button>
        <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} disabled={somenteLeitura} onClick={() => onMarcarTodos("meia")}>
          Marcar todos como meia diária
        </button>
      </div>

      {meses.map(({ ano, mes }) => {
        const diasNoMes = new Date(ano, mes + 1, 0).getDate();
        const primeiroDiaSemana = new Date(ano, mes, 1).getDay();
        const celulas: (string | null)[] = [];
        for (let i = 0; i < primeiroDiaSemana; i++) celulas.push(null);
        for (let dia = 1; dia <= diasNoMes; dia++) celulas.push(isoLocal(ano, mes, dia));

        return (
          <section key={`${ano}-${mes}`} style={{ marginBottom: "1rem" }}>
            <div style={{ fontWeight: 700, fontSize: "0.82rem", marginBottom: "0.4rem" }}>
              {NOMES_MES[mes]} de {ano}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: "4px" }}>
              {DIAS_SEMANA_ABREV.map((d) => (
                <div key={d} style={{ textAlign: "center", fontSize: "0.65rem", fontWeight: 700, color: "var(--text-muted)", padding: "0.15rem 0" }}>
                  {d}
                </div>
              ))}
              {celulas.map((iso, i) => {
                if (!iso) return <div key={`vazio-${i}`} />;
                const dentroDoPeriodo = iso >= dados.periodo_inicio && iso <= dados.periodo_fim;
                const infoDia = diasPorData.get(iso);
                const folga = diasNaoTrabalhados.has(iso);
                const meia = diasMeiaDiaria.has(iso);
                const desabilitado = somenteLeitura || !dentroDoPeriodo;
                const dia = Number(iso.slice(-2));

                let background = "var(--surface-2)";
                let borderColor = "var(--border)";
                let borderStyle: "solid" | "dashed" = "dashed";
                let color = "var(--text-muted)";
                if (dentroDoPeriodo) {
                  if (folga) {
                    borderColor = "var(--red)";
                    borderStyle = "dashed";
                    color = "var(--red)";
                  } else if (meia) {
                    borderColor = "var(--amber)";
                    borderStyle = "dashed";
                    color = "var(--amber)";
                  } else {
                    borderColor = "var(--dourado)";
                    borderStyle = "solid";
                    color = "var(--dourado-light)";
                  }
                }

                return (
                  <button
                    key={iso}
                    type="button"
                    disabled={desabilitado}
                    onClick={() => onClickDia(iso)}
                    title={infoDia?.pago ? "Dia já coberto por pagamento registrado" : meia ? "Meia diária — clique para virar trabalhado" : folga ? "Folga — clique para virar meia diária" : "Trabalhado — clique para virar folga"}
                    style={{
                      position: "relative",
                      padding: "0.45rem 0",
                      borderRadius: "var(--r-sm)",
                      fontSize: "0.76rem",
                      fontWeight: dentroDoPeriodo && !folga ? 700 : 500,
                      background,
                      color,
                      border: `1px ${borderStyle} ${borderColor}`,
                      textDecoration: dentroDoPeriodo && folga ? "line-through" : "none",
                      opacity: dentroDoPeriodo ? 1 : 0.5,
                      cursor: desabilitado ? "default" : "pointer",
                    }}
                  >
                    {dia}
                    {meia && dentroDoPeriodo && <span style={{ position: "absolute", bottom: 2, left: "50%", transform: "translateX(-50%)", fontSize: "0.55rem" }}>½</span>}
                    {infoDia?.pago && dentroDoPeriodo && (
                      <Lock size={9} style={{ position: "absolute", top: 3, right: 3, opacity: 0.75 }} />
                    )}
                  </button>
                );
              })}
            </div>
          </section>
        );
      })}

      <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", borderTop: "1px solid var(--border)", paddingTop: "0.6rem", marginTop: "0.4rem" }}>
        <strong style={{ color: "var(--dourado-light)" }}>{trabalhados}</strong> dia(s) trabalhado(s) ·{" "}
        <strong style={{ color: "var(--amber)" }}>{meias}</strong> meia(s) diária(s) ·{" "}
        <strong style={{ color: "var(--red)" }}>{folgas}</strong> folga(s) · {formatBRL(valor)}
      </div>
    </div>
  );
}
