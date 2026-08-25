"use client";
// Primitivos e tipos compartilhados pelas seções da Ficha do Animal (app
// móvel) — antes soltos em Ficha.tsx, agora centralizados aqui para que
// nenhuma seção duplique o catálogo de lançamentos (`SECOES`/`Campo`) nem os
// componentes de exibição (`ParDado`/`Grade`/`Secao`). Cada `SecaoX.tsx`
// importa só o que usa.
import { formatDate } from "@/lib/api";
import { estiloSexado, rotuloOrigemMovimentoLote } from "@/lib/constants";
import { MobCard } from "@/components/mobile/ui";
// Mesma regra da coluna "Parto" da versão de mesa (Reprodução — Serviço/IA e
// diagnóstico): só mostra a que parto aquele serviço deu origem quando o
// diagnóstico foi POSITIVO e o parto já aconteceu. Acoplamento mesa→mobile
// já intencional (ver Ficha.tsx original) — não duplicar a função aqui.
import { textoPartoOriginado } from "@/components/FichaAnimal";

// ── Tipo da ficha (catch-all, igual ao que Ficha.tsx sempre usou) ───────────
// Campos conhecidos são tipados; o resto (as 16 chaves de lançamento) cai no
// índice genérico — mesmo padrão de sempre, só que agora com os campos que a
// mesa já tinha e o mobile não tipava (pai com provas, precisao_parto,
// resumo_partos, linha_tempo_sanitaria) para dar paridade com FichaAnimal.tsx.
export type ResumoParto = {
  ordem_parto: number; data_parto: string; lactacao_encerrada: boolean; dias_em_lactacao: number;
  producao_total_kg: number | null; producao_media_dia_kg: number | null;
  producao_305_dias_kg: number | null; producao_305_dias_estimada: boolean;
  tentativas_emprenhar: number | null; del_concepcao: number | null;
  // Número da cria DAQUELE parto — "S/N" se pariu mas não numerou, vazio se
  // natimorto (não confundir os dois). Mesma paridade da mesa (FichaAnimal.tsx).
  cria: string;
};
export type PrecisaoParto = {
  data_ultima_ia_positiva: string | null;
  data_confirmacao_prenhez: string | null;
  dias_gestacao: number | null;
  data_parto_provavel: string | null;
  dias_para_parto: number | null;
};
export type Ficha = {
  animal: Record<string, unknown>;
  colostragem: Record<string, unknown> | null;
  compra: Record<string, unknown> | null;
  compras: Record<string, unknown>[];
  vendas: Record<string, unknown>[];
  gtas: string[];
  baixa: Record<string, unknown> | null;
  // Provas do touro pai (central/TPI/NM$) — mesmo formato de FichaAnimal.tsx,
  // hoje só exibido na mesa; ganham paridade na seção Dados Gerais do mobile.
  pai: { nome: string | null; naab: string | null; central?: string | null; tpi?: number | null; nm_dolar?: number | null } | null;
  previsao_parto: string | null;
  previsao_secagem: string | null;
  precisao_parto: PrecisaoParto | null;
  resumo_partos: ResumoParto[];
  // Número da cria do ÚLTIMO parto do animal — mesma regra de `ResumoParto.cria`
  // aplicada ao último item de `resumo_partos`. Ver fazenda.rules.parto_resumo.
  ultima_cria: string;
  linha_tempo_sanitaria: { data: string | null; tipo_evento: string; descricao: string | null; gta: string | null; responsavel: string | null }[];
} & Record<string, Record<string, unknown>[] | Record<string, unknown> | null>;

