"use client";
// Sub-tela: Protocolos — os 4 tipos juntos, em andamento e concluídos, com
// filtro por tipo. É o espelho no app da Central de Protocolos do site,
// consumindo os MESMOS endpoints (/central-protocolos/*).
//
// Lançar continua sendo em Lançar > Protocolos. O que existe aqui é a BAIXA
// de um protocolo já lançado — a exceção deliberada à regra "o Menu é só
// consulta", porque até 08/2026 a Agenda era o único lugar do sistema capaz
// de marcar uma etapa como realizada e escondia a etapa cujo dia tinha
// passado: protocolo que perdia o dia travava em "em andamento" para sempre.
// No curral é justamente onde se descobre que faltou dar baixa.
//
// A baixa segue a do site (app/protocolos/page.tsx › DetalheProtocolo): mostra
// o que aplicar no dia, pergunta de qual frasco/lote saiu e mostra os avisos
// de estoque da resposta. O `medicamentos` do POST sai de lib/baixaProtocolo.ts,
// o mesmo montador do site — as duas telas não podem divergir no formato.
import { useEffect, useState } from "react";
import { MobVoltar, MobCard, MobCampo, MobAviso } from "@/components/mobile/ui";
import {
  fetchCentralProtocolosAcompanhamento, fetchCentralProtocolosHistorico, formatDate,
  fetchDetalheProtocolo,
  type LinhaCentralProtocolos, type DetalheCentralProtocolo, type HormonioProtocolo,
} from "@/lib/api";
import {
  hormoniosDoDia, montarMedicamentosBaixa, mensagemBaixa, opcaoEfetiva, diaInseminacaoIatf,
  type EscolhaPorHormonio,
} from "@/lib/baixaProtocolo";
import { enviarOuEnfileirar } from "@/lib/offline";
import { exportarFolhaCampoPDF } from "@/lib/folhaProtocolo";
import { Printer, Share2 } from "lucide-react";
import type { ModoEntregaExport } from "@/lib/export";
import { ehApp } from "@/lib/nativo";
import { useCarregar, AvisoCopia, Carregando, Vazio } from "@/components/mobile/menu/comum";

const LABEL_TIPO: Record<string, string> = { produtivo: "Produtivo", reprodutivo: "Reprodutivo", sanitario: "Sanitário" };
// Badge por tipo — alinhado aos mesmos tokens --cat-* do Menu/Agenda (antes
// usava mob-azul/roxo/verde soltos, sem relação com o módulo do protocolo).
const COR_TIPO: Record<string, string> = {
  produtivo: "var(--cat-producao)", reprodutivo: "var(--cat-reproducao)", sanitario: "var(--cat-sanidade)",
};
const COR_ESTADO: Record<string, string> = {
  realizada: "var(--mob-verde)", atrasada: "var(--mob-vermelho)", pendente: "var(--mob-muted)",
};

type Aba = "andamento" | "concluidos";

function hoje() { return new Date().toISOString().slice(0, 10); }

