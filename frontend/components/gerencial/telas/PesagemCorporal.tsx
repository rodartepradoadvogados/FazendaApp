"use client";
// Lançamentos › Produção › Pesagem corporal — PROPOSTA de tela gerencial (variante desktop, só apresentação, dados de exemplo).
// Substitui components/FormPesagemCorporal.tsx (dois painéis lado a lado com rolagem própria + tabelas com maxHeight; relatório
// GMD/GPD ocupando metade da tela do lançamento). Aqui: UMA coluna, UMA rolagem por lista, e o relatório vira o segmento
// "Histórico de ganho" da mesma gaveta. A versão ligada a dados precisa PRESERVAR:
//  • Props: animais (AnimalRow[]), lotes (string[]), salvarPesagens (injeção do app de campo/offline; resposta { criados, enviado? } —
//    enviado === false = "Sem internet — guardado, será enviado quando conectar.").
//  • Modalidade animal | lote | planilha; data padrão = hoje; só envia peso_kg > 0 (em branco/zero não vai); lote com idade em meses.
//  • POST /producao/pesagens { data_pesagem, entradas: [{ numero_matriz, peso_kg }] } (criarPesagensCorporais).
//  • Planilha: baixarModeloPesagemCorporal() + importarPesagemCorporalPlanilha(file) (POST /producao/pesagens/importar → { criados, erros });
//    importa direto (sem pré-visualização); erros: contagem + até 10 mensagens.
//  • Histórico: GET /producao/pesagens/relatorio { numero_matriz?, grupo?, data_inicio?, data_fim? } → linhas { numero_matriz, grupo_primario,
//    num_pesagens, primeira_data/peso, ultima_data/peso, gmd_kg_dia, gpd_kg_dia }; recarrega ao mudar qualquer filtro e após salvar;
//    exportação PDF/Excel (ExportarBotoes, colunas nº, lote, nº pesagens, 1ª e última data/kg, GMD, GPD).
//  • Colunas "peso anterior / data / ganho / GMD" exigem o último peso por animal (campo novo na API de animais ou no relatório);
//    sem ele a tabela volta ao formato simples (Nº, idade, peso novo). Enter avança de linha (só front); Tab continua.
import React, { useMemo, useState } from "react";
import { Download, FileSpreadsheet, FileText, Info, Scale } from "lucide-react";
import { Ajuda, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, QuadroGaveta, Selo } from "@/components/gerencial/kit";
import { CaixaArquivo, LinhaGrupo, RotuloMini, Tecla, aoApertarEnter, dataBR, diasEntre, nb, numOuNull, semente, somarDias, HOJE_ISO } from "./utilProducao";

type Aba = "lancar" | "historico";
type Modo = "animal" | "lote" | "planilha";
type Animal = { n: string; lote: string; idade: number; ant: number | null; antData: string | null };

const LOTES = [
  { id: "01 - Novilhas Alta", n: 12, idade: [18, 26], kg: [385, 470], fixos: ["3335", "075"] },
  { id: "11 - Bezerras Desmamadas", n: 24, idade: [3, 6], kg: [90, 175], fixos: [] as string[] },
  { id: "12 - Recria 1", n: 31, idade: [7, 10], kg: [190, 265], fixos: [] as string[] },
  { id: "13 - Novilhas Novas", n: 18, idade: [11, 15], kg: [275, 355], fixos: ["11153", "9378"] },
];

const ANIMAIS: Animal[] = (() => {
  const r = semente(77);
  const vistos = new Set<string>();
  const out: Animal[] = [];
  for (const L of LOTES) {
    const nums = [...L.fixos];
    nums.forEach((x) => vistos.add(x));
    while (nums.length < L.n) {
      const x = String(1000 + Math.floor(r() * 8999));
      if (!vistos.has(x)) { vistos.add(x); nums.push(x); }
    }
    nums.forEach((n, i) => out.push({
      n, lote: L.id, idade: Math.round(L.idade[0] + r() * (L.idade[1] - L.idade[0])),
      ant: i === 4 && L.id === "13 - Novilhas Novas" ? null : Math.round(L.kg[0] + r() * (L.kg[1] - L.kg[0])),
      antData: i === 4 && L.id === "13 - Novilhas Novas" ? null : (r() > 0.2 ? "2026-09-28" : "2026-09-12"),
    }));
  }
  return out;
})();

