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
const EVT_ALIMENTO_REABRIR = "fazenda:reabrir-cadastro-alimento";
const CHAVE_ESTOQUE = "fazenda:pendente-cadastro-estoque";
const CHAVE_ALIMENTO = "fazenda:pendente-cadastro-alimento";
const CHAVE_ALIMENTO_REABRIR = "fazenda:pendente-reabrir-alimento";

// As duas telas são abas MUTUAMENTE EXCLUSIVAS de Cadastro.tsx (`aba === X &&
// <Componente />`) — a tela de destino não está montada ainda no instante em
// que o evento é disparado (só Cadastro.tsx, o pai, está sempre montado, e só
// ele troca a aba externa). Um CustomEvent puro se perderia nesse intervalo:
// ninguém do lado de lá está ouvindo até a aba trocar e o componente montar.
// Por isso o dado also fica em sessionStorage — a tela de destino lê e
// consome (uma vez) no PRÓPRIO mount, sem depender de estar ouvindo no
// instante exato do disparo. O CustomEvent continua disparado, útil só para
// o caso raro de a tela de destino já estar montada.
function guardarPendente(chave: string, dados: unknown) {
  try { sessionStorage.setItem(chave, JSON.stringify(dados)); } catch {}
}
function lerEConsumirPendente<T>(chave: string): T | null {
  try {
    const bruto = sessionStorage.getItem(chave);
    if (!bruto) return null;
    sessionStorage.removeItem(chave);
    return JSON.parse(bruto) as T;
  } catch {
    return null;
  }
}

export function pedirCadastroDeEstoque(dados: PrefillNovoEstoque) {
  guardarPendente(CHAVE_ESTOQUE, dados);
  window.dispatchEvent(new CustomEvent<PrefillNovoEstoque>(EVT_ESTOQUE, { detail: dados }));
}
export function consumirCadastroDeEstoquePendente(): PrefillNovoEstoque | null {
  return lerEConsumirPendente<PrefillNovoEstoque>(CHAVE_ESTOQUE);
}
export function onPedidoCadastroDeEstoque(cb: (dados: PrefillNovoEstoque) => void) {
  const handler = (e: Event) => cb((e as CustomEvent<PrefillNovoEstoque>).detail);
  window.addEventListener(EVT_ESTOQUE, handler);
  return () => window.removeEventListener(EVT_ESTOQUE, handler);
}

export function pedirCadastroDeAlimento(dados: PrefillNovoAlimento) {
  guardarPendente(CHAVE_ALIMENTO, dados);
  window.dispatchEvent(new CustomEvent<PrefillNovoAlimento>(EVT_ALIMENTO, { detail: dados }));
}
export function consumirCadastroDeAlimentoPendente(): PrefillNovoAlimento | null {
  return lerEConsumirPendente<PrefillNovoAlimento>(CHAVE_ALIMENTO);
}
export function onPedidoCadastroDeAlimento(cb: (dados: PrefillNovoAlimento) => void) {
  const handler = (e: Event) => cb((e as CustomEvent<PrefillNovoAlimento>).detail);
  window.addEventListener(EVT_ALIMENTO, handler);
  return () => window.removeEventListener(EVT_ALIMENTO, handler);
}

// Depois de criar um item de Estoque já vinculado a um Alimento existente
// (botão "Cadastrar novo item de estoque vinculado"), volta sozinho pra tela
// do Alimento de origem, já reaberto em edição com a lista de vinculados
// atualizada — sem isso, o usuário ficava com a sessão de edição perdida (a
// troca de aba desmonta CadastroAlimentacao) e nenhum jeito de ver que o
// vínculo deu certo sem sair e voltar manualmente.
export function pedirReaberturaDeAlimento(alimentoId: number) {
  guardarPendente(CHAVE_ALIMENTO_REABRIR, alimentoId);
  window.dispatchEvent(new CustomEvent<number>(EVT_ALIMENTO_REABRIR, { detail: alimentoId }));
}
export function consumirReaberturaDeAlimentoPendente(): number | null {
  return lerEConsumirPendente<number>(CHAVE_ALIMENTO_REABRIR);
}
export function onPedidoReaberturaDeAlimento(cb: (alimentoId: number) => void) {
  const handler = (e: Event) => cb((e as CustomEvent<number>).detail);
  window.addEventListener(EVT_ALIMENTO_REABRIR, handler);
  return () => window.removeEventListener(EVT_ALIMENTO_REABRIR, handler);
}
