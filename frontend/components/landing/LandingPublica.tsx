"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ArrowRight, LayoutDashboard, CheckCircle2, Award, Newspaper, TrendingUp,
} from "lucide-react";
import { PublicPage } from "@/components/institucional/PublicShell";
import { fetchNoticias, type NoticiaNews } from "@/lib/api";
import { imagemMateria } from "@/lib/newsVisual";
import { MODULOS, PLANOS, PRECO_PLACEHOLDER } from "./dados";

// Landing pública (T8) — o que um visitante SEM login vê em "/" (ver
// AuthShell.tsx::ROTA_PUBLICA e o bypass condicionado a `estado ===
// "deslogado"`, e app/page.tsx, que decide landing-vs-Capa consultando
// getToken()). Reaproveita a mesma casca das páginas /sobre/* (PublicPage,
// components/institucional/PublicShell.tsx) — mesmo cabeçalho com "Entrar",
// mesmo fundo marinho/dourado institucional, mesmo rodapé. Nenhuma cor nova:
// tudo vem de var(--cat-*)/var(--dourado*) já definidos em app/globals.css
// (ver PublicShell.tsx para o degradê de fundo, fixo por não poder usar
// var(--vinho) — ver comentário lá).
//
// Ajuste pós-lançamento (revisão visual): títulos grandes foram de peso 800
// para 700 — o site inteiro já usa peso 700 como padrão em h1-h4 (ver regra
// global em app/globals.css), esta landing é que estava sobrescrevendo esse
// padrão localmente com 800, "gritando" mais que o resto do produto.
// Destaques em dourado trocaram de --dourado-light (claro) para --dourado
// (mais escuro/sóbrio) a pedido do dono do produto.

function Hero() {
  return (
    <section style={{ position: "relative", overflow: "hidden", padding: "4rem 1.5rem 3.5rem" }}>
      <div aria-hidden="true" style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/images/bg-rebanho.webp" alt="" style={{
          position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover", objectPosition: "center 50%",
          opacity: 0.16, filter: "grayscale(1) contrast(1.08) brightness(0.95)", mixBlendMode: "luminosity",
        }} />
      </div>
      <div style={{ position: "relative", zIndex: 1, maxWidth: "760px", margin: "0 auto", textAlign: "center" }}>
        {/* Eyebrow suavizado: era 700/uppercase/0.06em de letter-spacing — lia
            como "gritado" sozinho, antes mesmo do h1 abaixo. Peso e
            letter-spacing reduzidos; cor trocada de --dourado-light (claro)
            para --dourado (mais escuro/sóbrio, mesmo token do resto da
            página). Fundo/borda eram rgba(201,164,76,*) — um hex de dourado
            inventado — agora derivam de var(--dourado) via color-mix. */}
        <span style={{
          display: "inline-block", padding: "0.3rem 0.75rem", borderRadius: "999px", fontSize: "0.72rem", fontWeight: 600,
          letterSpacing: "0.03em", textTransform: "uppercase", color: "var(--dourado)",
          background: "color-mix(in srgb, var(--dourado) 14%, transparent)",
          border: "1px solid color-mix(in srgb, var(--dourado) 30%, transparent)", marginBottom: "1.1rem",
        }}>
          Gestão completa da fazenda leiteira
        </span>
        {/* Peso 800→700 e escala reduzida (topo do clamp 2.9rem→2.5rem) — o
            resto do produto já usa peso 700 como padrão para h1-h4 (regra
            global em app/globals.css); esta landing sobrescrevia isso
            localmente, o que destoava do resto do site. */}
        <h1 style={{ fontSize: "clamp(1.75rem, 3.4vw, 2.5rem)", fontWeight: 700, lineHeight: 1.18, margin: "0 0 1rem", color: "#fff" }}>
          Sua fazenda leiteira, inteira, num só sistema
        </h1>
        <p style={{ fontSize: "1.05rem", color: "rgba(245,238,241,0.78)", margin: "0 0 1.8rem", lineHeight: 1.55 }}>
          Reprodução, produção, sanidade, alimentação, estoque e financeiro — o dia a dia da fazenda
          e a gestão de quem administra, no mesmo painel, atualizados em tempo real.
        </p>
        <div style={{ display: "flex", gap: "0.8rem", justifyContent: "center", flexWrap: "wrap" }}>
          <Link href="/login" className="btn-primary" style={{ fontSize: "0.92rem", padding: "0.65rem 1.4rem" }}>
            Entrar <ArrowRight size={16} />
          </Link>
          <a href="#planos" className="btn-ghost" style={{ fontSize: "0.92rem", padding: "0.65rem 1.4rem", color: "rgba(245,238,241,0.85)", borderColor: "rgba(255,255,255,0.25)" }}>
            Ver planos
          </a>
        </div>
      </div>
    </section>
  );
}

