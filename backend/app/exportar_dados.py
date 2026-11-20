"""Empacota os dados do evento para levar a outro servidor (ex.: Easypanel).

    python -m app.exportar_dados [pasta_destino]

Gera sorteio-dados-AAAAMMDD-HHMM.zip com:
  * sorteio.db: copia consistente (API de backup do SQLite, segura com WAL);
  * chave-identificacao.key: sem ela os CPFs importados param de funcionar;
  * vapid.json (se existir): chaves do push no celular;
  * uploads/: fotos e imagens dos premios.

Ficam de fora: backups antigos e a pasta https/ (o servidor novo usa o
certificado do proprio Easypanel). O zip tem dados pessoais (nomes, fotos e
codigos de identificacao): nao deixe em pasta sincronizada nem envie por
e-mail.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, arquivo_sqlite, settings

ARQUIVOS_SOLTOS = ("chave-identificacao.key", "vapid.json")


def exportar(destino: Path) -> Path:
    banco = arquivo_sqlite()
    if banco is None or not banco.exists():
        raise SystemExit(f"Banco SQLite nao encontrado ({settings.database_url}).")
    destino.mkdir(parents=True, exist_ok=True)
    pacote = destino / f"sorteio-dados-{datetime.now():%Y%m%d-%H%M}.zip"

    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "sorteio.db"
        origem = sqlite3.connect(banco)
        alvo = sqlite3.connect(copia)
        try:
            origem.backup(alvo)
        finally:
            alvo.close()
            origem.close()

        with zipfile.ZipFile(pacote, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(copia, "sorteio.db")
            for nome in ARQUIVOS_SOLTOS:
                arquivo = DATA_DIR / nome
                if arquivo.exists():
                    zf.write(arquivo, nome)
            uploads = Path(settings.upload_dir)
            if uploads.is_dir():
                for arquivo in sorted(uploads.rglob("*")):
                    if arquivo.is_file():
                        zf.write(arquivo, Path("uploads") / arquivo.relative_to(uploads))
    return pacote


def main() -> None:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR / "exportacao"
    pacote = exportar(destino.expanduser().resolve())
    with zipfile.ZipFile(pacote) as zf:
        nomes = zf.namelist()
    print(f"Pacote: {pacote}")
    print(f"  banco: sim | chave de identificacao: {'sim' if 'chave-identificacao.key' in nomes else 'NAO'}"
          f" | push (vapid.json): {'sim' if 'vapid.json' in nomes else 'nao existe ainda'}"
          f" | imagens: {sum(1 for n in nomes if n.startswith('uploads/'))}")
    if "chave-identificacao.key" not in nomes and not settings.chave_identificacao:
        print("ATENCAO: sem chave de identificacao, o autocadastro nao reconhece os CPFs importados.")


if __name__ == "__main__":
    main()
