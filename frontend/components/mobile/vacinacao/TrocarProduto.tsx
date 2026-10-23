"use client";
// Trocar produto/dose na hora (app de campo): item do estoque, "produto sem
// estoque" (texto livre, registra mesmo assim), ou sem produto. A dose pode
// ser por animal ou por peso. A lista do estoque vem da cópia local (funciona
// sem sinal com a última lista vista).
import { useMemo, useState } from "react";
import { carregarEstoqueSan, opcoesEstoqueSan, type ItemEstoqueSan } from "@/components/sanitario/comum";
import { DOSE_UNIDADES, ROTULO_UNIDADE, numOuNulo, type DoseUnidade, type ProdutoIn } from "@/lib/sanitarioTipos";
import { FaixaSan, Rotulo, useComCopia } from "./comum";

type Modo = "padrao" | "estoque" | "sem_estoque" | "vazio";

export function TrocarProduto({ titulo, atual, padraoTexto, estoquesPacote, permitirPadrao = true, onAplicar, onVoltar }: {
  titulo: string;
  atual: ProdutoIn | null;
  padraoTexto?: string;
  estoquesPacote?: { id: number; nome: string; unidade: string | null; saldo: number | null }[];
  permitirPadrao?: boolean;
  /** null = voltar ao produto do dia/cadastro */
  onAplicar: (p: ProdutoIn | null) => void;
  onVoltar: () => void;
}) {
  const lista = useComCopia<ItemEstoqueSan[]>("san_estoque", carregarEstoqueSan);
  const estoques = useMemo(() => {
    const m = new Map<number, { id: number; nome: string; unidade: string | null; saldo: number | null }>();
    for (const e of estoquesPacote || []) m.set(e.id, e);
    // Só Farmácia (lib/sanitarioTipos.ehItemFarmacia); a cópia antiga sem a marca conta como Farmácia.
    for (const e of opcoesEstoqueSan(lista.dados, atual?.estoque_id)) if (!m.has(e.id)) m.set(e.id, { id: e.id, nome: e.nome, unidade: e.unidade, saldo: e.quantidade });
    return [...m.values()].sort((a, b) => a.nome.localeCompare(b.nome));
  }, [estoquesPacote, lista.dados, atual?.estoque_id]);
  const [modo, setModo] = useState<Modo>(!atual ? (permitirPadrao ? "padrao" : "vazio") : (atual.modo as Modo) || "vazio");
  const [estoqueId, setEstoqueId] = useState<number | null>(atual?.estoque_id ?? null);
  const [texto, setTexto] = useState(atual?.texto || "");
  const [dose, setDose] = useState(atual?.dose_valor != null ? String(atual.dose_valor).replace(".", ",") : "");
  const [unidade, setUnidade] = useState<DoseUnidade | "">((atual?.dose_unidade as DoseUnidade) || "mL");
  const [xkg, setXkg] = useState(atual?.dose_x_kg != null ? String(atual.dose_x_kg) : "");
  const [busca, setBusca] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const escolhido = estoques.find((e) => e.id === estoqueId);

  function aplicar() {
    if (modo === "padrao") { onAplicar(null); return; }
    if (modo === "estoque" && !estoqueId) { setErro("Escolha o item do estoque."); return; }
    if (modo === "sem_estoque" && !texto.trim()) { setErro("Escreva o nome do produto."); return; }
    const doseNum = numOuNulo(dose.replace(",", "."));
    const p: ProdutoIn = {
      modo, estoque_id: modo === "estoque" ? estoqueId : null, texto: modo === "sem_estoque" ? texto.trim() : null,
      dose_valor: modo === "vazio" ? null : doseNum, dose_unidade: modo === "vazio" || doseNum == null ? null : (unidade || null),
      dose_x_kg: unidade === "mL_por_x_kg" ? numOuNulo(xkg) : null,
    };
    onAplicar(p);
  }

  const opcoes: { id: Modo; rot: string; sub: string }[] = [
    ...(permitirPadrao ? [{ id: "padrao" as Modo, rot: "Produto do dia", sub: padraoTexto || "Como foi marcado" }] : []),
    { id: "estoque", rot: "Do estoque", sub: "Baixa a cada animal registrado" },
    { id: "sem_estoque", rot: "Produto sem estoque", sub: "Registra mesmo assim, sem baixa" },
    { id: "vazio", rot: "Sem produto", sub: "Registrar sem informar o produto" },
  ];
  return (
    <div>
      <p className="mob-san-txt" style={{ marginTop: 0 }}>{titulo}</p>
      <div className="mob-san-chips" role="group" aria-label="Produto">
        {opcoes.map((o) => (
          <button key={o.id} type="button" className="mob-san-chip" aria-pressed={modo === o.id}
            onClick={() => { setModo(o.id); setErro(null); }}>
            <span>{o.rot}<small>{o.sub}</small></span>
          </button>
        ))}
      </div>
      {modo === "estoque" && (
        <>
          <Rotulo>Item do estoque</Rotulo>
          <input className="mob-input" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar no estoque" aria-label="Buscar no estoque" />
          <div style={{ maxHeight: "34vh", overflowY: "auto", marginTop: "0.5rem" }}>
            {estoques.filter((e) => !busca.trim() || e.nome.toLowerCase().includes(busca.trim().toLowerCase())).slice(0, 60).map((e) => (
              <label key={e.id} className="mob-san-linha" data-estado={e.saldo != null && e.saldo <= 0 ? "alerta" : undefined}>
                <input type="radio" name="estq" checked={estoqueId === e.id} onChange={() => setEstoqueId(e.id)} />
                <span style={{ flex: 1 }}>{e.nome}
                  <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>
                    {e.saldo != null ? `Saldo ${String(e.saldo).replace(".", ",")} ${e.unidade || ""}` : "saldo não informado"}
                    {e.saldo != null && e.saldo <= 0 ? " · sem saldo: registra mesmo assim" : ""}
                  </span></span>
              </label>
            ))}
            {!estoques.length && <p className="mob-san-txt">{lista.carregando ? "Carregando o estoque…" : "Sem a lista do estoque neste celular. Use “Produto sem estoque”."}</p>}
          </div>
          {escolhido && escolhido.saldo != null && escolhido.saldo <= 0 && (
            <FaixaSan tipo="atencao">{escolhido.nome} está sem saldo. O registro é feito e o estoque fica negativo até a entrada.</FaixaSan>
          )}
        </>
      )}
      {modo === "sem_estoque" && (
        <>
          <Rotulo>Nome do produto</Rotulo>
          <input className="mob-input" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="ex.: B19 da revenda" />
          <p className="mob-san-txt">Produto fora do estoque: a carência fica desconhecida e é decidida pelo administrador.</p>
        </>
      )}
      {(modo === "estoque" || modo === "sem_estoque") && (
        <>
          <Rotulo>Dose</Rotulo>
          <div className="mob-san-dupla" style={{ marginTop: 0 }}>
            <input className="mob-input" inputMode="decimal" value={dose} onChange={(e) => setDose(e.target.value)} placeholder="ex.: 2" aria-label="Dose" />
            <select className="mob-input" value={unidade} onChange={(e) => setUnidade(e.target.value as DoseUnidade)} aria-label="Unidade">
              {DOSE_UNIDADES.map((u) => <option key={u} value={u}>{ROTULO_UNIDADE[u]}</option>)}
            </select>
          </div>
          {unidade === "mL_por_x_kg" && (
            <input className="mob-input" style={{ marginTop: "0.5rem" }} inputMode="numeric" value={xkg} onChange={(e) => setXkg(e.target.value)}
              placeholder="a cada quantos kg (ex.: 50)" aria-label="A cada quantos kg" />
          )}
        </>
      )}
      {erro && <FaixaSan tipo="alerta">{erro}</FaixaSan>}
      <div className="mob-san-dupla" style={{ marginTop: "0.8rem" }}>
        <button type="button" className="mob-btn-2" onClick={onVoltar}>Voltar</button>
        <button type="button" className="mob-btn" onClick={aplicar}>Usar este</button>
      </div>
    </div>
  );
}
