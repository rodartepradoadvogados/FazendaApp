"use client";
// Sub-tela Produção: Últimos controles leiteiros (só leitura) — mesmo dado do
// site (Produção > Produção leiteira). Lançar um controle novo continua em
// Lançar > Produção > Controle leiteiro.
//
// Filtros no SERVIDOR (espec de Produção, out/2026): período (padrão 60 dias),
// rebanho em lactação / lote(s) na data do controle / animal(is) exatos, e
// último / 2 / 3 / todos os controles por vaca (padrão: o último). Com lote(s),
// a lista sai em blocos por lote com nº de vacas e média no topo.
import { useMemo, useState } from "react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchControles, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, ErroCarga } from "@/components/mobile/menu/comum";
import {
  AvisoCopiaOutroFiltro, ListaPorLote, LoteNaData, OpcoesFiltro, PainelFiltros, agruparPorLote, fmtNum, textoLote,
  useFiltrosProducao,
} from "@/components/mobile/menu/FiltrosProducao";
import { useOrdenacao } from "@/components/Ordenavel";
import { SeletorOrdenacao, type CampoOrdenacao } from "@/components/mobile/SeletorOrdenacao";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

// Chave FIXA (só o último resultado fica no cache offline) — o Menu lê esta
// mesma chave para o subtítulo "x kg no último" (app/app/menu/page.tsx).
const CHAVE = "menu_producao_controles";

const CAMPOS_ORDENACAO: CampoOrdenacao[] = [
  { chave: "data", rotulo: "Data" },
  { chave: "numero", rotulo: "Animal" },
  { chave: "producao_kg", rotulo: "Produção (kg)" },
  { chave: "del", rotulo: "DEL" },
];

type ControleRow = {
  numero: string; data: string | null; producao_kg: number | null; del: number | null;
  ordenha1_kg: number | null; ordenha2_kg: number | null; ordenha3_kg: number | null; grupo_primario: string | null;
  lote?: string | null; lote_fonte?: string | null;
};

type Ultimos = "1" | "2" | "3" | "todos";
const OPCOES_ULTIMOS: { v: Ultimos; l: string }[] = [
  { v: "1", l: "Último" }, { v: "2", l: "2 últimos" }, { v: "3", l: "3 últimos" }, { v: "todos", l: "Todos" },
];

const COLUNAS_EXPORT: ColunaExport[] = [
  { header: "Animal", key: "numero", width: 10 },
  { header: "Data", key: "data_br", width: 12 },
  { header: "Lote na data", key: "lote_txt", width: 24 },
  { header: "Produção (kg)", key: "producao_kg", width: 14, numerico: true },
  { header: "DEL", key: "del", width: 8, numerico: true },
  { header: "1ª ordenha", key: "ordenha1_kg", width: 11, numerico: true },
  { header: "2ª ordenha", key: "ordenha2_kg", width: 11, numerico: true },
  { header: "3ª ordenha", key: "ordenha3_kg", width: 11, numerico: true },
];
const COLUNAS_RESUMO: ColunaExport[] = [
  { header: "Lote", key: "lote", width: 24 },
  { header: "Vacas", key: "vacas", width: 8, numerico: true },
  { header: "Controles", key: "controles", width: 10, numerico: true },
  { header: "Média (kg)", key: "media", width: 12, numerico: true },
];

