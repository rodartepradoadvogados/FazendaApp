"use client";
import { useEffect, useState } from "react";
import { CalendarRange, AlertTriangle, Info } from "lucide-react";
import { fetchCiclos21Dias, formatDate, type CiclosResposta, type CicloReprodutivo } from "@/lib/api";
import { SecaoRecolhivel, TabBar, Indicador } from "@/components/ui";

/**
 * Risco de prenhez em ciclos de 21 dias — o BREDSUM\E do DairyComp.
 *
 * Substitui o relatório de ciclos que existia antes, que era FECHADO: só
 * conseguia contar 21 dias para frente a partir do D11 de um protocolo IATF ou
 * de uma inseminação. Aqui a âncora é livre — escolhe-se uma data e se ela é o
 * INÍCIO do primeiro ciclo (conta para frente) ou o FIM do último (conta para
 * trás).
 *
 * As regras que decidem quem entra em cada denominador estão em
 * backend/fazenda/rules/programa_reprodutivo.py (modelo lógico R1–R9).
 */

const hojeISO = () => new Date().toISOString().slice(0, 10);

function Pct({ valor, meta }: { valor: number | null; meta?: number }) {
  if (valor === null) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  const cor = meta === undefined ? "var(--text)" : valor >= meta ? "var(--green-light)" : "var(--amber)";
  return <span style={{ color: cor, fontWeight: 700 }}>{valor.toFixed(1)}%</span>;
}

// Funil de um ciclo: mostra a queda BR ELIG → BRED → PG ELIG → PREG em barras
// proporcionais, que é onde se enxerga de imediato ONDE o rebanho perde.
function Funil({ c }: { c: CicloReprodutivo }) {
  const base = Math.max(c.br_elig, 1);
  const etapas = [
    { rotulo: "BR ELIG", n: c.br_elig, cor: "var(--dourado-light)", ajuda: "Elegíveis para inseminação: aptas por pelo menos 11 dos 21 dias" },
    { rotulo: "BRED", n: c.bred, cor: "var(--green-light)", ajuda: "Efetivamente inseminadas dentro do ciclo" },
    { rotulo: "PG ELIG", n: c.pg_elig, cor: "var(--dourado-light)", ajuda: "Elegíveis para prenhez: continuavam no rebanho na janela de diagnóstico" },
    { rotulo: "PREG", n: c.preg, cor: "var(--green-light)", ajuda: "Confirmadas prenhes a partir de um serviço deste ciclo" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
      {etapas.map((e) => (
        <div key={e.rotulo} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }} title={e.ajuda}>
          <span style={{ fontSize: "0.68rem", width: 56, color: "var(--text-muted)", fontWeight: 600 }}>{e.rotulo}</span>
          <div style={{ flex: 1, background: "var(--surface-2)", borderRadius: 4, height: 14, overflow: "hidden" }}>
            <div style={{ width: `${(e.n / base) * 100}%`, background: e.cor, height: "100%" }} />
          </div>
          <span style={{ fontSize: "0.72rem", width: 34, textAlign: "right", fontWeight: 700 }}>{e.n}</span>
        </div>
      ))}
    </div>
  );
}

