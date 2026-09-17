"use client";
import { useEffect, useState } from "react";
import { CalendarRange, AlertTriangle, Info } from "lucide-react";
import { fetchCiclos21Dias, formatDate, NetworkError, type CiclosResposta, type CicloReprodutivo } from "@/lib/api";
import { SecaoRecolhivel, Indicador, TelaSkeleton, ErroCarregamento } from "@/components/ui";
import { FiltroCiclo21Dias } from "@/components/FiltroCiclo21Dias";
import { Modal } from "@/components/Modal";

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

// Data local, NÃO `toISOString()` — aquilo é UTC, e no Brasil (UTC−3) faria a
// tela abrir com a data de amanhã depois das 21h.
const hojeISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

// `meta` só é passada quando faz sentido comparar. Num ciclo cuja janela de
// diagnóstico ainda não fechou, a taxa de prenhez está subestimada por
// construção — pintá-la de âmbar contra a meta seria acusar de piora o que é
// só falta de tempo.
function Pct({ valor, meta }: { valor: number | null; meta?: number }) {
  if (valor === null) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  const cor = meta === undefined ? "var(--text-muted)" : valor >= meta ? "var(--green-light)" : "var(--amber)";
  return <span style={{ color: cor, fontWeight: 700 }}>{valor.toFixed(1)}%</span>;
}

const AJUDA = {
  br_elig: "Apt — elegíveis para inseminação: estiveram aptas em pelo menos 11 dos 21 dias do ciclo",
  bred: "Ins. — dessas, as que efetivamente receberam inseminação dentro do ciclo",
  pg_elig: "Apt Real — elegíveis para prenhez: das Apt, as que continuavam no rebanho no fim da janela de diagnóstico",
  preg: "Posit. — confirmadas prenhes a partir de um serviço deste ciclo",
  servico: "Taxa de serviço — Ins. ÷ Apt. Quanto do rebanho disponível foi inseminado.",
  prenhez: "Taxa de prenhez — Posit. ÷ Apt Real. NÃO é serviço × concepção: os denominadores são diferentes.",
  concepcao: "Taxa de concepção — Posit. ÷ serviços do ciclo cujo resultado já dá para saber",
};

// Legenda visível, não tooltip: esta tela é usada em tablet, e `title` não
// existe em toque.
function Legenda() {
  const itens = [
    ["Apt", "aptas ≥ 11 dos 21 dias — quem podia ser inseminada"],
    ["Ins.", "dessas, quem foi inseminada no ciclo"],
    ["Apt Real", "das Apt, quem seguia no rebanho no fim do diagnóstico"],
    ["Posit.", "quem ficou prenhe de um serviço deste ciclo"],
  ];
  return (
    <div className="card" style={{ marginBottom: "1rem", background: "var(--surface-2)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1.5rem" }}>
        {itens.map(([sigla, texto]) => (
          <span key={sigla} style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            <strong style={{ color: "var(--dourado-light)", fontWeight: 700 }}>{sigla}</strong> — {texto}
          </span>
        ))}
      </div>
      <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
        Serviço = Ins. ÷ Apt · Prenhez = Posit. ÷ Apt Real · Concepção = Posit. ÷ serviços com resultado.{" "}
        <strong>Prenhez não é serviço × concepção</strong> — os denominadores são diferentes.
      </p>
    </div>
  );
}

