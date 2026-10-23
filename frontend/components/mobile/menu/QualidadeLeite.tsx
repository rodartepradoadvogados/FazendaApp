"use client";
// Sub-tela Produção: Qualidade do leite (só leitura), mais recente primeiro.
//
// Espec de Produção (out/2026): Tanque e Individual SEPARADOS (antes as duas
// coletas vinham misturadas na mesma lista); no Individual, filtro por vaca(s)
// ou lote(s) — lote da vaca NA DATA da coleta; indicadores CCS, CBT, gordura,
// proteína, sólidos, ESD, lactose e NUL. Sem bonificação (fica no site).
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchQualidadeLeite, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, ErroCarga } from "@/components/mobile/menu/comum";
import {
  AvisoCopiaOutroFiltro, ListaPorLote, LoteNaData, OpcoesFiltro, PainelFiltros, agruparPorLote, fmtNum, textoLote,
  useFiltrosProducao,
} from "@/components/mobile/menu/FiltrosProducao";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

const CHAVE = "menu_producao_qualidade";

type QualidadeRow = {
  numero_matriz: string | null; data_coleta: string; ccs: number | null; cbt: number | null;
  gordura_pct: number | null; proteina_pct: number | null; solidos_totais_pct: number | null; esd_pct: number | null;
  lactose_pct: number | null; nul: number | null; lote?: string | null; lote_fonte?: string | null;
};
type Tipo = "tanque" | "individual";

const INDICADORES: { key: keyof QualidadeRow; l: string; casas: number; sufixo?: string }[] = [
  { key: "ccs", l: "CCS", casas: 0 },
  { key: "cbt", l: "CBT", casas: 0 },
  { key: "gordura_pct", l: "Gordura", casas: 2, sufixo: "%" },
  { key: "proteina_pct", l: "Proteína", casas: 2, sufixo: "%" },
  { key: "solidos_totais_pct", l: "Sólidos", casas: 2, sufixo: "%" },
  { key: "esd_pct", l: "ESD", casas: 2, sufixo: "%" },
  { key: "lactose_pct", l: "Lactose", casas: 2, sufixo: "%" },
  { key: "nul", l: "NUL", casas: 1 },
];

const COLUNAS_BASE: ColunaExport[] = [
  { header: "Data", key: "data_br", width: 12 },
  { header: "CCS (mil/mL)", key: "ccs", width: 12, numerico: true },
  { header: "CBT (mil UFC/mL)", key: "cbt", width: 14, numerico: true },
  { header: "Gordura (%)", key: "gordura_pct", width: 11, numerico: true },
  { header: "Proteína (%)", key: "proteina_pct", width: 11, numerico: true },
  { header: "Sólidos (%)", key: "solidos_totais_pct", width: 11, numerico: true },
  { header: "ESD (%)", key: "esd_pct", width: 9, numerico: true },
  { header: "Lactose (%)", key: "lactose_pct", width: 11, numerico: true },
  { header: "NUL (mg/dL)", key: "nul", width: 11, numerico: true },
];
const COLUNAS_INDIVIDUAL: ColunaExport[] = [
  { header: "Animal", key: "numero_matriz", width: 10 }, { header: "Lote na data", key: "lote_txt", width: 24 }, ...COLUNAS_BASE,
];
const COLUNAS_RESUMO: ColunaExport[] = [
  { header: "Lote", key: "lote", width: 24 },
  { header: "Vacas", key: "vacas", width: 8, numerico: true },
  { header: "Coletas", key: "coletas", width: 9, numerico: true },
  { header: "CCS média", key: "media", width: 12, numerico: true },
];

