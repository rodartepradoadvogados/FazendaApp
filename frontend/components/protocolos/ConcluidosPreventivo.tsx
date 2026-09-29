"use client";
// Protocolos › Concluídos (sanitário preventivo): histórico do que foi aplicado.
// Fatia 8; mockup fluxo-completo (proto-concl.js). Nada se apaga: erro vira
// "Estornada" (só o administrador, com motivo) e a original fica preservada.
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Ban, Flag, History, Printer, Search, Undo2 } from "lucide-react";
import {
  ehAdmin, estornarAplicacaoPreventiva, fetchConcluidosPreventivo, fetchDetalheAplicacao,
  type ConcluidosPreventivo as Dados, type DetalheAplicacao, type ItemConcluido,
} from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { GavetaLancamento } from "@/components/lancamentos/GavetaLancamento";
import { Indicador, TelaSkeleton } from "@/components/ui";
import type { ColunaExport } from "@/lib/export";
import { ResumoCustoFinanceiro } from "./FinanceiroAgendamento";
import { BannerReagentes, ComprovanteAplicacaoView, dataHoraLocal, horasTxt, RESULTADOS_ROTULO } from "./exameComum";
import {
  brl, Chips, dataCurta, dataHoraCurta, ForaJanelaBadge, inputStyle, MOTIVOS_ESTORNO, notaStyle, num, Pill, plural, textoMotivo,
} from "./preventivoComum";

const COLUNAS: ColunaExport[] = [
  { header: "Data", key: "data" }, { header: "Hora", key: "hora" }, { header: "Protocolo", key: "protocolo" },
  { header: "Estado", key: "estado" }, { header: "Animais aplicados", key: "aplicados" }, { header: "Não aplicados", key: "naoAplicados" },
  { header: "Fora da janela", key: "fora" }, { header: "Aplicador", key: "aplicador" }, { header: "Frasco/lote", key: "frasco" },
  { header: "Validade", key: "validade" }, { header: "Carência carne até", key: "carne" }, { header: "Carência leite até", key: "leite" },
  { header: "Custo (R$)", key: "custo" }, { header: "Conta a pagar (R$)", key: "conta" }, { header: "Pagamento vinculado (R$)", key: "pagamento" }, { header: "Canal", key: "canal" }, { header: "Retroativo", key: "retro" },
  { header: "Exceções e ciências", key: "excecoes" }, { header: "Motivo do estorno", key: "motivoEstorno" },
  // Exame (fatia 9b): campos gravados no registro concluído
  { header: "Tipo de teste", key: "tipoTeste" }, { header: "Nº do laudo", key: "laudo" }, { header: "Inoculação", key: "inoculacao" },
  { header: "Leitura", key: "leitura" }, { header: "Horas até a leitura", key: "horas" }, { header: "Leitura fora de 72–96 h", key: "foraJanela" },
  { header: "Negativos", key: "negativos" }, { header: "Reagentes", key: "reagentes" }, { header: "Inconclusivos", key: "inconclusivos" },
  { header: "Notificação dos reagentes", key: "notificacao" }, { header: "Reteste em", key: "reteste" },
];

function EstadoPill({ i }: { i: ItemConcluido }) {
  if (i.estado === "estornada") return <Pill cor="var(--red)" title={i.motivo_estorno || undefined}><Undo2 size={12} />Estornada</Pill>;
  if (i.estado === "cancelado") return <Pill cor="var(--text-muted)"><Ban size={12} />Cancelado</Pill>;
  // Exame nunca mostra "Aplicado": é "Exame realizado".
  return <Pill cor="var(--green-light)">{i.rotulo_estado || (i.tipo === "exame" ? "Exame realizado" : "Aplicado")}</Pill>;
}

/** Todos os animais lidos são reagentes: o comprovante fica bloqueado (negativos emitem normalmente). */
const todosReagentes = (i: ItemConcluido) => !!i.exame && i.animais_aplicados > 0 && i.exame.reagentes >= i.animais_aplicados;

