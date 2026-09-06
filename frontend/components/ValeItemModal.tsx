"use client";
import { useEffect, useMemo, useState } from "react";
import { Check, X, Loader2, AlertTriangle } from "lucide-react";
import { fetchPessoas, fetchOpcoesValeItem, formatBRL, formatDate, type ValeItemOpcoes } from "@/lib/api";
import { Modal } from "@/components/Modal";
import { MobVoltar } from "@/components/mobile/ui";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };

/**
 * Dados de UM item marcado (ou a marcar) como vale — mistura o contrato de
 * `POST/DELETE /cadastro/vale-item/{id}` (pessoa_id, modo, parcelas,
 * competencia_inicio, origem_tipo/id, observacao, confirmar) com campos só
 * de UI (pessoa_nome, origem_label), usados no chip de resumo da linha do
 * item em FormFinanceiro.tsx — nunca vão no payload (ver montarPayload lá).
 */
export type ValeItemDados = {
  pessoa_id: number; pessoa_nome: string;
  modo: "folha" | "avulso";
  // Quanto DO ITEM é vale — "integral" (o item inteiro) ou "parcial", e aí
  // exatamente um entre `percentual` e `valor`. O caso que criou isto, na
  // palavra do dono: "2/3 do preço da ração de cachorro é do funcionário,
  // vale, e 1/3 eu que pago". A sobra vira despesa normal da fazenda — o
  // backend divide o item em duas linhas, com a mesma conta gerencial e o
  // mesmo centro de custo (ver rules/vale_item.py::dividir_item_de_lancamento).
  abrangencia?: "integral" | "parcial";
  percentual?: number; valor?: number;
  parcelas: number; competencia_inicio: string;
  origem_tipo?: "empreitada" | "contrato" | "diaria";
  origem_id?: number; origem_label?: string;
  observacao?: string; confirmar?: boolean;
};

type PessoaAtiva = { id: number; nome: string; tipos: string[]; ativo: boolean };

function formaValue(modo: "folha" | "avulso", origemTipo?: string | null, origemId?: number | null) {
  if (modo === "folha") return "folha";
  if (origemTipo && origemId != null) return `avulso:${origemTipo}:${origemId}`;
  return "";
}

/**
 * Modal (desktop) / tela cheia (mobile) para marcar um item de lançamento
 * financeiro como "vale de funcionário/empreiteiro/diarista" — só pede
 * beneficiário e forma de desconto; valor e data vêm do próprio item (ver
 * FormFinanceiro.tsx e app/financeiro/page.tsx::FormEditarLancamento).
 *
 * O componente NÃO chama a API sozinho: quem grava (criação de item novo,
 * que só manda tudo junto no `POST /financeiro/lancamentos`, ou marcação de
 * item já salvo, que chama `marcarItemComoVale`) é o `onConfirmar` do pai —
 * por isso ele pode ser síncrono OU assíncrono. Se `onConfirmar` rejeitar
 * com o 409 de "estourou 40% do salário" (`err.status === 409` e
 * `err.detail.competencias_excedidas`), o modal continua aberto mostrando a
 * mensagem e troca o botão para "Lançar mesmo assim" (reenvia com
 * `confirmar: true`) — mesmo padrão de FolhaPagamentoView.tsx.
 */
