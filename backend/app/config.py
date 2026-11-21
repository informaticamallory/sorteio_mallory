from __future__ import annotations

from pathlib import Path

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# Pastas sincronizadas (OneDrive, Dropbox, Google Drive) travam o arquivo do
# banco durante o upload e produzem "database is locked" em plena operacao.
# Por isso o padrao e gravar fora do projeto, em LOCALAPPDATA.
PASTAS_SINCRONIZADAS = ("onedrive", "dropbox", "google drive", "icloud")


def caminho_sincronizado(caminho: Path) -> bool:
    texto = str(caminho).lower()
    return any(marca in texto for marca in PASTAS_SINCRONIZADAS)


def _data_dir_padrao() -> Path:
    definido = os.environ.get("DATA_DIR")
    if definido:
        return Path(definido).expanduser().resolve()
    candidato = BASE_DIR / "data"
    if not caminho_sincronizado(candidato):
        return candidato
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "sorteio-confraternizacao"
    return Path.home() / ".sorteio-confraternizacao"


DATA_DIR = _data_dir_padrao()


class Settings(BaseSettings):
    """Configuracao da aplicacao, lida de variaveis de ambiente ou do arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Troque em producao. Se nao definido, um valor fixo de desenvolvimento e usado.
    secret_key: str = "troque-esta-chave-em-producao-sorteio-confraternizacao"
    token_expira_minutos: int = 60 * 12

    # Para migrar para PostgreSQL basta apontar para
    # postgresql+psycopg://usuario:senha@host:5432/sorteio
    database_url: str = f"sqlite:///{(DATA_DIR / 'sorteio.db').as_posix()}"

    # Fuso horario do evento. Horarios sao SEMPRE gravados em UTC no banco
    # e convertidos para este fuso apenas na exibicao/exportacao.
    event_timezone: str = "America/Sao_Paulo"

    upload_dir: Path = DATA_DIR / "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024
    max_planilha_bytes: int = 10 * 1024 * 1024

    cors_origins: str = "*"

    # Credenciais do organizador criado no primeiro boot.
    admin_usuario: str = "organizador"
    admin_senha: str = "sorteio2026"
    admin_nome: str = "Organizador"

    # Protecao contra tentativas repetidas de login.
    login_max_falhas_conta: int = 5
    login_bloqueio_minutos: int = 15
    # Falhas por IP na janela, somando todas as contas (impede varrer usuarios).
    login_max_falhas_ip: int = 20

    # Autocadastro: tentativas erradas de matricula + nome por matricula
    # (na janela de login_bloqueio_minutos). O limite por IP e o do login.
    autocadastro_max_falhas_matricula: int = 5

    # Portal do Colaborador -------------------------------------------------
    # Endereco que os celulares usam para abrir o sistema (vai no QR Code),
    # ex.: https://sorteio.mallory.com.br ou http://192.168.0.10:8000.
    # Vazio: o painel sugere o endereco da rede local deste computador.
    url_publica: str = ""
    # Chave dos codigos de identificacao (HMAC de CPF/nascimento). Vazia: uma
    # chave aleatoria e criada em DATA_DIR/chave-identificacao.key. Trocar ou
    # perder a chave invalida os codigos ja importados (basta reimportar).
    chave_identificacao: str = ""
    # Validade do passe entre "identificar" e "confirmar cadastro".
    cadastro_passe_minutos: int = 20
    # Web Push (VAPID). Contato do responsavel ("mailto:..." ou "https://...").
    # Vazio: usa URL_PUBLICA quando ela e https. As chaves VAPID sao criadas
    # em DATA_DIR/vapid.json na primeira vez.
    vapid_subject: str = ""


settings = Settings()

DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)


def arquivo_sqlite(url: str | None = None) -> Path | None:
    """Caminho absoluto do arquivo SQLite da URL (None para outros bancos)."""
    from sqlalchemy.engine import make_url

    url_banco = make_url(url or settings.database_url)
    if url_banco.get_backend_name() != "sqlite":
        return None
    if not url_banco.database or url_banco.database == ":memory:":
        return None
    # Caminhos relativos sao resolvidos a partir do diretorio de trabalho,
    # exatamente como o driver do SQLite faz.
    return Path(url_banco.database).resolve()


def pasta_montada(pasta: Path, mountinfo: str) -> bool:
    """A pasta (ou uma pasta acima dela, exceto "/") e um ponto de montagem?

    `mountinfo` e o conteudo de /proc/self/mountinfo: o 5o campo de cada linha
    e o ponto de montagem. Bind mounts e volumes do Docker aparecem ali.
    """
    alvo = pasta.as_posix().rstrip("/") or "/"
    pontos = set()
    for linha in mountinfo.splitlines():
        campos = linha.split()
        if len(campos) >= 5:
            pontos.add(campos[4].replace("\\040", " "))
    atual = alvo
    while atual not in ("", "/"):
        if atual in pontos:
            return True
        atual = atual.rsplit("/", 1)[0] or "/"
    return False


def exigir_volume_de_dados() -> None:
    """No contêiner, recusa iniciar se DATA_DIR nao for um volume persistente.

    Sem volume, o banco fica dentro do contêiner e some a cada deploy (o
    sistema subia "zerado" sem avisar ninguem). Ativado pela variavel
    EXIGIR_VOLUME_DADOS=1, que o Dockerfile define; fora do Docker nao faz nada.
    """
    if os.environ.get("EXIGIR_VOLUME_DADOS", "").strip() not in ("1", "true", "sim"):
        return
    try:
        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError:
        return  # sem como conferir (nao e Linux): nao bloqueia
    if not pasta_montada(DATA_DIR, mountinfo):
        raise RuntimeError(
            f"{DATA_DIR} nao e um volume persistente: o banco seria apagado a cada deploy. "
            f"No Easypanel, em Montagens, crie uma montagem com caminho no contêiner {DATA_DIR} "
            "(Bind para /srv/sorteio/dados ou Volume) e implante de novo. "
            "Veja docs/publicar-easypanel.md."
        )


def avisos_de_ambiente() -> list[str]:
    """Problemas de configuracao que o operador precisa saber antes do evento."""
    avisos: list[str] = []
    # Verifica o arquivo real do banco, e nao so DATA_DIR: um DATABASE_URL no
    # .env pode apontar para dentro de uma pasta sincronizada.
    banco = arquivo_sqlite()
    if banco is not None and caminho_sincronizado(banco):
        avisos.append(
            f"O banco esta em uma pasta sincronizada ({banco}). O sincronismo trava o "
            "arquivo e causa erros de 'database is locked' durante o evento. "
            "Remova DATABASE_URL do .env (o padrao grava fora do OneDrive) ou "
            "defina DATA_DIR para uma pasta local."
        )
    if caminho_sincronizado(settings.upload_dir):
        avisos.append(f"As imagens estao em uma pasta sincronizada ({settings.upload_dir}).")
    if settings.secret_key.startswith("troque-esta-chave"):
        avisos.append("SECRET_KEY ainda e a de exemplo. Troque antes de usar em producao.")
    if settings.admin_senha == "sorteio2026":
        avisos.append("ADMIN_SENHA ainda e a de exemplo. Troque antes do evento.")
    return avisos
