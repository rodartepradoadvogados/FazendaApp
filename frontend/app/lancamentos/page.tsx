"use client";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  ClipboardList, Info, Heart, Stethoscope, Milk, Syringe, Wallet, Package, Baby, Scale,
  Trash2, Droplet, CalendarClock, Wheat, ArrowRightLeft, ShoppingCart, Skull, HeartPulse, Shield, Droplets, Dna, Gauge, Zap,
} from "lucide-react";
import { fetchAnimais, fetchEstoque, fetchServicosAnalise, fetchSanidade, fetchParametros } from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { AnimalRow } from "@/components/AnimalModal";
// Formulários grandes de cada sub-aba: dynamic() para que o navegador só baixe
// o código da sub-aba realmente aberta, em vez de tudo de uma vez com a página.
const FormFinanceiro = dynamic(() => import("@/components/FormFinanceiro").then((m) => m.FormFinanceiro), { ssr: false });
const FormExclusao = dynamic(() => import("@/components/FormExclusao").then((m) => m.FormExclusao), { ssr: false });
const FormPesagemCorporal = dynamic(() => import("@/components/FormPesagemCorporal").then((m) => m.FormPesagemCorporal), { ssr: false });
const MovimentarAnimais = dynamic(() => import("@/components/MovimentarAnimais"), { ssr: false });
const CompraVendaAnimalForm = dynamic(() => import("@/components/CompraVendaAnimalForm"), { ssr: false });
const CompraSemenForm = dynamic(() => import("@/components/CompraSemenForm"), { ssr: false });
const BaixarAnimal = dynamic(() => import("@/components/BaixarAnimal"), { ssr: false });
const FormSecagem = dynamic(() => import("@/components/FormSecagem").then((m) => m.FormSecagem), { ssr: false });
const FormQualidadeLeite = dynamic(() => import("@/components/FormQualidadeLeite").then((m) => m.FormQualidadeLeite), { ssr: false });
const FormEntregaLeite = dynamic(() => import("@/components/FormEntregaLeite").then((m) => m.FormEntregaLeite), { ssr: false });
const FormInducaoLactacao = dynamic(() => import("@/components/FormInducaoLactacao").then((m) => m.FormInducaoLactacao), { ssr: false });
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { type EstoqueItem } from "@/components/lancamentos/comumForms";
import { inaptidaoServico, useIdadeMinServico } from "@/components/lancamentos/_shared";
import { GavetaLancamento } from "@/components/lancamentos/GavetaLancamento";
// Formulários por tipo de lançamento (reprodutivo/produção/sanidade/dieta/
// estoque) — extraídos para components/lancamentos/*, mesmo motivo do bloco
// de dynamic() acima (code-splitting: só baixa o formulário da sub-aba aberta).
const FormProtocoloIatf = dynamic(() => import("@/components/lancamentos/FormProtocoloIatf").then((m) => m.FormProtocoloIatf), { ssr: false });
const FormInseminacao = dynamic(() => import("@/components/lancamentos/FormInseminacao").then((m) => m.FormInseminacao), { ssr: false });
const FormInducaoCio = dynamic(() => import("@/components/lancamentos/FormInducaoCio").then((m) => m.FormInducaoCio), { ssr: false });
const FormDiagnostico = dynamic(() => import("@/components/lancamentos/FormDiagnostico").then((m) => m.FormDiagnostico), { ssr: false });
const FormParto = dynamic(() => import("@/components/lancamentos/FormParto").then((m) => m.FormParto), { ssr: false });
const FormControle = dynamic(() => import("@/components/lancamentos/FormControle").then((m) => m.FormControle), { ssr: false });
const FormSanidade = dynamic(() => import("@/components/lancamentos/FormSanidade").then((m) => m.FormSanidade), { ssr: false });
const FormAplicarCalendarioSanitario = dynamic(() => import("@/components/lancamentos/FormAplicarCalendarioSanitario").then((m) => m.FormAplicarCalendarioSanitario), { ssr: false });
const FormPreventivoAplicacao = dynamic(() => import("@/components/lancamentos/FormPreventivoAplicacao").then((m) => m.FormPreventivoAplicacao), { ssr: false });
const BstLancamentoView = dynamic(() => import("@/components/lancamentos/FormProtocoloSanitario").then((m) => m.BstLancamentoView), { ssr: false });
const FormProtocoloSanitario = dynamic(() => import("@/components/lancamentos/FormProtocoloSanitario").then((m) => m.FormProtocoloSanitario), { ssr: false });
// A dieta em si (CadastrarNovaDieta) mudou de casa para Insumos e sanidade >
// Alimentação > "Lançar nova dieta" (ver app/alimentacao/page.tsx) — aqui
// ficou só o lançamento diário de consumo/sobra que consome essa dieta.
const ConsumoAlimento = dynamic(() => import("@/components/lancamentos/ConsumoAlimento").then((m) => m.ConsumoAlimento), { ssr: false });
const FormEstoque = dynamic(() => import("@/components/lancamentos/FormEstoque").then((m) => m.FormEstoque), { ssr: false });
const FormAjusteSaldoEstoque = dynamic(() => import("@/components/lancamentos/FormAjusteSaldoEstoque").then((m) => m.FormAjusteSaldoEstoque), { ssr: false });