// ── Print do app ──────────────────────────────────────────────────────────
// PLACEHOLDER DELIBERADO: ainda não existe uma captura de tela real do
// sistema para esta seção. O bloco abaixo é um mockup 100% desenhado em CSS
// (nenhuma imagem/foto real) só para dar volume visual à seção enquanto a
// screenshot de verdade não é produzida — por isso o rótulo "Prévia
// ilustrativa" fica sempre visível sobre ele, para não passar a impressão de
// que é a tela real do produto. Quando houver uma captura de verdade (ex.:
// da Capa em app/page.tsx), trocar este componente por um <img> apontando
// para um arquivo em /public/images/ e remover o rótulo.
function PrintDoApp() {
  const kpis = [
    { label: "Fêmeas no rebanho", cor: "var(--cat-reproducao)" },
    { label: "Prenhez / 21 dias", cor: "var(--cat-producao)" },
    { label: "Estoque abaixo do mínimo", cor: "var(--cat-estoque)" },
    { label: "Resultado do mês", cor: "var(--cat-financeiro)" },
  ];
  return (
    <section style={{ padding: "0 1.5rem 3.5rem" }}>
      <div style={{ maxWidth: "980px", margin: "0 auto" }}>
        <div className="card" style={{ padding: 0, overflow: "hidden", boxShadow: "0 30px 70px rgba(0,0,0,0.45)" }}>
          {/* Barra de "navegador" só decorativa */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.6rem 0.9rem", borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.03)" }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: "#E0705B" }} />
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: "#E0C15B" }} />
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: "#63B36B" }} />
            <span style={{
              marginLeft: "0.6rem", fontSize: "0.68rem", color: "var(--text-muted)", background: "var(--surface-2)",
              border: "1px solid var(--border)", borderRadius: "999px", padding: "0.15rem 0.7rem",
            }}>
              app.cowdata — Capa
            </span>
            <span style={{
              marginLeft: "auto", fontSize: "0.62rem", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase",
              color: "var(--dourado)", background: "color-mix(in srgb, var(--dourado) 14%, transparent)",
              border: "1px solid color-mix(in srgb, var(--dourado) 30%, transparent)",
              borderRadius: "999px", padding: "0.2rem 0.6rem",
            }}>
              Prévia ilustrativa
            </span>
          </div>
          {/* Corpo — grade de blocos abstratos representando KPIs + gráfico,
              não é uma tela real do sistema (ver comentário acima). */}
          <div style={{ padding: "1.3rem", display: "flex", flexDirection: "column", gap: "0.9rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px,1fr))", gap: "0.7rem" }}>
              {kpis.map((k) => (
                <div key={k.label} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.8rem", background: "var(--surface-2)" }}>
                  <div style={{ width: "2.2rem", height: "0.55rem", borderRadius: "999px", background: k.cor, opacity: 0.8, marginBottom: "0.6rem" }} />
                  <div style={{ width: "70%", height: "0.6rem", borderRadius: "999px", background: "rgba(245,238,241,0.22)", marginBottom: "0.4rem" }} />
                  <div style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{k.label}</div>
                </div>
              ))}
            </div>
            <div style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "1rem", background: "var(--surface-2)", display: "flex", alignItems: "flex-end", gap: "0.5rem", height: "120px" }}>
              {[38, 55, 46, 62, 58, 70, 64, 78, 72, 85].map((h, i) => (
                <div key={i} style={{ flex: 1, height: `${h}%`, borderRadius: "3px 3px 0 0", background: "color-mix(in srgb, var(--cat-producao) 70%, transparent)" }} />
              ))}
            </div>
          </div>
        </div>
        <p style={{ textAlign: "center", fontSize: "0.75rem", color: "rgba(245,238,241,0.5)", marginTop: "0.7rem" }}>
          <LayoutDashboard size={12} style={{ verticalAlign: "-2px", marginRight: "0.3rem" }} />
          Ilustração da Capa do sistema — a captura de tela real ainda será produzida.
        </p>
      </div>
    </section>
  );
}

