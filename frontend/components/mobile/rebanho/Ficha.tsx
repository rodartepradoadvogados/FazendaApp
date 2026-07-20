"use client";
// Tela REBANHO › aba "Ficha do Animal".
// Busca grande + lista completa de animais; ao tocar num animal abre a ficha
// completa (só leitura) numa sub-tela, com seções recolhíveis. Offline: ficha
// via cache por animal (chave "ficha_<numero>").
import { useEffect, useState } from "react";
import { fetchAnimais, fetchFichaAnimal, formatDate, registrarColostragem } from "@/lib/api";
import { fetchComCache, cacheEm } from "@/lib/offline";
import { MobCard, MobVoltar, MobLinha, MobCampo, MobAviso } from "@/components/mobile/ui";
import { estiloSexado } from "@/lib/constants";
import { BuscaAnimal, subtituloAnimal, type AnimalMob } from "./comum";

type Ficha = {
  animal: Record<string, unknown>;
  colostragem: Record<string, unknown> | null;
  compra: Record<string, unknown> | null;
  compras: Record<string, unknown>[];
  vendas: Record<string, unknown>[];
  gtas: string[];
  baixa: Record<string, unknown> | null;
  pai: { nome: string | null; naab: string | null } | null;
  previsao_parto: string | null;
  previsao_secagem: string | null;
} & Record<string, Record<string, unknown>[] | Record<string, unknown> | null>;

// Grupos de lançamentos (as chaves batem com o retorno de /animais/{n}/ficha).
type Campo = [chave: string, rotulo: string, data?: boolean];
const SECOES: { chave: string; titulo: string; campos: Campo[] }[] = [
  { chave: "movimentos_lote", titulo: "Movimentações de lote", campos: [["data_movimento", "Data", true], ["lote_origem", "De"], ["lote_destino", "Para"], ["motivo", "Motivo"]] },
  { chave: "partos", titulo: "Partos", campos: [["data_parto", "Data", true], ["ordem_parto", "Ordem"], ["tipo_parto", "Tipo"]] },
  { chave: "servicos", titulo: "Reprodução — serviço/IA", campos: [["data_servico", "Data", true], ["tipo_servico", "Tipo"], ["reprodutor", "Reprodutor"], ["tipo_semen", "Sêmen"], ["diagnostico", "Diagnóstico"], ["data_diagnostico", "Diagnosticado em", true]] },
  { chave: "protocolos_iatf", titulo: "Protocolo IATF", campos: [["dia", "Dia"], ["descricao", "Descrição"], ["data_prevista", "Prevista", true], ["realizada", "Feito"]] },
  { chave: "controles_leiteiros", titulo: "Controle leiteiro", campos: [["data_controle", "Data", true], ["producao_kg", "Produção (kg)"], ["del_no_controle", "DEL"]] },
  { chave: "pesagens_corporais", titulo: "Pesagens", campos: [["data_pesagem", "Data", true], ["peso_kg", "Peso (kg)"], ["del_dias", "DEL"]] },
  { chave: "qualidade_leite", titulo: "Qualidade do leite", campos: [["data_coleta", "Data", true], ["ccs", "CCS"], ["cbt", "CBT"]] },
  { chave: "aplicacoes_sanitarias", titulo: "Sanidade — aplicações", campos: [["data_aplicacao", "Data", true], ["produto", "Produto"], ["dose", "Dose"], ["unidade", "Un."]] },
  { chave: "protocolos_sanitarios", titulo: "Protocolos sanitários", campos: [["data_inicio", "Data", true], ["protocolo_nome", "Protocolo"], ["classificacao_mastite", "Mastite"]] },
  { chave: "secagens", titulo: "Secagens", campos: [["data_secagem", "Data", true], ["motivo", "Motivo"]] },
  { chave: "eventos_agenda", titulo: "Agenda — eventos", campos: [["data_evento", "Data", true], ["descricao", "Descrição"], ["categoria", "Categoria"]] },
  { chave: "exames_resultados", titulo: "Rastreabilidade — Exames", campos: [["data_exame", "Data", true], ["evento_sanitario_nome", "Exame"], ["resultado", "Resultado"]] },
  { chave: "ocorrencias_clinicas", titulo: "Rastreabilidade — Doenças", campos: [["data_ocorrencia", "Data", true], ["doenca", "Doença"], ["observacao", "Observação"]] },
];

