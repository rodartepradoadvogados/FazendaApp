"use client";
import { useEffect, useState } from "react";
import { FileText, AlertTriangle, Download, Pencil, Save, X } from "lucide-react";
import {
  fetchAnimais, fetchFichaAnimal, formatDate, atualizarAnimalFicha, registrarColostragem, fetchCategoriaSugerida,
  verificarMaeParto, type VerificacaoMaeParto, fetchEquivalenteMaduroDoAnimal, type TrioEquivalenteMaduro,
} from "@/lib/api";
import { exportarFichaPDF, SecaoFicha, ColunaExport } from "@/lib/export";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { SecaoRecolhivel, TabBar } from "@/components/ui";
import { estiloSexado, rotuloOrigemMovimentoLote } from "@/lib/constants";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { CampoMoeda } from "@/components/CampoMoeda";
import { CurvaLactacao, type FaixaReferencia, type PontoWood } from "@/components/CurvaLactacao";
import { TrioEquivalenteMaduroView, NotaExplicativaEM } from "@/components/TrioEquivalenteMaduro";

type PrecisaoParto = {
  data_ultima_ia_positiva: string | null;
  data_confirmacao_prenhez: string | null;
  dias_gestacao: number | null;
  data_parto_provavel: string | null;
  dias_para_parto: number | null;
};

type Ficha = {
  animal: Record<string, unknown>;
  pai: { nome: string | null; naab: string | null; central: string | null; tpi: number | null; nm_dolar: number | null } | null;
  precisao_parto: PrecisaoParto | null;
  partos: Record<string, unknown>[];
  // Quadro "por parto" — o que se quer ver "se fosse comprar este animal":
  // produção, duração, tentativas de emprenhar e DEL de concepção, por
  // lactação (mais antiga primeiro). Ver fazenda.rules.parto_resumo.
  resumo_partos: {
    ordem_parto: number; data_parto: string; lactacao_encerrada: boolean; dias_em_lactacao: number;
    producao_total_kg: number | null; producao_media_dia_kg: number | null;
    producao_305_dias_kg: number | null; producao_305_dias_estimada: boolean;
    tentativas_emprenhar: number | null; del_concepcao: number | null;
    // Número da cria DAQUELE parto — "S/N" se pariu mas não numerou, vazio
    // se natimorto (não confundir os dois). Ver fazenda.rules.parto_resumo.
    cria: string;
  }[];
  servicos: Record<string, unknown>[];
  protocolos_iatf: Record<string, unknown>[];
  movimentos_lote: Record<string, unknown>[];
  colostragem: Record<string, unknown> | null;
  controles_leiteiros: Record<string, unknown>[];
  pesagens_corporais: Record<string, unknown>[];
  qualidade_leite: Record<string, unknown>[];
  aplicacoes_sanitarias: Record<string, unknown>[];
  protocolos_sanitarios: Record<string, unknown>[];
  inducao_lactacao: Record<string, unknown>[];
  protocolos_customizados: Record<string, unknown>[];
  secagens: Record<string, unknown>[];
  eventos_agenda: Record<string, unknown>[];
  baixa: Record<string, unknown> | null;
  compra: Record<string, unknown> | null;
  compras: Record<string, unknown>[];
  vendas: Record<string, unknown>[];
  gtas: string[];
  ocorrencias_clinicas: Record<string, unknown>[];
  exames_resultados: Record<string, unknown>[];
  linha_tempo_sanitaria: { data: string | null; tipo_evento: string; descricao: string | null; gta: string | null; responsavel: string | null }[];
  // Média do rebanho por faixa de DEL — a linha de referência que a curva de
  // lactação desenha por trás dos pontos deste animal.
  curva_referencia_rebanho?: FaixaReferencia[];
  // Número da cria do ÚLTIMO parto do animal — "S/N" se pariu sem numerar a
  // cria, vazio ("") se o último parto foi natimorto (aborto nunca vira o
  // "último parto" aqui, já é filtrado antes). Ver fazenda.rules.parto_resumo
  // e o campo `cria` de cada linha de `resumo_partos`.
  ultima_cria: string;
  // Curva de Wood ajustada aos pontos reais DESTE animal (trajetória
  // esperada + projeção da cauda em aberto) — null sem controle suficiente.
  curva_wood?: PontoWood[] | null;
  // Mesma ideia de curva_referencia_rebanho, mas só com vacas na MESMA
  // ordem de parto deste animal — null se ele nunca pariu ou não há grupo.
  curva_referencia_grupo_ordem_parto?: FaixaReferencia[] | null;
};

/**
 * Quadro "por parto" — o que se quer ver "se fosse comprar este animal":
 * produção, duração e reprodução de cada lactação, lado a lado. Mais
 * antiga primeiro (mesma ordem de `ficha.resumo_partos`).
 */
// Número da cria (o filhote, não a ordem de parto da mãe) — itálico "sem
// dados" tanto pra quando não há número nenhum (natimorto/aborto, backend
// manda "") quanto pra "S/N" (pariu mas não numerou): as duas situações são
// igualmente "não sei o número", não vale a pena distinguir na tela.
function renderCria(valor: string | null | undefined) {
  if (!valor || valor === "S/N") return <em>sem dados</em>;
  return valor;
}