/**
 * Tela de Lançamentos — entrada de dados operacionais no sistema.
 * Cada tipo (reprodutivo, produção, sanidade, financeiro, dieta, estoque,
 * exclusão) tem um formulário próprio que reage aos dados reais do rebanho
 * (selects, DEL automático, cálculos de colostro, cronograma de IATF) e
 * GRAVA de verdade no banco. A faixa informativa no topo de cada tipo
 * (ver "banner por tipo" no fim do arquivo) descreve o que cada lançamento faz.
 */

const cod = (g: string | null | undefined) => (g && /^\d\d/.test(g) ? g.slice(0, 2) : "");
const LACT = ["01", "02", "03"];

// Redesign "Cooperativa" (T2, mockup 1e) — sub-tipos que abrem numa gaveta
// lateral (~330px) em vez do card cheio de sempre: todo o conteúdo físico de
// components/lancamentos/* (reprodutivo, produção, sanidade, alimentação,
// estoque). Financeiro (T4, duas colunas — outro agente mexendo em paralelo)
// e os demais sub-tipos (Pesagem, Secagem, Indução de lactação, Qualidade do
// leite, Venda mensal, Animais, Excluir lançamento) ficam de fora de propósito
// — continuam exatamente como eram, no card cheio abaixo.
const GAVETA_LEAFS = new Set([
  "protocolo_iatf", "inseminacao", "diagnostico", "parto", "inducao_cio", "controle",
  "sanidade_aplicacao", "preventivo_aplicacao", "calendario_sanitario", "bst", "protocolo_sanitario",
  "alimentacao_dieta", "estoque_entradas_saidas", "estoque_ajuste_saldo",
]);

