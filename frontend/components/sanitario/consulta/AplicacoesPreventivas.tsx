"use client";
// Sanidade › Preventiva › Aplicações: cada linha é um registro do histórico
// único (aplicação, resultado de exame, lançamento simples, planilha). Filtros
// por período, vacina e origem; selos janela/manual/curral; estorno (só
// administrador, com motivo); desfazer nos primeiros 10 s; exportar.
// Reaproveitada em Central › Concluídos › Sanitário › Preventivo com `grupo`
// (só as linhas de Vacina, de Exame ou dos Outros preventivos); sem `grupo`,
// é a tela de Sanidade, igual a sempre.
import { useMemo, useState } from "react";
import Link from "next/link";
import { Modal } from "@/components/Modal";
import { ErroCarregamento, TelaSkeleton } from "@/components/ui";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { useToast } from "@/components/Toast";
import { desfazerRegistros, estornarRegistro, listarCaixas, listarRegistros, mensagemDoErro } from "@/lib/apiSanitario";
import { ROTULO_ORIGEM, ROTULO_RESULTADO, fmtData, hojeISO, somarDias, textoDose, type Registro } from "@/lib/sanitarioTipos";
import { grupoDoTipo, linkCentral, tipoNoGrupo, type GrupoPreventivo } from "@/lib/protocolosNavegacao";
import { OrigemIcone, Seg, useCarregar, useEuSanitario } from "../comum";

type Origem = "todas" | "dia" | "lancamento_simples" | "ficha" | "importado" | "apos";
type Linha = Registro & { desfazivel: boolean };

async function carregar(f: { de: string; ate: string; caixa: string; estornados: boolean }): Promise<Linha[]> {
  const regs = await listarRegistros({ de: f.de || undefined, ate: f.ate || undefined, caixa_id: f.caixa ? Number(f.caixa) : null, incluir_estornados: f.estornados, limite: 1000 });
  const agora = Date.now();
  return regs.map((r) => ({ ...r, desfazivel: !!r.criado_em && agora - Date.parse(/Z$/.test(r.criado_em) ? r.criado_em : r.criado_em + "Z") < 10000 }));
}

