"use client";
// Sub-tela Produção: Pesagens — histórico de crescimento (GMD/GPD) por
// animal. Lançar uma pesagem nova continua em Lançar > Produção > Pesagem corporal.
//
// Filtros no SERVIDOR (espec de Produção, out/2026): período (padrão 60 dias),
// todos / lote(s) / animal(is) exatos. O lote escolhe QUAIS animais entram (os
// que estiveram nele no período) e o GMD usa TODAS as pesagens do animal no
// período — antes o filtro cortava as pesagens de quem mudou de lote.
// Correções: o cache era uma chave por período, nunca apagada (agora uma chave
// fixa, só o último resultado) e uma resposta antiga podia sobrescrever a nova
// ao trocar o período depressa (agora é descartada — ver useCarregar).
import { useEffect, useMemo } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchRelatorioPesagemCorporal, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, ErroCarga } from "@/components/mobile/menu/comum";
import {
  AvisoCopiaOutroFiltro, ListaPorLote, PainelFiltros, agruparPorLote, fmtNum, useFiltrosProducao,
} from "@/components/mobile/menu/FiltrosProducao";
import { useOrdenacao } from "@/components/Ordenavel";
import { SeletorOrdenacao, type CampoOrdenacao } from "@/components/mobile/SeletorOrdenacao";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

const CHAVE = "menu_producao_pesagens";

const CAMPOS_ORDENACAO: CampoOrdenacao[] = [
  { chave: "numero_matriz", rotulo: "Animal" },
  { chave: "gmd_kg_dia", rotulo: "GMD (kg/dia)" },
  { chave: "gpd_kg_dia", rotulo: "GPD (kg/dia)" },
  { chave: "ultima_data", rotulo: "Última pesagem" },
  { chave: "ultima_peso", rotulo: "Último peso" },
];

type LinhaPesagem = {
  numero_matriz: string; grupo_primario: string | null; lote?: string | null; lotes_no_periodo?: string[];
  primeira_data: string; primeira_peso: number; ultima_data: string; ultima_peso: number;
  gmd_kg_dia: number | null; gpd_kg_dia: number | null; num_pesagens: number;
};

const COLUNAS_EXPORT: ColunaExport[] = [
  { header: "Animal", key: "numero_matriz", width: 10 },
  { header: "Lote", key: "lote_txt", width: 24 },
  { header: "Lotes no período", key: "lotes_txt", width: 30 },
  { header: "1ª pesagem", key: "primeira_br", width: 12 },
  { header: "1º peso (kg)", key: "primeira_peso", width: 11, numerico: true },
  { header: "Última pesagem", key: "ultima_br", width: 13 },
  { header: "Último peso (kg)", key: "ultima_peso", width: 13, numerico: true },
  { header: "GMD (kg/dia)", key: "gmd_kg_dia", width: 12, numerico: true },
  { header: "GPD (kg/dia)", key: "gpd_kg_dia", width: 12, numerico: true },
  { header: "Pesagens", key: "num_pesagens", width: 9, numerico: true },
];
const COLUNAS_RESUMO: ColunaExport[] = [
  { header: "Lote", key: "lote", width: 24 },
  { header: "Animais", key: "vacas", width: 9, numerico: true },
  { header: "GMD médio (kg/dia)", key: "media", width: 16, numerico: true },
];

/** Faxina das cópias antigas (uma por período, nunca apagadas — "mob_cache_" é o prefixo de lib/offline.ts). */
function apagarCachesAntigos() {
  try {
    const antigas: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k && k.startsWith(`mob_cache_${CHAVE}_`)) antigas.push(k);
    }
    antigas.forEach((k) => localStorage.removeItem(k));
  } catch { /* sem localStorage — nada a limpar */ }
}

