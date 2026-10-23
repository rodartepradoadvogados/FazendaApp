"use client";
// Sub-tela Produção: Secagens (só leitura) — histórico de secagens, mais
// recente primeiro. Lançar uma nova secagem continua em Lançar > Produção > Secagem.
//
// Filtros no SERVIDOR (espec de Produção, out/2026): período (padrão 60 dias),
// animal(is) exatos, lote(s) — o lote em que a vaca estava ao ser SECA (o
// movimento para o lote de secas no mesmo dia não conta) — e motivo(s).
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchSecagensHistorico, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, ErroCarga } from "@/components/mobile/menu/comum";
import {
  AvisoCopiaOutroFiltro, ListaPorLote, LoteNaData, PainelFiltros, agruparPorLote, textoLote, useFiltrosProducao,
} from "@/components/mobile/menu/FiltrosProducao";
import { MOTIVOS_SECAGEM } from "@/components/lancamentos/comumForms";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

const CHAVE = "menu_producao_secagens";

type SecagemRow = {
  numero: string; data: string | null; motivo: string; escore_condicao_corporal: number | null; observacao: string | null;
  lote?: string | null; lote_fonte?: string | null;
};

const LABEL_MOTIVO: Record<string, string> = Object.fromEntries(MOTIVOS_SECAGEM.map((m) => [m.v, m.l]));

const COLUNAS_EXPORT: ColunaExport[] = [
  { header: "Animal", key: "numero", width: 10 },
  { header: "Data", key: "data_br", width: 12 },
  { header: "Lote ao secar", key: "lote_txt", width: 24 },
  { header: "Motivo", key: "motivo_txt", width: 18 },
  { header: "ECC", key: "escore_condicao_corporal", width: 8, numerico: true },
  { header: "Observação", key: "observacao", width: 30 },
];
const COLUNAS_RESUMO: ColunaExport[] = [
  { header: "Lote", key: "lote", width: 24 },
  { header: "Vacas", key: "vacas", width: 8, numerico: true },
  { header: "Secagens", key: "secagens", width: 10, numerico: true },
];

export default function Secagens({ onVoltar }: { onVoltar: () => void }) {
  const f = useFiltrosProducao();
  const [motivos, setMotivos] = useState<string[]>([]);
  const filtros = { ...f.params, motivos: motivos.length ? [...motivos].sort() : undefined };
  const rotulo = [
    ...f.partesRotulo,
    `Motivo: ${motivos.length ? motivos.map((m) => LABEL_MOTIVO[m] || m).join(", ") : "todos"}`,
  ].join(" · ");
  const { dados, doCache, carregando, mensagemErro, copiaDeOutroFiltro, recarregar } = useCarregar<{ secagens: SecagemRow[] }>(
    CHAVE, () => fetchSecagensHistorico(filtros),
    { assinatura: JSON.stringify(filtros), habilitado: f.periodoValido && f.escopoPronto, rotulo },
  );

  const regs = useMemo(
    () => [...(dados?.secagens ?? [])].sort((a, b) => ((a.data || "") < (b.data || "") ? 1 : -1)),
    [dados],
  );
  const linhasExport = useMemo(() => regs.map((r) => ({
    ...r, data_br: r.data ? formatDate(r.data) : "", lote_txt: textoLote(r.lote, r.lote_fonte),
    motivo_txt: LABEL_MOTIVO[r.motivo] || r.motivo,
  })), [regs]);
  const resumo = useMemo(() => agruparPorLote(regs, (r) => r.lote, (r) => r.numero)
    .map((b) => ({ lote: b.lote, vacas: b.vacas, secagens: b.linhas.length })), [regs]);
  const pronto = f.periodoValido && f.escopoPronto;

  return (
    <div>
      <MobVoltar titulo="Secagens" onVoltar={onVoltar} />
      <AvisoCopia chave={CHAVE} mostrar={doCache} />

      <PainelFiltros f={f}>
        <span style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" }}>Motivo</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginBottom: "0.7rem" }}>
          {MOTIVOS_SECAGEM.map((m) => {
            const ativo = motivos.includes(m.v);
            return (
              <button key={m.v} type="button" className={`mob-pill${ativo ? " ativa" : ""}`} aria-pressed={ativo}
                onClick={() => setMotivos((p) => (ativo ? p.filter((x) => x !== m.v) : [...p, m.v]))}>{m.l}</button>
            );
          })}
        </div>
      </PainelFiltros>

      {pronto && mensagemErro && <ErroCarga mensagem={`Não foi possível atualizar: ${mensagemErro}`} onTentar={recarregar} />}
      {pronto && copiaDeOutroFiltro && <AvisoCopiaOutroFiltro rotulo={dados?._rotuloFiltros} />}

      {!pronto ? null : carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : regs.length === 0 ? (
        <Vazio>Nenhuma secagem no período/filtro.</Vazio>
      ) : (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem", marginBottom: "0.6rem" }}>
            <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", margin: 0 }}>{regs.length} {regs.length !== 1 ? "secagens" : "secagem"}</p>
            <ExportarBotoes titulo="Secagens" colunas={COLUNAS_EXPORT} linhas={linhasExport} nomeArquivoBase="secagens"
              filtros={rotulo} resumo={{ titulo: "Resumo por lote (lote em que a vaca estava ao ser seca)", colunas: COLUNAS_RESUMO, linhas: resumo }} />
          </div>
          <ListaPorLote
            agrupar={f.agrupar} linhas={regs} loteDe={(r) => r.lote} numeroDe={(r) => r.numero}
            detalheBloco={(b) => <>{b.linhas.length} {b.linhas.length !== 1 ? "secagens" : "secagem"}</>}
            render={(r, i) => (
              <MobCard key={`${r.numero}-${r.data}-${i}`} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Nº {r.numero}</span>
                  <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{r.data ? formatDate(r.data) : "—"}</span>
                </div>
                <div style={{ fontSize: "0.82rem", marginTop: "0.3rem" }}>
                  {LABEL_MOTIVO[r.motivo] || r.motivo}
                  {r.escore_condicao_corporal != null ? ` · ECC ${r.escore_condicao_corporal}` : ""}
                </div>
                <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                  <LoteNaData lote={r.lote} fonte={r.lote_fonte} />
                </div>
                {r.observacao && <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>{r.observacao}</div>}
              </MobCard>
            )}
          />
        </>
      )}
    </div>
  );
}
