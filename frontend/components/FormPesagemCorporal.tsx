"use client";
// Lançamentos › Produção › Pesagem corporal — duas partes na mesma tela: "Lançar pesagens" (por animal, por lote, planilha) e
// "Histórico de ganho (GMD / GPD)". Uma coluna, uma rolagem por lista, barra fixa no pé com resumo + retorno + Salvar em ouro.
//  • Props: animais, lotes, salvarPesagens (injeção do app de campo/offline; { criados, enviado? } — enviado === false =
//    "Sem internet — guardado, será enviado quando conectar.").
//  • Só vai peso maior que 0 (em branco/zero não é lançado). POST /producao/pesagens { data_pesagem, entradas }.
//  • Planilha: modelo + importação direta (sem pré-visualização); erros: contagem + até 10 mensagens.
//  • Peso anterior / data / dias / ganho / GMD vêm do relatório SEM filtro (GET /producao/pesagens/relatorio: última pesagem de
//    cada animal). Sem ele (offline, erro) a tabela volta ao formato simples (Nº, idade, peso novo). Enter avança; Tab continua.
//  • Histórico: o mesmo relatório com filtros (animal, lote, período), recarregado a cada filtro e após salvar; exporta PDF/Excel.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import {
  baixarModeloPesagemCorporal, criarPesagensCorporais, fetchRelatorioPesagemCorporal, formatDate, importarPesagemCorporalPlanilha,
} from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { Ajuda, Aviso, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, Selo } from "@/components/gerencial/kit";
import { LinhaGrupo, RotuloMini, aoApertarEnter, dataBR, nb } from "@/components/gerencial/telas/utilProducao";
import { BOTAO_COM_ICONE, DicaEnter, EscolhaArquivo, EstadoVazio, NotaInfo } from "@/components/gerencial/telas/pecasProducao";
import { casaBusca } from "@/lib/busca";
import {
  agruparPorLote, faixaPesagem, hojeLocalIso, mensagemDoErro, montarEntradasPesagem, pesoValido, resumoErros, sobreAnterior, type UltimaPesagem,
} from "@/lib/producaoLancamento";

const COLUNAS_PESAGEM = [
  { header: "Nº", key: "numero_matriz" }, { header: "Lote", key: "grupo_primario" },
  { header: "Nº pesagens", key: "num_pesagens" }, { header: "1ª pesagem (data)", key: "primeira_data_fmt" },
  { header: "1ª pesagem (kg)", key: "primeira_peso" }, { header: "Última pesagem (data)", key: "ultima_data_fmt" },
  { header: "Última pesagem (kg)", key: "ultima_peso" }, { header: "GMD (kg/dia)", key: "gmd_kg_dia" }, { header: "GPD (kg/dia)", key: "gpd_kg_dia" },
];

type Linha = {
  numero_matriz: string; grupo_primario: string | null;
  primeira_data: string; primeira_peso: number; ultima_data: string; ultima_peso: number;
  gmd_kg_dia: number | null; gpd_kg_dia: number | null; num_pesagens: number;
};

type EntradaPesagem = { numero_matriz: string; peso_kg: number };
type SalvarPesagens = (dados: { data_pesagem: string; entradas: EntradaPesagem[] }) => Promise<{ criados: number; enviado?: boolean }>;
type Aba = "lancar" | "historico";
type Modo = "animal" | "lote" | "planilha";
type Retorno = { tipo: "ok" | "erro"; texto: string } | null;

const ALTURA_TABELA = { ["--gv-altura-tabela" as string]: "52rem" } as React.CSSProperties;
const DIR = { textAlign: "right" as const };
const TOPO: React.CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "1.5rem" };
const MAX_RESULTADOS_BUSCA = 6;
const kg = (v: number) => nb(v, Number.isInteger(v) ? 0 : 1);

