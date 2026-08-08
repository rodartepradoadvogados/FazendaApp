"use client";
// Etapas 5 (Energia), 6 (Proteína e PDR/PNDR) e 7 (Carboidratos e fibra) —
// mesmo componente genérico, só troca o conjunto de campos mostrado. Nomes
// de campo conferidos direto na saída real do motor (resultado_para_dict),
// não adivinhados — ver AGENTS do módulo para o comando que gera esse JSON.
import { Resultado } from "@/lib/dietas";

export type DominioWizard = "energia" | "proteina" | "carboidratos";

type Grupo = { titulo: string; linhas: { rotulo: string; valor: unknown; unidade?: string }[] };

function fmtValor(v: unknown, unidade?: string): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  if (typeof v === "number") {
    if (Number.isNaN(v)) return "—";
    return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (unidade ? ` ${unidade}` : "");
  }
  return String(v);
}

function gruposEnergia(r: Resultado): Grupo[] {
  const e = r.energia;
  return [
    { titulo: "Fluxo de energia bruta → líquida (Mcal/d)", linhas: [
      { rotulo: "Energia bruta", valor: e.energia_bruta_mcal },
      { rotulo: "Energia digestível", valor: e.energia_digestivel_mcal },
      { rotulo: "Energia metabolizável", valor: e.energia_metabolizavel_mcal },
      { rotulo: "Energia líquida", valor: e.energia_liquida_mcal },
      { rotulo: "Perda em gases", valor: e.perda_gases_mcal },
      { rotulo: "Perda em urina", valor: e.perda_urina_mcal },
    ] },
    { titulo: "Concentrações (Mcal/kg MS)", linhas: [
      { rotulo: "ED", valor: e.energia_digestivel_concentracao_mcal_kg },
      { rotulo: "EM", valor: e.energia_metabolizavel_concentracao_mcal_kg },
      { rotulo: "EL", valor: e.energia_liquida_concentracao_mcal_kg },
      { rotulo: "ELl do leite", valor: e.nel_leite_concentracao_mcal_kg },
    ] },
    { titulo: "Exigência por destino", linhas: [
      { rotulo: "Mantença — ELl", valor: e.nel_mantenca_mcal, unidade: "Mcal/d" },
      { rotulo: "Mantença — EM", valor: e.em_mantenca_mcal, unidade: "Mcal/d" },
      { rotulo: "Eficiência EM→EL (mantença)", valor: e.eficiencia_em_el_mantenca },
      { rotulo: "Gestação — ELl", valor: e.nel_gestacao_mcal, unidade: "Mcal/d" },
      { rotulo: "Gestação — EM", valor: e.em_gestacao_mcal, unidade: "Mcal/d" },
      { rotulo: "Ganho corporal — ELl", valor: e.nel_ganho_mcal, unidade: "Mcal/d" },
      { rotulo: "Ganho corporal — EM", valor: e.em_ganho_mcal, unidade: "Mcal/d" },
      { rotulo: "Leite — ELl", valor: e.nel_leite_mcal, unidade: "Mcal/d" },
      { rotulo: "Leite — EM", valor: e.em_leite_mcal, unidade: "Mcal/d" },
      { rotulo: "Total — ELl", valor: e.nel_uso_total_mcal, unidade: "Mcal/d" },
      { rotulo: "Total — EM", valor: e.em_uso_total_mcal, unidade: "Mcal/d" },
    ] },
    { titulo: "Balanço e produção permitida", linhas: [
      { rotulo: "Balanço de EM", valor: e.balanco_em_mcal, unidade: "Mcal/d" },
      { rotulo: "Balanço de ELl", valor: e.balanco_nel_mcal, unidade: "Mcal/d" },
      { rotulo: "Leite permitido pela energia", valor: e.leite_permitido_por_el_kg_dia, unidade: "kg/d" },
      { rotulo: "Ganho permitido pela energia", valor: e.ganho_permitido_por_el_kg_dia, unidade: "kg/d" },
      { rotulo: "Dias para +1 ponto de ECC", valor: e.dias_para_1_ponto_ecc },
      { rotulo: "Aviso de metano alternativo", valor: e.aviso_metano_alternativo },
    ] },
  ];
}

