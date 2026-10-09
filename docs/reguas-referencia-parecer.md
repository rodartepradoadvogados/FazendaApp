# Réguas de referência — requisitos do parecer jurídico (backend)

Parecer de 08/10/2026 sobre Relatórios › Réguas de referência. **O parecer não foi validado em fonte
oficial e os termos de várias fontes não foram verificados:** nada aqui vai ao ar para clientes sem a
validação do dono e do Alexandre Scarpa. O backend garante isso sozinho: o interruptor geral nasce
desligado e nenhuma régua é publicável hoje.

Arquivos:

| O quê | Onde |
|---|---|
| Faixas, fontes, dossiê, interruptores | `backend/fazenda/seed_data/reguas_referencia.json` |
| Textos versionados (alerta 7.1, modal 7.2, rodapé 7.5, autorização 6.2, botão 7.7, aceite 7.6) e bloco `empresa` | `backend/fazenda/seed_data/textos_juridicos.json` |
| Validador, situação de cada régua, carga pública | `backend/fazenda/rules/reguas_referencia.py` |
| Render e hash dos textos | `backend/fazenda/rules/textos_juridicos.py` |
| Aceites | `backend/fazenda/rules/aceites.py`, `api/routers/aceites.py` |
| Exportação | `api/routers/exportacoes_relatorio.py` |
| Operador (Painel CowData) | `api/routers/painel_cowdata_reguas.py` |
| Tabelas (append-only) | `backend/fazenda/models/juridico.py`, migração `c6f2a9d4e817` |
| Rotina mensal e checklist de lançamento | `docs/agents/reguas-referencia-mensal.md` |

## Quando uma régua vai ao ar

`situacao = "publicada"` só quando TUDO vale (ver docstring de `rules/reguas_referencia.py`):
interruptor geral `publicacao.liberada` + empresa constituída; régua `ativa`; faixa por desenho; uma fonte
nacional e uma internacional **ativas**; nada vencido (12 meses); dossiê completo com independência "sim";
dupla validação (pessoa diferente de quem compilou, sobre a mesma faixa, `pendente_de` vazio); termos
verificados no dossiê e em CADA fonte ativa (`termos_verificados_em` e `uso_comercial_confirmado_em`).
Fonte marcada `corroboracao_apenas` (parecer 3.3) não serve de base do dossiê.

Situações: `publicada` | `em_validacao` (falta algo do dossiê, da validação, dos termos ou da liberação)
| `retirada` (interruptor da régua, fonte desligada, perdeu um dos lados, ou perdeu a fonte base do dossiê)
| `vencida` | `sem_faixa` (a régua não tem faixa por desenho ou não tem os dois lados).

## Contratos para o front

Todas as rotas exigem login e fazenda selecionada (salvo as do Painel CowData). Datas `*_utc` em ISO-8601
com `Z`.

### `GET /financeiro/reguas-referencia`
```jsonc
{
  "versao": "2026-10", "versao_reguas": "2026-10 (revisada em 08/10/2026)",
  "revisado_em": "...", "conferida_em": "...", "valido_ate": "...", "proxima_conferencia": "...",
  "vencida": false,
  "publicacao": {"liberada": false},          // efetivo (já considera empresa pendente)
  "empresa_pendente": true,
  "aceite": {"tipo": "reguas", "versao": "1", "sha256": "…", "pendente": true, "aceito_em_utc": null},
  "aceite_pendente": true,                    // mostrar o modal "Entendi" (textos.modal) antes de tudo
  "faixas_ocultas_ate_aceite": true,          // enquanto pendente, NENHUMA faixa vem, mesmo publicada
  "textos": {
    "alerta":  {"chave","versao","vigente_desde","texto","sha256","aceite":null,...},   // caixa do topo (7.1)
    "modal":   {..., "texto", "sha256", "botao": "Entendi", "disponivel_para_aceite": true},  // pop-up (7.2)
    "compartilhamento_parametro": {...},      // rótulo do parâmetro (7.7), 2 linhas
    "rodape_exportacao": {...},               // MODELO com {{marcadores}}; o preenchido vem do POST de exportação
    "exportacao_autorizacao": {...}           // "Autorizo o envio deste relatório a {{destinatario}}."
  },
  "reguas": [{
    "codigo", "nome", "unidade", "definicao_cowdata",
    "situacao": "publicada|em_validacao|retirada|vencida|sem_faixa",
    "publicavel": false,                      // pronta para ir ao ar (falta só a liberação geral)
    "exibir_faixa": false,
    // só quando situacao == "publicada" e sem aceite pendente; senão null / []:
    "faixa": null, "fidedignidade": null, "ressalva": null, "compilado_em": null, "vence_em": null,
    "fontes": []                              // [{id, nome, ano, url, origem}] — quadro de fontes, sem logos
  }]
}
```
Também na resposta: `"exportacao": {"permitir_com_reguas": bool}` (o parâmetro 6.2 da fazenda, para a
tela saber se oferece "exportar com réguas" ou só "exportar sem réguas").