// Pesos já digitados no exemplo: GMD plausível em quase todos, uma que perdeu peso (11153) e uma digitação de 1ª pesagem.
const PESOS_INICIAIS: Record<string, string> = (() => {
  const p: Record<string, string> = {};
  let k = 0;
  for (const a of ANIMAIS) {
    if (a.lote === "13 - Novilhas Novas") {
      if (a.ant === null) { p[a.n] = "262"; continue; }
      if (k < 13) {
        const dias = diasEntre(a.antData as string, HOJE_ISO);
        p[a.n] = String(Math.round(a.ant + dias * (0.62 + (k % 5) * 0.07)));
        k++;
      }
    }
  }
  const perdeu = ANIMAIS.filter((a) => a.lote === "13 - Novilhas Novas" && a.ant !== null).sort((a, b) => a.n.localeCompare(b.n, "pt-BR", { numeric: true }))[2];
  if (perdeu?.ant) p[perdeu.n] = String(perdeu.ant - 6);
  return p;
})();

const HISTORICO = (() => {
  const r = semente(5);
  const doLote = (l: string) => ANIMAIS.filter((a) => a.ant !== null && a.lote === l).slice(0, 8);
  return [...doLote("01 - Novilhas Alta"), ...doLote("13 - Novilhas Novas")].map((a, i) => {
    const ult = a.ant as number;
    const ultData = a.antData as string;
    const primData = somarDias("2026-05-04", Math.floor(r() * 14));
    const dias = diasEntre(primData, ultData);
    const gmd = i === 10 ? -0.05 : 0.55 + r() * 0.4;
    const prim = Math.round(ult - gmd * dias);
    const g = Math.round(((ult - prim) / dias) * 100) / 100;
    return { n: a.n, lote: a.lote, np: 3 + Math.floor(r() * 4), primData, prim, ultData, ult, gmd: g, gpd: Math.round((g + (r() - 0.5) * 0.12) * 100) / 100 };
  });
})();

const th = { textAlign: "right" as const };
const BTN_LINHA: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: "0.4rem" };
const altura = { ["--gv-altura-tabela" as string]: "52rem" } as React.CSSProperties;
const topo: React.CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "1.5rem" };

