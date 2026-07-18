"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ClipboardList, RefreshCw, AlertTriangle, Hourglass, Syringe, CalendarClock,
  Stethoscope, HeartPulse, MilkOff, Baby, FlaskConical,
} from "lucide-react";
import { fetchRelatoriosManejo } from "@/lib/api";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import { SecaoRecolhivel } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { estiloSexado } from "@/lib/constants";

/**
 * RelatoriosManejo — listas de trabalho diárias da reprodução (PEV, a inseminar,
 * inseminados, toque/reconfirmação, prenhes, secagem, previsão de partos e
 * estoque de sêmen). Cada lista já vem ordenada pelo backend (vermelho primeiro)
 * e recebe um "semáforo" (bolinha colorida) segundo a urgência de manejo.
 */

// ── Tipos da resposta de GET /relatorios/manejo ──
type Cor = "vermelho" | "amarelo" | "verde" | "branco" | null;
type Parametros = {
  pev: number; meta_1a_ia: number; dias_toque: number; dias_reconfirmacao: number; periodo_seco: number;
};
type Pev = { numero: string | number; grupo: string; dias_pos_parto: number; data_parto: string | null; cor: Cor };
type AInseminar = { numero: string | number; grupo: string; dias_pos_parto: number; eh_vaca: boolean; situacao: string; cor: Cor };
type Inseminado = { numero: string | number; grupo: string; dias_inseminada: number; data_ultima_ia: string | null; touro: string; tipo: string; cor_dias: Cor; cor_cio: Cor; cor: Cor };
type ATocar = { numero: string | number; grupo: string; dias_inseminada: number; touro: string; cor: Cor };
type AReconfirmar = { numero: string | number; grupo: string; dias_inseminada: number; cor: Cor };
type Prenhe = { numero: string | number; grupo: string; dias_gestacao: number; dpp_concepcao: number; previsao_parto: string | null; reconfirmada: boolean; cor: Cor };
type Secagem = { numero: string | number; grupo: string; dias_para_secagem: number; previsao_secagem: string | null; luzes: number; cor: Cor };
type PrevisaoParto = { numero: string | number; grupo: string; dias_para_parto: number; previsao_parto: string | null; dias_gestacao: number; luzes: number; cor: Cor };
type EstoqueSemen = { touro_nome: string; codigo: string | null; central: string | null; tipo: string; doses: number; cor: Cor };

type RespManejo = {
  parametros: Parametros;
  pev: Pev[];
  a_inseminar: AInseminar[];
  inseminados: Inseminado[];
  a_tocar: ATocar[];
  a_reconfirmar: AReconfirmar[];
  prenhes: Prenhe[];
  secagem: Secagem[];
  previsao_partos: PrevisaoParto[];
  estoque_semen: EstoqueSemen[];
};

// ── Helpers ──
// Formata uma data ISO ("2026-07-10") em DD/MM/YYYY sem sofrer com fuso horário.
function fmtData(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (!y || !m || !d) return "—";
  return `${d}/${m}/${y}`;
}

// Cor do semáforo → variável de CSS do tema.
function corVar(cor: Cor): string {
  switch (cor) {
    case "vermelho": return "var(--red)";
    case "amarelo": return "var(--amber)";
    case "verde": return "var(--green-light)";
    case "branco": return "#e8e8e8";
    default: return "var(--text-muted)";
  }
}

// Bolinha ● colorida pelo semáforo; sem cor definida vira travessão.
function Dot({ cor }: { cor: Cor }) {
  if (!cor) return <span style={{ color: "var(--text-muted)" }}>—</span>;
  return <span aria-hidden style={{ color: corVar(cor), fontSize: "0.9rem", lineHeight: 1 }}>●</span>;
}

// Semáforo com "luzes": vermelho + 2 luzes = duas bolinhas (já passou do prazo).
function DotsLuzes({ cor, luzes }: { cor: Cor; luzes: number }) {
  if (cor === "vermelho" && luzes >= 1) {
    return (
      <span aria-hidden style={{ color: "var(--red)", fontSize: "0.9rem", lineHeight: 1, letterSpacing: "1px" }}>
        {"●".repeat(Math.min(luzes, 2))}
      </span>
    );
  }
  return <Dot cor={cor} />;
}

