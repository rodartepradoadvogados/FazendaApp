"use client";
import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import {
  criarServicoLote, fetchSemenDisponivel, fetchProtocolosIatfAtivos, fetchLancamentosIatf,
  fetchSugestaoAcasalamento, fetchTouros,
} from "@/lib/api";
import type { SemenDisponivel, Touro, SugestaoAcasalamento } from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { AnimalRow } from "@/components/AnimalModal";
import { TouroPicker, type TouroPickerItem } from "@/components/TouroPicker";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { TabBar } from "@/components/ui";
import { Campo, inputStyle, lbl, nota, codigoGrupo } from "@/components/lancamentos/comumForms";
import { IDADE_MIN_SERVICO } from "@/components/lancamentos/_shared";
import { useEstadosReprodutivos } from "@/lib/estadoReprodutivo";

const CAT_TOURO = [
  { id: "convencional" as const, label: "Convencional" },
  { id: "sexado" as const, label: "Sexado" },
  { id: "fazenda" as const, label: "Touro da fazenda" },
];

export function FormInseminacao({ animais }: { animais: AnimalRow[] }) {
  const { rotuloDe } = useEstadosReprodutivos();
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [dataServico, setDataServico] = useState("");
  const [tipo, setTipo] = useState<"cio_natural" | "iatf" | "monta_natural">("cio_natural");
  const [categoria, setCategoria] = useState<"convencional" | "sexado" | "fazenda">("convencional");
  const [touro, setTouro] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const { nomes: nomesResponsaveis } = usePessoasAtivas();
  // IATF: vincular a um lançamento já existente + auto-lançar retroativo.
  const [protocoloId, setProtocoloId] = useState("");
  const [autoLancar, setAutoLancar] = useState(false);
  const [lancamentos, setLancamentos] = useState<{ lancamento_id: number; nome_protocolo: string; data_d0: string }[]>([]);
  const [semen, setSemen] = useState<SemenDisponivel | null>(null);
  // Origem da seleção: avulsa (qualquer matriz apta) ou vinda de um protocolo
  // IATF vigente — nesse caso a lista se restringe às matrizes cujo
  // protocolo ainda não teve inseminação lançada (`pronta_para_inseminar`),
  // sem exigir que a etapa de hoje seja a de inseminação em si.
  const [origemSelecao, setOrigemSelecao] = useState<"avulsa" | "protocolo">("avulsa");
  const [protocolosAtivos, setProtocolosAtivos] = useState<{ lancamento_id: number; nome_protocolo: string; data_d0: string; animais: { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null; pronta_para_inseminar?: boolean }[] }[]>([]);
  const carregarProtocolosAtivos = () => fetchProtocolosIatfAtivos().then(setProtocolosAtivos).catch(() => setProtocolosAtivos([]));
  useEffect(() => { carregarProtocolosAtivos(); }, []);
  // "Protocolo de IATF atual" = protocolo ainda vigente (nenhum Serviço
  // lançado depois do D0) — não precisa estar na etapa D11 hoje: a
  // inseminação pode ser lançada a posteriori, depois de o hormônio já ter
  // sido aplicado há dias.
  const protocolosD11 = useMemo(
    () => protocolosAtivos
      .map((p) => ({ ...p, animaisD11: p.animais.filter((a) => a.pronta_para_inseminar) }))
      .filter((p) => p.animaisD11.length > 0),
    [protocolosAtivos]
  );
  const mapaProtocoloPorAnimal = useMemo(() => {
    const m = new Map<string, string>();
    protocolosD11.forEach((p) => p.animaisD11.forEach((a) => m.set(a.numero_matriz, p.nome_protocolo)));
    return m;
  }, [protocolosD11]);
  const animaisProtocolo = useMemo(() => animais.filter((a) => mapaProtocoloPorAnimal.has(a.numero)), [animais, mapaProtocoloPorAnimal]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  // "Incluir touros sem estoque": troca a fonte da seleção de touro pelo
  // catálogo NAAB completo, em vez de restringir aos que têm dose no estoque.
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [catalogoTouros, setCatalogoTouros] = useState<Touro[]>([]);
  useEffect(() => {
    if (incluirSemEstoque && !catalogoTouros.length) fetchTouros().then(setCatalogoTouros).catch(() => {});
  }, [incluirSemEstoque, catalogoTouros.length]);
  const itensCatalogoTouros: TouroPickerItem[] = useMemo(
    () => catalogoTouros.map((t) => ({ naab: t.naab, nome: t.nome || t.naab, central: t.central, raca: t.raca, tpi: t.tpi })),
    [catalogoTouros]
  );

  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleTodos = () => setSel((p) => (p.size === animais.length && animais.length ? new Set() : new Set(animais.map((a) => a.numero))));

  // Inseminação avulsa: animal(is) ou lote(s) — dentro de lote, pode escolher
  // mais de um; o protocolo IATF em andamento continua só por animal (D11).
  const [vinculoInsem, setVinculoInsem] = useState<"animal" | "lote">("animal");
  const [lotesSelecionadosInsem, setLotesSelecionadosInsem] = useState<string[]>([]);
  const codigosLotesAptas = useMemo(
    () => Array.from(new Set(animais.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [animais]
  );
  const animaisDoLoteInsem = useMemo(() => {
    const cods = new Set(lotesSelecionadosInsem);
    return animais.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [animais, lotesSelecionadosInsem]);
  // Ao escolher lote(s), começa com todas as aptas do(s) lote(s) marcadas;
  // a janela suspensa abaixo permite desmarcar animal a animal.
  const [selLoteInsem, setSelLoteInsem] = useState<Set<string>>(new Set());
  const toggleLoteInsem = (n: string) => setSelLoteInsem((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelLoteInsem(new Set(animaisDoLoteInsem.map((a) => a.numero)));
  }, [lotesSelecionadosInsem.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  const alvoFinal = useMemo(
    () => (origemSelecao === "avulsa" && vinculoInsem === "lote" ? selLoteInsem : sel),
    [origemSelecao, vinculoInsem, selLoteInsem, sel]
  );

  // Acasalamento direcionado: só faz sentido sugerir touro para UMA matriz por
  // vez (seleção em lote pula a sugestão, para não complicar a tela) — busca
  // assim que uma única matriz estiver selecionada. Falha de forma discreta
  // (ex.: animal sem genealogia cadastrada) sem travar o resto do formulário.
  const [sugestaoAcasalamento, setSugestaoAcasalamento] = useState<SugestaoAcasalamento | null>(null);
  const [carregandoSugestao, setCarregandoSugestao] = useState(false);
  const [erroSugestao, setErroSugestao] = useState<string | null>(null);
  useEffect(() => {
    if (alvoFinal.size !== 1) { setSugestaoAcasalamento(null); setErroSugestao(null); return; }
    const numeroMatriz = Array.from(alvoFinal)[0];
    let cancelado = false;
    setCarregandoSugestao(true); setErroSugestao(null);
    fetchSugestaoAcasalamento(numeroMatriz)
      .then((r) => { if (!cancelado) setSugestaoAcasalamento(r); })
      .catch((e) => {
        if (!cancelado) { setSugestaoAcasalamento(null); setErroSugestao(e?.message || "Não foi possível calcular a sugestão de touro para esta matriz."); }
      })
      .finally(() => { if (!cancelado) setCarregandoSugestao(false); });
    return () => { cancelado = true; };
  }, [alvoFinal]);

  useEffect(() => {
    fetchSemenDisponivel().then(setSemen).catch(() => setSemen(null));
    fetchLancamentosIatf().then(setLancamentos).catch(() => setLancamentos([]));
  }, []);

  // Vindo da Agenda (link "Ir para Inseminação" do D11): pré-seleciona matriz + IATF.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const numeroMatriz = qs.get("numero_matriz");
    if (numeroMatriz) setSel(new Set([numeroMatriz]));
    if (qs.get("protocolo")) { setTipo("iatf"); setOrigemSelecao("protocolo"); }
  }, []);

  // Na origem "protocolo", quando a seleção pertence a um único lançamento
  // IATF, vincula automaticamente — evita o usuário ter que escolher à toa.
  useEffect(() => {
    if (origemSelecao !== "protocolo") return;
    const ids = new Set<number>();
    sel.forEach((n) => {
      const p = protocolosD11.find((pp) => pp.animaisD11.some((a) => a.numero_matriz === n));
      if (p) ids.add(p.lancamento_id);
    });
    setProtocoloId(ids.size === 1 ? String([...ids][0]) : "");
  }, [sel, origemSelecao, protocolosD11]);

  // Touro da fazenda ⇒ sempre monta natural.
  useEffect(() => { if (categoria === "fazenda") setTipo("monta_natural"); }, [categoria]);

  const tourosDaCategoria = useMemo(
    () => (semen?.touros || []).filter((t) => t.tipo === categoria),
    [semen, categoria]
  );

  async function salvar() {
    setErro(null); setSucesso(null);
    const alvo = Array.from(alvoFinal);
    if (!alvo.length) { setErro("Selecione ao menos uma matriz."); return; }
    if (!dataServico) { setErro("Informe a data da inseminação."); return; }
    setSalvando(true);
    try {
      const r = await criarServicoLote({
        animais: alvo, data_servico: dataServico, tipo,
        reprodutor: touro || undefined, responsavel: responsavel || undefined,
        protocolo_lancamento_id: tipo === "iatf" && protocoloId ? Number(protocoloId) : null,
        auto_lancar_iatf: tipo === "iatf" ? autoLancar : false,
        tipo_semen: categoria === "fazenda" ? null : categoria,
      });
      if (r.incompativeis.length) {
        setVinculoInsem("animal"); setLotesSelecionadosInsem([]); setSel(new Set(r.incompativeis));
        setErro(`${r.incompativeis.join(", ")} não estão em nenhum protocolo IATF. Vincule a um protocolo existente ou marque "lançar protocolo automaticamente (D0 retroativo)" e salve de novo.`);
        if (r.criados) setSucesso(`${r.criados} inseminação(ões) registrada(s).`);
      } else {
        setSucesso(`${r.criados} inseminação(ões) registrada(s)${tipo === "iatf" ? " (IATF)" : tipo === "monta_natural" ? " (monta natural)" : " (cio natural)"}.`);
        setSel(new Set()); setLotesSelecionadosInsem([]); setTouro("");
      }
      // Sem isso, o estoque de sêmen exibido (doses do touro) e a lista de
      // matrizes em protocolo IATF vigente ficavam presos no valor de quando
      // a tela abriu — cada dose baixada, ou cada matriz já inseminada,
      // continuava aparecendo disponível até a página ser recarregada.
      if (r.criados) {
        fetchSemenDisponivel().then(setSemen).catch(() => {});
        carregarProtocolosAtivos();
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao registrar inseminação");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      {semen && (semen.abaixo_minimo.convencional || semen.abaixo_minimo.sexado) && (
        <div className="mb-3" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", background: "rgba(220,38,38,0.1)", border: "1px solid var(--red)", borderRadius: 8, padding: "0.6rem 0.8rem" }}>
          <AlertTriangle size={16} style={{ color: "var(--red)", marginTop: "0.1rem" }} />
          <span style={{ fontSize: "0.8rem" }}>
            Estoque de sêmen abaixo do mínimo:{" "}
            {semen.abaixo_minimo.convencional && `convencional ${semen.totais.convencional}/${semen.minimos.convencional}`}
            {semen.abaixo_minimo.convencional && semen.abaixo_minimo.sexado && " · "}
            {semen.abaixo_minimo.sexado && `sexado ${semen.totais.sexado}/${semen.minimos.sexado}`}. Registre a compra na NF.
          </span>
        </div>
      )}

      <div className="mb-3">
        <label style={lbl}>Origem da inseminação</label>
        <TabBar<"avulsa" | "protocolo">
          abas={[
            { id: "avulsa", label: "Inseminação avulsa", title: "Escolher livremente entre as matrizes aptas" },
            { id: "protocolo", label: "Protocolo de IATF atual", title: "Mostrar as matrizes com protocolo IATF vigente — ainda sem inseminação lançada, não importa em qual etapa do hormônio está hoje" },
          ]}
          ativa={origemSelecao}
          onChange={(o) => { setOrigemSelecao(o); setSel(new Set()); setLotesSelecionadosInsem([]); setVinculoInsem("animal"); if (o === "protocolo") setTipo("iatf"); }}
        />
        {origemSelecao === "protocolo" && !animaisProtocolo.length && (
          <p style={{ ...nota, color: "var(--amber)" }}>Nenhuma matriz está em protocolo IATF vigente sem inseminação já lançada.</p>
        )}
      </div>

      <Campo label={origemSelecao === "protocolo" ? "Matrizes em protocolo IATF vigente — pode selecionar várias" : "Matriz / novilha (aptas) — animal(is) ou lote(s)"} full>
        {origemSelecao === "protocolo" ? (
          <AnimalPickerModal
            animais={animaisProtocolo}
            selecionados={sel} onToggle={toggle}
            titulo="Escolher matrizes em protocolo IATF vigente"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
              { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
              { header: "Protocolo", render: (a: AnimalRow) => mapaProtocoloPorAnimal.get(a.numero) || "—" },
            ]}
          />
        ) : (
          <>
            <TabBar<"animal" | "lote">
              abas={[
                { id: "animal", label: "Animal(is)", title: "Selecionar matrizes/novilhas individualmente" },
                { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes — mostra as aptas de cada lote escolhido" },
              ]}
              ativa={vinculoInsem}
              onChange={setVinculoInsem}
            />
            {vinculoInsem === "animal" ? (
              <AnimalPickerModal
                animais={animais}
                selecionados={sel} onToggle={toggle}
                titulo="Escolher matriz / novilha"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
                ]}
              />
            ) : (
              <div style={{ marginTop: "0.5rem" }}>
                <LotePicker
                  opcoes={opcoesLoteDeAnimais(animais, codigosLotesAptas)}
                  selecionados={lotesSelecionadosInsem}
                  onChange={setLotesSelecionadosInsem}
                  placeholder="Selecionar lote(s)…"
                />
                {lotesSelecionadosInsem.length > 0 && (
                  <div style={{ marginTop: "0.6rem" }}>
                    <AnimalPickerModal
                      animais={animaisDoLoteInsem} selecionados={selLoteInsem} onToggle={toggleLoteInsem}
                      titulo="Confirmar aptas do(s) lote(s) selecionado(s)"
                      placeholder="Confirmar aptas do(s) lote(s)…"
                      // Sem isso, o lote entrava inteiro por padrão e o
                      // usuário só via quem foi incluído se lembrasse de
                      // clicar aqui — a lista de animais do lote escolhido
                      // agora aparece sozinha, forçando a decisão explícita
                      // (todos, nenhum, ou alguns) antes de seguir.
                      abrirAoMudar={lotesSelecionadosInsem.join("|")}
                      colunas={[
                        { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                        { header: "Lote", render: (a) => a.grupo_primario || "—" },
                        { header: "Sit. rep.", render: (a) => rotuloDe(a.numero) },
                      ]}
                    />
                    <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                      {selLoteInsem.size} de {animaisDoLoteInsem.length} apta(s) no(s) lote(s) selecionado(s) — "Selecionar todos"/"Limpar seleção" ou desmarque uma a uma na janela acima.
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </Campo>

      {alvoFinal.size === 1 && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.82rem", fontWeight: 700, marginBottom: "0.4rem" }}>
            Acasalamento direcionado — sugestão de touro para {Array.from(alvoFinal)[0]}
          </p>
          {carregandoSugestao && <p style={nota}>Calculando sugestão…</p>}
          {!carregandoSugestao && erroSugestao && (
            <p style={{ ...nota, color: "var(--amber)" }}>{erroSugestao}</p>
          )}
          {!carregandoSugestao && sugestaoAcasalamento && (
            <>
              {/* Nota fixa, sempre visível: os 3 critérios usados na sugestão. */}
              <ul style={{ fontSize: "0.72rem", color: "var(--text-muted)", margin: "0 0 0.6rem", paddingLeft: "1.1rem" }}>
                {sugestaoAcasalamento.criterios.map((c, i) => <li key={i} style={{ marginBottom: 2 }}>{c}</li>)}
              </ul>
              {!sugestaoAcasalamento.sugestoes.length ? (
                <p style={nota}>Nenhum touro com sêmen em estoque disponível para sugerir.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                  {sugestaoAcasalamento.sugestoes.map((s) => (
                    <div
                      key={`${s.naab || ""}-${s.nome || ""}`}
                      onClick={() => setTouro(s.nome || "")}
                      className="row-clickable"
                      title="Clique para usar este touro na inseminação"
                      style={{
                        cursor: "pointer", borderRadius: 8, padding: "0.5rem 0.7rem",
                        border: `1px solid ${s.tem_ancestral_comum ? "var(--red)" : "var(--border)"}`,
                        background: s.tem_ancestral_comum ? "rgba(220,38,38,0.08)" : "var(--surface)",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.6rem" }}>
                        <span style={{ fontWeight: 700, fontSize: "0.82rem" }}>
                          {s.nome}{s.naab ? ` · ${s.naab}` : ""}
                        </span>
                        <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexShrink: 0, whiteSpace: "nowrap" }}>
                          {s.tpi != null ? `TPI ${s.tpi} · ` : ""}
                          {s.tipo === "fazenda" ? "monta natural" : `${s.doses ?? 0} dose(s)`}
                        </span>
                      </div>
                      <p style={{ fontSize: "0.74rem", color: s.tem_ancestral_comum ? "var(--red)" : "var(--text-muted)", margin: "0.25rem 0 0" }}>
                        {s.motivo}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {alvoFinal.size > 0 && (
        <div className="mt-3" style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", alignItems: "center" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", fontWeight: 600 }}>
            {alvoFinal.size} matriz(es) selecionada(s) para esta inseminação:
          </span>
          {Array.from(alvoFinal).sort().map((n) => (
            <span key={n} style={{
              fontSize: "0.76rem", background: "var(--surface-2)", border: "1px solid var(--border)",
              borderRadius: "999px", padding: "0.15rem 0.6rem", fontWeight: 600,
            }}>
              {n}
            </span>
          ))}
        </div>
      )}
      </div>

      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Data da inseminação"><input type="date" style={inputStyle} value={dataServico} onChange={(e) => setDataServico(e.target.value)} /></Campo>
        <Campo label="Categoria do touro / sêmen">
          <select style={inputStyle} value={categoria} onChange={(e) => { setCategoria(e.target.value as typeof categoria); setTouro(""); }}>
            {CAT_TOURO.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </Campo>
        <Campo label={`Touro (${categoria === "fazenda" ? "monta natural" : incluirSemEstoque ? "catálogo NAAB completo" : "em estoque"})`}>
          {!incluirSemEstoque ? (
            <select style={inputStyle} value={touro} onChange={(e) => setTouro(e.target.value)}>
              <option value="">Selecione…</option>
              {tourosDaCategoria.map((t) => <option key={t.nome} value={t.nome}>{t.nome}{t.tipo !== "fazenda" ? ` (${t.doses} doses)` : ""}</option>)}
            </select>
          ) : (
            <TouroPicker style={inputStyle} itens={itensCatalogoTouros} value={touro} placeholder="Buscar touro no catálogo NAAB..."
              onChangeTexto={setTouro} onSelecionar={(t) => setTouro(t.nome)} />
          )}
          {!incluirSemEstoque && !tourosDaCategoria.length && <p style={{ fontSize: "0.72rem", color: "var(--amber)", marginTop: 2 }}>Nenhum touro {categoria} em estoque.</p>}
          {categoria !== "fazenda" && (
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginTop: "0.4rem", fontSize: "0.76rem", color: "var(--text-muted)", cursor: "pointer" }}>
              <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => { setIncluirSemEstoque(e.target.checked); setTouro(""); }} />
              Incluir touros sem estoque (catálogo completo NAAB)
            </label>
          )}
        </Campo>
        <Campo label="Responsável / inseminador">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="">Selecione…</option>{nomesResponsaveis.map((r) => <option key={r}>{r}</option>)}</select>
        </Campo>
      </div>

      <div className="mt-3">
        <label style={lbl}>Tipo de cobertura</label>
        <TabBar<"cio_natural" | "iatf" | "monta_natural">
          abas={[
            { id: "cio_natural", label: "Cio natural", title: "Inseminação de cio natural (sem protocolo)" },
            { id: "iatf", label: "IATF", title: "Inseminação de um protocolo IATF" },
            { id: "monta_natural", label: "Monta natural", title: "Cobertura por touro (monta natural)" },
          ]}
          ativa={tipo}
          onChange={(t) => { if (categoria !== "fazenda" && origemSelecao !== "protocolo") setTipo(t); }}
        />
        {categoria === "fazenda" && <p style={nota}>Touro da fazenda selecionado — registrado como <strong>monta natural</strong>.</p>}
        {origemSelecao === "protocolo" && <p style={nota}>Origem "Protocolo de IATF atual" — sempre registrado como <strong>IATF</strong>.</p>}
      </div>

      {tipo === "iatf" && origemSelecao === "protocolo" && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.82rem" }}>
            {protocoloId
              ? <>Vinculado automaticamente ao protocolo <strong>{protocolosD11.find((p) => String(p.lancamento_id) === protocoloId)?.nome_protocolo}</strong>.</>
              : "Cada matriz será vinculada ao seu próprio protocolo IATF em andamento (detectado automaticamente)."}
          </p>
        </div>
      )}

      {tipo === "iatf" && origemSelecao === "avulsa" && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Campo label="Vincular ao protocolo IATF">
              <select style={inputStyle} value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
                <option value="">Automático (o protocolo pendente do animal)</option>
                {lancamentos.map((l) => <option key={l.lancamento_id} value={l.lancamento_id}>{l.nome_protocolo}</option>)}
              </select>
            </Campo>
            <Campo label="Se o animal não estiver em protocolo">
              <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", padding: "0.45rem 0" }}>
                <input type="checkbox" checked={autoLancar} onChange={(e) => setAutoLancar(e.target.checked)} /> Lançar protocolo automaticamente (D0 retroativo)
              </label>
            </Campo>
          </div>
          <p style={nota}>O protocolo automático conta o D0 para trás (data do serviço − 11 dias) e só registra o protocolo — não gera aplicação de hormônio.</p>
        </div>
      )}

      <p style={nota}>Matriz lista apenas fêmeas aptas (≥ {IDADE_MIN_SERVICO} meses).</p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
      </div>
      </div>
    </>
  );
}

