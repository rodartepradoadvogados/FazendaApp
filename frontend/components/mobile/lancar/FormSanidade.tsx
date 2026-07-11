"use client";
// Sub-tela SANIDADE: aplicação de um produto por animal OU por lote.
// Endpoint do desktop: POST /sanidade/aplicacoes (o lote é resolvido para a
// lista de animais do grupo, como faz o desktop).
import { useMemo, useState } from "react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { fetchEstoque } from "@/lib/api";
import {
  type Animal, type EstoqueItem, useCache, useEnvio, hoje,
  MobPill, LinhaPills, SeletorAnimal, unidadesCompativeis,
} from "./comum";

export function FormSanidade({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoque().then((d) => d.itens as EstoqueItem[]), []);

  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [animal, setAnimal] = useState(animalFixado || "");
  const [lote, setLote] = useState("");
  const [data, setData] = useState(hoje());
  const [produto, setProduto] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [unidade, setUnidade] = useState("");

  // Lotes = grupos primários distintos dos animais (mesma base do desktop).
  const lotes = useMemo(() => {
    const set = new Set<string>();
    animais.forEach((a) => { if (a.grupo_primario) set.add(a.grupo_primario); });
    return Array.from(set).sort();
  }, [animais]);

  const produtos = useMemo(() => estoque.dados.map((e) => e.nome).sort(), [estoque.dados]);
  const compativeis = useMemo(() => unidadesCompativeis(estoque.dados.find((e) => e.nome === produto)?.unidade), [estoque.dados, produto]);

  function escolherProduto(nome: string) {
    setProduto(nome);
    const comp = unidadesCompativeis(estoque.dados.find((e) => e.nome === nome)?.unidade);
    setUnidade(comp[0] || "");
  }

  function salvar() {
    const alvo = modo === "animal"
      ? (animal ? [animal] : [])
      : animais.filter((a) => a.grupo_primario === lote).map((a) => a.numero);
    if (!alvo.length) return erroValidacao(modo === "animal" ? "Selecione o animal." : "Selecione o lote.");
    if (!produto) return erroValidacao("Selecione o produto.");
    if (!(Number(quantidade) > 0)) return erroValidacao("Informe a quantidade.");
    if (!unidade) return erroValidacao("Selecione a unidade.");
    enviar(
      "/sanidade/aplicacoes",
      { data_aplicacao: data, animais: alvo, itens: [{ produto, quantidade: Number(quantidade), unidade }] },
      `Aplicação ${produto} — ${modo === "animal" ? `animal ${animal}` : `lote ${lote}`}`,
      () => { setProduto(""); setQuantidade(""); setUnidade(""); },
    );
  }

  return (
    <>
      <LinhaPills>
        <MobPill ativa={modo === "animal"} onClick={() => setModo("animal")}>Animal</MobPill>
        <MobPill ativa={modo === "lote"} onClick={() => setModo("lote")}>Lote</MobPill>
      </LinhaPills>

      {modo === "animal" ? (
        <MobCampo label="Animal (nº / nome)">
          <SeletorAnimal animais={animais} valor={animal} onChange={setAnimal} placeholder="Buscar animal…" />
        </MobCampo>
      ) : (
        <MobCampo label="Lote">
          <select className="mob-input" value={lote} onChange={(e) => setLote(e.target.value)}>
            <option value="">Selecione o lote…</option>
            {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </MobCampo>
      )}

      <MobCampo label="Data">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Produto / medicamento">
        <select className="mob-input" value={produto} onChange={(e) => escolherProduto(e.target.value)}>
          <option value="">Selecione o produto…</option>
          {produtos.map((nome) => {
            const est = estoque.dados.find((e) => e.nome === nome);
            return <option key={nome} value={nome}>{nome}{est?.quantidade != null ? ` (${est.quantidade} ${est.unidade || ""})` : ""}</option>;
          })}
        </select>
      </MobCampo>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
        <MobCampo label="Quantidade (dose)">
          <input type="number" inputMode="decimal" className="mob-input" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="0" />
        </MobCampo>
        <MobCampo label="Unidade">
          <select className="mob-input" value={unidade} onChange={(e) => setUnidade(e.target.value)}>
            {!unidade && <option value="">—</option>}
            {compativeis.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </MobCampo>
      </div>
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