export default function Protocolos({ onVoltar }: { onVoltar: () => void }) {
  const [aba, setAba] = useState<Aba>("andamento");
  const [tipo, setTipo] = useState<string>("");
  const [aberto, setAberto] = useState<{ origem: string; id: number } | null>(null);

  const ativos = useCarregar<LinhaCentralProtocolos[]>(
    "menu_protocolos_andamento", () => fetchCentralProtocolosAcompanhamento(),
  );
  const concluidos = useCarregar<LinhaCentralProtocolos[]>(
    "menu_protocolos_concluidos", () => fetchCentralProtocolosHistorico(),
  );

  const atual = aba === "andamento" ? ativos : concluidos;
  const linhas = (atual.dados || []).filter((l) => !tipo || l.tipo === tipo);

  if (aberto) {
    return <DetalheProtocoloApp origem={aberto.origem} origemId={aberto.id} onVoltar={() => setAberto(null)} />;
  }

  return (
    <div>
      <MobVoltar titulo="Protocolos" onVoltar={onVoltar} />
      <AvisoCopia chave={aba === "andamento" ? "menu_protocolos_andamento" : "menu_protocolos_concluidos"} mostrar={atual.doCache} />

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.7rem" }}>
        {([["andamento", "Em andamento"], ["concluidos", "Concluídos"]] as [Aba, string][]).map(([id, label]) => (
          <button key={id} type="button" className={`mob-pill${aba === id ? " ativa" : ""}`} onClick={() => setAba(id)}>
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.9rem" }}>
        {([["", "Todos"], ["reprodutivo", "Reprodutivo"], ["produtivo", "Produtivo"], ["sanitario", "Sanitário"]] as [string, string][]).map(([id, label]) => (
          <button key={id || "todos"} type="button" className={`mob-pill${tipo === id ? " ativa" : ""}`} onClick={() => setTipo(id)}>
            {label}
          </button>
        ))}
      </div>

      {atual.carregando && !atual.dados ? (
        <Carregando />
      ) : !atual.dados ? (
        <Vazio>Sem dados salvos ainda. Conecte-se uma vez para baixar.</Vazio>
      ) : linhas.length === 0 ? (
        <Vazio>
          {aba === "andamento" ? "Nenhum protocolo em andamento" : "Nenhum protocolo concluído"}
          {tipo ? ` do tipo ${LABEL_TIPO[tipo]}.` : "."}
        </Vazio>
      ) : (
        linhas.map((l) => {
          return (
            <MobCard key={`${l.origem}-${l.origem_id}`} style={{ marginBottom: "0.7rem" }}
                     onClick={() => setAberto({ origem: l.origem, id: l.origem_id })}>
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.5rem", marginBottom: "0.35rem" }}>
                <span style={{ fontWeight: 800, fontSize: "0.92rem", lineHeight: 1.3 }}>{l.nome}</span>
                <span style={{
                  fontSize: "0.68rem", fontWeight: 800, flexShrink: 0, padding: "0.12rem 0.5rem", borderRadius: 999,
                  color: COR_TIPO[l.tipo] || "var(--mob-muted)",
                  border: `1px solid ${COR_TIPO[l.tipo] || "var(--mob-border)"}`,
                }}>{LABEL_TIPO[l.tipo] || l.tipo}</span>
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>
                {formatDate(l.data_inicio)} a {formatDate(l.data_fim)}
                {l.animais ? ` · ${l.animais} animal(is)` : ""}
              </div>
              <div style={{ fontSize: "0.85rem", marginTop: "0.3rem" }}>
                <span style={{ fontWeight: 800, color: "var(--mob-acao)" }}>
                  {l.etapas_realizadas}/{l.etapas_total} etapas
                </span>
                {aba === "andamento" && l.etapas_faltam > 0 && (
                  <span style={{ color: "var(--mob-muted)" }}> · faltam {l.etapas_faltam}</span>
                )}
                {l.status === "cancelado" && <span style={{ color: "var(--mob-vermelho)" }}> · cancelado</span>}
                {l.status === "encerrado" && <span style={{ color: "var(--mob-ambar)" }}> · encerrado</span>}
              </div>
              {aba === "andamento" && (
                <div style={{ fontSize: "0.76rem", color: "var(--mob-acao)", marginTop: "0.35rem", fontWeight: 700 }}>
                  Toque para dar baixa →
                </div>
              )}
            </MobCard>
          );
        })
      )}
    </div>
  );
}

// ───────────── Detalhe: a grade animal × dia, em coluna única ─────────────
// No celular a grade do site não cabe: aqui a leitura é por DIA (é assim que
// o trabalho acontece no tronco — "hoje é o D7 deste lote"), e cada dia abre
// a lista de animais daquele passo.
function DetalheProtocoloApp({ origem, origemId, onVoltar }: {
  origem: string; origemId: number; onVoltar: () => void;
}) {
  const [det, setDet] = useState<DetalheCentralProtocolo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "offline" | "erro"; msg: string } | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [diaBaixa, setDiaBaixa] = useState<number | null>(null);
  const [dataBaixa, setDataBaixa] = useState("");
  const [animaisFora, setAnimaisFora] = useState<string[]>([]);
  const [exportando, setExportando] = useState(false);
  // "Compartilhar" (folha do Android) só existe dentro do app.
  const [noApp, setNoApp] = useState(false);
  useEffect(() => { ehApp().then(setNoApp); }, []);
  // Frasco e lote escolhidos para cada medicamento do dia em baixa (índice do
  // medicamento → índice da opção em `h.opcoes` / id do lote). Zera ao abrir
  // outro dia e ao trocar a lista de opções (os índices mudam de sentido).
  const [frasco, setFrasco] = useState<EscolhaPorHormonio>({});
  const [lote, setLote] = useState<EscolhaPorHormonio>({});
  // "Incluir todos (inclusive sem estoque)" — igual ao site: lista toda marca
  // comercial cadastrada do princípio ativo, para registrar o que foi de fato
  // usado mesmo sem frasco em Estoque. Precisa de conexão (relê o detalhe);
  // offline ficam as opções da cópia salva.
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [carregandoOpcoes, setCarregandoOpcoes] = useState(false);

  const cache = useCarregar<DetalheCentralProtocolo>(
    `menu_protocolo_${origem}_${origemId}`, () => fetchDetalheProtocolo(origem, origemId),
  );
  const d = det || cache.dados;

  function abrirBaixa(dia: number) {
    const info = d?.dias.find((x) => x.dia === dia);
    setDiaBaixa(dia);
    setDataBaixa(info && info.data_prevista < hoje() ? info.data_prevista : hoje());
    setAnimaisFora([]);
    setFrasco({}); setLote({});
    setAviso(null);
  }

  async function alternarSemEstoque(v: boolean) {
    setCarregandoOpcoes(true); setErro(null);
    try {
      setDet(await fetchDetalheProtocolo(origem, origemId, v));
      setIncluirSemEstoque(v);
      setFrasco({}); setLote({});
    } catch {
      setErro("Não foi possível carregar a lista completa de medicamentos — precisa de conexão.");
    } finally { setCarregandoOpcoes(false); }
  }

  async function confirmar() {
    if (diaBaixa == null || !d) return;
    const pendentes = d.animais
      .filter((a) => a.celulas.some((c) => c.dia === diaBaixa && !c.realizada))
      .map((a) => a.numero_matriz);
    const marcados = pendentes.filter((n) => !animaisFora.includes(n));
    if (!marcados.length) { setAviso({ tipo: "erro", msg: "Selecione ao menos um animal." }); return; }

    // Sem medicamento no dia (customizado, lida, D11) vem `undefined` e o
    // campo nem vai no corpo — o backend usa os cadastrados, como antes.
    const medicamentos = montarMedicamentosBaixa(origem, hormoniosDoDia(origem, d, diaBaixa), frasco, lote);

    setSalvando(true); setErro(null);
    try {
      const r = await enviarOuEnfileirar(
        `/central-protocolos/${origem}/${origemId}/baixa`,
        {
          dia: diaBaixa,
          animais: marcados.length === pendentes.length ? null : marcados,
          data_realizacao: dataBaixa || null,
          ...(medicamentos ? { medicamentos } : {}),
        },
        `Baixa do protocolo ${d.nome} — D${diaBaixa}`,
        "POST",
      );
      setDiaBaixa(null);
      if (r.enviado) {
        // Avisos de estoque (saldo insuficiente, frasco não achado…) em âmbar,
        // como alerta — a baixa foi gravada mesmo assim.
        const temAvisos = !!r.resposta?.avisos?.length;
        setAviso({ tipo: temAvisos ? "offline" : "ok", msg: mensagemBaixa(r.resposta) });
        // Só relê do servidor quando o envio de fato aconteceu; offline, o
        // recarregamento traria de volta a grade sem a baixa.
        await fetchDetalheProtocolo(origem, origemId, incluirSemEstoque).then(setDet).catch(() => {});
      } else {
        // A fila offline (lib/offline.ts › sincronizar) não guarda o corpo da
        // resposta: os avisos de estoque deste envio não voltam para a tela.
        setAviso({ tipo: "offline", msg: medicamentos
          ? "Guardado — será enviado quando conectar, com o frasco escolhido. O estoque só é conferido no envio: depois de sincronizar, confira o saldo em Estoque."
          : "Guardado — será enviado quando conectar." });
      }
    } catch (e: any) {
      setErro(e?.message || "Não foi possível salvar.");
    } finally { setSalvando(false); }
  }

  // Sem isto, um erro na geração do PDF (ex.: dado incompleto vindo do cache
  // offline) virava rejeição de promise não tratada: o clique não fazia
  // NADA visível, sem alerta nenhum — pior ainda que um erro explícito.
  async function exportarFolha(modo: ModoEntregaExport = "baixar") {
    if (!d) return;
    setExportando(true); setErro(null);
    try {
      await exportarFolhaCampoPDF(d, modo);
    } catch (e: any) {
      setErro(e?.message || "Não foi possível gerar a folha de campo.");
    } finally {
      setExportando(false);
    }
  }

  if (cache.carregando && !d) return (<div><MobVoltar titulo="Protocolo" onVoltar={onVoltar} /><Carregando /></div>);
  if (!d) return (
    <div><MobVoltar titulo="Protocolo" onVoltar={onVoltar} />
      <Vazio>Sem dados salvos deste protocolo. Conecte-se uma vez para baixar.</Vazio></div>
  );

  const pendentesDoDia = diaBaixa == null ? [] :
    d.animais.filter((a) => a.celulas.some((c) => c.dia === diaBaixa && !c.realizada));
  const hormonios = hormoniosDoDia(origem, d, diaBaixa);
  const diaInseminacao = diaInseminacaoIatf(origem, d.dias);

  return (
    <div>
      <MobVoltar titulo={d.nome} onVoltar={onVoltar} />
      <AvisoCopia chave={`menu_protocolo_${origem}_${origemId}`} mostrar={cache.doCache && !det} />

      <div style={{ fontSize: "0.85rem", marginBottom: "0.8rem" }}>
        <strong>{d.etapas_realizadas}</strong> de {d.etapas_total} etapas
        {d.etapas_atrasadas > 0 && <span style={{ color: "var(--mob-vermelho)", fontWeight: 700 }}> · {d.etapas_atrasadas} atrasada(s)</span>}
        <span style={{ color: "var(--mob-muted)" }}> · {d.animais.length} animal(is)</span>
      </div>

      {d.encerrado_em && (
        <MobAviso tipo="offline">
          Encerrado em {formatDate(d.encerrado_em)}{d.encerrado_motivo ? ` — ${d.encerrado_motivo}` : ""}. Para reabrir, use o site.
        </MobAviso>
      )}
      {erro && <MobAviso tipo="erro">{erro}</MobAviso>}
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}

      {/* Só PDF no app: no celular, Excel não serve para nada e ocuparia
          espaço numa tela que é para ser resolvida com o polegar. A folha é
          para imprimir e o funcionário ir anotando à caneta, no curral. */}
      {diaBaixa == null && (
        <button type="button" className="mob-btn mob-btn-sec" style={{ marginBottom: "0.9rem" }}
                onClick={() => exportarFolha()} disabled={exportando}>
          <Printer size={16} style={{ marginRight: "0.4rem", verticalAlign: "-0.2em" }} />
          {exportando ? "Gerando…" : "Folha de campo (PDF)"}
        </button>
      )}
      {diaBaixa == null && noApp && (
        <button type="button" className="mob-btn mob-btn-sec" style={{ marginBottom: "0.9rem" }}
                onClick={() => exportarFolha("compartilhar")} disabled={exportando}>
          <Share2 size={16} style={{ marginRight: "0.4rem", verticalAlign: "-0.2em" }} />
          Compartilhar folha
        </button>
      )}

      {diaBaixa == null ? (
        d.dias.map((dia) => {
          const feito = dia.realizadas >= dia.total;
          const atrasado = !feito && dia.data_prevista < hoje();
          // Dia de inseminação do IATF: não dá baixa por aqui (o backend
          // recusa) — mesma regra do site, ver diaInseminacaoIatf.
          const ehInseminacao = dia.dia === diaInseminacao;
          const podeBaixar = !feito && !d.encerrado_em && !ehInseminacao;
          return (
            <MobCard key={dia.dia} style={{ marginBottom: "0.6rem" }}
                     onClick={podeBaixar ? () => abrirBaixa(dia.dia) : undefined}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.5rem" }}>
                <span style={{ fontWeight: 800, fontSize: "0.95rem" }}>{dia.rotulo}</span>
                <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)" }}>{formatDate(dia.data_prevista)}</span>
              </div>
              {dia.descricao && (
                <div style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>{dia.descricao}</div>
              )}
              <div style={{ fontSize: "0.85rem", marginTop: "0.35rem", fontWeight: 700,
                            color: COR_ESTADO[feito ? "realizada" : atrasado ? "atrasada" : "pendente"] }}>
                {feito ? `✓ ${dia.total} aplicada(s)` : `${dia.realizadas}/${dia.total} — ${atrasado ? "atrasado" : "a vencer"}`}
              </div>
              {podeBaixar && (
                <div style={{ fontSize: "0.76rem", color: "var(--mob-acao)", marginTop: "0.3rem", fontWeight: 700 }}>
                  Toque para dar baixa →
                </div>
              )}
              {!feito && !d.encerrado_em && ehInseminacao && (
                <div style={{ fontSize: "0.76rem", color: "var(--mob-ambar)", marginTop: "0.3rem" }}>
                  A inseminação não se confirma aqui: registre o serviço (touro/sêmen) em Lançar › Inseminação,
                  que fecha esta etapa sozinho.
                </div>
              )}
            </MobCard>
          );
        })
      ) : (
        <>
          <MobCampo label="Em que dia foi aplicado?">
            <input type="date" className="mob-input" value={dataBaixa} max={hoje()}
                   onChange={(e) => setDataBaixa(e.target.value)} />
          </MobCampo>
          <p style={{ fontSize: "0.76rem", color: "var(--mob-muted)", margin: "-0.4rem 0 0.9rem" }}>
            A data real da aplicação — é ela que vai para a ficha do animal, não a data de hoje.
          </p>

          <MobCampo label={`Animais (${pendentesDoDia.length - animaisFora.length} de ${pendentesDoDia.length})`}>
            <div>
              {pendentesDoDia.map((a) => {
                const marcado = !animaisFora.includes(a.numero_matriz);
                return (
                  <label key={a.numero_matriz}
                         style={{ display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.55rem 0.2rem",
                                  fontSize: "0.92rem", borderBottom: "1px solid var(--mob-border)" }}>
                    <input type="checkbox" checked={marcado} style={{ width: 22, height: 22 }}
                           onChange={(e) => setAnimaisFora((p) => e.target.checked
                             ? p.filter((n) => n !== a.numero_matriz) : [...p, a.numero_matriz])} />
                    {a.numero_matriz}
                  </label>
                );
              })}
            </div>
          </MobCampo>

          {hormonios.length > 0 && (
            <MedicamentosDoDia hormonios={hormonios} frasco={frasco} lote={lote}
                               incluirSemEstoque={incluirSemEstoque} carregandoOpcoes={carregandoOpcoes}
                               onFrasco={(idx, v) => {
                                 setFrasco((p) => ({ ...p, [idx]: v }));
                                 // Trocou o frasco — o lote escolhido antes não vale para o novo.
                                 setLote((p) => ({ ...p, [idx]: "" }));
                               }}
                               onLote={(idx, v) => setLote((p) => ({ ...p, [idx]: v }))}
                               onIncluirSemEstoque={alternarSemEstoque} />
          )}

          <button type="button" className="mob-btn" onClick={confirmar} disabled={salvando}>
            {salvando ? "Salvando…" : "Confirmar baixa"}
          </button>
          <button type="button" className="mob-btn mob-btn-sec" style={{ marginTop: "0.6rem" }}
                  onClick={() => setDiaBaixa(null)} disabled={salvando}>
            Cancelar
          </button>
        </>
      )}
    </div>
  );
}

