"""Gerenciamento de usuarios (somente ADMIN).

Regras:
  * so se exclui conta SEM historico operacional (nao sorteou, entregou,
    anulou, finalizou bloco, mudou regra nem fez nenhuma acao de gestao);
    as demais sao desativadas, preservando o historico. Os registros pessoais
    da conta excluida (login, troca de senha, autocadastro...) ficam na
    auditoria com o usuario anotado nos detalhes;
  * o admin nunca define nem ve a senha definitiva de outra pessoa: o sistema
    gera uma senha temporaria, exibida uma unica vez, que precisa ser trocada
    no primeiro acesso;
  * mudar perfil, desativar ou redefinir a senha encerra as sessoes da conta;
  * ninguem desativa ou rebaixa a si mesmo, e o ultimo ADMIN ativo e protegido.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import exigir_permissao
from ..models import (
    AuditLog,
    BlocoSorteio,
    Draw,
    InscricaoPush,
    Notificacao,
    Papel,
    Participant,
    RuleChange,
    User,
    utcnow,
)
from ..permissoes import PAPEIS_INTERNOS, Permissao
from ..schemas import (
    RegistroAuditoriaOut,
    SenhaTemporariaOut,
    UsuarioAdminOut,
    UsuarioEdicaoIn,
    UsuarioEdicaoOut,
    UsuarioNovoIn,
)
from ..security import gerar_senha_temporaria, hash_senha
from ..texto import contem

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])

GERENCIAR = exigir_permissao(Permissao.GERENCIAR_USUARIOS)
PAPEIS_DA_EQUIPE = {p.value for p in PAPEIS_INTERNOS}


def _buscar(db: Session, user_id: int) -> User:
    alvo = db.get(User, user_id)
    if alvo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado")
    return alvo


def _auditar(db: Session, autor: User, acao: str, alvo: User, **detalhes) -> None:  # noqa: ANN003
    db.add(
        AuditLog(
            usuario_id=autor.id,
            acao=acao,
            detalhes={"usuario_alvo_id": alvo.id, "usuario_alvo": alvo.usuario, **detalhes},
        )
    )


def _admins_ativos(db: Session) -> int:
    return db.scalar(
        select(func.count(User.id)).where(User.papel == Papel.ADMIN.value, User.ativo.is_(True))
    ) or 0


@router.get("", response_model=list[UsuarioAdminOut])
def listar(
    busca: str = Query("", max_length=120),
    papel: str | None = Query(None),
    ativo: bool | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(GERENCIAR),
) -> list[User]:
    condicoes = []
    if busca.strip():
        termo = busca.strip().lower()
        condicoes.append(or_(contem(User.usuario, termo), contem(func.lower(User.nome), termo)))
    if papel:
        condicoes.append(User.papel == papel)
    if ativo is not None:
        condicoes.append(User.ativo.is_(ativo))
    consulta = select(User).order_by(User.ativo.desc(), User.nome)
    if condicoes:
        consulta = consulta.where(*condicoes)
    return list(db.scalars(consulta).all())


@router.post("", response_model=SenhaTemporariaOut, status_code=status.HTTP_201_CREATED)
def criar(
    dados: UsuarioNovoIn, db: Session = Depends(get_db), autor: User = Depends(GERENCIAR)
) -> SenhaTemporariaOut:
    """Cria conta da equipe. Contas de COLABORADOR nascem pela ativacao (Fase 5)."""
    if dados.papel not in PAPEIS_DA_EQUIPE:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Perfil inválido para conta da equipe (ADMIN, ORGANIZADOR, SORTEIO, RECEPCAO ou ENTREGAS).",
        )
    if db.scalar(select(User.id).where(User.usuario == dados.usuario)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma conta com este usuário.")

    senha = gerar_senha_temporaria()
    novo = User(
        usuario=dados.usuario,
        nome=dados.nome.strip(),
        papel=dados.papel,
        setor=dados.setor.strip(),
        # A autorizacao para sortear so existe para o Organizador - RH.
        pode_sortear=dados.pode_sortear and dados.papel == Papel.ORGANIZADOR.value,
        senha_hash=hash_senha(senha),
        deve_trocar_senha=True,
    )
    db.add(novo)
    db.flush()
    _auditar(
        db, autor, "usuario_criado", novo, papel=novo.papel, setor=novo.setor, pode_sortear=novo.pode_sortear
    )
    db.commit()
    db.refresh(novo)
    return SenhaTemporariaOut(usuario=UsuarioAdminOut.model_validate(novo), senha_temporaria=senha)


@router.patch("/{user_id}", response_model=UsuarioEdicaoOut)
def editar(
    user_id: int,
    dados: UsuarioEdicaoIn,
    db: Session = Depends(get_db),
    autor: User = Depends(GERENCIAR),
) -> UsuarioEdicaoOut:
    alvo = _buscar(db, user_id)
    mudancas: dict = {}
    senha_temporaria: str | None = None

    if dados.nome is not None and dados.nome.strip() != alvo.nome:
        mudancas["nome"] = [alvo.nome, dados.nome.strip()]
        alvo.nome = dados.nome.strip()

    if dados.papel is not None and dados.papel != alvo.papel:
        if alvo.id == autor.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Você não pode alterar o próprio perfil.")
        if dados.papel not in PAPEIS_DA_EQUIPE:
            # Equipe -> Colaborador nao existe: use "Conta ativa" ou outro perfil.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Contas da equipe não voltam a ser Colaborador. Escolha outro perfil ou desative a conta.",
            )
        if alvo.papel == Papel.ADMIN.value and alvo.ativo and _admins_ativos(db) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Este é o último administrador ativo.")
        if alvo.papel == Papel.COLABORADOR.value:
            # Promocao (ex.: pessoa do RH que se cadastrou pelo QR Code). A
            # senha do portal (5 digitos do CPF) e fraca para a equipe: vira
            # uma senha temporaria, trocada no primeiro acesso. O vinculo com o
            # participante (cartao, premios, avisos) continua.
            senha_temporaria = gerar_senha_temporaria()
            alvo.senha_hash = hash_senha(senha_temporaria)
            alvo.deve_trocar_senha = True
            alvo.senha_alterada_em = utcnow()
            alvo.tentativas_falhas = 0
            alvo.bloqueado_ate = None
            mudancas["senha"] = "temporária gerada (promoção de colaborador)"
        mudancas["papel"] = [alvo.papel, dados.papel]
        alvo.papel = dados.papel
        if alvo.papel != Papel.ORGANIZADOR.value and alvo.pode_sortear:
            mudancas["pode_sortear"] = [True, False]
            alvo.pode_sortear = False

    if dados.setor is not None and dados.setor.strip() != alvo.setor:
        mudancas["setor"] = [alvo.setor, dados.setor.strip()]
        alvo.setor = dados.setor.strip()

    if dados.pode_sortear is not None and dados.pode_sortear != alvo.pode_sortear:
        if dados.pode_sortear and alvo.papel != Papel.ORGANIZADOR.value:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "A autorização para operar sorteios é só para o perfil Organizador — RH.",
            )
        mudancas["pode_sortear"] = [alvo.pode_sortear, dados.pode_sortear]
        alvo.pode_sortear = dados.pode_sortear

    if dados.ativo is not None and dados.ativo != alvo.ativo:
        if alvo.id == autor.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Você não pode desativar a própria conta.")
        if not dados.ativo and alvo.papel == Papel.ADMIN.value and _admins_ativos(db) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "Este é o último administrador ativo.")
        mudancas["ativo"] = [alvo.ativo, dados.ativo]
        alvo.ativo = dados.ativo

    if "papel" in mudancas or "ativo" in mudancas or "pode_sortear" in mudancas:
        # Perfil/permissoes novos ou conta desativada: os tokens antigos deixam
        # de valer (a pessoa entra de novo e recebe os menus certos).
        alvo.sessao_versao += 1
    if mudancas:
        _auditar(db, autor, "usuario_alterado", alvo, mudancas=mudancas)
        db.commit()
        db.refresh(alvo)
    saida = UsuarioEdicaoOut.model_validate(alvo)
    saida.senha_temporaria = senha_temporaria
    return saida


@router.post("/{user_id}/redefinir-senha", response_model=SenhaTemporariaOut)
def redefinir_senha(
    user_id: int, db: Session = Depends(get_db), autor: User = Depends(GERENCIAR)
) -> SenhaTemporariaOut:
    """Gera senha temporaria (exibida uma vez), encerra sessoes e desbloqueia."""
    alvo = _buscar(db, user_id)
    senha = gerar_senha_temporaria()
    alvo.senha_hash = hash_senha(senha)
    alvo.deve_trocar_senha = True
    alvo.senha_alterada_em = utcnow()
    alvo.tentativas_falhas = 0
    alvo.bloqueado_ate = None
    alvo.sessao_versao += 1
    _auditar(db, autor, "senha_redefinida", alvo)
    db.commit()
    db.refresh(alvo)
    return SenhaTemporariaOut(usuario=UsuarioAdminOut.model_validate(alvo), senha_temporaria=senha)


@router.post("/{user_id}/desbloquear", response_model=UsuarioAdminOut)
def desbloquear(
    user_id: int, db: Session = Depends(get_db), autor: User = Depends(GERENCIAR)
) -> User:
    alvo = _buscar(db, user_id)
    alvo.tentativas_falhas = 0
    alvo.bloqueado_ate = None
    _auditar(db, autor, "usuario_desbloqueado", alvo)
    db.commit()
    db.refresh(alvo)
    return alvo


@router.post("/{user_id}/encerrar-sessoes", response_model=UsuarioAdminOut)
def encerrar_sessoes(
    user_id: int, db: Session = Depends(get_db), autor: User = Depends(GERENCIAR)
) -> User:
    alvo = _buscar(db, user_id)
    alvo.sessao_versao += 1
    _auditar(db, autor, "sessoes_encerradas", alvo)
    db.commit()
    db.refresh(alvo)
    return alvo


# Acoes que a pessoa faz sobre a propria conta: nao impedem a exclusao.
ACOES_PESSOAIS = frozenset(
    {
        "login",
        "login_bloqueado",
        "senha_alterada",
        "sessoes_encerradas",
        "foto_alterada",
        "push_ativado",
        "push_desativado",
        "autocadastro_concluido",
    }
)


def _pessoal(registro: AuditLog, alvo: User) -> bool:
    if registro.acao not in ACOES_PESSOAIS:
        return False
    sobre = (registro.detalhes or {}).get("usuario_alvo_id")
    return sobre is None or sobre == alvo.id


def _motivo_para_nao_excluir(db: Session, alvo: User, registros: list[AuditLog]) -> str | None:
    if db.scalar(
        select(Draw.id)
        .where(
            or_(
                Draw.criado_por_id == alvo.id,
                Draw.entregue_por_id == alvo.id,
                Draw.anulado_por_id == alvo.id,
            )
        )
        .limit(1)
    ):
        return "realizou, entregou ou anulou sorteios"
    if db.scalar(select(BlocoSorteio.id).where(BlocoSorteio.finalizado_por_id == alvo.id).limit(1)):
        return "finalizou blocos de sorteio"
    if db.scalar(select(RuleChange.id).where(RuleChange.usuario_id == alvo.id).limit(1)):
        return "alterou regras do sorteio"
    if any(not _pessoal(r, alvo) for r in registros):
        return "tem ações de gestão registradas na auditoria"
    return None


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(
    user_id: int, db: Session = Depends(get_db), autor: User = Depends(GERENCIAR)
) -> Response:
    """Exclui a conta. O participante ligado a ela continua na lista, sem conta."""
    alvo = _buscar(db, user_id)
    if alvo.id == autor.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Você não pode excluir a própria conta.")
    if alvo.papel == Papel.ADMIN.value and alvo.ativo and _admins_ativos(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este é o último administrador ativo.")

    registros = list(db.scalars(select(AuditLog).where(AuditLog.usuario_id == alvo.id)).all())
    motivo = _motivo_para_nao_excluir(db, alvo, registros)
    if motivo:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Esta conta {motivo}; para preservar o histórico ela não pode ser excluída. "
            "Desative a conta em Editar.",
        )

    # Registros pessoais ficam na auditoria, sem o vinculo, com o usuario anotado.
    for registro in registros:
        registro.usuario_id = None
        registro.detalhes = {**(registro.detalhes or {}), "usuario_excluido": alvo.usuario}
    participantes = list(db.scalars(select(Participant).where(Participant.usuario_id == alvo.id)).all())
    for participante in participantes:
        participante.usuario_id = None
    db.execute(update(Notificacao).where(Notificacao.usuario_id == alvo.id).values(usuario_id=None))
    db.execute(delete(InscricaoPush).where(InscricaoPush.usuario_id == alvo.id))

    _auditar(
        db,
        autor,
        "usuario_excluido",
        alvo,
        nome=alvo.nome,
        papel=alvo.papel,
        participantes_desvinculados=[p.matricula for p in participantes],
    )
    db.delete(alvo)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/auditoria", response_model=list[RegistroAuditoriaOut])
def auditoria(
    user_id: int, db: Session = Depends(get_db), _: User = Depends(GERENCIAR)
) -> list[RegistroAuditoriaOut]:
    """O que a conta fez e o que foi feito com ela (ultimos 200 registros)."""
    alvo = _buscar(db, user_id)
    linhas = db.scalars(
        select(AuditLog)
        .where(
            or_(
                AuditLog.usuario_id == alvo.id,
                AuditLog.detalhes["usuario_alvo_id"].as_integer() == alvo.id,
            )
        )
        .order_by(AuditLog.criado_em.desc(), AuditLog.id.desc())
        .limit(200)
    ).all()
    return [
        RegistroAuditoriaOut(
            id=linha.id,
            acao=linha.acao,
            detalhes=linha.detalhes,
            usuario=linha.usuario.nome if linha.usuario else "",
            criado_em=linha.criado_em,
        )
        for linha in linhas
    ]

