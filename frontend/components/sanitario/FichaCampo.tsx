"use client";
// Ficha de campo do sanitário — PRÉ-PREENCHIDA (GET /sanitario/dias/{id}/ficha)
// ou VAZIA (GET /sanitario/ficha-vazia). O back devolve JSON; aqui vira a
// folha e o botão "Imprimir" usa o CSS de impressão (.san-imprimir em
// globals.css: só a folha sai no papel). Plano B para curral sem celular.
import { useEffect, useState } from "react";
import { Printer } from "lucide-react";
import { Modal } from "@/components/Modal";
import { fichaDoDia, fichaVazia as buscarFichaVazia, mensagemDoErro } from "@/lib/apiSanitario";
import { fmtData, textoProduto, type FichaDia, type FichaVazia } from "@/lib/sanitarioTipos";
import { Faixa } from "./comum";

const CABECALHO_VAZIA: Record<string, string> = {
  data: "Data ___/___/______", veterinario: "Veterinário ______________________", crmv: "CRMV __________",
  produto: "Produto ____________________", partida: "Partida ________",
};

export function imprimirFolha() {
  const corpo = document.body;
  corpo.classList.add("san-imprimindo");
  const tirar = () => { corpo.classList.remove("san-imprimindo"); window.removeEventListener("afterprint", tirar); };
  window.addEventListener("afterprint", tirar);
  window.print();
  // Navegadores que não disparam afterprint (alguns WebViews): tira depois.
  setTimeout(tirar, 4000);
}

export function FolhaPrePreenchida({ ficha }: { ficha: FichaDia }) {
  const vet = ficha.veterinario?.texto || "";
  return (
    <div className="san-folha san-imprimir">
      <div className="tit">{ficha.fazenda ? `${ficha.fazenda} · ` : ""}{ficha.titulo}{ficha.hora ? ` · ${ficha.hora}` : ""}</div>
      <div>Data: {fmtData(ficha.data)} · Veterinário: {vet || "______________________"} · CRMV: {ficha.veterinario?.crmv || "__________"}</div>
      <div>{ficha.caixas.map((c) => `${c.nome_curto}: ${textoProduto(c.produto)}`).join(" · ")}</div>
      <table>
        <thead><tr>{ficha.colunas.map((c) => <th key={c.chave}>{c.rotulo}</th>)}</tr></thead>
        <tbody>
          {ficha.linhas.map((l) => (
            <tr key={l.animal_id}>
              {ficha.colunas.map((c) => {
                if (c.chave.startsWith("caixa:")) {
                  const cid = Number(c.chave.slice(6));
                  return l.caixas.includes(cid) ? <td key={c.chave} className="box" /> : <td key={c.chave} className="box">—</td>;
                }
                const v: Record<string, string> = {
                  brinco: l.brinco, categoria: l.categoria || "", lote: l.lote || "", idade: l.idade || "",
                  peso: l.peso != null ? `${l.peso} kg` : "", dose: "", partida: "", assinatura: "", obs: "",
                };
                return <td key={c.chave}>{c.chave === "brinco" ? <b>{v.brinco}</b> : v[c.chave] ?? ""}</td>;
              })}
            </tr>
          ))}
          {Array.from({ length: ficha.linhas_em_branco || 0 }, (_, i) => (
            <tr key={`b${i}`}>{ficha.colunas.map((c) => <td key={c.chave} className={c.chave.startsWith("caixa:") ? "box" : undefined} />)}</tr>
          ))}
        </tbody>
      </table>
      <div className="rod">
        {ficha.rodape} Marque o quadrado de quem recebeu.
        {ficha.lembretes.length > 0 && <> Lembrete: {ficha.lembretes.join(" · ")}.</>}
      </div>
    </div>
  );
}

export function FolhaVazia({ ficha }: { ficha: FichaVazia }) {
  return (
    <div className="san-folha san-imprimir">
      <div className="tit">{ficha.fazenda ? `${ficha.fazenda} · ` : ""}{ficha.titulo}</div>
      <div>{ficha.campos_cabecalho.map((c) => CABECALHO_VAZIA[c] || c).join(" · ")}</div>
      <table>
        <thead><tr>{ficha.colunas.map((c) => <th key={c.chave}>{c.rotulo}</th>)}</tr></thead>
        <tbody>
          {Array.from({ length: ficha.linhas_em_branco || 0 }, (_, i) => (
            <tr key={i}>{ficha.colunas.map((c) => <td key={c.chave} className={c.chave === "aplicado" || c.chave === "resultado" ? "box" : undefined} />)}</tr>
          ))}
        </tbody>
      </table>
      <div className="rod">Preencha à mão e lance depois em Lançamentos › Preventivo (origem “ficha”).</div>
    </div>
  );
}

/** Pop-up com a ficha (pré-preenchida de um dia, ou vazia de uma ou mais vacinas/exames). */
export function ModalFicha({ diaId, caixaIds, linhas = 25, onFechar }: {
  diaId?: number; caixaIds?: number[]; linhas?: number; onFechar: () => void;
}) {
  const [ficha, setFicha] = useState<FichaDia | FichaVazia | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const ids = (caixaIds || []).join(",");
  useEffect(() => {
    let vivo = true;
    const lista = ids ? ids.split(",").map(Number) : [];
    const p: Promise<FichaDia | FichaVazia> = diaId ? fichaDoDia(diaId) : buscarFichaVazia(lista, linhas);
    p.then((f) => { if (vivo) setFicha(f); }).catch((e) => { if (vivo) setErro(mensagemDoErro(e, "Não foi possível montar a ficha.")); });
    return () => { vivo = false; };
  }, [diaId, ids, linhas]);
  return (
    <Modal title={diaId ? "Ficha de campo" : "Ficha vazia"} onClose={onFechar} width="960px" zIndex={110}>
      <div className="san-modal-corpo">
        <p className="san-modal-sub">{diaId ? "Pré-preenchida a partir do dia marcado. Plano B para curral sem celular."
          : "Para imprimir, levar ao curral e lançar depois."}</p>
        {erro ? <Faixa tipo="alerta">{erro}</Faixa> : !ficha ? <div className="skeleton" style={{ height: "16rem" }} role="status" aria-label="Montando a ficha" />
          : <div style={{ overflowX: "auto" }}>{ficha.tipo === "vazia" ? <FolhaVazia ficha={ficha} /> : <FolhaPrePreenchida ficha={ficha} />}</div>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onFechar}>Fechar</button>
        <button type="button" className="btn-primary" onClick={imprimirFolha} disabled={!ficha}>
          <Printer size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 6 }} />Imprimir
        </button>
      </div>
    </Modal>
  );
}
