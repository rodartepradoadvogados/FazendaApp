"use client";
// Lançamentos › Produção › Qualidade do leite — PROPOSTA de tela (variante desktop, só apresentação, dados de exemplo).
// Fonte atual: components/FormQualidadeLeite.tsx (também roda no app de campo com a prop `salvarQualidade`).
//
// O QUE A VERSÃO LIGADA A DADOS PRECISA PRESERVAR
//  • Alvo: tanque (numero_matriz = null) | uma vaca (obrigatória) | planilha (UploadPlanilha: baixarModeloQualidadeLeite + importarQualidadeLeitePlanilha).
//  • POST /producao/qualidade-leite via `salvarQualidade` (prop de injeção offline); retorno `{ enviado: false }` = "Sem internet — guardado".
//    Corpo: numero_matriz, data_coleta, ccs, cbt, gordura_pct, proteina_pct, solidos_totais_pct, esd_pct, lactose_pct, nul, observacao.
//  • Data da coleta obrigatória (e vaca, se "Uma vaca"); os 8 índices são opcionais, vazio = null (nunca 0); vírgula decimal aceita
//    (`Number(v.replace(",", "."))`) — por isso os campos são type="text" inputMode="decimal", não type="number".
//  • Depois de salvar: limpa vaca, índices e observação; mantém alvo e data.
//  • "Último valor" por índice = GET /producao/qualidade-leite (já usado em app/producao/page.tsx), filtrando tanque ou a vaca escolhida.
//  • As FAIXAS desta tela são SUGESTÕES a confirmar com o dono (nenhuma norma é afirmada como fato). A versão real deve ler as faixas
//    de Configurações › Parâmetros (as mesmas da bonificação, `tem_faixas_bonificacao`) e cair nas sugestões só quando não houver faixa.
//    O selo só INFORMA: nunca bloqueia o Salvar.
//  • CSS: as classes `.gq-*` abaixo estão num <style> local só para a proposta; na implementação sobem para o fim de `.gv-*` em globals.css.
import React, { useMemo, useState } from "react";
import { Download, FlaskConical, Upload } from "lucide-react";
import { Aviso, Ajuda, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, QuadroGaveta } from "@/components/gerencial/kit";

type Chave = "ccs" | "cbt" | "gordura" | "proteina" | "st" | "esd" | "lactose" | "nul";
type Alvo = "tanque" | "vaca" | "planilha";
type Situacao = "ok" | "atencao" | "fora" | "invalido";

type Indice = {
  chave: Chave; sigla: string; nome: string; unidade: string; casas: number;
  ok: [number, number]; atencao: [number, number]; foraRotulo: string;
  refOk: string; refAtencao: string;
};

// Faixas SUGERIDAS (comuns no setor) — confirmar com o dono antes de ligar. `atencao` contém `ok`; fora disso = fora da faixa.
const INDICES: Indice[] = [
  { chave: "ccs", sigla: "CCS", nome: "Contagem de células somáticas", unidade: "mil céls./mL", casas: 0, ok: [0, 200], atencao: [0, 400], foraRotulo: "Alto", refOk: "≤ 200", refAtencao: "atenção de 200 a 400 · alto acima de 400" },
  { chave: "cbt", sigla: "CBT", nome: "Contagem bacteriana total", unidade: "mil UFC/mL", casas: 0, ok: [0, 100], atencao: [0, 300], foraRotulo: "Alto", refOk: "≤ 100", refAtencao: "atenção de 100 a 300 · alto acima de 300" },
  { chave: "gordura", sigla: "Gordura", nome: "Gordura do leite", unidade: "%", casas: 2, ok: [3.4, 4.4], atencao: [3.0, 5.0], foraRotulo: "Fora da faixa", refOk: "3,4 a 4,4", refAtencao: "atenção de 3,0 a 3,4 e de 4,4 a 5,0" },
  { chave: "proteina", sigla: "Proteína", nome: "Proteína do leite", unidade: "%", casas: 2, ok: [3.1, 3.6], atencao: [2.9, 3.8], foraRotulo: "Fora da faixa", refOk: "3,1 a 3,6", refAtencao: "atenção de 2,9 a 3,1 e de 3,6 a 3,8" },
  { chave: "st", sigla: "ST", nome: "Sólidos totais", unidade: "%", casas: 2, ok: [12.0, 13.5], atencao: [11.4, 14.5], foraRotulo: "Fora da faixa", refOk: "12,0 a 13,5", refAtencao: "atenção de 11,4 a 12,0 e de 13,5 a 14,5" },
  { chave: "esd", sigla: "ESD", nome: "Extrato seco desengordurado", unidade: "%", casas: 2, ok: [8.6, 9.2], atencao: [8.4, 9.6], foraRotulo: "Fora da faixa", refOk: "8,6 a 9,2", refAtencao: "atenção de 8,4 a 8,6 e de 9,2 a 9,6" },
  { chave: "lactose", sigla: "Lactose", nome: "Lactose", unidade: "%", casas: 2, ok: [4.4, 4.9], atencao: [4.2, 5.1], foraRotulo: "Fora da faixa", refOk: "4,4 a 4,9", refAtencao: "atenção de 4,2 a 4,4 e de 4,9 a 5,1" },
  { chave: "nul", sigla: "NUL", nome: "Nitrogênio ureico (ureia)", unidade: "mg/dL", casas: 1, ok: [10, 14], atencao: [8, 18], foraRotulo: "Fora da faixa", refOk: "10 a 14", refAtencao: "atenção de 8 a 10 e de 14 a 18" },
];

