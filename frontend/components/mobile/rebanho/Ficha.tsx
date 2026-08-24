"use client";
// Tela REBANHO › aba "Ficha do Animal".
// Busca grande + lista completa de animais; ao tocar num animal abre a ficha
// completa (só leitura) numa sub-tela, com seções recolhíveis. Offline: ficha
// via cache por animal (chave "ficha_<numero>").
import { useEffect, useState } from "react";
import { fetchAnimais, fetchFichaAnimal, formatDate } from "@/lib/api";
import { fetchComCache, cacheEm, enviarOuEnfileirar } from "@/lib/offline";
import { MobCard, MobVoltar, MobLinha, MobCampo, MobAviso } from "@/components/mobile/ui";
import { estiloSexado, rotuloOrigemMovimentoLote } from "@/lib/constants";
import { BuscaAnimal, subtituloAnimal, type AnimalMob } from "./comum";
import { useOrdenacao } from "@/components/Ordenavel";
import { SeletorOrdenacao, type CampoOrdenacao } from "@/components/mobile/SeletorOrdenacao";
// Curva de lactação: mesmo componente SVG da ficha de mesa (sem biblioteca de
// gráfico — é o padrão do projeto). Só o CSS muda: as variáveis genéricas que
// o componente usa (--text-muted/--dourado-light/--border/--surface) são
// remapeadas aqui para os tokens --mob-* no `style` do wrapper, a mesma
// técnica de "--tint-cor" já usada no Menu (app/app/menu/page.tsx) — assim o
// gráfico nasce com a paleta do app de campo sem duplicar a lógica do SVG.
import { CurvaLactacao, type FaixaReferencia } from "@/components/CurvaLactacao";
// Mesma regra da coluna "Parto" da versão de mesa (Reprodução — Serviço/IA e
// diagnóstico): só mostra a que parto aquele serviço deu origem quando o
// diagnóstico foi POSITIVO e o parto já aconteceu.
import { textoPartoOriginado } from "@/components/FichaAnimal";

// Campos ordenáveis da lista "Todos os animais" (Rebanho › Ficha do animal).
const CAMPOS_ORDENACAO: CampoOrdenacao[] = [
  { chave: "numero", rotulo: "Brinco" },
  { chave: "nome", rotulo: "Nome" },
  { chave: "grupo_primario", rotulo: "Lote" },
  { chave: "categoria_abrev", rotulo: "Categoria" },
  { chave: "del_dias", rotulo: "DEL" },
];

type Ficha = {
  animal: Record<string, unknown>;
  colostragem: Record<string, unknown> | null;
  compra: Record<string, unknown> | null;
  compras: Record<string, unknown>[];
  vendas: Record<string, unknown>[];
  gtas: string[];
  baixa: Record<string, unknown> | null;
  pai: { nome: string | null; naab: string | null } | null;
  previsao_parto: string | null;
  previsao_secagem: string | null;
} & Record<string, Record<string, unknown>[] | Record<string, unknown> | null>;

// Grupos de lançamentos (as chaves batem com o retorno de /animais/{n}/ficha).
type Campo = [chave: string, rotulo: string, data?: boolean];
const SECOES: { chave: string; titulo: string; campos: Campo[] }[] = [
  { chave: "movimentos_lote", titulo: "Movimentações de lote", campos: [["data_movimento", "Data", true], ["lote_origem", "De"], ["lote_destino", "Para"], ["motivo", "Motivo"], ["origem", "Origem"]] },
  { chave: "partos", titulo: "Partos", campos: [["data_parto", "Data", true], ["ordem_parto", "Ordem"], ["tipo_parto", "Tipo"]] },
  { chave: "servicos", titulo: "Reprodução — serviço/IA", campos: [["data_servico", "Data", true], ["tipo_servico", "Tipo"], ["reprodutor", "Reprodutor"], ["tipo_semen", "Sêmen"], ["ordem_parto_na_ia", "Ordem de parto (na IA)"], ["diagnostico", "Diagnóstico"], ["data_diagnostico", "Diagnosticado em", true], ["parto", "Parto"]] },
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

function mostrarValor(v: unknown, data?: boolean): string {
  if (v == null || v === "") return "—";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (data) return formatDate(String(v));
  return String(v);
}

const rotulo: React.CSSProperties = { fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 };

function ParDado({ label, valor }: { label: string; valor: React.ReactNode }) {
  return (
    <div>
      <span style={rotulo}>{label}</span>
      <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{valor}</div>
    </div>
  );
}

function Grade({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.7rem 1rem" }}>{children}</div>;
}

function Secao({ chave, titulo, linhas, campos, altInicio }: { chave: string; titulo: string; linhas: Record<string, unknown>[]; campos: Campo[]; altInicio: number }) {
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
              {campos.map(([chave, rot, data]) => (
                <ParDado key={chave} label={rot} valor={
                  chave === "origem" ? rotuloOrigemMovimentoLote(l[chave])
                  : chave === "parto" ? textoPartoOriginado(l)
                  : mostrarValor(l[chave], data)
                } />
              ))}
            </Grade>
          </MobCard>
        ))}
      </div>
    </details>
  );
}

