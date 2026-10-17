"use client";
// Lançamento de PROTOCOLO IATF — o que fazer → matrizes (tabela com caixas, por lote) → protocolo e cronograma. Só agenda o
// protocolo hormonal; a inseminação em si (D11, ou o dia do molde) é lançada à parte, na tela Inseminação. Duas abas:
// "Lançar protocolo" e "Em andamento" (protocolos vigentes, com a correção de inclusão por engano). Mesma língua do Diagnóstico
// de gestação (kit gerencial). Montada na gaveta de Lançamentos e na Central de Protocolos (/protocolos).
//
// Quem decide é o servidor: a aptidão de cada fêmea (na data do D0) vem de GET /reproducao/aptidao-servico; matriz que já está
// em protocolo IATF vigente NÃO entra em outro (caixa desabilitada com o motivo; o servidor também recusa, 409).
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, X } from "lucide-react";
import {
  ErroApi, adicionarAnimaisIatf, criarProtocoloIatf, fetchLancamentosIatf, fetchProtocolosIatfAtivos, fetchProtocolosIatfCadastrados, removerAnimalIatf,
} from "@/lib/api";
import type { HormonioIatf, ProtocoloIatfMolde } from "@/lib/api";
import { invalidarEstadosReprodutivos } from "@/lib/estadoReprodutivo";
import { AnimalRow } from "@/components/AnimalModal";
import { EditorHormoniosIatf } from "@/components/EditorHormoniosIatf";
import { IDADE_MIN_SERVICO_PADRAO } from "@/components/lancamentos/_shared";
import { useAptidaoServico, useLinhasFemeas } from "@/components/lancamentos/useFemeasServico";
import { Aviso, Ajuda, BarraAcao, BotaoOuro, Faixa, Passo, Pilulas, Selo } from "@/components/gerencial/kit";
import { Abas, BuscaMatrizes, EstiloRepro, PilulasX } from "@/components/gerencial/telas/ReprodutivoComum";
import { TabelaFemeas } from "@/components/gerencial/telas/TabelaFemeas";
import { alterna, alternaAptas, ehApta, filtraLinhas, marcavel, ordenaNumero, resumoSelecao } from "@/lib/aptidaoServico";
import {
  DIA_INSEMINACAO_PADRAO, diaInseminacao, diaSemana, diasDoMolde, fmtData, hojeIso, nomeProtocoloAuto, nosDoCronograma, type NoTempo,
} from "@/lib/iatfCronograma";

type ProtocoloIatfAtivo = {
  lancamento_id: number; nome_protocolo: string; data_d0: string; concluido?: boolean; proxima_visita?: string;
  animais: {
    numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null; d0_confirmado?: boolean;
    tem_etapa_confirmada?: boolean; pronta_para_inseminar?: boolean;
  }[];
};
type Lancamento = { lancamento_id: number; nome_protocolo: string; data_d0: string; qtd_animais: number };
type Aba = "lancar" | "andamento";
type Modo = "novo" | "existente";

const CSS = `
.fp-grade-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 26rem), 1fr)); gap: 1.25rem; align-items: start; }
`;

