"use client";
// Tela REBANHO › aba "Ficha do Animal".
// Busca grande + lista completa de animais; ao tocar num animal abre a ficha
// completa (só leitura) numa sub-tela — hoje navegada por CARDS de seção
// (Resumo/Dados Gerais/Reprodução/Produção/Sanidade/Movimentações), no lugar
// do scroll único que a ficha tinha antes. Offline: ficha via cache por
// animal (chave "ficha_<numero>").
//
// Esta fachada faz só três coisas: busca a ficha (com cache offline), guarda
// qual seção está ativa (`secaoAtiva`), e trata o deep link da Agenda
// (`destacarInicial`, que força a entrada direto na seção Sanidade com o
// formulário de colostro já aberto). Todo o conteúdo de cada seção vive em
// `./ficha/SecaoX.tsx` — ver `./ficha/comumFicha.tsx` para os primitivos
// compartilhados (ParDado/Grade/Secao/catálogo de lançamentos).
import { useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { fetchAnimais, fetchFichaAnimal } from "@/lib/api";
import { fetchComCache, cacheEm } from "@/lib/offline";
import { MobCard, MobVoltar, MobLinha } from "@/components/mobile/ui";
import { BuscaAnimal, subtituloAnimal, type AnimalMob } from "./comum";
import { useOrdenacao } from "@/components/Ordenavel";
import { SeletorOrdenacao, type CampoOrdenacao } from "@/components/mobile/SeletorOrdenacao";
import { SeletorSecaoFicha, TITULO_SECAO, type SecaoChave } from "./ficha/SeletorSecaoFicha";
import { SecaoResumo } from "./ficha/SecaoResumo";
import { SecaoDadosGerais } from "./ficha/SecaoDadosGerais";
import { SecaoReproducao } from "./ficha/SecaoReproducao";
import { SecaoProducao } from "./ficha/SecaoProducao";
import { SecaoSanidade } from "./ficha/SecaoSanidade";
import { SecaoMovimentacoes } from "./ficha/SecaoMovimentacoes";
import type { Ficha } from "./ficha/comumFicha";

// Campos ordenáveis da lista "Todos os animais" (Rebanho › Ficha do animal).
const CAMPOS_ORDENACAO: CampoOrdenacao[] = [
  { chave: "numero", rotulo: "Brinco" },
  { chave: "nome", rotulo: "Nome" },
  { chave: "grupo_primario", rotulo: "Lote" },
  { chave: "categoria_abrev", rotulo: "Categoria" },
  { chave: "del_dias", rotulo: "DEL" },
];

/** Cartão de identidade (número, badge Ativo/Baixado, nome/raça/categoria,
 * lote) — mostrado só na grade de seleção de seção, não repetido em cada
 * seção (o cabeçalho de cada seção já leva "Nº — Nome" como subtítulo, ver
 * `MobVoltar`). O ícone de lápis ao lado do lote é só indicativo (a edição
 * de lote em si é feita em Lançar › Movimentar, fora do escopo desta ficha
 * só-leitura) — não é clicável. */
function IdentidadeFicha({ ficha }: { ficha: Ficha }) {
  const a = ficha.animal;
  const nome = a.nome ? String(a.nome) : null;
  const raca = a.raca ? String(a.raca) : null;
  const categoria = (a.categoria_completa || a.categoria_abrev) ? String(a.categoria_completa || a.categoria_abrev) : null;
  const subtitulo = [nome, [raca, categoria].filter(Boolean).join(" · ")].filter(Boolean).join(" — ");
  return (
    <MobCard style={{ marginBottom: "0.85rem" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: "0.55rem", flexWrap: "wrap" }}>
        <span style={{ fontSize: "1.15rem", fontWeight: 800 }}>Nº {String(a.numero)}</span>
        <span style={{ fontSize: "0.68rem", fontWeight: 800, letterSpacing: "0.04em", textTransform: "uppercase", padding: "0.14rem 0.5rem", border: `1px solid ${a.ativo === false ? "var(--mob-vermelho)" : "var(--mob-verde)"}`, color: a.ativo === false ? "var(--mob-vermelho)" : "var(--mob-verde)" }}>
          {a.ativo === false ? "Baixado" : "Ativo"}
        </span>
      </div>
      {subtitulo && <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>{subtitulo}</div>}
      {a.grupo_primario != null && a.grupo_primario !== "" && (
        <div style={{ marginTop: "0.65rem" }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.72rem", fontWeight: 600, padding: "0.28rem 0.6rem", background: "var(--mob-surface-2)", border: "1px solid var(--mob-border)", color: "var(--mob-text)" }}>
            {String(a.grupo_primario)}
            <Pencil size={11} style={{ color: "var(--mob-muted)" }} />
          </span>
        </div>
      )}
    </MobCard>
  );
}

// Exportado para telas fora de Rebanho (ex.: Menu › Agenda do Veterinário,
// Rebanho › Indicadores) abrirem a ficha do animal com seu próprio "voltar"
// local, sem navegar para a aba Rebanho.
export function FichaDetalhe({ numero, onVoltar, destacarInicial }: { numero: string; onVoltar: () => void; destacarInicial?: "colostragem" | "igg" | null }) {
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [doCache, setDoCache] = useState(false);
  const [secaoAtiva, setSecaoAtiva] = useState<SecaoChave | null>(null);

  // Chegou da Agenda com uma pendência de colostro/IgG: assim que a ficha
  // carrega, entra direto na seção Sanidade (o formulário de colostro abre
  // sozinho lá dentro — ver SecaoSanidade, que recebe `destacarInicial` só
  // uma vez, na montagem). Sem isto, quem vem do deep link cairia na grade
  // de seleção sem nada destacado.
  const [precisaAbrirSanidade, setPrecisaAbrirSanidade] = useState(!!destacarInicial);

  useEffect(() => {
    let vivo = true;
    setCarregando(true); setErro(null);
    fetchComCache<Ficha>(`ficha_${numero}`, () => fetchFichaAnimal(numero))
      .then(({ dados, doCache }) => {
        if (!vivo) return;
        if (dados) {
          setFicha(dados);
          setDoCache(doCache);
        } else {
          setErro("Sem internet e sem cópia salva desta ficha.");
        }
      })
      .catch((e) => { if (vivo) setErro(e?.message || "Erro ao carregar ficha."); })
      .finally(() => { if (vivo) setCarregando(false); });
    return () => { vivo = false; };
  }, [numero]);

  useEffect(() => {
    if (ficha && precisaAbrirSanidade) {
      setSecaoAtiva("sanidade");
      setPrecisaAbrirSanidade(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ficha]);

  async function recarregarFicha() {
    const { dados } = await fetchComCache<Ficha>(`ficha_${numero}`, () => fetchFichaAnimal(numero));
    if (dados) setFicha(dados);
  }

  const a = ficha?.animal;
  const nomeAnimal = a?.nome ? String(a.nome) : null;

  return (
    <div>
      {!secaoAtiva ? (
        <MobVoltar titulo={`Brinco ${numero}`} onVoltar={onVoltar} />
      ) : (
        <MobVoltar
          titulo={TITULO_SECAO[secaoAtiva]}
          subtitulo={`Nº ${numero}${nomeAnimal ? ` — ${nomeAnimal}` : ""}`}
          onVoltar={() => setSecaoAtiva(null)}
        />
      )}

      {carregando && <p style={{ color: "var(--mob-muted)" }}>Carregando ficha…</p>}
      {erro && <p style={{ color: "var(--mob-vermelho)", fontWeight: 600 }}>{erro}</p>}

      {ficha && a && (
        <>
          {doCache && !secaoAtiva && (
            <p style={{ fontSize: "0.78rem", color: "var(--mob-ambar)", fontWeight: 600, marginBottom: "0.6rem" }}>
              Mostrando cópia salva{cacheEm(`ficha_${numero}`) ? ` em ${new Date(cacheEm(`ficha_${numero}`)!).toLocaleString("pt-BR")}` : ""}.
            </p>
          )}

          {!secaoAtiva && (
            <>
              <IdentidadeFicha ficha={ficha} />
              <SeletorSecaoFicha onEscolher={setSecaoAtiva} />
            </>
          )}

          {secaoAtiva === "resumo" && <SecaoResumo ficha={ficha} />}
          {secaoAtiva === "dados_gerais" && <SecaoDadosGerais ficha={ficha} />}
          {secaoAtiva === "reproducao" && <SecaoReproducao ficha={ficha} />}
          {secaoAtiva === "producao" && <SecaoProducao ficha={ficha} numero={numero} />}
          {secaoAtiva === "sanidade" && (
            <SecaoSanidade
              ficha={ficha}
              numero={numero}
              destacarInicial={destacarInicial ?? null}
              recarregarFicha={recarregarFicha}
            />
          )}
          {secaoAtiva === "movimentacoes" && <SecaoMovimentacoes ficha={ficha} />}
        </>
      )}
    </div>
  );
}

export default function Ficha({ numeroInicial, destacarInicial }: { numeroInicial?: string | null; destacarInicial?: string | null } = {}) {
  const [aberto, setAberto] = useState<string | null>(numeroInicial ?? null);
  const [animais, setAnimais] = useState<AnimalMob[]>([]);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let vivo = true;
    fetchComCache<AnimalMob[]>("animais", () => fetchAnimais()).then(({ dados }) => {
      if (vivo) { setAnimais(dados || []); setCarregando(false); }
    });
    return () => { vivo = false; };
  }, []);

  const destacar = destacarInicial === "colostragem" || destacarInicial === "igg" ? destacarInicial : null;

  // Ordem padrão (nenhum campo escolhido no seletor): por brinco, como sempre
  // foi — o useOrdenacao só assume o controle depois que o usuário escolhe um
  // campo em SeletorOrdenacao. Precisa vir ANTES do "if (aberto) return" — hooks
  // não podem ser condicionais.
  const porNumero = [...animais].sort((a, b) => a.numero.localeCompare(b.numero, "pt-BR", { numeric: true }));
  const ord = useOrdenacao(porNumero);

  if (aberto) return <FichaDetalhe numero={aberto} onVoltar={() => setAberto(null)} destacarInicial={aberto === numeroInicial ? destacar : null} />;

  return (
    <div>
      <BuscaAnimal valor="" onEscolher={(n) => { if (n) setAberto(n); }} />

      <div className="mob-secao">Todos os animais{ord.linhasOrdenadas.length ? ` (${ord.linhasOrdenadas.length})` : ""}</div>
      <SeletorOrdenacao campos={CAMPOS_ORDENACAO} coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
      {carregando && <p style={{ color: "var(--mob-muted)" }}>Carregando…</p>}
      {!carregando && !ord.linhasOrdenadas.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal encontrado.</p>}
      {ord.linhasOrdenadas.map((r, i) => (
        <MobLinha key={r.numero} alt={(i % 2) as 0 | 1} titulo={`Brinco ${r.numero}${r.nome ? ` · ${r.nome}` : ""}`} subtitulo={subtituloAnimal(r)} onClick={() => setAberto(r.numero)} />
      ))}
    </div>
  );
}
