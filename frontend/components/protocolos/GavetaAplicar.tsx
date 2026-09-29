"use client";
// Gaveta APLICAR — a MESMA em Protocolos › Acompanhamento e na Agenda (mesma
// largura, mesmos campos, mesmo endpoint POST /sanidade/cronogramas/{id}/aplicar;
// só muda o `canal` gravado). Mockup: docs/agents/auditoria-preventivo-agenda/
// mockups/fluxo-completo.html (proto-aplicar-dr.js).
//
// Regras que a tela mostra e o servidor confere: aplicador obrigatório (B19 e
// tuberculose: só veterinário), frasco vencido pede ciência, "Desconsiderar
// estoque" pede motivo e não baixa, itens pendentes do checklist pedem só a
// ciência (nunca bloqueiam), animal não aplicado pede motivo e destino.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Check, ChevronDown, Info, Printer, Syringe, Undo2 } from "lucide-react";
import {
  aplicarAgendamentoPreventivo, desfazerAplicacaoPreventiva, fetchContextoAplicar,
  type AplicarAgendamentoPayload, type CanalAplicacao, type ContextoAplicar, type ResultadoAplicar, type ResultadoExame,
} from "@/lib/api";
import { GavetaLancamento } from "@/components/lancamentos/GavetaLancamento";
import { TelaSkeleton } from "@/components/ui";
import { ResumoCustoFinanceiro } from "./FinanceiroAgendamento";
import { BannerReagentes, ComprovanteAplicacaoView, dataHoraLocal, RESULTADOS_ROTULO } from "./exameComum";
import { FormLeitura } from "./GavetaExame";
import {
  brl, Chips, dataCurta, diaSemana, hojeIso, inputStyle, labelStyle, MOTIVOS_CIENCIA, MOTIVOS_ESTOQUE, MOTIVOS_NAO_APLICADO,
  notaStyle, num, Pill, plural, textoMotivo,
} from "./preventivoComum";

type Props = {
  cronogramaId: number;
  canal: CanalAplicacao;
  onFechar: () => void;
  /** Depois de aplicar (e também depois de desfazer): quem abriu recarrega a lista. */
  onMudou?: () => void;
  /** Só no canal Protocolos: leva à aba Concluídos. */
  onVerConcluidos?: () => void;
};

const horaAgora = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
// "1 dose" / "7 doses": a unidade do estoque vem no singular.
const unPl = (un: string, n: number) => (n === 1 || !un ? un : un === "dose" ? "doses" : un === "unidade" ? "unidades" : un);
const novaChave = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `ap-${Date.now()}-${Math.random().toString(16).slice(2)}`);

export function GavetaAplicar({ cronogramaId, canal, onFechar, onMudou, onVerConcluidos }: Props) {
  const [ctx, setCtx] = useState<ContextoAplicar | null>(null);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoAplicar | null>(null);
  const [desfeito, setDesfeito] = useState(false);
  const chave = useRef(novaChave());

  const carregar = useCallback(() => {
    fetchContextoAplicar(cronogramaId).then(setCtx).catch((e) => setErroCarga(e.message || "Erro ao abrir o agendamento"));
  }, [cronogramaId]);
  useEffect(() => { carregar(); }, [carregar]);

  const fase = ctx?.exame?.fase;
  const titulo = fase === "inoculacao" ? "Aplicar exame · inoculação" : fase === "leitura" ? "Aplicar exame · leitura" : fase === "coleta" ? "Aplicar exame · coleta" : "Aplicar";
  return (
    <GavetaLancamento aberto onFechar={() => { if (resultado) onMudou?.(); onFechar(); }} titulo={titulo} icone={Syringe}>
      {erroCarga && <div className="alert-critico mb-3"><AlertTriangle size={16} /><span>{erroCarga}</span></div>}
      {!ctx && !erroCarga && <TelaSkeleton kpis={0} />}
      {ctx && !resultado && fase === "leitura" && ctx.exame?.inoculacao && (
        <FormLeitura
          ctx={ctx} canal={canal} chave={chave.current}
          onAplicado={(r) => { setResultado(r); onMudou?.(); }}
          onFechar={onFechar}
        />
      )}
      {ctx && !resultado && !(fase === "leitura" && ctx.exame?.inoculacao) && (
        <FormAplicar
          ctx={ctx} canal={canal} chave={chave.current}
          onAplicado={(r) => { setResultado(r); onMudou?.(); }}
          onFechar={onFechar}
        />
      )}
      {ctx && resultado && (
        <Concluida
          ctx={ctx} r={resultado} canal={canal} desfeito={desfeito}
          onDesfeito={() => { setDesfeito(true); onMudou?.(); }}
          onFechar={onFechar} onVerConcluidos={onVerConcluidos}
        />
      )}
    </GavetaLancamento>
  );
}

