"""Cadastro do colaborador pelo QR Code (Portal do Colaborador).

Fluxo:
  1. identificar: matricula + data de nascimento + 5 primeiros digitos do CPF
     conferem com os codigos importados da planilha -> passe curto;
  2. confirmar: nome e matricula na tela, foto opcional -> conta, com a senha
     = 5 primeiros digitos do CPF (decisao do cliente, 18/11/2026);
  3. cartao da sorte: numero do sorteio ja existente no banco.

Barreiras (e o risco que fica):
  * nascimento e CPF sao previsiveis para quem conhece a pessoa: NAO sao
    autenticacao forte. Risco aceito pelo cliente: depois do cadastro o
    colaborador entra com matricula + 5 primeiros digitos do CPF (protegidos
    pelo bloqueio de 5 tentativas por conta e 20 por IP);
  * erros dizem apenas "nao conferem" (nao revelam qual dado esta errado nem
    se a matricula existe) e contam para limites por IP e por matricula;
  * participante sem CPF/nascimento importados nunca confere (mesma mensagem);
  * so vale o PRIMEIRO cadastro. Refazer (cadastro indevido, senha esquecida)
    so depois que o check-in libera, com motivo registrado;
  * o cadastro NAO confirma presenca nem registra pulseira: isso e do check-in;
  * CPF e nascimento nunca sao gravados nem vao para a auditoria;
  * tudo numa transacao exclusiva (BEGIN IMMEDIATE): dois aparelhos com a
    mesma matricula nao concluem os dois.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AuditLog, Event, Notificacao, Papel, Participant, User, utcnow
from ..security import hash_senha
from ..texto import normalizar_matricula
from . import identificacao
from .autenticacao import limitador
from .erros import RegraDeNegocio
from .imagens import ImagemInvalida, salvar_imagem

MENSAGEM_NAO_CONFERE = (
    "Os dados informados não conferem. Confira a matrícula, a data de nascimento e os "
    "5 primeiros dígitos do CPF, ou procure a Recepção do evento."
)
MENSAGEM_JA_CADASTRADO = (
    "Esta matrícula já tem cadastro. Entre com sua matrícula e senha. "
    "Esqueceu a senha ou não foi você? Procure a Recepção."
)
MENSAGEM_FECHADO = "O cadastro pelo celular não está aberto para este evento."
MENSAGEM_LIMITE = "Muitas tentativas. Aguarde alguns minutos ou procure a Recepção."
MENSAGEM_PASSE = "Sua confirmação expirou. Informe seus dados novamente."


def _auditar(db: Session, evento_id: int, usuario_id: int | None, acao: str, detalhes: dict) -> None:
    db.add(AuditLog(event_id=evento_id, usuario_id=usuario_id, acao=acao, detalhes=detalhes))


# ------------------------------------------------------------------ disponibilidade
def cadastro_aberto(evento: Event) -> bool:
    """Ativo no painel e dentro do periodo (quando definido)."""
    if not evento.autocadastro_ativo:
        return False
    agora = utcnow()
    if evento.autocadastro_inicio is not None and agora < evento.autocadastro_inicio:
        return False
    if evento.autocadastro_fim is not None and agora > evento.autocadastro_fim:
        return False
    return True


def exigir_aberto(evento: Event) -> None:
    if not cadastro_aberto(evento):
        raise RegraDeNegocio(MENSAGEM_FECHADO, 403)


# ------------------------------------------------------------------ busca por matricula
def _participante_por_matricula(db: Session, evento: Event, matricula: str) -> Participant | None:
    """Matricula exata; senao a forma normalizada ("26" acha "00026"), se for unica."""
    texto = matricula.strip()
    if not texto:
        return None
    exato = db.scalar(
        select(Participant).where(Participant.event_id == evento.id, Participant.matricula == texto)
    )
    if exato is not None:
        return exato
    candidatos = db.scalars(
        select(Participant).where(
            Participant.event_id == evento.id,
            Participant.matricula_normalizada == normalizar_matricula(texto),
        )
    ).all()
    if len(candidatos) == 1:
        return candidatos[0]
    # Bancos anteriores a migracao 0008 em memoria de teste: caixa diferente.
    candidatos = db.scalars(
        select(Participant).where(
            Participant.event_id == evento.id, func.upper(Participant.matricula) == texto.upper()
        )
    ).all()
    return candidatos[0] if len(candidatos) == 1 else None


# ------------------------------------------------------------------ passo 1
def identificar(
    db: Session, evento: Event, matricula: str, nascimento: date | None, cinco_digitos: str | None, ip: str
) -> Participant:
    """Confere matricula + nascimento + 5 digitos do CPF. So devolve quem ainda nao tem cadastro."""
    exigir_aberto(evento)
    chave_ip = f"autocadastro-ip:{ip}"
    chave_matricula = f"autocadastro-matricula:{evento.id}:{normalizar_matricula(matricula)}"
    if limitador.excedeu(chave_ip, settings.login_max_falhas_ip) or limitador.excedeu(
        chave_matricula, settings.autocadastro_max_falhas_matricula
    ):
        raise RegraDeNegocio(MENSAGEM_LIMITE, 429)

    participante = _participante_por_matricula(db, evento, matricula)
    confere = (
        participante is not None
        and nascimento is not None
        and cinco_digitos is not None
        and identificacao.confere(participante.identificacao_hash, nascimento, cinco_digitos)
    )
    if not confere:
        limitador.registrar(chave_ip, chave_matricula)
        raise RegraDeNegocio(MENSAGEM_NAO_CONFERE, 401)
    if participante.usuario_id is not None:
        raise RegraDeNegocio(MENSAGEM_JA_CADASTRADO, 409)
    return participante


# ------------------------------------------------------------------ passo 2
@dataclass
class Conclusao:
    usuario: User
    participante: Participant
    conta_nova: bool
    # Foto que deixou de ser usada (trocada ou removida): apagar apos o commit.
    foto_descartada: str | None = None


def _login_livre(db: Session, base: str) -> str:
    candidato, n = base, 1
    while db.scalar(select(User.id).where(User.usuario == candidato)) is not None:
        n += 1
        candidato = f"{base}.{n}"
    return candidato


def conta_da_equipe(conta: User | None) -> bool:
    """Conta de equipe (qualquer perfil que nao seja COLABORADOR)."""
    return conta is not None and conta.papel != Papel.COLABORADOR.value


def conta_para(db: Session, evento: Event, participante: Participant) -> tuple[User | None, str]:
    """Conta existente a reaproveitar (ou None) e o login que o colaborador usara.

    O login padrao e a matricula. A matricula e unica por pessoa (decisao do
    cliente, 26/11/2026; PJ recebem numero proprio no cadastro de participantes),
    entao a conta ativa com esse login e sempre a mesma pessoa (outro evento,
    cadastro liberado pelo check-in, ou alguem da equipe que usa a matricula
    como login) e e reaproveitada, mesmo com o nome escrito de outro jeito.

    Conta da EQUIPE (ver conta_da_equipe): o cartao fica nela, mas a senha NAO
    muda e o cadastro nao abre sessao. Quem conhece nascimento e CPF so liga o
    cadastro a conta; entrar continua exigindo a senha da equipe.

    Conta ja ligada a outro participante deste evento, ou conta da equipe
    desativada: o colaborador ganha um login proprio ("<matricula>.e<evento>").
    """
    base = participante.matricula.strip().lower()
    existente = db.scalar(select(User).where(User.usuario == base))
    if existente is None:
        return None, base
    vinculada_aqui = db.scalar(
        select(Participant.id).where(
            Participant.event_id == evento.id, Participant.usuario_id == existente.id
        )
    )
    if conta_da_equipe(existente) and (vinculada_aqui is None and existente.ativo):
        return existente, existente.usuario
    mesma_pessoa = existente.papel == Papel.COLABORADOR.value and vinculada_aqui is None
    if mesma_pessoa:
        if not existente.ativo:
            raise RegraDeNegocio("Sua conta está desativada. Procure a organização do evento.", 403)
        return existente, existente.usuario
    return None, _login_livre(db, f"{base}.e{evento.id}")


def participante_do_passe(db: Session, evento: Event, participante_id: int) -> Participant:
    participante = db.get(Participant, participante_id)
    if participante is None or participante.event_id != evento.id:
        raise RegraDeNegocio(MENSAGEM_PASSE, 401)
    if participante.usuario_id is not None:
        raise RegraDeNegocio(MENSAGEM_JA_CADASTRADO, 409)
    return participante


def concluir(
    db: Session,
    evento: Event,
    participante: Participant,
    *,
    ip: str,
    nascimento: date | None,
    cinco_digitos: str | None,
    foto: bytes | None,
    foto_nome: str = "",
    remover_foto: bool = False,
) -> Conclusao:
    """Confere de novo nascimento + 5 digitos, grava a foto (opcional) e cria/vincula a conta.

    Decisao do cliente (18/11/2026): a senha do colaborador e os 5 primeiros
    digitos do CPF. Por isso eles sao conferidos de novo aqui (com o codigo
    importado) antes de virar o hash da senha: a senha nunca e um valor
    escolhido pelo aparelho. O sistema guarda so o hash (PBKDF2), nunca os digitos.
    O chamador faz o commit. Nao confirma presenca e nao registra pulseira.
    Se o commit falhar, o chamador deve apagar a foto nova (apagar_foto).
    """
    exigir_aberto(evento)
    chave_matricula = f"autocadastro-matricula:{evento.id}:{participante.matricula_normalizada}"
    if limitador.excedeu(chave_matricula, settings.autocadastro_max_falhas_matricula):
        raise RegraDeNegocio(MENSAGEM_LIMITE, 429)
    if (
        nascimento is None
        or cinco_digitos is None
        or not identificacao.confere(participante.identificacao_hash, nascimento, cinco_digitos)
    ):
        limitador.registrar(f"autocadastro-ip:{ip}", chave_matricula)
        raise RegraDeNegocio(MENSAGEM_NAO_CONFERE, 401)
    senha = cinco_digitos
    conta, login = conta_para(db, evento, participante)

    foto_url = None
    if foto:
        try:
            foto_url = salvar_imagem(foto, foto_nome)
        except ImagemInvalida as exc:
            raise RegraDeNegocio(str(exc), 422) from exc

    agora = utcnow()
    conta_nova = conta is None
    if conta is None:
        conta = User(
            usuario=login,
            nome=participante.nome,
            senha_hash=hash_senha(senha),
            papel=Papel.COLABORADOR.value,
            senha_alterada_em=agora,
            ultimo_acesso_em=agora,
        )
        db.add(conta)
        db.flush()
    elif conta_da_equipe(conta):
        # Conta da equipe: so liga o cartao. Senha, nome e sessoes nao mudam.
        pass
    else:
        # O nome da planilha mais recente passa a valer para a conta.
        conta.nome = participante.nome
        conta.senha_hash = hash_senha(senha)
        conta.deve_trocar_senha = False
        conta.senha_alterada_em = agora
        conta.ultimo_acesso_em = agora
        conta.tentativas_falhas = 0
        conta.bloqueado_ate = None
        conta.sessao_versao += 1

    participante.usuario_id = conta.id
    foto_anterior = participante.foto_url
    if foto_url:
        participante.foto_url = foto_url
    elif remover_foto:
        participante.foto_url = None

    # Notificacoes criadas antes do cadastro passam a ser desta conta.
    db.execute(
        update(Notificacao)
        .where(Notificacao.participant_id == participante.id)
        .values(usuario_id=conta.id)
    )
    _auditar(
        db,
        evento.id,
        conta.id,
        "autocadastro_concluido",
        {
            "participante_id": participante.id,
            "usuario_id": conta.id,
            "conta": "criada" if conta_nova else ("equipe" if conta_da_equipe(conta) else "existente"),
            "foto": "nova" if foto_url else ("removida" if remover_foto and foto_anterior else "sem_alteracao"),
            "origem": "portal_qrcode",
            "ip": ip,
        },
    )
    db.flush()
    descartada = foto_anterior if foto_anterior and foto_anterior != participante.foto_url else None
    return Conclusao(
        usuario=conta, participante=participante, conta_nova=conta_nova, foto_descartada=descartada
    )


# ------------------------------------------------------------------ check-in
def liberar_novo_cadastro(
    db: Session, evento: Event, participante: Participant, motivo: str, usuario: User
) -> None:
    """Check-in desfaz o vinculo para a pessoa refazer o cadastro.

    Usado quando alguem se cadastrou no lugar de outra pessoa ou quando o
    colaborador esqueceu a senha. A conta antiga e desconectada de todos os
    aparelhos. A pulseira, entregue pelo check-in, continua com o participante.
    O historico (resultados, notificacoes, auditoria) e preservado.
    """
    if participante.usuario_id is None:
        raise RegraDeNegocio("Este participante ainda não fez o cadastro.", 409)
    conta = db.get(User, participante.usuario_id)
    if conta is not None and conta.papel != Papel.COLABORADOR.value:
        raise RegraDeNegocio("Este cadastro está ligado a uma conta da equipe. Procure um administrador.", 409)
    if conta is not None:
        conta.sessao_versao += 1
    _auditar(
        db,
        evento.id,
        usuario.id,
        "cadastro_liberado",
        {
            "participante_id": participante.id,
            "usuario_id": participante.usuario_id,
            "pulseira_anterior": participante.pulseira,
            "motivo": motivo,
        },
    )
    participante.usuario_id = None


# ------------------------------------------------------------------ fotos
def apagar_foto(url: str | None) -> None:
    """Remove a foto gravada por uma conclusao que nao chegou ao commit."""
    if not url or not url.startswith("/uploads/"):
        return
    caminho = settings.upload_dir / Path(url).name
    caminho.unlink(missing_ok=True)


def apagar_foto_se_orfa(db: Session, url: str | None) -> None:
    """Apaga o arquivo da foto se nenhum participante a usa mais (LGPD)."""
    if not url or not url.startswith("/uploads/"):
        return
    em_uso = db.scalar(select(Participant.id).where(Participant.foto_url == url).limit(1))
    if em_uso is None:
        apagar_foto(url)