// Exportado para telas fora de Rebanho (ex.: Menu › Agenda do Veterinário)
// abrirem a ficha do animal com seu próprio "voltar" local, sem navegar para
// a aba Rebanho.
export function FichaDetalhe({ numero, onVoltar, destacarInicial }: { numero: string; onVoltar: () => void; destacarInicial?: "colostragem" | "igg" | null }) {
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [doCache, setDoCache] = useState(false);

  const [editColostro, setEditColostro] = useState(false);
  const [formColostro, setFormColostro] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [destacar, setDestacar] = useState<"colostragem" | "igg" | null>(destacarInicial ?? null);
  const [abrirEdicaoAoCarregar, setAbrirEdicaoAoCarregar] = useState(!!destacarInicial);

  useEffect(() => {
    let vivo = true;
    setCarregando(true); setErro(null);
    fetchComCache<Ficha>(`ficha_${numero}`, () => fetchFichaAnimal(numero))
      .then(({ dados, doCache }) => {
        if (!vivo) return;
        if (dados) {
          setFicha(dados);
          setDoCache(doCache);
        } else {
          setErro("Sem internet e sem cópia salva desta ficha.");
        }
      })
      .catch((e) => { if (vivo) setErro(e?.message || "Erro ao carregar ficha."); })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [numero]);

  const a = ficha?.animal;
  const colostragem = ficha?.colostragem as Record<string, unknown> | null;
  const baixa = ficha?.baixa as Record<string, unknown> | null;
  const compra = ficha?.compra as Record<string, unknown> | null;
  const pai = ficha?.pai;
  // "Última produção" precisa vir do histórico ao vivo (controles_leiteiros,
  // já ordenado ascendente por data_controle pelo backend), não de
  // Animal.ult_cl_kg/data_ult_leite — essas duas colunas só avançam no
  // próximo reimport de GERAL.csv (Ideagri), então logo após um controle
  // leiteiro novo lançado no app elas ainda mostram o penúltimo controle.
  const controlesLeiteiros = (ficha?.controles_leiteiros as Record<string, unknown>[] | undefined) || [];
  const ultimoControle = controlesLeiteiros.length ? controlesLeiteiros[controlesLeiteiros.length - 1] : null;
  // Mesmos pontos (DEL × kg) que a versão de mesa desenha na curva — vêm do
  // mesmo /animais/{n}/ficha, só que aqui o tipo Ficha é um catch-all
  // genérico, então lê-se e valida-se campo a campo (sem `!`).
  const pontosLactacao = controlesLeiteiros
    .map((c) => ({
      del: Number(c.del_no_controle),
      kg: Number(c.producao_kg),
      data: c.data_controle ? formatDate(String(c.data_controle)) : null,
    }))
    .filter((p) => Number.isFinite(p.del) && Number.isFinite(p.kg));
  const referenciaLactacao = ficha?.curva_referencia_rebanho as unknown as FaixaReferencia[] | undefined;
  // Na mesa a curva fica atrás de uma aba: quem abre, escolheu vê-la. Aqui é
  // card sempre visível, e mostrar "Curva de lactação — sem controle" para
  // uma bezerra de 8 meses é ruído numa tela onde cada centímetro custa. O
  // card só aparece para quem já pariu (aí o vazio é informativo: falta
  // lançar o controle) ou para quem já tem ponto na curva.
  const jaPariu = ((ficha?.partos as unknown[] | undefined) || []).length > 0;

  function abrirEditColostro() {
    const c: Record<string, unknown> = colostragem || {};
    setFormColostro({
      tomou_colostro: c.tomou_colostro == null ? "" : String(c.tomou_colostro),
      litros_colostro: c.litros_colostro != null ? String(c.litros_colostro) : "",
      brix_colostro: c.brix_colostro != null ? String(c.brix_colostro) : "",
      data_colostro: c.data_colostro != null ? String(c.data_colostro) : "",
      hora_parto: c.hora_parto != null ? String(c.hora_parto) : "",
      hora_colostro: c.hora_colostro != null ? String(c.hora_colostro) : "",
      peso_nascer_kg: c.peso_nascer_kg != null ? String(c.peso_nascer_kg) : "",
      brix_soro: c.brix_soro != null ? String(c.brix_soro) : "",
      proteina_serica: c.proteina_serica != null ? String(c.proteina_serica) : "",
      apenas_colostro_po: c.apenas_colostro_po == null ? "" : String(c.apenas_colostro_po),
      data_teste_sangue: c.data_teste_sangue != null ? String(c.data_teste_sangue) : "",
      observacao: c.observacao != null ? String(c.observacao) : "",
    });
    setEditColostro(true); setAviso(null);
  }

  // Chegou da Agenda com uma pendência de colostro/IgG: assim que a ficha
  // carrega, abre direto o formulário de colostragem.
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
      // Via fila offline (enviarOuEnfileirar): sem internet no curral/maternidade
      // (cenário comum logo após o parto), o lançamento fica guardado e some
      // sozinho quando a conexão voltar — igual aos demais lançamentos do app.
      const { enviado } = await enviarOuEnfileirar(
        "/sanidade/colostragem",
        {
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
          apenas_colostro_po: f.apenas_colostro_po === "" ? undefined : f.apenas_colostro_po === "true",
          data_teste_sangue: f.data_teste_sangue || undefined,
          observacao: f.observacao || undefined,
        },
        `Colostragem/IgG — brinco ${numero}`,
        "POST",
      );
      setEditColostro(false);
      setAviso(enviado ? "Colostragem/IgG salvos." : "Sem internet — guardado, será enviado ao conectar.");
      setDestacar(null);
      if (enviado) {
        const { dados } = await fetchComCache<Ficha>(`ficha_${numero}`, () => fetchFichaAnimal(numero));
        if (dados) setFicha(dados);
      }
    } catch (e) {
      setAviso(e instanceof Error ? e.message : "Erro ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  // Alternância de cor dos cartões ABAIXO do primeiro (identificação) — mesmo
  // esquema da Agenda (claro: branco/paleta; escuro: preto contornado de
  // vinho/verde). Contador corrido: cada cartão renderizado consome um índice.
  let altContador = 0;
  const proximoAlt = (): 0 | 1 => (altContador++ % 2) as 0 | 1;

  return (
    <div>
      <MobVoltar titulo={`Brinco ${numero}`} onVoltar={onVoltar} />
      {carregando && <p style={{ color: "var(--mob-muted)" }}>Carregando ficha…</p>}
      {erro && <p style={{ color: "var(--mob-vermelho)", fontWeight: 600 }}>{erro}</p>}

      {a && (
        <>
          {doCache && (
            <p style={{ fontSize: "0.78rem", color: "var(--mob-ambar)", fontWeight: 600, marginBottom: "0.6rem" }}>
              Mostrando cópia salva{cacheEm(`ficha_${numero}`) ? ` em ${new Date(cacheEm(`ficha_${numero}`)!).toLocaleString("pt-BR")}` : ""}.
            </p>
          )}

          <MobCard style={{ marginBottom: "0.7rem" }}>
            <div style={{ fontWeight: 800, fontSize: "1.05rem", marginBottom: "0.7rem" }}>
              {String(a.nome || `Brinco ${a.numero}`)}
              <span style={{ color: a.ativo === false ? "var(--mob-vermelho)" : "var(--mob-verde)", fontSize: "0.8rem", fontWeight: 700, marginLeft: "0.5rem" }}>
                {a.ativo === false ? "Baixado" : "Ativo"}
              </span>
            </div>
            <Grade>
              <ParDado label="Sexo" valor={a.sexo === "M" ? "Macho" : a.sexo === "F" ? "Fêmea" : "—"} />
              <ParDado label="Categoria" valor={String(a.categoria_abrev || a.categoria_completa || "—")} />
              <ParDado label="Lote atual" valor={String(a.grupo_primario || "—")} />
              <ParDado label="Raça" valor={String(a.raca || "—")} />
              <ParDado label="Nascimento" valor={a.data_nasc ? formatDate(String(a.data_nasc)) : "—"} />
              <ParDado label="Entrada" valor={a.data_entrada ? formatDate(String(a.data_entrada)) : "—"} />
              <ParDado label="Mãe" valor={String(a.mae_numero || "—")} />
              <ParDado label="DEL" valor={a.del_dias != null ? String(a.del_dias) : "—"} />
              <ParDado label="Pai" valor={pai?.nome ? `${pai.nome}${pai.naab ? ` (${pai.naab})` : ""}` : "—"} />
              <ParDado label="Grau de sangue" valor={String(a.grau_sangue || "—")} />
              <ParDado label="Última produção" valor={ultimoControle?.producao_kg != null ? `${Number(ultimoControle.producao_kg).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} kg${ultimoControle.data_controle ? ` (${formatDate(String(ultimoControle.data_controle))})` : ""}` : "—"} />
              <ParDado label="Dias de gestação" valor={(ficha?.precisao_parto as Record<string, unknown> | null)?.dias_gestacao != null ? String((ficha!.precisao_parto as Record<string, unknown>).dias_gestacao) : "—"} />
              <ParDado label="Previsão de secagem" valor={ficha?.previsao_secagem ? formatDate(ficha.previsao_secagem) : "—"} />
              <ParDado label="Previsão de parto" valor={ficha?.previsao_parto ? formatDate(ficha.previsao_parto) : "—"} />
            </Grade>
          </MobCard>

          {a.sexo === "F" && (jaPariu || pontosLactacao.length > 0) && (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }}>
              <div style={{ fontWeight: 700, marginBottom: "0.4rem" }}>Curva de lactação</div>
              <div style={{
                ["--text-muted" as any]: "var(--mob-muted)",
                ["--dourado-light" as any]: "var(--mob-dourado-2)",
                ["--border" as any]: "var(--mob-border)",
                ["--surface" as any]: "var(--mob-surface)",
              }}>
                <CurvaLactacao pontos={pontosLactacao} referencia={referenciaLactacao} />
              </div>
            </MobCard>
          )}

          <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem", borderColor: destacar ? "var(--mob-vermelho)" : undefined }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
                <div style={{ fontWeight: 700 }}>Colostragem / IgG</div>
                {!editColostro && <button type="button" className="mob-btn mob-btn-sec" style={{ width: "auto", padding: "0.35rem 0.9rem" }} onClick={abrirEditColostro}>Editar</button>}
              </div>

              {destacar && !editColostro && (
                <p style={{ fontSize: "0.82rem", color: "var(--mob-vermelho)", fontWeight: 700, marginBottom: "0.6rem" }}>
                  Pendente da Agenda — preencha {destacar === "colostragem" ? "os litros e o Brix do colostro" : "o Brix do soro (IgG)"} abaixo.
                </p>
              )}

              {aviso && (
                <MobAviso tipo={aviso.includes("Erro") || aviso.includes("erro") ? "erro" : aviso.startsWith("Sem internet") ? "offline" : "ok"}>
                  {aviso}
                </MobAviso>
              )}

              {!editColostro ? (
                <Grade>
                  <ParDado label="Peso ao nascer (kg)" valor={mostrarValor(colostragem?.peso_nascer_kg)} />
                  <ParDado label="Tomou colostro?" valor={mostrarValor(colostragem?.tomou_colostro)} />
                  <ParDado label="Litros" valor={mostrarValor(colostragem?.litros_colostro)} />
                  <ParDado label="Brix colostro" valor={mostrarValor(colostragem?.brix_colostro)} />
                  <ParDado label="Brix soro" valor={mostrarValor(colostragem?.brix_soro)} />
                  <ParDado label="Proteína sérica" valor={mostrarValor(colostragem?.proteina_serica)} />
                  <ParDado label="Só colostro em pó?" valor={mostrarValor(colostragem?.apenas_colostro_po)} />
                </Grade>
              ) : (
                <div style={{ marginTop: "0.3rem" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 0.8rem" }}>
                    <MobCampo label="Hora do parto">
                      <input type="time" className="mob-input" value={formColostro.hora_parto || ""} onChange={(e) => setFormColostro((p) => ({ ...p, hora_parto: e.target.value }))} />
                    </MobCampo>
                    <MobCampo label="Hora do colostro">
                      <input type="time" className="mob-input" value={formColostro.hora_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, hora_colostro: e.target.value }))} />
                    </MobCampo>
                  </div>
                  <MobCampo label="Peso ao nascer (kg)">
                    <input type="number" step="0.1" inputMode="decimal" className="mob-input" value={formColostro.peso_nascer_kg || ""} onChange={(e) => setFormColostro((p) => ({ ...p, peso_nascer_kg: e.target.value }))} placeholder="ex.: 38" />
                  </MobCampo>
                  <MobCampo label="Tomou colostro?">
                    <select className="mob-input" value={formColostro.tomou_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, tomou_colostro: e.target.value }))}>
                      <option value="">—</option>
                      <option value="true">Sim</option>
                      <option value="false">Não</option>
                    </select>
                  </MobCampo>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 0.8rem" }}>
                    <MobCampo label={destacar === "colostragem" ? "Litros (pendente)" : "Litros"}>
                      <input type="number" inputMode="decimal" className="mob-input" style={destacar === "colostragem" ? { borderColor: "var(--mob-vermelho)" } : undefined}
                        value={formColostro.litros_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, litros_colostro: e.target.value }))} />
                    </MobCampo>
                    <MobCampo label={destacar === "colostragem" ? "Brix colostro (pendente)" : "Brix colostro"}>
                      <input type="number" inputMode="decimal" className="mob-input" style={destacar === "colostragem" ? { borderColor: "var(--mob-vermelho)" } : undefined}
                        value={formColostro.brix_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, brix_colostro: e.target.value }))} />
                    </MobCampo>
                  </div>
                  <MobCampo label="Data do colostro">
                    <input type="date" className="mob-input" value={formColostro.data_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, data_colostro: e.target.value }))} />
                  </MobCampo>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 0.8rem" }}>
                    <MobCampo label={destacar === "igg" ? "Brix do soro / IgG (pendente)" : "Brix do soro / IgG"}>
                      <input type="number" inputMode="decimal" className="mob-input" style={destacar === "igg" ? { borderColor: "var(--mob-vermelho)" } : undefined}
                        value={formColostro.brix_soro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, brix_soro: e.target.value }))} />
                    </MobCampo>
                    <MobCampo label="Proteína sérica (g/dL)">
                      <input type="number" step="0.1" inputMode="decimal" className="mob-input" value={formColostro.proteina_serica || ""} onChange={(e) => setFormColostro((p) => ({ ...p, proteina_serica: e.target.value }))} placeholder="ex.: 6,0" />
                    </MobCampo>
                  </div>
                  <MobCampo label="Data do teste de sangue">
                    <input type="date" className="mob-input" value={formColostro.data_teste_sangue || ""} onChange={(e) => setFormColostro((p) => ({ ...p, data_teste_sangue: e.target.value }))} />
                  </MobCampo>
                  <MobCampo label="Recebeu somente colostro em pó?">
                    <select className="mob-input" value={formColostro.apenas_colostro_po || ""} onChange={(e) => setFormColostro((p) => ({ ...p, apenas_colostro_po: e.target.value }))}>
                      <option value="">—</option>
                      <option value="true">Sim (sem colostro materno)</option>
                      <option value="false">Não</option>
                    </select>
                  </MobCampo>
                  <MobCampo label="Observação">
                    <input className="mob-input" value={formColostro.observacao || ""} onChange={(e) => setFormColostro((p) => ({ ...p, observacao: e.target.value }))} />
                  </MobCampo>
                  <div style={{ display: "flex", gap: "0.6rem", marginTop: "0.4rem" }}>
                    <button type="button" className="mob-btn" style={{ flex: 1 }} disabled={salvando} onClick={salvarColostro}>{salvando ? "Salvando…" : "Salvar"}</button>
                    <button type="button" className="mob-btn mob-btn-sec" style={{ flex: 1 }} onClick={() => setEditColostro(false)}>Cancelar</button>
                  </div>
                </div>
              )}
            </MobCard>

          {!!ficha?.gtas?.length && (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }}>
              <div style={{ fontWeight: 700, marginBottom: "0.4rem" }}>GTA(s) do animal</div>
              <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{ficha!.gtas.join(", ")}</div>
            </MobCard>
          )}

          {(ficha?.compras || (compra ? [compra] : [])).map((c, i) => (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }} key={`compra-${i}`}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem" }}>Compra</div>
              <Grade>
                <ParDado label="Data" valor={mostrarValor(c.data_compra, true)} />
                <ParDado label="Vendedor" valor={mostrarValor(c.vendedor)} />
                <ParDado label="Valor" valor={c.valor != null ? `R$ ${c.valor}` : "—"} />
                <ParDado label="GTA" valor={mostrarValor(c.gta)} />
                <ParDado label="Responsável" valor={mostrarValor(c.responsavel)} />
              </Grade>
            </MobCard>
          ))}

          {(ficha?.vendas || []).map((v, i) => (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }} key={`venda-${i}`}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem" }}>Venda</div>
              <Grade>
                <ParDado label="Data" valor={mostrarValor(v.data_venda, true)} />
                <ParDado label="Comprador" valor={mostrarValor(v.comprador)} />
                <ParDado label="Valor" valor={v.valor != null ? `R$ ${v.valor}` : "—"} />
                <ParDado label="GTA" valor={mostrarValor(v.gta)} />
                <ParDado label="Responsável" valor={mostrarValor(v.responsavel)} />
              </Grade>
            </MobCard>
          ))}

          {baixa && (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem", borderColor: "var(--mob-vermelho)" }}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem", color: "var(--mob-vermelho)" }}>Baixa (saída do rebanho)</div>
              <Grade>
                <ParDado label="Data" valor={mostrarValor(baixa.data_baixa, true)} />
                <ParDado label="Tipo" valor={mostrarValor(baixa.tipo_baixa)} />
                <ParDado label="Motivo" valor={mostrarValor(baixa.motivo)} />
                <ParDado label="Valor" valor={baixa.valor != null ? `R$ ${baixa.valor}` : "—"} />
              </Grade>
            </MobCard>
          )}

          <div className="mob-secao">Lançamentos</div>
          {SECOES.map((s) => {
            const linhas = (ficha?.[s.chave] as Record<string, unknown>[]) || [];
            const altInicio = altContador;
            altContador += linhas.length;
            return <Secao key={s.chave} chave={s.chave} titulo={s.titulo} campos={s.campos} linhas={linhas} altInicio={altInicio} />;
          })}
          {SECOES.every((s) => !((ficha?.[s.chave] as unknown[]) || []).length) && (
            <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum lançamento registrado para este animal.</p>
          )}
        </>
      )}
    </div>
  );
}

