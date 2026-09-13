"use client";
import React from "react";

/**
 * Campo de valor em reais — digita como caixa registradora/app de banco: cada
 * dígito entra pela direita (nas casas de centavo) e o campo se formata
 * sozinho como "R$ 0,00" a cada tecla. Nunca existe um estado intermediário
 * ambíguo (duas vírgulas, ponto solto) — todo valor exibido já é um número
 * válido, e `onChange` sempre entrega reais (ex.: 1234.56), não string.
 */
export function CampoMoeda({
  value, onChange, onBlur, placeholder = "R$ 0,00", disabled = false, style, className, autoFocus = false, id, name,
}: {
  value: number | null | undefined;
  onChange: (v: number) => void;
  /**
   * Chamado ao SAIR do campo, com o valor final em reais. Existe porque
   * validar a cada tecla é impossível aqui: o campo digita como caixa
   * registradora (cada dígito entra pela direita), então trocar R$ 3.000 por
   * R$ 3.500 passa obrigatoriamente por R$ 0,03, R$ 0,35 e R$ 3,50 — e uma
   * regra de "valor menor que o previsto" dispararia em todos eles. Quem
   * precisa validar um valor inteiro valida na saída do campo.
   */
  onBlur?: (v: number) => void;
  placeholder?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
  className?: string;
  autoFocus?: boolean;
  id?: string;
  name?: string;
}) {
  const centavos = Math.round((value || 0) * 100);
  const exibido = centavos === 0 ? "" : (centavos / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  function aoDigitar(e: React.ChangeEvent<HTMLInputElement>) {
    // Só dígitos sobrevivem — "R$", ".", "," e qualquer outro caractere da
    // formatação são só decoração, nunca dado. Teto de 11 dígitos (até
    // R$ 999.999.999,99) pra um clique/colar acidental não estourar o valor.
    const digitos = e.target.value.replace(/\D/g, "").replace(/^0+(?=\d)/, "").slice(0, 11);
    onChange(digitos ? parseInt(digitos, 10) / 100 : 0);
  }

  return (
    <input
      type="text"
      inputMode="decimal"
      id={id}
      name={name}
      autoFocus={autoFocus}
      disabled={disabled}
      value={exibido}
      placeholder={placeholder}
      style={style}
      className={className}
      onChange={aoDigitar}
      onBlur={onBlur ? () => onBlur(value || 0) : undefined}
    />
  );
}
