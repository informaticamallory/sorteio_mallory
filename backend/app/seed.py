"""Dados ficticios de demonstracao.

Tudo que este script cria fica marcado com `Event.demo = True`, para nunca se
confundir com um evento real (as telas mostram a faixa "Evento de demonstracao"
a partir desse campo; o nome do evento nao leva prefixo). Use:

    python -m app.seed            # cria/recria o evento de demonstracao
    python -m app.seed --limpar   # remove apenas os eventos de demonstracao
"""

from __future__ import annotations

import io
import random
import sys

from PIL import Image, ImageDraw
from sqlalchemy import delete, select

from .config import settings
from .database import session_scope
from .migracoes import aplicar_migracoes
from .models import DisplayState, Draw, Event, Papel, Participant, Prize, PrizeUnit, User
from .security import hash_senha, novo_token_telao

NOMES = [
    "Ana Beatriz Moraes", "Bruno Carvalho Lima", "Camila Figueiredo", "Daniel Rocha Alves",
    "Eduarda Nunes Prado", "Fabio Teixeira", "Gabriela Antunes", "Henrique Sampaio",
    "Isabela Cardoso", "Joao Vitor Barros", "Karina Mendes", "Leonardo Prado",
    "Mariana Siqueira", "Nelson Tavares", "Olivia Ramos", "Paulo Cesar Dias",
    "Queila Fontes", "Rafael Monteiro", "Simone Bastos", "Thiago Azevedo",
    "Ursula Campos", "Vinicius Araujo", "Wanderley Pinto", "Yasmin Correia",
    "Zeca Albuquerque", "Alice Guimaraes", "Bernardo Esteves", "Clara Vasconcelos",
    "Diego Ferraz", "Elisa Marinho", "Felipe Caldeira", "Giovana Peixoto",
    "Hugo Salgado", "Ingrid Bezerra", "Jonas Medeiros", "Katia Lemos",
    "Lucas Villela", "Marcela Drummond", "Nicolas Paiva", "Patricia Goulart",
    "Otavio Bandeira", "Renata Quintela", "Sergio Valadares", "Tatiane Furtado",
    "Ulisses Camargo", "Vanessa Portela", "William Trindade", "Ximena Duarte",
    "Yuri Benevides", "Zilda Napoleao", "Adriano Belmonte", "Bianca Rezende",
    "Caio Setubal", "Debora Assuncao", "Emerson Vilela", "Flavia Toledo",
    "Gustavo Pimentel", "Heloisa Serrano", "Igor Bessa", "Juliana Macedo",
]

SETORES = [
    "Financeiro", "Producao", "Comercial", "Logistica",
    "Recursos Humanos", "Tecnologia", "Qualidade", "Manutencao",
]

PREMIOS = [
    ("Smart TV 50\"", "Smart TV 4K com assistente de voz", 1, (26, 54, 93)),
    ("Fone Bluetooth", "Fone com cancelamento de ruido", 3, (109, 40, 217)),
    ("Air Fryer 5L", "Fritadeira eletrica digital", 2, (190, 24, 93)),
    ("Caixa de Som Portatil", "A prova d'agua, bateria de 20h", 4, (13, 148, 136)),
    ("Vale-Compras R$ 500", None, 2, (180, 83, 9)),
    ("Bicicleta Aro 29", "Mountain bike com 21 marchas", 1, (21, 128, 61)),
    ("Kit Churrasco", "Kit completo com 8 pecas", 3, (124, 45, 18)),
    ("Smartwatch", "Monitor de atividades e notificacoes", 2, (30, 64, 175)),
]


def _imagem_placeholder(titulo: str, cor: tuple[int, int, int]) -> str:
    """Gera uma imagem simples para o premio, sem depender de arquivos externos."""
    largura, altura = 800, 600
    img = Image.new("RGB", (largura, altura), cor)
    desenho = ImageDraw.Draw(img)
    for i in range(0, altura, 4):
        fator = 1 - (i / altura) * 0.45
        desenho.line(
            [(0, i), (largura, i)],
            fill=tuple(max(0, int(c * fator)) for c in cor),
        )
    desenho.rectangle([40, 40, largura - 40, altura - 40], outline=(212, 175, 55), width=6)
    caixa = desenho.textbbox((0, 0), titulo)
    desenho.text(
        ((largura - (caixa[2] - caixa[0])) / 2, altura / 2 - 8),
        titulo,
        fill=(248, 250, 252),
    )
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=88)

    import secrets

    nome = f"demo-{secrets.token_hex(8)}.jpg"
    (settings.upload_dir / nome).write_bytes(buffer.getvalue())
    return f"/uploads/{nome}"