export default function Ciclos21DiasPage() {
  const [ancora, setAncora] = useState(hojeISO());
  const [modo, setModo] = useState<"inicio" | "fim">("fim");
  const [nCiclos, setNCiclos] = useState(6);
  const [categoria, setCategoria] = useState("todas");
  const [dados, setDados] = useState<CiclosResposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [detalhe, setDetalhe] = useState<CicloReprodutivo | null>(null);

  useEffect(() => {
    let cancelado = false;
    setCarregando(true); setErro(null);
    fetchCiclos21Dias(ancora, modo, nCiclos, categoria)
      .then((d) => { if (!cancelado) setDados(d); })
      .catch((e) => { if (!cancelado) { setDados(null); setErro(e.message); } })
      .finally(() => { if (!cancelado) setCarregando(false); });
    return () => { cancelado = true; };
  }, [ancora, modo, nCiclos, categoria]);

  return (
    <div>
      <h1 style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "1.6rem", fontWeight: 700 }}>
        <CalendarRange size={26} /> Ciclos de 21 dias
      </h1>
      <p style={{ color: "var(--text-muted)", marginBottom: "1rem" }}>
        Risco de prenhez por ciclo, no padrão BREDSUM\E. O denominador é o rebanho
        elegível — não só quem foi inseminado.
      </p>

      {/* ---------------- Controles da simulação ---------------- */}
      <div className="card" style={{ marginBottom: "1rem" }}>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Data de referência</label>
            <input type="date" value={ancora} onChange={(e) => setAncora(e.target.value)}
              style={{ width: "100%", padding: "0.4rem 0.6rem", borderRadius: 6, fontSize: "0.85rem",
                background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }} />
          </div>
          <div>
            <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Nº de ciclos</label>
            <input type="number" min={1} max={26} value={nCiclos}
              onChange={(e) => setNCiclos(Math.min(26, Math.max(1, Number(e.target.value) || 1)))}
              style={{ width: "100%", padding: "0.4rem 0.6rem", borderRadius: 6, fontSize: "0.85rem",
                background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }} />
          </div>
          <div>
            <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
            <select value={categoria} onChange={(e) => setCategoria(e.target.value)}
              style={{ width: "100%", padding: "0.4rem 0.6rem", borderRadius: 6, fontSize: "0.85rem",
                background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}>
              <option value="todas">Todas</option>
              <option value="vaca">Vacas</option>
              <option value="novilha">Novilhas</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>A data é o…</label>
            <TabBar<"inicio" | "fim">
              abas={[
                { id: "inicio", label: "Início", title: "A data escolhida é o primeiro dia do 1º ciclo — conta para frente" },
                { id: "fim", label: "Fim", title: "A data escolhida é o último dia do último ciclo — conta para trás" },
              ]}
              ativa={modo}
              onChange={setModo}
            />
          </div>
        </div>
        {dados && (
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
            Período avaliado: {formatDate(dados.periodo.inicio)} a {formatDate(dados.periodo.fim)} ·{" "}
            {dados.resumo.animais_avaliados} animal(is) no rebanho ·{" "}
            PEV {dados.parametros.pev_dias} d · mínimo {dados.parametros.dias_minimos_no_ciclo} d no ciclo ·{" "}
            resultado conhecido em {dados.parametros.dias_resultado_conhecido} d
          </p>
        )}
      </div>

      {erro && (
        <div className="card" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start",
          background: "rgba(220,38,38,0.1)", border: "1px solid var(--red)", marginBottom: "1rem" }}>
          <AlertTriangle size={16} style={{ color: "var(--red)", marginTop: 2 }} />
          <span style={{ fontSize: "0.85rem" }}>{erro}</span>
        </div>
      )}
      {carregando && <p style={{ color: "var(--text-muted)" }}>Calculando…</p>}

      {dados && !carregando && (
        <>
          {/* ---------------- Resumo do período ---------------- */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3" style={{ marginBottom: "1rem" }}>
            <Indicador rotulo="Taxa de serviço" title={`Meta ${dados.metas.taxa_servico}% — servidas ÷ elegíveis (BRED ÷ BR ELIG)`}
              valor={dados.resumo.taxa_servico === null ? "—" : `${dados.resumo.taxa_servico}%`}
              cor={dados.resumo.taxa_servico !== null && dados.resumo.taxa_servico >= dados.metas.taxa_servico ? "var(--green-light)" : "var(--amber)"} />
            <Indicador rotulo="Taxa de prenhez (21 d)" title={`Meta ${dados.metas.taxa_prenhez}% — prenhes ÷ PG ELIG. NÃO é serviço × concepção.`}
              valor={dados.resumo.taxa_prenhez === null ? "—" : `${dados.resumo.taxa_prenhez}%`}
              cor={dados.resumo.taxa_prenhez !== null && dados.resumo.taxa_prenhez >= dados.metas.taxa_prenhez ? "var(--green-light)" : "var(--amber)"} />
            <Indicador rotulo="Taxa de concepção" title={`Meta ${dados.metas.taxa_concepcao}% — prenhes ÷ serviços com resultado conhecido`}
              valor={dados.resumo.taxa_concepcao === null ? "—" : `${dados.resumo.taxa_concepcao}%`}
              cor={dados.resumo.taxa_concepcao !== null && dados.resumo.taxa_concepcao >= dados.metas.taxa_concepcao ? "var(--green-light)" : "var(--amber)"} />
          </div>

          {/* ---------------- Tabela por ciclo ---------------- */}
          <div className="card" style={{ marginBottom: "1rem" }}>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead>
                  <tr>
                    <th>Ciclo</th><th>Período</th>
                    <th style={{ textAlign: "right" }} title="Elegíveis para inseminação">BR ELIG</th>
                    <th style={{ textAlign: "right" }} title="Inseminadas no ciclo">BRED</th>
                    <th style={{ textAlign: "right" }}>Serviço</th>
                    <th style={{ textAlign: "right" }} title="Elegíveis para prenhez">PG ELIG</th>
                    <th style={{ textAlign: "right" }} title="Confirmadas prenhes">PREG</th>
                    <th style={{ textAlign: "right" }}>Prenhez</th>
                    <th style={{ textAlign: "right" }}>Concepção</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.ciclos.map((c) => (
                    <tr key={c.ciclo} onClick={() => setDetalhe(c)} className="row-clickable"
                      style={{ cursor: "pointer" }} title="Clique para ver quem entrou em cada denominador">
                      <td style={{ fontWeight: 700 }}>{c.ciclo}</td>
                      <td style={{ fontSize: "0.78rem" }}>{formatDate(c.inicio)} – {formatDate(c.fim)}</td>
                      <td style={{ textAlign: "right" }}>{c.br_elig}</td>
                      <td style={{ textAlign: "right" }}>{c.bred}</td>
                      <td style={{ textAlign: "right" }}><Pct valor={c.taxa_servico} meta={dados.metas.taxa_servico} /></td>
                      <td style={{ textAlign: "right" }}>{c.pg_elig}</td>
                      <td style={{ textAlign: "right" }}>{c.preg}</td>
                      <td style={{ textAlign: "right" }}><Pct valor={c.taxa_prenhez} meta={dados.metas.taxa_prenhez} /></td>
                      <td style={{ textAlign: "right" }}><Pct valor={c.taxa_concepcao} meta={dados.metas.taxa_concepcao} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ---------------- Funis por ciclo ---------------- */}
          <SecaoRecolhivel titulo="Onde o rebanho perde, ciclo a ciclo" badge={String(dados.ciclos.length)}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {dados.ciclos.map((c) => (
                <div key={c.ciclo} className="card" style={{ background: "var(--surface-2)" }}>
                  <p style={{ fontSize: "0.8rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                    Ciclo {c.ciclo} — {formatDate(c.inicio)} a {formatDate(c.fim)}
                  </p>
                  <Funil c={c} />
                </div>
              ))}
            </div>
          </SecaoRecolhivel>

          <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", marginTop: "1rem",
            fontSize: "0.75rem", color: "var(--text-muted)" }}>
            <Info size={14} style={{ marginTop: 2, flexShrink: 0 }} />
            <span>{dados.ressalva_historica}</span>
          </div>
        </>
      )}

      {/* ---------------- Drill-down: quem entrou em cada balde ---------------- */}
      {detalhe && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex",
          alignItems: "center", justifyContent: "center", zIndex: 90, padding: "1rem" }}>
          <div className="card" style={{ width: 780, maxWidth: "96vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0 }}>
                Ciclo {detalhe.ciclo} — {formatDate(detalhe.inicio)} a {formatDate(detalhe.fim)}
              </div>
              <button onClick={() => setDetalhe(null)} className="btn-ghost">Fechar</button>
            </div>
            <div style={{ overflowY: "auto" }}>
              {([
                ["Elegíveis para inseminação (BR ELIG)", detalhe.animais.br_elig],
                ["Inseminadas no ciclo (BRED)", detalhe.animais.bred],
                ["Elegíveis para prenhez (PG ELIG)", detalhe.animais.pg_elig],
                ["Confirmadas prenhes (PREG)", detalhe.animais.preg],
              ] as const).map(([titulo, nums]) => (
                <div key={titulo} style={{ marginBottom: "0.9rem" }}>
                  <p style={{ fontSize: "0.78rem", fontWeight: 700, marginBottom: "0.35rem" }}>
                    {titulo} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>({nums.length})</span>
                  </p>
                  {nums.length ? (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                      {nums.map((n) => (
                        <span key={n} style={{ fontSize: "0.74rem", background: "var(--surface-2)",
                          border: "1px solid var(--border)", borderRadius: 999, padding: "0.12rem 0.55rem", fontWeight: 600 }}>
                          {n}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Nenhum animal.</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
