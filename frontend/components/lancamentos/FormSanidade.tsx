"use client";
import React, { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { criarAplicacaoSanidade, fetchApresentacoesFarmacia, fetchDoencas, fetchMedicamentos, fetchPrincipiosAtivos, marcarEventoRealizado } from "@/lib/api";
import type { ApresentacaoFarmacia } from "@/lib/api";
import { RESPONSAVEIS, VIAS_APLICACAO } from "@/lib/constants";
import { AnimalRow } from "@/components/AnimalModal";
import { EstoquePicker } from "@/components/EstoquePicker";
import {
  Campo, Secao, inputStyle, nota,
  type EstoqueItem, type ItemSanidade, itemSanidadeVazio, unidadesCompativeis, EstoqueRestante,
} from "@/components/lancamentos/comumForms";
import { SelectAnimal } from "@/components/lancamentos/_shared";

export function FormSanidade({ animais, lotes, estoque, produtos }: { animais: AnimalRow[]; lotes: string[]; estoque: EstoqueItem[]; produtos: string[] }) {
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [animal, setAnimal] = useState("");
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [itens, setItens] = useState<ItemSanidade[]>([itemSanidadeVazio()]);
  const [dataAplicacao, setDataAplicacao] = useState(() => new Date().toISOString().slice(0, 10));
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  // "Já foi aplicado?" — quando Não (ou data futura), nada baixa do estoque:
  // fica programado na Agenda até você dar baixa.
  const [aplicado, setAplicado] = useState(true);
  // Vindo da Agenda ("Dar baixa" de um evento sanitário): ao salvar, marca o
  // evento como realizado para sumir da Agenda.
  const [eventoAgenda, setEventoAgenda] = useState<string | null>(null);
  // "Qual frasco/apresentação você está usando?" — por item, as apresentações
  // (frascos/marcas) do mesmo princípio ativo que existem no estoque. Só pergunta
  // quando há mais de uma.
  const [frascosPorItem, setFrascosPorItem] = useState<Record<number, ApresentacaoFarmacia[]>>({});
  // Lançamento por doença ou princípio ativo: abre só os medicamentos que
  // correspondem ao critério (via Farmácia). Listas de opções e produtos
  // filtrados por item.
  const [principiosNomes, setPrincipiosNomes] = useState<string[]>([]);
  const [doencasNomes, setDoencasNomes] = useState<string[]>([]);
  const [opcoesPorItem, setOpcoesPorItem] = useState<Record<number, string[]>>({});
  // Catálogo geral de medicamento/hormônio/vacina (finalidade "Medicamento",
  // com saldo em estoque) para o modo "Medicamento (todos)" — ração/material/
  // equipamento não aparecem mais aqui. "Incluir itens sem estoque" resolve o
  // problema na hora (mesmo padrão do "incluir touros sem estoque").
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [catalogoMedicamentos, setCatalogoMedicamentos] = useState<string[]>([]);
  useEffect(() => {
    fetchMedicamentos({ incluir_sem_estoque: incluirSemEstoque }).then((m: any[]) => setCatalogoMedicamentos(m.map((x) => x.nome))).catch(() => {});
  }, [incluirSemEstoque]);
  useEffect(() => {
    fetchPrincipiosAtivos().then((d: any[]) => setPrincipiosNomes(d.map((p) => p.nome))).catch(() => {});
    fetchDoencas().then((d: any[]) => setDoencasNomes(d.map((x) => x.nome))).catch(() => {});
  }, []);

  // Pré-preenche a partir da Agenda (medicamento padrão do evento sanitário),
  // deixando tudo editável na hora.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get("ir") !== "sanidade_aplicacao") return;
    const numero = qs.get("numero_matriz");
    if (numero) { setModo("animal"); setAnimal(numero); }
    const data = qs.get("data"); if (data) setDataAplicacao(data);
    const produto = qs.get("produto");
    if (produto) {
      setItens([{
        ...itemSanidadeVazio(),
        produto, via: qs.get("via") || "", quantidade: qs.get("dose") || "", unidade: qs.get("unidade") || "",
      }]);
    }
    setEventoAgenda(qs.get("evento_agenda"));
  }, []);

  const toggleLote = (l: string) => setLotesSel((p) => { const s = new Set(p); s.has(l) ? s.delete(l) : s.add(l); return s; });
  // Lista de produtos vem do relatório de sanidade (medicamentos já aplicados),
  // complementada pelo catálogo geral de medicamento/hormônio/vacina em estoque.
  const listaProdutos = Array.from(new Set([...produtos, ...catalogoMedicamentos])).sort();

  const atualizarItem = (idx: number, patch: Partial<ItemSanidade>) => setItens((p) => {
    const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n;
  });
  const escolherProduto = (idx: number, produto: string) => {
    const compativeis = unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade);
    atualizarItem(idx, { produto, unidade: compativeis[0] || "", estoque_id: null });
    // "Qual frasco?": busca as apresentações do mesmo princípio ativo. Mais de
    // uma → o usuário escolhe; só uma → já fixa nela.
    fetchApresentacoesFarmacia({ produto }).then((fr) => {
      setFrascosPorItem((p) => ({ ...p, [idx]: fr }));
      if (fr.length === 1) atualizarItem(idx, { estoque_id: fr[0].estoque_id });
    }).catch(() => setFrascosPorItem((p) => ({ ...p, [idx]: [] })));
  };
  const acrescentarItem = () => setItens((p) => [...p, itemSanidadeVazio()]);
  const removerItem = (idx: number) => setItens((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  // Muda o modo de escolha do medicamento (todos / por princípio ativo / por doença).
  const escolherDefinirPor = (idx: number, valor: ItemSanidade["definirPor"]) => {
    atualizarItem(idx, { definirPor: valor, criterio: "", produto: "", unidade: "", estoque_id: null });
    setOpcoesPorItem((o) => ({ ...o, [idx]: [] }));
  };
  const escolherCriterio = (idx: number, criterio: string) => {
    atualizarItem(idx, { criterio, produto: "", unidade: "", estoque_id: null });
    if (!criterio) { setOpcoesPorItem((o) => ({ ...o, [idx]: [] })); return; }
    const def = itens[idx].definirPor;
    const filtro = def === "principio_ativo" ? { principio_ativo: criterio } : { doenca: criterio };
    fetchMedicamentos({ ...filtro, incluir_sem_estoque: incluirSemEstoque })
      .then((m: any[]) => setOpcoesPorItem((o) => ({ ...o, [idx]: m.map((x) => x.nome) })))
      .catch(() => setOpcoesPorItem((o) => ({ ...o, [idx]: [] })));
  };

  async function salvar() {
    setErro(null); setSucesso(null);
    const animaisAlvo = modo === "animal"
      ? (animal ? [animal] : [])
      : animais.filter((a) => a.grupo_primario && lotesSel.has(a.grupo_primario)).map((a) => a.numero);
    if (!animaisAlvo.length) { setErro(modo === "animal" ? "Selecione o animal." : "Selecione ao menos um lote."); return; }
    const itensValidos = itens.filter((i) => i.produto && Number(i.quantidade) > 0 && i.unidade);
    if (!itensValidos.length) { setErro("Adicione ao menos um produto com quantidade e unidade."); return; }

    setSalvando(true);
    try {
      const hojeStr = new Date().toISOString().slice(0, 10);
      const aplicadoEfetivo = aplicado && dataAplicacao <= hojeStr;
      const r = await criarAplicacaoSanidade({
        data_aplicacao: dataAplicacao, animais: animaisAlvo, responsavel: responsavel || undefined, observacao: observacao || undefined,
        itens: itensValidos.map((i) => ({ produto: i.produto, via: i.via || undefined, quantidade: Number(i.quantidade), unidade: i.unidade, estoque_id: i.estoque_id ?? undefined })),
        aplicado: aplicadoEfetivo,
      });
      if (aplicadoEfetivo && eventoAgenda) { await marcarEventoRealizado(eventoAgenda).catch(() => {}); setEventoAgenda(null); }
      setSucesso(r.programado
        ? `Aplicação PROGRAMADA na Agenda (não baixou estoque). Dê baixa quando aplicar.`
        : `${r.criados} aplicação(ões) lançada(s) com sucesso.${r.avisos?.length ? " " + r.avisos.join(" ") : ""}${eventoAgenda ? " Baixado da Agenda." : ""}`);
      setItens([itemSanidadeVazio()]); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar aplicação de sanidade");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Lançar por">
          <select style={inputStyle} value={modo} onChange={(e) => setModo(e.target.value as any)}><option value="animal">Animal</option><option value="lote">Lote</option></select>
        </Campo>
        <Campo label="Data"><input type="date" style={inputStyle} value={dataAplicacao} onChange={(e) => setDataAplicacao(e.target.value)} /></Campo>
        {modo === "animal"
          ? <Campo label="Animal" full><SelectAnimal animais={animais} value={animal} onChange={setAnimal} /></Campo>
          : <Campo label="Lotes" full>
              <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
                {lotes.map((l) => <label key={l} className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}><input type="checkbox" checked={lotesSel.has(l)} onChange={() => toggleLote(l)} /> {l}</label>)}
              </div>
            </Campo>}
        <Campo label="Responsável"><select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="" disabled>Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select></Campo>
        <Campo label="Observação"><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
        <Campo label="Já foi aplicado?" full>
          {dataAplicacao > new Date().toISOString().slice(0, 10) ? (
            <p style={{ fontSize: "0.8rem", color: "var(--amber)" }}>Data futura — será <strong>programado na Agenda</strong> (não baixa estoque até você dar baixa).</p>
          ) : (
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={aplicado} onChange={() => setAplicado(true)} /> Sim — aplicar e baixar o estoque agora</label>
              <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={!aplicado} onChange={() => setAplicado(false)} /> Não — só programar na Agenda</label>
            </div>
          )}
        </Campo>
      </div>

      <Secao>Produtos aplicados</Secao>
      <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.78rem", color: "var(--text-muted)", cursor: "pointer" }}>
        <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => setIncluirSemEstoque(e.target.checked)} />
        Incluir itens sem estoque
      </label>
      <div className="space-y-3">
        {itens.map((item, idx) => {
          const estoqueItem = estoque.find((e) => e.nome === item.produto);
          const compativeis = unidadesCompativeis(estoqueItem?.unidade);
          return (
            <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.75rem", position: "relative" }}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ marginBottom: "0.6rem" }}>
                <Campo label="Definir medicamento por">
                  <select style={inputStyle} value={item.definirPor} onChange={(e) => escolherDefinirPor(idx, e.target.value as ItemSanidade["definirPor"])}>
                    <option value="medicamento">Medicamento (todos)</option>
                    <option value="principio_ativo">Princípio ativo</option>
                    <option value="doenca">Doença</option>
                  </select>
                </Campo>
                {item.definirPor !== "medicamento" && (
                  <Campo label={item.definirPor === "principio_ativo" ? "Princípio ativo" : "Doença"}>
                    <select style={inputStyle} value={item.criterio} onChange={(e) => escolherCriterio(idx, e.target.value)}>
                      <option value="">Selecione…</option>
                      {(item.definirPor === "principio_ativo" ? principiosNomes : doencasNomes).map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </Campo>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Campo label={`Produto/medicamento ${idx + 1}`}>
                  <EstoquePicker
                    itens={(item.definirPor === "medicamento" ? listaProdutos : (opcoesPorItem[idx] || [])).map((nome) => estoque.find((e) => e.nome === nome) || { nome })}
                    value={item.produto} onChange={(nome) => escolherProduto(idx, nome)}
                    placeholder={item.definirPor !== "medicamento" && !item.criterio ? `Escolha ${item.definirPor === "principio_ativo" ? "o princípio ativo" : "a doença"} primeiro` : "Selecionar produto…"}
                  />
                  {item.definirPor !== "medicamento" && item.criterio && !(opcoesPorItem[idx] || []).length && (
                    <p style={{ fontSize: "0.68rem", color: "var(--amber)", marginTop: 2 }}>Nenhum medicamento com esse critério.</p>
                  )}
                </Campo>
                <Campo label="Via">
                  <select style={inputStyle} value={item.via} onChange={(e) => atualizarItem(idx, { via: e.target.value })}>
                    <option value="">Selecione…</option>
                    {VIAS_APLICACAO.map((o) => <option key={o}>{o}</option>)}
                  </select>
                </Campo>
                <Campo label="Quantidade (dose)"><input type="number" inputMode="decimal" style={inputStyle} value={item.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} /></Campo>
                <Campo label="Unidade">
                  <select style={inputStyle} value={item.unidade} onChange={(e) => atualizarItem(idx, { unidade: e.target.value })}>
                    {compativeis.map((u) => <option key={u}>{u}</option>)}
                  </select>
                </Campo>
              </div>
              {(frascosPorItem[idx]?.length ?? 0) > 1 && (
                <div style={{ marginTop: "0.6rem", background: "var(--surface-2)", border: "1px solid var(--dourado)", borderRadius: 8, padding: "0.55rem 0.7rem" }}>
                  <label style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--dourado-light)", display: "block", marginBottom: "0.3rem" }}>
                    Qual frasco/apresentação você está usando agora?
                  </label>
                  <select style={inputStyle} value={item.estoque_id ?? ""} onChange={(e) => atualizarItem(idx, { estoque_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">Selecione o frasco…</option>
                    {frascosPorItem[idx].map((f) => (
                      <option key={f.estoque_id} value={f.estoque_id}>
                        {f.nome}{f.marca ? ` · ${f.marca}` : ""} — saldo {f.saldo} {f.unidade || ""}{!f.estoque_inicializado ? " (sem estoque inicial)" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              {item.produto && <EstoqueRestante estoque={estoque} produto={item.produto} quantidade={Number(item.quantidade) || 0} />}
              {itens.length > 1 && (
                <button onClick={() => removerItem(idx)} title="Remover este item" aria-label="Remover este item" className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", color: "var(--red)", fontSize: "0.72rem" }}>
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          );
        })}
      </div>
      <button onClick={acrescentarItem} className="btn-ghost flex items-center gap-1 mt-2" style={{ fontSize: "0.78rem" }}><Plus size={14} /> Acrescentar produto</button>

      <p style={nota}>Ao salvar, dá baixa da quantidade no estoque (por animal, ou multiplicada pelo efetivo dos lotes) quando a unidade escolhida bater com a unidade de estoque do produto.</p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}
