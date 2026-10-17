"use client";
// Tabela de SELEÇÃO de fêmeas (caixas, agrupada por lote, com aptidão em selo + motivo em texto) — a peça comum das telas
// reais de Lançamentos › Reprodutivo (Inseminação, Protocolo IATF, Indução de cio). Dados vêm prontos (LinhaFemea, ver
// lib/aptidaoServico.ts); aqui só se desenha e se avisa quem clicou em quê. Estilo: classes .gv-* (globals.css) e .rp-*
// (EstiloRepro, de ReprodutivoComum). Só tokens.
//   · apta       → selo "Apta", marcável;
//   · confirmar  → selo "Confirmar" + motivo; marcável (o servidor aceita forçar) e, marcada, diz "pede confirmação";
//   · bloqueada  → caixa DESABILITADA, selo "Bloqueada" + motivo em texto (o servidor recusa).
import React from "react";
import { Selo } from "@/components/gerencial/kit";
import { agrupaPorLote, ehApta, marcavel, todasAptasMarcadas, type LinhaFemea } from "@/lib/aptidaoServico";

// O motivo pode ser uma frase: quebra linha em vez de empurrar a tabela para o lado.
const CSS_FEMEAS = `.rp-motivo.tf-motivo { white-space: normal; display: inline-block; max-width: 15rem; vertical-align: middle; line-height: 1.35; }`;

export function TabelaFemeas({
  linhas, sel, onToggle, onToggleLote, onToggleAptas, mostrarProtocolo, colunaExtra, tituloAptidao = "Aptidão para servir",
  rotuloConfirmar = "Confirmar", altura = "36rem", vazio = "Nenhuma fêmea na lista.", carregando,
}: {
  linhas: readonly LinhaFemea[]; sel: ReadonlySet<string>;
  onToggle: (numero: string) => void;
  onToggleLote: (lote: string, itens: readonly LinhaFemea[]) => void;
  onToggleAptas: () => void;
  mostrarProtocolo?: boolean;
  /** Coluna a mais (ex.: "Última indução"). */
  colunaExtra?: { titulo: string; valor: (l: LinhaFemea) => React.ReactNode };
  tituloAptidao?: string;
  /** Texto do selo de quem pede confirmação (na Indução de cio, "Confira": é só informativo). */
  rotuloConfirmar?: string;
  altura?: string; vazio?: string; carregando?: boolean;
}) {
  const grupos = agrupaPorLote(linhas);
  const aptas = linhas.filter(ehApta);
  const colunas = 7 + (mostrarProtocolo ? 1 : 0) + (colunaExtra ? 1 : 0);
  return (
    <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: altura }}>
      <style>{CSS_FEMEAS}</style>
      <table className="gv-tabela">
        <thead>
          <tr>
            <th scope="col" style={{ width: "2.4rem" }}>
              <input type="checkbox" checked={todasAptasMarcadas(linhas, sel)} onChange={onToggleAptas} disabled={!aptas.length}
                aria-label="Marcar todas as aptas da lista" />
            </th>
            <th scope="col">Nº</th><th scope="col">Categoria</th>
            <th scope="col" title="Dias em lactação (vacas) ou idade em meses (novilhas)">DEL · idade</th>
            <th scope="col">Situação reprodutiva</th>
            <th scope="col" title="Última inseminação ou monta registrada">Última IA / monta</th>
            {mostrarProtocolo && <th scope="col" title="Protocolo IATF vigente em que a matriz está">Protocolo</th>}
            {colunaExtra && <th scope="col">{colunaExtra.titulo}</th>}
            <th scope="col">{tituloAptidao}</th>
          </tr>
        </thead>
        <tbody>
          {grupos.length === 0 && (
            <tr className="rp-tab-vazia"><td colSpan={colunas}>{carregando ? "Carregando as fêmeas…" : vazio}</td></tr>
          )}
          {grupos.map(({ lote, itens }) => {
            const aptasDoLote = itens.filter(ehApta);
            const loteMarcado = todasAptasMarcadas(itens, sel);
            const nBloq = itens.filter((l) => !marcavel(l)).length;
            return (
              <React.Fragment key={lote}>
                <tr className="gv-grupo">
                  <th scope="rowgroup" colSpan={colunas}>
                    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", cursor: aptasDoLote.length ? "pointer" : "default" }}>
                      <input type="checkbox" checked={loteMarcado} disabled={!aptasDoLote.length} onChange={() => onToggleLote(lote, itens)}
                        aria-label={`Marcar as aptas do lote ${lote}`} />
                      {lote} · {itens.length} {itens.length === 1 ? "fêmea" : "fêmeas"} · {aptasDoLote.length} {aptasDoLote.length === 1 ? "apta" : "aptas"}
                      {nBloq > 0 && ` · ${nBloq} ${nBloq === 1 ? "bloqueada" : "bloqueadas"}`}
                    </label>
                  </th>
                </tr>
                {itens.map((l) => {
                  const marcada = sel.has(l.numero);
                  const bloqueada = !marcavel(l);
                  const cls = marcada ? "gv-linha-marcada" : bloqueada ? "gv-linha-fora" : undefined;
                  return (
                    <tr key={l.numero} className={cls} title={l.aptidao.detalhe}>
                      <td>
                        <input type="checkbox" checked={marcada} disabled={bloqueada} onChange={() => onToggle(l.numero)}
                          aria-label={bloqueada ? `${l.numero} não pode ser marcada: ${l.aptidao.motivo ?? "bloqueada"}` : `Selecionar ${l.numero}`} />
                      </td>
                      <td className="gv-forte">
                        {l.numero}{l.preMarcada && <> <Selo tom="info" titulo="Já veio marcada (diagnóstico negativo ou Agenda)">Pré-marcada</Selo></>}
                      </td>
                      <td>{l.categoria}</td>
                      <td className="gv-num">{l.marco}</td>
                      <td>{l.situacao}</td>
                      <td className="gv-num">{l.ultima}</td>
                      {mostrarProtocolo && <td>{l.protocolo ? <Selo tom="info" titulo={l.protocoloTitulo}>{l.protocolo}</Selo> : "—"}</td>}
                      {colunaExtra && <td className="gv-num">{colunaExtra.valor(l)}</td>}
                      <td>
                        {l.aptidao.nivel === "apta" && <Selo tom="ok">Apta</Selo>}
                        {l.aptidao.nivel === "confirmar" && (
                          <>
                            <Selo tom="atencao">{rotuloConfirmar}</Selo>
                            <span className="rp-motivo tf-motivo">{l.aptidao.motivo}{marcada && rotuloConfirmar === "Confirmar" && <span className="rp-motivo-conf"> · pede confirmação</span>}</span>
                          </>
                        )}
                        {l.aptidao.nivel === "bloqueada" && (
                          <>
                            <Selo tom="bloqueio">Bloqueada</Selo>
                            <span className="rp-motivo tf-motivo">{l.aptidao.motivo}</span>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
