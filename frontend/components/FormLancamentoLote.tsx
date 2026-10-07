"use client";
// Lançamento em lote: várias notas de UM fornecedor lançadas de uma vez (ex.: as ~20 notas do posto de
// combustível pagas na virada do mês). Cada nota é um lançamento completo; o lote as agrupa numa fatura
// já fechada (ou paga). Grava TUDO OU NADA. Rascunho automático no navegador.
import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Check, Copy, Plus, Trash2, X } from "lucide-react";
import {
  abrirFatura, anexarArquivoLancamentoPorId, anexarComprovanteEmLote, criarLoteFatura, fetchCentrosCusto, lancarNotasAvulsas, lancarNotasNaFatura, fetchContasCorrentes,
  fetchEstoqueAtivos, fetchFornecedores, fetchOpcoesFinanceiro, fetchPlanoContas, formatBRL, getUsuario,
  type ContaCorrenteCadastro, type FaturaDetalhe, type LoteIn, type LoteResultado,
} from "@/lib/api";
import { CampoMoeda } from "@/components/CampoMoeda";
import { Dropzone } from "@/components/Dropzone";
import { SeletorContaGerencial } from "@/components/SeletorContaGerencial";
import { EstoquePicker, type EstoqueItemPicker } from "@/components/EstoquePicker";
import type { ContaPlano } from "@/lib/contaGerencial";

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: "var(--r-sm)", padding: "0.4rem 0.5rem", fontSize: "0.84rem", minWidth: 0,
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.2rem" };
const FORMAS = [{ v: "pix", r: "Pix" }, { v: "transferencia", r: "Transferência" }, { v: "boleto", r: "Boleto" }, { v: "debito", r: "Débito" }];
const TIPOS_DOC_PADRAO = ["Nota fiscal", "Cupom fiscal", "Recibo", "Comprovante", "Fatura"];
const CHAVE_RASCUNHO = "cowdata_lote_rascunho_v1";
const hoje = () => new Date().toISOString().slice(0, 10);

type Item = { uid: number; tipoItem: "produto" | "servico"; produto: string; codigo: string; nome: string; qtd: string; unit: number };
type Nota = {
  uid: number; tipoDoc: string; numero: string; semNumero: boolean; data: string; itens: Item[];
  desconto: number; acrescimo: number; anexo: File | null;
};
type Produto = EstoqueItemPicker & { conta_gerencial_despesa_padrao: string | null };

let _uid = 0;
const novoUid = () => ++_uid;
const itemVazio = (): Item => ({ uid: novoUid(), tipoItem: "produto", produto: "", codigo: "", nome: "", qtd: "", unit: 0 });
const notaVazia = (tipoDoc: string, data: string): Nota => ({
  uid: novoUid(), tipoDoc, numero: "", semNumero: false, data, itens: [itemVazio()], desconto: 0, acrescimo: 0, anexo: null,
});
const totalItem = (i: Item) => Math.round((Number(i.qtd.replace(",", ".")) || 0) * i.unit * 100) / 100;
const liquidoNota = (n: Nota) => Math.round((n.itens.reduce((s, i) => s + totalItem(i), 0) - n.desconto + n.acrescimo) * 100) / 100;

