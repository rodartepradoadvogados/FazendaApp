// Cache de leitura da Agenda (sessionStorage) para a 1ª dobra aparecer JÁ com os
// dados da última visita, enquanto a rede atualiza por baixo (sem skeleton).
// Só vale para o mesmo dia e a mesma conta; qualquer falha do storage é ignorada.
const LIMITE = 1_500_000; // ~1,5 MB por visão

function chave(visao: string, dia: string): string | null {
  try {
    const conta = window.localStorage.getItem("conta_ativa") || "0";
    return `agenda2:${conta}:${visao}:${dia}`;
  } catch { return null; }
}

export function lerCacheAgenda(visao: string, dia: string): any | null {
  const k = chave(visao, dia);
  if (!k) return null;
  try {
    const bruto = window.sessionStorage.getItem(k);
    return bruto ? JSON.parse(bruto) : null;
  } catch { return null; }
}

export function gravarCacheAgenda(visao: string, dia: string, dados: any): void {
  const k = chave(visao, dia);
  if (!k) return;
  try {
    const txt = JSON.stringify(dados);
    if (txt.length <= LIMITE) window.sessionStorage.setItem(k, txt);
  } catch { /* storage cheio ou bloqueado: segue sem cache */ }
}
