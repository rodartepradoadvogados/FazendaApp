"use client";
// "Adicionar produto, serviço ou conta gerencial" e "Associar a produto/serviço já existente":
// os dois diálogos que o lançamento financeiro sempre teve, agora compartilhados com o lançamento de notas
// em fatura/lote (que tinha perdido os dois). Quem usa decide o que fazer com o resultado.
import { useState } from "react";
import { Modal } from "@/components/Modal";
import NovoItemEstoque from "@/components/NovoItemEstoque";
import NovoServicoRapido from "@/components/NovoServicoRapido";
import NovaContaGerencial from "@/components/NovaContaGerencial";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import { ServicoPicker } from "@/components/ServicoPicker";

export type ModoAdicionar = "produto" | "servico" | "conta";

export function ModalAdicionarCadastro({ tipo, temEstoque, modoInicial, nomeSugerido, onClose, onProduto, onServico, onConta }: {
  tipo: "despesa" | "receita"; temEstoque: boolean; modoInicial: ModoAdicionar; nomeSugerido?: string;
  onClose: () => void;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onProduto: (item: any) => void;
  onServico: (servico: { nome: string }) => void;
  onConta: (conta: { codigo: string; nome: string }) => void;
}) {
  const [modo, setModo] = useState<ModoAdicionar>(modoInicial);
  const pilula = (m: ModoAdicionar, rotulo: string, dica: string) => (
    <button type="button" title={dica} onClick={() => setModo(m)} aria-pressed={modo === m}
      style={{ fontSize: "0.78rem", padding: "0.35rem 0.8rem", borderRadius: "999px", cursor: "pointer",
        border: "1px solid " + (modo === m ? "var(--dourado)" : "var(--border)"),
        background: modo === m ? "rgba(94,26,46,0.4)" : "transparent",
        color: modo === m ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: modo === m ? 700 : 500 }}>
      {rotulo}
    </button>
  );
  const nome = nomeSugerido?.trim();
  return (
    <Modal title="Adicionar produto, serviço ou conta gerencial" onClose={onClose} width="900px">
      <div className="flex items-center gap-2 mb-3">
        {temEstoque && pilula("produto", "Novo produto (estoque)", "Cadastrar um novo produto de estoque")}
        {pilula("servico", "Novo serviço", "Cadastrar um novo serviço")}
        {pilula("conta", "Nova conta gerencial", "Cadastrar uma nova conta gerencial")}
      </div>
      {modo === "produto" && temEstoque ? (
        // Pré-preenche com o nome já lançado (ex.: veio do XML/OCR e não batia com nada do estoque) —
        // cadastrar com o MESMO texto é o que faz o item "virar" reconhecido: o sistema reconhece por igualdade de nome.
        <NovoItemEstoque prefill={nome ? { nome } : undefined} onCriado={onProduto} onCancelar={onClose} />
      ) : modo === "servico" ? (
        <NovoServicoRapido prefillNome={nome} onCriado={onServico} onCancelar={onClose} />
      ) : (
        <NovaContaGerencial tipoSugerido={tipo} onCriado={onConta} onCancelar={onClose} />
      )}
    </Modal>
  );
}

/** Associar um item sem cadastro a um produto/serviço que já existe — só troca o texto pelo nome cadastrado. */
export function ModalAssociarExistente({ tipoItem, produtos, servicos, onEscolher, onClose }: {
  tipoItem: "produto" | "servico"; produtos: EstoqueItemPicker[]; servicos: string[];
  onEscolher: (nome: string) => void; onClose: () => void;
}) {
  return (
    <Modal title={`Associar a ${tipoItem === "servico" ? "serviço" : "produto"} já existente`} onClose={onClose} width="600px">
      {tipoItem === "servico" ? (
        <ServicoPicker servicos={servicos.map((nome) => ({ nome }))} value="" onChange={(nome) => { if (nome) onEscolher(nome); }} />
      ) : (
        <EstoquePicker itens={produtos} value="" todasFinalidades incluirNaoEstocaveis onChange={(nome) => { if (nome) onEscolher(nome); }} />
      )}
      <div className="flex justify-end mt-3">
        <button type="button" className="btn-ghost" onClick={onClose}>Cancelar</button>
      </div>
    </Modal>
  );
}
