"use client";
// Etapa 3 — o que o animal exige, calculado automaticamente (sem clique) a
// partir do `resultado` já calculado pela Etapa 4 em segundo plano. Nomes de
// campo conferidos direto na saída real do motor (resultado_para_dict), não
// adivinhados — ver AGENTS do módulo para o comando que gera esse JSON.
import { Resultado } from "@/lib/dietas";

function fmt(v: number | null | undefined, casas = 1): string {
  return v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

function Kpi({ rotulo, valor, unidade }: { rotulo: string; valor: string; unidade: string }) {
  return (
    <div className="kpi-card kpi-card--destaque">
      <div className="kpi-value">{valor} <span style={{ fontSize: "0.95rem", fontWeight: 600, color: "var(--text-muted)" }}>{unidade}</span></div>
      <div className="kpi-label">{rotulo}</div>
    </div>
  );
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <tr>
      <td style={{ padding: "0.4rem 0.7rem", color: "var(--text-muted)", fontSize: "0.82rem" }}>{rotulo}</td>
      <td style={{ padding: "0.4rem 0.7rem", color: "var(--text)", fontWeight: 600, fontSize: "0.82rem", textAlign: "right" }}>{valor}</td>
    </tr>
  );
}

export function PainelExigencias({ resultado }: { resultado: Resultado | null }) {
  if (!resultado) {
    return <div className="empty-state">Preencha a grade (Etapa 1) e os dados do animal (Etapa 2) para ver as exigências calculadas.</div>;
  }
  const { energia, proteina, minerais, consumo } = resultado;
  const nelMantenca = Number(energia.nel_mantenca_mcal) || 0;
  const nelLeite = Number(energia.nel_leite_mcal) || 0;
  const pmMantenca = proteina.exigencias.manutencao_g as number;
  const caExigido = minerais.calcio.exigencia;

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", gap: "0.9rem", marginBottom: "1rem" }}>
        <Kpi rotulo="ELl de mantença" valor={fmt(nelMantenca, 2)} unidade="Mcal/d" />
        <Kpi rotulo="ELl de leite" valor={fmt(nelLeite, 2)} unidade="Mcal/d" />
        <Kpi rotulo="PM de mantença" valor={fmt(pmMantenca, 0)} unidade="g/d" />
        <Kpi rotulo="Cálcio (absorvido)" valor={fmt(caExigido, 1)} unidade="g/d" />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(18rem, 1fr))", gap: "0.9rem" }}>
        {/* As duas estimativas lado a lado: a fibra é ou não fator limitante?
            Ver consumo.py — o valor que vale para o balanço é o COM fibra,
            porque é o limite físico; o sem fibra é o potencial do animal. */}
        <div className="card" style={{ padding: 0 }}>
          <div className="card-header">Consumo de matéria seca</div>
          <table style={{ width: "100%" }}><tbody>
            <Linha rotulo="Potencial do animal (sem olhar a fibra)" valor={`${fmt(consumo.cms_sem_fibra_kg_dia, 2)} kg/d`} />
            <Linha rotulo="Limite com a fibra desta dieta" valor={`${fmt(consumo.cms_com_fibra_kg_dia, 2)} kg/d`} />
            <Linha rotulo="CMS usado no balanço" valor={`${fmt(consumo.cms_kg_dia, 2)} kg/d`} />
            {consumo.monensina_reducao_kg_dia > 0 && (
              <Linha rotulo="Já descontado pela monensina" valor={`−${fmt(consumo.monensina_reducao_kg_dia, 2)} kg/d`} />
            )}
            <Linha rotulo="% do peso vivo" valor={`${fmt(consumo.cms_pct_pv, 2)}%`} />
            <Linha rotulo="g/kg PV^0,75" valor={fmt(consumo.cms_g_kg_pv075, 1)} />
          </tbody></table>
          <div style={{ padding: "0.6rem 0.7rem", borderTop: "1px solid var(--border)" }}>
            {consumo.equacao_usada === 0 ? (
              <p style={{ margin: 0, fontSize: "0.76rem", color: "var(--text-muted)" }}>
                O balanço está usando o <strong>CMS informado manualmente</strong>. As duas estimativas acima ficam só
                como comparação.
              </p>
            ) : consumo.fibra_e_limitante ? (
              <p style={{ margin: 0, fontSize: "0.76rem", color: "var(--text)" }}>
                <strong style={{ color: "var(--amber)" }}>A fibra está limitando o consumo.</strong>{" "}
                Esta vaca teria potencial para comer {fmt(consumo.cms_sem_fibra_kg_dia, 2)} kg, mas o volumoso desta
                dieta só permite {fmt(consumo.cms_com_fibra_kg_dia, 2)} kg — <strong>{fmt(consumo.fibra_limita_kg_dia, 2)} kg/d
                a menos</strong>. Reduzir FDN de volumoso ou melhorar a digestibilidade da fibra liberaria esse consumo.
              </p>
            ) : (
              <p style={{ margin: 0, fontSize: "0.76rem", color: "var(--text)" }}>
                <strong style={{ color: "var(--green-light)" }}>A fibra não está limitando.</strong>{" "}
                O volumoso desta dieta permite pelo menos o que o animal comeria pelo próprio potencial — quem manda
                aqui é o animal, não a dieta.
              </p>
            )}
            <p style={{ margin: "0.4rem 0 0", fontSize: "0.68rem", color: "var(--text-muted)" }}>
              Equações NASEM (2021), Cap. 2: nº {consumo.equacao_sem_fibra} (só fatores do animal) e
              nº {consumo.equacao_com_fibra} (fatores do animal + fibra da dieta).
            </p>
          </div>
        </div>

        <div className="card" style={{ padding: 0 }}>
          <div className="card-header">Energia líquida de lactação, por destino</div>
          <table style={{ width: "100%" }}><tbody>
            <Linha rotulo="Mantença" valor={`${fmt(energia.nel_mantenca_mcal as number, 2)} Mcal/d`} />
            <Linha rotulo="Leite" valor={`${fmt(energia.nel_leite_mcal as number, 2)} Mcal/d`} />
            <Linha rotulo="Gestação" valor={`${fmt(energia.nel_gestacao_mcal as number, 2)} Mcal/d`} />
            <Linha rotulo="Ganho corporal" valor={`${fmt(energia.nel_ganho_mcal as number, 2)} Mcal/d`} />
            <Linha rotulo="Total exigido" valor={`${fmt(energia.nel_uso_total_mcal as number, 2)} Mcal/d`} />
          </tbody></table>
        </div>

        <div className="card" style={{ padding: 0 }}>
          <div className="card-header">Proteína metabolizável, por destino</div>
          <table style={{ width: "100%" }}><tbody>
            <Linha rotulo="Mantença" valor={`${fmt(proteina.exigencias.manutencao_g as number, 0)} g/d`} />
            <Linha rotulo="Leite" valor={`${fmt(proteina.exigencias.leite_g as number, 0)} g/d`} />
            <Linha rotulo="Gestação" valor={`${fmt(proteina.exigencias.gestacao_g as number, 0)} g/d`} />
            <Linha rotulo="Ganho corporal" valor={`${fmt(proteina.exigencias.ganho_g as number, 0)} g/d`} />
            <Linha rotulo="Total exigido" valor={`${fmt(proteina.exigencias.total_g as number, 0)} g/d`} />
          </tbody></table>
        </div>

        <div className="card" style={{ padding: 0 }}>
          <div className="card-header">Macrominerais absorvidos, exigência</div>
          <table style={{ width: "100%" }}><tbody>
            <Linha rotulo="Cálcio" valor={`${fmt(minerais.calcio.exigencia, 1)} g/d`} />
            <Linha rotulo="Fósforo" valor={`${fmt(minerais.fosforo.exigencia, 1)} g/d`} />
            <Linha rotulo="Magnésio" valor={`${fmt(minerais.magnesio.exigencia, 1)} g/d`} />
            <Linha rotulo="Sódio" valor={`${fmt(minerais.sodio.exigencia, 1)} g/d`} />
            <Linha rotulo="Cloro" valor={`${fmt(minerais.cloro.exigencia, 1)} g/d`} />
            <Linha rotulo="Potássio" valor={`${fmt(minerais.potassio.exigencia, 1)} g/d`} />
            <Linha rotulo="Enxofre" valor={`${fmt(minerais.enxofre.exigencia, 1)} g/d`} />
          </tbody></table>
        </div>
      </div>
    </div>
  );
}
