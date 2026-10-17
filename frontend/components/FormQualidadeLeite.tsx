"use client";
// Lançamentos › Produção › Qualidade do leite — tela gerencial (kit components/gerencial/kit.tsx).
// Também roda no app de campo: `salvarQualidade` é a prop de injeção offline (retorno `{ enviado: false }` = "guardado, sem internet").
// Regras puras (índices, faixas, classificação, payload) em lib/qualidadeLeite.ts, com testes.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, Upload } from "lucide-react";
import { criarQualidadeLeite, baixarModeloQualidadeLeite, importarQualidadeLeitePlanilha, fetchQualidadeLeite } from "@/lib/api";
import { fetchFaixasBonificacaoQualidade } from "@/lib/apiProducaoGerencial";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { Aviso, Ajuda, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas } from "@/components/gerencial/kit";
import { CSS_RAIZ } from "@/components/gerencial/producaoCss";
import { dataBR, diasEntre, hojeLocal, lerNumero, mensagemDe, nb, plural } from "@/lib/producaoGerencial";
import {
  INDICES, classificar, descreverFaixasLaticinio, faixasAtivasDoIndice, montarPayloadQualidade, ultimaColeta,
  type AlvoQualidade, type ChaveIndice, type DadosQualidadeLeite, type FaixaBonificacao, type Indice, type RegistroQualidade,
} from "@/lib/qualidadeLeite";

type SalvarQualidadeLeite = (dados: DadosQualidadeLeite) => Promise<{ enviado?: boolean } | void>;
type ResultadoImportacao = { criados: number; erros: string[] };

const ALVOS: { id: AlvoQualidade; nome: string; titulo: string; ajuda: string }[] = [
  { id: "tanque", nome: "Tanque (todas em lactação)", titulo: "Coleta única representando o rebanho em lactação (amostra do tanque)", ajuda: "Uma coleta única que representa todas as vacas em lactação (amostra do tanque)." },
  { id: "vaca", nome: "Uma vaca", titulo: "Coleta individual de uma vaca", ajuda: "Coleta individual de uma vaca — útil para investigar mastite." },
  { id: "planilha", nome: "Planilha", titulo: "Lançar várias coletas de uma vez, a partir de uma planilha (Excel ou CSV)", ajuda: "Várias coletas de uma vez, a partir de uma planilha (Excel ou CSV)." },
];

const SEM_FAIXAS: FaixaBonificacao[] = [];
const VAZIOS: Record<ChaveIndice, string> = { ccs: "", cbt: "", gordura: "", proteina: "", st: "", esd: "", lactose: "", nul: "" };

const CSS = `
.gq-tabela th[scope="row"] { text-align: left; font-weight: 400; padding: 0.42rem 0.6rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
.gq-tabela th[scope="row"] b { display: block; font-size: 0.85rem; font-weight: 800; }
.gq-tabela th[scope="row"] span { display: block; font-size: 0.72rem; color: var(--text-muted); }
.gq-valor { display: flex; align-items: center; gap: 0.5rem; }
.gq-valor .gv-celula-input { width: 6.2rem; min-height: 2rem; }
.gq-un { font-size: 0.72rem; color: var(--text-muted); }
.gq-ref b { font-weight: 800; font-variant-numeric: tabular-nums; }
.gq-ref span { display: block; font-size: 0.72rem; color: var(--text-muted); white-space: normal; }
.gq-ref .gq-lat { color: var(--ft-aco); }
.gq-delta { display: block; margin-top: 0.15rem; font-size: 0.72rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.gv-selo.gq-selo[data-tom="ok"] { color: var(--ft-verde); border-color: var(--ft-verde); }
.gv-selo.gq-selo[data-tom="atencao"] { color: var(--ft-ambar); border-color: var(--ft-ambar); background: transparent; }
.gv-selo.gq-selo[data-tom="fora"], .gv-selo.gq-selo[data-tom="invalido"] { color: var(--ft-verm); border-color: var(--ft-verm); }
.gq-linha-atencao > td, .gq-linha-atencao > th { background: color-mix(in srgb, var(--ft-ambar) 7%, transparent); }
.gq-linha-fora > td, .gq-linha-fora > th { background: color-mix(in srgb, var(--ft-verm) 6%, transparent); }
.gq-cabeca { display: flex; align-items: baseline; gap: 0.6rem; margin: 0 0 0.45rem; }
.gq-cabeca span:last-child { font-size: 0.76rem; color: var(--text-muted); text-transform: none; letter-spacing: 0; font-weight: 400; }
.gq-campos { display: grid; grid-template-columns: repeat(auto-fit, minmax(13rem, 24rem)); gap: 0.75rem; align-items: start; }
.gq-planilha { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.9rem; align-items: stretch; }
.gq-planilha-botoes { display: flex; flex-direction: column; gap: 0.5rem; justify-content: center; }
.gq-erros { margin: 0.3rem 0 0; padding-left: 1.1rem; color: var(--text-muted); font-size: 0.78rem; }
@media (max-width: 767px) { .gq-planilha { grid-template-columns: minmax(0, 1fr); } }
`;

