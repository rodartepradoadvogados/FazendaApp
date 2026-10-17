"use client";
// Lançamentos › Produção › Controle leiteiro — PROPOSTA de tela gerencial (variante desktop, só apresentação, dados de exemplo).
// Substitui components/lancamentos/FormControle.tsx (dois painéis com rolagem própria, "Total do lote" no cabeçalho do card,
// "Salvar" sem contagem). A versão ligada a dados precisa PRESERVAR:
//  • Fonte da lista de vacas: flag `em_lactacao` da API de animais (fallback: lote de lactação OU del_dias > 0 quando undefined);
//    por lote entram só as `em_lactacao !== false` — o servidor recusa o lote inteiro se uma entrada não tiver lactação aberta.
//  • Ordenha em branco = null (nunca 0); só envia vaca com ≥ 1 ordenha; nº de ordenhas 2 | 3; data padrão = hoje.
//  • POST /producao/controles { data_controle, entradas: [{ numero_matriz, ordenhas: (number|null)[] }] } (criarControlesLeiteiros).
//  • Planilha: baixarModeloControleLeiteiro("animal" | "lote"); upload .xlsx/.xlsm/.csv → preVisualizarControleLeiteiroPlanilha
//    (POST /producao/controle-leiteiro/pre-visualizar → { linhas, erros }); linhas editáveis (data, 1ª–3ª ordenha, total; remover
//    linha); confirmarControleLeiteiroPlanilha(linhas) (POST /producao/controle-leiteiro/confirmar → { criados }).
//    Erros de leitura: contagem + as 5 primeiras mensagens; o resto "e mais N".
//  • Colunas novas (último controle, variação) exigem o último controle por vaca: campo novo na API de animais ou no GET de
//    controles (não existe hoje) — se faltar, a coluna some e o resto continua igual.
//  • Enter avança (ordem do DOM: ordenhas da vaca → próxima vaca) é só do front; Tab continua. Componentes sem estado interno do pai.
import React, { useMemo, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Download, Info, Milk, Trash2 } from "lucide-react";
import { Aviso, Ajuda, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, QuadroGaveta, Selo } from "@/components/gerencial/kit";
import { CaixaArquivo, LinhaGrupo, RotuloMini, Tecla, aoApertarEnter, dataBR, nb, numOuNull, semente, HOJE_ISO } from "./utilProducao";

type Modo = "vaca" | "lote" | "planilha";
type Vaca = { n: string; lote: string; del: number; ult: number; ultData: string };

const LOTES_LACT = [
  { id: "01 - Novilhas Alta", n: 11, del: [40, 180], kg: [17, 25], fixos: ["11153", "3335", "075", "9378"] },
  { id: "02 - Vacas Alta", n: 52, del: [60, 200], kg: [26, 41], fixos: [] as string[] },
  { id: "03 - Vacas Média", n: 62, del: [200, 330], kg: [15, 26], fixos: [] as string[] },
  { id: "04 - Pós-parto/Tratamento", n: 17, del: [2, 24], kg: [24, 38], fixos: [] as string[] },
];
const FORA_DA_LACTACAO = 31; // secas, novilhas e machos que compartilham o lote — não aparecem

// Vacas de exemplo geradas de forma determinística (a imagem sai sempre igual).
const VACAS: Vaca[] = (() => {
  const r = semente(2610);
  const vistos = new Set<string>();
  const out: Vaca[] = [];
  for (const L of LOTES_LACT) {
    const nums = [...L.fixos];
    nums.forEach((n) => vistos.add(n));
    while (nums.length < L.n) {
      const n = String(1000 + Math.floor(r() * 8999));
      if (!vistos.has(n)) { vistos.add(n); nums.push(n); }
    }
    for (const n of nums) {
      out.push({
        n, lote: L.id, del: Math.round(L.del[0] + r() * (L.del[1] - L.del[0])),
        ult: Math.round((L.kg[0] + r() * (L.kg[1] - L.kg[0])) * 10) / 10, ultData: r() > 0.12 ? "2026-10-03" : "2026-09-26",
      });
    }
  }
  return out;
})();
const TOTAL_LACTACAO = VACAS.length; // 142