export default function Ficha({ numeroInicial, destacarInicial }: { numeroInicial?: string | null; destacarInicial?: string | null } = {}) {
  const [aberto, setAberto] = useState<string | null>(numeroInicial ?? null);
  const [animais, setAnimais] = useState<AnimalMob[]>([]);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let vivo = true;
    fetchComCache<AnimalMob[]>("animais", () => fetchAnimais()).then(({ dados }) => {
      if (vivo) { setAnimais(dados || []); setCarregando(false); }
    });
    return () => { vivo = false; };
  }, []);

  const destacar = destacarInicial === "colostragem" || destacarInicial === "igg" ? destacarInicial : null;

  // Ordem padrão (nenhum campo escolhido no seletor): por brinco, como sempre
  // foi — o useOrdenacao só assume o controle depois que o usuário escolhe um
  // campo em SeletorOrdenacao. Precisa vir ANTES do "if (aberto) return" — hooks
  // não podem ser condicionais.
  const porNumero = [...animais].sort((a, b) => a.numero.localeCompare(b.numero, "pt-BR", { numeric: true }));
  const ord = useOrdenacao(porNumero);

  if (aberto) return <FichaDetalhe numero={aberto} onVoltar={() => setAberto(null)} destacarInicial={aberto === numeroInicial ? destacar : null} />;

  return (
    <div>
      <BuscaAnimal valor="" onEscolher={(n) => { if (n) setAberto(n); }} />

      <div className="mob-secao">Todos os animais{ord.linhasOrdenadas.length ? ` (${ord.linhasOrdenadas.length})` : ""}</div>
      <SeletorOrdenacao campos={CAMPOS_ORDENACAO} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
      {carregando && <p style={{ color: "var(--mob-muted)" }}>Carregando…</p>}
      {!carregando && !ord.linhasOrdenadas.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal encontrado.</p>}
      {ord.linhasOrdenadas.map((r, i) => (
        <MobLinha key={r.numero} alt={(i % 2) as 0 | 1} titulo={`Brinco ${r.numero}${r.nome ? ` · ${r.nome}` : ""}`} subtitulo={subtituloAnimal(r)} onClick={() => setAberto(r.numero)} />
      ))}
    </div>
  );
}
