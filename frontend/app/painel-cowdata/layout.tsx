"use client";
// Painel CowData — administração da EMPRESA de software (isolado da Fazenda
// Jairo Nasser, ver AuthShell.tsx::ehPainelCowData). Paleta própria, com
// aparência selecionável (escuro/misto/claro — ver lib/painelCowDataTema.tsx
// e o botão no topo do menu); "escuro" é o padrão e continua sendo a mesma
// paleta cinza-azulada do Painel do Contador de sempre, pedido explícito do
// usuário para os dois painéis "à parte" da fazenda se lerem como a mesma
// família visual — misto/claro são variações desta seção, só ela.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type CSSProperties } from "react";
import {
  LayoutGrid, CreditCard, Building2, Wallet, Users, Bot, Lock, ShieldCheck, ArrowLeft, Menu, X, ListChecks, Dna, Pill, UserCog,
  SlidersHorizontal, Newspaper, Sun, Moon, SunMoon,
} from "lucide-react";
import { CowDataMark } from "@/components/brand/CowDataMark";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { ehAppOuPwa } from "@/lib/nativo";
import { temAreaPainelCowData, ehDono, type AreaPainelCowData } from "@/lib/api";
import { consumirVeioDaAdministracao } from "@/lib/portalAdministracao";
import { PainelCowDataTemaProvider, usePainelCowDataTema, type TemaPainelCowData } from "@/lib/painelCowDataTema";

// Só estas 3 áreas têm a permissão de verdade aplicada nas rotas do backend
// hoje (ver exigir_area_painel_cowdata em painel_cowdata.py/cofre_acesso.py)
// — as demais ficam fora do menu de quem não é dono, mesmo que a área
// esteja marcada no cadastro dele, pra nunca mostrar um item que ainda
// devolve 403 nas rotas de verdade.
const AREAS_ENFORCADAS: AreaPainelCowData[] = ["equipe", "financeiro", "cofre", "cadastros"];