// ── Catálogo de lançamentos (as 16 chaves do retorno de /animais/{n}/ficha) ──
// Único lugar onde este catálogo existe no mobile — cada seção busca a sua
// entrada por `chave` (ver `secaoPorChave`) em vez de redeclarar `campos`.
export type Campo = [chave: string, rotulo: string, data?: boolean];
export const SECOES: { chave: string; titulo: string; campos: Campo[] }[] = [
  { chave: "movimentos_lote", titulo: "Movimentações de lote", campos: [["data_movimento", "Data", true], ["lote_origem", "De"], ["lote_destino", "Para"], ["motivo", "Motivo"], ["origem", "Origem"]] },
  { chave: "partos", titulo: "Partos", campos: [["data_parto", "Data", true], ["ordem_parto", "Ordem"], ["tipo_parto", "Tipo"]] },
  // Provas do touro pai (central/TPI/NM$) — a mesa já mostra na tabela de
  // Serviços (FichaAnimal.tsx › SECOES), o mobile não listava; adicionadas
  // aqui para dar paridade (ver plano de redesenho).
  { chave: "servicos", titulo: "Reprodução — serviço/IA", campos: [["data_servico", "Data", true], ["tipo_servico", "Tipo"], ["reprodutor", "Reprodutor"], ["touro_central", "Central do pai"], ["touro_tpi", "TPI do pai"], ["touro_nm", "NM$ do pai"], ["tipo_semen", "Sêmen"], ["ordem_parto_na_ia", "Ordem de parto (na IA)"], ["diagnostico", "Diagnóstico"], ["data_diagnostico", "Diagnosticado em", true], ["parto", "Parto"]] },
  { chave: "protocolos_iatf", titulo: "Protocolo IATF", campos: [["dia", "Dia"], ["descricao", "Descrição"], ["data_prevista", "Prevista", true], ["realizada", "Feito"]] },
  { chave: "controles_leiteiros", titulo: "Controle leiteiro", campos: [["data_controle", "Data", true], ["producao_kg", "Produção (kg)"], ["del_no_controle", "DEL"]] },
  { chave: "pesagens_corporais", titulo: "Pesagens", campos: [["data_pesagem", "Data", true], ["peso_kg", "Peso (kg)"], ["del_dias", "DEL"]] },
  { chave: "qualidade_leite", titulo: "Qualidade do leite", campos: [["data_coleta", "Data", true], ["ccs", "CCS"], ["cbt", "CBT"]] },
  { chave: "aplicacoes_sanitarias", titulo: "Sanidade — aplicações", campos: [["data_aplicacao", "Data", true], ["produto", "Produto"], ["dose", "Dose"], ["unidade", "Un."]] },
  { chave: "protocolos_sanitarios", titulo: "Protocolos sanitários", campos: [["data_inicio", "Data", true], ["protocolo_nome", "Protocolo"], ["classificacao_mastite", "Mastite"]] },
  { chave: "inducao_lactacao", titulo: "Indução de lactação", campos: [["data_prevista", "Prevista", true], ["nome_protocolo", "Protocolo"], ["descricao", "Etapa"], ["realizada", "Feito"]] },
  { chave: "protocolos_customizados", titulo: "Protocolo personalizado", campos: [["data_prevista", "Prevista", true], ["nome_protocolo", "Protocolo"], ["descricao", "Etapa"], ["realizada", "Feito"]] },
  { chave: "secagens", titulo: "Secagens", campos: [["data_secagem", "Data", true], ["motivo", "Motivo"]] },
  { chave: "eventos_agenda", titulo: "Agenda — eventos", campos: [["data_evento", "Data", true], ["descricao", "Descrição"], ["categoria", "Categoria"]] },
  { chave: "exames_resultados", titulo: "Rastreabilidade — Exames", campos: [["data_exame", "Data", true], ["evento_sanitario_nome", "Exame"], ["resultado", "Resultado"]] },
  { chave: "ocorrencias_clinicas", titulo: "Rastreabilidade — Doenças", campos: [["data_ocorrencia", "Data", true], ["doenca", "Doença"], ["observacao", "Observação"]] },
];

export function secaoPorChave(chave: string) {
  return SECOES.find((s) => s.chave === chave)!;
}

export function mostrarValor(v: unknown, data?: boolean): string {
  if (v == null || v === "") return "—";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (data) return formatDate(String(v));
  return String(v);
}

const rotuloEstilo: React.CSSProperties = { fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 };

export function ParDado({ label, valor }: { label: string; valor: React.ReactNode }) {
  return (
    <div>
      <span style={rotuloEstilo}>{label}</span>
      <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{valor}</div>
    </div>
  );
}

