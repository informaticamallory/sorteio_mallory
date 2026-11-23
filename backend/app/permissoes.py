"""Perfis de acesso (RBAC).

Fonte unica de verdade sobre o que cada papel pode fazer. As rotas declaram a
permissao que exigem via `deps.requer` / `deps.exigir_permissao`; nunca
comparam papeis diretamente, para que mudar a politica seja editar apenas este
arquivo. tests/test_acesso.py confere a matriz rota a rota.

Decisao registrada: ANULAR_RESULTADO e so do ADMIN, como pede a especificacao
("o operador nao pode alterar resultados"). Consequencia pratica: com a regra
"ausente -> anula e sorteia de novo", o operador precisa de um admin a cada
ausencia. Para liberar, acrescente ANULAR_RESULTADO ao papel SORTEIO.
"""

from __future__ import annotations

import enum

from .models import Papel


class Permissao(str, enum.Enum):
    # Leitura basica do evento (nome, regras, resumo), comum a equipe interna.
    VISUALIZAR_EVENTO = "visualizar_evento"
    # Administracao. GERENCIAR_EVENTOS = criar eventos (configuracao global);
    # CONFIGURAR_EVENTO = configurar o evento (identidade, cadastro, QR, telao).
    GERENCIAR_EVENTOS = "gerenciar_eventos"
    CONFIGURAR_EVENTO = "configurar_evento"
    GERENCIAR_USUARIOS = "gerenciar_usuarios"
    GERENCIAR_PARTICIPANTES = "gerenciar_participantes"
    CADASTRAR_PREMIOS = "cadastrar_premios"
    CONFIGURAR_BLOCOS = "configurar_blocos"
    DEFINIR_REGRAS = "definir_regras"
    ANULAR_RESULTADO = "anular_resultado"
    CONSULTAR_RELATORIOS = "consultar_relatorios"
    EXPORTAR_RESULTADOS = "exportar_resultados"
    VISUALIZAR_AUDITORIA = "visualizar_auditoria"
    # Operacao do sorteio
    VISUALIZAR_BLOCOS = "visualizar_blocos"
    CONTROLAR_SORTEIO = "controlar_sorteio"
    CONTROLAR_TELAO = "controlar_telao"
    CONSULTAR_RESULTADOS = "consultar_resultados"
    # Sortear um premio do bloco fora da sequencia definida (com motivo,
    # registrado na auditoria). So o ADMIN.
    PULAR_ORDEM_DO_BLOCO = "pular_ordem_do_bloco"
    # Recepcao
    PESQUISAR_COLABORADORES = "pesquisar_colaboradores"
    CONFIRMAR_ENTREGA = "confirmar_entrega"
    # Desfazer uma entrega confirmada (sempre com justificativa).
    DESFAZER_ENTREGA = "desfazer_entrega"
    CONSULTAR_ATENDIMENTOS = "consultar_atendimentos"
    # Credenciamento
    ACOMPANHAR_CREDENCIAMENTO = "acompanhar_credenciamento"
    AUXILIAR_CREDENCIAMENTO = "auxiliar_credenciamento"
    # Colaborador: somente os proprios dados
    ACESSAR_AREA_PESSOAL = "acessar_area_pessoal"