export function FormLancamentoLote({ onSujo, fatura, onLancado }: {
  onSujo?: (sujo: boolean) => void;
  /** Modo fatura: as notas entram numa fatura ABERTA; fornecedor, conta e centro de custo vêm dela e não há vencimento/pagamento aqui. */
  fatura?: FaturaDetalhe;
  onLancado?: () => void;
}) {
  const modoFatura = !!fatura;
  const [fornecedores, setFornecedores] = useState<string[]>([]);
  const [tiposDoc, setTiposDoc] = useState<string[]>(TIPOS_DOC_PADRAO);
  const [contas, setContas] = useState<ContaCorrenteCadastro[]>([]);
  const [centros, setCentros] = useState<{ nome: string; padrao?: boolean; ativo?: boolean }[]>([]);
  const [plano, setPlano] = useState<ContaPlano[]>([]);
  const [produtos, setProdutos] = useState<Produto[]>([]);
  useEffect(() => {
    Promise.all([fetchFornecedores().catch(() => []), fetchOpcoesFinanceiro().catch(() => ({} as any))]).then(([cad, op]: any[]) => {
      const nomes = new Set<string>([...(op.fornecedores || []), ...(cad || []).map((f: any) => f.nome)]);
      setFornecedores(Array.from(nomes).sort((a, b) => a.localeCompare(b, "pt-BR")));
      if (op.tipos_documento?.length) setTiposDoc(op.tipos_documento);
    });
    fetchContasCorrentes().then(setContas).catch(() => {});
    fetchCentrosCusto().then((l: any[]) => setCentros(l.filter((c) => c.ativo !== false))).catch(() => {});
    fetchPlanoContas().then(setPlano).catch(() => {});
    fetchEstoqueAtivos().then((d) => setProdutos((d.itens || []).map((i: any) => ({
      nome: i.nome, categoria: i.categoria ?? null, quantidade: i.quantidade ?? null, unidade: i.unidade ?? null,
      estocavel: i.estocavel ?? null, finalidade: i.finalidade ?? null,
      conta_gerencial_despesa_padrao: i.conta_gerencial_despesa_padrao ?? null,
    })))).catch(() => {});
  }, []);
  const contasAtivas = useMemo(() => contas.filter((c) => c.ativo), [contas]);

  const [fornecedorLivre, setFornecedor] = useState("");
  const [contaLivre, setContaBancaria] = useState("");
  const [centroLivre, setCentroCusto] = useState("");
  const fornecedor = fatura ? fatura.fornecedor : fornecedorLivre;
  const contaBancaria = fatura ? fatura.conta_bancaria || "" : contaLivre;
  const centroCusto = fatura ? fatura.centro_custo || "" : centroLivre;
  useEffect(() => { if (!fatura && !centroLivre) { const p = centros.find((c) => c.padrao); if (p) setCentroCusto(p.nome); } }, [centros]); // eslint-disable-line react-hooks/exhaustive-deps
  const [notas, setNotas] = useState<Nota[]>(() => [notaVazia("Nota fiscal", hoje())]);
  const [modo, setModo] = useState<"venc" | "parc" | "pago">("venc");
  const [vencimento, setVencimento] = useState("");
  const [parcN, setParcN] = useState("3");
  const [parcPrimeiro, setParcPrimeiro] = useState("");
  const [parcIntervalo, setParcIntervalo] = useState<"mensal" | "30dias">("mensal");
  const [pagData, setPagData] = useState(hoje());
  const [pagForma, setPagForma] = useState("pix");
  const [pagComp, setPagComp] = useState("");
  const [comprovante, setComprovante] = useState<File | null>(null);
  const [totalForn, setTotalForn] = useState(0);

  const usuario = getUsuario();
  const responsavel = usuario?.nome || usuario?.username || "Você";

  const totalNotas = useMemo(() => Math.round(notas.reduce((s, n) => s + liquidoNota(n), 0) * 100) / 100, [notas]);
  const totalItens = useMemo(() => notas.reduce((s, n) => s + n.itens.length, 0), [notas]);
  // Prévia das parcelas da fatura: cada nota é dividida em n partes (centavos sobrantes na última), como no servidor.
  const previaParcelas = useMemo(() => {
    const n = Number(parcN) || 0;
    if (modo !== "parc" || n < 2 || n > 24 || !parcPrimeiro) return [];
    const somas = Array(n).fill(0);
    notas.forEach((nt) => {
      const cent = Math.round(liquidoNota(nt) * 100);
      if (cent <= 0) return;
      const base = Math.floor(cent / n);
      for (let i = 0; i < n; i++) somas[i] += i === n - 1 ? cent - base * (n - 1) : base;
    });
    const [a, m, d] = parcPrimeiro.split("-").map(Number);
    return somas.map((c, i) => {
      let data: Date;
      if (parcIntervalo === "30dias") data = new Date(a, m - 1, d + 30 * i);
      else { const alvo = new Date(a, m - 1 + i, 1); data = new Date(alvo.getFullYear(), alvo.getMonth(), Math.min(d, new Date(alvo.getFullYear(), alvo.getMonth() + 1, 0).getDate())); }
      return { n: i + 1, data: data.toLocaleDateString("pt-BR"), valor: c / 100 };
    });
  }, [modo, parcN, parcPrimeiro, parcIntervalo, notas]);
  const diferenca = totalForn > 0 ? Math.round((totalForn - totalNotas) * 100) / 100 : null;

  // Estocáveis: avisa na própria tela quais itens darão entrada no estoque.
  const estocaveis = useMemo(() => {
    const nomes = new Set<string>();
    notas.forEach((n) => n.itens.forEach((i) => {
      if (i.tipoItem === "produto" && i.produto && produtos.find((p) => p.nome === i.produto && p.estocavel !== false)) nomes.add(i.produto);
    }));
    return Array.from(nomes);
  }, [notas, produtos]);

  // Duplicidade DENTRO do lote (mesmo tipo + número).
  const duplicadasNoLote = useMemo(() => {
    const vistos = new Map<string, number>();
    const dup = new Set<number>();
    notas.forEach((n, idx) => {
      const num = n.numero.trim().toLowerCase();
      if (n.semNumero || !num) return;
      const k = `${n.tipoDoc.toLowerCase()}|${num}`;
      if (vistos.has(k)) { dup.add(idx); dup.add(vistos.get(k)!); } else vistos.set(k, idx);
    });
    return dup;
  }, [notas]);

  const sujo = useMemo(() => Boolean(fornecedor || notas.some((n) => n.numero || n.itens.some((i) => i.produto || i.unit))), [fornecedor, notas]);
  useEffect(() => { onSujo?.(sujo); }, [sujo, onSujo]);

  // ── Rascunho no navegador (texto; arquivos não são guardados) ──
  const chaveRascunho = fatura ? `${CHAVE_RASCUNHO}_fatura_${fatura.id}` : CHAVE_RASCUNHO;
  const [rascunhoSalvo, setRascunhoSalvo] = useState<{ em: string; dados: any } | null>(null);
  useEffect(() => {
    try { const r = localStorage.getItem(chaveRascunho); if (r) setRascunhoSalvo(JSON.parse(r)); } catch { /* sem storage: segue sem rascunho */ }
  }, []);
  useEffect(() => {
    if (!sujo) return;
    const t = setTimeout(() => {
      try {
        localStorage.setItem(chaveRascunho, JSON.stringify({
          em: new Date().toISOString(),
          dados: { fornecedor, contaBancaria, centroCusto, modo, vencimento, parcN, parcPrimeiro, parcIntervalo, pagData, pagForma, pagComp, totalForn,
            notas: notas.map((n) => ({ ...n, anexo: null })) },
        }));
      } catch { /* cota cheia ou bloqueado: rascunho é só conveniência */ }
    }, 600);
    return () => clearTimeout(t);
  }, [sujo, fornecedor, contaBancaria, centroCusto, modo, vencimento, parcN, parcPrimeiro, parcIntervalo, pagData, pagForma, pagComp, totalForn, notas]);
  function restaurar() {
    const d = rascunhoSalvo?.dados; if (!d) return;
    setFornecedor(d.fornecedor || ""); setContaBancaria(d.contaBancaria || ""); setCentroCusto(d.centroCusto || "");
    setModo(d.modo || "venc"); setVencimento(d.vencimento || ""); setParcN(d.parcN || "3"); setParcPrimeiro(d.parcPrimeiro || "");
    setParcIntervalo(d.parcIntervalo || "mensal"); setPagData(d.pagData || hoje()); setPagForma(d.pagForma || "pix"); setPagComp(d.pagComp || ""); setTotalForn(d.totalForn || 0);
    if (Array.isArray(d.notas) && d.notas.length) setNotas(d.notas.map((n: Nota) => ({ ...n, uid: novoUid(), anexo: null, itens: n.itens.map((i) => ({ ...i, uid: novoUid() })) })));
    setRascunhoSalvo(null);
  }
  function descartarRascunho() { try { localStorage.removeItem(chaveRascunho); } catch { /* ignora */ } setRascunhoSalvo(null); }

  // ── Edição ──
  const raiz = useRef<HTMLDivElement>(null);
  function setNota(uid: number, patch: Partial<Nota>) { setNotas((a) => a.map((n) => (n.uid === uid ? { ...n, ...patch } : n))); }
  function setItem(nuid: number, iuid: number, patch: Partial<Item>) {
    setNotas((a) => a.map((n) => (n.uid === nuid ? { ...n, itens: n.itens.map((i) => (i.uid === iuid ? { ...i, ...patch } : i)) } : n)));
  }
  function focar(iuid: number) { setTimeout(() => raiz.current?.querySelector<HTMLElement>(`[data-item="${iuid}"] [data-foco]`)?.focus(), 60); }
  function novoItem(nuid: number) {
    const it = itemVazio();
    setNotas((a) => a.map((n) => (n.uid === nuid ? { ...n, itens: [...n.itens, it] } : n)));
    focar(it.uid);
  }
  function removerItem(nuid: number, iuid: number) {
    setNotas((a) => a.map((n) => (n.uid === nuid && n.itens.length > 1 ? { ...n, itens: n.itens.filter((i) => i.uid !== iuid) } : n)));
  }
  function novaNota() {
    const ultima = notas[notas.length - 1];
    setNotas((a) => [...a, notaVazia(ultima?.tipoDoc || "Nota fiscal", ultima?.data || hoje())]);
  }
  function duplicar(n: Nota) {
    setNotas((a) => [...a, { ...n, uid: novoUid(), numero: "", anexo: null, itens: n.itens.map((i) => ({ ...i, uid: novoUid() })) }]);
  }
  function excluirNota(uid: number) { setNotas((a) => (a.length > 1 ? a.filter((n) => n.uid !== uid) : a)); }

  // ── Envio ──
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [pendencia, setPendencia] = useState<{ tipo: "divergencia" | "duplicadas" | "fora_periodo"; mensagem: string; itens?: any[]; fora?: { nota: number; data_emissao: string; motivo: string }[] } | null>(null);

  function montar(conf: { divergencia?: boolean; duplicados?: boolean }): LoteIn {
    const parcelas = Number(parcN) || 0;
    return {
      fornecedor, conta_bancaria: contaBancaria || null, centro_custo: centroCusto || null,
      notas: notas.map((n) => ({
        tipo_documento: n.tipoDoc, numero_documento: n.semNumero ? null : n.numero.trim() || null, sem_numero: n.semNumero,
        data_emissao: n.data, desconto: n.desconto, acrescimo: n.acrescimo,
        itens: n.itens.map((i) => ({
          codigo_conta_gerencial: i.codigo || null, nome_conta_gerencial: i.nome || null, produto: i.produto.trim(), tipo_item: i.tipoItem,
          quantidade: Number(i.qtd.replace(",", ".")) || null, valor_unitario: i.unit || null, valor_total: totalItem(i),
        })),
      })),
      modo, data_vencimento: modo === "venc" ? vencimento : null,
      parcelamento: modo === "parc" ? { n: parcelas, primeiro_vencimento: parcPrimeiro, intervalo: parcIntervalo } : null,
      pagamento: modo === "pago" ? { data_pagamento: pagData, forma_pagamento: pagForma, conta_bancaria: contaBancaria || null, numero_documento_pagamento: pagComp.trim() || null } : null,
      total_fornecedor: totalForn > 0 ? totalForn : null,
      confirmar_divergencia: !!conf.divergencia, confirmar_duplicados: !!conf.duplicados,
    };
  }

  function validar(): string | null {
    if (!fornecedor) return "Escolha o fornecedor do lote.";
    if (!modoFatura && !contaBancaria && modo === "pago") return "Escolha a conta bancária do pagamento.";
    if (duplicadasNoLote.size) return "Há notas repetidas neste lote (mesmo tipo e número). Corrija antes de lançar.";
    for (let k = 0; k < notas.length; k++) {
      const n = notas[k];
      if (!n.semNumero && !n.numero.trim()) return `Nota ${k + 1}: informe o número ou marque "sem número".`;
      if (!n.data) return `Nota ${k + 1}: informe a data.`;
      if (n.itens.some((i) => !i.produto.trim() || totalItem(i) <= 0)) return `Nota ${k + 1}: todo item precisa de produto/serviço e valor maior que zero.`;
      if (n.itens.some((i) => i.tipoItem === "produto" && !(Number(i.qtd.replace(",", ".")) > 0))) return `Nota ${k + 1}: informe a quantidade de cada produto.`;
      if (liquidoNota(n) <= 0) return `Nota ${k + 1}: o valor líquido deve ser positivo.`;
    }
    if (modoFatura) return null;
    if (modo === "venc" && !vencimento) return "Informe o vencimento do lote.";
    if (modo === "parc" && (!(Number(parcN) >= 2) || !parcPrimeiro)) return "Informe o número de parcelas (2 ou mais) e o primeiro vencimento.";
    if (modo === "pago" && !pagData) return "Informe a data do pagamento.";
    return null;
  }

  const escolhaFora = useRef<Conf["foraPeriodo"]>(undefined);
  type Conf = { divergencia?: boolean; duplicados?: boolean; foraPeriodo?: "nesta" | "nova" | "avulsa" };

  async function anexarDepois(porNota: { idx: number; ids: number[] }[], idsPagos?: number[]): Promise<string[]> {
    const falhas: string[] = [];
    for (const { idx, ids } of porNota) {
      const n = notas[idx];
      if (!n?.anexo) continue;
      try { await anexarArquivoLancamentoPorId(ids[0], n.anexo, n.tipoDoc, n.semNumero ? null : n.numero.trim() || null, n.data); }
      catch (e: any) { falhas.push(`nota ${idx + 1} (${e.message || "erro"})`); }
    }
    if (idsPagos && comprovante) {
      try { await anexarComprovanteEmLote(idsPagos, [comprovante], "Comprovante de pagamento"); }
      catch (e: any) { falhas.push(`comprovante (${e.message || "erro"})`); }
    }
    return falhas;
  }

  function encerrar(texto: string) {
    escolhaFora.current = undefined;
    setSucesso(texto);
    descartarRascunho();
    if (!fatura) setFornecedor("");
    setNotas([notaVazia("Nota fiscal", hoje())]); setTotalForn(0); setComprovante(null); setPagComp("");
    onSujo?.(false);
    onLancado?.();
  }

  // Modo fatura: lança as notas na fatura aberta. Nota fora do período pergunta o que fazer (abre `pendencia`).
  async function lancarNaFatura(conf: Conf) {
    if (!fatura) return;
    if (conf.foraPeriodo) escolhaFora.current = conf.foraPeriodo;
    else conf = { ...conf, foraPeriodo: escolhaFora.current };
    const todas = montar({}).notas;
    const dentro: number[] = [];
    const fora: number[] = [];
    todas.forEach((n, i) => {
      const antes = n.data_emissao < fatura.data_abertura;
      const depois = !!fatura.data_fechamento_prevista && n.data_emissao > fatura.data_fechamento_prevista;
      (antes || depois ? fora : dentro).push(i);
    });
    const escolha = conf.foraPeriodo;
    if (fora.length && !escolha) {
      setPendencia({
        tipo: "fora_periodo", mensagem: "", fora: fora.map((i) => ({ nota: i + 1, data_emissao: todas[i].data_emissao,
          motivo: todas[i].data_emissao < fatura.data_abertura ? "anterior à abertura da fatura" : "posterior ao fechamento previsto da fatura" })),
      });
      return;
    }
    const porNota: { idx: number; ids: number[] }[] = [];
    const avisos: string[] = [];
    const resumo: string[] = [];
    const pegar = (idxs: number[]) => idxs.map((i) => todas[i]);
    const registrar = (idxs: number[], notasFeitas: { ids: number[]; avisos_estoque: string[] }[]) => {
      notasFeitas.forEach((r, k) => { porNota.push({ idx: idxs[k], ids: r.ids }); avisos.push(...r.avisos_estoque); });
    };
    const dentroEnviar = escolha === "nesta" ? [...dentro, ...fora] : dentro;
    let novaFaturaId: number | null = null;
    try {
      if (fora.length && escolha === "nova") {
        const datas = fora.map((i) => todas[i].data_emissao).sort();
        const [ai, mi] = datas[0].split("-").map(Number);
        const [af, mf] = datas[datas.length - 1].split("-").map(Number);
        const nova = await abrirFatura({
          fornecedor: fatura.fornecedor, data_abertura: `${ai}-${String(mi).padStart(2, "0")}-01`,
          data_fechamento_prevista: `${af}-${String(mf).padStart(2, "0")}-${String(new Date(af, mf, 0).getDate()).padStart(2, "0")}`,
          data_vencimento: fatura.data_vencimento, conta_bancaria: fatura.conta_bancaria, centro_custo: fatura.centro_custo,
        });
        novaFaturaId = nova.id;
        const r = await lancarNotasNaFatura(nova.id, { notas: pegar(fora), confirmar_duplicados: !!conf.duplicados, confirmar_fora_periodo: true });
        registrar(fora, r.notas);
        resumo.push(`${fora.length} nota(s) na nova fatura "${nova.rotulo}"`);
      } else if (fora.length && escolha === "avulsa") {
        const r = await lancarNotasAvulsas({
          fornecedor: fatura.fornecedor, conta_bancaria: fatura.conta_bancaria, centro_custo: fatura.centro_custo,
          notas: pegar(fora), data_vencimento: fatura.data_vencimento || hoje(), confirmar_duplicados: !!conf.duplicados,
        });
        registrar(fora, r.notas);
        resumo.push(`${fora.length} nota(s) sem fatura`);
      }
      if (dentroEnviar.length) {
        const r = await lancarNotasNaFatura(fatura.id, { notas: pegar(dentroEnviar), confirmar_duplicados: !!conf.duplicados, confirmar_fora_periodo: true });
        registrar(dentroEnviar, r.notas);
        resumo.unshift(`${dentroEnviar.length} nota(s) na fatura "${fatura.rotulo}"`);
      }
    } catch (e) {
      if (novaFaturaId !== null && porNota.length === 0) { /* a fatura nova ficou vazia: o usuário a exclui na lista, se quiser */ }
      throw e;
    }
    const falhas = await anexarDepois(porNota);
    setPendencia(null);
    encerrar(`Lançado: ${resumo.join("; ")}.` + (avisos.length ? ` ${avisos.join(" ")}` : "") +
      (falhas.length ? ` Atenção: as notas foram gravadas, mas faltou anexar: ${falhas.join("; ")}. Anexe pelo lançamento.` : ""));
  }

  async function lancar(conf: Conf = {}) {
    setErro(null); setSucesso(null);
    const problema = validar();
    if (problema) { setErro(problema); return; }
    setSalvando(true);
    try {
      if (modoFatura) { await lancarNaFatura(conf); return; }
      const r: LoteResultado = await criarLoteFatura(montar({ divergencia: conf.divergencia, duplicados: conf.duplicados }));
      setPendencia(null);
      const falhas = await anexarDepois(r.notas.map((x, i) => ({ idx: i, ids: x.ids })), modo === "pago" ? r.ids_contas : undefined);
      const avisos = r.notas.flatMap((x) => x.avisos_estoque);
      encerrar(
        `Lote lançado: ${r.notas.length} nota(s), ${formatBRL(r.valor_total)}, fatura "${r.rotulo}" (${r.status === "paga" ? "paga" : "fechada"}).` +
        (avisos.length ? ` ${avisos.join(" ")}` : "") +
        (falhas.length ? ` Atenção: o lote foi gravado, mas faltou anexar: ${falhas.join("; ")}. Anexe pelo lançamento.` : ""),
      );
    } catch (e: any) {
      const d = e.detail;
      if (e.status === 409 && d?.codigo === "divergencia_total") {
        const dif = Math.abs(Math.round((d.total_fornecedor - d.soma_notas) * 100) / 100);
        setPendencia({ tipo: "divergencia", mensagem: `O total das notas (${formatBRL(d.soma_notas)}) difere do total informado pelo fornecedor (${formatBRL(d.total_fornecedor)}) em ${formatBRL(dif)}.` });
      }
      else if (e.status === 409 && d?.codigo === "duplicadas") setPendencia({ tipo: "duplicadas", mensagem: d.mensagem, itens: d.duplicadas });
      else setErro(e.message || (modoFatura ? "Erro ao lançar as notas." : "Erro ao lançar o lote. Nada foi gravado."));
    } finally { setSalvando(false); }
  }

  const aviso = (cor: string): React.CSSProperties => ({ fontSize: "0.8rem", padding: "0.45rem 0.65rem", borderRadius: "var(--r-sm)", border: `1px solid ${cor}`, margin: "0.4rem 0" });

  return (
    <div ref={raiz}>
      {rascunhoSalvo && (
        <div className="card mb-3" style={{ border: "1px solid var(--dourado)" }}>
          <p style={{ fontSize: "0.82rem", marginBottom: "0.5rem" }}>
            Há um rascunho de lote salvo neste navegador ({new Date(rascunhoSalvo.em).toLocaleString("pt-BR")}). Os anexos não são guardados no rascunho.
          </p>
          <div className="flex gap-2">
            <button type="button" className="btn-primary" onClick={restaurar}>Restaurar rascunho</button>
            <button type="button" className="btn-ghost" onClick={descartarRascunho}>Descartar</button>
          </div>
        </div>
      )}

      <div className="card">
        <p className="card-header mb-2">{modoFatura ? `Fatura: ${fatura!.rotulo}` : "Dados do lote"}</p>
        {modoFatura ? (
          <div className="flex flex-wrap gap-x-8 gap-y-1" style={{ fontSize: "0.84rem" }}>
            <span>Fornecedor: <strong>{fatura!.fornecedor}</strong></span>
            <span>Conta: <strong>{fatura!.conta_bancaria || "—"}</strong></span>
            <span>Centro de custo: <strong>{fatura!.centro_custo || "—"}</strong></span>
            <span>Período: <strong>{fatura!.data_abertura.split("-").reverse().join("/")}{fatura!.data_fechamento_prevista ? ` a ${fatura!.data_fechamento_prevista.split("-").reverse().join("/")}` : " (sem fechamento previsto)"}</strong></span>
            <span>Responsável: <strong>{responsavel} (você)</strong></span>
          </div>
        ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div><label style={lbl} htmlFor="lote-forn">Fornecedor (único)</label>
            <select id="lote-forn" style={inputStyle} value={fornecedor} onChange={(e) => setFornecedor(e.target.value)}>
              <option value="">Selecione…</option>{fornecedores.map((f) => <option key={f} value={f}>{f}</option>)}</select></div>
          <div><label style={lbl} htmlFor="lote-conta">Conta bancária</label>
            <select id="lote-conta" style={inputStyle} value={contaBancaria} onChange={(e) => setContaBancaria(e.target.value)}>
              <option value="">Selecione…</option>{contasAtivas.map((c) => <option key={c.id} value={c.rotulo}>{c.rotulo}</option>)}</select></div>
          <div><label style={lbl} htmlFor="lote-cc">Centro de custo</label>
            <select id="lote-cc" style={inputStyle} value={centroCusto} onChange={(e) => setCentroCusto(e.target.value)}>
              <option value="">Selecione…</option>{centros.map((c) => <option key={c.nome} value={c.nome}>{c.nome}</option>)}</select></div>
          <div><label style={lbl} htmlFor="lote-resp">Responsável</label>
            <input id="lote-resp" style={{ ...inputStyle, background: "transparent", borderStyle: "dashed" }} value={`${responsavel} (você)`} readOnly /></div>
        </div>
        )}
      </div>

      <div className="grid gap-3 mt-3" style={{ gridTemplateColumns: "minmax(0,1fr)" }}>
        <div>
          {notas.map((n, idx) => (
            <div key={n.uid} className="card" style={{ marginBottom: "0.8rem", padding: 0, overflow: "hidden", border: duplicadasNoLote.has(idx) ? "1px solid var(--red)" : undefined }}>
              <div className="flex flex-wrap items-center justify-between gap-2" style={{ padding: "0.5rem 0.8rem", background: "var(--surface-2)", borderBottom: "1px solid var(--border)" }}>
                <strong style={{ fontSize: "0.85rem" }}>Nota {idx + 1} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>· {n.itens.length} item(ns)</span></strong>
                <div className="flex items-center gap-2 flex-wrap">
                  <label style={{ fontSize: "0.76rem", display: "flex", gap: "0.3rem", alignItems: "center", margin: 0 }}>
                    <input type="checkbox" checked={n.semNumero} onChange={(e) => setNota(n.uid, { semNumero: e.target.checked })} /> sem número
                  </label>
                  <button type="button" className="btn-ghost" style={{ fontSize: "0.74rem" }} onClick={() => duplicar(n)}><Copy size={12} /> Duplicar nota</button>
                  {notas.length > 1 && <button type="button" className="btn-ghost" style={{ fontSize: "0.74rem", color: "var(--red)" }} onClick={() => excluirNota(n.uid)}><Trash2 size={12} /> Excluir nota</button>}
                </div>
              </div>
              <div style={{ padding: "0.7rem 0.8rem" }}>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
                  <div><label style={lbl}>Tipo de documento</label>
                    <select style={inputStyle} value={n.tipoDoc} onChange={(e) => setNota(n.uid, { tipoDoc: e.target.value })}>
                      {Array.from(new Set([...tiposDoc, n.tipoDoc])).map((t) => <option key={t} value={t}>{t}</option>)}</select></div>
                  <div><label style={lbl}>Número do documento</label>
                    <input style={inputStyle} value={n.numero} disabled={n.semNumero} onChange={(e) => setNota(n.uid, { numero: e.target.value })} placeholder={n.semNumero ? "sem número" : "Obrigatório"} /></div>
                  <div><label style={lbl}>Data (emissão)</label>
                    <input type="date" style={inputStyle} value={n.data} onChange={(e) => setNota(n.uid, { data: e.target.value })} /></div>
                  <div><label style={lbl}>Anexo (foto do cupom)</label>
                    {n.anexo ? (
                      <div className="flex items-center justify-between gap-2" style={{ fontSize: "0.76rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.3rem 0.5rem" }}>
                        <span style={{ wordBreak: "break-all" }}>{n.anexo.name}</span>
                        <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => setNota(n.uid, { anexo: null })} aria-label="Remover anexo"><X size={12} /></button>
                      </div>
                    ) : <Dropzone accept="application/pdf,image/jpeg,image/png" label="Arraste ou clique" hint="PDF, JPG ou PNG" onFiles={(f) => setNota(n.uid, { anexo: f[0] || null })} />}
                  </div>
                </div>

                <div style={{ overflowX: "auto" }}>
                  <div style={{ minWidth: 820 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "96px minmax(170px,1.5fr) minmax(170px,1.4fr) 70px 110px 110px 30px", gap: "0.4rem", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: "0.25rem" }}>
                      <span>Tipo</span><span>Produto ou serviço</span><span>Conta gerencial</span><span style={{ textAlign: "right" }}>Qtd</span><span style={{ textAlign: "right" }}>Vl. unit.</span><span style={{ textAlign: "right" }}>Total</span><span />
                    </div>
                    {n.itens.map((it) => (
                      <div key={it.uid} data-item={it.uid} style={{ display: "grid", gridTemplateColumns: "96px minmax(170px,1.5fr) minmax(170px,1.4fr) 70px 110px 110px 30px", gap: "0.4rem", alignItems: "center", marginBottom: "0.35rem" }}>
                        <select style={inputStyle} aria-label="Tipo do item" value={it.tipoItem} onChange={(e) => setItem(n.uid, it.uid, { tipoItem: e.target.value as "produto" | "servico", produto: "", qtd: e.target.value === "servico" ? "1" : "" })}>
                          <option value="produto">produto</option><option value="servico">serviço</option></select>
                        {it.tipoItem === "produto" ? (
                          <div data-foco tabIndex={-1}>
                            <EstoquePicker itens={produtos} value={it.produto} todasFinalidades incluirNaoEstocaveis onChange={(nome) => {
                              const p = produtos.find((x) => x.nome === nome);
                              const padrao = p?.conta_gerencial_despesa_padrao ? plano.find((c) => c.codigo === p.conta_gerencial_despesa_padrao) : null;
                              setItem(n.uid, it.uid, { produto: nome, ...(padrao ? { codigo: padrao.codigo, nome: padrao.nome } : {}) });
                            }} />
                          </div>
                        ) : (
                          <input data-foco style={inputStyle} aria-label="Descrição do serviço" value={it.produto} onChange={(e) => setItem(n.uid, it.uid, { produto: e.target.value })} placeholder="ex.: Lavagem" />
                        )}
                        <SeletorContaGerencial contas={plano} tipo="despesa" natureza={it.tipoItem} codigo={it.codigo} nome={it.nome}
                          onSelect={(codigo, nome) => setItem(n.uid, it.uid, { codigo, nome })} placeholder="Conta (galho mais baixo)…" />
                        <input style={{ ...inputStyle, textAlign: "right" }} aria-label="Quantidade" inputMode="decimal" value={it.qtd} onChange={(e) => setItem(n.uid, it.uid, { qtd: e.target.value })} />
                        <CampoMoeda style={{ ...inputStyle, textAlign: "right" }} value={it.unit} onChange={(v) => setItem(n.uid, it.uid, { unit: v })} />
                        <input style={{ ...inputStyle, textAlign: "right", background: "transparent", borderStyle: "dashed", fontVariantNumeric: "tabular-nums" }} aria-label="Valor total do item" readOnly value={formatBRL(totalItem(it))} />
                        <button type="button" className="btn-ghost" style={{ color: "var(--red)", padding: "0.2rem" }} aria-label="Remover item" onClick={() => removerItem(n.uid, it.uid)}><X size={13} /></button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 mt-2">
                  <button type="button" className="btn-ghost" style={{ fontSize: "0.78rem" }} onClick={() => novoItem(n.uid)}><Plus size={13} /> Acrescentar produto ou serviço</button>
                  <details style={{ fontSize: "0.78rem" }}>
                    <summary style={{ cursor: "pointer", color: "var(--text-muted)" }}>Mais opções (desconto e acréscimo da nota)</summary>
                    <div className="grid grid-cols-2 gap-3 mt-2" style={{ minWidth: 260 }}>
                      <div><label style={lbl}>Desconto (R$)</label><CampoMoeda style={inputStyle} value={n.desconto} onChange={(v) => setNota(n.uid, { desconto: v })} /></div>
                      <div><label style={lbl}>Acréscimo (R$)</label><CampoMoeda style={inputStyle} value={n.acrescimo} onChange={(v) => setNota(n.uid, { acrescimo: v })} /></div>
                    </div>
                  </details>
                </div>
                <div className="flex items-center justify-between mt-2">
                  <span style={{ fontSize: "0.76rem", color: duplicadasNoLote.has(idx) ? "var(--red)" : "var(--amber)" }}>
                    {duplicadasNoLote.has(idx) ? "Repetida neste lote: mesmo tipo e número." : !n.semNumero && !n.numero.trim() ? 'Informe o número ou marque "sem número".' : ""}
                  </span>
                  <span style={{ fontSize: "0.85rem" }}>Valor da nota: <strong style={{ fontVariantNumeric: "tabular-nums" }}>{formatBRL(liquidoNota(n))}</strong></span>
                </div>
              </div>
            </div>
          ))}
          <button type="button" className="btn-primary" onClick={novaNota}><Plus size={14} /> Nova nota</button>
          <span style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginLeft: "0.6rem" }}>A nova nota herda tipo de documento e data da anterior.</span>
        </div>

        {!modoFatura && (
        <div className="card">
          <p className="card-header mb-2">Vencimento e pagamento do lote</p>
          <div className="flex flex-wrap gap-2">
            {([["venc", "Vencimento único"], ["parc", "Parcelar a fatura"], ["pago", "Já pago"]] as const).map(([v, r]) => (
              <label key={v} style={{ display: "flex", gap: "0.35rem", alignItems: "center", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.65rem", fontSize: "0.82rem", cursor: "pointer", background: modo === v ? "var(--surface-2)" : undefined, margin: 0 }}>
                <input type="radio" name="lote-modo" checked={modo === v} onChange={() => setModo(v)} /> {r}
              </label>
            ))}
          </div>
          {modo === "venc" && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
              <div><label style={lbl} htmlFor="lote-venc">Vencimento (todas as notas)</label><input id="lote-venc" type="date" style={inputStyle} value={vencimento} onChange={(e) => setVencimento(e.target.value)} /></div>
            </div>
          )}
          {modo === "parc" && (
            <div className="mt-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div><label style={lbl} htmlFor="lote-pn">Número de parcelas da fatura</label><input id="lote-pn" type="number" min={2} max={24} style={inputStyle} value={parcN} onChange={(e) => setParcN(e.target.value)} /></div>
                <div><label style={lbl} htmlFor="lote-pd">Primeiro vencimento</label><input id="lote-pd" type="date" style={inputStyle} value={parcPrimeiro} onChange={(e) => setParcPrimeiro(e.target.value)} /></div>
                <div><label style={lbl} htmlFor="lote-pi">Intervalo</label>
                  <select id="lote-pi" style={inputStyle} value={parcIntervalo} onChange={(e) => setParcIntervalo(e.target.value as "mensal" | "30dias")}><option value="mensal">Mensal</option><option value="30dias">A cada 30 dias</option></select></div>
              </div>
              <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>Cada nota é dividida nas mesmas parcelas; os centavos que sobram ficam na última.</p>
              {previaParcelas.length > 0 && (
                <div style={{ fontSize: "0.8rem", marginTop: "0.3rem", fontVariantNumeric: "tabular-nums" }} data-testid="previa-parcelas">
                  {previaParcelas.map((x) => <div key={x.n}>Parcela {x.n}/{previaParcelas.length} · {x.data} · <strong>{formatBRL(x.valor)}</strong></div>)}
                </div>
              )}
            </div>
          )}
          {modo === "pago" && (
            <div className="mt-3">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div><label style={lbl} htmlFor="lote-pgd">Data do pagamento</label><input id="lote-pgd" type="date" style={inputStyle} value={pagData} onChange={(e) => setPagData(e.target.value)} /></div>
                <div><label style={lbl} htmlFor="lote-pgf">Forma</label>
                  <select id="lote-pgf" style={inputStyle} value={pagForma} onChange={(e) => setPagForma(e.target.value)}>{FORMAS.map((f) => <option key={f.v} value={f.v}>{f.r}</option>)}</select></div>
                <div><label style={lbl} htmlFor="lote-pgc">Nº do comprovante</label><input id="lote-pgc" style={inputStyle} value={pagComp} onChange={(e) => setPagComp(e.target.value)} placeholder="Ex.: código do Pix" /></div>
              </div>
              <label style={{ ...lbl, marginTop: "0.6rem" }}>Comprovante único da fatura (um arquivo, vale para todas as notas)</label>
              {comprovante ? (
                <div className="flex items-center justify-between gap-2" style={{ fontSize: "0.78rem", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem" }}>
                  <span style={{ wordBreak: "break-all" }}>{comprovante.name}</span>
                  <button type="button" className="btn-ghost" style={{ color: "var(--red)" }} onClick={() => setComprovante(null)}><X size={12} /> Remover</button>
                </div>
              ) : <Dropzone accept="application/pdf,image/jpeg,image/png" label="Arraste o comprovante aqui ou clique para selecionar" hint="PDF, JPG ou PNG" onFiles={(f) => setComprovante(f[0] || null)} />}
            </div>
          )}
        </div>
        )}

        <div className="card">
          <p className="card-header mb-2">{modoFatura ? "Resumo das notas" : "Resumo do lote"}</p>
          <div className="flex flex-wrap gap-x-8 gap-y-1" style={{ fontSize: "0.85rem" }}>
            <span>Notas: <strong>{notas.length}</strong></span><span>Itens: <strong>{totalItens}</strong></span>
            <span>Total das notas: <strong style={{ fontVariantNumeric: "tabular-nums" }}>{formatBRL(totalNotas)}</strong></span>
          </div>
          {!modoFatura && <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-3">
            <div><label style={lbl} htmlFor="lote-tf">Total da fatura informado pelo fornecedor (opcional)</label>
              <CampoMoeda id="lote-tf" style={{ ...inputStyle, textAlign: "right" }} value={totalForn} onChange={setTotalForn} /></div>
          </div>}
          {!modoFatura && diferenca !== null && (
            <div style={aviso(diferenca === 0 ? "var(--green-light)" : "var(--red)")}>
              {diferenca === 0 ? "Confere com a fatura do fornecedor." : `Diferença de ${formatBRL(Math.abs(diferenca))}${diferenca > 0 ? " a menos nas notas" : " a mais nas notas"}. Revise antes de lançar.`}
            </div>
          )}
          {estocaveis.length > 0 && <div style={aviso("var(--amber)")}>{estocaveis.length} item(ns) estocável(is) darão entrada no estoque: {estocaveis.join(", ")}.</div>}
          {modoFatura ? (
            <div style={aviso("var(--border)")}>
              As notas entram na fatura <strong>{fatura!.rotulo}</strong>. {fatura!.parcelas_n ? `O parcelamento da fatura (${fatura!.parcelas_n}x) é aplicado a cada nota.` : "O vencimento e o parcelamento são definidos na fatura."}
            </div>
          ) : (
          <div style={aviso("var(--border)")}>
            Será criada a fatura <strong>{fornecedor ? `${fornecedor} — ${(notas.map((n) => n.data).filter(Boolean).sort()[0] || hoje()).slice(5, 7)}/${(notas.map((n) => n.data).filter(Boolean).sort()[0] || hoje()).slice(0, 4)}` : "do fornecedor"}</strong>,
            já {modo === "pago" ? "paga" : "fechada"}.
          </div>
          )}
        </div>
      </div>

      {erro && <div className="alert-critico mt-3"><AlertTriangle size={18} /><span>{erro}</span></div>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.84rem", marginTop: "0.7rem" }}>{sucesso}</p>}

      <div className="mt-3 flex items-center gap-3 flex-wrap">
        <button type="button" className="btn-primary" disabled={salvando} onClick={() => lancar()}><Check size={14} /> {salvando ? "Lançando…" : modoFatura ? "Lançar notas na fatura" : "Lançar lote (tudo ou nada)"}</button>
        <span style={{ fontSize: "0.74rem", color: "var(--text-muted)" }}>Se qualquer nota falhar, nada é gravado.</span>
      </div>

      {pendencia && (
        <div role="dialog" aria-modal="true" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" style={{ width: "560px", maxWidth: "95vw" }}>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle size={18} style={{ color: "var(--amber)" }} />
              <strong>{pendencia.tipo === "divergencia" ? "O total não confere com o fornecedor" : pendencia.tipo === "fora_periodo" ? "Nota fora do período da fatura" : "Notas que parecem já lançadas"}</strong></div>
            {pendencia.mensagem && <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "0.7rem" }}>{pendencia.mensagem}</p>}
            {pendencia.fora && (
              <>
                <ul style={{ fontSize: "0.8rem", paddingLeft: "1rem", marginBottom: "0.7rem" }}>
                  {pendencia.fora.map((d) => <li key={d.nota}>Nota {d.nota} ({d.data_emissao.split("-").reverse().join("/")}): {d.motivo}.</li>)}
                </ul>
                <p style={{ fontSize: "0.82rem", marginBottom: "0.7rem" }}>O que fazer com {pendencia.fora.length === 1 ? "essa nota" : "essas notas"}?</p>
              </>
            )}
            {pendencia.itens && (
              <ul style={{ fontSize: "0.8rem", paddingLeft: "1rem", marginBottom: "0.7rem" }}>
                {pendencia.itens.map((d) => <li key={d.nota}>Nota {d.nota} (nº {d.numero_documento}) já existe como {d.numero_lancamento}{d.data_emissao ? `, de ${d.data_emissao.split("-").reverse().join("/")}` : ""}, {formatBRL(d.valor_total || 0)}.</li>)}
              </ul>
            )}
            <div className="flex gap-3 flex-wrap">
              {pendencia.tipo === "fora_periodo" ? (
                <>
                  <button type="button" className="btn-primary" disabled={salvando} onClick={() => lancar({ foraPeriodo: "nesta" })}><Check size={14} /> Lançar nesta fatura</button>
                  <button type="button" className="btn-ghost" disabled={salvando} onClick={() => lancar({ foraPeriodo: "nova" })}>Abrir nova fatura</button>
                  <button type="button" className="btn-ghost" disabled={salvando} onClick={() => lancar({ foraPeriodo: "avulsa" })}>Lançar sem fatura</button>
                </>
              ) : (
                <button type="button" className="btn-primary" disabled={salvando}
                  onClick={() => lancar({ ...(pendencia.tipo === "divergencia" ? { divergencia: true } : { duplicados: true, divergencia: true }), foraPeriodo: escolhaFora.current })}><Check size={14} /> Lançar mesmo assim</button>
              )}
              <button type="button" className="btn-ghost" onClick={() => { escolhaFora.current = undefined; setPendencia(null); }}><X size={14} /> Voltar e revisar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
