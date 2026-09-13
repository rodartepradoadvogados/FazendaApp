"use client";
// Seção SANIDADE — Colostragem/IgG (formulário de edição já existia no
// mobile, só mudou de arquivo e de dono do estado — antes vivia em
// FichaDetalhe, agora é local a esta seção) + Rastreabilidade Sanitária
// unificada (linha do tempo/exames/doenças — hoje só na ficha de mesa, aqui
// como pílulas em vez de abas, ver MobPill/LinhaPills já usados em Lançar) +
// acordeões de aplicações/protocolos sanitários.
import { useState } from "react";
import { formatDate } from "@/lib/api";
import { enviarOuEnfileirar } from "@/lib/offline";
import { MobCard, MobCampo, MobAviso } from "@/components/mobile/ui";
import { MobPill, LinhaPills } from "@/components/mobile/lancar/comum";
import { Grade, ParDado, Secao, secaoPorChave, mostrarValor, tituloCartao, type Ficha } from "./comumFicha";

function classeColostro(brix: unknown): string {
  const v = brix == null ? null : Number(brix);
  if (v == null || Number.isNaN(v)) return "—";
  if (v > 25) return "Ouro (excelente)";
  if (v >= 18) return "Prata (médio)";
  return "Bronze (ruim)";
}
function classeSoro(brix: unknown): string {
  const v = brix == null ? null : Number(brix);
  if (v == null || Number.isNaN(v)) return "—";
  if (v >= 8.4) return "Sucesso";
  if (v >= 8.1) return "Alerta";
  return "Falha";
}

function formColostroInicial(c: Record<string, unknown> | null): Record<string, string> {
  return {
    tomou_colostro: c?.tomou_colostro == null ? "" : String(c.tomou_colostro),
    litros_colostro: c?.litros_colostro != null ? String(c.litros_colostro) : "",
    brix_colostro: c?.brix_colostro != null ? String(c.brix_colostro) : "",
    data_colostro: c?.data_colostro != null ? String(c.data_colostro) : "",
    hora_parto: c?.hora_parto != null ? String(c.hora_parto) : "",
    hora_colostro: c?.hora_colostro != null ? String(c.hora_colostro) : "",
    peso_nascer_kg: c?.peso_nascer_kg != null ? String(c.peso_nascer_kg) : "",
    brix_soro: c?.brix_soro != null ? String(c.brix_soro) : "",
    proteina_serica: c?.proteina_serica != null ? String(c.proteina_serica) : "",
    apenas_colostro_po: c?.apenas_colostro_po == null ? "" : String(c.apenas_colostro_po),
    data_teste_sangue: c?.data_teste_sangue != null ? String(c.data_teste_sangue) : "",
    observacao: c?.observacao != null ? String(c.observacao) : "",
  };
}

/** Corpo de uma pílula da Rastreabilidade sanitária (Exames/Doenças) — mesmo
 * padrão MobCard/Grade/ParDado das demais listas da ficha, sem o
 * `<details>` ao redor (a própria pílula já cumpre o papel de "aberto"). */
function ListaCampos({ chave, linhas }: { chave: string; linhas: Record<string, unknown>[] }) {
  const s = secaoPorChave(chave);
  if (!linhas.length) return <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>Nenhum registro.</p>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      {linhas.map((l, i) => (
        <MobCard key={i} alt={(i % 2) as 0 | 1}>
          <Grade>
            {s.campos.map(([chaveCampo, rot, data]) => (
              <ParDado key={chaveCampo} label={rot} valor={mostrarValor(l[chaveCampo], data)} />
            ))}
          </Grade>
        </MobCard>
      ))}
    </div>
  );
}

