"use client";
import { useEffect, useMemo, useState } from "react";
import { Wheat, Users, Scale, PlusCircle, Trash2, CheckCircle2, TriangleAlert, Info, Loader2, Truck } from "lucide-react";
import {
  fetchLotes, fetchAlimentos, fetchParametros,
  fetchDietaDoLote, fetchConsumoDoDia, fetchJanelaSobra, lancarConsumo, lancarSobra,
  type ConsumoDoDia, type ConsumoItemIn, type DietaDoLote, type JanelaSobra,
} from "@/lib/api";
import { opcoesPosicaoLeitura } from "@/lib/tratos";
import { Campo, inputStyle, nota } from "@/components/lancamentos/comumForms";
import { UNIDADES } from "@/components/lancamentos/_shared";

/* ─────────────────────────────────────────────────────────────────────────
   Lançamentos > Alimentação — consumo diário e sobra de cocho (sessão 3,
   Frente D; redesenho de 23/09/2026). Antes esta aba lançava a DIETA
   (CadastrarNovaDieta, que mudou de casa para Insumos e sanidade >
   Alimentação > "Lançar nova dieta" — ver app/alimentacao/page.tsx). Agora é
   aqui que o funcionário registra o que de fato foi fornecido no cocho, lote
   por lote, todo dia — em DUAS sub-abas, refletindo o fluxo real: o
   funcionário mede a sobra de ONTEM primeiro, lança, e só depois abastece o
   vagão de hoje.

   "Lote" aqui é o INT de DietaLancamento.lote (mesma linguagem do endpoint),
   não o "01 - Nome" de Animal.grupo_primario usado nos outros Form* desta
   pasta — por isso a lista de lotes vem de fetchLotes() (cadastro de lotes,
   Lote.codigo/nome), não do array `lotes` calculado a partir dos animais.
   A ponte entre os dois mundos é `Number(lote.codigo)` ⇄ `f"{lote:02d}"`.

   Modo "Quantidade direta" (23/09/2026): o funcionário não digita mais o kg
   de CADA alimento — ele informa só o kg TOTAL ofertado no vagão, e a
   quantidade de cada alimento é derivada da % dele na dieta cadastrada
   (calculada no SERVIDOR, nunca no cliente — ver origem "vagao" em
   lancarConsumo/POST /alimentacao/consumo, mesma postura de "não confiar no
   cliente" que o modo "por nº de animais" já tinha). Só os itens cuja
   unidade não converte para kg (litro, dose, unidade) continuam com input
   manual — não tem como saber que fração de um vagão em quilos é "1 dose".

   Tratos por dieta (21/10/2026): com o parâmetro "lançar consumo por trato"
   ligado (Parâmetros > Alimentação), cada fornecimento diz de qual trato da
   dieta é. A sobra se refere a um CICLO DE 24h definido pela posição da
   leitura cadastrada na dieta (entre quais tratos é lida — lib/tratos.ts), e
   antes de gravar a tela sempre mostra o período pré-montado para Confirmar /
   Selecionar outro período / Cancelar (GET /alimentacao/sobra/janela).
   ───────────────────────────────────────────────────────────────────── */

type LoteCadastro = {
  id: number; codigo: string; nome: string; ativo?: boolean;
  // Colunas novas do lote (Frente A). Podem ainda não estar sendo devolvidas
  // pelo router de /lotes/ enquanto essa ponta não for atualizada em paralelo
  // — por isso tratamos ausência como "false" (mesmo padrão restritivo do
  // valor default no banco), nunca como "true" por engano.
  permitir_fora_da_dieta?: boolean;
  permitir_sem_estoque?: boolean;
};

type ItemExtra = { alimento: string; quantidade: string; unidade: string };
const itemExtraVazio = (): ItemExtra => ({ alimento: "", quantidade: "", unidade: "kg" });

const fmt = (v: number) => Number(v.toFixed(2)).toLocaleString("pt-BR");
const hojeIso = () => new Date().toISOString().slice(0, 10);
const ontemIso = () => { const d = new Date(); d.setDate(d.getDate() - 1); return d.toISOString().slice(0, 10); };
const fmtDataBR = (iso: string) => { const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; };