export function AplicacoesPreventivas({ grupo = null }: { grupo?: GrupoPreventivo | null } = {}) {
  const toast = useToast();
  const { admin } = useEuSanitario();
  const hoje = hojeISO();
  const [de, setDe] = useState(somarDias(hoje, -90));
  const [ate, setAte] = useState(hoje);
  const [caixa, setCaixa] = useState("");
  const [origem, setOrigem] = useState<Origem>("todas");
  const [estornados, setEstornados] = useState(false);
  const { dados, erro, carregando, recarregar } = useCarregar(() => carregar({ de, ate, caixa, estornados }), [de, ate, caixa, estornados]);
  const caixas = useCarregar(() => listarCaixas("todas"), []);
  const [estorno, setEstorno] = useState<Registro | null>(null);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const linhas = useMemo(() => (dados || []).filter((r) => tipoNoGrupo(r.tipo, grupo)
    && (origem === "todas" ? true : origem === "apos" ? r.apos_fechamento : r.origem === origem)), [dados, origem, grupo]);
  const exp = useMemo(() => linhas.map((r) => ({
    data: fmtData(r.data), animal: r.numero || "", vacina: r.caixa || r.outro_texto || "", ciclo: r.ciclo_chave || "",
    produto: r.produto_texto || "", dose: textoDose(r), origem: ROTULO_ORIGEM[r.origem] || r.origem,
    aplicador: r.aplicador_texto || "", veterinario: r.veterinario_texto || "", resultado: r.resultado ? ROTULO_RESULTADO[r.resultado] : "",
    carencia_leite: fmtData(r.carencia_leite_ate), estado: r.estado,
  })), [linhas]);

  async function estornar() {
    if (!estorno) return;
    setOcupado(true);
    try { await estornarRegistro(estorno.id, motivo.trim()); toast("Estornado. O estoque foi devolvido."); setEstorno(null); setMotivo(""); recarregar(); }
    catch (e) { toast(mensagemDoErro(e), "erro"); } finally { setOcupado(false); }
  }
  async function desfazer(r: Registro) {
    try { await desfazerRegistros([r.id]); toast("Desfeito."); recarregar(); }
    catch (e) { toast(mensagemDoErro(e, "Passou o tempo de desfazer. Use o estorno."), "erro"); }
  }

  return (
    <div className="san-pagina">
      <div className="san-linha">
        <div className="san-campo medio"><label htmlFor="aDe">De</label><input id="aDe" className="san-input" type="date" value={de} onChange={(e) => setDe(e.target.value)} /></div>
        <div className="san-campo medio"><label htmlFor="aAte">Até</label><input id="aAte" className="san-input" type="date" value={ate} onChange={(e) => setAte(e.target.value)} /></div>
        <div className="san-campo" style={{ flex: "1 1 240px" }}><label htmlFor="aCx">Vacina ou exame</label>
          <select id="aCx" className="san-input" value={caixa} onChange={(e) => setCaixa(e.target.value)}>
            <option value="">Todos</option>{(caixas.dados || []).filter((c) => tipoNoGrupo(c.tipo, grupo)).map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </select></div>
        <label className="san-liga"><input type="checkbox" checked={estornados} onChange={(e) => setEstornados(e.target.checked)} /><span>Mostrar estornados</span></label>
      </div>
      <div className="san-acoes">
        <Seg<Origem> rotulo="Origem" valor={origem} onChange={setOrigem} opcoes={[
          { id: "todas", label: "Todas" }, { id: "dia", label: "Dia marcado" }, { id: "lancamento_simples", label: "Lançamento simples" },
          { id: "ficha", label: "Ficha" }, { id: "importado", label: "Planilha" }, { id: "apos", label: "Após o fechamento" },
        ]} />
        <span className="san-nota san-num" style={{ marginLeft: "auto" }}>{linhas.length} {linhas.length === 1 ? "registro" : "registros"}</span>
        <ExportarBotoes titulo="Sanidade preventiva — aplicações" nomeArquivoBase="sanitario_aplicacoes" linhas={exp} colunas={[
          { header: "Data", key: "data" }, { header: "Animal", key: "animal" }, { header: "Vacina/exame", key: "vacina" }, { header: "Ciclo", key: "ciclo" },
          { header: "Produto", key: "produto" }, { header: "Dose", key: "dose" }, { header: "Origem", key: "origem" }, { header: "Aplicador", key: "aplicador" },
          { header: "Veterinário", key: "veterinario" }, { header: "Resultado", key: "resultado" }, { header: "Carência leite até", key: "carencia_leite" }, { header: "Estado", key: "estado" },
        ]} />
      </div>
      {erro ? <ErroCarregamento mensagem={erro} onRetry={recarregar} /> : !dados ? <TelaSkeleton kpis={0} label="Carregando as aplicações" /> : (
        <section className="san-bloco" style={carregando ? { opacity: 0.6 } : undefined}>
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Data</th><th>Animal</th><th>Vacina ou exame</th><th>Produto · dose</th><th>Quem</th><th>Origem</th><th>Carência</th><th>Notas</th><th><span className="san-sr">Ações</span></th></tr></thead>
              <tbody>
                {linhas.length ? linhas.map((r) => (
                  <tr key={r.id} style={r.estado !== "valido" ? { opacity: 0.6 } : undefined}>
                    <td className="san-num" style={{ whiteSpace: "nowrap" }}>{fmtData(r.data)}{r.hora && <div className="san-nota">{r.hora}</div>}</td>
                    <td><b className="san-num">{r.numero || "—"}</b></td>
                    <td>{r.caixa || r.outro_texto || "—"}{r.ciclo_chave && !r.ciclo_chave.startsWith("X:") && <div className="san-nota">ciclo {r.ciclo_chave}{r.dose_num && r.dose_num > 1 ? ` · ${r.dose_num}ª dose` : ""}</div>}
                      {r.resultado && <div><b>{ROTULO_RESULTADO[r.resultado]}</b></div>}</td>
                    <td>{r.produto_texto || "—"}{textoDose(r) && <div className="san-nota san-num">{textoDose(r)}</div>}</td>
                    <td>{r.aplicador_texto || "—"}{r.veterinario_texto && r.veterinario_texto !== r.aplicador_texto && <div className="san-nota">vet. {r.veterinario_texto}{r.crmv_texto ? ` · ${r.crmv_texto}` : ""}</div>}</td>
                    <td>
                      <span className="san-acoes" style={{ gap: 6, flexWrap: "nowrap" }}>
                        {r.dia_item_id ? <OrigemIcone origem={r.decisao_curral ? "curral" : r.fora_da_regra ? "manual" : "janela"} /> : null}
                        <span className="san-nota">{ROTULO_ORIGEM[r.origem] || r.origem}</span>
                      </span>
                      {r.dia_id && <div><Link className="san-link" href={linkCentral.aplicarPreventivo({ dia: r.dia_id }, grupoDoTipo(r.tipo))}>abrir o dia</Link></div>}
                    </td>
                    <td className="san-nota">
                      {r.carencia_leite_ate && r.carencia_leite_ate >= hojeISO() ? <>leite até {fmtData(r.carencia_leite_ate, true)}<br /></> : null}
                      {r.carencia_carne_ate && r.carencia_carne_ate >= hojeISO() ? <>carne até {fmtData(r.carencia_carne_ate, true)}<br /></> : null}
                      {r.carencia_modo && (r.carencia_leite_ate || r.carencia_carne_ate) ? r.carencia_modo : ""}
                    </td>
                    <td className="san-nota">
                      {r.decisao_curral && <b>Decisão no curral. </b>}
                      {r.fora_da_regra && "Fora da regra, com consentimento. "}
                      {r.apos_fechamento && <b>Lançado após o fechamento. </b>}
                      {r.retroativo && `Retroativo${r.retroativo_motivo ? ": " + r.retroativo_motivo : ""}. `}
                      {r.so_registro && "Só registro. "}
                      {r.peso_estimado && "Peso estimado. "}
                      {r.estado !== "valido" && <b>Estornado{r.estornado_motivo ? `: ${r.estornado_motivo}` : ""}. </b>}
                    </td>
                    <td>
                      {r.estado === "valido" && r.desfazivel && <button type="button" className="san-link" onClick={() => desfazer(r)}>Desfazer</button>}
                      {r.estado === "valido" && admin && !r.desfazivel && <button type="button" className="san-link" onClick={() => { setMotivo(""); setEstorno(r); }}>Estornar</button>}
                    </td>
                  </tr>
                )) : <tr><td colSpan={9} className="san-nota" style={{ textAlign: "center", padding: "1.2rem" }}>Nenhum registro com esses filtros.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {estorno && (
        <Modal title={`Estornar · ${estorno.numero || ""} · ${estorno.caixa || estorno.outro_texto || ""}`} onClose={() => setEstorno(null)} width="520px">
          <div className="san-modal-corpo">
            <p className="san-modal-sub">Devolve o estoque, tira a carência e a próxima dose ainda não aplicada. O registro fica no histórico como estornado.</p>
            <div className="san-campo"><label htmlFor="aMot">Motivo</label><input id="aMot" className="san-input" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="ex.: lançado no animal errado" /></div>
          </div>
          <div className="san-modal-rodape">
            <button type="button" className="btn-ghost" onClick={() => setEstorno(null)}>Cancelar</button>
            <button type="button" className="btn-primary-gold" disabled={ocupado || !motivo.trim()} onClick={estornar}>{ocupado ? "Estornando…" : "Estornar"}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
