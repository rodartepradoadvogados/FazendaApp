"""
Teste-sentinela do item P2 #1 da auditoria de segurança de 02/09/2026
(docs/security-audit/achados.json) — trava a classe inteira de bug em vez de
só os ~30 pontos já corrigidos: uma rota POST que CRIA uma linha nova
(`session.add(...)`) mas resolve `fazenda_id` pela dependência TOLERANTE
`get_fazenda_atual_id` (pode vir `None` quando o token não tem "fid" — ex.:
sessão legada, Painel CowData) grava a linha nova com `fazenda_id=None`,
órfã de qualquer isolamento por fazenda. A dependência certa para escrita é
`get_fazenda_id_escrita` (nunca None em ambiente com fazenda provisionada —
ver `fazenda.auth.resolver_fazenda_id_escrita`).

Percorre toda `fazenda/api/routers/` (recursivo) via AST — não import, para
não precisar montar toda a aplicação nem um banco — e falha se achar uma
função decorada com `@router*.post(...)` que ao mesmo tempo (a) tem um
parâmetro `fazenda_id` cujo default é `Depends(get_fazenda_atual_id)` e (b)
chama `session.add(`/`.add_all(` em algum lugar do corpo (heurística de "cria
linha nova"). Toda rota nova cai automaticamente sob esta rede; toda exceção
legítima (endpoint de update/estorno que só citou "fazenda_id" de leitura,
não de criação) precisa entrar explicitamente em `_PERMITIDAS` abaixo, com
comentário explicando por quê — nunca em silêncio.
"""
from __future__ import annotations

import ast
from pathlib import Path

_DIR_ROUTERS = Path(__file__).resolve().parent.parent / "fazenda" / "api" / "routers"

# (arquivo relativo a fazenda/api/routers/, nome da função): motivo por que
# NÃO é uma falha de isolamento apesar de bater na heurística acima.
_PERMITIDAS: dict[tuple[str, str], str] = {
    ("assistente.py", "criar_ensinamento"): (
        "Módulo-piloto: fazenda_id=None documentado no próprio arquivo como "
        "'token de antes do piloto' — comportamento intencional, não bug."
    ),
    ("fazendas.py", "vincular_usuario"): (
        "O fazenda_id gravado vem do parâmetro de PATH {fazenda_id}, não da "
        "dependência tolerante (que aqui só delimita escopo de autorização)."
    ),
    ("sanidade.py", "criar_cronograma_manual"): (
        "CronogramaSanitario herda fazenda_id do CalendarioSanitario pai "
        "(calendario.fazenda_id), nunca da dependência injetada."
    ),
    ("cadastro/protocolos_sanitarios.py", "migrar_dose_protocolos_sanitarios"): (
        "Utilitário de backfill/relatório sobre linhas já existentes, não "
        "cria recurso novo por pedido do usuário."
    ),
    ("aprovacoes.py", "rejeitar"): "Ação de desfazer sobre LancamentoPendente existente — não cria nada.",
    ("aprovacoes.py", "desfazer"): "Idem — reversão de uma linha existente.",
    ("central_protocolos.py", "cancelar"): (
        "Estorno de um lançamento existente; os MovimentoEstoque compensatórios "
        "herdam fazenda_id do lançamento sendo cancelado, não da dependência."
    ),
    ("baixas.py", "marcar_a_descartar"): "Atualização em lote de Animal já existente.",
    ("estoque.py", "mesclar_itens_estoque"): "Mescla itens de Estoque já existentes, não cria item novo.",
    ("estoque.py", "restaurar_padrao_cowdata"): "Restaura valores em um item de Estoque já existente.",
    ("cadastro/animais.py", "renumerar_animal"): "Renomeia um Animal já existente.",
    ("reproducao.py", "enviar_ultimo_diagnostico"): "Só envia e-mail, não grava nada novo.",
    ("reproducao.py", "abrir_lactacao"): "Atualiza um Animal/Sanidade já existente.",
    ("reproducao.py", "registrar_diagnostico"): "Atualiza o Servico já existente com o resultado do diagnóstico.",
    ("reproducao.py", "registrar_reconfirmacao"): "Atualiza o Servico já existente.",
    ("reproducao.py", "registrar_perda_prenhez"): "Atualiza o Servico já existente.",
    ("cadastro/rh_folha.py", "simular_rescisao"): "Calculadora pura — o próprio docstring diz 'não grava nada'.",
    ("formulacao_dietas.py", "duplicar_simulacao"): (
        "A cópia é gravada com original.fazenda_id (fazenda da simulação "
        "sendo duplicada), não com o parâmetro tolerante — o próprio código "
        "já comenta que é de propósito, para não gerar cópia órfã quando "
        "quem duplica não tem fazenda selecionada no token."
    ),
}


