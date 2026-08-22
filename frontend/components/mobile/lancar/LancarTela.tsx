"use client";
// Tela LANÇAR (lançamento rápido) do app de campo. Busca grande no topo que
// "fixa" um animal num chip; SEIS blocos grandes (os destinos de maior uso
// real no dia a dia de campo) abrem sub-telas com mini-formulários; o resto
// — administrativo (Financeiro/Estoque) e as ações irreversíveis (Baixar/
// Excluir, que continuam existindo, só não na tela principal) — mora na
// gaveta "Mais opções". Todo envio passa por enviarOuEnfileirar (offline-first).
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Activity, Milk, Syringe, Wheat, ArrowLeftRight, Skull, Search, X, ChevronRight, Landmark, Boxes, Trash2, ListChecks, MoreHorizontal, Sun } from "lucide-react";
import { MobTitulo, MobBloco, MobVoltar, MobGaveta } from "@/components/mobile/ui";
import { fetchAnimais, podeModulo } from "@/lib/api";
import { type Animal, useCache, filtrarAnimais, rotuloAnimal } from "./comum";

// Cada bloco grande só baixa a sub-tela que abre quando o usuário toca nela —
// importante em conexão de campo, onde o app roda mais.
const FormReprodutivo = dynamic(() => import("./FormReprodutivo").then((m) => m.FormReprodutivo), { ssr: false });
const FormProducao = dynamic(() => import("./FormProducao").then((m) => m.FormProducao), { ssr: false });
const FormSanidade = dynamic(() => import("./FormSanidade").then((m) => m.FormSanidade), { ssr: false });
const FormAlimentacao = dynamic(() => import("./FormAlimentacao").then((m) => m.FormAlimentacao), { ssr: false });
const FormProtocolos = dynamic(() => import("./FormProtocolos").then((m) => m.FormProtocolos), { ssr: false });
const Movimentar = dynamic(() => import("@/components/mobile/rebanho/Movimentar"), { ssr: false });
const Baixar = dynamic(() => import("@/components/mobile/rebanho/Baixar"), { ssr: false });
const FormFinanceiroApp = dynamic(() => import("./FormFinanceiroApp"), { ssr: false });
const BalancoEstoque = dynamic(() => import("./BalancoEstoque"), { ssr: false });
const FormExclusao = dynamic(() => import("@/components/FormExclusao").then((m) => m.FormExclusao), { ssr: false });

type Tela = "reprodutivo" | "producao" | "sanidade" | "alimentacao" | "protocolos" | "movimentar" | "baixar" | "financeiro" | "estoque" | "exclusao";

const TITULOS: Record<Tela, string> = {
  reprodutivo: "Reprodutivo",
  producao: "Produção (leite)",
  sanidade: "Sanidade",
  alimentacao: "Alimentação",
  protocolos: "Protocolos",
  movimentar: "Movimentar animais",
  baixar: "Baixar animal",
  financeiro: "Financeiro",
  estoque: "Balanço de estoque",
  exclusao: "Excluir lançamento",
};