export function PesagemCorporal({ abaInicial = "lancar" }: { abaInicial?: Aba }) {
  const [aba, setAba] = useState<Aba>(abaInicial);
  const [modo, setModo] = useState<Modo>("lote");
  const [data, setData] = useState(HOJE_ISO);
  const [lotesSel, setLotesSel] = useState<string[]>(["13 - Novilhas Novas"]);
  const [busca, setBusca] = useState("");
  const [pesos, setPesos] = useState<Record<string, string>>(PESOS_INICIAIS);
  const [retorno, setRetorno] = useState<React.ReactNode>(null);
  // Histórico
  const [ver, setVer] = useState<"todos" | "lote" | "animal">("todos");
  const [loteRel, setLoteRel] = useState("13 - Novilhas Novas");
  const [ini, setIni] = useState("2026-05-01");
  const [fim, setFim] = useState(HOJE_ISO);

  const alternarLote = (id: string) => setLotesSel((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const visiveis = useMemo(() => {
    const base = modo === "animal"
      ? (busca.trim() ? ANIMAIS.filter((a) => a.n.includes(busca.trim())).slice(0, 6) : [])
      : ANIMAIS.filter((a) => lotesSel.includes(a.lote));
    return [...base].sort((a, b) => a.lote.localeCompare(b.lote, "pt-BR", { numeric: true }) || a.n.localeCompare(b.n, "pt-BR", { numeric: true }));
  }, [modo, busca, lotesSel]);
  const grupos = useMemo(() => {
    const m = new Map<string, Animal[]>();
    visiveis.forEach((a) => m.set(a.lote, [...(m.get(a.lote) ?? []), a]));
    return [...m.entries()];
  }, [visiveis]);

  const pesoDe = (n: string) => { const v = numOuNull(pesos[n]); return v !== null && v > 0 ? v : null; };
  const calc = (a: Animal) => {
    const novo = pesoDe(a.n);
    if (novo === null || a.ant === null || !a.antData) return { novo, ganho: null as number | null, gmd: null as number | null, dias: a.antData ? diasEntre(a.antData, data) : null };
    const dias = Math.max(1, diasEntre(a.antData, data));
    return { novo, ganho: novo - a.ant, gmd: (novo - a.ant) / dias, dias };
  };
  const pesados = visiveis.filter((a) => pesoDe(a.n) !== null);
  const pesoMedio = pesados.length ? pesados.reduce((s, a) => s + (pesoDe(a.n) ?? 0), 0) / pesados.length : 0;
  const gmds = pesados.map((a) => calc(a).gmd).filter((x): x is number => x !== null);
  const gmdMedio = gmds.length ? gmds.reduce((s, x) => s + x, 0) / gmds.length : 0;
  const perderam = pesados.filter((a) => (calc(a).ganho ?? 0) < 0).length;

  function salvar() {
    setRetorno(<span role="status" style={{ color: "var(--ft-verde)" }}>✓ {pesados.length} pesagens lançadas em {dataBR(data)} · peso médio {nb(pesoMedio)} kg</span>);
    setPesos((p) => { const n = { ...p }; pesados.forEach((a) => { delete n[a.n]; }); return n; });
  }

  const nomeModo = modo === "animal" ? "Por animal" : modo === "lote" ? "Por lote" : "Planilha";
  const hist = HISTORICO.filter((h) => ver === "todos" || (ver === "lote" ? h.lote === loteRel : busca ? h.n.includes(busca) : true));
  const histGrupos = useMemo(() => {
    const m = new Map<string, typeof HISTORICO>();
    hist.forEach((h) => m.set(h.lote, [...(m.get(h.lote) ?? []), h]));
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b, "pt-BR", { numeric: true }));
  }, [hist]);
  const histGmd = hist.length ? hist.reduce((s, h) => s + h.gmd, 0) / hist.length : 0;
  const histGpd = hist.length ? hist.reduce((s, h) => s + h.gpd, 0) / hist.length : 0;

  return (
    <QuadroGaveta titulo="Lançar pesagem corporal" icone={Scale} largura={1320}>
      <div style={{ marginBottom: "0.9rem" }}>
        <Pilulas<Aba> rotulo="Parte da tela" valor={aba} onChange={setAba} opcoes={[
          { id: "lancar", nome: "Lançar pesagens", titulo: "Registrar o peso de hoje" },
          { id: "historico", nome: "Histórico de ganho (GMD / GPD)", titulo: "Relatório de crescimento por animal ou lote" },
        ]} />
      </div>

      {aba === "lancar" ? (
        <>
          <Faixa itens={[
            { rotulo: "Animais para pesar", valor: 85 },
            { rotulo: "Última pesagem do rebanho", valor: "28/09/2026" },
            { rotulo: "GMD médio da última pesagem", valor: <>0,78 <small style={{ fontSize: "0.7rem", fontWeight: 600 }}>kg/dia</small></> },
            { rotulo: "Sem pesar há mais de 60 dias", valor: 5, tom: "atencao" },
          ]} />

          <Passo n={1} id="pc-p1" titulo="Como lançar">
            <div style={topo}>
              <div className="gv-campo">
                <RotuloMini>Modalidade</RotuloMini>
                <Pilulas<Modo> rotulo="Modalidade" valor={modo} onChange={setModo} opcoes={[
                  { id: "animal", nome: "Por animal", titulo: "Um animal de cada vez" },
                  { id: "lote", nome: "Por lote", titulo: "Todos os animais de um ou mais lotes numa tabela" },
                  { id: "planilha", nome: "Planilha (Excel / CSV)", titulo: "Importar as pesagens preenchidas fora do app" },
                ]} />
              </div>
              {modo !== "planilha" && <Campo rotulo="Data da pesagem" id="pc-data"><input type="date" value={data} onChange={(e) => setData(e.target.value)} /></Campo>}
            </div>
            {modo === "planilha" && <Ajuda>A data de cada pesagem vem da planilha. O modelo traz as colunas certas; as linhas com erro são listadas depois da importação.</Ajuda>}
          </Passo>

          {modo !== "planilha" ? (
            <Passo n={2} id="pc-p2" titulo={modo === "animal" ? "Animal" : "Animais por lote"} direita={
              <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
                <Tecla>Enter</Tecla> avança para o próximo animal · <Tecla>Shift</Tecla>+<Tecla>Enter</Tecla> volta
              </span>
            }>
              {modo === "lote" ? (
                <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternarLote} opcoes={LOTES.map((L) => ({ id: L.id, nome: L.id, n: L.n }))} />
              ) : (
                <div className="gv-campo" style={{ maxWidth: "22rem" }}>
                  <label htmlFor="pc-busca">Buscar animal pelo número</label>
                  <input id="pc-busca" type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 3335" />
                </div>
              )}
              {visiveis.length === 0 ? (
                <div style={{ border: "1px dashed var(--border-strong, var(--border))", borderRadius: "var(--r-sm)", background: "var(--surface-2)", padding: "1.2rem", color: "var(--text-muted)", fontSize: "0.82rem" }}>
                  {modo === "lote" ? "Marque um ou mais lotes acima para listar os animais." : "Digite o número do animal para listá-lo."}
                </div>
              ) : (
                <div className="gv-tabela-moldura" style={altura}>
                  <table className="gv-tabela">
                    <thead>
                      <tr>
                        <th scope="col">Nº</th>
                        <th scope="col" style={th}>Idade (meses)</th>
                        <th scope="col" style={th}>Peso anterior (kg)</th>
                        <th scope="col" style={th}>Data anterior</th>
                        <th scope="col" style={th} title="Dias entre a pesagem anterior e a data desta">Dias</th>
                        <th scope="col" style={th}>Peso novo (kg)</th>
                        <th scope="col" style={th}>Ganho (kg)</th>
                        <th scope="col" style={th}>GMD (kg/dia)</th>
                        <th scope="col">Situação</th>
                      </tr>
                    </thead>
                    <tbody onKeyDown={aoApertarEnter}>
                      {grupos.map(([lote, as]) => (
                        <React.Fragment key={lote}>
                          <LinhaGrupo colSpan={9} titulo={lote} n={as.length} />
                          {as.map((a) => {
                            const c = calc(a);
                            const perdeu = c.ganho !== null && c.ganho < 0;
                            return (
                              <tr key={a.n} className={c.novo !== null ? "gv-linha-marcada" : undefined}>
                                <td className="gv-forte gv-num">{a.n}</td>
                                <td className="gv-num gv-dir">{a.idade}</td>
                                <td className="gv-num gv-dir">{a.ant !== null ? nb(a.ant, 0) : "—"}</td>
                                <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{a.antData ? dataBR(a.antData) : "—"}</td>
                                <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{c.dias ?? "—"}</td>
                                <td className="gv-dir">
                                  <input className="gv-celula-input" type="number" inputMode="decimal" step="1" min="0" data-nav="" placeholder="kg"
                                    aria-label={`Peso novo do animal ${a.n}, em kg`} value={pesos[a.n] ?? ""}
                                    onChange={(e) => setPesos((p) => ({ ...p, [a.n]: e.target.value }))} />
                                </td>
                                <td className="gv-num gv-dir gv-forte" style={perdeu ? { color: "var(--ft-verm)" } : undefined}>
                                  {c.ganho !== null ? `${c.ganho > 0 ? "+" : ""}${nb(c.ganho, 0)}` : "—"}
                                </td>
                                <td className="gv-num gv-dir gv-forte" style={perdeu ? { color: "var(--ft-verm)" } : undefined}>
                                  {c.gmd !== null ? nb(c.gmd, 2) : "—"}
                                </td>
                                <td>
                                  {perdeu ? <Selo tom="atencao">▼ Perdeu peso</Selo>
                                    : c.novo !== null && a.ant === null ? <Selo tom="info">1ª pesagem</Selo>
                                    : c.novo !== null ? <Selo tom="ok">Ganhou</Selo>
                                    : <span style={{ color: "var(--text-muted)" }}>—</span>}
                                </td>
                              </tr>
                            );
                          })}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="gv-ajuda" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <Info size={13} aria-hidden="true" style={{ flexShrink: 0 }} />
                <span>Ganho e GMD aparecem na hora, calculados sobre a pesagem anterior do próprio animal. Quem ficar em branco (ou com 0) não é lançado.</span>
              </p>
            </Passo>
          ) : (
            <Passo n={2} id="pc-p2" titulo="Planilha preenchida">
              <div className="gv-linha">
                <button type="button" className="btn-ghost" style={BTN_LINHA}><Download size={13} aria-hidden="true" /> Baixar modelo</button>
              </div>
              <CaixaArquivo nome="pesagens_17-10-2026.xlsx" detalhe="31 KB · pronta para importar" aceita=".xlsx, .xlsm ou .csv" />
              <Aviso2 />
            </Passo>
          )}

          <BarraAcao
            retorno={retorno}
            resumo={modo === "planilha"
              ? "Planilha escolhida · pesagens_17-10-2026.xlsx"
              : `${pesados.length} pesagens · peso médio ${nb(pesoMedio)} kg · GMD médio ${nb(gmdMedio, 2)} kg/dia`}
            detalhe={modo === "planilha"
              ? "Importa direto, sem pré-visualização; as linhas com erro aparecem depois"
              : `${nomeModo} · ${dataBR(data)}${perderam ? ` · ${perderam} perdeu peso: confira a digitação` : " · só vai quem tem peso maior que 0"}`}
            acao={<BotaoOuro onClick={salvar} desabilitado={modo !== "planilha" && !pesados.length}>
              {modo === "planilha" ? "Importar planilha" : `Salvar (${pesados.length})`}
            </BotaoOuro>}
          />
        </>
      ) : (
        <>
          <Faixa itens={[
            { rotulo: "Animais no filtro", valor: hist.length },
            { rotulo: "GMD médio", valor: <>{nb(histGmd, 2)} <small style={{ fontSize: "0.7rem", fontWeight: 600 }}>kg/dia</small></> },
            { rotulo: "GPD médio", valor: <>{nb(histGpd, 2)} <small style={{ fontSize: "0.7rem", fontWeight: 600 }}>kg/dia</small></> },
            { rotulo: "Perderam peso no período", valor: hist.filter((h) => h.gmd < 0).length, tom: "atencao" },
          ]} />

          <Passo n={1} id="pc-h1" titulo="O que ver" direita={
            <span className="gv-linha">
              <button type="button" className="btn-ghost" style={BTN_LINHA}><FileText size={13} aria-hidden="true" /> Exportar PDF</button>
              <button type="button" className="btn-ghost" style={BTN_LINHA}><FileSpreadsheet size={13} aria-hidden="true" /> Exportar Excel</button>
            </span>
          }>
            <div style={topo}>
              <div className="gv-campo">
                <RotuloMini>Ver</RotuloMini>
                <Pilulas<"todos" | "lote" | "animal"> rotulo="Ver" valor={ver} onChange={setVer} opcoes={[
                  { id: "todos", nome: "Todos os animais" }, { id: "lote", nome: "Um lote" }, { id: "animal", nome: "Um animal" },
                ]} />
              </div>
              {ver === "lote" && (
                <Campo rotulo="Lote" id="pc-h-lote">
                  <select value={loteRel} onChange={(e) => setLoteRel(e.target.value)}>
                    <option value="">Selecione…</option>
                    {LOTES.map((L) => <option key={L.id} value={L.id}>{L.id}</option>)}
                  </select>
                </Campo>
              )}
              {ver === "animal" && (
                <Campo rotulo="Animal" id="pc-h-animal"><input type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nº do animal" /></Campo>
              )}
              <Campo rotulo="Período de" id="pc-h-ini"><input type="date" value={ini} onChange={(e) => setIni(e.target.value)} /></Campo>
              <Campo rotulo="Período até" id="pc-h-fim"><input type="date" value={fim} onChange={(e) => setFim(e.target.value)} /></Campo>
            </div>
          </Passo>

          <Passo n={2} id="pc-h2" titulo="Ganho de peso por animal">
            <div className="gv-tabela-moldura" style={altura}>
              <table className="gv-tabela">
                <thead>
                  <tr>
                    <th scope="col">Nº</th>
                    <th scope="col" style={th}>Nº pesagens</th>
                    <th scope="col" style={th}>1ª pesagem</th><th scope="col" style={th}>1ª (kg)</th>
                    <th scope="col" style={th}>Última pesagem</th><th scope="col" style={th}>Última (kg)</th>
                    <th scope="col" style={th}>GMD (kg/dia)</th><th scope="col" style={th}>GPD (kg/dia)</th>
                    <th scope="col">Situação</th>
                  </tr>
                </thead>
                <tbody>
                  {histGrupos.map(([lote, hs]) => (
                    <React.Fragment key={lote}>
                      <LinhaGrupo colSpan={9} titulo={lote} n={hs.length} />
                      {hs.map((h) => (
                        <tr key={h.n}>
                          <td className="gv-forte gv-num">{h.n}</td>
                          <td className="gv-num gv-dir">{h.np}</td>
                          <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{dataBR(h.primData)}</td>
                          <td className="gv-num gv-dir">{nb(h.prim, 0)}</td>
                          <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{dataBR(h.ultData)}</td>
                          <td className="gv-num gv-dir">{nb(h.ult, 0)}</td>
                          <td className="gv-num gv-dir gv-forte" style={h.gmd < 0 ? { color: "var(--ft-verm)" } : undefined}>{nb(h.gmd, 2)}</td>
                          <td className="gv-num gv-dir gv-forte" style={h.gpd < 0 ? { color: "var(--ft-verm)" } : undefined}>{nb(h.gpd, 2)}</td>
                          <td>{h.gmd < 0 ? <Selo tom="atencao">▼ Perdeu peso</Selo> : <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                        </tr>
                      ))}
                    </React.Fragment>
                  ))}
                  {!hist.length && <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma pesagem no filtro.</td></tr>}
                </tbody>
              </table>
            </div>
            <Ajuda><b>GMD</b>: ganho médio diário entre a primeira e a última pesagem do período. <b>GPD</b>: média dos ganhos diários entre pesagens consecutivas. Para lançar uma pesagem nova, volte para “Lançar pesagens”.</Ajuda>
          </Passo>
        </>
      )}
    </QuadroGaveta>
  );
}

function Aviso2() {
  return (
    <p className="gv-ajuda" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
      <Info size={13} aria-hidden="true" style={{ flexShrink: 0 }} />
      <span>Depois de importar você vê aqui quantos lançamentos foram criados e as primeiras 10 linhas com erro.</span>
    </p>
  );
}