// ───────────────────────────── formulário ─────────────────────────────
function FormAplicar({ ctx, canal, chave, onAplicado, onFechar }: {
  ctx: ContextoAplicar; canal: CanalAplicacao; chave: string;
  onAplicado: (r: ResultadoAplicar) => void; onFechar: () => void;
}) {
  const hoje = ctx.hoje || hojeIso();
  const exame = ctx.exame || null;                 // exame: inoculação (TB) ou coleta (brucelose e outros)
  const semProduto = !!exame && !ctx.produto;      // exame sem produto (sorologia) não mexe no estoque
  const ckEst = ctx.estoque.checklist;
  const desconsiderouNoChecklist = ckEst.estado === "desconsiderado";
  const loteInicial = (() => {
    if (desconsiderouNoChecklist || !ctx.estoque.encontrado) return "";
    if (ckEst.estado === "vinculado" && ckEst.lote_id && ctx.estoque.lotes.some((l) => l.id === ckEst.lote_id && !l.vencido)) return String(ckEst.lote_id);
    return ctx.estoque.lote_sugerido_id ? String(ctx.estoque.lote_sugerido_id) : "";
  })();

  const [marc, setMarc] = useState<Set<string>>(() => new Set(ctx.animais.map((a) => a.numero_matriz)));
  const [naoMotivo, setNaoMotivo] = useState<Record<string, string>>({});
  const [naoOutro, setNaoOutro] = useState<Record<string, string>>({});
  const [naoDestino, setNaoDestino] = useState<Record<string, "espera" | "naoSeAplica">>({});
  const [animAberto, setAnimAberto] = useState(false);
  const [lote, setLote] = useState(loteInicial);
  const [ciente, setCiente] = useState(false);
  const [desconsiderar, setDesconsiderar] = useState(semProduto ? false : (desconsiderouNoChecklist || !ctx.estoque.encontrado));
  const [tipoTeste, setTipoTeste] = useState("");
  const [laudo, setLaudo] = useState("");
  const [resColeta, setResColeta] = useState<Record<string, ResultadoExame | "">>({});
  const [motEst, setMotEst] = useState(desconsiderouNoChecklist ? (ckEst.motivo || "") : "");
  const [motEstOutro, setMotEstOutro] = useState("");
  const [loteVet, setLoteVet] = useState(desconsiderouNoChecklist ? (ckEst.lote || "") : "");
  const [valVet, setValVet] = useState(desconsiderouNoChecklist ? (ckEst.validade || "") : "");
  const [aplicadorId, setAplicadorId] = useState(ctx.aplicador_sugerido_id ? String(ctx.aplicador_sugerido_id) : "");
  const [dataModo, setDataModo] = useState<"hoje" | "outra">("hoje");
  const [dataOutra, setDataOutra] = useState(hoje);
  const [hora, setHora] = useState(horaAgora());
  const [custo, setCusto] = useState("");
  const [pesos, setPesos] = useState<Record<string, string>>({});
  const [cientePend, setCientePend] = useState(false);
  const [motCiencia, setMotCiencia] = useState("");
  const [resumoAberto, setResumoAberto] = useState(false);
  const [tentou, setTentou] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erroServ, setErroServ] = useState<string | null>(null);

  const dataReal = dataModo === "hoje" ? hoje : dataOutra;
  const pessoa = ctx.pessoas.find((p) => String(p.id) === aplicadorId);
  const frasco = ctx.estoque.lotes.find((l) => String(l.id) === lote);
  const frascoVencido = !desconsiderar && !!frasco?.vencido;
  const pend = ctx.checklist.pendentes;

  const doseDe = (n: string): number | null => {
    const a = ctx.animais.find((x) => x.numero_matriz === n);
    if (!a) return null;
    const p = pesos[n] ? Number(String(pesos[n]).replace(",", ".")) : NaN;
    // Dose por peso: o peso digitado na hora vale mais que a pesagem/estimativa.
    if (ctx.por_peso && !isNaN(p) && p > 0 && ctx.kg_ref && ctx.dose_ref) return (p / ctx.kg_ref) * ctx.dose_ref;
    return a.dose;
  };
  const aplicados = ctx.animais.filter((a) => marc.has(a.numero_matriz));
  const nao = ctx.animais.filter((a) => !marc.has(a.numero_matriz));
  const totalDose = aplicados.reduce((s, a) => s + (doseDe(a.numero_matriz) || 0), 0);
  const un = ctx.unidade || "";
  const custoNum = custo.trim() !== "" && !isNaN(Number(custo.replace(",", "."))) ? Number(custo.replace(",", ".")) : null;
  const semPeso = aplicados.filter((a) => ctx.por_peso && doseDe(a.numero_matriz) == null).map((a) => a.numero_matriz);
  const saldoFrasco = desconsiderar ? null : (frasco ? frasco.saldo : ctx.estoque.saldo);
  const faltam = saldoFrasco != null ? Math.max(0, totalDose - saldoFrasco) : 0;
  const restante = saldoFrasco != null ? Math.max(0, saldoFrasco - totalDose) : null;
  const carenciaCarne = ctx.carencia.carne_dias != null ? somaDias(dataReal, ctx.carencia.carne_dias) : null;
  const carenciaLeite = ctx.carencia.proibido_lactacao ? null : ctx.carencia.leite_dias != null ? somaDias(dataReal, ctx.carencia.leite_dias) : null;
  const foraJanela = aplicados.filter((a) => a.origem === "fora_janela").length;
  const restritos = aplicados.filter((a) => a.restricao);
  const comResColeta = aplicados.filter((a) => resColeta[a.numero_matriz]);

  const motivoNao = (n: string) => textoMotivo(naoMotivo[n] || "", naoOutro[n] || "");
  let erro = "";
  if (!aplicados.length) erro = "Marque pelo menos 1 animal aplicado.";
  else if (!aplicadorId) erro = "Escolha quem aplicou.";
  else if (dataReal > hoje) erro = "A data real não pode ser futura.";
  else if (ctx.exige_veterinario && !pessoa?.veterinario) erro = `Só veterinário habilitado (CRMV) aplica ${ctx.protocolo_nome}.`;
  else if (restritos.length) erro = `Brucelose B19: só fêmeas de 3 a 8 meses. Desmarque ${restritos.map((a) => a.numero_matriz).join(", ")}.`;
  else if (desconsiderar && !textoMotivo(motEst, motEstOutro)) erro = "Escolha o motivo para desconsiderar o estoque.";
  else if (!desconsiderar && !semProduto && !ctx.estoque.encontrado) erro = "O produto não está no estoque: desconsidere o estoque com motivo.";
  else if (frascoVencido && !ciente) erro = "Frasco vencido: marque a ciência para usar assim mesmo.";
  else if (semPeso.length) erro = `Informe o peso de: ${semPeso.join(", ")}.`;
  else if (nao.some((a) => !motivoNao(a.numero_matriz))) erro = "Escolha o motivo de cada animal não aplicado.";
  else if (exame?.fase === "coleta" && comResColeta.length > 0 && comResColeta.length < aplicados.length) erro = "Informe o resultado de todos os animais coletados (ou de nenhum).";
  else if (pend.length && !cientePend) erro = `Marque a ciência dos ${pend.length} ${plural(pend.length, "item pendente", "itens pendentes")} do checklist.`;

  async function aplicar() {
    setTentou(true);
    if (erro) return;
    setSalvando(true); setErroServ(null);
    const corpo: AplicarAgendamentoPayload = {
      canal, aplicador_pessoa_id: Number(aplicadorId), animais_aplicados: aplicados.map((a) => a.numero_matriz),
      nao_aplicados: nao.map((a) => ({ numero_matriz: a.numero_matriz, motivo: motivoNao(a.numero_matriz), destino: naoDestino[a.numero_matriz] || "espera" })),
      data_aplicacao: dataReal, hora: hora || null, custo: custoNum,
      ciencia_pendentes: pend.length > 0 && cientePend, ciencia_motivo: cientePend ? (motCiencia || null) : null,
      chave_idempotencia: chave,
    };
    if (exame) {
      if (tipoTeste) corpo.tipo_teste = tipoTeste;
      if (laudo.trim()) corpo.laudo = laudo.trim();
      if (exame.fase === "coleta" && comResColeta.length > 0) corpo.resultados = Object.fromEntries(aplicados.map((a) => [a.numero_matriz, resColeta[a.numero_matriz] as ResultadoExame]));
    }
    if (semProduto) {
      // sem produto: nada de estoque
    } else if (desconsiderar) {
      corpo.desconsiderar_estoque = true;
      corpo.motivo_desconsiderar_estoque = textoMotivo(motEst, motEstOutro);
      corpo.lote_veterinario = loteVet.trim() || null;
      corpo.validade_veterinario = valVet || null;
    } else {
      corpo.estoque_id = ctx.estoque.estoque_id;
      corpo.lote_id = lote ? Number(lote) : null;
      corpo.ciente_vencido = frascoVencido && ciente;
    }
    const pesosNum: Record<string, number> = {};
    Object.entries(pesos).forEach(([n, v]) => { const x = Number(String(v).replace(",", ".")); if (x > 0) pesosNum[n] = x; });
    if (ctx.por_peso && Object.keys(pesosNum).length) corpo.pesos = pesosNum;
    try {
      onAplicado(await aplicarAgendamentoPreventivo(ctx.cronograma_id, corpo));
    } catch (e: any) { setErroServ(e.message || "Erro ao aplicar"); } finally { setSalvando(false); }
  }

  // Custo: o digitado; senão doses x preço do estoque; frasco do veterinário (estoque desconsiderado) = a informar.
  const precoUn = ctx.financeiro?.necessidade.preco_unitario ?? null;
  const custoConferir: number | null = custoNum != null ? custoNum : desconsiderar || precoUn == null ? null : Math.round(totalDose * precoUn * 100) / 100;
  const custoMotivo = custoConferir != null ? null : desconsiderar ? "Frasco do veterinário: sem custo calculado" : (ctx.financeiro?.necessidade.custo_motivo || "Sem preço cadastrado para este produto");
  const leituraEm = exame?.fase === "inoculacao" ? `leitura em ${dataCurta(somaDias(dataReal, 3))} às ${hora || "—"} (72 h)` : "";
  const linhaResumo = exame
    ? `${aplicados.length} ${plural(aplicados.length, "animal", "animais")}${semProduto ? "" : ` · ${num(totalDose)} ${unPl(un, totalDose)} · restante ${restante == null ? "—" : `${num(restante)} ${unPl(un, restante)}`}`}${leituraEm ? ` · ${leituraEm}` : " · resultado do laboratório"} · custo ${custoConferir != null ? brl(custoConferir) : "a informar"}${ctx.financeiro && ctx.financeiro.contas_ativas > 0 ? ` · conta a pagar ${brl(ctx.financeiro.conta_a_pagar_total)}` : ""}`
    : `${aplicados.length} ${plural(aplicados.length, "animal", "animais")} · ${num(totalDose)} ${unPl(un, totalDose)} · restante ${restante == null ? "—" : `${num(restante)} ${unPl(un, restante)}`}${carenciaCarne ? ` · carne até ${dataCurta(carenciaCarne)}` : ""}${carenciaLeite ? ` · leite até ${dataCurta(carenciaLeite)}` : ""} · custo ${custoConferir != null ? brl(custoConferir) : "a informar"}${ctx.financeiro && ctx.financeiro.contas_ativas > 0 ? ` · conta a pagar ${brl(ctx.financeiro.conta_a_pagar_total)}` : ""}`;
  const boxAviso = (cor: string, texto: React.ReactNode, icone = <AlertTriangle size={15} />) => (
    <div role="status" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", fontSize: "0.82rem", border: `1px solid ${cor}`, borderLeft: `4px solid ${cor}`, borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem", background: "var(--surface-2)" }}>
      <span style={{ color: cor, marginTop: 2, display: "inline-flex" }}>{icone}</span><span>{texto}</span>
    </div>
  );

  return (
    <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div>
        <p style={{ ...notaStyle, margin: 0 }}>
          Aberto de: <b>{canal === "Agenda" ? "Agenda" : "Protocolos › Acompanhamento"}</b>
        </p>
        <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--dourado-light)", marginTop: "0.3rem" }}>{ctx.protocolo_nome}</h2>
        <p style={notaStyle}>
          {diaSemana(ctx.data_evento)} {dataCurta(ctx.data_evento)}{ctx.hora ? ` ${ctx.hora}` : ""} · {ctx.responsavel.nome}{ctx.responsavel.crmv ? ` (${ctx.responsavel.crmv})` : ""}
          {ctx.produto ? ` · ${ctx.produto}` : ""}
        </p>
      </div>

      {/* avisos */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {exame?.fase === "inoculacao" && boxAviso("var(--dourado-light)", <>Inoculação da tuberculina: só veterinário habilitado (CRMV). A leitura fica marcada para <b>72 h depois</b>, na mesma hora, e vai para a Agenda; o registro só entra em Concluídos com o resultado de cada animal.</>, <Info size={15} />)}
        {exame?.fase === "coleta" && boxAviso("var(--dourado-light)", <>Exame de uma etapa só (coleta): informe o nº do laudo. Se o resultado do laboratório já chegou, marque abaixo; reagente gera o aviso persistente e pede a notificação.</>, <Info size={15} />)}
        {restritos.length > 0 && boxAviso("var(--red)", <><b>Brucelose B19: só fêmeas de 3 a 8 meses.</b> {restritos.map((a) => `${a.numero_matriz} (${a.restricao?.split(": ")[1] || a.restricao})`).join("; ")}. Desmarque esses animais (motivo: Outro).</>)}
        {frascoVencido && boxAviso("var(--red)", <><b>Frasco vencido.</b> O frasco {frasco?.numero_lote || `#${frasco?.id}`} venceu em {dataCurta(frasco?.validade)}. É preciso ciência para usar assim mesmo; ela fica registrada com o seu nome e a hora.</>)}
        {!frascoVencido && frasco && frasco.vence_em_dias != null && frasco.vence_em_dias <= 30 && boxAviso("var(--amber)", <><b>Validade próxima.</b> O frasco {frasco.numero_lote || `#${frasco.id}`} vence em {frasco.vence_em_dias} {plural(frasco.vence_em_dias, "dia", "dias")} ({dataCurta(frasco.validade)}).</>)}
        {faltam > 0 && boxAviso("var(--amber)", <><b>Estoque insuficiente.</b> Faltam {num(faltam)} {un}. A aplicação não é bloqueada: o estoque fica negativo e a divergência é avisada. Comunique a compra.</>)}
        {ctx.exige_veterinario && !pessoa?.veterinario && boxAviso("var(--red)", <><b>{ctx.protocolo_nome}: só veterinário habilitado (CRMV) aplica.</b> Escolha o veterinário em “Quem aplicou”.</>)}
        {ctx.carencia.proibido_lactacao && boxAviso("var(--red)", <><b>Não usar em vaca em lactação.</b> Confira os animais antes de aplicar.</>)}
        {dataReal < hoje && boxAviso("var(--dourado-light)", "Aplicação já realizada: confira a data e a hora em que foi feita.", <Info size={15} />)}
        {ctx.data_evento > hoje && boxAviso("var(--dourado-light)", `Aplicando antes da data agendada (${dataCurta(ctx.data_evento)}). Tudo o que estava combinado continua valendo.`, <Info size={15} />)}
        {foraJanela > 0 && boxAviso("var(--amber)", `${foraJanela} ${plural(foraJanela, "animal incluído", "animais incluídos")} fora da janela de aplicação (fica marcado no histórico).`)}
      </div>

      {/* resumo */}
      <details className="card" open={resumoAberto} onToggle={(e) => setResumoAberto((e.currentTarget as HTMLDetailsElement).open)} style={{ padding: "0.6rem 0.9rem" }}>
        <summary style={{ cursor: "pointer", display: "flex", flexDirection: "column", gap: 2, listStyle: "none" }}>
          <span style={{ ...labelStyle, marginBottom: 0, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" }}>{exame?.fase === "inoculacao" ? "O que acontece ao confirmar a inoculação" : "O que acontece ao aplicar"}</span>
          <span style={{ fontSize: "0.86rem", fontWeight: 600 }}>{linhaResumo}</span>
          <span style={{ ...notaStyle, display: "inline-flex", alignItems: "center", gap: 3 }}><ChevronDown size={13} />Detalhes</span>
        </summary>
        <ul style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "0.6rem", listStyle: "none", margin: "0.7rem 0 0", padding: 0 }}>
          <Item k="Animais" v={String(aplicados.length)} />
          <Item k={ctx.por_peso ? "Volume" : "Doses"} v={`${num(totalDose)} ${unPl(un, totalDose)}`} />
          <Item k="Estoque restante" v={restante == null ? "sem saída" : `${num(restante)} ${unPl(un, restante)}`} />
          {!exame && <Item k="Carência" v={[carenciaCarne ? `carne até ${dataCurta(carenciaCarne)}` : "", carenciaLeite ? `leite até ${dataCurta(carenciaLeite)}` : "", ctx.carencia.proibido_lactacao ? "leite: não usar em lactação" : ""].filter(Boolean).join(" · ") || "sem carência informada"} />}
          {exame?.fase === "inoculacao" && <Item k="Leitura" v={leituraEm.replace(" (72 h)", "")} />}
          <Item k={custoNum != null ? "Custo" : "Custo previsto"} v={custoConferir != null ? brl(custoConferir) : "a informar"} />
        </ul>
        {ctx.financeiro && (
          <div style={{ marginTop: "0.7rem" }}>
            <ResumoCustoFinanceiro bloco={{ ...ctx.financeiro, custo_motivo: custoMotivo }} custo={custoConferir} rotuloCusto={custoNum != null ? "Custo" : "Custo previsto"} />
          </div>
        )}
        <p style={{ ...notaStyle, marginTop: "0.6rem" }}>{exame
          ? (exame.fase === "inoculacao" ? "A inoculação baixa a tuberculina do estoque e marca a leitura para 72 h depois; o registro vai para Concluídos só com o resultado. " : "O exame vai para Concluídos como “Exame realizado”. ")
          : <>{ctx.por_peso ? "Dose por peso: cada animal recebe pelo seu peso. " : ""}Cada animal vira uma linha em Sanidade e o registro vai para <b>Concluídos</b>.</>}</p>
      </details>

      {/* animais */}
      <div>
        <span style={labelStyle}>Animais: marque quem foi aplicado</span>
        {/* Até 6 animais aparecem direto; acima disso a lista recolhe (abre sozinha se alguém ficar de fora). */}
        <Recolhivel colapsavel={ctx.animais.length > 6} aberto={animAberto || nao.length > 0} onToggle={setAnimAberto}
                    resumo={<><b>{aplicados.length} de {ctx.animais.length} marcados como aplicados</b> · ver e ajustar os animais</>}>
          <div className="card" style={{ padding: "0.3rem 0.8rem" }}>
            {ctx.animais.map((a) => {
              const mk = marc.has(a.numero_matriz);
              const d = doseDe(a.numero_matriz);
              return (
                <div key={a.numero_matriz} style={{ borderBottom: "1px solid var(--border)", padding: "0.5rem 0" }}>
                  <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
                    <label style={{ display: "flex", gap: "0.6rem", alignItems: "center", cursor: "pointer", flex: "1 1 220px", minWidth: 0 }}>
                      <input type="checkbox" checked={mk} aria-label={`Aplicado em ${a.numero_matriz}`} style={{ width: 18, height: 18 }}
                             onChange={() => setMarc((p) => { const s = new Set(p); if (s.has(a.numero_matriz)) s.delete(a.numero_matriz); else s.add(a.numero_matriz); return s; })} />
                      <span>
                        <b>{a.numero_matriz}{a.nome ? ` ${a.nome}` : ""}</b>
                        <span style={{ ...notaStyle, display: "block" }}>
                          {a.lote || "Sem lote"} · {d != null ? `${num(d)} ${un}` : (semProduto ? "coleta" : "sem peso")}
                          {ctx.por_peso && a.peso_kg ? ` (${num(a.peso_kg, 0)} kg${a.peso_estimado ? ", estimativa pelo lote" : ""})` : ""}
                        </span>
                      </span>
                    </label>
                    {a.origem === "fora_janela" && <Pill cor="var(--amber)" title={a.motivo || undefined}>Fora da janela</Pill>}
                    {a.restricao && <Pill cor="var(--red)" title={a.restricao}>B19: só fêmea de 3 a 8 meses</Pill>}
                    {exame?.fase === "coleta" && mk && (
                      <select style={{ ...inputStyle, width: 150, minHeight: 36 }} aria-label={`Resultado de ${a.numero_matriz} (se já conhecido)`} value={resColeta[a.numero_matriz] || ""}
                              onChange={(e) => setResColeta((p) => ({ ...p, [a.numero_matriz]: e.target.value as ResultadoExame | "" }))}>
                        <option value="">Resultado: depois</option>
                        {exame.resultados.map((r) => <option key={r} value={r}>{RESULTADOS_ROTULO[r]}</option>)}
                      </select>
                    )}
                    {ctx.por_peso && mk && (a.peso_estimado || a.sem_peso) && (
                      <input inputMode="decimal" style={{ ...inputStyle, width: 120 }} placeholder="peso (kg)" aria-label={`Peso de ${a.numero_matriz} (kg)`} value={pesos[a.numero_matriz] || ""}
                             onChange={(e) => setPesos((p) => ({ ...p, [a.numero_matriz]: e.target.value }))} />
                    )}
                  </div>
                  {!mk && (
                    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", padding: "0.5rem 0 0 2rem" }}>
                      <select style={{ ...inputStyle, flex: "1 1 180px", width: "auto" }} aria-label={`Motivo de ${a.numero_matriz} não ter sido aplicado`}
                              value={naoMotivo[a.numero_matriz] || ""} onChange={(e) => setNaoMotivo((p) => ({ ...p, [a.numero_matriz]: e.target.value }))}>
                        <option value="">Motivo (obrigatório)</option>
                        {MOTIVOS_NAO_APLICADO.map((m) => <option key={m}>{m}</option>)}
                      </select>
                      {naoMotivo[a.numero_matriz] === "Outro" && (
                        <input style={{ ...inputStyle, flex: "1 1 180px", width: "auto" }} aria-label={`Descreva o motivo de ${a.numero_matriz}`} placeholder="Descreva" value={naoOutro[a.numero_matriz] || ""}
                               onChange={(e) => setNaoOutro((p) => ({ ...p, [a.numero_matriz]: e.target.value }))} />
                      )}
                      <select style={{ ...inputStyle, flex: "1 1 200px", width: "auto" }} aria-label={`Destino de ${a.numero_matriz}`} value={naoDestino[a.numero_matriz] || "espera"}
                              onChange={(e) => setNaoDestino((p) => ({ ...p, [a.numero_matriz]: e.target.value as "espera" | "naoSeAplica" }))}>
                        <option value="espera">Volta à lista de espera</option>
                        <option value="naoSeAplica">Desconsiderar</option>
                      </select>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Recolhivel>
        <p style={{ ...notaStyle, marginTop: "0.3rem" }}>
          <button type="button" className="btn-ghost" style={{ padding: 0, border: "none", textDecoration: "underline" }}
                  onClick={() => setMarc(marc.size === ctx.animais.length ? new Set() : new Set(ctx.animais.map((a) => a.numero_matriz)))}>
            {marc.size === ctx.animais.length ? "Desmarcar todos" : "Marcar todos como aplicados"}
          </button>
          {nao.length > 0 && ` · ${nao.length} ${plural(nao.length, "animal fica fora", "animais ficam fora")}`}
        </p>
      </div>

      {/* frasco e estoque (exame sem produto — sorologia — não usa estoque) */}
      {!semProduto && <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label htmlFor="ap-fr" style={labelStyle}>Frasco / lote (validade)</label>
          <select id="ap-fr" style={inputStyle} value={lote} disabled={desconsiderar || !ctx.estoque.encontrado || !ctx.estoque.lotes.length}
                  onChange={(e) => { setLote(e.target.value); setCiente(false); }}>
            {desconsiderar ? <option>Estoque desconsiderado (sem baixa){loteVet ? ` · lote ${loteVet}` : ""}</option>
              : !ctx.estoque.encontrado ? <option>Sem produto no estoque</option>
              : <>
                {!ctx.estoque.lotes.length && <option value="">Sem frascos abertos: baixa no saldo do item</option>}
                {ctx.estoque.lotes.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.numero_lote || `#${l.id}`} · validade {dataCurta(l.validade)} · saldo {num(l.saldo)}{l.vencido ? " · VENCIDO" : l.vence_em_dias != null && l.vence_em_dias <= 30 ? ` · vence em ${l.vence_em_dias} dias` : ""}
                  </option>
                ))}
              </>}
          </select>
          <span style={notaStyle}>{desconsiderar ? "Nada é baixado do estoque." : `${ctx.estoque.nome || ctx.produto || ""} · o frasco vencido nunca vem escolhido`}</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div><label htmlFor="ap-dose" style={labelStyle}>Dose</label><input id="ap-dose" style={inputStyle} readOnly aria-readonly="true" value={ctx.dose_texto} /></div>
          <div><label htmlFor="ap-via" style={labelStyle}>Via</label><input id="ap-via" style={inputStyle} readOnly aria-readonly="true" value={ctx.via || "—"} /><span style={notaStyle}>Via aprovada; não pode ser trocada.</span></div>
        </div>
      </div>}
      {semProduto && <div><label htmlFor="ap-via" style={labelStyle}>Como é feito</label><input id="ap-via" style={inputStyle} readOnly aria-readonly="true" value={ctx.via || ctx.dose_texto || "Coleta"} /></div>}
      {exame?.fase === "inoculacao" && (
        <div>
          <label htmlFor="ap-tt" style={labelStyle}>Tipo de teste (a leitura confirma)</label>
          <select id="ap-tt" style={inputStyle} value={tipoTeste} onChange={(e) => setTipoTeste(e.target.value)}>
            <option value="">Escolher na leitura</option>
            {exame.tipos_teste.map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
      )}
      {exame?.fase === "coleta" && (
        <div>
          <label htmlFor="ap-laudo" style={labelStyle}>Nº do laudo / protocolo do laboratório (opcional)</label>
          <input id="ap-laudo" style={inputStyle} value={laudo} onChange={(e) => setLaudo(e.target.value)} />
        </div>
      )}
      {frascoVencido && (
        <label style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", cursor: "pointer", fontSize: "0.85rem" }}>
          <input type="checkbox" checked={ciente} onChange={(e) => setCiente(e.target.checked)} style={{ width: 18, height: 18, marginTop: 2 }} />
          <span><b>Ciente, usar assim mesmo.</b> O frasco está vencido e a ciência fica registrada com o meu nome e a hora.</span>
        </label>
      )}
      {!semProduto && <label style={{ display: "flex", gap: "0.6rem", alignItems: "center", cursor: "pointer", fontSize: "0.85rem" }}>
        <input type="checkbox" checked={desconsiderar} disabled={!ctx.estoque.encontrado} onChange={(e) => setDesconsiderar(e.target.checked)} style={{ width: 18, height: 18 }} />
        <span>Desconsiderar estoque (frasco do veterinário: nada é baixado)</span>
      </label>}
      {desconsiderar && !semProduto && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: "0.7rem", padding: "0.8rem 1rem" }}>
          <Chips idBase="ap-me" rotulo="Motivo (obrigatório; nada vem marcado)" opcoes={MOTIVOS_ESTOQUE} valor={motEst} onChange={setMotEst}
                 erro={tentou && !textoMotivo(motEst, motEstOutro) ? "Escolha o motivo para desconsiderar o estoque." : null} />
          {motEst === "Outro" && <input style={inputStyle} aria-label="Descreva o motivo" placeholder="Descreva o motivo" value={motEstOutro} onChange={(e) => setMotEstOutro(e.target.value)} />}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div><label htmlFor="ap-lv" style={labelStyle}>Lote do frasco</label><input id="ap-lv" style={inputStyle} value={loteVet} onChange={(e) => setLoteVet(e.target.value)} placeholder="ex.: VET-778" /></div>
            <div><label htmlFor="ap-vv" style={labelStyle}>Validade</label><input id="ap-vv" type="date" style={inputStyle} value={valVet} onChange={(e) => setValVet(e.target.value)} /></div>
          </div>
        </div>
      )}

      {/* quem, quando, custo */}
      <div>
        <label htmlFor="ap-quem" style={labelStyle}>Quem aplicou</label>
        <select id="ap-quem" style={inputStyle} value={aplicadorId} onChange={(e) => setAplicadorId(e.target.value)}>
          <option value="">Escolha quem aplicou</option>
          {ctx.pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.veterinario ? "veterinário" : (p.tipo || "pessoa").toLowerCase()}{p.crmv ? `, ${p.crmv}` : ""})</option>)}
        </select>
        {!aplicadorId && <span style={notaStyle}>Obrigatório: escolha quem aplicou para liberar o botão.</span>}
      </div>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ ...labelStyle, marginBottom: "0.3rem" }}>Data e hora reais</legend>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
          {(["hoje", "outra"] as const).map((m) => (
            <label key={m} style={{ display: "inline-flex", gap: 6, alignItems: "center", cursor: "pointer", fontSize: "0.82rem", padding: "0.35rem 0.8rem", borderRadius: 999,
                                    border: `1px solid ${dataModo === m ? "var(--pill-active-border)" : "var(--border)"}`, background: dataModo === m ? "var(--pill-active-bg)" : "transparent",
                                    color: dataModo === m ? "var(--pill-active-fg)" : "var(--text)", fontWeight: dataModo === m ? 700 : 500 }}>
              <input type="radio" name="ap-dt" checked={dataModo === m} onChange={() => { setDataModo(m); if (m === "hoje") setDataOutra(hoje); }} />
              {m === "hoje" ? `Hoje · ${dataCurta(hoje)}` : "Outra data"}
            </label>
          ))}
          {dataModo === "outra" && <input type="date" style={{ ...inputStyle, width: "auto" }} aria-label="Outra data" value={dataOutra} max={hoje} onChange={(e) => setDataOutra(e.target.value)} />}
          <input type="time" style={{ ...inputStyle, width: "auto" }} aria-label="Hora" value={hora} onChange={(e) => setHora(e.target.value)} />
        </div>
      </fieldset>
      <div>
        <label htmlFor="ap-custo" style={labelStyle}>Custo (opcional)</label>
        <input id="ap-custo" inputMode="decimal" style={inputStyle} value={custo} onChange={(e) => setCusto(e.target.value)}
               placeholder={desconsiderar ? "Informe o custo do frasco ou deixe a informar" : "Em branco: doses × preço do estoque"} />
      </div>

      {/* ciência dos pendentes */}
      {pend.length > 0 && (
        <div className="card" style={{ padding: "0.8rem 1rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <label style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", cursor: "pointer", fontSize: "0.85rem" }}>
            <input type="checkbox" checked={cientePend} onChange={(e) => setCientePend(e.target.checked)} style={{ width: 18, height: 18, marginTop: 2 }} />
            <span>
              <b>Ciente dos {pend.length} {plural(pend.length, "item pendente", "itens pendentes")} do checklist.</b> Aplicar não é bloqueado; a ciência (itens, quem e quando) fica gravada no registro.
              <span style={{ ...notaStyle, display: "block" }}>{pend.map((p) => p.nome).join(" · ")}</span>
            </span>
          </label>
          {cientePend && <Chips idBase="ap-mc" rotulo="Motivo (opcional)" opcoes={MOTIVOS_CIENCIA} valor={motCiencia} onChange={setMotCiencia} />}
        </div>
      )}

      {erroServ && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erroServ}</p>}

      {/* rodapé fixo */}
      <div style={{
        position: "sticky", bottom: "-0.9rem", margin: "0 -0.9rem -0.9rem", padding: "0.75rem 0.9rem", background: "var(--surface)",
        borderTop: "1px solid var(--border)", display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap", zIndex: 2,
      }}>
        <button type="button" id="ap-ok" className="btn-primary-gold" aria-disabled={!!erro || salvando} disabled={salvando || !aplicadorId}
                title={!aplicadorId ? "Escolha quem aplicou" : undefined} onClick={aplicar}>
          <Check size={14} /> {salvando ? "Salvando…" : exame?.fase === "inoculacao" ? `Confirmar inoculação (${aplicados.length})` : exame?.fase === "coleta" ? `Aplicar (coleta · ${aplicados.length})` : `Aplicar (${aplicados.length} ${plural(aplicados.length, "animal", "animais")})`}
        </button>
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <span id="ap-erro" role="status" style={{ ...notaStyle, color: "var(--amber)", flex: "1 1 200px" }}>{erro}</span>
      </div>
    </div>
  );
}