export default function UltimosControles({ onVoltar }: { onVoltar: () => void }) {
  const f = useFiltrosProducao({ rotuloRebanho: "Rebanho em lactação" });
  const [ultimos, setUltimos] = useState<Ultimos>("1");
  const filtros = {
    ...f.params,
    rebanho_lactacao: f.escopo === "rebanho",
    ultimos: ultimos === "todos" ? null : Number(ultimos),
  };
  const rotulo = [...f.partesRotulo, `Mostrar: ${OPCOES_ULTIMOS.find((o) => o.v === ultimos)?.l.toLowerCase()} por vaca`].join(" · ");
  const { dados, doCache, carregando, mensagemErro, copiaDeOutroFiltro, recarregar } = useCarregar<{ controles: ControleRow[] }>(
    CHAVE, () => fetchControles(filtros),
    { assinatura: JSON.stringify(filtros), habilitado: f.periodoValido && f.escopoPronto, rotulo },
  );

  const regs = useMemo(() => dados?.controles ?? [], [dados]);
  const ord = useOrdenacao(regs);
  const linhas = ord.linhasOrdenadas;
  const vacas = useMemo(() => new Set(regs.map((r) => r.numero)).size, [regs]);
  const valores = regs.map((r) => r.producao_kg).filter((v): v is number => v != null);
  const media = valores.length ? valores.reduce((s, v) => s + v, 0) / valores.length : null;

  const linhasExport = useMemo(() => linhas.map((r) => ({
    ...r, data_br: r.data ? formatDate(r.data) : "", lote_txt: textoLote(r.lote, r.lote_fonte),
    producao_kg: r.producao_kg ?? "", del: r.del ?? "",
  })), [linhas]);
  const resumo = useMemo(() => agruparPorLote(regs, (r) => r.lote, (r) => r.numero, (r) => r.producao_kg)
    .map((b) => ({ lote: b.lote, vacas: b.vacas, controles: b.linhas.length, media: b.media != null ? Number(b.media.toFixed(1)) : "" })), [regs]);

  const pronto = f.periodoValido && f.escopoPronto;

  return (
    <div>
      <MobVoltar titulo="Últimos controles leiteiros" onVoltar={onVoltar} />
      <AvisoCopia chave={CHAVE} mostrar={doCache} />

      <PainelFiltros f={f} rotuloRebanho="Rebanho em lactação">
        <OpcoesFiltro rotulo="Controles por vaca" opcoes={OPCOES_ULTIMOS} valor={ultimos} onChange={setUltimos} />
      </PainelFiltros>

      {pronto && mensagemErro && <ErroCarga mensagem={`Não foi possível atualizar: ${mensagemErro}`} onTentar={recarregar} />}
      {pronto && copiaDeOutroFiltro && <AvisoCopiaOutroFiltro rotulo={dados?._rotuloFiltros} />}

      {!pronto ? null : carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : regs.length === 0 ? (
        <Vazio>Nenhum controle no período/filtro.</Vazio>
      ) : (
        <>
          <MobCard style={{ marginBottom: "0.7rem", display: "flex", justifyContent: "space-between", gap: "0.6rem", flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--mob-muted)", fontWeight: 700 }}>
              {vacas} {vacas !== 1 ? "vacas" : "vaca"} · {regs.length} controle{regs.length !== 1 ? "s" : ""}
            </span>
            <span style={{ fontSize: "0.9rem", fontWeight: 800, color: "var(--mob-verde)" }}>Média {fmtNum(media)} kg</span>
          </MobCard>
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.6rem" }}>
            <ExportarBotoes titulo="Controles leiteiros" colunas={COLUNAS_EXPORT} linhas={linhasExport} nomeArquivoBase="controles_leiteiros"
              filtros={rotulo} resumo={{ titulo: "Resumo por lote (lote na data do controle)", colunas: COLUNAS_RESUMO, linhas: resumo }} />
          </div>
          <SeletorOrdenacao campos={CAMPOS_ORDENACAO} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
          <ListaPorLote
            agrupar={f.agrupar} linhas={linhas} loteDe={(r) => r.lote} numeroDe={(r) => r.numero} valorDe={(r) => r.producao_kg}
            detalheBloco={(b) => <>média {fmtNum(b.media)} kg</>}
            render={(r, i) => {
              const ordenhas = [r.ordenha1_kg, r.ordenha2_kg, r.ordenha3_kg].filter((v) => v != null);
              return (
                <MobCard key={`${r.numero}-${r.data}-${i}`} alt={(i % 2) as 0 | 1} style={{ marginBottom: "0.5rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.6rem" }}>
                    <span style={{ fontWeight: 800, fontSize: "1.02rem" }}>Nº {r.numero}</span>
                    <strong style={{ color: "var(--mob-verde)", fontSize: "0.95rem" }}>{fmtNum(r.producao_kg)} kg</strong>
                  </div>
                  <div style={{ fontSize: "0.78rem", color: "var(--mob-muted)", marginTop: "0.25rem", display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
                    <span>{r.data ? formatDate(r.data) : "—"} · <LoteNaData lote={r.lote ?? r.grupo_primario} fonte={r.lote_fonte} /></span>
                    <span>DEL {r.del ?? "—"}</span>
                  </div>
                  {ordenhas.length > 1 && (
                    <div style={{ fontSize: "0.74rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>
                      Ordenhas: {ordenhas.map((v) => fmtNum(v)).join(" + ")}
                    </div>
                  )}
                </MobCard>
              );
            }}
          />
        </>
      )}
    </div>
  );
}