// ───────────── "O que aplicar neste dia" + de qual frasco/lote ─────────────
// Versão de polegar do bloco "Qual medicamento/frasco você está usando?" do
// site: um cartão por medicamento, com o seletor de frasco (opções do
// detalhe, saldo ao lado) e, quando o frasco tem mais de um lote de compra
// aberto, o de lote — vazio deixa o backend tirar do mais antigo (FIFO).
function MedicamentosDoDia({ hormonios, frasco, lote, incluirSemEstoque, carregandoOpcoes, onFrasco, onLote, onIncluirSemEstoque }: {
  hormonios: HormonioProtocolo[]; frasco: EscolhaPorHormonio; lote: EscolhaPorHormonio;
  incluirSemEstoque: boolean; carregandoOpcoes: boolean;
  onFrasco: (idx: number, v: number | "") => void; onLote: (idx: number, v: number | "") => void;
  onIncluirSemEstoque: (v: boolean) => void;
}) {
  return (
    <div style={{ marginBottom: "0.9rem" }}>
      <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.4rem" }}>
        O que aplicar neste dia
      </div>
      {hormonios.map((h, idx) => {
        const sel = opcaoEfetiva(h, frasco[idx]);
        const opcao = sel === "" ? undefined : h.opcoes?.[sel];
        const lotes = opcao?.lotes || [];
        const detalhe = [
          h.dose != null ? `${h.dose}${h.unidade ? ` ${h.unidade}` : ""}` : null,
          h.via,
        ].filter(Boolean).join(" · ");
        return (
          <MobCard key={idx} style={{ marginBottom: "0.6rem" }}>
            <div style={{ fontWeight: 800, fontSize: "0.92rem" }}>{h.produto}</div>
            {detalhe && <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.15rem" }}>{detalhe}</div>}
            <div style={{ marginTop: "0.6rem" }}>
              {(h.opcoes?.length ?? 0) === 0 ? (
                <p style={{ fontSize: "0.8rem", color: "var(--mob-ambar)", margin: 0 }}>
                  Sem medicamento em estoque para este princípio.
                  {!incluirSemEstoque && " Marque \"incluir mesmo sem estoque\" abaixo para registrar o que foi usado."}
                </p>
              ) : (
                <MobCampo label="De qual frasco?">
                  <select className="mob-input" value={sel} disabled={carregandoOpcoes}
                          onChange={(e) => onFrasco(idx, e.target.value === "" ? "" : Number(e.target.value))}>
                    <option value="">Selecione o frasco…</option>
                    {h.opcoes.map((o, oi) => (
                      <option key={oi} value={oi}>
                        {o.nome}{o.marca ? ` · ${o.marca}` : ""}
                        {o.sem_estoque ? " — sem frasco em estoque" : ` — saldo ${o.saldo} ${o.unidade || ""}${!o.estoque_inicializado ? " (sem estoque inicial)" : ""}`}
                      </option>
                    ))}
                  </select>
                </MobCampo>
              )}
              {lotes.length > 1 && (
                <MobCampo label="De qual lote?">
                  <select className="mob-input" value={lote[idx] ?? ""}
                          onChange={(e) => onLote(idx, e.target.value === "" ? "" : Number(e.target.value))}>
                    <option value="">Automático — mais antigo primeiro</option>
                    {lotes.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.numero_lote ? `Lote ${l.numero_lote}` : `Comprado em ${formatDate(l.data_compra)}`} — saldo {l.quantidade_restante}
                      </option>
                    ))}
                  </select>
                </MobCampo>
              )}
            </div>
          </MobCard>
        );
      })}
      <label style={{ display: "flex", alignItems: "center", gap: "0.6rem", fontSize: "0.85rem", padding: "0.3rem 0.2rem" }}>
        <input type="checkbox" checked={incluirSemEstoque} disabled={carregandoOpcoes} style={{ width: 22, height: 22 }}
               onChange={(e) => onIncluirSemEstoque(e.target.checked)} />
        {carregandoOpcoes ? "Carregando…" : "Incluir todos os medicamentos (inclusive sem estoque)"}
      </label>
    </div>
  );
}
