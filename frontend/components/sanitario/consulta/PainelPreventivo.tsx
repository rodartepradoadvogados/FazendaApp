"use client";
// Sanidade › Preventiva › Painel (próximos 30 dias). Só consulta: para marcar
// ou aplicar, a Central de Protocolos. Os parâmetros que mudam a tela aparecem
// na faixa de cima; as contagens são de animais distintos.
import { useState } from "react";
import Link from "next/link";
import { FileText, Milk } from "lucide-react";
import { Modal } from "@/components/Modal";
import { ErroCarregamento, TelaSkeleton } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { cumprirPrazo, leiteSeparado, mensagemDoErro, painel } from "@/lib/apiSanitario";
import { ROTULO_MODO_LEITE, diaSemana, diferencaDias, fmtData, hojeISO, somarDias, type Prazo } from "@/lib/sanitarioTipos";
import { grupoDoDia, linkCentral, urlCentral } from "@/lib/protocolosNavegacao";
import { Faixa, useCarregar, useEuSanitario } from "../comum";

const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export function ModalCumprir({ prazo, onFeito, onFechar }: { prazo: Prazo; onFeito: () => void; onFechar: () => void }) {
  const [doc, setDoc] = useState("");
  const [data, setData] = useState(hojeISO());
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  return (
    <Modal title={prazo.tipo === "atestado" ? "Atestado enviado" : "Comprovação feita"} onClose={onFechar} width="520px">
      <div className="san-modal-corpo">
        <p className="san-modal-sub">{prazo.caixa || "Vacina/exame"}{prazo.destinatario ? ` · para ${prazo.destinatario}` : ""} · vencia em {fmtData(prazo.vence_em)}.</p>
        <div className="san-linha">
          <div className="san-campo"><label htmlFor="pDoc">Número do documento (opcional)</label><input id="pDoc" className="san-input" value={doc} onChange={(e) => setDoc(e.target.value)} /></div>
          <div className="san-campo medio"><label htmlFor="pData">Feito em</label><input id="pData" className="san-input" type="date" value={data} max={hojeISO()} onChange={(e) => setData(e.target.value)} /></div>
        </div>
        {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={async () => {
          setSalvando(true); setErro(null);
          try { await cumprirPrazo(prazo.id, { documento_numero: doc.trim() || null, cumprido_em: data || null }); onFeito(); }
          catch (e) { setErro(mensagemDoErro(e)); } finally { setSalvando(false); }
        }}>{salvando ? "Gravando…" : "Registrar"}</button>
      </div>
    </Modal>
  );
}

export function PainelPreventivo() {
  const toast = useToast();
  const { admin } = useEuSanitario();
  const { dados: p, erro, recarregar } = useCarregar(() => painel(30), []);
  const leite = useCarregar(() => leiteSeparado(), []);
  const [cumprir, setCumprir] = useState<Prazo | null>(null);

  if (erro) return <ErroCarregamento mensagem={erro} onRetry={recarregar} />;
  if (!p) return <TelaSkeleton kpis={6} label="Carregando o painel preventivo" />;
  const hoje = p.parametros.hoje;
  const fim = somarDias(hoje, p.parametros.dias - 1);
  const ok = p.cobertura.reduce((s, c) => s + c.aplicados, 0);
  const tot = p.cobertura.reduce((s, c) => s + c.devidos, 0);
  const pct = tot ? Math.round((ok / tot) * 100) : null;
  const atrasadosAnimais = new Set(p.atrasadas.flatMap((a) => a.animal_ids)).size;
  const prazoPerto = p.prazos.some((x) => diferencaDias(hoje, x.vence_em) <= 10);

  return (
    <div className="san-pagina">
      <div className="san-params">
        <span>Período: <b>{fmtData(hoje, true)} a {fmtData(fim, true)}</b> ({p.parametros.dias} dias)</span>
        <span>Cobertura: <b>último ciclo de cada vacina obrigatória ativa</b></span>
        <span>Contagem: <b>animais distintos</b></span>
        <span>Antecedência padrão dos avisos: <b>{p.parametros.antecedencia_padrao_dias} dias</b></span>
        <span>Tuberculina: <b>{p.parametros.modo_tuberculina === "so_resultado" ? "só resultado" : p.parametros.modo_tuberculina}</b></span>
        <Link href="/parametros" className="san-link">Mudar parâmetros</Link>
      </div>
      <div className="san-kpis">
        <Link href="/sanidade?aba=preventiva&sub=janela" className={`san-kpi ${pct != null && pct < 80 ? "atencao" : ""}`}>
          <div className="l">Cobertura obrigatória</div><div className="v">{pct == null ? "—" : `${pct}%`}</div>
          <div className="d san-num">{tot ? `${ok} de ${tot} nas vacinas obrigatórias` : "nenhuma vacina obrigatória ativa"}</div>
        </Link>
        <Link href="/sanidade?aba=preventiva&sub=janela" className={`san-kpi ${p.atrasadas.length ? "alerta" : ""}`}>
          <div className="l">Atrasadas</div><div className="v">{atrasadosAnimais}</div><div className="d">animais distintos em {p.atrasadas.length} {p.atrasadas.length === 1 ? "vacina" : "vacinas"}</div>
        </Link>
        <div className={`san-kpi ${p.em_carencia.animais ? "atencao" : ""}`}>
          <div className="l">Em carência hoje</div><div className="v">{p.em_carencia.animais}</div><div className="d">leite {p.em_carencia.leite} · carne {p.em_carencia.carne}</div>
        </div>
        <div className="san-kpi">
          <div className="l">Custo · {p.parametros.dias} dias</div><div className="v" style={{ fontSize: "1.2rem" }}>{brl(p.custo_periodo)}</div><div className="d">registros com produto do estoque</div>
        </div>
        <Link href={urlCentral({ aba: "acompanhamento", area: "sanitario", san: "preventivo", grupo: null })} className="san-kpi">
          <div className="l">Dias marcados</div><div className="v">{p.resumo.dias}</div><div className="d">Vacina ou Exame até {fmtData(fim, true)}</div>
        </Link>
        <div className={`san-kpi ${prazoPerto ? "alerta" : ""}`}>
          <div className="l">Prazos legais</div><div className="v">{p.prazos.length}</div><div className="d">{p.prazos[0] ? `próximo vence ${fmtData(p.prazos[0].vence_em, true)}` : "nada vencendo"}</div>
        </div>
      </div>
      {admin && p.carencia_sem_aceite.length > 0 && (
        <Faixa tipo="atencao">{p.carencia_sem_aceite.length} {p.carencia_sem_aceite.length > 1 ? "vacinas estão" : "vacina está"} com carência sem aceite: o leite vai para o tanque e o registro marca “sem aceite”.{" "}
          <Link className="san-link" href={linkCentral.cadastroPreventivo({ caixa: p.carencia_sem_aceite[0], passo: 7 })}>Resolver no cadastro</Link></Faixa>
      )}
      <div className="san-grid2">
        <section className="san-bloco">
          <div className="san-bloco-cab"><h3>Cobertura por vacina obrigatória</h3></div>
          <div className="overflow-x-auto">
            <table className="fazenda-table"><thead><tr><th>Vacina</th><th style={{ textAlign: "right" }}>Cobertos</th><th>%</th></tr></thead>
              <tbody>{p.cobertura.length ? p.cobertura.map((c) => (
                <tr key={c.caixa_id}><td><b>{c.caixa}</b></td><td className="san-num" style={{ textAlign: "right" }}>{c.devidos ? `${c.aplicados} de ${c.devidos}` : "—"}</td>
                  <td style={{ minWidth: 130 }}>{c.pct != null ? (
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <div className={`san-barra ${c.pct < 50 ? "ruim" : c.pct < 90 ? "med" : ""}`}><i style={{ width: `${c.pct}%` }} /></div><b className="san-num">{c.pct}%</b>
                    </div>) : <span className="san-nota">sem ciclo iniciado</span>}</td></tr>
              )) : <tr><td colSpan={3} className="san-nota">Nenhuma vacina obrigatória ativa. Marque “obrigatório” no cadastro.</td></tr>}</tbody></table>
          </div>
        </section>
        <section className="san-bloco">
          <div className="san-bloco-cab"><h3>Prazos legais</h3></div>
          <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {p.prazos.length ? p.prazos.map((x) => {
              const dias = diferencaDias(hoje, x.vence_em);
              return (
                <Faixa key={x.id} tipo={dias <= 10 ? "alerta" : "atencao"} role="status">
                  <b>{x.tipo === "atestado" ? "Atestado" : "Comprovação"} · {x.caixa || "vacina"}</b>{x.destinatario ? ` para ${x.destinatario}` : ""}
                  <br /><span className="san-num">Vence {diaSemana(x.vence_em)} {fmtData(x.vence_em)} ({dias < 0 ? `vencido há ${-dias} dias` : `${dias} dias`})</span>
                  {x.registro_ids.length ? ` · ${x.registro_ids.length} ${x.registro_ids.length > 1 ? "aplicações" : "aplicação"}` : ""}
                  {admin && <div style={{ marginTop: 6 }}><button type="button" className="btn-ghost san-btn-sm" onClick={() => setCumprir(x)}>
                    <FileText size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />{x.tipo === "atestado" ? "Registrar envio" : "Registrar comprovação"}</button></div>}
                </Faixa>
              );
            }) : <p className="san-nota" style={{ margin: 0 }}>Nenhum prazo legal aberto.</p>}
          </div>
        </section>
        <section className="san-bloco">
          <div className="san-bloco-cab"><h3>Consumo × estoque · {p.parametros.dias} dias</h3></div>
          <div className="overflow-x-auto">
            <table className="fazenda-table"><thead><tr><th>Produto</th><th>Vacinas</th><th style={{ textAlign: "right" }}>Precisa</th><th style={{ textAlign: "right" }}>Saldo</th><th style={{ textAlign: "right" }}>Falta</th></tr></thead>
              <tbody>{p.consumo.length ? p.consumo.map((c) => (
                <tr key={c.estoque_id}><td>{c.produto || `#${c.estoque_id}`}{c.sem_peso ? <div className="san-nota">{c.sem_peso} sem peso (dose por kg)</div> : null}</td>
                  <td className="san-nota">{c.caixas.join(", ")}</td>
                  <td className="san-num" style={{ textAlign: "right" }}>{c.necessario} {c.unidade || ""}</td>
                  <td className="san-num" style={{ textAlign: "right" }}>{c.saldo ?? "—"}</td>
                  <td className="san-num" style={{ textAlign: "right", ...(c.falta ? { color: "var(--alert-fg)", fontWeight: 800 } : {}) }}>{c.falta || "—"}</td></tr>
              )) : <tr><td colSpan={5} className="san-nota">Nada previsto com produto do estoque.</td></tr>}</tbody></table>
          </div>
        </section>
        <section className="san-bloco">
          <div className="san-bloco-cab"><h3>Atrasadas e próximos 7 dias</h3></div>
          <div className="san-bloco-corpo" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
            <div><span className="san-rot">Atrasadas</span>
              {p.atrasadas.length ? <ul style={{ margin: "0.3rem 0 0", paddingLeft: "1.1rem", fontSize: "0.82rem" }}>
                {p.atrasadas.map((a) => <li key={a.caixa_id}><b>{a.caixa}</b> · {a.animais} {a.animais > 1 ? "animais" : "animal"} <Link className="san-link" href={`/sanidade?aba=preventiva&sub=janela&caixa=${a.caixa_id}`}>ver quais</Link></li>)}
              </ul> : <p className="san-nota" style={{ margin: 0 }}>Nenhuma.</p>}</div>
            <div><span className="san-rot">Próximos 7 dias</span>
              {p.proximos_7_dias.length ? <ul style={{ margin: "0.3rem 0 0", paddingLeft: "1.1rem", fontSize: "0.82rem" }}>
                {p.proximos_7_dias.map((d) => <li key={d.id}><Link className="san-link" href={linkCentral.aplicarPreventivo({ dia: d.id }, grupoDoDia(d))}>{d.nome}</Link>{d.hora ? ` · ${d.hora}` : ""} · {d.contagens.animais} animais</li>)}
              </ul> : <p className="san-nota" style={{ margin: 0 }}>Nenhum dia marcado.</p>}</div>
          </div>
        </section>
      </div>
      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Leite separado hoje</h3><span className="san-nota">curativos e preventivos juntos · vacas ainda em carência de leite</span></div>
        {leite.erro ? <div className="san-bloco-corpo"><ErroCarregamento mensagem={leite.erro} onRetry={leite.recarregar} /></div>
          : !leite.dados ? <div className="san-bloco-corpo"><div className="skeleton" style={{ height: "4rem" }} /></div>
            : leite.dados.itens.length ? (
              <div className="overflow-x-auto">
                <table className="fazenda-table"><thead><tr><th>Vaca</th><th>Origem</th><th>Produto / vacina</th><th>Aplicação</th><th>Libera o leite</th><th>Leite</th></tr></thead>
                  <tbody>{leite.dados.itens.map((i, k) => (
                    <tr key={`${i.origem}-${i.registro_id ?? i.sanidade_id ?? k}`}><td><b className="san-num">{i.numero}</b></td><td>{i.origem === "preventivo" ? "Preventivo" : "Curativo"}</td>
                      <td>{i.produto || i.caixa || "—"}</td><td className="san-num">{fmtData(i.data_aplicacao, true)}</td><td className="san-num"><b>{fmtData(i.liberacao_leite, true)}</b></td>
                      <td>{ROTULO_MODO_LEITE[i.modo as keyof typeof ROTULO_MODO_LEITE] || i.modo}</td></tr>
                  ))}</tbody></table>
              </div>
            ) : <div className="san-bloco-corpo"><p className="san-nota" style={{ margin: 0 }}><Milk size={14} aria-hidden="true" style={{ verticalAlign: "-2px" }} /> Nenhuma vaca com leite separado hoje.</p></div>}
      </section>
      {cumprir && <ModalCumprir prazo={cumprir} onFechar={() => setCumprir(null)} onFeito={() => { setCumprir(null); toast("Prazo registrado como cumprido."); recarregar(); }} />}
    </div>
  );
}