// `area` casa com AREAS_PAINEL_COWDATA (backend) — dono vê tudo; um membro
// da Equipe CowData com login próprio (ver lib/api.ts::temAreaPainelCowData)
// só vê os itens cuja área está liberada pra ele. Hoje só Equipe/Financeiro/
// Suporte têm a permissão de verdade aplicada nas rotas (ver
// exigir_area_painel_cowdata no backend) — os demais ficam escondidos por
// enquanto para quem não é dono, mesmo que a área apareça marcada no
// cadastro dele (ver docstring de equipe_cowdata_acesso.py).
// Exportado — reaproveitado pelo início mobile do app (ver
// components/painel-cowdata/mobile/InicioMobilePainelCowData.tsx) pra listar
// as mesmas áreas do site, sem duplicar a lista.
export const GRUPOS: { titulo: string; itens: { href: string; label: string; icon: any; area: AreaPainelCowData }[] }[] = [
  {
    titulo: "Negócio",
    itens: [
      { href: "/painel-cowdata", label: "Cockpit", icon: LayoutGrid, area: "cockpit" },
      { href: "/painel-cowdata/assinaturas", label: "Assinaturas", icon: CreditCard, area: "assinaturas" },
      { href: "/painel-cowdata/fazendas", label: "Fazendas (clientes)", icon: Building2, area: "fazendas" },
    ],
  },
  {
    titulo: "Administração",
    itens: [
      { href: "/painel-cowdata/financeiro", label: "Financeiro CowData", icon: Wallet, area: "financeiro" },
      { href: "/painel-cowdata/equipe", label: "Equipe CowData", icon: Users, area: "equipe" },
    ],
  },
  {
    titulo: "Operação",
    itens: [
      { href: "/painel-cowdata/produto", label: "Produto e robôs", icon: Bot, area: "produto" },
      // Rota continua /cofre (histórico, testes e o próprio dado gravado já
      // usam esse nome) — só o rótulo do menu virou "Suporte", a pedido do
      // usuário, com 2 sub-abas dentro da própria página (Acesso CowData /
      // Auditoria de Acessos CowData — ver painel-cowdata/cofre/page.tsx).
      { href: "/painel-cowdata/cofre", label: "Suporte", icon: Lock, area: "cofre" },
      { href: "/painel-cowdata/confianca", label: "Confiança e LGPD", icon: ShieldCheck, area: "confianca" },
      // Motivos/raças/unidades de estoque/tipos-métodos aplicáveis a todas as
      // fazendas-cliente de uma vez, ou só às selecionadas — ver
      // painel-cowdata/cadastros/page.tsx.
      { href: "/painel-cowdata/cadastros", label: "Cadastros globais", icon: ListChecks, area: "cadastros" },
      // Catálogo de touros — mesma tela/rotas do Cadastro > Touros de
      // qualquer fazenda (Touro não tem fazenda_id: é global por natureza,
      // não precisa de mecânica de "aplicar em fazendas" nenhuma).
      { href: "/painel-cowdata/touros", label: "Touros Naab", icon: Dna, area: "cadastros" },
      // Catálogo global de indicações/princípios/marcas da Farmácia — mesmo
      // componente da sub-aba Farmácia dos Cadastros da fazenda, chamado sem
      // fazenda selecionada (ver app/painel-cowdata/farmacia/page.tsx).
      { href: "/painel-cowdata/farmacia", label: "Farmácia", icon: Pill, area: "cadastros" },
      // Diferente dos itens acima, este NUNCA "aplica em várias fazendas de
      // uma vez" — login é sempre de uma fazenda só, escolhida explicitamente
      // (ver app/painel-cowdata/usuarios/page.tsx).
      { href: "/painel-cowdata/usuarios", label: "Usuários", icon: UserCog, area: "cadastros" },
      // Metas/configurações de manejo, agenda, RH e financeiro
      // (ParametroFazenda) — mesma mecânica de Cadastros globais (aplicar em
      // todas ou só nas selecionadas). Ver painel-cowdata/parametros/page.tsx.
      { href: "/painel-cowdata/parametros", label: "Parâmetros", icon: SlidersHorizontal, area: "cadastros" },
      // Admin do blog (NoticiaNews/FonteNews) — não tem fazenda_id, é global
      // por natureza; mesmo componente de Configurações > News de qualquer
      // fazenda. Ver app/painel-cowdata/news/page.tsx.
      { href: "/painel-cowdata/news", label: "News", icon: Newspaper, area: "cadastros" },
    ],
  },
];

// Mesma regra de filtro por área que a barra lateral já aplicava — extraída
// pra função à parte (era um `const` dentro do componente) porque o início
// mobile do app (fora desta árvore de componente) precisa do mesmo cálculo.
export function gruposVisiveisPainelCowData() {
  return ehDono()
    ? GRUPOS
    : GRUPOS
        .map((g) => ({ ...g, itens: g.itens.filter((i) => AREAS_ENFORCADAS.includes(i.area) && temAreaPainelCowData(i.area)) }))
        .filter((g) => g.itens.length > 0);
}

export default function PainelCowDataLayout({ children }: { children: React.ReactNode }) {
  return (
    <PainelCowDataTemaProvider>
      <PainelCowDataShell>{children}</PainelCowDataShell>
    </PainelCowDataTemaProvider>
  );
}

// Seletor de 3 vias (escuro/misto/claro) — mesma mecânica de segmented
// control do AparenciaSelector.tsx do site, mas independente dele: este
// painel não segue o tema do site (ver comentário de tokensPainel abaixo).
const OPCOES_TEMA: { valor: TemaPainelCowData; label: string; icon: any }[] = [
  { valor: "escuro", label: "Escuro", icon: Moon },
  { valor: "misto", label: "Misto", icon: SunMoon },
  { valor: "claro", label: "Claro", icon: Sun },
];