function gruposProteina(r: Resultado): Grupo[] {
  const p = r.proteina;
  const mic = r.microbiana;
  const d = r.dieta;
  return [
    { titulo: "Suprimento de proteína metabolizável (g/d)", linhas: [
      { rotulo: "PNDR digestível", valor: p.suprimento.pndr_digestivel_g },
      { rotulo: "Proteína microbiana verdadeira digestível", valor: p.suprimento.proteina_microbiana_verdadeira_digestivel_g },
      { rotulo: "PM total fornecida", valor: p.suprimento.pm_fornecida_g },
    ] },
    { titulo: "Perdas endógenas de mantença (g/d)", linhas: [
      { rotulo: "Descamação (PB)", valor: p.manutencao.descamacao_cp_g },
      { rotulo: "Descamação (proteína líquida)", valor: p.manutencao.descamacao_np_g },
      { rotulo: "Fecal endógena (PB)", valor: p.manutencao.fecal_endogena_cp_g },
      { rotulo: "Fecal endógena (proteína líquida)", valor: p.manutencao.fecal_endogena_np_g },
      { rotulo: "Urinária endógena", valor: p.manutencao.urinaria_endogena_np_g },
    ] },
    { titulo: "Exigência de PM por destino (g/d)", linhas: [
      { rotulo: "Mantença", valor: p.exigencias.manutencao_g },
      { rotulo: "Gestação", valor: p.exigencias.gestacao_g },
      { rotulo: "Ganho corporal", valor: p.exigencias.ganho_g },
      { rotulo: "Leite", valor: p.exigencias.leite_g },
      { rotulo: "Total", valor: p.exigencias.total_g },
    ] },
    { titulo: "Balanço", linhas: [
      { rotulo: "Balanço de PM", valor: p.balanco_g, unidade: "g/d" },
      { rotulo: "Leite permitido pela PM", valor: p.leite_permitido_por_pm_kg_dia, unidade: "kg/d" },
      { rotulo: "Nitrogênio urinário", valor: p.nitrogenio_urinario_g_dia, unidade: "g/d" },
    ] },
    { titulo: "Fração ruminal / microbiana", linhas: [
      { rotulo: "PDR disponível para microbiana", valor: mic.pdr_para_microbiana_kg, unidade: "kg/d" },
      { rotulo: "Capacidade máxima de síntese", valor: mic.capacidade_maxima_g_dia, unidade: "g/d" },
      { rotulo: "Nitrogênio microbiano", valor: mic.nitrogenio_microbiano_g_dia, unidade: "g/d" },
      { rotulo: "Proteína microbiana bruta", valor: mic.proteina_microbiana_bruta_g_dia, unidade: "g/d" },
      { rotulo: "Proteína microbiana verdadeira", valor: mic.proteina_microbiana_verdadeira_g_dia, unidade: "g/d" },
      { rotulo: "Proteína microbiana verdadeira digestível", valor: mic.proteina_microbiana_verdadeira_digestivel_g_dia, unidade: "g/d" },
    ] },
    { titulo: "PDR / PNDR da dieta (% da MS)", linhas: [
      { rotulo: "PDR", valor: d.rdp_pct_dm },
      { rotulo: "PNDR", valor: d.rup_pct_dm },
      { rotulo: "PNDR (% da PB)", valor: d.rup_pct_cp },
      { rotulo: "PNDR digestível", valor: d.rup_digestivel_pct_dm },
      { rotulo: "NNP (% da MS)", valor: d.npncp_pct_dm },
    ] },
  ];
}

