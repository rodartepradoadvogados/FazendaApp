"use client";
// Tela-eixo de escolha de conta — ÚNICO componente, em TODO o sistema (site
// e app; ver justificativa em app/escolher-conta/page.tsx), para dois
// momentos que antes tinham (ou teriam) UIs parecidas mas separadas:
//   1. Logo após o login, quando há mais de um acesso vinculado ao mesmo
//      usuário (fazendas e/ou Painel CowData).
//   2. "Trocar de conta", alcançável a qualquer momento pelo menu (Sidebar
//      no site, app/app/menu no app) — sem pedir senha de novo.
// Duas telas quase-iguais (uma no fluxo de login, outra no menu) são duas
// chances de um dia divergirem uma da outra — um badge corrigido numa e
// esquecido na outra, por exemplo. Por isso existe só esta.
import { ChevronRight, ShieldCheck, Building2, FlaskConical, LogOut } from "lucide-react";
import type { FazendaAtual } from "@/lib/api";

export function EscolherConta({
  opcoes, contaAtualId, carregando, erro, onEscolher, onSairDaConta,
}: {
  opcoes: FazendaAtual[];
  // Conta ativa NESTE APARELHO agora — 0 = Painel CowData, id>0 = a
  // fazenda, null/undefined = nenhuma escolhida ainda (ex.: entre o login
  // e esta tela, quando há mais de um acesso).
  //
  // Ela é MARCADA, nunca desabilitada. A primeira versão desta tela a
  // bloqueava, com o raciocínio de que clicar na própria conta seria um
  // clique sem efeito — mas o verbo estava errado: quem chega aqui vindo do
  // sistema não quer TROCAR para a conta em que já está, quer CONTINUAR
  // nela. Bloqueada, a tela obrigava a pessoa a entrar numa fazenda
  // qualquer só para voltar de onde saiu — o oposto do que a marca
  // prometia. Agora o rótulo é "Continuar aqui" e o clique leva ao destino.
  contaAtualId?: number | null;
  carregando: boolean;
  erro: string | null;
  onEscolher: (opcao: FazendaAtual) => void;
  // Ausente no 1º acesso pós-login (ainda não existe sessão nenhuma para
  // encerrar — quem quiser desistir usa "← Voltar" do próprio formulário de
  // login). Presente sempre que a tela é alcançada por "Trocar de conta"
  // (já autenticado) — ver app/escolher-conta/page.tsx. "Sair" é
  // deliberadamente secundário aqui: separado por um filete, sem o peso
  // visual das contas — troca de conta é ação do dia a dia, sair é rara.
  onSairDaConta?: () => void;
}) {
  const temCowdata = opcoes.some((f) => f.cowdata);
  return (
    <>
      <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem", margin: "0 0 1.1rem", fontWeight: 600 }}>
        {temCowdata
          ? "Entrar como administrador de uma fazenda, ou no Painel CowData?"
          : opcoes.length > 1
          ? "Você tem acesso a mais de uma fazenda — qual delas?"
          : "Sua conta"}
      </p>

      {opcoes.length === 0 && (
        <p style={{ textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>Nenhuma conta disponível.</p>
      )}

      <div className="space-y-2">
        {opcoes.map((f) => {
          // Fazendas de verdade nunca têm id 0 (sentinela do Painel
          // CowData) — comparar só o id já distingue os dois casos, sem
          // precisar checar `.cowdata` também.
          const aqui = contaAtualId != null && f.id === contaAtualId;
          return (
            <button key={f.cowdata ? "cowdata" : f.id} type="button" disabled={carregando}
              onClick={() => onEscolher(f)}
              className="btn-ghost" style={{
                width: "100%", justifyContent: "flex-start", alignItems: "center", gap: "0.6rem", padding: "0.7rem 0.9rem",
                border: f.eh_teste ? "1px solid var(--red)" : "1px solid var(--border)",
                background: f.eh_teste ? "color-mix(in srgb, var(--red) 12%, transparent)" : undefined,
                cursor: "pointer",
              }}>
              {f.cowdata
                ? <ShieldCheck size={16} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />
                : f.eh_teste
                ? <FlaskConical size={16} style={{ color: "var(--red)", flexShrink: 0 }} />
                : <Building2 size={16} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />}
              <span style={{ textAlign: "left", minWidth: 0, flex: 1 }}>
                <span style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                  <strong>{f.nome}</strong>
                  {f.eh_teste && (
                    <span style={{
                      fontSize: "0.65rem", fontWeight: 700, color: "var(--red)", border: "1px solid var(--red)",
                      borderRadius: "var(--r-sm)", padding: "0.05rem 0.4rem", letterSpacing: "0.02em", whiteSpace: "nowrap",
                    }}>
                      AMBIENTE DE TESTE
                    </span>
                  )}
                </span>
                {f.cowdata
                  ? <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Administração da CowData — acesso de suporte às fazendas-clientes</span>
                  : f.eh_teste
                  ? <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Cópia-sandbox para testar sem afetar dados reais</span>
                  : (f.cidade || f.uf) && <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{[f.cidade, f.uf].filter(Boolean).join(" · ")}</span>}
              </span>
              {aqui && (
                <span style={{
                  fontSize: "0.68rem", fontWeight: 700, color: "var(--dourado-light)", whiteSpace: "nowrap",
                  border: "1px solid var(--dourado-light)", borderRadius: "var(--r-sm)", padding: "0.05rem 0.4rem",
                }}>
                  CONTINUAR AQUI
                </span>
              )}
              <ChevronRight size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
            </button>
          );
        })}
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.82rem", marginTop: "0.6rem" }}>{erro}</p>}

      {onSairDaConta && (
        <>
          <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "1.2rem 0 0.8rem" }} />
          <button type="button" onClick={onSairDaConta} disabled={carregando}
            style={{
              width: "100%", background: "none", border: "none", padding: "0.3rem",
              color: "var(--text-muted)", fontSize: "0.78rem", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem",
            }}>
            <LogOut size={13} /> Sair da conta
          </button>
        </>
      )}
    </>
  );
}
