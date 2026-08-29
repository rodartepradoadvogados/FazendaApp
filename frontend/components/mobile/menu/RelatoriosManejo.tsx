"use client";
// Sub-tela: Relatórios de Manejo (só leitura). Abas em pílula, uma por lista
// semaforizada (o que fazer). Cada aba mostra animal + motivo + cor do semáforo.
// Só as listas de manejo — sem os relatórios gerenciais com gráficos.
// Exportação Excel/PDF da aba atual — mesmas colunas/nome de arquivo da versão
// site (components/RelatoriosManejo.tsx), ver EXPORT_CONFIG abaixo.
import { useState } from "react";
import { MobVoltar } from "@/components/mobile/ui";
import { fetchRelatoriosManejo, formatDate } from "@/lib/api";
import { useCarregar, AvisoCopia, Carregando, Vazio, Bolinha, NumAnimal } from "@/components/mobile/menu/comum";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

type Item = {
  numero: string; grupo?: string | null; cor?: string | null;
  dias_pos_parto?: number | null; dias_inseminada?: number | null; dias_gestacao?: number | null;
  dias_para_secagem?: number | null; dias_para_parto?: number | null; situacao?: string | null; touro?: string | null;
  // Campos usados só na exportação (mesma resposta de GET /relatorios/manejo
  // já consumida pela versão site — ver components/RelatoriosManejo.tsx).
  data_parto?: string | null; data_ultima_ia?: string | null; tipo?: string | null;
  dpp_concepcao?: number | null; previsao_parto?: string | null; reconfirmada?: boolean | null;
  previsao_secagem?: string | null;
};
type Resposta = Record<string, Item[]>;