export default function PesagemHistorico({ onVoltar }: { onVoltar: () => void }) {
  useEffect(apagarCachesAntigos, []);
  const f = useFiltrosProducao();
  const rotulo = f.partesRotulo.join(" · ");
  const { dados, doCache, carregando, mensagemErro, copiaDeOutroFiltro, recarregar } = useCarregar<{ linhas: LinhaPesagem[] }>(
    CHAVE, () => fetchRelatorioPesagemCorporal(f.params),
    { assinatura: JSON.stringify(f.params), habilitado: f.periodoValido && f.escopoPronto, rotulo },
  );

  const linhas = useMemo(() => dados?.linhas ?? [], [dados]);
  const ord = useOrdenacao(linhas);
  const loteDe = (l: LinhaPesagem) => l.lote ?? l.grupo_primario;
  const linhasExport = useMemo(() => ord.linhasOrdenadas.map((l) => ({
    ...l, lote_txt: (l.lote ?? l.grupo_primario) || "Sem lote", lotes_txt: (l.lotes_no_periodo ?? []).join(", "),
    primeira_br: formatDate(l.primeira_data), ultima_br: formatDate(l.ultima_data),
    gmd_kg_dia: l.gmd_kg_dia ?? "", gpd_kg_dia: l.gpd_kg_dia ?? "",
  })), [ord.linhasOrdenadas]);
  const resumo = useMemo(() => agruparPorLote(linhas, (l) => l.lote ?? l.grupo_primario, (l) => l.numero_matriz, (l) => l.gmd_kg_dia)
    .map((b) => ({ lote: b.lote, vacas: b.vacas, media: b.media != null ? Number(b.media.toFixed(3)) : "" })), [linhas]);
  const pronto = f.periodoValido && f.escopoPronto;

  return (
    <div>
      <MobVoltar titulo="Pesagens" onVoltar={onVoltar} />
      <AvisoCopia chave={CHAVE} mostrar={doCache} />

      <PainelFiltros f={f} rotuloRebanho="Todos" />

      {pronto && mensagemErro && <ErroCarga mensagem={`Não foi possível atualizar: ${mensagemErro}`} onTentar={recarregar} />}
      {pronto && copiaDeOutroFiltro && <AvisoCopiaOutroFiltro rotulo={dados?._rotuloFiltros} />}

      {!pronto ? null : carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : linhas.length === 0 ? (
        <Vazio>Nenhuma pesagem no período/filtro.</Vazio>
      ) : (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem", marginBottom: "0.6rem" }}>
            <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", margin: 0 }}>{linhas.length} {linhas.length !== 1 ? "animais" : "animal"}</p>
            <ExportarBotoes titulo="Pesagens — GMD/GPD" colunas={COLUNAS_EXPORT} linhas={linhasExport} nomeArquivoBase="pesagens"
              filtros={rotulo} resumo={{ titulo: "Resumo por lote", colunas: COLUNAS_RESUMO, linhas: resumo }} />
          </div>
          <SeletorOrdenacao campos={CAMPOS_ORDENACAO} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ListaPorLote
            agrupar={f.agrupar} linhas={ord.linhasOrdenadas} loteDe={loteDe} numeroDe={(l) => l.numero_matriz} valorDe={(l) => l.gmd_kg_dia}
            detalheBloco={(b) => <>GMD médio {fmtNum(b.media, 3)} kg/dia</>}
            render={(l, i) => (
              <MobCard key={l.numero_matriz} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Nº {l.numero_matriz}</span>
                  <strong style={{ color: "var(--mob-verde)", fontSize: "0.95rem" }}>{l.gmd_kg_dia != null ? `${l.gmd_kg_dia} kg/dia` : "—"}</strong>
                </div>
                <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.25rem", display: "flex", justifyContent: "space-between" }}>
                  <span>{loteDe(l) ? `Lote ${loteDe(l)}` : "—"} · {l.num_pesagens} {l.num_pesagens !== 1 ? "pesagens" : "pesagem"}</span>
                  <span>GPD {l.gpd_kg_dia ?? "—"}</span>
                </div>
                {(l.lotes_no_periodo?.length ?? 0) > 1 && (
                  <div style={{ fontSize: "0.74rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>Passou por: {l.lotes_no_periodo!.join(", ")}</div>
                )}
                <div style={{ fontSize: "0.74rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                  {formatDate(l.primeira_data)} · {l.primeira_peso} kg → {formatDate(l.ultima_data)} · {l.ultima_peso} kg
                </div>
              </MobCard>
            )}
          />
        </>
      )}
    </div>
  );
}