export default function ValeItemModal({
  apresentacao, valorItem, dataItem, produtoItem, inicial, onConfirmar, onCancelar,
}: {
  apresentacao: "modal" | "tela";
  valorItem: number;
  dataItem: string;
  produtoItem: string;
  inicial: ValeItemDados | null;
  onConfirmar: (d: ValeItemDados) => void | Promise<void>;
  onCancelar: () => void;
}) {
  const [pessoas, setPessoas] = useState<PessoaAtiva[]>([]);
  useEffect(() => {
    fetchPessoas().then((d: PessoaAtiva[]) => setPessoas((d || []).filter((p) => p.ativo))).catch(() => {});
  }, []);

  const [pessoaId, setPessoaId] = useState<number | null>(inicial?.pessoa_id ?? null);
  const [opcoes, setOpcoes] = useState<ValeItemOpcoes | null>(null);
  const [carregandoOpcoes, setCarregandoOpcoes] = useState(false);

  const [forma, setForma] = useState<string>(inicial ? formaValue(inicial.modo, inicial.origem_tipo, inicial.origem_id) : "");
  const [parcelas, setParcelas] = useState<string>(inicial?.modo === "folha" ? String(inicial.parcelas || 1) : "1");
  const [competenciaInicio, setCompetenciaInicio] = useState<string>(
    inicial?.modo === "folha" && inicial.competencia_inicio ? inicial.competencia_inicio : (dataItem || "").slice(0, 7),
  );
  const [observacao, setObservacao] = useState(inicial?.observacao || "");
  // Integral × parcial. O padrão é "integral" para a esmagadora maioria dos
  // itens continuar sendo um clique só — parcial é a exceção declarada.
  const [abrangencia, setAbrangencia] = useState<"integral" | "parcial">(inicial?.abrangencia || "integral");
  const [criterio, setCriterio] = useState<"percentual" | "valor">(inicial?.valor != null ? "valor" : "percentual");
  const [percentual, setPercentual] = useState<string>(inicial?.percentual != null ? String(inicial.percentual) : "");
  const [valorParcial, setValorParcial] = useState<string>(inicial?.valor != null ? String(inicial.valor) : "");

  // Prévia do rateio, calculada na tela com a MESMA conta do servidor
  // (`valor_vale_do_item`): sem ela o dono digita "66,67%" sem saber quanto
  // sobra para a fazenda, e é justamente a sobra que ele quer conferir.
  const previa = useMemo(() => {
    if (abrangencia === "integral") return null;
    const bruto = criterio === "percentual"
      ? (Number(percentual) > 0 ? Math.round(valorItem * Number(percentual)) / 100 : NaN)
      : Number(valorParcial);
    const doFuncionario = Math.round((bruto + Number.EPSILON) * 100) / 100;
    if (!Number.isFinite(doFuncionario) || doFuncionario <= 0 || doFuncionario >= valorItem) return null;
    return { doFuncionario, daFazenda: Math.round((valorItem - doFuncionario) * 100) / 100 };
  }, [abrangencia, criterio, percentual, valorParcial, valorItem]);

  const [erro, setErro] = useState<string | null>(null);
  const [erro409, setErro409] = useState<{ mensagem: string; competencias_excedidas: { competencia: string; total: number }[] } | null>(null);
  const [confirmando, setConfirmando] = useState(false);

  // Ao trocar de pessoa (inclusive na 1ª carga, se `inicial` já traz uma),
  // busca as origens disponíveis dela — spinner + Confirmar desabilitado
  // enquanto carrega (ver `confirmarDesabilitado` abaixo).
  useEffect(() => {
    if (!pessoaId) { setOpcoes(null); return; }
    setCarregandoOpcoes(true); setOpcoes(null); setErro(null); setErro409(null);
    fetchOpcoesValeItem(pessoaId)
      .then((d) => setOpcoes(d))
      .catch((e: any) => setErro(e.message || "Erro ao buscar opções de vale"))
      .finally(() => setCarregandoOpcoes(false));
  }, [pessoaId]);

  const pessoaSelecionada = useMemo(() => pessoas.find((p) => p.id === pessoaId) || null, [pessoas, pessoaId]);

  const formaOpcoes = useMemo(() => {
    const lista: { value: string; label: string }[] = [];
    if (opcoes?.folha.disponivel) lista.push({ value: "folha", label: "Descontar da folha de pagamento" });
    (opcoes?.origens || []).forEach((o) => {
      lista.push({
        value: `avulso:${o.origem_tipo}:${o.origem_id}`,
        label: `Abater de ${o.label}${o.saldo_pendente != null ? ` (saldo ${formatBRL(o.saldo_pendente)})` : ""}`,
      });
    });
    return lista;
  }, [opcoes]);

  // Auto-seleção pedida: 1 única opção vira texto estático (força `forma`
  // pra ela sempre); com mais de uma, só pré-marca a sugestão do backend na
  // 1ª vez que as opções desta pessoa chegam (nunca sobrescreve escolha já
  // feita pelo usuário nem a marcação vinda de `inicial`).
  useEffect(() => {
    if (!opcoes) return;
    if (formaOpcoes.length === 1) { setForma(formaOpcoes[0].value); return; }
    if (!forma && opcoes.sugestao) {
      const v = formaValue(opcoes.sugestao.modo, opcoes.sugestao.origem_tipo, opcoes.sugestao.origem_id);
      if (v) setForma(v);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opcoes, formaOpcoes]);

  const modo: "folha" | "avulso" = forma === "folha" ? "folha" : "avulso";

  async function confirmarClick(forcar: boolean) {
    setErro(null);
    if (!pessoaId || !pessoaSelecionada) { setErro("Selecione o beneficiário."); return; }
    if (!opcoes || opcoes.bloqueio) return;
    if (!forma) { setErro("Selecione a forma de desconto."); return; }
    if (forma === "folha" && (!parcelas || Number(parcelas) < 1)) { setErro("Informe ao menos 1 parcela."); return; }
    if (abrangencia === "parcial" && !previa) {
      setErro(
        criterio === "percentual"
          ? "Informe um percentual entre 0 e 100 (100% é vale integral)."
          : `Informe um valor maior que zero e menor que ${formatBRL(valorItem)} (o item inteiro é vale integral).`,
      );
      return;
    }

    const origemEscolhida = forma !== "folha" ? forma.split(":") : null;
    const formaLabel = formaOpcoes.find((o) => o.value === forma)?.label;
    const dados: ValeItemDados = {
      pessoa_id: pessoaId, pessoa_nome: pessoaSelecionada.nome,
      modo,
      abrangencia,
      // Só o critério escolhido vai no payload: o servidor recusa (400) se os
      // dois vierem juntos, porque não há desempate que não fosse chute.
      percentual: abrangencia === "parcial" && criterio === "percentual" ? Number(percentual) : undefined,
      valor: abrangencia === "parcial" && criterio === "valor" ? Number(valorParcial) : undefined,
      parcelas: modo === "folha" ? Number(parcelas) || 1 : 1,
      competencia_inicio: modo === "folha" ? (competenciaInicio || (dataItem || "").slice(0, 7)) : "",
      origem_tipo: origemEscolhida ? (origemEscolhida[1] as ValeItemDados["origem_tipo"]) : undefined,
      origem_id: origemEscolhida ? Number(origemEscolhida[2]) : undefined,
      origem_label: modo === "avulso" ? (formaLabel || "").replace(/^Abater de /, "") : undefined,
      observacao: observacao.trim() || undefined,
      confirmar: forcar || undefined,
    };
    setConfirmando(true);
    try {
      await onConfirmar(dados);
      setErro409(null);
    } catch (e: any) {
      if (e?.status === 409 && e?.detail?.competencias_excedidas) {
        setErro409({ mensagem: e.detail.mensagem, competencias_excedidas: e.detail.competencias_excedidas || [] });
      } else {
        setErro(e?.message || "Erro ao salvar o vale");
      }
    } finally {
      setConfirmando(false);
    }
  }

  const confirmarDesabilitado =
    confirmando || !pessoaId || carregandoOpcoes || !opcoes || !!opcoes.bloqueio ||
    formaOpcoes.length === 0 || (formaOpcoes.length > 1 && !forma);

  const conteudo = (
    <div className="space-y-3">
      <div>
        <p style={{ fontSize: "0.9rem", fontWeight: 700 }}>
          {produtoItem} — {formatBRL(valorItem)} — {dataItem ? formatDate(dataItem) : "—"}
        </p>
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
          O valor e a data vêm do item da nota. O dinheiro já saiu na compra; isto só reclassifica o gasto
          como adiantamento a receber da pessoa.
        </p>
      </div>

      <div>
        <label style={lbl}>Beneficiário</label>
        <select style={inputStyle} value={pessoaId ?? ""} onChange={(e) => {
          const v = e.target.value ? Number(e.target.value) : null;
          setPessoaId(v); setForma(""); setErro(null); setErro409(null);
        }}>
          <option value="">Selecione…</option>
          {pessoas.map((p) => <option key={p.id} value={p.id}>{p.nome} — {(p.tipos || []).join("/")}</option>)}
        </select>
      </div>

      {carregandoOpcoes && (
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <Loader2 size={14} className="animate-spin" /> Carregando opções…
        </p>
      )}

      {opcoes && opcoes.bloqueio && (
        <div>
          <div style={{ fontSize: "0.82rem", color: "var(--red)", background: "rgba(190,40,40,0.1)", border: "1px solid var(--red)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.75rem" }}>
            <AlertTriangle size={14} style={{ display: "inline", marginRight: "0.3rem", verticalAlign: "-2px" }} />
            {opcoes.bloqueio}
          </div>
          <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem", marginTop: "0.5rem" }}
            onClick={() => { setPessoaId(null); setOpcoes(null); }}>
            Escolher outra pessoa
          </button>
        </div>
      )}

      {opcoes && !opcoes.bloqueio && (
        <>
          <div>
            <label style={lbl}>Forma de desconto</label>
            {formaOpcoes.length === 1 ? (
              <p style={{ ...inputStyle, background: "transparent", border: "1px dashed var(--border)" }}>{formaOpcoes[0].label}</p>
            ) : (
              <select style={inputStyle} value={forma} onChange={(e) => setForma(e.target.value)}>
                <option value="">Selecione…</option>
                {formaOpcoes.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            )}
          </div>

          <div>
            <label style={lbl}>Quanto deste item é vale?</label>
            <div className="flex items-center gap-4" style={{ fontSize: "0.82rem" }}>
              <label className="flex items-center gap-1">
                <input type="radio" checked={abrangencia === "integral"} onChange={() => setAbrangencia("integral")} />
                Integral ({formatBRL(valorItem)})
              </label>
              <label className="flex items-center gap-1">
                <input type="radio" checked={abrangencia === "parcial"} onChange={() => setAbrangencia("parcial")} />
                Parcial
              </label>
            </div>
          </div>

          {abrangencia === "parcial" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label style={lbl}>Informar por</label>
                <select style={inputStyle} value={criterio} onChange={(e) => setCriterio(e.target.value as "percentual" | "valor")}>
                  <option value="percentual">Percentual do item</option>
                  <option value="valor">Valor em reais</option>
                </select>
              </div>
              <div>
                <label style={lbl}>{criterio === "percentual" ? "% do funcionário" : "R$ do funcionário"}</label>
                {criterio === "percentual" ? (
                  <input type="number" min={0} max={100} step="0.01" style={inputStyle}
                    value={percentual} onChange={(e) => setPercentual(e.target.value)} />
                ) : (
                  <input type="number" min={0} step="0.01" style={inputStyle}
                    value={valorParcial} onChange={(e) => setValorParcial(e.target.value)} />
                )}
              </div>
              <p style={{ gridColumn: "1 / -1", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                {previa
                  ? `Vale do funcionário: ${formatBRL(previa.doFuncionario)} · Despesa da fazenda: ${formatBRL(previa.daFazenda)} (mesma conta gerencial e centro de custo do item).`
                  : "O restante vira despesa normal da fazenda, na mesma conta gerencial e no mesmo centro de custo do item."}
              </p>
            </div>
          )}

          {forma === "folha" && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label style={lbl}>Nº de parcelas na folha</label>
                <input type="number" min={1} style={inputStyle} value={parcelas} onChange={(e) => setParcelas(e.target.value)} />
              </div>
              <div>
                <label style={lbl}>Competência inicial</label>
                <input type="month" style={inputStyle} value={competenciaInicio} onChange={(e) => setCompetenciaInicio(e.target.value)} />
              </div>
              {opcoes.folha.limite_por_competencia != null && (
                <p style={{ gridColumn: "1 / -1", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                  Limite de 40% do salário: {formatBRL(opcoes.folha.limite_por_competencia)}
                </p>
              )}
            </div>
          )}

          <div>
            <label style={lbl}>Observação (opcional)</label>
            <textarea style={{ ...inputStyle, minHeight: "3.5rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} />
          </div>
        </>
      )}

      {erro409 && (
        <div style={{ fontSize: "0.8rem", color: "var(--amber)", background: "rgba(217,119,6,0.1)", border: "1px solid var(--amber)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.75rem" }}>
          <AlertTriangle size={14} style={{ display: "inline", marginRight: "0.3rem", verticalAlign: "-2px" }} />
          {erro409.mensagem}
          {erro409.competencias_excedidas.length > 0 && (
            <> — {erro409.competencias_excedidas.map((c) => `${c.competencia} (${formatBRL(c.total)})`).join(", ")}</>
          )}
        </div>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem" }}>{erro}</p>}

      <div className="flex items-center gap-3 mt-2">
        <button type="button" className="btn-primary" disabled={confirmarDesabilitado}
          onClick={() => confirmarClick(!!erro409)}>
          <Check size={14} /> {confirmando ? "Salvando…" : erro409 ? "Lançar mesmo assim" : "Confirmar"}
        </button>
        <button type="button" className="btn-ghost" onClick={onCancelar}><X size={14} /> Cancelar</button>
      </div>
    </div>
  );

  if (apresentacao === "tela") {
    return (
      <div>
        <MobVoltar titulo="Vale de funcionário" onVoltar={onCancelar} />
        {conteudo}
      </div>
    );
  }

  return (
    <Modal title="Vale de funcionário" onClose={onCancelar} width="560px">
      {conteudo}
    </Modal>
  );
}