// Tipos de lançamento, agrupados: alguns grupos (Reprodutivo, Produção) têm uma
// camada inferior de sub-tipos, para economizar abas no menu.
// Ordem alfabética pelo label (ignorando acento), com "Excluir lançamento"
// sempre por último — não é alfabético de propósito (é a ação mais perigosa).
const TIPOS_GRUPOS = [
  { id: "alimentacao_dieta", label: "Alimentação", icon: Wheat, desc: "Consumo diário por lote (nº de animais ou kg direto) e sobra de cocho — só os alimentos da dieta ativa do lote.", leaf: "alimentacao_dieta" },
  {
    id: "animais", label: "Animais", icon: ArrowRightLeft,
    desc: "Movimentar animais entre lotes, comprar/vender ou dar baixa (morte/descarte).",
    subs: [
      { id: "mover_animais", label: "Movimentar animais", icon: ArrowRightLeft, desc: "Transferir um ou vários animais de lote." },
      {
        id: "compra_venda", label: "Compra / Venda", icon: ShoppingCart, desc: "Registrar a compra ou a venda de animal(is).",
        subs: [
          { id: "comprar_animal", label: "Comprar animal", icon: ShoppingCart, desc: "Registrar a compra de animal(is) — vendedor via fornecedor, conta gerencial restrita, GTA/ICMS, comissão de corretagem." },
          { id: "comprar_semen", label: "Comprar sêmen", icon: Dna, desc: "Registrar a compra de sêmen — touro já cadastrado ou do banco de dados NAAB, conta gerencial restrita (Sêmen); soma as doses ao estoque de sêmen." },
          { id: "vender_animal", label: "Vender animal", icon: ShoppingCart, desc: "Registrar a venda de animal(is) — comprador via cadastro, motivo/categoria(s) da venda, conta gerencial restrita, GTA/ICMS, comissão de corretagem." },
        ],
      },
      { id: "baixar_animal", label: "Baixa", icon: Skull, desc: "Registrar saída do rebanho: venda, morte, descarte ou marcar 'A descartar'." },
    ],
  },
  {
    id: "estoque", label: "Balanço de estoque", icon: Package,
    desc: "Entrada ou saída de item do estoque (balanço do saldo).",
    subs: [
      { id: "estoque_entradas_saidas", label: "Entradas/saídas", icon: Package, desc: "Entrada ou saída de item do estoque, um movimento por vez." },
      { id: "estoque_ajuste_saldo", label: "Ajuste de saldo atual", icon: Gauge, desc: "Corrigir o saldo para a quantidade real contada — o sistema calcula sozinho se é entrada ou saída." },
    ],
  },
  {
    id: "financeiro", label: "Financeiro", icon: Wallet,
    desc: "Lançamento de receita ou despesa.",
    subs: [
      { id: "financeiro_despesa", label: "Contas a pagar (despesa)", icon: Wallet, desc: "Lançamento de despesa/conta a pagar." },
      { id: "financeiro_receita", label: "Contas a receber (receita)", icon: Wallet, desc: "Lançamento de receita/conta a receber." },
    ],
  },
  {
    id: "producao", label: "Produção", icon: Milk,
    desc: "Controle leiteiro ou pesagem corporal.",
    subs: [
      { id: "controle", label: "Controle leiteiro", icon: Milk, desc: "Pesagem de leite por vaca ou por lote." },
      { id: "pesagem", label: "Pesagem corporal", icon: Scale, desc: "Peso vivo por animal ou por lote — acompanha o crescimento do rebanho." },
      { id: "secagem", label: "Secagem", icon: Droplet, desc: "Registro de secagem, motivo, ECC e produto(s) — sugere a mudança para o lote de secas." },
      { id: "inducao_lactacao", label: "Indução de lactação", icon: Syringe, desc: "Lança o protocolo de indução (18 ou 28 dias) em um ou vários animais — gera o cronograma completo na Agenda." },
      { id: "qualidade_leite", label: "Qualidade do leite", icon: Milk, desc: "CCS, CBT, gordura, proteína, sólidos totais e ESD — por vaca ou do tanque (rebanho em lactação)." },
      { id: "entrega_leite", label: "Venda mensal do leite", icon: Milk, desc: "Quantidade entregue ao laticínio no mês — compara com o controle leiteiro e a receita recebida." },
      { id: "bst", label: "BST", icon: Droplets, desc: "Somatotropina bovina — selecione os animais direto nas tabelas de Aptas/Incluir no próximo BST/Inaptas e lance (aplicar, agendar ou marcar inapta)." },
    ],
  },
  {
    id: "reprodutivo", label: "Reprodutivo", icon: Heart,
    desc: "Serviço/IA, diagnóstico de gestação ou parto/nascimento.",
    subs: [
      { id: "protocolo_iatf", label: "Protocolo IATF", icon: Heart, desc: "Agendar só o protocolo hormonal (D0/D7/D9/D11) na agenda — individual ou em lote." },
      { id: "inseminacao", label: "Inseminação", icon: Heart, desc: "Registrar a inseminação/cobertura em si — cio natural ou de um protocolo já agendado." },
      { id: "diagnostico", label: "Diagnóstico de gestação", icon: Stethoscope, desc: "Resultado do toque / diagnóstico de prenhez." },
      { id: "parto", label: "Parto / nascimento", icon: Baby, desc: "Registro de parto, da cria e do manejo de colostro." },
      { id: "inducao_cio", label: "Indução de cio", icon: Zap, desc: "Estímulo hormonal (PGF2α/Cloprostenol) para a vaca entrar em cio em 2 a 5 dias — sem misturar com protocolo IATF, inseminação ou diagnóstico." },
    ],
  },
  {
    id: "sanidade", label: "Sanitário", icon: HeartPulse,
    desc: "Tratamento curativo ou manejo preventivo.",
    grupos: [
      {
        id: "sanidade_curativa", label: "Curativa", icon: HeartPulse,
        desc: "Tratamento curativo: aplicações de medicamento e protocolos sanitários.",
        subs: [
          { id: "sanidade_aplicacao", label: "Avulso", icon: Syringe, desc: "Aplicação avulsa de medicamento curativo — por animal, categoria, vários animais ou lote." },
          { id: "protocolo_sanitario", label: "Protocolo sanitário", icon: ClipboardList, desc: "Aplicar um protocolo cadastrado (mastite e outros) a um animal — gera um evento na Agenda por dia (D1, D2...)." },
        ],
      },
      {
        id: "sanidade_preventiva", label: "Preventiva", icon: Shield,
        desc: "Manejo preventivo: aplicações preventivas e calendário sanitário.",
        subs: [
          { id: "preventivo_aplicacao", label: "Avulso", icon: Syringe, desc: "Aplicar um preventivo (vacina/exame) sem vínculo com um protocolo do calendário — por animal, categoria ou lote." },
          { id: "calendario_sanitario", label: "Calendário sanitário", icon: CalendarClock, desc: "Aplicar um protocolo já cadastrado no calendário (vacina ou exame) — escolha o protocolo e lance para os animais." },
        ],
      },
    ],
  },
  { id: "exclusao", label: "Excluir lançamento", icon: Trash2, desc: "Apagar um lançamento já salvo, com filtros e prévia de impacto.", leaf: "exclusao" },
];

// Um item de "subs" pode, por sua vez, ter os próprios "subs" (mais um nível
// de sub-aba — caso de Compra/Venda dentro de Animais) — achata recursivamente
// até sobrarem só as folhas de verdade (as que têm formulário próprio).
function achatarSubs(itens: any[]): any[] {
  return itens.flatMap((it) => (it.subs ? achatarSubs(it.subs) : [it]));
}

