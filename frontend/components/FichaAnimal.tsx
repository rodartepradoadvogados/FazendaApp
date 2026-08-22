"use client";
import { useEffect, useState } from "react";
import { FileText, AlertTriangle, Download, Pencil, Save, X } from "lucide-react";
import { fetchAnimais, fetchFichaAnimal, formatDate, atualizarAnimalFicha, registrarColostragem, fetchCategoriaSugerida, verificarMaeParto, type VerificacaoMaeParto } from "@/lib/api";
import { exportarFichaPDF, SecaoFicha, ColunaExport } from "@/lib/export";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { SecaoRecolhivel, TabBar } from "@/components/ui";
import { estiloSexado, rotuloOrigemMovimentoLote } from "@/lib/constants";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { CampoMoeda } from "@/components/CampoMoeda";
import { CurvaLactacao, type FaixaReferencia } from "@/components/CurvaLactacao";

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
};

/**
 * Quadro "por parto" — o que se quer ver "se fosse comprar este animal":
 * produção, duração e reprodução de cada lactação, lado a lado. Mais
 * antiga primeiro (mesma ordem de `ficha.resumo_partos`).
 */
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
  ] },
  { chave: "servicos", titulo: "Reprodução — Serviço/IA e diagnóstico", colunas: [
    { header: "Data serviço", key: "data_servicoFmt" }, { header: "Tipo", key: "tipo_servico" }, { header: "Protocolo", key: "protocolo" },
    { header: "Pai (touro/sêmen)", key: "reprodutor" }, { header: "NAAB do pai", key: "reprodutor_naab" },
    { header: "Central do pai", key: "touro_central" }, { header: "TPI do pai", key: "touro_tpi" }, { header: "NM$ do pai", key: "touro_nm" },
    { header: "Ordem de parto (na IA)", key: "ordem_parto_na_ia" }, { header: "Tentativa", key: "ordem_tentativa" },
    { header: "Data diagnóstico", key: "data_diagnosticoFmt" }, { header: "Diagnóstico", key: "diagnostico" },
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
    // Rótulo amigável da origem (manual/sugestão confirmada/automática/passiva)
    // — badge só de leitura na Ficha, mantendo o valor bruto para ordenação.
    if (chave === "movimentos_lote") nova.origemFmt = rotuloOrigemMovimentoLote(l.origem);
    return nova;
  });
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
function SecaoHistoricoTabela({ chave, titulo, colunas, linhas, onAbrirCria }: {
  chave: string; titulo: string; colunas: ColunaExport[]; linhas: Record<string, unknown>[]; onAbrirCria: (numero: string) => void;
}) {
  const ord = useOrdenacao(linhas);
  return (
    <SecaoRecolhivel titulo={titulo} badge={String(linhas.length)}>
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
    </SecaoRecolhivel>
  );
}

// Controle leiteiro: a mesma seção, em duas leituras — a tabela (o dado bruto,
// linha a linha) e a curva de lactação (a forma da lactação ao longo do DEL,
// comparada com a média do rebanho). São perguntas diferentes sobre os mesmos
// números: "o que foi medido?" e "isto está bom?".
function SecaoControleLeiteiro({ colunas, linhas, brutas, referencia, onAbrirCria }: {
  colunas: ColunaExport[];
  linhas: Record<string, unknown>[];
  brutas: Record<string, unknown>[];
  referencia?: FaixaReferencia[];
  onAbrirCria: (numero: string) => void;
}) {
  const [aba, setAba] = useState<"tabela" | "curva">("tabela");
  const ord = useOrdenacao(linhas);

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
      {aba === "curva" ? (
        <CurvaLactacao pontos={pontos} referencia={referencia} />
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

  const ordLinhaTempo = useOrdenacao(ficha?.linha_tempo_sanitaria ?? []);

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
    const secoes: SecaoFicha[] = SECOES
      .map((s) => ({ titulo: s.titulo, colunas: s.colunas, linhas: formatarLinhas(s.chave, (ficha[s.chave] as Record<string, unknown>[]) || []) }));
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
            <div style={{ marginTop: "0.85rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border)", display: "grid", gridTemplateColumns: "repeat(3, minmax(120px, 1fr))", gap: "0.75rem", fontSize: "0.8rem" }}>
              <div><span style={labelStyle}>Dias de gestação</span><br />{ficha.precisao_parto?.dias_gestacao ?? "—"}</div>
              <div><span style={labelStyle}>DEL atual</span><br />{a.del_dias != null ? String(a.del_dias) : "—"}</div>
              <div><span style={labelStyle}>Previsão de parto</span><br />{ficha.precisao_parto?.data_parto_provavel ? formatDate(ficha.precisao_parto.data_parto_provavel) : "—"}</div>
            </div>
          </div>

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

          <QuadroResumoPartos linhas={ficha.resumo_partos} />

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

          {!!ficha.linha_tempo_sanitaria?.length && (
            <SecaoRecolhivel titulo="Rastreabilidade sanitária — linha do tempo" badge={String(ficha.linha_tempo_sanitaria.length)}>
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
            </SecaoRecolhivel>
          )}

          {SECOES.filter((s) => s.chave !== "partos").map((s) => {
            const linhasBrutas = (ficha[s.chave] as Record<string, unknown>[]) || [];
            if (!linhasBrutas.length) return null;
            const linhas = formatarLinhas(s.chave, linhasBrutas);
            // Controle leiteiro ganha a alternância tabela ↔ curva de lactação.
            if (s.chave === "controles_leiteiros") {
              return (
                <SecaoControleLeiteiro key={s.chave} colunas={s.colunas} linhas={linhas}
                  brutas={linhasBrutas} referencia={ficha.curva_referencia_rebanho} onAbrirCria={buscar} />
              );
            }
            return (
              <SecaoHistoricoTabela key={s.chave} chave={s.chave} titulo={s.titulo} colunas={s.colunas} linhas={linhas} onAbrirCria={buscar} />
            );
          })}

          {SECOES.every((s) => !((ficha[s.chave] as unknown[]) || []).length) && !ficha.colostragem && !ficha.compra && !ficha.baixa
            && !ficha.compras?.length && !ficha.vendas?.length && (
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