PERMISSOES_POR_PAPEL: dict[Papel, frozenset[Permissao]] = {
    Papel.ADMIN: frozenset(Permissao),
    Papel.SORTEIO: frozenset(
        {
            Permissao.VISUALIZAR_EVENTO,
            Permissao.VISUALIZAR_BLOCOS,
            Permissao.CONTROLAR_SORTEIO,
            Permissao.CONTROLAR_TELAO,
            Permissao.CONSULTAR_RESULTADOS,
        }
    ),
    # Organizador - RH: responsavel pela confraternizacao. Configura o evento
    # (nao cria eventos), participantes, premios, blocos, regras, credenciamento,
    # entregas (inclusive desfazer, com justificativa) e relatorios. Usuarios,
    # anulacao de resultado e auditoria ficam so com o ADMIN. Sortear, so com
    # a autorizacao da conta (User.pode_sortear): ver permissoes_do_usuario.
    Papel.ORGANIZADOR: frozenset(
        {
            Permissao.VISUALIZAR_EVENTO,
            Permissao.CONFIGURAR_EVENTO,
            Permissao.GERENCIAR_PARTICIPANTES,
            Permissao.CADASTRAR_PREMIOS,
            Permissao.CONFIGURAR_BLOCOS,
            Permissao.VISUALIZAR_BLOCOS,
            Permissao.DEFINIR_REGRAS,
            Permissao.CONSULTAR_RELATORIOS,
            Permissao.EXPORTAR_RESULTADOS,
            Permissao.CONSULTAR_RESULTADOS,
            Permissao.PESQUISAR_COLABORADORES,
            Permissao.CONFIRMAR_ENTREGA,
            Permissao.DESFAZER_ENTREGA,
            Permissao.CONSULTAR_ATENDIMENTOS,
            Permissao.ACOMPANHAR_CREDENCIAMENTO,
            Permissao.AUXILIAR_CREDENCIAMENTO,
        }
    ),
    # Recepcao: o check-in e a consulta do numero sao publicos (/recepcao);
    # com a conta, tambem acompanha o credenciamento e vincula pulseiras.
    Papel.RECEPCAO: frozenset(
        {
            Permissao.VISUALIZAR_EVENTO,
            Permissao.ACOMPANHAR_CREDENCIAMENTO,
            Permissao.AUXILIAR_CREDENCIAMENTO,
        }
    ),
    # Equipe de Entregas: Central de Entregas (localizar, confirmar, historico).
    # Nao desfaz entregas, nao mexe em sorteios nem em usuarios.
    Papel.ENTREGAS: frozenset(
        {
            Permissao.VISUALIZAR_EVENTO,
            Permissao.PESQUISAR_COLABORADORES,
            Permissao.CONFIRMAR_ENTREGA,
            Permissao.CONSULTAR_ATENDIMENTOS,
        }
    ),
    Papel.COLABORADOR: frozenset({Permissao.ACESSAR_AREA_PESSOAL}),
}

# O que a autorizacao "pode operar sorteios" acrescenta a um Organizador - RH.
PERMISSOES_DE_SORTEIO = frozenset({Permissao.CONTROLAR_SORTEIO, Permissao.CONTROLAR_TELAO})

# Quem e da equipe tambem pode ser participante (ex.: colaborador do RH
# promovido a Organizador): continua vendo o PROPRIO cartao, premios e avisos.
# A area pessoal so mostra os cadastros ligados a conta logada.
for _papel in (Papel.SORTEIO, Papel.ORGANIZADOR, Papel.RECEPCAO, Papel.ENTREGAS):
    PERMISSOES_POR_PAPEL[_papel] = PERMISSOES_POR_PAPEL[_papel] | {Permissao.ACESSAR_AREA_PESSOAL}


def permissoes_do_papel(papel: str) -> frozenset[Permissao]:
    """Papel desconhecido (ex.: valor corrompido) nao recebe permissao alguma."""
    try:
        return PERMISSOES_POR_PAPEL[Papel(papel)]
    except ValueError:
        return frozenset()


def permissoes_do_usuario(user) -> frozenset[Permissao]:  # noqa: ANN001
    """Permissoes efetivas da conta: as do perfil + a autorizacao para sortear."""
    base = permissoes_do_papel(user.papel)
    if user.papel == Papel.ORGANIZADOR.value and getattr(user, "pode_sortear", False):
        return base | PERMISSOES_DE_SORTEIO
    return base


def tem_permissao(papel_ou_usuario, *necessarias: Permissao) -> bool:  # noqa: ANN001
    """Aceita a conta (User) ou so o papel (texto)."""
    concedidas = (
        permissoes_do_papel(papel_ou_usuario)
        if isinstance(papel_ou_usuario, str)
        else permissoes_do_usuario(papel_ou_usuario)
    )
    return all(p in concedidas for p in necessarias)


def tem_alguma_permissao(papel_ou_usuario, *opcoes: Permissao) -> bool:  # noqa: ANN001
    concedidas = (
        permissoes_do_papel(papel_ou_usuario)
        if isinstance(papel_ou_usuario, str)
        else permissoes_do_usuario(papel_ou_usuario)
    )
    return any(p in concedidas for p in opcoes)


# Contas da equipe do evento. COLABORADOR fica de fora: so ve a propria area.
PAPEIS_INTERNOS = frozenset(
    {Papel.ADMIN, Papel.SORTEIO, Papel.ORGANIZADOR, Papel.RECEPCAO, Papel.ENTREGAS}
)
