"use client";
// Lançar › Reprodutivo › Parto / nascimento — tela gerencial (passos numerados, tabela com caixas, barra fixa no pé).
// Substitui o formulário antigo (25 campos, duas colunas com rolagem própria). Mantém o export, o nome e as props
// (animais, lotes, onSalvo), então app/lancamentos/page.tsx não muda. Peças visuais: components/gerencial/telas/PartoPecas.tsx;
// regras puras (sexo obrigatório, payloads, colostro): lib/partoLancamento.ts (testado em lib/partoLancamento.test.ts).
//
// Endpoints (iguais aos do formulário antigo): POST /reproducao/parto · POST /reproducao/encerramento-gestacao (aborto) ·
// POST /sanidade/colostragem (um por cria) · POST /producao/sugestao-lote-evento · POST /movimentacoes/mover · POST /lotes/preview
// (Categoria) · GET /parametros/transferencia-lote-automatica.
// Falha da colostragem ou do lote NUNCA desfaz o parto já salvo: vira "Atenção: …" no retorno da barra.
import React, { useEffect, useMemo, useState } from "react";
import {
  criarMovimentacao, criarParto, encerrarGestacao, fetchTransferenciaLoteAutomatica, previewCriteriosLote, registrarColostragem,
  sugestaoLoteEvento, type LoteSugeridoEvento,
} from "@/lib/api";
import type { AnimalRow } from "@/components/AnimalModal";
import { codigoGrupo } from "@/components/lancamentos/comumForms";
import { CATEGORIAS_ANIMAIS } from "@/components/lancamentos/_shared";
import { PopupAborto } from "@/components/lancamentos/PopupAborto";
import { Ajuda, BarraAcao, BotaoOuro, Faixa, Passo, Pilulas } from "@/components/gerencial/kit";
import { BuscaMatrizes, EstiloRepro, PilulasX, alterna, fmtData } from "@/components/gerencial/telas/ReprodutivoComum";
import {
  EstiloParto, PainelColostro, PainelLotes, TabelaPartos, type CriaColostro, type ItemRevisaoLote, type MaeLinha,
} from "@/components/gerencial/telas/PartoPecas";
import { hojeLocal, somaDias } from "@/lib/financeiroSituacao";
import { invalidarEstadosReprodutivos, useEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { normalizarBusca } from "@/lib/busca";
import {
  abortosSemResposta, baixada2Efetiva, baixadaEfetiva, chaveCria, colostroTemDado, colostroVazio, ehAborto, linhaEfetiva,
  linhaVazia, payloadColostragem, payloadParto, problemasDeSalvar, relativoPrevisto, resumoDosPartos, TIPOS_PARTO_LOTE,
  type Colostro, type EfetivaParto, type LinhaParto,
} from "@/lib/partoLancamento";

type Modo = "animal" | "lote" | "categoria";
type PendenciaLote = { numero: string; rotuloAnimal: string; loteSugerido: LoteSugeridoEvento; motivo: string; data: string };
type ErroComMsg = { message?: string };
const msgDe = (e: unknown) => (e as ErroComMsg | null)?.message;
type Retorno = { ok: string; atencao: string[]; erros: string[]; movidos: string[] };

const soData = (iso: string | null | undefined) => (iso && /^\d{4}-\d{2}-\d{2}/.test(iso) ? iso.slice(0, 10) : null);
const ehFemeaAtiva = (a: AnimalRow) => (a.sexo || "").toUpperCase() !== "M" && a.ativo !== false;

export function FormParto({ animais, lotes, onSalvo }: { animais: AnimalRow[]; lotes: string[]; onSalvo?: () => void }) {
  const hoje = useMemo(() => hojeLocal(), []);
  const { porNumero, rotuloDe } = useEstadosReprodutivos();

  const [modo, setModo] = useState<Modo>("animal");
  const modoLote = modo !== "animal";

  // "Uma matriz": linhas adicionadas (uma por parto). Lote/Categoria: dados por matriz e marcação própria.
  const [adds, setAdds] = useState<string[]>([]);
  const [dadosAnimal, setDadosAnimal] = useState<Record<string, LinhaParto>>({});
  const [colostros, setColostros] = useState<Record<string, Colostro>>({});
  const [busca, setBusca] = useState("");
  const [abertas, setAbertas] = useState<Set<string>>(new Set());

  const [lote, setLote] = useState("");
  const [cats, setCats] = useState<string[]>([]);
  const [catsCarregadas, setCatsCarregadas] = useState<{ chave: string; nums: string[] }>({ chave: "", nums: [] });
  const [dadosLote, setDadosLote] = useState<Record<string, LinhaParto>>({});
  const [marcLote, setMarcLote] = useState<Set<string>>(new Set());
  const [lancadosLote, setLancadosLote] = useState<Set<string>>(new Set());
  const [dataTodas, setDataTodas] = useState(hoje);
  const [tipoTodas, setTipoTodas] = useState("");

  const [salvando, setSalvando] = useState(false);
  const [retorno, setRetorno] = useState<Retorno | null>(null);
  const [filaAborto, setFilaAborto] = useState<string[]>([]);
  const [filaLotes, setFilaLotes] = useState<PendenciaLote[]>([]);
  const [lotesAberto, setLotesAberto] = useState(false);
  const [movendoLote, setMovendoLote] = useState(false);

  // Configurações > Parâmetros > "transferir para o lote sugerido automaticamente": mãe e crias vão sozinhas, sem revisão.
  const [transferenciaAutomatica, setTransferenciaAutomatica] = useState(false);
  useEffect(() => { fetchTransferenciaLoteAutomatica().then(setTransferenciaAutomatica).catch(() => {}); }, []);

  const opcoesLote = useMemo(
    () => lotes.map((l) => ({ codigo: codigoGrupo(l), rotulo: l })).filter((o): o is { codigo: string; rotulo: string } => !!o.codigo),
    [lotes],
  );
  const porNum = useMemo(() => new Map(animais.map((a) => [a.numero, a])), [animais]);

  // Categoria: união das categorias marcadas (mesmo motor de critérios de Configurações > Lotes — POST /lotes/preview).
  const chaveCats = [...cats].sort().join("|");
  useEffect(() => {
    if (!cats.length) return;
    let vivo = true;
    Promise.all(cats.map((id) => {
      const cat = CATEGORIAS_ANIMAIS.find((c) => c.id === id);
      if (!cat) return Promise.resolve([] as string[]);
      return previewCriteriosLote(cat.criterios).then((r: { animais?: string[] }) => r.animais || []).catch(() => [] as string[]);
    })).then((listas) => { if (vivo) setCatsCarregadas({ chave: chaveCats, nums: Array.from(new Set(listas.flat())) }); });
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chaveCats]);
  const carregandoCats = cats.length > 0 && catsCarregadas.chave !== chaveCats;
  const uniaoCats = useMemo(() => (cats.length > 0 && catsCarregadas.chave === chaveCats ? catsCarregadas.nums : []), [cats.length, catsCarregadas, chaveCats]);

  // Lote/Categoria: matrizes da fonte escolhida (só fêmeas ativas — macho/baixado não pare).
  const fonteLote = useMemo<AnimalRow[]>(() => {
    if (modo === "lote") return lote ? animais.filter((a) => a.grupo_primario === lote && ehFemeaAtiva(a)) : [];
    if (modo === "categoria") { const s = new Set(uniaoCats); return animais.filter((a) => s.has(a.numero) && ehFemeaAtiva(a)); }
    return [];
  }, [modo, lote, uniaoCats, animais]);
  const fonteLoteVis = useMemo(() => fonteLote.filter((a) => !lancadosLote.has(a.numero)), [fonteLote, lancadosLote]);

  // Decisão do dono: no Lote/Categoria ficam marcadas TODAS as matrizes (como no formulário antigo).
  const chaveFonte = `${modo}|${lote}|${uniaoCats.join(",")}`;
  const [chaveVista, setChaveVista] = useState(chaveFonte);
  if (chaveVista !== chaveFonte) {
    // Troca de lote/categoria: reaplica "todas marcadas" (ajuste de estado durante a renderização, sem efeito).
    setChaveVista(chaveFonte);
    setMarcLote(new Set(fonteLote.map((a) => a.numero)));
    setLancadosLote(new Set());
  }

  const dados = modoLote ? dadosLote : dadosAnimal;
  const setDados = modoLote ? setDadosLote : setDadosAnimal;
  const muda = (n: string, p: Partial<LinhaParto>) => setDados((d) => ({ ...d, [n]: { ...(d[n] ?? linhaVazia(hoje)), ...p } }));

  function infoMae(n: string): MaeLinha {
    const a = porNum.get(n);
    const e = porNumero.get(n);
    const cod = codigoGrupo(a?.grupo_primario) ?? a?.grupo_primario ?? "—";
    const prev = soData(e?.parto_previsto);
    const sub = e?.estado === "gestante" && prev
      ? `${cod} · prevista ${fmtData(prev, true)} (${relativoPrevisto(prev, hoje)})`
      : `${cod} · ${rotuloDe(n)}`;
    return { n, lote: a?.grupo_primario ?? "", sub };
  }

  const linhasVis: MaeLinha[] = useMemo(
    () => (modoLote ? fonteLoteVis.map((a) => a.numero) : adds).map(infoMae),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [modoLote, fonteLoteVis, adds, porNum, porNumero, hoje],
  );
  const marc: ReadonlySet<string> = useMemo(() => (modoLote ? marcLote : new Set(adds)), [modoLote, marcLote, adds]);

  function aoMarcar(n: string) {
    if (!modoLote) {
      setAdds((a) => a.filter((x) => x !== n));
      return;
    }
    setMarcLote((m) => alterna(m, n));
  }
  function adiciona(n: string) {
    if (adds.includes(n)) return;
    setAdds((a) => [...a, n]);
    setDadosAnimal((d) => ({ ...d, [n]: d[n] ?? linhaVazia(hoje) }));
    setBusca("");
  }
  function trocaModo(m: Modo) { setModo(m); setRetorno(null); }
  const alternaCat = (id: string) => setCats((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));

  // Sugestões de "Uma matriz": gestantes com parto previsto nos próximos 3 dias (e as atrasadas); ou o resultado da busca.
  const sugestoes = useMemo(() => {
    const q = normalizarBusca(busca.trim());
    if (q) {
      return animais
        .filter((a) => ehFemeaAtiva(a) && !adds.includes(a.numero) && normalizarBusca(`${a.numero} ${a.grupo_primario ?? ""}`).includes(q))
        .slice(0, 8).map((a) => ({ n: a.numero, rot: soData(porNumero.get(a.numero)?.parto_previsto) }));
    }
    const lim = somaDias(hoje, 3);
    return animais
      .filter((a) => ehFemeaAtiva(a) && !adds.includes(a.numero))
      .map((a) => ({ n: a.numero, e: porNumero.get(a.numero) }))
      .filter((x) => x.e?.estado === "gestante" && soData(x.e?.parto_previsto) && soData(x.e?.parto_previsto)! <= lim)
      .sort((p, q2) => soData(p.e?.parto_previsto)!.localeCompare(soData(q2.e?.parto_previsto)!))
      .slice(0, 12).map((x) => ({ n: x.n, rot: soData(x.e?.parto_previsto) }));
  }, [busca, animais, adds, porNumero, hoje]);

  // Faixa de números (o estado do mundo antes de lançar).
  const faixa = useMemo(() => {
    const carregado = porNumero.size > 0;
    const gest = animais.filter((a) => a.ativo !== false).map((a) => ({ a, prev: porNumero.get(a.numero)?.estado === "gestante" ? soData(porNumero.get(a.numero)?.parto_previsto) : null })).filter((x) => x.prev);
    const v = (n: number) => (carregado ? n : "—");
    return [
      { rotulo: "A parir em 7 dias", valor: v(gest.filter((x) => x.prev! <= somaDias(hoje, 7)).length) },
      { rotulo: "Passaram da data prevista", valor: v(gest.filter((x) => x.prev! < hoje).length), tom: "atencao" as const },
      { rotulo: "Partos lançados hoje", valor: animais.filter((a) => soData(a.data_ult_parto) === hoje).length, tom: "ok" as const },
      { rotulo: "Novilhas a parir em 15 dias", valor: v(gest.filter((x) => /novilha/i.test(x.a.categoria_abrev || x.a.categoria_completa || "") && x.prev! <= somaDias(hoje, 15)).length) },
    ];
  }, [animais, porNumero, hoje]);

  // Efeito do que está marcado.
  const efetivas: EfetivaParto[] = useMemo(
    () => linhasVis.filter((g) => marc.has(g.n)).map((g) => ({ n: g.n, l: linhaEfetiva(dados[g.n] ?? linhaVazia(hoje), modoLote, dataTodas, tipoTodas) })),
    [linhasVis, marc, dados, modoLote, dataTodas, tipoTodas, hoje],
  );
  const resumo = resumoDosPartos(efetivas);
  const problemas = problemasDeSalvar(efetivas);
  const existentes = useMemo(() => new Set(animais.map((a) => a.numero)), [animais]);
  const repetidas = new Set(problemas.repetidas);
  const bloqueado = efetivas.length === 0 || problemas.semSexo.length > 0 || problemas.semData.length > 0 || problemas.repetidas.length > 0;

  // Colostro/IgG: um registro por cria que vai ser cadastrada (número informado e não baixada). Só em "Uma matriz".
  const criasColostro: CriaColostro[] = [];
  const criasSemColostro: string[] = [];
  if (!modoLote) {
    for (const e of efetivas) {
      if (ehAborto(e.l)) continue;
      const c1 = e.l.cria.trim();
      if (c1) { if (baixadaEfetiva(e.l)) criasSemColostro.push(c1); else criasColostro.push({ chave: chaveCria(e.n, 1), cria: c1, mae: e.n, ordem: 1 }); }
      const c2 = e.l.gemelar ? e.l.cria2.trim() : "";
      if (c2) { if (baixada2Efetiva(e.l)) criasSemColostro.push(c2); else criasColostro.push({ chave: chaveCria(e.n, 2), cria: c2, mae: e.n, ordem: 2 }); }
    }
  }
  const mudaColostro = (chave: string, patch: Partial<Colostro>) => setColostros((c) => ({ ...c, [chave]: { ...(c[chave] ?? colostroVazio()), ...patch } }));

  /* ───────────── lote (sugestão do motor de critérios) ───────────── */
  async function prepararPendenciaLote(
    numero: string, rotuloAnimal: string, categoriaAbrev: string, extra: { del_dias?: number | null; data_nasc?: string | null },
    loteAtualRotulo: string | null, motivo: string, data: string, falhas: string[],
  ): Promise<PendenciaLote | null> {
    try {
      const { lote_sugerido } = await sugestaoLoteEvento({ numero_matriz: numero, categoria_abrev: categoriaAbrev, ...extra });
      if (!lote_sugerido) return null; // nenhum lote bate nos critérios — segue sem perguntar
      if (loteAtualRotulo && lote_sugerido.rotulo === loteAtualRotulo) return null; // já está lá
      return { numero, rotuloAnimal, loteSugerido: lote_sugerido, motivo, data };
    } catch (e) {
      falhas.push(`sugestão de lote para ${numero} não pôde ser calculada${msgDe(e) ? `: ${msgDe(e)}` : ""}`);
      return null;
    }
  }
  // Aloca sem perguntar (parâmetro ligado, ou cria no Lote/Categoria). Só afirma "movido" se o servidor confirmar.
  async function alocarSemConfirmar(numero: string, categoriaAbrev: string, extra: { del_dias?: number | null; data_nasc?: string | null }, motivo: string, data: string, falhas: string[]) {
    try {
      const { lote_sugerido } = await sugestaoLoteEvento({ numero_matriz: numero, categoria_abrev: categoriaAbrev, ...extra });
      if (!lote_sugerido) return null;
      const r = await criarMovimentacao({ data_movimento: data, motivo, lote_destino_codigo: lote_sugerido.codigo, animais: [numero], origem: "sugestao_automatica" });
      const moveuDeFato = (r.movidos ?? 0) >= 1 && !(r.nao_encontrados || []).includes(numero);
      if (!moveuDeFato) { falhas.push(`${numero} não foi movido para o lote ${lote_sugerido.rotulo} (a movimentação não foi confirmada pelo servidor)`); return null; }
      return lote_sugerido.rotulo as string;
    } catch (e) {
      falhas.push(`alocação do animal ${numero} não pôde ser feita${msgDe(e) ? `: ${msgDe(e)}` : ""}`);
    }
    return null;
  }

  async function confirmarLotes(escolhas: Record<string, string>) {
    const pendentes = filaLotes;
    setMovendoLote(true);
    const movidos: string[] = []; const falhas: string[] = [];
    for (const pend of pendentes) {
      const codigo = escolhas[pend.numero];
      if (!codigo) continue; // "Não movimentar"
      const rotulo = opcoesLote.find((o) => o.codigo === codigo)?.rotulo || codigo;
      try {
        const r = await criarMovimentacao({ data_movimento: pend.data, motivo: pend.motivo, lote_destino_codigo: codigo, animais: [pend.numero], origem: "sugestao_confirmada" });
        const moveuDeFato = (r.movidos ?? 0) >= 1 && !(r.nao_encontrados || []).includes(pend.numero);
        if (moveuDeFato) movidos.push(`${pend.numero} → ${rotulo}`);
        else falhas.push(`Não foi possível confirmar a movimentação de ${pend.numero} para o lote ${rotulo}.`);
      } catch (e) {
        falhas.push(`Erro ao mover ${pend.numero}: ${msgDe(e) || "erro desconhecido"}.`);
      }
    }
    setRetorno((r) => (r ? { ...r, movidos: [...r.movidos, ...movidos], erros: [...r.erros, ...falhas] } : { ok: "", atencao: [], erros: falhas, movidos }));
    setMovendoLote(false); setFilaLotes([]); setLotesAberto(false);
  }

  /* ───────────── salvar ───────────── */
  async function executarSalvar(dadosUsados: Record<string, LinhaParto>) {
    setSalvando(true); setRetorno(null); setFilaLotes([]); setLotesAberto(false);
    const alvos = linhasVis.filter((g) => marc.has(g.n)).map((g) => ({ n: g.n, l: linhaEfetiva(dadosUsados[g.n] ?? linhaVazia(hoje), modoLote, dataTodas, tipoTodas) }));
    const salvos: string[] = [];
    const partosOk: { n: string; ordem: number | null }[] = []; const abortosOk: string[] = []; const criasOk: string[] = [];
    const erros: string[] = []; const falhasEfeito: string[] = []; const movidosAuto: string[] = [];
    const pendencias: PendenciaLote[] = [];
    let lactacoesAbertas = 0;

    for (const { n, l } of alvos) {
      try {
        if (ehAborto(l)) {
          // Aborto não é parto: perda de prenhez no serviço certo (+ lactação com a data real, se escolhido).
          const r = await encerrarGestacao({ numero_matriz: n, data: l.data, tipo: "aborto", abrir_lactacao: l.lact === "sim", motivo: "aborto" });
          abortosOk.push(n); salvos.push(n);
          if (r.lactacao_aberta) lactacoesAbertas += 1;
          if (r.sugerir_lote) {
            const loteAtual = porNum.get(n)?.grupo_primario || null;
            const delDias = r.del_dias ?? 0;
            if (transferenciaAutomatica) {
              const destino = await alocarSemConfirmar(n, "Vaca", { del_dias: delDias }, "Aborto", l.data, falhasEfeito);
              if (destino) movidosAuto.push(`${n} → ${destino}`);
            } else {
              const pend = await prepararPendenciaLote(n, "a vaca", "Vaca", { del_dias: delDias }, loteAtual, "Aborto", l.data, falhasEfeito);
              if (pend) pendencias.push(pend);
            }
          }
          continue;
        }

        const r = await criarParto(payloadParto(n, l));
        partosOk.push({ n, ordem: r.ordem_parto ?? null }); salvos.push(n);
        const criadas: string[] = r.crias_criadas || [];
        criasOk.push(...criadas);
        const sexoDa = (c: string) => (c === l.cria2.trim() && l.gemelar ? l.sexo2 : l.sexo);
        const categoriaDa = (c: string) => (sexoDa(c) === "M" ? "Bezerro" : "Bezerra");

        // Efeitos complementares: nunca desfazem o parto já salvo.
        if (modoLote) {
          // Lote/Categoria: cria alocada sem confirmar; a mãe NÃO é movida automaticamente (evita N confirmações).
          for (const c of criadas) await alocarSemConfirmar(c, categoriaDa(c), { data_nasc: l.data }, "Nascimento", l.data, falhasEfeito);
        } else {
          const loteAtualMae = porNum.get(n)?.grupo_primario || null;
          if (transferenciaAutomatica) {
            const loteMae = await alocarSemConfirmar(n, "Vaca", { del_dias: 0 }, "Parto", l.data, falhasEfeito);
            if (loteMae) movidosAuto.push(`${n} → ${loteMae}`);
            for (const c of criadas) {
              const loteCria = await alocarSemConfirmar(c, categoriaDa(c), { data_nasc: l.data }, "Nascimento", l.data, falhasEfeito);
              if (loteCria) movidosAuto.push(`${c} → ${loteCria}`);
            }
          } else {
            const pendMae = await prepararPendenciaLote(n, "a vaca", "Vaca", { del_dias: 0 }, loteAtualMae, "Parto", l.data, falhasEfeito);
            if (pendMae) pendencias.push(pendMae);
            for (const c of criadas) {
              const pendCria = await prepararPendenciaLote(c, sexoDa(c) === "M" ? "o bezerro" : "a bezerra", categoriaDa(c), { data_nasc: l.data }, null, "Nascimento", l.data, falhasEfeito);
              if (pendCria) pendencias.push(pendCria);
            }
          }
          // Colostro/IgG: um registro POR cria, só das criadas e só se algum dado foi informado.
          const slots: { chave: string; numero: string }[] = [
            ...(l.cria.trim() ? [{ chave: chaveCria(n, 1), numero: l.cria.trim() }] : []),
            ...(l.gemelar && l.cria2.trim() ? [{ chave: chaveCria(n, 2), numero: l.cria2.trim() }] : []),
          ];
          for (const s of slots) {
            const col = colostros[s.chave];
            if (!colostroTemDado(col)) continue;
            if (!criadas.includes(s.numero)) { falhasEfeito.push(`o colostro da cria ${s.numero} não foi gravado (cria baixada ou já cadastrada)`); continue; }
            try { await registrarColostragem(payloadColostragem(s.numero, col!, l.data)); }
            catch (e) { falhasEfeito.push(`a colostragem da cria ${s.numero} não pôde ser gravada${msgDe(e) ? `: ${msgDe(e)}` : ""}`); }
          }
        }
      } catch (e) {
        erros.push(`${n}: ${msgDe(e) || (ehAborto(l) ? "erro ao registrar o aborto" : "erro ao registrar parto")}`);
      }
    }

    // Mensagem de retorno (resumo do que foi gravado).
    const partes: string[] = [];
    if (partosOk.length === 1 && alvos.length === 1) partes.push(`Parto registrado${partosOk[0].ordem != null ? ` (ordem ${partosOk[0].ordem})` : ""} para ${partosOk[0].n}`);
    else if (partosOk.length) partes.push(`${partosOk.length} ${partosOk.length === 1 ? "parto registrado" : "partos registrados"}${erros.length ? ` de ${alvos.length}` : ""}`);
    if (abortosOk.length) partes.push(`Aborto registrado para ${abortosOk.join(", ")}${lactacoesAbertas ? ` · lactação aberta em ${lactacoesAbertas}` : ""}`);
    if (criasOk.length) partes.push(`${criasOk.length === 1 ? "cria" : "crias"} ${criasOk.join(" e ")} ${criasOk.length === 1 ? "cadastrada" : "cadastradas"}`);
    if (pendencias.length) partes.push(`${pendencias.length} ${pendencias.length === 1 ? "sugestão" : "sugestões"} de lote aguardando revisão`);
    if (movidosAuto.length) partes.push(`transferido(s) automaticamente: ${movidosAuto.join(", ")}`);
    if (modoLote && partosOk.length) partes.push("a mãe não é movida de lote neste modo (Rebanho › Movimentar animais)");
    setRetorno({ ok: salvos.length ? `✓ ${partes.join(" · ")}.` : "", atencao: falhasEfeito, erros, movidos: [] });
    if (pendencias.length) setFilaLotes(pendencias);

    if (salvos.length) {
      invalidarEstadosReprodutivos();
      if (modoLote) {
        setLancadosLote((s) => new Set([...s, ...salvos]));
        setDadosLote((d) => { const x = { ...d }; salvos.forEach((n) => delete x[n]); return x; });
      } else {
        setAdds((a) => a.filter((n) => !salvos.includes(n)));
        setDadosAnimal((d) => { const x = { ...d }; salvos.forEach((n) => delete x[n]); return x; });
        setColostros((c) => { const x = { ...c }; salvos.forEach((n) => { delete x[chaveCria(n, 1)]; delete x[chaveCria(n, 2)]; }); return x; });
      }
      onSalvo?.();
    }
    setSalvando(false);
  }

  function salvar() {
    if (bloqueado || salvando) return;
    // Aborto sem resposta a "abrir lactação?": o popup pergunta (um por vez) e, no fim, grava tudo.
    const faltam = abortosSemResposta(efetivas);
    if (faltam.length) { setFilaAborto(faltam); return; }
    void executarSalvar(dadosAnimal);
  }
  async function responderAborto(sim: boolean) {
    const n = filaAborto[0];
    const novos = { ...dadosAnimal, [n]: { ...(dadosAnimal[n] ?? linhaVazia(hoje)), lact: (sim ? "sim" : "nao") as LinhaParto["lact"] } };
    setDadosAnimal(novos);
    const resto = filaAborto.slice(1);
    setFilaAborto(resto);
    if (!resto.length) await executarSalvar(novos);
  }

  const rotuloBotao = modoLote
    ? `Salvar ${efetivas.length || ""} ${efetivas.length === 1 ? "parto" : "partos"}`.replace("  ", " ")
    : `Lançar ${efetivas.length || ""} ${efetivas.length === 1 ? "registro" : "registros"}`.replace("  ", " ");

  const itensRevisao: ItemRevisaoLote[] = filaLotes.map((p) => ({ numero: p.numero, rotulo: p.rotuloAnimal, sugerido: p.loteSugerido.codigo }));
  const vazioTabela = modoLote
    ? (modo === "lote" ? (lote ? "Nenhuma matriz neste lote." : "Escolha um lote acima para ver as matrizes.") : (cats.length ? (carregandoCats ? "Carregando as matrizes das categorias…" : "Nenhuma matriz nesta(s) categoria(s).") : "Escolha uma ou mais categorias acima para ver as matrizes."))
    : "Adicione a matriz que pariu, nas sugestões acima ou pela busca.";

  return (
    <div className="pt-raiz">
      <EstiloRepro />
      <EstiloParto />
      <Faixa itens={faixa} />

      <Passo n={1} id="pt-p1" titulo="Como lançar">
        <Pilulas<Modo> rotulo="Modo de lançamento" valor={modo} onChange={trocaModo} opcoes={[
          { id: "animal", nome: "Uma matriz", titulo: "Parto de uma matriz (ou de várias, uma linha por parto), com cria, colostragem e IgG" },
          { id: "lote", nome: "Lote", titulo: "Partos simples das matrizes de um lote" },
          { id: "categoria", nome: "Categoria", titulo: "Partos simples das matrizes de uma ou mais categorias" },
        ]} />
        {modo === "lote" && (
          <PilulasX<string> rotulo="Lote" valor={lote} onChange={setLote}
            opcoes={lotes.map((l) => ({ id: l, nome: l, n: animais.filter((a) => a.grupo_primario === l && ehFemeaAtiva(a)).length }))} />
        )}
        {modo === "categoria" && (
          <Pilulas<string> rotulo="Categorias" valor={cats} onChange={alternaCat}
            opcoes={CATEGORIAS_ANIMAIS.map((c) => ({ id: c.id, nome: c.label }))} />
        )}
        {modoLote && (
          <>
            <div className="rp-grade-4" style={{ maxWidth: "36rem", gridTemplateColumns: "repeat(2, minmax(0, 1fr))" }}>
              <div className="gv-campo"><label htmlFor="pt-data-todas">Data do parto (todas)</label>
                <input id="pt-data-todas" type="date" className="rp-input" value={dataTodas} onChange={(e) => setDataTodas(e.target.value)} /></div>
              <div className="gv-campo"><label htmlFor="pt-tipo-todas">Tipo de parto (todas)</label>
                <select id="pt-tipo-todas" className="rp-select" value={tipoTodas} onChange={(e) => setTipoTodas(e.target.value)}>
                  <option value="">Selecione…</option>{TIPOS_PARTO_LOTE.map((t) => <option key={t}>{t}</option>)}
                </select></div>
            </div>
            <Ajuda>
              Modo simplificado: data e tipo valem para todas; por linha você informa nº da cria, sexo, baixada e retenção de placenta. <strong>Aborto, parto gemelar e colostro/IgG ficam só no modo “Uma matriz”.</strong>{" "}
              A cria é alocada no lote sugerido sem perguntar; a mudança de lote das mães não é automática aqui (Rebanho › Movimentar animais).
            </Ajuda>
          </>
        )}
      </Passo>

      <Passo n={2} id="pt-p2" titulo="Partos a lançar" direita={
        <span className="rp-contagem" aria-live="polite">{efetivas.length} de {linhasVis.length} {modoLote ? "marcadas" : efetivas.length === 1 ? "matriz na lista" : "matrizes na lista"}</span>
      }>
        {!modoLote && (
          <div className="rp-ferr">
            <BuscaMatrizes valor={busca} onChange={setBusca} rotulo="Buscar matriz que pariu (nº ou lote)" />
            <div className="rp-tarja">
              <span>{busca.trim() ? "Resultado:" : "Previstas para os próximos 3 dias:"}</span>
              {sugestoes.length === 0 && <span>nenhuma</span>}
              {sugestoes.map((g) => (
                <button key={g.n} type="button" className="rp-chip" onClick={() => adiciona(g.n)} aria-label={`Adicionar ${g.n}`}>
                  + {g.n} {g.rot && <small>{relativoPrevisto(g.rot, hoje)}</small>}
                </button>
              ))}
            </div>
          </div>
        )}
        <TabelaPartos linhasVis={linhasVis} modoLote={modoLote} marc={marc} dados={dados} dataTodas={dataTodas} tipoTodas={tipoTodas}
          abertas={abertas} existentes={existentes} repetidas={repetidas} vazio={vazioTabela}
          onToggle={aoMarcar} onMuda={muda} onAbre={(n) => setAbertas((a) => alterna(a, n))} />
        <Ajuda>
          {modoLote
            ? "Cria em branco = a matriz pariu sem cria cadastrada. Sexo é obrigatório quando há cria. Cria “baixada” não entra no rebanho; natimorto força baixada. Ficam marcadas todas as matrizes da lista; desmarque as que não pariram."
            : <>Número da cria em branco = <strong>sem cria</strong> (natimorto/baixa). <strong>Sexo é obrigatório quando há cria</strong>: o sistema não assume “fêmea”. Retenção de placenta gera item na Agenda. Para mais de uma matriz, adicione quantas precisar: cada linha é um parto.</>}
        </Ajuda>
      </Passo>

      {!modoLote && (
        <Passo n={3} id="pt-p3" titulo="Colostro e IgG de cada cria">
          <PainelColostro crias={criasColostro} dados={colostros} onMuda={mudaColostro} baixadas={criasSemColostro} />
          <Ajuda>Um registro por cria, gravado em Sanidade › Relatório sanitário de bezerras. Se a gravação do colostro falhar, o parto continua salvo e o retorno avisa.</Ajuda>
        </Passo>
      )}

      <BarraAcao
        resumo={`${resumo.registros} ${resumo.registros === 1 ? "registro" : "registros"} · ${resumo.partos} ${resumo.partos === 1 ? "parto" : "partos"} · ${resumo.crias} ${resumo.crias === 1 ? "cria" : "crias"}${resumo.abortos ? ` · ${resumo.abortos} ${resumo.abortos === 1 ? "aborto" : "abortos"}` : ""}`}
        detalhe={problemas.semSexo.length
          ? <span className="rp-err" role="alert">Falta o sexo da cria de {problemas.semSexo.join(", ")} — preencha para lançar.</span>
          : problemas.repetidas.length ? <span className="rp-err" role="alert">Número de cria repetido: {problemas.repetidas.join(", ")}.</span>
          : problemas.semData.length ? <span className="rp-err" role="alert">Informe a data do parto de {problemas.semData.join(", ")}.</span>
          : efetivas.length === 0 ? (modoLote ? "Marque ao menos uma matriz na tabela do passo 2" : "Adicione ao menos uma matriz no passo 2")
          : modoLote ? "Ao salvar, cada cria é alocada no lote sugerido; a mãe não é movida neste modo."
          : transferenciaAutomatica ? "Ao salvar, mãe e crias vão sozinhas para o lote sugerido (parâmetro ligado)."
          : "Ao salvar, sugere o lote da mãe e de cada cria; você confirma antes de mover."}
        retorno={retorno && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", width: "100%", maxHeight: "45vh", overflowY: "auto" }}>
            <div className="rp-retorno-linha">
              <span style={{ display: "flex", flexDirection: "column", gap: "0.2rem", flex: "1 1 20rem", minWidth: 0 }}>
                {retorno.ok && <span className="rp-ok">{retorno.ok}</span>}
                {retorno.movidos.length > 0 && <span className="rp-ok">Movido(s): {retorno.movidos.join(", ")}.</span>}
                {retorno.erros.map((e) => <span key={e} className="rp-err" role="alert">{e}</span>)}
                {retorno.atencao.length > 0 && <span style={{ color: "var(--ft-ouro-txt)", fontWeight: 600 }}>Atenção: {retorno.atencao.join("; ")}.</span>}
              </span>
              {filaLotes.length > 0 && (
                <button type="button" className="btn-secondary" aria-expanded={lotesAberto} onClick={() => setLotesAberto((a) => !a)}>Revisar lotes ({filaLotes.length})</button>
              )}
              <button type="button" className="btn-ghost" onClick={() => { setRetorno(null); setFilaLotes([]); setLotesAberto(false); }} title={filaLotes.length ? "Descarta a revisão de lotes: ninguém é movido" : undefined}>Dispensar</button>
            </div>
            {lotesAberto && filaLotes.length > 0 && (
              <PainelLotes itens={itensRevisao} opcoes={opcoesLote} ocupado={movendoLote} onConfirmar={confirmarLotes} onFechar={() => setLotesAberto(false)} />
            )}
            {filaLotes.length > 0 && (
              <span className="rp-mudo" style={{ fontSize: "0.74rem" }}>Com “transferir para o lote sugerido automaticamente” ligado em Configurações › Parâmetros, mãe e crias são movidas sozinhas e esta revisão não aparece.</span>
            )}
          </div>
        )}
        acao={<BotaoOuro desabilitado={bloqueado || salvando} onClick={salvar}>{salvando ? "Salvando…" : rotuloBotao}</BotaoOuro>}
      />

      {filaAborto.length > 0 && (
        <PopupAborto
          key={filaAborto[0]}
          numeroMatriz={filaAborto[0]}
          // A visibilidade é da fila (filaAborto); a resposta do popup entra no MESMO POST que grava o aborto.
          onFechar={() => {}}
          onResponder={responderAborto}
        />
      )}
    </div>
  );
}