// Colunas e nome de arquivo de exportação por aba — espelha exatamente a
// versão site (mesmos headers/ordem/nomeArquivoBase de cada BarraExport em
// components/RelatoriosManejo.tsx), para que o mesmo relatório baixado no
// site ou no app tenha sempre a mesma cara.
const EXPORT_CONFIG: Record<string, { colunas: ColunaExport[]; linha: (i: Item) => Record<string, unknown> }> = {
  pev: {
    colunas: [
      { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
      { header: "Dias pós-parto", key: "dias_pos_parto" }, { header: "Data do parto", key: "data_parto" },
    ],
    linha: (i) => ({ numero: i.numero, grupo: i.grupo, dias_pos_parto: i.dias_pos_parto, data_parto: formatDate(i.data_parto || "") }),
  },
  a_inseminar: {
    colunas: [
      { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
      { header: "Dias pós-parto", key: "dias_pos_parto" }, { header: "Situação", key: "situacao" },
    ],
    linha: (i) => ({ numero: i.numero, grupo: i.grupo, dias_pos_parto: i.dias_pos_parto, situacao: i.situacao }),
  },
  inseminados: {
    colunas: [
      { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
      { header: "Dias de inseminada", key: "dias_inseminada" }, { header: "Última IA/cobertura", key: "data_ultima_ia" },
      { header: "Touro", key: "touro" }, { header: "Tipo", key: "tipo" },
    ],
    linha: (i) => ({ numero: i.numero, grupo: i.grupo, dias_inseminada: i.dias_inseminada, data_ultima_ia: formatDate(i.data_ultima_ia || ""), touro: i.touro, tipo: i.tipo }),
  },
  a_tocar: {
    colunas: [
      { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
      { header: "Dias de inseminada", key: "dias_inseminada" }, { header: "Touro", key: "touro" },
    ],
    linha: (i) => ({ numero: i.numero, grupo: i.grupo, dias_inseminada: i.dias_inseminada, touro: i.touro }),
  },
  a_reconfirmar: {
    colunas: [
      { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" }, { header: "Dias", key: "dias_inseminada" },
    ],
    linha: (i) => ({ numero: i.numero, grupo: i.grupo, dias_inseminada: i.dias_inseminada }),
  },
  prenhes: {
    colunas: [
      { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
      { header: "Dias de gestação", key: "dias_gestacao" }, { header: "Dias pós-parto na concepção", key: "dpp_concepcao" },
      { header: "Previsão de parto", key: "previsao_parto" }, { header: "Reconfirmada", key: "reconfirmada" },
    ],
    linha: (i) => ({
      numero: i.numero, grupo: i.grupo, dias_gestacao: i.dias_gestacao, dpp_concepcao: i.dpp_concepcao,
      previsao_parto: formatDate(i.previsao_parto || ""), reconfirmada: i.reconfirmada ? "Sim" : "Não",
    }),
  },
  secagem: {
    colunas: [
      { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
      { header: "Dias para secagem", key: "dias_para_secagem" }, { header: "Previsão de secagem", key: "previsao_secagem" },
    ],
    linha: (i) => ({ numero: i.numero, grupo: i.grupo, dias_para_secagem: i.dias_para_secagem, previsao_secagem: formatDate(i.previsao_secagem || "") }),
  },
  previsao_partos: {
    colunas: [
      { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
      { header: "Dias para parir", key: "dias_para_parto" }, { header: "Previsão de parto", key: "previsao_parto" },
      { header: "Dias de gestação", key: "dias_gestacao" },
    ],
    linha: (i) => ({ numero: i.numero, grupo: i.grupo, dias_para_parto: i.dias_para_parto, previsao_parto: formatDate(i.previsao_parto || ""), dias_gestacao: i.dias_gestacao }),
  },
};

// As 8 listas de manejo (fazenda/rules/relatorios_gerenciais.py::relatorios_manejo).
const ABAS: { chave: string; rotulo: string; detalhe: (i: Item) => string }[] = [
  { chave: "pev", rotulo: "PEV", detalhe: (i) => (i.dias_pos_parto != null ? `${i.dias_pos_parto} dias pós-parto` : "no PEV") },
  { chave: "a_inseminar", rotulo: "A inseminar", detalhe: (i) => [i.situacao, i.dias_pos_parto != null ? `${i.dias_pos_parto} DPP` : null].filter(Boolean).join(" · ") || "a inseminar" },
  { chave: "inseminados", rotulo: "Inseminados", detalhe: (i) => [i.dias_inseminada != null ? `${i.dias_inseminada} dias inseminada` : null, i.touro].filter(Boolean).join(" · ") || "inseminada" },
  { chave: "a_tocar", rotulo: "A tocar", detalhe: (i) => (i.dias_inseminada != null ? `tocar · ${i.dias_inseminada} dias inseminada` : "tocar") },
  { chave: "a_reconfirmar", rotulo: "A reconfirmar", detalhe: (i) => (i.dias_inseminada != null ? `reconfirmar · ${i.dias_inseminada} dias` : "reconfirmar") },
  { chave: "prenhes", rotulo: "Prenhes", detalhe: (i) => (i.dias_gestacao != null ? `${i.dias_gestacao} dias de gestação` : "prenhe") },
  { chave: "secagem", rotulo: "Secagem", detalhe: (i) => (i.dias_para_secagem != null ? `secar em ${i.dias_para_secagem} dias` : "secar") },
  { chave: "previsao_partos", rotulo: "Partos", detalhe: (i) => (i.dias_para_parto != null ? `parir em ${i.dias_para_parto} dias` : "previsão de parto") },
];

export default function RelatoriosManejo({ onVoltar }: { onVoltar: () => void }) {
  const { dados, doCache, carregando } = useCarregar<Resposta>("menu_relatorios_manejo", fetchRelatoriosManejo);
  const [aba, setAba] = useState(ABAS[0].chave);

  const cfg = ABAS.find((a) => a.chave === aba) || ABAS[0];
  const itens = (dados?.[aba] as Item[] | undefined) || [];

  return (
    <div>
      <MobVoltar titulo="Relatórios de Manejo" onVoltar={onVoltar} />
      <AvisoCopia chave="menu_relatorios_manejo" mostrar={doCache} />

      {/* Abas roláveis — cada uma com a contagem da sua lista. */}
      <div style={{ display: "flex", gap: "0.5rem", overflowX: "auto", paddingBottom: "0.4rem", marginBottom: "0.8rem", WebkitOverflowScrolling: "touch" }}>
        {ABAS.map((a) => {
          const n = (dados?.[a.chave] as Item[] | undefined)?.length ?? 0;
          return (
            <button key={a.chave} type="button" className={`mob-pill${aba === a.chave ? " ativa" : ""}`}
              style={{ whiteSpace: "nowrap", flexShrink: 0, padding: "0.55rem 0.85rem" }} onClick={() => setAba(a.chave)}>
              {a.rotulo} {n > 0 ? `(${n})` : ""}
            </button>
          );
        })}
      </div>

      {dados && itens.length > 0 && (
        <div className="flex items-center justify-end mb-2">
          <ExportarBotoes
            titulo={`Relatórios de Manejo — ${cfg.rotulo}`}
            colunas={EXPORT_CONFIG[aba].colunas}
            linhas={itens.map((i) => EXPORT_CONFIG[aba].linha(i))}
            nomeArquivoBase={`manejo_${aba}`}
          />
        </div>
      )}

      {carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : itens.length === 0 ? (
        <Vazio>Nenhum animal nesta lista 🎉</Vazio>
      ) : (
        itens.map((i) => (
          <div key={i.numero} className="mob-card" style={{ padding: "0.7rem 1rem", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.7rem" }}>
            <Bolinha cor={i.cor} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <NumAnimal>Nº {i.numero}</NumAnimal>
              <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>
                {cfg.detalhe(i)}{i.grupo ? ` · ${i.grupo}` : ""}
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
