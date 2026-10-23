"use client";
// Sub-tela Produção: BST — histórico de aplicações (só leitura), mais recente
// primeiro. As tabelas de aptas/incluir no próximo/inaptas já aparecem no
// cartão do dia na Agenda; aplicar, agendar ou marcar inapta continua em
// Lançar > Produção > BST.
//
// Filtros no SERVIDOR (espec de Produção, out/2026): período (padrão 60 dias),
// rebanho todo / lote(s) NO DIA da aplicação / animal(is) exatos, faixa de DEL
// NO DIA DA APLICAÇÃO (a linha mostra também o DEL de hoje) e origem — a
// rotina de BST ou um curativo da Sanidade com produto BST (marcado "Sanidade").
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchRelatorioBst, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, ErroCarga } from "@/components/mobile/menu/comum";
import {
  AvisoCopiaOutroFiltro, ListaPorLote, LoteNaData, OpcoesFiltro, PainelFiltros, agruparPorLote, fmtNum, textoLote,
  useFiltrosProducao,
} from "@/components/mobile/menu/FiltrosProducao";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

const CHAVE = "menu_producao_bst";

type AplicacaoBst = {
  numero_matriz: string; data_aplicacao: string | null; produto: string; dose: number | null;
  unidade: string | null; responsavel: string | null; lote: string | null; categoria: string | null;
  lote_fonte?: string | null; del_aplicacao?: number | null; del_hoje?: number | null; origem?: string | null;
};
type Origem = "" | "rotina" | "sanidade";
const OPCOES_ORIGEM: { v: Origem; l: string }[] = [
  { v: "", l: "Todas" }, { v: "rotina", l: "Rotina BST" }, { v: "sanidade", l: "Sanidade" },
];

const COLUNAS_EXPORT: ColunaExport[] = [
  { header: "Animal", key: "numero_matriz", width: 10 },
  { header: "Data", key: "data_br", width: 12 },
  { header: "Lote na data", key: "lote_txt", width: 24 },
  { header: "DEL na aplicação", key: "del_aplicacao", width: 10, numerico: true },
  { header: "DEL hoje", key: "del_hoje", width: 9, numerico: true },
  { header: "Produto", key: "produto", width: 18 },
  { header: "Dose", key: "dose_txt", width: 10 },
  { header: "Origem", key: "origem", width: 12 },
  { header: "Responsável", key: "responsavel", width: 16 },
];
const COLUNAS_RESUMO: ColunaExport[] = [
  { header: "Lote", key: "lote", width: 24 },
  { header: "Vacas", key: "vacas", width: 8, numerico: true },
  { header: "Aplicações", key: "aplicacoes", width: 11, numerico: true },
  { header: "DEL médio na aplicação", key: "media", width: 14, numerico: true },
];