function gruposCarboidratos(r: Resultado): Grupo[] {
  const d = r.dieta;
  const dig = r.digestao as any;
  const ing = dig.ingestoes || {};
  return [
    { titulo: "Composição da dieta (% da MS)", linhas: [
      { rotulo: "FDN", valor: d.fdn_pct },
      { rotulo: "FDA", valor: d.fda_pct },
      { rotulo: "Lignina", valor: d.lignina_pct },
      { rotulo: "Amido", valor: d.amido_pct },
      { rotulo: "Açúcares", valor: d.acucares_pct },
      { rotulo: "Carboidratos não fibrosos (CNF)", valor: d.cnf_pct_dm },
    ] },
    { titulo: "Forragem", linhas: [
      { rotulo: "% forragem na dieta", valor: d.forragem_pct },
      { rotulo: "FDN da forragem (% MS)", valor: d.forragem_ndf_pct_dm },
      { rotulo: "FDN da forragem (% da FDN total)", valor: d.forragem_ndf_sobre_ndf_pct },
      { rotulo: "Relação FDA/FDN", valor: d.adf_ndf },
      { rotulo: "dNDF48 da forragem (% da FDN da forragem)", valor: d.forragem_dndf48_sobre_forragem_ndf_pct },
    ] },
    { titulo: "Digestão ruminal e no trato total", linhas: [
      { rotulo: "Digestibilidade ruminal da FDN", valor: dig.rum_dc_ndf_pct, unidade: "%" },
      { rotulo: "Digestibilidade ruminal do amido", valor: dig.rum_dc_st_pct, unidade: "%" },
      { rotulo: "FDN digerida no rúmen", valor: dig.rum_dig_ndf_kg, unidade: "kg/d" },
      { rotulo: "Amido digerido no rúmen", valor: dig.rum_dig_st_kg, unidade: "kg/d" },
      { rotulo: "Digestibilidade total da FDN", valor: dig.tt_dc_ndf_pct, unidade: "%" },
      { rotulo: "Digestibilidade total do amido", valor: dig.tt_dc_st_pct, unidade: "%" },
      { rotulo: "FDN digerida total", valor: dig.ndf_digerida_kg, unidade: "kg/d" },
      { rotulo: "Amido digerido total", valor: dig.amido_digerido_kg, unidade: "kg/d" },
      { rotulo: "FDN digerida (% da dieta)", valor: dig.ndf_digerida_pct_dieta },
    ] },
    { titulo: "Ingestões diárias (kg/d)", linhas: [
      { rotulo: "CMS", valor: ing.cms_kg_dia },
      { rotulo: "PB", valor: ing.pb_kg },
      { rotulo: "FDN", valor: ing.fdn_kg },
      { rotulo: "FDA", valor: ing.fda_kg },
      { rotulo: "Amido", valor: ing.amido_kg },
      { rotulo: "Ácidos graxos", valor: ing.ag_kg },
      { rotulo: "Cinzas", valor: ing.cinzas_kg },
      { rotulo: "FDN de forragem", valor: ing.for_ndf_kg },
    ] },
  ];
}

export function PainelDominio({ dominio, resultado }: { dominio: DominioWizard; resultado: Resultado | null }) {
  if (!resultado) {
    return <div className="empty-state">Preencha a grade (Etapa 1) e os dados do animal (Etapa 2) para ver este detalhamento.</div>;
  }
  const grupos = dominio === "energia" ? gruposEnergia(resultado) : dominio === "proteina" ? gruposProteina(resultado) : gruposCarboidratos(resultado);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(18rem, 1fr))", gap: "0.9rem" }}>
      {grupos.map((g) => (
        <div key={g.titulo} className="card" style={{ padding: 0 }}>
          <div className="card-header">{g.titulo}</div>
          <table style={{ width: "100%" }}>
            <tbody>
              {g.linhas.map((l) => (
                <tr key={l.rotulo}>
                  <td style={{ padding: "0.4rem 0.7rem", color: "var(--text-muted)", fontSize: "0.82rem" }}>{l.rotulo}</td>
                  <td style={{ padding: "0.4rem 0.7rem", color: "var(--text)", fontWeight: 600, fontSize: "0.82rem", textAlign: "right" }}>{fmtValor(l.valor, l.unidade)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