function AparenciaPainelCowData({ cor }: { cor: ReturnType<typeof usePainelCowDataTema>["cor"] }) {
  const { tema, setTema } = usePainelCowDataTema();
  return (
    <div style={{ display: "flex", gap: "0.2rem", padding: "0.2rem", borderRadius: 999, background: cor.bg, border: `1px solid ${cor.borda}` }}>
      {OPCOES_TEMA.map((op) => {
        const Icon = op.icon;
        const ativo = tema === op.valor;
        return (
          <button key={op.valor} onClick={() => setTema(op.valor)} title={`Aparência: ${op.label}`}
            style={{
              display: "flex", alignItems: "center", gap: "0.3rem", padding: "0.3rem 0.55rem", borderRadius: 999,
              border: "none", cursor: "pointer", fontSize: "0.68rem", fontWeight: 700,
              background: ativo ? cor.dourado : "transparent",
              color: ativo ? cor.bg : cor.mudo,
            }}>
            <Icon size={12} /> {op.label}
          </button>
        );
      })}
    </div>
  );
}

function PainelCowDataShell({ children }: { children: React.ReactNode }) {
  const { cor: COR } = usePainelCowDataTema();
  const path = usePathname();
  const router = useRouter();
  const [aberto, setAberto] = useState(false);
  // Cockpit (raiz /painel-cowdata) ainda não tem a área aplicada de verdade
  // na rota (ver AREAS_ENFORCADAS acima) — sem isso, um membro da equipe
  // sem ser dono cairia numa tela quebrada (403 no fetch do resumo) logo
  // após escolher "Painel CowData" no login. Manda pra primeira área de
  // verdade que ele tiver, em vez disso.
  useEffect(() => {
    // "/painel-cowdata/cockpit" é a mesma tela (Cockpit), só que na versão
    // mobile do app (ver InicioMobilePainelCowData) — precisa da MESMA
    // guarda, senão um membro da equipe sem ser dono alcançaria de propósito
    // pela URL uma tela sem a permissão de verdade aplicada na rota.
    if (ehDono() || (path !== "/painel-cowdata" && path !== "/painel-cowdata/cockpit")) return;
    const primeiraArea = GRUPOS.flatMap((g) => g.itens).find((i) => AREAS_ENFORCADAS.includes(i.area) && temAreaPainelCowData(i.area));
    router.replace(primeiraArea?.href || "/");
  }, [path, router]);
  // Chegou aqui pelo item "Painel CowData" do Menu do app (ver
  // app/app/menu/page.tsx) — "voltar à fazenda" precisa cair no /app, nunca
  // no site desktop completo (mesma regra do AuthShell::destinoRaiz). Cobre
  // app nativo E PWA instalado (ver lib/nativo.ts::ehAppOuPwa).
  // "Voltar" tem 3 destinos possíveis: veio do portal Administração (voltar
  // para lá, não para a Capa — ver lib/portalAdministracao.ts), app/PWA
  // nativo (voltar para o Menu do app), ou nenhum dos dois (voltar para a
  // Capa do site, o de sempre).
  const [voltarHref, setVoltarHref] = useState("/");
  const [voltarLabel, setVoltarLabel] = useState("Voltar à fazenda");
  useEffect(() => {
    if (consumirVeioDaAdministracao()) {
      setVoltarHref("/usuarios");
      setVoltarLabel("Voltar à Administração");
      return;
    }
    ehAppOuPwa().then((app) => { if (app) setVoltarHref("/app"); });
  }, []);

  const gruposVisiveis = gruposVisiveisPainelCowData();

  // App nativo/PWA — casca própria (grade de início + telas focadas com
  // botão "voltar", ver components/painel-cowdata/mobile/) em vez da barra
  // lateral/gaveta pensada pro desktop. Pedido explícito do usuário
  // (01/09/2026): "ao clicar em painel CowData no app, abra essa versão".
  const [appMode, setAppMode] = useState(false);
  useEffect(() => { ehAppOuPwa().then(setAppMode); }, []);

  const navConteudo = (
    <>
      <div style={{ padding: "calc(1.1rem + env(safe-area-inset-top, 0px)) 1.1rem 0.9rem" }}>
        <Link href={voltarHref} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", color: COR.mudo, textDecoration: "none", marginBottom: "0.9rem" }}>
          <ArrowLeft size={13} /> {voltarLabel}
        </Link>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
          <CowDataMark size={40} />
          <CowDataWordmark size="1.1rem" cowColor={COR.textoPainel} dataColor={COR.doradoClaro} />
        </div>
        <p style={{ fontSize: "0.62rem", color: COR.mudo, textTransform: "uppercase", letterSpacing: "0.08em", marginTop: "0.4rem" }}>
          Painel da empresa
        </p>
      </div>
      <div style={{ padding: "0 1.1rem 0.9rem" }}>
        <AparenciaPainelCowData cor={COR} />
      </div>
      <nav style={{ flex: 1, padding: "0.4rem 0.8rem", overflowY: "auto" }}>
        {gruposVisiveis.map((g) => (
          <div key={g.titulo} style={{ marginBottom: "1.1rem" }}>
            <p style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: COR.mudo, margin: "0 0 0.4rem 0.5rem" }}>
              {g.titulo}
            </p>
            {g.itens.map((item) => {
              const ativo = item.href === "/painel-cowdata" ? path === item.href : path.startsWith(item.href);
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href} onClick={() => setAberto(false)}
                  style={{
                    display: "flex", alignItems: "center", gap: "0.55rem", padding: "0.45rem 0.6rem", borderRadius: "var(--r-sm)",
                    fontSize: "0.8rem", textDecoration: "none", marginBottom: "0.15rem",
                    color: ativo ? COR.doradoClaro : COR.texto,
                    background: ativo ? "rgba(143,160,181,0.14)" : "transparent",
                    borderLeft: ativo ? `2px solid ${COR.doradoClaro}` : "2px solid transparent",
                  }}>
                  <Icon size={15} /> {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </>
  );

  // FazendasAdmin.tsx (única tela daqui que reaproveita .card/.card-header do
  // site) herdava --surface/--text do TEMA DO SITE (claro/escuro/misto,
  // configurável em Aparência) em vez da paleta fixa deste painel — com o
  // site em tema claro, o texto (quase branco, pensado pra fundo escuro)
  // ficava ilegível sobre o card branco. Redefinindo os tokens aqui, escopados
  // a esta subárvore, qualquer coisa que use .card/.card-header sempre lê
  // certo, independente do tema do site logado.
  const tokensPainel = {
    "--surface": COR.painel, "--surface-2": COR.painelAlt,
    "--border": COR.borda, "--border-strong": COR.bordaClara,
    "--text": COR.texto, "--text-muted": COR.mudo,
    "--card-header-bg": COR.painelAlt, "--card-header-fg": COR.dourado,
    "--pill-active-bg": COR.dourado, "--pill-active-fg": COR.bg,
  } as CSSProperties;

  if (appMode) {
    // Estas 2 rotas trazem a própria tela cheia (cabeçalho incluso) — ver
    // InicioMobilePainelCowData/CockpitMobile. As demais ainda são as telas
    // do site (Fazendas, Usuários, Financeiro CowData etc. — cadastros
    // completos demais pra reconstruir aqui de uma vez); só ganham uma barra
    // mínima de volta, no lugar da gaveta lateral, pra nunca ficarem sem
    // navegação nenhuma dentro do app.
    if (path === "/painel-cowdata" || path === "/painel-cowdata/cockpit") {
      return <div style={{ minHeight: "100vh", background: COR.bg, color: COR.texto, fontFamily: "system-ui, sans-serif", ...tokensPainel }}>{children}</div>;
    }
    const itemAtual = GRUPOS.flatMap((g) => g.itens).find((i) => i.href !== "/painel-cowdata" && path.startsWith(i.href));
    return (
      <div style={{ minHeight: "100vh", background: COR.bg, color: COR.texto, fontFamily: "system-ui, sans-serif", ...tokensPainel }}>
        <div style={{
          display: "flex", alignItems: "center", gap: "0.6rem", borderBottom: `1px solid ${COR.borda}`,
          padding: "calc(0.9rem + env(safe-area-inset-top, 0px)) 1.1rem 0.9rem",
        }}>
          <button onClick={() => router.push("/painel-cowdata")} aria-label="Voltar ao Painel CowData" title="Voltar ao Painel CowData"
            style={{ background: "none", border: "none", color: COR.texto, cursor: "pointer", display: "flex", flexShrink: 0 }}>
            <ArrowLeft size={19} />
          </button>
          <span style={{ fontSize: "1.02rem", fontWeight: 700 }}>{itemAtual?.label || "Painel CowData"}</span>
        </div>
        <div style={{ padding: "1rem 1.1rem 2rem" }}>{children}</div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: COR.bg, color: COR.texto, fontFamily: "system-ui, sans-serif", ...tokensPainel }} className="md:flex">
      {/* Barra superior — só no mobile. Mesmo padrão do Sidebar.tsx do site —
          precisa do MESMO respiro pra status bar/notch (env(safe-area-inset-top))
          e do MESMO offset pra faixa de suporte (--suporte-banner-h) que todo
          outro cabeçalho fixo do app usa (ver app/app/layout.tsx) — sem isso,
          esta barra ficava por baixo da status bar em app instalado/nativo
          (edge-to-edge, ver appleWebApp.statusBarStyle no layout raiz): o
          hambúrguer ficava visualmente atrás do relógio/bateria do celular e
          não recebia toque nenhum (achado real, 01/09/2026). */}
      <div className="md:hidden flex items-center gap-3 px-4 fixed left-0 right-0 z-30"
        style={{
          top: "var(--suporte-banner-h, 0px)",
          height: "calc(3.25rem + env(safe-area-inset-top, 0px))",
          paddingTop: "env(safe-area-inset-top, 0px)",
          background: COR.painel, borderBottom: `1px solid ${COR.borda}`,
        }}>
        <button onClick={() => setAberto(true)} aria-label="Abrir menu" title="Abrir o menu do Painel CowData"
          style={{ background: "none", border: "none", color: COR.textoPainel, cursor: "pointer", display: "flex" }}>
          <Menu size={22} />
        </button>
        <CowDataWordmark size="0.85rem" cowColor={COR.textoPainel} dataColor={COR.doradoClaro} />
        <span style={{ color: COR.mudo, fontSize: "0.7rem" }}>· Painel da empresa</span>
      </div>
      <div className="md:hidden" style={{ height: "calc(3.25rem + env(safe-area-inset-top, 0px))" }} aria-hidden="true" />

      {aberto && <div className="md:hidden fixed inset-0 z-40" style={{ background: "rgba(0,0,0,0.55)" }} onClick={() => setAberto(false)} />}

      <aside
        style={{ width: "15rem", flexShrink: 0, background: COR.painel, borderRight: `1px solid ${COR.borda}`, display: "flex", flexDirection: "column" }}
        className={`fixed md:static inset-y-0 left-0 z-50 transform transition-transform duration-200 ${aberto ? "translate-x-0" : "-translate-x-full"} md:translate-x-0`}
      >
        <button onClick={() => setAberto(false)} aria-label="Fechar menu" title="Fechar o menu do Painel CowData"
          className="md:hidden"
          style={{ position: "absolute", top: 12, right: 12, background: "none", border: "none", color: COR.mudo, cursor: "pointer" }}>
          <X size={20} />
        </button>
        {navConteudo}
      </aside>
      <main style={{ flex: 1, padding: "1.2rem 1rem", overflowY: "auto", overflowX: "hidden" }} className="md:py-8 md:px-10">{children}</main>
    </div>
  );
}
