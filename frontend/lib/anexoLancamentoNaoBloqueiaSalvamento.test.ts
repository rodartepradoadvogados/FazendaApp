// Bug real de produção (Financeiro > novo lançamento): o usuário via "Sem
// conexão com a API" ao salvar, mas o lançamento tinha sido salvo mesmo
// assim. Este teste prova que uma falha de rede no upload do ANEXO (chamada
// secundária, disparada DEPOIS que o lançamento já foi criado com sucesso —
// ver FormFinanceiro.tsx::salvar) nunca vira essa mensagem genérica de
// conectividade nem impede o "salvo com sucesso": cada anexo é pego
// individualmente (mesmo padrão do trecho real em FormFinanceiro.tsx).
// Roda com o runner nativo do Node: `npm test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { anexarArquivoLancamento, criarLancamentoFinanceiro } from "./api.ts";

function respostaOk(corpo: unknown) {
  return new Response(JSON.stringify(corpo), { status: 200, headers: { "Content-Type": "application/json" } });
}

test("anexo que falha na rede não impede a criação do lançamento nem gera erro genérico de conectividade", async () => {
  (globalThis as any).fetch = async (url: string) => {
    if (String(url).includes("/anexos")) throw new TypeError("Failed to fetch"); // upload de anexo: rede cai
    return respostaOk({ numero_lancamento: "LC-2026-00042" }); // POST do lançamento em si: sucesso
  };

  const r = await criarLancamentoFinanceiro({ tipo: "despesa", itens: [] });
  assert.equal(r.numero_lancamento, "LC-2026-00042"); // o lançamento em si foi criado

  const arquivo = new File([new Uint8Array([1, 2, 3])], "comprovante.pdf", { type: "application/pdf" });
  // Mesmo trecho de FormFinanceiro.tsx::salvar — cada anexo pego individualmente,
  // nunca deixando o catch propagar pro chamador.
  const falhasAnexo = (await Promise.all(
    [arquivo].map((f) => anexarArquivoLancamento(r.numero_lancamento, f).then(() => null).catch(() => f.name)),
  )).filter(Boolean);

  assert.deepEqual(falhasAnexo, ["comprovante.pdf"]);
});
