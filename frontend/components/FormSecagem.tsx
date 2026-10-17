"use client";
// Lançamentos › Produção › Secagem — 4 passos numerados em UMA coluna: vacas (tabela com DEL, gestação, data prevista e situação),
// dados da secagem, produtos (opcional) e vacina pré-parto (opcional). As decisões ("já consta como seca", "mover para o lote das
// secas") e o resultado ficam dentro da barra fixa do pé, junto do Salvar em ouro.
//  • Props: animais, estoque, produtos, numeroInicial (pré-marca a vaca vinda de Listas › Previsão de secagem), salvarSecagem e
//    salvarMovimentacao (injeção do app de campo/offline; offline não traz `lote_sugerido`: "guardado, será enviado quando conectar").
//  • Só vacas em lactação (animalEmLactacao). Animal(is) ou lote(s); o lote COMEÇA SEM NINGUÉM MARCADO, de propósito.
//  • GET /producao/secagem-lista (uma chamada: DEL, dias de gestação, data prevista, situação) alimenta a tabela; com UMA vaca
//    marcada a data da secagem vem preenchida com a prevista (60 d antes do parto). Sem a lista (backend antigo/offline) cai em
//    GET /producao/secagem-info?numero_matriz. Aviso/motivo_exclusao só informa, não bloqueia.
//  • POST /producao/secagem por vaca, uma de cada vez (falhou = volta marcada, o que já salvou não se perde). Motivo obrigatório,
//    ECC 1–5 (passo 0,25), produtos (dosagem por vaca ou total ÷ nº de vacas, estoque restante informado), data futura ⇒
//    `aplicado=false` (programa na Agenda, não baixa estoque), vacina pré-parto (Sim exige ≥ 1; "já aplicada agora" baixa e registra).
//  • 409 "já consta como seca" PAUSA a fila: Substituir reenvia com `substituir_secagem_id`; Cancelar pula só essa vaca.
//  • Depois de salvar: lote sugerido por vaca, uma a uma (confirmação) ou automático (Configurações › Parâmetros).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalendarClock, Plus, Search, Trash2 } from "lucide-react";
import {
  criarMovimentacao, criarSecagem, fetchMedicamentos, fetchSecagemInfo, fetchSecagemLista, fetchTransferenciaLoteAutomatica,
  formatDate, type SecagemLista,
} from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { AnimalRow } from "@/components/AnimalModal";
import { Ajuda, Aviso, BarraAcao, BotaoOuro, Campo, Faixa, Passo, Pilulas, Selo } from "@/components/gerencial/kit";
import { LinhaGrupo, RotuloMini, dataBR, nb, somarDias } from "@/components/gerencial/telas/utilProducao";
import { BOTAO_COM_ICONE, EstadoVazio, NotaInfo } from "@/components/gerencial/telas/pecasProducao";
import {
  type EstoqueItem, unidadesCompativeis, codigoGrupo, MOTIVOS_SECAGEM, animalEmLactacao,
} from "@/components/lancamentos/comumForms";
import { casaBusca } from "@/lib/busca";
import {
  agruparPorLote, aplicadoEfetivo, erroDeSecagem, hojeLocalIso, LIMITE_PROXIMAS_DIAS, mensagemDoErro, numOuNull, passaFiltroSecagem,
  produtosParaEnvio, situacaoSecagem, totalAplicado, type FiltroSecagem, type ItemProdutoSecagem, type ModoDosagem,
} from "@/lib/producaoLancamento";

type DadosSecagem = {
  numero_matriz: string; data_secagem: string; motivo: string; escore_condicao_corporal: number | null;
  observacao?: string; responsavel?: string; aplicado?: boolean;
  produtos: { produto: string; via?: string; quantidade: number; unidade: string }[];
  vacinas_pre_parto: string[]; vacina_pre_parto_aplicada_agora: boolean; vacina_pre_parto: boolean | null;
  substituir_secagem_id?: number;
};
// "Esta vaca já consta como seca — substituir a data da secagem anterior ou cancelar este lançamento?" (ver
// `ErroApi.secagemAnterior`, POST /producao/secagem). Guarda o que falta para retomar a fila depois da resposta do usuário —
// `payloadBase` é o mesmo objeto para todo o lote (motivo, data, produtos…), só o `numero_matriz` muda a cada vaca.
type ConflitoSecagem = {
  numero: string;
  secagemAnterior: { id: number; data_secagem: string; motivo: string };
  payloadBase: Omit<DadosSecagem, "numero_matriz" | "substituir_secagem_id">;
  restantes: string[];
};
// `lote_sugerido` só vem preenchido quando o envio foi síncrono (enviado !== false) — na fila offline não há como saber a
// sugestão de lote antes de o item sincronizar de verdade, então a transferência automática não dispara nesses casos.
// `avisos`/`programado` são o retorno do servidor (baixa de estoque, o que foi programado na Agenda).
type ResultadoSecagem = { lote_sugerido?: { codigo: string; nome: string; rotulo: string }; enviado?: boolean; avisos?: string[]; programado?: boolean };
type DadosMovimentacao = {
  data_movimento: string; motivo?: string; lote_destino_codigo: string; animais: string[];
  origem?: "manual" | "sugestao_confirmada" | "sugestao_automatica" | "sugestao_passiva" | "importacao";
};
type ResultadoMovimentacao = { movidos: number; nao_encontrados: string[] };
type Sugestao = { numero: string; lote: { codigo: string; rotulo: string } };
type Andamento = "fila" | "lancada" | "conflito" | "falhou" | "cancelada";
type Info = { del_atual: number | null; data_prevista_secagem: string | null; deve_secar: boolean | null; motivo_exclusao: string | null; dias_gestacao: number | null };
type Resultado = {
  salvos: string[]; falhados: string[]; puladas: string[]; enfileirado: boolean; data: string;
  baixas: string[]; avisos: string[]; movimentos: string[]; falhasMov: string[];
};

