"use client";
// Etapa 4 — grade reduzida e editável à esquerda, balanço nutricional ao vivo
// à direita. O cálculo em si (debounce 400ms + AbortController) roda no
// wizard pai (app/dietas/[id]/page.tsx) porque a Etapa 3 e os domínios 5-7
// também precisam do mesmo `resultado` — evita recalcular a mesma dieta em
// paralelo para cada etapa que o usuário visita.
import { Loader2 } from "lucide-react";
import { ItemGrade, Resultado } from "@/lib/dietas";
import { ConsumoTotal } from "@/components/dietas/ConsumoTotal";

function fmt(v: number | null | undefined, casas = 2): string {
  return v == null || Number.isNaN(v) ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

const COR_SITUACAO: Record<string, string> = {
  adequado: "var(--green-light)", deficit: "var(--red)", excesso: "var(--amber)",
};
const ROTULO_SITUACAO: Record<string, string> = { adequado: "Adequado", deficit: "Déficit", excesso: "Excesso" };

export function PainelBalanco({
  itens, onChangeItens, resultado, calculando, onAbrirAplicar, cmsTotal, onChangeCmsTotal,
  exigenciasEditadas, onChangeExigenciasEditadas,
}: {
  itens: ItemGrade[]; onChangeItens: (itens: ItemGrade[]) => void; resultado: Resultado | null; calculando: boolean;
  onAbrirAplicar: () => void;
  // "Consumo total" — o mesmo campo da Etapa 2, espelhado aqui porque é ele
  // que define o kg de MS de cada linha da grade ao lado.
  cmsTotal: number | null | undefined; onChangeCmsTotal: (v: number | null) => void;
  // Overrides manuais da coluna "Exigência", {nutriente: valor} — o motor já
  // devolve `resultado.balanco` com o override aplicado (balanço/situação
  // recalculados a partir dele, ver backend `_aplicar_exigencias_editadas`);
  // aqui só decide a COR (mesma convenção cinza/preto de `ms_pct` abaixo) e
  // dispara o recálculo ao editar.
  exigenciasEditadas: Record<string, number>; onChangeExigenciasEditadas: (m: Record<string, number>) => void;
}) {
  function atualizar(idx: number, patch: Partial<ItemGrade>) {
    onChangeItens(itens.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  // Editar um campo que veio do banco de alimentos marca-o em
  // `campos_editados` — mesma convenção da Etapa 1 (GradeAlimentos). É esse
  // conjunto que decide a cor: valor puxado do banco fica CINZA, valor
  // digitado aqui na formulação fica PRETO, para o nutricionista enxergar
  // num relance o que é composição de laudo e o que é ajuste dele.
  function atualizarCampoDoBanco(idx: number, campo: keyof ItemGrade, valorTexto: string) {
    const it = itens[idx];
    const editados = new Set(it.campos_editados || []);
    editados.add(campo as string);
    atualizar(idx, { [campo]: valorTexto === "" ? null : Number(valorTexto), campos_editados: Array.from(editados) } as Partial<ItemGrade>);
  }

  function foiEditado(it: ItemGrade, campo: string): boolean {
    return (it.campos_editados || []).includes(campo);
  }

  // Cinza = veio do banco de alimentos; preto = editado nesta formulação.
  function corDoValor(editado: boolean): React.CSSProperties {
    return { color: editado ? "var(--text)" : "var(--text-muted)", fontWeight: editado ? 700 : 400 };
  }

  // Mesma convenção da coluna "Teor MS %" acima, aplicada à "Exigência" do
  // painel de balanço: cinza = calculada automaticamente a partir do animal
  // (Etapa 3); preto = o nutricionista sobrepôs manualmente. Limpar o campo
  // remove o override e volta a puxar o valor do motor.
  function atualizarExigencia(nutriente: string, valorTexto: string) {
    const novo = { ...exigenciasEditadas };
    if (valorTexto === "") delete novo[nutriente];
    else novo[nutriente] = Number(valorTexto);
    onChangeExigenciasEditadas(novo);
  }

  function foiExigenciaEditada(nutriente: string): boolean {
    return Object.prototype.hasOwnProperty.call(exigenciasEditadas, nutriente);
  }

  const porNome = new Map((resultado?.ingredientes || []).map((r) => [r.nome, r]));

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.8rem" }}>
        <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700, color: "var(--text)" }}>Balanço ao vivo</h3>
        {calculando && (
          <span style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", color: "var(--text-muted)" }}>
            <Loader2 size={13} className="animate-spin" /> calculando…
          </span>
        )}
        <button type="button" className="btn-primary-gold" style={{ marginLeft: "auto" }} onClick={onAbrirAplicar} disabled={!resultado || itens.length === 0}>
          Aplicar na dieta atual
        </button>
      </div>

      <div style={{ marginBottom: "0.9rem" }}>
        <ConsumoTotal resultado={resultado} valor={cmsTotal} onChange={onChangeCmsTotal}
          gradeVazia={itens.length === 0} compacto />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(20rem, 1.1fr) minmax(22rem, 1fr)", gap: "1rem", alignItems: "start" }}>
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="fazenda-table">
            <thead><tr>
              <th>Ingrediente</th>
              <th title="Quanto deste alimento entra na dieta, em % da matéria seca total">Inclusão %</th>
              <th title="Quanto do alimento é matéria seca (silagem ~30%, milho ~88%). Vem do banco de alimentos; edite se o laudo do seu silo disser outro valor.">Teor MS %</th>
              <th>kg MS/d</th><th>kg MN/d</th><th>R$/d</th>
            </tr></thead>
            <tbody>
              {itens.length === 0 && <tr><td colSpan={6}><div className="empty-state">Volte à Etapa 1 para montar a grade.</div></td></tr>}
              {itens.map((it, idx) => {
                const r = porNome.get(it.nome);
                return (
                  <tr key={idx}>
                    <td>
                      <input
                        value={it.nome} onChange={(e) => atualizar(idx, { nome: e.target.value })}
                        style={{ width: "100%", padding: "0.3rem 0.4rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.8rem" }}
                      />
                    </td>
                    <td>
                      <input
                        type="number" step="0.1" value={it.proporcao_ms_pct}
                        onChange={(e) => atualizar(idx, { proporcao_ms_pct: Number(e.target.value) })}
                        style={{ width: "5rem", padding: "0.3rem 0.4rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.8rem" }}
                      />
                    </td>
                    {/* Teor de MS: puxa do banco de alimentos (cinza) e vira
                        preto assim que o usuário digita por cima — é o que
                        converte kg de MS em kg de matéria natural no trato. */}
                    <td>
                      <input
                        type="number" step="0.1" min={0} max={100}
                        value={it.ms_pct ?? ""}
                        onChange={(e) => atualizarCampoDoBanco(idx, "ms_pct", e.target.value)}
                        title={foiEditado(it, "ms_pct") ? "Editado nesta formulação" : "Valor do banco de alimentos"}
                        style={{
                          width: "5rem", padding: "0.3rem 0.4rem", borderRadius: "var(--r-sm)",
                          border: "1px solid var(--border)", background: "var(--surface)", fontSize: "0.8rem",
                          borderStyle: foiEditado(it, "ms_pct") ? "solid" : "dashed",
                          ...corDoValor(foiEditado(it, "ms_pct")),
                        }}
                      />
                    </td>
                    <td>{fmt(r?.kg_materia_seca_dia)}</td>
                    <td>{fmt(r?.kg_materia_natural_dia)}</td>
                    <td>{fmt(r?.custo_dia)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="fazenda-table">
            <thead><tr><th>Nutriente</th><th>Exigência</th><th>Fornecido</th><th>Balanço</th><th>Situação</th></tr></thead>
            <tbody>
              {!resultado && <tr><td colSpan={5}><div className="empty-state">Sem cálculo ainda.</div></td></tr>}
              {resultado?.balanco.map((linha) => (
                <tr key={linha.nutriente}>
                  <td style={{ fontWeight: 600 }}>{linha.nutriente}</td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.3rem" }}>
                      <input
                        type="number" step="0.01" value={linha.exigencia}
                        onChange={(e) => atualizarExigencia(linha.nutriente, e.target.value)}
                        title={foiExigenciaEditada(linha.nutriente) ? "Editado nesta formulação — apague pra voltar ao valor calculado da Etapa 3" : "Calculado a partir do animal (Etapa 3)"}
                        style={{
                          width: "5.2rem", padding: "0.25rem 0.35rem", borderRadius: "var(--r-sm)",
                          border: "1px solid var(--border)", background: "var(--surface)", fontSize: "0.78rem",
                          borderStyle: foiExigenciaEditada(linha.nutriente) ? "solid" : "dashed",
                          ...corDoValor(foiExigenciaEditada(linha.nutriente)),
                        }}
                      />
                      <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>{linha.unidade}</span>
                    </div>
                  </td>
                  <td>{fmt(linha.fornecido)} {linha.unidade}</td>
                  <td style={{ color: COR_SITUACAO[linha.situacao], fontWeight: 700 }}>{fmt(linha.balanco)}</td>
                  <td>
                    <span style={{ color: COR_SITUACAO[linha.situacao], fontWeight: 700, fontSize: "0.78rem" }}>{ROTULO_SITUACAO[linha.situacao] || linha.situacao}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {resultado && resultado.avisos.length > 0 && (
        <div style={{ marginTop: "0.9rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {resultado.avisos.map((a, i) => (
            <div key={i} className="alert-critico" style={{
              background: a.severidade === "bloqueante" ? "color-mix(in srgb, var(--red) 16%, transparent)" : a.severidade === "atencao" ? "color-mix(in srgb, var(--amber) 16%, transparent)" : "var(--surface-2)",
              borderColor: a.severidade === "bloqueante" ? "var(--red)" : a.severidade === "atencao" ? "var(--amber)" : "var(--border)",
              color: "var(--text)",
            }}>
              {a.mensagem}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
