"use client";
// Sub-tela ESTOQUE: movimento de entrada ou saída de um item.
// Endpoint do desktop: POST /estoque/movimentar (usa os movimentos genéricos
// "Entrada de ajuste" / "Saída de ajuste").
import { useMemo, useState } from "react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { fetchEstoque } from "@/lib/api";
import { type EstoqueItem, useCache, useEnvio, hoje, MobPill, LinhaPills } from "./comum";

export function FormEstoque() {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoque().then((d) => d.itens as EstoqueItem[]), []);

  const [tipo, setTipo] = useState<"entrada" | "saida">("entrada");
  const [nome, setNome] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [data, setData] = useState(hoje());

  const itens = useMemo(() => [...estoque.dados].sort((a, b) => a.nome.localeCompare(b.nome)), [estoque.dados]);
  const item = estoque.dados.find((e) => e.nome === nome);
  const unidade = item?.unidade || "";

  function salvar() {
    if (!nome) return erroValidacao("Selecione o item.");
    if (!(Number(quantidade) > 0)) return erroValidacao("Informe a quantidade.");
    const movimento = tipo === "entrada" ? "Entrada de ajuste" : "Saída de ajuste";
    enviar(
      "/estoque/movimentar",
      { nome, movimento, quantidade: Number(quantidade), unidade: unidade || undefined, data_movimento: data },
      `Estoque ${tipo === "entrada" ? "entrada" : "saída"} — ${quantidade} ${unidade} de ${nome}`,
      () => setQuantidade(""),
    );
  }

  return (
    <>
      <LinhaPills>
        <MobPill ativa={tipo === "entrada"} onClick={() => setTipo("entrada")}>Entrada</MobPill>
        <MobPill ativa={tipo === "saida"} onClick={() => setTipo("saida")}>Saída</MobPill>
      </LinhaPills>

      <MobCampo label="Item do estoque">
        <select className="mob-input" value={nome} onChange={(e) => setNome(e.target.value)}>
          <option value="">Selecione o item…</option>
          {itens.map((e) => <option key={e.nome} value={e.nome}>{e.nome}{e.quantidade != null ? ` (${e.quantidade} ${e.unidade || ""})` : ""}</option>)}
        </select>
      </MobCampo>
      <MobCampo label={`Quantidade${unidade ? ` (${unidade})` : ""}`}>
        <input type="number" inputMode="decimal" className="mob-input" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="0" />
      </MobCampo>
      <MobCampo label="Data">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