// Conta quantos vermelho / amarelo / verde há numa lista (campo "cor" por padrão).
function contar(linhas: { cor?: Cor }[]): { v: number; a: number; g: number } {
  let v = 0, a = 0, g = 0;
  for (const l of linhas) {
    if (l.cor === "vermelho") v++;
    else if (l.cor === "amarelo") a++;
    else if (l.cor === "verde") g++;
  }
  return { v, a, g };
}

// Badge do cabeçalho: três bolinhas coloridas com a contagem de cada cor.
function BadgeCores({ linhas }: { linhas: { cor?: Cor }[] }) {
  const { v, a, g } = contar(linhas);
  const item = (color: string, n: number, titulo: string) => (
    <span title={titulo} style={{ display: "inline-flex", alignItems: "center", gap: "0.2rem", fontSize: "0.72rem", color: "var(--text-muted)" }}>
      <span aria-hidden style={{ color, fontSize: "0.85rem", lineHeight: 1 }}>●</span>{n}
    </span>
  );
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.6rem", whiteSpace: "nowrap" }}>
      {item("var(--red)", v, "Vermelho")}
      {item("var(--amber)", a, "Amarelo")}
      {item("var(--green-light)", g, "Verde")}
    </span>
  );
}

// Definição de coluna da tabela de manejo.
// `campo` (opcional): chave do objeto de linha pela qual ordenar ao clicar no
// cabeçalho. Colunas sem `campo` (semáforo, colunas puramente derivadas) ficam
// como <th> comum, não clicável.
type Col = { header: string; campo?: string; render: (row: any) => React.ReactNode; style?: React.CSSProperties };