# `async def` é FUNÇÃO DIFERENTE para o ast: `ast.AsyncFunctionDef` não é
# subclasse de `ast.FunctionDef`. Até set/2026 esta sentinela só olhava a
# segunda — 39 das 265 rotas POST do sistema (15%) passavam por baixo da rede
# em silêncio, exatamente as que fazem upload/webhook/importação. O verde delas
# não vinha de estarem certas: vinha de nunca terem sido olhadas.
_Rota = ast.FunctionDef | ast.AsyncFunctionDef
_TIPOS_ROTA = (ast.FunctionDef, ast.AsyncFunctionDef)


def _nome_dependencia(default: ast.expr) -> str | None:
    """Se `default` for `Depends(algo)`, devolve o nome de `algo`; senão None."""
    if not (isinstance(default, ast.Call) and isinstance(default.func, ast.Name) and default.func.id == "Depends"):
        return None
    if default.args and isinstance(default.args[0], ast.Name):
        return default.args[0].id
    return None


def _eh_rota_post(func: _Rota) -> bool:
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "post":
            return True
    return False


def _usa_fazenda_atual_id_tolerante(func: _Rota) -> bool:
    args = func.args
    defaults_por_arg = list(zip(args.args[len(args.args) - len(args.defaults):], args.defaults))
    defaults_por_arg += list(zip(args.kwonlyargs, args.kw_defaults or []))
    for arg, default in defaults_por_arg:
        if arg.arg == "fazenda_id" and default is not None and _nome_dependencia(default) == "get_fazenda_atual_id":
            return True
    return False


def _cria_linha_nova(func: _Rota) -> bool:
    """`session.add(Model(...))` (constrói e persiste um objeto NOVO) conta;
    `session.add(variavel_ja_existente)` (reanexar um objeto obtido via
    session.get/exec — padrão comum de update) não conta. `add_all([...])`
    conta se qualquer elemento da lista for uma construção de objeto novo."""
    for node in ast.walk(func):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr == "add" and node.args and isinstance(node.args[0], ast.Call):
            return True
        if node.func.attr == "add_all" and node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
            if any(isinstance(el, ast.Call) for el in node.args[0].elts):
                return True
    return False


def test_rota_post_que_cria_linha_usa_fazenda_id_escrita():
    violacoes = []
    # Contador de não-vacuidade: sem ele, esta sentinela passa VERDE se um dia
    # `_DIR_ROUTERS` apontar para o lugar errado (pasta movida/renomeada), se o
    # `rglob` não achar nada, ou se um refactor trocar a forma do decorador —
    # zero rota examinada, zero violação, tudo azul. A asserção no fim exige que
    # ela tenha REALMENTE olhado a família de rotas que promete cobrir.
    rotas_post_examinadas = 0
    for arquivo in sorted(_DIR_ROUTERS.rglob("*.py")):
        caminho_relativo = arquivo.relative_to(_DIR_ROUTERS).as_posix()
        if "painel_cowdata" in caminho_relativo:
            # Catálogos globais do Painel CowData — operam sem fazenda
            # específica de propósito (não são rotas de fazenda-cliente).
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for node in ast.walk(arvore):
            if not isinstance(node, _TIPOS_ROTA) or not _eh_rota_post(node):
                continue
            rotas_post_examinadas += 1
            if not _usa_fazenda_atual_id_tolerante(node):
                continue
            if not _cria_linha_nova(node):
                continue
            chave = (caminho_relativo, node.name)
            if chave in _PERMITIDAS:
                continue
            violacoes.append(f"{caminho_relativo}:{node.lineno} {node.name}()")

    # Piso deliberadamente folgado (o sistema tem ~265 rotas POST hoje): não é
    # para travar contagem, é para acusar "não examinei nada" e "de repente
    # examinei um punhado".
    assert rotas_post_examinadas > 150, (
        f"a varredura examinou só {rotas_post_examinadas} rotas POST em {_DIR_ROUTERS} — "
        "esta sentinela está passando por não ter olhado nada, não por estar tudo certo. "
        "Confira o caminho de _DIR_ROUTERS e a heurística de _eh_rota_post."
    )

    assert not violacoes, (
        "Rota(s) POST que criam linha nova usando a dependência TOLERANTE "
        "get_fazenda_atual_id em vez de get_fazenda_id_escrita (ver "
        "docs/security-audit/achados.json, P2 #1). Troque a dependência, ou "
        "se for um falso positivo (a rota não cria nada novo de verdade, ou "
        "herda fazenda_id de outro lugar), adicione a exceção com motivo em "
        "_PERMITIDAS neste arquivo:\n  " + "\n  ".join(violacoes)
    )