function Recolhivel({ colapsavel, aberto, onToggle, resumo, children }: {
  colapsavel: boolean; aberto: boolean; onToggle: (aberto: boolean) => void; resumo: React.ReactNode; children: React.ReactNode;
}) {
  if (!colapsavel) return <>{children}</>;
  return (
    <details open={aberto} onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)}>
      <summary style={{ cursor: "pointer", fontSize: "0.85rem", marginBottom: "0.4rem" }}>{resumo}</summary>
      {children}
    </details>
  );
}

function Item({ k, v }: { k: string; v: string }) {
  return (
    <li style={{ background: "var(--surface-2)", borderRadius: "var(--r-sm)", padding: "0.5rem 0.7rem" }}>
      <span style={{ ...notaStyle, display: "block" }}>{k}</span>
      <b style={{ fontSize: v.length > 14 ? "0.85rem" : "1rem" }}>{v}</b>
    </li>
  );
}

function somaDias(iso: string, dias: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + dias);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// ───────────────────────── Aplicação concluída ─────────────────────────
function Concluida({ ctx, r, canal, desfeito, onDesfeito, onFechar, onVerConcluidos }: {
  ctx: ContextoAplicar; r: ResultadoAplicar; canal: CanalAplicacao; desfeito: boolean;
  onDesfeito: () => void; onFechar: () => void; onVerConcluidos?: () => void;
}) {
  const ap = r.aplicacao;
  const fase = ap.fase || null;
  const [comprovante, setComprovante] = useState(false);
  const [recargaBanner, setRecargaBanner] = useState(0);
  const [restante, setRestante] = useState(r.desfazer_segundos);
  const [erro, setErro] = useState<string | null>(null);
  const [desfazendo, setDesfazendo] = useState(false);
  useEffect(() => {
    if (desfeito || restante <= 0) return;
    const t = setTimeout(() => setRestante((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [restante, desfeito]);
  const aplicados = ap.animais.filter((a) => a.resultado === "aplicado");
  const nao = ap.animais.filter((a) => a.resultado === "nao_aplicado");

  async function desfazer() {
    setDesfazendo(true); setErro(null);
    try { await desfazerAplicacaoPreventiva(ap.id); onDesfeito(); }
    catch (e: any) { setErro(e.message || "Não foi possível desfazer"); setRestante(0); }
    finally { setDesfazendo(false); }
  }

  if (desfeito) {
    return (
      <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }} role="status">
        <div className="card">
          <div className="card-header mb-2 flex items-center gap-2"><Undo2 size={16} /> Desfeito na hora</div>
          <p style={{ fontSize: "0.9rem" }}>{fase === "leitura" ? "A leitura foi desfeita: o resultado saiu, o agendamento voltou a “Agendado” (aguardando a leitura) e a original fica preservada como Estornada."
            : fase === "inoculacao" ? "A inoculação foi desfeita: a tuberculina voltou ao estoque e o agendamento voltou à data anterior. A original fica preservada como Estornada."
            : "A aplicação foi desfeita: o estoque voltou e o agendamento continua Agendado. A original fica preservada como Estornada."}</p>
        </div>
        <div><button type="button" className="btn-secondary" onClick={onFechar}>Fechar</button></div>
      </div>
    );
  }
  return (
    <div className="le-raiz" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div className="card" role="status">
        <div className="card-header mb-2 flex items-center gap-2"><Check size={16} /> {fase === "inoculacao" ? "Inoculação registrada" : fase ? "Exame realizado" : "Aplicado"} · {ctx.protocolo_nome} · {aplicados.length} {plural(aplicados.length, "animal", "animais")} · {dataCurta(ap.data_aplicacao)} {ap.hora || ""}</div>
        <p style={{ fontWeight: 700, fontSize: "0.9rem", marginBottom: "0.4rem" }}>O que o sistema fez sozinho</p>
        {fase && <ListaExame ctx={ctx} r={r} />}
        {!fase && <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.86rem", lineHeight: 1.7 }}>
          <li>{aplicados.length} {plural(aplicados.length, "aplicação registrada", "aplicações registradas")} em Sanidade (natureza preventiva).</li>
          <li>{ap.estoque_desconsiderado ? `Estoque desconsiderado (${ap.estoque_motivo}): nada foi baixado.` : `Estoque baixado: ${num(ap.dose_total)} ${unPl(ap.unidade || "", ap.dose_total || 0)}${ap.lote_texto ? ` do lote ${ap.lote_texto}` : ""}.`}</li>
          {(ap.carencia_carne_ate || ap.carencia_leite_ate) && <li>Carência: {[ap.carencia_carne_ate ? `carne até ${dataCurta(ap.carencia_carne_ate)}` : "", ap.carencia_leite_ate ? `leite até ${dataCurta(ap.carencia_leite_ate)}` : ""].filter(Boolean).join(" · ")}.</li>}
          <li>Registrado por {ap.aplicador_nome ? `${ap.aplicador_nome} (aplicador)` : "—"} pelo canal {ap.canal}.</li>
          <li>
            <b>Custo:</b> {ap.custo != null ? brl(ap.custo) : <b style={{ color: "var(--amber)" }}>a informar</b>}
            {ap.custo == null && r.financeiro?.custo_motivo ? ` (${r.financeiro.custo_motivo})` : ""}
            {r.financeiro && r.financeiro.contas_ativas > 0 ? ` · conta a pagar lançada: ${brl(r.financeiro.conta_a_pagar_total)}`
              : r.financeiro && r.financeiro.pagamento_vinculado_total > 0 ? " · vinculado ao pagamento já realizado"
              : " · sem conta a pagar: lance em Contas a pagar"}
            {" "}<a href={r.financeiro?.link_contas_a_pagar || "/financeiro"} className="lnk" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Ver contas a pagar</a>.
          </li>
          {ap.ciencia_itens.length > 0 && <li>Ciência de {ap.ciencia_itens.length} {plural(ap.ciencia_itens.length, "item pendente", "itens pendentes")} gravada com o seu nome e a hora.</li>}
          <li>Foi para <b>Concluídos</b>{ap.excecoes.length ? `, com selo de exceção: ${ap.excecoes.join("; ")}` : ""}.</li>
        </ul>}
        {r.avisos.map((a) => <p key={a} role="alert" style={{ color: "var(--amber)", fontSize: "0.82rem", marginTop: "0.4rem", display: "flex", gap: 6 }}><AlertTriangle size={14} style={{ flexShrink: 0, marginTop: 2 }} />{a}</p>)}
      </div>
      {nao.length > 0 && (
        <div className="card">
          <div className="card-header mb-2">{nao.length} {plural(nao.length, "animal não foi aplicado", "animais não foram aplicados")}</div>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            {nao.map((n) => (
              <li key={n.numero_matriz} style={{ display: "flex", gap: "0.6rem", padding: "0.35rem 0", borderBottom: "1px solid var(--border)", fontSize: "0.85rem" }}>
                <b style={{ flex: 1 }}>{n.numero_matriz}<span style={{ ...notaStyle, display: "block", fontWeight: 400 }}>{n.motivo_nao}</span></b>
                <span style={notaStyle}>{n.destino_nao === "naoSeAplica" ? "Desconsiderado" : "Voltou à lista de espera"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {fase && fase !== "inoculacao" && <BannerReagentes aplicacaoId={ap.id} recarga={recargaBanner} onMudou={() => setRecargaBanner((n) => n + 1)} />}
      {erro && <p role="alert" style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
      <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
        {fase && fase !== "inoculacao" && (
          <button type="button" className="btn-secondary" data-testid="abrir-comprovante" onClick={() => setComprovante(true)}
                  disabled={ap.animais.filter((a) => a.resultado === "aplicado").length > 0 && ap.animais.filter((a) => a.resultado === "aplicado").every((a) => a.exame_resultado === "reagente")}
                  title={ap.animais.filter((a) => a.resultado === "aplicado").every((a) => a.exame_resultado === "reagente") ? "Bloqueado: todos os animais são reagentes." : undefined}>
            <Printer size={14} /> Comprovante
          </button>
        )}
        {canal === "Protocolos" && onVerConcluidos && <button type="button" className="btn-primary-gold" onClick={() => { onFechar(); onVerConcluidos(); }}>Ver em Concluídos</button>}
        {restante > 0 && ap.pode_desfazer && (
          <button type="button" className="btn-secondary" disabled={desfazendo} onClick={desfazer}>
            <Undo2 size={14} /> Desfazer ({restante} s)
          </button>
        )}
        <button type="button" className="btn-ghost" onClick={onFechar}>{canal === "Agenda" ? "Voltar à Agenda" : "Voltar ao Acompanhamento"}</button>
      </div>
      {restante <= 0 && <p style={notaStyle}>{fase === "inoculacao"
        ? "Depois de 10 segundos, corrigir a inoculação só pelo administrador, com motivo (antes de registrar a leitura)."
        : "Depois de 10 segundos, corrigir só pelo administrador, em Concluídos › Estornar, com motivo."}</p>}
      {comprovante && <ComprovanteAplicacaoView aplicacaoId={ap.id} onFechar={() => setComprovante(false)} />}
    </div>
  );
}

/** "O que o sistema fez sozinho" do exame: inoculação (estoque, leitura marcada) ou leitura/coleta (resultado, reagente, reteste). */
function ListaExame({ r }: { ctx: ContextoAplicar; r: ResultadoAplicar }) {
  const ap = r.aplicacao;
  const lidos = ap.animais.filter((a) => a.resultado === "aplicado");
  const conta = (x: string) => lidos.filter((a) => a.exame_resultado === x).length;
  const retestes = lidos.filter((a) => a.reteste_em).map((a) => a.reteste_em as string).sort();
  const custoTxt = ap.custo != null ? brl(ap.custo) : "a informar";
  return (
    <ul style={{ margin: 0, paddingLeft: "1.1rem", fontSize: "0.86rem", lineHeight: 1.7 }}>
      {ap.fase === "inoculacao" && <>
        <li>Inoculação registrada em {lidos.length} {plural(lidos.length, "animal", "animais")}{ap.tipo_teste ? ` (${ap.tipo_teste})` : ""}.</li>
        <li>{ap.estoque_desconsiderado ? `Estoque desconsiderado (${ap.estoque_motivo}): nada foi baixado.` : ap.dose_total ? `Estoque baixado: ${num(ap.dose_total)} ${unPl(ap.unidade || "", ap.dose_total || 0)}${ap.lote_texto ? ` do lote ${ap.lote_texto}` : ""}.` : "Sem produto no estoque."}</li>
        <li><b>Leitura marcada para {dataHoraLocal(ap.leitura_prevista_em)}</b> (72 h) — vai para a Agenda e para o Acompanhamento; janela até {dataHoraLocal(ap.leitura_limite_em)}.</li>
      </>}
      {ap.fase === "leitura" && <>
        <li>Resultado: {conta("negativo")} {plural(conta("negativo"), "negativo", "negativos")} · {conta("reagente")} {plural(conta("reagente"), "reagente", "reagentes")} · {conta("inconclusivo")} {plural(conta("inconclusivo"), "inconclusivo", "inconclusivos")}. Cada resultado virou uma linha em Sanidade › Exames.</li>
        <li>Leitura {horasTxtLocal(ap.leitura_horas)} após a inoculação{ap.leitura_fora_janela ? " — fora da janela de 72–96 h (fica sinalizado)" : ""}; tipo de teste {ap.tipo_teste || "—"}{ap.laudo ? ` · laudo ${ap.laudo}` : " · laudo não informado"}.</li>
        {conta("reagente") > 0 && <li style={{ color: "var(--red)" }}><b>{conta("reagente")} {plural(conta("reagente"), "reagente", "reagentes")}:</b> saiu dos demais agendamentos (ex.: aftosa), ficou “a descartar” e o aviso abaixo continua até sair do rebanho. Registre a notificação ao serviço veterinário oficial.</li>}
        {retestes.length > 0 && <li>Reteste dos inconclusivos em {dataCurta(retestes[0])} (60 dias): entra na lista de espera nessa data.</li>}
      </>}
      {ap.fase === "coleta" && <>
        <li>Coleta registrada em {lidos.length} {plural(lidos.length, "animal", "animais")}{ap.laudo ? ` · laudo ${ap.laudo}` : ""}.</li>
        {conta("coletado") > 0 && <li>{conta("coletado")} {plural(conta("coletado"), "animal", "animais")} aguardando o resultado do laboratório.</li>}
        {conta("negativo") + conta("reagente") + conta("inconclusivo") > 0 && <li>Resultado: {conta("negativo")} negativos · {conta("reagente")} reagentes · {conta("inconclusivo")} inconclusivos.</li>}
      </>}
      <li>
        <b>Custo:</b> {ap.custo != null ? custoTxt : <b style={{ color: "var(--amber)" }}>a informar</b>}
        {r.financeiro && r.financeiro.contas_ativas > 0 ? ` · conta a pagar lançada: ${brl(r.financeiro.conta_a_pagar_total)}` : ""}
        {" "}<a href={r.financeiro?.link_contas_a_pagar || "/financeiro"} className="lnk" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Ver contas a pagar</a>.
      </li>
      <li>Registrado por {ap.aplicador_nome ? `${ap.aplicador_nome}${ap.aplicador_crmv ? ` (${ap.aplicador_crmv})` : ""}` : "—"} pelo canal {ap.canal}.</li>
      {ap.fase !== "inoculacao" && <li>Foi para <b>Concluídos</b> como <b>Exame realizado</b>{ap.excecoes.length ? `, com selo de exceção: ${ap.excecoes.join("; ")}` : ""}.</li>}
      {ap.fase === "inoculacao" && ap.excecoes.length > 0 && <li>Exceções: {ap.excecoes.join("; ")}.</li>}
    </ul>
  );
}
const horasTxtLocal = (h: number | null | undefined) => (h == null ? "—" : `${Math.round(h)} h`);
