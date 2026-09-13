"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { formatBRL, type ComposicaoMediaVariaveis } from "@/lib/api";

/*
 * A MÉDIA DAS VERBAS VARIÁVEIS HABITUAIS, E COMO ELA FOI APURADA.
 *
 * Este componente existe por uma razão só, e ela não é decorativa: uma média
 * que ninguém consegue conferir é uma média que ninguém confia — e num
 * sistema de folha isso é inaceitável. O número que entra na base do 13º, das
 * férias e da rescisão tem de vir acompanhado de QUAIS competências entraram,
 * QUAIS rubricas em cada uma, QUANTO somaram e POR QUANTO foi dividido.
 *
 * As três coisas que ele precisa deixar óbvias, e que a tela erraria se
 * mostrasse só o número:
 *
 * 1. "NÃO APURADA" ≠ "APUROU E DEU ZERO". `aplicada: false` é o parâmetro
 *    desligado — o cálculo saiu só sobre o salário-base, como sempre saiu.
 *    `aplicada: true` com `media: 0` é outra coisa: o sistema olhou o período
 *    e a pessoa não teve verba variável nenhuma. Confundir as duas faria o
 *    dono achar que a feature está quebrada quando ela só está desligada.
 * 2. O DIVISOR. Mês com contrato em vigor e sem folha lançada entra no
 *    divisor valendo zero (Decreto 57.155/65, art. 2º — "meses de vigência do
 *    contrato"). É a escolha que mais muda o valor, então o número de
 *    competências sem folha aparece EM DESTAQUE, não escondido na tabela.
 * 3. O FUNDAMENTO. Cada janela tem o artigo que a sustenta, e ele vem escrito
 *    do servidor — a tela não redige direito trabalhista.
 */

const ROTULO_JANELA: Record<string, string> = {
  ano_civil: "Ano civil",
  periodo_aquisitivo: "Período aquisitivo",
  ultimos_12_meses: "Últimos 12 meses",
};

export function MediaVerbasVariaveis({
  composicao,
  titulo,
  compacto = false,
}: {
  composicao: ComposicaoMediaVariaveis | null | undefined;
  /** Nome da verba a que esta média se aplica ("13º salário", "Férias",
   *  "Aviso prévio indenizado") — na rescisão são três blocos e sem o título
   *  ninguém sabe qual média é qual. */
  titulo?: string;
  /** `true` esconde a tabela por padrão (listagens); `false` já abre. */
  compacto?: boolean;
}) {
  const [aberto, setAberto] = useState(!compacto);
  if (!composicao) return null;

  const cab = (
    <span style={{ fontWeight: 700 }}>
      {titulo ? `${titulo} — ` : ""}Média de verbas variáveis
    </span>
  );

  // Parâmetro desligado: uma linha explicando, e nada mais. Mostrar uma tabela
  // vazia aqui sugeriria que o sistema tentou e não achou nada.
  if (!composicao.aplicada) {
    return (
      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
        {cab}: <strong>não apurada</strong>.{" "}
        {composicao.motivo ||
          "O parâmetro de médias de verbas variáveis está desligado nesta fazenda."}
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: "0.5rem 0.7rem", marginTop: "0.4rem", fontSize: "0.78rem" }}>
      <button
        className="btn-ghost"
        style={{ fontSize: "0.78rem", padding: 0, display: "flex", alignItems: "center", gap: "0.3rem" }}
        onClick={() => setAberto((v) => !v)}
      >
        {aberto ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {cab}
        <strong style={{ color: "var(--dourado-light)" }}>{formatBRL(composicao.media)}</strong>
        <span style={{ color: "var(--text-muted)" }}>/ mês</span>
      </button>

      {aberto && (
        <div style={{ marginTop: "0.4rem" }}>
          <div style={{ color: "var(--text-muted)", marginBottom: "0.3rem" }}>
            {ROTULO_JANELA[composicao.janela] || composicao.janela} · {composicao.rotulo_janela} ·{" "}
            {formatBRL(composicao.total)} ÷ {composicao.divisor} = <strong>{formatBRL(composicao.media)}</strong>
          </div>
          <div style={{ color: "var(--text-muted)", marginBottom: "0.4rem" }}>
            Divisor: {composicao.criterio_divisor}.
            {composicao.competencias_sem_folha > 0 && (
              <>
                {" "}
                <strong style={{ color: "var(--amber)" }}>
                  {composicao.competencias_sem_folha} competência(s) sem folha lançada
                </strong>{" "}
                entram no divisor valendo zero — é o que a norma manda dividir (meses de
                vigência do contrato), e é o que puxa a média para baixo.
              </>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="fazenda-table" style={{ fontSize: "0.74rem" }}>
              <thead>
                <tr>
                  <th>Competência</th>
                  <th>Rubricas salariais variáveis</th>
                  <th style={{ textAlign: "right" }}>Valor</th>
                </tr>
              </thead>
              <tbody>
                {composicao.competencias.map((comp) => (
                  <tr key={comp.competencia}>
                    <td>{comp.rotulo}</td>
                    <td style={{ color: comp.rubricas.length ? undefined : "var(--text-muted)" }}>
                      {comp.rubricas.length
                        ? comp.rubricas.map((r) => `${r.rotulo} ${formatBRL(r.valor)}`).join(" · ")
                        : comp.sem_folha
                          ? "sem folha lançada"
                          : "sem verba variável"}
                    </td>
                    <td style={{ textAlign: "right" }}>{formatBRL(comp.valor)}</td>
                  </tr>
                ))}
                <tr>
                  <td style={{ fontWeight: 700 }}>Total</td>
                  <td></td>
                  <td style={{ textAlign: "right", fontWeight: 700 }}>{formatBRL(composicao.total)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {composicao.fundamento && (
            <p style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: "0.4rem" }}>
              {composicao.fundamento}.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