// Dois pares, NÃO um funil. Apt Real é subconjunto de Apt, não de Ins.: numa
// cascata de quatro barras a terceira pode CRESCER, e quem lê como funil conclui
// que o rebanho "recuperou" vacas no meio do caminho. São duas perguntas
// distintas — quantas foram inseminadas, e quantas ficaram prenhes — cada uma
// com seu próprio denominador.
function Pares({ c }: { c: CicloReprodutivo }) {
  const pares = [
    { titulo: "Serviço", den: { rotulo: "Apt", n: c.br_elig, ajuda: AJUDA.br_elig },
      num: { rotulo: "Ins.", n: c.bred, ajuda: AJUDA.bred }, taxa: c.taxa_servico },
    { titulo: "Prenhez", den: { rotulo: "Apt Real", n: c.pg_elig, ajuda: AJUDA.pg_elig },
      num: { rotulo: "Posit.", n: c.preg, ajuda: AJUDA.preg }, taxa: c.taxa_prenhez },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
      {pares.map((p) => {
        const base = Math.max(p.den.n, 1);
        return (
          <div key={p.titulo}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.7rem",
              color: "var(--text-muted)", fontWeight: 700, marginBottom: "0.25rem" }}>
              <span>{p.titulo}</span>
              <span>{p.taxa === null ? "—" : `${p.taxa.toFixed(1)}%`}</span>
            </div>
            {/* Achado do lote 2: este `title` era um tooltip morto em toque
                (mesma lição que o comentário da própria Legenda() acima já
                registra) — removido; a Legenda, sempre visível, já cobre
                a mesma explicação de Apt/Ins./Apt Real/Posit. sem depender de hover. */}
            {[p.den, p.num].map((e, i) => (
              <div key={e.rotulo} style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: i ? "0.25rem" : 0 }}>
                <span style={{ fontSize: "0.68rem", width: 56, color: "var(--text-muted)", fontWeight: 600 }}>{e.rotulo}</span>
                <div style={{ flex: 1, background: "var(--surface)", borderRadius: 4, height: 14, overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(100, (e.n / base) * 100)}%`,
                    background: i ? "var(--green-light)" : "var(--dourado-light)", height: "100%" }} />
                </div>
                <span style={{ fontSize: "0.72rem", width: 34, textAlign: "right", fontWeight: 700 }}>{e.n}</span>
              </div>
            ))}
          </div>
        );
      })}
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
  const [offline, setOffline] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [detalhe, setDetalhe] = useState<CicloReprodutivo | null>(null);

  useEffect(() => {
    let cancelado = false;
    setCarregando(true); setErro(null); setOffline(false);
    fetchCiclos21Dias(ancora, modo, nCiclos, categoria)
      .then((d) => { if (!cancelado) setDados(d); })
      .catch((e) => {
        if (cancelado) return;
        setDados(null);
        // Falha de rede já ganha o aviso global (OfflineBanner, ver
        // AuthShell/lib/api.ts::authFetch) — aqui só uma nota curta local,
        // sem repetir "Failed to fetch" cru como se fosse erro de servidor.
        if (e instanceof NetworkError) setOffline(true);
        else setErro(e.message);
      })
      .finally(() => { if (!cancelado) setCarregando(false); });
    return () => { cancelado = true; };
  }, [ancora, modo, nCiclos, categoria]);

  // Achado do lote 2: erro sem saída (sem retry) — "Tentar novamente" só
  // re-executa o mesmo fetch dos parâmetros atuais, sem precisar mudar
  // ancora/modo/nCiclos/categoria pra reacionar o useEffect acima.
  const tentarNovamente = () => {
    setCarregando(true); setErro(null); setOffline(false);
    fetchCiclos21Dias(ancora, modo, nCiclos, categoria)
      .then(setDados)
      .catch((e) => {
        setDados(null);
        if (e instanceof NetworkError) setOffline(true);
        else setErro(e.message);
      })
      .finally(() => setCarregando(false));
  };

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
        <FiltroCiclo21Dias
          ancora={ancora} setAncora={setAncora}
          modo={modo} setModo={setModo}
          nCiclos={nCiclos} setNCiclos={setNCiclos}
          categoria={categoria} setCategoria={setCategoria}
        />
        {dados && (
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
            Período avaliado: {formatDate(dados.periodo.inicio)} a {formatDate(dados.periodo.fim)} ·{" "}
            {dados.resumo.animais_carregados} animal(is) no rebanho, {dados.resumo.animais_avaliados} entraram em algum ciclo ·{" "}
            PEV {dados.parametros.pev_dias} d · mínimo {dados.parametros.dias_minimos_no_ciclo} d no ciclo ·{" "}
            resultado conhecido em {dados.parametros.dias_resultado_conhecido} d
          </p>
        )}
      </div>

      {dados && !carregando && <Legenda />}

      {offline && (
        <div className="card" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start",
          background: "rgba(217,119,6,0.1)", border: "1px solid var(--amber)", marginBottom: "1rem" }}>
          <AlertTriangle size={16} style={{ color: "var(--amber)", marginTop: 2 }} />
          <span style={{ fontSize: "0.85rem" }}>Você está sem conexão. Os dados não puderam ser atualizados agora.</span>
        </div>
      )}
      {erro && <ErroCarregamento mensagem={`Não foi possível carregar o ciclo de 21 dias: ${erro}.`} onRetry={tentarNovamente} />}
      {carregando && <TelaSkeleton kpis={3} />}

      {dados && !carregando && (
        <>
          {/* ---------------- Resumo do período ---------------- */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3" style={{ marginBottom: "1rem" }}>
            <Indicador rotulo="Taxa de serviço" title={`Meta ${dados.metas.taxa_servico}% — servidas ÷ elegíveis (Ins. ÷ Apt)`}
              valor={dados.resumo.taxa_servico === null ? "—" : `${dados.resumo.taxa_servico}%`}
              cor={dados.resumo.taxa_servico !== null && dados.resumo.taxa_servico >= dados.metas.taxa_servico ? "var(--green-light)" : "var(--amber)"} />
            <Indicador rotulo="Taxa de prenhez (21 d)" title={`Meta ${dados.metas.taxa_prenhez}% — prenhes ÷ Apt Real. NÃO é serviço × concepção.`}
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
                    <th style={{ textAlign: "right" }} title={AJUDA.br_elig}>Apt</th>
                    <th style={{ textAlign: "right" }} title={AJUDA.bred}>Ins.</th>
                    <th style={{ textAlign: "right" }} title={AJUDA.servico}>Serviço</th>
                    <th style={{ textAlign: "right" }} title={AJUDA.pg_elig}>Apt Real</th>
                    <th style={{ textAlign: "right" }} title={AJUDA.preg}>Posit.</th>
                    <th style={{ textAlign: "right" }} title={AJUDA.prenhez}>Prenhez</th>
                    <th style={{ textAlign: "right" }} title={AJUDA.concepcao}>Concepção</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.ciclos.map((c) => (
                    <tr key={c.ciclo} onClick={() => setDetalhe(c)} className="row-clickable"
                      style={{ cursor: "pointer", opacity: c.janela_dg_completa ? 1 : 0.65 }}
                      title={c.janela_dg_completa
                        ? "Clique para ver quem entrou em cada denominador"
                        : "Janela de diagnóstico ainda aberta: a prenhez e a concepção deste ciclo ainda vão subir. Não compare com a meta."}>
                      <td style={{ fontWeight: 700 }}>{c.ciclo}</td>
                      <td style={{ fontSize: "0.78rem" }}>
                        {formatDate(c.inicio)} – {formatDate(c.fim)}
                        {!c.janela_dg_completa && (
                          <span style={{ marginLeft: "0.4rem", fontSize: "0.68rem", fontWeight: 700,
                            color: "var(--text-muted)", border: "1px solid var(--border)",
                            borderRadius: 999, padding: "0.05rem 0.4rem", whiteSpace: "nowrap" }}>
                            em apuração
                          </span>
                        )}
                      </td>
                      <td style={{ textAlign: "right" }}>{c.br_elig}</td>
                      <td style={{ textAlign: "right" }}>{c.bred}</td>
                      <td style={{ textAlign: "right" }}><Pct valor={c.taxa_servico} meta={dados.metas.taxa_servico} /></td>
                      <td style={{ textAlign: "right" }}>{c.pg_elig}</td>
                      <td style={{ textAlign: "right" }}>{c.preg}</td>
                      {/* Sem `meta` quando a janela está aberta: o número está
                          estruturalmente baixo e o semáforo mentiria. */}
                      <td style={{ textAlign: "right" }}><Pct valor={c.taxa_prenhez} meta={c.janela_dg_completa ? dados.metas.taxa_prenhez : undefined} /></td>
                      <td style={{ textAlign: "right" }}><Pct valor={c.taxa_concepcao} meta={c.janela_dg_completa ? dados.metas.taxa_concepcao : undefined} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ---------------- Funis por ciclo ---------------- */}
          <SecaoRecolhivel titulo="Serviço e prenhez, ciclo a ciclo" badge={String(dados.ciclos.length)}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {dados.ciclos.map((c) => (
                <div key={c.ciclo} className="card" style={{ background: "var(--surface-2)" }}>
                  <p style={{ fontSize: "0.8rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                    Ciclo {c.ciclo} — {formatDate(c.inicio)} a {formatDate(c.fim)}
                  </p>
                  <Pares c={c} />
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
        <Modal title={`Ciclo ${detalhe.ciclo} — ${formatDate(detalhe.inicio)} a ${formatDate(detalhe.fim)}`} width="780px" onClose={() => setDetalhe(null)}>
              {([
                ["Elegíveis para inseminação (Apt)", detalhe.animais.br_elig],
                ["Inseminadas no ciclo (Ins.)", detalhe.animais.bred],
                ["Elegíveis para prenhez (Apt Real)", detalhe.animais.pg_elig],
                ["Confirmadas prenhes (Posit.)", detalhe.animais.preg],
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
        </Modal>
      )}
    </div>
  );
}
