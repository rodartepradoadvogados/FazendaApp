"use client";
import { useEffect, useState } from "react";
import { FileText, AlertTriangle, Download } from "lucide-react";
import { fetchAnimais, fetchFichaAnimal, formatDate } from "@/lib/api";
import { exportarFichaPDF, SecaoFicha, ColunaExport } from "@/lib/export";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { SecaoRecolhivel } from "@/components/ui";

type Ficha = {
  animal: Record<string, unknown>;
  partos: Record<string, unknown>[];
  servicos: Record<string, unknown>[];
  protocolos_iatf: Record<string, unknown>[];
  movimentos_lote: Record<string, unknown>[];
  colostragem: Record<string, unknown> | null;
  controles_leiteiros: Record<string, unknown>[];
  pesagens_corporais: Record<string, unknown>[];
  qualidade_leite: Record<string, unknown>[];
  aplicacoes_sanitarias: Record<string, unknown>[];
  protocolos_sanitarios: Record<string, unknown>[];
  secagens: Record<string, unknown>[];
  eventos_agenda: Record<string, unknown>[];
  baixa: Record<string, unknown> | null;
  compra: Record<string, unknown> | null;
};

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
    { header: "Sexo cria 1", key: "sexo_cria_1" }, { header: "Sexo cria 2", key: "sexo_cria_2" },
    { header: "Gemelar?", key: "gemelar" }, { header: "Retenção de placenta?", key: "retencao_placenta" },
  ] },
  { chave: "servicos", titulo: "Reprodução — Serviço/IA e diagnóstico", colunas: [
    { header: "Data serviço", key: "data_servicoFmt" }, { header: "Tipo", key: "tipo_servico" }, { header: "Protocolo", key: "protocolo" },
    { header: "Reprodutor", key: "reprodutor" }, { header: "Tentativa", key: "ordem_tentativa" },
    { header: "Data diagnóstico", key: "data_diagnosticoFmt" }, { header: "Diagnóstico", key: "diagnostico" },
  ] },
  { chave: "protocolos_iatf", titulo: "Protocolo IATF (D0/D7/D9/D11)", colunas: [
    { header: "Dia", key: "dia" }, { header: "Descrição", key: "descricao" }, { header: "Data prevista", key: "data_previstaFmt" },
    { header: "Realizada?", key: "realizada" }, { header: "Data realização", key: "data_realizacaoFmt" },
  ] },
  { chave: "movimentos_lote", titulo: "Movimentação de lote", colunas: [
    { header: "Data", key: "data_movimentoFmt" }, { header: "Lote origem", key: "lote_origem" }, { header: "Lote destino", key: "lote_destino" },
    { header: "Motivo", key: "motivo" }, { header: "Responsável", key: "responsavel" },
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
  { chave: "eventos_agenda", titulo: "Agenda — eventos manuais", colunas: [
    { header: "Data", key: "data_eventoFmt" }, { header: "Descrição", key: "descricao" }, { header: "Categoria", key: "categoria" },
    { header: "Tipo", key: "tipo_evento" },
  ] },
];

const DATA_KEYS: Record<string, string> = {
  partos: "data_parto", servicos: "data_servico", protocolos_iatf: "data_prevista", movimentos_lote: "data_movimento",
  controles_leiteiros: "data_controle", pesagens_corporais: "data_pesagem", qualidade_leite: "data_coleta",
  aplicacoes_sanitarias: "data_aplicacao", protocolos_sanitarios: "data_inicio", secagens: "data_secagem", eventos_agenda: "data_evento",
};
const DATA_KEYS_EXTRA: Record<string, string[]> = {
  servicos: ["data_diagnostico"], protocolos_iatf: ["data_realizacao"],
};

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
    return nova;
  });
}

const cardStyle: React.CSSProperties = { marginBottom: "1rem" };
const labelStyle: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)" };