function QuadroResumoPartos({ linhas }: { linhas: Ficha["resumo_partos"] }) {
  if (!linhas?.length) return null;
  const fmtKg = (v: number | null) => (v == null ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} kg`);
  return (
    <div className="card" style={cardStyle}>
      <div className="card-header mb-2">Resumo por parto</div>
      <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
        Produção, duração e reprodução de cada lactação — o essencial para avaliar o animal de uma vez.
      </p>
      <div className="overflow-x-auto">
        <table className="fazenda-table">
          <thead><tr>
            <th>Parto</th>
            <th>Status</th>
            <th style={{ textAlign: "right" }}>Dias em lactação</th>
            <th style={{ textAlign: "right" }}>Produção total</th>
            <th style={{ textAlign: "right" }}>Média/dia</th>
            <th style={{ textAlign: "right" }}>305 dias</th>
            <th style={{ textAlign: "right" }}>Tentativas p/ emprenhar</th>
            <th style={{ textAlign: "right" }}>DEL na concepção</th>
            <th>Cria</th>
          </tr></thead>
          <tbody>
            {linhas.map((l) => (
              <tr key={l.ordem_parto}>
                <td style={{ fontWeight: 700 }}>{l.ordem_parto}º — {formatDate(l.data_parto)}</td>
                <td style={{ fontSize: "0.78rem", color: l.lactacao_encerrada ? "var(--text-muted)" : "var(--dourado-light)" }}>
                  {l.lactacao_encerrada ? "Encerrada" : "Em andamento"}
                </td>
                <td style={{ textAlign: "right" }}>{l.dias_em_lactacao}</td>
                <td style={{ textAlign: "right" }}>{fmtKg(l.producao_total_kg)}</td>
                <td style={{ textAlign: "right" }}>{fmtKg(l.producao_media_dia_kg)}</td>
                <td style={{ textAlign: "right" }}>
                  {fmtKg(l.producao_305_dias_kg)}
                  {l.producao_305_dias_kg != null && l.producao_305_dias_estimada && (
                    <span title="Lactação com menos de 305 dias registrados — estimativa a partir da média diária real" style={{ marginLeft: "0.3rem", fontSize: "0.68rem", color: "var(--text-muted)" }}>(estim.)</span>
                  )}
                </td>
                <td style={{ textAlign: "right" }}>{l.tentativas_emprenhar ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{l.del_concepcao ?? "—"}</td>
                <td>{renderCria(l.cria)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function classeColostro(brix: number | null): string {
  if (brix == null) return "—";
  if (brix > 25) return "Ouro (excelente)";
  if (brix >= 18) return "Prata (médio)";
  return "Bronze (ruim)";
}
function classeSoro(brix: number | null): string {
  if (brix == null) return "—";
  if (brix >= 8.4) return "Sucesso";
  if (brix >= 8.1) return "Alerta";
  return "Falha";
}

const SECOES: { chave: keyof Ficha; titulo: string; colunas: ColunaExport[] }[] = [
  { chave: "partos", titulo: "Partos", colunas: [
    { header: "Data", key: "data_partoFmt" }, { header: "Ordem", key: "ordem_parto" }, { header: "Tipo", key: "tipo_parto" },
    { header: "Cria 1", key: "numero_cria_1" }, { header: "Cria 2", key: "numero_cria_2" },
    { header: "Sexo cria 1", key: "sexo_cria_1" }, { header: "Sexo cria 2", key: "sexo_cria_2" },
    { header: "Gemelar?", key: "gemelar" }, { header: "Retenção de placenta?", key: "retencao_placenta" },
    // Coluna auxiliar: distingue, linha a linha, o parto/aborto que conta na
    // ordem de parto e abre lactação do aborto que não conta nem abre (ver
    // fazenda.rules.parto.eh_parto_produtivo e o campo
    // `conta_ordem_parto_lactacao` do backend). Pequena e discreta de
    // propósito — é um auxílio de leitura do histórico bruto, não uma
    // métrica principal como as demais colunas.
    { header: "Considerar ordem de parto/lactação", key: "conta_ordem_parto_lactacao" },
  ] },
  { chave: "servicos", titulo: "Reprodução — Serviço/IA e diagnóstico", colunas: [
    { header: "Data serviço", key: "data_servicoFmt" }, { header: "Tipo", key: "tipo_servico" }, { header: "Protocolo", key: "protocolo" },
    { header: "Pai (touro/sêmen)", key: "reprodutor" }, { header: "NAAB do pai", key: "reprodutor_naab" },
    { header: "Central do pai", key: "touro_central" }, { header: "TPI do pai", key: "touro_tpi" }, { header: "NM$ do pai", key: "touro_nm" },
    { header: "Ordem de parto (na IA)", key: "ordem_parto_na_ia" }, { header: "Tentativa", key: "ordem_tentativa" },
    { header: "Data diagnóstico", key: "data_diagnosticoFmt" }, { header: "Diagnóstico", key: "diagnostico" },
    // Parto que ESTE serviço deu origem — só preenchida quando o diagnóstico
    // foi POSITIVO ("—" se ainda não pariu apesar disso; vazia se o
    // diagnóstico não foi positivo). Ver `parto_resultante_data` no backend
    // (fazenda.api.routers.animais.ficha_animal) e `textoPartoOriginado` abaixo.
    { header: "Parto", key: "parto" },
  ] },
  { chave: "protocolos_iatf", titulo: "Protocolo IATF (D0/D7/D9/D11)", colunas: [
    { header: "Dia", key: "dia" }, { header: "Descrição", key: "descricao" }, { header: "Data prevista", key: "data_previstaFmt" },
    { header: "Realizada?", key: "realizada" }, { header: "Data realização", key: "data_realizacaoFmt" },
  ] },
  { chave: "inducao_lactacao", titulo: "Indução de lactação", colunas: [
    { header: "Protocolo", key: "nome_protocolo" }, { header: "Dia", key: "dia" }, { header: "Etapa", key: "descricao" },
    { header: "Data prevista", key: "data_previstaFmt" }, { header: "Realizada?", key: "realizada" }, { header: "Data realização", key: "data_realizacaoFmt" },
  ] },
  { chave: "protocolos_customizados", titulo: "Protocolo personalizado", colunas: [
    { header: "Protocolo", key: "nome_protocolo" }, { header: "Dia", key: "dia" }, { header: "Etapa", key: "descricao" },
    { header: "Insumo", key: "insumo" }, { header: "Data prevista", key: "data_previstaFmt" },
    { header: "Realizada?", key: "realizada" }, { header: "Data realização", key: "data_realizacaoFmt" },
  ] },
  { chave: "movimentos_lote", titulo: "Movimentação de lote", colunas: [
    { header: "Data", key: "data_movimentoFmt" }, { header: "Lote origem", key: "lote_origem" }, { header: "Lote destino", key: "lote_destino" },
    { header: "Motivo", key: "motivo" }, { header: "Origem", key: "origemFmt" }, { header: "Responsável", key: "responsavel" },
  ] },
  { chave: "controles_leiteiros", titulo: "Controle leiteiro", colunas: [
    { header: "Data", key: "data_controleFmt" }, { header: "Produção (kg)", key: "producao_kg" },
    { header: "Ordenha 1", key: "ordenha1_kg" }, { header: "Ordenha 2", key: "ordenha2_kg" }, { header: "Ordenha 3", key: "ordenha3_kg" },
    { header: "DEL no controle", key: "del_no_controle" },
  ] },
  { chave: "pesagens_corporais", titulo: "Pesagem corporal", colunas: [
    { header: "Data", key: "data_pesagemFmt" }, { header: "Peso (kg)", key: "peso_kg" }, { header: "DEL", key: "del_dias" },
    { header: "Idade (meses)", key: "idade_meses" }, { header: "Lote", key: "grupo_primario" },
  ] },
  { chave: "qualidade_leite", titulo: "Qualidade do leite", colunas: [
    { header: "Data coleta", key: "data_coletaFmt" }, { header: "CCS", key: "ccs" }, { header: "CBT", key: "cbt" },
    { header: "Gordura (%)", key: "gordura_pct" }, { header: "Proteína (%)", key: "proteina_pct" },
  ] },
  { chave: "aplicacoes_sanitarias", titulo: "Sanidade — aplicações", colunas: [
    { header: "Data", key: "data_aplicacaoFmt" }, { header: "Produto", key: "produto" }, { header: "Categoria", key: "categoria" },
    { header: "Dose", key: "dose" }, { header: "Unidade", key: "unidade" }, { header: "Via", key: "via" }, { header: "Responsável", key: "responsavel" },
  ] },
  { chave: "protocolos_sanitarios", titulo: "Protocolo sanitário", colunas: [
    { header: "Data início", key: "data_inicioFmt" }, { header: "Protocolo", key: "protocolo_nome" },
    { header: "Responsável", key: "responsavel" }, { header: "Classificação mastite", key: "classificacao_mastite" },
  ] },
  { chave: "secagens", titulo: "Secagem", colunas: [
    { header: "Data", key: "data_secagemFmt" }, { header: "Motivo", key: "motivo" }, { header: "Escore corporal", key: "escore_condicao_corporal" },
  ] },
  { chave: "exames_resultados", titulo: "Rastreabilidade sanitária — Exames", colunas: [
    { header: "Data", key: "data_exameFmt" }, { header: "Exame", key: "evento_sanitario_nome" }, { header: "Resultado", key: "resultado" },
    { header: "Valor", key: "valor_numerico" }, { header: "Faixa", key: "banda" }, { header: "Veterinário", key: "veterinario" },
  ] },
  { chave: "ocorrencias_clinicas", titulo: "Rastreabilidade sanitária — Doenças (ocorrências clínicas)", colunas: [
    { header: "Data", key: "data_ocorrenciaFmt" }, { header: "Doença", key: "doenca" }, { header: "Observação", key: "observacao" }, { header: "Origem", key: "origem" },
  ] },
  { chave: "eventos_agenda", titulo: "Agenda — eventos manuais", colunas: [
    { header: "Data", key: "data_eventoFmt" }, { header: "Descrição", key: "descricao" }, { header: "Categoria", key: "categoria" },
    { header: "Tipo", key: "tipo_evento" },
  ] },
];

const DATA_KEYS: Record<string, string> = {
  partos: "data_parto", servicos: "data_servico", protocolos_iatf: "data_prevista", movimentos_lote: "data_movimento",
  controles_leiteiros: "data_controle", pesagens_corporais: "data_pesagem", qualidade_leite: "data_coleta",
  aplicacoes_sanitarias: "data_aplicacao", protocolos_sanitarios: "data_inicio", secagens: "data_secagem", eventos_agenda: "data_evento",
  exames_resultados: "data_exame", ocorrencias_clinicas: "data_ocorrencia",
  inducao_lactacao: "data_prevista", protocolos_customizados: "data_prevista",
};
const DATA_KEYS_EXTRA: Record<string, string[]> = {
  servicos: ["data_diagnostico"], protocolos_iatf: ["data_realizacao"],
  inducao_lactacao: ["data_realizacao"], protocolos_customizados: ["data_realizacao"],
};

// Ordem visual das seções "de produção/protocolo" entre o card de Controle
// leiteiro e o card unificado de Rastreabilidade sanitária — sempre as
// mesmas entradas de SECOES (colunas/PDF não mudam), só a posição na tela.
const CHAVES_SECOES_PRODUCAO: (keyof Ficha)[] = [
  "protocolos_iatf", "inducao_lactacao", "protocolos_customizados",
  "pesagens_corporais", "qualidade_leite", "protocolos_sanitarios", "secagens",
];

// Coluna "Parto" da tabela de Serviço/IA e diagnóstico: texto curto (não é
// data formatada nem "—"/vazio padrão) — por isso não segue o padrão
// "campoFmt" das demais colunas de data, e sim uma função própria,
// reaproveitada tal e qual pela versão mobile (ver FichaDetalhe em
// mobile/rebanho/Ficha.tsx) para as duas telas mostrarem exatamente a mesma
// regra.
export function textoPartoOriginado(l: Record<string, unknown>): string {
  const positivo = String(l.diagnostico || "").trim().toUpperCase() === "POSITIVO";
  if (!positivo) return "";
  const dataParto = l.parto_resultante_data as string | null | undefined;
  return dataParto ? formatDate(dataParto) : "—";
}

function formatarLinhas(chave: string, linhas: Record<string, unknown>[]): Record<string, unknown>[] {
  return linhas.map((l) => {
    const nova: Record<string, unknown> = { ...l };
    const base = DATA_KEYS[chave];
    if (base) nova[`${base}Fmt`] = l[base] ? formatDate(l[base] as string) : "—";
    for (const extra of DATA_KEYS_EXTRA[chave] || []) {
      nova[`${extra}Fmt`] = l[extra] ? formatDate(l[extra] as string) : "—";
    }
    if ("gemelar" in nova) nova.gemelar = nova.gemelar ? "Sim" : "Não";
    if ("retencao_placenta" in nova) nova.retencao_placenta = nova.retencao_placenta ? "Sim" : "Não";
    if ("realizada" in nova) nova.realizada = nova.realizada ? "Sim" : "Não";
    if ("conta_ordem_parto_lactacao" in nova) nova.conta_ordem_parto_lactacao = nova.conta_ordem_parto_lactacao ? "Sim" : "Não";
    // Rótulo amigável da origem (manual/sugestão confirmada/automática/passiva)
    // — badge só de leitura na Ficha, mantendo o valor bruto para ordenação.
    if (chave === "movimentos_lote") nova.origemFmt = rotuloOrigemMovimentoLote(l.origem);
    if (chave === "servicos") nova.parto = textoPartoOriginado(l);
    return nova;
  });
}

// As três primeiras seções do PDF exportado (Quadro resumo, Informação da
// previsão de parto e Resumo por parto) não vêm de uma lista (`ficha[chave]`)
// como as demais — são os cartões de identificação/previsão/lactação
// mostrados no topo da tela, com uma única linha cada. Construídas aqui a
// partir dos MESMOS campos já exibidos na tela (nenhum dado novo, só
// reorganizados para o formato tabela do exportador).
function construirSecaoQuadroResumo(ficha: Ficha): SecaoFicha {
  const a = ficha.animal as Record<string, unknown>;
  const linha: Record<string, unknown> = {
    sexo: a.sexo === "M" ? "Macho" : a.sexo === "F" ? "Fêmea" : "—",
    categoria: String(a.categoria_abrev || a.categoria_completa || "—"),
    lote_atual: String(a.grupo_primario || "—"),
    data_nasc: a.data_nasc ? formatDate(a.data_nasc as string) : "—",
    mae: String(a.mae_numero || "—"),
    pai: ficha.pai?.nome ? `${ficha.pai.nome}${ficha.pai.naab ? ` (NAAB ${ficha.pai.naab})` : ""}` : "—",
    raca: String(a.raca || "—"),
    grau_sangue: String(a.grau_sangue || "—"),
    situacao: a.ativo ? "Ativo" : "Baixado",
    data_entrada: a.data_entrada ? formatDate(a.data_entrada as string) : "—",
    valor: a.valor != null ? `R$ ${a.valor}` : "—",
    dias_gestacao: ficha.precisao_parto?.dias_gestacao ?? "—",
    del_atual: a.del_dias != null ? String(a.del_dias) : "—",
    previsao_parto: ficha.precisao_parto?.data_parto_provavel ? formatDate(ficha.precisao_parto.data_parto_provavel) : "—",
    // Cria do último parto — "S/N" se pariu sem numerar, vazio (aqui "—")
    // se o último parto foi natimorto. Ver fazenda.rules.parto_resumo.
    ultima_cria: (ficha.ultima_cria && ficha.ultima_cria !== "S/N") ? ficha.ultima_cria : "sem dados",
  };
  return {
    titulo: "Quadro resumo",
    colunas: [
      { header: "Sexo", key: "sexo" }, { header: "Categoria", key: "categoria" }, { header: "Lote atual", key: "lote_atual" },
      { header: "Data de nascimento", key: "data_nasc" }, { header: "Mãe", key: "mae" }, { header: "Pai", key: "pai" },
      { header: "Raça", key: "raca" }, { header: "Grau de sangue", key: "grau_sangue" }, { header: "Situação", key: "situacao" },
      { header: "Data de entrada", key: "data_entrada" }, { header: "Valor", key: "valor" },
      { header: "Dias de gestação", key: "dias_gestacao" }, { header: "DEL atual", key: "del_atual" },
      { header: "Previsão de parto", key: "previsao_parto" }, { header: "Última cria", key: "ultima_cria" },
    ],
    linhas: [linha],
  };
}

function construirSecaoPrevisaoParto(pp: PrecisaoParto): SecaoFicha {
  const linha: Record<string, unknown> = {
    ultima_ia: pp.data_ultima_ia_positiva ? formatDate(pp.data_ultima_ia_positiva) : "—",
    diagnostico_positivo: pp.data_confirmacao_prenhez ? formatDate(pp.data_confirmacao_prenhez) : "—",
    dias_gestacao: pp.dias_gestacao ?? "—",
    previsao_parto: pp.data_parto_provavel ? formatDate(pp.data_parto_provavel) : "—",
    dias_faltam: pp.dias_para_parto != null ? `${pp.dias_para_parto} dia(s)` : "—",
  };
  return {
    titulo: "Informação da previsão de parto",
    colunas: [
      { header: "Última IA", key: "ultima_ia" }, { header: "Último diagnóstico positivo", key: "diagnostico_positivo" },
      { header: "Dias de gestação", key: "dias_gestacao" }, { header: "Previsão de parto", key: "previsao_parto" },
      { header: "Faltam", key: "dias_faltam" },
    ],
    linhas: [linha],
  };
}

function construirSecaoResumoPartos(linhas: Ficha["resumo_partos"]): SecaoFicha {
  const fmtKg = (v: number | null) => (v == null ? "—" : `${v.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} kg`);
  return {
    titulo: "Resumo por parto",
    colunas: [
      { header: "Parto", key: "parto" }, { header: "Status", key: "status" },
      { header: "DEL", key: "dias_em_lactacao" }, { header: "Produção total", key: "producao_total" },
      { header: "Média/dia", key: "producao_media_dia" }, { header: "305 dias", key: "producao_305_dias" },
      { header: "Tentativas p/ emprenhar", key: "tentativas_emprenhar" }, { header: "DEL na concepção", key: "del_concepcao" },
      { header: "Cria", key: "cria" },
    ],
    linhas: linhas.map((l) => ({
      parto: `${l.ordem_parto}º — ${formatDate(l.data_parto)}`,
      status: l.lactacao_encerrada ? "Encerrada" : "Em andamento",
      dias_em_lactacao: l.dias_em_lactacao,
      producao_total: fmtKg(l.producao_total_kg),
      producao_media_dia: fmtKg(l.producao_media_dia_kg),
      producao_305_dias: fmtKg(l.producao_305_dias_kg),
      tentativas_emprenhar: l.tentativas_emprenhar ?? "—",
      del_concepcao: l.del_concepcao ?? "—",
      cria: (l.cria && l.cria !== "S/N") ? l.cria : "sem dados",
    })),
  };
}

// Linha do tempo de rastreabilidade sanitária, no formato do exportador —
// mesmos campos genéricos já mostrados na aba "Linha do tempo" do card
// unificado de Rastreabilidade sanitária (data, tipo de evento, descrição,
// GTA, responsável). Antes esta seção não entrava no PDF; agora entra logo
// antes de "Exames", já que na tela as duas são abas do mesmo card.
function construirSecaoLinhaTempo(linhaTempo: Ficha["linha_tempo_sanitaria"]): SecaoFicha {
  return {
    titulo: "Rastreabilidade sanitária — Linha do tempo",
    colunas: [
      { header: "Data", key: "dataFmt" }, { header: "Evento", key: "tipo_evento" },
      { header: "Descrição", key: "descricao" }, { header: "GTA", key: "gta" }, { header: "Responsável", key: "responsavel" },
    ],
    linhas: (linhaTempo || []).map((e) => ({
      dataFmt: e.data ? formatDate(e.data) : "—",
      tipo_evento: e.tipo_evento,
      descricao: e.descricao || "—",
      gta: e.gta || "—",
      responsavel: e.responsavel || "—",
    })),
  };
}

const cardStyle: React.CSSProperties = { marginBottom: "1rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };
const inpStyle: React.CSSProperties = { width: "100%", padding: "0.35rem 0.5rem", borderRadius: 6, fontSize: "0.82rem", background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" };
const btnEdit: React.CSSProperties = { fontSize: "0.75rem", display: "inline-flex", alignItems: "center", gap: "0.3rem" };

// Seção genérica de histórico (partos, serviços, sanidade etc.) — colunas
// dinâmicas por seção. Cada seção ganha sua própria ordenação (hook próprio,
// por isso é um componente e não um `.map()` direto). Colunas formatadas
// (chave terminando em "Fmt") ordenam pelo campo bruto correspondente —
// `formatarLinhas` mantém os dois no mesmo objeto — igual à regra usada no
// Relatório Personalizado (prefere campo bruto ao formatado).
// A tabela em si (sem o card/recolhível ao redor) — extraída para ser
// reaproveitada tanto pelas seções de histórico "padrão" (`SecaoHistoricoTabela`
// abaixo) quanto pelas abas "Exames" e "Doenças" do card unificado de
// Rastreabilidade sanitária (`SecaoRastreabilidadeSanitaria`), que já tem seu
// próprio `SecaoRecolhivel` ao redor das abas.
function TabelaSecaoDados({ chave, colunas, linhas, onAbrirCria }: {
  chave: string; colunas: ColunaExport[]; linhas: Record<string, unknown>[]; onAbrirCria: (numero: string) => void;
}) {
  const ord = useOrdenacao(linhas);
  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table">
        <thead>
          <tr>
            {colunas.map((c) => {
              const campo = c.key.endsWith("Fmt") ? c.key.slice(0, -3) : c.key;
              return <ThOrdenavel key={c.key} label={c.header} campo={campo} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />;
            })}
          </tr>
        </thead>
        <tbody>
          {ord.linhasOrdenadas.map((l, i) => (
            <tr key={i} style={chave === "servicos" ? estiloSexado(l.tipo_semen as string | null | undefined) : undefined}
              title={chave === "servicos" && l.tipo_semen === "sexado" ? "Inseminação com sêmen sexado" : undefined}>
              {colunas.map((c) => {
                const val = l[c.key];
                // Número da cria: link para abrir a ficha da própria cria.
                if ((c.key === "numero_cria_1" || c.key === "numero_cria_2") && val) {
                  return (
                    <td key={c.key} style={{ fontSize: "0.78rem" }}>
                      <button onClick={() => onAbrirCria(String(val))} title={`Abrir a ficha da cria ${val}`}
                        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", color: "var(--dourado-light)", textDecoration: "underline", fontWeight: 600, fontSize: "0.78rem" }}>
                        {String(val)}
                      </button>
                    </td>
                  );
                }
                return <td key={c.key} style={{ fontSize: "0.78rem" }}>{String(val ?? "—")}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SecaoHistoricoTabela({ chave, titulo, colunas, linhas, onAbrirCria }: {
  chave: string; titulo: string; colunas: ColunaExport[]; linhas: Record<string, unknown>[]; onAbrirCria: (numero: string) => void;
}) {
  return (
    <SecaoRecolhivel titulo={titulo} badge={String(linhas.length)}>
      <TabelaSecaoDados chave={chave} colunas={colunas} linhas={linhas} onAbrirCria={onAbrirCria} />
    </SecaoRecolhivel>
  );
}

// Controle leiteiro: a mesma seção, em duas leituras — a tabela (o dado bruto,
// linha a linha) e a curva de lactação (a forma da lactação ao longo do DEL,
// comparada com a média do rebanho). São perguntas diferentes sobre os mesmos
// números: "o que foi medido?" e "isto está bom?".
function SecaoControleLeiteiro({ colunas, linhas, brutas, referencia, referenciaGrupo, curvaWood, onAbrirCria, numeroMatriz }: {
  colunas: ColunaExport[];
  linhas: Record<string, unknown>[];
  brutas: Record<string, unknown>[];
  referencia?: FaixaReferencia[];
  referenciaGrupo?: FaixaReferencia[] | null;
  curvaWood?: PontoWood[] | null;
  onAbrirCria: (numero: string) => void;
  numeroMatriz: string;
}) {
  const [aba, setAba] = useState<"tabela" | "curva">("tabela");
  const ord = useOrdenacao(linhas);

  // Equivalente maduro deste animal — produz hoje × produzirá na
  // maturidade, calculado pelo mesmo motor do relatório de Produção (ver
  // docs/equivalente-maduro-proposta.md). Erro/404 (sem lactação ainda) fica
  // silencioso — não é uma falha da ficha, é o animal não ter base ainda.
  const [trioEM, setTrioEM] = useState<TrioEquivalenteMaduro | null>(null);
  useEffect(() => {
    fetchEquivalenteMaduroDoAnimal(numeroMatriz).then(setTrioEM).catch(() => setTrioEM(null));
  }, [numeroMatriz]);

  const pontos = brutas
    .map((c) => ({
      del: Number(c.del_no_controle),
      kg: Number(c.producao_kg),
      data: c.data_controle ? formatDate(String(c.data_controle)) : null,
    }))
    .filter((p) => Number.isFinite(p.del) && Number.isFinite(p.kg));

  return (
    <SecaoRecolhivel titulo="Controle leiteiro" badge={String(linhas.length)}>
      <TabBar<"tabela" | "curva">
        abas={[
          { id: "tabela", label: "Tabela", title: "Os controles leiteiros lançados, linha a linha" },
          { id: "curva", label: "Curva de lactação", title: "Produção por DEL, com a média do rebanho como referência" },
        ]}
        ativa={aba}
        onChange={setAba}
      />
      {trioEM && (
        <div style={{ background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.8rem", margin: "0.75rem 0" }}>
          <p style={{ margin: "0 0 0.5rem", fontWeight: 700, fontSize: "0.8rem" }}>Equivalente maduro</p>
          <TrioEquivalenteMaduroView trio={trioEM} />
          <NotaExplicativaEM />
        </div>
      )}
      {aba === "curva" ? (
        <CurvaLactacao pontos={pontos} referencia={referencia}
          referenciaGrupo={referenciaGrupo || undefined} curvaWood={curvaWood || undefined} />
      ) : (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                {colunas.map((c) => {
                  const campo = c.key.endsWith("Fmt") ? c.key.slice(0, -3) : c.key;
                  return <ThOrdenavel key={c.key} label={c.header} campo={campo} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />;
                })}
              </tr>
            </thead>
            <tbody>
              {ord.linhasOrdenadas.map((l, i) => (
                <tr key={i}>
                  {colunas.map((c) => (
                    <td key={c.key} style={{ fontSize: "0.78rem" }}>{String(l[c.key] ?? "—")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SecaoRecolhivel>
  );
}

// Rastreabilidade sanitária: um único card com três leituras do mesmo
// histórico sanitário/de movimentação do animal — "Linha do tempo" (visão
// cronológica combinada de compra/venda/aplicações/protocolos/exames/doenças/
// baixa, com campos genéricos), "Exames" (resultados de laboratório, com
// valor/faixa/veterinário) e "Doenças" (ocorrências clínicas). Antes eram
// dois blocos soltos na tela (linha do tempo fora do array SECOES, Exames
// dentro dele) mais um terceiro card de Doenças — unificados aqui por serem
// a mesma família temática (rastreabilidade sanitária), com abas em vez de
// três cards separados.
function SecaoRastreabilidadeSanitaria({
  linhaTempo, colunasExames, exames, colunasDoencas, doencas, onAbrirCria,
}: {
  linhaTempo: Ficha["linha_tempo_sanitaria"];
  colunasExames: ColunaExport[]; exames: Record<string, unknown>[];
  colunasDoencas: ColunaExport[]; doencas: Record<string, unknown>[];
  onAbrirCria: (numero: string) => void;
}) {
  const [aba, setAba] = useState<"linha_tempo" | "exames" | "doencas">("linha_tempo");
  const ordLinhaTempo = useOrdenacao(linhaTempo);
  const total = linhaTempo.length + exames.length + doencas.length;
  if (!total) return null;

  return (
    <SecaoRecolhivel titulo="Rastreabilidade sanitária" badge={String(total)}>
      <TabBar<"linha_tempo" | "exames" | "doencas">
        abas={[
          { id: "linha_tempo", label: "Linha do tempo", title: `Compra, venda, aplicações, protocolos, exames, doenças e baixa, em ordem cronológica (${linhaTempo.length})` },
          { id: "exames", label: "Exames", title: `Resultados de exames laboratoriais — BLV, brucelose, tuberculose etc. (${exames.length})` },
          { id: "doencas", label: "Doenças", title: `Ocorrências clínicas registradas para o animal (${doencas.length})` },
        ]}
        ativa={aba}
        onChange={setAba}
      />
      {aba === "linha_tempo" && (
        linhaTempo.length ? (
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead>
                <tr>
                  <ThOrdenavel label="Data" campo="data" coluna={ordLinhaTempo.coluna} dir={ordLinhaTempo.dir} ordenar={ordLinhaTempo.ordenar} />
                  <ThOrdenavel label="Evento" campo="tipo_evento" coluna={ordLinhaTempo.coluna} dir={ordLinhaTempo.dir} ordenar={ordLinhaTempo.ordenar} />
                  <ThOrdenavel label="Descrição" campo="descricao" coluna={ordLinhaTempo.coluna} dir={ordLinhaTempo.dir} ordenar={ordLinhaTempo.ordenar} />
                  <ThOrdenavel label="GTA" campo="gta" coluna={ordLinhaTempo.coluna} dir={ordLinhaTempo.dir} ordenar={ordLinhaTempo.ordenar} />
                  <ThOrdenavel label="Responsável" campo="responsavel" coluna={ordLinhaTempo.coluna} dir={ordLinhaTempo.dir} ordenar={ordLinhaTempo.ordenar} />
                </tr>
              </thead>
              <tbody>
                {ordLinhaTempo.linhasOrdenadas.map((e, i) => (
                  <tr key={i}>
                    <td style={{ fontSize: "0.78rem" }}>{e.data ? formatDate(e.data) : "—"}</td>
                    <td style={{ fontSize: "0.78rem", fontWeight: 600 }}>{e.tipo_evento}</td>
                    <td style={{ fontSize: "0.78rem" }}>{e.descricao || "—"}</td>
                    <td style={{ fontSize: "0.78rem", color: e.gta ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: e.gta ? 700 : 400 }}>{e.gta || "—"}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{e.responsavel || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhum evento na linha do tempo.</p>
      )}
      {aba === "exames" && (
        exames.length
          ? <TabelaSecaoDados chave="exames_resultados" colunas={colunasExames} linhas={exames} onAbrirCria={onAbrirCria} />
          : <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhum exame lançado.</p>
      )}
      {aba === "doencas" && (
        doencas.length
          ? <TabelaSecaoDados chave="ocorrencias_clinicas" colunas={colunasDoencas} linhas={doencas} onAbrirCria={onAbrirCria} />
          : <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Nenhuma ocorrência clínica registrada.</p>
      )}
    </SecaoRecolhivel>
  );
}

// Um campo editável (label + input/select) para os formulários da ficha.
// `destaque` marca em vermelho o campo que motivou uma pendência da Agenda
// (colostragem/IgG não lançados no parto) — sinaliza exatamente o que falta,
// em vez de só levar o usuário até a tela.
function CampoEdit({ label, children, destaque }: { label: string; children: React.ReactNode; destaque?: boolean }) {
  return <div><label style={destaque ? { ...labelStyle, color: "var(--red)", fontWeight: 700 } : labelStyle}>{label}{destaque ? " — pendente" : ""}</label>{children}</div>;
}

export default function FichaAnimal({ numeroInicial }: { numeroInicial?: string } = {}) {
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [numero, setNumero] = useState("");
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  // Edição inline: cadastro do animal e colostragem/IgG.
  const [editAnimal, setEditAnimal] = useState(false);
  const [formAnimal, setFormAnimal] = useState<Record<string, any>>({});
  const [editColostro, setEditColostro] = useState(false);
  const [formColostro, setFormColostro] = useState<Record<string, any>>({});
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  // Chegando da Agenda (pendência de colostragem/IgG não lançada no parto):
  // abre direto na ficha do animal certo, com o campo em falta destacado e o
  // formulário de colostragem já aberto para preencher.
  const [destacar, setDestacar] = useState<"colostragem" | "igg" | null>(null);
  const [abrirEdicaoAoCarregar, setAbrirEdicaoAoCarregar] = useState(false);
  // Popup de confirmação ao mudar a mãe — cruza com os partos dela (ver
  // /reproducao/verificar-mae) antes de salvar, mostrando data/parto e
  // eventuais inconsistências.
  const [confirmMae, setConfirmMae] = useState<{ verificacao: VerificacaoMaeParto; payload: Record<string, any> } | null>(null);

  useEffect(() => { fetchAnimais({ incluirMachos: true }).then(setAnimais).catch(() => {}); }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const n = numeroInicial || params.get("numero");
    const d = params.get("destacar");
    if (d === "colostragem" || d === "igg") { setDestacar(d); setAbrirEdicaoAoCarregar(true); }
    if (n) buscar(n);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numeroInicial]);

  async function buscar(n: string) {
    setNumero(n);
    setFicha(null);
    setErro(null);
    if (!n) return;
    setCarregando(true);
    try {
      setFicha(await fetchFichaAnimal(n));
    } catch (e: any) {
      setErro(e.message || "Erro ao buscar ficha do animal");
    } finally {
      setCarregando(false);
    }
  }

  function abrirEditAnimal() {
    const a2: any = ficha?.animal || {};
    setFormAnimal({
      nome: a2.nome ?? "", sexo: a2.sexo ?? "", raca: a2.raca ?? "", grau_sangue: a2.grau_sangue ?? "",
      categoria_abrev: a2.categoria_abrev ?? "", grupo_primario: a2.grupo_primario ?? "",
      data_nasc: a2.data_nasc ?? "", data_entrada: a2.data_entrada ?? "",
      mae_numero: a2.mae_numero ?? "", mae_nome: a2.mae_nome ?? "",
      proprietario: a2.proprietario ?? "", valor: a2.valor ?? "", observacoes: a2.observacoes ?? "",
      // Não editável mais nesta tela (ver remoção do checkbox abaixo), mas
      // precisa continuar no payload: o PUT reescreve TODOS os campos de
      // AnimalFichaIn (sem exclude_unset) — se sumisse daqui, salvar
      // qualquer outro campo da ficha resetaria excluir_bst para False.
      excluir_bst: a2.excluir_bst ?? false,
    });
    setEditAnimal(true); setAviso(null);
    // Categoria em branco (comum em animais recém-importados) → sugere pelos
    // parâmetros cadastrados em Configurações > Cadastro > Categorias, já que
    // "os animais seguem os parâmetros". Continua editável/substituível.
    if (!a2.categoria_abrev && numero) {
      fetchCategoriaSugerida(numero).then((r) => {
        if (r.categoria) setFormAnimal((f) => (f.categoria_abrev ? f : { ...f, categoria_abrev: r.categoria as string }));
      }).catch(() => {});
    }
  }
  async function salvarAnimal(payloadConfirmado?: Record<string, any>) {
    setSalvando(true); setAviso(null);
    try {
      let payload = payloadConfirmado;
      if (!payload) {
        payload = { numero, ...formAnimal };
        Object.keys(payload).forEach((k) => { if (payload![k] === "") payload![k] = null; });
        if (payload.valor != null) payload.valor = Number(payload.valor) || null;
        // Mãe mudou (e não é vazia) — cruza com os partos dela antes de
        // salvar, avisando com um popup de confirmação (data/parto/inconsistências).
        const maeOriginal = (ficha?.animal as any)?.mae_numero || null;
        if (payload.mae_numero && payload.mae_numero !== maeOriginal) {
          const verificacao = await verificarMaeParto(payload.mae_numero, numero);
          setConfirmMae({ verificacao, payload });
          setSalvando(false);
          return;
        }
      }
      await atualizarAnimalFicha(numero, payload);
      setEditAnimal(false); setAviso("Ficha atualizada."); setConfirmMae(null);
      await buscar(numero);
    } catch (e: any) { setAviso(e.message || "Erro ao salvar."); }
    finally { setSalvando(false); }
  }

  function abrirEditColostro() {
    const c: any = ficha?.colostragem || {};
    setFormColostro({
      tomou_colostro: c.tomou_colostro == null ? "" : String(c.tomou_colostro),
      litros_colostro: c.litros_colostro ?? "", brix_colostro: c.brix_colostro ?? "",
      data_colostro: c.data_colostro ?? "", brix_soro: c.brix_soro ?? "",
      hora_parto: c.hora_parto ?? "", hora_colostro: c.hora_colostro ?? "", peso_nascer_kg: c.peso_nascer_kg ?? "",
      proteina_serica: c.proteina_serica ?? "", apenas_colostro_po: c.apenas_colostro_po ? "true" : "",
      data_teste_sangue: c.data_teste_sangue ?? "", observacao: c.observacao ?? "",
    });
    setEditColostro(true); setAviso(null);
  }

  // Chegou da Agenda com uma pendência de colostro/IgG: assim que a ficha
  // carrega, abre direto o formulário de colostragem (não fica só na tela de
  // leitura esperando o usuário achar o botão "Lançar").
  useEffect(() => {
    if (ficha && abrirEdicaoAoCarregar) {
      abrirEditColostro();
      setAbrirEdicaoAoCarregar(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ficha]);

  async function salvarColostro() {
    setSalvando(true); setAviso(null);
    try {
      const f = formColostro;
      await registrarColostragem({
        numero_animal: numero,
        tomou_colostro: f.tomou_colostro === "" ? undefined : f.tomou_colostro === "true",
        litros_colostro: f.litros_colostro === "" ? undefined : Number(f.litros_colostro),
        brix_colostro: f.brix_colostro === "" ? undefined : Number(f.brix_colostro),
        data_colostro: f.data_colostro || undefined,
        hora_parto: f.hora_parto || undefined,
        hora_colostro: f.hora_colostro || undefined,
        peso_nascer_kg: f.peso_nascer_kg === "" ? undefined : Number(f.peso_nascer_kg),
        brix_soro: f.brix_soro === "" ? undefined : Number(f.brix_soro),
        proteina_serica: f.proteina_serica === "" ? undefined : Number(f.proteina_serica),
        apenas_colostro_po: f.apenas_colostro_po === "true" ? true : undefined,
        data_teste_sangue: f.data_teste_sangue || undefined,
        observacao: f.observacao || undefined,
      });
      setEditColostro(false); setAviso("Colostragem/IgG salvos.");
      setDestacar(null);
      await buscar(numero);
    } catch (e: any) { setAviso(e.message || "Erro ao salvar."); }
    finally { setSalvando(false); }
  }

  async function exportarPDF() {
    if (!ficha) return;
    // Ordem fixa dos 4 primeiros blocos do PDF exportado — a mesma sequência
    // em que o usuário lê a ficha na tela (identificação → previsão de parto
    // em aberto → histórico de partos → resumo por lactação) — só depois vem
    // o restante das seções (reprodução, sanidade, produção etc.), na mesma
    // ordem de sempre (SECOES, sem "partos" — já usado no bloco 3). A "Linha
    // do tempo" (que não vem de SECOES — ver `ficha.linha_tempo_sanitaria`)
    // é inserida logo antes de "Exames", já que na tela as duas viraram abas
    // do mesmo card de Rastreabilidade sanitária.
    const partosSecao = SECOES.find((s) => s.chave === "partos")!;
    const demaisSecoes: SecaoFicha[] = [];
    for (const s of SECOES.filter((s) => s.chave !== "partos")) {
      if (s.chave === "exames_resultados") demaisSecoes.push(construirSecaoLinhaTempo(ficha.linha_tempo_sanitaria));
      demaisSecoes.push({ titulo: s.titulo, colunas: s.colunas, linhas: formatarLinhas(s.chave, (ficha[s.chave] as Record<string, unknown>[]) || []) });
    }
    const secoes: SecaoFicha[] = [
      construirSecaoQuadroResumo(ficha),
      ...(ficha.precisao_parto ? [construirSecaoPrevisaoParto(ficha.precisao_parto)] : []),
      { titulo: partosSecao.titulo, colunas: partosSecao.colunas, linhas: formatarLinhas("partos", ficha.partos || []) },
      construirSecaoResumoPartos(ficha.resumo_partos || []),
      ...demaisSecoes,
    ];
    try {
      await exportarFichaPDF(
        `Ficha do animal ${numero}`,
        `${ficha.animal.nome ? `${ficha.animal.nome} — ` : ""}${ficha.animal.categoria_abrev || ""} · Lote ${ficha.animal.grupo_primario || "—"}`,
        secoes,
        `ficha_animal_${numero}`,
      );
    } catch {
      // erro já mostrado ao usuário dentro de exportarFichaPDF (lib/export.ts)
    }
  }

  // Renderiza uma seção "padrão" (tabela genérica de histórico) de SECOES
  // pela chave — usado para posicionar cada card na ordem visual desejada
  // sem depender da ordem de declaração de SECOES (que também alimenta o
  // PDF e por isso não muda).
  function renderSecao(chave: keyof Ficha) {
    if (!ficha) return null;
    const s = SECOES.find((x) => x.chave === chave);
    if (!s) return null;
    const linhasBrutas = (ficha[chave] as Record<string, unknown>[]) || [];
    if (!linhasBrutas.length) return null;
    const linhas = formatarLinhas(chave as string, linhasBrutas);
    return <SecaoHistoricoTabela key={chave as string} chave={chave as string} titulo={s.titulo} colunas={s.colunas} linhas={linhas} onAbrirCria={buscar} />;
  }

  function renderControleLeiteiro() {
    if (!ficha) return null;
    const linhasBrutas = (ficha.controles_leiteiros as Record<string, unknown>[]) || [];
    if (!linhasBrutas.length) return null;
    const s = SECOES.find((x) => x.chave === "controles_leiteiros")!;
    const linhas = formatarLinhas("controles_leiteiros", linhasBrutas);
    return (
      <SecaoControleLeiteiro colunas={s.colunas} linhas={linhas} brutas={linhasBrutas}
        referencia={ficha.curva_referencia_rebanho}
        referenciaGrupo={ficha.curva_referencia_grupo_ordem_parto} curvaWood={ficha.curva_wood}
        onAbrirCria={buscar}
        numeroMatriz={String(ficha.animal.numero ?? "")} />
    );
  }

  const a = ficha?.animal;

  return (
    <div className="p-6">
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><FileText size={16} /> Ficha do animal</div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Todos os lançamentos já registrados para o animal escolhido — reprodução, partos, colostragem/IgG,
          produção, sanidade (aplicações, protocolos, exames e doenças), GTA de compra/venda, movimentação de
          lote, baixa e agenda — reunidos em uma única ficha, com a linha do tempo de rastreabilidade sanitária.
        </p>
        <div style={{ maxWidth: "420px" }}>
          <label style={labelStyle}>Animal</label>
          <AnimalPicker animais={animais} value={numero} onChange={buscar} />
        </div>
      </div>

      {carregando && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}
      {erro && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {erro}.</span></div>}

      {ficha && a && (
        <>
          {aviso && <div className="mb-3" style={{ fontSize: "0.8rem", color: "var(--green-light)" }}>{aviso}</div>}
          <div className="card" style={cardStyle}>
            <div className="card-header mb-3 flex items-center justify-between">
              <span>{String(a.nome || a.numero)} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>(nº {String(a.numero)})</span></span>
              <div className="flex items-center gap-2">
                {!editAnimal && <button className="btn-ghost" style={btnEdit} onClick={abrirEditAnimal}><Pencil size={13} /> Editar cadastro</button>}
                <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={exportarPDF}>
                  <Download size={13} /> Exportar PDF
                </button>
              </div>
            </div>
            {editAnimal ? (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <CampoEdit label="Nome"><input style={inpStyle} value={formAnimal.nome} onChange={(e) => setFormAnimal((f) => ({ ...f, nome: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Sexo"><select style={inpStyle} value={formAnimal.sexo} onChange={(e) => setFormAnimal((f) => ({ ...f, sexo: e.target.value }))}><option value="">—</option><option value="F">Fêmea</option><option value="M">Macho</option></select></CampoEdit>
                  <CampoEdit label="Categoria"><input style={inpStyle} value={formAnimal.categoria_abrev} onChange={(e) => setFormAnimal((f) => ({ ...f, categoria_abrev: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Lote"><input style={inpStyle} value={formAnimal.grupo_primario} onChange={(e) => setFormAnimal((f) => ({ ...f, grupo_primario: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Data de nascimento"><input type="date" style={inpStyle} value={formAnimal.data_nasc || ""} onChange={(e) => setFormAnimal((f) => ({ ...f, data_nasc: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Data de entrada"><input type="date" style={inpStyle} value={formAnimal.data_entrada || ""} onChange={(e) => setFormAnimal((f) => ({ ...f, data_entrada: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Raça"><input style={inpStyle} value={formAnimal.raca} onChange={(e) => setFormAnimal((f) => ({ ...f, raca: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Grau de sangue"><input style={inpStyle} value={formAnimal.grau_sangue} onChange={(e) => setFormAnimal((f) => ({ ...f, grau_sangue: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Mãe (nº)"><input style={inpStyle} value={formAnimal.mae_numero} onChange={(e) => setFormAnimal((f) => ({ ...f, mae_numero: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Proprietário"><input style={inpStyle} value={formAnimal.proprietario} onChange={(e) => setFormAnimal((f) => ({ ...f, proprietario: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Valor (R$)"><CampoMoeda style={inpStyle} value={Number(formAnimal.valor) || 0} onChange={(v) => setFormAnimal((f) => ({ ...f, valor: v ? String(v) : "" }))} /></CampoEdit>
                  <div style={{ gridColumn: "span 2" }}><CampoEdit label="Observações"><input style={inpStyle} value={formAnimal.observacoes} onChange={(e) => setFormAnimal((f) => ({ ...f, observacoes: e.target.value }))} /></CampoEdit></div>
                </div>
                <div className="flex items-center gap-2 mt-3">
                  <button className="btn-primary" style={btnEdit} disabled={salvando} onClick={() => salvarAnimal()}><Save size={13} /> {salvando ? "Salvando…" : "Salvar"}</button>
                  <button className="btn-ghost" style={btnEdit} onClick={() => setEditAnimal(false)}><X size={13} /> Cancelar</button>
                </div>
              </>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ fontSize: "0.8rem" }}>
                <div><span style={labelStyle}>Sexo</span><br />{a.sexo === "M" ? "Macho" : a.sexo === "F" ? "Fêmea" : "—"}</div>
                <div><span style={labelStyle}>Categoria</span><br />{String(a.categoria_abrev || a.categoria_completa || "—")}</div>
                <div><span style={labelStyle}>Lote atual</span><br />{String(a.grupo_primario || "—")}</div>
                <div><span style={labelStyle}>Data de nascimento</span><br />{a.data_nasc ? formatDate(a.data_nasc as string) : "—"}</div>
                <div><span style={labelStyle}>Mãe</span><br />{String(a.mae_numero || "—")}</div>
                <div><span style={labelStyle}>Pai</span><br />
                  {ficha.pai?.nome ? `${ficha.pai.nome}${ficha.pai.naab ? ` (NAAB ${ficha.pai.naab})` : ""}` : "—"}
                </div>
                <div><span style={labelStyle}>Raça</span><br />{String(a.raca || "—")}</div>
                <div><span style={labelStyle}>Grau de sangue</span><br />{String(a.grau_sangue || "—")}</div>
                <div><span style={labelStyle}>Situação</span><br />{a.ativo ? "Ativo" : "Baixado"}</div>
                <div><span style={labelStyle}>Data de entrada</span><br />{a.data_entrada ? formatDate(a.data_entrada as string) : "—"}</div>
                <div><span style={labelStyle}>Valor</span><br />{a.valor != null ? `R$ ${a.valor}` : "—"}</div>
              </div>
            )}
            <div style={{ marginTop: "0.85rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border)", display: "grid", gridTemplateColumns: "repeat(4, minmax(120px, 1fr))", gap: "0.75rem", fontSize: "0.8rem" }}>
              <div><span style={labelStyle}>Dias de gestação</span><br />{ficha.precisao_parto?.dias_gestacao ?? "—"}</div>
              <div><span style={labelStyle}>DEL atual</span><br />{a.del_dias != null ? String(a.del_dias) : "—"}</div>
              <div><span style={labelStyle}>Previsão de parto</span><br />{ficha.precisao_parto?.data_parto_provavel ? formatDate(ficha.precisao_parto.data_parto_provavel) : "—"}</div>
              <div><span style={labelStyle}>Última cria</span><br />{renderCria(ficha.ultima_cria)}</div>
            </div>
          </div>

          <div className="card" style={destacar ? { ...cardStyle, borderColor: "var(--red)" } : cardStyle}>
            <div className="card-header mb-3 flex items-center justify-between">
              <span>Colostragem e teste de sangue (IgG)</span>
              {!editColostro && <button className="btn-ghost" style={btnEdit} onClick={abrirEditColostro}><Pencil size={13} /> {ficha.colostragem ? "Editar" : "Lançar"}</button>}
            </div>
            {destacar && (
              <p style={{ fontSize: "0.78rem", color: "var(--red)", fontWeight: 600, marginBottom: "0.6rem" }}>
                <AlertTriangle size={13} style={{ display: "inline", marginRight: "0.3rem", verticalAlign: "-2px" }} />
                Pendente da Agenda — preencha {destacar === "colostragem" ? "os litros e o Brix do colostro" : "o Brix do soro (IgG)"} abaixo.
              </p>
            )}
            {editColostro ? (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <CampoEdit label="Tomou colostro?"><select style={inpStyle} value={formColostro.tomou_colostro} onChange={(e) => setFormColostro((f) => ({ ...f, tomou_colostro: e.target.value }))}><option value="">—</option><option value="true">Sim</option><option value="false">Não</option></select></CampoEdit>
                  <CampoEdit label="Litros de colostro" destaque={destacar === "colostragem"}><input type="number" style={inpStyle} value={formColostro.litros_colostro} onChange={(e) => setFormColostro((f) => ({ ...f, litros_colostro: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Brix colostro (%)" destaque={destacar === "colostragem"}><input type="number" style={inpStyle} value={formColostro.brix_colostro} onChange={(e) => setFormColostro((f) => ({ ...f, brix_colostro: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Data do colostro"><input type="date" style={inpStyle} value={formColostro.data_colostro || ""} onChange={(e) => setFormColostro((f) => ({ ...f, data_colostro: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Brix soro / IgG (%)" destaque={destacar === "igg"}><input type="number" style={inpStyle} value={formColostro.brix_soro} onChange={(e) => setFormColostro((f) => ({ ...f, brix_soro: e.target.value }))} /></CampoEdit>
                  <CampoEdit label="Data do teste de sangue"><input type="date" style={inpStyle} value={formColostro.data_teste_sangue || ""} onChange={(e) => setFormColostro((f) => ({ ...f, data_teste_sangue: e.target.value }))} /></CampoEdit>
                  <div style={{ gridColumn: "span 2" }}><CampoEdit label="Observação"><input style={inpStyle} value={formColostro.observacao} onChange={(e) => setFormColostro((f) => ({ ...f, observacao: e.target.value }))} /></CampoEdit></div>
                </div>
                <div className="flex items-center gap-2 mt-3">
                  <button className="btn-primary" style={btnEdit} disabled={salvando} onClick={salvarColostro}><Save size={13} /> {salvando ? "Salvando…" : "Salvar"}</button>
                  <button className="btn-ghost" style={btnEdit} onClick={() => setEditColostro(false)}><X size={13} /> Cancelar</button>
                </div>
              </>
            ) : ficha.colostragem ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ fontSize: "0.8rem" }}>
                <div><span style={labelStyle}>Tomou colostro?</span><br />{ficha.colostragem.tomou_colostro == null ? "—" : ficha.colostragem.tomou_colostro ? "Sim" : "Não"}</div>
                <div><span style={labelStyle}>Litros</span><br />{String(ficha.colostragem.litros_colostro ?? "—")}</div>
                <div><span style={labelStyle}>Brix colostro (%)</span><br />{String(ficha.colostragem.brix_colostro ?? "—")} — {classeColostro(ficha.colostragem.brix_colostro as number | null)}</div>
                <div><span style={labelStyle}>Brix soro (%)</span><br />{String(ficha.colostragem.brix_soro ?? "—")} — {classeSoro(ficha.colostragem.brix_soro as number | null)}</div>
              </div>
            ) : (
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Dados de colostragem/IgG ainda não lançados. Clique em <strong>Lançar</strong> para preencher.</p>
            )}
          </div>

          <QuadroResumoPartos linhas={ficha.resumo_partos} />

          {ficha.precisao_parto && (
            <div className="card" style={cardStyle}>
              <div className="card-header mb-3">Previsão de parto</div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3" style={{ fontSize: "0.8rem" }}>
                <div><span style={labelStyle}>Última IA</span><br />{ficha.precisao_parto.data_ultima_ia_positiva ? formatDate(ficha.precisao_parto.data_ultima_ia_positiva) : "—"}</div>
                <div><span style={labelStyle}>Último diagnóstico positivo</span><br />{ficha.precisao_parto.data_confirmacao_prenhez ? formatDate(ficha.precisao_parto.data_confirmacao_prenhez) : "—"}</div>
                <div><span style={labelStyle}>Dias de gestação</span><br />{ficha.precisao_parto.dias_gestacao ?? "—"}</div>
                <div><span style={labelStyle}>Data da previsão de parto</span><br />{ficha.precisao_parto.data_parto_provavel ? formatDate(ficha.precisao_parto.data_parto_provavel) : "—"}</div>
                <div><span style={labelStyle}>Faltam</span><br />{ficha.precisao_parto.dias_para_parto != null ? `${ficha.precisao_parto.dias_para_parto} dia(s)` : "—"}</div>
              </div>
            </div>
          )}

          {!!ficha.partos?.length && (
            <SecaoHistoricoTabela chave="partos" titulo="Partos" colunas={SECOES[0].colunas} linhas={formatarLinhas("partos", ficha.partos)} onAbrirCria={buscar} />
          )}

          {!!ficha.gtas?.length && (
            <div className="card" style={cardStyle}>
              <div className="card-header mb-3">GTA(s) do animal</div>
              <div className="flex flex-wrap gap-2">
                {ficha.gtas.map((g) => (
                  <span key={g} style={{ fontSize: "0.78rem", fontWeight: 700, padding: "0.2rem 0.6rem", borderRadius: "999px", background: "rgba(198,162,74,0.15)", color: "var(--dourado-light)" }}>
                    GTA {g}
                  </span>
                ))}
              </div>
            </div>
          )}

          {ficha.compras?.map((c, i) => (
            <div className="card" style={cardStyle} key={`compra-${i}`}>
              <div className="card-header mb-3">Compra{ficha.compras.length > 1 ? ` (${i + 1}/${ficha.compras.length})` : ""}</div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3" style={{ fontSize: "0.8rem" }}>
                <div><span style={labelStyle}>Data</span><br />{formatDate(c.data_compra as string)}</div>
                <div><span style={labelStyle}>Vendedor</span><br />{String(c.vendedor)}</div>
                <div><span style={labelStyle}>Valor</span><br />R$ {String(c.valor)}</div>
                <div><span style={labelStyle}>GTA</span><br />{String(c.gta || "—")}</div>
                <div><span style={labelStyle}>Responsável</span><br />{String(c.responsavel || "—")}</div>
              </div>
            </div>
          ))}

          {ficha.vendas?.map((v, i) => (
            <div className="card" style={cardStyle} key={`venda-${i}`}>
              <div className="card-header mb-3">Venda{ficha.vendas.length > 1 ? ` (${i + 1}/${ficha.vendas.length})` : ""}</div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3" style={{ fontSize: "0.8rem" }}>
                <div><span style={labelStyle}>Data</span><br />{formatDate(v.data_venda as string)}</div>
                <div><span style={labelStyle}>Comprador</span><br />{String(v.comprador)}</div>
                <div><span style={labelStyle}>Valor</span><br />R$ {String(v.valor)}</div>
                <div><span style={labelStyle}>GTA</span><br />{String(v.gta || "—")}</div>
                <div><span style={labelStyle}>Responsável</span><br />{String(v.responsavel || "—")}</div>
              </div>
            </div>
          ))}

          {ficha.baixa && (
            <div className="card" style={{ ...cardStyle, borderColor: "var(--red)" }}>
              <div className="card-header mb-3">Baixa (saída do rebanho)</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ fontSize: "0.8rem" }}>
                <div><span style={labelStyle}>Data</span><br />{formatDate(ficha.baixa.data_baixa as string)}</div>
                <div><span style={labelStyle}>Tipo</span><br />{String(ficha.baixa.tipo_baixa)}</div>
                <div><span style={labelStyle}>Motivo</span><br />{String(ficha.baixa.motivo)}</div>
                <div><span style={labelStyle}>Valor</span><br />{ficha.baixa.valor != null ? `R$ ${ficha.baixa.valor}` : "—"}</div>
              </div>
            </div>
          )}

          {renderSecao("servicos")}

          {renderControleLeiteiro()}

          {CHAVES_SECOES_PRODUCAO.map((chave) => renderSecao(chave))}

          <SecaoRastreabilidadeSanitaria
            linhaTempo={ficha.linha_tempo_sanitaria || []}
            colunasExames={SECOES.find((s) => s.chave === "exames_resultados")!.colunas}
            exames={formatarLinhas("exames_resultados", ficha.exames_resultados || [])}
            colunasDoencas={SECOES.find((s) => s.chave === "ocorrencias_clinicas")!.colunas}
            doencas={formatarLinhas("ocorrencias_clinicas", ficha.ocorrencias_clinicas || [])}
            onAbrirCria={buscar}
          />

          {renderSecao("aplicacoes_sanitarias")}

          {renderSecao("movimentos_lote")}

          {renderSecao("eventos_agenda")}

          {SECOES.every((s) => !((ficha[s.chave] as unknown[]) || []).length) && !ficha.colostragem && !ficha.compra && !ficha.baixa
            && !ficha.compras?.length && !ficha.vendas?.length && !ficha.linha_tempo_sanitaria?.length && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lançamento encontrado para este animal.</p>
          )}
        </>
      )}

      {confirmMae && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 90, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "440px", maxWidth: "95vw" }}>
            <div className="card-header mb-3 flex items-center gap-2"><AlertTriangle size={15} /> Confirmar mãe informada</div>
            {confirmMae.verificacao.parto_correspondente ? (
              <p style={{ fontSize: "0.85rem", marginBottom: "0.6rem" }}>
                Encontramos um parto da mãe {confirmMae.payload.mae_numero} em{" "}
                {formatDate(confirmMae.verificacao.parto_correspondente.data_parto as string)}
                {confirmMae.verificacao.parto_correspondente.ordem_parto ? ` (${confirmMae.verificacao.parto_correspondente.ordem_parto}º parto)` : ""}.
              </p>
            ) : (
              <p style={{ fontSize: "0.85rem", marginBottom: "0.6rem" }}>
                Não encontramos um parto da mãe {confirmMae.payload.mae_numero} próximo da data de nascimento deste animal.
              </p>
            )}
            {confirmMae.verificacao.inconsistencias.map((msg, i) => (
              <p key={i} style={{ fontSize: "0.8rem", color: "var(--amber, #B9831F)", display: "flex", alignItems: "flex-start", gap: "0.4rem", marginBottom: "0.4rem" }}>
                <AlertTriangle size={13} style={{ marginTop: "0.15rem", flexShrink: 0 }} /> {msg}
              </p>
            ))}
            <p style={{ fontSize: "0.8rem", marginTop: "0.4rem" }}>Confirma que deseja salvar assim mesmo?</p>
            <div className="flex items-center gap-3 mt-4">
              <button className="btn-primary" onClick={() => salvarAnimal(confirmMae.payload)} disabled={salvando}>{salvando ? "Salvando…" : "Confirmar e salvar"}</button>
              <button className="btn-ghost" onClick={() => setConfirmMae(null)}>Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
