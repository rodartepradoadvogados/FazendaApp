"use client";
// Lançamentos › Produção › Controle leiteiro — três jeitos de lançar (por vaca, por lote, planilha), sempre numa TABELA com
// o contexto da decisão (DEL, último controle, variação) e a barra fixa no pé (resumo + retorno + Salvar em ouro).
//  • Quem entra: vacas com lactação ABERTA (flag `em_lactacao` da API; sem ela, lote de lactação ou DEL > 0). Por lote, só as
//    `em_lactacao !== false`: o servidor recusa o lote inteiro se uma entrada não tiver lactação aberta.
//  • Ordenha em branco = null (nunca 0); só vai a vaca com ao menos 1 ordenha; 2 ou 3 ordenhas; data padrão = hoje.
//  • POST /producao/controles { data_controle, entradas: [{ numero_matriz, ordenhas }] }. Planilha: modelo por animal/lote,
//    pré-visualização editável (nada salvo até confirmar), erros de leitura (contagem + 5 primeiras + "e mais N").
//  • "Último controle" e "Variação" vêm de `producao_kg`/`producao_data` da API de animais (controle mais recente da vaca);
//    dado congelado do Ideagri não entra na variação. Enter avança de campo (só front); Tab continua.
import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, Download, Trash2 } from "lucide-react";
import {
  baixarModeloControleLeiteiro, confirmarControleLeiteiroPlanilha, criarControlesLeiteiros,
  preVisualizarControleLeiteiroPlanilha, ErroApi, type LinhaControleLeiteiroPreview,
} from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { Ajuda, Aviso, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, Selo } from "@/components/gerencial/kit";
import { LinhaGrupo, RotuloMini, aoApertarEnter, dataBR, nb } from "@/components/gerencial/telas/utilProducao";
import { BOTAO_COM_ICONE, DicaEnter, EscolhaArquivo, EstadoVazio, NotaInfo } from "@/components/gerencial/telas/pecasProducao";
import { casaBusca } from "@/lib/busca";
import {
  agruparPorLote, faixaControle, hojeLocalIso, jaTemControleNaData, mensagemDoErro, montarEntradasControle, numOuNull, resumoErros,
  totalDaVaca, vacaEmLactacao, vacasDoLoteParaControle, variacaoControle,
} from "@/lib/producaoLancamento";

type Modo = "vaca" | "lote" | "planilha";
type Coluna = "numero" | "del" | "ult" | "total";
// `semVaca`: a vaca que travou o lançamento por carência de leite com bloqueio
// total (409 `carencia_bloqueio` do sanitário) — a tela oferece lançar as outras.
type Retorno = { tipo: "ok" | "erro"; texto: string; semVaca?: string } | null;
type DetalheCarencia = { erro?: string; msg?: string; numero_matriz?: string; liberacao_leite?: string };
type RespostaControles = { criados: number; carencia?: { numero_matriz: string; modo: string; liberacao_leite: string }[] };

const ALTURA_TABELA = { ["--gv-altura-tabela" as string]: "40rem" } as React.CSSProperties;
const DIR = { textAlign: "right" as const };
const MAX_RESULTADOS_BUSCA = 8;

function Ordenavel({ rotulo, col, sort, onSort }: {
  rotulo: string; col: Coluna; sort: { col: Coluna; asc: boolean }; onSort: (c: Coluna) => void;
}) {
  const ativo = sort.col === col;
  const esquerda = col === "numero";
  return (
    <th scope="col" aria-sort={ativo ? (sort.asc ? "ascending" : "descending") : "none"} style={{ textAlign: esquerda ? "left" : "right" }}>
      <button type="button" onClick={() => onSort(col)} style={{
        all: "unset", cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "0.2rem", color: "inherit", font: "inherit",
        letterSpacing: "inherit", textTransform: "inherit", minHeight: "1.5rem",
      }}>
        {rotulo}{ativo && (sort.asc ? <ArrowUp size={11} aria-hidden="true" /> : <ArrowDown size={11} aria-hidden="true" />)}
      </button>
    </th>
  );
}

