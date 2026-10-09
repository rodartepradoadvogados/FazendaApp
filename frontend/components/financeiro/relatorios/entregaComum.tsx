"use client";
// Peças comuns às telas de Entrega ao contador (Fase C5) — também usadas fora
// dos Relatórios: a lista do pacote vai para o Painel do Contador (/contador) e
// o selo do mês vai para o Resumo do Financeiro.
import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Download, FileText, LoaderCircle, Lock, LockOpen } from "lucide-react";
import {
  baixarPacoteContador, fetchMesesFechamento, type ItemPacote, type MesResumo,
} from "@/lib/fechamentoApi";
import { lerContexto, periodoDe, type EstadoContexto } from "@/lib/relatorioContexto";
import { mesDoPeriodo, nomeMes } from "@/lib/relatorioFechamento";
import { useContextoRelatorio, type TravasContexto } from "./useContextoRelatorio";

/** Contexto das telas que são sempre de UM mês (Fechamento, Conciliação): se a URL
 *  traz outro tipo de período (ex.: o ano do Pacote), a barra mostra o último mês
 *  fechável dele — sem reescrever a URL, para o Voltar continuar valendo. */
export function useContextoMensal(padrao: EstadoContexto, hoje: string, travasBase: Omit<TravasContexto, "per" | "perSugerido" | "tiposPeriodo">) {
  const forcarDe = (per: string) => (per.startsWith("m:") ? undefined : `m:${mesDoPeriodo(periodoDe(per) ?? periodoDe(padrao.per)!, hoje)}`);
  // O `per` da URL visto por último (estado, não ref: ajustado durante o render, padrão do React).
  const [perVisto, setPerVisto] = useState<string>(() =>
    typeof window === "undefined" ? padrao.per : lerContexto(window.location.search, padrao).per);
  // perSugerido (não `per`): o mês sugerido não trava a barra — a pessoa troca o mês (integração da Fase C).
  const travas: TravasContexto = { ...travasBase, tiposPeriodo: ["m"], perSugerido: forcarDe(perVisto) };
  const ctx = useContextoRelatorio(padrao, travas);
  if (ctx.estado.per !== perVisto) setPerVisto(ctx.estado.per);
  return ctx;
}

export type TomPill = "ok" | "aten" | "info" | "neu" | "ruim";
const CLASSE_PILL: Record<TomPill, string> = { ok: "pago", aten: "logo", info: "aberto", neu: "", ruim: "venc" };

/** Pílula de status: SEMPRE ícone + palavra (nunca só cor). */
export function Pill({ tom, children, icone }: { tom: TomPill; children: ReactNode; icone?: ReactNode }) {
  const ic = icone ?? (tom === "ok" ? <CheckCircle2 size={12} aria-hidden /> : tom === "aten" || tom === "ruim" ? <AlertTriangle size={12} aria-hidden /> : null);
  return <span className={`st-pill ce-pill ${CLASSE_PILL[tom]}`}>{ic}{children}</span>;
}

/** A lista "O que vai no pacote" com os botões de baixar (Relatórios e Painel do Contador). */
export function ListaPacote({ itens, inicio, fim, extraAcoes }: { itens: ItemPacote[]; inicio: string; fim: string; extraAcoes?: ReactNode }) {
  const [gerando, setGerando] = useState<"zip" | "pdf" | null>(null);
  const [feito, setFeito] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const baixar = async (formato: "zip" | "pdf") => {
    setGerando(formato); setErro(null); setFeito(null);
    try { setFeito(await baixarPacoteContador(inicio, fim, formato)); } catch (e) { setErro((e as Error).message); } finally { setGerando(null); }
  };
  const pend = itens.filter((i) => !i.ok).length;
  return (<>
    <ul className="ce-lst" aria-label="Arquivos do pacote">
      {itens.map((i) => (
        <li key={i.id}>
          <span className={`ce-ic ${i.ok ? "ok" : "aten"}`}>{i.ok ? <CheckCircle2 size={18} aria-hidden /> : <AlertTriangle size={18} aria-hidden />}</span>
          <div><b>{i.nome}</b><small>{i.formato} · {i.detalhe}</small></div>
          <Pill tom={i.ok ? "ok" : "aten"} icone={null}>{i.ok ? "pronto" : "pendência"}</Pill>
        </li>
      ))}
    </ul>
    <div className="ce-acts">
      <button type="button" className="ce-btn-pri" onClick={() => baixar("zip")} disabled={gerando !== null} aria-busy={gerando === "zip"}>
        {gerando === "zip" ? <LoaderCircle size={16} className="ce-gira" aria-hidden /> : <Download size={16} aria-hidden />}
        {gerando === "zip" ? "Gerando o pacote…" : "Baixar o pacote (ZIP: PDF + Excel + CSV)"}
      </button>
      <button type="button" className="ce-btn" onClick={() => baixar("pdf")} disabled={gerando !== null} aria-busy={gerando === "pdf"}>
        {gerando === "pdf" ? <LoaderCircle size={14} className="ce-gira" aria-hidden /> : <FileText size={14} aria-hidden />} Só o PDF
      </button>
      {extraAcoes}
    </div>
    <div aria-live="polite">
      {feito && (
        <div className="ce-ok" role="status" style={{ marginTop: ".7rem" }}>
          <CheckCircle2 size={18} aria-hidden />
          <div><b>{feito} baixado</b>
            <p>Cabeçalho com a fazenda, o período e quem gerou em todos os arquivos; números reais nas planilhas.{pend ? " As pendências seguem junto (pendencias.csv e LEIA-ME.txt), para o contador saber o que falta." : ""}</p>
          </div>
        </div>
      )}
      {erro && <p className="ce-erro" role="alert" style={{ marginTop: ".6rem" }}>{erro}</p>}
    </div>
  </>);
}

/** Selo discreto do mês anterior (aberto/fechado) — Resumo do Financeiro. Só com as regras novas. */
export function SeloEstadoMes({ hoje }: { hoje: string }) {
  const [mes, setMes] = useState<MesResumo | null>(null);
  useEffect(() => {
    let vivo = true;
    fetchMesesFechamento(undefined, 2).then((r) => {
      if (!vivo || !r.regras_v2) return;
      const anterior = r.meses.find((m) => m.status !== "em_curso" && m.mes < hoje.slice(0, 7));
      setMes(anterior ?? null);
    }).catch(() => { /* selo é opcional: sem ele, nada muda */ });
    return () => { vivo = false; };
  }, [hoje]);
  if (!mes) return null;
  const fechado = mes.status === "fechado";
  return (
    <a href={`/financeiro?sub=fechamento_mes&per=m:${mes.mes}`} className="st-pill" style={{ textDecoration: "none" }}
      title={fechado ? "Mês fechado: alterar exige reabrir com motivo" : "Mês ainda aberto: confira e feche em Relatórios › Fechamento do mês"}>
      {fechado ? <Lock size={12} aria-hidden /> : <LockOpen size={12} aria-hidden />}
      {nomeMes(mes.mes)} {fechado ? "fechado" : "aberto"}
    </a>
  );
}
