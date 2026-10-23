"use client";
// Sanidade › Preventiva › Animais na janela: cada vacina/exame mostra quem
// está dentro e por quê (motivos do motor). Selecionar animais → "Agendar na
// Central" (abre "Marcar Vacina ou Exame" com eles já escolhidos) ou
// "Dispensar neste ciclo" (motivo opcional).
import { Fragment, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { Modal } from "@/components/Modal";
import { ErroCarregamento, TelaSkeleton } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { animaisNaJanela, dispensarAnimais, listarCaixas, mensagemDoErro } from "@/lib/apiSanitario";
import { ROTULO_TIPO, fmtData, hojeISO, type JanelaItem } from "@/lib/sanitarioTipos";
import { Chip, ChipSituacao, Faixa, useCarregar } from "../comum";

const chaveSel = (caixaId: number, it: JanelaItem) => `${caixaId}|${it.animal_id}|${it.ciclo_chave ?? ""}|${it.dose_num ?? ""}`;

export function AnimaisNaJanela({ caixaInicial }: { caixaInicial?: number | null }) {
  const router = useRouter();
  const toast = useToast();
  const [filtro, setFiltro] = useState<string>(caixaInicial ? String(caixaInicial) : "");
  const { dados, erro, carregando, recarregar } = useCarregar(() => animaisNaJanela({ caixa_id: filtro ? Number(filtro) : null }), [filtro]);
  const caixas = useCarregar(() => listarCaixas("todas"), []);
  const [sel, setSel] = useState<Map<string, { caixa_id: number; it: JanelaItem }>>(new Map());
  const [abertos, setAbertos] = useState<Set<string>>(new Set());
  const [dispensar, setDispensar] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [acao, setAcao] = useState<"dispensar" | "descartar">("dispensar");
  const [ocupado, setOcupado] = useState(false);
  const inativas = (caixas.dados || []).filter((c) => c.estado === "inativa").length;
  const ativas = (caixas.dados || []).filter((c) => c.estado === "ativa");
  const grupos = useMemo(() => (dados || []).filter((g) => g.itens.length), [dados]);
  const selecionados = [...sel.values()];
  const nAnimais = new Set(selecionados.map((s) => s.it.animal_id)).size;
  const nCaixas = new Set(selecionados.map((s) => s.caixa_id)).size;

  function alternar(cid: number, it: JanelaItem) {
    const k = chaveSel(cid, it);
    setSel((p) => { const n = new Map(p); if (n.has(k)) n.delete(k); else n.set(k, { caixa_id: cid, it }); return n; });
  }
  function agendar() {
    const pares = selecionados.map((s) => `${s.caixa_id}-${s.it.animal_id}`).join(",");
    router.push(`/protocolos?aba=vacinas&sub=marcados&marcar=${pares}`);
  }
  async function confirmarDispensa() {
    setOcupado(true);
    try {
      const r = await dispensarAnimais(selecionados.map((s) => ({ caixa_id: s.caixa_id, animal_id: s.it.animal_id, ciclo_chave: s.it.ciclo_chave, dose_num: s.it.dose_num })),
        acao, motivo.trim() || null);
      toast(`${r.dispensados} ${r.dispensados === 1 ? "animal dispensado" : "animais dispensados"} neste ciclo.`);
      setDispensar(false); setSel(new Map()); setMotivo(""); recarregar();
    } catch (e) { toast(mensagemDoErro(e), "erro"); } finally { setOcupado(false); }
  }

  return (
    <div className="san-pagina">
      <div className="san-params">
        <span>Referência: <b>hoje, {fmtData(hojeISO(), true)}</b></span>
        <span>Mostra: <b>na janela, em aviso, atrasadas e marcadas</b></span>
        <span>Mínimo e antecedência: <b>de cada vacina</b> (ao lado do nome)</span>
        <span>Vacinas inativas fora da lista: <b>{inativas}</b></span>
        <Link href="/protocolos?aba=vacinas&sub=cadastro" className="san-link">Mudar na Central</Link>
      </div>
      <div className="san-linha">
        <div className="san-campo medio" style={{ flex: "0 1 320px" }}>
          <label htmlFor="fCaixa">Vacina ou exame</label>
          <select id="fCaixa" className="san-input" value={filtro} onChange={(e) => { setFiltro(e.target.value); setSel(new Map()); }}>
            <option value="">Todas as ativas</option>
            {ativas.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </select>
        </div>
      </div>
      {erro ? <ErroCarregamento mensagem={erro} onRetry={recarregar} /> : !dados ? <TelaSkeleton kpis={0} label="Carregando os animais na janela" /> : grupos.length ? grupos.map((g) => {
        const dentro = g.itens.filter((i) => i.estado !== "marcada");
        const aglomerou = g.minimo != null && dentro.length >= g.minimo;
        return (
          <section key={g.caixa_id} className="san-bloco" aria-labelledby={`g_${g.caixa_id}`} style={carregando ? { opacity: 0.6 } : undefined}>
            <div className="san-bloco-cab">
              <div className="san-acoes">
                <h3 id={`g_${g.caixa_id}`}>{g.caixa}</h3>
                <span className="san-tag">{ROTULO_TIPO[g.tipo] || g.tipo}</span>
                <span className="san-nota san-num">{dentro.length} na caixa · mínimo {g.minimo ?? "—"}</span>
                {aglomerou && <Chip tipo="aviso">aglomerou</Chip>}
              </div>
              {dentro.length > 0 && (
                <button type="button" className="san-link" onClick={() => setSel((p) => { const n = new Map(p); dentro.forEach((it) => n.set(chaveSel(g.caixa_id, it), { caixa_id: g.caixa_id, it })); return n; })}>Selecionar todos</button>
              )}
            </div>
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr><th><span className="san-sr">Selecionar</span></th><th>Brinco</th><th>Categoria</th><th>Situação</th><th>Janela</th><th>Por quê</th></tr></thead>
                <tbody>{g.itens.map((it) => {
                  const k = chaveSel(g.caixa_id, it);
                  const ab = abertos.has(k);
                  return (
                    <Fragment key={k}>
                      <tr>
                        <td>{it.estado === "marcada" ? null : <input type="checkbox" aria-label={`Selecionar ${it.numero} em ${g.caixa}`} checked={sel.has(k)} onChange={() => alternar(g.caixa_id, it)} />}</td>
                        <td><b className="san-num">{it.numero}</b></td>
                        <td>{it.categoria || "—"}<div className="san-nota">{it.lote || "sem lote"}{it.dose_num && it.dose_num > 1 ? ` · ${it.dose_num}ª dose` : ""}</div></td>
                        <td>{it.estado === "marcada" && it.dia_id
                          ? <Link className="san-link" href={`/protocolos?aba=vacinas&sub=marcados&dia=${it.dia_id}`}><ChipSituacao estado={it.estado} /></Link>
                          : <ChipSituacao estado={it.estado} texto={it.texto} />}</td>
                        <td className="san-nota san-num">{it.janela_inicio ? `${fmtData(it.janela_inicio, true)} a ${fmtData(it.janela_fim, true)}` : "—"}</td>
                        <td><button type="button" className="san-link" aria-expanded={ab} onClick={() => setAbertos((p) => { const n = new Set(p); if (n.has(k)) n.delete(k); else n.add(k); return n; })}>{ab ? "Esconder" : "Ver por quê"}</button></td>
                      </tr>
                      {ab && (
                        <tr><td /><td colSpan={5}>
                          <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.8rem" }}>
                            {(it.porque.length ? it.porque : [{ ok: true, texto: it.texto || "Na regra." }]).map((m, i) => (
                              <li key={i} style={{ color: m.ok ? undefined : "var(--alert-fg)" }}>{m.ok ? "" : "Não: "}{m.texto}</li>
                            ))}
                          </ul>
                        </td></tr>
                      )}
                    </Fragment>
                  );
                })}</tbody>
              </table>
            </div>
          </section>
        );
      }) : <Faixa tipo="ok">Nenhum animal nas vacinas ativas agora.{ativas.length ? "" : " Ative vacinas e exames na Central de Protocolos › Vacinas e exames › Cadastro."}</Faixa>}
      {selecionados.length > 0 && (
        <div className="san-barra-sel" role="region" aria-label="Seleção">
          <span className="cont">{nAnimais} {nAnimais > 1 ? "animais" : "animal"} em {nCaixas} {nCaixas > 1 ? "vacinas" : "vacina"}</span>
          <button type="button" className="btn-ghost" onClick={() => setSel(new Map())}>Limpar</button>
          <button type="button" className="btn-ghost" onClick={() => setDispensar(true)}>Dispensar neste ciclo</button>
          <button type="button" className="btn-primary" onClick={agendar}>Agendar na Central<ArrowRight size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginLeft: 4 }} /></button>
        </div>
      )}
      {dispensar && (
        <Modal title={`Dispensar ${nAnimais} ${nAnimais > 1 ? "animais" : "animal"} neste ciclo`} onClose={() => setDispensar(false)} width="540px">
          <div className="san-modal-corpo">
            <div className="san-opcs lista" role="radiogroup" aria-label="Como dispensar">
              <label className="san-opc"><input type="radio" name="dAc" checked={acao === "dispensar"} onChange={() => setAcao("dispensar")} />
                <span><b>Dispensar</b><small>Sai da caixa neste ciclo e fica registrado.</small></span></label>
              <label className="san-opc"><input type="radio" name="dAc" checked={acao === "descartar"} onChange={() => setAcao("descartar")} />
                <span><b>Descartar vacina</b><small>Some da lista; fica registrado como descartada.</small></span></label>
            </div>
            <div className="san-campo"><label htmlFor="dMot">Motivo (opcional)</label>
              <input id="dMot" className="san-input" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="ex.: animal vai ser vendido" /></div>
          </div>
          <div className="san-modal-rodape">
            <button type="button" className="btn-ghost" onClick={() => setDispensar(false)}>Cancelar</button>
            <button type="button" className="btn-primary-gold" disabled={ocupado} onClick={confirmarDispensa}>{ocupado ? "Gravando…" : "Dispensar"}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