export function LancarTela() {
  const animais = useCache<Animal[]>("animais", () => fetchAnimais() as Promise<Animal[]>, []);
  // /app/lancar#financeiro (ex.: atalho "$ Lançar financeiro" do Calendário
  // Sanitário) abre direto em Financeiro > Contas a pagar — o `?servico=`
  // que vem junto é lido pelo próprio FormFinanceiro (ver components/
  // FormFinanceiro.tsx), não precisa ser tratado aqui.
  const [tela, setTela] = useState<Tela | null>(() => (
    typeof window !== "undefined" && window.location.hash === "#financeiro" ? "financeiro" : null
  ));
  const [fixado, setFixado] = useState<Animal | null>(null);
  // Ao "gerar movimentação financeira" no Balanço de estoque, guarda qual
  // pílula (despesa/receita) o Financeiro deve abrir já selecionada. Fica
  // undefined ao entrar por "Financeiro" direto, para o submenu aparecer
  // primeiro (ver FormFinanceiroApp: tipoInicial ausente = mostra a grade).
  const [tipoFinanceiroInicial, setTipoFinanceiroInicial] = useState<"despesa" | "receita" | undefined>(() => (
    typeof window !== "undefined" && window.location.hash === "#financeiro" ? "despesa" : undefined
  ));
  // Só sabemos a permissão real depois de montar (localStorage não existe no
  // servidor) — evita vazar os blocos de Financeiro/Estoque antes da hora.
  const [montado, setMontado] = useState(false);
  useEffect(() => { setMontado(true); }, []);
  // Gaveta "Mais opções" — tudo que NÃO está entre os 6 blocos principais
  // (ver comentário na tela principal, abaixo).
  const [maisOpcoes, setMaisOpcoes] = useState(false);

  // ── Sub-tela aberta ────────────────────────────────────────────────────────
  if (tela) {
    return (
      <div>
        {tela !== "financeiro" && tela !== "estoque" && <MobVoltar titulo={TITULOS[tela]} onVoltar={() => setTela(null)} />}
        {tela === "reprodutivo" && <FormReprodutivo animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "producao" && <FormProducao animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "sanidade" && <FormSanidade animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "alimentacao" && <FormAlimentacao />}
        {tela === "protocolos" && <FormProtocolos animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "movimentar" && <Movimentar />}
        {tela === "baixar" && <Baixar />}
        {tela === "financeiro" && <FormFinanceiroApp onVoltar={() => setTela(null)} tipoInicial={tipoFinanceiroInicial} animais={animais.dados} />}
        {tela === "estoque" && (
          <BalancoEstoque
            onVoltar={() => setTela(null)}
            onIrParaFinanceiro={(t) => { setTipoFinanceiroInicial(t); setTela("financeiro"); }}
          />
        )}
        {tela === "exclusao" && (
          <div className="mob-form-embutido">
            <FormExclusao />
          </div>
        )}
      </div>
    );
  }

  // ── Tela principal ─────────────────────────────────────────────────────────
  // Os 6 blocos abaixo são os destinos MAIS usados no dia a dia de campo —
  // reprodutivo e produção decidem o que fazer com a vaca hoje, sanidade e
  // alimentação vêm logo atrás em frequência real, protocolos e movimentar
  // fecham a rotina de curral. O resto (Financeiro/Estoque — administrativo,
  // não é decisão de curral — e Baixar/Excluir — irreversíveis, propositalmente
  // fora do alcance do toque mais comum) foi para a gaveta "Mais opções":
  // continuam existindo e alcançáveis, só não competem com o que se usa toda
  // hora pelo mesmo espaço de tela/toque. Baixar/Excluir moram SEMPRE lá
  // dentro (nunca voltam pra tela principal), então o botão "Mais opções"
  // sempre tem pelo menos essas duas — não é condicional a nenhuma permissão.
  return (
    <div>
      <MobTitulo>Lançamento Rápido</MobTitulo>

      {/* Atalho pro Modo Curral (T6) — visão ampliada/alto-contraste das
          tarefas de hoje + os mesmos 3 lançamentos mais frequentes abaixo,
          pensada pra quando o aparelho está sendo usado dentro do curral. */}
      <Link href="/app/curral" className="mob-linha" style={{ marginBottom: "0.9rem", color: "var(--mob-dourado)", fontWeight: 700 }}>
        <Sun size={20} /> Abrir Modo Curral
        <ChevronRight size={18} style={{ marginLeft: "auto", color: "var(--mob-muted)" }} />
      </Link>

      {fixado
        ? <ChipAnimal animal={fixado} onSoltar={() => setFixado(null)} />
        : <BuscaAnimal animais={animais.dados} onEscolher={setFixado} />}

      {/* Os 3 destinos de maior frequência de uso real (rotina diária de
          campo) ganham um bloco maior, empilhado, acima da grade normal —
          menos rolagem pro toque mais comum. */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginTop: "0.4rem" }}>
        <MobBloco variante="grande" icone={<Activity size={24} />} label="Reprodutivo" onClick={() => setTela("reprodutivo")} />
        <MobBloco variante="grande" icone={<Milk size={24} />} label="Produção (Leite)" onClick={() => setTela("producao")} />
        <MobBloco variante="grande" icone={<Syringe size={24} />} label="Sanidade" onClick={() => setTela("sanidade")} />
      </div>

      <div className="mob-secao">Outros lançamentos frequentes</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.7rem" }}>
        <MobBloco icone={<Wheat size={22} />} label="Alimentação" onClick={() => setTela("alimentacao")} />
        <MobBloco icone={<ListChecks size={22} />} label="Protocolos" onClick={() => setTela("protocolos")} />
        <MobBloco icone={<ArrowLeftRight size={22} />} label="Movimentar" onClick={() => setTela("movimentar")} />
      </div>

      {/* Gaveta "Mais opções" — Financeiro/Balanço de estoque (administrativo,
          não é decisão de curral) e, SEMPRE aqui dentro (nunca na tela
          principal), Baixar animal/Excluir lançamento — irreversíveis. */}
      <button type="button" className="mob-linha" style={{ marginTop: "0.9rem", justifyContent: "center", fontWeight: 700 }}
        onClick={() => setMaisOpcoes(true)}>
        <MoreHorizontal size={20} style={{ color: "var(--mob-muted)" }} />
        Mais opções
      </button>

      <MobGaveta aberto={maisOpcoes} titulo="Mais opções" onFechar={() => setMaisOpcoes(false)}>
        {montado && (podeModulo("financeiro") || podeModulo("estoque")) && (
          <>
            <div className="mob-secao" style={{ marginTop: 0 }}>Administrativo</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.7rem", marginBottom: "1.1rem" }}>
              {montado && podeModulo("financeiro") && (
                <MobBloco icone={<Landmark size={22} />} label="Financeiro" onClick={() => { setTipoFinanceiroInicial(undefined); setMaisOpcoes(false); setTela("financeiro"); }} />
              )}
              {montado && podeModulo("estoque") && (
                <MobBloco icone={<Boxes size={22} />} label="Balanço de estoque" onClick={() => { setMaisOpcoes(false); setTela("estoque"); }} />
              )}
            </div>
          </>
        )}

        {/* Ações realmente destrutivas/irreversíveis — separadas estruturalmente
            do resto da grade, não só pela cor do ícone (ver .mob-bloco .icone),
            pra não ficarem lado a lado com um toque comum do dia a dia. */}
        <div className="mob-secao" style={{ color: "var(--mob-vermelho)" }}>Ações irreversíveis</div>
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.7rem", padding: "0.6rem", borderRadius: "var(--r-app)",
          border: "1px solid color-mix(in srgb, var(--mob-vermelho) 35%, transparent)",
          background: "color-mix(in srgb, var(--mob-vermelho) 6%, transparent)",
        }}>
          <MobBloco icone={<Skull size={22} />} label="Baixar animal" cor="var(--mob-vermelho)" onClick={() => { setMaisOpcoes(false); setTela("baixar"); }} />
          <MobBloco icone={<Trash2 size={22} />} label="Excluir lançamento" cor="var(--mob-vermelho)" onClick={() => { setMaisOpcoes(false); setTela("exclusao"); }} />
        </div>
      </MobGaveta>
    </div>
  );
}

