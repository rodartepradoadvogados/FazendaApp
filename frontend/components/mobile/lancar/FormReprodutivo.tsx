"use client";
// Sub-tela REPRODUTIVO: quatro lançamentos em pílulas — Inseminação,
// Diagnóstico, Parto e Protocolo IATF (D0). Usa os mesmos endpoints do
// desktop (/reproducao/*). Inseminação e Protocolo IATF são lançamentos EM LOTE
// (dois passos, como o Diagnóstico) e moram em ./lote/ — aqui só se escolhe qual abrir.
import { useEffect, useState, type CSSProperties } from "react";
import { Syringe, Stethoscope, Baby, CalendarClock } from "lucide-react";
import { MobCampo, MobAviso, MobVoltar, MobConfirmModal } from "@/components/mobile/ui";
import { sugestaoLoteEvento, criarMovimentacao, fetchLotes } from "@/lib/api";
import { enviarOuEnfileirar, fetchComCache } from "@/lib/offline";
import { delDesdeParto } from "@/lib/partoLancamento";
import { hojeLocal } from "@/lib/financeiroSituacao";
import { DiagnosticoGestacao } from "./DiagnosticoGestacao";
import { Inseminacao } from "./lote/InseminacaoLote";
import { ProtocoloIatf } from "./lote/ProtocoloIatfLote";
import {
  type Animal, useEnvio, useRascunho, hoje,
  BotoesEscolha, SeletorAnimal, GradeAcoes, RascunhoAviso,
} from "./comum";

type Aba = "inseminacao" | "diagnostico" | "parto" | "iatf";

const TITULOS_ABA: Record<Aba, string> = {
  inseminacao: "Inseminação", diagnostico: "Diagnóstico", parto: "Parto", iatf: "Protocolo IATF",
};

export function FormReprodutivo({ animais, animalFixado, restringirA }: { animais: Animal[]; animalFixado: string | null; restringirA?: Aba[] }) {
  const [aba, setAba] = useState<Aba | null>(null);
  // Diagnóstico Negativo → "Salvar e lançar inseminação": abre a Inseminação com estes animais já escolhidos.
  const [paraInseminar, setParaInseminar] = useState<string[] | null>(null);

  if (!aba) {
    // `restringirA` (opcional): usado pelo Modo Curral para mostrar só
    // Inseminação/Parto — sem o prop (undefined), o comportamento é idêntico
    // ao de hoje, as 4 opções completas usadas por Lançar (LancarTela.tsx).
    const opcoes = [
      { id: "inseminacao", label: "Inseminação", icone: <Syringe size={28} />, cor: "var(--mob-azul)" },
      { id: "diagnostico", label: "Diagnóstico", icone: <Stethoscope size={28} />, cor: "var(--mob-verde)" },
      { id: "parto", label: "Parto", icone: <Baby size={28} />, cor: "var(--mob-roxo)" },
      { id: "iatf", label: "Protocolo IATF", icone: <CalendarClock size={28} />, cor: "var(--mob-laranja)" },
    ].filter((o) => !restringirA || restringirA.includes(o.id as Aba));
    return <GradeAcoes opcoes={opcoes} onEscolher={(id) => setAba(id as Aba)} />;
  }

  return (
    <>
      <MobVoltar titulo={TITULOS_ABA[aba]} onVoltar={() => { setAba(null); setParaInseminar(null); }} />
      {aba === "inseminacao" && <Inseminacao animais={animais} animalFixado={animalFixado} matrizesIniciais={paraInseminar ?? undefined} />}
      {aba === "diagnostico" && <DiagnosticoGestacao animalFixado={animalFixado} onIrParaInseminacao={(n) => { setParaInseminar(n); setAba("inseminacao"); }} />}
      {aba === "parto" && <Parto animais={animais} animalFixado={animalFixado} />}
      {aba === "iatf" && <ProtocoloIatf animais={animais} animalFixado={animalFixado} />}
    </>
  );
}