export function ConsumoAlimento({ onSalvo }: { onSalvo?: () => void }) {
  const [lotesCadastro, setLotesCadastro] = useState<LoteCadastro[] | null>(null);
  const [alimentosCadastro, setAlimentosCadastro] = useState<{ id: number; nome: string }[]>([]);
  // sobra_alvo_pct/min/max — Configurações > Parâmetros > Alimentação
  // (Frente A). Defaults abaixo só cobrem o instante antes da resposta chegar.
  const [paramAlim, setParamAlim] = useState({ alvo: 5, min: 3, max: 7 });
  // modo_lancamento_alimentacao: "fornecido_sobra" (padrão, tela normal) ·
  // "baixa_automatica" (baixa diária sozinha, sem lançamento) · "nao_lancar".
  // `undefined` = ainda não sabemos (evita piscar a explicação errada
  // enquanto o parâmetro não chegou).
  const [modo, setModo] = useState<string | undefined>(undefined);

  useEffect(() => {
    fetchLotes().then(setLotesCadastro).catch(() => setLotesCadastro([]));
    fetchAlimentos()
      .then((d) => setAlimentosCadastro(d.filter((a) => a.ativo !== false).map((a) => ({ id: a.id, nome: a.nome }))))
      .catch(() => {});
    fetchParametros()
      .then((d) => {
        const itens: any[] = d?.grupos?.alimentacao?.itens ?? [];
        const valor = (chave: string, padrao: number) => {
          const it = itens.find((i) => i.chave === chave);
          const n = it ? Number(it.valor) : NaN;
          return Number.isFinite(n) ? n : padrao;
        };
        setParamAlim({ alvo: valor("sobra_alvo_pct", 5), min: valor("sobra_min_pct", 3), max: valor("sobra_max_pct", 7) });
        setModo(String(itens.find((i) => i.chave === "modo_lancamento_alimentacao")?.valor ?? "fornecido_sobra"));
      })
      .catch(() => setModo("fornecido_sobra"));
  }, []);

  const [subTab, setSubTab] = useState<"fornecimento" | "sobra">("fornecimento");
  const [loteCodigo, setLoteCodigo] = useState("");
  const [data, setData] = useState(hojeIso);
  const [origem, setOrigem] = useState<"animais" | "kg">("animais");
  const [numAnimais, setNumAnimais] = useState("");
  const [kgVagao, setKgVagao] = useState("");
  // Só para os itens da dieta que NÃO convertem para kg (percentual_dieta
  // null) — os demais são derivados de `kgVagao`, não digitados aqui.
  const [quantidadesKg, setQuantidadesKg] = useState<Record<string, string>>({});
  const [extras, setExtras] = useState<ItemExtra[]>([]);

  // Sobra tem data PRÓPRIA (item novo, 23/09/2026). Dieta SEM posição da
  // leitura cadastrada (comportamento antigo): é o dia do fornecimento a que
  // a sobra se refere — em regra o dia ANTERIOR (o funcionário mede a sobra
  // de ontem antes de abastecer o vagão de hoje), por isso o padrão "ontem".
  // Dieta COM posição: é a data da LEITURA (padrão hoje) e o período sai da
  // posição — ex.: lida entre o Trato 2 e o Trato 1 hoje = tratos de ontem.
  const [dataSobra, setDataSobra] = useState(ontemIso);
  const [kgSobra, setKgSobra] = useState("");
  // Confirmação do período ("A sobra se refere ao…?") e "Selecionar outro
  // período": undefined = posição da dieta; "civil" = dia inteiro do
  // fornecimento (comportamento antigo); número = outra posição da leitura.
  const [confirmandoSobra, setConfirmandoSobra] = useState(false);
  const [outroPeriodo, setOutroPeriodo] = useState(false);
  const [escolhaSobra, setEscolhaSobra] = useState<number | "civil" | undefined>(undefined);
  const [janela, setJanela] = useState<JanelaSobra | null>(null);
  const [trato, setTrato] = useState("");

  // undefined = ainda carregando · null = lote sem dieta ativa (404 do backend)
  const [dietaInfo, setDietaInfo] = useState<DietaDoLote | null | undefined>(undefined);
  const [consumoHoje, setConsumoHoje] = useState<ConsumoDoDia | null>(null);

  const [enviando, setEnviando] = useState(false);
  const [enviandoSobra, setEnviandoSobra] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [erroSobra, setErroSobra] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [sucessoSobra, setSucessoSobra] = useState<string | null>(null);

  const loteObj = useMemo(() => lotesCadastro?.find((l) => l.codigo === loteCodigo) ?? null, [lotesCadastro, loteCodigo]);
  const loteSel = loteCodigo ? Number(loteCodigo) : null;

  useEffect(() => {
    if (!loteSel) { setDietaInfo(undefined); return; }
    let cancelado = false;
    setDietaInfo(undefined);
    fetchDietaDoLote(loteSel).then((d) => {
      if (cancelado) return;
      setDietaInfo(d);
      setDataSobra(d?.sobra_posicao_leitura != null ? hojeIso() : ontemIso());
    }).catch(() => { if (!cancelado) setDietaInfo(null); });
    return () => { cancelado = true; };
  }, [loteSel]);

  useEffect(() => {
    if (!loteSel) { setConsumoHoje(null); return; }
    let cancelado = false;
    fetchConsumoDoDia(loteSel, data).then((d) => { if (!cancelado) setConsumoHoje(d); }).catch(() => { if (!cancelado) setConsumoHoje(null); });
    return () => { cancelado = true; };
  }, [loteSel, data]);

  // Período (janela de tratos) a que a sobra lida em `dataSobra` se refere,
  // com o fornecido nessa janela (base da sobra %) e a sobra já lançada para
  // o mesmo ciclo — é o resumo que a confirmação mostra.
  const [versaoSobra, setVersaoSobra] = useState(0);
  useEffect(() => {
    if (!loteSel) { setJanela(null); return; }
    let cancelado = false;
    fetchJanelaSobra({
      lote: loteSel, data: dataSobra,
      posicao_leitura: typeof escolhaSobra === "number" ? escolhaSobra : null, dia_civil: escolhaSobra === "civil",
    }).then((j) => { if (!cancelado) setJanela(j); }).catch(() => { if (!cancelado) setJanela(null); });
    return () => { cancelado = true; };
  }, [loteSel, dataSobra, escolhaSobra, versaoSobra]);

  const itensDieta = dietaInfo?.itens ?? [];
  // Itens da dieta sem conversão para kg — ficam fora da tabela automática
  // (Fornecimento) e fora do rateio de sobra (Sobra de cocho), sempre pelo
  // mesmo critério (`converte_para_kg`/`percentual_dieta` null).
  const itensSemConversao = itensDieta.filter((it) => !it.converte_para_kg);
  // Parâmetro da fazenda "lançar consumo por trato" (Parâmetros > Alimentação).
  const porTrato = !!dietaInfo?.consumo_por_trato;

  function selecionarLote(codigo: string) {
    setLoteCodigo(codigo);
    setNumAnimais(""); setQuantidadesKg({}); setExtras([]); setKgVagao(""); setKgSobra(""); setTrato("");
    setConfirmandoSobra(false); setOutroPeriodo(false); setEscolhaSobra(undefined);
    setErro(null); setAvisos([]); setSucesso(null); setErroSobra(null); setSucessoSobra(null);
  }

  const acrescentarExtra = () => setExtras((p) => [...p, itemExtraVazio()]);
  const atualizarExtra = (idx: number, patch: Partial<ItemExtra>) => setExtras((p) => { const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n; });
  const removerExtra = (idx: number) => setExtras((p) => p.filter((_, i) => i !== idx));

  function montarItens(): ConsumoItemIn[] {
    let base: ConsumoItemIn[];
    if (origem === "animais") {
      const n = Number(numAnimais);
      base = !n || n <= 0
        ? []
        : itensDieta
            .filter((it) => it.por_cabeca != null)
            .map((it) => ({ alimento: it.alimento, alimento_id: it.alimento_id, unidade: it.unidade, quantidade: Number((it.por_cabeca! * n).toFixed(3)) }));
    } else {
      // "Quantidade direta": só os itens SEM conversão para kg entram como
      // item explícito — os demais são resolvidos no servidor a partir de
      // `kgVagao` (origem "vagao", ver enviarConsumo).
      base = itensSemConversao
        .filter((it) => Number(quantidadesKg[it.alimento]) > 0)
        .map((it) => ({ alimento: it.alimento, alimento_id: it.alimento_id, unidade: it.unidade, quantidade: Number(quantidadesKg[it.alimento]) }));
    }
    const foraDaDieta: ConsumoItemIn[] = extras
      .filter((e) => e.alimento && Number(e.quantidade) > 0)
      .map((e) => ({ alimento: e.alimento, alimento_id: alimentosCadastro.find((a) => a.nome === e.alimento)?.id ?? null, unidade: e.unidade, quantidade: Number(e.quantidade) }));
    return [...base, ...foraDaDieta];
  }

  async function enviarConsumo() {
    setErro(null); setSucesso(null); setAvisos([]);
    if (!loteSel) { setErro("Selecione um lote."); return; }
    if (dietaInfo === null) { setErro("Este lote não tem dieta ativa — cadastre uma em Insumos e sanidade > Alimentação > Lançar nova dieta."); return; }
    if (porTrato && !trato) { setErro("Informe de qual trato é este fornecimento."); return; }
    if (origem === "animais" && !(Number(numAnimais) > 0)) { setErro("Informe o número de animais."); return; }
    if (origem === "kg" && !(Number(kgVagao) > 0)) { setErro("Informe o kg total ofertado no vagão."); return; }
    const itens = montarItens();
    if (origem === "animais" && !itens.length) { setErro("Informe ao menos um alimento com quantidade."); return; }
    setEnviando(true);
    try {
      const resp = await lancarConsumo({
        lote: loteSel, data, num_animais: origem === "animais" ? Number(numAnimais) : null,
        origem: origem === "kg" ? "vagao" : "animais",
        kg_vagao: origem === "kg" ? Number(kgVagao) : null,
        itens,
        ...(porTrato ? { trato: Number(trato) } : {}),
      });
      setAvisos(resp.avisos || []);
      setSucesso("Consumo lançado.");
      setNumAnimais(""); setQuantidadesKg({}); setExtras([]); setKgVagao(""); setTrato("");
      setConsumoHoje(await fetchConsumoDoDia(loteSel, data));
      onSalvo?.();
    } catch (e: any) {
      // Mensagem do backend já vem clara (409 de fora-da-dieta / sem-estoque
      // inclusos) — ver mensagemErroApi em lib/api.ts. É ela que explica a
      // recusa ao usuário (item D8 da spec).
      setErro(e.message || "Erro ao lançar consumo.");
    } finally {
      setEnviando(false);
    }
  }

  const kgFornecidoJanela = janela?.kg_fornecido_janela ?? 0;
  const previewPct = kgSobra !== "" && kgFornecidoJanela > 0 ? (Number(kgSobra) / kgFornecidoJanela) * 100 : null;
  const statusFaixa = (pct: number | null): "abaixo" | "dentro" | "acima" | null => {
    if (pct == null) return null;
    if (pct < paramAlim.min) return "abaixo";
    if (pct > paramAlim.max) return "acima";
    return "dentro";
  };
  const corFaixa = (s: "abaixo" | "dentro" | "acima" | null) => (s === "dentro" ? "var(--green-light)" : s === null ? "var(--text-muted)" : "var(--amber)");

  // Registrar sobra = primeiro mostrar o período pré-montado; só "Confirmar"
  // grava (decisão do dono — a confirmação aparece SEMPRE).
  function pedirConfirmacaoSobra() {
    setErroSobra(null); setSucessoSobra(null);
    if (!loteSel) { setErroSobra("Selecione um lote."); return; }
    if (kgSobra.trim() === "" || !(Number(kgSobra) >= 0)) { setErroSobra("Informe a sobra em kg."); return; }
    if (!janela) { setErroSobra("Não foi possível montar o período da sobra — confira a conexão e tente de novo."); return; }
    setOutroPeriodo(false);
    setConfirmandoSobra(true);
  }

  function cancelarSobra() {
    setConfirmandoSobra(false); setOutroPeriodo(false); setEscolhaSobra(undefined);
  }

  async function enviarSobra() {
    setErroSobra(null); setSucessoSobra(null);
    if (!loteSel) { setErroSobra("Selecione um lote."); return; }
    const kg = Number(kgSobra);
    if (!(kg >= 0)) { setErroSobra("Informe a sobra em kg."); return; }
    setEnviandoSobra(true);
    try {
      const r = await lancarSobra({
        lote: loteSel, data: dataSobra, kg_sobra: kg,
        ...(escolhaSobra === "civil" ? { dia_civil: true } : typeof escolhaSobra === "number" ? { posicao_leitura: escolhaSobra } : {}),
      });
      setSucessoSobra(`${r.substituiu ? "Sobra substituída" : "Sobra registrada"}${r.sobra_pct != null ? ` — ${fmt(r.sobra_pct)}% do fornecido no período` : ""}.`);
      setKgSobra("");
      cancelarSobra();
      setVersaoSobra((v) => v + 1);
      onSalvo?.();
    } catch (e: any) {
      setErroSobra(e.message || "Erro ao lançar sobra.");
    } finally {
      setEnviandoSobra(false);
    }
  }

  // Item D10 — "nao_lancar" já esconde a aba inteira lá em cima (Lançamentos
  // > Alimentação some do menu, ver app/lancamentos/page.tsx); a mensagem
  // aqui é só uma rede de segurança para quem chegar por um link antigo.
  if (modo === "nao_lancar") {
    return (
      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><Wheat size={15} /> Consumo do dia</div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>O lançamento manual de consumo está desativado em Parâmetros &gt; Alimentação.</p>
      </div>
    );
  }
  if (modo === "baixa_automatica") {
    return (
      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><Wheat size={15} /> Consumo do dia</div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
          A baixa de estoque da alimentação é diária e automática, de acordo com a dieta cadastrada de cada lote — não é preciso lançar
          consumo aqui. Para mudar esse comportamento, veja Parâmetros &gt; Alimentação.
        </p>
      </div>
    );
  }

  const kgVagaoNum = Number(kgVagao) || 0;
  const posicaoDieta = dietaInfo?.sobra_posicao_leitura ?? null;
  const posicaoSobra = escolhaSobra === undefined ? posicaoDieta : escolhaSobra === "civil" ? null : escolhaSobra;
  const nTratos = dietaInfo?.num_tratos ?? 2;
  const itensComPercentual = itensDieta.filter((it) => it.percentual_dieta != null);

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><Wheat size={15} /> Alimentação — consumo do dia</div>

        <div style={{ maxWidth: "20rem", marginBottom: "0.8rem" }}>
          <Campo label="Lote">
            <select style={inputStyle} value={loteCodigo} onChange={(e) => selecionarLote(e.target.value)}>
              <option value="">Selecione...</option>
              {(lotesCadastro ?? []).filter((l) => l.ativo !== false).map((l) => (
                <option key={l.id} value={l.codigo}>{l.codigo} - {l.nome}</option>
              ))}
            </select>
          </Campo>
        </div>

        {loteObj && (
          <p style={{ ...nota, marginLeft: 0, marginBottom: "0.8rem" }}>
            {loteObj.permitir_fora_da_dieta ? "Aceita alimentos fora da dieta." : "Só aceita os alimentos da dieta cadastrada."}
            {" · "}
            {loteObj.permitir_sem_estoque ? "Aceita lançar mesmo sem saldo em estoque." : "Bloqueia lançamento sem saldo em estoque."}
          </p>
        )}

        {!loteSel && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Escolha um lote para lançar.</p>}

        {loteSel && (
          <div className="flex flex-wrap gap-2 mb-3">
            <button type="button" className={subTab === "fornecimento" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setSubTab("fornecimento")}>
              <Truck size={14} /> Fornecimento
            </button>
            <button type="button" className={subTab === "sobra" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setSubTab("sobra")}>
              <Scale size={14} /> Sobra de cocho
            </button>
          </div>
        )}

        {loteSel && subTab === "fornecimento" && dietaInfo === undefined && (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Loader2 size={14} className="animate-spin" /> Carregando dieta do lote...
          </p>
        )}

        {loteSel && subTab === "fornecimento" && dietaInfo === null && (
          <div className="alert-critico"><TriangleAlert size={16} /><span>Este lote não tem dieta ativa. Cadastre em Insumos e sanidade &gt; Alimentação &gt; Lançar nova dieta.</span></div>
        )}

        {loteSel && subTab === "fornecimento" && dietaInfo && (
          <>
            <div style={{ maxWidth: "12rem", marginBottom: "0.8rem" }}>
              <Campo label="Data do fornecimento">
                <input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} />
              </Campo>
            </div>

            {porTrato && (
              <div style={{ marginBottom: "0.8rem" }}>
                <p style={{ ...nota, marginLeft: 0, marginBottom: "0.3rem" }}>De qual trato é este fornecimento? (a fazenda lança o consumo por trato)</p>
                <div className="flex flex-wrap gap-2">
                  {Array.from({ length: dietaInfo.num_tratos }, (_, i) => String(i + 1)).map((t) => (
                    <button key={t} type="button" className={trato === t ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.8rem" }} onClick={() => setTrato(t)}>
                      Trato {t} ({fmt(dietaInfo.tratos_pct[Number(t) - 1] ?? 0)}%)
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-wrap gap-2 mb-3">
              <button type="button" className={origem === "animais" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setOrigem("animais")}>
                <Users size={14} /> Por nº de animais
              </button>
              <button type="button" className={origem === "kg" ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.8rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setOrigem("kg")}>
                <Scale size={14} /> Quantidade direta
              </button>
            </div>

            {origem === "animais" ? (
              <>
                <div style={{ maxWidth: "12rem", marginBottom: "0.8rem" }}>
                  <Campo label="Número de animais">
                    <input type="number" inputMode="numeric" min={1} style={inputStyle} value={numAnimais} onChange={(e) => setNumAnimais(e.target.value)} />
                  </Campo>
                </div>
                <p style={nota}>Cada alimento é a quantidade por cabeça da dieta × o nº de animais informado.</p>

                <div className="overflow-x-auto mt-2">
                  <table className="fazenda-table">
                    <thead><tr><th>Alimento</th><th style={{ textAlign: "right" }}>Calculado</th><th></th></tr></thead>
                    <tbody>
                      {itensDieta.map((it) => {
                        const calc = Number(numAnimais) > 0 && it.por_cabeca != null ? Number(numAnimais) * it.por_cabeca : null;
                        return (
                          <tr key={it.alimento}>
                            <td style={{ fontSize: "0.85rem" }}>{it.alimento}</td>
                            <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                              {calc != null ? <strong>{fmt(calc)} {it.unidade}</strong> : <span style={{ color: "var(--text-muted)" }}>—</span>}
                            </td>
                            <td></td>
                          </tr>
                        );
                      })}
                      {!itensDieta.length && <tr><td colSpan={3} style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Dieta sem itens programados.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <>
                <div style={{ maxWidth: "14rem", marginBottom: "0.6rem" }}>
                  <Campo label="Kg totais ofertados no vagão">
                    <input type="number" inputMode="decimal" min={0} style={inputStyle} value={kgVagao} onChange={(e) => setKgVagao(e.target.value)} />
                  </Campo>
                </div>
                <p style={nota}>
                  A quantidade de cada alimento é calculada automaticamente pela % dele na dieta cadastrada do lote — não é preciso
                  digitar alimento por alimento.
                </p>

                {/* Tabela gerencial e automática (item novo, 23/09/2026): atualiza
                    ao vivo a partir do kg do vagão, sem nenhum lançamento —
                    é só a conta da dieta aplicada ao total informado. */}
                <div className="overflow-x-auto mt-2">
                  <table className="fazenda-table">
                    <thead>
                      <tr>
                        <th>Alimento</th>
                        <th style={{ textAlign: "right" }}>Total dieta (kg)</th>
                        <th style={{ textAlign: "right" }}>Total dieta (%)</th>
                        <th style={{ textAlign: "right" }}>Fornecido (kg)</th>
                        <th style={{ textAlign: "right" }}>Fornecido (%)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {itensComPercentual.map((it) => {
                        const fornecidoKg = kgVagaoNum > 0 ? kgVagaoNum * (it.percentual_dieta! / 100) : 0;
                        return (
                          <tr key={it.alimento}>
                            <td style={{ fontSize: "0.85rem" }}>{it.alimento}</td>
                            <td style={{ textAlign: "right" }}>{it.kg_total != null ? fmt(it.kg_total) : "—"}</td>
                            <td style={{ textAlign: "right" }}>{fmt(it.percentual_dieta!)}%</td>
                            <td style={{ textAlign: "right" }}><strong>{fmt(fornecidoKg)}</strong></td>
                            <td style={{ textAlign: "right" }}>{fmt(it.percentual_dieta!)}%</td>
                          </tr>
                        );
                      })}
                      {!itensComPercentual.length && (
                        <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nenhum alimento desta dieta converte para kg — lance manualmente abaixo.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {/* Itens sem conversão para kg (litro, dose, unidade...) — não
                    dá pra saber a fração do vagão que representam, então
                    continuam com input manual, como já era antes. */}
                {itensSemConversao.length > 0 && (
                  <div className="mt-3">
                    <p style={{ ...nota, marginLeft: 0, display: "flex", alignItems: "flex-start", gap: "0.3rem" }}>
                      <Info size={12} style={{ flexShrink: 0, marginTop: "0.15rem" }} />
                      Itens sem conversão para kg — lance a quantidade de cada um manualmente:
                    </p>
                    <table className="fazenda-table">
                      <thead><tr><th>Alimento</th><th style={{ textAlign: "right" }}>Fornecido</th><th></th></tr></thead>
                      <tbody>
                        {itensSemConversao.map((it) => (
                          <tr key={it.alimento}>
                            <td style={{ fontSize: "0.85rem" }}>{it.alimento}</td>
                            <td style={{ textAlign: "right" }}>
                              <input type="number" inputMode="decimal" style={{ ...inputStyle, width: "7rem", textAlign: "right", display: "inline-block" }}
                                value={quantidadesKg[it.alimento] ?? ""} placeholder="0"
                                onChange={(e) => setQuantidadesKg((p) => ({ ...p, [it.alimento]: e.target.value }))} />
                            </td>
                            <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{it.unidade}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}

            {/* Fora da dieta — só oferecido quando o lote permite (item D8: a
                tela explica a política antes de o usuário tentar e levar 409). */}
            <div className="mt-3">
              {loteObj?.permitir_fora_da_dieta ? (
                <>
                  {extras.map((ex, idx) => (
                    <div key={idx} className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-2" style={{ alignItems: "end" }}>
                      <Campo label="Alimento fora da dieta">
                        <select style={inputStyle} value={ex.alimento} onChange={(e) => atualizarExtra(idx, { alimento: e.target.value })}>
                          <option value="">Selecione...</option>
                          {alimentosCadastro.map((a) => <option key={a.id} value={a.nome}>{a.nome}</option>)}
                        </select>
                      </Campo>
                      <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={ex.quantidade} onChange={(e) => atualizarExtra(idx, { quantidade: e.target.value })} /></Campo>
                      <Campo label="Unidade">
                        <select style={inputStyle} value={ex.unidade} onChange={(e) => atualizarExtra(idx, { unidade: e.target.value })}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select>
                      </Campo>
                      <button onClick={() => removerExtra(idx)} title="Remover" aria-label="Remover alimento" className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem" }}><Trash2 size={13} /></button>
                    </div>
                  ))}
                  <button onClick={acrescentarExtra} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><PlusCircle size={13} /> Adicionar alimento fora da dieta</button>
                </>
              ) : (
                <p style={nota}>Este lote não aceita alimentos fora da dieta cadastrada — habilite a flag no cadastro do lote para liberar.</p>
              )}
            </div>

            {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.8rem" }}>{erro}</p>}
            {avisos.length > 0 && (
              <div style={{ marginTop: "0.8rem", padding: "0.6rem 0.8rem", borderRadius: "var(--r-sm)", border: "1px solid var(--amber)", background: "color-mix(in srgb, var(--amber) 12%, transparent)" }}>
                {avisos.map((a, i) => (
                  <p key={i} style={{ fontSize: "0.78rem", color: "var(--text)", display: "flex", alignItems: "flex-start", gap: "0.4rem", margin: i ? "0.3rem 0 0" : 0 }}>
                    <TriangleAlert size={13} style={{ flexShrink: 0, marginTop: "0.15rem", color: "var(--amber)" }} /> {a}
                  </p>
                ))}
              </div>
            )}
            {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

            <button className="btn-primary mt-3" style={{ fontSize: "0.85rem" }} disabled={enviando} onClick={enviarConsumo}>
              {enviando ? "Lançando..." : "Lançar consumo"}
            </button>

            {/* Item D4: acumulado do dia — lançamentos do mesmo dia somam por
                alimento (B2), então isto é sempre o total já registrado hoje,
                não apenas o que está sendo digitado agora. */}
            {consumoHoje && consumoHoje.itens.length > 0 && (
              <div className="mt-4">
                <p style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--dourado-light)", marginBottom: "0.4rem" }}>
                  Já lançado em {fmtDataBR(data)} ({fmt(consumoHoje.kg_fornecido_total)} kg no total)
                </p>
                {(consumoHoje.por_trato?.length ?? 0) > 0 && (
                  <p style={{ ...nota, marginLeft: 0, marginBottom: "0.4rem" }}>
                    {consumoHoje.por_trato!.map((t) => `Trato ${t.trato}: ${fmt(t.kg)} kg`).join(" · ")}
                    {(consumoHoje.kg_sem_trato ?? 0) > 0 && ` · sem trato: ${fmt(consumoHoje.kg_sem_trato!)} kg`}
                  </p>
                )}
                <div className="overflow-x-auto">
                  <table className="fazenda-table" style={{ margin: 0 }}>
                    <thead><tr><th>Alimento</th><th style={{ textAlign: "right" }}>Quantidade</th></tr></thead>
                    <tbody>
                      {consumoHoje.itens.map((it) => (
                        <tr key={it.alimento}><td style={{ fontSize: "0.82rem" }}>{it.alimento}</td><td style={{ textAlign: "right" }}>{fmt(it.quantidade)} {it.unidade}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}

        {loteSel && subTab === "sobra" && (
          <>
            <div style={{ maxWidth: "12rem", marginBottom: "0.4rem" }}>
              <Campo label={posicaoDieta == null ? "Data da sobra (dia do fornecimento)" : "Data da leitura da sobra"}>
                <input type="date" style={inputStyle} value={dataSobra} onChange={(e) => { setDataSobra(e.target.value); setKgSobra(""); setErroSobra(null); setSucessoSobra(null); setConfirmandoSobra(false); }} />
              </Campo>
            </div>

            {/* Nota fixa (item novo, 23/09/2026): fundo escuro/preto e texto
                em "ATENÇÃO" dourado escuro SEMPRE, nos três modos de tema
                (claro/misto/escuro) — pedido explícito do produtor, por isso
                cores fixas em vez dos tokens de tema (--amber/--surface)
                usados no resto da tela. Não "corrija" para var(...) achando
                que é inconsistência. O texto muda conforme a dieta tenha (ou
                não) a posição da leitura cadastrada (21/10/2026). */}
            <div style={{ marginTop: "0.2rem", marginBottom: "0.9rem", padding: "0.7rem 0.9rem", borderRadius: "var(--r-sm)", background: "#161616", border: "1px solid #3a2f14" }}>
              <p style={{ margin: 0, fontSize: "0.72rem", fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", color: "#B8860B" }}>
                Atenção
              </p>
              {posicaoDieta == null ? (
                <p style={{ margin: "0.35rem 0 0", fontSize: "0.8rem", color: "#f2f2f2", lineHeight: 1.5 }}>
                  O lançamento da sobra de cocho se refere, em regra, à data do dia anterior à do fornecimento.<br />
                  Hoje: {fmtDataBR(hojeIso())}<br />
                  Sobra de cocho - ontem: {fmtDataBR(ontemIso())}
                </p>
              ) : (
                <p style={{ margin: "0.35rem 0 0", fontSize: "0.8rem", color: "#f2f2f2", lineHeight: 1.5 }}>
                  Informe o dia em que a sobra foi LIDA. A dieta deste lote diz que a leitura é feita entre o Trato {posicaoDieta} e o
                  Trato {posicaoDieta >= nTratos ? 1 : posicaoDieta + 1} — o período (ciclo de 24h) é montado sozinho e você confirma antes de gravar.
                </p>
              )}
            </div>

            <div style={{ maxWidth: "12rem", marginBottom: "0.6rem" }}>
              <Campo label="Sobra (kg totais)">
                <input type="number" inputMode="decimal" min={0} style={inputStyle} value={kgSobra} onChange={(e) => setKgSobra(e.target.value)} />
              </Campo>
            </div>
            <p style={nota}>Uma sobra por ciclo de 24h — lançar de novo para o mesmo período substitui o valor anterior, não soma.</p>

            {janela && (
              <p style={{ ...nota, marginLeft: 0, marginTop: "0.4rem" }}>
                Período: {janela.descricao.replace(/^A sobra se refere /, "").replace(/\?$/, "")} · fornecido nesse período: {fmt(janela.kg_fornecido_janela)} kg
              </p>
            )}

            {/* Item D6: percentual calculado + status da faixa, antes mesmo
                de o usuário confirmar — é a mesma conta que gera o alerta na
                central e na agenda (Frente C), só que aqui é prévia. Sempre
                em relação ao fornecido NO PERÍODO (janela de tratos) da sobra. */}
            {previewPct != null && (
              <p style={{ fontSize: "0.85rem", marginTop: "0.5rem", display: "flex", alignItems: "center", gap: "0.4rem", color: corFaixa(statusFaixa(previewPct)) }}>
                {statusFaixa(previewPct) === "dentro" ? <CheckCircle2 size={15} /> : <TriangleAlert size={15} />}
                <strong>{fmt(previewPct)}%</strong> do fornecido no período
                {statusFaixa(previewPct) === "dentro" && " — dentro da faixa aceitável"}
                {statusFaixa(previewPct) === "abaixo" && ` — abaixo do mínimo (${paramAlim.min}%)`}
                {statusFaixa(previewPct) === "acima" && ` — acima do máximo (${paramAlim.max}%)`}
              </p>
            )}
            {previewPct == null && kgSobra !== "" && janela && kgFornecidoJanela === 0 && (
              <p style={{ ...nota, marginLeft: 0 }}>Sem consumo lançado nesse período ainda — não dá para calcular o percentual.</p>
            )}
            <p style={nota}>Alvo: {paramAlim.alvo}% · aceitável entre {paramAlim.min}% e {paramAlim.max}%.</p>

            {janela?.kg_sobra_existente != null && (
              <p style={{ fontSize: "0.8rem", marginTop: "0.4rem", color: "var(--text-muted)" }}>
                Já registrado para esse período: <strong style={{ color: "var(--text)" }}>{fmt(janela.kg_sobra_existente)} kg</strong>
                {kgFornecidoJanela > 0 && ` (${fmt((janela.kg_sobra_existente / kgFornecidoJanela) * 100)}%)`}
              </p>
            )}

            {itensSemConversao.length > 0 && (
              <p style={{ ...nota, marginLeft: 0, marginTop: "0.5rem", display: "flex", alignItems: "flex-start", gap: "0.3rem" }}>
                <Info size={12} style={{ flexShrink: 0, marginTop: "0.15rem" }} />
                Fora do rateio da sobra por alimento (unidade sem conversão para kg): {itensSemConversao.map((i) => i.alimento).join(", ")}.
              </p>
            )}

            {erroSobra && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erroSobra}</p>}
            {sucessoSobra && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucessoSobra}</p>}

            {!confirmandoSobra ? (
              <button className="btn-primary mt-3" style={{ fontSize: "0.85rem" }} disabled={enviandoSobra} onClick={pedirConfirmacaoSobra}>
                Registrar sobra
              </button>
            ) : (
              <div className="mt-3" style={{ padding: "0.8rem 0.9rem", borderRadius: "var(--r-sm)", border: "1px solid var(--dourado)", background: "var(--surface-2)", maxWidth: "36rem" }}>
                <p style={{ margin: 0, fontSize: "0.9rem", fontWeight: 700 }}>{janela?.descricao}</p>
                <p style={{ ...nota, marginLeft: 0, marginTop: "0.3rem" }}>
                  {kgSobra} kg de sobra{previewPct != null ? ` = ${fmt(previewPct)}% de ${fmt(kgFornecidoJanela)} kg fornecidos no período` : ""}
                  {janela?.kg_sobra_existente != null ? ` · substitui os ${fmt(janela.kg_sobra_existente)} kg já lançados para esse período` : ""}.
                </p>

                {outroPeriodo && (
                  <div className="mt-2">
                    <div style={{ maxWidth: "12rem", marginBottom: "0.5rem" }}>
                      <Campo label={escolhaSobra === "civil" ? "Dia do fornecimento" : "Data da leitura"}>
                        <input type="date" style={inputStyle} value={dataSobra} onChange={(e) => setDataSobra(e.target.value)} />
                      </Campo>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {opcoesPosicaoLeitura(nTratos).map((o) => (
                        <button key={o.valor} type="button" className={posicaoSobra === o.valor ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.76rem" }}
                          onClick={() => setEscolhaSobra(o.valor)}>
                          Lida entre {o.rotulo}
                        </button>
                      ))}
                      <button type="button" className={posicaoSobra == null ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.76rem" }}
                        onClick={() => setEscolhaSobra("civil")}>
                        Dia inteiro do fornecimento
                      </button>
                    </div>
                  </div>
                )}

                <div className="flex flex-wrap gap-2 mt-3">
                  <button className="btn-primary" style={{ fontSize: "0.82rem" }} disabled={enviandoSobra || !janela} onClick={enviarSobra}>
                    {enviandoSobra ? "Registrando..." : "Confirmar"}
                  </button>
                  {!outroPeriodo && (
                    <button className="btn-secondary" style={{ fontSize: "0.82rem" }} disabled={enviandoSobra} onClick={() => setOutroPeriodo(true)}>
                      Selecionar outro período
                    </button>
                  )}
                  <button className="btn-ghost" style={{ fontSize: "0.82rem" }} disabled={enviandoSobra} onClick={cancelarSobra}>Cancelar</button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