// Constrói o nó da árvore de sub-navegação recursivamente, para os itens que
// tiverem sub-abas próprias (mesmo caso acima).
function paraSubNavNode(it: any): SubNavNode {
  return { id: it.id, label: it.label, icon: it.icon, children: it.subs?.map(paraSubNavNode) };
}

// Lista achatada de sub-tipos (folhas), usada para saber qual formulário renderizar.
// Um grupo pode ter folhas direto (subs), estar sozinho (leaf) ou se ramificar em
// sub-grupos (grupos) — caso do Sanitário, que abre Curativa/Preventiva antes das folhas.
const TIPOS_LEAFS = TIPOS_GRUPOS.flatMap((g) =>
  g.grupos ? g.grupos.flatMap((sg) => achatarSubs(sg.subs)) : g.subs ? achatarSubs(g.subs) : [{ id: g.leaf!, label: g.label, icon: g.icon, desc: g.desc }]
);

export default function LancamentosPage() {
  const [sel, setSel] = useState("protocolo_iatf");
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  const [sujo, setSujo] = useState(false);
  // Gaveta lateral (T2, mockup 1e) — abre sozinha ao entrar/trocar para um dos
  // GAVETA_LEAFS; fechada, a tela só mostra a faixa "Abrir lançamento" no
  // lugar do formulário. `formKey` força o formulário a nascer de novo (só ao
  // clicar "Salvar e próximo" no rodapé, nunca sozinho, senão descartaria
  // trabalho em andamento) e `mensagemSalva` controla esse rodapé.
  const ehGaveta = GAVETA_LEAFS.has(sel);
  const [gavetaAberta, setGavetaAberta] = useState(false);
  const [formKey, setFormKey] = useState(0);
  const [mensagemSalva, setMensagemSalva] = useState<string | null>(null);
  useEffect(() => {
    setGavetaAberta(GAVETA_LEAFS.has(sel));
    setMensagemSalva(null);
  }, [sel]);
  const fecharGaveta = useCallback(() => {
    if (sujo && !window.confirm("Você tem certeza que quer sair dessa página? Os dados não salvos serão perdidos.")) return;
    setSujo(false);
    setMensagemSalva(null);
    setGavetaAberta(false);
  }, [sujo]);
  // Contas a pagar também permite compra de sêmen — em vez de duplicar o
  // fluxo, reusa o mesmo formulário/endpoint de Lançamentos > Animais >
  // Compra/Venda > Comprar sêmen (mesma CompraSemen + baixa/soma de doses).
  const [despesaCompraSemen, setDespesaCompraSemen] = useState(false);
  // Atalho vindo da Agenda (ex.: "Ir para Inseminação" de um lembrete D11 de protocolo IATF).
  useEffect(() => {
    const ir = new URLSearchParams(window.location.search).get("ir");
    if (ir && TIPOS_LEAFS.some((t) => t.id === ir)) setSel(ir);
  }, []);

  // modo_lancamento_alimentacao (Configurações > Parâmetros > Alimentação):
  // "nao_lancar" tira a aba de Alimentação do menu por completo (item D10) —
  // não é só esconder o formulário, é a aba mesma que não deve aparecer.
  const [modoAlimentacao, setModoAlimentacao] = useState<string | null>(null);
  useEffect(() => {
    fetchParametros()
      .then((d) => {
        const itens: any[] = d?.grupos?.alimentacao?.itens ?? [];
        setModoAlimentacao(String(itens.find((i) => i.chave === "modo_lancamento_alimentacao")?.valor ?? "fornecido_sobra"));
      })
      .catch(() => setModoAlimentacao("fornecido_sobra"));
  }, []);
  // Se a aba estava aberta e o parâmetro virou "nao_lancar" embaixo do
  // usuário (ou o link "ir=" de outra tela apontava pra cá), sai dela —
  // nunca deixa a tela de consumo visível com o modo desligado.
  useEffect(() => {
    if (sel === "alimentacao_dieta" && modoAlimentacao === "nao_lancar") setSel("protocolo_iatf");
  }, [sel, modoAlimentacao]);
  const trocarTipo = useCallback((novoId: string) => {
    if (novoId === sel) return;
    if (sujo && !window.confirm("Você tem certeza que quer sair dessa página? Os dados não salvos serão perdidos.")) return;
    setSujo(false);
    setSel(novoId);
  }, [sel, sujo]);
  // Redirecionamento pós-salvamento (ex.: Balanço de estoque → Financeiro com
  // "gerar movimentação financeira"): o balanço já foi salvo com sucesso, então
  // não é "sair com dados não salvos" — troca direto, sem o confirm de saída.
  const irParaFinanceiroAposEstoque = useCallback((leaf: "financeiro_despesa" | "financeiro_receita") => {
    setSujo(false);
    setSel(leaf);
  }, []);
  // Avisa também ao fechar a aba/recarregar/sair do site com dados não salvos.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => { if (sujo) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [sujo]);

  // "Sujo" genérico (fallback para os formulários que não sabem se avisar
  // sozinhos, como FormFinanceiro faz via `onSujo`): em vez de marcar sujo em
  // QUALQUER evento de mudança — o que nunca desmarcava, mesmo apagando tudo
  // de volta —, compara os campos do formulário atual contra o instantâneo
  // ("baseline") tirado assim que a sub-aba abriu. Valor padrão de nascença
  // (ex.: "Data do controle" já vem com hoje, "Modalidade" já vem com uma
  // opção marcada) não conta como trabalho do usuário — mesmo raciocínio do
  // caso do centro de custo em FormFinanceiro, só que aqui genérico, porque
  // a maioria dos formulários de Lançamentos não expõe seu próprio `sujo`.
  const cardRef = useRef<HTMLDivElement>(null);
  const baselineRef = useRef<string[]>([]);
  const valorDoCampo = (el: Element): string => {
    if (el instanceof HTMLInputElement) return el.type === "checkbox" || el.type === "radio" ? String(el.checked) : el.value;
    if (el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) return el.value;
    return "";
  };
  const capturarBaseline = useCallback(() => {
    const el = cardRef.current;
    baselineRef.current = el ? Array.from(el.querySelectorAll("input, textarea, select")).map(valorDoCampo) : [];
  }, []);
  // Recaptura a baseline sempre que a sub-aba muda — é o formulário NOVO que
  // acabou de nascer que serve de referência, nunca o antigo. Para as sub-abas
  // de gaveta, o formulário só existe de verdade quando ela está aberta (o
  // `{gavetaAberta && <Form.../>}` abaixo) e nasce de novo a cada `formKey` —
  // as duas entram nas dependências para recapturar no momento certo.
  useEffect(() => { capturarBaseline(); }, [sel, gavetaAberta, formKey, capturarBaseline]);
  const verificarSujo = useCallback(() => {
    if (sel === "exclusao") return;
    const el = cardRef.current;
    if (!el) return;
    const atuais = Array.from(el.querySelectorAll("input, textarea, select")).map(valorDoCampo);
    const mudou = atuais.length !== baselineRef.current.length || atuais.some((v, i) => v !== baselineRef.current[i]);
    setSujo(mudou);
  }, [sel]);

  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItem[]>([]);
  const [servicos, setServicos] = useState<any[]>([]);
  const [produtosSanidade, setProdutosSanidade] = useState<string[]>([]);
  const recarregarListasBase = useCallback(() => {
    fetchAnimais().then(setAnimais).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchServicosAnalise().then((d) => setServicos(d.servicos || [])).catch(() => {});
    fetchSanidade().then((d) => setProdutosSanidade(Array.from(new Set((d.aplicacoes || d.registros || []).map((r: any) => r.produto).filter(Boolean))).sort() as string[])).catch(() => {});
  }, []);
  useEffect(() => { recarregarListasBase(); }, [recarregarListasBase]);
  // Disparado por qualquer Form* da gaveta assim que salva com sucesso (prop
  // `onSalvo`) — mostra o rodapé "Salvar e próximo"/"Concluir" e já atualiza
  // as listas (saldo de estoque, animais) para o próximo lançamento em
  // sequência já refletir o que acabou de mudar.
  const aoSalvarNaGaveta = useCallback(() => {
    setMensagemSalva("Lançamento salvo com sucesso.");
    recarregarListasBase();
  }, [recarregarListasBase]);
  const salvarEProximo = useCallback(() => {
    setMensagemSalva(null);
    setSujo(false);
    setFormKey((k) => k + 1);
  }, []);
  const concluirGaveta = useCallback(() => {
    setMensagemSalva(null);
    setSujo(false);
    setGavetaAberta(false);
  }, []);

  // Última IA/cobertura por matriz (para o diagnóstico puxar automático).
  const ultServico = useMemo(() => {
    const m: Record<string, string> = {};
    servicos.forEach((s) => { if (s.numero && s.data && (!m[s.numero] || s.data > m[s.numero])) m[s.numero] = s.data; });
    return m;
  }, [servicos]);

  // Lotes: remove duplicados que diferem só por maiúscula/minúscula (ex.: "03 - Média"
  // e "03 - MÉDIA"), mantendo a versão em caixa-alta.
  const lotes = useMemo(() => {
    const porChave = new Map<string, string>();
    (animais.map((a) => a.grupo_primario).filter(Boolean) as string[]).forEach((l) => {
      const chave = l.toUpperCase();
      const atual = porChave.get(chave);
      if (!atual || l === l.toUpperCase()) porChave.set(chave, l === l.toUpperCase() ? l : atual || l);
    });
    return Array.from(porChave.values()).sort();
  }, [animais]);
  const lotesLact = useMemo(() => lotes.filter((l) => LACT.includes(cod(l))), [lotes]);
  // Aptidão a serviço: a lista passa a mostrar TODAS as fêmeas, com as
  // inaptas em cinza e o motivo ao lado (ver `motivosInaptidao` abaixo), em
  // vez de escondê-las.
  //
  // Antes, este bloco filtrava por `idade_meses >= 13` — um número cravado no
  // código do front, diferente do parâmetro real da fazenda (15 meses) e
  // inexistente no backend, que aceitava qualquer coisa que chegasse pela
  // API. A trava de verdade agora é do backend (409 com o motivo, ver
  // `backend/fazenda/rules/aptidao.py`); aqui só se ANTECIPA o veredito, com
  // o parâmetro de verdade, para o usuário não descobrir depois de preencher
  // o formulário inteiro. Sumir com a vaca da lista era pior que recusá-la:
  // não explicava nada e ainda parecia bug de cadastro.
  const idadeMinServico = useIdadeMinServico();
  const motivosInaptidao = useMemo(() => {
    const m = new Map<string, string>();
    animais.forEach((a) => {
      const i = inaptidaoServico(a, idadeMinServico);
      if (i) m.set(a.numero, i.rotulo);
    });
    return m;
  }, [animais, idadeMinServico]);
  const tipo = TIPOS_LEAFS.find((t) => t.id === sel)!;

  // Piloto do drill-down: a Sidebar desenha esta árvore (grupo → sub-grupo →
  // folha) no lugar da lista de módulos enquanto Lançamentos estiver aberto.
  // Alimentação some da árvore quando o modo de lançamento for "nao_lancar"
  // (item D10) — filtra aqui, no ponto único que a Sidebar de fato lê.
  const subNavTree: SubNavNode[] = useMemo(() => TIPOS_GRUPOS
    .filter((g) => !(g.id === "alimentacao_dieta" && modoAlimentacao === "nao_lancar"))
    .map((g) => ({
      id: g.leaf ?? g.id, label: g.label, icon: g.icon,
      children: g.grupos
        ? g.grupos.map((sg) => ({ id: sg.id, label: sg.label, icon: sg.icon, children: sg.subs.map(paraSubNavNode) }))
        : g.subs?.map(paraSubNavNode),
    })), [modoAlimentacao]);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: sel, onSelect: trocarTipo }), [subNavTree, sel, trocarTipo]));

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><ClipboardList size={22} style={{ color: "var(--dourado-light)" }} /> Lançamentos</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Entrada de dados direto no sistema — escolha o tipo e preencha.</p>
      </div>

      <div className="card mb-4" style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", background: "rgba(94,26,46,0.18)" }}>
        <Info size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          {sel === "financeiro_despesa" || sel === "financeiro_receita" ? (
            <><strong style={{ color: "var(--text)" }}>Financeiro já grava de verdade.</strong> Os lançamentos aqui vão para o banco permanente e aparecem nas 5 abas de contas do menu Financeiro.</>
          ) : sel === "controle" ? (
            <><strong style={{ color: "var(--text)" }}>Controle leiteiro já grava de verdade.</strong> As pesagens lançadas aqui vão para o banco permanente.</>
          ) : sel === "pesagem" ? (
            <><strong style={{ color: "var(--text)" }}>Pesagem corporal já grava de verdade.</strong> Os pesos lançados aqui vão para o banco permanente e alimentam o relatório de GMD/GPD logo abaixo.</>
          ) : sel === "exclusao" ? (
            <><strong style={{ color: "var(--text)" }}>Exclusão apaga de verdade.</strong> Administradores excluem na hora; os demais usuários só solicitam, e a exclusão fica pendente de aprovação.</>
          ) : sel === "diagnostico" ? (
            <><strong style={{ color: "var(--text)" }}>Diagnóstico já grava de verdade.</strong> Um resultado marcado para retoque entra na agenda automaticamente.</>
          ) : sel === "estoque_entradas_saidas" ? (
            <><strong style={{ color: "var(--text)" }}>Estoque já grava de verdade.</strong> Entradas e saídas lançadas aqui atualizam a quantidade do item na hora. Aqui é lugar de ajuste, cortesia ou lançamento que faltou — não de aplicação em animais nem de outros lançamentos, que têm sub-aba própria.</>
          ) : sel === "estoque_ajuste_saldo" ? (
            <><strong style={{ color: "var(--text)" }}>Ajuste de saldo já grava de verdade.</strong> Informe a quantidade que você contou de verdade no estoque — o sistema compara com o saldo cadastrado e lança sozinho a entrada ou a saída da diferença. Aqui é lugar de ajuste, cortesia ou lançamento que faltou — não de aplicação nem de outros lançamentos, que têm sub-aba própria.</>
          ) : sel === "alimentacao_dieta" ? (
            <><strong style={{ color: "var(--text)" }}>Consumo já grava de verdade.</strong> Dá baixa em estoque na hora. Só oferece os alimentos da dieta ativa do lote — fora da dieta ou sem saldo só entra se o cadastro do lote permitir.</>
          ) : sel === "sanidade_aplicacao" ? (
            <><strong style={{ color: "var(--text)" }}>Sanidade já grava de verdade.</strong> Aceita vários produtos por lançamento; a baixa de estoque só acontece quando a unidade escolhida bate com a do estoque.</>
          ) : sel === "preventivo_aplicacao" ? (
            <><strong style={{ color: "var(--text)" }}>Avulso já grava de verdade.</strong> Escolha o evento preventivo (vacina/exame), o lote/categoria e marque os animais — sem vínculo com um protocolo do calendário; se for vacina/tratamento, aplica com baixa de estoque. Exame não baixa estoque.</>
          ) : sel === "calendario_sanitario" ? (
            <><strong style={{ color: "var(--text)" }}>Calendário sanitário já grava de verdade.</strong> Aqui só se aplica um protocolo já cadastrado (Central de Protocolos &gt; Cadastro &gt; Sanitário &gt; Preventivo) — escolha-o, confira o resumo e lance para os animais.</>
          ) : sel === "bst" ? (
            <><strong style={{ color: "var(--text)" }}>BST — somatotropina bovina.</strong> Vacas aptas e excluídas do dia, com a próxima visita de BST.</>
          ) : sel === "protocolo_sanitario" ? (
            <><strong style={{ color: "var(--text)" }}>Protocolo sanitário já grava de verdade.</strong> Cria um evento na Agenda por etapa (D1, D2...) — ao marcar "realizado", dá baixa automática do produto no Estoque.</>
          ) : sel === "secagem" ? (
            <><strong style={{ color: "var(--text)" }}>Secagem já grava de verdade.</strong> Ao salvar, sugere mover a vaca para o lote das secas — você confirma antes da mudança.</>
          ) : sel === "inducao_lactacao" ? (
            <><strong style={{ color: "var(--text)" }}>Indução de lactação já grava de verdade.</strong> Gera um evento por dia do cronograma na Agenda — medicamentos com baixa automática de estoque, e uma observação de manejo (implante, adaptação na ordenha, iniciar a ordenha) visível para o funcionário.</>
          ) : sel === "qualidade_leite" ? (
            <><strong style={{ color: "var(--text)" }}>Qualidade do leite já grava de verdade.</strong> Lance por uma vaca ou pelo tanque (todas as vacas em lactação) — alimenta o relatório e o gráfico de qualidade em Produção.</>
          ) : sel === "entrega_leite" ? (
            <><strong style={{ color: "var(--text)" }}>Venda mensal já grava de verdade.</strong> Compara o controle leiteiro projetado do mês, a receita do laticínio e o que foi de fato entregue.</>
          ) : sel === "parto" ? (
            <><strong style={{ color: "var(--text)" }}>Parto/nascimento já grava de verdade.</strong> Cadastra a cria e sugere o lote de mãe e cria (confirmação antes de mover). Colostragem/IgG da 1ª cria também gravam — veja em Sanidade &gt; Relatório sanitário de bezerras.</>
          ) : sel === "protocolo_iatf" ? (
            <><strong style={{ color: "var(--text)" }}>Protocolo IATF já grava de verdade.</strong> Agenda só os passos hormonais (D0/D7/D9/D11) na Agenda — a inseminação em si é lançada à parte, na sub-aba Inseminação.</>
          ) : sel === "inseminacao" ? (
            <><strong style={{ color: "var(--text)" }}>Inseminação já grava de verdade.</strong> Registra a cobertura/IA (cio natural ou vinda de um protocolo IATF já agendado) e calcula a ordem/intervalo de tentativas.</>
          ) : sel === "inducao_cio" ? (
            <><strong style={{ color: "var(--text)" }}>Indução de cio já grava de verdade.</strong> Gera histórico (sem tocar em Servico/Protocolo IATF) e um lembrete "Observar cio" na Agenda entre 2 e 5 dias depois da aplicação — some sozinho assim que a inseminação for lançada.</>
          ) : null}
        </p>
      </div>

      {ehGaveta ? (
        <div className="card">
          <div className="card-header mb-1 flex items-center gap-2"><tipo.icon size={14} /> {tipo.label}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0.4rem 0 1rem" }}>{tipo.desc}</p>
          <button type="button" className="btn-primary" onClick={() => setGavetaAberta(true)}>
            <tipo.icon size={14} /> Abrir lançamento
          </button>
        </div>
      ) : (
        <div className="card" ref={cardRef} onChange={verificarSujo}>
          <div className="card-header mb-1 flex items-center gap-2"><tipo.icon size={14} /> {tipo.label}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0.4rem 0 1rem" }}>{tipo.desc}</p>
          {sel === "pesagem" && <FormPesagemCorporal animais={animais} lotes={lotes} />}
          {sel === "secagem" && <FormSecagem animais={animais} estoque={estoque} produtos={produtosSanidade} />}
          {sel === "inducao_lactacao" && <FormInducaoLactacao animais={animais} />}
          {sel === "qualidade_leite" && <FormQualidadeLeite animais={animais} />}
          {sel === "entrega_leite" && <FormEntregaLeite />}
          {sel === "financeiro_despesa" && (
            <>
              <div className="flex flex-wrap gap-2 mb-4">
                <button type="button" className={despesaCompraSemen ? "btn-secondary" : "btn-primary"} style={{ fontSize: "0.8rem" }}
                  onClick={() => setDespesaCompraSemen(false)}>
                  Lançamento genérico
                </button>
                <button type="button" className={despesaCompraSemen ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.8rem" }}
                  onClick={() => setDespesaCompraSemen(true)}>
                  Compra de sêmen
                </button>
              </div>
              {despesaCompraSemen ? (
                <>
                  <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "1rem" }}>
                    Mesmo formulário de Lançamentos &gt; Animais &gt; Compra/Venda &gt; Comprar sêmen — a compra soma as
                    doses no Estoque de sêmen e gera a conta a pagar (3.01.02.01 — Sêmen) automaticamente.
                  </p>
                  <CompraSemenForm />
                </>
              ) : (
                <FormFinanceiro tipo="despesa" responsaveis={nomesResponsaveis} onSujo={setSujo} />
              )}
            </>
          )}
          {sel === "financeiro_receita" && <FormFinanceiro tipo="receita" responsaveis={nomesResponsaveis} onSujo={setSujo} />}
          {sel === "mover_animais" && <MovimentarAnimais />}
          {sel === "comprar_animal" && <CompraVendaAnimalForm modo="compra" animais={animais} />}
          {sel === "comprar_semen" && <CompraSemenForm />}
          {sel === "vender_animal" && <CompraVendaAnimalForm modo="venda" animais={animais} />}
          {sel === "baixar_animal" && <BaixarAnimal />}
          {sel === "exclusao" && <FormExclusao />}
        </div>
      )}

      <GavetaLancamento
        aberto={ehGaveta && gavetaAberta}
        onFechar={fecharGaveta}
        titulo={tipo.label}
        icone={tipo.icon}
        mensagemSalva={mensagemSalva}
        onSalvarProximo={salvarEProximo}
        onConcluir={concluirGaveta}
      >
        {ehGaveta && gavetaAberta && (
          <div ref={cardRef} onChange={verificarSujo}>
            {sel === "protocolo_iatf" && <FormProtocoloIatf key={formKey} animais={animais} motivosInaptidao={motivosInaptidao} idadeMinServico={idadeMinServico} onSalvo={aoSalvarNaGaveta} />}
            {sel === "inseminacao" && <FormInseminacao key={formKey} animais={animais} motivosInaptidao={motivosInaptidao} idadeMinServico={idadeMinServico} onSalvo={aoSalvarNaGaveta} />}
            {sel === "diagnostico" && <FormDiagnostico key={formKey} animais={animais} ultServico={ultServico} onSalvo={aoSalvarNaGaveta} />}
            {sel === "parto" && <FormParto key={formKey} animais={animais} lotes={lotes} onSalvo={aoSalvarNaGaveta} />}
            {sel === "inducao_cio" && <FormInducaoCio key={formKey} animais={animais} estoque={estoque} motivosInaptidao={motivosInaptidao} onSalvo={aoSalvarNaGaveta} />}
            {sel === "controle" && <FormControle key={formKey} animais={animais} lotesLact={lotesLact} onSalvo={aoSalvarNaGaveta} />}
            {sel === "sanidade_aplicacao" && <FormSanidade key={formKey} animais={animais} lotes={lotes} estoque={estoque} produtos={produtosSanidade} onSalvo={aoSalvarNaGaveta} />}
            {sel === "preventivo_aplicacao" && <FormPreventivoAplicacao key={formKey} animais={animais} lotes={lotes} estoque={estoque} onSalvo={aoSalvarNaGaveta} />}
            {sel === "calendario_sanitario" && <FormAplicarCalendarioSanitario key={formKey} animais={animais} lotes={lotes} estoque={estoque} onSalvo={aoSalvarNaGaveta} />}
            {sel === "bst" && <BstLancamentoView key={formKey} />}
            {sel === "protocolo_sanitario" && <FormProtocoloSanitario key={formKey} animais={animais} estoque={estoque} onSalvo={aoSalvarNaGaveta} />}
            {sel === "alimentacao_dieta" && <ConsumoAlimento key={formKey} onSalvo={aoSalvarNaGaveta} />}
            {sel === "estoque_entradas_saidas" && <FormEstoque key={formKey} estoque={estoque} onIrParaFinanceiro={irParaFinanceiroAposEstoque} onSalvo={aoSalvarNaGaveta} />}
            {sel === "estoque_ajuste_saldo" && <FormAjusteSaldoEstoque key={formKey} estoque={estoque} onSalvo={aoSalvarNaGaveta} />}
          </div>
        )}
      </GavetaLancamento>
    </div>
  );
}