def limpar_demo() -> int:
    """Remove SOMENTE eventos marcados como demo, inclusive seus sorteios.

    Os resultados sao apagados explicitamente antes do evento: sem isso, a
    exclusao dos participantes esbarra na FK draws.participant_id (RESTRICT),
    que existe justamente para proteger o historico de eventos reais.
    """
    with session_scope() as db:
        eventos = db.scalars(select(Event).where(Event.demo.is_(True))).all()
        ids = [evento.id for evento in eventos]
        if ids:
            # Contas criadas pelo autocadastro de participantes de demonstracao:
            # nao podem continuar ocupando a matricula como login. Sao
            # desativadas e renomeadas (a auditoria delas e preservada).
            contas_demo = set(
                db.scalars(
                    select(Participant.usuario_id).where(
                        Participant.event_id.in_(ids), Participant.usuario_id.is_not(None)
                    )
                ).all()
            )
            # display_states, notificacoes e codigos seguem pelo ON DELETE do banco.
            db.execute(delete(Draw).where(Draw.event_id.in_(ids)))
            for evento in eventos:
                db.delete(evento)
            db.flush()
            for user_id in contas_demo:
                conta = db.get(User, user_id)
                em_uso = db.scalar(select(Participant.id).where(Participant.usuario_id == user_id))
                if conta is not None and conta.papel == Papel.COLABORADOR.value and em_uso is None:
                    conta.ativo = False
                    conta.usuario = f"demo-removida-{conta.id}"
                    conta.sessao_versao += 1
    return len(ids)


def criar_demo() -> int:
    aleatorio = random.Random(20261212)
    with session_scope() as db:
        organizador = db.scalar(select(User).where(User.usuario == settings.admin_usuario.lower()))
        if organizador is None:
            organizador = User(
                usuario=settings.admin_usuario.lower(),
                nome=settings.admin_nome,
                senha_hash=hash_senha(settings.admin_senha),
                papel=Papel.ADMIN.value,
            )
            db.add(organizador)
            db.flush()

        evento = Event(
            nome="Confraternização de Fim de Ano 2026",
            empresa_nome="Mallory",
            telao_token=novo_token_telao(),
            mensagem_boas_vindas="Bem-vindos à nossa Confraternização de Fim de Ano!",
            mensagem_encerramento="Obrigado por um ano incrivel. Boas festas a todos!",
            regras_participacao=(
                "Participam todos os colaboradores presentes no evento. "
                "Cada pessoa pode ganhar apenas um premio. "
                "O ganhador deve estar presente no momento do sorteio."
            ),
            permite_multiplas_vitorias=False,
            exige_presenca=True,
            tratamento_ausente="resortear",
            ausente_pode_concorrer_novamente=False,
            duracao_animacao_ms=6000,
            demo=True,
        )
        db.add(evento)
        db.flush()
        db.add(DisplayState(event_id=evento.id, versao=1))

        for indice, nome in enumerate(NOMES):
            db.add(
                Participant(
                    event_id=evento.id,
                    nome=nome,
                    # Matricula com zeros a esquerda, para exercitar a preservacao.
                    matricula=f"{indice + 1:05d}",
                    setor=SETORES[indice % len(SETORES)],
                    presente=aleatorio.random() < 0.8,
                )
            )

        for ordem, (nome, descricao, quantidade, cor) in enumerate(PREMIOS, start=1):
            premio = Prize(
                event_id=evento.id,
                nome=nome,
                descricao=descricao,
                # O ultimo premio fica sem imagem de proposito, para exercitar
                # o espaco visual de fallback no telao.
                imagem_url=None if ordem == len(PREMIOS) else _imagem_placeholder(nome, cor),
                quantidade=quantidade,
                ordem=ordem,
            )
            db.add(premio)
            db.flush()
            for numero in range(1, quantidade + 1):
                db.add(PrizeUnit(prize_id=premio.id, numero=numero))

        db.flush()
        return evento.id


def main() -> None:
    aplicar_migracoes()
    if "--limpar" in sys.argv:
        total = limpar_demo()
        print(f"Removidos {total} evento(s) de demonstracao.")
        return
    removidos = limpar_demo()
    if removidos:
        print(f"Removidos {removidos} evento(s) de demonstracao anteriores.")
    event_id = criar_demo()
    with session_scope() as db:
        evento = db.get(Event, event_id)
        print("Evento de demonstracao criado.")
        print(f"  id .............. {evento.id}")
        print(f"  nome ............ {evento.nome}")
        print(f"  participantes ... {len(NOMES)}")
        print(f"  premios ......... {len(PREMIOS)}")
        print(f"  telao ........... /telao/{evento.telao_token}")
        print()
        print(f"  login ........... {settings.admin_usuario} / {settings.admin_senha}")


if __name__ == "__main__":
    main()