const ALTURA_TABELA = { ["--gv-altura-tabela" as string]: "44rem" } as React.CSSProperties;
const SEM_ALTURA = { ["--gv-altura-tabela" as string]: "none" } as React.CSSProperties;
const DIR = { textAlign: "right" as const };
const VIAS = ["Intramuscular", "Subcutânea", "Intramamária", "Oral", "Tópica"];
const GRUPO_RADIO: React.CSSProperties = { accentColor: "var(--ft-ouro)", border: 0, padding: 0, margin: 0, display: "flex", gap: "0.9rem", flexWrap: "wrap", alignItems: "center" };
const ROTULO_RADIO: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", cursor: "pointer", minHeight: "1.9rem" };
const LEGENDA: React.CSSProperties = { float: "left", marginRight: "0.9rem", fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", padding: 0 };

function SeloAndamento({ a }: { a: Andamento }) {
  if (a === "lancada") return <Selo tom="ok">✓ Lançada</Selo>;
  if (a === "conflito") return <Selo tom="bloqueio" titulo="Esta vaca já tem secagem lançada: decida na barra abaixo">Já consta como seca</Selo>;
  if (a === "falhou") return <Selo tom="bloqueio">Falhou · tente de novo</Selo>;
  if (a === "cancelada") return <Selo tom="neutro">Cancelada</Selo>;
  return <Selo tom="neutro">Na fila</Selo>;
}

/** Retorno dentro da barra: decisão pendente (substituir/cancelar), resultado do último salvamento e lote sugerido, um a um. */
function RetornoSecagem({ erro, resultado, conflito, resolvendo, dataSecagem, fila, transferindo, aoSubstituir, aoCancelar, aoMover, aoPular, automatica }: {
  erro: string | null; resultado: Resultado | null; conflito: ConflitoSecagem | null; resolvendo: boolean; dataSecagem: string;
  fila: Sugestao[]; transferindo: boolean; aoSubstituir: () => void; aoCancelar: () => void; aoMover: () => void; aoPular: () => void; automatica: boolean;
}) {
  const proxima = fila[0] ?? null;
  const r = resultado;
  if (!erro && !r && !conflito && !proxima) return null;
  const lista = (xs: string[]) => (xs.length > 8 ? `${xs.slice(0, 8).join(", ")} e mais ${xs.length - 8}` : xs.join(", "));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem", width: "100%" }}>
      {r && r.salvos.length > 0 && (
        <span role="status" style={{ color: "var(--ft-verde)" }}>
          ✓ Secagem {r.enfileirado ? "guardada" : "lançada"} para {r.salvos.length} {r.salvos.length === 1 ? "vaca" : "vacas"} ({lista(r.salvos)}) em {dataBR(r.data)}
          {r.enfileirado ? " — será enviada quando conectar" : r.baixas.length ? ` · baixa no estoque: ${r.baixas.join(", ")}` : ""}
        </span>
      )}
      {r && r.avisos.length > 0 && (
        <span style={{ color: "var(--text-muted)", display: "block" }}>
          <CalendarClock size={13} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4, display: "inline" }} />{" "}
          {r.avisos.join(" ")}
        </span>
      )}
      {r && r.puladas.length > 0 && <span style={{ color: "var(--text-muted)" }}>Cancelado sem lançar: {r.puladas.join(", ")}.</span>}
      {r && r.movimentos.length > 0 && <span role="status" style={{ color: "var(--ft-verde)" }}>{r.movimentos.join(" ")}</span>}
      {r && r.falhados.length > 0 && (
        <span role="alert" style={{ color: "var(--ft-verm)" }}>
          {r.salvos.length ? "Falharam" : "Nenhuma secagem lançada. Falharam"}: {r.falhados.join(", ")} — voltaram marcadas abaixo, com o formulário preenchido, para tentar de novo só elas.
        </span>
      )}
      {r && r.falhasMov.length > 0 && <span role="alert" style={{ color: "var(--ft-verm)" }}>Não foi possível transferir automaticamente: {r.falhasMov.join(", ")}.</span>}
      {erro && <span role="alert" style={{ color: "var(--ft-verm)" }}>{erro}</span>}
      {conflito && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", paddingTop: "0.45rem", borderTop: "1px solid var(--border)" }}>
          <Selo tom="bloqueio">Já consta como seca</Selo>
          <span style={{ flex: 1, minWidth: "20rem" }}>
            A vaca <b>{conflito.numero}</b> já tem secagem lançada em <b>{formatDate(conflito.secagemAnterior.data_secagem)}</b> ({conflito.secagemAnterior.motivo}) —
            não há lactação aberta em {formatDate(dataSecagem)}. Se aquela foi lançada errada (data errada, lote errado), substitua pela data de agora;
            se foi a certa, cancele só esta vaca (as demais continuam).
          </span>
          <button type="button" className="btn-ghost" onClick={aoCancelar} disabled={resolvendo}>Cancelar este lançamento</button>
          <button type="button" className="btn-primary" onClick={aoSubstituir} disabled={resolvendo}>
            {resolvendo ? "Substituindo…" : `Substituir a secagem de ${formatDate(conflito.secagemAnterior.data_secagem)}`}
          </button>
        </div>
      )}
      {proxima && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", paddingTop: "0.45rem", borderTop: "1px solid var(--border)" }}>
          <Selo tom="atencao">Lote sugerido</Selo>
          <span style={{ flex: 1, minWidth: "18rem" }}>
            Mover a vaca <b>{proxima.numero}</b> para <b>{proxima.lote.rotulo}</b>?{" "}
            <span style={{ color: "var(--text-muted)" }}>
              {fila.length > 1 ? `Mais ${fila.length - 1} na fila depois desta. ` : ""}
              {automatica ? "" : "Para mover sem perguntar: Configurações › Parâmetros › transferir automaticamente."}
            </span>
          </span>
          <button type="button" className="btn-ghost" onClick={aoPular} disabled={transferindo}>Agora não</button>
          <button type="button" className="btn-primary" onClick={aoMover} disabled={transferindo}>{transferindo ? "Movendo…" : "Sim, mover"}</button>
        </div>
      )}
    </div>
  );
}

