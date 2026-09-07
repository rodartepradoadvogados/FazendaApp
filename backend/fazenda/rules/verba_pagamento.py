"""
Quais verbas do holerite podem ser alteradas NO ATO DO PAGAMENTO, sob que
condição, e o que a lei não deixa alterar de jeito nenhum.

O PEDIDO DO DONO, na íntegra do sentido: o pop-up de pagar a folha ganha uma
coluna de edição com DOIS estados por verba. Nas editáveis (vales,
bonificações, vale-transporte) a palavra "Editar". Nas demais — INSS, IR,
salário e as verbas salariais ou indenizatórias — um CADEADO. O cadeado NÃO
bloqueia: clicado, abre um aviso de que alterar aquele valor "será tido como
alteração daquele momento em diante" e pergunta se tem certeza; confirmando, a
edição é permitida. Salário para MAIOR avisa que aquele passa a ser o novo
salário daquele momento em diante. Salário para MENOR é recusado, e só.

POR QUE ESTAS REGRAS MORAM NUM MÓDULO PURO. Elas são aplicadas duas vezes: na
tela (`frontend/lib/pagamentoFolhaRegras.ts`, que desenha "Editar" ou o
cadeado e recusa antes de mandar) e no servidor (`rh_folha_pagar.py`, que
recusa de novo, porque nenhuma dessas travas pode existir só no navegador). O
único jeito de os dois lados não discordarem é a régua ser explícita, escrita
uma vez de cada lado e testada nos dois — e é por isso que as MENSAGENS
literais também vivem aqui: a recusa do salário menor tem que sair com o mesmo
texto na tela e no 400 do servidor.

O QUE ESTE MÓDULO NÃO DECIDE: o destino da diferença de uma parcela de vale
(abater / desconsiderar / reparcelar / acréscimo avulso). Essa régua é a do
PR #708 e continua em `rh_vale_acoes.py` — aqui só se decide QUEM pode ser
editado, nunca o que acontece com uma dívida.

Sem I/O e sem sessão: quem chama carrega os objetos e passa os números.
Ver `backend/tests/test_folha_pagar_edicao_verba.py`.
"""
from __future__ import annotations

from fazenda.rules.rubrica_folha import (
    ALTERACAO_LIVRE,
    CATALOGO_DESCONTOS,
    CATALOGO_VENCIMENTOS,
    ESPECIE_VENCIMENTO,
)

# Meio centavo: abaixo disso, dois valores em reais são o mesmo valor. Mesma
# tolerância de `rh_folha_pagar.CENTAVO` e de `pagamentoFolhaRegras.ts` — sem
# ela, um arredondamento de exibição viraria "alteração de salário".
CENTAVO = 0.005

# ── As três classes de verba, do ponto de vista da COLUNA DE EDIÇÃO ──
#
# São três e não dois porque o salário, embora apareça na tela com o mesmo
# cadeado das demais contratuais, tem regra PRÓPRIA depois da confirmação:
# para maior vira aumento incorporado, para menor é recusado. Fundir as duas
# classes obrigaria cada chamador a lembrar do caso especial — e esquecer
# significaria deixar passar redução de salário.
CLASSE_LIVRE = "livre"            # mostra "Editar"
CLASSE_CONTRATUAL = "contratual"  # mostra cadeado; edita depois de confirmar
CLASSE_SALARIO = "salario"        # cadeado + as regras de maior/menor

# A classe das linhas FIXAS do holerite — as que não são rubrica de catálogo
# (ver `rules/holerite.py::ORDEM_TIPOS` e `_detalhe_folha`).
#
#   bruto  → é o salário do mês. Alterá-lo é alterar o contrato (art. 468).
#   inss   → valor retido do empregado e recolhido ao INSS: quem determina não
#   ir       é a fazenda, é a lei. Mexer é declarar retenção diferente da
#            apurada — cadeado, com confirmação, nunca proibição (o valor
#            informado à mão pelo contador já é um caminho previsto no modelo,
#            ver `referencia_retencao`).
#   vale   → dívida da PESSOA, com cronograma próprio. Quanto foi descontado
#            neste mês é medição, não promessa: "Editar". É a única linha cuja
#            diferença abre as decisões do vale.
#   outros → `FolhaPagamento.descontos`, o desconto manual sem itemização.
#            Também é medição do mês: "Editar".
#
# `liquido` e `vale_assumido` não entram de propósito: o primeiro é o TOTAL do
# recibo (não é verba, e editá-lo seria editar a soma das outras); o segundo
# nem viaja dentro de `detalhe` — é a parcela que a fazenda assumiu, que não é
# descontada de ninguém.
CLASSE_POR_TIPO_DE_LINHA: dict[str, str] = {
    "bruto": CLASSE_SALARIO,
    "inss": CLASSE_CONTRATUAL,
    "ir": CLASSE_CONTRATUAL,
    "vale": CLASSE_LIVRE,
    "outros": CLASSE_LIVRE,
}