/* ───────────────────────────── subcomponentes (fora do pai) ───────────────────────────── */
function LinhaDoTempo({ nos }: { nos: NoTempo[] }) {
  return (
    <ol className="rp-linha-tempo" style={{ listStyle: "none", margin: 0, padding: 0 }} aria-label="Cronograma do protocolo">
      {nos.map((n) => (
        <li key={n.dia} className={`rp-etapa${n.fim ? " rp-etapa-fim" : ""}`}>
          <span className="rp-no" data-fim={n.fim ? "true" : undefined}>D{n.dia}</span>
          <span className="rp-etapa-data">{n.data ? fmtData(n.data, true) : "—"}</span>
          <span className="rp-etapa-dow">{n.data ? diaSemana(n.data) : ""}</span>
          <span className="rp-etapa-txt">
            {n.subtitulo && <i>{n.subtitulo}</i>}
            {n.linhas.length ? n.linhas.map((l) => <span key={l} style={{ display: "block" }}>{l}</span>) : <i>sem medicamento informado</i>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function TabelaAndamento({ dados, busca, removendo, onRemover }: {
  dados: ProtocoloIatfAtivo[]; busca: string; removendo: string | null; onRemover: (lancamentoId: number, numero: string) => void;
}) {
  const q = busca.trim().toLowerCase();
  return (
    <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "36rem" }}>
      <table className="gv-tabela">
        <thead><tr>
          <th scope="col">Nº</th><th scope="col">Etapa atual</th><th scope="col">Data da etapa</th><th scope="col">D0 na Agenda</th><th scope="col" className="gv-dir">Corrigir</th>
        </tr></thead>
        <tbody>
          {dados.length === 0 && <tr className="rp-tab-vazia"><td colSpan={5}>Nenhum protocolo IATF em andamento.</td></tr>}
          {dados.map((p) => {
            const animais = [...p.animais].filter((a) => !q || a.numero_matriz.toLowerCase().includes(q)).sort((a, b) => ordenaNumero(a.numero_matriz, b.numero_matriz));
            if (q && !animais.length) return null;
            return (
              <React.Fragment key={p.lancamento_id}>
                <tr className="gv-grupo">
                  <th scope="rowgroup" colSpan={5}>
                    {p.nome_protocolo} · D0 {fmtData(p.data_d0)} · {p.animais.length} {p.animais.length === 1 ? "animal" : "animais"}
                    {p.concluido && ` · hormônio concluído${p.proxima_visita ? ` · próxima visita ${fmtData(p.proxima_visita)}` : ""}`}
                  </th>
                </tr>
                {animais.map((a) => {
                  // Só dá para remover enquanto nenhuma etapa dela foi confirmada na Agenda (o servidor recusa o resto).
                  const travado = a.tem_etapa_confirmada ?? !!a.d0_confirmado;
                  const chave = `${p.lancamento_id}-${a.numero_matriz}`;
                  return (
                    <tr key={a.numero_matriz}>
                      <td className="gv-forte">{a.numero_matriz}</td>
                      <td>
                        {a.etapa_atual}{" "}
                        {a.pronta_para_inseminar && <Selo tom="ok" titulo="Protocolo vigente sem inseminação lançada">Pronta para inseminar</Selo>}
                      </td>
                      <td className="gv-num">{a.data_etapa_atual ? fmtData(a.data_etapa_atual) : "—"}</td>
                      <td>
                        {a.d0_confirmado
                          ? <Selo tom="ok" titulo="D0 confirmado na Agenda"><Check size={11} aria-hidden="true" /> Confirmado</Selo>
                          : <Selo tom="atencao" titulo="D0 ainda não confirmado na Agenda — pode ter entrado no protocolo sem ter sido implantada"><AlertTriangle size={11} aria-hidden="true" /> Não confirmado</Selo>}
                      </td>
                      <td className="gv-dir">
                        <button type="button" className="btn-ghost" disabled={travado || removendo === chave}
                          onClick={() => onRemover(p.lancamento_id, a.numero_matriz)}
                          title={travado ? "Não dá para remover: já há etapa confirmada na Agenda (desmarque “Realizado” lá antes)" : "Remover este animal do protocolo (corrige inclusão por engano)"}
                          style={{ display: "inline-flex", gap: "0.25rem", alignItems: "center", padding: "0.2rem 0.55rem", fontSize: "0.74rem", cursor: travado ? "not-allowed" : "pointer" }}>
                          <X size={12} aria-hidden="true" /> Remover
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ───────────────────────────── a tela ───────────────────────────── */
export function FormProtocoloIatf({ animais, motivosInaptidao, idadeMinServico = IDADE_MIN_SERVICO_PADRAO, onSalvo }: {
  animais: AnimalRow[];
  // numero -> motivo de inaptidão DURA antecipado pela página; vale só enquanto a resposta do servidor não chega.
  motivosInaptidao?: Map<string, string>;
  idadeMinServico?: number;
  onSalvo?: () => void;
}) {
  const [aba, setAba] = useState<Aba>("lancar");
  const [modo, setModo] = useState<Modo>("novo");
  const [origem, setOrigem] = useState<"animais" | "lotes">("animais");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busca, setBusca] = useState("");
  const [d0, setD0] = useState(() => hojeIso());
  const [hormonios, setHormonios] = useState<HormonioIatf[]>([]);
  // Molde cadastrado (Central de Protocolos > Cadastro), opcional: escolhido, MANDA nos dias e nos hormônios (dias livres:
  // D0/D8/D10/D12…). Sem molde: cronograma clássico D0/D7/D9/D11 e hormônios digitados na hora.
  const [moldes, setMoldes] = useState<ProtocoloIatfMolde[]>([]);
  const [moldeId, setMoldeId] = useState("");
  const [existentes, setExistentes] = useState<Lancamento[]>([]);
  const [existenteId, setExistenteId] = useState("");
  const [ativos, setAtivos] = useState<ProtocoloIatfAtivo[]>([]);
  const [buscaAnd, setBuscaAnd] = useState("");
  const [removendo, setRemovendo] = useState<string | null>(null);
  const [erroRemocao, setErroRemocao] = useState<string | null>(null);

  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [jaLancado, setJaLancado] = useState(false);
  const [podeForcar, setPodeForcar] = useState(false);

  const carregarAtivos = useCallback(() => fetchProtocolosIatfAtivos().then(setAtivos).catch(() => setAtivos([])), []);
  const carregarExistentes = useCallback(() => fetchLancamentosIatf().then(setExistentes).catch(() => setExistentes([])), []);
  useEffect(() => {
    carregarAtivos();
    carregarExistentes();
    fetchProtocolosIatfCadastrados().then((ms) => setMoldes(ms.filter((m) => m.ativo))).catch(() => setMoldes([]));
  }, [carregarAtivos, carregarExistentes]);

  const molde = moldes.find((m) => String(m.id) === moldeId) ?? null;
  const diasMolde = molde ? diasDoMolde(molde.etapas) : [];
  const diaIA = molde ? diaInseminacao(diasMolde) : DIA_INSEMINACAO_PADRAO;
  const nomeBase = molde?.nome || "Protocolo IATF";
  const nomeProtocolo = nomeProtocoloAuto(d0, nomeBase, diaIA);
  const existente = existentes.find((l) => String(l.lancamento_id) === existenteId) ?? null;
  // Hormônios efetivamente enviados: do molde (etapa por etapa, direto) quando há molde; digitados na hora quando não.
  const hormoniosEfetivos: HormonioIatf[] = molde
    ? molde.etapas.map((e) => ({ dia: e.dia, produto: e.produto, dose: e.dose, unidade: e.unidade, via: e.via }))
    : hormonios;

  // ── fêmeas, com o veredito do servidor na data do D0 ───────────────────────────────────────────────────────────
  const dataAptidao = modo === "existente" ? (existente?.data_d0?.slice(0, 10) ?? "") : d0;
  const { api, falhou: aptidaoFalhou, recarregar: recarregarAptidao } = useAptidaoServico(dataAptidao);
  const linhas = useLinhasFemeas({
    animais, api, motivosInaptidao, bloquearEmProtocolo: true, protocoloDestinoId: modo === "existente" && existente ? existente.lancamento_id : null,
  });
  const lotes = useMemo(() => {
    const m = new Map<string, number>();
    linhas.forEach((l) => m.set(l.lote, (m.get(l.lote) ?? 0) + 1));
    return [...m.entries()].sort(([a], [b]) => ordenaNumero(a, b));
  }, [linhas]);
  const base = useMemo(() => (origem === "animais" ? linhas : linhas.filter((l) => lotesSel.includes(l.lote))), [origem, linhas, lotesSel]);
  const visiveis = useMemo(() => filtraLinhas(base, busca), [base, busca]);

  const bloqueadasNumeros = useMemo(() => new Set(linhas.filter((l) => !marcavel(l)).map((l) => l.numero)), [linhas]);
  const selEfetiva = useMemo(() => new Set([...sel].filter((n) => !bloqueadasNumeros.has(n))), [sel, bloqueadasNumeros]);
  const ignoradas = useMemo(() => linhas.filter((l) => sel.has(l.numero) && !marcavel(l)), [linhas, sel]);
  const nSel = selEfetiva.size;
  const { pedemConfirmacao } = useMemo(() => resumoSelecao(linhas, selEfetiva), [linhas, selEfetiva]);

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

  const nos = nosDoCronograma(d0, molde ? molde.etapas : null, hormonios);

  // ── salvar ────────────────────────────────────────────────────────────────────────────────────────────────────
  async function salvar(forcar = false) {
    setErro(null); setSucesso(null); setJaLancado(false); setPodeForcar(false);
    const alvo = [...sel].filter((n) => !bloqueadasNumeros.has(n)).sort(ordenaNumero);
    if (!alvo.length) { setErro("Selecione ao menos um animal."); return; }
    setSalvando(true);
    try {
      if (modo === "existente") {
        if (!existenteId) { setErro("Selecione o protocolo existente."); return; }
        const r = await adicionarAnimaisIatf(Number(existenteId), alvo, forcar || undefined);
        setSucesso(`${r.adicionados} ${r.adicionados === 1 ? "animal adicionado" : "animais adicionados"} ao protocolo “${r.nome_protocolo}”.`);
      } else {
        if (!d0) { setErro("Informe a data do D0."); return; }
        const r = await criarProtocoloIatf({ animais: alvo, data_d0: d0, protocolo_id: moldeId ? Number(moldeId) : null, hormonios: hormoniosEfetivos, forcar: forcar || undefined });
        // `criado: false` = o servidor achou um lançamento ativo idêntico (mesmo protocolo/D0/animais) e reaproveitou em vez de
        // duplicar — duplo clique ou retry da fila offline. Sem este ramo a tela diria "0 eventos na Agenda", que parece defeito.
        if (r.criado === false) {
          setJaLancado(true);
          setSucesso(r.aviso || "Este protocolo já estava lançado para estes animais nesta data — nada foi duplicado.");
        } else {
          setSucesso(`Protocolo “${nomeProtocolo}” agendado para ${r.animais} ${r.animais === 1 ? "animal" : "animais"} — ${r.eventos_criados} eventos na Agenda (D0 a D${diaIA}).`);
        }
      }
      setSel(new Set()); setLotesSel([]);
      invalidarEstadosReprodutivos();
      carregarAtivos(); carregarExistentes(); recarregarAptidao();
      onSalvo?.();
    } catch (e) {
      setErro(e instanceof Error && e.message ? e.message : "Erro ao lançar protocolo IATF");
      // 409 confirmável (peso da novilha, matriz que consta gestante): oferece "confirmar". "Já em protocolo", idade, a descartar: não.
      if (e instanceof ErroApi && e.status === 409 && e.confirmavel) setPodeForcar(true);
      else if (e instanceof ErroApi && e.status === 409) recarregarAptidao();
    } finally {
      setSalvando(false);
    }
  }

  async function remover(lancamentoId: number, numero: string) {
    if (!window.confirm(`Remover ${numero} deste protocolo? Só é possível se nenhuma etapa dela já foi confirmada.`)) return;
    setErroRemocao(null);
    const chave = `${lancamentoId}-${numero}`;
    setRemovendo(chave);
    try {
      await removerAnimalIatf(lancamentoId, numero);
      await carregarAtivos();
      carregarExistentes(); recarregarAptidao();
    } catch (e) {
      setErroRemocao(e instanceof Error && e.message ? e.message : "Não foi possível remover este animal.");
    } finally {
      setRemovendo(null);
    }
  }

  // ── resumo da barra ───────────────────────────────────────────────────────────────────────────────────────────
  const plural = (n: number) => (n === 1 ? "animal" : "animais");
  const resumo = modo === "novo"
    ? `${nSel} ${plural(nSel)} · ${molde ? molde.nome : "Protocolo IATF (sem molde)"}`
    : `${nSel} ${plural(nSel)} entram em “${existente ? existente.nome_protocolo : "—"}”`;
  const conf = pedemConfirmacao ? ` · ${pedemConfirmacao} pede(m) confirmação (o servidor vai perguntar ao salvar)` : "";
  const detalhe = !nSel ? "Marque ao menos um animal na tabela do passo 2"
    : modo === "novo"
      ? (!d0 ? "Falta a data do D0" : `D0 ${fmtData(d0)} · inseminação D${diaIA} em ${fmtData(nos[nos.length - 1]?.data ?? "")}${conf}`)
      : (!existente ? "Escolha o protocolo no passo 3" : `Mesmo D0 do protocolo (${fmtData(existente.data_d0)})${conf}`);
  const podeSalvar = nSel > 0 && (modo === "novo" ? !!d0 : !!existente) && !salvando;

  const faixa = [
    { rotulo: "Protocolos em andamento", valor: ativos.length },
    { rotulo: "Animais em protocolo", valor: ativos.reduce((s, p) => s + p.animais.length, 0) },
    { rotulo: "Prontas para inseminar", valor: ativos.reduce((s, p) => s + p.animais.filter((a) => a.pronta_para_inseminar).length, 0), tom: "ok" as const },
    { rotulo: "D0 sem confirmar", valor: ativos.reduce((s, p) => s + p.animais.filter((a) => !a.d0_confirmado).length, 0), tom: "atencao" as const },
    { rotulo: "Moldes ativos", valor: moldes.length },
  ];
  const idadeMin = api?.idade_min_meses ?? idadeMinServico;
  const nAnimaisAtivos = ativos.reduce((s, p) => s + p.animais.length, 0);

  return (
    <div style={{ display: "flex", flexDirection: "column" }}>
      <EstiloRepro />
      <style>{CSS}</style>
      <Faixa itens={faixa} />
      <Abas<Aba> rotulo="Protocolo IATF" ativa={aba} onChange={setAba} abas={[
        { id: "lancar", nome: "Lançar protocolo" },
        { id: "andamento", nome: "Em andamento", n: ativos.length },
      ]} />

      {/* Os dois painéis ficam montados (só um à vista): o que foi digitado em "Lançar" — hormônios inclusive — não se perde
          ao espiar "Em andamento". */}
      <div role="tabpanel" aria-labelledby="aba-andamento" hidden={aba !== "andamento"} style={{ display: aba === "andamento" ? "flex" : "none", flexDirection: "column", gap: "0.6rem" }}>
        <div className="rp-ferr">
          <BuscaMatrizes valor={buscaAnd} onChange={setBuscaAnd} rotulo="Buscar animal" />
          <span className="rp-contagem">{ativos.length} {ativos.length === 1 ? "protocolo" : "protocolos"} · {nAnimaisAtivos} {plural(nAnimaisAtivos)}</span>
        </div>
        {erroRemocao && <Aviso tom="erro">{erroRemocao}</Aviso>}
        <TabelaAndamento dados={ativos} busca={buscaAnd} removendo={removendo} onRemover={remover} />
        <Ajuda>
          “Pronta para inseminar” = protocolo vigente sem inseminação lançada; ela vai para a tela <strong>Inseminação</strong> (origem “Protocolo IATF vigente”).
          Remover um animal corrige inclusão por engano e <strong>só é possível enquanto nenhuma etapa dele foi confirmada na Agenda</strong>.
        </Ajuda>
      </div>

      <div role="tabpanel" aria-labelledby="aba-lancar" hidden={aba !== "lancar"} style={{ display: aba === "lancar" ? "block" : "none" }}>
        {aptidaoFalhou && !api && (
          <div style={{ marginBottom: "0.9rem" }}>
            <Aviso>
              <AlertTriangle size={15} style={{ marginTop: "0.1rem", flexShrink: 0 }} aria-hidden="true" />
              <span>Não consegui conferir a aptidão de cada fêmea agora. A tabela mostra só o que o cadastro já indica; peso e “consta gestante” serão conferidos ao salvar.</span>
            </Aviso>
          </div>
        )}
        <Passo n={1} id="iatf-p1" titulo="O que fazer">
          <Pilulas<Modo> rotulo="Modo" valor={modo} onChange={(m) => { setModo(m); setErro(null); setPodeForcar(false); }} opcoes={[
            { id: "novo", nome: "Novo protocolo", titulo: "Criar um novo protocolo IATF (define D0 e hormônios)" },
            { id: "existente", nome: "Adicionar a protocolo existente", n: existentes.length, titulo: "Incluir animais num protocolo já lançado (mesmo D0 e nome)" },
          ]} />
          <Ajuda>
            {modo === "novo" ? "Cria um lançamento com D0, hormônios e os eventos de cada etapa na Agenda." : "Os animais entram com o mesmo D0, nome e hormônios do protocolo escolhido."}
          </Ajuda>
        </Passo>

        <Passo n={2} id="iatf-p2" titulo="Matrizes" direita={
          <span className="rp-contagem" aria-live="polite">
            {nSel} de {visiveis.length} {nSel === 1 ? "marcada" : "marcadas"}{pedemConfirmacao > 0 && ` · ${pedemConfirmacao} pede(m) confirmação`}
          </span>
        }>
          <div className="rp-ferr">
            <PilulasX<"animais" | "lotes"> rotulo="Escolher por" valor={origem} onChange={(o) => { setOrigem(o); setLotesSel([]); }}
              opcoes={[{ id: "animais", nome: "Animais" }, { id: "lotes", nome: "Lotes", n: lotes.length }]} />
            <BuscaMatrizes valor={busca} onChange={setBusca} />
            <button type="button" className="btn-ghost" onClick={() => setSel((p) => alternaAptas(p, visiveis))}>Marcar / desmarcar as aptas</button>
            <button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!sel.size}>Limpar</button>
          </div>
          {origem === "lotes" && (
            <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternaLote} opcoes={lotes.map(([l, n]) => ({ id: l, nome: l, n }))} />
          )}
          {ignoradas.length > 0 && (
            <Aviso>
              <AlertTriangle size={15} style={{ marginTop: "0.1rem", flexShrink: 0 }} aria-hidden="true" />
              <span>
                Marcadas, mas bloqueadas agora — <strong>não serão enviadas</strong>: {ignoradas.map((l) => `${l.numero} (${l.aptidao.motivo})`).join("; ")}.
              </span>
            </Aviso>
          )}
          <TabelaFemeas
            linhas={visiveis} sel={selEfetiva} mostrarProtocolo altura="36rem" carregando={!animais.length}
            vazio={origem === "lotes" ? "Marque um ou mais lotes acima." : busca ? "Nenhuma fêmea bate com a busca." : "Nenhuma fêmea na lista."}
            onToggle={(n) => setSel((p) => alterna(p, n))}
            onToggleAptas={() => setSel((p) => alternaAptas(p, visiveis))}
            onToggleLote={(_l, itens) => setSel((p) => alternaAptas(p, itens))}
          />
          <Ajuda>
            A lista mostra <strong>todas as fêmeas</strong>. <strong>Bloqueada</strong> (caixa desabilitada, com o motivo): idade mínima de {idadeMin} meses, marcada a descartar, baixada ou
            <strong> já em protocolo IATF vigente</strong> — o servidor recusa. <strong>Confirmar</strong>: peso da novilha lançado abaixo do mínimo e matriz que consta gestante — marcável; ao salvar
            o servidor pede a sua confirmação. Isto só agenda o protocolo hormonal: a inseminação em si (D{modo === "novo" ? diaIA : DIA_INSEMINACAO_PADRAO}) é lançada à parte, na tela <strong>Inseminação</strong>.
          </Ajuda>
        </Passo>

        <Passo n={3} id="iatf-p3" titulo={modo === "novo" ? "Protocolo e cronograma" : "Protocolo existente"}>
          {modo === "novo" ? (
            <>
              <div className="fp-grade-2">
                <div className="rp-col">
                  <div className="gv-campo">
                    <label htmlFor="iatf-molde">Protocolo cadastrado (opcional)</label>
                    <select id="iatf-molde" className="rp-select" value={moldeId} onChange={(e) => setMoldeId(e.target.value)}>
                      <option value="">Sem molde — informar hormônios abaixo</option>
                      {moldes.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
                    </select>
                  </div>
                  <div className="gv-campo">
                    <label htmlFor="iatf-d0">Data do D0</label>
                    <input id="iatf-d0" type="date" className="rp-input" value={d0} onChange={(e) => setD0(e.target.value)} />
                  </div>
                  <div className="gv-campo">
                    <label htmlFor="iatf-nome">Nome do lançamento (automático)</label>
                    <input id="iatf-nome" className="rp-input" readOnly value={nomeProtocolo || "Informe a data do D0…"} style={{ fontVariantNumeric: "tabular-nums" }} />
                  </div>
                  <p className="gv-ajuda">
                    {molde
                      ? <>O molde <strong>manda nos dias e nos hormônios</strong>; para mudar dose, produto ou dia, edite em <strong>Central de Protocolos › Cadastro</strong>. Ao confirmar cada dia na Agenda você ainda escolhe o frasco em estoque do princípio ativo.</>
                      : <>Sem molde: cronograma clássico D0/D7/D9/D11 e hormônios digitados abaixo. A inseminação é sempre 2 dias depois da última etapa de hormônio.</>}
                  </p>
                </div>
                <div className="rp-bloco">
                  <div className="rp-bloco-t">Cronograma — vai para a Agenda de cada animal</div>
                  <LinhaDoTempo nos={nos} />
                  <p className="gv-ajuda" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
                    Ao salvar, cria os eventos D0 a D{diaIA} na Agenda para cada animal marcado ({nSel} × {nos.length} = <strong>{nSel * nos.length}</strong> eventos).
                  </p>
                </div>
              </div>
              {!molde && (
                <div className="rp-bloco">
                  <div className="rp-bloco-t">Hormônios por dia (opcional) — dão baixa no estoque quando você confirma o dia na Agenda</div>
                  <EditorHormoniosIatf onChange={setHormonios} />
                </div>
              )}
            </>
          ) : (
            <div className="fp-grade-2">
              <div className="gv-campo">
                <label htmlFor="iatf-exist">Protocolo existente</label>
                <select id="iatf-exist" className="rp-select" value={existenteId} onChange={(e) => setExistenteId(e.target.value)}>
                  <option value="">Selecione o protocolo…</option>
                  {existentes.map((l) => <option key={l.lancamento_id} value={l.lancamento_id}>{l.nome_protocolo} — {l.qtd_animais} animal(is)</option>)}
                </select>
              </div>
              {existente && (
                <div className="rp-bloco">
                  <div className="rp-bloco-t">O que muda no protocolo</div>
                  <div style={{ fontSize: "0.85rem" }}>
                    D0 <strong>{fmtData(existente.data_d0)}</strong> · hoje {existente.qtd_animais} {plural(existente.qtd_animais)} → <strong>{existente.qtd_animais + nSel}</strong> com os {nSel} marcados.
                  </div>
                  <p className="gv-ajuda">Os eventos das etapas já vencidas também entram na Agenda dos novos animais — confira antes de lançar.</p>
                </div>
              )}
            </div>
          )}
        </Passo>
      </div>

      {aba === "lancar" && (
        <BarraAcao
          resumo={resumo}
          detalhe={detalhe}
          retorno={(erro || sucesso || podeForcar) ? (
            <div className="rp-retorno-linha">
              {sucesso && (jaLancado ? <span className="rp-mudo" role="status">{sucesso}</span> : <span className="rp-ok" role="status">✓ {sucesso}</span>)}
              {erro && <span className="rp-err" role="alert">{erro}</span>}
              <span style={{ flex: 1 }} />
              {sucesso && <button type="button" className="btn-ghost" onClick={() => setAba("andamento")}>Ver em andamento</button>}
              {podeForcar && (
                <button type="button" className="btn-secondary" onClick={() => salvar(true)} disabled={salvando}
                  title="Lança o protocolo assumindo a situação descrita ao lado">Confirmar e lançar mesmo assim</button>
              )}
            </div>
          ) : undefined}
          secundaria={<button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!sel.size}>Limpar</button>}
          acao={<BotaoOuro desabilitado={!podeSalvar} onClick={() => salvar()}>
            {salvando ? "Salvando…" : modo === "novo" ? `Lançar protocolo${nSel ? ` (${nSel})` : ""}` : `Adicionar${nSel ? ` ${nSel}` : ""} ao protocolo`}
          </BotaoOuro>}
        />
      )}
    </div>
  );
}
