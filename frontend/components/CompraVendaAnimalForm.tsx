"use client";
import { useEffect, useMemo, useState } from "react";
import { ShoppingCart, Tag, Check, AlertTriangle } from "lucide-react";
import {
  fetchFornecedores, fetchPlanoContas, fetchOpcoesFinanceiro, fetchMotivosVenda,
  criarCompraAnimal, criarVendaAnimal, fetchComprasAnimais, fetchVendasAnimais,
  ehAdmin, formatBRL,
} from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
import type { ContaPlano } from "@/lib/contaGerencial";
import { SeletorContaGerencial } from "./SeletorContaGerencial";
import { AnimalPickerModal } from "./AnimalPickerModal";
import type { AnimalRow } from "./AnimalModal";
import ComissaoCorretagemForm from "./ComissaoCorretagemForm";
import { ParcelasEditor, CampoQtdParcelas, dividirParcelas, type Parcela } from "./ParcelasEditor";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
const hoje = () => new Date().toISOString().split("T")[0];

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>;
}

// Ramos do plano de contas onde a compra/venda de animal deve ser lançada —
// mesmos prefixos usados no backend para validar (aqui só restringe a árvore
// mostrada no seletor).
const PREFIXOS_COMPRA = ["3.10.06", "3.10.07"];
const PREFIXOS_VENDA = ["2.01.02"];

type Fornecedor = { id: number; nome: string; tipo: string; ativo: boolean };
type Registro = {
  id: number; numero_animal: string; valor: number; tipo_valor: string;
  numero_lancamento_gerado: string | null; usuario_nome?: string | null;
  vendedor?: string; comprador?: string; data_compra?: string; data_venda?: string;
  gta?: string | null;
};

