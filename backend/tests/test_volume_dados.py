"""Trava do conteiner: sem volume persistente em /data, o sistema nao sobe."""
from __future__ import annotations

from pathlib import Path

import pytest

from app import config

# Trechos reais de /proc/self/mountinfo de um conteiner Docker.
SEM_VOLUME = """\
612 540 0:52 / / rw,relatime master:301 - overlay overlay rw,lowerdir=/var/lib/docker/overlay2/l/X
613 612 0:55 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
617 612 8:1 /var/lib/docker/containers/abc/resolv.conf /etc/resolv.conf rw,relatime - ext4 /dev/sda1 rw
"""
COM_BIND = SEM_VOLUME + "618 612 8:1 /srv/sorteio/dados /data rw,relatime - ext4 /dev/sda1 rw\n"
COM_VOLUME = SEM_VOLUME + "619 612 8:1 /var/lib/docker/volumes/sorteio/_data /data rw,relatime - ext4 /dev/sda1 rw\n"


@pytest.mark.parametrize(
    "mountinfo,pasta,esperado",
    [
        (SEM_VOLUME, "/data", False),
        (COM_BIND, "/data", True),
        (COM_VOLUME, "/data", True),
        (COM_BIND, "/data/sub", True),  # montagem acima da pasta tambem vale
        (COM_BIND, "/dados", False),
        (SEM_VOLUME, "/", False),  # a raiz do conteiner nao conta
    ],
)
def test_pasta_montada(mountinfo, pasta, esperado):
    assert config.pasta_montada(Path(pasta), mountinfo) is esperado


def test_sem_a_variavel_nao_bloqueia(monkeypatch):
    monkeypatch.delenv("EXIGIR_VOLUME_DADOS", raising=False)
    config.exigir_volume_de_dados()  # nao levanta


def test_com_a_variavel_e_sem_volume_recusa_iniciar(monkeypatch, tmp_path):
    arquivo = tmp_path / "mountinfo"
    arquivo.write_text(SEM_VOLUME, encoding="utf-8")
    monkeypatch.setenv("EXIGIR_VOLUME_DADOS", "1")
    monkeypatch.setattr(config, "DATA_DIR", Path("/data"))
    leitura_original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, *a, **k: leitura_original(arquivo, *a, **k)
        if self.as_posix() == "/proc/self/mountinfo"
        else leitura_original(self, *a, **k),
    )
    with pytest.raises(RuntimeError, match="nao e um volume persistente"):
        config.exigir_volume_de_dados()

    arquivo.write_text(COM_BIND, encoding="utf-8")
    config.exigir_volume_de_dados()  # com o bind mount, sobe normalmente
