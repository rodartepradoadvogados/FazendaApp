"use client";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  ClipboardList, Info, Heart, Stethoscope, Milk, Syringe, Wallet, Package, Baby, Scale,
  Trash2, Droplet, CalendarClock, Wheat, ArrowRightLeft, ShoppingCart, Skull, HeartPulse, Shield, Droplets, Dna, Gauge, ListChecks,
} from "lucide-react";
import { fetchAnimais, fetchEstoque, fetchServicosAnalise, fetchSanidade } from "@/lib/api";
import { RESPONSAVEIS } from "@/lib/constants";
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
import { IDADE_MIN_SERVICO } from "@/components/lancamentos/_shared";
// Formulários por tipo de lançamento (reprodutivo/produção/sanidade/dieta/
// estoque) — extraídos para components/lancamentos/*, mesmo motivo do bloco
// de dynamic() acima (code-splitting: só baixa o formulário da sub-aba aberta).
const FormProtocoloIatf = dynamic(() => import("@/components/lancamentos/FormProtocoloIatf").then((m) => m.FormProtocoloIatf), { ssr: false });
const FormInseminacao = dynamic(() => import("@/components/lancamentos/FormInseminacao").then((m) => m.FormInseminacao), { ssr: false });
const FormDiagnostico = dynamic(() => import("@/components/lancamentos/FormDiagnostico").then((m) => m.FormDiagnostico), { ssr: false });
const FormParto = dynamic(() => import("@/components/lancamentos/FormParto").then((m) => m.FormParto), { ssr: false });
const FormControle = dynamic(() => import("@/components/lancamentos/FormControle").then((m) => m.FormControle), { ssr: false });
const FormSanidade = dynamic(() => import("@/components/lancamentos/FormSanidade").then((m) => m.FormSanidade), { ssr: false });
const FormCalendarioSanitario = dynamic(() => import("@/components/lancamentos/FormCalendarioSanitario").then((m) => m.FormCalendarioSanitario), { ssr: false });
const FormPreventivoAplicacao = dynamic(() => import("@/components/lancamentos/FormPreventivoAplicacao").then((m) => m.FormPreventivoAplicacao), { ssr: false });
const BstLancamentoView = dynamic(() => import("@/components/lancamentos/FormProtocoloSanitario").then((m) => m.BstLancamentoView), { ssr: false });
const FormProtocoloSanitario = dynamic(() => import("@/components/lancamentos/FormProtocoloSanitario").then((m) => m.FormProtocoloSanitario), { ssr: false });
const FormAlimentacaoDieta = dynamic(() => import("@/components/lancamentos/FormAlimentacaoDieta").then((m) => m.FormAlimentacaoDieta), { ssr: false });
const FormEstoque = dynamic(() => import("@/components/lancamentos/FormEstoque").then((m) => m.FormEstoque), { ssr: false });
const FormAjusteSaldoEstoque = dynamic(() => import("@/components/lancamentos/FormAjusteSaldoEstoque").then((m) => m.FormAjusteSaldoEstoque), { ssr: false });
const FormProtocoloCustomizado = dynamic(() => import("@/components/lancamentos/FormProtocoloCustomizado").then((m) => m.FormProtocoloCustomizado), { ssr: false });

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

