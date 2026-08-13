// Sinalizador de navegação "vim do portal Administração" — usado só para o
// link "Voltar" de Painel CowData e Painel do Contador saber para onde
// voltar. Os dois têm casca própria (bespoke), fora de InsightsLayout.tsx,
// então não dá para decidir isso só pela rota atual: o mesmo /painel-cowdata
// é alcançado tanto pelo portal Administração (aba "Painel CowData", clique
// dentro da mesma guia do navegador) quanto por login direto da Equipe
// CowData (login/page.tsx) ou pelo Menu do app (app/app/menu/page.tsx) — nos
// dois últimos casos "voltar" continua sendo a fazenda/app, não Administração.
//
// sessionStorage (não query param) de propósito: não suja a URL nem exige
// Suspense boundary (useSearchParams em layout estático quebraria o build —
// ver app/redefinir-senha/page.tsx para o padrão que isso exigiria). Setado
// no clique da aba (InsightsLayout), lido e IMEDIATAMENTE apagado no mount
// do destino — um valor "grudado" faria uma visita direta futura (ex.:
// recarregar a página) herdar por engano o "voltar para Administração".
const CHAVE = "cowdata:veio_da_administracao";

export function marcarVeioDaAdministracao(): void {
  try {
    sessionStorage.setItem(CHAVE, "1");
  } catch {
    // sessionStorage indisponível (modo privado restrito etc.) — sem
    // problema, o destino só cai no "voltar à fazenda" de sempre.
  }
}

export function consumirVeioDaAdministracao(): boolean {
  try {
    const veio = sessionStorage.getItem(CHAVE) === "1";
    if (veio) sessionStorage.removeItem(CHAVE);
    return veio;
  } catch {
    return false;
  }
}