### `GET /financeiro/reguas-referencia/indicadores-fazenda`
`?data_inicio=&data_fim=&regime=competencia|caixa&centro_custo=&hoje=` → o número da FAZENDA de cada régua,
tirado das mesmas linhas da DRE e do Resultado por litro do servidor (e do saldo de hoje do Caixa real, só
para administrador): `{indicadores: {codigo: {valor|null, conta|null, relatorio|null, motivo|null}}}`.
`conta` é a divisão escrita com os dois números em R$; `relatorio` é o id da árvore de Relatórios que explica
o número; `motivo` diz por que não há número. Nenhuma faixa sai daqui (`rules/reguas_indicadores.py`).

Texto do alerta/modal: exibir **exatamente** `texto` (quebras de linha `\n`). Sem semáforo, sem
"acima/abaixo da média": faixa cinza neutra e a palavra "referência" (parecer 6.3).

### Modal "Entendi" (6.1.3)
- `GET /financeiro/reguas-referencia/aceite` → `{texto: {...modal}, tipo, versao, sha256, pendente, aceito_em_utc}`.
- `POST /financeiro/reguas-referencia/aceite` `{versao, sha256}` → 201 com o registro. **409** se a versão
  ou o hash não forem os vigentes (texto mudou: recarregue e mostre de novo). Reexibir sempre que
  `aceite_pendente` voltar a `true` (texto novo = hash novo).
- Aceite é por usuário **e** por fazenda. O contador também registra (rota sem a trava de escrita dele).

### Aceites genéricos (6.1)
- `GET /aceites/vigentes` → `{geral, clausula, reguas}`, cada um com `texto, versao, sha256,
  disponivel_para_aceite, pendente, pendente_para_mim`.
- `POST /aceites` `{tipo: "geral"|"clausula"|"reguas", versao, sha256}` → 201. `geral`/`clausula`: **409**
  enquanto os Termos de Uso não existirem (empresa).
- `GET /aceites/comprovante[?usuario_id=&baixar=true]` → comprovante JSON (o próprio usuário; outro
  usuário só para admin, e só da mesma fazenda). `baixar=true` manda como arquivo.
- Registro: usuário, fazenda, tipo, chave e versão do texto, SHA-256, IP (entrada mais à direita do
  `X-Forwarded-For`), user-agent (até 512), `criado_em` UTC. Tabela `aceite_termos` append-only: o ORM
  recusa UPDATE/DELETE e um gatilho no banco barra até SQL cru.

### Exportação/compartilhamento (6.2)
- Parâmetro da fazenda `permitir_exportar_com_reguas` (bool, **padrão false**), editado só por admin em
  `PUT /parametros/permitir_exportar_com_reguas` `{valor: true}`. O Painel CowData não aplica em massa (403).