export function FormSecagem({
  animais, estoque, produtos, numeroInicial,
  salvarSecagem = criarSecagem, salvarMovimentacao = criarMovimentacao,
}: {
  animais: AnimalRow[]; estoque: EstoqueItem[]; produtos: string[]; numeroInicial?: string;
  salvarSecagem?: (dados: DadosSecagem) => Promise<ResultadoSecagem>;
  salvarMovimentacao?: (dados: DadosMovimentacao) => Promise<ResultadoMovimentacao & { enviado?: boolean }>;
}) {
  const [hoje] = useState(hojeLocalIso);
  // Secagem só faz sentido para quem está em lactação — sem este filtro a lista misturava secas, novilhas e machos que só
  // compartilham o grupo_primario.
  const animaisLactacao = useMemo(() => animais.filter(animalEmLactacao), [animais]);
  const porNumeroAnimal = useMemo(() => new Map(animais.map((a) => [a.numero, a])), [animais]);

  // Previsão por vaca (uma chamada). undefined = carregando; null = indisponível (backend antigo/offline): tabela sem previsão.
  const [lista, setLista] = useState<SecagemLista | null | undefined>(undefined);
  const recarregarLista = useCallback(() => { fetchSecagemLista().then(setLista).catch(() => setLista((p) => p ?? null)); }, []);
  useEffect(() => { recarregarLista(); }, [recarregarLista]);
  const linhaPorNumero = useMemo(() => new Map((lista?.animais ?? []).map((l) => [l.numero_matriz, l])), [lista]);

  // Vaca(s): animais ou lote(s). Lote começa SEM ninguém marcado (para não secar por engano quem ficou no lote).
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [mostrar, setMostrar] = useState<FiltroSecagem>(numeroInicial ? "todas" : "proximas");
  const [busca, setBusca] = useState("");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [selAnimal, setSelAnimal] = useState<Set<string>>(() => (numeroInicial ? new Set([numeroInicial]) : new Set()));
  const [selLote, setSelLote] = useState<Set<string>>(new Set());
  const alvo = modo === "lote" ? selLote : selAnimal;
  const setAlvo = modo === "lote" ? setSelLote : setSelAnimal;
  const nVacas = alvo.size;
  const matriz = nVacas === 1 ? Array.from(alvo)[0] : "";
  const alternar = (n: string) => setAlvo((p) => { const s = new Set(p); if (s.has(n)) s.delete(n); else s.add(n); return s; });
  const trocarLote = (id: string) => { setLotesSel((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id])); setSelLote(new Set()); };

  const [infoFallback, setInfoFallback] = useState<{ numero: string; info: Info | null } | null>(null);
  const [prefeitoPara, setPrefeitoPara] = useState(numeroInicial ?? "");
  const [dataSecagem, setDataSecagem] = useState(hoje);
  const [motivo, setMotivo] = useState("");
  const [ecc, setEcc] = useState("");
  const [observacao, setObservacao] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [itens, setItens] = useState<ItemProdutoSecagem[]>([]);
  // "Dosagem" pode ser a dose DE CADA vaca (padrão) ou o TOTAL da aplicação inteira (divide pelo nº de vacas antes de lançar).
  const [modoDosagem, setModoDosagem] = useState<Record<number, ModoDosagem>>({});
  const [aplicado, setAplicado] = useState(true);
  const [vacinaSim, setVacinaSim] = useState(false);
  const [vacinas, setVacinas] = useState<string[]>([]);
  const [vacinasSel, setVacinasSel] = useState<string[]>([]);
  const [vacinaAgora, setVacinaAgora] = useState(false);
  const [semEstoque, setSemEstoque] = useState(false);

  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [andamento, setAndamento] = useState<Record<string, Andamento>>({});
  // Após secar, oferece mover para o(s) lote(s) sugerido(s) — uma fila (secar várias de uma vez pode sugerir lotes diferentes).
  const [filaTransferencia, setFilaTransferencia] = useState<Sugestao[]>([]);
  const [transferindo, setTransferindo] = useState(false);
  // Acumuladores do lote em andamento — em refs porque só são lidos no fim/retomada da fila e ficam vivos entre a pausa
  // (decisão de conflito) e a retomada.
  const salvosRef = useRef<string[]>([]);
  const falhadosRef = useRef<string[]>([]);
  const puladasRef = useRef<string[]>([]);
  const pendentesRef = useRef<Sugestao[]>([]);
  const avisosRef = useRef<Set<string>>(new Set());
  const baixasRef = useRef<string[]>([]);
  const enfileiradoRef = useRef(false);
  const [conflito, setConflito] = useState<ConflitoSecagem | null>(null);
  const [resolvendoConflito, setResolvendoConflito] = useState(false);
  // Configurações > Parâmetros > "transferir para o lote sugerido automaticamente": liga = pula a pergunta e move sozinho.
  const [transferenciaAutomatica, setTransferenciaAutomatica] = useState(false);
  useEffect(() => { fetchTransferenciaLoteAutomatica().then(setTransferenciaAutomatica).catch(() => {}); }, []);

  // Com UMA vaca marcada: DEL, gestação e data prevista — da lista; quem não está nela (ou sem a lista) cai em /secagem-info.
  const linhaDaMatriz = matriz ? linhaPorNumero.get(matriz) : undefined;
  const precisaFallback = !!matriz && lista !== undefined && !linhaDaMatriz;
  const fallbackPronto = !!infoFallback && infoFallback.numero === matriz;
  const carregandoInfo = precisaFallback && !fallbackPronto;
  const info: Info | null = linhaDaMatriz
    ? { del_atual: linhaDaMatriz.del_atual, data_prevista_secagem: linhaDaMatriz.data_prevista_secagem, deve_secar: linhaDaMatriz.deve_secar, motivo_exclusao: linhaDaMatriz.motivo_exclusao, dias_gestacao: linhaDaMatriz.dias_gestacao }
    : fallbackPronto ? infoFallback.info : null;
  useEffect(() => {
    if (!precisaFallback) return;
    let vivo = true;
    fetchSecagemInfo(matriz)
      .then((d: Info) => { if (vivo) setInfoFallback({ numero: matriz, info: d }); })
      .catch(() => { if (vivo) setInfoFallback({ numero: matriz, info: null }); });
    return () => { vivo = false; };
  }, [precisaFallback, matriz]);
  // A data da secagem vem preenchida com a prevista UMA vez por vaca marcada (ajuste na própria renderização, sem efeito):
  // trocar a seleção volta a preencher; dados que chegam depois (recarga da lista) não apagam a data que o usuário digitou.
  if (!matriz && prefeitoPara !== "") setPrefeitoPara("");
  else if (matriz && lista !== undefined && !carregandoInfo && prefeitoPara !== matriz) {
    setPrefeitoPara(matriz);
    if (info?.data_prevista_secagem) setDataSecagem(info.data_prevista_secagem);
  }

  // Vacinas (pré-parto).
  useEffect(() => {
    fetchMedicamentos({ finalidade: "vacina_pre_parto", incluir_sem_estoque: semEstoque }).then((d) => setVacinas((d as { nome: string }[]).map((m) => m.nome))).catch(() => {});
  }, [semEstoque]);

  const nomesEstoque = estoque.map((e) => e.nome);
  // Produto de secagem é de livre escolha — não trava na lista de "aptos para secagem", mostra todo o estoque/produtos.
  const listaProdutos = Array.from(new Set([...produtos, ...nomesEstoque])).slice().sort();
  const atualizarItem = (idx: number, patch: Partial<ItemProdutoSecagem>) => setItens((p) => p.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  const escolherProduto = (idx: number, produto: string) => {
    const compativeis = unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade);
    atualizarItem(idx, { produto, unidade: compativeis[0] || "" });
  };
  const removerItem = (idx: number) => {
    setItens((p) => p.filter((_, i) => i !== idx));
    // as escolhas "por vaca/total" andam junto com o índice da linha
    setModoDosagem((m) => Object.fromEntries(Object.entries(m).filter(([k]) => Number(k) !== idx).map(([k, v]) => [Number(k) > idx ? Number(k) - 1 : Number(k), v])));
  };

  // ── tabela de vacas ──
  const lotesDisponiveis = useMemo(() => {
    const m = new Map<string, number>();
    for (const a of animaisLactacao) if (a.grupo_primario) m.set(a.grupo_primario, (m.get(a.grupo_primario) ?? 0) + 1);
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b, "pt-BR", { numeric: true }));
  }, [animaisLactacao]);
  const diasDe = (n: string) => linhaPorNumero.get(n)?.dias_para_secagem ?? null;
  const filtroEfetivo: FiltroSecagem = lista ? mostrar : "todas";
  const nAtrasadas = (lista?.animais ?? []).filter((l) => (l.dias_para_secagem ?? 0) < 0).length;
  const nProximas = (lista?.animais ?? []).filter((l) => l.dias_para_secagem !== null && l.dias_para_secagem >= 0 && l.dias_para_secagem <= LIMITE_PROXIMAS_DIAS).length;
  const nAteTrintaDias = nAtrasadas + nProximas;

  // Quem já está marcado fica sempre na lista (mesmo fora do filtro): marcação nunca fica invisível.
  const linhas = useMemo(() => {
    const doModo = modo === "lote"
      ? animaisLactacao.filter((a) => !!a.grupo_primario && lotesSel.includes(a.grupo_primario))
      : animaisLactacao.filter((a) => passaFiltroSecagem(filtroEfetivo, linhaPorNumero.get(a.numero)?.dias_para_secagem));
    const marcadas = Array.from(alvo).map((n) => porNumeroAnimal.get(n)).filter((a): a is AnimalRow => !!a);
    const todas = Array.from(new Map([...doModo, ...marcadas].map((a) => [a.numero, a])).values());
    const filtradas = busca.trim() ? todas.filter((a) => casaBusca(a.numero, busca) || alvo.has(a.numero)) : todas;
    return filtradas.sort((a, b) => (linhaPorNumero.get(a.numero)?.dias_para_secagem ?? 9999) - (linhaPorNumero.get(b.numero)?.dias_para_secagem ?? 9999)
      || a.numero.localeCompare(b.numero, "pt-BR", { numeric: true }));
  }, [modo, animaisLactacao, lotesSel, filtroEfetivo, linhaPorNumero, alvo, porNumeroAnimal, busca]);
  const grupos = useMemo(() => agruparPorLote(linhas, (a) => a.grupo_primario), [linhas]);
  const todasMarcadas = linhas.length > 0 && linhas.every((a) => alvo.has(a.numero));
  const marcarTodasDaLista = () => setAlvo(todasMarcadas ? new Set(Array.from(alvo).filter((n) => !linhas.some((a) => a.numero === n))) : new Set([...alvo, ...linhas.map((a) => a.numero)]));
  const atrasadasDaLista = linhas.filter((a) => (diasDe(a.numero) ?? 0) < 0);
  const marcarAtrasadas = () => setAlvo((p) => new Set([...p, ...atrasadasDaLista.map((a) => a.numero)]));

  const motivoRotulo = MOTIVOS_SECAGEM.find((m) => m.v === motivo)?.l.toLowerCase();
  const itensCompletos = produtosParaEnvio(itens, modoDosagem, nVacas);
  const futura = dataSecagem > hoje;
  const baixa = aplicadoEfetivo(aplicado, dataSecagem, hoje) && itensCompletos.length > 0;
  const bloqueio = erroDeSecagem({ nVacas, motivo, vacinaSim, vacinas: vacinasSel, ecc });
  const pendenteDecisao = !!conflito || filaTransferencia.length > 0;
  const podeSalvar = !bloqueio && !!dataSecagem && !salvando && !pendenteDecisao;

  const marcar = (numero: string, a: Andamento) => setAndamento((p) => ({ ...p, [numero]: a }));
  function acumularRetorno(r: ResultadoSecagem) {
    if (r.enviado === false) enfileiradoRef.current = true;
    (r.avisos ?? []).forEach((x) => avisosRef.current.add(x));
  }
  const grupoAtual = (numero: string) => codigoGrupo(animais.find((a) => a.numero === numero)?.grupo_primario);

  // Lote por animal (mesmo padrão do Diagnóstico): registra sucesso/falha por matriz, sem perder a seleção de quem falhou. Pode
  // PAUSAR no meio de um lote quando uma vaca já consta como seca — por isso os acumuladores vivem em refs e a fila é retomável.
  async function processarFilaSecagem(numeros: string[], payloadBase: ConflitoSecagem["payloadBase"]) {
    for (let i = 0; i < numeros.length; i++) {
      const numero = numeros[i];
      try {
        const r = await salvarSecagem({ numero_matriz: numero, ...payloadBase });
        acumularRetorno(r);
        // Cada vaca pode ter uma sugestão diferente (ex.: alguma já está no lote das secas) — só entra na fila quem precisa mudar.
        // Sem internet, `lote_sugerido` nem vem: essa vaca simplesmente não entra na fila de transferência agora.
        if (r.lote_sugerido && grupoAtual(numero) !== r.lote_sugerido.codigo) pendentesRef.current.push({ numero, lote: r.lote_sugerido });
        salvosRef.current.push(numero);
        marcar(numero, "lancada");
      } catch (e) {
        const anterior = (e as { secagemAnterior?: ConflitoSecagem["secagemAnterior"] | null } | null)?.secagemAnterior;
        if (anterior) {
          // Pausa aqui — a decisão (substituir/cancelar) é do usuário.
          marcar(numero, "conflito");
          setConflito({ numero, secagemAnterior: anterior, payloadBase, restantes: numeros.slice(i + 1) });
          return;
        }
        falhadosRef.current.push(numero);
        marcar(numero, "falhou");
      }
    }
    await finalizarLoteSecagem(payloadBase.data_secagem);
  }

  async function finalizarLoteSecagem(dataLote: string) {
    const salvos = salvosRef.current, falhados = falhadosRef.current, puladas = puladasRef.current;
    const pendentes = pendentesRef.current;
    const res: Resultado = {
      salvos: [...salvos], falhados: [...falhados], puladas: [...puladas], enfileirado: enfileiradoRef.current, data: dataLote,
      baixas: enfileiradoRef.current ? [] : [...baixasRef.current], avisos: Array.from(avisosRef.current), movimentos: [], falhasMov: [],
    };
    if (falhados.length) {
      setModo("animal"); setLotesSel([]); setSelLote(new Set()); setSelAnimal(new Set(falhados)); setMostrar("todas");
    } else {
      if (pendentes.length && transferenciaAutomatica) {
        // "Transferir automaticamente" ligado em Configurações > Parâmetros — move sozinho, sem perguntar.
        for (const p of pendentes) {
          try {
            const r = await salvarMovimentacao({ data_movimento: dataLote, motivo: "Secagem", lote_destino_codigo: p.lote.codigo, animais: [p.numero], origem: "sugestao_automatica" });
            if (r.enviado === false) res.movimentos.push(`${p.numero} → ${p.lote.rotulo} (guardado, será enviado ao conectar).`);
            else if ((r.movidos ?? 0) >= 1 && !(r.nao_encontrados || []).includes(p.numero)) res.movimentos.push(`Transferida automaticamente: ${p.numero} → ${p.lote.rotulo}.`);
            else res.falhasMov.push(p.numero);
          } catch { res.falhasMov.push(p.numero); }
        }
      } else if (pendentes.length) {
        // Fila de confirmação, uma de cada vez — cada vaca pode precisar de um lote diferente (ou nenhum, se já estiver no certo).
        setFilaTransferencia(pendentes);
      }
      setSelAnimal(new Set()); setSelLote(new Set()); setLotesSel([]);
      setMotivo(""); setEcc(""); setObservacao(""); setItens([]); setModoDosagem({});
      setVacinaSim(false); setVacinasSel([]); setVacinaAgora(false);
    }
    setResultado(res);
    setSalvando(false);
    recarregarLista();
  }

  async function salvar() {
    setErro(null); setResultado(null);
    if (bloqueio) { setErro(bloqueio); return; }
    const aplicadoEf = aplicadoEfetivo(aplicado, dataSecagem, hoje);
    const produtosParaApi = produtosParaEnvio(itens, modoDosagem, nVacas);
    const payloadBase: ConflitoSecagem["payloadBase"] = {
      data_secagem: dataSecagem, motivo,
      escore_condicao_corporal: numOuNull(ecc),
      observacao: observacao || undefined, responsavel: responsavel || undefined, aplicado: aplicadoEf,
      produtos: produtosParaApi,
      vacinas_pre_parto: vacinaSim ? vacinasSel : [],
      vacina_pre_parto_aplicada_agora: vacinaSim ? vacinaAgora : false,
      vacina_pre_parto: vacinaSim,
    };
    const numeros = Array.from(alvo);
    salvosRef.current = []; falhadosRef.current = []; puladasRef.current = []; pendentesRef.current = [];
    avisosRef.current = new Set(); enfileiradoRef.current = false;
    // O que sai do estoque nesta aplicação (só quando baixa de verdade: data não futura e "aplicados agora").
    baixasRef.current = aplicadoEf
      ? itens.map((it, idx) => ({ it, idx })).filter(({ it }) => it.produto && Number(it.quantidade) > 0 && it.unidade)
          .map(({ it, idx }) => `${it.produto} −${nb(totalAplicado(Number(it.quantidade), modoDosagem[idx], numeros.length), 0)} ${it.unidade}`)
      : [];
    setAndamento((p) => ({ ...p, ...Object.fromEntries(numeros.map((n) => [n, "fila" as Andamento])) }));
    setSalvando(true);
    try {
      await processarFilaSecagem(numeros, payloadBase);
    } catch (e) {
      setErro(mensagemDoErro(e, "Erro ao lançar secagem"));
      setSalvando(false);
    }
  }

  async function resolverConflitoSubstituir() {
    if (!conflito) return;
    setResolvendoConflito(true);
    try {
      const r = await salvarSecagem({ numero_matriz: conflito.numero, ...conflito.payloadBase, substituir_secagem_id: conflito.secagemAnterior.id });
      acumularRetorno(r);
      if (r.lote_sugerido && grupoAtual(conflito.numero) !== r.lote_sugerido.codigo) pendentesRef.current.push({ numero: conflito.numero, lote: r.lote_sugerido });
      salvosRef.current.push(conflito.numero);
      marcar(conflito.numero, "lancada");
    } catch {
      falhadosRef.current.push(conflito.numero);
      marcar(conflito.numero, "falhou");
    } finally {
      setResolvendoConflito(false);
      const { restantes, payloadBase } = conflito;
      setConflito(null);
      await processarFilaSecagem(restantes, payloadBase);
    }
  }

  async function resolverConflitoCancelar() {
    if (!conflito) return;
    puladasRef.current.push(conflito.numero);
    marcar(conflito.numero, "cancelada");
    const { restantes, payloadBase } = conflito;
    setConflito(null);
    await processarFilaSecagem(restantes, payloadBase);
  }

  const proximaTransferencia = filaTransferencia[0] ?? null;
  const acrescentarMovimento = (texto: string) => setResultado((r) => (r ? { ...r, movimentos: [...r.movimentos, texto] } : r));
  async function confirmarTransferenciaLote() {
    if (!proximaTransferencia) return;
    const { numero, lote } = proximaTransferencia;
    setTransferindo(true);
    try {
      const r = await salvarMovimentacao({ data_movimento: dataSecagem, motivo: "Secagem", lote_destino_codigo: lote.codigo, animais: [numero], origem: "sugestao_confirmada" });
      if (r.enviado === false) {
        acrescentarMovimento(`${numero} guardada para mover ao lote ${lote.rotulo} — será enviada quando conectar.`);
        setFilaTransferencia((f) => f.slice(1));
        return;
      }
      const moveuDeFato = (r.movidos ?? 0) >= 1 && !(r.nao_encontrados || []).includes(numero);
      if (!moveuDeFato) throw new Error(`Não foi possível mover ${numero} para o lote ${lote.rotulo}.`);
      acrescentarMovimento(`${numero} movida para o lote ${lote.rotulo}.`);
      setFilaTransferencia((f) => f.slice(1));
    } catch (e) {
      setErro(mensagemDoErro(e, "Erro ao mover para o lote."));
    } finally {
      setTransferindo(false);
    }
  }
  const pularTransferenciaLote = () => setFilaTransferencia((f) => f.slice(1));

  const unico = matriz ? info : null;
  const vacinasVisiveis = vacinas;
  const retorno = (
    <RetornoSecagem
      erro={erro} resultado={resultado} conflito={conflito} resolvendo={resolvendoConflito} dataSecagem={dataSecagem}
      fila={filaTransferencia} transferindo={transferindo} automatica={transferenciaAutomatica}
      aoSubstituir={resolverConflitoSubstituir} aoCancelar={resolverConflitoCancelar} aoMover={confirmarTransferenciaLote} aoPular={pularTransferenciaLote}
    />
  );
  const temRetorno = !!(erro || resultado || conflito || proximaTransferencia);

  return (
    <div style={{ display: "flex", flexDirection: "column", fontSize: "0.85rem", color: "var(--text)" }}>
      <Faixa itens={[
        { rotulo: "Vacas em lactação", valor: lista ? lista.animais.length : animaisLactacao.length },
        { rotulo: "Secar nos próximos 30 dias", valor: lista ? nProximas : "—", tom: nProximas ? "atencao" : undefined },
        { rotulo: "Já passaram da data prevista", valor: lista ? nAtrasadas : "—", tom: nAtrasadas ? "alerta" : undefined },
        { rotulo: "Última secagem lançada", valor: lista?.ultima_secagem ? dataBR(lista.ultima_secagem) : "—" },
      ]} />

      <Passo n={1} id="sc-p1" titulo="Quais vacas secar" direita={
        <span style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }} aria-live="polite">
          {nVacas} {nVacas === 1 ? "marcada" : "marcadas"} · {linhas.length} na lista
        </span>
      }>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "1.5rem" }}>
          <div className="gv-campo">
            <RotuloMini>Escolher por</RotuloMini>
            <Pilulas<"animal" | "lote"> rotulo="Escolher por" valor={modo} onChange={setModo} opcoes={[
              { id: "animal", nome: "Animal(is)", titulo: "Marcar vacas uma a uma" },
              { id: "lote", nome: "Lote(s)", titulo: "Escolher um ou mais lotes — começa sem ninguém marcado" },
            ]} />
          </div>
          {modo === "animal" ? (
            lista ? (
              <div className="gv-campo">
                <RotuloMini>Mostrar</RotuloMini>
                <Pilulas<FiltroSecagem> rotulo="Mostrar" valor={mostrar} onChange={setMostrar} opcoes={[
                  { id: "proximas", nome: "Até 30 dias", n: nAteTrintaDias, titulo: "Secagem prevista em até 30 dias, inclusive as já atrasadas" },
                  { id: "atrasadas", nome: "Atrasadas", n: nAtrasadas },
                  { id: "todas", nome: "Todas", n: animaisLactacao.length },
                ]} />
              </div>
            ) : null
          ) : (
            <div className="gv-campo">
              <RotuloMini>Lotes</RotuloMini>
              <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={trocarLote} opcoes={lotesDisponiveis.map(([l, n]) => ({ id: l, nome: l, n }))} />
            </div>
          )}
          <div className="gv-campo" style={{ minWidth: "13rem" }}>
            <label htmlFor="sc-busca">Buscar vaca</label>
            <input id="sc-busca" type="search" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nº da vaca" />
          </div>
          <span style={{ flex: 1 }} />
          <button type="button" className="btn-ghost" style={BOTAO_COM_ICONE} onClick={marcarAtrasadas} disabled={!atrasadasDaLista.length}>
            <Search size={13} aria-hidden="true" /> Marcar as atrasadas
          </button>
          <button type="button" className="btn-ghost" onClick={() => setAlvo(new Set())} disabled={!nVacas}>Limpar</button>
        </div>

        {modo === "lote" && lotesSel.length === 0 && nVacas === 0 ? (
          <EstadoVazio>Escolha um ou mais lotes. A lista abre sem ninguém marcado, de propósito: quem entra é decisão sua (para não secar por engano quem ficou no lote).</EstadoVazio>
        ) : (
          <div className="gv-tabela-moldura" style={ALTURA_TABELA}>
            <table className="gv-tabela">
              <thead>
                <tr>
                  <th scope="col" style={{ width: "2.4rem" }}>
                    <input type="checkbox" aria-label="Marcar todas as vacas da lista" checked={todasMarcadas} onChange={marcarTodasDaLista} disabled={!linhas.length} />
                  </th>
                  <th scope="col">Nº</th>
                  <th scope="col" style={DIR}>DEL</th>
                  <th scope="col" style={DIR}>Dias de gestação</th>
                  <th scope="col" style={DIR} title="Parto previsto − período seco (60 dias por padrão)">Secagem prevista</th>
                  <th scope="col">Situação</th>
                  <th scope="col">Aviso</th>
                  <th scope="col">Neste lançamento</th>
                </tr>
              </thead>
              <tbody>
                {grupos.map(([lote, vs]) => (
                  <React.Fragment key={lote}>
                    <LinhaGrupo colSpan={8} titulo={lote} n={vs.length} />
                    {vs.map((a) => {
                      const l = linhaPorNumero.get(a.numero);
                      const sit = situacaoSecagem(l?.dias_para_secagem, l?.deve_secar);
                      const semLactacao = lista ? !l : a.em_lactacao === false;
                      const and = andamento[a.numero];
                      return (
                        <tr key={a.numero} className={alvo.has(a.numero) ? "gv-linha-marcada" : undefined}>
                          <td><input type="checkbox" checked={alvo.has(a.numero)} onChange={() => alternar(a.numero)} aria-label={`Marcar a vaca ${a.numero}`} /></td>
                          <td className="gv-forte gv-num">{a.numero}</td>
                          <td className="gv-num gv-dir">{l?.del_atual ?? a.del_dias ?? "—"}</td>
                          <td className="gv-num gv-dir">{l?.dias_gestacao ?? "—"}</td>
                          <td className="gv-num gv-dir">{l?.data_prevista_secagem ? dataBR(l.data_prevista_secagem) : "—"}</td>
                          <td>{lista ? <Selo tom={sit.tom} titulo={sit.titulo}>{sit.texto}</Selo> : <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                          <td className="gv-quebra" style={{ color: "var(--text-muted)", fontSize: "0.78rem", whiteSpace: "normal", minWidth: "12rem" }}>
                            {semLactacao
                              ? <Selo tom="atencao" titulo="Pode já constar como seca: o servidor pede para substituir ou cancelar">Sem lactação aberta</Selo>
                              : l?.deve_secar === false && l.motivo_exclusao ? l.motivo_exclusao
                              : lista && l && l.dias_para_secagem === null ? "Sem data de parto: confirme a prenhez antes" : ""}
                          </td>
                          <td>{and ? <SeloAndamento a={and} /> : <span style={{ color: "var(--text-muted)" }}>—</span>}</td>
                        </tr>
                      );
                    })}
                  </React.Fragment>
                ))}
                {!linhas.length && <tr><td colSpan={8} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma vaca neste filtro.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <NotaInfo>
          Só aparecem vacas em lactação (lote de lactação ou DEL em curso). A data prevista é 60 dias antes do parto; “sem prenhez” e “atrasada” informam, não impedem.
          Com uma só vaca marcada, a data da secagem vem preenchida com a prevista.
          {lista === null ? " A previsão por vaca não carregou (sem conexão ou servidor desatualizado): a tabela mostra só o que o cadastro tem." : ""}
        </NotaInfo>
        {matriz && (
          carregandoInfo ? <p className="gv-ajuda">Carregando dados da vaca {matriz}…</p>
            : unico ? (
              <p className="gv-ajuda">
                <b style={{ color: "var(--text)" }}>Vaca {matriz}:</b> DEL {unico.del_atual ?? "—"} · {unico.dias_gestacao ?? "—"} dias de gestação · secagem prevista {unico.data_prevista_secagem ? formatDate(unico.data_prevista_secagem) : "—"}.
                {unico.motivo_exclusao && <span style={{ color: "var(--ft-ambar)" }}> {unico.motivo_exclusao}</span>}
              </p>
            ) : null
        )}
      </Passo>

      <Passo n={2} id="sc-p2" titulo="Dados da secagem">
        <div className="gv-grade" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))" }}>
          <Campo rotulo="Data da secagem" id="sc-data"><input type="date" value={dataSecagem} onChange={(e) => setDataSecagem(e.target.value)} /></Campo>
          <Campo rotulo="Motivo (obrigatório)" id="sc-motivo">
            <select value={motivo} onChange={(e) => setMotivo(e.target.value)}>
              <option value="" disabled>Selecione…</option>
              {MOTIVOS_SECAGEM.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
            </select>
          </Campo>
          <Campo rotulo="ECC (1 a 5, opcional)" id="sc-ecc"><input type="number" step={0.25} min={1} max={5} value={ecc} onChange={(e) => setEcc(e.target.value)} placeholder="ex.: 3,25" /></Campo>
          <Campo rotulo="Responsável" id="sc-resp">
            <select value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
              <option value="">Selecione…</option>
              {nomesResponsaveis.map((r) => <option key={r}>{r}</option>)}
            </select>
          </Campo>
          <Campo rotulo="Observação" id="sc-obs"><input value={observacao} onChange={(e) => setObservacao(e.target.value)} placeholder="opcional" /></Campo>
        </div>
        <Ajuda>A data pode ser retroativa. Escore de condição corporal em passos de 0,25 (opcional). O que você escolher aqui vale para todas as vacas marcadas.</Ajuda>
      </Passo>

      <Passo n={3} id="sc-p3" titulo="Produtos de secagem (opcional)" direita={
        <button type="button" className="btn-ghost" style={BOTAO_COM_ICONE} onClick={() => setItens((x) => [...x, { produto: "", via: "", quantidade: "", unidade: "" }])}>
          <Plus size={14} aria-hidden="true" /> Acrescentar produto
        </button>
      }>
        {itens.length === 0 ? (
          <p className="gv-ajuda">Sem produtos: a secagem é lançada sem baixa de estoque. Use “Acrescentar produto” se aplicou antibiótico, selante ou outro.</p>
        ) : (
          <div className="gv-tabela-moldura" style={SEM_ALTURA}>
            <table className="gv-tabela">
              <thead>
                <tr>
                  <th scope="col">Produto</th><th scope="col">Via</th><th scope="col" style={DIR}>Dosagem</th><th scope="col">Unidade</th>
                  <th scope="col">A dosagem é</th><th scope="col" style={DIR}>Total da aplicação</th><th scope="col">Estoque depois</th><th scope="col" aria-label="Remover"></th>
                </tr>
              </thead>
              <tbody>
                {itens.map((it, i) => {
                  const est = estoque.find((e) => e.nome === it.produto);
                  const compativeis = unidadesCompativeis(est?.unidade);
                  const q = Number(it.quantidade) || 0;
                  const modoD = modoDosagem[i] ?? "por_vaca";
                  const total = totalAplicado(q, modoD, nVacas);
                  const porVaca = modoD === "total" && nVacas > 1 ? q / nVacas : q;
                  const atual = est?.quantidade ?? null;
                  const restante = atual !== null ? atual - total : null;
                  return (
                    <tr key={i}>
                      <td>
                        <select className="gv-celula-input" style={{ width: "19rem", textAlign: "left" }} aria-label={`Produto ${i + 1}`} value={it.produto} onChange={(e) => escolherProduto(i, e.target.value)}>
                          <option value="" disabled>Selecione…</option>
                          {listaProdutos.map((nome) => {
                            const e = estoque.find((x) => x.nome === nome);
                            return <option key={nome} value={nome}>{nome}{e?.quantidade != null ? ` (${e.quantidade} ${e.unidade || ""})` : ""}</option>;
                          })}
                        </select>
                      </td>
                      <td>
                        <select className="gv-celula-input" style={{ width: "8.8rem", textAlign: "left" }} aria-label={`Via do produto ${i + 1}`} value={it.via} onChange={(e) => atualizarItem(i, { via: e.target.value })}>
                          <option value="">Selecione…</option>{VIAS.map((v) => <option key={v}>{v}</option>)}
                        </select>
                      </td>
                      <td className="gv-dir"><input className="gv-celula-input" style={{ width: "4.5rem" }} type="number" inputMode="decimal" min="0" aria-label={`Dosagem do produto ${i + 1}`} value={it.quantidade} onChange={(e) => atualizarItem(i, { quantidade: e.target.value })} /></td>
                      <td>
                        <select className="gv-celula-input" style={{ width: "6rem", textAlign: "left" }} aria-label={`Unidade do produto ${i + 1}`} value={it.unidade} onChange={(e) => atualizarItem(i, { unidade: e.target.value })}>
                          <option value="" disabled>—</option>
                          {compativeis.map((u) => <option key={u}>{u}</option>)}
                        </select>
                      </td>
                      <td>
                        {nVacas > 1 ? (
                          <fieldset style={{ ...GRUPO_RADIO, flexWrap: "nowrap", whiteSpace: "nowrap" }} role="radiogroup" aria-label={`Como a dosagem do produto ${i + 1} vale`}>
                            <label style={ROTULO_RADIO}><input type="radio" name={`dose-${i}`} checked={modoD === "por_vaca"} onChange={() => setModoDosagem((p) => ({ ...p, [i]: "por_vaca" }))} /> por vaca</label>
                            <label style={ROTULO_RADIO}><input type="radio" name={`dose-${i}`} checked={modoD === "total"} onChange={() => setModoDosagem((p) => ({ ...p, [i]: "total" }))} /> total ÷ {nVacas}</label>
                          </fieldset>
                        ) : <span style={{ color: "var(--text-muted)" }}>por vaca</span>}
                      </td>
                      <td className="gv-num gv-dir">
                        {q > 0 ? (modoD === "total" && nVacas > 1 ? `${nb(porVaca, 2)} × ${nVacas} = ${nb(q, 0)} ${it.unidade}` : `${nb(q, 0)} × ${Math.max(1, nVacas)} = ${nb(total, 0)} ${it.unidade}`) : "—"}
                      </td>
                      <td>
                        {est && q > 0 && atual !== null && restante !== null ? (
                          restante < 0
                            ? <span className="gv-num" style={{ display: "inline-flex", alignItems: "center", gap: "0.45rem" }}>{nb(atual, 0)} → <b style={{ color: "var(--ft-verm)" }}>{nb(restante, 0)}</b><Selo tom="atencao" titulo="Informa, não bloqueia: confira o estoque">Insuficiente</Selo></span>
                            : <span className="gv-num">{nb(atual, 0)} → <b>{nb(restante, 0)}</b> {est.unidade || ""}</span>
                        ) : <span style={{ color: "var(--text-muted)" }}>—</span>}
                      </td>
                      <td className="gv-dir">
                        <button type="button" className="btn-ghost" style={BOTAO_COM_ICONE} aria-label={`Remover o produto ${i + 1}`} title="Remover este produto" onClick={() => removerItem(i)}>
                          <Trash2 size={13} aria-hidden="true" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {itens.some((i) => i.produto) && (futura ? (
          <Aviso><CalendarClock size={15} aria-hidden="true" style={{ flexShrink: 0, marginTop: "0.1rem" }} /><span>Data futura: os produtos serão <b>programados na Agenda</b>; o estoque só baixa quando você der baixa lá.</span></Aviso>
        ) : (
          <fieldset style={GRUPO_RADIO} role="radiogroup" aria-label="Os produtos já foram aplicados?">
            <legend style={LEGENDA}>Aplicados agora?</legend>
            <label style={ROTULO_RADIO}><input type="radio" name="sc-aplicado" checked={aplicado} onChange={() => setAplicado(true)} /> Sim — aplicar e baixar o estoque agora</label>
            <label style={ROTULO_RADIO}><input type="radio" name="sc-aplicado" checked={!aplicado} onChange={() => setAplicado(false)} /> Não — só programar na Agenda</label>
          </fieldset>
        ))}
      </Passo>

      <Passo n={4} id="sc-p4" titulo="Vacina pré-parto (opcional)">
        <fieldset style={GRUPO_RADIO} role="radiogroup" aria-label="Aplicar vacina pré-parto?">
          <label style={ROTULO_RADIO}><input type="radio" name="sc-vacina" checked={!vacinaSim} onChange={() => { setVacinaSim(false); setVacinasSel([]); }} /> Não</label>
          <label style={ROTULO_RADIO}><input type="radio" name="sc-vacina" checked={vacinaSim} onChange={() => setVacinaSim(true)} /> Sim — aplicar vacina(s) pré-parto</label>
        </fieldset>
        {vacinaSim && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem", paddingLeft: "0.2rem" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1.5rem", alignItems: "center" }}>
              {vacinasVisiveis.map((nome) => {
                const e = estoque.find((x) => x.nome === nome);
                return (
                  <label key={nome} style={ROTULO_RADIO}>
                    <input type="checkbox" checked={vacinasSel.includes(nome)} style={{ accentColor: "var(--ft-ouro)", width: "1.05rem", height: "1.05rem" }}
                      onChange={() => setVacinasSel((p) => (p.includes(nome) ? p.filter((x) => x !== nome) : [...p, nome]))} />
                    {nome}{e ? <span style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>{(e.quantidade ?? 0) > 0 ? `estoque ${e.quantidade} ${e.unidade || ""}` : "sem estoque"}</span> : null}
                  </label>
                );
              })}
              <label style={{ ...ROTULO_RADIO, color: "var(--text-muted)", fontSize: "0.76rem" }}>
                <input type="checkbox" checked={semEstoque} onChange={(e) => setSemEstoque(e.target.checked)} style={{ accentColor: "var(--ft-ouro)" }} /> Incluir itens sem estoque
              </label>
            </div>
            {!vacinasVisiveis.length && (
              <Ajuda>Nenhuma vacina com estoque disponível. Marque “Incluir itens sem estoque” para ver também as vacinas sem saldo cadastrado.</Ajuda>
            )}
            {vacinasSel.length === 0 && <Aviso tom="erro">Marque ao menos uma vacina pré-parto, ou volte para “Não”.</Aviso>}
            {vacinasSel.length > 0 && (
              <>
                <fieldset style={GRUPO_RADIO} role="radiogroup" aria-label="As vacinas já foram aplicadas agora?">
                  <legend style={LEGENDA}>Já aplicada agora?</legend>
                  <label style={ROTULO_RADIO}><input type="radio" name="sc-vacina-agora" checked={!vacinaAgora} onChange={() => setVacinaAgora(false)} /> Não, aplico depois</label>
                  <label style={ROTULO_RADIO}><input type="radio" name="sc-vacina-agora" checked={vacinaAgora} onChange={() => setVacinaAgora(true)} /> Sim, já apliquei</label>
                </fieldset>
                <Ajuda>
                  {vacinaAgora
                    ? "Registra a aplicação em Sanidade e dá baixa no estoque agora; não cria pendência na Agenda."
                    : `Cria uma pendência na Agenda para ${dataSecagem ? dataBR(somarDias(dataSecagem, 1)) : "o dia seguinte"} (dia seguinte à secagem), com a vaca e a(s) vacina(s) a aplicar.`}
                </Ajuda>
              </>
            )}
          </div>
        )}
      </Passo>

      <BarraAcao
        retorno={temRetorno ? retorno : undefined}
        resumo={`${nVacas} ${nVacas === 1 ? "vaca" : "vacas"} · motivo ${motivoRotulo ?? "— escolha"} · ${
          itensCompletos.length === 0 ? "sem produtos" : `${baixa ? "baixa" : "programa"} ${itensCompletos.length} ${itensCompletos.length === 1 ? "produto" : "produtos"}`}`}
        detalhe={`Secagem em ${dataSecagem ? dataBR(dataSecagem) : "—"}${futura ? " (futura)" : ""}${vacinaSim && vacinasSel.length ? ` · vacina pré-parto: ${vacinasSel.length}${vacinaAgora ? " (aplicada agora)" : " (pendência na Agenda)"}` : ""}${!motivo ? " · falta o motivo" : ""}${pendenteDecisao ? " · responda a decisão acima" : ""}`}
        secundaria={resultado && !pendenteDecisao && !salvando ? <button type="button" className="btn-ghost" onClick={() => { setResultado(null); setErro(null); }}>Fechar aviso</button> : undefined}
        acao={<BotaoOuro onClick={salvar} desabilitado={!podeSalvar}>{salvando ? "Salvando…" : `Salvar (${nVacas})`}</BotaoOuro>}
      />
    </div>
  );
}
