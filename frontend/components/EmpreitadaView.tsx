"use client";
// Consolidação de UX (backlog #532) — o formulário de lançamento e o card de
// listagem (comuns a Empreitada/Contrato) vivem agora em
// CadastroAvulsoParceladoGenerico.tsx; aqui só ficam as particularidades da
// empreita: pagamento "por etapa" (com sua própria tabela de etapas) e a
// listagem das etapas já lançadas. Nenhum endpoint mudou.
import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2, CheckCircle2, Upload } from "lucide-react";
import {
  fetchPessoas, fetchEmpreitadas, criarEmpreitada, concluirEtapaEmpreitada, formatBRL,
  atualizarParcelaEmpreitada, redistribuirParcelasEmpreitada, confirmarExclusao, ehAdmin,
  anexarArquivoPessoa,
} from "@/lib/api";
import { type ModoSecaoCategoria } from "@/components/ui";
import CadastroAvulsoParceladoGenerico, { type ParcelaAvulsa, type ValeItemAvulso } from "@/components/CadastroAvulsoParceladoGenerico";
import { inputSm } from "@/components/estiloCampoAvulso";
import { CampoMoeda } from "@/components/CampoMoeda";

type Pessoa = { id: number; nome: string; tipos: string[] };
type Etapa = {
  id: number; nome: string; valor: number; ordem: number; concluida: boolean;
  data_conclusao: string | null; numero_lancamento_gerado: string | null; status_pagamento: string;
};
type Empreitada = {
  id: number; pessoa_id: number; pessoa_nome: string; descricao: string; valor_total: number;
  tipo_pagamento: string; status: string; observacao: string | null;
  parcelas: ParcelaAvulsa[]; etapas: Etapa[]; vales: ValeItemAvulso[];
};

const FREQUENCIAS = [
  { id: "mensal", label: "Mensal" },
  { id: "semanal", label: "Semanal" },
  { id: "quinzenal", label: "Quinzenal" },
  { id: "inicio_empreita", label: "No início da empreita" },
  { id: "fim_empreita", label: "Ao final da empreita" },
  { id: "por_etapa", label: "Ao final de cada etapa" },
];
// Forma de pagamento com data única (não recorrente) — pede só 1 data e
// lança 1 parcela com o valor total, que cai na Agenda/Contas a Pagar
// igual às demais (ver ParcelamentoEditor para mensal/semanal/quinzenal).
const FORMAS_DATA_UNICA = ["inicio_empreita", "fim_empreita"];

type EtapaForm = { nome: string; valor: string };
const etapaFormVazia: EtapaForm[] = [{ nome: "", valor: "" }];