type Ultimo = { data: string; v: Partial<Record<Chave, number>> };
const ULTIMO_TANQUE: Ultimo = { data: "10/10/2026", v: { ccs: 182, cbt: 64, gordura: 3.74, proteina: 3.21, st: 12.3, esd: 8.62, lactose: 4.58, nul: 11.8 } };
const VACAS: { numero: string; lote: string; ultimo: Ultimo | null }[] = [
  { numero: "11153", lote: "02 - Vacas Alta", ultimo: { data: "26/09/2026", v: { ccs: 548, cbt: 40, gordura: 3.9, proteina: 3.3 } } },
  { numero: "3335", lote: "02 - Vacas Alta", ultimo: { data: "26/09/2026", v: { ccs: 164, cbt: 32, gordura: 3.6, proteina: 3.2 } } },
  { numero: "075", lote: "04 - Pós-parto/Tratamento", ultimo: null },
  { numero: "9378", lote: "02 - Vacas Alta", ultimo: { data: "12/09/2026", v: { ccs: 236, gordura: 4.1, proteina: 3.4 } } },
];

const ALVOS: { id: Alvo; nome: string; titulo: string; ajuda: string }[] = [
  { id: "tanque", nome: "Tanque (todas em lactação)", titulo: "Coleta única representando o rebanho em lactação (amostra do tanque)", ajuda: "Uma coleta única que representa todas as vacas em lactação (amostra do tanque)." },
  { id: "vaca", nome: "Uma vaca", titulo: "Coleta individual de uma vaca", ajuda: "Coleta individual de uma vaca — útil para investigar mastite." },
  { id: "planilha", nome: "Planilha", titulo: "Lançar várias coletas de uma vez, a partir de uma planilha (Excel ou CSV)", ajuda: "Várias coletas de uma vez, a partir de uma planilha (Excel ou CSV)." },
];

