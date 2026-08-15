"use client";
import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { fetchAgendaVeterinario, fetchUltimoDiagnostico, salvarDiagnostico, LISTAS_AGENDA_VETERINARIO } from "@/lib/api";
import type { AgendaVetResposta } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, codigoGrupo } from "@/components/lancamentos/comumForms";
import { PopupVinculoFinanceiro, type OrigemPopupVinculo } from "@/components/lancamentos/PopupVinculoFinanceiro";
import { PopupAborto } from "@/components/lancamentos/PopupAborto";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";

const fmtDiaBr = (iso: string | null | undefined) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");

// Resumo do último diagnóstico da matriz selecionada — toque, retoque
// (reconfirmação) ou perda de prenhez, o que tiver acontecido por último.
function resumoUltimoDiagnostico(s: any): string {
  if (!s) return "Sem diagnóstico anterior registrado.";
  if (s.data_perda_prenhez) {
    const motivo = s.motivo_perda_prenhez === "aborto" ? "Aborto" : s.motivo_perda_prenhez === "natimorto" ? "Natimorto" : "Perda de prenhez";
    return `Última perda de prenhez: ${motivo}, em ${fmtDiaBr(s.data_perda_prenhez)}.`;
  }
  if (s.data_reconfirmacao) {
    return `Último diagnóstico: retoque (reconfirmação) em ${fmtDiaBr(s.data_reconfirmacao)} — resultado ${s.diagnostico_reconfirmacao || "—"}.`;
  }
  if (s.data_diagnostico) {
    return `Último diagnóstico: toque em ${fmtDiaBr(s.data_diagnostico)} — resultado ${s.diagnostico || "—"}.`;
  }
  return "Sem diagnóstico anterior registrado.";
}

