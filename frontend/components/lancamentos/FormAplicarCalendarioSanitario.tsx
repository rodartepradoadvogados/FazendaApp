"use client";
import React, { useEffect, useMemo, useState } from "react";
import { fetchCalendarioSanitario, formatDate } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { Campo, inputStyle, nota, type EstoqueItem } from "@/components/lancamentos/comumForms";
import { FREQUENCIA_UNIDADES } from "@/components/lancamentos/_shared";
import { FormPreventivoAplicacao } from "@/components/lancamentos/FormPreventivoAplicacao";
import { tipoRegra } from "@/components/lancamentos/FormCalendarioSanitario";

type RegraCalendario = {
  id: number; evento_sanitario_id: number; evento_sanitario_nome: string;
  categoria_preventiva: string | null;
  doenca_nome: string | null; produto: string | null; dosagem: string | null; unidade: string | null;
  frequencia_valor: number; frequencia_unidade: string; proxima_ocorrencia: string;
};

/**
 * Lançamentos > Sanitário > Preventiva > Calendário sanitário — só APLICA
 * uma regra já cadastrada (o cadastro em si mudou de lugar: Central de
 * Protocolos > Cadastro > Sanitário > Preventivo, ver FormCalendarioSanitario
 * lá). Lista fechada (nada de criar regra aqui) — escolhe-se o protocolo,
 * confere-se o resumo (produto/dosagem ou exame, frequência, data prevista)
 * e lança-se para os animais/lote/categoria. Uma aplicação sem vínculo com
 * nenhum protocolo cadastrado é o lançamento "Avulso", não este.
 */
export function FormAplicarCalendarioSanitario({ animais, lotes, estoque }: { animais: AnimalRow[]; lotes: string[]; estoque: EstoqueItem[] }) {
  const [regras, setRegras] = useState<RegraCalendario[] | null>(null);
  const [regraId, setRegraId] = useState("");

  useEffect(() => { fetchCalendarioSanitario().then(setRegras).catch(() => setRegras([])); }, []);

  // Só vacina/exame — "avulso/outro" não tem lugar aqui (vive só no Avulso).
  const opcoes = useMemo(() => (regras ?? []).filter((r) => tipoRegra(r) !== "avulso"), [regras]);
  const regraSel = opcoes.find((r) => String(r.id) === regraId);
  const ehExame = regraSel ? tipoRegra(regraSel) === "exame" : false;

  return (
    <>
      <p style={nota}>
        Escolha um protocolo já cadastrado no calendário sanitário (Central de Protocolos {"›"} Cadastro {"›"} Sanitário{" "}
        {"›"} Preventivo) para aplicar agora. Para uma aplicação sem vínculo com nenhum protocolo, use a aba "Avulso".
      </p>
      <Campo label="Protocolo cadastrado">
        <select style={inputStyle} value={regraId} onChange={(e) => setRegraId(e.target.value)}>
          <option value="">{regras === null ? "Carregando…" : "Selecione…"}</option>
          {opcoes.map((r) => (
            <option key={r.id} value={r.id}>{r.evento_sanitario_nome} — próx. {formatDate(r.proxima_ocorrencia)}</option>
          ))}
        </select>
      </Campo>
      {regras !== null && !opcoes.length && (
        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
          Nenhum protocolo cadastrado ainda. Cadastre em Central de Protocolos {"›"} Cadastro {"›"} Sanitário {"›"} Preventivo.
        </p>
      )}

      {regraSel && (
        <div className="card" style={{ marginTop: "0.75rem", background: "var(--surface-2)" }}>
          <div className="card-header mb-2">{regraSel.evento_sanitario_nome}</div>
          <div style={{ fontSize: "0.82rem", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
            <div>Tipo: <strong>{ehExame ? "Exame" : "Vacina"}</strong></div>
            {regraSel.doenca_nome && <div>Previne: <strong>{regraSel.doenca_nome}</strong></div>}
            {ehExame ? (
              <div>Exame agendado — sem baixa de estoque.</div>
            ) : (
              <div>
                Produto: <strong>{regraSel.produto || "—"}</strong>
                {regraSel.dosagem ? ` · ${regraSel.dosagem}${regraSel.unidade ? " " + regraSel.unidade : ""}` : ""}
              </div>
            )}
            <div>Frequência: a cada {regraSel.frequencia_valor} {FREQUENCIA_UNIDADES.find((u) => u.v === regraSel.frequencia_unidade)?.l?.toLowerCase() ?? regraSel.frequencia_unidade}</div>
            <div>Data prevista: <strong>{formatDate(regraSel.proxima_ocorrencia)}</strong></div>
          </div>
        </div>
      )}

      {regraSel && (
        <div style={{ marginTop: "1rem" }}>
          <FormPreventivoAplicacao animais={animais} lotes={lotes} estoque={estoque}
            calendarioFixo={{ id: regraSel.id, evento_sanitario_id: regraSel.evento_sanitario_id }} />
        </div>
      )}
    </>
  );
}