- `POST /relatorios/exportacoes` — chamar ANTES de gerar o arquivo/link:
  ```json
  {"relatorio": "dre", "formato": "pdf|xlsx|csv|link", "com_reguas": true,
   "destinatario": "Banco X", "destinatario_tipo": "banco|contador|comprador|outro",
   "finalidade": "Pedido de crédito", "autorizacao_confirmada": true}
  ```
  Respostas: **201** `{id, ..., versao_reguas, rodape: {versao, texto, sha256} | null}`; **403** parâmetro
  desligado (oferecer "exportar sem réguas"); **400** sem destinatário, finalidade ou confirmação; **409**
  aceite das réguas pendente ou nenhuma régua publicada. `com_reguas: false` sempre passa (e é registrado).
  O `rodape.texto` (7.5) vai **no mesmo bloco da régua**, sem opção de remover. Sem link público
  permanente, sem marca d'água de "certificado".
- `GET /relatorios/exportacoes[?limite=]` → log da fazenda (admin). Tabela `exportacao_relatorio_log`,
  append-only.

### Reportar erro (6.3/7.4)
- `POST /financeiro/reguas-referencia/reportar-erro` `{regua_codigo, texto (3–1000)}` → 201
  `{id, status: "aberto", versao_reguas, criado_em_utc}`; 404 régua inexistente.
- Operador: `GET /painel-cowdata/reguas-referencia/erros[?status=]` (área "produto"),
  `PATCH /painel-cowdata/reguas-referencia/erros/{id}` `{status: em_analise|resolvido|descartado, resposta}`
  (dono-equivalente). Também: `GET /painel-cowdata/reguas-referencia/diagnostico` (o que falta para cada
  régua ir ao ar) e `GET /painel-cowdata/reguas-referencia/aceites/comprovante?usuario_id=&fazenda_id=`
  (dono-equivalente).

## Decisões
- Os textos ficam num arquivo próprio (`textos_juridicos.json`), fora do JSON das faixas: a rotina mensal
  edita as faixas e nunca toca nos textos. Mudar um texto exige subir a versão e o `sha256_modelo` (o teste
  recusa texto alterado sem versão nova) e mover a anterior para `historico`.
- Hash = SHA-256 do texto **renderizado** e normalizado (NFC, `\n`, sem espaço no fim das linhas). Por
  isso preencher a empresa ou passar a valer o trecho do método muda o hash e pede aceite novo.
- O trecho "Mostramos uma faixa quando pelo menos uma fonte brasileira e uma estrangeira…" entra no
  modal só quando há régua publicada (toda régua publicada tem, por definição, o dossiê que o comprova).
- Enquanto o aceite está pendente, a API não manda faixa nenhuma (defesa além da tela).
- Fora de `publicada`, a API também não manda `ressalva` nem `fontes`: várias ressalvas citam números das
  fontes (faixas disfarçadas). O teste varre a resposta atrás dos números das faixas.
- Aceites, exportações e reportes ficam fora da cópia para a Fazenda Teste (`replicacao_fazenda.py`):
  são prova/fila, não dado da fazenda.
- Nomes de fonte sem "Cepea" (parecer 9.3); validador recusa.

## Pendências humanas (não resolvidas por código)
1. **Empresa:** preencher `empresa` em `textos_juridicos.json` (razão social, CNPJ, e-mail do responsável).
   Sem isso a liberação é recusada pelo validador.
2. **Termos das fontes:** cada fonte com `termos_verificados_em` e `uso_comercial_confirmado_em` (com PDF/print
   datado guardado fora do repositório). CNA por escrito; Anuário Leite: autorização; NW Farm Credit: excluir
   ou autorizar.
3. **Dupla validação** do dono e do Alexandre Scarpa em cada dossiê (`validado_por` com a faixa validada;
   `pendente_de: []`); completar `pagina_ou_tabela` onde está `null`.
4. **Clickwrap geral** (aceite dos Termos no cadastro e cláusula em destaque): a infraestrutura está pronta
   (`tipo` "geral"/"clausula"), mas os Termos de Uso e a Política de Privacidade dependem da empresa. Quando
   existirem: texto em `textos_juridicos.json` (tirar `pendente`, preencher `{{versao_termos}}`,
   `{{data_termos}}`, `{{clausula}}`) e a tela de cadastro passa a exigir o aceite. E-mail de confirmação
   com cópia dos Termos (6.1.4) também fica para essa etapa.
5. **Liberação:** só depois do checklist do item 10 (ver `docs/agents/reguas-referencia-mensal.md`).