// ── Busca grande do topo ───────────────────────────────────────────────────
function BuscaAnimal({ animais, onEscolher }: { animais: Animal[]; onEscolher: (a: Animal) => void }) {
  const [q, setQ] = useState("");
  const resultados = q.trim() ? filtrarAnimais(animais, q).slice(0, 8) : [];
  return (
    <div style={{ marginBottom: "1.1rem" }}>
      <div style={{ position: "relative" }}>
        <Search size={19} style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)", pointerEvents: "none" }} />
        <input className="mob-input" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar brinco ou lote…" style={{ paddingLeft: "2.6rem", fontSize: "1.05rem" }} />
      </div>
      {q.trim() !== "" && (
        <div style={{ marginTop: "0.5rem", display: "grid", gap: "0.5rem" }}>
          {resultados.map((a) => (
            <button key={a.numero} type="button" className="mob-linha" onClick={() => { onEscolher(a); setQ(""); }}>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontWeight: 700 }}>{a.numero}</span>
                {rotuloAnimal(a) && <span style={{ display: "block", fontSize: "0.82rem", color: "var(--mob-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{rotuloAnimal(a)}</span>}
              </span>
              <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
            </button>
          ))}
          {resultados.length === 0 && <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem", padding: "0.2rem 0.1rem" }}>Nenhum animal encontrado.</p>}
        </div>
      )}
    </div>
  );
}

// ── Chip do animal fixado ──────────────────────────────────────────────────
function ChipAnimal({ animal, onSoltar }: { animal: Animal; onSoltar: () => void }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1.1rem",
      padding: "0.7rem 0.8rem 0.7rem 1rem", borderRadius: "var(--r-app)",
      background: "var(--mob-vinho)", color: "#FFFFFF",
    }}>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontWeight: 800, fontSize: "1rem" }}>{animal.numero}</span>
        {rotuloAnimal(animal) && <span style={{ display: "block", fontSize: "0.8rem", opacity: 0.85, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{rotuloAnimal(animal)}</span>}
      </span>
      <button type="button" onClick={onSoltar} aria-label="Soltar animal"
        style={{ width: 56, height: 56, borderRadius: "var(--r-app)", border: "none", cursor: "pointer", background: "rgba(255,255,255,0.16)", color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <X size={18} />
      </button>
    </div>
  );
}