export function FormDiagnostico({ animais, ultServico }: { animais: AnimalRow[]; ultServico: Record<string, string> }) {
  const { porNumero, rotuloDe } = useEstadosReprodutivos();
  // Lista as matrizes servidas (inseminadas ou prenhes a reconfirmar) — estado ao vivo.
  // Enquanto o estado ao vivo não chegou (ou a requisição falhou) cai no texto do
  // CSV: melhor um filtro desatualizado do que um formulário sem nenhum animal.
  const servidas = useMemo(() => {
    if (!porNumero.size) return animais.filter((a) => a.sit_rep === "Ins." || a.sit_rep === "Ges.");
    return animais.filter((a) => {
      const estado = porNumero.get(a.numero)?.estado;
      return estado === "inseminada" || estado === "gestante";
    });
  }, [animais, porNumero]);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const toggle = (n: string) => setSelecionados((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });

  // Animal(is), lote(s) ou Agenda do veterinário — dentro de lote/agenda, pode
  // escolher mais de um; a lista de animais mostrada é sempre a das servidas
  // dentro do(s) lote(s)/categoria(s) escolhido(s).
  const [vinculo, setVinculo] = useState<"animal" | "lote" | "agenda">("animal");
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const codigosLotesServidas = useMemo(
    () => Array.from(new Set(servidas.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [servidas]
  );
  const animaisDoLote = useMemo(() => {
    const cods = new Set(lotesSelecionados);
    return servidas.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [servidas, lotesSelecionados]);
  // Ao escolher lote(s), começa com todas as servidas do(s) lote(s) marcadas;
  // a janela suspensa abaixo permite desmarcar animal a animal.
  const [selLote, setSelLote] = useState<Set<string>>(new Set());
  const toggleLote = (n: string) => setSelLote((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelLote(new Set(animaisDoLote.map((a) => a.numero)));
  }, [lotesSelecionados.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps

  // Agenda do veterinário: busca as listas sob demanda (1ª vez que o modo é
  // aberto) e deixa marcar uma ou mais categorias — a lista de animais é a
  // exata que aparece na agenda, com a janela suspensa permitindo ajustar.
  const [agendaVet, setAgendaVet] = useState<AgendaVetResposta | null>(null);
  const [agendaCarregando, setAgendaCarregando] = useState(false);
  const [categoriasAgenda, setCategoriasAgenda] = useState<string[]>([]);
  useEffect(() => {
    if (vinculo === "agenda" && !agendaVet && !agendaCarregando) {
      setAgendaCarregando(true);
      fetchAgendaVeterinario().then(setAgendaVet).catch(() => {}).finally(() => setAgendaCarregando(false));
    }
  }, [vinculo, agendaVet, agendaCarregando]);
  const numerosDaAgenda = useMemo(() => {
    if (!agendaVet) return new Set<string>();
    const s = new Set<string>();
    categoriasAgenda.forEach((cat) => (agendaVet.listas[cat] || []).forEach((item) => s.add(item.numero_matriz)));
    return s;
  }, [agendaVet, categoriasAgenda]);
  const animaisDaAgenda = useMemo(() => {
    const nums = numerosDaAgenda;
    return animais.filter((a) => nums.has(a.numero));
  }, [animais, numerosDaAgenda]);
  const [selAgenda, setSelAgenda] = useState<Set<string>>(new Set());
  const toggleAgenda = (n: string) => setSelAgenda((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelAgenda(new Set(animaisDaAgenda.map((a) => a.numero)));
  }, [Array.from(numerosDaAgenda).sort().join("|")]); // eslint-disable-line react-hooks/exhaustive-deps

  const numerosAlvo = useMemo(
    () => (vinculo === "lote" ? selLote : vinculo === "agenda" ? selAgenda : selecionados),
    [vinculo, selLote, selAgenda, selecionados]
  );

  // Ao selecionar exatamente uma matriz, mostra o resumo do diagnóstico
  // anterior dela (data, resultado e se foi toque/retoque/perda) — em seleção
  // múltipla (lote/agenda) não há um único "último diagnóstico" para mostrar.
  const [numeroUltimo, setNumeroUltimo] = useState<string | null>(null);
  const [ultimoServicoAnimal, setUltimoServicoAnimal] = useState<any | null>(null);
  useEffect(() => {
    if (numerosAlvo.size !== 1) { setNumeroUltimo(null); setUltimoServicoAnimal(null); return; }
    const numero = Array.from(numerosAlvo)[0];
    setNumeroUltimo(numero);
    fetchUltimoDiagnostico(numero).then(setUltimoServicoAnimal).catch(() => setUltimoServicoAnimal(null));
  }, [Array.from(numerosAlvo).sort().join("|")]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fila de popups de aborto — o backend detecta quando o lançamento é o 3º
  // diagnóstico sobre a mesma prenhez (toque + retoque já confirmados) e
  // devolve aborto_detectado: true em vez de sobrescrever o toque anterior.
  const [abortosPendentes, setAbortosPendentes] = useState<string[]>([]);

  const [data, setData] = useState("");
  const [metodo, setMetodo] = useState("");
  const [resultado, setResultado] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  // Popup de vínculo financeiro — a data do diagnóstico coincide com a data
  // da visita reprodutiva/D0 do protocolo (ver PopupVinculoFinanceiro).
  const [popupOrigem, setPopupOrigem] = useState<OrigemPopupVinculo | null>(null);
  // Snapshot do que foi salvo — usado só se o usuário clicar "Cancelar" no
  // popup, pra restaurar a seleção/data/resultado e poder editar e reenviar.
  const [dadosParaCancelar, setDadosParaCancelar] = useState<{ numeros: Set<string>; data: string; metodo: string; resultado: string } | null>(null);

  function cancelarDiagnostico() {
    if (dadosParaCancelar) {
      setVinculo("animal");
      setSelecionados(dadosParaCancelar.numeros);
      setLotesSelecionados([]);
      setCategoriasAgenda([]);
      setData(dadosParaCancelar.data);
      setMetodo(dadosParaCancelar.metodo);
      setResultado(dadosParaCancelar.resultado);
    }
    setSucesso(null);
    setErro("Diagnóstico cancelado — ajuste os dados e salve novamente.");
    setPopupOrigem(null);
    setDadosParaCancelar(null);
  }

  // Animais selecionados com menos de 30 dias desde a última inseminação/cobertura.
  const animaisComAviso = useMemo(() => {
    if (!data) return [];
    return Array.from(numerosAlvo).filter((n) => {
      const us = ultServico[n];
      if (!us) return false;
      const dias = (new Date(data + "T00:00:00").getTime() - new Date(us + "T00:00:00").getTime()) / 86400000;
      return dias >= 0 && dias < 30;
    });
  }, [numerosAlvo, data, ultServico]);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!numerosAlvo.size || !data || !resultado) { setErro("Selecione ao menos uma matriz, a data e o resultado do diagnóstico."); return; }
    setSalvando(true);
    // Loop por animal: registra quais salvaram e quais falharam, para não perder
    // o trabalho já feito nem a seleção dos que precisam de nova tentativa.
    const salvos: string[] = [];
    const falhados: string[] = [];
    const servicoIds: number[] = [];
    // Animais em que o backend detectou o 3º lançamento sobre a mesma
    // prenhez (toque + retoque já confirmados) — não é um novo toque, é
    // interpretado como aborto (ver registrar_diagnostico no backend).
    const abortos: string[] = [];
    // Guardados para restaurar a tela caso o usuário cancele no popup de
    // vínculo financeiro (ver onCancelarDiagnostico) — o resto do fluxo já
    // limpa esses campos assim que salva com sucesso.
    const numerosSalvos = new Set(numerosAlvo);
    const dataSalva = data;
    const metodoSalvo = metodo;
    const resultadoSalvo = resultado;
    try {
      for (const numero of numerosAlvo) {
        try {
          const r = await salvarDiagnostico({ numero_matriz: numero, data_diagnostico: data, resultado: resultado as any, metodo: metodo || undefined });
          if (r?.aborto_detectado) {
            abortos.push(numero);
          } else if (r?.id) {
            servicoIds.push(r.id);
          }
          salvos.push(numero);
        } catch {
          falhados.push(numero);
        }
      }
      if (abortos.length) {
        setAbortosPendentes((p) => [...p, ...abortos]);
      } else if (!falhados.length && servicoIds.length) {
        setPopupOrigem({ tipo: "servico", ids: servicoIds, produto: "Diagnóstico de gestação — visita reprodutiva", data, responsavel: null });
        setDadosParaCancelar({ numeros: numerosSalvos, data: dataSalva, metodo: metodoSalvo, resultado: resultadoSalvo });
      }
      if (falhados.length) {
        // Sucesso parcial: passa para seleção individual só com quem falhou, para reenviar.
        setVinculo("animal"); setLotesSelecionados([]); setCategoriasAgenda([]); setSelecionados(new Set(falhados));
        if (salvos.length) {
          setSucesso(`Salvos: ${salvos.length}.`);
          setErro(`Falharam: ${falhados.join(", ")} — tente novamente só esses.`);
        } else {
          setErro(`Nenhum diagnóstico salvo. Falharam: ${falhados.join(", ")} — tente novamente.`);
        }
      } else {
        setSucesso(
          abortos.length
            ? `${abortos.length} animal(is) já tinham prenhez confirmada duas vezes (toque + retoque) — lançamento registrado como aborto (perda de prenhez): ${abortos.join(", ")}.`
            : resultado === "retoque"
            ? `Diagnóstico salvo para ${salvos.length} animal(is). Entraram na agenda para retoque.`
            : `Diagnóstico salvo para ${salvos.length} animal(is).`
        );
        setSelecionados(new Set()); setLotesSelecionados([]); setCategoriasAgenda([]); setData(""); setMetodo(""); setResultado("");
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar diagnóstico");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <Campo label="Matriz / novilha (servidas) — animal(is), lote(s) ou Agenda do veterinário" full>
        <TabBar<"animal" | "lote" | "agenda">
          abas={[
            { id: "animal", label: "Animal(is)", title: "Selecionar matrizes/novilhas individualmente" },
            { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes — mostra as servidas de cada lote escolhido" },
            { id: "agenda", label: "Agenda do veterinário", title: "Selecionar a partir das listas da Agenda do veterinário — mesma classificação usada no roteiro do dia" },
          ]}
          ativa={vinculo}
          onChange={setVinculo}
        />
        {vinculo === "animal" && (
          <AnimalPickerModal
            animais={servidas} selecionados={selecionados} onToggle={toggle}
            titulo="Escolher matriz / novilha servida"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
              { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
              { header: "Última IA/cobertura", render: (a) => ultServico[a.numero] ? new Date(ultServico[a.numero] + "T00:00:00").toLocaleDateString("pt-BR") : "—" },
            ]}
          />
        )}
        {vinculo === "lote" && (
          <div style={{ marginTop: "0.5rem" }}>
            <LotePicker
              opcoes={opcoesLoteDeAnimais(servidas, codigosLotesServidas)}
              selecionados={lotesSelecionados}
              onChange={setLotesSelecionados}
              placeholder="Selecionar lote(s)…"
            />
            {lotesSelecionados.length > 0 && (
              <div style={{ marginTop: "0.6rem" }}>
                <AnimalPickerModal
                  animais={animaisDoLote} selecionados={selLote} onToggle={toggleLote}
                  titulo="Ajustar servidas do(s) lote(s) selecionado(s)"
                  placeholder="Ajustar servidas do(s) lote(s)…"
                  colunas={[
                    { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                    { header: "Lote", render: (a) => a.grupo_primario || "—" },
                    { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
                    { header: "Última IA/cobertura", render: (a) => ultServico[a.numero] ? new Date(ultServico[a.numero] + "T00:00:00").toLocaleDateString("pt-BR") : "—" },
                  ]}
                />
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  {selLote.size} de {animaisDoLote.length} servida(s) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir alguma.
                </p>
              </div>
            )}
          </div>
        )}
        {vinculo === "agenda" && (
          <div style={{ marginTop: "0.5rem" }}>
            {agendaCarregando && <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Carregando agenda do veterinário…</p>}
            {agendaVet && (
              <>
                <div className="flex flex-wrap gap-2">
                  {LISTAS_AGENDA_VETERINARIO.filter((l) => (agendaVet.totais[l.chave] || 0) > 0).map((l) => {
                    const ativa = categoriasAgenda.includes(l.chave);
                    return (
                      <button key={l.chave} type="button"
                        onClick={() => setCategoriasAgenda((p) => ativa ? p.filter((c) => c !== l.chave) : [...p, l.chave])}
                        style={{
                          fontSize: "0.75rem", padding: "0.3rem 0.65rem", borderRadius: "999px", cursor: "pointer",
                          border: "1px solid " + (ativa ? "var(--dourado)" : "var(--border)"),
                          background: ativa ? "var(--dourado)" : "transparent",
                          color: ativa ? "#1a1a1a" : "var(--text-muted)", fontWeight: ativa ? 700 : 400,
                        }}>
                        {l.rotulo} ({agendaVet.totais[l.chave]})
                      </button>
                    );
                  })}
                </div>
                {categoriasAgenda.length > 0 && (
                  <div style={{ marginTop: "0.6rem" }}>
                    <AnimalPickerModal
                      animais={animaisDaAgenda} selecionados={selAgenda} onToggle={toggleAgenda}
                      titulo="Ajustar animais da(s) categoria(s) selecionada(s)"
                      placeholder="Ajustar animais da agenda do veterinário…"
                      colunas={[
                        { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                        { header: "Lote", render: (a) => a.grupo_primario || "—" },
                        { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
                        { header: "Última IA/cobertura", render: (a) => ultServico[a.numero] ? new Date(ultServico[a.numero] + "T00:00:00").toLocaleDateString("pt-BR") : "—" },
                      ]}
                    />
                    <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                      {selAgenda.size} de {animaisDaAgenda.length} animal(is) na(s) categoria(s) selecionada(s) — desmarque na janela acima para excluir algum.
                    </p>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </Campo>

      {numeroUltimo && (
        <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
          <strong>{numeroUltimo}:</strong> {resumoUltimoDiagnostico(ultimoServicoAnimal)}
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <Campo label="Data do diagnóstico"><input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></Campo>
        <Campo label="Método">
          <select style={inputStyle} value={metodo} onChange={(e) => setMetodo(e.target.value)}>
            <option value="" disabled>Selecione…</option><option>Palpação</option><option>Ultrassom</option><option>Cio de repasse</option>
          </select>
        </Campo>
        <Campo label="Resultado" full>
          <select style={inputStyle} value={resultado} onChange={(e) => setResultado(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            <option value="retoque">Positivo — marcar para retoque (segue em observação para reconfirmar)</option>
            <option value="reconfirmada">Positivo — reconfirmada (prenhez confirmada)</option>
            <option value="negativo">Negativo (vazia)</option>
            <option value="indefinido">Indefinido (inconclusivo — reavaliar)</option>
          </select>
        </Campo>
      </div>
      {metodo === "Cio de repasse" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
          <strong>Cio de repasse:</strong> a vaca retornou ao cio após a inseminação. Detecção esperada — scratch (adesivo) aplicado por volta de 14 dias após a última IA/monta e cio natural observado entre 15 e 28 dias após o scratch.
        </p>
      )}

      {animaisComAviso.length > 0 && (
        <div className="mt-3" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", background: "rgba(217,119,6,0.12)", border: "1px solid var(--amber)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem" }}>
          <AlertTriangle size={16} style={{ color: "var(--amber)", marginTop: "0.1rem" }} />
          <span style={{ fontSize: "0.8rem" }}>
            {animaisComAviso.length} animal(is) com menos de 30 dias da última inseminação/cobertura: {animaisComAviso.join(", ")}. Deseja confirmar mesmo assim?
          </span>
        </div>
      )}
      {resultado === "negativo" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Ao confirmar, os animais ficam como <strong>vazia</strong> e serão colocados para observação na próxima visita reprodutiva.
        </p>
      )}
      {resultado === "retoque" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Os animais entram na <strong>agenda para retoque</strong>, no dia da próxima visita reprodutiva.
        </p>
      )}
      {resultado === "indefinido" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Resultado <strong>inconclusivo</strong> — a matriz <strong>não</strong> vira vazia; segue para nova avaliação.
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>

      {popupOrigem && (
        <PopupVinculoFinanceiro
          origem={popupOrigem}
          onFechar={() => { setPopupOrigem(null); setDadosParaCancelar(null); }}
          onCancelar={cancelarDiagnostico}
        />
      )}

      {abortosPendentes.length > 0 && (
        <PopupAborto
          numeroMatriz={abortosPendentes[0]}
          onFechar={() => setAbortosPendentes((p) => p.slice(1))}
        />
      )}
    </>
  );
}