export function SecaoSanidade({ ficha, numero, destacarInicial, recarregarFicha }: {
  ficha: Ficha; numero: string; destacarInicial?: "colostragem" | "igg" | null; recarregarFicha: () => Promise<void>;
}) {
  const colostragem = ficha.colostragem as Record<string, unknown> | null;

  // Estado do formulário de colostro é local a esta seção — o componente só
  // monta depois que a ficha já carregou (a fachada só mostra seções depois
  // que `ficha` existe), então não precisa do useEffect "abrir ao carregar"
  // que a versão anterior tinha: já nasce aberto quando veio destacado.
  const [editColostro, setEditColostro] = useState(!!destacarInicial);
  const [formColostro, setFormColostro] = useState<Record<string, string>>(() => formColostroInicial(colostragem));
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [destacar, setDestacar] = useState<"colostragem" | "igg" | null>(destacarInicial ?? null);

  function abrirEditColostro() {
    setFormColostro(formColostroInicial(colostragem));
    setEditColostro(true);
    setAviso(null);
  }

  async function salvarColostro() {
    setSalvando(true); setAviso(null);
    try {
      const f = formColostro;
      const { enviado } = await enviarOuEnfileirar(
        "/sanidade/colostragem",
        {
          numero_animal: numero,
          tomou_colostro: f.tomou_colostro === "" ? undefined : f.tomou_colostro === "true",
          litros_colostro: f.litros_colostro === "" ? undefined : Number(f.litros_colostro),
          brix_colostro: f.brix_colostro === "" ? undefined : Number(f.brix_colostro),
          data_colostro: f.data_colostro || undefined,
          hora_parto: f.hora_parto || undefined,
          hora_colostro: f.hora_colostro || undefined,
          peso_nascer_kg: f.peso_nascer_kg === "" ? undefined : Number(f.peso_nascer_kg),
          brix_soro: f.brix_soro === "" ? undefined : Number(f.brix_soro),
          proteina_serica: f.proteina_serica === "" ? undefined : Number(f.proteina_serica),
          apenas_colostro_po: f.apenas_colostro_po === "" ? undefined : f.apenas_colostro_po === "true",
          data_teste_sangue: f.data_teste_sangue || undefined,
          observacao: f.observacao || undefined,
        },
        `Colostragem/IgG — brinco ${numero}`,
        "POST",
      );
      setEditColostro(false);
      setAviso(enviado ? "Colostragem/IgG salvos." : "Sem internet — guardado, será enviado ao conectar.");
      setDestacar(null);
      if (enviado) await recarregarFicha();
    } catch (e) {
      setAviso(e instanceof Error ? e.message : "Erro ao salvar.");
    } finally {
      setSalvando(false);
    }
  }

  const [pillAtiva, setPillAtiva] = useState<"linha_tempo" | "exames" | "doencas">("linha_tempo");
  const linhaTempo = ficha.linha_tempo_sanitaria || [];
  const exames = (ficha.exames_resultados as Record<string, unknown>[]) || [];
  const doencas = (ficha.ocorrencias_clinicas as Record<string, unknown>[]) || [];
  const totalRastreabilidade = linhaTempo.length + exames.length + doencas.length;

  let altContador = 2; // colostro + rastreabilidade já consumiram as 2 primeiras cores
  function acordeao(chave: string) {
    const s = secaoPorChave(chave);
    const linhas = (ficha[chave] as Record<string, unknown>[]) || [];
    const altInicio = altContador;
    altContador += linhas.length;
    return <Secao key={chave} chave={chave} titulo={s.titulo} campos={s.campos} linhas={linhas} altInicio={altInicio} />;
  }

  return (
    <div>
      <MobCard alt={0} style={{ marginBottom: "0.85rem", borderColor: destacar ? "var(--mob-vermelho)" : undefined }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.6rem" }}>
          <p style={{ ...tituloCartao, marginBottom: 0 }}>Colostragem / IgG</p>
          {!editColostro && <button type="button" className="mob-btn mob-btn-sec" style={{ width: "auto", padding: "0.35rem 0.9rem" }} onClick={abrirEditColostro}>{colostragem ? "Editar" : "Lançar"}</button>}
        </div>

        {destacar && !editColostro && (
          <p style={{ fontSize: "0.82rem", color: "var(--mob-vermelho)", fontWeight: 700, marginBottom: "0.6rem" }}>
            Pendente da Agenda — preencha {destacar === "colostragem" ? "os litros e o Brix do colostro" : "o Brix do soro (IgG)"} abaixo.
          </p>
        )}

        {aviso && (
          <MobAviso tipo={aviso.includes("Erro") || aviso.includes("erro") ? "erro" : aviso.startsWith("Sem internet") ? "offline" : "ok"}>
            {aviso}
          </MobAviso>
        )}

        {!editColostro ? (
          colostragem ? (
            <Grade>
              <ParDado label="Peso ao nascer (kg)" valor={mostrarValor(colostragem.peso_nascer_kg)} />
              <ParDado label="Tomou colostro?" valor={mostrarValor(colostragem.tomou_colostro)} />
              <ParDado label="Litros" valor={mostrarValor(colostragem.litros_colostro)} />
              <ParDado label="Brix colostro" valor={<>{mostrarValor(colostragem.brix_colostro)} — {classeColostro(colostragem.brix_colostro)}</>} />
              <ParDado label="Brix soro" valor={<>{mostrarValor(colostragem.brix_soro)} — {classeSoro(colostragem.brix_soro)}</>} />
              <ParDado label="Proteína sérica" valor={mostrarValor(colostragem.proteina_serica)} />
              <ParDado label="Só colostro em pó?" valor={mostrarValor(colostragem.apenas_colostro_po)} />
              <ParDado label="Data do colostro" valor={colostragem.data_colostro ? formatDate(String(colostragem.data_colostro)) : "—"} />
            </Grade>
          ) : (
            <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>Dados de colostragem/IgG ainda não lançados. Toque em <strong>Lançar</strong> para preencher.</p>
          )
        ) : (
          <div style={{ marginTop: "0.3rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 0.8rem" }}>
              <MobCampo label="Hora do parto">
                <input type="time" className="mob-input" value={formColostro.hora_parto || ""} onChange={(e) => setFormColostro((p) => ({ ...p, hora_parto: e.target.value }))} />
              </MobCampo>
              <MobCampo label="Hora do colostro">
                <input type="time" className="mob-input" value={formColostro.hora_colostro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, hora_colostro: e.target.value }))} />
              </MobCampo>
            </div>
            <MobCampo label="Peso ao nascer (kg)">
              <input type="number" step="0.1" inputMode="decimal" className="mob-input" value={formColostro.peso_nascer_kg || ""} onChange={(e) => setFormColostro((p) => ({ ...p, peso_nascer_kg: e.target.value }))} placeholder="ex.: 38" />
            </MobCampo>
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
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 0.8rem" }}>
              <MobCampo label={destacar === "igg" ? "Brix do soro / IgG (pendente)" : "Brix do soro / IgG"}>
                <input type="number" inputMode="decimal" className="mob-input" style={destacar === "igg" ? { borderColor: "var(--mob-vermelho)" } : undefined}
                  value={formColostro.brix_soro || ""} onChange={(e) => setFormColostro((p) => ({ ...p, brix_soro: e.target.value }))} />
              </MobCampo>
              <MobCampo label="Proteína sérica (g/dL)">
                <input type="number" step="0.1" inputMode="decimal" className="mob-input" value={formColostro.proteina_serica || ""} onChange={(e) => setFormColostro((p) => ({ ...p, proteina_serica: e.target.value }))} placeholder="ex.: 6,0" />
              </MobCampo>
            </div>
            <MobCampo label="Data do teste de sangue">
              <input type="date" className="mob-input" value={formColostro.data_teste_sangue || ""} onChange={(e) => setFormColostro((p) => ({ ...p, data_teste_sangue: e.target.value }))} />
            </MobCampo>
            <MobCampo label="Recebeu somente colostro em pó?">
              <select className="mob-input" value={formColostro.apenas_colostro_po || ""} onChange={(e) => setFormColostro((p) => ({ ...p, apenas_colostro_po: e.target.value }))}>
                <option value="">—</option>
                <option value="true">Sim (sem colostro materno)</option>
                <option value="false">Não</option>
              </select>
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

      <MobCard alt={1} style={{ marginBottom: "0.85rem" }}>
        <p style={tituloCartao}>Rastreabilidade sanitária</p>
        <LinhaPills>
          <MobPill ativa={pillAtiva === "linha_tempo"} onClick={() => setPillAtiva("linha_tempo")}>Linha do tempo ({linhaTempo.length})</MobPill>
          <MobPill ativa={pillAtiva === "exames"} onClick={() => setPillAtiva("exames")}>Exames ({exames.length})</MobPill>
          <MobPill ativa={pillAtiva === "doencas"} onClick={() => setPillAtiva("doencas")}>Doenças ({doencas.length})</MobPill>
        </LinhaPills>

        {!totalRastreabilidade && (
          <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>Nenhum evento de rastreabilidade sanitária registrado.</p>
        )}

        {!!totalRastreabilidade && pillAtiva === "linha_tempo" && (
          linhaTempo.length ? (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {linhaTempo.map((e, i) => (
                <div key={i} style={{ display: "flex", gap: "0.6rem", padding: "0.5rem 0", borderBottom: i < linhaTempo.length - 1 ? "1px dashed var(--mob-border)" : "none" }}>
                  <span style={{ width: 8, height: 8, borderRadius: "50%", marginTop: "0.35rem", flexShrink: 0, background: "var(--cat-sanidade)" }} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: "0.82rem" }}>{e.tipo_evento}</div>
                    <div style={{ fontSize: "0.74rem", color: "var(--mob-muted)" }}>
                      {e.data ? formatDate(e.data) : "—"}{e.descricao ? ` — ${e.descricao}` : ""}
                      {e.gta ? ` · GTA ${e.gta}` : ""}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)" }}>Nenhum evento na linha do tempo.</p>
        )}
        {!!totalRastreabilidade && pillAtiva === "exames" && <ListaCampos chave="exames_resultados" linhas={exames} />}
        {!!totalRastreabilidade && pillAtiva === "doencas" && <ListaCampos chave="ocorrencias_clinicas" linhas={doencas} />}
      </MobCard>

      {acordeao("aplicacoes_sanitarias")}
      {acordeao("protocolos_sanitarios")}
    </div>
  );
}
