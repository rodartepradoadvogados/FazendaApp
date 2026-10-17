"use client";
// Lançamento de INSEMINAÇÃO — origem → matrizes (tabela com caixas, por lote) → sêmen e touro → data, responsável e vínculo.
// Mesma língua do Diagnóstico de gestação (kit gerencial): faixa de números no topo, passos numerados, aptidão em selo com o
// motivo em texto, barra fixa com o resumo, o retorno do salvamento e o botão em ouro. Roda na gaveta de Lançamentos, na gaveta
// da Agenda (`prefill`) e no destino do Diagnóstico Negativo (`prefill.numeros`).
//
// Quem decide é o servidor: a aptidão de cada fêmea vem de GET /reproducao/aptidao-servico (o MESMO código que dá o 409 ao
// gravar); matriz em protocolo IATF vigente não recebe cio natural / monta natural (só IATF, que vincula e fecha o protocolo).
// Bloqueada = caixa desabilitada com o motivo; "Confirmar" = marcável, o 409 confirmável vira o botão "Confirmar e lançar mesmo assim".
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import {
  ErroApi, criarServicoLote, fetchLancamentosIatf, fetchProtocolosIatfAtivos, fetchSemenDisponivel, fetchSugestaoAcasalamento, fetchTouros,
} from "@/lib/api";
import type { SemenDisponivel, SugestaoAcasalamento, Touro } from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { invalidarEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { AnimalRow } from "@/components/AnimalModal";
import { TouroPicker, type TouroPickerItem } from "@/components/TouroPicker";
import { IDADE_MIN_SERVICO_PADRAO } from "@/components/lancamentos/_shared";
import { useAptidaoServico, useLinhasFemeas } from "@/components/lancamentos/useFemeasServico";
import { Aviso, Ajuda, BarraAcao, BotaoOuro, Faixa, Passo, Pilulas, Selo } from "@/components/gerencial/kit";
import { BuscaMatrizes, EstiloRepro, PilulasX } from "@/components/gerencial/telas/ReprodutivoComum";
import { TabelaFemeas } from "@/components/gerencial/telas/TabelaFemeas";
import {
  alterna, alternaAptas, contagemFaixa, ehApta, filtraLinhas, marcavel, ordenaNumero, resumoSelecao,
} from "@/lib/aptidaoServico";
import { d0Retroativo, fmtData, hojeIso } from "@/lib/iatfCronograma";

type CatTouro = "convencional" | "sexado" | "fazenda";
type Cobertura = "cio_natural" | "iatf" | "monta_natural";
type Origem = "animais" | "lotes" | "protocolo";

const ROTULO_CAT: Record<CatTouro, string> = { convencional: "Convencional", sexado: "Sexado", fazenda: "Touro da fazenda" };
const ROTULO_COB: Record<Cobertura, string> = { cio_natural: "Cio natural", iatf: "IATF", monta_natural: "Monta natural" };
const CATEGORIAS: CatTouro[] = ["convencional", "sexado", "fazenda"];

const CSS = `
.fi-grade-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 24rem), 1fr)); gap: 1.25rem; align-items: start; }
.fi-grade-campos { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 14rem), 1fr)); gap: 0.75rem; align-items: end; }
.fi-grade-sug { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); gap: 0.75rem; }
.fi-check { display: inline-flex; align-items: center; gap: 0.45rem; font-size: 0.82rem; padding: 0.4rem 0; cursor: pointer; color: var(--text); }
.fi-check input { width: 1.05rem; height: 1.05rem; accent-color: var(--ft-ouro); }
`;

export function FormInseminacao({ animais, motivosInaptidao, idadeMinServico = IDADE_MIN_SERVICO_PADRAO, prefill, onSalvo }: {
  animais: AnimalRow[];
  // numero -> motivo de inaptidão DURA que a página antecipa (idade mínima, baixada, a descartar). Vale só enquanto a resposta
  // do servidor (GET /reproducao/aptidao-servico) não chega; depois dela, o servidor manda (inclusive peso e gestante).
  motivosInaptidao?: Map<string, string>;
  idadeMinServico?: number;
  prefill?: { numeroMatriz?: string | null; numeros?: string[]; protocolo?: string | null };
  onSalvo?: () => void;
}) {
  const [origem, setOrigem] = useState<Origem>("animais");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");
  const [preMarcadas, setPreMarcadas] = useState<Set<string>>(new Set());
  const [origemPre, setOrigemPre] = useState<"diagnostico" | "agenda" | null>(null);

  const [dataServico, setDataServico] = useState(() => hojeIso());
  const [tipo, setTipo] = useState<Cobertura>("cio_natural");
  const [categoria, setCategoria] = useState<CatTouro>("convencional");
  const [touro, setTouro] = useState("");
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [catalogoTouros, setCatalogoTouros] = useState<Touro[]>([]);
  const [responsavel, setResponsavel] = useState("");
  const { nomes: nomesResponsaveis } = usePessoasAtivas();

  // IATF: vincular a um lançamento já existente + lançar o D0 retroativo.
  const [protocoloId, setProtocoloId] = useState("");
  const [autoLancar, setAutoLancar] = useState(false);
  const [lancamentos, setLancamentos] = useState<{ lancamento_id: number; nome_protocolo: string; data_d0: string }[]>([]);
  const [semen, setSemen] = useState<SemenDisponivel | null>(null);
  const [protocolosAtivos, setProtocolosAtivos] = useState<{
    lancamento_id: number; nome_protocolo: string; data_d0: string;
    animais: { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null; pronta_para_inseminar?: boolean }[];
  }[]>([]);

  const [sugestao, setSugestao] = useState<SugestaoAcasalamento | null>(null);
  const [carregandoSugestao, setCarregandoSugestao] = useState(false);
  const [erroSugestao, setErroSugestao] = useState<string | null>(null);
  const [sugAberta, setSugAberta] = useState(true);

  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [podeForcar, setPodeForcar] = useState(false);

  // ── dados de apoio ────────────────────────────────────────────────────────────────────────────────────────────
  const carregarProtocolosAtivos = useCallback(() => fetchProtocolosIatfAtivos().then(setProtocolosAtivos).catch(() => setProtocolosAtivos([])), []);
  useEffect(() => {
    carregarProtocolosAtivos();
    fetchSemenDisponivel().then(setSemen).catch(() => setSemen(null));
    fetchLancamentosIatf().then(setLancamentos).catch(() => setLancamentos([]));
  }, [carregarProtocolosAtivos]);
  useEffect(() => {
    if (incluirSemEstoque && !catalogoTouros.length) fetchTouros().then(setCatalogoTouros).catch(() => {});
  }, [incluirSemEstoque, catalogoTouros.length]);
  const itensCatalogo: TouroPickerItem[] = useMemo(
    () => catalogoTouros.map((t) => ({ naab: t.naab, nome: t.nome || t.naab, central: t.central, raca: t.raca, tpi: t.tpi })),
    [catalogoTouros],
  );

  // Vindo da Agenda (link "Ir para Inseminação" do D11) ou do Diagnóstico Negativo: pré-seleciona matriz(es) + IATF.
  // `prefill` (gaveta aberta direto da Agenda) tem prioridade; sem ele, cai na querystring de sempre.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const numeroMatriz = prefill?.numeroMatriz ?? qs.get("numero_matriz");
    // `numeros`: vários animais de uma vez (diagnóstico Negativo → "Lançar inseminação para estas N vacas").
    if (prefill?.numeros?.length) { setSel(new Set(prefill.numeros)); setPreMarcadas(new Set(prefill.numeros)); setOrigemPre("diagnostico"); }
    else if (numeroMatriz) { setSel(new Set([numeroMatriz])); setPreMarcadas(new Set([numeroMatriz])); setOrigemPre("agenda"); }
    if (prefill?.protocolo ?? qs.get("protocolo")) { setTipo("iatf"); setOrigem("protocolo"); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // "Protocolo IATF vigente" = ainda sem inseminação lançada depois do D0; NÃO precisa estar na etapa D11 hoje (a IA pode ser
  // lançada a posteriori, com o hormônio já aplicado há dias).
  const protocolosProntos = useMemo(
    () => protocolosAtivos
      .map((p) => ({ ...p, prontos: p.animais.filter((a) => a.pronta_para_inseminar) }))
      .filter((p) => p.prontos.length > 0),
    [protocolosAtivos],
  );
  const protocoloDoAnimal = useMemo(() => {
    const m = new Map<string, { lancamento_id: number; nome_protocolo: string }>();
    protocolosProntos.forEach((p) => p.prontos.forEach((a) => m.set(a.numero_matriz, p)));
    return m;
  }, [protocolosProntos]);

  // ── regras de cobertura ───────────────────────────────────────────────────────────────────────────────────────
  // Touro da fazenda ⇒ sempre monta natural; origem "Protocolo IATF vigente" ⇒ sempre IATF.
  const tipoEf: Cobertura = origem === "protocolo" ? "iatf" : categoria === "fazenda" ? "monta_natural" : tipo;

  // ── fêmeas, com o veredito do servidor para a data do serviço ─────────────────────────────────────────────────
  const { api, falhou: aptidaoFalhou, recarregar: recarregarAptidao } = useAptidaoServico(dataServico);
  const linhas = useLinhasFemeas({
    animais, api, motivosInaptidao, bloquearEmProtocolo: tipoEf !== "iatf", dataReferencia: dataServico, preMarcadas,
  });
  const lotes = useMemo(() => {
    const m = new Map<string, number>();
    linhas.forEach((l) => m.set(l.lote, (m.get(l.lote) ?? 0) + 1));
    return [...m.entries()].sort(([a], [b]) => ordenaNumero(a, b));
  }, [linhas]);
  const base = useMemo(
    () => (origem === "animais" ? linhas : origem === "lotes" ? linhas.filter((l) => lotesSel.includes(l.lote)) : linhas.filter((l) => protocoloDoAnimal.has(l.numero))),
    [origem, linhas, lotesSel, protocoloDoAnimal],
  );
  const visiveis = useMemo(() => filtraLinhas(base, busca), [base, busca]);
  const faixaN = useMemo(() => contagemFaixa(linhas), [linhas]);

  // Marcada mas bloqueada (a data ou a cobertura mudou): fica de fora do envio, e o aviso diz quem e por quê.
  const bloqueadasNumeros = useMemo(() => new Set(linhas.filter((l) => !marcavel(l)).map((l) => l.numero)), [linhas]);
  const selEfetiva = useMemo(() => new Set([...sel].filter((n) => !bloqueadasNumeros.has(n))), [sel, bloqueadasNumeros]);
  const ignoradas = useMemo(() => linhas.filter((l) => sel.has(l.numero) && !marcavel(l)), [linhas, sel]);
  const alvo = useMemo(() => [...selEfetiva].sort(ordenaNumero), [selEfetiva]);
  const nSel = alvo.length;
  const { pedemConfirmacao } = useMemo(() => resumoSelecao(linhas, selEfetiva), [linhas, selEfetiva]);
  const alvoUnico = nSel === 1 ? alvo[0] : null;

  // Origem "protocolo": quando a seleção pertence a um único lançamento, vincula automaticamente.
  useEffect(() => {
    if (origem !== "protocolo") return;
    const ids = new Set<number>();
    sel.forEach((n) => { const p = protocoloDoAnimal.get(n); if (p) ids.add(p.lancamento_id); });
    setProtocoloId(ids.size === 1 ? String([...ids][0]) : "");
  }, [sel, origem, protocoloDoAnimal]);

  // Sugestão de acasalamento: só com UMA matriz. Falha de forma discreta (animal sem genealogia) sem travar o resto.
  useEffect(() => {
    if (!alvoUnico) { setSugestao(null); setErroSugestao(null); return; }
    let cancelado = false;
    setCarregandoSugestao(true); setErroSugestao(null);
    fetchSugestaoAcasalamento(alvoUnico)
      .then((r) => { if (!cancelado) setSugestao(r); })
      .catch((e) => { if (!cancelado) { setSugestao(null); setErroSugestao(e?.message || "Não foi possível calcular a sugestão de touro para esta matriz."); } })
      .finally(() => { if (!cancelado) setCarregandoSugestao(false); });
    return () => { cancelado = true; };
  }, [alvoUnico]);

  // ── touro e estoque de sêmen ──────────────────────────────────────────────────────────────────────────────────
  const tourosDaCategoria = useMemo(() => (semen?.touros ?? []).filter((t) => t.tipo === categoria), [semen, categoria]);
  const touroEstoque = tourosDaCategoria.find((t) => t.nome === touro);
  const abaixo = semen ? (["convencional", "sexado"] as const).filter((c) => semen.abaixo_minimo[c]) : [];

  function trocaOrigem(o: Origem) {
    setOrigem(o); setBusca(""); setLotesSel([]); setOrigemPre(null); setErro(null); setSucesso(null); setPodeForcar(false);
    // Protocolo vigente: já vêm marcadas as prontas (a tabela mostra quem são; é só desmarcar quem não vai).
    setSel(o === "protocolo" ? new Set(protocoloDoAnimal.keys()) : new Set());
  }
  function alternaLote(lote: string) {
    const ativo = lotesSel.includes(lote);
    setLotesSel(ativo ? lotesSel.filter((l) => l !== lote) : [...lotesSel, lote]);
    // Escolher um lote marca as aptas dele (ajustável na tabela); tirar o lote desmarca as dele.
    const doLote = linhas.filter((l) => l.lote === lote);
    setSel((p) => {
      const s = new Set(p);
      doLote.forEach((l) => { if (ativo) s.delete(l.numero); else if (ehApta(l)) s.add(l.numero); });
      return s;
    });
  }
  function escolheCategoria(c: CatTouro) {
    setCategoria(c); setTouro(""); setIncluirSemEstoque(false);
  }
  function escolheSugestao(s: { nome?: string | null; tipo?: string }) {
    if (s.tipo === "convencional" || s.tipo === "sexado" || s.tipo === "fazenda") { setCategoria(s.tipo); setIncluirSemEstoque(false); }
    setTouro(s.nome || "");
  }

  // ── salvar ────────────────────────────────────────────────────────────────────────────────────────────────────
  async function salvar(forcar = false) {
    setErro(null); setSucesso(null); setPodeForcar(false);
    const alvoEnvio = [...sel].filter((n) => !bloqueadasNumeros.has(n)).sort(ordenaNumero);
    if (!alvoEnvio.length) { setErro("Selecione ao menos uma matriz."); return; }
    if (!dataServico) { setErro("Informe a data da inseminação."); return; }
    setSalvando(true);
    try {
      const r = await criarServicoLote({
        animais: alvoEnvio, data_servico: dataServico, tipo: tipoEf,
        reprodutor: touro || undefined, responsavel: responsavel || undefined,
        protocolo_lancamento_id: tipoEf === "iatf" && protocoloId ? Number(protocoloId) : null,
        auto_lancar_iatf: tipoEf === "iatf" ? autoLancar : false,
        tipo_semen: categoria === "fazenda" ? null : categoria,
        forcar: forcar || undefined,
      });
      const dose = touro && tipoEf !== "monta_natural" && r.criados ? ` · ${touro}: −${r.criados} ${r.criados === 1 ? "dose" : "doses"}` : "";
      if (r.incompativeis.length) {
        setOrigem("animais"); setLotesSel([]); setSel(new Set(r.incompativeis));
        setErro(`${r.incompativeis.join(", ")} não estão em nenhum protocolo IATF. Vincule a um protocolo existente ou marque “Lançar D0 retroativo” e salve de novo.`);
        if (r.criados) setSucesso(`${r.criados} inseminação(ões) registrada(s)${dose}.`);
      } else {
        setSucesso(`${r.criados} ${r.criados === 1 ? "inseminação registrada" : "inseminações registradas"} (${ROTULO_COB[tipoEf].toLowerCase()})${dose}.`);
        setSel(new Set()); setLotesSel([]); setTouro(""); setPreMarcadas(new Set()); setOrigemPre(null);
        onSalvo?.();
      }
      // O estoque de sêmen exibido, a lista de matrizes em protocolo e o estado reprodutivo mudaram: recarrega.
      if (r.criados) {
        invalidarEstadosReprodutivos();
        fetchSemenDisponivel().then(setSemen).catch(() => {});
        carregarProtocolosAtivos();
        recarregarAptidao();
      }
    } catch (e) {
      setErro(e instanceof Error && e.message ? e.message : "Erro ao registrar inseminação");
      // 409 de aptidão CONFIRMÁVEL (peso da novilha lançado abaixo do mínimo, ou matriz que consta gestante): o servidor recusou,
      // mas aceita a decisão de uma pessoa. Idade, a descartar, baixada e "já em protocolo" nunca são confirmáveis.
      if (e instanceof ErroApi && e.status === 409 && e.confirmavel) setPodeForcar(true);
      else if (e instanceof ErroApi && e.status === 409) recarregarAptidao();
    } finally {
      setSalvando(false);
    }
  }

  // ── resumo da barra ───────────────────────────────────────────────────────────────────────────────────────────
  const doseTxt = (() => {
    if (categoria === "fazenda") return touro ? `${touro} (monta natural)` : "touro da fazenda";
    if (!touro) return "sem touro escolhido — nenhuma dose será baixada";
    if (!touroEstoque) return `${touro} (catálogo, sem estoque)`;
    const restam = touroEstoque.doses - nSel;
    return `${touroEstoque.nome} (−${nSel} ${nSel === 1 ? "dose" : "doses"}, ${restam >= 0 ? `restam ${restam}` : `faltam ${-restam}`})`;
  })();
  const resumo = `${nSel} ${nSel === 1 ? "matriz" : "matrizes"} · ${ROTULO_CAT[categoria]} · ${doseTxt}`;
  const detalhe = !nSel ? "Marque ao menos uma matriz na tabela do passo 2"
    : !dataServico ? "Falta a data da inseminação"
    : `${ROTULO_COB[tipoEf]} em ${fmtData(dataServico)}${responsavel ? ` · ${responsavel}` : ""}${pedemConfirmacao ? ` · ${pedemConfirmacao} pede(m) confirmação (o servidor vai perguntar ao salvar)` : ""}`;

  const faixa = [
    { rotulo: "Fêmeas na lista", valor: faixaN.total },
    { rotulo: "Aptas a servir", valor: faixaN.aptas, tom: "ok" as const },
    { rotulo: "Pedem confirmação", valor: faixaN.confirmar, tom: faixaN.confirmar ? ("atencao" as const) : undefined },
    { rotulo: "Bloqueadas", valor: faixaN.bloqueadas },
    { rotulo: "Prontas do protocolo IATF", valor: protocoloDoAnimal.size },
    { rotulo: "Sêmen convencional", valor: semen ? `${semen.totais.convencional}/${semen.minimos.convencional}` : "—", tom: semen?.abaixo_minimo.convencional ? ("alerta" as const) : ("ok" as const) },
    { rotulo: "Sêmen sexado", valor: semen ? `${semen.totais.sexado}/${semen.minimos.sexado}` : "—", tom: semen?.abaixo_minimo.sexado ? ("alerta" as const) : ("ok" as const) },
  ];
  const idadeMin = api?.idade_min_meses ?? idadeMinServico;
  const d0Retro = d0Retroativo(dataServico);
  const nomeProtocoloVinculado = lancamentos.find((l) => String(l.lancamento_id) === protocoloId)?.nome_protocolo
    ?? protocolosAtivos.find((p) => String(p.lancamento_id) === protocoloId)?.nome_protocolo;

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <EstiloRepro />
      <style>{CSS}</style>
      <Faixa itens={faixa} />
      {semen && abaixo.length > 0 && (
        <div style={{ marginBottom: "0.9rem" }}>
          <Aviso tom="erro">
            <AlertTriangle size={15} style={{ marginTop: "0.1rem", flexShrink: 0 }} aria-hidden="true" />
            <span>
              Estoque de sêmen abaixo do mínimo: {abaixo.map((c) => `${c} ${semen.totais[c]}/${semen.minimos[c]}`).join(" · ")}. Registre a compra na NF. Você ainda pode lançar com o que há.
            </span>
          </Aviso>
        </div>
      )}
      {aptidaoFalhou && !api && (
        <div style={{ marginBottom: "0.9rem" }}>
          <Aviso>
            <AlertTriangle size={15} style={{ marginTop: "0.1rem", flexShrink: 0 }} aria-hidden="true" />
            <span>Não consegui conferir a aptidão de cada fêmea agora. A tabela mostra só o que o cadastro já indica; peso e “consta gestante” serão conferidos ao salvar.</span>
          </Aviso>
        </div>
      )}

      <Passo n={1} id="ins-p1" titulo="De onde vêm as matrizes">
        <Pilulas<Origem> rotulo="Origem da inseminação" valor={origem} onChange={trocaOrigem} opcoes={[
          { id: "animais", nome: "Animais", titulo: "Escolher animal por animal na tabela" },
          { id: "lotes", nome: "Lotes", n: lotes.length, titulo: "Escolher um ou mais lotes — entram as aptas de cada um" },
          { id: "protocolo", nome: "Protocolo IATF vigente", n: protocoloDoAnimal.size, titulo: "Matrizes de protocolo IATF vigente ainda sem inseminação lançada — não importa em que etapa do hormônio estão hoje" },
        ]} />
        {origem === "lotes" && (
          <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternaLote} opcoes={lotes.map(([l, n]) => ({ id: l, nome: l, n }))} />
        )}
        {origem === "protocolo" && (
          <Ajuda>
            Só matrizes de protocolo vigente <strong>sem inseminação lançada</strong> (prontas), mesmo que a etapa de hoje não seja a D11. A cobertura passa a ser <strong>IATF</strong>.
            {protocolosProntos.length > 0
              ? <> Em uso: <strong>{protocolosProntos.map((p) => p.nome_protocolo).join(" · ")}</strong>.</>
              : " Nenhuma matriz está em protocolo IATF vigente sem inseminação já lançada."}
          </Ajuda>
        )}
        {origemPre && preMarcadas.size > 0 && (
          <div className="rp-tarja" role="status">
            <Selo tom="info">{origemPre === "agenda" ? "Veio da Agenda" : "Vieram do diagnóstico"}</Selo>
            <span><strong>{preMarcadas.size}</strong> {preMarcadas.size === 1 ? "matriz já marcada" : "matrizes já marcadas"} na tabela abaixo:</span>
            {[...preMarcadas].sort(ordenaNumero).map((n) => <span key={n} className="rp-chip">{n}</span>)}
            <button type="button" className="btn-ghost" onClick={() => { setSel(new Set()); setOrigemPre(null); }}>Desmarcar tudo</button>
          </div>
        )}
      </Passo>

      <Passo n={2} id="ins-p2" titulo="Matrizes" direita={
        <span className="rp-contagem" aria-live="polite">
          {nSel} de {visiveis.length} {nSel === 1 ? "marcada" : "marcadas"}{pedemConfirmacao > 0 && ` · ${pedemConfirmacao} pede(m) confirmação`}
        </span>
      }>
        <div className="rp-ferr">
          <BuscaMatrizes valor={busca} onChange={setBusca} />
          <button type="button" className="btn-ghost" onClick={() => setSel((p) => alternaAptas(p, visiveis))}>Marcar / desmarcar as aptas</button>
          <button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!sel.size}>Limpar seleção</button>
        </div>
        {ignoradas.length > 0 && (
          <Aviso>
            <AlertTriangle size={15} style={{ marginTop: "0.1rem", flexShrink: 0 }} aria-hidden="true" />
            <span>
              Marcadas, mas bloqueadas agora — <strong>não serão enviadas</strong>:{" "}
              {ignoradas.map((l) => `${l.numero} (${l.aptidao.motivo})`).join("; ")}.
            </span>
          </Aviso>
        )}
        <TabelaFemeas
          linhas={visiveis} sel={selEfetiva} mostrarProtocolo altura="36rem" carregando={!animais.length}
          vazio={origem === "lotes" ? "Marque um ou mais lotes acima." : origem === "protocolo" ? "Nenhuma matriz de protocolo vigente pronta para inseminar." : busca ? "Nenhuma fêmea bate com a busca." : "Nenhuma fêmea na lista."}
          onToggle={(n) => setSel((p) => alterna(p, n))}
          onToggleAptas={() => setSel((p) => alternaAptas(p, visiveis))}
          onToggleLote={(_l, itens) => setSel((p) => alternaAptas(p, itens))}
        />
        <Ajuda>
          A lista mostra <strong>todas as fêmeas</strong>. <strong>Bloqueada</strong> (caixa desabilitada, com o motivo): idade mínima de {idadeMin} meses, marcada a descartar, baixada
          {tipoEf !== "iatf" && <> ou já em <strong>protocolo IATF vigente</strong> (com cio natural / monta natural; para ela, lance como IATF)</>}. O servidor recusa.{" "}
          <strong>Confirmar</strong>: peso da novilha lançado abaixo do mínimo e matriz que consta gestante — marcável; ao salvar o servidor pede a sua confirmação.
        </Ajuda>
      </Passo>

      <Passo n={3} id="ins-p3" titulo="Sêmen e touro">
        <div className="fi-grade-2">
          <div className="rp-col">
            <div className="gv-rotulo">Categoria do sêmen</div>
            <PilulasX<CatTouro> rotulo="Categoria do touro / sêmen" valor={categoria} onChange={escolheCategoria} opcoes={[
              { id: "convencional", nome: "Convencional", n: semen?.totais.convencional, titulo: "Doses em estoque" },
              { id: "sexado", nome: "Sexado", n: semen?.totais.sexado, titulo: "Doses em estoque" },
              { id: "fazenda", nome: "Touro da fazenda", titulo: "Monta natural" },
            ]} />
            <div className="gv-rotulo" style={{ marginTop: "0.4rem" }}>Tipo de cobertura</div>
            <PilulasX<Cobertura> rotulo="Tipo de cobertura" valor={tipoEf} onChange={setTipo} opcoes={[
              { id: "cio_natural", nome: "Cio natural", travada: categoria === "fazenda" || origem === "protocolo", titulo: "Inseminação de cio natural (sem protocolo)" },
              { id: "iatf", nome: "IATF", travada: categoria === "fazenda", titulo: "Inseminação de um protocolo IATF" },
              { id: "monta_natural", nome: "Monta natural", travada: origem === "protocolo" || categoria === "fazenda", titulo: "Cobertura por touro (monta natural)" },
            ]} />
            {categoria === "fazenda" && <p className="gv-ajuda">Touro da fazenda escolhido: registrado como <strong>monta natural</strong>.</p>}
            {origem === "protocolo" && <p className="gv-ajuda">Origem “Protocolo IATF vigente”: sempre registrada como <strong>IATF</strong>.</p>}
          </div>

          <div className="rp-col">
            <div className="gv-rotulo">{categoria === "fazenda" ? "Touro (monta natural)" : incluirSemEstoque ? "Touro (catálogo NAAB completo)" : "Touro (em estoque)"}</div>
            {!incluirSemEstoque ? (
              <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "12rem" }}>
                <table className="gv-tabela">
                  <thead><tr>
                    <th scope="col" style={{ width: "2.4rem" }}><span style={{ position: "absolute", left: "-9999px" }}>Escolher</span></th>
                    <th scope="col">Touro</th><th scope="col" className="gv-dir">Doses</th><th scope="col" className="gv-dir">Depois de lançar</th>
                  </tr></thead>
                  <tbody>
                    {tourosDaCategoria.length === 0 && (
                      <tr className="rp-tab-vazia"><td colSpan={4}>Nenhum touro {ROTULO_CAT[categoria].toLowerCase()} em estoque.</td></tr>
                    )}
                    {tourosDaCategoria.map((t) => {
                      const restam = t.doses - nSel;
                      const escolhido = touro === t.nome;
                      return (
                        <tr key={t.nome} className={escolhido ? "gv-linha-marcada" : undefined}>
                          <td><input type="radio" name="ins-touro" checked={escolhido} onChange={() => setTouro(t.nome)} aria-label={`Usar ${t.nome}`} style={{ width: "1.05rem", height: "1.05rem", accentColor: "var(--ft-ouro)" }} /></td>
                          <td className="gv-forte">{t.nome}</td>
                          <td className="gv-num gv-dir">{t.tipo === "fazenda" ? "—" : t.doses}</td>
                          <td className="gv-num gv-dir">
                            {t.tipo === "fazenda" ? "monta natural" : !escolhido ? <span className="rp-mudo">—</span>
                              : restam >= 0 ? <>−{nSel} · restam <b>{restam}</b></> : <span className="rp-err">faltam {-restam}</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="gv-campo" role="group" aria-label="Buscar touro no catálogo NAAB">
                <TouroPicker className="rp-input" itens={itensCatalogo} value={touro} placeholder="Nome, NAAB ou central…"
                  onChangeTexto={setTouro} onSelecionar={(t) => setTouro(t.nome)} />
              </div>
            )}
            {categoria !== "fazenda" && (
              <label className="fi-check" style={{ color: "var(--text-muted)", fontSize: "0.78rem" }}>
                <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => { setIncluirSemEstoque(e.target.checked); setTouro(""); }} />
                Incluir touros sem estoque (catálogo NAAB completo)
              </label>
            )}
          </div>
        </div>

        <div className="rp-recolher">
          <button type="button" className="rp-recolher-topo" aria-expanded={sugAberta && !!alvoUnico} disabled={!alvoUnico} onClick={() => setSugAberta((a) => !a)}>
            <span aria-hidden="true">{sugAberta && alvoUnico ? "▾" : "▸"}</span>
            Sugestão de acasalamento
            <span className="rp-recolher-sub">
              {alvoUnico ? `para a matriz ${alvoUnico} — critérios e touros em estoque` : `só com 1 matriz marcada (agora ${nSel}) — a sugestão pula a seleção em lote`}
            </span>
          </button>
          {sugAberta && alvoUnico && (
            <div className="rp-recolher-corpo">
              {carregandoSugestao && <p className="gv-ajuda">Calculando sugestão…</p>}
              {!carregandoSugestao && erroSugestao && <p className="gv-ajuda" style={{ color: "var(--ft-ambar)" }}>{erroSugestao}</p>}
              {!carregandoSugestao && sugestao && (
                <>
                  {/* Nota fixa, sempre visível: os critérios usados na sugestão. */}
                  <ul className="rp-lista">{sugestao.criterios.map((c, i) => <li key={i}>{c}</li>)}</ul>
                  {!sugestao.sugestoes.length ? (
                    <p className="gv-ajuda">Nenhum touro com sêmen em estoque disponível para sugerir.</p>
                  ) : (
                    <div className="fi-grade-sug">
                      {sugestao.sugestoes.map((s) => (
                        <button key={`${s.naab || ""}-${s.nome || ""}`} type="button" className="rp-sug" data-alerta={s.tem_ancestral_comum}
                          aria-pressed={!!s.nome && touro === s.nome} title="Clique para usar este touro na inseminação" onClick={() => escolheSugestao(s)}>
                          <span className="rp-sug-topo">
                            <span>{s.nome}{s.naab ? ` · ${s.naab}` : ""}</span>
                            <span>{s.tpi != null ? `TPI ${s.tpi} · ` : ""}{s.tipo === "fazenda" ? "monta natural" : `${s.doses ?? 0} dose(s)`}</span>
                          </span>
                          <p>{s.tem_ancestral_comum && <AlertTriangle size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: "0.25rem" }} />}{s.motivo}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </Passo>

      <Passo n={4} id="ins-p4" titulo="Data, responsável e vínculo">
        <div className="fi-grade-campos">
          <div className="gv-campo">
            <label htmlFor="ins-data">Data da inseminação</label>
            <input id="ins-data" type="date" className="rp-input" value={dataServico} onChange={(e) => setDataServico(e.target.value)} />
          </div>
          <div className="gv-campo">
            <label htmlFor="ins-resp">Responsável / inseminador</label>
            <select id="ins-resp" className="rp-select" value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
              <option value="">Selecione…</option>
              {nomesResponsaveis.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          {tipoEf === "iatf" && origem !== "protocolo" && (
            <>
              <div className="gv-campo">
                <label htmlFor="ins-vinculo">Vincular ao protocolo IATF</label>
                <select id="ins-vinculo" className="rp-select" value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
                  <option value="">Automático (o protocolo pendente do animal)</option>
                  {lancamentos.map((l) => <option key={l.lancamento_id} value={l.lancamento_id}>{l.nome_protocolo}</option>)}
                </select>
              </div>
              <div className="gv-campo">
                <span className="gv-rotulo" style={{ fontSize: "0.7rem" }}>Se o animal não estiver em protocolo</span>
                <label className="fi-check">
                  <input type="checkbox" checked={autoLancar} onChange={(e) => setAutoLancar(e.target.checked)} /> Lançar D0 retroativo (serviço − 11 dias)
                </label>
              </div>
            </>
          )}
        </div>
        {tipoEf === "iatf" && origem !== "protocolo" && (
          <Ajuda>
            {autoLancar
              ? <>O D0 será lançado em <strong>{fmtData(d0Retro)}</strong> (data do serviço − 11 dias). Só registra o protocolo — não gera aplicação de hormônio nem baixa de estoque.</>
              : "Sem D0 retroativo, matriz fora de protocolo volta como incompatível e fica marcada para você vincular a um protocolo existente."}
          </Ajuda>
        )}
        {tipoEf === "iatf" && origem === "protocolo" && (
          <Ajuda>
            {protocoloId
              ? <>Vinculado automaticamente ao protocolo <strong>{nomeProtocoloVinculado}</strong>.</>
              : "Cada matriz será vinculada ao seu próprio protocolo IATF em andamento (detectado automaticamente)."}
          </Ajuda>
        )}
        {tipoEf !== "iatf" && <Ajuda>O vínculo com protocolo IATF e o D0 retroativo aparecem quando a cobertura é IATF.</Ajuda>}
      </Passo>

      <BarraAcao
        resumo={resumo}
        detalhe={detalhe}
        retorno={(erro || sucesso || podeForcar) ? (
          <div className="rp-retorno-linha">
            {sucesso && <span className="rp-ok" role="status">✓ {sucesso}</span>}
            {sucesso && !erro && <span className="rp-mudo">Matrizes já inseminadas saíram da lista de prontas do protocolo.</span>}
            {erro && <span className="rp-err" role="alert">{erro}</span>}
            {podeForcar && (
              <>
                <span className="gv-espaco" style={{ flex: 1 }} />
                <button type="button" className="btn-secondary" onClick={() => salvar(true)} disabled={salvando}
                  title="Registra a inseminação assumindo a situação descrita ao lado">Confirmar e lançar mesmo assim</button>
              </>
            )}
          </div>
        ) : undefined}
        secundaria={<button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!sel.size}>Limpar</button>}
        acao={<BotaoOuro desabilitado={salvando || !nSel || !dataServico} onClick={() => salvar()}>
          {salvando ? "Salvando…" : `Lançar ${nSel || ""} ${nSel === 1 ? "inseminação" : "inseminações"}`.replace("  ", " ")}
        </BotaoOuro>}
      />
    </div>
  );
}