function CelulaVariacao({ total, vaca, data }: { total: number | null; vaca: AnimalRow; data: string }) {
  if (jaTemControleNaData(vaca, data)) {
    return <Selo tom="info" titulo="Esta vaca já tem controle nesta data: lançar de novo substitui o registro do dia">Já lançada nesta data</Selo>;
  }
  const v = variacaoControle(total, vaca, data);
  if (!v) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  return (
    <Selo tom={v.conferir ? "atencao" : "neutro"} titulo={`Variação de ${nb(v.pct, 0)}% sobre o último controle (${nb(vaca.producao_kg ?? 0)} kg)`}>
      {v.pct >= 0 ? "▲" : "▼"} {nb(Math.abs(v.pct), 0)}%{v.conferir ? " · conferir" : ""}
    </Selo>
  );
}

export function FormControle({ animais, lotesLact, onSalvo }: { animais: AnimalRow[]; lotesLact: string[]; onSalvo?: () => void }) {
  const [hoje] = useState(hojeLocalIso);
  const [modo, setModo] = useState<Modo>("lote");
  const [nOrd, setNOrd] = useState<2 | 3>(2);
  const [data, setData] = useState(hoje);
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [busca, setBusca] = useState("");
  const [valores, setValores] = useState<Record<string, string[]>>({});
  const [sort, setSort] = useState<{ col: Coluna; asc: boolean }>({ col: "numero", asc: true });
  const [salvando, setSalvando] = useState(false);
  const [retorno, setRetorno] = useState<Retorno>(null);
  const [relancar, setRelancar] = useState(0);

  // Planilha: ler → revisar/corrigir → confirmar (nada é salvo antes do "Confirmar").
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [lendo, setLendo] = useState(false);
  const [linhas, setLinhas] = useState<LinhaControleLeiteiroPreview[] | null>(null);
  const [errosLeitura, setErrosLeitura] = useState<string[]>([]);
  const [salvandoPlanilha, setSalvandoPlanilha] = useState(false);

  const vacasLact = useMemo(() => animais.filter((a) => vacaEmLactacao(a, lotesLact)), [animais, lotesLact]);
  const faixa = useMemo(() => faixaControle(vacasLact, hoje), [vacasLact, hoje]);
  const doLote = useMemo(() => vacasDoLoteParaControle(animais, lotesSel), [animais, lotesSel]);
  const contagemPorLote = useMemo(() => {
    const m = new Map<string, number>();
    for (const l of lotesLact) m.set(l, vacasDoLoteParaControle(animais, [l]).vacas.length);
    return m;
  }, [animais, lotesLact]);

  const temValor = (n: string) => (valores[n] ?? []).slice(0, nOrd).some((v) => v.trim() !== "");
  const totalDe = (n: string) => totalDaVaca(valores[n], nOrd);

  // O que está na tabela é o que será salvo: por lote, as vacas dos lotes marcados; por vaca, o resultado da busca MAIS
  // quem já tem ordenha digitada (trocar a busca nunca esconde — e nunca perde — o que foi digitado).
  const base: AnimalRow[] = useMemo(() => {
    if (modo === "lote") return doLote.vacas;
    if (modo !== "vaca") return [];
    const achadas = busca.trim() ? vacasLact.filter((v) => casaBusca(v.numero, busca)).slice(0, MAX_RESULTADOS_BUSCA) : [];
    const digitadas = vacasLact.filter((v) => (valores[v.numero] ?? []).slice(0, nOrd).some((x) => x.trim() !== ""));
    return Array.from(new Map([...achadas, ...digitadas].map((v) => [v.numero, v])).values());
  }, [modo, doLote, busca, vacasLact, valores, nOrd]);

  const grupos = useMemo(() => {
    const chave = (v: AnimalRow): number | string => {
      if (sort.col === "del") return v.del_dias ?? -1;
      if (sort.col === "ult") return v.producao_kg ?? -1;
      if (sort.col === "total") return totalDaVaca(valores[v.numero], nOrd) ?? -1;
      return v.numero;
    };
    const ordenada = [...base].sort((a, b) => {
      const x = chave(a), y = chave(b);
      const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "pt-BR", { numeric: true });
      return sort.asc ? c : -c;
    });
    return agruparPorLote(ordenada, (v) => v.grupo_primario);
  }, [base, sort, valores, nOrd]);

  const comPesagem = base.filter((v) => temValor(v.numero));
  const totalLote = comPesagem.reduce((s, v) => s + (totalDe(v.numero) ?? 0), 0);
  const media = comPesagem.length ? totalLote / comPesagem.length : 0;
  const totalPlanilha = (linhas ?? []).reduce((s, l) => s + (l.total_kg ?? 0), 0);

  const ordenar = (c: Coluna) => setSort((p) => ({ col: c, asc: p.col === c ? !p.asc : true }));
  const alternarLote = (id: string) => setLotesSel((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  function setOrdenha(numero: string, i: number, v: string) {
    setValores((p) => { const arr = [...(p[numero] ?? ["", "", ""])]; arr[i] = v; return { ...p, [numero]: arr }; });
  }
  function trocarModo(m: Modo) { setModo(m); setRetorno(null); }

  async function salvar() {
    setRetorno(null);
    // Ordenha em branco vira `null` (não lançada), nunca `0`: um 0 gravado como ordenha real puxaria a média para baixo.
    const entradas = montarEntradasControle(base.map((v) => v.numero), valores, nOrd);
    if (!entradas.length) {
      setRetorno({ tipo: "erro", texto: modo === "vaca" ? "Selecione a vaca e informe ao menos uma ordenha." : "Informe a pesagem de ao menos uma vaca do lote." });
      return;
    }
    setSalvando(true);
    try {
      const r: RespostaControles = await criarControlesLeiteiros({ data_controle: data, entradas });
      const kg = entradas.reduce((s, e) => s + e.ordenhas.reduce<number>((a, x) => a + (x ?? 0), 0), 0);
      // Vacas em carência de leite (sanitário): "descarte" grava fora do tanque; "tanque" segue normal, no log.
      const car = (r.carencia || []).map((c) => `${c.numero_matriz} (${c.modo === "descarte" ? "leite descartado" : "vai para o tanque"}, libera ${dataBR(c.liberacao_leite)})`);
      setRetorno({ tipo: "ok", texto: `${r.criados} ${r.criados === 1 ? "pesagem lançada" : "pesagens lançadas"} em ${dataBR(data)} · ${nb(kg)} kg`
        + (car.length ? ` · em carência: ${car.join("; ")}` : "") });
      setValores((p) => { const n = { ...p }; entradas.forEach((e) => { delete n[e.numero_matriz]; }); return n; });
      onSalvo?.();
    } catch (e) {
      const det = e instanceof ErroApi && e.detalhe && typeof e.detalhe === "object" ? (e.detalhe as DetalheCarencia) : null;
      if (det?.erro === "carencia_bloqueio" && det.numero_matriz) {
        setRetorno({ tipo: "erro", semVaca: det.numero_matriz,
          texto: `${det.msg || `${det.numero_matriz} está em carência de leite com bloqueio total.`} Nada foi gravado.` });
      } else {
        setRetorno({ tipo: "erro", texto: mensagemDoErro(e, "Erro ao lançar controle leiteiro") });
      }
    } finally {
      setSalvando(false);
    }
  }

  // Carência com bloqueio total: tira a vaca da pesagem e lança as outras.
  function lancarSemVaca(numero: string) {
    setValores((p) => { const n = { ...p }; delete n[numero]; return n; });
    setRetorno(null);
    setRelancar((x) => x + 1);
  }
  useEffect(() => {
    if (!relancar) return;
    const t = setTimeout(() => { salvar(); }, 0);
    return () => clearTimeout(t);
  }, [relancar]); // eslint-disable-line react-hooks/exhaustive-deps

  async function lerPlanilha() {
    if (!arquivo) return;
    setLendo(true); setRetorno(null);
    try {
      const r = await preVisualizarControleLeiteiroPlanilha(arquivo);
      setLinhas(r.linhas); setErrosLeitura(r.erros);
    } catch (e) {
      setRetorno({ tipo: "erro", texto: mensagemDoErro(e, "Erro ao ler a planilha") });
    } finally {
      setLendo(false);
    }
  }
  const atualizarLinha = (idx: number, patch: Partial<LinhaControleLeiteiroPreview>) =>
    setLinhas((p) => (p ? p.map((l, i) => (i === idx ? { ...l, ...patch } : l)) : p));
  const removerLinha = (idx: number) => setLinhas((p) => (p ? p.filter((_, i) => i !== idx) : p));
  async function confirmarPlanilha() {
    if (!linhas || !linhas.length) return;
    setSalvandoPlanilha(true); setRetorno(null);
    try {
      const r = await confirmarControleLeiteiroPlanilha(linhas);
      setRetorno({ tipo: "ok", texto: `${r.criados} lançamento(s) salvo(s) com sucesso.` });
      setLinhas(null); setArquivo(null); setErrosLeitura([]);
      onSalvo?.();
    } catch (e) {
      setRetorno({ tipo: "erro", texto: mensagemDoErro(e, "Erro ao salvar o controle leiteiro") });
    } finally {
      setSalvandoPlanilha(false);
    }
  }
  const baixarModelo = (m: "animal" | "lote") =>
    baixarModeloControleLeiteiro(m).catch(() => setRetorno({ tipo: "erro", texto: "Erro ao baixar o modelo." }));

  const nomeModo = modo === "vaca" ? "Por vaca" : modo === "lote" ? "Por lote" : "Planilha";
  const erros = resumoErros(errosLeitura, 5);
  const colunas = 5 + nOrd;
  const aviso = retorno && (
    <span role={retorno.tipo === "erro" ? "alert" : "status"} style={{ color: retorno.tipo === "erro" ? "var(--ft-verm)" : "var(--ft-verde)" }}>
      {retorno.tipo === "ok" ? "✓ " : ""}{retorno.texto}
      {retorno.semVaca && (
        <>{" "}<button type="button" className="san-link" onClick={() => lancarSemVaca(retorno.semVaca!)}>Lançar as outras sem a {retorno.semVaca}</button></>
      )}
    </span>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", fontSize: "0.85rem", color: "var(--text)" }}>
      <Faixa itens={[
        { rotulo: "Vacas em lactação", valor: faixa.vacas },
        { rotulo: "Último controle", valor: faixa.ultimoControle ? dataBR(faixa.ultimoControle) : "—" },
        { rotulo: "Média do último controle", valor: faixa.mediaUltimo != null ? <>{nb(faixa.mediaUltimo)} <small style={{ fontSize: "0.7rem", fontWeight: 600 }}>kg/vaca</small></> : "—" },
        { rotulo: "Sem controle há mais de 30 dias", valor: faixa.semControle, tom: faixa.semControle ? "atencao" : undefined },
      ]} />

      <Passo n={1} id="cl-p1" titulo="Como lançar">
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "1.5rem" }}>
          <div className="gv-campo">
            <RotuloMini>Modalidade</RotuloMini>
            <Pilulas<Modo> rotulo="Modalidade" valor={modo} onChange={trocarModo} opcoes={[
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
        {modo === "vaca" && <Ajuda>Digite o número para achar a vaca em lactação; a DEL e o último controle aparecem na própria linha.</Ajuda>}
        {modo === "planilha" && <Ajuda>Na planilha, a data de cada vaca vem do arquivo. Antes de salvar você revisa e corrige o que foi lido.</Ajuda>}
      </Passo>

      {modo !== "planilha" && (
        <Passo n={2} id="cl-p2" titulo={modo === "vaca" ? "Vaca em lactação" : "Vacas em lactação por lote"} direita={<DicaEnter avanca="a próxima ordenha / vaca" />}>
          {modo === "lote" ? (
            <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternarLote}
              opcoes={lotesLact.map((l) => ({ id: l, nome: l, n: contagemPorLote.get(l) ?? 0 }))} />
          ) : (
            <div className="gv-campo" style={{ maxWidth: "22rem" }}>
              <label htmlFor="cl-busca">Buscar vaca pelo número</label>
              <input id="cl-busca" type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 11153" />
            </div>
          )}
          <NotaInfo>
            {modo === "lote" && lotesSel.length > 0 && doLote.foraDaLactacao > 0
              ? `${doLote.foraDaLactacao} animal(is) do lote fora da lista por não ter lactação aberta (secas, novilhas, machos). `
              : "Só aparecem vacas com lactação aberta. "}
            O servidor recusa o lançamento de quem não tem lactação aberta; se a vaca pariu e não aparece, lance o parto antes.
          </NotaInfo>

          {base.length === 0 ? (
            <EstadoVazio>
              {modo === "lote" ? (lotesSel.length ? "Nenhuma vaca em lactação neste lote." : "Marque um ou mais lotes acima para listar as vacas.")
                : busca.trim() ? "Nenhuma vaca em lactação com esse número." : "Digite o número da vaca para listá-la."}
            </EstadoVazio>
          ) : (
            <div className="gv-tabela-moldura" style={ALTURA_TABELA}>
              <table className="gv-tabela">
                <thead>
                  <tr>
                    <Ordenavel rotulo="Nº" col="numero" sort={sort} onSort={ordenar} />
                    <Ordenavel rotulo="DEL" col="del" sort={sort} onSort={ordenar} />
                    <Ordenavel rotulo="Último controle" col="ult" sort={sort} onSort={ordenar} />
                    {Array.from({ length: nOrd }, (_, i) => <th key={i} scope="col" style={DIR}>{i + 1}ª ordenha (kg)</th>)}
                    <Ordenavel rotulo="Total da vaca" col="total" sort={sort} onSort={ordenar} />
                    <th scope="col">Variação</th>
                  </tr>
                </thead>
                <tbody onKeyDown={aoApertarEnter}>
                  {grupos.map(([lote, vs]) => (
                    <React.Fragment key={lote}>
                      <LinhaGrupo colSpan={colunas} titulo={lote} n={vs.length} />
                      {vs.map((v) => {
                        const t = totalDe(v.numero);
                        return (
                          <tr key={v.numero} className={temValor(v.numero) ? "gv-linha-marcada" : undefined}>
                            <td className="gv-forte gv-num">{v.numero}</td>
                            <td className="gv-num gv-dir">{v.del_dias ?? "—"}</td>
                            <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}
                              title={v.producao_origem === "congelado" ? "Dado congelado do Ideagri: não anda mais" : undefined}>
                              {v.producao_kg != null
                                ? <>{nb(v.producao_kg)} kg{v.producao_data ? ` · ${dataBR(v.producao_data, true)}` : ""}{v.producao_origem === "congelado" ? " (Ideagri)" : ""}</>
                                : "—"}
                            </td>
                            {Array.from({ length: nOrd }, (_, i) => (
                              <td key={i} className="gv-dir">
                                <input className="gv-celula-input" type="number" inputMode="decimal" step="0.1" min="0" data-nav=""
                                  aria-label={`${i + 1}ª ordenha da vaca ${v.numero}, em kg`} placeholder="kg"
                                  value={(valores[v.numero] ?? [])[i] ?? ""} onChange={(e) => setOrdenha(v.numero, i, e.target.value)} />
                              </td>
                            ))}
                            <td className="gv-num gv-dir gv-forte">{t !== null ? nb(t) : "—"}</td>
                            <td><CelulaVariacao total={t} vaca={v} data={data} /></td>
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
              <button type="button" className="btn-ghost" style={BOTAO_COM_ICONE} onClick={() => baixarModelo("animal")}><Download size={13} aria-hidden="true" /> Modelo por animal</button>
              <button type="button" className="btn-ghost" style={BOTAO_COM_ICONE} onClick={() => baixarModelo("lote")}><Download size={13} aria-hidden="true" /> Modelo por lote</button>
              <span className="gv-espaco" style={{ flex: 1 }} />
              <button type="button" className="btn-primary" disabled={!arquivo || lendo || !!linhas} onClick={lerPlanilha}>{lendo ? "Lendo…" : "Ler planilha"}</button>
            </div>
            <EscolhaArquivo id="cl-arquivo" arquivo={arquivo} aceita=".xlsx,.xlsm,.csv"
              onEscolher={(f) => { setArquivo(f); setLinhas(null); setErrosLeitura([]); setRetorno(null); }}
              detalhe={linhas ? `${linhas.length} linhas lidas${errosLeitura.length ? ` · ${errosLeitura.length} ignoradas` : ""}` : undefined} />
            <Ajuda>Baixe o modelo, preencha fora do app e anexe aqui — antes de salvar, você revisa e pode corrigir os valores lidos.</Ajuda>
          </Passo>
          {linhas && (
            <Passo n={3} id="cl-p3" titulo="Revise o que foi lido" direita={<Selo tom="info">Nada foi salvo ainda</Selo>}>
              {errosLeitura.length > 0 && (
                <Aviso>
                  <AlertTriangle size={15} aria-hidden="true" style={{ marginTop: "0.1rem", flexShrink: 0 }} />
                  <span>
                    <b>{errosLeitura.length} {errosLeitura.length === 1 ? "linha da planilha não pôde ser lida e foi ignorada" : "linhas da planilha não puderam ser lidas e foram ignoradas"}.</b>
                    {erros.resto > 0 ? ` Primeiras ${erros.primeiras.length}:` : ""}
                    <span style={{ display: "block", marginTop: "0.2rem", color: "var(--text)" }}>{erros.primeiras.join(" · ")}</span>
                    {erros.resto > 0 && <span style={{ display: "block", color: "var(--text-muted)" }}>e mais {erros.resto}. Corrija na planilha e leia de novo, se precisar delas.</span>}
                  </span>
                </Aviso>
              )}
              <div className="gv-tabela-moldura" style={ALTURA_TABELA}>
                <table className="gv-tabela">
                  <thead>
                    <tr>
                      <th scope="col">Nº</th><th scope="col">Data</th>
                      <th scope="col" style={DIR}>1ª ordenha (kg)</th><th scope="col" style={DIR}>2ª ordenha (kg)</th><th scope="col" style={DIR}>3ª ordenha (kg)</th>
                      <th scope="col" style={DIR}>Total (kg)</th><th scope="col" aria-label="Remover linha" style={{ width: "2.5rem" }}></th>
                    </tr>
                  </thead>
                  <tbody onKeyDown={aoApertarEnter}>
                    {linhas.map((l, idx) => (
                      <tr key={`${l.numero_matriz}-${idx}`}>
                        <td className="gv-forte gv-num">{l.numero_matriz}</td>
                        <td><input className="gv-celula-input" style={{ width: "8.5rem", textAlign: "left" }} type="date" value={l.data_controle} data-nav=""
                          aria-label={`Data da vaca ${l.numero_matriz}`} onChange={(e) => atualizarLinha(idx, { data_controle: e.target.value })} /></td>
                        {(["ordenha1_kg", "ordenha2_kg", "ordenha3_kg", "total_kg"] as const).map((campo, i) => (
                          <td key={campo} className="gv-dir">
                            <input className="gv-celula-input" type="number" inputMode="decimal" step="0.1" data-nav=""
                              aria-label={`${campo === "total_kg" ? "Total" : `${i + 1}ª ordenha`} da vaca ${l.numero_matriz}`}
                              value={l[campo] ?? ""} onChange={(e) => atualizarLinha(idx, { [campo]: numOuNull(e.target.value) })} />
                          </td>
                        ))}
                        <td className="gv-dir">
                          <button type="button" className="btn-ghost" style={BOTAO_COM_ICONE} aria-label={`Remover a linha da vaca ${l.numero_matriz}`} title="Remover esta linha" onClick={() => removerLinha(idx)}>
                            <Trash2 size={13} aria-hidden="true" />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {!linhas.length && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma linha restante.</td></tr>}
                  </tbody>
                </table>
              </div>
            </Passo>
          )}
        </>
      )}

      <BarraAcao
        retorno={aviso || undefined}
        resumo={modo === "planilha"
          ? (linhas ? `${linhas.length} lançamentos prontos · total ${nb(totalPlanilha)} kg` : "Nenhuma planilha lida ainda")
          : `${comPesagem.length} com pesagem de ${base.length} · total ${nb(totalLote)} kg · média ${nb(media)} kg/vaca`}
        detalhe={modo === "planilha"
          ? (linhas ? "Planilha · confira os valores acima antes de confirmar" : "Escolha o arquivo e clique em “Ler planilha”")
          : `${nomeModo} · ${nOrd} ordenhas · ${data ? dataBR(data) : "sem data"} · só vai quem tem ao menos 1 ordenha`}
        secundaria={modo === "planilha" && linhas ? (
          <button type="button" className="btn-ghost" onClick={() => { setLinhas(null); setErrosLeitura([]); }}>Cancelar</button>
        ) : undefined}
        acao={modo === "planilha" ? (
          <BotaoOuro onClick={confirmarPlanilha} desabilitado={!linhas?.length || salvandoPlanilha}>
            {salvandoPlanilha ? "Salvando…" : `Confirmar e salvar (${linhas?.length ?? 0})`}
          </BotaoOuro>
        ) : (
          <BotaoOuro onClick={salvar} desabilitado={!comPesagem.length || salvando || !data}>
            {salvando ? "Salvando…" : `Salvar (${comPesagem.length})`}
          </BotaoOuro>
        )}
      />
    </div>
  );
}