// ── Parto → POST /reproducao/parto (ou /reproducao/encerramento-gestacao p/
// Aborto) ─────────────────────────────────────────────────────────────────
// Espelha o formulário do site (FormParto.tsx): tipo de parto (inclui
// Natimorto/Aborto), retenção de placenta, parto gemelar (2ª cria), e os
// blocos de colostragem/IgG da cria — recolhidos por padrão (toque para
// abrir), já que a maioria dos partos no curral não tem esses dados na hora.
//
// Após o parto ser salvo de verdade (online), sugere lote real para a MÃE
// (del_dias=0, acabou de parir) e para cada CRIA cadastrada (categoria
// Bezerra/Bezerro, data_nasc = data do parto) via sugestaoLoteEvento — mesma
// função do site. Um pop-up por vez (mãe primeiro, crias depois), nunca
// sobrepostos; só confirma se o usuário tocar em "Confirmar", e só mostra
// sucesso se criarMovimentacao realmente funcionar. Sugestão/alocação só
// roda com o lançamento enviado online de fato — se caiu na fila offline
// (sem internet), não há como saber ainda se foi aceito, então pula esse
// passo (fica só para quando sincronizar). Sem lote que bata nos critérios
// (não há lote pré-definido), o pop-up PERGUNTA para qual lote mandar em vez de
// pular em silêncio (`semSugestao`). Mesma regra vale para a
// colostragem: só é gravada (2º POST, /sanidade/colostragem) se a 1ª cria
// foi de fato criada E algum campo de colostro/IgG foi preenchido — mesma
// lógica de `registrarColostragem` do site.
type SugestaoLoteParto = { tipo: "mae" | "cria"; numero: string; codigo: string; rotulo: string; motivo: string; semSugestao?: boolean };
type LoteCadastro = { codigo: string; rotulo: string };

const TIPOS_PARTO = ["Normal", "Distócico moderado", "Distócico severo", "Cesariana", "Natimorto", "Aborto"];
const LITROS_COLOSTRO = ["1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"];
const BRIX_COLOSTRO_OPCOES = Array.from({ length: 21 }, (_, i) => String(15 + i)); // 15%…35%
const BRIX_SORO_OPCOES = Array.from({ length: 13 }, (_, i) => (6 + i * 0.5).toFixed(1)); // 6,0%…12,0%

// Classificação simplificada (mesmos limiares do site — ver FormParto.tsx),
// só para dar um retorno imediato de qualidade no formulário compacto do app.
function classeColostro(brix: number): { txt: string; cor: string } {
  if (brix > 25) return { txt: "Ouro (excelente)", cor: "var(--mob-verde)" };
  if (brix >= 18) return { txt: "Prata (médio)", cor: "var(--mob-ambar)" };
  return { txt: "Bronze (ruim)", cor: "var(--mob-vermelho)" };
}
function classeSoro(brix: number): { txt: string; cor: string } {
  if (brix >= 8.4) return { txt: "Sucesso — bezerra protegida", cor: "var(--mob-verde)" };
  if (brix >= 8.1) return { txt: "Alerta — monitorar", cor: "var(--mob-ambar)" };
  return { txt: "Falha — ação urgente", cor: "var(--mob-vermelho)" };
}

