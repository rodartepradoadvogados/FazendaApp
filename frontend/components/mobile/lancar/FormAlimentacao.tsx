"use client";
// Sub-tela ALIMENTAÇÃO: registro do "real oferecido" a uma dieta —
// o lançamento diário mais simples do desktop (lote/dieta, alimento, kg, data).
// Endpoint: POST /alimentacao/dietas/{id}/real.
//
// Carrega TODAS as dietas (sem forçar "ativo"): o usuário escolhe o LOTE e,
// dentro dele, a dieta — preferindo a ativa. A mensagem "nenhuma dieta
// cadastrada" só aparece quando realmente não existe nenhuma dieta.
import { useEffect, useMemo, useState } from "react";
import { MobCampo, MobAviso } from "@/components/mobile/ui";
import { fetchDietas, fetchLotes } from "@/lib/api";
import { type Dieta, useCache, useEnvio, useRascunho, hoje, RascunhoAviso } from "./comum";

type Lote = { id: number; codigo: string; nome: string };
type DraftAlimentacao = { loteSel: string; dietaId: string; alimento: string; quantidade: string };

export function FormAlimentacao() {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  // Sem filtro de "ativo": pegamos tudo e tratamos ativa/encerrada na tela.
  const dietas = useCache<Dieta[]>("dietas", () => fetchDietas() as Promise<Dieta[]>, []);
  const lotes = useCache<Lote[]>("lotes", () => fetchLotes() as Promise<Lote[]>, []);

  // Rascunho — a quantidade pesada no cocho é exatamente o tipo de dado que
  // se perde numa interrupção (docs/agents/design-implementation.md §5,
  // acabamento-de-campo.html).
  const rascunho = useRascunho<DraftAlimentacao>("alimentacao", { loteSel: "", dietaId: "", alimento: "", quantidade: "" });
  const { loteSel, dietaId, alimento, quantidade } = rascunho.valor;
  const atualizar = (patch: Partial<DraftAlimentacao>) => rascunho.setValor((atual) => ({ ...atual, ...patch }));
  const setLoteSel = (v: string) => atualizar({ loteSel: v });
  const setDietaId = (v: string) => atualizar({ dietaId: v });
  const setAlimento = (v: string) => atualizar({ alimento: v });
  const setQuantidade = (v: string) => atualizar({ quantidade: v });
  const [data, setData] = useState(hoje());

  const rotuloLote = (l: number) => {
    const lo = lotes.dados.find((x) => Number(x.codigo) === l);
    return lo ? `${lo.codigo} - ${lo.nome}` : `Lote ${l}`;
  };

  // Lotes que têm alguma dieta (ordenados). Prefere quem tem dieta ativa.
  const lotesComDieta = useMemo(() => {
    const nums = Array.from(new Set(dietas.dados.map((d) => d.lote)));
    return nums.sort((a, b) => a - b);
  }, [dietas.dados]);

  const dietasDoLote = useMemo(
    () => dietas.dados.filter((d) => String(d.lote) === loteSel),
    [dietas.dados, loteSel],
  );

  // Dieta preferida do lote: a ativa; senão, se houver só uma, ela mesma.
  const dietaPreferida = useMemo(() => {
    const ativa = dietasDoLote.find((d) => d.ativa);
    if (ativa) return ativa;
    if (dietasDoLote.length === 1) return dietasDoLote[0];
    return undefined;
  }, [dietasDoLote]);

  // Se só existe um lote com dieta, já seleciona.
  useEffect(() => {
    if (!loteSel && lotesComDieta.length === 1) setLoteSel(String(lotesComDieta[0]));
  }, [lotesComDieta, loteSel]);

  // Ao trocar de lote, seleciona a dieta preferida (ou limpa se ambígua).
  useEffect(() => {
    atualizar({ dietaId: dietaPreferida ? String(dietaPreferida.id) : "", alimento: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loteSel]);

  const dietaSel = useMemo(() => dietas.dados.find((d) => String(d.id) === dietaId), [dietas.dados, dietaId]);
  const itemSel = useMemo(() => dietaSel?.itens_programados.find((i) => i.alimento === alimento), [dietaSel, alimento]);

  function salvar() {
    if (!dietaSel) return erroValidacao("Selecione o lote e a dieta.");
    if (!alimento || !itemSel) return erroValidacao("Selecione o alimento.");
    if (!(Number(quantidade) > 0)) return erroValidacao("Informe a quantidade fornecida.");
    enviar(
      `/alimentacao/dietas/${dietaSel.id}/real`,
      { data, itens: [{ alimento, quantidade: Number(quantidade), unidade: itemSel.unidade }] },
      `Alimentação — ${rotuloLote(dietaSel.lote)}: ${quantidade} ${itemSel.unidade} de ${alimento}`,
      () => atualizar({ alimento: "", quantidade: "" }),
    );
  }

  // Só mostra o vazio quando a lista carregou e está realmente vazia.
  if (dietas.pronto && dietas.dados.length === 0) {
    return (
      <p style={{ color: "var(--mob-muted)", fontSize: "0.95rem", lineHeight: 1.5 }}>
        Nenhuma dieta cadastrada. Cadastre a dieta do lote nas Configurações do site (Alimentação);
        aqui você registra o consumo real do dia quando houver dieta.
      </p>
    );
  }

  const dietaEncerrada = dietaSel && !dietaSel.ativa;

  return (
    <>
      <RascunhoAviso mostrar={rascunho.salvo} />
      <MobCampo label="Lote">
        <select className="mob-input" value={loteSel} onChange={(e) => setLoteSel(e.target.value)}>
          <option value="">Selecione o lote…</option>
          {lotesComDieta.map((l) => <option key={l} value={String(l)}>{rotuloLote(l)}</option>)}
        </select>
      </MobCampo>

      {/* Só pede a dieta quando o lote tem mais de uma (senão já vem escolhida). */}
      {dietasDoLote.length > 1 && (
        <MobCampo label="Dieta do lote">
          <select className="mob-input" value={dietaId} onChange={(e) => { setDietaId(e.target.value); setAlimento(""); }}>
            <option value="">Selecione a dieta…</option>
            {dietasDoLote.map((d) => (
              <option key={d.id} value={String(d.id)}>
                Dieta #{d.id}{d.ativa ? " (ativa)" : " (encerrada)"}
              </option>
            ))}
          </select>
        </MobCampo>
      )}

      <MobCampo label="Alimento">
        <select className="mob-input" value={alimento} onChange={(e) => setAlimento(e.target.value)} disabled={!dietaSel}>
          <option value="">{dietaSel ? "Selecione o alimento…" : "Escolha o lote primeiro"}</option>
          {dietaSel?.itens_programados.map((i) => <option key={i.alimento} value={i.alimento}>{i.alimento} ({i.unidade})</option>)}
        </select>
      </MobCampo>
      <MobCampo label={`Quantidade fornecida${itemSel ? ` (${itemSel.unidade})` : ""}`}>
        <input type="number" inputMode="decimal" className="mob-input" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="0" />
      </MobCampo>
      <MobCampo label="Data">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>

      {dietaEncerrada && (
        <MobAviso tipo="offline">Esta dieta está encerrada — o consumo será registrado nela mesmo assim.</MobAviso>
      )}

      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
