/**
 * Executor das ferramentas `pagina_*` do Assistente — roda AQUI, no navegador
 * de quem perguntou, e não num Chromium no servidor.
 *
 * Por quê (decisão de 22/10/2026, depois de checar as premissas do plano de
 * MCP): o backend fica no Railway e o Hermes na VPS, então não existe
 * `localhost` entre eles; `hermes mcp serve` exporta conversas, não
 * ferramentas de browser; e um browser no servidor navegaria com a sessão de
 * quem configurou o vault — qualquer funcionário veria as telas do dono. Aqui
 * a sessão é sempre a de quem perguntou, sem Chromium e sem custo.
 *
 * O backend devolve `aguardando: [{id, nome, argumentos}]`, este módulo executa
 * no DOM da aba atual e o resultado volta em `resultados_pagina`. Ver
 * backend/fazenda/rules/ferramentas_pagina.py.
 */

export type PedidoPagina = {
  id: string;
  nome: string;
  argumentos: Record<string, unknown>;
};

export type ResultadoPagina = {
  id: string;
  resultado: { ok: boolean; [chave: string]: unknown };
};

export type OpcoesExecucao = {
  /** Navegação do app (router.push do next/navigation) — quem chama fornece. */
  navegar: (caminho: string) => void;
};

const ESPERA_PADRAO_MS = 8000;

function texto(valor: unknown, padrao = ""): string {
  return typeof valor === "string" && valor.trim() ? valor.trim() : padrao;
}

function numero(valor: unknown, padrao: number, minimo: number, maximo: number): number {
  const n = typeof valor === "number" && Number.isFinite(valor) ? valor : padrao;
  return Math.min(maximo, Math.max(minimo, n));
}

function achar(seletor: string): Element | null {
  try {
    return document.querySelector(seletor);
  } catch {
    return null; // seletor inválido: quem chamou recebe erro tratado
  }
}