/** Grid de rótulo:valor — `cols` só muda de 2 (padrão) para 3 no cartão de
 * situação atual do Resumo (mockup aprovado: "situação g3"). */
export function Grade({ children, cols = 2 }: { children: React.ReactNode; cols?: 2 | 3 }) {
  return <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: "0.7rem 1rem" }}>{children}</div>;
}

/** Acordeão genérico de uma lista de lançamentos (`SECOES[i]`) — cada linha
 * vira um MobCard com Grade/ParDado dos campos daquela seção. Mesmo
 * componente que Ficha.tsx sempre usou; só mudou de arquivo. `altInicio`
 * decide a paridade do 1º card (para continuar a alternância de cor vinda
 * de cards já renderizados antes dele na mesma tela). */
export function Secao({ chave, titulo, linhas, campos, altInicio }: { chave: string; titulo: string; linhas: Record<string, unknown>[]; campos: Campo[]; altInicio: number }) {
  if (!linhas.length) return null;
  return (
    <details style={{ marginBottom: "0.7rem" }}>
      <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: "0.95rem", padding: "0.85rem 1rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)", borderRadius: "var(--r-app)", listStyle: "none", display: "flex", justifyContent: "space-between", alignItems: "center", boxShadow: "var(--mob-sombra)" }}>
        <span>{titulo}</span>
        <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", fontWeight: 700 }}>{linhas.length}</span>
      </summary>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
        {linhas.map((l, i) => (
          <MobCard key={i} alt={((altInicio + i) % 2) as 0 | 1}
            style={chave === "servicos" ? estiloSexado(l.tipo_semen as string | null | undefined) : undefined}>
            <Grade>
              {campos.map(([chaveCampo, rot, data]) => (
                <ParDado key={chaveCampo} label={rot} valor={
                  chaveCampo === "origem" ? rotuloOrigemMovimentoLote(l[chaveCampo])
                  : chaveCampo === "parto" ? textoPartoOriginado(l)
                  : mostrarValor(l[chaveCampo], data)
                } />
              ))}
            </Grade>
          </MobCard>
        ))}
      </div>
    </details>
  );
}

/** Alternância de cor dos cartões (`alt`/`proximoAlt`), reiniciada POR SEÇÃO
 * — antes era um contador corrido pela ficha inteira; com a navegação em
 * cards, cada `SecaoX.tsx` chama isto uma vez no topo do próprio render
 * (função pura, sem estado React — só precisa recomeçar a cada render, como
 * o `let altContador = 0` que já existia). */
export function criarAlternador(): () => 0 | 1 {
  let n = 0;
  return () => (n++ % 2) as 0 | 1;
}

/** Remapeamento inline de tokens "de mesa" (--surface/--border/--text-muted
 * etc.) para os tokens --mob-* do app de campo — mesma técnica que
 * `CurvaLactacao` já recebia em Ficha.tsx (linhas ~300-305 da versão
 * anterior), agora também usada por `TrioEquivalenteMaduroView`/
 * `NotaExplicativaEM` (components/TrioEquivalenteMaduro.tsx), que leem os
 * mesmos tokens de mesa. Um `<div style={ESTILO_TOKENS_MESA}>` ao redor do
 * componente de mesa basta — sem duplicar nenhuma lógica de desenho. */
export const ESTILO_TOKENS_MESA: React.CSSProperties = {
  ["--text-muted" as any]: "var(--mob-muted)",
  ["--dourado-light" as any]: "var(--mob-dourado-2)",
  ["--dourado" as any]: "var(--mob-dourado)",
  ["--border" as any]: "var(--mob-border)",
  ["--surface" as any]: "var(--mob-surface)",
  ["--surface-2" as any]: "var(--mob-surface-2)",
  ["--green-light" as any]: "var(--mob-verde)",
  ["--amber" as any]: "var(--mob-ambar)",
  ["--red" as any]: "var(--mob-vermelho)",
};

export const tituloCartao: React.CSSProperties = { fontSize: "0.72rem", fontWeight: 800, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--mob-muted)", marginBottom: "0.7rem" };