export function FormPesagemCorporal({ animais, lotes, salvarPesagens = criarPesagensCorporais }: { animais: AnimalRow[]; lotes: string[]; salvarPesagens?: SalvarPesagens }) {
  const [hoje] = useState(hojeLocalIso);
  const [aba, setAba] = useState<Aba>("lancar");

  // ── Lançar ──
  const [modo, setModo] = useState<Modo>("lote");
  const [data, setData] = useState(hoje);
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [busca, setBusca] = useState("");
  const [pesos, setPesos] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);
  const [retorno, setRetorno] = useState<Retorno>(null);
  // Planilha
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [importando, setImportando] = useState(false);
  const [errosPlanilha, setErrosPlanilha] = useState<string[]>([]);

  // Última pesagem de cada animal (relatório sem filtro). null = não carregou (offline/erro): tabela simples.
  const [ultimas, setUltimas] = useState<Linha[] | null>(null);
  const [versao, setVersao] = useState(0);
  const carregarUltimas = useCallback(() => {
    fetchRelatorioPesagemCorporal().then((d) => setUltimas(d.linhas as Linha[])).catch(() => setUltimas(null));
  }, []);
  useEffect(() => { carregarUltimas(); }, [carregarUltimas]);
  const anteriorDe = useMemo(() => {
    const m = new Map<string, UltimaPesagem>();
    for (const l of ultimas ?? []) m.set(l.numero_matriz, { ultima_data: l.ultima_data, ultima_peso: l.ultima_peso });
    return m;
  }, [ultimas]);
  const faixa = useMemo(() => faixaPesagem(animais.length, ultimas ?? [], hoje), [animais.length, ultimas, hoje]);
  const contagemPorLote = useMemo(() => {
    const m = new Map<string, number>();
    for (const a of animais) if (a.grupo_primario) m.set(a.grupo_primario, (m.get(a.grupo_primario) ?? 0) + 1);
    return m;
  }, [animais]);

  // O que está na tabela é o que será salvo. Por animal: o resultado da busca MAIS quem já tem peso digitado.
  const visiveis = useMemo(() => {
    if (modo === "lote") return animais.filter((a) => !!a.grupo_primario && lotesSel.includes(a.grupo_primario));
    if (modo !== "animal") return [];
    const achados = busca.trim() ? animais.filter((a) => casaBusca(a.numero, busca)).slice(0, MAX_RESULTADOS_BUSCA) : [];
    const digitados = animais.filter((a) => (pesos[a.numero] ?? "").trim() !== "");
    return Array.from(new Map([...achados, ...digitados].map((a) => [a.numero, a])).values());
  }, [modo, animais, lotesSel, busca, pesos]);
  const grupos = useMemo(
    () => agruparPorLote([...visiveis].sort((a, b) => a.numero.localeCompare(b.numero, "pt-BR", { numeric: true })), (a) => a.grupo_primario),
    [visiveis],
  );

  const calc = (a: AnimalRow) => sobreAnterior(pesoValido(pesos[a.numero]), anteriorDe.get(a.numero), data);
  const pesados = visiveis.filter((a) => pesoValido(pesos[a.numero]) !== null);
  const pesoMedio = pesados.length ? pesados.reduce((s, a) => s + (pesoValido(pesos[a.numero]) ?? 0), 0) / pesados.length : 0;
  const gmds = pesados.map((a) => calc(a).gmd).filter((x): x is number => x !== null);
  const gmdMedio = gmds.length ? gmds.reduce((s, x) => s + x, 0) / gmds.length : 0;
  const perderam = pesados.filter((a) => (calc(a).ganho ?? 0) < 0).length;
  const alternarLote = (id: string) => setLotesSel((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  function trocarModo(m: Modo) { setModo(m); setRetorno(null); setErrosPlanilha([]); }

  async function salvar() {
    setRetorno(null);
    const entradas = montarEntradasPesagem(visiveis.map((a) => a.numero), pesos);
    if (!entradas.length) {
      setRetorno({ tipo: "erro", texto: modo === "animal" ? "Selecione o animal e informe o peso." : "Informe o peso de ao menos um animal do lote." });
      return;
    }
    setSalvando(true);
    try {
      const r = await salvarPesagens({ data_pesagem: data, entradas });
      const medio = entradas.reduce((s, e) => s + e.peso_kg, 0) / entradas.length;
      setRetorno({
        tipo: "ok",
        texto: r.enviado === false
          ? "Sem internet — guardado, será enviado quando conectar."
          : `${r.criados} ${r.criados === 1 ? "pesagem lançada" : "pesagens lançadas"} em ${dataBR(data)} · peso médio ${nb(medio)} kg`,
      });
      setPesos((p) => { const n = { ...p }; entradas.forEach((e) => { delete n[e.numero_matriz]; }); return n; });
      carregarUltimas(); setVersao((v) => v + 1);
    } catch (e) {
      setRetorno({ tipo: "erro", texto: mensagemDoErro(e, "Erro ao lançar pesagem corporal") });
    } finally {
      setSalvando(false);
    }
  }

  async function importar() {
    if (!arquivo) return;
    setImportando(true); setRetorno(null); setErrosPlanilha([]);
    try {
      const r = await importarPesagemCorporalPlanilha(arquivo);
      setErrosPlanilha(r.erros);
      setRetorno({ tipo: "ok", texto: `${r.criados} lançamento(s) criado(s)${r.erros.length ? ` — ${r.erros.length} linha(s) com erro` : "."}` });
      setArquivo(null);
      carregarUltimas(); setVersao((v) => v + 1);
    } catch (e) {
      setRetorno({ tipo: "erro", texto: mensagemDoErro(e, "Erro ao importar planilha") });
    } finally {
      setImportando(false);
    }
  }

  // ── Histórico de ganho (GMD / GPD) ──
  const [relTipo, setRelTipo] = useState<"animal" | "lote" | "todos">("todos");
  const [relAnimal, setRelAnimal] = useState("");
  const [relLote, setRelLote] = useState("");
  const [relIni, setRelIni] = useState("");
  const [relFim, setRelFim] = useState("");
  // O resultado guarda de qual filtro ele é: "carregando" = o filtro atual ainda não tem resposta (sem setState dentro do efeito).
  const [resposta, setResposta] = useState<{ chave: string; linhas: Linha[] } | null>(null);
  const chaveRel = JSON.stringify([relTipo, relAnimal, relLote, relIni, relFim, versao]);
  useEffect(() => {
    if (aba !== "historico") return;
    let vivo = true;
    fetchRelatorioPesagemCorporal({
      numero_matriz: relTipo === "animal" ? relAnimal || undefined : undefined,
      grupo: relTipo === "lote" ? relLote || undefined : undefined,
      data_inicio: relIni || undefined,
      data_fim: relFim || undefined,
    }).then((d) => { if (vivo) setResposta({ chave: chaveRel, linhas: d.linhas }); })
      .catch(() => { if (vivo) setResposta({ chave: chaveRel, linhas: [] }); });
    return () => { vivo = false; };
  }, [aba, relTipo, relAnimal, relLote, relIni, relFim, versao, chaveRel]);
  const carregandoRel = !resposta || resposta.chave !== chaveRel;
  const hist = useMemo(() => resposta?.linhas ?? [], [resposta]);
  const histGrupos = useMemo(() => agruparPorLote(hist, (h) => h.grupo_primario), [hist]);
  const media = (xs: (number | null)[]) => { const v = xs.filter((x): x is number => x !== null); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null; };
  const histGmd = media(hist.map((h) => h.gmd_kg_dia));
  const histGpd = media(hist.map((h) => h.gpd_kg_dia));
  const kgDia = (v: number | null) => (v === null ? "—" : <>{nb(v, 2)} <small style={{ fontSize: "0.7rem", fontWeight: 600 }}>kg/dia</small></>);

  const aviso = retorno && (
    <span role={retorno.tipo === "erro" ? "alert" : "status"} style={{ color: retorno.tipo === "erro" ? "var(--ft-verm)" : "var(--ft-verde)" }}>
      {retorno.tipo === "ok" ? "✓ " : ""}{retorno.texto}
    </span>
  );
  const errosP = resumoErros(errosPlanilha, 10);
  const nomeModo = modo === "animal" ? "Por animal" : modo === "lote" ? "Por lote" : "Planilha";
  const comAnterior = ultimas !== null;
  const colunas = comAnterior ? 9 : 3;

  return (
    <div style={{ display: "flex", flexDirection: "column", fontSize: "0.85rem", color: "var(--text)" }}>
      <div style={{ marginBottom: "0.9rem" }}>
        <Pilulas<Aba> rotulo="Parte da tela" valor={aba} onChange={setAba} opcoes={[
          { id: "lancar", nome: "Lançar pesagens", titulo: "Registrar o peso de hoje" },
          { id: "historico", nome: "Histórico de ganho (GMD / GPD)", titulo: "Relatório de crescimento por animal ou lote" },
        ]} />
      </div>

      {aba === "lancar" ? (
        <>
          <Faixa itens={[
            { rotulo: "Animais cadastrados", valor: faixa.animais },
            { rotulo: "Última pesagem do rebanho", valor: faixa.ultimaPesagem ? dataBR(faixa.ultimaPesagem) : "—" },
            { rotulo: "GMD médio do histórico", valor: faixa.gmdMedio != null ? <>{nb(faixa.gmdMedio, 2)} <small style={{ fontSize: "0.7rem", fontWeight: 600 }}>kg/dia</small></> : "—" },
            { rotulo: "Sem pesar há mais de 60 dias", valor: faixa.semPesar, tom: faixa.semPesar ? "atencao" : undefined },
          ]} />

          <Passo n={1} id="pc-p1" titulo="Como lançar">
            <div style={TOPO}>
              <div className="gv-campo">
                <RotuloMini>Modalidade</RotuloMini>
                <Pilulas<Modo> rotulo="Modalidade" valor={modo} onChange={trocarModo} opcoes={[
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
            <Passo n={2} id="pc-p2" titulo={modo === "animal" ? "Animal" : "Animais por lote"} direita={<DicaEnter avanca="o próximo animal" />}>
              {modo === "lote" ? (
                <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternarLote} opcoes={lotes.map((l) => ({ id: l, nome: l, n: contagemPorLote.get(l) ?? 0 }))} />
              ) : (
                <div className="gv-campo" style={{ maxWidth: "22rem" }}>
                  <label htmlFor="pc-busca">Buscar animal pelo número</label>
                  <input id="pc-busca" type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 3335" />
                </div>
              )}
              {visiveis.length === 0 ? (
                <EstadoVazio>
                  {modo === "lote" ? (lotesSel.length ? "Nenhum animal neste lote." : "Marque um ou mais lotes acima para listar os animais.")
                    : busca.trim() ? "Nenhum animal com esse número." : "Digite o número do animal para listá-lo."}
                </EstadoVazio>
              ) : (
                <div className="gv-tabela-moldura" style={ALTURA_TABELA}>
                  <table className="gv-tabela">
                    <thead>
                      <tr>
                        <th scope="col">Nº</th>
                        <th scope="col" style={DIR}>Idade (meses)</th>
                        {comAnterior && <>
                          <th scope="col" style={DIR}>Peso anterior (kg)</th>
                          <th scope="col" style={DIR}>Data anterior</th>
                          <th scope="col" style={DIR} title="Dias entre a pesagem anterior e a data desta">Dias</th>
                        </>}
                        <th scope="col" style={DIR}>Peso novo (kg)</th>
                        {comAnterior && <>
                          <th scope="col" style={DIR}>Ganho (kg)</th>
                          <th scope="col" style={DIR}>GMD (kg/dia)</th>
                          <th scope="col">Situação</th>
                        </>}
                      </tr>
                    </thead>
                    <tbody onKeyDown={aoApertarEnter}>
                      {grupos.map(([lote, as]) => (
                        <React.Fragment key={lote}>
                          <LinhaGrupo colSpan={colunas} titulo={lote} n={as.length} />
                          {as.map((a) => {
                            const c = calc(a);
                            const ant = anteriorDe.get(a.numero);
                            const perdeu = c.ganho !== null && c.ganho < 0;
                            return (
                              <tr key={a.numero} className={c.novo !== null ? "gv-linha-marcada" : undefined}>
                                <td className="gv-forte gv-num">{a.numero}</td>
                                <td className="gv-num gv-dir">{a.idade_meses ?? "—"}</td>
                                {comAnterior && <>
                                  <td className="gv-num gv-dir">{ant ? kg(ant.ultima_peso) : "—"}</td>
                                  <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{ant ? dataBR(ant.ultima_data) : "—"}</td>
                                  <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{c.dias ?? "—"}</td>
                                </>}
                                <td className="gv-dir">
                                  <input className="gv-celula-input" type="number" inputMode="decimal" step="any" min="0" data-nav="" placeholder="kg"
                                    aria-label={`Peso novo do animal ${a.numero}, em kg`} value={pesos[a.numero] ?? ""}
                                    onChange={(e) => setPesos((p) => ({ ...p, [a.numero]: e.target.value }))} />
                                </td>
                                {comAnterior && <>
                                  <td className="gv-num gv-dir gv-forte" style={perdeu ? { color: "var(--ft-verm)" } : undefined}>
                                    {c.ganho !== null ? `${c.ganho > 0 ? "+" : ""}${nb(c.ganho, Number.isInteger(c.ganho) ? 0 : 1)}` : "—"}
                                  </td>
                                  <td className="gv-num gv-dir gv-forte" style={perdeu ? { color: "var(--ft-verm)" } : undefined}>
                                    {c.gmd !== null ? nb(c.gmd, 2) : "—"}
                                  </td>
                                  <td>
                                    {c.jaPesada && ant ? (
                                      <Selo tom="info" titulo="Lançar de novo na mesma data substitui o peso do dia">
                                        {ant.ultima_data === data ? "Já pesada nesta data" : `Pesagem em ${dataBR(ant.ultima_data, true)}`}
                                      </Selo>
                                    ) : perdeu ? <Selo tom="atencao">▼ Perdeu peso</Selo>
                                      : c.primeira ? <Selo tom="info">1ª pesagem</Selo>
                                      : c.novo !== null ? <Selo tom={(c.ganho ?? 0) > 0 ? "ok" : "neutro"}>{(c.ganho ?? 0) > 0 ? "Ganhou" : "Manteve"}</Selo>
                                      : <span style={{ color: "var(--text-muted)" }}>—</span>}
                                  </td>
                                </>}
                              </tr>
                            );
                          })}
                        </React.Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <NotaInfo>
                {comAnterior
                  ? "Ganho e GMD aparecem na hora, calculados sobre a pesagem anterior do próprio animal. "
                  : "Sem conexão com o histórico: a pesagem anterior não aparece, mas o lançamento funciona normalmente. "}
                Quem ficar em branco (ou com 0) não é lançado.
              </NotaInfo>
            </Passo>
          ) : (
            <Passo n={2} id="pc-p2" titulo="Planilha preenchida">
              <div className="gv-linha">
                <button type="button" className="btn-ghost" style={BOTAO_COM_ICONE}
                  onClick={() => baixarModeloPesagemCorporal().catch(() => setRetorno({ tipo: "erro", texto: "Erro ao baixar o modelo." }))}>
                  <Download size={13} aria-hidden="true" /> Baixar modelo
                </button>
              </div>
              <EscolhaArquivo id="pc-arquivo" arquivo={arquivo} aceita=".xlsx,.xlsm,.csv" detalhe="pronta para importar"
                onEscolher={(f) => { setArquivo(f); setRetorno(null); setErrosPlanilha([]); }} />
              {errosPlanilha.length > 0 && (
                <Aviso>
                  <span>
                    <b>{errosPlanilha.length} {errosPlanilha.length === 1 ? "linha com erro" : "linhas com erro"}:</b>
                    <span style={{ display: "block", marginTop: "0.2rem", color: "var(--text)" }}>{errosP.primeiras.join(" · ")}</span>
                    {errosP.resto > 0 && <span style={{ display: "block", color: "var(--text-muted)" }}>e mais {errosP.resto}.</span>}
                  </span>
                </Aviso>
              )}
              <NotaInfo>Importa direto, sem pré-visualização. Depois de importar você vê aqui quantos lançamentos foram criados e as primeiras 10 linhas com erro.</NotaInfo>
            </Passo>
          )}

          <BarraAcao
            retorno={aviso || undefined}
            resumo={modo === "planilha"
              ? (arquivo ? `Planilha escolhida · ${arquivo.name}` : "Nenhuma planilha escolhida")
              : `${pesados.length} ${pesados.length === 1 ? "pesagem" : "pesagens"} · peso médio ${nb(pesoMedio)} kg${comAnterior ? ` · GMD médio ${nb(gmdMedio, 2)} kg/dia` : ""}`}
            detalhe={modo === "planilha"
              ? "Importa direto, sem pré-visualização; as linhas com erro aparecem depois"
              : `${nomeModo} · ${data ? dataBR(data) : "sem data"}${perderam ? ` · ${perderam} perdeu peso: confira a digitação` : " · só vai quem tem peso maior que 0"}`}
            acao={modo === "planilha"
              ? <BotaoOuro onClick={importar} desabilitado={!arquivo || importando}>{importando ? "Importando…" : "Importar planilha"}</BotaoOuro>
              : <BotaoOuro onClick={salvar} desabilitado={!pesados.length || salvando || !data}>{salvando ? "Salvando…" : `Salvar (${pesados.length})`}</BotaoOuro>}
          />
        </>
      ) : (
        <>
          <Faixa itens={[
            { rotulo: "Animais no filtro", valor: hist.length },
            { rotulo: "GMD médio", valor: kgDia(histGmd) },
            { rotulo: "GPD médio", valor: kgDia(histGpd) },
            { rotulo: "Perderam peso no período", valor: hist.filter((h) => (h.gmd_kg_dia ?? 0) < 0).length, tom: hist.some((h) => (h.gmd_kg_dia ?? 0) < 0) ? "atencao" : undefined },
          ]} />

          <Passo n={1} id="pc-h1" titulo="O que ver" direita={
            <ExportarBotoes
              titulo="Relatório de crescimento (GMD/GPD)" nomeArquivoBase="pesagem_corporal" colunas={COLUNAS_PESAGEM}
              linhas={hist.map((l) => ({ ...l, primeira_data_fmt: formatDate(l.primeira_data), ultima_data_fmt: formatDate(l.ultima_data) }))}
            />
          }>
            <div style={TOPO}>
              <div className="gv-campo">
                <RotuloMini>Ver</RotuloMini>
                <Pilulas<"todos" | "lote" | "animal"> rotulo="Ver" valor={relTipo} onChange={(t) => { setRelTipo(t); setRelAnimal(""); setRelLote(""); }} opcoes={[
                  { id: "todos", nome: "Todos os animais" }, { id: "lote", nome: "Um lote" }, { id: "animal", nome: "Um animal" },
                ]} />
              </div>
              {relTipo === "lote" && (
                <Campo rotulo="Lote" id="pc-h-lote">
                  <select value={relLote} onChange={(e) => setRelLote(e.target.value)}>
                    <option value="">Selecione…</option>
                    {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </Campo>
              )}
              {relTipo === "animal" && (
                <div className="gv-campo" style={{ minWidth: "16rem" }}>
                  <RotuloMini>Animal</RotuloMini>
                  <AnimalPicker animais={animais} value={relAnimal} onChange={setRelAnimal} placeholder="Selecione…" />
                </div>
              )}
              <Campo rotulo="Período de" id="pc-h-ini"><input type="date" value={relIni} onChange={(e) => setRelIni(e.target.value)} /></Campo>
              <Campo rotulo="Período até" id="pc-h-fim"><input type="date" value={relFim} onChange={(e) => setRelFim(e.target.value)} /></Campo>
            </div>
          </Passo>

          <Passo n={2} id="pc-h2" titulo="Ganho de peso por animal">
            {carregandoRel ? (
              <p className="gv-ajuda" role="status">Carregando…</p>
            ) : (
              <div className="gv-tabela-moldura" style={ALTURA_TABELA}>
                <table className="gv-tabela">
                  <thead>
                    <tr>
                      <th scope="col">Nº</th>
                      <th scope="col" style={DIR}>Nº pesagens</th>
                      <th scope="col" style={DIR}>1ª pesagem</th><th scope="col" style={DIR}>1ª (kg)</th>
                      <th scope="col" style={DIR}>Última pesagem</th><th scope="col" style={DIR}>Última (kg)</th>
                      <th scope="col" style={DIR}>GMD (kg/dia)</th><th scope="col" style={DIR}>GPD (kg/dia)</th>
                      <th scope="col">Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {histGrupos.map(([lote, hs]) => (
                      <React.Fragment key={lote}>
                        <LinhaGrupo colSpan={9} titulo={lote} n={hs.length} />
                        {hs.map((h) => (
                          <tr key={h.numero_matriz}>
                            <td className="gv-forte gv-num">{h.numero_matriz}</td>
                            <td className="gv-num gv-dir">{h.num_pesagens}</td>
                            <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{dataBR(h.primeira_data)}</td>
                            <td className="gv-num gv-dir">{kg(h.primeira_peso)}</td>
                            <td className="gv-num gv-dir" style={{ color: "var(--text-muted)" }}>{dataBR(h.ultima_data)}</td>
                            <td className="gv-num gv-dir">{kg(h.ultima_peso)}</td>
                            <td className="gv-num gv-dir gv-forte" style={(h.gmd_kg_dia ?? 0) < 0 ? { color: "var(--ft-verm)" } : undefined}>{h.gmd_kg_dia != null ? nb(h.gmd_kg_dia, 2) : "—"}</td>
                            <td className="gv-num gv-dir gv-forte" style={(h.gpd_kg_dia ?? 0) < 0 ? { color: "var(--ft-verm)" } : undefined}>{h.gpd_kg_dia != null ? nb(h.gpd_kg_dia, 2) : "—"}</td>
                            <td>{(h.gmd_kg_dia ?? 0) < 0 ? <Selo tom="atencao">▼ Perdeu peso</Selo> : <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                          </tr>
                        ))}
                      </React.Fragment>
                    ))}
                    {!hist.length && <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma pesagem no filtro.</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
            <Ajuda><b>GMD</b>: ganho médio diário entre a primeira e a última pesagem do período. <b>GPD</b>: média dos ganhos diários entre pesagens consecutivas. Para lançar uma pesagem nova, volte para “Lançar pesagens”.</Ajuda>
          </Passo>
        </>
      )}
    </div>
  );
}
