"use client";
// Ponte entre o cadastro de Alimento (Configurações > Cadastro > Alimentação
// > Alimentos) e o cadastro de item de Estoque (...> Itens de estoque) —
// telas irmãs, cada uma dona do próprio estado de aba/formulário. Em vez de
// levantar tudo para o componente pai (Cadastro.tsx), a conversão "vira
// produto de estoque"/"vira alimento" dispara um evento no window com os
// dados extraíveis; a tela de destino escuta e abre o formulário já
// preenchido, e o Cadastro.tsx escuta só para trocar a aba externa.
export type PrefillNovoEstoque = { nome: string; finalidade?: string; alimentoId?: number };
export type PrefillNovoAlimento = { nome: string; estoqueId?: number };

const EVT_ESTOQUE = "fazenda:ir-cadastro-estoque";
const EVT_ALIMENTO = "fazenda:ir-cadastro-alimento";

export function pedirCadastroDeEstoque(dados: PrefillNovoEstoque) {
  window.dispatchEvent(new CustomEvent<PrefillNovoEstoque>(EVT_ESTOQUE, { detail: dados }));
}
export function onPedidoCadastroDeEstoque(cb: (dados: PrefillNovoEstoque) => void) {
  const handler = (e: Event) => cb((e as CustomEvent<PrefillNovoEstoque>).detail);
  window.addEventListener(EVT_ESTOQUE, handler);
  return () => window.removeEventListener(EVT_ESTOQUE, handler);
}

export function pedirCadastroDeAlimento(dados: PrefillNovoAlimento) {
  window.dispatchEvent(new CustomEvent<PrefillNovoAlimento>(EVT_ALIMENTO, { detail: dados }));
}
export function onPedidoCadastroDeAlimento(cb: (dados: PrefillNovoAlimento) => void) {
  const handler = (e: Event) => cb((e as CustomEvent<PrefillNovoAlimento>).detail);
  window.addEventListener(EVT_ALIMENTO, handler);
  return () => window.removeEventListener(EVT_ALIMENTO, handler);
}
