"use client";
// Sub-tela ALIMENTAÇÃO: registro do "real oferecido" a uma dieta ativa —
// o lançamento diário mais simples do desktop (lote/dieta, alimento, kg, data).
// Endpoint: POST /alimentacao/dietas/{id}/real.
import { useMemo, useState } from "react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { fetchDietas, fetchLotes } from "@/lib/api";
import { type Dieta, useCache, useEnvio, hoje } from "./comum";

type Lote = { id: number; codigo: string; nome: string };

export function FormAlimentacao() {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const dietas = useCache<Dieta[]>("dietas_ativas", () => fetchDietas({ ativo: true }) as Promise<Dieta[]>, []);
  const lotes = useCache<Lote[]>("lotes", () => fetchLotes() as Promise<Lote[]>, []);

  const [dietaId, setDietaId] = useState("");
  const [alimento, setAlimento] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [data, setData] = useState(hoje());

  const rotuloLote = (l: number) => {
    const lo = lotes.dados.find((x) => Number(x.codigo) === l);
    return lo ? `${lo.codigo} - ${lo.nome}` : `Lote ${l}`;
  };
  const dietaSel = useMemo(() => dietas.dados.find((d) => String(d.id) === dietaId), [dietas.dados, dietaId]);
  const itemSel = useMemo(() => dietaSel?.itens_programados.find((i) => i.alimento === alimento), [dietaSel, alimento]);

  function salvar() {
    if (!dietaSel) return erroValidacao("Selecione a dieta (lote).");
    if (!alimento || !itemSel) return erroValidacao("Selecione o alimento.");
    if (!(Number(quantidade) > 0)) return erroValidacao("Informe a quantidade fornecida.");
    enviar(
      `/alimentacao/dietas/${dietaSel.id}/real`,
      { data, itens: [{ alimento, quantidade: Number(quantidade), unidade: itemSel.unidade }] },
      `Alimentação — ${rotuloLote(dietaSel.lote)}: ${quantidade} ${itemSel.unidade} de ${alimento}`,
      () => { setAlimento(""); setQuantidade(""); },
    );
  }

  if (dietas.pronto && dietas.dados.length === 0) {
    return (
      <p style={{ color: "var(--mob-muted)", fontSize: "0.95rem", lineHeight: 1.5 }}>
        Nenhuma dieta ativa. Abra uma dieta para o lote no sistema (desktop) antes de registrar o consumo do dia aqui.
      </p>
    );
  }

  return (
    <>
      <MobCampo label="Lote / dieta ativa">
        <select className="mob-input" value={dietaId} onChange={(e) => { setDietaId(e.target.value); setAlimento(""); }}>
          <option value="">Selecione a dieta…</option>
          {dietas.dados.map((d) => <option key={d.id} value={d.id}>{rotuloLote(d.lote)}</option>)}
        </select>
      </MobCampo>
      <MobCampo label="Alimento">
        <select className="mob-input" value={alimento} onChange={(e) => setAlimento(e.target.value)} disabled={!dietaSel}>
          <option value="">{dietaSel ? "Selecione o alimento…" : "Escolha a dieta primeiro"}</option>
          {dietaSel?.itens_programados.map((i) => <option key={i.alimento} value={i.alimento}>{i.alimento} ({i.unidade})</option>)}
        </select>
      </MobCampo>
      <MobCampo label={`Quantidade fornecida${itemSel ? ` (${itemSel.unidade})` : ""}`}>
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