function dormir(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Espera o seletor existir (para tela que carrega em pedaços). */
async function esperarSeletor(seletor: string, timeoutMs: number): Promise<Element | null> {
  const limite = Date.now() + timeoutMs;
  for (;;) {
    const el = achar(seletor);
    if (el) return el;
    if (Date.now() >= limite) return null;
    await dormir(100);
  }
}

/** Texto visível, sem script/style, quebrado em linhas legíveis. */
function textoVisivel(el: Element): string {
  const clone = el.cloneNode(true) as Element;
  clone.querySelectorAll("script,style,noscript").forEach((n) => n.remove());
  const bruto = (clone as HTMLElement).innerText ?? clone.textContent ?? "";
  return bruto
    .split("\n")
    .map((l) => l.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
}

function preencherCampo(el: Element, valor: string): void {
  const campo = el as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
  const prototipo =
    campo instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : campo instanceof HTMLSelectElement
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototipo, "value")?.set;
  // Setter nativo: sem ele, frameworks controlados (React) não percebem a mudança.
  if (setter) setter.call(campo, valor);
  else campo.value = valor;
  campo.dispatchEvent(new Event("input", { bubbles: true }));
  campo.dispatchEvent(new Event("change", { bubbles: true }));
}

async function aguardarTela(caminho: string): Promise<boolean> {
  const limite = Date.now() + 6000;
  for (;;) {
    const mesmoCaminho = window.location.pathname.startsWith(caminho.split("?")[0]);
    if (mesmoCaminho && document.readyState !== "loading" && achar("main, [role=main]")) return true;
    if (Date.now() >= limite) return mesmoCaminho;
    await dormir(120);
  }
}

/** Rótulos que indicam ação destrutiva ou de gravação: o assistente olha e
 * preenche, mas quem exclui, cancela ou salva é a pessoa. */
const ROTULO_BLOQUEADO =
  /\b(exclu\w*|apag\w*|remov\w*|delet\w*|descart\w*|zerar|encerr\w*|desativ\w*|inativ\w*|cancel\w*|sair|logout|salvar|gravar|confirmar|finaliz\w*|lan[cç]ar|registrar|enviar|assinar|pagar|baixar)\b/i;

function rotuloDoElemento(el: Element): string {
  const h = el as HTMLElement;
  return [h.innerText, h.getAttribute("aria-label"), h.getAttribute("title"), (h as HTMLInputElement).value]
    .filter((t): t is string => typeof t === "string")
    .join(" ")
    .slice(0, 200);
}

/** Motivo do bloqueio de um clique, ou null se pode clicar. */
export function motivoBloqueioClique(el: Element): string | null {
  const alvo = el.closest("button, a, [role=button], input[type=submit], input[type=button]") ?? el;
  if ((alvo as HTMLElement).dataset?.destrutivo !== undefined) return "ação destrutiva";
  if ((alvo as HTMLInputElement).type === "submit") return "botão que grava dados";
  if (ROTULO_BLOQUEADO.test(rotuloDoElemento(alvo))) return "ação destrutiva ou de gravação";
  return null;
}

/** Enter só em campo de busca: em formulário comum equivale a salvar. */
export function podeEnviarComEnter(el: Element): boolean {
  const h = el as HTMLInputElement;
  const marca = `${h.type ?? ""} ${h.name ?? ""} ${h.getAttribute?.("role") ?? ""} ${h.getAttribute?.("aria-label") ?? ""} ${h.placeholder ?? ""}`;
  return /search|busca|pesquis|filtr/i.test(marca);
}

/** Executa UM pedido. Nunca lança: erro vira `resultado.ok = false`. */
export async function executarPedido(
  pedido: PedidoPagina,
  opcoes: OpcoesExecucao,
): Promise<ResultadoPagina> {
  const args = pedido.argumentos ?? {};
  try {
    switch (pedido.nome) {
      case "pagina_info":
        return {
          id: pedido.id,
          resultado: {
            ok: true,
            caminho: window.location.pathname + window.location.search,
            titulo: document.title,
            carregada: document.readyState === "complete",
          },
        };

      case "pagina_navegar": {
        const caminho = texto(args.caminho);
        // Mesma regra do backend: só caminho interno.
        if (!caminho.startsWith("/") || caminho.startsWith("//")) {
          return { id: pedido.id, resultado: { ok: false, erro: "caminho interno inválido" } };
        }
        opcoes.navegar(caminho);
        const chegou = await aguardarTela(caminho);
        return {
          id: pedido.id,
          resultado: {
            ok: chegou,
            caminho: window.location.pathname,
            titulo: document.title,
            ...(chegou ? {} : { erro: "a tela não terminou de carregar a tempo" }),
          },
        };
      }

      case "pagina_ler": {
        const seletor = texto(args.seletor, "main");
        const limite = numero(args.limite, 4000, 100, 20000);
        const el = await esperarSeletor(seletor, 4000);
        if (!el) {
          return { id: pedido.id, resultado: { ok: false, erro: `não achei '${seletor}' na tela` } };
        }
        const conteudo = textoVisivel(el).slice(0, limite);
        return {
          id: pedido.id,
          resultado: { ok: true, seletor, caminho: window.location.pathname, texto: conteudo, truncado: conteudo.length >= limite },
        };
      }

      case "pagina_clicar": {
        const seletor = texto(args.seletor);
        const el = await esperarSeletor(seletor, 4000);
        if (!el) return { id: pedido.id, resultado: { ok: false, erro: `não achei '${seletor}'` } };
        const bloqueio = motivoBloqueioClique(el);
        if (bloqueio) {
          return {
            id: pedido.id,
            resultado: { ok: false, erro: `clique bloqueado (${bloqueio}); peça para o usuário fazer isso` },
          };
        }
        (el as HTMLElement).click();
        await dormir(400);
        return { id: pedido.id, resultado: { ok: true, seletor, caminho: window.location.pathname } };
      }

      case "pagina_preencher": {
        const seletor = texto(args.seletor);
        const el = await esperarSeletor(seletor, 4000);
        if (!el) return { id: pedido.id, resultado: { ok: false, erro: `não achei '${seletor}'` } };
        if ((el as HTMLInputElement).type === "password" || (el as HTMLInputElement).type === "file") {
          return { id: pedido.id, resultado: { ok: false, erro: "este tipo de campo não pode ser preenchido pelo assistente" } };
        }
        preencherCampo(el, texto(args.valor));
        if (args.enviar === true && !podeEnviarComEnter(el)) {
          return { id: pedido.id, resultado: { ok: false, erro: "Enter bloqueado: só em campo de busca/filtro" } };
        }
        if (args.enviar === true) {
          const campo = el as HTMLElement;
          campo.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
          campo.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
        }
        await dormir(300);
        return { id: pedido.id, resultado: { ok: true, seletor } };
      }

      case "pagina_esperar": {
        const seletor = texto(args.seletor);
        const timeout = numero(args.timeout_ms, ESPERA_PADRAO_MS, 100, 30000);
        const el = await esperarSeletor(seletor, timeout);
        return {
          id: pedido.id,
          resultado: el ? { ok: true, seletor } : { ok: false, erro: `'${seletor}' não apareceu em ${timeout}ms` },
        };
      }

      default:
        return { id: pedido.id, resultado: { ok: false, erro: `ferramenta desconhecida: ${pedido.nome}` } };
    }
  } catch (e: unknown) {
    return {
      id: pedido.id,
      resultado: { ok: false, erro: e instanceof Error ? e.message : "falha ao executar na tela" },
    };
  }
}
