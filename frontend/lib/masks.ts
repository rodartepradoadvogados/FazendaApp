/**
 * Máscaras de campo (telefone, CPF/CNPJ, CEP) — formata progressivamente
 * enquanto o usuário digita, sem depender de biblioteca externa. Cada função
 * recebe o valor bruto do input (já com a máscara antiga aplicada ou não) e
 * devolve o valor reformatado; o valor "limpo" (só dígitos) é o que deve ser
 * enviado ao backend quando aplicável.
 */

const soDigitos = (v: string) => v.replace(/\D/g, "");

export function maskTelefone(v: string): string {
  const d = soDigitos(v).slice(0, 11);
  if (d.length <= 10) {
    // (99) 9999-9999
    return d
      .replace(/^(\d{2})(\d)/, "($1) $2")
      .replace(/(\d{4})(\d{1,4})$/, "$1-$2");
  }
  // (99) 99999-9999
  return d
    .replace(/^(\d{2})(\d)/, "($1) $2")
    .replace(/(\d{5})(\d{1,4})$/, "$1-$2");
}

export function maskCpfCnpj(v: string): string {
  const d = soDigitos(v).slice(0, 14);
  if (d.length <= 11) {
    // CPF: 999.999.999-99
    return d
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  }
  // CNPJ: 99.999.999/9999-99
  return d
    .replace(/(\d{2})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1/$2")
    .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}

export function maskCep(v: string): string {
  const d = soDigitos(v).slice(0, 8);
  return d.replace(/(\d{5})(\d{1,3})$/, "$1-$2");
}

/** CPF fixo (999.999.999-99) — para quando o tipo já foi escolhido antes
 * (ver Fazenda: pergunta CPF ou CNPJ, não deixa livre — SeletorTipoDocumento). */
export function maskCpf(v: string): string {
  const d = soDigitos(v).slice(0, 11);
  return d
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
}

/** CNPJ fixo (99.999.999/9999-99) — mesmo princípio de maskCpf. */
export function maskCnpj(v: string): string {
  const d = soDigitos(v).slice(0, 14);
  return d
    .replace(/(\d{2})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1/$2")
    .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}