export function ConcluidosPreventivo({ idInicial }: { idInicial?: number | null }) {
  const admin = ehAdmin();
  const [comprovanteId, setComprovanteId] = useState<number | null>(null);
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [recarga, setRecarga] = useState(0);
  const [protocolo, setProtocolo] = useState("");
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [q, setQ] = useState("");
  const [fora, setFora] = useState(false);
  const [aberto, setAberto] = useState<number | null>(idInicial ?? null);
  const [estornando, setEstornando] = useState<ItemConcluido | null>(null);
  const recarregar = useCallback(() => setRecarga((n) => n + 1), []);

  useEffect(() => {
    let vivo = true;
    const t = setTimeout(() => {
      fetchConcluidosPreventivo({ calendarioId: protocolo ? Number(protocolo) : undefined, de: de || undefined, ate: ate || undefined, foraJanela: fora, q: q.trim() || undefined })
        .then((d) => { if (vivo) { setDados(d); setErro(null); } })
        .catch((e) => { if (vivo) setErro(e.message || "Erro ao carregar os concluídos"); });
    }, q ? 250 : 0);
    return () => { vivo = false; clearTimeout(t); };
  }, [protocolo, de, ate, q, fora, recarga]);

  const protocolos = useMemo(() => {
    const m = new Map<number, string>();
    (dados?.itens || []).forEach((i) => m.set(i.calendario_sanitario_id, i.protocolo_nome));
    return Array.from(m.entries());
  }, [dados]);

  const linhasExport = useMemo(() => (dados?.itens || []).filter((i) => i.estado !== "cancelado").map((i) => ({
    data: dataCurta(i.data), hora: i.hora || "", protocolo: i.protocolo_nome, estado: i.estado === "estornada" ? "Estornada" : (i.rotulo_estado || "Aplicado"),
    aplicados: i.animais_aplicados, naoAplicados: i.animais_nao_aplicados, fora: i.fora_janela, aplicador: i.aplicador_nome || "",
    frasco: i.frasco, validade: dataCurta(i.validade), carne: dataCurta(i.carencia_carne_ate), leite: dataCurta(i.carencia_leite_ate),
    custo: i.custo == null ? "a informar" : i.custo.toFixed(2).replace(".", ","),
    conta: i.financeiro && i.financeiro.contas_ativas > 0 ? i.financeiro.conta_a_pagar_total.toFixed(2).replace(".", ",") : "",
    pagamento: i.financeiro && i.financeiro.pagamento_vinculado_total > 0 ? i.financeiro.pagamento_vinculado_total.toFixed(2).replace(".", ",") : "",
    canal: i.canal || "", retro: i.retroativo ? "Sim" : "Não",
    excecoes: i.excecoes.join(" | "), motivoEstorno: i.motivo_estorno || "",
    tipoTeste: i.exame?.tipo_teste || "", laudo: i.exame?.laudo || "",
    inoculacao: i.exame?.inoculacao_data ? `${dataCurta(i.exame.inoculacao_data)} ${i.exame.inoculacao_hora || ""}`.trim() : "",
    leitura: i.exame ? `${dataCurta(i.exame.leitura_data)} ${i.exame.leitura_hora || ""}`.trim() : "",
    horas: i.exame?.leitura_horas != null ? String(Math.round(i.exame.leitura_horas)) : "",
    foraJanela: i.exame ? (i.exame.leitura_fora_janela ? "Sim" : "Não") : "",
    negativos: i.exame ? i.exame.negativos : "", reagentes: i.exame ? i.exame.reagentes : "", inconclusivos: i.exame ? i.exame.inconclusivos : "",
    notificacao: i.exame && i.exame.reagentes ? (i.exame.reagentes_pendentes_notificacao ? `${i.exame.reagentes_pendentes_notificacao} pendente(s)` : "Registrada") : "",
    reteste: i.exame?.reteste_em ? dataCurta(i.exame.reteste_em) : "",
  })), [dados]);

  if (erro) return <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>{erro}</span></div>;
  if (!dados) return <TelaSkeleton kpis={3} />;

  return (
    <div className="le-raiz">
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.8rem", flexWrap: "wrap", alignItems: "flex-start", marginBottom: "0.9rem" }}>
        <div>
          <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>Concluídos do preventivo</h2>
          <p style={notaStyle}>Histórico do que já foi aplicado. Nada se apaga: erro vira “Estornada” e a original fica.</p>
        </div>
        <ExportarBotoes titulo="Protocolos — Concluídos do preventivo" nomeArquivoBase="concluidos_preventivo" colunas={COLUNAS} linhas={linhasExport} />
      </div>

      <BannerReagentes recarga={recarga} onMudou={recarregar} />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
        <Indicador categoria="sanidade" valor={dados.resumo.aplicados} rotulo="Aplicações registradas" />
        <Indicador categoria="sanidade" valor={dados.resumo.animais} rotulo="Animais atendidos" />
        <Indicador categoria="sanidade" valor={dados.resumo.estornados} rotulo="Estornadas" cor={dados.resumo.estornados ? "var(--red)" : undefined} />
      </div>

      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginBottom: "0.8rem", alignItems: "center" }}>
        <div style={{ flex: "0 1 230px" }}>
          <label className="sr-only" htmlFor="cc-p">Protocolo</label>
          <select id="cc-p" style={inputStyle} value={protocolo} onChange={(e) => setProtocolo(e.target.value)}>
            <option value="">Todos os protocolos</option>
            {protocolos.map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
          </select>
        </div>
        <input type="date" aria-label="Data inicial" style={{ ...inputStyle, width: 160 }} value={de} onChange={(e) => setDe(e.target.value)} />
        <input type="date" aria-label="Data final" style={{ ...inputStyle, width: 160 }} value={ate} onChange={(e) => setAte(e.target.value)} />
        <div style={{ position: "relative", flex: "1 1 200px" }}>
          <Search size={14} style={{ position: "absolute", left: 8, top: 11, color: "var(--text-muted)" }} />
          <input type="search" aria-label="Buscar animal ou frasco" style={{ ...inputStyle, paddingLeft: 28 }} placeholder="Brinco ou frasco…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: "0.82rem", cursor: "pointer" }}>
          <input type="checkbox" checked={fora} onChange={(e) => setFora(e.target.checked)} /> Fora da janela apenas
        </label>
      </div>

      {!dados.itens.length ? (
        <div className="card" style={{ textAlign: "center", padding: "2rem 1rem" }}>
          <History size={28} style={{ color: "var(--text-muted)", margin: "0 auto 0.6rem" }} />
          <p style={{ fontWeight: 700 }}>Nada concluído neste período</p>
          <p style={{ ...notaStyle, marginTop: "0.3rem" }}>Ajuste os filtros ou aplique um agendamento em Acompanhamento.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <p style={{ ...notaStyle, marginBottom: "0.4rem" }}>{dados.total} {plural(dados.total, "registro", "registros")}</p>
          <table className="fazenda-table" aria-label="Concluídos do preventivo">
            <thead><tr><th>Data</th><th>Protocolo</th><th>Para quem</th><th>Responsável</th><th>Frasco/lote</th><th>Carência</th><th>Custo</th><th><span className="sr-only">Ações</span></th></tr></thead>
            <tbody>
              {dados.itens.map((i) => (
                <tr key={`${i.id ?? "x"}-${i.cronograma_id}`} tabIndex={0} style={{ cursor: i.id ? "pointer" : undefined, opacity: i.estado === "estornada" ? 0.72 : 1 }}
                    onClick={() => i.id && setAberto(i.id)} onKeyDown={(e) => { if (e.key === "Enter" && i.id) setAberto(i.id); }}
                    aria-label={`Abrir ${i.protocolo_nome} de ${dataCurta(i.data)}`}>
                  <td style={{ fontSize: "0.82rem" }}>{dataCurta(i.data)}<span style={{ ...notaStyle, display: "block" }}>{i.hora || ""}</span></td>
                  <td>
                    <b style={{ fontSize: "0.85rem" }}>{i.protocolo_nome}</b>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                      <EstadoPill i={i} />
                      {i.retroativo && <Pill cor="var(--dourado-light)">Retroativo</Pill>}
                      {i.canal && <Pill cor="var(--text-muted)">{i.canal}</Pill>}
                      {i.com_excecao && <Pill cor="var(--amber)" title={i.excecoes.join("; ")}><AlertTriangle size={12} />Com exceção</Pill>}
                      {i.exame && i.estado === "aplicada" && i.exame.reagentes > 0 && (
                        <Pill cor={i.exame.reagentes_pendentes_notificacao ? "var(--red)" : "var(--amber)"}><AlertTriangle size={12} />{i.exame.reagentes} {plural(i.exame.reagentes, "reagente", "reagentes")}{i.exame.reagentes_pendentes_notificacao ? " · notificar" : " · notificado"}</Pill>
                      )}
                      {i.exame && i.estado === "aplicada" && i.exame.leitura_fora_janela && <Pill cor="var(--amber)" title="Leitura fora da janela de 72–96 h"><AlertTriangle size={12} />Fora de 72–96 h</Pill>}
                      {i.estado === "cancelado" && i.motivo && <span style={notaStyle}>{i.motivo}</span>}
                    </div>
                  </td>
                  <td style={{ fontSize: "0.82rem" }}>
                    {i.estado === "cancelado" ? `${i.animais_nao_aplicados} ${plural(i.animais_nao_aplicados, "animal", "animais")}` : `${i.animais_aplicados + i.animais_nao_aplicados} ${plural(i.animais_aplicados + i.animais_nao_aplicados, "animal", "animais")}`}
                    {i.estado !== "cancelado" && !i.exame && <span style={{ ...notaStyle, display: "block" }}>{i.animais_aplicados} aplicados · {i.animais_nao_aplicados} não aplicados</span>}
                    {i.exame && i.estado !== "cancelado" && (
                      <span style={{ ...notaStyle, display: "block" }}>
                        {i.exame.fase === "coleta" && i.exame.coletados > 0 ? `${i.exame.coletados} coletados` : `${i.exame.negativos} neg · ${i.exame.reagentes} reag · ${i.exame.inconclusivos} inconcl.`}
                      </span>
                    )}
                    {i.fora_janela > 0 && <div><ForaJanelaBadge n={i.fora_janela} /></div>}
                  </td>
                  <td style={{ fontSize: "0.82rem" }}>{i.aplicador_nome || "—"}{i.aplicador_crmv && <span style={{ ...notaStyle, display: "block" }}>{i.aplicador_crmv}</span>}</td>
                  <td style={{ fontSize: "0.82rem" }}>{i.frasco}{i.validade && <span style={{ ...notaStyle, display: "block" }}>val. {dataCurta(i.validade)}</span>}</td>
                  <td style={{ fontSize: "0.78rem" }}>
                    {i.estado === "estornada" ? "sem carência (estornada)" : [i.carencia_carne_ate ? `carne até ${dataCurta(i.carencia_carne_ate).slice(0, 5)}` : "", i.carencia_leite_ate ? `leite até ${dataCurta(i.carencia_leite_ate).slice(0, 5)}` : ""].filter(Boolean).join(" · ") || "—"}
                  </td>
                  <td style={{ fontSize: "0.82rem", textAlign: "right" }}>
                    {i.estado === "cancelado" ? "—" : i.custo == null ? <span style={{ color: "var(--amber)", fontWeight: 700 }}>a informar</span> : brl(i.custo)}
                    {i.financeiro && i.financeiro.contas_ativas > 0 && (
                      <a href={i.financeiro.link_contas_a_pagar} onClick={(e) => e.stopPropagation()} className="lnk" title="Abrir Contas a pagar"
                         style={{ ...notaStyle, display: "block", textDecoration: "underline", color: "var(--dourado-light)", whiteSpace: "nowrap" }}>conta a pagar {brl(i.financeiro.conta_a_pagar_total)}</a>
                    )}
                    {i.financeiro && i.financeiro.pagamento_vinculado_total > 0 && <span style={{ ...notaStyle, display: "block", whiteSpace: "nowrap" }}>pagamento vinculado {brl(i.financeiro.pagamento_vinculado_total)}</span>}
                    {i.financeiro && i.financeiro.contas.some((c) => c.estado === "cancelado") && i.financeiro.contas_ativas === 0 && <span style={{ ...notaStyle, display: "block" }}>conta cancelada</span>}
                  </td>
                  <td onClick={(e) => e.stopPropagation()} style={{ whiteSpace: "nowrap" }}>
                    {i.estado === "aplicada" && i.id != null && (
                      <button type="button" className="btn-ghost" onClick={() => setComprovanteId(i.id)} disabled={todosReagentes(i)}
                              title={todosReagentes(i) ? "Bloqueado: todos os animais são reagentes." : "Comprovante para imprimir"}>
                        <Printer size={14} /> Comprovante
                      </button>
                    )}
                    {i.estado === "aplicada" && (
                      <button type="button" className="btn-ghost" disabled={!admin} onClick={() => setEstornando(i)}
                              title={admin ? "Estornar: a original fica preservada" : "Só o perfil Administrador estorna"}>
                        <Undo2 size={14} /> Estornar{admin ? "" : " (administrador)"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {comprovanteId != null && <ComprovanteAplicacaoView aplicacaoId={comprovanteId} onFechar={() => setComprovanteId(null)} />}
      {aberto != null && <GavetaDetalhe id={aberto} admin={admin} onFechar={() => setAberto(null)} onEstornar={(i) => { setAberto(null); setEstornando(i); }} lista={dados.itens} />}
      {estornando && <GavetaEstornar item={estornando} onFechar={() => setEstornando(null)} onFeito={() => { setEstornando(null); recarregar(); }} />}
    </div>
  );
}

// ─────────────────────────── detalhe (imutável) ───────────────────────────
function GavetaDetalhe({ id, admin, lista, onFechar, onEstornar }: { id: number; admin: boolean; lista: ItemConcluido[]; onFechar: () => void; onEstornar: (i: ItemConcluido) => void }) {
  const [d, setD] = useState<DetalheAplicacao | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<"animais" | "checklist" | "historico">("animais");
  const [comprovante, setComprovante] = useState(false);
  useEffect(() => { fetchDetalheAplicacao(id).then(setD).catch((e) => setErro(e.message)); }, [id]);
  const item = lista.find((i) => i.id === id);
  return (
    <GavetaLancamento aberto onFechar={onFechar} titulo="Detalhe do concluído" icone={History}>
      {erro && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erro}</span></div>}
      {!d && !erro && <TelaSkeleton kpis={0} />}
      {d && (
        <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
          <div>
            <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>{d.protocolo_nome}</h2>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "0.3rem 0" }}>
              {d.estado === "estornada" ? <Pill cor="var(--red)"><Undo2 size={12} />Estornada</Pill> : <Pill cor="var(--green-light)">{d.rotulo_estado || (d.exame ? "Exame realizado" : "Aplicado")}</Pill>}
              <Pill cor="var(--text-muted)">{d.canal}</Pill>
              {d.retroativo && <Pill cor="var(--dourado-light)">Retroativo</Pill>}
              <span style={notaStyle}>Registro imutável · {dataCurta(d.data_aplicacao)} {d.hora || ""}</span>
            </div>
          </div>
          <ul style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.6rem", listStyle: "none", margin: 0, padding: 0 }}>
            <li className="card" style={{ padding: "0.5rem 0.7rem" }}><span style={notaStyle}>Aplicador</span><b style={{ display: "block", fontSize: "0.9rem" }}>{d.aplicador_nome || "—"}{d.aplicador_crmv ? ` (${d.aplicador_crmv})` : ""}</b></li>
            <li className="card" style={{ padding: "0.5rem 0.7rem" }}><span style={notaStyle}>Frasco / lote</span><b style={{ display: "block", fontSize: "0.9rem" }}>{d.lote_texto || (d.estoque_desconsiderado ? "sem baixa" : "—")}{d.validade ? ` · val. ${dataCurta(d.validade)}` : ""}</b></li>
            <li className="card" style={{ padding: "0.5rem 0.7rem" }}><span style={notaStyle}>Custo</span><b style={{ display: "block", color: d.custo == null ? "var(--amber)" : undefined }}>{brl(d.custo)}</b></li>
          </ul>
          {d.exame && (
            <div className="card" data-testid="bloco-exame" style={{ padding: "0.6rem 0.9rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <h3 className="card-header" style={{ marginBottom: 0 }}>Exame</h3>
              <ul style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.6rem", listStyle: "none", margin: 0, padding: 0 }}>
                {d.exame.fase === "leitura" && <li><span style={notaStyle}>Inoculação</span><b style={{ display: "block", fontSize: "0.9rem" }}>{dataCurta(d.exame.inoculacao_data)} {d.exame.inoculacao_hora || ""}</b></li>}
                <li><span style={notaStyle}>{d.exame.fase === "leitura" ? "Leitura" : "Coleta"}</span><b style={{ display: "block", fontSize: "0.9rem" }}>{dataCurta(d.exame.leitura_data)} {d.exame.leitura_hora || ""}{d.exame.leitura_horas != null ? ` · ${horasTxt(d.exame.leitura_horas)} depois` : ""}</b></li>
                {d.exame.tipo_teste && <li><span style={notaStyle}>Tipo de teste</span><b style={{ display: "block", fontSize: "0.9rem" }}>{d.exame.tipo_teste}</b></li>}
                <li><span style={notaStyle}>Nº do laudo</span><b style={{ display: "block", fontSize: "0.9rem" }}>{d.exame.laudo || "não informado"}</b></li>
                {d.exame.fase === "leitura" && <li><span style={notaStyle}>Resultado</span><b style={{ display: "block", fontSize: "0.9rem" }}>{d.exame.negativos} neg · {d.exame.reagentes} reag · {d.exame.inconclusivos} inconcl.</b></li>}
                {d.exame.reteste_em && <li><span style={notaStyle}>Reteste (inconclusivo)</span><b style={{ display: "block", fontSize: "0.9rem" }}>{dataCurta(d.exame.reteste_em)}</b></li>}
              </ul>
              {d.exame.leitura_fora_janela && <p style={{ color: "var(--amber)", fontSize: "0.84rem", display: "flex", gap: 6 }}><AlertTriangle size={14} style={{ marginTop: 2, flexShrink: 0 }} /><span>Leitura fora da janela de 72–96 h{d.exame.leitura_justificativa ? `: ${d.exame.leitura_justificativa}` : ""}.</span></p>}
            </div>
          )}
          {d.exame && d.exame.reagentes > 0 && d.estado === "aplicada" && <BannerReagentes aplicacaoId={d.id} />}
          {d.financeiro && (
            <div className="card" style={{ padding: "0.6rem 0.9rem" }}>
              <h3 className="card-header" style={{ marginBottom: "0.4rem" }}>Financeiro deste agendamento</h3>
              <ResumoCustoFinanceiro bloco={d.financeiro} rotuloCusto="Custo" custo={d.custo} />
            </div>
          )}
          <p style={notaStyle}>
            {d.carencia_texto ? `${d.carencia_texto}. ` : ""}
            {d.carencia_carne_ate ? `Carne até ${dataCurta(d.carencia_carne_ate)}. ` : ""}{d.carencia_leite_ate ? `Leite até ${dataCurta(d.carencia_leite_ate)}. ` : ""}
            Registrado por {d.registrado_por || "—"}.
          </p>
          {d.excecoes.length > 0 && <p style={{ color: "var(--amber)", fontSize: "0.84rem", display: "flex", gap: 6 }}><AlertTriangle size={14} style={{ marginTop: 2, flexShrink: 0 }} /><span><b>Exceções:</b> {d.excecoes.join("; ")}.</span></p>}
          {d.estado === "estornada" && <p role="status" style={{ color: "var(--red)", fontSize: "0.84rem" }}><b>Estornada por {d.estornado_por || "—"} em {dataHoraCurta(d.estornado_em)}{d.motivo_estorno ? `: ${d.motivo_estorno}` : " (desfeita na hora)"}. A original fica preservada.</b></p>}

          <div role="tablist" aria-label="Detalhe do concluído" style={{ display: "flex", gap: "0.4rem", borderBottom: "1px solid var(--border)" }}>
            {([["animais", "Animais"], ["checklist", "Checklist"], ["historico", "Histórico"]] as const).map(([k, n]) => (
              <button key={k} type="button" role="tab" aria-selected={aba === k} onClick={() => setAba(k)}
                      style={{ padding: "0.5rem 0.9rem", background: "transparent", border: "none", cursor: "pointer", fontSize: "0.85rem", fontWeight: aba === k ? 700 : 500,
                               color: aba === k ? "var(--dourado-light)" : "var(--text-muted)", borderBottom: aba === k ? "2px solid var(--dourado)" : "2px solid transparent" }}>{n}</button>
            ))}
          </div>
          {aba === "animais" && (
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr><th>Animal</th><th>Origem</th>{d.exame ? <><th>Resultado</th><th>Espessura</th></> : <><th>Dose</th><th>Peso</th></>}<th>Situação</th></tr></thead>
                <tbody>
                  {d.animais.map((a) => (
                    <tr key={a.numero_matriz}>
                      <td><b>{a.numero_matriz}</b>{a.nome ? <span style={{ ...notaStyle, display: "block" }}>{a.nome}</span> : null}</td>
                      <td style={{ fontSize: "0.82rem" }}>{a.origem === "fora_janela" ? <><ForaJanelaBadge n={1} />{a.motivo_origem && <span style={{ ...notaStyle, display: "block" }}>{a.motivo_origem}</span>}</> : "Na janela"}</td>
                      {d.exame ? (
                        <>
                          <td style={{ fontSize: "0.82rem", fontWeight: a.exame_resultado === "reagente" ? 700 : 400, color: a.exame_resultado === "reagente" ? "var(--red)" : undefined }}>
                            {a.exame_resultado ? RESULTADOS_ROTULO[a.exame_resultado] || a.exame_resultado : "—"}
                            {a.reteste_em && <span style={{ ...notaStyle, display: "block", fontWeight: 400 }}>reteste em {dataCurta(a.reteste_em)}</span>}
                          </td>
                          <td style={{ fontSize: "0.82rem" }}>{a.espessura_mm != null ? `${num(a.espessura_mm)} mm` : "—"}</td>
                        </>
                      ) : (
                        <>
                          <td style={{ fontSize: "0.82rem" }}>{a.resultado === "aplicado" ? `${num(a.dose)} ${a.unidade || ""}` : "—"}</td>
                          <td style={{ fontSize: "0.82rem" }}>{a.peso_kg ? `${num(a.peso_kg, 0)} kg${a.peso_estimado ? " (estimativa)" : ""}` : "—"}</td>
                        </>
                      )}
                      <td style={{ fontSize: "0.82rem" }}>
                        {a.resultado === "aplicado"
                          ? (d.exame ? (a.exame_resultado === "reagente" ? (a.notificado_em ? `Reagente · notificado por ${a.notificado_por || "—"} em ${dataHoraCurta(a.notificado_em)}` : "Reagente · notificação pendente") : "Exame realizado") : "Aplicado")
                          : `Não aplicado: ${a.motivo_nao} · ${a.destino_nao === "naoSeAplica" ? "desconsiderado" : "voltou à lista de espera"}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {aba === "checklist" && (
            <div>
              {d.ciencia_itens.length > 0 && (
                <p style={{ fontSize: "0.85rem", marginBottom: "0.6rem" }}>
                  <b>Ciência de {d.ciencia_itens.length} {plural(d.ciencia_itens.length, "item pendente", "itens pendentes")}</b> por {d.ciencia_usuario || "—"} em {dataHoraCurta(d.ciencia_em)}
                  {d.ciencia_motivo ? ` (${d.ciencia_motivo})` : ""}: {d.ciencia_itens.map((c) => c.nome).join(", ")}.
                </p>
              )}
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {d.checklist.itens.map((i) => (
                  <li key={i.id} style={{ padding: "0.4rem 0", borderBottom: "1px solid var(--border)", fontSize: "0.85rem" }}>
                    <b>{i.nome}</b> <span style={notaStyle}>· {i.status === "cumprido" ? "resolvido" : i.status === "pulado" ? `desconsiderado${i.observacao ? `: ${i.observacao}` : ""}` : "pendente"}</span>
                  </li>
                ))}
                {!d.checklist.itens.length && <li style={notaStyle}>Sem itens de checklist neste agendamento.</li>}
              </ul>
            </div>
          )}
          {aba === "historico" && (
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {d.log.slice().reverse().map((l) => (
                <li key={l.id} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--border)", fontSize: "0.85rem", color: l.acao === "Estornou" ? "var(--red)" : undefined }}>
                  <b>{l.acao}</b>
                  {l.detalhe && <span style={{ ...notaStyle, display: "block" }}>{l.detalhe}</span>}
                  {l.motivo && <span style={{ ...notaStyle, display: "block" }}>Motivo: {l.motivo}</span>}
                  <span style={{ ...notaStyle, display: "block" }}>{l.usuario_nome || "Sistema"} · {dataHoraCurta(l.criado_em)}{l.canal ? ` · ${l.canal}` : ""}</span>
                </li>
              ))}
            </ul>
          )}
          <div style={{ position: "sticky", bottom: "-0.9rem", margin: "0 -0.9rem -0.9rem", padding: "0.75rem 0.9rem", background: "var(--surface)", borderTop: "1px solid var(--border)", display: "flex", gap: "0.6rem", zIndex: 2 }}>
            {d.estado === "aplicada" && (
              <button type="button" className="btn-secondary" data-testid="detalhe-comprovante" onClick={() => setComprovante(true)}
                      disabled={!!d.exame && d.exame.reagentes > 0 && d.exame.reagentes >= d.animais.filter((a) => a.resultado === "aplicado").length}
                      title={d.exame && d.exame.reagentes >= d.animais.filter((a) => a.resultado === "aplicado").length && d.exame.reagentes > 0 ? "Bloqueado: todos os animais são reagentes." : "Comprovante para imprimir"}>
                <Printer size={14} /> Comprovante
              </button>
            )}
            {d.estado === "aplicada" && item && (
              <button type="button" className="btn-ghost" disabled={!admin} onClick={() => onEstornar(item)} title={admin ? undefined : "Só o perfil Administrador estorna"}>
                <Undo2 size={14} /> Estornar (administrador)
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={onFechar}>Fechar</button>
          </div>
        </div>
      )}
      {comprovante && <ComprovanteAplicacaoView aplicacaoId={id} onFechar={() => setComprovante(false)} />}
    </GavetaLancamento>
  );
}

// ─────────────────────────── estornar (admin, com motivo) ───────────────────────────
function GavetaEstornar({ item, onFechar, onFeito }: { item: ItemConcluido; onFechar: () => void; onFeito: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [outro, setOutro] = useState("");
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const texto = textoMotivo(motivo, outro);

  async function estornar() {
    setTentou(true);
    if (!texto || item.id == null) return;
    setSalvando(true); setErro(null);
    try { await estornarAplicacaoPreventiva(item.id, texto); onFeito(); }
    catch (e: any) { setErro(e.message || "Erro ao estornar"); } finally { setSalvando(false); }
  }
  return (
    <GavetaLancamento aberto onFechar={onFechar} titulo="Estornar (administrador)" icone={Undo2}>
      <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
        <div>
          <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)" }}>Estornar registro de {dataCurta(item.data)}</h2>
          <p style={notaStyle}>{item.protocolo_nome} · {item.animais_aplicados} {plural(item.animais_aplicados, "animal", "animais")}</p>
        </div>
        <p style={{ display: "flex", gap: 6, color: "var(--amber)", fontSize: "0.85rem" }}>
          <AlertTriangle size={15} style={{ marginTop: 2, flexShrink: 0 }} />
          O registro original fica preservado como “Estornada”, o estoque volta e o agendamento volta a “Agendado”. Fica gravado quem estornou e por quê.
        </p>
        <Chips idBase="es-m" rotulo="Motivo (obrigatório)" opcoes={MOTIVOS_ESTORNO} valor={motivo} onChange={setMotivo} erro={tentou && !texto ? "Escolha o motivo." : null} />
        {motivo === "Outro motivo" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={outro} onChange={(e) => setOutro(e.target.value)} />}
        {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
        <div style={{ display: "flex", gap: "0.6rem" }}>
          <button type="button" className="btn-primary" style={{ background: "var(--red)" }} disabled={salvando} onClick={estornar}><Undo2 size={14} /> {salvando ? "Estornando…" : "Estornar"}</button>
          <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        </div>
      </div>
    </GavetaLancamento>
  );
}
