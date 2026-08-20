"use client";
import { useEffect, useMemo, useState } from "react";
import { Wheat, Users, Scale, PlusCircle, Trash2, CheckCircle2, TriangleAlert, Info, Loader2 } from "lucide-react";
import {
  fetchLotes, fetchAlimentos, fetchParametros,
  fetchDietaDoLote, fetchConsumoDoDia, lancarConsumo, lancarSobra,
  type ItemDietaDoLote, type ConsumoDoDia, type ConsumoItemIn,
} from "@/lib/api";
import { Campo, inputStyle, nota } from "@/components/lancamentos/comumForms";
import { UNIDADES } from "@/components/lancamentos/_shared";

/* ─────────────────────────────────────────────────────────────────────────
   Lançamentos > Alimentação — consumo diário e sobra de cocho (sessão 3,
   Frente D). Antes esta aba lançava a DIETA (CadastrarNovaDieta, que mudou
   de casa para Insumos e sanidade > Alimentação > "Lançar nova dieta" — ver
   app/alimentacao/page.tsx). Agora é aqui que o funcionário registra o que
   de fato foi fornecido no cocho, lote por lote, todo dia.

   "Lote" aqui é o INT de DietaLancamento.lote (mesma linguagem do endpoint),
   não o "01 - Nome" de Animal.grupo_primario usado nos outros Form* desta
   pasta — por isso a lista de lotes vem de fetchLotes() (cadastro de lotes,
   Lote.codigo/nome), não do array `lotes` calculado a partir dos animais.
   A ponte entre os dois mundos é `Number(lote.codigo)` ⇄ `f"{lote:02d}"`.
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
const hoje = () => new Date().toISOString().slice(0, 10);

export function ConsumoAlimento() {
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

  const [loteCodigo, setLoteCodigo] = useState("");
  const [data, setData] = useState(hoje);
  const [origem, setOrigem] = useState<"animais" | "kg">("animais");
  const [numAnimais, setNumAnimais] = useState("");
  const [quantidadesKg, setQuantidadesKg] = useState<Record<string, string>>({});
  const [extras, setExtras] = useState<ItemExtra[]>([]);
  const [kgSobra, setKgSobra] = useState("");

  // undefined = ainda carregando · null = lote sem dieta ativa (404 do backend)
  const [dietaInfo, setDietaInfo] = useState<{ itens: ItemDietaDoLote[]; base_quantidade: string } | null | undefined>(undefined);
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
    if (!loteSel) { setDietaInfo(undefined); setConsumoHoje(null); return; }
    let cancelado = false;
    setDietaInfo(undefined);
    setConsumoHoje(null);
    fetchDietaDoLote(loteSel).then((d) => { if (!cancelado) setDietaInfo(d); }).catch(() => { if (!cancelado) setDietaInfo(null); });
    fetchConsumoDoDia(loteSel, data).then((d) => { if (!cancelado) setConsumoHoje(d); }).catch(() => { if (!cancelado) setConsumoHoje(null); });
    return () => { cancelado = true; };
  }, [loteSel, data]);

  const itensDieta = dietaInfo?.itens ?? [];

  function selecionarLote(codigo: string) {
    setLoteCodigo(codigo);
    setNumAnimais(""); setQuantidadesKg({}); setExtras([]); setKgSobra("");
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
      base = itensDieta
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
    if (origem === "animais" && !(Number(numAnimais) > 0)) { setErro("Informe o número de animais."); return; }
    const itens = montarItens();
    if (!itens.length) { setErro("Informe ao menos um alimento com quantidade."); return; }
    setEnviando(true);
    try {
      const resp = await lancarConsumo({ lote: loteSel, data, num_animais: origem === "animais" ? Number(numAnimais) : null, origem, itens });
      setAvisos(resp.avisos || []);
      setSucesso("Consumo lançado.");
      setNumAnimais(""); setQuantidadesKg({}); setExtras([]);
      setConsumoHoje(await fetchConsumoDoDia(loteSel, data));
    } catch (e: any) {
      // Mensagem do backend já vem clara (409 de fora-da-dieta / sem-estoque
      // inclusos) — ver mensagemErroApi em lib/api.ts. É ela que explica a
      // recusa ao usuário (item D8 da spec).
      setErro(e.message || "Erro ao lançar consumo.");
    } finally {
      setEnviando(false);
    }
  }

  const kgFornecidoHoje = consumoHoje?.kg_fornecido_total ?? 0;
  const previewPct = kgSobra !== "" && kgFornecidoHoje > 0 ? (Number(kgSobra) / kgFornecidoHoje) * 100 : null;
  const statusFaixa = (pct: number | null): "abaixo" | "dentro" | "acima" | null => {
    if (pct == null) return null;
    if (pct < paramAlim.min) return "abaixo";
    if (pct > paramAlim.max) return "acima";
    return "dentro";
  };
  const corFaixa = (s: "abaixo" | "dentro" | "acima" | null) => (s === "dentro" ? "var(--green-light)" : s === null ? "var(--text-muted)" : "var(--amber)");

  async function enviarSobra() {
    setErroSobra(null); setSucessoSobra(null);
    if (!loteSel) { setErroSobra("Selecione um lote."); return; }
    const kg = Number(kgSobra);
    if (!(kg >= 0)) { setErroSobra("Informe a sobra em kg."); return; }
    setEnviandoSobra(true);
    try {
      await lancarSobra({ lote: loteSel, data, kg_sobra: kg });
      setSucessoSobra("Sobra registrada.");
      setKgSobra("");
      setConsumoHoje(await fetchConsumoDoDia(loteSel, data));
    } catch (e: any) {
      setErroSobra(e.message || "Erro ao lançar sobra.");
    } finally {
      setEnviandoSobra(false);
    }
  }

  const itensSemConversao = itensDieta.filter((it) => !it.converte_para_kg);

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

  return (
    <div className="space-y-4">
      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><Wheat size={15} /> Consumo do dia</div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <Campo label="Lote">
            <select style={inputStyle} value={loteCodigo} onChange={(e) => selecionarLote(e.target.value)}>
              <option value="">Selecione...</option>
              {(lotesCadastro ?? []).filter((l) => l.ativo !== false).map((l) => (
                <option key={l.id} value={l.codigo}>{l.codigo} - {l.nome}</option>
              ))}
            </select>
          </Campo>
          <Campo label="Data">
            <input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} />
          </Campo>
        </div>

        {loteObj && (
          <p style={{ ...nota, marginLeft: 0, marginBottom: "0.8rem" }}>
            {loteObj.permitir_fora_da_dieta ? "Aceita alimentos fora da dieta." : "Só aceita os alimentos da dieta cadastrada."}
            {" · "}
            {loteObj.permitir_sem_estoque ? "Aceita lançar mesmo sem saldo em estoque." : "Bloqueia lançamento sem saldo em estoque."}
          </p>
        )}

        {!loteSel && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Escolha um lote para ver a dieta ativa.</p>}

        {loteSel && dietaInfo === undefined && (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>
            <Loader2 size={14} className="animate-spin" /> Carregando dieta do lote...
          </p>
        )}

        {loteSel && dietaInfo === null && (
          <div className="alert-critico"><TriangleAlert size={16} /><span>Este lote não tem dieta ativa. Cadastre em Insumos e sanidade &gt; Alimentação &gt; Lançar nova dieta.</span></div>
        )}

        {loteSel && dietaInfo && (
          <>
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
              </>
            ) : (
              <p style={nota}>Informe a quantidade fornecida de cada alimento, na unidade programada na dieta.</p>
            )}

            <div className="overflow-x-auto mt-2">
              <table className="fazenda-table">
                <thead><tr><th>Alimento</th><th style={{ textAlign: "right" }}>{origem === "animais" ? "Calculado" : "Fornecido"}</th><th></th></tr></thead>
                <tbody>
                  {itensDieta.map((it) => {
                    const calc = origem === "animais" && Number(numAnimais) > 0 && it.por_cabeca != null
                      ? Number(numAnimais) * it.por_cabeca
                      : null;
                    return (
                      <tr key={it.alimento}>
                        <td style={{ fontSize: "0.85rem" }}>
                          {it.alimento}
                          {!it.converte_para_kg && (
                            <span title="Unidade sem conversão para kg — fica fora do rateio da sobra" style={{ marginLeft: "0.4rem", fontSize: "0.66rem", color: "var(--amber)", whiteSpace: "nowrap" }}>
                              fora do rateio de sobra
                            </span>
                          )}
                        </td>
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          {origem === "animais" ? (
                            calc != null ? <strong>{fmt(calc)} {it.unidade}</strong> : <span style={{ color: "var(--text-muted)" }}>—</span>
                          ) : (
                            <input type="number" inputMode="decimal" style={{ ...inputStyle, width: "7rem", textAlign: "right", display: "inline-block" }}
                              value={quantidadesKg[it.alimento] ?? ""} placeholder="0"
                              onChange={(e) => setQuantidadesKg((p) => ({ ...p, [it.alimento]: e.target.value }))} />
                          )}
                        </td>
                        <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{origem === "kg" ? it.unidade : ""}</td>
                      </tr>
                    );
                  })}
                  {!itensDieta.length && <tr><td colSpan={3} style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Dieta sem itens programados.</td></tr>}
                </tbody>
              </table>
            </div>

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
                  Já lançado hoje ({fmt(consumoHoje.kg_fornecido_total)} kg no total)
                </p>
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
      </div>

      {/* Item D5: card separado para a sobra — kg totais do lote no dia,
          rateio por alimento fica para o relatório (fora desta tela). */}
      <div className="card">
        <div className="card-header mb-3 flex items-center gap-2"><Scale size={15} /> Sobra de cocho</div>

        {!loteSel ? (
          <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Selecione um lote no card acima.</p>
        ) : (
          <>
            <div style={{ maxWidth: "12rem", marginBottom: "0.6rem" }}>
              <Campo label="Sobra (kg totais)">
                <input type="number" inputMode="decimal" min={0} style={inputStyle} value={kgSobra} onChange={(e) => setKgSobra(e.target.value)} />
              </Campo>
            </div>
            <p style={nota}>Lançar de novo hoje substitui o valor anterior — sobra é a medição do dia, não soma.</p>

            {/* Item D6: percentual calculado + status da faixa, antes mesmo
                de o usuário confirmar — é a mesma conta que gera o alerta na
                central e na agenda (Frente C), só que aqui é prévia. */}
            {previewPct != null && (
              <p style={{ fontSize: "0.85rem", marginTop: "0.5rem", display: "flex", alignItems: "center", gap: "0.4rem", color: corFaixa(statusFaixa(previewPct)) }}>
                {statusFaixa(previewPct) === "dentro" ? <CheckCircle2 size={15} /> : <TriangleAlert size={15} />}
                <strong>{fmt(previewPct)}%</strong> do fornecido
                {statusFaixa(previewPct) === "dentro" && " — dentro da faixa aceitável"}
                {statusFaixa(previewPct) === "abaixo" && ` — abaixo do mínimo (${paramAlim.min}%)`}
                {statusFaixa(previewPct) === "acima" && ` — acima do máximo (${paramAlim.max}%)`}
              </p>
            )}
            {previewPct == null && kgSobra !== "" && kgFornecidoHoje === 0 && (
              <p style={{ ...nota, marginLeft: 0 }}>Sem consumo lançado hoje ainda — não dá para calcular o percentual.</p>
            )}
            <p style={nota}>Alvo: {paramAlim.alvo}% · aceitável entre {paramAlim.min}% e {paramAlim.max}%.</p>

            {consumoHoje?.sobra_kg != null && (
              <p style={{ fontSize: "0.8rem", marginTop: "0.4rem", color: "var(--text-muted)" }}>
                Já registrado hoje: <strong style={{ color: "var(--text)" }}>{fmt(consumoHoje.sobra_kg)} kg</strong>
                {consumoHoje.sobra_pct != null && ` (${fmt(consumoHoje.sobra_pct)}%)`}
                {consumoHoje.dentro_da_faixa === true && <span style={{ color: "var(--green-light)" }}> — dentro da faixa</span>}
                {consumoHoje.dentro_da_faixa === false && <span style={{ color: "var(--amber)" }}> — fora da faixa (veja a central de alertas)</span>}
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

            <button className="btn-primary mt-3" style={{ fontSize: "0.85rem" }} disabled={enviandoSobra} onClick={enviarSobra}>
              {enviandoSobra ? "Registrando..." : "Registrar sobra"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
