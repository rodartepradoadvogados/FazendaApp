"use client";
// Marcar (ou editar) o dia de "Vacina" / "Exame" — §4 do modelo.
//   - várias vacinas/exames no mesmo dia; data/hora; veterinário da lista de
//     Cadastros › Pessoas (função veterinário) ou texto livre (CRMV pedido, não
//     exigido); produto e dose por vacina;
//   - animais: quem estará pronto na data prevista (simulação do back) ou os que
//     vieram selecionados de Sanidade › Animais na janela; "Ajustar animais"
//     abre o seletor;
//   - data diferente da prevista: o back simula e lista os riscos; a pessoa
//     decide manter / ajustar / dividir (decisão no log);
//   - quem está fora da regra volta como 409 `consentimento_necessario`: abre o
//     pop-up de consentimento e reenvia.
// Editar usa PUT /sanitario/dias/{id} com `versao_lock` (dois aparelhos ao
// mesmo tempo → 409 `versao_desatualizada`).
import { useEffect, useMemo, useRef, useState } from "react";
import { Search, Users } from "lucide-react";
import { Modal } from "@/components/Modal";
import {
  codigoDoErro, dataPrevista as buscarDataPrevista, detalheDoErro, editarDia, listarCaixas, listarVeterinarios, marcarDia,
  mensagemDoErro, obterCaixa, simularDia,
} from "@/lib/apiSanitario";
import {
  DOSE_UNIDADES, ROTULO_UNIDADE, diaSemana, fmtData, hojeISO, intOuNulo, numOuNulo, tipoDoDia,
  type CaixaResumo, type ConsentimentoIn, type DecisaoRiscos, type Dia, type DiaItemIn, type ItemForaRegra, type ProdutoIn,
  type Simulacao, type Veterinarios,
} from "@/lib/sanitarioTipos";
import { Faixa, carregarEstoqueSan, type ItemEstoqueSan } from "../comum";
import { SeletorAnimais, carregarAnimaisSan, type Elegibilidade } from "../SeletorAnimais";
import { ModalConsentimento, type ItemConsentimento } from "../ModalConsentimento";
import { PainelRiscos, idsEmRisco, temRiscos, textoDecisao, type EscolhaRiscos } from "../PainelRiscos";

type Sel = Map<number, { caixas: Set<number>; origem: "janela" | "manual"; numero: string }>;

/** Elegibilidade por animal a partir de uma simulação do back. */
export function elegibilidadeDaSimulacao(sim: Simulacao, ids: number[]): Map<number, Elegibilidade> {
  const ok = new Set(sim.animais.map((a) => a.animal_id));
  const texto = new Map<number, string>();
  for (const r of sim.riscos) for (const id of r.animal_ids) if (!texto.has(id)) texto.set(id, r.texto);
  const m = new Map<number, Elegibilidade>();
  for (const id of ids) m.set(id, ok.has(id) ? { ok: true, texto: null } : { ok: false, texto: texto.get(id) || "já recebeu neste ciclo ou fora do público" });
  return m;
}