export default function FichaAnimal() {
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [numero, setNumero] = useState("");
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);

  useEffect(() => { fetchAnimais({ incluirMachos: true }).then(setAnimais).catch(() => {}); }, []);

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

  async function exportarPDF() {
    if (!ficha) return;
    const secoes: SecaoFicha[] = SECOES
      .map((s) => ({ titulo: s.titulo, colunas: s.colunas, linhas: formatarLinhas(s.chave, (ficha[s.chave] as Record<string, unknown>[]) || []) }));
    await exportarFichaPDF(
      `Ficha do animal ${numero}`,
      `${ficha.animal.nome ? `${ficha.animal.nome} — ` : ""}${ficha.animal.categoria_abrev || ""} · Lote ${ficha.animal.grupo_primario || "—"}`,
      secoes,
      `ficha_animal_${numero}`,
    );
  }

  const a = ficha?.animal;

  return (
    <div className="p-6">
      <div className="card mb-4">
        <div className="card-header mb-3 flex items-center gap-2"><FileText size={16} /> Ficha do animal</div>
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
          Todos os lançamentos já registrados para o animal escolhido — reprodução, partos, colostragem/IgG,
          produção, sanidade, movimentação de lote, compra/baixa e agenda — reunidos em uma única ficha.
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
          <div className="card" style={cardStyle}>
            <div className="card-header mb-3 flex items-center justify-between">
              <span>{String(a.nome || a.numero)} <span style={{ color: "var(--dourado-light)", fontWeight: 400 }}>(nº {String(a.numero)})</span></span>
              <button className="btn-primary" style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.35rem" }} onClick={exportarPDF}>
                <Download size={13} /> Exportar PDF (ficha completa)
              </button>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ fontSize: "0.8rem" }}>
              <div><span style={labelStyle}>Sexo</span><br />{a.sexo === "M" ? "Macho" : a.sexo === "F" ? "Fêmea" : "—"}</div>
              <div><span style={labelStyle}>Categoria</span><br />{String(a.categoria_abrev || a.categoria_completa || "—")}</div>
              <div><span style={labelStyle}>Lote atual</span><br />{String(a.grupo_primario || "—")}</div>
              <div><span style={labelStyle}>Data de nascimento</span><br />{a.data_nasc ? formatDate(a.data_nasc as string) : "—"}</div>
              <div><span style={labelStyle}>Mãe</span><br />{String(a.mae_numero || "—")}</div>
              <div><span style={labelStyle}>Raça</span><br />{String(a.raca || "—")}</div>
              <div><span style={labelStyle}>Situação</span><br />{a.ativo ? "Ativo" : "Baixado"}</div>
              <div><span style={labelStyle}>Data de entrada</span><br />{a.data_entrada ? formatDate(a.data_entrada as string) : "—"}</div>
            </div>
          </div>

          {ficha.colostragem && (
            <div className="card" style={cardStyle}>
              <div className="card-header mb-3">Colostragem e teste de sangue (IgG)</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ fontSize: "0.8rem" }}>
                <div><span style={labelStyle}>Tomou colostro?</span><br />{ficha.colostragem.tomou_colostro == null ? "—" : ficha.colostragem.tomou_colostro ? "Sim" : "Não"}</div>
                <div><span style={labelStyle}>Litros</span><br />{String(ficha.colostragem.litros_colostro ?? "—")}</div>
                <div><span style={labelStyle}>Brix colostro (%)</span><br />{String(ficha.colostragem.brix_colostro ?? "—")} — {classeColostro(ficha.colostragem.brix_colostro as number | null)}</div>
                <div><span style={labelStyle}>Brix soro (%)</span><br />{String(ficha.colostragem.brix_soro ?? "—")} — {classeSoro(ficha.colostragem.brix_soro as number | null)}</div>
              </div>
            </div>
          )}

          {ficha.compra && (
            <div className="card" style={cardStyle}>
              <div className="card-header mb-3">Compra</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ fontSize: "0.8rem" }}>
                <div><span style={labelStyle}>Data</span><br />{formatDate(ficha.compra.data_compra as string)}</div>
                <div><span style={labelStyle}>Vendedor</span><br />{String(ficha.compra.vendedor)}</div>
                <div><span style={labelStyle}>Valor</span><br />R$ {String(ficha.compra.valor)}</div>
                <div><span style={labelStyle}>Responsável</span><br />{String(ficha.compra.responsavel || "—")}</div>
              </div>
            </div>
          )}

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

          {SECOES.map((s) => {
            const linhasBrutas = (ficha[s.chave] as Record<string, unknown>[]) || [];
            if (!linhasBrutas.length) return null;
            const linhas = formatarLinhas(s.chave, linhasBrutas);
            return (
              <SecaoRecolhivel key={s.chave} titulo={s.titulo} badge={String(linhas.length)}>
                <div className="overflow-x-auto">
                  <table className="fazenda-table">
                    <thead><tr>{s.colunas.map((c) => <th key={c.key}>{c.header}</th>)}</tr></thead>
                    <tbody>
                      {linhas.map((l, i) => (
                        <tr key={i}>{s.colunas.map((c) => <td key={c.key} style={{ fontSize: "0.78rem" }}>{String(l[c.key] ?? "—")}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </SecaoRecolhivel>
            );
          })}

          {SECOES.every((s) => !((ficha[s.chave] as unknown[]) || []).length) && !ficha.colostragem && !ficha.compra && !ficha.baixa && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhum lançamento encontrado para este animal.</p>
          )}
        </>
      )}
    </div>
  );
}