const dataBR = (iso: string) => (iso ? iso.split("-").reverse().join("/") : "—");
const nb = (v: number, casas: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
/** Vazio = null (nunca 0); aceita vírgula; texto que não é número = NaN (sinaliza). */
function ler(v: string): number | null {
  if (v.trim() === "") return null;
  return Number(v.replace(",", "."));
}
function classificar(i: Indice, v: number | null): Situacao | null {
  if (v === null) return null;
  if (!Number.isFinite(v)) return "invalido";
  if (v >= i.ok[0] && v <= i.ok[1]) return "ok";
  if (v >= i.atencao[0] && v <= i.atencao[1]) return "atencao";
  return "fora";
}
const ROTULO_SIT = (i: Indice, s: Situacao) => (s === "ok" ? "Na faixa" : s === "atencao" ? "Atenção" : s === "fora" ? i.foraRotulo : "Número inválido");

const CSS = `
.gq-tabela th[scope="row"] { text-align: left; font-weight: 400; padding: 0.42rem 0.6rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
.gq-tabela th[scope="row"] b { display: block; font-size: 0.85rem; font-weight: 800; }
.gq-tabela th[scope="row"] span { display: block; font-size: 0.72rem; color: var(--text-muted); }
.gq-valor { display: flex; align-items: center; gap: 0.5rem; }
.gq-valor .gv-celula-input { width: 6.2rem; min-height: 2rem; }
.gq-un { font-size: 0.72rem; color: var(--text-muted); }
.gq-ref b { font-weight: 800; font-variant-numeric: tabular-nums; }
.gq-ref span { display: block; font-size: 0.72rem; color: var(--text-muted); white-space: normal; }
.gq-delta { display: block; margin-top: 0.15rem; font-size: 0.72rem; color: var(--text-muted); font-variant-numeric: tabular-nums; }
.gv-selo.gq-selo[data-tom="ok"] { color: var(--ft-verde); border-color: var(--ft-verde); }
.gv-selo.gq-selo[data-tom="atencao"] { color: var(--ft-ambar); border-color: var(--ft-ambar); background: transparent; }
.gv-selo.gq-selo[data-tom="fora"] { color: var(--ft-verm); border-color: var(--ft-verm); }
.gv-selo.gq-selo[data-tom="invalido"] { color: var(--ft-verm); border-color: var(--ft-verm); }
.gq-linha-atencao > td, .gq-linha-atencao > th { background: color-mix(in srgb, var(--ft-ambar) 7%, transparent); }
.gq-linha-fora > td, .gq-linha-fora > th { background: color-mix(in srgb, var(--ft-verm) 6%, transparent); }
.gq-cabeca { display: flex; align-items: baseline; gap: 0.6rem; margin: 0 0 0.45rem; }
.gq-cabeca span:last-child { font-size: 0.76rem; color: var(--text-muted); text-transform: none; letter-spacing: 0; font-weight: 400; }
.gq-campos { display: grid; grid-template-columns: 14rem 24rem; gap: 0.75rem; align-items: start; }
.gq-planilha { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0.9rem; align-items: stretch; }
.gq-solta { display: flex; flex-direction: column; justify-content: center; gap: 0.15rem; padding: 0.9rem 1.1rem; border: 1.5px dashed var(--border-strong, var(--border)); border-radius: var(--r-sm); background: var(--surface-2); min-height: 4.2rem; }
.gq-solta b { font-size: 0.85rem; } .gq-solta span { font-size: 0.74rem; color: var(--text-muted); }
.gq-botao-i { display: inline-flex; align-items: center; gap: 0.45rem; min-height: 2.2rem; }
`;

export function QualidadeLeite({ alvoInicial = "tanque" }: { alvoInicial?: Alvo }) {
  const [alvo, setAlvo] = useState<Alvo>(alvoInicial);
  const [vaca, setVaca] = useState("");
  const [data, setData] = useState("2026-10-17");
  const [vals, setVals] = useState<Record<Chave, string>>({ ccs: "312", cbt: "78", gordura: "3,82", proteina: "3,28", st: "12,41", esd: "", lactose: "", nul: "" });
  const [obs, setObs] = useState("");
  const [retorno, setRetorno] = useState<string | null>(null);

  const ultimo: Ultimo | null = alvo === "vaca" ? VACAS.find((v) => v.numero === vaca)?.ultimo ?? null : ULTIMO_TANQUE;

  const linhas = useMemo(() => INDICES.map((i) => {
    const v = ler(vals[i.chave]);
    const u = ultimo?.v[i.chave] ?? null;
    return { i, v, sit: classificar(i, v), u, uSit: u === null ? null : classificar(i, u) };
  }), [vals, ultimo]);

  const preenchidos = linhas.filter((l) => l.v !== null).length;
  const emAtencao = linhas.filter((l) => l.sit === "atencao");
  const fora = linhas.filter((l) => l.sit === "fora");
  const invalidos = linhas.filter((l) => l.sit === "invalido");

  const faltaVaca = alvo === "vaca" && !vaca;
  const faltaData = !data;
  const semSalvar = faltaVaca || faltaData || invalidos.length > 0;
  const quem = alvo === "tanque" ? "Tanque" : vaca ? `Vaca ${vaca}` : "Uma vaca";

  const resumo = alvo === "planilha"
    ? "Planilha · nenhum arquivo escolhido"
    : [quem, dataBR(data), `${preenchidos === 0 ? "nenhum índice preenchido" : `${preenchidos} ${preenchidos === 1 ? "índice preenchido" : "índices preenchidos"}`}`,
       ...(emAtencao.length ? [`${emAtencao.length} em atenção`] : []), ...(fora.length ? [`${fora.length} fora da faixa`] : [])].join(" · ");

  const detalhe = alvo === "planilha"
    ? "Baixe o modelo, preencha e importe — cada linha vira uma coleta."
    : faltaVaca ? "Falta escolher a vaca."
    : faltaData ? "Falta a data da coleta."
    : invalidos.length ? `Corrija ${invalidos.map((l) => l.i.sigla).join(", ")}: use número, por exemplo 3,82.`
    : emAtencao.length + fora.length > 0
      ? `${[...emAtencao, ...fora].map((l) => `${l.i.sigla} ${nb(l.v as number, l.i.casas)}`).join(" · ")} — o selo só informa; salvar não é bloqueado.`
      : preenchidos === 0 ? "Sem índices o lançamento guarda só a data (todos são opcionais)." : "Todos os índices preenchidos estão na faixa sugerida.";

  function salvar() {
    setRetorno(`Qualidade do leite lançada — ${quem} · ${dataBR(data)} · ${preenchidos} ${preenchidos === 1 ? "índice" : "índices"}.`);
    setVaca(""); setObs("");
    setVals({ ccs: "", cbt: "", gordura: "", proteina: "", st: "", esd: "", lactose: "", nul: "" });
  }

  const ajudaAlvo = ALVOS.find((a) => a.id === alvo)?.ajuda;
  const t = ULTIMO_TANQUE.v;
  const itensFaixa = [
    { chave: "ccs" as const, v: t.ccs }, { chave: "cbt" as const, v: t.cbt },
    { chave: "gordura" as const, v: t.gordura }, { chave: "proteina" as const, v: t.proteina },
  ].map(({ chave, v }) => {
    const i = INDICES.find((x) => x.chave === chave) as Indice;
    const s = v === undefined ? null : classificar(i, v);
    return {
      rotulo: `${i.sigla} · ${i.unidade}`, valor: v === undefined ? "—" : nb(v, i.casas),
      tom: s === "ok" ? ("ok" as const) : s === "atencao" ? ("atencao" as const) : s === "fora" ? ("alerta" as const) : undefined,
    };
  });

  return (
    <>
      <style>{CSS}</style>
      <QuadroGaveta titulo="Qualidade do leite" icone={FlaskConical} largura={1320}>
        <div className="gq-cabeca gv-rotulo"><span>Último tanque · {ULTIMO_TANQUE.data}</span><span>há 7 dias</span></div>
        <Faixa itens={itensFaixa} />

        <Passo n={1} id="ql-p1" titulo="O que foi coletado">
          <Pilulas<Alvo> rotulo="Alvo da coleta" opcoes={ALVOS.map((a) => ({ id: a.id, nome: a.nome, titulo: a.titulo }))} valor={alvo} onChange={setAlvo} />
          <Ajuda>{ajudaAlvo}{alvo === "tanque" && " Tem várias coletas de uma vez? Use “Planilha”, ao lado."}</Ajuda>
          {alvo !== "planilha" && (
            <div className="gq-campos">
              <Campo rotulo="Data da coleta (obrigatória)" id="ql-data">
                <input type="date" value={data} onChange={(e) => setData(e.target.value)} />
              </Campo>
              {alvo === "vaca" && (
                <Campo rotulo="Vaca (obrigatória)" id="ql-vaca">
                  <select value={vaca} onChange={(e) => setVaca(e.target.value)}>
                    <option value="">Selecione a vaca…</option>
                    {VACAS.map((v) => <option key={v.numero} value={v.numero}>{v.numero} · {v.lote}</option>)}
                  </select>
                </Campo>
              )}
            </div>
          )}
        </Passo>

        {alvo !== "planilha" ? (
          <>
            <Passo n={2} id="ql-p2" titulo="Índices do laudo" direita={<span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Todos opcionais — preencha só os que o laudo trouxer · aceita vírgula (3,82)</span>}>
              <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "none" }}>
                <table className="gv-tabela gq-tabela">
                  <thead>
                    <tr>
                      <th scope="col">Índice</th><th scope="col">Valor do laudo</th><th scope="col">Situação</th>
                      <th scope="col" title="Faixas sugeridas — a confirmar com o dono">Faixa de referência (sugerida)</th>
                      <th scope="col">{alvo === "vaca" ? (vaca ? `Último da vaca ${vaca}${ultimo ? ` · ${ultimo.data}` : ""}` : "Último da vaca") : `Último tanque · ${ULTIMO_TANQUE.data}`}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {linhas.map(({ i, sit, v, u, uSit }) => {
                      const delta = v !== null && Number.isFinite(v) && u !== null ? v - u : null;
                      return (
                        <tr key={i.chave} className={sit === "atencao" ? "gq-linha-atencao" : sit === "fora" || sit === "invalido" ? "gq-linha-fora" : undefined}>
                          <th scope="row"><b>{i.sigla}</b><span>{i.nome}</span></th>
                          <td>
                            <div className="gq-valor">
                              <input className="gv-celula-input" type="text" inputMode="decimal" autoComplete="off" data-nav
                                aria-label={`${i.sigla} (${i.unidade})`} aria-invalid={sit === "invalido"} placeholder="—"
                                value={vals[i.chave]} onChange={(e) => setVals((p) => ({ ...p, [i.chave]: e.target.value }))} />
                              <span className="gq-un">{i.unidade}</span>
                            </div>
                          </td>
                          <td>
                            {sit ? <span className="gv-selo gq-selo" data-tom={sit}>{ROTULO_SIT(i, sit)}</span> : <span className="gq-un">sem valor</span>}
                            {delta !== null && delta !== 0 && <span className="gq-delta">{delta > 0 ? "▲" : "▼"} {nb(Math.abs(delta), i.casas)} {delta > 0 ? "acima" : "abaixo"} do último</span>}
                          </td>
                          <td className="gq-ref"><b>{i.refOk} {i.unidade}</b><span>{i.refAtencao}</span></td>
                          <td className="gv-num">
                            {u === null ? <span className="gq-un">—</span> : (
                              <>
                                <b>{nb(u, i.casas)}</b> <span className="gq-un">{i.unidade}</span>
                                {uSit && uSit !== "ok" && <> <span className="gv-selo gq-selo" data-tom={uSit}>{ROTULO_SIT(i, uSit)}</span></>}
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
                As faixas de bonificação do seu laticínio ficam em Configurações › Parâmetros.
              </Ajuda>
            </Passo>

            <Passo n={3} id="ql-p3" titulo="Observação (opcional)">
              <div style={{ maxWidth: "48rem" }} className="gv-campo">
                <input id="ql-obs" aria-label="Observação" type="text" value={obs} placeholder="Ex.: laudo do laticínio, coleta após tratamento de mastite…" onChange={(e) => setObs(e.target.value)} />
              </div>
            </Passo>
          </>
        ) : (
          <Passo n={2} id="ql-p2" titulo="Planilha de coletas">
            <div className="gq-planilha">
              <div className="gq-solta">
                <b>Arraste a planilha para cá ou escolha o arquivo</b>
                <span>Aceita Excel (.xlsx) e CSV · cada linha vira uma coleta (tanque ou vaca)</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", justifyContent: "center" }}>
                <button type="button" className="btn-ghost gq-botao-i"><Download size={14} aria-hidden="true" /> Baixar modelo</button>
                <button type="button" className="btn-ghost gq-botao-i"><Upload size={14} aria-hidden="true" /> Escolher arquivo</button>
              </div>
            </div>
            <Aviso>Comece pelo modelo: ele traz as colunas certas. Depois da importação, a tela mostra quantas coletas entraram e quais linhas foram recusadas, com o motivo.</Aviso>
          </Passo>
        )}

        <BarraAcao
          resumo={resumo}
          detalhe={detalhe}
          retorno={retorno ? <span role="status" style={{ color: "var(--ft-verde)", fontWeight: 700 }}>✓ {retorno}</span> : undefined}
          acao={alvo === "planilha"
            ? <BotaoOuro desabilitado>Importar planilha</BotaoOuro>
            : <BotaoOuro desabilitado={semSalvar} onClick={salvar}>Salvar qualidade do leite</BotaoOuro>}
        />
      </QuadroGaveta>
    </>
  );
}