// Tabela padrão de manejo: 1ª coluna é o semáforo (bolinha por `cor`), demais são as colunas passadas.
function TabelaManejo({
  colunas, linhas, corKey = "cor", renderDot, rowStyle,
}: {
  colunas: Col[];
  linhas: any[];
  corKey?: string;
  renderDot?: (row: any) => React.ReactNode;
  rowStyle?: (row: any) => React.CSSProperties | undefined;
}) {
  const dotDe = renderDot || ((row: any) => <Dot cor={row[corKey]} />);
  const { linhasOrdenadas, coluna, dir, ordenar } = useOrdenacao(linhas);
  return (
    <div className="overflow-x-auto">
      <table className="fazenda-table" style={{ margin: 0 }}>
        <thead>
          <tr>
            <th style={{ width: "1.6rem", textAlign: "center" }} title="Semáforo de manejo"></th>
            {colunas.map((c) =>
              c.campo ? (
                <ThOrdenavel key={c.header} label={c.header} campo={c.campo} coluna={coluna} dir={dir} ordenar={ordenar} />
              ) : (
                <th key={c.header}>{c.header}</th>
              )
            )}
          </tr>
        </thead>
        <tbody>
          {linhasOrdenadas.map((row, i) => (
            <tr key={`${row.numero ?? row.touro_nome ?? "l"}-${i}`} style={rowStyle?.(row)}>
              <td style={{ textAlign: "center" }}>{dotDe(row)}</td>
              {colunas.map((c) => <td key={c.header} style={c.style}>{c.render(row)}</td>)}
            </tr>
          ))}
          {linhasOrdenadas.length === 0 && (
            <tr>
              <td colSpan={colunas.length + 1} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>
                Nenhum animal nesta lista.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// Parágrafo de descrição da seção (também usado como tooltip via `descricao`).
function DescParagrafo({ texto }: { texto: string }) {
  return (
    <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", lineHeight: 1.5, margin: "0 0 0.85rem" }}>
      {texto}
    </p>
  );
}

// Barra superior do corpo com os botões de exportação alinhados à direita.
function BarraExport(props: { titulo: string; nomeArquivoBase: string; colunas: { header: string; key: string }[]; linhas: Record<string, unknown>[] }) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.6rem" }}>
      <ExportarBotoes {...props} />
    </div>
  );
}

const estiloNum: React.CSSProperties = { fontWeight: 700 };
const estiloMudo: React.CSSProperties = { color: "var(--text-muted)", fontSize: "0.8rem" };

// ── Descrições (verbatim) de cada seção ──
const DESC = {
  pev: "Vacas que ainda estão dentro do PEV de 45 dias e portanto não devem ser inseminadas — ajuda no manejo pós-parto e exames ginecológicos. VERMELHO: 0 a 14 dias pós-parto (atenção a enfermidades puerperais). AMARELO: 15 a 29 dias. VERDE: 30 dias até o fim do PEV, aguardando liberação para inseminar.",
  aInseminar: "Vacas aptas a inseminar a qualquer cio. VERDE: terminaram o PEV de 45 dias. AMARELO: faltam 15 dias ou menos para a meta de 100 dias para 1ª IA. VERMELHO: já passaram a meta de 100 dias sem inseminar, ou foram inseminadas e confirmadas vazias.",
  inseminados: "Coluna Dias de Inseminada — VERDE: recém-inseminadas (sem tempo para diagnóstico). AMARELO: dentro do período ideal de toque (30 a 60 dias). VERMELHO: ultrapassaram o prazo do diagnóstico. Coluna Cio Provável — AMARELO: 16/17 ou 25/26 dias após a IA (podem retornar ao cio). VERMELHO: 18 a 24 dias (maior probabilidade de retorno).",
  toque: "Vacas e novilhas a diagnosticar (toque, a partir de 30 dias de inseminada) ou a reconfirmar a prenhez. AMARELO: passou o período de toque mas ainda dentro do prazo da visita do veterinário. VERMELHO: já deveria ter sido tocada ou reconfirmada.",
  prenhes: "VERDE: emprenharam até 150 dias após o parto. AMARELO: entre 151 e 300 dias. VERMELHO: acima de 300 dias. BRANCO: novilhas.",
  secagem: "VERDE: faltam mais de 15 dias para secar. AMARELO: entre 8 e 15 dias. VERMELHO: uma semana ou menos (uma luz) ou já deveria ter secado (duas luzes).",
  previsaoPartos: "Lista vacas e novilhas com prenhez reconfirmada e mais de 200 dias de gestação. VERDE: faltam mais de 15 dias para parir. AMARELO: entre 8 e 15 dias. VERMELHO: uma semana ou menos (uma luz) ou já deveria ter parido (duas luzes).",
  estoque: "Convencional — VERMELHO: menos de 15 doses. AMARELO: 15 a 25. VERDE: mais de 25. Sexado — VERMELHO: menos de 5. AMARELO: 5 a 15. VERDE: mais de 15. Cadastre os touros e as doses em Configurações → Cadastro → Estoque de sêmen.",
};

export default function RelatoriosManejo() {
  const [dados, setDados] = useState<RespManejo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const carregar = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchRelatoriosManejo()
      .then((d: RespManejo) => setDados(d))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  const p = dados?.parametros;
  const linhaParametros = useMemo(() => {
    if (!p) return null;
    return `PEV ${p.pev}d · Meta 1ª IA ${p.meta_1a_ia}d · Toque ${p.dias_toque}d · Período seco ${p.periodo_seco}d`;
  }, [p]);

  return (
    <div className="p-6 animate-in">
      {/* Cabeçalho */}
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ClipboardList size={22} style={{ color: "var(--dourado-light)" }} />
            Listas de Trabalho
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Listas de trabalho da reprodução com semáforo de urgência — clique em cada seção para expandir.
          </p>
        </div>
        <button
          type="button"
          className="btn-ghost"
          onClick={carregar}
          title="Recarregar"
          style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Parâmetros em uso */}
      {linhaParametros && (
        <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "1rem" }}>
          {linhaParametros}
        </p>
      )}

      {/* Erro / carregando */}
      {error && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>Não foi possível carregar os relatórios de manejo: {error}</span>
        </div>
      )}
      {loading && !dados && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {dados && (
        <>
          {/* 1) Vacas no PEV */}
          <SecaoRecolhivel
            titulo="Vacas no PEV (período de espera voluntária)"
            icon={Hourglass}
            descricao={DESC.pev}
            badge={<BadgeCores linhas={dados.pev} />}
          >
            <BarraExport
              titulo="Vacas no PEV"
              nomeArquivoBase="manejo_pev"
              colunas={[
                { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
                { header: "Dias pós-parto", key: "dias_pos_parto" }, { header: "Data do parto", key: "data_parto" },
              ]}
              linhas={dados.pev.map((r) => ({ numero: r.numero, grupo: r.grupo, dias_pos_parto: r.dias_pos_parto, data_parto: fmtData(r.data_parto) }))}
            />
            <DescParagrafo texto={DESC.pev} />
            <TabelaManejo
              linhas={dados.pev}
              colunas={[
                { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
                { header: "Grupo", campo: "grupo", render: (r) => r.grupo, style: estiloMudo },
                { header: "Dias pós-parto", campo: "dias_pos_parto", render: (r) => r.dias_pos_parto },
                { header: "Data do parto", campo: "data_parto", render: (r) => fmtData(r.data_parto) },
              ]}
            />
          </SecaoRecolhivel>

          {/* 2) Vacas a inseminar */}
          <SecaoRecolhivel
            titulo="Vacas a inseminar"
            icon={Syringe}
            descricao={DESC.aInseminar}
            badge={<BadgeCores linhas={dados.a_inseminar} />}
          >
            <BarraExport
              titulo="Vacas a inseminar"
              nomeArquivoBase="manejo_a_inseminar"
              colunas={[
                { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
                { header: "Dias pós-parto", key: "dias_pos_parto" }, { header: "Situação", key: "situacao" },
              ]}
              linhas={dados.a_inseminar.map((r) => ({ numero: r.numero, grupo: r.grupo, dias_pos_parto: r.dias_pos_parto, situacao: r.situacao }))}
            />
            <DescParagrafo texto={DESC.aInseminar} />
            <TabelaManejo
              linhas={dados.a_inseminar}
              colunas={[
                { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
                { header: "Grupo", campo: "grupo", render: (r) => r.grupo, style: estiloMudo },
                { header: "Dias pós-parto", campo: "dias_pos_parto", render: (r) => r.dias_pos_parto },
                { header: "Situação", campo: "situacao", render: (r) => r.situacao },
              ]}
            />
          </SecaoRecolhivel>

          {/* 3) Animais inseminados */}
          <SecaoRecolhivel
            titulo="Animais inseminados"
            icon={CalendarClock}
            descricao={DESC.inseminados}
            badge={<BadgeCores linhas={dados.inseminados} />}
          >
            <BarraExport
              titulo="Animais inseminados"
              nomeArquivoBase="manejo_inseminados"
              colunas={[
                { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
                { header: "Dias de inseminada", key: "dias_inseminada" }, { header: "Última IA/cobertura", key: "data_ultima_ia" },
                { header: "Touro", key: "touro" }, { header: "Tipo", key: "tipo" },
              ]}
              linhas={dados.inseminados.map((r) => ({ numero: r.numero, grupo: r.grupo, dias_inseminada: r.dias_inseminada, data_ultima_ia: fmtData(r.data_ultima_ia), touro: r.touro, tipo: r.tipo }))}
            />
            <DescParagrafo texto={DESC.inseminados} />
            {/* A bolinha principal usa `cor` (= cor_dias); há uma coluna extra de semáforo para o Cio provável (cor_cio). */}
            <TabelaManejo
              linhas={dados.inseminados}
              rowStyle={(r) => estiloSexado(r.tipo_semen)}
              colunas={[
                { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
                { header: "Grupo", campo: "grupo", render: (r) => r.grupo, style: estiloMudo },
                { header: "Dias de inseminada", campo: "dias_inseminada", render: (r) => r.dias_inseminada },
                { header: "Última IA/cobertura", campo: "data_ultima_ia", render: (r) => fmtData(r.data_ultima_ia), style: estiloMudo },
                { header: "Touro", campo: "touro", render: (r) => r.touro || "—", style: { fontWeight: 600 } },
                { header: "Tipo", campo: "tipo", render: (r) => r.tipo || "—", style: estiloMudo },
                { header: "Cio provável", render: (r) => <Dot cor={r.cor_cio} />, style: { textAlign: "center" } },
              ]}
            />
          </SecaoRecolhivel>

          {/* 4) Toque e confirmação (duas sub-tabelas) */}
          <SecaoRecolhivel
            titulo="Toque e confirmação"
            icon={Stethoscope}
            descricao={DESC.toque}
            badge={<BadgeCores linhas={[...dados.a_tocar, ...dados.a_reconfirmar]} />}
          >
            <DescParagrafo texto={DESC.toque} />

            {/* A tocar */}
            <div className="card-header" style={{ fontSize: "0.85rem", margin: "0.25rem 0 0.5rem" }}>A tocar</div>
            <BarraExport
              titulo="Toque e confirmação — A tocar"
              nomeArquivoBase="manejo_a_tocar"
              colunas={[
                { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
                { header: "Dias de inseminada", key: "dias_inseminada" }, { header: "Touro", key: "touro" },
              ]}
              linhas={dados.a_tocar.map((r) => ({ numero: r.numero, grupo: r.grupo, dias_inseminada: r.dias_inseminada, touro: r.touro }))}
            />
            <TabelaManejo
              linhas={dados.a_tocar}
              colunas={[
                { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
                { header: "Grupo", campo: "grupo", render: (r) => r.grupo, style: estiloMudo },
                { header: "Dias de inseminada", campo: "dias_inseminada", render: (r) => r.dias_inseminada },
                { header: "Touro", campo: "touro", render: (r) => r.touro || "—", style: { fontWeight: 600 } },
              ]}
            />

            {/* A reconfirmar */}
            <div className="card-header" style={{ fontSize: "0.85rem", margin: "1rem 0 0.5rem" }}>A reconfirmar</div>
            <BarraExport
              titulo="Toque e confirmação — A reconfirmar"
              nomeArquivoBase="manejo_a_reconfirmar"
              colunas={[
                { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" }, { header: "Dias", key: "dias_inseminada" },
              ]}
              linhas={dados.a_reconfirmar.map((r) => ({ numero: r.numero, grupo: r.grupo, dias_inseminada: r.dias_inseminada }))}
            />
            <TabelaManejo
              linhas={dados.a_reconfirmar}
              colunas={[
                { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
                { header: "Grupo", campo: "grupo", render: (r) => r.grupo, style: estiloMudo },
                { header: "Dias", campo: "dias_inseminada", render: (r) => r.dias_inseminada },
              ]}
            />
          </SecaoRecolhivel>

          {/* 5) Animais prenhes */}
          <SecaoRecolhivel
            titulo="Animais prenhes"
            icon={HeartPulse}
            descricao={DESC.prenhes}
            badge={<BadgeCores linhas={dados.prenhes} />}
          >
            <BarraExport
              titulo="Animais prenhes"
              nomeArquivoBase="manejo_prenhes"
              colunas={[
                { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
                { header: "Dias de gestação", key: "dias_gestacao" }, { header: "Dias pós-parto na concepção", key: "dpp_concepcao" },
                { header: "Previsão de parto", key: "previsao_parto" }, { header: "Reconfirmada", key: "reconfirmada" },
              ]}
              linhas={dados.prenhes.map((r) => ({
                numero: r.numero, grupo: r.grupo, dias_gestacao: r.dias_gestacao, dpp_concepcao: r.dpp_concepcao,
                previsao_parto: fmtData(r.previsao_parto), reconfirmada: r.reconfirmada ? "Sim" : "Não",
              }))}
            />
            <DescParagrafo texto={DESC.prenhes} />
            <TabelaManejo
              linhas={dados.prenhes}
              colunas={[
                { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
                { header: "Grupo", campo: "grupo", render: (r) => r.grupo, style: estiloMudo },
                { header: "Dias de gestação", campo: "dias_gestacao", render: (r) => r.dias_gestacao },
                { header: "Dias pós-parto na concepção", campo: "dpp_concepcao", render: (r) => r.dpp_concepcao },
                { header: "Previsão de parto", campo: "previsao_parto", render: (r) => fmtData(r.previsao_parto) },
                { header: "Reconfirmada", campo: "reconfirmada", render: (r) => (r.reconfirmada ? "Sim" : "Não") },
              ]}
            />
          </SecaoRecolhivel>

          {/* 6) Secagem */}
          <SecaoRecolhivel
            titulo="Secagem"
            icon={MilkOff}
            descricao={DESC.secagem}
            badge={<BadgeCores linhas={dados.secagem} />}
          >
            <BarraExport
              titulo="Secagem"
              nomeArquivoBase="manejo_secagem"
              colunas={[
                { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
                { header: "Dias para secagem", key: "dias_para_secagem" }, { header: "Previsão de secagem", key: "previsao_secagem" },
              ]}
              linhas={dados.secagem.map((r) => ({ numero: r.numero, grupo: r.grupo, dias_para_secagem: r.dias_para_secagem, previsao_secagem: fmtData(r.previsao_secagem) }))}
            />
            <DescParagrafo texto={DESC.secagem} />
            <TabelaManejo
              linhas={dados.secagem}
              renderDot={(r) => <DotsLuzes cor={r.cor} luzes={r.luzes} />}
              colunas={[
                { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
                { header: "Grupo", campo: "grupo", render: (r) => r.grupo, style: estiloMudo },
                { header: "Dias para secagem", campo: "dias_para_secagem", render: (r) => r.dias_para_secagem },
                { header: "Previsão de secagem", campo: "previsao_secagem", render: (r) => fmtData(r.previsao_secagem) },
              ]}
            />
          </SecaoRecolhivel>

          {/* 7) Previsão de partos */}
          <SecaoRecolhivel
            titulo="Previsão de partos"
            icon={Baby}
            descricao={DESC.previsaoPartos}
            badge={<BadgeCores linhas={dados.previsao_partos} />}
          >
            <BarraExport
              titulo="Previsão de partos"
              nomeArquivoBase="manejo_previsao_partos"
              colunas={[
                { header: "Nº", key: "numero" }, { header: "Grupo", key: "grupo" },
                { header: "Dias para parir", key: "dias_para_parto" }, { header: "Previsão de parto", key: "previsao_parto" },
                { header: "Dias de gestação", key: "dias_gestacao" },
              ]}
              linhas={dados.previsao_partos.map((r) => ({
                numero: r.numero, grupo: r.grupo, dias_para_parto: r.dias_para_parto,
                previsao_parto: fmtData(r.previsao_parto), dias_gestacao: r.dias_gestacao,
              }))}
            />
            <DescParagrafo texto={DESC.previsaoPartos} />
            <TabelaManejo
              linhas={dados.previsao_partos}
              renderDot={(r) => <DotsLuzes cor={r.cor} luzes={r.luzes} />}
              colunas={[
                { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
                { header: "Grupo", campo: "grupo", render: (r) => r.grupo, style: estiloMudo },
                { header: "Dias para parir", campo: "dias_para_parto", render: (r) => r.dias_para_parto },
                { header: "Previsão de parto", campo: "previsao_parto", render: (r) => fmtData(r.previsao_parto) },
                { header: "Dias de gestação", campo: "dias_gestacao", render: (r) => r.dias_gestacao },
              ]}
            />
          </SecaoRecolhivel>

          {/* 8) Estoque de sêmen */}
          <SecaoRecolhivel
            titulo="Estoque de sêmen"
            icon={FlaskConical}
            descricao={DESC.estoque}
            badge={<BadgeCores linhas={dados.estoque_semen} />}
          >
            <DescParagrafo texto={DESC.estoque} />
            {dados.estoque_semen.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", padding: "0.5rem 0" }}>
                Nenhum touro cadastrado. Cadastre os touros e as doses em Configurações → Cadastro → Estoque de sêmen.
              </p>
            ) : (
              <>
                <BarraExport
                  titulo="Estoque de sêmen"
                  nomeArquivoBase="manejo_estoque_semen"
                  colunas={[
                    { header: "Touro", key: "touro_nome" }, { header: "Código", key: "codigo" },
                    { header: "Central", key: "central" }, { header: "Tipo", key: "tipo" }, { header: "Doses", key: "doses" },
                  ]}
                  linhas={dados.estoque_semen.map((r) => ({
                    touro_nome: r.touro_nome, codigo: r.codigo ?? "—", central: r.central ?? "—",
                    tipo: r.tipo === "sexado" ? "Sexado" : "Convencional", doses: r.doses,
                  }))}
                />
                <TabelaManejo
                  linhas={dados.estoque_semen}
                  colunas={[
                    { header: "Touro", campo: "touro_nome", render: (r) => r.touro_nome, style: estiloNum },
                    { header: "Código", campo: "codigo", render: (r) => r.codigo || "—", style: estiloMudo },
                    { header: "Central", campo: "central", render: (r) => r.central || "—", style: estiloMudo },
                    { header: "Tipo", campo: "tipo", render: (r) => (r.tipo === "sexado" ? "Sexado" : "Convencional") },
                    { header: "Doses", campo: "doses", render: (r) => r.doses },
                  ]}
                />
              </>
            )}
          </SecaoRecolhivel>
        </>
      )}
    </div>
  );
}