/** Enter avança para o próximo campo da grade (Shift+Enter volta); Tab continua como sempre. */
function aoApertarEnter(e: React.KeyboardEvent<HTMLElement>) {
  if (e.key !== "Enter") return;
  const alvo = e.target as HTMLElement;
  if (!(alvo instanceof HTMLInputElement) || alvo.dataset.nav === undefined) return;
  e.preventDefault();
  const todos = Array.from(e.currentTarget.querySelectorAll<HTMLInputElement>("input[data-nav]"));
  const prox = todos[todos.indexOf(alvo) + (e.shiftKey ? -1 : 1)];
  if (prox) { prox.focus(); prox.select(); }
}

function valorDe(r: RegistroQualidade | null, i: Indice): number | null {
  const v = r?.[i.campo];
  return typeof v === "number" ? v : null;
}

function ColunaReferencia({ i, faixas }: { i: Indice; faixas: FaixaBonificacao[] }) {
  const lat = descreverFaixasLaticinio(faixas, i);
  return (
    <td className="gq-ref">
      <b>{i.refOk} {i.unidade}</b>
      <span>{i.refAtencao}</span>
      {lat && <span className="gq-lat">Seu laticínio — {lat}</span>}
    </td>
  );
}

export function FormQualidadeLeite({ animais, salvarQualidade = criarQualidadeLeite }: { animais: AnimalRow[]; salvarQualidade?: SalvarQualidadeLeite }) {
  const [alvo, setAlvo] = useState<AlvoQualidade>("tanque");
  const [vaca, setVaca] = useState("");
  const [data, setData] = useState(hojeLocal);
  const [valores, setValores] = useState<Record<ChaveIndice, string>>(VAZIOS);
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [retorno, setRetorno] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  const [registros, setRegistros] = useState<RegistroQualidade[] | null>(null);
  const [faixas, setFaixas] = useState<FaixaBonificacao[]>([]);

  const [arquivo, setArquivo] = useState<File | null>(null);
  const [sobre, setSobre] = useState(false);
  const [importando, setImportando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoImportacao | null>(null);
  const [erroPlanilha, setErroPlanilha] = useState<string | null>(null);
  const entradaArquivo = useRef<HTMLInputElement>(null);

  const carregarRegistros = useCallback(() => {
    fetchQualidadeLeite().then((d) => setRegistros(d.registros ?? [])).catch(() => setRegistros([]));
  }, []);
  useEffect(() => {
    carregarRegistros();
    fetchFaixasBonificacaoQualidade().then(setFaixas).catch(() => setFaixas([]));
  }, [carregarRegistros]);

  const alvoColeta: "tanque" | "vaca" = alvo === "vaca" ? "vaca" : "tanque";
  // As faixas do laticínio valem para a coleta do TANQUE (é o que ele paga); numa vaca só a faixa sugerida.
  const faixasDoAlvo = alvo === "tanque" ? faixas : SEM_FAIXAS;
  const ultimo = useMemo(() => (registros ? ultimaColeta(registros, alvoColeta, vaca) : null), [registros, alvoColeta, vaca]);
  const ultimoTanque = useMemo(() => (registros ? ultimaColeta(registros, "tanque", "") : null), [registros]);

  const linhas = useMemo(() => INDICES.map((i) => {
    const v = lerNumero(valores[i.chave]);
    const u = valorDe(ultimo, i);
    return { i, v, c: classificar(i, v, faixasDoAlvo), u, uc: u === null ? null : classificar(i, u, faixasDoAlvo) };
  }), [valores, ultimo, faixasDoAlvo]);

  const preenchidos = linhas.filter((l) => l.v !== null).length;
  const emAtencao = linhas.filter((l) => l.c?.situacao === "atencao");
  const fora = linhas.filter((l) => l.c?.situacao === "fora");
  const invalidos = linhas.filter((l) => l.c?.situacao === "invalido");

  const faltaVaca = alvo === "vaca" && !vaca;
  const faltaData = !data;
  const semSalvar = salvando || faltaVaca || faltaData || invalidos.length > 0;
  const quem = alvo === "tanque" ? "Tanque" : vaca ? `Vaca ${vaca}` : "Uma vaca";

  const resumo = alvo === "planilha"
    ? (arquivo ? `Planilha · ${arquivo.name}` : "Planilha · nenhum arquivo escolhido")
    : [quem, dataBR(data), preenchidos === 0 ? "nenhum índice preenchido" : `${preenchidos} ${plural(preenchidos, "índice preenchido", "índices preenchidos")}`,
       ...(emAtencao.length ? [`${emAtencao.length} em atenção`] : []), ...(fora.length ? [`${fora.length} fora da faixa`] : [])].join(" · ");

  const detalhe = alvo === "planilha"
    ? "Baixe o modelo, preencha e importe — cada linha vira uma coleta."
    : faltaVaca ? "Falta escolher a vaca."
    : faltaData ? "Falta a data da coleta."
    : invalidos.length ? `Corrija ${invalidos.map((l) => l.i.sigla).join(", ")}: use número, por exemplo 3,82.`
    : emAtencao.length + fora.length > 0
      ? `${[...emAtencao, ...fora].map((l) => `${l.i.sigla} ${nb(l.v as number, l.i.casas)}`).join(" · ")} — o selo só informa; salvar não é bloqueado.`
      : preenchidos === 0 ? "Sem índices o lançamento guarda só a data (todos são opcionais)." : "Todos os índices preenchidos estão na faixa.";

  async function salvar() {
    setRetorno(null);
    const p = montarPayloadQualidade({ alvo: alvoColeta, vaca, data, valores, observacao });
    if ("erro" in p) { setRetorno({ tipo: "erro", texto: p.erro }); return; }
    setSalvando(true);
    try {
      const r = await salvarQualidade(p.dados);
      const n = preenchidos;
      setRetorno({
        tipo: "ok",
        texto: r?.enviado === false
          ? "Sem internet — guardado, será enviado quando conectar."
          : `Qualidade do leite lançada — ${quem} · ${dataBR(data)} · ${n} ${plural(n, "índice", "índices")}.`,
      });
      setVaca(""); setValores(VAZIOS); setObservacao("");
      if (r?.enviado !== false) carregarRegistros(); // offline apagaria a lista já carregada
    } catch (e) {
      setRetorno({ tipo: "erro", texto: mensagemDe(e, "Erro ao lançar qualidade do leite") });
    } finally {
      setSalvando(false);
    }
  }

  async function importar() {
    if (!arquivo) return;
    setImportando(true); setErroPlanilha(null); setResultado(null);
    try {
      const r = await importarQualidadeLeitePlanilha(arquivo);
      setResultado(r); setArquivo(null);
      if (r.criados > 0) carregarRegistros();
    } catch (e) {
      setErroPlanilha(mensagemDe(e, "Erro ao importar planilha"));
    } finally {
      setImportando(false);
    }
  }

  const escolherArquivo = (f: File | null | undefined) => { setArquivo(f ?? null); setResultado(null); setErroPlanilha(null); };

  // Faixa de números: o último TANQUE lançado (o "estado do mundo" antes de lançar).
  const itensFaixa = (["ccs", "cbt", "gordura", "proteina"] as const).map((chave) => {
    const i = INDICES.find((x) => x.chave === chave) as Indice;
    const v = valorDe(ultimoTanque, i);
    const c = v === null ? null : classificar(i, v, faixas);
    return {
      rotulo: `${i.sigla} · ${i.unidade}`, valor: v === null ? "—" : nb(v, i.casas),
      tom: c?.situacao === "ok" ? ("ok" as const) : c?.situacao === "atencao" ? ("atencao" as const) : c?.situacao === "fora" ? ("alerta" as const) : undefined,
    };
  });
  const dias = ultimoTanque ? diasEntre(ultimoTanque.data_coleta, hojeLocal()) : null;

  const retornoNode = retorno
    ? (retorno.tipo === "ok"
      ? <span role="status" className="gp-ok">✓ {retorno.texto}</span>
      : <span role="alert" className="gp-erro">{retorno.texto}</span>)
    : undefined;

  const ajudaAlvo = ALVOS.find((a) => a.id === alvo)?.ajuda;

  return (
    <div className="gp-raiz">
      <style>{CSS_RAIZ + CSS}</style>

      <div className="gq-cabeca gv-rotulo">
        <span>{ultimoTanque ? `Último tanque · ${dataBR(ultimoTanque.data_coleta)}` : registros ? "Nenhuma coleta do tanque lançada ainda" : "Último tanque · carregando…"}</span>
        {dias !== null && <span>{dias <= 0 ? "hoje" : `há ${dias} ${plural(dias, "dia", "dias")}`}</span>}
      </div>
      <Faixa itens={itensFaixa} />

      <Passo n={1} id="ql-p1" titulo="O que foi coletado">
        <Pilulas<AlvoQualidade> rotulo="Alvo da coleta" opcoes={ALVOS.map((a) => ({ id: a.id, nome: a.nome, titulo: a.titulo }))} valor={alvo} onChange={(a) => { setAlvo(a); setRetorno(null); }} />
        <Ajuda>{ajudaAlvo}{alvo === "tanque" && " Tem várias coletas de uma vez? Use “Planilha”, ao lado."}</Ajuda>
        {alvo !== "planilha" && (
          <div className="gq-campos">
            <Campo rotulo="Data da coleta (obrigatória)" id="ql-data">
              <input type="date" value={data} onChange={(e) => setData(e.target.value)} />
            </Campo>
            {alvo === "vaca" && (
              <div className="gv-campo">
                <label id="ql-vaca-r">Vaca (obrigatória)</label>
                <AnimalPicker animais={animais} value={vaca} onChange={setVaca} placeholder="Selecione a vaca…" />
              </div>
            )}
          </div>
        )}
      </Passo>

      {alvo !== "planilha" ? (
        <>
          <Passo n={2} id="ql-p2" titulo="Índices do laudo" direita={<span className="gp-muda" style={{ fontSize: "0.8rem" }}>Todos opcionais — preencha só os que o laudo trouxer · aceita vírgula (3,82)</span>}>
            <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "none" }}>
              <table className="gv-tabela gq-tabela">
                <thead>
                  <tr>
                    <th scope="col">Índice</th><th scope="col">Valor do laudo</th><th scope="col">Situação</th>
                    <th scope="col" title="Faixas sugeridas — a confirmar com o dono">Faixa de referência (sugerida)</th>
                    <th scope="col">{alvo === "vaca" ? (vaca ? `Último da vaca ${vaca}${ultimo ? ` · ${dataBR(ultimo.data_coleta)}` : ""}` : "Último da vaca") : `Último tanque${ultimo ? ` · ${dataBR(ultimo.data_coleta)}` : ""}`}</th>
                  </tr>
                </thead>
                <tbody onKeyDown={aoApertarEnter}>
                  {linhas.map(({ i, v, c, u, uc }) => {
                    const sit = c?.situacao;
                    const delta = v !== null && Number.isFinite(v) && u !== null ? v - u : null;
                    return (
                      <tr key={i.chave} className={sit === "atencao" ? "gq-linha-atencao" : sit === "fora" || sit === "invalido" ? "gq-linha-fora" : undefined}>
                        <th scope="row"><b>{i.sigla}</b><span>{i.nome}</span></th>
                        <td>
                          <div className="gq-valor">
                            <input className="gv-celula-input" type="text" inputMode="decimal" autoComplete="off" data-nav
                              aria-label={`${i.sigla} (${i.unidade})`} aria-invalid={sit === "invalido"} placeholder="—"
                              value={valores[i.chave]} onChange={(e) => setValores((p) => ({ ...p, [i.chave]: e.target.value }))} />
                            <span className="gq-un">{i.unidade}</span>
                          </div>
                        </td>
                        <td>
                          {c && sit ? <span className="gv-selo gq-selo" data-tom={sit}>{c.rotulo}</span> : <span className="gq-un">sem valor</span>}
                          {c?.origem === "laticinio" && c.ajuste !== undefined && c.ajuste !== 0 && (
                            <span className="gq-delta">{c.ajuste > 0 ? "+" : "−"}R$ {Math.abs(c.ajuste).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}/L (tabela do laticínio)</span>
                          )}
                          {delta !== null && delta !== 0 && <span className="gq-delta">{delta > 0 ? "▲" : "▼"} {nb(Math.abs(delta), i.casas)} {delta > 0 ? "acima" : "abaixo"} do último</span>}
                        </td>
                        <ColunaReferencia i={i} faixas={faixasDoAlvo} />
                        <td className="gv-num">
                          {u === null ? <span className="gq-un">—</span> : (
                            <>
                              <b>{nb(u, i.casas)}</b> <span className="gq-un">{i.unidade}</span>
                              {uc && uc.situacao !== "ok" && <> <span className="gv-selo gq-selo" data-tom={uc.situacao}>{uc.rotulo}</span></>}
                            </>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Ajuda>
              Faixas de referência <strong>sugeridas</strong> (valores comuns no setor), a confirmar pelo dono. Os selos só informam e nunca impedem o Salvar.
              {alvo === "tanque" && faixasAtivasCadastradas(faixas) ? " Onde o laticínio cadastrou a tabela de bonificação (CCS, CBT, gordura, proteína), o selo segue a tabela dele." : " A tabela de bonificação do seu laticínio fica em Configurações › Parâmetros."}
            </Ajuda>
          </Passo>

          <Passo n={3} id="ql-p3" titulo="Observação (opcional)">
            <div style={{ maxWidth: "48rem" }} className="gv-campo">
              <input id="ql-obs" aria-label="Observação" type="text" value={observacao} placeholder="Ex.: laudo do laticínio, coleta após tratamento de mastite…" onChange={(e) => setObservacao(e.target.value)} />
            </div>
          </Passo>
        </>
      ) : (
        <Passo n={2} id="ql-p2" titulo="Planilha de coletas">
          <div className="gq-planilha">
            <div
              className="gp-solta" data-sobre={sobre}
              onDragOver={(e) => { e.preventDefault(); setSobre(true); }}
              onDragLeave={() => setSobre(false)}
              onDrop={(e) => { e.preventDefault(); setSobre(false); escolherArquivo(e.dataTransfer.files?.[0]); }}
            >
              <b>{arquivo ? arquivo.name : "Arraste a planilha para cá ou escolha o arquivo"}</b>
              <span>{arquivo ? "Pronta para importar." : "Aceita Excel (.xlsx) e CSV · cada linha vira uma coleta (tanque ou vaca)"}</span>
            </div>
            <div className="gq-planilha-botoes">
              <button type="button" className="btn-ghost" onClick={() => baixarModeloQualidadeLeite().catch(() => setErroPlanilha("Erro ao baixar o modelo."))}><Download size={14} aria-hidden="true" /> Baixar modelo</button>
              <button type="button" className="btn-ghost" onClick={() => entradaArquivo.current?.click()}><Upload size={14} aria-hidden="true" /> Escolher arquivo</button>
              <input ref={entradaArquivo} className="gp-sr" tabIndex={-1} aria-label="Arquivo da planilha de qualidade do leite" type="file" accept=".xlsx,.xlsm,.csv"
                onChange={(e) => { escolherArquivo(e.target.files?.[0]); e.target.value = ""; }} />
            </div>
          </div>
          <Aviso>Comece pelo modelo: ele traz as colunas certas. Depois da importação, a tela mostra quantas coletas entraram e quais linhas foram recusadas, com o motivo.</Aviso>
          {erroPlanilha && <Aviso tom="erro">{erroPlanilha}</Aviso>}
          {resultado && (
            <Aviso>
              <div>
                <strong>{resultado.criados} {plural(resultado.criados, "coleta importada", "coletas importadas")}</strong>
                {resultado.erros.length > 0 && <> — {resultado.erros.length} {plural(resultado.erros.length, "linha recusada", "linhas recusadas")}:</>}
                {resultado.erros.length > 0 && (
                  <ul className="gq-erros">
                    {resultado.erros.slice(0, 10).map((e, k) => <li key={k}>{e}</li>)}
                    {resultado.erros.length > 10 && <li>e mais {resultado.erros.length - 10}…</li>}
                  </ul>
                )}
              </div>
            </Aviso>
          )}
        </Passo>
      )}

      <BarraAcao
        resumo={resumo}
        detalhe={detalhe}
        retorno={alvo === "planilha" ? undefined : retornoNode}
        acao={alvo === "planilha"
          ? <BotaoOuro desabilitado={!arquivo || importando} onClick={importar}>{importando ? "Importando…" : "Importar planilha"}</BotaoOuro>
          : <BotaoOuro desabilitado={semSalvar} onClick={salvar}>{salvando ? "Salvando…" : "Salvar qualidade do leite"}</BotaoOuro>}
      />
    </div>
  );
}

function faixasAtivasCadastradas(faixas: FaixaBonificacao[]): boolean {
  return INDICES.some((i) => faixasAtivasDoIndice(faixas, i).length > 0);
}