export default function EmpreitadaView({ mostrar = "tudo" }: { mostrar?: ModoSecaoCategoria }) {
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [itens, setItens] = useState<Empreitada[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [etapasForm, setEtapasForm] = useState<EtapaForm[]>(etapaFormVazia);
  const [msgEtapa, setMsgEtapa] = useState<string | null>(null);
  // Anexo opcional do contrato de empreita — guardado na Pessoa (empreiteiro),
  // igual aos demais documentos dela (ver PessoaAnexo / categoria "Contrato de empreita").
  const [contratoAnexo, setContratoAnexo] = useState<File | null>(null);
  // G9 — exclusão do cabeçalho da empreita (motor genérico: admin exclui na
  // hora, operador só solicita). Erro (ex.: 400 de parcela já paga) fica
  // escopado ao item, exibido junto das etapas em renderItemExtra.
  const [excluindoId, setExcluindoId] = useState<number | null>(null);
  const [msgExclusao, setMsgExclusao] = useState<{ id: number; texto: string } | null>(null);

  const empreiteiros = useMemo(() => pessoas.filter((p) => p.tipos.includes("Empreiteiro")), [pessoas]);

  const carregar = () => fetchEmpreitadas().then(setItens).catch((e) => setError(e.message));
  useEffect(() => { carregar(); fetchPessoas().then(setPessoas).catch(() => {}); }, []);

  const dividirEtapasProporcionalmente = (valorTotal: number) => {
    const n = etapasForm.length || 1;
    const base = Math.floor((valorTotal / n) * 100) / 100;
    const resto = Math.round((valorTotal - base * n) * 100) / 100;
    setEtapasForm(etapasForm.map((e, i) => ({ ...e, valor: (i === n - 1 ? base + resto : base).toFixed(2) })));
  };

  async function concluirEtapa(empreitadaId: number, etapaId: number) {
    try {
      await concluirEtapaEmpreitada(empreitadaId, etapaId);
      carregar();
    } catch (e: any) {
      setMsgEtapa(e.message || "Erro ao concluir etapa");
    }
  }

  async function excluirEmpreitada(item: Empreitada) {
    const admin = ehAdmin();
    const msg = admin
      ? `Excluir a empreita de ${item.pessoa_nome} (${item.descricao})? Isso não pode ser desfeito.`
      : `Solicitar a exclusão da empreita de ${item.pessoa_nome} (${item.descricao})? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setMsgExclusao(null);
    setExcluindoId(item.id);
    try {
      const r = await confirmarExclusao("empreitada", String(item.id));
      if (r.status !== "excluido") {
        setMsgExclusao({ id: item.id, texto: "Solicitação de exclusão enviada — aguardando aprovação de um administrador." });
      }
      carregar();
    } catch (e: any) {
      setMsgExclusao({ id: item.id, texto: e.message || "Erro ao excluir empreita" });
    } finally {
      setExcluindoId(null);
    }
  }

  return (
    <CadastroAvulsoParceladoGenerico<Empreitada>
      mostrar={mostrar}
      itens={itens} error={error} recarregar={carregar}
      pessoas={empreiteiros} labelPessoa="Empreiteiro" placeholderDescricao="Ex.: Roçagem geral, construção de cerca…"
      msgSelecionePessoa="Selecione o empreiteiro." msgDescricaoObrigatoria="Informe a descrição da empreita."
      formasPagamento={FREQUENCIAS} formaPagamentoInicial="mensal"
      formasDataUnica={FORMAS_DATA_UNICA}
      textoDataUnica={(valor) => `Será lançada 1 conta no valor total (${formatBRL(valor)}), com vencimento na data acima — cai na Agenda e em Contas a Pagar.`}
      formasSemParcelamento={["por_etapa"]} formasSemCampoData={["por_etapa"]}
      validarExtra={({ formaPagamento }) =>
        formaPagamento === "por_etapa" && !etapasForm.some((e) => e.nome.trim() && e.valor)
          ? "Informe ao menos uma etapa com nome e valor." : null
      }
      resetExtra={() => { setEtapasForm(etapaFormVazia); setContratoAnexo(null); }}
      renderExtra={({ valorTotal }) => (
        <div className="mb-3">
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", marginBottom: "0.5rem" }}>
            O pagamento de cada etapa será lançado na Agenda e em Contas a Pagar para análise sempre no dia 1º do mês
            seguinte à conclusão da etapa. Divida o valor total proporcionalmente entre as etapas ou informe um valor
            específico para cada uma — tudo editável.
          </p>
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.8rem" }}>
              <thead><tr><th>Etapa</th><th>Valor (R$)</th><th></th></tr></thead>
              <tbody>
                {etapasForm.map((et, i) => (
                  <tr key={i}>
                    <td><input style={inputSm} value={et.nome} onChange={(e) => setEtapasForm(etapasForm.map((x, idx) => idx === i ? { ...x, nome: e.target.value } : x))} placeholder={`Etapa ${i + 1}`} /></td>
                    <td><CampoMoeda style={{ ...inputSm, width: "120px" }} value={Number(et.valor) || 0} onChange={(v) => setEtapasForm(etapasForm.map((x, idx) => idx === i ? { ...x, valor: v ? String(v) : "" } : x))} /></td>
                    <td><button type="button" className="btn-ghost" onClick={() => setEtapasForm(etapasForm.filter((_, idx) => idx !== i))}><Trash2 size={13} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-2" style={{ marginTop: "0.4rem" }}>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => setEtapasForm([...etapasForm, { nome: "", valor: "" }])}>
              <Plus size={13} /> Adicionar etapa
            </button>
            <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => dividirEtapasProporcionalmente(valorTotal)} disabled={!valorTotal}>
              Dividir proporcionalmente
            </button>
          </div>
          <div className="card" style={{ marginTop: "0.6rem", padding: "0.6rem 0.8rem" }}>
            <label style={{ fontSize: "0.78rem", display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}>
              <Upload size={13} style={{ flexShrink: 0, color: "var(--dourado-light)" }} />
              Anexar contrato de empreita (opcional)
              <input type="file" style={{ display: "none" }} onChange={(e) => setContratoAnexo(e.target.files?.[0] || null)} />
            </label>
            {contratoAnexo && (
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {contratoAnexo.name}{" "}
                <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setContratoAnexo(null)}>remover</button>
              </p>
            )}
            <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
              Salvo junto aos documentos do empreiteiro em Pessoas (categoria "Contrato de empreita").
            </p>
          </div>
        </div>
      )}
      tituloNovo="Nova empreita" descricaoNovo="Lançamento global (por frequência) ou por etapa" labelSalvar="Lançar empreita"
      salvar={async ({ pessoaId, descricao, valorTotal, formaPagamento, parcelasPayload, observacao }) => {
        await criarEmpreitada({
          pessoa_id: Number(pessoaId), descricao, valor_total: parseFloat(valorTotal),
          tipo_pagamento: formaPagamento, observacao: observacao || undefined,
          parcelas: formaPagamento === "por_etapa" ? undefined : parcelasPayload,
          etapas: formaPagamento === "por_etapa"
            ? etapasForm.filter((e) => e.nome.trim() && e.valor).map((e) => ({ nome: e.nome.trim(), valor: parseFloat(e.valor) || 0 }))
            : undefined,
        });
        if (contratoAnexo) {
          await anexarArquivoPessoa(Number(pessoaId), contratoAnexo, "Contrato de empreita");
        }
        return "Empreita lançada.";
      }}
      tituloVale="Vale de empreita" descricaoVale="Adiantamento abatido da próxima parcela/etapa pendente"
      valeOrigemTipo="empreitada" valeStatusExcluido="concluida"
      onEditarParcela={atualizarParcelaEmpreitada}
      onRedistribuirParcelas={redistribuirParcelasEmpreitada}
      tituloListagem="Empreitas lançadas" textoVazioListagem="Nenhuma empreita lançada ainda."
      statusLabel={(status) => (status === "concluida" ? "concluída" : "em andamento")}
      acaoItem={(item) => (
        <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} title="Excluir empreita"
          disabled={excluindoId === item.id} onClick={() => excluirEmpreitada(item)}>
          <Trash2 size={13} />
        </button>
      )}
      renderItemExtra={(item) => (
        <>
          {msgEtapa && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.5rem" }}>{msgEtapa}</p>}
          {msgExclusao?.id === item.id && <p style={{ color: "var(--red)", fontSize: "0.75rem", marginTop: "0.5rem" }}>{msgExclusao.texto}</p>}
          {item.etapas.length > 0 && (
            <table className="fazenda-table" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}>
              <thead><tr><th>Etapa</th><th>Valor</th><th>Situação</th><th></th></tr></thead>
              <tbody>
                {item.etapas.map((et) => (
                  <tr key={et.id}>
                    <td>{et.nome}</td>
                    <td>{formatBRL(et.valor)}</td>
                    <td>{et.concluida ? `concluída em ${et.data_conclusao} (${et.status_pagamento})` : "pendente"}</td>
                    <td>
                      {!et.concluida && (
                        <button className="btn-ghost" style={{ fontSize: "0.72rem", display: "flex", alignItems: "center", gap: "0.3rem" }} onClick={() => concluirEtapa(item.id, et.id)}>
                          <CheckCircle2 size={13} /> Concluir
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    />
  );
}
