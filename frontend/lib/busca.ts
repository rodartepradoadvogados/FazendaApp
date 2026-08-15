// Normalização de texto para BUSCA — nunca para exibição ou gravação.
//
// O valor mostrado na tela e salvo no banco continua com acento e maiúscula
// normais; só a COMPARAÇÃO ignora o que não deveria importar para achar um
// resultado: caixa alta/baixa, acento/cedilha, e hífen/underscore/espaço
// ("sal-mineral", "sal_mineral" e "sal mineral" devem casar com o termo
// digitado "salmineral", e vice-versa).
//
// Ponto ÚNICO para isso: antes desta função, cada tela reinventava sua
// própria normalização — algumas com `.toLowerCase()` puro (sem tratar
// acento nenhum), outras com uma cópia colada de `normalize("NFD") + regex`
// (repetida em ~10 arquivos diferentes, cada um com sua leve variação), sem
// nenhuma tratar hífen/underscore/espaço. Resultado: corrigir a busca de um
// campo (ex.: produto) não corrigia o irmão (ex.: serviço), porque cada tela
// tinha sua própria cópia da lógica. Buscas por texto do sistema devem
// importar daqui em vez de reescrever a normalização localmente.
export function normalizarBusca(texto: string | null | undefined): string {
  if (!texto) return "";
  return texto
    // NFD decompõe cada caractere acentuado em base + marca combinante
    // (ex.: "ç" -> "c" + ̧, "ã" -> "a" + ̃); ̀-ͯ cobre todas as
    // marcas diacríticas combinantes do Unicode, então removê-las depois do
    // NFD é o jeito padrão (sem biblioteca externa) de tirar acento/cedilha.
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    // Hífen, underscore e espaço não devem importar na comparação — só aqui,
    // no lado da busca; nunca no valor exibido/gravado.
    .replace(/[-_\s]+/g, "");
}

/**
 * True se `termo` (o que o usuário digitou) aparece em `alvo`, ignorando
 * caixa, acento/cedilha e hífen/underscore/espaço dos dois lados.
 *
 * Termo vazio (ou só espaços) sempre casa — é o padrão "busca vazia mostra
 * tudo" que praticamente todo picker/filtro de lista já espera, então
 * `casaBusca(item, busca)` substitui direto o `!busca || item.includes(busca)`
 * espalhado pelas telas.
 */
export function casaBusca(alvo: string | null | undefined, termo: string | null | undefined): boolean {
  const termoNormalizado = normalizarBusca(termo);
  if (!termoNormalizado) return true;
  return normalizarBusca(alvo).includes(termoNormalizado);
}
