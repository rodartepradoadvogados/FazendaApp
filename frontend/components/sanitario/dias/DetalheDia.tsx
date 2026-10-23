"use client";
// O dia aberto ("Vacina · B19 · 25/12"): executar no site, um animal por vez
// ou o grupo todo (o grupo não fecha — dá para incluir animais na hora),
// trocar produto/dose, carência a decidir (pop-up), consentimento de quem está
// fora da regra, resultado de exame, estorno (admin), fechar (faltantes voltam
// para a caixa ou são dispensados), cancelar, ficha de campo e o registro (log).
import { useMemo, useState } from "react";
import { ArrowLeft, Ban, Check, Pencil, Plus, Printer, Users, X } from "lucide-react";
import { Modal } from "@/components/Modal";
import { ErroCarregamento, TelaSkeleton } from "@/components/ui";
import { useToast } from "@/components/Toast";
import {
  adicionarAnimaisDia, aplicarGrupo, cancelarDia, codigoDoErro, decidirCarenciaDia, detalheDoErro, editarDia, estornarRegistro,
  fecharDia, lancarResultado, listarCaixas, listarVeterinarios, logDoDia, mensagemDoErro, obterDia, pacoteOffline, registrarNoDia,
  registrosDoDia, removerAnimalDia,
} from "@/lib/apiSanitario";
import {
  DOSE_UNIDADES, RESULTADOS, ROTULO_ESTADO_DIA, ROTULO_MODO_LEITE, ROTULO_RESULTADO, ROTULO_UNIDADE, diaSemana, fmtData, fmtDataHora,
  intOuNulo, numOuNulo, textoProduto,
  type CaixaResumo, type CarenciaDecisaoIn, type Dia, type DiaCaixa, type DiaItem, type ItemForaRegra, type ItemRegistro, type LogItem,
  type ModoLeite, type ProdutoIn, type Registro, type Resultado, type ResultadoRegistro, type Veterinarios,
} from "@/lib/sanitarioTipos";
import {
  BarraDesfazer, CampoPessoa, Faixa, LegendaOrigem, OrigemIcone, Seg, carregarEstoqueSan, opcoesEstoqueSan, useCarregar, useEuSanitario,
  type ItemEstoqueSan, type PessoaEscolhida,
} from "../comum";
import { SeletorAnimais, type Elegibilidade } from "../SeletorAnimais";
import { ModalConsentimento, type ItemConsentimento } from "../ModalConsentimento";
import { ModalCarencia } from "../ModalCarencia";
import { ModalFicha } from "../FichaCampo";
import { ModalMarcarDia } from "./ModalMarcarDia";

type Dados = { dia: Dia; registros: Registro[]; log: LogItem[]; caixas: CaixaResumo[]; estoque: ItemEstoqueSan[]; vets: Veterinarios };

async function carregarTudo(id: number): Promise<Dados> {
  const [dia, registros, log, caixas, estoque, vets] = await Promise.all([
    obterDia(id), registrosDoDia(id), logDoDia(id).catch(() => [] as LogItem[]), listarCaixas("todas").catch(() => [] as CaixaResumo[]),
    carregarEstoqueSan().catch(() => [] as ItemEstoqueSan[]), listarVeterinarios().catch(() => ({ pessoas: [], aceita_texto_livre: true })),
  ]);
  return { dia, registros, log, caixas, estoque, vets };
}

