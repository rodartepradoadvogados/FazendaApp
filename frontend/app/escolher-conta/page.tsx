"use client";
// Tela-eixo de escolha de conta — ver components/EscolherConta.tsx para a
// visão geral e a justificativa de existir UMA SÓ tela (não duas parecidas
// que saem de sincronia). Esta rota é o "eixo" propriamente dito, alcançado
// em 3 momentos, com o MESMO comportamento no site e no app:
//
//  1. Logo após o login: app/login/page.tsx redireciona pra cá (com
//     ?next=...) em vez de desenhar a própria lista — antes disto, a
//     mesma UI (fazenda/Painel CowData, badge de Fazenda Teste etc.)
//     existia só ali, inacessível de fora.
//  2. "Trocar de conta" no menu (Sidebar.tsx no site, app/app/menu/page.tsx
//     no app) — a qualquer momento, sem pedir senha de novo.
//  3. Sozinha, ao abrir o app (ver components/AuthShell.tsx), quando a
//     pessoa tem mais de um acesso — nunca em navegação interna.
//
// Por que rota própria (e não um parâmetro em cima da tela de login, ou um
// componente duplicado no menu): o login É pré-autenticação (mostra a
// própria tela de usuário/senha por trás) e o menu já mostra sistema
// completo por trás — misturar os três atrás de uma flag encavalaria
// estados que não têm nada a ver um com o outro. Uma rota dedicada, fora da
// casca normal do site (ver bypass em AuthShell.tsx, mesmo padrão do
// Painel CowData) mas exigindo login válido, é o meio-termo: um único
// lugar, sem herdar nenhuma das duas cascas que não fazem sentido aqui.
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { EscolherConta } from "@/components/EscolherConta";
import {
  ehContador, escolherConta, fetchContasDisponiveis, getContaAtivaId, logout, type FazendaAtual,
} from "@/lib/api";
import { ehAppDeCampo } from "@/lib/nativo";

function Conteudo() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");

  const [opcoes, setOpcoes] = useState<FazendaAtual[] | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchContasDisponiveis()
      .then(setOpcoes)
      .catch((e) => setErro(e.message || "Não foi possível carregar suas contas"));
  }, []);

  const irParaDestino = async () => {
    // Vínculo de contador: casca própria, ignora "next" (mesmo comportamento
    // do login, ver app/login/page.tsx::irParaDestino).
    if (ehContador()) { router.replace("/contador"); return; }
    if (next && next.startsWith("/")) { router.replace(next); return; }
    router.replace((await ehAppDeCampo()) ? "/app" : "/");
  };

  const aoEscolher = async (opcao: FazendaAtual) => {
    setCarregando(true); setErro(null);
    try {
      await escolherConta(opcao);
      if (opcao.cowdata) { router.replace("/painel-cowdata"); return; }
      await irParaDestino();
    } catch (err: any) {
      setErro(err.message || "Não foi possível trocar de conta");
      setCarregando(false);
    }
  };

  const sairDaConta = () => {
    // Confirmação simples (window.confirm, mesmo padrão do resto do site —
    // ver ListaCadastroSimples.tsx) — "Sair" é ação rara e encerra a sessão
    // de verdade neste aparelho, então merece uma pergunta antes, mas sem o
    // peso de desenhar mais um modal só para isto.
    if (window.confirm("Sair da conta? Você vai precisar entrar de novo para continuar usando o sistema neste aparelho.")) {
      logout();
    }
  };

  return (
    <section style={{
      minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center", padding: "3rem 1.5rem",
      background: "var(--bg)",
    }}>
      <div className="card" style={{ width: "100%", maxWidth: "352px" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem", marginBottom: "1.3rem" }}>
          <CowDataMark size={46} />
          <CowDataWordmark size="1.3rem" />
        </div>
        {opcoes === null ? (
          <p style={{ textAlign: "center", color: "var(--text-muted)" }}><Loader2 size={18} className="animate-spin" /></p>
        ) : (
          <EscolherConta
            opcoes={opcoes}
            contaAtualId={getContaAtivaId()}
            carregando={carregando}
            erro={erro}
            onEscolher={aoEscolher}
            onSairDaConta={sairDaConta}
          />
        )}
      </div>
    </section>
  );
}

export default function EscolherContaPage() {
  return (
    <Suspense fallback={null}>
      <Conteudo />
    </Suspense>
  );
}