export default function CompraVendaAnimalForm({ modo, animais }: { modo: "compra" | "venda"; animais: AnimalRow[] }) {
  const ehCompra = modo === "compra";
  const tipoFinanceiro: "despesa" | "receita" = ehCompra ? "despesa" : "receita";
  const prefixosConta = ehCompra ? PREFIXOS_COMPRA : PREFIXOS_VENDA;
  const rotuloContraparte = ehCompra ? "Vendedor" : "Comprador";

  const [animaisSel, setAnimaisSel] = useState<Set<string>>(new Set());
  const toggleAnimal = (numero: string) => setAnimaisSel((prev) => {
    const novo = new Set(prev); if (novo.has(numero)) novo.delete(numero); else novo.add(numero); return novo;
  });
  const animaisEscolhidos = useMemo(() => animais.filter((a) => animaisSel.has(a.numero)), [animais, animaisSel]);
  const quantidade = animaisSel.size;

  const [contraparte, setContraparte] = useState("");
  const [data, setData] = useState(hoje());
  const [valor, setValor] = useState("");
  const [tipoValor, setTipoValor] = useState("por_animal");
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");

  // Motivo(s)/categoria(s) — só na venda.
  const [motivosVenda, setMotivosVenda] = useState<{ id: number; nome: string; ativo: boolean }[]>([]);
  const [motivoVenda, setMotivoVenda] = useState("");
  const categoriasDisponiveis = useMemo(
    () => Array.from(new Set(animaisEscolhidos.map((a) => a.categoria_abrev || a.categoria_completa).filter(Boolean) as string[])),
    [animaisEscolhidos]
  );
  const [categoriasSel, setCategoriasSel] = useState<Set<string>>(new Set());
  // Ao mudar a seleção de animais, todas as categorias presentes nascem
  // marcadas por padrão (o usuário desmarca a que não quiser na nota).
  useEffect(() => {
    setCategoriasSel(new Set(categoriasDisponiveis));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoriasDisponiveis.join("|")]);

  // Conta gerencial (restrita) + centro de custo + demais dados da nota.
  const [planoContas, setPlanoContas] = useState<ContaPlano[]>([]);
  const [opcoes, setOpcoes] = useState<{ centros_custo: string[]; contas_bancarias: string[]; tipos_documento: string[] }>({ centros_custo: [], contas_bancarias: [], tipos_documento: [] });
  const [codigoConta, setCodigoConta] = useState("");
  const [nomeConta, setNomeConta] = useState("");
  const [descricao, setDescricao] = useState("");
  const [centroCusto, setCentroCusto] = useState("");
  const [tipoDocumento, setTipoDocumento] = useState("");
  const [numeroDocumento, setNumeroDocumento] = useState("");
  const [dataEmissao, setDataEmissao] = useState("");
  const [dataVencimento, setDataVencimento] = useState("");
  const [dataPrevista, setDataPrevista] = useState(""); // entrada (compra) ou saída (venda)
  const [dataPedido, setDataPedido] = useState("");
  const [entregue, setEntregue] = useState(false);
  const [desconto, setDesconto] = useState("");
  const [acrescimo, setAcrescimo] = useState("");

  const [parcelado, setParcelado] = useState(false);
  const [qtdParcelas, setQtdParcelas] = useState("2");
  const [parcelas, setParcelas] = useState<Parcela[]>([]);

  const [jaPago, setJaPago] = useState(false);
  const [dataPagamento, setDataPagamento] = useState("");
  const [valorPago, setValorPago] = useState("");
  const [contaBancaria, setContaBancaria] = useState("");
  const [numeroDocumentoPagamento, setNumeroDocumentoPagamento] = useState("");

  const [gta, setGta] = useState("");
  const [icmsIncide, setIcmsIncide] = useState(false);
  const [icmsTipo, setIcmsTipo] = useState("");
  const [icmsValor, setIcmsValor] = useState("");

  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [pagarComissao, setPagarComissao] = useState(false);
  const [corretorNome, setCorretorNome] = useState("");
  const [valorComissao, setValorComissao] = useState("");
  const [formaComissao, setFormaComissao] = useState("redirecionado");
  const [dataVencimentoComissao, setDataVencimentoComissao] = useState("");
  const [parcelarComissao, setParcelarComissao] = useState(false);
  const [parcelasComissao, setParcelasComissao] = useState<Parcela[]>([]);
  const corretores = useMemo(() => fornecedores.filter((f) => f.tipo === "corretor" && f.ativo).map((f) => f.nome), [fornecedores]);
  const contrapartes = useMemo(() => {
    const tiposOk = ehCompra ? (t: string) => t !== "corretor" : (t: string) => t === "cliente";
    return fornecedores.filter((f) => tiposOk(f.tipo) && f.ativo).map((f) => f.nome).sort((a, b) => a.localeCompare(b));
  }, [fornecedores, ehCompra]);

  const [historico, setHistorico] = useState<Registro[] | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "erro" | "sucesso"; texto: string } | null>(null);
  const admin = ehAdmin();

  const ordHistorico = useOrdenacao(historico ?? []);

  const carregar = () => {
    fetchFornecedores().then(setFornecedores).catch(() => {});
    fetchPlanoContas().then(setPlanoContas).catch(() => {});
    fetchOpcoesFinanceiro().then(setOpcoes).catch(() => {});
    if (!ehCompra) fetchMotivosVenda().then(setMotivosVenda).catch(() => {});
    (ehCompra ? fetchComprasAnimais() : fetchVendasAnimais()).then(setHistorico).catch(() => {});
  };
  useEffect(carregar, [ehCompra]);

  const valorNum = Number(valor) || 0;
  const valorUnitario = tipoValor === "por_animal" ? valorNum : (quantidade ? valorNum / quantidade : 0);
  const valorTotalBruto = tipoValor === "total" ? valorNum : valorNum * quantidade;
  const valorLiquido = Math.round((valorTotalBruto - (Number(desconto) || 0) + (Number(acrescimo) || 0)) * 100) / 100;

  // Regenera as parcelas (divisão igual) quando ligar o parcelamento ou mudar quantidade.
  useEffect(() => {
    if (!parcelado) { setParcelas([]); return; }
    const n = Math.max(1, Math.round(Number(qtdParcelas) || 0));
    setParcelas(dividirParcelas(valorLiquido, n, dataPrevista || dataEmissao));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parcelado, qtdParcelas]);

  const limpar = () => {
    setAnimaisSel(new Set()); setContraparte(""); setValor(""); setTipoValor("por_animal");
    setObservacao(""); setMotivoVenda(""); setCategoriasSel(new Set());
    setCodigoConta(""); setNomeConta(""); setDescricao(""); setCentroCusto(""); setTipoDocumento("");
    setNumeroDocumento(""); setDataEmissao(""); setDataVencimento(""); setDataPrevista(""); setDataPedido("");
    setEntregue(false); setDesconto(""); setAcrescimo(""); setParcelado(false); setQtdParcelas("2"); setParcelas([]);
    setJaPago(false); setDataPagamento(""); setValorPago(""); setContaBancaria(""); setNumeroDocumentoPagamento("");
    setGta(""); setIcmsIncide(false); setIcmsTipo(""); setIcmsValor("");
    setPagarComissao(false); setCorretorNome(""); setValorComissao(""); setFormaComissao("redirecionado");
    setDataVencimentoComissao(""); setParcelarComissao(false); setParcelasComissao([]);
  };

  const salvar = async () => {
    setMsg(null);
    if (!animaisSel.size) { setMsg({ tipo: "erro", texto: "Informe ao menos um animal." }); return; }
    if (!contraparte.trim()) { setMsg({ tipo: "erro", texto: `Informe o ${rotuloContraparte.toLowerCase()}.` }); return; }
    if (!valor) { setMsg({ tipo: "erro", texto: `Informe o valor da ${ehCompra ? "compra" : "venda"}.` }); return; }
    if (!codigoConta) { setMsg({ tipo: "erro", texto: "Selecione a conta gerencial." }); return; }
    if (icmsIncide && !icmsTipo) { setMsg({ tipo: "erro", texto: "Informe se o ICMS é intermunicipal ou interestadual." }); return; }
    if (pagarComissao && (!corretorNome.trim() || !valorComissao)) {
      setMsg({ tipo: "erro", texto: "Informe o corretor e o valor da comissão." }); return;
    }

    const camposComuns = {
      codigo_conta_gerencial: codigoConta,
      descricao: descricao || undefined,
      centro_custo: centroCusto || undefined,
      tipo_documento: tipoDocumento || undefined,
      numero_documento: numeroDocumento || undefined,
      data_emissao: dataEmissao || undefined,
      data_vencimento: !parcelado ? (dataVencimento || undefined) : undefined,
      data_pedido: dataPedido || undefined,
      entregue,
      desconto: Number(desconto) || 0,
      acrescimo: Number(acrescimo) || 0,
      parcelas: parcelado ? parcelas.map((p) => ({ data_vencimento: p.data_vencimento, valor: Number(p.valor) || 0 })) : [],
      data_pagamento: !parcelado && jaPago ? dataPagamento || undefined : undefined,
      valor_pago: !parcelado && jaPago ? Number(valorPago) || 0 : undefined,
      conta_bancaria: !parcelado && jaPago ? contaBancaria || undefined : undefined,
      numero_documento_pagamento: !parcelado && jaPago ? numeroDocumentoPagamento || undefined : undefined,
      gta: gta || undefined,
      icms_incide: icmsIncide,
      icms_tipo: icmsIncide ? icmsTipo : undefined,
      icms_valor: icmsIncide ? Number(icmsValor) || undefined : undefined,
      pagar_comissao: pagarComissao,
      corretor_nome: pagarComissao ? corretorNome.trim() : undefined,
      valor_comissao: pagarComissao ? Number(valorComissao) : undefined,
      forma_comissao: pagarComissao ? formaComissao : undefined,
      data_vencimento_comissao: pagarComissao && formaComissao === "separado" && !parcelarComissao ? dataVencimentoComissao || undefined : undefined,
      parcelas_comissao: pagarComissao && formaComissao === "separado" && parcelarComissao
        ? parcelasComissao.map((p) => ({ data_vencimento: p.data_vencimento, valor: Number(p.valor) || 0 })) : [],
    };

    setSalvando(true);
    try {
      const r = ehCompra
        ? await criarCompraAnimal({
            ...camposComuns, animais: Array.from(animaisSel), vendedor: contraparte.trim(),
            valor: valorNum, tipo_valor: tipoValor, data_compra: data,
            observacao: observacao || undefined, responsavel: responsavel || undefined,
            data_prevista_entrada: dataPrevista || undefined,
          })
        : await criarVendaAnimal({
            ...camposComuns, animais: Array.from(animaisSel), comprador: contraparte.trim(),
            valor: valorNum, tipo_valor: tipoValor, data_venda: data,
            observacao: observacao || undefined, responsavel: responsavel || undefined,
            categorias: Array.from(categoriasSel), motivo_venda: motivoVenda || undefined,
            data_prevista_saida: dataPrevista || undefined,
          });
      const n = ehCompra ? (r as any).comprados : (r as any).vendidos;
      setMsg({ tipo: "sucesso", texto: `${n} animal(is) registrado(s) como ${ehCompra ? "comprado(s)" : "vendido(s)"}.` });
      limpar();
      carregar();
    } catch (e: any) {
      setMsg({ tipo: "erro", texto: e.message || `Erro ao registrar ${ehCompra ? "compra" : "venda"}` });
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div className="animate-in">
      <div className="card mb-4">
        <div className="mb-3">
          <label style={lbl}>Número(s) do(s) animal(is)</label>
          <AnimalPickerModal
            animais={animais}
            selecionados={animaisSel}
            onToggle={toggleAnimal}
            titulo={`Escolher animais para ${ehCompra ? "comprar" : "vender"}`}
            placeholder="Selecionar animais…"
            permitirNovoAnimal={ehCompra}
            colunas={[
              { header: "Nº", render: (a) => a.numero },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
              { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
            ]}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <Campo label={`${rotuloContraparte} (fornecedor)`}>
            <select style={inputStyle} value={contraparte} onChange={(e) => setContraparte(e.target.value)}>
              <option value="">Selecione…</option>
              {contrapartes.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
            {!contrapartes.length && <p style={{ fontSize: "0.7rem", color: "var(--amber)", marginTop: "0.2rem" }}>
              Cadastre {ehCompra ? "fornecedores" : "clientes"} em Configurações → Cadastro → Pessoas/Fornecedores.
            </p>}
          </Campo>
          <Campo label={`Data da ${ehCompra ? "compra" : "venda"}`}>
            <input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} />
          </Campo>
          <Campo label="GTA (Guia de Trânsito Animal)">
            <input style={inputStyle} value={gta} onChange={(e) => setGta(e.target.value)} placeholder="nº da GTA" />
          </Campo>
        </div>

        <div className="mb-1" style={{ maxWidth: "480px" }}>
          <label style={lbl}>O valor informado é...</label>
          <div className="flex gap-4 mt-1" style={{ fontSize: "0.82rem" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
              <input type="radio" name={`tipo_valor_${modo}`} checked={tipoValor === "por_animal"} onChange={() => setTipoValor("por_animal")} />
              Por animal
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
              <input type="radio" name={`tipo_valor_${modo}`} checked={tipoValor === "total"} onChange={() => setTipoValor("total")} />
              Total ({quantidade || 0} animal(is))
            </label>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 mb-2" style={{ maxWidth: "480px" }}>
          <Campo label={tipoValor === "total" ? "Valor total (R$)" : "Valor por animal (R$)"}>
            <input type="number" step="0.01" style={inputStyle} value={valor} onChange={(e) => setValor(e.target.value)} />
          </Campo>
        </div>
        {!!quantidade && !!valorNum && (
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
            Resumo: <strong style={{ color: "var(--text)" }}>{quantidade}</strong> animal(is) × {formatBRL(valorUnitario)} =
            {" "}<strong style={{ color: "var(--dourado-light)" }}>{formatBRL(valorLiquido)}</strong>
            {(Number(desconto) > 0 || Number(acrescimo) > 0) && " (já com desconto/acréscimo)"}
          </p>
        )}

        {!ehCompra && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <Campo label="Motivo da venda">
              <select style={inputStyle} value={motivoVenda} onChange={(e) => setMotivoVenda(e.target.value)}>
                <option value="">Selecione…</option>
                {motivosVenda.filter((m) => m.ativo).map((m) => <option key={m.id} value={m.nome}>{m.nome}</option>)}
              </select>
              <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                Lista editável em Configurações → Parâmetros → Parâmetros gerais.
              </p>
            </Campo>
            {!!categoriasDisponiveis.length && (
              <Campo label="Categoria(s) vendida(s) nesta nota">
                <div className="flex items-center gap-3" style={{ flexWrap: "wrap", marginTop: "0.2rem" }}>
                  {categoriasDisponiveis.map((c) => (
                    <label key={c} style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.8rem", cursor: "pointer" }}>
                      <input type="checkbox" checked={categoriasSel.has(c)} onChange={() => setCategoriasSel((prev) => {
                        const novo = new Set(prev); if (novo.has(c)) novo.delete(c); else novo.add(c); return novo;
                      })} /> {c}
                    </label>
                  ))}
                </div>
                <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                  Pode misturar mais de uma categoria na mesma nota (ex.: descarte + touro).
                </p>
              </Campo>
            )}
          </div>
        )}

        <Campo label="Conta gerencial" full>
          <SeletorContaGerencial
            contas={planoContas}
            tipo={tipoFinanceiro}
            prefixosPermitidos={prefixosConta}
            codigo={codigoConta}
            nome={nomeConta}
            onSelect={(codigo, nome) => { setCodigoConta(codigo); setNomeConta(nome); }}
            placeholder={ehCompra ? "Compra de animal (3.10.06/3.10.07)…" : "Venda de animal (2.01.02)…"}
          />
        </Campo>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3 mb-3">
          <Campo label="Descrição (opcional)"><input style={inputStyle} value={descricao} onChange={(e) => setDescricao(e.target.value)} /></Campo>
          <Campo label="Centro de custo">
            <select style={inputStyle} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
              <option value="">Selecione…</option>
              {opcoes.centros_custo.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Campo>
          <Campo label="Responsável pelo lançamento">
            <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
              <option value="">Selecione...</option>
              {RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </Campo>
          <Campo label="Tipo de documento">
            <select style={inputStyle} value={tipoDocumento} onChange={(e) => setTipoDocumento(e.target.value)}>
              <option value="">Selecione…</option>
              {(opcoes.tipos_documento.length ? opcoes.tipos_documento : ["Nota fiscal", "Recibo", "Contrato"]).map((t) => <option key={t}>{t}</option>)}
            </select>
          </Campo>
          <Campo label="Número do documento"><input style={inputStyle} value={numeroDocumento} onChange={(e) => setNumeroDocumento(e.target.value)} /></Campo>
          <Campo label="Data de emissão"><input type="date" style={inputStyle} value={dataEmissao} onChange={(e) => setDataEmissao(e.target.value)} /></Campo>
          {!parcelado && (
            <Campo label="Data de vencimento">
              <input type="date" style={inputStyle} value={dataVencimento} onChange={(e) => setDataVencimento(e.target.value)} />
            </Campo>
          )}
          <Campo label={`Data prevista de ${ehCompra ? "entrada" : "saída"}`}>
            <input type="date" style={inputStyle} value={dataPrevista} onChange={(e) => setDataPrevista(e.target.value)} />
          </Campo>
          <Campo label="Data do pedido"><input type="date" style={inputStyle} value={dataPedido} onChange={(e) => setDataPedido(e.target.value)} /></Campo>
          <Campo label={`Já ${ehCompra ? "entregue" : "recebido"}?`}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.82rem", marginTop: "0.4rem" }}>
              <input type="checkbox" checked={entregue} onChange={(e) => setEntregue(e.target.checked)} /> Sim
            </label>
          </Campo>
          <Campo label="Desconto (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={desconto} onChange={(e) => setDesconto(e.target.value)} placeholder="0,00" /></Campo>
          <Campo label="Acréscimo (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={acrescimo} onChange={(e) => setAcrescimo(e.target.value)} placeholder="0,00" /></Campo>
        </div>

        {/* ICMS */}
        <div className="card mb-3" style={{ background: "var(--surface-2)" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
            <input type="checkbox" checked={icmsIncide} onChange={(e) => setIcmsIncide(e.target.checked)} /> Há incidência de ICMS?
          </label>
          {icmsIncide && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
              <div>
                <label style={lbl}>Tipo de operação</label>
                <div className="flex gap-4 mt-1" style={{ fontSize: "0.82rem" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
                    <input type="radio" name={`icms_tipo_${modo}`} checked={icmsTipo === "intermunicipal"} onChange={() => setIcmsTipo("intermunicipal")} /> Intermunicipal
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", cursor: "pointer" }}>
                    <input type="radio" name={`icms_tipo_${modo}`} checked={icmsTipo === "interestadual"} onChange={() => setIcmsTipo("interestadual")} /> Interestadual
                  </label>
                </div>
                <p style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  <AlertTriangle size={11} style={{ display: "inline", marginRight: "0.2rem" }} />
                  Há várias isenções para operações intermunicipais — confirme com a contabilidade antes de recolher.
                </p>
              </div>
              <Campo label="Valor do ICMS (R$)"><input type="number" step="0.01" style={inputStyle} value={icmsValor} onChange={(e) => setIcmsValor(e.target.value)} /></Campo>
            </div>
          )}
        </div>

        <ComissaoCorretagemForm
          pagarComissao={pagarComissao} setPagarComissao={setPagarComissao}
          corretorNome={corretorNome} setCorretorNome={setCorretorNome}
          valorComissao={valorComissao} setValorComissao={setValorComissao}
          formaComissao={formaComissao} setFormaComissao={setFormaComissao}
          corretores={corretores}
          dataVencimentoComissao={dataVencimentoComissao} setDataVencimentoComissao={setDataVencimentoComissao}
          parcelarComissao={parcelarComissao} setParcelarComissao={setParcelarComissao}
          parcelasComissao={parcelasComissao} setParcelasComissao={setParcelasComissao}
        />

        {/* Parcelamento da compra/venda */}
        <div className="card mb-3" style={{ background: "var(--surface-2)" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
            <input type="checkbox" checked={parcelado} onChange={(e) => setParcelado(e.target.checked)} /> Lançamento parcelado
          </label>
          {parcelado && (
            <div style={{ marginTop: "0.6rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <CampoQtdParcelas qtd={qtdParcelas} setQtd={setQtdParcelas} />
              <ParcelasEditor parcelas={parcelas} setParcelas={setParcelas} valorReferencia={valorLiquido} tituloContaA={ehCompra ? "pagar" : "receber"} />
            </div>
          )}
        </div>

        {/* Pagamento imediato (só para lançamento não parcelado) */}
        {!parcelado && (
          <div className="card mb-3" style={{ background: "var(--surface-2)" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem", fontWeight: 600 }}>
              <input type="checkbox" checked={jaPago} onChange={(e) => setJaPago(e.target.checked)} /> Já foi {ehCompra ? "pago" : "recebido"}
            </label>
            {jaPago && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
                <Campo label="Data de pagamento"><input type="date" style={inputStyle} value={dataPagamento} onChange={(e) => setDataPagamento(e.target.value)} /></Campo>
                <Campo label="Valor pago (R$)"><input type="number" inputMode="decimal" style={inputStyle} value={valorPago} onChange={(e) => setValorPago(e.target.value)} /></Campo>
                <Campo label="Conta bancária">
                  <select style={inputStyle} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
                    <option value="">Selecione…</option>
                    {opcoes.contas_bancarias.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </Campo>
                <Campo label="Número do documento de pagamento"><input style={inputStyle} value={numeroDocumentoPagamento} onChange={(e) => setNumeroDocumentoPagamento(e.target.value)} /></Campo>
              </div>
            )}
          </div>
        )}

        <Campo label="Observação (opcional)" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>

        {msg && (
          <p style={{ color: msg.tipo === "erro" ? "var(--red)" : "var(--green-light)", fontSize: "0.85rem", margin: "0.75rem 0" }}>{msg.texto}</p>
        )}
        <button className="btn-primary mt-3" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }} onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : `Registrar ${ehCompra ? "compra" : "venda"} de ${quantidade || ""} animal(is)`}
        </button>
      </div>

      {historico && historico.length > 0 && (
        <div className="card">
          <div className="card-header mb-3">{ehCompra ? "Compras" : "Vendas"} registradas</div>
          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr>
                <ThOrdenavel label="Nº" campo="numero_animal" coluna={ordHistorico.coluna} dir={ordHistorico.dir} ordenar={ordHistorico.ordenar} />
                <ThOrdenavel label={rotuloContraparte} campo={ehCompra ? "vendedor" : "comprador"} coluna={ordHistorico.coluna} dir={ordHistorico.dir} ordenar={ordHistorico.ordenar} />
                <ThOrdenavel label="Data" campo={ehCompra ? "data_compra" : "data_venda"} coluna={ordHistorico.coluna} dir={ordHistorico.dir} ordenar={ordHistorico.ordenar} />
                <ThOrdenavel label="Valor (por animal)" campo="valor" coluna={ordHistorico.coluna} dir={ordHistorico.dir} ordenar={ordHistorico.ordenar} alinhar="right" />
                <ThOrdenavel label="GTA" campo="gta" coluna={ordHistorico.coluna} dir={ordHistorico.dir} ordenar={ordHistorico.ordenar} />
                <ThOrdenavel label="Lançamento" campo="numero_lancamento_gerado" coluna={ordHistorico.coluna} dir={ordHistorico.dir} ordenar={ordHistorico.ordenar} />
                {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
              </tr></thead>
              <tbody>
                {ordHistorico.linhasOrdenadas.map((c) => (
                  <tr key={c.id}>
                    <td style={{ fontWeight: 700 }}>{c.numero_animal}</td>
                    <td style={{ fontSize: "0.8rem" }}>{ehCompra ? c.vendedor : c.comprador}</td>
                    <td style={{ fontSize: "0.8rem" }}>{ehCompra ? c.data_compra : c.data_venda}</td>
                    <td style={{ textAlign: "right" }}>R$ {c.valor.toFixed(2)}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.gta || "—"}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.numero_lancamento_gerado || "—"}</td>
                    {admin && <td style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{c.usuario_nome ?? "—"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
