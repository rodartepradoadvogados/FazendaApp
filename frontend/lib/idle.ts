// Logout automático por inatividade (15 minutos sem mexer no site/app) — por
// segurança (não deixa os dados da fazenda expostos numa tela aberta) e para
// o controle de acessos do proprietário (ver Configurações > Cadastro > Usuários).
//
// A última atividade é guardada no localStorage (não só em memória) porque no
// app móvel instalado o navegador pode suspender os timers em JS quando a
// aba/app vai para segundo plano — ao voltar (`visibilitychange`), checamos
// na hora se já passou do limite, em vez de confiar só no setInterval.
import { getToken, logout, manterConectadoAtivo } from "./api";

const CHAVE_ULTIMA_ATIVIDADE = "ultima_atividade_ts";
export const LIMITE_INATIVIDADE_MS = 15 * 60 * 1000; // 15 minutos
const INTERVALO_VERIFICACAO_MS = 20 * 1000;
const EVENTOS_ATIVIDADE = ["mousemove", "mousedown", "keydown", "touchstart", "scroll", "wheel"] as const;

function marcarAtividade() {
  try { localStorage.setItem(CHAVE_ULTIMA_ATIVIDADE, String(Date.now())); } catch { /* ignore */ }
}

function inativoDemais(): boolean {
  try {
    const ultima = Number(localStorage.getItem(CHAVE_ULTIMA_ATIVIDADE) || 0);
    return ultima > 0 && Date.now() - ultima > LIMITE_INATIVIDADE_MS;
  } catch { return false; }
}

/** Liga o monitor de inatividade; retorna a função de limpeza (chamar no cleanup do useEffect). */
export function iniciarMonitorInatividade(): () => void {
  if (typeof window === "undefined" || !getToken()) return () => {};
  // "Manter conectado neste aparelho" promete só pedir login de novo se a
  // pessoa sair, desinstalar o app ou desmarcar a opção (ver comentário em
  // backend/fazenda/auth.py::TOKEN_VALIDADE_LONGA_S) — deslogar por
  // inatividade quebraria essa promessa toda vez que o celular ficasse mais
  // de 15 min no bolso entre uma tarefa e outra da fazenda.
  if (manterConectadoAtivo()) return () => {};
  marcarAtividade();

  // Throttle simples: não regrava a cada pixel de mousemove.
  let ultimoRegistro = 0;
  const aoInteragir = () => {
    const agora = Date.now();
    if (agora - ultimoRegistro > 2000) { ultimoRegistro = agora; marcarAtividade(); }
  };
  EVENTOS_ATIVIDADE.forEach((ev) => window.addEventListener(ev, aoInteragir, { passive: true }));

  const verificar = () => { if (getToken() && inativoDemais()) logout(); };
  const intervalo = window.setInterval(verificar, INTERVALO_VERIFICACAO_MS);

  // Ao voltar de segundo plano (app móvel suspenso, aba trocada), verifica na hora.
  const aoVoltarVisivel = () => { if (document.visibilityState === "visible") verificar(); };
  document.addEventListener("visibilitychange", aoVoltarVisivel);

  return () => {
    EVENTOS_ATIVIDADE.forEach((ev) => window.removeEventListener(ev, aoInteragir));
    document.removeEventListener("visibilitychange", aoVoltarVisivel);
    window.clearInterval(intervalo);
  };
}
