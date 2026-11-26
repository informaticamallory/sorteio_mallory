"""Cadastro do colaborador pelo QR Code (publico, sem login).

Nenhuma rota daqui devolve dado pessoal sem que matricula + data de
nascimento + 5 primeiros digitos do CPF confiram com os codigos importados.
A lista de eventos expoe apenas o nome e a identidade visual dos eventos com
cadastro aberto. CPF e nascimento nunca sao gravados nem registrados.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Event, Participant
from ..schemas import (
    AutocadastroOut,
    CartaoSorteOut,
    EventoAutocadastroOut,
    IdentificacaoIn,
    IdentificacaoOut,
)
from ..security import criar_passe_cadastro, criar_token, ler_passe_cadastro
from ..services import autocadastro as servico
from ..services import identificacao
from ..services.elegibilidade import matricula_da_sorte
from ..services.erros import RegraDeNegocio
from .auth import usuario_out

router = APIRouter(prefix="/api/autocadastro", tags=["autocadastro"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconhecido"


def _evento(db: Session, event_id: int) -> Event:
    evento = db.get(Event, event_id)
    # Evento inexistente, desativado ou fora do periodo respondem igual.
    if evento is None or not servico.cadastro_aberto(evento):
        raise HTTPException(status.HTTP_404_NOT_FOUND, servico.MENSAGEM_FECHADO)
    return evento


def _erro(exc: RegraDeNegocio) -> HTTPException:
    return HTTPException(exc.status_code, exc.mensagem)


def _publico(e: Event) -> EventoAutocadastroOut:
    return EventoAutocadastroOut(
        id=e.id,
        nome=e.nome,
        empresa_nome=e.empresa_nome,
        logo_url=e.logo_url,
        cor_fundo=e.cor_fundo,
        cor_primaria=e.cor_primaria,
        demo=e.demo,
    )


def cartao(evento: Event, participante: Participant) -> CartaoSorteOut:
    return CartaoSorteOut(
        evento_id=evento.id,
        evento_nome=evento.nome,
        empresa_nome=evento.empresa_nome,
        nome=participante.nome,
        matricula=participante.matricula,
        foto_url=participante.foto_url,
        numero_sorteio=participante.numero_sorteio,
        matricula_da_sorte=matricula_da_sorte(evento, participante),
        presente=participante.presente,
        participando=participante.participando,
    )


@router.get("/eventos", response_model=list[EventoAutocadastroOut])
def eventos_abertos(db: Session = Depends(get_db)) -> list[EventoAutocadastroOut]:
    eventos = db.scalars(
        select(Event)
        # Evento de teste nao aparece na lista do cadastro pelo QR Code.
        .where(Event.autocadastro_ativo.is_(True), Event.evento_teste.is_(False))
        .order_by(Event.criado_em.desc())
    ).all()
    return [_publico(e) for e in eventos if servico.cadastro_aberto(e)]


@router.get("/{event_id}", response_model=EventoAutocadastroOut)
def evento_do_qrcode(event_id: int, db: Session = Depends(get_db)) -> EventoAutocadastroOut:
    """Evento do link do QR Code (/evento/{id}/cadastro), se o cadastro estiver aberto."""
    return _publico(_evento(db, event_id))


@router.post("/{event_id}/identificar", response_model=IdentificacaoOut)
def identificar(
    event_id: int, dados: IdentificacaoIn, request: Request, db: Session = Depends(get_db)
) -> IdentificacaoOut:
    """Passo 1: matricula + nascimento + 5 digitos do CPF -> passe curto."""
    evento = _evento(db, event_id)
    nascimento = identificacao.normalizar_nascimento(dados.nascimento)
    cinco = identificacao.cinco_digitos_validos(dados.cpf5)
    try:
        participante = servico.identificar(db, evento, dados.matricula, nascimento, cinco, _ip(request))
        _conta, login = servico.conta_para(db, evento, participante)
    except RegraDeNegocio as exc:
        db.rollback()
        raise _erro(exc) from exc
    return IdentificacaoOut(
        passe=criar_passe_cadastro(evento.id, participante.id),
        nome=participante.nome,
        matricula=participante.matricula,
        foto_url=participante.foto_url,
        login=login,
    )


@router.post("/{event_id}/concluir", response_model=AutocadastroOut)
def concluir(
    event_id: int,
    request: Request,
    passe: str = Form(..., max_length=2000),
    # Conferidos de novo: os 5 digitos viram a senha (so o hash e gravado).
    nascimento: str = Form(..., max_length=20),
    cpf5: str = Form(..., max_length=20),
    remover_foto: bool = Form(False),
    foto: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> AutocadastroOut:
    """Passo 2: foto opcional -> conta (senha = 5 primeiros digitos do CPF). Nao confirma presenca."""
    evento = _evento(db, event_id)
    lido = ler_passe_cadastro(passe)
    if lido is None or lido[0] != evento.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, servico.MENSAGEM_PASSE)

    conteudo = foto.file.read(settings.max_upload_bytes + 1) if foto is not None else None
    if conteudo is not None and len(conteudo) > settings.max_upload_bytes:
        limite = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Foto maior que {limite} MB")

    foto_gravada = None
    try:
        participante = servico.participante_do_passe(db, evento, lido[1])
        resultado = servico.concluir(
            db,
            evento,
            participante,
            ip=_ip(request),
            nascimento=identificacao.normalizar_nascimento(nascimento),
            cinco_digitos=identificacao.cinco_digitos_validos(cpf5),
            foto=conteudo or None,
            foto_nome=(foto.filename or "") if foto is not None else "",
            remover_foto=remover_foto,
        )
        foto_gravada = resultado.participante.foto_url if conteudo else None
        db.commit()
    except RegraDeNegocio as exc:
        db.rollback()
        raise _erro(exc) from exc
    except IntegrityError as exc:
        # Dois aparelhos concluindo o mesmo cadastro no mesmo instante.
        db.rollback()
        servico.apagar_foto(foto_gravada)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este cadastro acabou de ser concluído em outro aparelho. Entre com sua matrícula e senha.",
        ) from exc
    servico.apagar_foto_se_orfa(db, resultado.foto_descartada)

    usuario = resultado.usuario
    db.refresh(usuario)
    db.refresh(resultado.participante)
    return AutocadastroOut(
        access_token=criar_token(usuario.id, usuario.sessao_versao),
        usuario=usuario_out(usuario),
        login=usuario.usuario,
        conta_nova=resultado.conta_nova,
        cartao=cartao(evento, resultado.participante),
    )