function Parto({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, setAviso, erroValidacao } = useEnvio();
  // Rascunho da matriz — mesma razão dos demais formulários (docs/agents/
  // design-implementation.md §5, acabamento-de-campo.html).
  const rascunho = useRascunho<string>("parto_matriz", animalFixado || "");
  const matriz = rascunho.valor;
  const setMatriz = rascunho.setValor;
  const [data, setData] = useState(hoje());
  const [tipoParto, setTipoParto] = useState("");
  const [retencaoPlacenta, setRetencaoPlacenta] = useState(false);
  const [gemelar, setGemelar] = useState(false);
  const [gemelarSexo, setGemelarSexo] = useState("");
  const [criaSexo, setCriaSexo] = useState<"F" | "M" | "">("");
  const [criaNumero, setCriaNumero] = useState("");
  const [criaBaixada, setCriaBaixada] = useState(false);
  const [cria2Sexo, setCria2Sexo] = useState<"F" | "M" | "">("");
  const [cria2Numero, setCria2Numero] = useState("");
  const [cria2Baixada, setCria2Baixada] = useState(false);
  const [salvando, setSalvando] = useState(false);

  // Colostragem/IgG da 1ª cria — recolhido por padrão (progressive disclosure,
  // mesmo padrão do "Hormônios do protocolo" em ProtocoloIatf, abaixo).
  const [verColostro, setVerColostro] = useState(false);
  const [horaParto, setHoraParto] = useState("");
  const [horaColostro, setHoraColostro] = useState("");
  const [pesoNascer, setPesoNascer] = useState("");
  const [tomouColostro, setTomouColostro] = useState<"Sim" | "Não" | "">("");
  const [litrosColostro, setLitrosColostro] = useState("");
  const [brixColostro, setBrixColostro] = useState("");
  const [brixSoro, setBrixSoro] = useState("");
  const [proteinaSerica, setProteinaSerica] = useState("");
  const [apenasColostroPo, setApenasColostroPo] = useState(false);

  const ehAborto = tipoParto === "Aborto";
  const [abortoPendente, setAbortoPendente] = useState(false);
  const [salvandoAborto, setSalvandoAborto] = useState(false);

  // Natimorto: nasceu, mas não entra no rebanho — baixa automática (mesmo
  // comportamento do site); sexo continua sendo perguntado.
  useEffect(() => {
    if (tipoParto === "Natimorto") { setCriaBaixada(true); setCria2Baixada(true); }
  }, [tipoParto]);

  const clsColostro = brixColostro ? classeColostro(Number(brixColostro)) : null;
  const clsSoro = brixSoro ? classeSoro(Number(brixSoro)) : null;

  const [filaSugestoes, setFilaSugestoes] = useState<SugestaoLoteParto[]>([]);
  const [movendo, setMovendo] = useState(false);
  // Destino escolhido à mão quando o sistema não tem lote pré-definido para o animal.
  const [lotesCadastro, setLotesCadastro] = useState<LoteCadastro[]>([]);
  const [loteEscolhido, setLoteEscolhido] = useState("");
  useEffect(() => {
    fetchComCache<LoteCadastro[]>("lotes_cadastro", () => fetchLotes()).then(({ dados }) => setLotesCadastro(dados || []));
  }, []);
  const [avisosLote, setAvisosLote] = useState<{ tipo: "ok" | "erro"; msg: string }[]>([]);

  function limparCampos() {
    setTipoParto(""); setRetencaoPlacenta(false); setGemelar(false); setGemelarSexo("");
    setCriaSexo(""); setCriaNumero(""); setCriaBaixada(false);
    setCria2Sexo(""); setCria2Numero(""); setCria2Baixada(false);
    setHoraParto(""); setHoraColostro(""); setPesoNascer("");
    setTomouColostro(""); setLitrosColostro(""); setBrixColostro("");
    setBrixSoro(""); setProteinaSerica(""); setApenasColostroPo(false);
    setVerColostro(false);
  }

  // Sugere lote da mãe (del_dias já calculado pelo backend) e enfileira a
  // pergunta se for diferente do lote atual — usado tanto pelo parto normal
  // quanto pelo aborto.
  async function sugerirLoteMae(delDias: number, motivo: string, fila: SugestaoLoteParto[]) {
    const matrizObj = animais.find((a) => a.numero === matriz);
    try {
      const { lote_sugerido } = await sugestaoLoteEvento({
        numero_matriz: matriz,
        categoria_abrev: matrizObj?.categoria_abrev || matrizObj?.categoria_completa || "",
        del_dias: delDias,
      });
      if (!lote_sugerido) {
        fila.push({ tipo: "mae", numero: matriz, codigo: "", rotulo: "", motivo, semSugestao: true });
      } else if (lote_sugerido.rotulo !== matrizObj?.grupo_primario) {
        fila.push({ tipo: "mae", numero: matriz, codigo: lote_sugerido.codigo, rotulo: lote_sugerido.rotulo, motivo });
      }
    } catch { /* sugestão é best-effort — não bloqueia o lançamento já salvo */ }
  }

  async function salvar() {
    if (!matriz) return erroValidacao("Selecione a matriz.");
    if (!data) return erroValidacao("Informe a data do parto.");
    if (ehAborto) {
      // Só ABRE a pergunta "deseja abrir lactação?" — a gravação (num POST
      // só, /reproducao/encerramento-gestacao) acontece em `concluirAborto`,
      // igual ao PopupAborto do site.
      setAbortoPendente(true);
      return;
    }
    if (!criaSexo) return erroValidacao("Toque no sexo da cria (F ou M).");
    // Sexo é obrigatório para toda cria com número (o servidor recusa com 422): a 2ª cria não pode mais ser descartada em silêncio.
    if (gemelar && cria2Numero.trim() && !cria2Sexo) return erroValidacao("Toque no sexo da 2ª cria (F ou M).");

    const crias: { numero: string; sexo: string; nasceu_viva: boolean }[] = [
      { numero: criaNumero.trim(), sexo: criaSexo, nasceu_viva: !criaBaixada },
      ...(gemelar && cria2Sexo ? [{ numero: cria2Numero.trim(), sexo: cria2Sexo, nasceu_viva: !cria2Baixada }] : []),
    ];

    setSalvando(true);
    setAviso(null);
    setAvisosLote([]);
    setFilaSugestoes([]);
    try {
      const { enviado, resposta } = await enviarOuEnfileirar(
        "/reproducao/parto",
        {
          numero_matriz: matriz, data_parto: data, tipo_parto: tipoParto || undefined,
          crias, retencao_placenta: retencaoPlacenta || undefined, gemelar: gemelar || undefined,
          gemelar_sexo: gemelar ? (gemelarSexo || undefined) : undefined,
        },
        `Parto — matriz ${matriz} (cria ${criaSexo === "F" ? "fêmea" : "macho"})`,
      );
      setAviso(enviado
        ? { tipo: "ok", msg: "Lançamento salvo." }
        : { tipo: "offline", msg: "Sem internet — guardado, será enviado automaticamente ao conectar." });
      try { navigator.vibrate?.(enviado ? 20 : [15, 60, 15]); } catch { /* sem suporte — segue sem vibrar */ }

      if (enviado) {
        const criasCriadas: string[] = resposta?.crias_criadas || [];
        const fila: SugestaoLoteParto[] = [];
        // DEL real (parto lançado com data de 2 dias atrás = DEL 2) — é o que o motor de critérios usa para achar o lote.
        await sugerirLoteMae(delDesdeParto(data, hojeLocal()), "Parto", fila);

        for (const c of criasCriadas) {
          const sexoCria = c === cria2Numero.trim() ? cria2Sexo : criaSexo;
          try {
            const { lote_sugerido } = await sugestaoLoteEvento({
              numero_matriz: c,
              categoria_abrev: sexoCria === "F" ? "Bezerra" : "Bezerro",
              data_nasc: data,
            });
            fila.push(lote_sugerido
              ? { tipo: "cria", numero: c, codigo: lote_sugerido.codigo, rotulo: lote_sugerido.rotulo, motivo: "Nascimento" }
              : { tipo: "cria", numero: c, codigo: "", rotulo: "", motivo: "Nascimento", semSugestao: true });
          } catch { /* idem */ }
        }
        setFilaSugestoes(fila);

        // Colostragem/IgG só descrevem a 1ª cria (mesmo formulário único do
        // site) — grava só se ela foi de fato criada e algum dado foi informado.
        const criaRegistrada = criasCriadas.includes(criaNumero.trim());
        const algumDadoColostro = tomouColostro || litrosColostro || brixColostro || brixSoro || proteinaSerica || horaParto || horaColostro || pesoNascer || apenasColostroPo;
        if (criaRegistrada && algumDadoColostro) {
          try {
            await enviarOuEnfileirar(
              "/sanidade/colostragem",
              {
                numero_animal: criaNumero.trim(),
                tomou_colostro: tomouColostro ? tomouColostro === "Sim" : undefined,
                litros_colostro: litrosColostro ? Number(litrosColostro) : undefined,
                brix_colostro: brixColostro ? Number(brixColostro) : undefined,
                data_colostro: brixColostro ? data : undefined,
                hora_parto: horaParto || undefined,
                hora_colostro: horaColostro || undefined,
                peso_nascer_kg: pesoNascer ? Number(pesoNascer) : undefined,
                brix_soro: brixSoro ? Number(brixSoro) : undefined,
                proteina_serica: proteinaSerica ? Number(proteinaSerica) : undefined,
                apenas_colostro_po: apenasColostroPo || undefined,
                data_teste_sangue: brixSoro ? data : undefined,
              },
              `Colostragem/IgG — brinco ${criaNumero.trim()}`,
            );
          } catch (e) {
            setAvisosLote((p) => [...p, { tipo: "erro", msg: `A colostragem não pôde ser gravada${e instanceof Error ? `: ${e.message}` : ""}.` }]);
          }
        }
      }

      limparCampos();
    } catch (e) {
      setAviso({ tipo: "erro", msg: e instanceof Error ? e.message : "Erro ao salvar." });
      try { navigator.vibrate?.([25, 60, 25, 60, 25]); } catch { /* sem suporte — segue sem vibrar */ }
    } finally {
      setSalvando(false);
    }
  }

  // Aborto: grava tudo num POST só (POST /reproducao/encerramento-gestacao)
  // — `Parto` com `ordem_parto` NULL, perda de prenhez no serviço vigente e,
  // se respondido "sim", a `Lactacao` com a data real do evento — igual ao
  // `concluirAborto` do site. Via enviarOuEnfileirar (não `encerrarGestacao`
  // de lib/api.ts) para não perder a fila offline.
  async function concluirAborto(abrirLact: boolean) {
    setSalvandoAborto(true);
    setAviso(null);
    setAvisosLote([]);
    setFilaSugestoes([]);
    try {
      const { enviado, resposta } = await enviarOuEnfileirar(
        "/reproducao/encerramento-gestacao",
        { numero_matriz: matriz, data, tipo: "aborto", abrir_lactacao: abrirLact, motivo: "aborto" },
        `Aborto — matriz ${matriz}`,
      );
      setAviso(enviado
        ? { tipo: "ok", msg: "Aborto registrado." }
        : { tipo: "offline", msg: "Sem internet — guardado, será enviado automaticamente ao conectar." });
      try { navigator.vibrate?.(enviado ? 20 : [15, 60, 15]); } catch { /* sem suporte — segue sem vibrar */ }

      if (enviado && resposta?.sugerir_lote) {
        const fila: SugestaoLoteParto[] = [];
        await sugerirLoteMae(resposta.del_dias ?? 0, "Aborto", fila);
        setFilaSugestoes(fila);
      }

      limparCampos();
    } catch (e) {
      setAviso({ tipo: "erro", msg: e instanceof Error ? e.message : "Erro ao salvar." });
      try { navigator.vibrate?.([25, 60, 25, 60, 25]); } catch { /* sem suporte — segue sem vibrar */ }
    } finally {
      setSalvandoAborto(false);
      setAbortoPendente(false);
    }
  }

  async function confirmarSugestaoAtual() {
    const item = filaSugestoes[0];
    if (!item) return;
    // Sem sugestão do sistema: o destino é o que a pessoa escolheu na lista.
    const codigo = item.semSugestao ? loteEscolhido : item.codigo;
    const rotulo = item.semSugestao ? (lotesCadastro.find((l) => l.codigo === codigo)?.rotulo || codigo) : item.rotulo;
    if (!codigo) return;
    setMovendo(true);
    try {
      await criarMovimentacao({ data_movimento: data, motivo: item.motivo, lote_destino_codigo: codigo, animais: [item.numero], origem: "sugestao_confirmada" });
      setAvisosLote((p) => [...p, { tipo: "ok", msg: `${item.numero} movido para o lote ${rotulo}.` }]);
    } catch (e) {
      // Erro real na movimentação — não finge sucesso, mostra o problema.
      setAvisosLote((p) => [...p, { tipo: "erro", msg: `Não foi possível mover ${item.numero} para o lote ${rotulo}${e instanceof Error ? `: ${e.message}` : ""}.` }]);
    } finally {
      setMovendo(false);
      setLoteEscolhido("");
      setFilaSugestoes((f) => f.slice(1));
    }
  }
  function cancelarSugestaoAtual() {
    setLoteEscolhido("");
    setFilaSugestoes((f) => f.slice(1));
  }

  const sugestaoAtual = filaSugestoes[0];
  const checkboxStyle: CSSProperties = { display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.9rem", padding: "0.3rem 0" };

  return (
    <>
      <RascunhoAviso mostrar={rascunho.salvo} />
      <MobCampo label="Matriz (nº / nome)">
        <SeletorAnimal animais={animais} valor={matriz} onChange={setMatriz} placeholder="Buscar matriz…" />
      </MobCampo>
      <MobCampo label="Data do parto">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>
      <MobCampo label="Tipo de parto">
        <select className="mob-input" value={tipoParto} onChange={(e) => setTipoParto(e.target.value)}>
          <option value="">Selecione…</option>
          {TIPOS_PARTO.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </MobCampo>

      {ehAborto ? (
        <p style={{ fontSize: "0.82rem", color: "var(--mob-muted)", lineHeight: 1.4, marginBottom: "0.9rem" }}>
          Aborto não é um parto — nenhuma cria é cadastrada. Ao salvar, registra a perda de prenhez da matriz e
          pergunta se deseja abrir lactação.
        </p>
      ) : (
        <>
          <MobCampo label="Retenção de placenta">
            <label style={checkboxStyle}>
              <input type="checkbox" checked={retencaoPlacenta} onChange={(e) => setRetencaoPlacenta(e.target.checked)} /> Sim (gera item na Agenda)
            </label>
          </MobCampo>
          <MobCampo label="Parto gemelar (2 crias)">
            <label style={checkboxStyle}>
              <input type="checkbox" checked={gemelar} onChange={(e) => setGemelar(e.target.checked)} /> Sim
            </label>
          </MobCampo>
          {gemelar && (
            <MobCampo label="Sexos do parto gemelar">
              <select className="mob-input" value={gemelarSexo} onChange={(e) => setGemelarSexo(e.target.value)}>
                <option value="">Selecione… (ou deriva dos sexos)</option>
                <option value="FF">FF — duas fêmeas</option>
                <option value="FM">FM — fêmea e macho</option>
                <option value="MM">MM — dois machos</option>
              </select>
            </MobCampo>
          )}

          <MobCampo label="Sexo da cria">
            <BotoesEscolha
              opcoes={[{ valor: "F", label: "Fêmea" }, { valor: "M", label: "Macho" }]}
              valor={criaSexo} onChange={setCriaSexo}
            />
          </MobCampo>
          <MobCampo label="Número da cria (opcional — vazio = baixa automática)">
            <input className="mob-input" value={criaNumero} onChange={(e) => setCriaNumero(e.target.value)} placeholder="ex.: 4521" />
          </MobCampo>
          <MobCampo label="Cria baixada? (não entra no rebanho)">
            <select className="mob-input" value={criaBaixada ? "Sim" : "Não"} disabled={tipoParto === "Natimorto"} onChange={(e) => setCriaBaixada(e.target.value === "Sim")}>
              <option>Não</option><option>Sim</option>
            </select>
            {tipoParto === "Natimorto" && <p style={{ fontSize: "0.72rem", color: "var(--mob-muted)", marginTop: "0.2rem" }}>Automático — natimorto.</p>}
          </MobCampo>

          {gemelar && (
            <>
              <div className="mob-secao" style={{ fontSize: "0.85rem" }}>2ª cria</div>
              <MobCampo label="Sexo da 2ª cria">
                <BotoesEscolha
                  opcoes={[{ valor: "F", label: "Fêmea" }, { valor: "M", label: "Macho" }]}
                  valor={cria2Sexo} onChange={setCria2Sexo}
                />
              </MobCampo>
              <MobCampo label="Número da 2ª cria">
                <input className="mob-input" value={cria2Numero} onChange={(e) => setCria2Numero(e.target.value)} placeholder="ex.: 4522" />
              </MobCampo>
              <MobCampo label="2ª cria baixada?">
                <select className="mob-input" value={cria2Baixada ? "Sim" : "Não"} disabled={tipoParto === "Natimorto"} onChange={(e) => setCria2Baixada(e.target.value === "Sim")}>
                  <option>Não</option><option>Sim</option>
                </select>
              </MobCampo>
            </>
          )}

          <button type="button" className="mob-btn-2" onClick={() => setVerColostro((v) => !v)} style={{ justifyContent: "space-between", marginBottom: "0.9rem" }}>
            <span>Colostragem e IgG da cria (opcional)</span>
            <span aria-hidden style={{ fontWeight: 800 }}>{verColostro ? "−" : "+"}</span>
          </button>
          {verColostro && (
            <div style={{ marginBottom: "0.4rem" }}>
              <div className="mob-secao" style={{ fontSize: "0.8rem" }}>Colostragem</div>
              <MobCampo label="Hora do parto"><input type="time" className="mob-input" value={horaParto} onChange={(e) => setHoraParto(e.target.value)} /></MobCampo>
              <MobCampo label="Hora do colostro"><input type="time" className="mob-input" value={horaColostro} onChange={(e) => setHoraColostro(e.target.value)} /></MobCampo>
              <MobCampo label="Peso ao nascer (kg)">
                <input type="number" step="0.1" inputMode="decimal" className="mob-input" value={pesoNascer} onChange={(e) => setPesoNascer(e.target.value)} placeholder="ex.: 38" />
              </MobCampo>
              <MobCampo label="Tomou colostro?">
                <BotoesEscolha opcoes={[{ valor: "Sim", label: "Sim" }, { valor: "Não", label: "Não" }]} valor={tomouColostro} onChange={setTomouColostro} />
              </MobCampo>
              <MobCampo label="Quantidade de colostro (litros)">
                <select className="mob-input" value={litrosColostro} onChange={(e) => setLitrosColostro(e.target.value)}>
                  <option value="">Selecione…</option>
                  {LITROS_COLOSTRO.map((l) => <option key={l} value={l}>{l} L</option>)}
                </select>
              </MobCampo>
              <MobCampo label="Brix do colostro (%)">
                <select className="mob-input" value={brixColostro} onChange={(e) => setBrixColostro(e.target.value)}>
                  <option value="">Selecione…</option>
                  {BRIX_COLOSTRO_OPCOES.map((b) => <option key={b} value={b}>{b}%</option>)}
                </select>
                {clsColostro && <p style={{ fontSize: "0.78rem", marginTop: "0.3rem", color: clsColostro.cor, fontWeight: 700 }}>{clsColostro.txt}</p>}
              </MobCampo>

              <div className="mob-secao" style={{ fontSize: "0.8rem" }}>Exame de sangue (IgG)</div>
              <MobCampo label="Brix do soro (%)">
                <select className="mob-input" value={brixSoro} onChange={(e) => setBrixSoro(e.target.value)}>
                  <option value="">Selecione…</option>
                  {BRIX_SORO_OPCOES.map((v) => <option key={v} value={v}>{v.replace(".", ",")}%</option>)}
                </select>
                {clsSoro && <p style={{ fontSize: "0.78rem", marginTop: "0.3rem", color: clsSoro.cor, fontWeight: 700 }}>{clsSoro.txt}</p>}
              </MobCampo>
              <MobCampo label="Proteína sérica (g/dL)">
                <input type="number" step="0.1" inputMode="decimal" className="mob-input" value={proteinaSerica} onChange={(e) => setProteinaSerica(e.target.value)} placeholder="ex.: 6,0" />
              </MobCampo>
              <label style={checkboxStyle}>
                <input type="checkbox" checked={apenasColostroPo} onChange={(e) => setApenasColostroPo(e.target.checked)} /> Só colostro em pó (sem colostro materno)
              </label>
            </div>
          )}
        </>
      )}

      <button className="mob-btn" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
      {avisosLote.map((a, i) => <MobAviso key={i} tipo={a.tipo}>{a.msg}</MobAviso>)}

      {sugestaoAtual && (
        <MobConfirmModal
          titulo={sugestaoAtual.tipo === "mae" ? "Mover a mãe de lote?" : "Alocar a cria em um lote?"}
          onCancelar={cancelarSugestaoAtual}
          onConfirmar={confirmarSugestaoAtual}
          confirmando={movendo}
          confirmarDesabilitado={!!sugestaoAtual.semSugestao && !loteEscolhido}
          textoCancelar={sugestaoAtual.semSugestao ? "Não mover" : "Cancelar"}
        >
          {sugestaoAtual.semSugestao ? (
            <>
              {sugestaoAtual.tipo === "mae"
                ? <>A matriz <strong>{sugestaoAtual.numero}</strong> pariu agora, mas nenhum lote tem esse perfil cadastrado.</>
                : <>A cria <strong>{sugestaoAtual.numero}</strong> ainda não tem lote e nenhum lote tem esse perfil cadastrado.</>}
              {" "}Para qual lote quer mandar?
              <select className="mob-input" aria-label="Lote de destino" value={loteEscolhido} onChange={(e) => setLoteEscolhido(e.target.value)} style={{ marginTop: "0.6rem" }}>
                <option value="">Escolha o lote…</option>
                {lotesCadastro.map((l) => <option key={l.codigo} value={l.codigo}>{l.rotulo}</option>)}
              </select>
            </>
          ) : sugestaoAtual.tipo === "mae"
            ? <>A matriz <strong>{sugestaoAtual.numero}</strong> pariu agora — mover para o lote <strong>{sugestaoAtual.rotulo}</strong>?</>
            : <>A cria <strong>{sugestaoAtual.numero}</strong> ainda não tem lote — alocar no lote <strong>{sugestaoAtual.rotulo}</strong>?</>}
        </MobConfirmModal>
      )}

      {abortoPendente && (
        <MobConfirmModal
          titulo="Perda de prenhez (aborto)"
          onCancelar={() => concluirAborto(false)}
          onConfirmar={() => concluirAborto(true)}
          confirmando={salvandoAborto}
          textoCancelar="Não, só aborto"
          textoConfirmar="Sim, abrir lactação"
        >
          A matriz <strong>{matriz}</strong> voltará ao status vazio, em observação. Deseja abrir lactação para ela?
        </MobConfirmModal>
      )}
    </>
  );
}

// Lançar › Protocolos › IATF (FormProtocolos) abre este MESMO componente — duas portas, uma implementação.
export { ProtocoloIatf };
