"use client";
// Campo "Consumo total" + as duas estimativas de CMS, no mesmo desenho do
// NASEM Dairy 8 (tela Ration): as estimativas são SOMENTE LEITURA e existe um
// campo à parte — o Total Intake — que é o consumo que realmente comanda a
// dieta. O usuário chega nele digitando ou clicando em "Usar esta estimativa".
//
// Por que não deixar o sistema escolher sozinho: as duas estimativas
// respondem a perguntas diferentes. A "pelo animal" diz quanto esta vaca
// comeria pelo porte, produção e estágio; a "pelo animal + fibra" diz quanto o
// volumoso desta dieta permite comer. Qual das duas vale é julgamento do
// nutricionista, não do software.
//
// Aparece nas Etapas 2 e 4 (mesmo componente, mesmo valor) — na 2 junto dos
// dados do animal, na 4 ao lado da grade, onde dá para ver na hora o efeito
// sobre kg MS/dia e custo de cada ingrediente.
import { Resultado } from "@/lib/dietas";

function fmt(v: number | null | undefined, casas = 2): string {
  return v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

export function ConsumoTotal({
  resultado, valor, onChange, gradeVazia = false, compacto = false,
}: {
  resultado: Resultado | null;
  valor: number | null | undefined;
  onChange: (v: number | null) => void;
  // Sem alimentos na grade, a equação da fibra não tem o que ler e devolve um
  // número sem sentido (no próprio NASEM, dieta vazia dá ~10 kg contra ~25 da
  // estimativa pelo animal). Nesse estado o botão dela fica desabilitado.
  gradeVazia?: boolean;
  compacto?: boolean;
}) {
  const c = resultado?.consumo;

  const rotulo: React.CSSProperties = { fontSize: "0.74rem", color: "var(--text-muted)" };
  const entrada: React.CSSProperties = {
    padding: "0.42rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)",
    background: "var(--surface)", color: "var(--text)", fontSize: "0.9rem", fontWeight: 700, width: "7.5rem",
  };
  const btn: React.CSSProperties = {
    fontSize: "0.72rem", padding: "0.3rem 0.6rem", borderRadius: "var(--r-sm)",
    border: "1px solid var(--dourado)", background: "transparent", color: "var(--dourado)", cursor: "pointer",
    whiteSpace: "nowrap",
  };
  const btnOff: React.CSSProperties = { ...btn, opacity: 0.45, cursor: "not-allowed" };

  function Estimativa({ titulo, kg, equacao, desabilitado, dica }: {
    titulo: string; kg: number | undefined; equacao: number | undefined; desabilitado?: boolean; dica?: string;
  }) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <div style={{ minWidth: "13rem" }}>
          <div style={rotulo}>{titulo}</div>
          <div style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text)" }}>
            {fmt(kg)} <span style={{ fontSize: "0.72rem", fontWeight: 400, color: "var(--text-muted)" }}>kg/dia</span>
            {equacao != null && <span style={{ fontSize: "0.68rem", fontWeight: 400, color: "var(--text-muted)" }}> · eq. {equacao}</span>}
          </div>
        </div>
        <button type="button" title={dica} disabled={desabilitado || kg == null}
          style={desabilitado || kg == null ? btnOff : btn}
          onClick={() => kg != null && onChange(Number(kg.toFixed(3)))}>
          Usar esta estimativa
        </button>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: compacto ? "0.7rem 0.9rem" : undefined }}>
      <div className="card-header" style={{ marginBottom: "0.6rem" }}>Consumo de matéria seca</div>

      <div style={{ display: "flex", alignItems: "flex-end", gap: "0.6rem", flexWrap: "wrap", marginBottom: "0.8rem" }}>
        <div>
          <div style={rotulo}>Consumo total (kg/dia)</div>
          <input type="number" step="0.1" min={0} style={entrada}
            value={valor ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />
        </div>
        <p style={{ margin: 0, fontSize: "0.72rem", color: "var(--text-muted)", flex: 1, minWidth: "14rem", lineHeight: 1.45 }}>
          É este número que comanda a dieta: define o kg de matéria seca de cada ingrediente da grade.
          Digite o consumo medido no cocho ou puxe uma das estimativas abaixo.
        </p>
      </div>

      {!c ? (
        <p style={{ margin: 0, fontSize: "0.76rem", color: "var(--text-muted)" }}>
          Preencha os dados do animal para ver as estimativas.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          <Estimativa titulo="Estimativa pelo animal" kg={c.cms_sem_fibra_kg_dia} equacao={c.equacao_sem_fibra}
            dica="Quanto esta vaca comeria pelo porte, produção, condição corporal e estágio da lactação — não olha a dieta." />
          <Estimativa titulo="Estimativa pelo animal + fibra" kg={c.cms_com_fibra_kg_dia} equacao={c.equacao_com_fibra}
            desabilitado={gradeVazia}
            dica={gradeVazia
              ? "Monte a grade de alimentos primeiro: sem alimentos, a equação da fibra não tem o que ler."
              : "Quanto o volumoso desta dieta permite comer. É o limite físico imposto pela fibra."} />

          {gradeVazia && (
            <p style={{ margin: 0, fontSize: "0.72rem", color: "var(--amber)" }}>
              A grade de alimentos está vazia — a estimativa pela fibra ainda não vale.
            </p>
          )}

          {!gradeVazia && c.fibra_e_limitante && (
            <p style={{ margin: 0, fontSize: "0.74rem", color: "var(--text)" }}>
              <strong style={{ color: "var(--amber)" }}>A fibra está limitando o consumo</strong> em{" "}
              {fmt(c.fibra_limita_kg_dia)} kg/dia. Reduzir FDN de volumoso ou melhorar a digestibilidade da fibra
              liberaria essa diferença.
            </p>
          )}
          {!gradeVazia && !c.fibra_e_limitante && (
            <p style={{ margin: 0, fontSize: "0.74rem", color: "var(--text)" }}>
              <strong style={{ color: "var(--green-light)" }}>A fibra não está limitando</strong> — o volumoso desta
              dieta permite pelo menos o que o animal comeria pelo próprio potencial.
            </p>
          )}

          {c.monensina_reducao_kg_dia > 0 && (
            <p style={{ margin: 0, fontSize: "0.7rem", color: "var(--text-muted)" }}>
              As duas estimativas já vêm com −{fmt(c.monensina_reducao_kg_dia)} kg/dia pela monensina. O valor que você
              digitar no Consumo total é respeitado como está, sem novo desconto.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
