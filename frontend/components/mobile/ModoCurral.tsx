"use client";
// MODO CURRAL — tela nova do redesign (T6), pensada para o momento em que o
// aparelho está sendo usado DENTRO do curral: sol forte, uma mão só (a outra
// segura o animal/a corda), possivelmente com luva. Não é uma tela a mais
// entre várias, é uma visão DELIBERADAMENTE mais simples e maior que o resto
// do app:
//   - Lista "Fazer agora": as tarefas de hoje (e atrasadas) da Agenda, só que
//     em cartões bem maiores, com o mínimo de texto e o alvo de toque do
//     check MAIOR que o piso geral de 56px do app (72px aqui).
//   - "Lançar rápido": atalho direto para os 3 destinos de maior frequência
//     de uso real de campo (mesmos 3 já priorizados em Lançar — ver
//     components/mobile/lancar/LancarTela.tsx, blocos "grande"), sem passar
//     pela busca/menu da tela Lançar inteira.
//
// Deliberadamente NÃO reimplementa aqui os fluxos ricos de confirmação da
// Agenda completa (protocolo em lote, "qual frasco?", dar baixa com
// dose/veterinário etc.) — isso duplicaria uma lógica grande e delicada
// (estoque, backend) fora do lugar que já a mantém corretamente. Uma
// pendência que exige esses passos aparece aqui do mesmo jeito (nada
// escondido), só que o toque nela leva para a Agenda completa em vez de um
// check direto — ver `ehSimples`, abaixo.
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Sun, Check, ChevronRight, Activity, Milk, Syringe } from "lucide-react";
import { MobVoltar, corCategoria, iconeCategoria } from "@/components/mobile/ui";
import { fetchAgenda, today, fetchAnimais } from "@/lib/api";
import { fetchComCache, enviarOuEnfileirar, useOnline } from "@/lib/offline";
import { useCache, type Animal } from "@/components/mobile/lancar/comum";

const FormReprodutivo = dynamic(() => import("@/components/mobile/lancar/FormReprodutivo").then((m) => m.FormReprodutivo), { ssr: false });
const FormProducao = dynamic(() => import("@/components/mobile/lancar/FormProducao").then((m) => m.FormProducao), { ssr: false });
const FormSanidade = dynamic(() => import("@/components/mobile/lancar/FormSanidade").then((m) => m.FormSanidade), { ssr: false });

// Só os campos que esta tela realmente lê — o formato completo (com todos os
// campos de protocolo/cronograma/BST) vive em app/app/page.tsx (Agenda).
type Evento = {
  id: string; data: string; categoria: string; descricao: string;
  numero_animal?: string | null; lote?: string | null; observacao?: string | null;
  tipo?: string | null;
};
type Agenda = { eventos?: Evento[] };

// Tipos que exigem um painel de confirmação rico (dose, produto, veterinário,
// "lote ou individual" etc.) — ver app/app/page.tsx para o tratamento
// completo de cada um. Qualquer evento com um destes `tipo` some do toque
// direto aqui e vira "abrir na Agenda completa".
const TIPOS_COMPLEXOS = new Set([
  "protocolo_iatf", "protocolo_inducao", "protocolo_sanitario", "protocolo_customizado",
  "cronograma_sanitario_animal", "cronograma_sanitario_modo", "cronograma_sanitario_urgente", "cronograma_sanitario_aplicar",
  "bst_aplicacao", "sugestao_movimentacao", "colostragem_pendente", "igg_pendente",
  "evento_sanitario", "calendario_sanitario", "aplicacao_agendada",
]);
function ehSimples(e: Evento): boolean {
  return !e.tipo || !TIPOS_COMPLEXOS.has(e.tipo);
}

function tituloEvento(e: Evento): string {
  if (e.numero_animal) return `Nº ${e.numero_animal}`;
  if (e.lote) return `Lote ${e.lote}`;
  return e.descricao;
}

type TelaRapida = "reprodutivo" | "producao" | "sanidade" | null;

