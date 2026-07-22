"use client";
// Ponte entre Sanitário Preventivo/Reprodução (diagnóstico de gestação) e o
// Lançamento financeiro — ao escolher, no popup de vínculo pós-salvar, "1)
// lançar este evento em contas a pagar", a tela de Financeiro > Contas a
// pagar escuta este evento e abre já preenchida com os dados pertinentes do
// evento de origem (produto/serviço, data, responsável), faltando só o que é
// exclusivo do financeiro (valor, pagamento, parcelamento). Ao salvar, o
// próprio formulário vincula de volta o lançamento criado ao evento de
// origem (ver POST /financeiro/vincular-evento-sanitario-reprodutivo).
// Mesmo padrão "sticky" de estoqueFinanceiroBridge.ts — mas, diferente dele,
// o gatilho (Sanitário Preventivo, Diagnóstico de gestação) e o destino
// (Financeiro > Contas a pagar) costumam viver em sub-abas distintas da
// navegação drill-down, alcançadas via navegação de página inteira (mesmo
// padrão do botão "Lançar financeiro" já existente em app/sanidade/page.tsx),
// não troca de aba em memória — por isso o pedido também é persistido em
// sessionStorage, sobrevivendo ao reload completo da página.
export type OrigemVinculoSanitarioReprodutivo = {
  tipo: "sanidade" | "exame" | "servico";
  ids: number[];
  produto: string;
  data_emissao?: string;
  responsavel?: string | null;
};

const EVT = "fazenda:ir-lancamento-financeiro-de-evento-sanitario-reprodutivo";
const CHAVE_SESSION = "fazenda_pedido_lancamento_de_evento";
let pendente: OrigemVinculoSanitarioReprodutivo | null = null;

export function pedirLancamentoFinanceiroDeEvento(dados: OrigemVinculoSanitarioReprodutivo) {
  pendente = dados;
  try { sessionStorage.setItem(CHAVE_SESSION, JSON.stringify(dados)); } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent<OrigemVinculoSanitarioReprodutivo>(EVT, { detail: dados }));
}

export function onPedidoLancamentoFinanceiroDeEvento(cb: (dados: OrigemVinculoSanitarioReprodutivo) => void) {
  let dados = pendente;
  if (!dados) {
    try {
      const raw = sessionStorage.getItem(CHAVE_SESSION);
      if (raw) dados = JSON.parse(raw);
    } catch { /* ignore */ }
  }
  if (dados) {
    pendente = null;
    try { sessionStorage.removeItem(CHAVE_SESSION); } catch { /* ignore */ }
    cb(dados);
  }
  const handler = (e: Event) => cb((e as CustomEvent<OrigemVinculoSanitarioReprodutivo>).detail);
  window.addEventListener(EVT, handler);
  return () => window.removeEventListener(EVT, handler);
}