// Tipos de lançamento, agrupados: alguns grupos (Reprodutivo, Produção) têm uma
// camada inferior de sub-tipos, para economizar abas no menu.
// Ordem alfabética pelo label (ignorando acento), com "Excluir lançamento"
// sempre por último — não é alfabético de propósito (é a ação mais perigosa).
const TIPOS_GRUPOS = [
  { id: "alimentacao_dieta", label: "Alimentação", icon: Wheat, desc: "Dieta por lote: plano programado, real oferecido e histórico de abertura/encerramento.", leaf: "alimentacao_dieta" },
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
    id: "protocolo_customizado", label: "Protocolo personalizado", icon: ListChecks,
    desc: "Aplicar um protocolo personalizado (Cadastro > Protocolos personalizados) a animal(is), lote(s) ou como tarefa da fazenda.",
    leaf: "protocolo_customizado",
  },
  {
    id: "reprodutivo", label: "Reprodutivo", icon: Heart,
    desc: "Serviço/IA, diagnóstico de gestação ou parto/nascimento.",
    subs: [
      { id: "protocolo_iatf", label: "Protocolo IATF", icon: Heart, desc: "Agendar só o protocolo hormonal (D0/D7/D9/D11) na agenda — individual ou em lote." },
      { id: "inseminacao", label: "Inseminação", icon: Heart, desc: "Registrar a inseminação/cobertura em si — cio natural ou de um protocolo já agendado." },
      { id: "diagnostico", label: "Diagnóstico de gestação", icon: Stethoscope, desc: "Resultado do toque / diagnóstico de prenhez." },
      { id: "parto", label: "Parto / nascimento", icon: Baby, desc: "Registro de parto, da cria e do manejo de colostro." },
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
          { id: "sanidade_aplicacao", label: "Aplicações", icon: Syringe, desc: "Aplicação de medicamento curativo — por animal, categoria, vários animais ou lote." },
          { id: "protocolo_sanitario", label: "Protocolo sanitário", icon: ClipboardList, desc: "Aplicar um protocolo cadastrado (mastite e outros) a um animal — gera um evento na Agenda por dia (D1, D2...)." },
        ],
      },
      {
        id: "sanidade_preventiva", label: "Preventiva", icon: Shield,
        desc: "Manejo preventivo: aplicações preventivas e calendário sanitário.",
        subs: [
          { id: "preventivo_aplicacao", label: "Aplicações", icon: Syringe, desc: "Aplicar um preventivo (vacina/exame) a animais, categoria ou lote — registra e alimenta o calendário." },
          { id: "calendario_sanitario", label: "Calendário sanitário", icon: CalendarClock, desc: "Regra recorrente (sazonal/de rebanho ou por fase fisiológica): evento, frequência, produto e dosagem." },
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
  const [sujo, setSujo] = useState(false);
  // Contas a pagar também permite compra de sêmen — em vez de duplicar o
  // fluxo, reusa o mesmo formulário/endpoint de Lançamentos > Animais >
  // Compra/Venda > Comprar sêmen (mesma CompraSemen + baixa/soma de doses).
  const [despesaCompraSemen, setDespesaCompraSemen] = useState(false);
  // Atalho vindo da Agenda (ex.: "Ir para Inseminação" de um lembrete D11 de protocolo IATF).
  useEffect(() => {
    const ir = new URLSearchParams(window.location.search).get("ir");
    if (ir && TIPOS_LEAFS.some((t) => t.id === ir)) setSel(ir);
  }, []);
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
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItem[]>([]);
  const [servicos, setServicos] = useState<any[]>([]);
  const [produtosSanidade, setProdutosSanidade] = useState<string[]>([]);
  useEffect(() => {
    fetchAnimais().then(setAnimais).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchServicosAnalise().then((d) => setServicos(d.servicos || [])).catch(() => {});
    fetchSanidade().then((d) => setProdutosSanidade(Array.from(new Set((d.aplicacoes || d.registros || []).map((r: any) => r.produto).filter(Boolean))).sort() as string[])).catch(() => {});
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
  // Fêmeas aptas a serviço: idade >= 13 meses (mantém as sem idade informada, por segurança).
  const aptasServico = useMemo(() => animais.filter((a) => {
    const idade = (a as any).idade_meses;
    return idade == null || idade >= IDADE_MIN_SERVICO;
  }), [animais]);
  const tipo = TIPOS_LEAFS.find((t) => t.id === sel)!;

  // Piloto do drill-down: a Sidebar desenha esta árvore (grupo → sub-grupo →
  // folha) no lugar da lista de módulos enquanto Lançamentos estiver aberto.
  const subNavTree: SubNavNode[] = useMemo(() => TIPOS_GRUPOS.map((g) => ({
    id: g.leaf ?? g.id, label: g.label, icon: g.icon,
    children: g.grupos
      ? g.grupos.map((sg) => ({ id: sg.id, label: sg.label, icon: sg.icon, children: sg.subs.map(paraSubNavNode) }))
      : g.subs?.map(paraSubNavNode),
  })), []);
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
            <><strong style={{ color: "var(--text)" }}>Estoque já grava de verdade.</strong> Entradas e saídas lançadas aqui atualizam a quantidade do item na hora.</>
          ) : sel === "estoque_ajuste_saldo" ? (
            <><strong style={{ color: "var(--text)" }}>Ajuste de saldo já grava de verdade.</strong> Informe a quantidade que você contou de verdade no estoque — o sistema compara com o saldo cadastrado e lança sozinho a entrada ou a saída da diferença.</>
          ) : sel === "alimentacao_dieta" ? (
            <><strong style={{ color: "var(--text)" }}>Dieta já grava de verdade.</strong> Só uma dieta fica ativa por lote; ao encerrar, você pode lançar a próxima na hora. A data prevista de encerramento entra na Agenda para análise.</>
          ) : sel === "sanidade_aplicacao" ? (
            <><strong style={{ color: "var(--text)" }}>Sanidade já grava de verdade.</strong> Aceita vários produtos por lançamento; a baixa de estoque só acontece quando a unidade escolhida bate com a do estoque.</>
          ) : sel === "preventivo_aplicacao" ? (
            <><strong style={{ color: "var(--text)" }}>Preventivo já grava de verdade.</strong> Escolha o evento preventivo (vacina/exame), o lote/categoria e marque os animais — registra o calendário e, se for vacina/tratamento, a aplicação com baixa de estoque. Exame não baixa estoque.</>
          ) : sel === "calendario_sanitario" ? (
            <><strong style={{ color: "var(--text)" }}>Calendário sanitário já grava de verdade.</strong> Cada regra recorrente vira pendência na Agenda (dá baixa) e aparece na aba Sanidade &gt; Preventivo, com filtro por data e por evento.</>
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
          ) : sel === "protocolo_customizado" ? (
            <><strong style={{ color: "var(--text)" }}>Protocolo personalizado já grava de verdade.</strong> Gera um evento por dia do cronograma na Agenda — em animal(is), lote(s) ou como tarefa geral da fazenda (sem animal específico). O insumo sugerido é só informativo, sem baixa automática de estoque.</>
          ) : null}
        </p>
      </div>

      <div className="card" onChange={() => sel !== "exclusao" && setSujo(true)}>
        <div className="card-header mb-1 flex items-center gap-2"><tipo.icon size={14} /> {tipo.label}</div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0.4rem 0 1rem" }}>{tipo.desc}</p>
        {sel === "protocolo_iatf" && <FormProtocoloIatf animais={aptasServico} />}
        {sel === "inseminacao" && <FormInseminacao animais={aptasServico} />}
        {sel === "protocolo_customizado" && <FormProtocoloCustomizado animais={animais} />}
        {sel === "diagnostico" && <FormDiagnostico animais={animais} ultServico={ultServico} />}
        {sel === "parto" && <FormParto animais={animais} lotes={lotes} />}
        {sel === "controle" && <FormControle animais={animais} lotesLact={lotesLact} />}
        {sel === "pesagem" && <FormPesagemCorporal animais={animais} lotes={lotes} />}
        {sel === "secagem" && <FormSecagem animais={animais} estoque={estoque} produtos={produtosSanidade} />}
        {sel === "inducao_lactacao" && <FormInducaoLactacao animais={animais} />}
        {sel === "qualidade_leite" && <FormQualidadeLeite animais={animais} />}
        {sel === "entrega_leite" && <FormEntregaLeite />}
        {sel === "sanidade_aplicacao" && <FormSanidade animais={animais} lotes={lotes} estoque={estoque} produtos={produtosSanidade} />}
        {sel === "preventivo_aplicacao" && <FormPreventivoAplicacao animais={animais} lotes={lotes} estoque={estoque} />}
        {sel === "calendario_sanitario" && <FormCalendarioSanitario estoque={estoque} />}
        {sel === "bst" && <BstLancamentoView />}
        {sel === "protocolo_sanitario" && <FormProtocoloSanitario animais={animais} estoque={estoque} />}
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
              <FormFinanceiro tipo="despesa" responsaveis={RESPONSAVEIS} onSujo={setSujo} />
            )}
          </>
        )}
        {sel === "financeiro_receita" && <FormFinanceiro tipo="receita" responsaveis={RESPONSAVEIS} onSujo={setSujo} />}
        {sel === "estoque_entradas_saidas" && <FormEstoque estoque={estoque} onIrParaFinanceiro={irParaFinanceiroAposEstoque} />}
        {sel === "estoque_ajuste_saldo" && <FormAjusteSaldoEstoque estoque={estoque} />}
        {sel === "mover_animais" && <MovimentarAnimais />}
        {sel === "comprar_animal" && <CompraVendaAnimalForm modo="compra" animais={animais} />}
        {sel === "comprar_semen" && <CompraSemenForm />}
        {sel === "vender_animal" && <CompraVendaAnimalForm modo="venda" animais={animais} />}
        {sel === "baixar_animal" && <BaixarAnimal />}
        {sel === "alimentacao_dieta" && <FormAlimentacaoDieta />}
        {sel === "exclusao" && <FormExclusao />}
      </div>
    </div>
  );
}