// Digitação já feita no exemplo: dá o resumo da barra e mostra o selo de variação (uma digitação suspeita de cada lado).
const VALORES_INICIAIS: Record<string, string[]> = (() => {
  const v: Record<string, string[]> = {};
  const lote01 = VACAS.filter((x) => x.lote === "01 - Novilhas Alta");
  lote01.slice(0, 8).forEach((x, i) => {
    const metade = x.ult / 2;
    const a = Math.round((metade + ((i % 3) - 1) * 0.6) * 10) / 10;
    const b = Math.round((metade + ((i % 2) ? 0.4 : -0.3)) * 10) / 10;
    v[x.n] = [String(a), String(b), ""];
  });
  if (lote01[2]) v[lote01[2].n] = ["4.8", "11.2", ""];   // caiu muito: pode ser ordenha esquecida
  if (lote01[5]) v[lote01[5].n] = ["112", "10.9", ""];   // 112 em vez de 11,2: erro de vírgula
  if (lote01[7]) v[lote01[7].n] = ["10.1", "", ""];      // só a 1ª ordenha lançada (a 2ª fica null)
  return v;
})();

const PLANILHA_LINHAS = [
  { n: "11153", data: "2026-10-17", o: ["12.4", "11.8", ""], total: "24.2" },
  { n: "3335", data: "2026-10-17", o: ["10.2", "9.9", ""], total: "20.1" },
  { n: "075", data: "2026-10-17", o: ["9.6", "9.1", ""], total: "18.7" },
  { n: "9378", data: "2026-10-16", o: ["14.0", "13.2", ""], total: "27.2" },
  { n: "4410", data: "2026-10-17", o: ["13.3", "12.8", ""], total: "26.1" },
  { n: "2287", data: "2026-10-17", o: ["8.7", "8.4", ""], total: "17.1" },
  { n: "6031", data: "2026-10-17", o: ["15.1", "14.6", ""], total: "29.7" },
];
const PLANILHA_ERROS = [
  "Linha 9: nº “AB12” não foi encontrado no rebanho",
  "Linha 14: 2ª ordenha “dois” não é um número",
  "Linha 15: data 31/02/2026 inválida",
  "Linha 22: a vaca 5521 está fora da lactação",
  "Linha 31: nº 3335 repetido na planilha",
  "Linha 33: sem nenhuma ordenha preenchida",
  "Linha 40: data de outro ano (2025)",
];

const BTN_LINHA: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: "0.4rem" };
const th = { textAlign: "right" as const };
const gradeTop: React.CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "1.5rem" };
const altura = { ["--gv-altura-tabela" as string]: "40rem" } as React.CSSProperties;

function SeloVariacao({ total, ult }: { total: number; ult: number }) {
  const pct = ((total - ult) / ult) * 100;
  const suspeita = Math.abs(pct) >= 25;
  const seta = pct >= 0 ? "▲" : "▼";
  return (
    <Selo tom={suspeita ? "atencao" : "neutro"} titulo={`Variação de ${nb(pct, 0)}% sobre o último controle (${nb(ult)} kg)`}>
      {seta} {nb(Math.abs(pct), 0)}%{suspeita ? " · conferir" : ""}
    </Selo>
  );
}

function Ordenavel({ rotulo, col, sort, onSort, dir = "right" }: {
  rotulo: string; col: string; sort: { col: string; asc: boolean }; onSort: (c: string) => void; dir?: "left" | "right";
}) {
  const ativo = sort.col === col;
  return (
    <th scope="col" aria-sort={ativo ? (sort.asc ? "ascending" : "descending") : "none"} style={{ textAlign: dir }}>
      <button type="button" onClick={() => onSort(col)} style={{
        all: "unset", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.2rem", color: "inherit", font: "inherit",
        letterSpacing: "inherit", textTransform: "inherit",
      }}>
        {rotulo}{ativo && (sort.asc ? <ArrowUp size={11} aria-hidden="true" /> : <ArrowDown size={11} aria-hidden="true" />)}
      </button>
    </th>
  );
}