const rotuloLbl: React.CSSProperties = { display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" };

export default function BstHistorico({ onVoltar }: { onVoltar: () => void }) {
  const f = useFiltrosProducao();
  const [delMin, setDelMin] = useState("");
  const [delMax, setDelMax] = useState("");
  const [origem, setOrigem] = useState<Origem>("");
  const nMin = delMin === "" ? null : Number(delMin);
  const nMax = delMax === "" ? null : Number(delMax);
  const faixaInvalida = nMin != null && nMax != null && nMin > nMax;
  const filtros = { ...f.params, del_min: nMin, del_max: nMax, origem };
  const rotulo = [
    ...f.partesRotulo,
    nMin != null || nMax != null ? `DEL na aplicação: ${nMin ?? 0} a ${nMax ?? "sem limite"}` : null,
    `Origem: ${OPCOES_ORIGEM.find((o) => o.v === origem)?.l}`,
  ].filter(Boolean).join(" · ");
  const pronto = f.periodoValido && f.escopoPronto && !faixaInvalida;
  const { dados, doCache, carregando, mensagemErro, copiaDeOutroFiltro, recarregar } = useCarregar<{ aplicacoes: AplicacaoBst[] }>(
    CHAVE, () => fetchRelatorioBst(filtros), { assinatura: JSON.stringify(filtros), habilitado: pronto, rotulo },
  );

  const regs = useMemo(
    () => [...(dados?.aplicacoes ?? [])].sort((a, b) => ((a.data_aplicacao || "") < (b.data_aplicacao || "") ? 1 : -1)),
    [dados],
  );
  const vacasDistintas = useMemo(() => new Set(regs.map((r) => r.numero_matriz)).size, [regs]);
  const linhasExport = useMemo(() => regs.map((r) => ({
    ...r, data_br: r.data_aplicacao ? formatDate(r.data_aplicacao) : "", lote_txt: textoLote(r.lote, r.lote_fonte),
    dose_txt: r.dose != null ? `${r.dose} ${r.unidade || ""}`.trim() : "", del_aplicacao: r.del_aplicacao ?? "", del_hoje: r.del_hoje ?? "",
  })), [regs]);
  const resumo = useMemo(() => agruparPorLote(regs, (r) => r.lote, (r) => r.numero_matriz, (r) => r.del_aplicacao)
    .map((b) => ({ lote: b.lote, vacas: b.vacas, aplicacoes: b.linhas.length, media: b.media != null ? Math.round(b.media) : "" })), [regs]);

  return (
    <div>
      <MobVoltar titulo="BST — aplicações" onVoltar={onVoltar} />
      <AvisoCopia chave={CHAVE} mostrar={doCache} />

      <PainelFiltros f={f}>
        <div style={{ display: "flex", gap: "0.6rem", marginBottom: "0.7rem" }}>
          <label style={{ flex: 1 }}>
            <span style={rotuloLbl}>DEL na aplicação — de</span>
            <input className="mob-input" type="number" min={0} inputMode="numeric" value={delMin} placeholder="ex.: 60"
              onChange={(e) => setDelMin(e.target.value.replace(/\D/g, ""))} />
          </label>
          <label style={{ flex: 1 }}>
            <span style={rotuloLbl}>até</span>
            <input className="mob-input" type="number" min={0} inputMode="numeric" value={delMax} placeholder="ex.: 200"
              onChange={(e) => setDelMax(e.target.value.replace(/\D/g, ""))} />
          </label>
        </div>
        {faixaInvalida && (
          <p role="alert" style={{ margin: "-0.4rem 0 0.7rem", fontSize: "0.82rem", fontWeight: 700, color: "var(--mob-vermelho)" }}>
            O DEL mínimo é maior que o máximo — ajuste a faixa.
          </p>
        )}
        <OpcoesFiltro rotulo="Origem" opcoes={OPCOES_ORIGEM} valor={origem} onChange={setOrigem} />
      </PainelFiltros>

      {pronto && mensagemErro && <ErroCarga mensagem={`Não foi possível atualizar: ${mensagemErro}`} onTentar={recarregar} />}
      {pronto && copiaDeOutroFiltro && <AvisoCopiaOutroFiltro rotulo={dados?._rotuloFiltros} />}

      {!pronto ? null : carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : regs.length === 0 ? (
        <Vazio>Nenhuma aplicação no período/filtro.</Vazio>
      ) : (
        <>
          <MobCard style={{ marginBottom: "0.7rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--mob-muted)", fontWeight: 700 }}>{regs.length} {regs.length !== 1 ? "aplicações" : "aplicação"}</span>
            <span style={{ fontSize: "0.85rem", color: "var(--mob-muted)", fontWeight: 700 }}>{vacasDistintas} vaca{vacasDistintas !== 1 ? "s" : ""}</span>
          </MobCard>
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.6rem" }}>
            <ExportarBotoes titulo="BST — aplicações" colunas={COLUNAS_EXPORT} linhas={linhasExport} nomeArquivoBase="bst_aplicacoes"
              filtros={rotulo} resumo={{ titulo: "Resumo por lote (lote no dia da aplicação)", colunas: COLUNAS_RESUMO, linhas: resumo }} />
          </div>
          <ListaPorLote
            agrupar={f.agrupar} linhas={regs} loteDe={(r) => r.lote} numeroDe={(r) => r.numero_matriz} valorDe={(r) => r.del_aplicacao}
            detalheBloco={(b) => <>DEL médio {fmtNum(b.media, 0)}</>}
            render={(r, i) => (
              <MobCard key={`${r.numero_matriz}-${r.data_aplicacao}-${i}`} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Nº {r.numero_matriz}</span>
                  <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{r.data_aplicacao ? formatDate(r.data_aplicacao) : "—"}</span>
                </div>
                <div style={{ fontSize: "0.82rem", marginTop: "0.3rem", display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                  <span>{r.produto}{r.dose != null ? ` — ${r.dose} ${r.unidade || ""}` : ""}</span>
                  {r.origem === "Sanidade" && (
                    <span style={{ fontSize: "0.72rem", fontWeight: 800, color: "var(--mob-ambar)", whiteSpace: "nowrap" }}>Sanidade</span>
                  )}
                </div>
                <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                  DEL na aplicação {r.del_aplicacao ?? "—"} · DEL hoje {r.del_hoje ?? "—"}
                </div>
                <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                  <LoteNaData lote={r.lote} fonte={r.lote_fonte} />{r.responsavel ? ` · ${r.responsavel}` : ""}
                </div>
              </MobCard>
            )}
          />
        </>
      )}
    </div>
  );
}
