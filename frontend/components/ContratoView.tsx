"use client";
// Consolidação de UX (backlog #532) — formulário de lançamento e card de
// listagem agora vivem em CadastroAvulsoParceladoGenerico.tsx (compartilhado
// com EmpreitadaView); aqui só ficam as particularidades do contrato: "sem
// frequência definida" (lembrete mensal na Agenda) e o botão de encerrar.
// Nenhum endpoint mudou.
import { useEffect, useState } from "react";
import { XCircle, Trash2 } from "lucide-react";
import {
  fetchPessoas, fetchContratos, criarContrato, encerrarContrato,
  atualizarParcelaContrato, redistribuirParcelasContrato, confirmarExclusao, ehAdmin,
} from "@/lib/api";
import CadastroAvulsoParceladoGenerico, { type ParcelaAvulsa, type ValeItemAvulso } from "@/components/CadastroAvulsoParceladoGenerico";

type Pessoa = { id: number; nome: string; tipos: string[] };
type Contrato = {
  id: number; pessoa_id: number; pessoa_nome: string; descricao: string; valor_total: number;
  forma_pagamento: string | null; status: string; observacao: string | null;
  origem_lembrete_agenda_id: number | null; parcelas: ParcelaAvulsa[]; vales: ValeItemAvulso[];
};

const FORMAS = [
  { id: "", label: "Sem frequência definida (lembrete mensal na Agenda)" },
  { id: "mensal", label: "Mensal" },
  { id: "quinzenal", label: "Quinzenal" },
  { id: "semanal", label: "Semanal" },
];

export default function ContratoView() {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [itens, setItens] = useState<Contrato[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msgEncerrar, setMsgEncerrar] = useState<string | null>(null);
  // G10 — exclusão do contrato (motor genérico), sempre disponível ao lado
  // de "Encerrar" (são coisas diferentes: encerrado continua existindo no
  // histórico, excluído some — inclusive o lembrete de Agenda).
  const [excluindoId, setExcluindoId] = useState<number | null>(null);
  const [msgExclusao, setMsgExclusao] = useState<{ id: number; texto: string } | null>(null);

  const carregar = () => fetchContratos().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchPessoas().then(setPessoas).catch(() => {}); }, []);

  async function encerrar(id: number) {
    try {
      await encerrarContrato(id);
      carregar();
    } catch (e: any) {
      setMsgEncerrar(e.message || "Erro ao encerrar contrato");
    }
  }

  async function excluirContrato(item: Contrato) {
    const admin = ehAdmin();
    const msg = admin
      ? `Excluir o contrato de ${item.pessoa_nome} (${item.descricao})? Isso não pode ser desfeito.`
      : `Solicitar a exclusão do contrato de ${item.pessoa_nome} (${item.descricao})? Um administrador precisa aprovar antes de ser excluído de fato.`;
    if (!window.confirm(msg)) return;
    setMsgExclusao(null);
    setExcluindoId(item.id);
    try {
      const r = await confirmarExclusao("contrato", String(item.id));
      if (r.status !== "excluido") {
        setMsgExclusao({ id: item.id, texto: "Solicitação de exclusão enviada — aguardando aprovação de um administrador." });
      }
      carregar();
    } catch (e: any) {
      setMsgExclusao({ id: item.id, texto: e.message || "Erro ao excluir contrato" });
    } finally {
      setExcluindoId(null);
    }
  }

  return (
    <CadastroAvulsoParceladoGenerico<Contrato>
      itens={itens} error={error} recarregar={carregar}
      pessoas={pessoas} labelPessoa="Pessoa" placeholderDescricao="Ex.: Consultoria, parceria de arrendamento…"
      msgSelecionePessoa="Selecione a pessoa." msgDescricaoObrigatoria="Informe a descrição do contrato."
      formasPagamento={FORMAS} formaPagamentoInicial=""
      formasSemParcelamento={[""]} formasSemCampoData={[""]}
      textoSemParcelamento="Sem frequência definida: todo dia 1º do mês haverá um alerta na Agenda para pagar este contrato ou definir uma nova data."
      tituloNovo="Novo contrato" descricaoNovo="Valor total pago por frequência ou sem data fixa" labelSalvar="Lançar contrato"
      salvar={async ({ pessoaId, descricao, valorTotal, formaPagamento, parcelasPayload, observacao }) => {
        await criarContrato({
          pessoa_id: Number(pessoaId), descricao, valor_total: parseFloat(valorTotal),
          forma_pagamento: formaPagamento || null, observacao: observacao || undefined,
          parcelas: formaPagamento ? parcelasPayload : undefined,
        });
        return formaPagamento
          ? "Contrato lançado."
          : "Contrato lançado — todo dia 1º do mês haverá um alerta na Agenda para pagar ou definir uma nova data.";
      }}
      tituloVale="Vale de contrato" descricaoVale="Adiantamento abatido da próxima parcela pendente"
      valeOrigemTipo="contrato" valeStatusExcluido="encerrado"
      onEditarParcela={atualizarParcelaContrato}
      onRedistribuirParcelas={redistribuirParcelasContrato}
      tituloListagem="Contratos lançados" textoVazioListagem="Nenhum contrato lançado ainda."
      acaoItem={(item) => (
        <span className="flex items-center gap-2">
          {item.status === "ativo" && (
            <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => encerrar(item.id)}>
              <XCircle size={13} /> Encerrar
            </button>
          )}
          <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} title="Excluir contrato"
            disabled={excluindoId === item.id} onClick={() => excluirContrato(item)}>
            <Trash2 size={13} />
          </button>
        </span>
      )}
      renderItemExtra={(item) => (
        <>
          {msgEncerrar && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.5rem" }}>{msgEncerrar}</p>}
          {msgExclusao?.id === item.id && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.5rem" }}>{msgExclusao.texto}</p>}
          {item.parcelas.length === 0 && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.3rem" }}>
              Sem frequência definida — alerta mensal na Agenda todo dia 1º.
            </p>
          )}
        </>
      )}
    />
  );
}