export function ControleLeiteiro({ modoInicial = "lote" }: { modoInicial?: Modo }) {
  const [modo, setModo] = useState<Modo>(modoInicial);
  const [nOrd, setNOrd] = useState<2 | 3>(2);
  const [data, setData] = useState(HOJE_ISO);
  const [lotesSel, setLotesSel] = useState<string[]>(["01 - Novilhas Alta", "04 - Pós-parto/Tratamento"]);
  const [busca, setBusca] = useState("");
  const [valores, setValores] = useState<Record<string, string[]>>(VALORES_INICIAIS);
  const [sort, setSort] = useState<{ col: string; asc: boolean }>({ col: "numero", asc: true });
  const [linhas, setLinhas] = useState(PLANILHA_LINHAS);
  const [retorno, setRetorno] = useState<React.ReactNode>(null);

  const ordenar = (c: string) => setSort((p) => ({ col: c, asc: p.col === c ? !p.asc : true }));
  const alternarLote = (id: string) => setLotesSel((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const totalDe = (n: string): number | null => {
    const vs = (valores[n] ?? []).slice(0, nOrd).map(numOuNull).filter((x): x is number => x !== null);
    return vs.length ? vs.reduce((s, x) => s + x, 0) : null;
  };

  const visiveis = useMemo(() => {
    const base = modo === "vaca"
      ? (busca.trim() ? VACAS.filter((v) => v.n.includes(busca.trim())).slice(0, 8) : [])
      : VACAS.filter((v) => lotesSel.includes(v.lote));
    const chave = (v: Vaca): number | string => {
      if (sort.col === "del") return v.del;
      if (sort.col === "ult") return v.ult;
      if (sort.col === "total") return totalDe(v.n) ?? -1;
      return v.n;
    };
    return [...base].sort((a, b) => {
      if (a.lote !== b.lote) return a.lote.localeCompare(b.lote, "pt-BR", { numeric: true });
      const x = chave(a), y = chave(b);
      const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "pt-BR", { numeric: true });
      return sort.asc ? c : -c;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modo, busca, lotesSel, sort, valores, nOrd]);

  const grupos = useMemo(() => {
    const m = new Map<string, Vaca[]>();
    visiveis.forEach((v) => m.set(v.lote, [...(m.get(v.lote) ?? []), v]));
    return [...m.entries()];
  }, [visiveis]);

  const comPesagem = visiveis.filter((v) => totalDe(v.n) !== null);
  const totalLote = comPesagem.reduce((s, v) => s + (totalDe(v.n) ?? 0), 0);
  const media = comPesagem.length ? totalLote / comPesagem.length : 0;
  const totalPlanilha = linhas.reduce((s, l) => s + (numOuNull(l.total) ?? 0), 0);

  function setOrdenha(n: string, i: number, v: string) {
    setValores((p) => { const arr = [...(p[n] ?? ["", "", ""])]; arr[i] = v; return { ...p, [n]: arr }; });
  }
  function salvar() {
    if (modo === "planilha") {
      setRetorno(<span role="status" style={{ color: "var(--ft-verde)" }}>✓ {linhas.length} lançamentos salvos da planilha</span>);
      return;
    }
    setRetorno(<span role="status" style={{ color: "var(--ft-verde)" }}>✓ {comPesagem.length} pesagens lançadas em {dataBR(data)} · {nb(totalLote)} kg</span>);
    setValores((p) => { const n = { ...p }; comPesagem.forEach((v) => { delete n[v.n]; }); return n; });
  }

  const nomeModo = modo === "vaca" ? "Por vaca" : modo === "lote" ? "Por lote" : "Planilha";
  const colunasTabela = 4 + nOrd;

  return (
    <QuadroGaveta titulo="Lançar controle leiteiro" icone={Milk} largura={1320}>
      <Faixa itens={[
        { rotulo: "Vacas em lactação", valor: TOTAL_LACTACAO },
        { rotulo: "Último controle", valor: "03/10/2026" },
        { rotulo: "Média do último controle", valor: <>24,6 <small style={{ fontSize: "0.7rem", fontWeight: 600 }}>kg/vaca</small></> },
        { rotulo: "Sem controle há mais de 30 dias", valor: 6, tom: "atencao" },
      ]} />

      <Passo n={1} id="cl-p1" titulo="Como lançar">
        <div style={gradeTop}>
          <div className="gv-campo">
            <RotuloMini>Modalidade</RotuloMini>
            <Pilulas<Modo> rotulo="Modalidade" valor={modo} onChange={setModo} opcoes={[
              { id: "vaca", nome: "Por vaca", titulo: "Uma vaca de cada vez" },
              { id: "lote", nome: "Por lote", titulo: "Todas as vacas de um ou mais lotes numa tabela" },
              { id: "planilha", nome: "Planilha (Excel / CSV)", titulo: "Importar o controle preenchido fora do app" },
            ]} />
          </div>
          {modo !== "planilha" && (
            <>
              <div className="gv-campo">
                <RotuloMini>Nº de ordenhas</RotuloMini>
                <Pilulas<"2" | "3"> rotulo="Número de ordenhas" valor={String(nOrd) as "2" | "3"} onChange={(i) => setNOrd(i === "3" ? 3 : 2)}
                  opcoes={[{ id: "2", nome: "2 ordenhas" }, { id: "3", nome: "3 ordenhas" }]} />
              </div>
              <Campo rotulo="Data do controle" id="cl-data"><input type="date" value={data} onChange={(e) => setData(e.target.value)} /></Campo>
            </>
          )}
        </div>
        {modo === "vaca" && <Ajuda>Digite o número para achar a vaca em lactação; a DEL aparece na própria linha.</Ajuda>}
        {modo === "planilha" && <Ajuda>Na planilha, a data de cada vaca vem do arquivo. Antes de salvar você revisa e corrige o que foi lido.</Ajuda>}
      </Passo>

      {modo !== "planilha" && (
        <Passo n={2} id="cl-p2" titulo={modo === "vaca" ? "Vaca em lactação" : "Vacas em lactação por lote"} direita={
          <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
            <Tecla>Enter</Tecla> avança para a próxima ordenha / vaca · <Tecla>Shift</Tecla>+<Tecla>Enter</Tecla> volta
          </span>
        }>
          {modo === "lote" ? (
            <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternarLote}
              opcoes={LOTES_LACT.map((L) => ({ id: L.id, nome: L.id, n: L.n }))} />
          ) : (
            <div className="gv-campo" style={{ maxWidth: "22rem" }}>
              <label htmlFor="cl-busca">Buscar vaca pelo número</label>
              <input id="cl-busca" type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 11153" />
            </div>
          )}
          <p className="gv-ajuda" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Info size={13} aria-hidden="true" style={{ flexShrink: 0 }} />
            <span>{FORA_DA_LACTACAO} animais fora da lactação (secas, novilhas, machos) não aparecem aqui — o servidor recusa o lançamento de quem não tem lactação aberta.</span>
          </p>

          {visiveis.length === 0 ? (
            <div style={{ border: "1px dashed var(--border-strong, var(--border))", borderRadius: "var(--r-sm)", background: "var(--surface-2)", padding: "1.2rem", color: "var(--text-muted)", fontSize: "0.82rem" }}>
              {modo === "lote" ? "Marque um ou mais lotes acima para listar as vacas." : "Digite o número da vaca para listá-la."}
            </div>
          ) : (
            <div className="gv-tabela-moldura" style={altura}>
              <table className="gv-tabela">
                <thead>
                  <tr>
                    <Ordenavel rotulo="Nº" col="numero" sort={sort} onSort={ordenar} dir="left" />
                    <Ordenavel rotulo="DEL" col="del" sort={sort} onSort={ordenar} />
                    <Ordenavel rotulo="Último controle" col="ult" sort={sort} onSort={ordenar} />
                    {Array.from({ length: nOrd }, (_, i) => <th key={i} scope="col" style={th}>{i + 1}ª ordenha (kg)</th>)}
                    <Ordenavel rotulo="Total da vaca" col="total" sort={sort} onSort={ordenar} />
                    <th scope="col">Variação</th>
                  </tr>
                </thead>
                <tbody onKeyDown={aoApertarEnter}>
                  {grupos.map(([lote, vs]) => (
                    <React.Fragment key={lote}>
                      <LinhaGrupo colSpan={colunasTabela + 1} titulo={lote} n={vs.length} />
                      {vs.map((v) => {
                        const t = totalDe(v.n);
                        return (
                          <tr key={v.n} className={t !== null ? "gv-linha-marcada" : undefined}>
                            <td className="gv-forte gv-num">{v.n}</td>
                            <td className="gv-num gv-dir">{v.del}</td>
                            <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{nb(v.ult)} kg · {dataBR(v.ultData, true)}</td>
                            {Array.from({ length: nOrd }, (_, i) => (
                              <td key={i} className="gv-dir">
                                <input className="gv-celula-input" type="number" inputMode="decimal" step="0.1" min="0" data-nav=""
                                  aria-label={`${i + 1}ª ordenha da vaca ${v.n}, em kg`} placeholder="kg"
                                  value={(valores[v.n] ?? [])[i] ?? ""} onChange={(e) => setOrdenha(v.n, i, e.target.value)} />
                              </td>
                            ))}
                            <td className="gv-num gv-dir gv-forte">{t !== null ? nb(t) : "—"}</td>
                            <td>{t !== null ? <SeloVariacao total={t} ult={v.ult} /> : <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                          </tr>
                        );
                      })}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Ajuda>“▲▼” compara o total do dia com o último controle da vaca; variação de 25% ou mais vem marcada “conferir” para pegar erro de digitação. Em branco = ordenha não lançada (nunca 0).</Ajuda>
        </Passo>
      )}

      {modo === "planilha" && (
        <>
          <Passo n={2} id="cl-p2" titulo="Planilha preenchida">
            <div className="gv-linha">
              <button type="button" className="btn-ghost" style={BTN_LINHA}><Download size={13} aria-hidden="true" /> Modelo por animal</button>
              <button type="button" className="btn-ghost" style={BTN_LINHA}><Download size={13} aria-hidden="true" /> Modelo por lote</button>
              <span className="gv-espaco" style={{ flex: 1 }} />
              <button type="button" className="btn-primary">Ler planilha</button>
            </div>
            <CaixaArquivo nome="controle_leiteiro_17-10-2026.xlsx" detalhe="48 KB · 7 linhas lidas · 7 ignoradas" aceita=".xlsx, .xlsm ou .csv" />
          </Passo>
          <Passo n={3} id="cl-p3" titulo="Revise o que foi lido" direita={<Selo tom="info">Nada foi salvo ainda</Selo>}>
            <Aviso>
              <AlertTriangle size={15} aria-hidden="true" style={{ marginTop: "0.1rem", flexShrink: 0 }} />
              <span>
                <b>{PLANILHA_ERROS.length} linhas da planilha não puderam ser lidas e foram ignoradas.</b> Primeiras 5:
                <span style={{ display: "block", marginTop: "0.2rem", color: "var(--text)" }}>{PLANILHA_ERROS.slice(0, 5).join(" · ")}</span>
                <span style={{ display: "block", color: "var(--text-muted)" }}>e mais {PLANILHA_ERROS.length - 5}. Corrija na planilha e leia de novo, se precisar delas.</span>
              </span>
            </Aviso>
            <div className="gv-tabela-moldura" style={altura}>
              <table className="gv-tabela">
                <thead>
                  <tr>
                    <th scope="col">Nº</th><th scope="col">Data</th>
                    <th scope="col" style={th}>1ª ordenha (kg)</th><th scope="col" style={th}>2ª ordenha (kg)</th><th scope="col" style={th}>3ª ordenha (kg)</th>
                    <th scope="col" style={th}>Total (kg)</th><th scope="col" aria-label="Remover linha" style={{ width: "2.5rem" }}></th>
                  </tr>
                </thead>
                <tbody onKeyDown={aoApertarEnter}>
                  {linhas.map((l, idx) => {
                    const atualizar = (patch: Partial<typeof l>) => setLinhas((p) => p.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
                    return (
                      <tr key={l.n}>
                        <td className="gv-forte gv-num">{l.n}</td>
                        <td><input className="gv-celula-input" style={{ width: "8.5rem", textAlign: "left" }} type="date" value={l.data} aria-label={`Data da vaca ${l.n}`} onChange={(e) => atualizar({ data: e.target.value })} data-nav="" /></td>
                        {[0, 1, 2].map((i) => (
                          <td key={i} className="gv-dir">
                            <input className="gv-celula-input" type="number" inputMode="decimal" step="0.1" data-nav="" aria-label={`${i + 1}ª ordenha da vaca ${l.n}`}
                              value={l.o[i]} onChange={(e) => atualizar({ o: l.o.map((x, j) => (j === i ? e.target.value : x)) })} />
                          </td>
                        ))}
                        <td className="gv-dir"><input className="gv-celula-input" type="number" inputMode="decimal" step="0.1" data-nav="" aria-label={`Total da vaca ${l.n}`} value={l.total} onChange={(e) => atualizar({ total: e.target.value })} /></td>
                        <td className="gv-dir">
                          <button type="button" className="btn-ghost" style={BTN_LINHA} aria-label={`Remover a linha da vaca ${l.n}`} title="Remover esta linha" onClick={() => setLinhas((p) => p.filter((_, i) => i !== idx))}>
                            <Trash2 size={13} aria-hidden="true" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                  {!linhas.length && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma linha restante.</td></tr>}
                </tbody>
              </table>
            </div>
          </Passo>
        </>
      )}

      <BarraAcao
        retorno={retorno}
        resumo={modo === "planilha"
          ? `${linhas.length} lançamentos prontos · total ${nb(totalPlanilha)} kg`
          : `${comPesagem.length} com pesagem de ${visiveis.length} · total do lote ${nb(totalLote)} kg · média ${nb(media)} kg/vaca`}
        detalhe={modo === "planilha"
          ? "Planilha · você revisou os valores acima"
          : `${nomeModo} · ${nOrd} ordenhas · ${dataBR(data)} · só vai quem tem ao menos 1 ordenha`}
        acao={<BotaoOuro onClick={salvar} desabilitado={modo === "planilha" ? !linhas.length : !comPesagem.length}>
          {modo === "planilha" ? `Confirmar e salvar (${linhas.length})` : `Salvar (${comPesagem.length})`}
        </BotaoOuro>}
      />
    </QuadroGaveta>
  );
}