export function ModalMarcarDia({ dia, caixasIniciais = [], paresIniciais, onFechar, onSalvo }: {
  /** Editar este dia (precisa vir com `itens`). */
  dia?: Dia | null;
  caixasIniciais?: number[];
  /** Animais já escolhidos (ex.: vindos de Sanidade › Animais na janela). */
  paresIniciais?: { caixa_id: number; animal_id: number; numero?: string | null }[];
  onFechar: () => void;
  onSalvo: (dias: Dia[], mensagem: string) => void;
}) {
  const editando = !!dia;
  const [caixas, setCaixas] = useState<CaixaResumo[] | null>(null);
  const [vets, setVets] = useState<Veterinarios | null>(null);
  const [estoque, setEstoque] = useState<ItemEstoqueSan[]>([]);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [cx, setCx] = useState<Set<number>>(() => new Set(dia ? dia.caixas.map((c) => c.caixa_id) : [...caixasIniciais, ...(paresIniciais || []).map((p) => p.caixa_id)]));
  const [prev, setPrev] = useState<string | null>(dia ? (dia.data_prevista || dia.data) : null);
  const [data, setData] = useState<string>(dia ? dia.data : "");
  const [hora, setHora] = useState(dia?.hora || "07:00");
  const [vetSel, setVetSel] = useState<string>(dia?.veterinario?.pessoa_id ? String(dia.veterinario.pessoa_id) : dia?.veterinario?.texto ? "__txt" : "");
  const [vetTxt, setVetTxt] = useState(dia?.veterinario?.pessoa_id ? "" : dia?.veterinario?.texto || "");
  const [vetCrmv, setVetCrmv] = useState(dia?.veterinario?.crmv || "");
  const [produtos, setProdutos] = useState<Record<number, ProdutoIn>>(() => Object.fromEntries((dia?.caixas || []).map((c) => [c.caixa_id, { ...c.produto }])));
  const [observacao, setObservacao] = useState(dia?.observacao || "");
  const [sel, setSel] = useState<Sel>(() => {
    const m: Sel = new Map();
    for (const it of dia?.itens || []) {
      if (it.estado === "removido") continue;
      const e = m.get(it.animal_id) || { caixas: new Set<number>(), origem: it.origem === "janela" ? "janela" as const : "manual" as const, numero: it.numero || String(it.animal_id) };
      e.caixas.add(it.caixa_id); m.set(it.animal_id, e);
    }
    for (const p of paresIniciais || []) {
      const e = m.get(p.animal_id) || { caixas: new Set<number>(), origem: "janela" as const, numero: p.numero || String(p.animal_id) };
      e.caixas.add(p.caixa_id); m.set(p.animal_id, e);
    }
    return m;
  });
  const [consentimentos, setConsentimentos] = useState<ConsentimentoIn[]>([]);
  const [sim, setSim] = useState<Simulacao | null>(null);
  const [simulando, setSimulando] = useState(false);
  const [escolha, setEscolha] = useState<EscolhaRiscos>("manter");
  const [entrantes, setEntrantes] = useState(false);
  const [seletor, setSeletor] = useState(false);
  const [consent, setConsent] = useState<{ itens: ItemConsentimento[]; semAtestado: string } | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [selecaoCarregando, setSelecaoCarregando] = useState(false);
  const [reenvio, setReenvio] = useState<ConsentimentoIn[] | null>(null);
  const [numeros, setNumeros] = useState<Map<number, string>>(new Map());
  const preencheuSel = useRef(editando || !!paresIniciais?.length);

  // Brinco de cada animal (os pares vindos de Sanidade trazem só o id).
  useEffect(() => {
    let vivo = true;
    carregarAnimaisSan().then((l) => { if (vivo) setNumeros(new Map(l.map((a) => [a.id, a.numero]))); }).catch(() => undefined);
    return () => { vivo = false; };
  }, []);

  useEffect(() => {
    let vivo = true;
    Promise.all([listarCaixas("ativa"), listarVeterinarios().catch(() => ({ pessoas: [], aceita_texto_livre: true })), carregarEstoqueSan().catch(() => [])])
      .then(([c, v, e]) => { if (vivo) { setCaixas(c); setVets(v); setEstoque(e); } })
      .catch((e) => { if (vivo) setErroCarga(mensagemDoErro(e, "Não foi possível abrir.")); });
    return () => { vivo = false; };
  }, []);

  const cxIds = useMemo(() => [...cx].sort((a, b) => a - b), [cx]);
  const chaveCx = cxIds.join(",");
  const nomeCx = useMemo(() => new Map((caixas || []).map((c) => [c.id, c.nome_curto || c.nome])), [caixas]);
  const tipoCx = useMemo(() => new Map((caixas || []).map((c) => [c.id, c.tipo])), [caixas]);

  // Produto padrão de cada vacina nova escolhida (vem da definição da caixa).
  useEffect(() => {
    const faltam = cxIds.filter((id) => !(id in produtos) && tipoCx.get(id) !== "exame");
    if (!faltam.length) return;
    let vivo = true;
    Promise.allSettled(faltam.map((id) => obterCaixa(id))).then((rs) => {
      if (!vivo) return;
      setProdutos((p) => {
        const n = { ...p };
        rs.forEach((r) => {
          if (r.status !== "fulfilled") return;
          const d = r.value.definicao;
          n[r.value.id] = { modo: d.produto_modo, estoque_id: d.estoque_id, texto: d.produto_texto, dose_valor: d.dose_valor, dose_unidade: d.dose_unidade, dose_x_kg: d.dose_x_kg };
        });
        return n;
      });
    });
    return () => { vivo = false; };
  }, [chaveCx, tipoCx]); // eslint-disable-line react-hooks/exhaustive-deps

  // Data prevista (criar): muda quando as vacinas mudam.
  useEffect(() => {
    if (editando || !cxIds.length) return;
    let vivo = true;
    buscarDataPrevista(cxIds).then((r) => {
      if (!vivo) return;
      setPrev(r.data_prevista);
      setData((d) => d || r.data_prevista);
    }).catch((e) => { if (vivo) setErro(mensagemDoErro(e)); });
    return () => { vivo = false; };
  }, [chaveCx]); // eslint-disable-line react-hooks/exhaustive-deps

  // Seleção inicial (criar, sem animais vindos de fora): quem estará pronto na data prevista.
  useEffect(() => {
    if (preencheuSel.current || !prev || !cxIds.length) return;
    let vivo = true;
    setTimeout(() => { if (vivo) setSelecaoCarregando(true); }, 0);
    simularDia(cxIds, prev, prev, null).then((s) => {
      if (!vivo) return;
      const m: Sel = new Map();
      for (const a of s.animais) m.set(a.animal_id, { caixas: new Set(a.caixa_ids), origem: "janela", numero: a.numero });
      for (const r of s.riscos) r.animal_ids.forEach((id, i) => {
        const e = m.get(id) || { caixas: new Set<number>(), origem: "janela" as const, numero: r.numeros[i] || String(id) };
        r.caixa_ids.forEach((c) => e.caixas.add(c)); m.set(id, e);
      });
      setSel(m);
    }).catch((e) => { if (vivo) setErro(mensagemDoErro(e, "Não foi possível ver quem estará pronto.")); })
      .finally(() => { if (vivo) setSelecaoCarregando(false); });
    return () => { vivo = false; };
  }, [prev, chaveCx]); // eslint-disable-line react-hooks/exhaustive-deps

  // Simulação da data escolhida, quando difere da prevista.
  const idsJanela = useMemo(() => [...sel.entries()].filter(([, v]) => v.origem === "janela").map(([k]) => k), [sel]);
  const chaveSim = `${chaveCx}|${data}|${prev}|${idsJanela.join(",")}`;
  useEffect(() => {
    if (!prev || !data || !cxIds.length || data === prev) { setTimeout(() => setSim(null), 0); return; }
    let vivo = true;
    setTimeout(() => { if (vivo) setSimulando(true); }, 0);
    simularDia(cxIds, data, prev, idsJanela).then((s) => { if (vivo) setSim(s); })
      .catch((e) => { if (vivo) setErro(mensagemDoErro(e, "Não foi possível simular a nova data.")); })
      .finally(() => { if (vivo) setSimulando(false); });
    return () => { vivo = false; };
  }, [chaveSim]); // eslint-disable-line react-hooks/exhaustive-deps

  // Reenvio depois do consentimento: roda na renderização em que `sel` já está atualizado.
  useEffect(() => {
    if (!reenvio) return;
    const t = setTimeout(() => { setReenvio(null); salvar(reenvio); }, 0);
    return () => clearTimeout(t);
  }, [reenvio]); // eslint-disable-line react-hooks/exhaustive-deps

  function alternarCaixa(id: number, on: boolean) {
    setCx((p) => { const n = new Set(p); if (on) n.add(id); else n.delete(id); return n; });
    if (!on) setSel((p) => { const n: Sel = new Map(); p.forEach((v, k) => { const c = new Set(v.caixas); c.delete(id); if (c.size) n.set(k, { ...v, caixas: c }); }); return n; });
    else if (!editando) preencheuSel.current = false;
  }

  const animaisSel = [...sel.entries()].filter(([, v]) => [...v.caixas].some((c) => cx.has(c)));
  const manuais = animaisSel.filter(([, v]) => v.origem === "manual").length;
  const tipo = tipoDoDia(cxIds.map((id) => ({ tipo: tipoCx.get(id) })));

  function itensParaEnvio(filtro: (id: number) => boolean, extra: Simulacao["entram"] = []): DiaItemIn[] {
    const out: DiaItemIn[] = [];
    for (const [aid, v] of sel) {
      if (!filtro(aid)) continue;
      const cids = [...v.caixas].filter((c) => cx.has(c));
      if (cids.length) out.push({ animal_id: aid, caixa_ids: cids });
    }
    for (const e of extra) if (!sel.has(e.animal_id) && filtro(e.animal_id)) out.push({ animal_id: e.animal_id, caixa_ids: e.caixa_ids.filter((c) => cx.has(c)) });
    return out.filter((i) => (i.caixa_ids || []).length);
  }

  const veterinario = () => vetSel === "__txt" ? { texto: vetTxt || null, crmv: vetCrmv || null }
    : vetSel ? { pessoa_id: Number(vetSel), crmv: vetCrmv || null } : null;

  async function salvar(consExtra: ConsentimentoIn[] = []) {
    setErro(null);
    if (!cx.size) { setErro("Escolha ao menos uma vacina ou exame."); return; }
    if (!data) { setErro("Escolha a data."); return; }
    const cons = [...consentimentos, ...consExtra];
    const decisao: DecisaoRiscos | null = sim && temRiscos(sim) ? { decisao: escolha, texto: textoDecisao(sim, escolha, entrantes) } : null;
    const prods: Record<number, ProdutoIn> = {};
    for (const id of cxIds) if (tipoCx.get(id) !== "exame" && produtos[id]) prods[id] = produtos[id];
    setSalvando(true);
    try {
      if (editando && dia) {
        const r = await editarDia(dia.id, {
          versao_lock: dia.versao_lock, data, hora, data_prevista: prev, veterinario: veterinario(), produtos: prods,
          observacao, decisao_riscos: decisao,
        });
        onSalvo([r], `${r.nome} atualizado.`);
        return;
      }
      const risco = idsEmRisco(sim);
      const entram = entrantes && sim ? sim.entram : [];
      const base = { caixa_ids: cxIds, hora, veterinario: veterinario(), produtos: prods, consentimentos: cons, observacao };
      if (decisao && escolha === "dividir" && risco.size) {
        const d1 = await marcarDia({ ...base, data: prev || data, data_prevista: prev, itens: itensParaEnvio((id) => risco.has(id)) });
        const d2 = await marcarDia({ ...base, data, data_prevista: prev, itens: itensParaEnvio((id) => !risco.has(id), entram), decisao_riscos: decisao });
        onSalvo([d1, d2], `Dois dias marcados: ${fmtData(d1.data, true)} e ${fmtData(d2.data, true)}.`);
        return;
      }
      const filtro = decisao && escolha === "ajustar" ? (id: number) => !risco.has(id) : () => true;
      const itens = itensParaEnvio(filtro, entram);
      if (!itens.length) { setErro("Nenhum animal escolhido. Use “Ajustar animais”."); return; }
      const r = await marcarDia({ ...base, data, data_prevista: prev, itens, decisao_riscos: decisao });
      onSalvo([r], `${r.nome} marcada. Já aparece na Agenda e no celular.`);
    } catch (e) {
      const cod = codigoDoErro(e);
      if (cod === "consentimento_necessario") {
        const det = detalheDoErro<{ itens: ItemForaRegra[]; pergunta_atestado_caixas: number[] }>(e);
        setConsentimentos(cons);
        setConsent({
          itens: (det?.itens || []).map((i) => ({ animal_id: i.animal_id, numero: i.numero, caixa_id: i.caixa_id, caixa: i.caixa, motivo: i.motivo })),
          semAtestado: (det?.pergunta_atestado_caixas || []).map((c) => nomeCx.get(c) || `#${c}`).join(", "),
        });
      } else if (cod === "decisao_riscos_necessaria") {
        const det = detalheDoErro<Simulacao & { mensagem: string }>(e);
        if (det) setSim({ data: det.data, data_prevista: det.data_prevista, riscos: det.riscos || [], entram: det.entram || [], animais: det.animais || [] });
        setErro(det?.mensagem || "Decida o que fazer com os riscos da data.");
      } else if (cod === "versao_desatualizada") {
        setErro("Alguém mudou este dia enquanto você editava. Feche e abra de novo para ver a versão atual.");
      } else {
        setErro(mensagemDoErro(e, "Não foi possível marcar."));
      }
    } finally {
      setSalvando(false);
    }
  }

  const titulo = editando && dia ? `Editar ${dia.nome}` : "Marcar Vacina ou Exame";
  return (
    <>
      <Modal title={titulo} onClose={onFechar} width="820px">
        <div className="san-modal-corpo">
          <p className="san-modal-sub">Aparece na Agenda e no celular. Na véspera, todos os usuários do app recebem o comunicado.</p>
          {erroCarga ? <Faixa tipo="alerta">{erroCarga}</Faixa> : !caixas ? <div className="skeleton" style={{ height: "12rem" }} role="status" aria-label="Carregando" /> : (<>
            <div className="san-campo">
              <span className="san-rot">Vacinas e exames deste dia</span>
              {editando ? (
                <p style={{ margin: 0, fontSize: "0.84rem" }}>{dia?.caixas.map((c) => c.nome_curto).join(" · ")} <span className="san-nota">(para mudar, marque outro dia)</span></p>
              ) : caixas.length ? (
                <div className="san-opcs">
                  {caixas.map((c) => (
                    <label key={c.id} className="san-opc">
                      <input type="checkbox" checked={cx.has(c.id)} onChange={(e) => alternarCaixa(c.id, e.target.checked)} />
                      <span>{c.nome_curto || c.nome}<small className="san-num">{c.na_caixa} na caixa</small></span>
                    </label>
                  ))}
                </div>
              ) : <Faixa tipo="atencao">Nenhuma vacina ou exame ativo. Ative em Cadastro.</Faixa>}
            </div>
            <div className="san-linha">
              <div className="san-campo medio">
                <label htmlFor="mData">Data</label>
                <input id="mData" className="san-input" type="date" value={data} min={editando ? undefined : hojeISO()} onChange={(e) => setData(e.target.value)} />
              </div>
              <div className="san-campo curto">
                <label htmlFor="mHora">Hora</label>
                <input id="mHora" className="san-input" type="time" value={hora} onChange={(e) => setHora(e.target.value)} />
              </div>
              <p className="san-nota" style={{ flex: "2 1 220px", margin: 0 }}>
                {prev ? <>Data prevista: <b>{diaSemana(prev)} {fmtData(prev, true)}</b>{data && data !== prev && <> · <button type="button" className="san-link" onClick={() => setData(prev)}>voltar para a prevista</button></>}</> : cx.size ? "Calculando a data prevista…" : ""}
              </p>
            </div>
            <div className="san-linha">
              <div className="san-campo" style={{ flex: "1 1 260px" }}>
                <label htmlFor="mVet">Veterinário</label>
                <select id="mVet" className="san-input" value={vetSel} onChange={(e) => setVetSel(e.target.value)}>
                  <option value="">Sem veterinário</option>
                  {(vets?.pessoas || []).map((p) => <option key={p.pessoa_id} value={p.pessoa_id}>{p.nome}{p.crmv ? ` · ${p.crmv}` : ""}</option>)}
                  <option value="__txt">Outro (escrever)</option>
                </select>
              </div>
              {vetSel === "__txt" && (<>
                <div className="san-campo"><label htmlFor="mVetTxt">Nome</label><input id="mVetTxt" className="san-input" value={vetTxt} onChange={(e) => setVetTxt(e.target.value)} /></div>
                <div className="san-campo medio"><label htmlFor="mVetCrmv">CRMV (opcional)</label><input id="mVetCrmv" className="san-input" value={vetCrmv} onChange={(e) => setVetCrmv(e.target.value)} /></div>
              </>)}
            </div>
            <p className="san-nota" style={{ margin: "-0.4rem 0 0" }}>A lista vem de Cadastros › Pessoas (função veterinário). CRMV é pedido, não exigido.</p>
            {cxIds.filter((id) => tipoCx.get(id) !== "exame").map((id) => {
              const p = produtos[id] || { modo: "vazio" };
              const valorSel = p.modo === "estoque" && p.estoque_id ? `e:${p.estoque_id}` : p.modo === "sem_estoque" ? "sem" : p.modo === "nao_se_aplica" ? "nada" : "vazio";
              return (
                <div key={id} className="san-linha">
                  <div className="san-campo" style={{ flex: "2 1 240px" }}>
                    <label htmlFor={`mP${id}`}>Produto · {nomeCx.get(id)}</label>
                    <select id={`mP${id}`} className="san-input" value={valorSel} onChange={(e) => {
                      const v = e.target.value;
                      const novo: ProdutoIn = v.startsWith("e:") ? { ...p, modo: "estoque", estoque_id: Number(v.slice(2)) }
                        : v === "sem" ? { ...p, modo: "sem_estoque", estoque_id: null } : v === "nada" ? { ...p, modo: "nao_se_aplica", estoque_id: null } : { ...p, modo: "vazio", estoque_id: null };
                      setProdutos((x) => ({ ...x, [id]: novo }));
                    }}>
                      <option value="vazio">Escolher no dia</option>
                      {estoque.map((e) => <option key={e.id} value={`e:${e.id}`}>{e.nome}{e.quantidade != null ? ` · saldo ${e.quantidade}` : ""}</option>)}
                      <option value="sem">Produto sem estoque</option>
                      <option value="nada">Sem produto</option>
                    </select>
                  </div>
                  {p.modo === "sem_estoque" && (
                    <div className="san-campo"><label htmlFor={`mPt${id}`}>Nome do produto</label>
                      <input id={`mPt${id}`} className="san-input" value={p.texto || ""} onChange={(e) => setProdutos((x) => ({ ...x, [id]: { ...p, texto: e.target.value } }))} /></div>
                  )}
                  <div className="san-campo curto"><label htmlFor={`mD${id}`}>Dose</label>
                    <input id={`mD${id}`} className="san-input" type="number" step="0.1" min={0} value={p.dose_valor ?? ""} onChange={(e) => setProdutos((x) => ({ ...x, [id]: { ...p, dose_valor: numOuNulo(e.target.value) } }))} /></div>
                  <div className="san-campo curto"><label htmlFor={`mU${id}`}>Unidade</label>
                    <select id={`mU${id}`} className="san-input" value={p.dose_unidade || ""} onChange={(e) => setProdutos((x) => ({ ...x, [id]: { ...p, dose_unidade: (e.target.value || null) as ProdutoIn["dose_unidade"] } }))}>
                      <option value="">—</option>{DOSE_UNIDADES.map((u) => <option key={u} value={u}>{ROTULO_UNIDADE[u]}</option>)}
                    </select></div>
                  {p.dose_unidade === "mL_por_x_kg" && (
                    <div className="san-campo curto"><label htmlFor={`mX${id}`}>X (kg)</label>
                      <input id={`mX${id}`} className="san-input" type="number" min={1} value={p.dose_x_kg ?? ""} onChange={(e) => setProdutos((x) => ({ ...x, [id]: { ...p, dose_x_kg: intOuNulo(e.target.value) } }))} /></div>
                  )}
                </div>
              );
            })}
            {!editando && (
              <Faixa>
                {selecaoCarregando ? "Vendo quem estará pronto na data prevista…" : (<>
                  <b className="san-num">{animaisSel.length}</b> {animaisSel.length === 1 ? "animal" : "animais distintos"}{manuais ? ` · ${manuais} incluídos à mão` : ""}
                  {animaisSel.length > 0 && <>: <span className="san-num">{animaisSel.slice(0, 24).map(([k, v]) => numeros.get(k) || v.numero).join(", ")}{animaisSel.length > 24 ? "…" : ""}</span></>}
                </>)}
                <div style={{ marginTop: "0.4rem" }}>
                  <button type="button" className="btn-ghost san-btn-sm" disabled={!cx.size || !data} onClick={() => setSeletor(true)}>
                    <Search size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />Ajustar animais
                  </button>
                </div>
              </Faixa>
            )}
            {editando && (
              <p className="san-nota" style={{ margin: 0 }}><Users size={12} aria-hidden="true" style={{ verticalAlign: "-1px" }} /> {dia?.contagens.animais} animais. Para incluir ou tirar animais, use o dia aberto (Adicionar animais).</p>
            )}
            <PainelRiscos sim={sim} carregando={simulando} escolha={escolha} onEscolha={setEscolha} incluirEntrantes={entrantes}
              onIncluirEntrantes={setEntrantes} onVoltarPrevista={prev ? () => setData(prev) : undefined} />
            <div className="san-campo">
              <label htmlFor="mObs">Observação (opcional)</label>
              <input id="mObs" className="san-input" value={observacao} onChange={(e) => setObservacao(e.target.value)} />
            </div>
            {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
          </>)}
        </div>
        <div className="san-modal-rodape">
          <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
          <button type="button" className="btn-primary-gold" disabled={salvando || !caixas || simulando} onClick={() => salvar()}>
            {salvando ? "Gravando…" : editando ? "Salvar alterações" : `Marcar ${tipo}`}
          </button>
        </div>
      </Modal>
      {seletor && (
        <SeletorAnimais titulo={`Animais deste dia`} rotuloOk="Usar"
          subtitulo={`Conferindo a regra de ${cxIds.map((c) => nomeCx.get(c)).join(", ")} em ${fmtData(data, true)}. Quem está fora pode entrar com o seu consentimento.`}
          jaSelecionados={animaisSel.map(([k]) => k)}
          checar={async (ids) => elegibilidadeDaSimulacao(await simularDia(cxIds, data, prev || data, ids), ids)}
          onFechar={() => setSeletor(false)}
          onConfirmar={async (ids, animais) => {
            setSeletor(false);
            const num = new Map(animais.map((a) => [a.id, a.numero]));
            let s: Simulacao | null = null;
            try { s = await simularDia(cxIds, data, prev || data, ids); } catch { s = null; }
            const okCx = new Map((s?.animais || []).map((a) => [a.animal_id, a.caixa_ids]));
            setSel((p) => {
              const n: Sel = new Map();
              for (const id of ids) {
                const antigo = p.get(id);
                if (antigo) { n.set(id, antigo); continue; }
                const ok = okCx.get(id);
                n.set(id, { caixas: new Set(ok && ok.length ? ok : cxIds), origem: ok && ok.length ? "janela" : "manual", numero: num.get(id) || String(id) });
              }
              return n;
            });
          }} />
      )}
      {consent && (
        <ModalConsentimento itens={consent.itens} perguntarAtestado={!!consent.semAtestado} nomesSemAtestado={consent.semAtestado}
          onVoltar={() => setConsent(null)}
          onConfirmar={(r) => {
            setConsent(null);
            setSel((p) => {
              const n: Sel = new Map(p);
              for (const x of r.recusados) {
                const e = n.get(x.animal_id); if (!e) continue;
                const c = new Set(e.caixas); if (x.caixa_id != null) c.delete(x.caixa_id); else c.clear();
                if (c.size) n.set(x.animal_id, { ...e, caixas: c }); else n.delete(x.animal_id);
              }
              for (const a of r.aceitos) { const e = n.get(a.animal_id); if (e) n.set(a.animal_id, { ...e, origem: "manual" }); }
              return n;
            });
            setReenvio(r.aceitos); // reenvia depois que a seleção (sem os recusados) estiver aplicada
          }} />
      )}
    </>
  );
}