// ── pop-ups pequenos ──
function ModalFechar({ dia, onFeito, onFechar }: { dia: Dia; onFeito: (d: Dia) => void; onFechar: () => void }) {
  const faltam = useMemo(() => {
    const m = new Map<number, string>();
    for (const i of dia.itens || []) if (i.estado === "pendente") m.set(i.animal_id, i.numero || String(i.animal_id));
    return [...m.values()];
  }, [dia]);
  const [destino, setDestino] = useState<"voltar" | "dispensar">("voltar");
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  async function fechar() {
    setSalvando(true); setErro(null);
    try { onFeito(await fecharDia(dia.id, destino, motivo.trim() || null)); }
    catch (e) { setErro(mensagemDoErro(e)); } finally { setSalvando(false); }
  }
  return (
    <Modal title={`Fechar ${dia.nome}`} onClose={onFechar} width="580px">
      <div className="san-modal-corpo">
        <p style={{ margin: 0, fontSize: "0.86rem" }}><b className="san-num">{faltam.length}</b> {faltam.length === 1 ? "animal ficou" : "animais ficaram"} sem registro{faltam.length ? `: ${faltam.slice(0, 30).join(", ")}${faltam.length > 30 ? "…" : ""}` : ""}.</p>
        {faltam.length > 0 && (<>
          <div className="san-opcs lista" role="radiogroup" aria-label="O que fazer com quem faltou">
            <label className="san-opc"><input type="radio" name="fdM" checked={destino === "voltar"} onChange={() => setDestino("voltar")} />
              <span><b>Voltam para a caixa</b><small>Aparecem de novo em Animais na janela.</small></span></label>
            <label className="san-opc"><input type="radio" name="fdM" checked={destino === "dispensar"} onChange={() => setDestino("dispensar")} />
              <span><b>Dispensar neste ciclo</b><small>Motivo opcional.</small></span></label>
          </div>
          {destino === "dispensar" && (
            <div className="san-campo"><label htmlFor="fdMot">Motivo da dispensa (opcional)</label>
              <input id="fdMot" className="san-input" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="ex.: decisão do veterinário" /></div>
          )}
        </>)}
        <Faixa>Registros guardados num celular sem sinal entram como <b>lançados após o fechamento</b> quando chegarem. Se ninguém fechar, o dia fecha sozinho às 23:59 do dia seguinte.</Faixa>
        {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={fechar}>{salvando ? "Fechando…" : "Fechar o dia"}</button>
      </div>
    </Modal>
  );
}

function ModalCancelar({ dia, onFeito, onFechar }: { dia: Dia; onFeito: (d: Dia) => void; onFechar: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  return (
    <Modal title={`Cancelar ${dia.nome}`} onClose={onFechar} width="520px">
      <div className="san-modal-corpo">
        <p className="san-modal-sub">Os animais voltam para a caixa. O que já foi registrado continua no histórico.</p>
        <div className="san-campo"><label htmlFor="cMot">Motivo (opcional)</label>
          <input id="cMot" className="san-input" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="ex.: chuva, veterinário não veio" /></div>
        {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onFechar}>Voltar</button>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={async () => {
          setSalvando(true); setErro(null);
          try { onFeito(await cancelarDia(dia.id, motivo.trim() || null)); } catch (e) { setErro(mensagemDoErro(e)); } finally { setSalvando(false); }
        }}>{salvando ? "Cancelando…" : "Cancelar o dia"}</button>
      </div>
    </Modal>
  );
}

function ModalTrocarProduto({ dia, caixa, estoque, onFeito, onFechar }: {
  dia: Dia; caixa: DiaCaixa; estoque: ItemEstoqueSan[]; onFeito: (d: Dia) => void; onFechar: () => void;
}) {
  const [p, setP] = useState<ProdutoIn>({ ...caixa.produto, modo: caixa.produto.modo === "vazio" ? "estoque" : caixa.produto.modo });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  async function salvar() {
    setSalvando(true); setErro(null);
    try { onFeito(await editarDia(dia.id, { versao_lock: dia.versao_lock, produtos: { [caixa.caixa_id]: p } })); }
    catch (e) {
      setErro(codigoDoErro(e) === "versao_desatualizada" ? "Alguém mudou este dia agora há pouco. Feche e abra de novo." : mensagemDoErro(e));
    } finally { setSalvando(false); }
  }
  return (
    <Modal title={`Trocar produto ou dose · ${caixa.nome_curto}`} onClose={onFechar} width="560px">
      <div className="san-modal-corpo">
        <div className="san-opcs lista" role="radiogroup" aria-label="Produto">
          {([["estoque", "Do estoque"], ["sem_estoque", "Incluir produto sem estoque"], ["nao_se_aplica", "Registrar sem produto"]] as const).map(([k, t]) => (
            <label key={k} className="san-opc"><input type="radio" name="tpM" checked={p.modo === k} onChange={() => setP({ ...p, modo: k })} /><span>{t}</span></label>
          ))}
        </div>
        {p.modo === "estoque" && (
          <div className="san-campo"><label htmlFor="tpE">Item</label>
            <select id="tpE" className="san-input" value={p.estoque_id ?? ""} onChange={(e) => setP({ ...p, estoque_id: intOuNulo(e.target.value) })}>
              <option value="">Escolha…</option>
              {opcoesEstoqueSan(estoque, p.estoque_id).map((e) => <option key={e.id} value={e.id}>{e.nome}{e.quantidade != null ? ` · saldo ${e.quantidade} ${e.unidade || ""}` : ""}</option>)}
            </select></div>
        )}
        {p.modo === "sem_estoque" && (
          <div className="san-campo"><label htmlFor="tpT">Nome do produto</label>
            <input id="tpT" className="san-input" value={p.texto || ""} onChange={(e) => setP({ ...p, texto: e.target.value })} placeholder="ex.: frasco trazido pelo veterinário" /></div>
        )}
        {p.modo !== "nao_se_aplica" && (
          <div className="san-linha">
            <div className="san-campo curto"><label htmlFor="tpD">Dose</label>
              <input id="tpD" className="san-input" type="number" step="0.1" min={0} value={p.dose_valor ?? ""} onChange={(e) => setP({ ...p, dose_valor: numOuNulo(e.target.value) })} /></div>
            <div className="san-campo medio"><label htmlFor="tpU">Unidade</label>
              <select id="tpU" className="san-input" value={p.dose_unidade || ""} onChange={(e) => setP({ ...p, dose_unidade: (e.target.value || null) as ProdutoIn["dose_unidade"] })}>
                <option value="">—</option>{DOSE_UNIDADES.map((u) => <option key={u} value={u}>{ROTULO_UNIDADE[u]}</option>)}
              </select></div>
            {p.dose_unidade === "mL_por_x_kg" && (
              <div className="san-campo curto"><label htmlFor="tpX">X (kg)</label>
                <input id="tpX" className="san-input" type="number" min={1} value={p.dose_x_kg ?? ""} onChange={(e) => setP({ ...p, dose_x_kg: numOuNulo(e.target.value) })} /></div>
            )}
          </div>
        )}
        <p className="san-nota" style={{ margin: 0 }}>Vale para os próximos registros deste dia. Os já gravados ficam como foram. Produto trocado sem carência cadastrada faz o sistema perguntar o que fazer com o leite.</p>
        {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={salvar}>{salvando ? "Gravando…" : "Usar este produto"}</button>
      </div>
    </Modal>
  );
}

function ModalResultado({ registro, numero, vets, vetPadrao, onFeito, onFechar }: {
  registro: Registro; numero: string; vets: Veterinarios; vetPadrao: number | null; onFeito: () => void; onFechar: () => void;
}) {
  const [res, setRes] = useState<Resultado>(registro.resultado || "negativo");
  const [valor, setValor] = useState(registro.resultado_valor != null ? String(registro.resultado_valor) : "");
  const [vet, setVet] = useState<string>(vetPadrao ? String(vetPadrao) : registro.veterinario_pessoa_id ? String(registro.veterinario_pessoa_id) : "");
  const [vetTxt, setVetTxt] = useState(registro.veterinario_texto || "");
  const [crmv, setCrmv] = useState(registro.crmv_texto || "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  return (
    <Modal title={`Resultado · ${numero} · ${registro.caixa || "exame"}`} onClose={onFechar} width="560px">
      <div className="san-modal-corpo">
        <Seg<Resultado> rotulo="Resultado" valor={res} onChange={setRes} opcoes={RESULTADOS.map((r) => ({ id: r, label: ROTULO_RESULTADO[r] }))} />
        <div className="san-linha">
          <div className="san-campo curto"><label htmlFor="rV">Valor (opcional)</label>
            <input id="rV" className="san-input" type="number" step="0.1" value={valor} onChange={(e) => setValor(e.target.value)} /></div>
          <div className="san-campo"><label htmlFor="rVet">Veterinário responsável</label>
            <select id="rVet" className="san-input" value={vet} onChange={(e) => setVet(e.target.value)}>
              <option value="">Escrever o nome</option>
              {vets.pessoas.map((p) => <option key={p.pessoa_id} value={p.pessoa_id}>{p.nome}{p.crmv ? ` · ${p.crmv}` : ""}</option>)}
            </select></div>
        </div>
        {!vet && (
          <div className="san-linha">
            <div className="san-campo"><label htmlFor="rVt">Nome do veterinário</label><input id="rVt" className="san-input" value={vetTxt} onChange={(e) => setVetTxt(e.target.value)} /></div>
            <div className="san-campo medio"><label htmlFor="rCr">CRMV (opcional)</label><input id="rCr" className="san-input" value={crmv} onChange={(e) => setCrmv(e.target.value)} /></div>
          </div>
        )}
        <p className="san-nota" style={{ margin: 0 }}>Reagente gera só um aviso para os administradores (sem pendência).</p>
        {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <button type="button" className="btn-primary-gold" disabled={salvando} onClick={async () => {
          setSalvando(true); setErro(null);
          try {
            await lancarResultado(registro.id, {
              resultado: res, resultado_valor: numOuNulo(valor), veterinario_pessoa_id: vet ? Number(vet) : null,
              veterinario_texto: vet ? null : vetTxt.trim() || null, crmv_texto: vet ? null : crmv.trim() || null,
            });
            onFeito();
          } catch (e) { setErro(mensagemDoErro(e)); } finally { setSalvando(false); }
        }}>{salvando ? "Gravando…" : "Gravar resultado"}</button>
      </div>
    </Modal>
  );
}

function ModalEstorno({ registro, numero, onFeito, onFechar }: { registro: Registro; numero: string; onFeito: () => void; onFechar: () => void }) {
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  return (
    <Modal title={`Estornar · ${numero} · ${registro.caixa || registro.outro_texto || ""}`} onClose={onFechar} width="520px">
      <div className="san-modal-corpo">
        <p className="san-modal-sub">Devolve o estoque, tira a carência e a próxima dose ainda não aplicada. O registro fica no histórico como estornado.</p>
        <div className="san-campo"><label htmlFor="eMot">Motivo</label>
          <input id="eMot" className="san-input" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="ex.: lançado no animal errado" /></div>
        {erro && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{erro}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <button type="button" className="btn-primary-gold" disabled={salvando || !motivo.trim()} onClick={async () => {
          setSalvando(true); setErro(null);
          try { await estornarRegistro(registro.id, motivo.trim()); onFeito(); } catch (e) { setErro(mensagemDoErro(e)); } finally { setSalvando(false); }
        }}>{salvando ? "Estornando…" : "Estornar"}</button>
      </div>
    </Modal>
  );
}

// ── tela ──
type Pend = { acao: () => Promise<ResultadoRegistro>; itens: ItemRegistro[] };

export function DetalheDia({ diaId, onVoltar }: { diaId: number; onVoltar: () => void }) {
  const toast = useToast();
  const { eu, admin } = useEuSanitario();
  const { dados, erro, carregando, recarregar } = useCarregar(() => carregarTudo(diaId), [diaId]);
  const [aplicador, setAplicador] = useState<PessoaEscolhida>({ pessoa_id: null, texto: "" });
  const [ocupado, setOcupado] = useState(false);
  const [desfazer, setDesfazer] = useState<{ ids: number[]; ate: string | null; texto: string } | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [carencia, setCarencia] = useState<{ pend: Pend; caixaId: number; item: ItemRegistro } | null>(null);
  const [erroCarencia, setErroCarencia] = useState<string | null>(null);
  const [consentReg, setConsentReg] = useState<ItemRegistro[] | null>(null);
  const [consentAdd, setConsentAdd] = useState<{ itens: ItemConsentimento[]; pedido: { animal_id: number; caixa_ids: number[] }[]; semAtestado: string } | null>(null);
  const [modal, setModal] = useState<null | "fechar" | "cancelar" | "editar" | "ficha" | "adicionar">(null);
  const [trocar, setTrocar] = useState<DiaCaixa | null>(null);
  const [resultado, setResultado] = useState<{ reg: Registro; numero: string } | null>(null);
  const [estorno, setEstorno] = useState<{ reg: Registro; numero: string } | null>(null);
  const [erroAcao, setErroAcao] = useState<string | null>(null);
  const [elegCx, setElegCx] = useState<Map<number, number[]>>(new Map());

  const dia = dados?.dia;
  const regPorId = useMemo(() => new Map((dados?.registros || []).map((r) => [r.id, r])), [dados]);
  const caixaResumo = useMemo(() => new Map((dados?.caixas || []).map((c) => [c.id, c])), [dados]);
  const estoqueId = useMemo(() => new Map((dados?.estoque || []).map((e) => [e.id, e])), [dados]);
  const linhas = useMemo(() => {
    const m = new Map<number, { animal_id: number; numero: string; origem: string; itens: Map<number, DiaItem>; curral: boolean }>();
    for (const it of dia?.itens || []) {
      if (it.estado === "removido") continue;
      const l = m.get(it.animal_id) || { animal_id: it.animal_id, numero: it.numero || String(it.animal_id), origem: it.origem, itens: new Map(), curral: false };
      l.itens.set(it.caixa_id, it);
      if (it.origem === "manual" && l.origem === "janela") l.origem = "manual";
      if (it.origem === "curral") { l.origem = "curral"; l.curral = true; }
      m.set(it.animal_id, l);
    }
    return [...m.values()].sort((a, b) => a.numero.localeCompare(b.numero, undefined, { numeric: true }));
  }, [dia]);

  if (erro) return <ErroCarregamento mensagem={erro} onRetry={recarregar} />;
  if (!dados || !dia) return <TelaSkeleton kpis={0} label="Abrindo o dia" />;
  const fechado = dia.estado === "fechado" || dia.estado === "cancelado";
  const pendentes = (dia.itens || []).filter((i) => i.estado === "pendente");
  const totalItens = (dia.itens || []).filter((i) => i.estado !== "removido").length;

  async function executar(acao: () => Promise<ResultadoRegistro>) {
    setOcupado(true); setErroAcao(null);
    try {
      const r = await acao();
      tratarResultado(r, acao);
    } catch (e) {
      setErroAcao(mensagemDoErro(e, "Não foi possível registrar."));
    } finally { setOcupado(false); }
  }
  function tratarResultado(r: ResultadoRegistro, acao: () => Promise<ResultadoRegistro>) {
    const textos = new Set<string>();
    for (const it of r.itens) for (const a of it.avisos) if (!["fora_da_regra", "carencia_decisao"].includes(a.codigo)) textos.add(a.texto);
    setAvisos([...textos]);
    if (r.registro_ids.length) {
      const an = new Set(r.itens.filter((i) => i.status === "gravado").map((i) => i.numero)).size;
      setDesfazer({ ids: r.registro_ids, ate: r.desfazer_ate, texto: `${r.gravados} ${r.gravados > 1 ? "registros gravados" : "registro gravado"} · ${an} ${an > 1 ? "animais" : "animal"}` });
    } else if (!r.pendentes) {
      toast(r.duplicados ? "Nada novo: já estava registrado." : "Nada novo para registrar.");
    }
    const pendCar = r.itens.filter((i) => i.status === "pendente" && i.requer.includes("carencia_decisao"));
    const pendCons = r.itens.filter((i) => i.status === "pendente" && i.requer.includes("consentimento") && !i.requer.includes("carencia_decisao"));
    if (pendCar.length && pendCar[0].caixa_id != null) setCarencia({ pend: { acao, itens: pendCar }, caixaId: pendCar[0].caixa_id, item: pendCar[0] });
    else if (pendCons.length) setConsentReg(pendCons);
    recarregar();
  }
  const aplicarAnimal = (animalId: number) => {
    const ids = pendentes.filter((i) => i.animal_id === animalId).map((i) => i.id);
    return executar(() => aplicarGrupo(dia.id, { itemIds: ids, aplicadorPessoaId: aplicador.pessoa_id, aplicadorTexto: aplicador.texto || null }));
  };
  const aplicarTodos = () => executar(() => aplicarGrupo(dia.id, { aplicadorPessoaId: aplicador.pessoa_id, aplicadorTexto: aplicador.texto || null }));

  async function decidirCarencia(d: { modo: ModoLeite; leite_dias: number | null; carne_dias: number | null }) {
    if (!carencia) return;
    setErroCarencia(null);
    try {
      await decidirCarenciaDia(dia!.id, carencia.caixaId, d.modo, d.leite_dias, d.carne_dias);
      const acao = carencia.pend.acao;
      setCarencia(null);
      await executar(acao);
    } catch (e) { setErroCarencia(mensagemDoErro(e)); }
  }
  function checarAdicionar(): (ids: number[]) => Promise<Map<number, Elegibilidade>> {
    return async (ids) => {
      const pac = await pacoteOffline(dia!.id);
      const porId = new Map(pac.animais.map((a) => [a.animal_id, a]));
      setElegCx(new Map(pac.animais.map((a) => [a.animal_id, Object.entries(a.caixas).filter(([, v]) => v.elegivel).map(([k]) => Number(k))])));
      const m = new Map<number, Elegibilidade>();
      for (const id of ids) {
        const a = porId.get(id);
        if (!a) { m.set(id, { ok: false, texto: "fora do rebanho ativo" }); continue; }
        const vals = Object.values(a.caixas);
        const ok = vals.some((v) => v.elegivel);
        m.set(id, { ok, texto: ok ? null : vals.find((v) => v.motivo)?.motivo || "não cumpre a regra" });
      }
      return m;
    };
  }
  async function adicionar(pedido: { animal_id: number; caixa_ids: number[] }[], cons: { animal_id: number; caixa_id?: number | null; aceito: boolean; motivo_exibido?: string | null; quer_atestado?: boolean | null; atestado_destinatario?: string | null }[] = []) {
    setOcupado(true); setErroAcao(null);
    try {
      const r = await adicionarAnimaisDia(dia!.id, pedido, cons);
      const n = new Set(pedido.map((p) => p.animal_id)).size;
      toast(`${n} ${n > 1 ? "animais incluídos" : "animal incluído"} no dia.`);
      setAvisos((r.avisos || []).map((a) => a.texto));
      recarregar();
    } catch (e) {
      if (codigoDoErro(e) === "consentimento_necessario") {
        const det = detalheDoErro<{ itens: ItemForaRegra[]; pergunta_atestado_caixas: number[] }>(e);
        setConsentAdd({
          pedido,
          itens: (det?.itens || []).map((i) => ({ animal_id: i.animal_id, numero: i.numero, caixa_id: i.caixa_id, caixa: i.caixa, motivo: i.motivo })),
          semAtestado: (det?.pergunta_atestado_caixas || []).map((c) => caixaResumo.get(c)?.nome_curto || `#${c}`).join(", "),
        });
      } else setErroAcao(mensagemDoErro(e, "Não foi possível adicionar os animais."));
    } finally { setOcupado(false); }
  }

  const vetNome = dia.veterinario?.pessoa_id ? dados.vets.pessoas.find((p) => p.pessoa_id === dia.veterinario.pessoa_id)?.nome || dia.veterinario.texto
    : dia.veterinario?.texto;
  const crmv = dia.veterinario?.crmv || (dia.veterinario?.pessoa_id ? dados.vets.pessoas.find((p) => p.pessoa_id === dia.veterinario.pessoa_id)?.crmv : null);
  const horaDoRegistro = (it: DiaItem) => (it.registro_id ? regPorId.get(it.registro_id)?.hora : null);

  return (
    <div className="san-pagina">
      <div className="san-cab">
        <div>
          <h2>{dia.nome}</h2>
          <p>{diaSemana(dia.data)} {fmtData(dia.data)}{dia.hora ? ` às ${dia.hora}` : ""} · {vetNome || "sem veterinário"}{crmv ? ` · ${crmv}` : " · CRMV não informado (pedido, não exigido)"} · {ROTULO_ESTADO_DIA[dia.estado] || dia.estado}</p>
        </div>
        <div className="san-acoes">
          <button type="button" className="btn-ghost" onClick={onVoltar}><ArrowLeft size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Voltar</button>
          {dia.estado !== "cancelado" && <button type="button" className="btn-ghost" onClick={() => setModal("adicionar")} disabled={ocupado}><Plus size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Adicionar animais</button>}
          <button type="button" className="btn-ghost" onClick={() => setModal("ficha")}><Printer size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Ficha de campo</button>
          {!fechado && <button type="button" className="btn-ghost" onClick={() => setModal("editar")}><Pencil size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Editar</button>}
          {!fechado && <button type="button" className="btn-ghost" onClick={() => setModal("fechar")}>Fechar o dia</button>}
          {!fechado && <button type="button" className="btn-ghost" onClick={() => setModal("cancelar")}><Ban size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Cancelar</button>}
          {dia.estado !== "cancelado" && (
            <button type="button" className="btn-primary-gold" onClick={aplicarTodos} disabled={ocupado || !pendentes.length}>
              <Users size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Aplicar no grupo todo
            </button>
          )}
        </div>
      </div>
      {dia.estado === "fechado" && (
        <Faixa>Dia fechado em {fmtDataHora(dia.fechado_em)}{dia.fechamento_auto ? " (automático, confira)" : ""}. O que chegar agora entra como <b>lançado após o fechamento</b>{dia.contagens.registros_apos_fechamento ? ` (${dia.contagens.registros_apos_fechamento} até agora)` : ""}.</Faixa>
      )}
      {dia.estado === "cancelado" && <Faixa tipo="atencao">Dia cancelado{dia.motivo_cancelamento ? `: ${dia.motivo_cancelamento}` : ""}.</Faixa>}
      {dia.decisao_riscos && <p className="san-nota" style={{ margin: 0 }}>Decisão registrada sobre a data: {dia.decisao_riscos.texto || dia.decisao_riscos.decisao}.</p>}
      {desfazer && <BarraDesfazer registroIds={desfazer.ids} ate={desfazer.ate} texto={desfazer.texto}
        onDesfeito={() => { setDesfazer(null); toast("Desfeito: nada ficou no histórico."); recarregar(); }} onFim={() => setDesfazer(null)} />}
      {avisos.length > 0 && <Faixa tipo="atencao"><ul style={{ margin: 0 }}>{avisos.map((a) => <li key={a}>{a}</li>)}</ul></Faixa>}
      {erroAcao && <Faixa tipo="alerta">{erroAcao}</Faixa>}

      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Produto e dose</h3><span className="san-nota">pode trocar na hora · estoque baixa a cada animal</span></div>
        <div className="san-bloco-corpo san-prods">
          {dia.caixas.map((c) => {
            const e = c.produto.estoque_id ? estoqueId.get(c.produto.estoque_id) : null;
            const cr = caixaResumo.get(c.caixa_id);
            return (
              <div key={c.caixa_id} className="san-prod">
                <b>{c.nome_curto}</b>
                <span>{c.tipo === "exame" ? "Exame: sem produto" : textoProduto(c.produto, e?.nome)}</span>
                {e && <span className="san-nota san-num" style={e.quantidade != null && e.quantidade < 0 ? { color: "var(--alert-fg)", fontWeight: 700 } : undefined}>
                  Saldo: {e.quantidade ?? "—"} {e.unidade || ""}{e.quantidade != null && e.quantidade < 0 ? " · faltou estoque: registre a compra" : ""}</span>}
                <span className="san-nota">{c.tipo === "exame" ? "Resultado por animal" : c.carencia_decisao
                  ? `Carência decidida no dia: ${c.carencia_decisao.modo ? ROTULO_MODO_LEITE[c.carencia_decisao.modo].toLowerCase() : ""} · leite ${c.carencia_decisao.leite_dias ?? "?"} d · carne ${c.carencia_decisao.carne_dias ?? "?"} d`
                  : cr && !cr.carencia_aceita ? "Carência sem aceite: será perguntado ao aplicar" : "Carência da regra da vacina"}</span>
                {!fechado && c.tipo !== "exame" && <button type="button" className="san-link" style={{ alignSelf: "flex-start" }} onClick={() => setTrocar(c)}>Trocar produto ou dose</button>}
              </div>
            );
          })}
        </div>
      </section>

      <section className="san-bloco">
        <div className="san-bloco-cab">
          <h3>Animais</h3>
          <span className="san-nota san-num">{dia.contagens.feitos} de {totalItens} registros · {dia.contagens.animais} animais</span>
        </div>
        {dia.estado !== "cancelado" && (
          <div className="san-bloco-corpo" style={{ borderBottom: "1px solid var(--border)" }}>
            <CampoPessoa id="dAplic" rotulo="Quem aplicou (opcional)" valor={aplicador} onChange={setAplicador} />
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr>
              <th><span className="san-sr">Origem</span></th><th>Brinco</th>
              {dia.caixas.map((c) => <th key={c.caixa_id}>{c.nome_curto}</th>)}
              <th><span className="san-sr">Ações</span></th>
            </tr></thead>
            <tbody>
              {linhas.length ? linhas.map((l) => {
                const temPend = [...l.itens.values()].some((i) => i.estado === "pendente");
                return (
                  <tr key={l.animal_id}>
                    <td><OrigemIcone origem={l.origem} /></td>
                    <td><b className="san-num">{l.numero}</b>{l.curral && <div className="san-nota">decisão no curral</div>}</td>
                    {dia.caixas.map((c) => {
                      const it = l.itens.get(c.caixa_id);
                      if (!it) return <td key={c.caixa_id}><span className="san-st fora">não entra</span></td>;
                      const reg = it.registro_id ? regPorId.get(it.registro_id) : null;
                      return (
                        <td key={c.caixa_id}>
                          {it.estado === "feito" ? (
                            <span className="san-st ok"><Check size={12} aria-hidden="true" />{horaDoRegistro(it) || "feito"}{reg?.apos_fechamento ? " · após o fechamento" : ""}</span>
                          ) : it.estado === "pendente" ? <span className="san-st pend">pendente</span>
                            : <span className="san-st fora">{it.estado === "faltou" ? "faltou" : it.estado === "dispensado" ? "dispensado" : it.estado}</span>}
                          {reg && c.tipo === "exame" && (
                            <div>{reg.resultado ? <b>{ROTULO_RESULTADO[reg.resultado]}</b> : null}
                              {(eu?.pode.ler_exame) && <button type="button" className="san-link" style={{ marginLeft: 6 }} onClick={() => setResultado({ reg, numero: l.numero })}>{reg.resultado ? "corrigir" : "lançar resultado"}</button>}</div>
                          )}
                          {reg && admin && <div><button type="button" className="san-link" onClick={() => setEstorno({ reg, numero: l.numero })}>estornar</button></div>}
                          {it.estado === "pendente" && !fechado && (
                            <button type="button" className="san-link" style={{ marginLeft: 6 }} aria-label={`Tirar ${l.numero} de ${c.nome_curto}`} title="Tirar do dia" disabled={ocupado}
                              onClick={async () => { setOcupado(true); try { await removerAnimalDia(dia.id, it.id); recarregar(); } catch (e) { setErroAcao(mensagemDoErro(e)); } finally { setOcupado(false); } }}>
                              <X size={12} aria-hidden="true" />
                            </button>
                          )}
                        </td>
                      );
                    })}
                    <td>{temPend && dia.estado !== "cancelado"
                      ? <button type="button" className="btn-primary-gold san-btn-sm" disabled={ocupado} onClick={() => aplicarAnimal(l.animal_id)}>Aplicar</button>
                      : <span className="san-nota">{temPend ? "" : "feito"}</span>}</td>
                  </tr>
                );
              }) : (
                <tr><td colSpan={dia.caixas.length + 3} className="san-nota" style={{ textAlign: "center", padding: "1.2rem" }}>Nenhum animal. Use “Adicionar animais”.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="san-bloco-corpo"><LegendaOrigem extra="Aplicar um por vez ou o grupo todo. O grupo não fecha: dá para incluir animais na hora." /></div>
      </section>

      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Registro deste dia</h3>{carregando && <span className="san-nota">atualizando…</span>}</div>
        <div className="san-bloco-corpo">
          {dados.log.length ? <div className="san-log">{dados.log.map((g) => <div key={g.id}><time>{fmtDataHora(g.em)}</time><span>{textoLog(g)}</span></div>)}</div>
            : <p className="san-nota" style={{ margin: 0 }}>Nada registrado ainda.</p>}
        </div>
      </section>

      {modal === "fechar" && <ModalFechar dia={dia} onFechar={() => setModal(null)} onFeito={(d) => { setModal(null); toast(`${d.nome} fechada.`); recarregar(); }} />}
      {modal === "cancelar" && <ModalCancelar dia={dia} onFechar={() => setModal(null)} onFeito={(d) => { setModal(null); toast(`${d.nome} cancelada.`); recarregar(); }} />}
      {modal === "editar" && <ModalMarcarDia dia={dia} onFechar={() => setModal(null)} onSalvo={(_, msg) => { setModal(null); toast(msg); recarregar(); }} />}
      {modal === "ficha" && <ModalFicha diaId={dia.id} onFechar={() => setModal(null)} />}
      {modal === "adicionar" && (
        <SeletorAnimais titulo="Adicionar animais" rotuloOk="Adicionar"
          subtitulo={`Conferindo a regra de ${dia.caixas.map((c) => c.nome_curto).join(", ")}. Quem está fora pode entrar com o seu consentimento.`}
          excluir={linhas.map((l) => l.animal_id)} checar={checarAdicionar()} onFechar={() => setModal(null)}
          onConfirmar={(ids) => {
            setModal(null);
            const todas = dia.caixas.map((c) => c.caixa_id);
            adicionar(ids.map((id) => ({ animal_id: id, caixa_ids: elegCx.get(id)?.length ? elegCx.get(id)! : todas })));
          }} />
      )}
      {trocar && <ModalTrocarProduto dia={dia} caixa={trocar} estoque={dados.estoque} onFechar={() => setTrocar(null)}
        onFeito={() => { setTrocar(null); toast("Produto trocado para os próximos registros."); recarregar(); }} />}
      {resultado && <ModalResultado registro={resultado.reg} numero={resultado.numero} vets={dados.vets} vetPadrao={eu?.veterinario_pessoa_id ?? dia.veterinario?.pessoa_id ?? null}
        onFechar={() => setResultado(null)} onFeito={() => { setResultado(null); toast("Resultado gravado."); recarregar(); }} />}
      {estorno && <ModalEstorno registro={estorno.reg} numero={estorno.numero} onFechar={() => setEstorno(null)}
        onFeito={() => { setEstorno(null); toast("Estornado. O estoque foi devolvido."); recarregar(); }} />}
      {carencia && (
        <ModalCarencia nome={dia.caixas.find((c) => c.caixa_id === carencia.caixaId)?.nome_curto || "vacina"} motivo={carencia.item.motivo_carencia}
          sugestao={carencia.item.carencia_sugerida as CarenciaDecisaoIn | undefined} erro={erroCarencia} salvando={ocupado}
          onCancelar={() => { setCarencia(null); setErroCarencia(null); }} onDecidir={decidirCarencia} />
      )}
      {consentReg && (
        <ModalConsentimento itens={consentReg.map((i) => ({ animal_id: i.animal_id || 0, numero: i.numero, caixa_id: i.caixa_id, caixa: dia.caixas.find((c) => c.caixa_id === i.caixa_id)?.nome_curto, motivo: i.motivo_fora || "fora da regra" }))}
          perguntarAtestado={consentReg.some((i) => i.pergunta_atestado)} onVoltar={() => setConsentReg(null)}
          onConfirmar={(r) => {
            setConsentReg(null);
            if (!r.aceitos.length) return;
            executar(() => registrarNoDia(dia.id, r.aceitos.map((a) => ({
              animal_id: a.animal_id, caixa_id: a.caixa_id ?? null, aplicador_pessoa_id: aplicador.pessoa_id, aplicador_texto: aplicador.texto || null,
              consentimento: { aceito: true, motivo_exibido: a.motivo_exibido, quer_atestado: a.quer_atestado, atestado_destinatario: a.atestado_destinatario },
            }))));
          }} />
      )}
      {consentAdd && (
        <ModalConsentimento itens={consentAdd.itens} perguntarAtestado={!!consentAdd.semAtestado} nomesSemAtestado={consentAdd.semAtestado}
          onVoltar={() => setConsentAdd(null)}
          onConfirmar={(r) => {
            const pedido = consentAdd.pedido.map((p) => ({
              ...p, caixa_ids: p.caixa_ids.filter((c) => !r.recusados.some((x) => x.animal_id === p.animal_id && (x.caixa_id === c || x.caixa_id == null))),
            })).filter((p) => p.caixa_ids.length);
            setConsentAdd(null);
            if (pedido.length) adicionar(pedido, r.aceitos);
          }} />
      )}
    </div>
  );
}

/** Linha do registro (log) do dia. A ciência da preparação (app) mostra quem
 *  e o que ficou sem conferir. */
function textoLog(g: LogItem): string {
  if (g.tipo === "preparacao.ciencia") {
    const itens = Array.isArray(g.payload?.itens_abertos) ? (g.payload!.itens_abertos as string[]) : [];
    return `Ciência da preparação: ${g.texto || "sem nome"}${itens.length ? ` — sem conferir: ${itens.join("; ")}` : ""}.`;
  }
  return g.texto || g.tipo;
}
