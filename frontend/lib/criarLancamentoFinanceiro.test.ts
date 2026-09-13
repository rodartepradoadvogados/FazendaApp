// Testes de frontend/lib/api.ts::criarLancamentoFinanceiro — bug real de
// produção: "Sem conexão com a API" aparecia ao salvar um lançamento
// financeiro que, na verdade, TINHA sido salvo (a resposta que se perdeu no
// caminho de volta, não o POST em si — ver Idempotency-Key no backend).
// Roda com o runner nativo do Node (sem depender de jest/vitest, que o
// projeto não tem instalado): `npm test` (ver script em package.json).
import { test } from "node:test";
import assert from "node:assert/strict";
import { criarLancamentoFinanceiro } from "./api.ts";

function respostaOk(corpo: unknown) {
  return new Response(JSON.stringify(corpo), { status: 200, headers: { "Content-Type": "application/json" } });
}

test("criarLancamentoFinanceiro: sobrevive a 2 falhas de rede seguidas se a 3ª tentativa emplacar", async () => {
  let chamadas = 0;
  const chavesUsadas: string[] = [];
  (globalThis as any).fetch = async (_url: string, opts: any) => {
    chamadas++;
    chavesUsadas.push(opts.headers.get("Idempotency-Key"));
    if (chamadas < 3) throw new TypeError("Failed to fetch"); // mesmo erro que fetch lança sem resposta HTTP
    return respostaOk({ numero_lancamento: "LC-2026-00099" });
  };

  const resultado = await criarLancamentoFinanceiro({ tipo: "despesa", itens: [] });
  assert.equal(resultado.numero_lancamento, "LC-2026-00099");
  assert.equal(chamadas, 3);
  // Mesma chave em todas as tentativas — é isso que permite ao backend
  // reconhecer a repetição e devolver o lançamento já criado em vez de duplicar.
  assert.equal(new Set(chavesUsadas).size, 1);
});

test("criarLancamentoFinanceiro: continua reportando falha real quando NENHUMA tentativa emplaca", async () => {
  (globalThis as any).fetch = async () => { throw new TypeError("Failed to fetch"); };

  await assert.rejects(
    () => criarLancamentoFinanceiro({ tipo: "despesa", itens: [] }),
    (e: any) => {
      assert.match(e.message, /Sem conexão com a API/);
      return true;
    },
  );
});

test("criarLancamentoFinanceiro: sem nenhuma falha de rede, faz só 1 tentativa", async () => {
  let chamadas = 0;
  (globalThis as any).fetch = async () => { chamadas++; return respostaOk({ numero_lancamento: "LC-2026-00100" }); };

  const resultado = await criarLancamentoFinanceiro({ tipo: "despesa", itens: [] });
  assert.equal(resultado.numero_lancamento, "LC-2026-00100");
  assert.equal(chamadas, 1);
});