function Modulos() {
  return (
    <section id="modulos" style={{ padding: "0 1.5rem 3.5rem" }}>
      <div style={{ maxWidth: "1120px", margin: "0 auto" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#fff", margin: "0 0 0.5rem", textAlign: "center" }}>
          Tudo que a fazenda precisa, em um painel só
        </h2>
        <p style={{ textAlign: "center", color: "rgba(245,238,241,0.68)", fontSize: "0.9rem", margin: "0 0 2rem" }}>
          8 módulos, cada um pensado para o dia a dia de quem toca a fazenda — do curral ao financeiro.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px,1fr))", gap: "1rem" }}>
          {MODULOS.map((m) => (
            <div key={m.chave} className="card" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              <div style={{
                width: "2.6rem", height: "2.6rem", borderRadius: "50%", flexShrink: 0,
                background: `color-mix(in srgb, ${m.cor} 18%, var(--surface-2))`, border: `1px solid ${m.cor}`,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <m.icon size={19} color={m.cor} />
              </div>
              <div style={{ fontWeight: 700, color: "var(--text)", fontSize: "0.95rem" }}>{m.titulo}</div>
              <p style={{ margin: 0, color: "var(--text-muted)", fontSize: "0.82rem", lineHeight: 1.5 }}>{m.texto}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function CartaoPlano({ plano }: { plano: (typeof PLANOS)[number] }) {
  if (plano.sobMedida) {
    // Layout invertido/diferenciado: faixa horizontal cheia, cor de destaque
    // em vez de card neutro, sem preço, CTA de orçamento (não "assinar").
    return (
      <div style={{
        gridColumn: "1 / -1", display: "flex", flexWrap: "wrap", alignItems: "center", gap: "1.2rem",
        justifyContent: "space-between", padding: "1.6rem 1.8rem", borderRadius: "var(--r-md)",
        background: "linear-gradient(120deg, color-mix(in srgb, var(--dourado) 16%, transparent), color-mix(in srgb, var(--dourado) 5%, transparent))",
        border: "1px solid color-mix(in srgb, var(--dourado) 35%, transparent)",
      }}>
        <div style={{ maxWidth: "560px" }}>
          <div style={{ fontWeight: 700, fontSize: "1.15rem", color: "#fff", marginBottom: "0.3rem" }}>{plano.nome}</div>
          <p style={{ margin: 0, color: "rgba(245,238,241,0.75)", fontSize: "0.88rem", lineHeight: 1.5 }}>{plano.resumo}</p>
        </div>
        {/* NOTA: não existe hoje nenhum canal de contato/orçamento no produto
            (sem formulário, e-mail ou WhatsApp cadastrado em lugar nenhum do
            código — conferido em todo o frontend/backend). Até esse canal
            existir, "Solicitar orçamento" leva para /login (a única rota
            pública que já funciona de verdade) em vez de um link fabricado
            que pareceria funcionar sem funcionar. Trocar por mailto:/link
            de WhatsApp/formulário assim que o produto definir o canal real. */}
        <Link href="/login" className="btn-primary-gold" style={{ fontSize: "0.88rem", padding: "0.6rem 1.3rem", flexShrink: 0 }}>
          Solicitar orçamento <ArrowRight size={15} />
        </Link>
      </div>
    );
  }
  return (
    <div className="card" style={{
      display: "flex", flexDirection: "column", height: "100%", position: "relative",
      // .card tem uma regra global (app/globals.css: ".card { overflow-x: auto; }",
      // para cards com tabela larga rolarem por dentro) que, por espec de CSS,
      // força overflow-y para "auto" também quando só overflow-x é setado —
      // e overflow não-visível em qualquer eixo recorta filhos absolutos que
      // ultrapassam a caixa. Era exatamente isso que cortava ao meio o selo
      // "Mais escolhido" abaixo (top: -0.7rem, poking para fora do card) em
      // toda largura testada (confirmado via screenshot, não suposição).
      // overflow:visible aqui devolve o comportamento local sem tocar a regra
      // global (que outros cards com tabela ainda precisam).
      overflow: "visible",
      border: plano.destaque ? "1px solid var(--dourado)" : undefined,
      boxShadow: plano.destaque ? "0 0 0 1px var(--dourado), 0 18px 40px color-mix(in srgb, var(--dourado) 15%, transparent)" : undefined,
    }}>
      {plano.destaque && (
        <span style={{
          position: "absolute", top: "-0.7rem", left: "50%", transform: "translateX(-50%)",
          display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.66rem", fontWeight: 700,
          letterSpacing: "0.04em", textTransform: "uppercase", color: "#1a1a1a", background: "var(--dourado)",
          borderRadius: "999px", padding: "0.25rem 0.7rem", whiteSpace: "nowrap",
        }}>
          <Award size={11} /> Mais escolhido
        </span>
      )}
      <div style={{ fontWeight: 700, fontSize: "1.05rem", color: "#fff", marginTop: plano.destaque ? "0.4rem" : 0 }}>{plano.nome}</div>
      <p style={{ margin: "0.3rem 0 0.9rem", color: "var(--text-muted)", fontSize: "0.8rem", lineHeight: 1.45, minHeight: "2.6rem" }}>{plano.resumo}</p>
      <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "var(--dourado)", marginBottom: "1rem" }}>{PRECO_PLACEHOLDER}</div>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "0.5rem", flex: 1 }}>
        {plano.itens.map((item) => (
          <li key={item} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.82rem", color: "rgba(245,238,241,0.82)" }}>
            <CheckCircle2 size={15} style={{ color: "var(--green-light)", flexShrink: 0, marginTop: "0.1rem" }} />
            {item}
          </li>
        ))}
      </ul>
      <Link href="/login" className={plano.destaque ? "btn-primary-gold" : "btn-primary"}
        style={{ width: "100%", justifyContent: "center", marginTop: "1.2rem", fontSize: "0.85rem" }}>
        Assinar
      </Link>
    </div>
  );
}

function Planos() {
  return (
    <section id="planos" style={{ padding: "0 1.5rem 3.5rem" }}>
      <div style={{ maxWidth: "1120px", margin: "0 auto" }}>
        <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#fff", margin: "0 0 0.5rem", textAlign: "center" }}>
          Um plano para cada tamanho de fazenda
        </h2>
        <p style={{ textAlign: "center", color: "rgba(245,238,241,0.68)", fontSize: "0.9rem", margin: "0 0 2rem" }}>
          Módulos crescem com a operação — comece pelo essencial ou já entre com tudo.
        </p>
        {/* Era "repeat(auto-fit, minmax(230px,1fr))": confirmado via screenshot
            (Playwright, ~830-1050px de largura) que o auto-fit encaixava 3
            cards numa linha e deixava o 4º (Diamond) sozinho numa linha
            própria, esticado — layout imprevisível, não intencional.
            Breakpoints fixos (1/2/4 colunas) substituem o auto-fit: cada
            largura sempre fecha uma grade completa, sem card órfão. */}
        <div className="planos-grid">
          {PLANOS.map((p) => <CartaoPlano key={p.chave} plano={p} />)}
        </div>
        <style>{`
          .planos-grid { display: grid; grid-template-columns: 1fr; gap: 1.1rem; align-items: stretch; }
          @media (min-width: 640px) { .planos-grid { grid-template-columns: repeat(2, 1fr); } }
          @media (min-width: 1000px) { .planos-grid { grid-template-columns: repeat(4, 1fr); } }
        `}</style>
      </div>
    </section>
  );
}

function MilkNewsTeaser() {
  const [materias, setMaterias] = useState<NoticiaNews[] | null>(null);

  useEffect(() => {
    fetchNoticias()
      .then((feed) => {
        const todas = feed.fontes.flatMap((f) => f.noticias);
        todas.sort((a, b) => (b.data_publicacao || b.capturado_em || "").localeCompare(a.data_publicacao || a.capturado_em || ""));
        setMaterias(todas.slice(0, 3));
      })
      .catch(() => setMaterias([]));
  }, []);

  if (materias && materias.length === 0) return null; // sem matérias hoje — não mostra a seção vazia

  return (
    <section style={{ padding: "0 1.5rem 3.5rem" }}>
      <div style={{ maxWidth: "1120px", margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.6rem", marginBottom: "1.2rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--dourado)", fontSize: "0.78rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.03em" }}>
              <Newspaper size={14} /> Milk News
            </div>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#fff", margin: "0.3rem 0 0" }}>O mercado do leite, resumido todo santo dia</h2>
          </div>
          <Link href="/news" style={{ color: "var(--dourado)", fontSize: "0.85rem", fontWeight: 600, textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
            Ver todas as matérias <ArrowRight size={14} />
          </Link>
        </div>
        {!materias ? (
          <p style={{ color: "rgba(245,238,241,0.55)", fontSize: "0.85rem" }}>Carregando matérias…</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px,1fr))", gap: "1rem" }}>
            {materias.map((n, i) => (
              <Link key={n.id} href="/news" className="card" style={{
                display: "flex", flexDirection: "column", padding: 0, overflow: "hidden", textDecoration: "none",
              }}>
                <div style={{ position: "relative", height: "120px" }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={imagemMateria(n, i)} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                  <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: "3px", background: "var(--dourado)" }} />
                </div>
                <div style={{ padding: "0.9rem 1rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.3rem", fontSize: "0.66rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--dourado)", marginBottom: "0.4rem" }}>
                    <TrendingUp size={11} /> {n.categoria || "Notícia setorial"}
                  </div>
                  <div style={{ fontWeight: 700, color: "var(--text)", fontSize: "0.88rem", lineHeight: 1.35 }}>{n.manchete}</div>
                  {n.resumo && (
                    <p style={{ margin: "0.5rem 0 0", color: "var(--text-muted)", fontSize: "0.78rem", lineHeight: 1.4 }}>
                      {n.resumo.length > 110 ? `${n.resumo.slice(0, 107)}…` : n.resumo}
                    </p>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function ChamadaFinal() {
  return (
    <section style={{ padding: "3.5rem 1.5rem 3rem", textAlign: "center", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
      <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#fff", margin: "0 0 0.6rem" }}>
        Pronto para organizar a fazenda de um jeito só?
      </h2>
      <p style={{ color: "rgba(245,238,241,0.7)", fontSize: "0.92rem", margin: "0 0 1.4rem" }}>
        Entre com o seu usuário — ou fale com a gente para montar um plano sob medida.
      </p>
      <Link href="/login" className="btn-primary" style={{ fontSize: "0.92rem", padding: "0.65rem 1.5rem" }}>
        Entrar <ArrowRight size={16} />
      </Link>
    </section>
  );
}

export function LandingPublica() {
  return (
    <PublicPage>
      <Hero />
      <PrintDoApp />
      <Modulos />
      <Planos />
      <MilkNewsTeaser />
      <ChamadaFinal />
    </PublicPage>
  );
}