export default function QualidadeLeite({ onVoltar }: { onVoltar: () => void }) {
  const f = useFiltrosProducao({ rotuloRebanho: "Todas as vacas" });
  const [tipo, setTipo] = useState<Tipo>("tanque");
  const individual = tipo === "individual";
  const filtros = individual ? { ...f.params, tipo } : { data_inicio: f.params.data_inicio, data_fim: f.params.data_fim, tipo };
  const rotulo = [
    individual ? f.partesRotulo.join(" · ") : f.partesRotulo[0],
    individual ? "Coletas individuais" : "Coletas do tanque",
  ].join(" · ");
  const { dados, doCache, carregando, mensagemErro, copiaDeOutroFiltro, recarregar } = useCarregar<{ registros: QualidadeRow[] }>(
    CHAVE, () => fetchQualidadeLeite(filtros),
    { assinatura: JSON.stringify(filtros), habilitado: f.periodoValido && (!individual || f.escopoPronto), rotulo },
  );

  const regs = useMemo(
    () => [...(dados?.registros ?? [])].sort((a, b) => (a.data_coleta < b.data_coleta ? 1 : -1)),
    [dados],
  );
  const linhasExport = useMemo(() => regs.map((r) => ({
    ...r, data_br: formatDate(r.data_coleta), lote_txt: textoLote(r.lote, r.lote_fonte),
  })), [regs]);
  const resumo = useMemo(() => individual
    ? agruparPorLote(regs, (r) => r.lote, (r) => r.numero_matriz || "", (r) => r.ccs)
      .map((b) => ({ lote: b.lote, vacas: b.vacas, coletas: b.linhas.length, media: b.media != null ? Math.round(b.media) : "" }))
    : [], [regs, individual]);

  const pronto = f.periodoValido && (!individual || f.escopoPronto);

  return (
    <div>
      <MobVoltar titulo="Qualidade do leite" onVoltar={onVoltar} />
      <AvisoCopia chave={CHAVE} mostrar={doCache} />

      <PainelFiltros f={f} rotuloRebanho="Todas" mostrarEscopo={individual}>
        <OpcoesFiltro rotulo="Coleta" valor={tipo} onChange={setTipo}
          opcoes={[{ v: "tanque", l: "Tanque" }, { v: "individual", l: "Individual (por vaca)" }]} />
      </PainelFiltros>

      {pronto && mensagemErro && <ErroCarga mensagem={`Não foi possível atualizar: ${mensagemErro}`} onTentar={recarregar} />}
      {pronto && copiaDeOutroFiltro && <AvisoCopiaOutroFiltro rotulo={dados?._rotuloFiltros} />}

      {!pronto ? null : carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : regs.length === 0 ? (
        <Vazio>Nenhuma coleta {individual ? "individual" : "do tanque"} no período/filtro.</Vazio>
      ) : (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem", marginBottom: "0.6rem" }}>
            <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", margin: 0 }}>{regs.length} coleta{regs.length !== 1 ? "s" : ""}</p>
            <ExportarBotoes titulo={`Qualidade do leite — ${individual ? "individual" : "tanque"}`}
              colunas={individual ? COLUNAS_INDIVIDUAL : COLUNAS_BASE} linhas={linhasExport} nomeArquivoBase={`qualidade_leite_${tipo}`}
              filtros={rotulo} resumo={individual ? { titulo: "Resumo por lote (lote na data da coleta)", colunas: COLUNAS_RESUMO, linhas: resumo } : undefined} />
          </div>
          <ListaPorLote
            agrupar={individual && f.agrupar} linhas={regs} loteDe={(r) => r.lote} numeroDe={(r) => r.numero_matriz || ""}
            valorDe={(r) => r.ccs} detalheBloco={(b) => <>CCS média {fmtNum(b.media, 0)}</>}
            render={(r, i) => (
              <MobCard key={`${r.numero_matriz || "tanque"}-${r.data_coleta}-${i}`} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>{r.numero_matriz ? `Nº ${r.numero_matriz}` : "Tanque"}</span>
                  <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{formatDate(r.data_coleta)}</span>
                </div>
                {r.numero_matriz && (
                  <div style={{ fontSize: "0.76rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>
                    <LoteNaData lote={r.lote} fonte={r.lote_fonte} />
                  </div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: "0.35rem 0.6rem", marginTop: "0.4rem", fontSize: "0.8rem" }}>
                  {INDICADORES.map((ind) => {
                    const v = r[ind.key] as number | null;
                    return (
                      <span key={ind.key}>
                        <span style={{ color: "var(--mob-muted)" }}>{ind.l}</span><br />
                        <strong>{v == null ? "—" : `${fmtNum(v, ind.casas)}${ind.sufixo ?? ""}`}</strong>
                      </span>
                    );
                  })}
                </div>
              </MobCard>
            )}
          />
        </>
      )}
    </div>
  );
}
