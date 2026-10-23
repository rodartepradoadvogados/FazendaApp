/**
 * Laço de conversa do Assistente, do lado do navegador.
 *
 * O backend pode responder `aguardando: [...]` quando o modelo pede para ver
 * ou operar a TELA (ferramentas `pagina_*`). Aqui essas ações são executadas na
 * aba do próprio usuário e o resultado volta ao backend, que continua a
 * resposta. Sem isso, a conversa ficaria parada esperando um Chromium que não
 * existe no servidor (ver lib/ferramentasPagina.ts).
 */
import { perguntarAssistente, type AssistenteResposta } from "./api";
import { executarPedido, type ResultadoPagina } from "./ferramentasPagina";

/** Teto de idas e voltas de tela numa pergunta — evita laço infinito de clique. */
export const MAX_VOLTAS_PAGINA = 6;

export type OpcoesConversa = {
  navegar: (caminho: string) => void;
  /** Chamado antes de cada ação na tela (para a interface mostrar "olhando a tela…"). */
  aoExecutarNaTela?: (pedidos: number) => void;
};

export async function conversar(
  mensagem: string,
  historico: AssistenteResposta["historico"],
  opcoes: OpcoesConversa,
): Promise<AssistenteResposta> {
  let r = await perguntarAssistente(mensagem, historico);

  for (let volta = 0; r.aguardando?.length && volta < MAX_VOLTAS_PAGINA; volta++) {
    opcoes.aoExecutarNaTela?.(r.aguardando.length);
    const resultados: ResultadoPagina[] = [];
    for (const pedido of r.aguardando) {
      resultados.push(await executarPedido(pedido, { navegar: opcoes.navegar }));
    }
    r = await perguntarAssistente("", r.historico, resultados);
  }

  if (r.aguardando?.length) {
    // Estourou o teto: devolve o que já existe, sem deixar o usuário sem resposta.
    return { ...r, resposta: r.resposta || "Não consegui concluir a navegação na tela — tente de novo." };
  }
  return r;
}
