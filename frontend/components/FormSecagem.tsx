"use client";
import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import {
  fetchSecagemInfo, criarSecagem, criarMovimentacao, fetchMedicamentos, formatDate, fetchTransferenciaLoteAutomatica,
} from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { Modal } from "@/components/Modal";
import { TabBar } from "@/components/ui";
import {
  Campo, Secao, inputStyle, nota,
  type EstoqueItem, type ItemSanidade, itemSanidadeVazio, unidadesCompativeis, EstoqueRestante, codigoGrupo, MOTIVOS_SECAGEM,
  animalEmLactacao,
} from "@/components/lancamentos/comumForms";

export function FormSecagem({ animais, estoque, produtos, numeroInicial }: { animais: AnimalRow[]; estoque: EstoqueItem[]; produtos: string[]; numeroInicial?: string }) {
  // Secagem só faz sentido para quem está em lactação — sem este filtro, a
  // lista de candidatas (e a tabela de lotes, com sua contagem e DEL médio)
  // misturava secas, novilhas e machos que só compartilham o grupo_primario.
  const animaisLactacao = useMemo(() => animais.filter(animalEmLactacao), [animais]);

  // Animal(is) ou lote(s) — dentro de lote, pode escolher mais de um; mesmo
  // padrão do Diagnóstico (TabBar + AnimalPickerModal/LotePicker).
  const [vinculo, setVinculo] = useState<"animal" | "lote">("animal");
  // Chegou de uma lista de trabalho (ex.: Listas > Previsão de secagem) já
  // com o animal escolhido — pré-seleciona, sem exigir passar pelo seletor.
  const [selecionados, setSelecionados] = useState<Set<string>>(() => (numeroInicial ? new Set([numeroInicial]) : new Set()));
  const toggle = (n: string) => setSelecionados((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const codigosLotes = useMemo(
    () => Array.from(new Set(animaisLactacao.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [animaisLactacao]
  );
  const animaisDoLoteSel = useMemo(() => {
    const cods = new Set(lotesSelecionados);
    return animaisLactacao.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [animaisLactacao, lotesSelecionados]);
  const [selLote, setSelLote] = useState<Set<string>>(new Set());
  const toggleLote = (n: string) => setSelLote((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelLote(new Set(animaisDoLoteSel.map((a) => a.numero)));
  }, [lotesSelecionados.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  const numerosAlvo = useMemo(() => (vinculo === "lote" ? selLote : selecionados), [vinculo, selLote, selecionados]);
  const matriz = numerosAlvo.size === 1 ? Array.from(numerosAlvo)[0] : "";

  const [info, setInfo] = useState<{ del_atual: number | null; data_prevista_secagem: string | null; deve_secar: boolean | null; motivo_exclusao: string | null; dias_gestacao: number | null } | null>(null);
  const [carregandoInfo, setCarregandoInfo] = useState(false);
  const [dataSecagem, setDataSecagem] = useState(() => new Date().toISOString().slice(0, 10));
  const [motivo, setMotivo] = useState("");
  const [ecc, setEcc] = useState("");
  const [observacao, setObservacao] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [itens, setItens] = useState<ItemSanidade[]>([itemSanidadeVazio()]);
  // "Dosagem" de cada produto de secagem pode ser a dose DE CADA vaca (padrão
  // — aplica o valor cheio a cada animal selecionado) ou o TOTAL usado na
  // aplicação inteira (divide pelo nº de vacas antes de lançar) — só faz
  // diferença de verdade quando mais de uma vaca está selecionada.
  const [modoDosagem, setModoDosagem] = useState<Record<number, "por_vaca" | "total">>({});
  const [aplicado, setAplicado] = useState(true);
  const [vacinas, setVacinas] = useState<string[]>([]);
  const [aplicarVacinaPreParto, setAplicarVacinaPreParto] = useState(false);
  const [vacinasPreParto, setVacinasPreParto] = useState<string[]>([]);
  const [vacinaPreParteAplicadaAgora, setVacinaPreParteAplicadaAgora] = useState(false);
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  // Após secar, oferece mover pra(s) o(s) lote(s) sugerido(s) numa janela
  // suspensa em vez do window.confirm nativo — uma fila (não só a última
  // secada), já que secar várias de uma vez pode sugerir lotes diferentes
  // por vaca (ex.: alguma já estava lá, critério bate diferente por animal).
  const [filaTransferencia, setFilaTransferencia] = useState<{ numero: string; lote: { codigo: string; rotulo: string } }[]>([]);
  const transferenciaPendente = filaTransferencia[0] || null;
  const [transferindo, setTransferindo] = useState(false);
  // Configurações > Parâmetros > "transferir para o lote sugerido
  // automaticamente" — quando ligado, pula a janela de confirmação abaixo e
  // move sozinho.
  const [transferenciaAutomatica, setTransferenciaAutomatica] = useState(false);
  useEffect(() => { fetchTransferenciaLoteAutomatica().then(setTransferenciaAutomatica).catch(() => {}); }, []);

  useEffect(() => {
    if (!matriz) { setInfo(null); return; }
    setCarregandoInfo(true);
    fetchSecagemInfo(matriz)
      .then((d) => { setInfo(d); if (d.data_prevista_secagem) setDataSecagem(d.data_prevista_secagem); })
      .catch(() => setInfo(null))
      .finally(() => setCarregandoInfo(false));
  }, [matriz]);

  // Vacinas (pré-parto).
  useEffect(() => {
    fetchMedicamentos({ finalidade: "vacina_pre_parto", incluir_sem_estoque: incluirSemEstoque }).then((d) => setVacinas((d as any[]).map((m) => m.nome))).catch(() => {});
  }, [incluirSemEstoque]);

  const nomesEstoque = estoque.map((e) => e.nome);
  // Produto de secagem é de livre escolha — não trava na lista de "aptos
  // para secagem" (finalidade cadastrada), mostra todo o estoque/produtos.
  const listaProdutos = Array.from(new Set([...produtos, ...nomesEstoque])).slice().sort();
  const atualizarItem = (idx: number, patch: Partial<ItemSanidade>) => setItens((p) => { const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n; });
  const escolherProduto = (idx: number, produto: string) => {
    const compativeis = unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade);
    atualizarItem(idx, { produto, unidade: compativeis[0] || "" });
  };
  const acrescentarItem = () => setItens((p) => [...p, itemSanidadeVazio()]);
  const removerItem = (idx: number) => setItens((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!numerosAlvo.size) { setErro("Selecione ao menos uma vaca (ou lote)."); return; }
    if (!motivo) { setErro("Selecione o motivo da secagem."); return; }
    if (aplicarVacinaPreParto && !vacinasPreParto.length) {
      setErro('Marque ao menos uma vacina pré-parto, ou volte para "Não" acima.'); return;
    }
    // Índice original preservado (não o do array filtrado) — é por ele que
    // modoDosagem sabe se a dosagem digitada é por vaca ou o total a dividir.
    const itensValidos = itens
      .map((i, idx) => ({ ...i, idx }))
      .filter((i) => i.produto && Number(i.quantidade) > 0 && i.unidade);
    const aplicadoEfetivo = aplicado && dataSecagem <= new Date().toISOString().slice(0, 10);
    const produtosParaEnvio = itensValidos.map((i) => ({
      produto: i.produto, via: i.via || undefined,
      quantidade: modoDosagem[i.idx] === "total" && numerosAlvo.size > 1 ? Number(i.quantidade) / numerosAlvo.size : Number(i.quantidade),
      unidade: i.unidade,
    }));

    setSalvando(true);
    // Loop por animal (mesmo padrão do Diagnóstico): registra sucesso/falha por
    // matriz, sem perder a seleção de quem falhou.
    const salvos: string[] = [];
    const falhados: string[] = [];
    const pendentes: { numero: string; lote: { codigo: string; rotulo: string } }[] = [];
    try {
      for (const numero of numerosAlvo) {
        try {
          const r = await criarSecagem({
            numero_matriz: numero, data_secagem: dataSecagem, motivo,
            escore_condicao_corporal: ecc ? Number(ecc) : null,
            observacao: observacao || undefined, responsavel: responsavel || undefined, aplicado: aplicadoEfetivo,
            produtos: produtosParaEnvio,
            vacinas_pre_parto: aplicarVacinaPreParto ? vacinasPreParto : [],
            vacina_pre_parto_aplicada_agora: aplicarVacinaPreParto ? vacinaPreParteAplicadaAgora : false,
            vacina_pre_parto: aplicarVacinaPreParto,
          });
          // Cada vaca pode ter uma sugestão diferente (ex.: alguma já está no
          // lote das secas) — só entra na fila quem realmente precisa mudar.
          if (r.lote_sugerido && codigoGrupo(animais.find((a) => a.numero === numero)?.grupo_primario) !== r.lote_sugerido.codigo) {
            pendentes.push({ numero, lote: r.lote_sugerido });
          }
          salvos.push(numero);
        } catch {
          falhados.push(numero);
        }
      }
      if (falhados.length) {
        setVinculo("animal"); setLotesSelecionados([]); setSelecionados(new Set(falhados));
        if (salvos.length) {
          setSucesso(`Secagem lançada para ${salvos.length} animal(is).`);
          setErro(`Falharam: ${falhados.join(", ")} — tente novamente só esses.`);
        } else {
          setErro(`Nenhuma secagem lançada. Falharam: ${falhados.join(", ")} — tente novamente.`);
        }
      } else {
        setSucesso(`Secagem lançada com sucesso para ${salvos.length} animal(is).`);
        if (pendentes.length && transferenciaAutomatica) {
          // "Transferir automaticamente" ligado em Configurações > Parâmetros
          // — move sozinho, sem abrir a janela de confirmação abaixo.
          const movidos: string[] = []; const falhasMov: string[] = [];
          for (const p of pendentes) {
            try {
              const r = await criarMovimentacao({ data_movimento: dataSecagem, motivo: "Secagem", lote_destino_codigo: p.lote.codigo, animais: [p.numero], origem: "sugestao_automatica" });
              if ((r.movidos ?? 0) >= 1 && !(r.nao_encontrados || []).includes(p.numero)) movidos.push(`${p.numero} → ${p.lote.rotulo}`);
              else falhasMov.push(p.numero);
            } catch { falhasMov.push(p.numero); }
          }
          if (movidos.length) setSucesso((s) => `${s} Transferido(s) automaticamente: ${movidos.join(", ")}.`);
          if (falhasMov.length) setErro(`Não foi possível transferir automaticamente: ${falhasMov.join(", ")}.`);
        } else if (pendentes.length) {
          // Fila de confirmação, uma de cada vez — inclusive quando várias
          // vacas foram secadas juntas, cada uma pode precisar de um lote
          // diferente (ou nenhum, se já estiver no lote certo).
          setFilaTransferencia(pendentes);
        }
        setSelecionados(new Set()); setLotesSelecionados([]);
        setMotivo(""); setEcc(""); setObservacao(""); setItens([itemSanidadeVazio()]); setModoDosagem({});
        setAplicarVacinaPreParto(false); setVacinasPreParto([]); setVacinaPreParteAplicadaAgora(false);
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar secagem");
    } finally {
      setSalvando(false);
    }
  }

  async function confirmarTransferenciaLote() {
    if (!transferenciaPendente) return;
    const { numero, lote } = transferenciaPendente;
    setTransferindo(true);
    try {
      const r = await criarMovimentacao({ data_movimento: dataSecagem, motivo: "Secagem", lote_destino_codigo: lote.codigo, animais: [numero], origem: "sugestao_confirmada" });
      const moveuDeFato = (r.movidos ?? 0) >= 1 && !(r.nao_encontrados || []).includes(numero);
      if (!moveuDeFato) throw new Error(`Não foi possível mover ${numero} para o lote ${lote.rotulo}.`);
      setSucesso((s) => `${s || ""} ${numero} movida para o lote ${lote.rotulo}.`);
      setFilaTransferencia((f) => f.slice(1));
    } catch (e: any) {
      setErro(e.message || "Erro ao mover para o lote.");
    } finally {
      setTransferindo(false);
    }
  }

  function pularTransferenciaLote() {
    setFilaTransferencia((f) => f.slice(1));
  }

  return (
    <>
      <Campo label="Vaca(s) — animal(is) ou lote(s)" full>
        <TabBar<"animal" | "lote">
          abas={[
            { id: "animal", label: "Animal(is)", title: "Selecionar vacas individualmente" },
            { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes" },
          ]}
          ativa={vinculo}
          onChange={setVinculo}
        />
        <p style={nota}>Lista apenas vacas em lactação (lote de lactação ou DEL em curso).</p>
        {vinculo === "animal" ? (
          <AnimalPickerModal
            animais={animaisLactacao} selecionados={selecionados} onToggle={toggle}
            titulo="Escolher vaca(s) para secar"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
            ]}
          />
        ) : (
          <div style={{ marginTop: "0.5rem" }}>
            <LotePicker
              opcoes={opcoesLoteDeAnimais(animaisLactacao, codigosLotes)}
              selecionados={lotesSelecionados}
              onChange={setLotesSelecionados}
              placeholder="Selecionar lote(s)…"
            />
            {lotesSelecionados.length > 0 && (
              <div style={{ marginTop: "0.6rem" }}>
                <AnimalPickerModal
                  animais={animaisDoLoteSel} selecionados={selLote} onToggle={toggleLote}
                  titulo="Ajustar vacas do(s) lote(s) selecionado(s)"
                  placeholder="Ajustar vacas do(s) lote(s)…"
                  colunas={[
                    { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                    { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  ]}
                />
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  {selLote.size} de {animaisDoLoteSel.length} vaca(s) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir alguma.
                </p>
              </div>
            )}
          </div>
        )}
      </Campo>

      {numerosAlvo.size > 0 && (
        <div className="mt-3" style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", alignItems: "center" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600 }}>
            {numerosAlvo.size} vaca(s) selecionada(s):
          </span>
          {Array.from(numerosAlvo).sort().map((n) => (
            <span key={n} style={{
              fontSize: "0.76rem", background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: "999px", padding: "0.15rem 0.6rem", fontWeight: 600,
            }}>
              {n}
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        {numerosAlvo.size === 1 && (
          <>
            <Campo label="DEL atual">
              <input style={{ ...inputStyle, opacity: 0.8 }} readOnly value={carregandoInfo ? "Carregando…" : info?.del_atual != null ? `${info.del_atual} dias` : "—"} />
            </Campo>
            <Campo label="Dias de gestação">
              <input style={{ ...inputStyle, opacity: 0.8 }} readOnly value={info?.dias_gestacao != null ? `${info.dias_gestacao} dias` : "—"} />
            </Campo>
            <Campo label="Data prevista de secagem (60 dias antes do parto)">
              <input style={{ ...inputStyle, opacity: 0.8 }} readOnly value={info?.data_prevista_secagem ? formatDate(info.data_prevista_secagem) : "—"} />
            </Campo>
          </>
        )}
        <Campo label="Data da secagem (pode ser retroativa)"><input type="date" style={inputStyle} value={dataSecagem} onChange={(e) => setDataSecagem(e.target.value)} /></Campo>
        <Campo label="Motivo da secagem">
          <select style={inputStyle} value={motivo} onChange={(e) => setMotivo(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            {MOTIVOS_SECAGEM.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
          </select>
        </Campo>
        <Campo label="Escore de condição corporal (opcional, 1 a 5)">
          <input type="number" step={0.25} min={1} max={5} style={inputStyle} value={ecc} onChange={(e) => setEcc(e.target.value)} placeholder="ex.: 3,25" />
        </Campo>
        <Campo label="Responsável"><select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="">Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select></Campo>
        <Campo label="Observação"><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      {info?.motivo_exclusao && <p style={{ ...nota, color: "var(--amber)" }}>{info.motivo_exclusao}</p>}

      <Secao>Produto(s) de secagem (opcional)</Secao>
      <div className="space-y-3">
        {itens.map((item, idx) => {
          const estoqueItem = estoque.find((e) => e.nome === item.produto);
          const compativeis = unidadesCompativeis(estoqueItem?.unidade);
          return (
            <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.75rem", position: "relative" }}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Campo label={`Medicamento ${idx + 1}`}>
                  <select style={inputStyle} value={item.produto} onChange={(e) => escolherProduto(idx, e.target.value)}>
                    <option value="" disabled>Selecione…</option>
                    {listaProdutos.map((nome) => {
                      const est = estoque.find((e) => e.nome === nome);
                      return <option key={nome} value={nome}>{nome}{est?.quantidade != null ? ` (${est.quantidade} ${est.unidade || ""})` : ""}</option>;
                    })}
                  </select>
                </Campo>
                <Campo label="Via">
                  <select style={inputStyle} value={item.via} onChange={(e) => atualizarItem(idx, { via: e.target.value })}>
                    <option value="">Selecione…</option>
                    {["Intramuscular", "Subcutânea", "Intramamária", "Oral", "Tópica"].map((o) => <option key={o}>{o}</option>)}
                  </select>
                </Campo>
                <Campo label="Dosagem"><input type="number" inputMode="decimal" style={inputStyle} value={item.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} /></Campo>
                <Campo label="Unidade">
                  <select style={inputStyle} value={item.unidade} onChange={(e) => atualizarItem(idx, { unidade: e.target.value })}>
                    {compativeis.map((u) => <option key={u}>{u}</option>)}
                  </select>
                </Campo>
              </div>
              {numerosAlvo.size > 1 && (
                <div className="flex items-center gap-4 mt-2">
                  <label className="flex items-center gap-2" style={{ fontSize: "0.78rem", cursor: "pointer" }}>
                    <input type="radio" checked={(modoDosagem[idx] ?? "por_vaca") === "por_vaca"} onChange={() => setModoDosagem((p) => ({ ...p, [idx]: "por_vaca" }))} /> Dosagem por vaca
                  </label>
                  <label className="flex items-center gap-2" style={{ fontSize: "0.78rem", cursor: "pointer" }}>
                    <input type="radio" checked={modoDosagem[idx] === "total"} onChange={() => setModoDosagem((p) => ({ ...p, [idx]: "total" }))} /> Dosagem total (divide pelas {numerosAlvo.size} vacas)
                  </label>
                </div>
              )}
              {item.produto && (
                <EstoqueRestante
                  estoque={estoque} produto={item.produto}
                  quantidade={(modoDosagem[idx] === "total" && numerosAlvo.size > 1 ? (Number(item.quantidade) || 0) : (Number(item.quantidade) || 0) * Math.max(1, numerosAlvo.size))}
                />
              )}
              {itens.length > 1 && (
                <button onClick={() => removerItem(idx)} title="Remover este item" aria-label="Remover este item" className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", color: "var(--red)", fontSize: "0.72rem" }}>
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          );
        })}
      </div>
      <div className="flex items-center gap-2 mt-2" style={{ flexWrap: "wrap" }}>
        <button onClick={acrescentarItem} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.78rem" }}><Plus size={14} /> Acrescentar produto</button>
      </div>

      <Secao>Vacina(s) pré-parto</Secao>
      <div className="flex items-center gap-4 mb-2">
        <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}>
          <input type="radio" checked={!aplicarVacinaPreParto} onChange={() => { setAplicarVacinaPreParto(false); setVacinasPreParto([]); }} /> Não
        </label>
        <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}>
          <input type="radio" checked={aplicarVacinaPreParto} onChange={() => setAplicarVacinaPreParto(true)} /> Sim — aplicar vacina(s) pré-parto
        </label>
      </div>
      {aplicarVacinaPreParto && (
        <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.75rem" }}>
          <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.75rem", color: "var(--text-muted)", cursor: "pointer" }}>
            <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => setIncluirSemEstoque(e.target.checked)} />
            Incluir itens sem estoque
          </label>
          {!vacinas.length && (
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              Nenhuma vacina com estoque disponível. Marque "Incluir itens sem estoque" acima para ver também as vacinas sem saldo cadastrado.
            </p>
          )}
          {vacinas.map((v) => (
            <label key={v} className="flex items-center gap-2" style={{ fontSize: "0.82rem", cursor: "pointer", padding: "0.15rem 0" }}>
              <input type="checkbox" checked={vacinasPreParto.includes(v)}
                onChange={() => setVacinasPreParto((p) => p.includes(v) ? p.filter((x) => x !== v) : [...p, v])} />
              {v}
            </label>
          ))}
          {vacinasPreParto.length > 0 && (
            <div className="flex items-center gap-4 mt-3" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
              <span style={{ fontSize: "0.8rem" }}>Vacina(s) já aplicada(s) agora?</span>
              <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", cursor: "pointer" }}>
                <input type="radio" checked={!vacinaPreParteAplicadaAgora} onChange={() => setVacinaPreParteAplicadaAgora(false)} /> Não, aplico depois
              </label>
              <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", cursor: "pointer" }}>
                <input type="radio" checked={vacinaPreParteAplicadaAgora} onChange={() => setVacinaPreParteAplicadaAgora(true)} /> Sim, já apliquei agora
              </label>
            </div>
          )}
          <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
            {vacinaPreParteAplicadaAgora
              ? "Registra a aplicação em Sanidade e dá baixa no estoque agora — não gera pendência na Agenda."
              : "Gera uma pendência na Agenda para o dia seguinte à secagem, com o animal e a(s) vacina(s) a aplicar."}
          </p>
        </div>
      )}

      {itens.some((i) => i.produto) && (
        <Campo label="O(s) produto(s) de secagem já foram aplicados?">
          {dataSecagem > new Date().toISOString().slice(0, 10) ? (
            <p style={{ fontSize: "0.8rem", color: "var(--amber)" }}>Data futura — o(s) produto(s) serão <strong>programados na Agenda</strong> (não baixa estoque até você dar baixa).</p>
          ) : (
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={aplicado} onChange={() => setAplicado(true)} /> Sim — aplicar e baixar o estoque agora</label>
              <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={!aplicado} onChange={() => setAplicado(false)} /> Não — só programar na Agenda</label>
            </div>
          )}
        </Campo>
      )}

      {aplicarVacinaPreParto && !vacinasPreParto.length && (
        <p style={{ ...nota, marginLeft: 0, display: "block", color: "var(--amber)" }}>
          Marque ao menos uma vacina pré-parto acima para salvar, ou volte para "Não".
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando || !numerosAlvo.size || (aplicarVacinaPreParto && !vacinasPreParto.length)}>
          {salvando ? "Salvando…" : `Salvar (${numerosAlvo.size || 0} ${numerosAlvo.size !== 1 ? "animais" : "animal"})`}
        </button>
      </div>

      {transferenciaPendente && (
        <Modal title="Mover para o lote das secas" onClose={pularTransferenciaLote} width="420px" zIndex={95}>
          <p style={{ fontSize: "0.9rem", marginBottom: "1rem" }}>
            Deseja transferir a vaca <strong>{transferenciaPendente.numero}</strong> para o lote{" "}
            <strong>{transferenciaPendente.lote.rotulo}</strong>?
            {filaTransferencia.length > 1 && (
              <><br /><span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>Mais {filaTransferencia.length - 1} vaca(s) na fila depois desta.</span></>
            )}
          </p>
          <div className="flex items-center justify-end gap-2">
            <button className="btn-ghost" onClick={pularTransferenciaLote} disabled={transferindo}>Não</button>
            <button className="btn-primary" onClick={confirmarTransferenciaLote} disabled={transferindo}>
              {transferindo ? "Movendo…" : "Sim, transferir"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