function mostrarValor(v: unknown, data?: boolean): string {
  if (v == null || v === "") return "—";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (data) return formatDate(String(v));
  return String(v);
}

const rotulo: React.CSSProperties = { fontSize: "0.7rem", color: "var(--mob-muted)", fontWeight: 600 };

function ParDado({ label, valor }: { label: string; valor: React.ReactNode }) {
  return (
    <div>
      <span style={rotulo}>{label}</span>
      <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{valor}</div>
    </div>
  );
}

function Grade({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.7rem 1rem" }}>{children}</div>;
}

function Secao({ chave, titulo, linhas, campos, altInicio }: { chave: string; titulo: string; linhas: Record<string, unknown>[]; campos: Campo[]; altInicio: number }) {
  if (!linhas.length) return null;
  return (
    <details style={{ marginBottom: "0.7rem" }}>
      <summary style={{ cursor: "pointer", fontWeight: 700, fontSize: "0.95rem", padding: "0.85rem 1rem", background: "var(--mob-surface)", border: "1px solid var(--mob-border)", borderRadius: 14, listStyle: "none", display: "flex", justifyContent: "space-between", alignItems: "center", boxShadow: "var(--mob-sombra)" }}>
        <span>{titulo}</span>
        <span style={{ fontSize: "0.78rem", color: "var(--mob-muted)", fontWeight: 700 }}>{linhas.length}</span>
      </summary>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
        {linhas.map((l, i) => (
          <MobCard key={i} alt={((altInicio + i) % 2) as 0 | 1}
            style={chave === "servicos" ? estiloSexado(l.tipo_semen as string | null | undefined) : undefined}>
            <Grade>
              {campos.map(([chave, rot, data]) => (
                <ParDado key={chave} label={rot} valor={mostrarValor(l[chave], data)} />
              ))}
            </Grade>
          </MobCard>
        ))}
      </div>
    </details>
  );
}

// Exportado para telas fora de Rebanho (ex.: Menu › Agenda do Veterinário)
// abrirem a ficha do animal com seu próprio "voltar" local, sem navegar para
// a aba Rebanho.
export function FichaDetalhe({ numero, onVoltar, destacarInicial }: { numero: string; onVoltar: () => void; destacarInicial?: "colostragem" | "igg" | null }) {
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [doCache, setDoCache] = useState(false);

  const [editColostro, setEditColostro] = useState(false);
  const [formColostro, setFormColostro] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [destacar, setDestacar] = useState<"colostragem" | "igg" | null>(destacarInicial ?? null);
  const [abrirEdicaoAoCarregar, setAbrirEdicaoAoCarregar] = useState(!!destacarInicial);

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

  const a = ficha?.animal;
  const colostragem = ficha?.colostragem as Record<string, unknown> | null;
  const baixa = ficha?.baixa as Record<string, unknown> | null;
  const compra = ficha?.compra as Record<string, unknown> | null;
  const pai = ficha?.pai;

  function abrirEditColostro() {
    const c: Record<string, unknown> = colostragem || {};
    setFormColostro({
      tomou_colostro: c.tomou_colostro == null ? "" : String(c.tomou_colostro),
      litros_colostro: c.litros_colostro != null ? String(c.litros_colostro) : "",
      brix_colostro: c.brix_colostro != null ? String(c.brix_colostro) : "",
      data_colostro: c.data_colostro != null ? String(c.data_colostro) : "",
      brix_soro: c.brix_soro != null ? String(c.brix_soro) : "",
      data_teste_sangue: c.data_teste_sangue != null ? String(c.data_teste_sangue) : "",
      observacao: c.observacao != null ? String(c.observacao) : "",
    });
    setEditColostro(true); setAviso(null);
  }

  // Chegou da Agenda com uma pendência de colostro/IgG: assim que a ficha
  // carrega, abre direto o formulário de colostragem.
  useEffect(() => {
    if (ficha && abrirEdicaoAoCarregar) {
      abrirEditColostro();
      setAbrirEdicaoAoCarregar(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ficha]);

  async function salvarColostro() {
    setSalvando(true); setAviso(null);
    try {
      const f = formColostro;
      await registrarColostragem({
        numero_animal: numero,
        tomou_colostro: f.tomou_colostro === "" ? undefined : f.tomou_colostro === "true",
        litros_colostro: f.litros_colostro === "" ? undefined : Number(f.litros_colostro),
        brix_colostro: f.brix_colostro === "" ? undefined : Number(f.brix_colostro),
        data_colostro: f.data_colostro || undefined,
        brix_soro: f.brix_soro === "" ? undefined : Number(f.brix_soro),
        data_teste_sangue: f.data_teste_sangue || undefined,
        observacao: f.observacao || undefined,
      });
      setEditColostro(false); setAviso("Colostragem/IgG salvos.");
      setDestacar(null);
      const { dados } = await fetchComCache<Ficha>(`ficha_${numero}`, () => fetchFichaAnimal(numero));
      if (dados) setFicha(dados);
    } catch (e) {
      setAviso(e instanceof Error ? e.message : "Erro ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  // Alternância de cor dos cartões ABAIXO do primeiro (identificação) — mesmo
  // esquema da Agenda (claro: branco/paleta; escuro: preto contornado de
  // vinho/verde). Contador corrido: cada cartão renderizado consome um índice.
  let altContador = 0;
  const proximoAlt = (): 0 | 1 => (altContador++ % 2) as 0 | 1;

  return (
    <div>
      <MobVoltar titulo={`Brinco ${numero}`} onVoltar={onVoltar} />
      {carregando && <p style={{ color: "var(--mob-muted)" }}>Carregando ficha…</p>}
      {erro && <p style={{ color: "var(--mob-vermelho)", fontWeight: 600 }}>{erro}</p>}

      {a && (
        <>
          {doCache && (
            <p style={{ fontSize: "0.78rem", color: "var(--mob-ambar)", fontWeight: 600, marginBottom: "0.6rem" }}>
              Mostrando cópia salva{cacheEm(`ficha_${numero}`) ? ` em ${new Date(cacheEm(`ficha_${numero}`)!).toLocaleString("pt-BR")}` : ""}.
            </p>
          )}

          <MobCard style={{ marginBottom: "0.7rem" }}>
            <div style={{ fontWeight: 800, fontSize: "1.05rem", marginBottom: "0.7rem" }}>
              {String(a.nome || `Brinco ${a.numero}`)}
              <span style={{ color: a.ativo === false ? "var(--mob-vermelho)" : "var(--mob-verde)", fontSize: "0.8rem", fontWeight: 700, marginLeft: "0.5rem" }}>
                {a.ativo === false ? "Baixado" : "Ativo"}
              </span>
            </div>
            <Grade>
              <ParDado label="Sexo" valor={a.sexo === "M" ? "Macho" : a.sexo === "F" ? "Fêmea" : "—"} />
              <ParDado label="Categoria" valor={String(a.categoria_abrev || a.categoria_completa || "—")} />
              <ParDado label="Lote atual" valor={String(a.grupo_primario || "—")} />
              <ParDado label="Raça" valor={String(a.raca || "—")} />
              <ParDado label="Nascimento" valor={a.data_nasc ? formatDate(String(a.data_nasc)) : "—"} />
              <ParDado label="Entrada" valor={a.data_entrada ? formatDate(String(a.data_entrada)) : "—"} />
              <ParDado label="Mãe" valor={String(a.mae_numero || "—")} />
              <ParDado label="DEL" valor={a.del_dias != null ? String(a.del_dias) : "—"} />
              <ParDado label="Pai" valor={pai?.nome ? `${pai.nome}${pai.naab ? ` (${pai.naab})` : ""}` : "—"} />
              <ParDado label="Grau de sangue" valor={String(a.grau_sangue || "—")} />
              <ParDado label="Última produção" valor={a.ult_cl_kg != null ? `${Number(a.ult_cl_kg).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} kg${a.data_ult_leite ? ` (${formatDate(String(a.data_ult_leite))})` : ""}` : "—"} />
              <ParDado label="Previsão de secagem" valor={ficha?.previsao_secagem ? formatDate(ficha.previsao_secagem) : "—"} />
              <ParDado label="Previsão de parto" valor={ficha?.previsao_parto ? formatDate(ficha.previsao_parto) : "—"} />
            </Grade>
          </MobCard>

          <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem", borderColor: destacar ? "var(--mob-vermelho)" : undefined }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
                <div style={{ fontWeight: 700 }}>Colostragem / IgG</div>
                {!editColostro && <button type="button" className="mob-btn mob-btn-sec" style={{ width: "auto", padding: "0.35rem 0.9rem" }} onClick={abrirEditColostro}>Editar</button>}
              </div>

              {destacar && !editColostro && (
                <p style={{ fontSize: "0.82rem", color: "var(--mob-vermelho)", fontWeight: 700, marginBottom: "0.6rem" }}>
                  Pendente da Agenda — preencha {destacar === "colostragem" ? "os litros e o Brix do colostro" : "o Brix do soro (IgG)"} abaixo.
                </p>
              )}

              {aviso && <MobAviso tipo={aviso.includes("Erro") || aviso.includes("erro") ? "erro" : "ok"}>{aviso}</MobAviso>}

              {!editColostro ? (
                <Grade>
                  <ParDado label="Tomou colostro?" valor={mostrarValor(colostragem?.tomou_colostro)} />
                  <ParDado label="Litros" valor={mostrarValor(colostragem?.litros_colostro)} />
                  <ParDado label="Brix colostro" valor={mostrarValor(colostragem?.brix_colostro)} />
                  <ParDado label="Brix soro" valor={mostrarValor(colostragem?.brix_soro)} />
                </Grade>
              ) : (
                <div style={{ marginTop: "0.3rem" }}>
                  <MobCampo label="Tomou colostro?">
                    <select className="mob-input" value={formColostro.tomou_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, tomou_colostro: e.target.value }))}>
                      <option value="">—</option>
                      <option value="true">Sim</option>
                      <option value="false">Não</option>
                    </select>
                  </MobCampo>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 0.8rem" }}>
                    <MobCampo label={destacar === "colostragem" ? "Litros (pendente)" : "Litros"}>
                      <input type="number" inputMode="decimal" className="mob-input" style={destacar === "colostragem" ? { borderColor: "var(--mob-vermelho)" } : undefined}
                        value={formColostro.litros_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, litros_colostro: e.target.value }))} />
                    </MobCampo>
                    <MobCampo label={destacar === "colostragem" ? "Brix colostro (pendente)" : "Brix colostro"}>
                      <input type="number" inputMode="decimal" className="mob-input" style={destacar === "colostragem" ? { borderColor: "var(--mob-vermelho)" } : undefined}
                        value={formColostro.brix_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, brix_colostro: e.target.value }))} />
                    </MobCampo>
                  </div>
                  <MobCampo label="Data do colostro">
                    <input type="date" className="mob-input" value={formColostro.data_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, data_colostro: e.target.value }))} />
                  </MobCampo>
                  <MobCampo label={destacar === "igg" ? "Brix do soro / IgG (pendente)" : "Brix do soro / IgG"}>
                    <input type="number" inputMode="decimal" className="mob-input" style={destacar === "igg" ? { borderColor: "var(--mob-vermelho)" } : undefined}
                      value={formColostro.brix_soro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, brix_soro: e.target.value }))} />
                  </MobCampo>
                  <MobCampo label="Data do teste de sangue">
                    <input type="date" className="mob-input" value={formColostro.data_teste_sangue || ""} onChange={(e) => setFormColostro((p) => ({ ...p, data_teste_sangue: e.target.value }))} />
                  </MobCampo>
                  <MobCampo label="Observação">
                    <input className="mob-input" value={formColostro.observacao || ""} onChange={(e) => setFormColostro((p) => ({ ...p, observacao: e.target.value }))} />
                  </MobCampo>
                  <div style={{ display: "flex", gap: "0.6rem", marginTop: "0.4rem" }}>
                    <button type="button" className="mob-btn" style={{ flex: 1 }} disabled={salvando} onClick={salvarColostro}>{salvando ? "Salvando…" : "Salvar"}</button>
                    <button type="button" className="mob-btn mob-btn-sec" style={{ flex: 1 }} onClick={() => setEditColostro(false)}>Cancelar</button>
                  </div>
                </div>
              )}
            </MobCard>

          {!!ficha?.gtas?.length && (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }}>
              <div style={{ fontWeight: 700, marginBottom: "0.4rem" }}>GTA(s) do animal</div>
              <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{ficha!.gtas.join(", ")}</div>
            </MobCard>
          )}

          {(ficha?.compras || (compra ? [compra] : [])).map((c, i) => (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }} key={`compra-${i}`}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem" }}>Compra</div>
              <Grade>
                <ParDado label="Data" valor={mostrarValor(c.data_compra, true)} />
                <ParDado label="Vendedor" valor={mostrarValor(c.vendedor)} />
                <ParDado label="Valor" valor={c.valor != null ? `R$ ${c.valor}` : "—"} />
                <ParDado label="GTA" valor={mostrarValor(c.gta)} />
                <ParDado label="Responsável" valor={mostrarValor(c.responsavel)} />
              </Grade>
            </MobCard>
          ))}

          {(ficha?.vendas || []).map((v, i) => (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem" }} key={`venda-${i}`}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem" }}>Venda</div>
              <Grade>
                <ParDado label="Data" valor={mostrarValor(v.data_venda, true)} />
                <ParDado label="Comprador" valor={mostrarValor(v.comprador)} />
                <ParDado label="Valor" valor={v.valor != null ? `R$ ${v.valor}` : "—"} />
                <ParDado label="GTA" valor={mostrarValor(v.gta)} />
                <ParDado label="Responsável" valor={mostrarValor(v.responsavel)} />
              </Grade>
            </MobCard>
          ))}

          {baixa && (
            <MobCard alt={proximoAlt()} style={{ marginBottom: "0.7rem", borderColor: "var(--mob-vermelho)" }}>
              <div style={{ fontWeight: 700, marginBottom: "0.6rem", color: "var(--mob-vermelho)" }}>Baixa (saída do rebanho)</div>
              <Grade>
                <ParDado label="Data" valor={mostrarValor(baixa.data_baixa, true)} />
                <ParDado label="Tipo" valor={mostrarValor(baixa.tipo_baixa)} />
                <ParDado label="Motivo" valor={mostrarValor(baixa.motivo)} />
                <ParDado label="Valor" valor={baixa.valor != null ? `R$ ${baixa.valor}` : "—"} />
              </Grade>
            </MobCard>
          )}

          <div className="mob-secao">Lançamentos</div>
          {SECOES.map((s) => {
            const linhas = (ficha?.[s.chave] as Record<string, unknown>[]) || [];
            const altInicio = altContador;
            altContador += linhas.length;
            return <Secao key={s.chave} chave={s.chave} titulo={s.titulo} campos={s.campos} linhas={linhas} altInicio={altInicio} />;
          })}
          {SECOES.every((s) => !((ficha?.[s.chave] as unknown[]) || []).length) && (
            <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum lançamento registrado para este animal.</p>
          )}
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

  if (aberto) return <FichaDetalhe numero={aberto} onVoltar={() => setAberto(null)} destacarInicial={aberto === numeroInicial ? destacar : null} />;

  const ordenados = [...animais].sort((a, b) => a.numero.localeCompare(b.numero, "pt-BR", { numeric: true }));

  return (
    <div>
      <BuscaAnimal valor="" onEscolher={(n) => { if (n) setAberto(n); }} />

      <div className="mob-secao">Todos os animais{ordenados.length ? ` (${ordenados.length})` : ""}</div>
      {carregando && <p style={{ color: "var(--mob-muted)" }}>Carregando…</p>}
      {!carregando && !ordenados.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem" }}>Nenhum animal encontrado.</p>}
      {ordenados.map((r, i) => (
        <MobLinha key={r.numero} alt={(i % 2) as 0 | 1} titulo={`Brinco ${r.numero}${r.nome ? ` · ${r.nome}` : ""}`} subtitulo={subtituloAnimal(r)} onClick={() => setAberto(r.numero)} />
      ))}
    </div>
  );
}