export function ModoCurral({ onVoltar }: { onVoltar: () => void }) {
  const online = useOnline();
  const hoje = today();
  // MESMA chave de cache que a Agenda (app/app/page.tsx) usa — se a Agenda já
  // foi aberta hoje, o Modo Curral aproveita a cópia sem gastar uma requisição
  // extra; e o inverso também vale (o que este componente busca serve à
  // Agenda depois, se ela abrir primeiro fora de ordem).
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [carregando, setCarregando] = useState(true);
  // MESMA chave de cache que a Agenda completa usa (app/app/page.tsx) — se
  // ela já foi aberta hoje, o Modo Curral aproveita a cópia sem gastar uma
  // requisição extra (e vice-versa).
  useEffect(() => {
    let vivo = true;
    fetchComCache<Agenda>(`agenda_mob_${hoje}`, () => fetchAgenda(hoje))
      .then(({ dados }) => { if (vivo) { setAgenda(dados); setCarregando(false); } })
      .catch(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [hoje]);

  const [feitos, setFeitos] = useState<Set<string>>(new Set());
  const [erro, setErro] = useState<string | null>(null);
  const [telaRapida, setTelaRapida] = useState<TelaRapida>(null);

  const animais = useCache<Animal[]>("animais", () => fetchAnimais() as Promise<Animal[]>, []);

  const pendentesHoje = useMemo(() => {
    const evs = (agenda?.eventos || []).filter((e) => e.data <= hoje && !feitos.has(e.id));
    // Atrasadas primeiro, hoje depois — mesmo critério da Agenda completa.
    return evs.sort((a, b) => (a.data < b.data ? -1 : a.data > b.data ? 1 : 0));
  }, [agenda, hoje, feitos]);

  async function concluir(e: Evento) {
    setErro(null);
    setFeitos((p) => new Set(p).add(e.id));
    try {
      await enviarOuEnfileirar("/agenda/realizados", { evento_id: e.id }, `Concluir: ${tituloEvento(e)}`, "POST");
      try { navigator.vibrate?.(20); } catch { /* sem suporte — segue sem vibrar */ }
    } catch (err) {
      setFeitos((p) => { const n = new Set(p); n.delete(e.id); return n; });
      setErro(err instanceof Error ? err.message : "Não foi possível salvar.");
    }
  }

  // ── Lançar rápido: sub-formulário aberto ────────────────────────────────
  if (telaRapida) {
    const titulos: Record<Exclude<TelaRapida, null>, string> = { reprodutivo: "Reprodutivo", producao: "Produção (leite)", sanidade: "Sanidade" };
    return (
      <div className="curral-alvo">
        <MobVoltar titulo={titulos[telaRapida]} onVoltar={() => setTelaRapida(null)} />
        {telaRapida === "reprodutivo" && <FormReprodutivo animais={animais.dados} animalFixado={null} />}
        {telaRapida === "producao" && <FormProducao animais={animais.dados} animalFixado={null} />}
        {telaRapida === "sanidade" && <FormSanidade animais={animais.dados} animalFixado={null} />}
      </div>
    );
  }

  return (
    <div className="curral-alvo">
      <MobVoltar titulo="Modo Curral" onVoltar={onVoltar} />

      <p style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-muted)", margin: "0 0 1rem" }}>
        <Sun size={16} /> Textos grandes, alto contraste — pensado para uso com luva e sol forte
      </p>

      {!online && (
        <div className="curral-aviso curral-aviso-offline">Sem conexão agora — os toques abaixo ficam guardados e são enviados sozinhos depois.</div>
      )}
      {erro && <div className="curral-aviso curral-aviso-erro">{erro}</div>}

      <div className="curral-secao">Fazer agora</div>
      {carregando && <p style={{ color: "var(--mob-muted)", padding: "1rem 0" }}>Carregando…</p>}
      {!carregando && pendentesHoje.length === 0 && (
        <div className="curral-vazio">
          <Check size={30} />
          <p>Nada pendente para hoje. 🎉</p>
        </div>
      )}
      <div style={{ display: "grid", gap: "0.7rem" }}>
        {pendentesHoje.map((e) => {
          const simples = ehSimples(e);
          const atrasado = e.data < hoje;
          const cor = corCategoria(e.categoria);
          const Icon = iconeCategoria(e.categoria);
          return (
            <div key={e.id} className="curral-card" style={{ borderLeftColor: atrasado ? "var(--mob-vermelho)" : cor }}>
              <span className="curral-card-icone" style={{ background: `color-mix(in srgb, ${cor} 18%, transparent)`, color: cor }}>
                <Icon size={26} />
              </span>
              <span className="curral-card-texto">
                <span className="curral-card-titulo">{tituloEvento(e)}</span>
                <span className="curral-card-sub">{e.descricao !== tituloEvento(e) ? e.descricao : (atrasado ? "Atrasado" : "Hoje")}</span>
              </span>
              {simples ? (
                <button type="button" className="curral-check" aria-label={`Concluir: ${tituloEvento(e)}`} onClick={() => concluir(e)}>
                  <Check size={30} strokeWidth={3} />
                </button>
              ) : (
                <Link href="/app" className="curral-abrir" aria-label="Abrir na Agenda completa" title="Precisa de mais informação — abrir na Agenda completa">
                  <ChevronRight size={26} />
                </Link>
              )}
            </div>
          );
        })}
      </div>

      <div className="curral-secao">Lançar rápido</div>
      <div style={{ display: "grid", gap: "0.7rem" }}>
        <button type="button" className="curral-lancar" onClick={() => setTelaRapida("reprodutivo")}>
          <Activity size={28} /> Reprodutivo
        </button>
        <button type="button" className="curral-lancar" onClick={() => setTelaRapida("producao")}>
          <Milk size={28} /> Produção (Leite)
        </button>
        <button type="button" className="curral-lancar" onClick={() => setTelaRapida("sanidade")}>
          <Syringe size={28} /> Sanidade
        </button>
      </div>

      <Link href="/app/lancar" className="curral-mais">
        Ver todos os lançamentos <ChevronRight size={18} />
      </Link>
    </div>
  );
}