# ── As mensagens literais, palavra por palavra como o dono as escreveu ──
#
# Ficam aqui, e não soltas no endpoint, porque a MESMA frase precisa sair na
# tela (antes de mandar) e no corpo do 400 (quando alguém manda mesmo assim,
# por fora da tela). Duas cópias divergentes seriam duas recusas diferentes
# para o mesmo fato.
MENSAGEM_SALARIO_MENOR = (
    "O valor informado é inferior ao salário do funcionário. "
    "Não é permitida a alteração contratual lesiva."
)
# A observação em itálico e letra menor do mesmo pop-up: o caminho de fazer a
# redução onde ela É possível. Existe porque uma recusa sem saída manda o
# usuário procurar no escuro — e a redução de salário, quando é legítima
# (acordo coletivo, art. 7º, VI, da Constituição), se faz no cadastro, não no
# ato de pagar um mês.
NOTA_SALARIO_MENOR = (
    "a alteração do salário do funcionário para o valor informado deverá ser feita "
    "diretamente em Administração > Configurações > Cadastro > Pessoas > "
    "Editar cadastro do funcionário > Salário-base (R$)."
)

# Confirmação exigida do cadeado: a tela abre o pop-up, o servidor exige a
# marca de que ele foi confirmado. Não é enfeite — é a diferença entre uma
# alteração contratual assumida e um número trocado sem querer num campo.
MENSAGEM_SEM_CONFIRMACAO = (
    "Esta verba só pode ser alterada com confirmação: a alteração vale daquele momento "
    "em diante. Confirme no aviso do cadeado antes de pagar."
)


def classe_da_linha(tipo: str) -> str | None:
    """A classe de uma linha FIXA do holerite; None quando a linha não é verba
    editável (líquido, e qualquer tipo novo que apareça no futuro — o padrão é
    não deixar editar o que este módulo não conhece)."""
    return CLASSE_POR_TIPO_DE_LINHA.get(tipo)


def classe_da_rubrica(codigo: str, especie: str) -> str:
    """A classe de uma rubrica avulsa, lida do catálogo (`alteracao`).

    Código desconhecido cai em CONTRATUAL: o lado seguro de uma verba que
    este catálogo não reconhece é pedir confirmação, nunca liberar em
    silêncio."""
    catalogo = CATALOGO_VENCIMENTOS if especie == ESPECIE_VENCIMENTO else CATALOGO_DESCONTOS
    verbete = catalogo.get(codigo, {})
    return CLASSE_LIVRE if verbete.get("alteracao") == ALTERACAO_LIVRE else CLASSE_CONTRATUAL


def exige_confirmacao(classe: str) -> bool:
    """Só a verba LIVRE dispensa o aviso do cadeado."""
    return classe != CLASSE_LIVRE


def mesma_quantia(a: float, b: float) -> bool:
    return abs(round(a, 2) - round(b, 2)) <= CENTAVO


def direcao_do_salario(previsto: float, informado: float) -> str:
    """"igual" | "maior" | "menor" — qual dos três pop-ups do salário abre.

    A comparação é contra o BRUTO DESTE MÊS (`FolhaPagamento.valor_bruto`), e
    não contra `Pessoa.salario_base`, porque é o bruto que está escrito na
    linha que o usuário está editando. Quando os dois divergem (mês de
    admissão proporcional, folha ajustada à mão), o aumento não é gravado —
    ver `pode_virar_novo_salario`."""
    if mesma_quantia(previsto, informado):
        return "igual"
    return "maior" if informado > previsto else "menor"


def pode_virar_novo_salario(valor_bruto_da_folha: float, salario_base_da_pessoa: float | None) -> bool:
    """
    O aumento digitado no ato do pagamento só pode virar NOVO SALÁRIO quando o
    bruto deste mês é o salário do cadastro.

    POR QUE ESTA TRAVA EXISTE, e por que ela não é preciosismo. O aumento é
    gravado como a DIFERENÇA entre o que foi digitado e o bruto da folha, e é
    essa mesma diferença que `_propagar_aumento` soma a `Pessoa.salario_base`.
    Isso só fecha enquanto os dois pontos de partida são o mesmo número. No
    mês de admissão, por exemplo, o bruto é proporcional (R$ 1.500 de um
    salário de R$ 3.000): digitar R$ 1.800 ali significa "pagar R$ 300 a mais
    NESTE mês", e somar R$ 300 ao salário do cadastro transformaria um ajuste
    de proporcionalidade num aumento permanente de salário que ninguém
    concedeu. Sem uma tabela de histórico de salário — que o modelo não tem —
    não há como distinguir os dois casos, e a saída honesta é recusar com
    explicação em vez de gravar um contrato que não existiu.
    """
    if salario_base_da_pessoa is None:
        return False
    return mesma_quantia(valor_bruto_da_folha, salario_base_da_pessoa)


MENSAGEM_SALARIO_SEM_REFERENCIA = (
    "O salário desta competência ({bruto}) é diferente do salário-base cadastrado do "
    "funcionário ({base}) — pode ser mês de admissão ou folha ajustada à mão. Não dá para "
    "deduzir daqui qual seria o novo salário sem inventar um número. Altere o salário-base em "
    "Administração > Configurações > Cadastro > Pessoas e lance o que faltar neste mês como "
    "vencimento avulso."
)
