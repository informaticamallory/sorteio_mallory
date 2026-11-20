from __future__ import annotations

import io
import secrets

from PIL import Image, UnidentifiedImageError

from ..config import settings

FORMATOS_ACEITOS = {"JPEG", "PNG", "WEBP", "GIF"}
MAX_LADO = 1600


class ImagemInvalida(Exception):
    pass


def salvar_imagem(conteudo: bytes, nome_original: str) -> str:
    """Valida e normaliza a imagem enviada, devolvendo a URL publica.

    A validacao nao confia na extensao nem no content-type: a imagem e aberta
    pelo Pillow, verificada e reescrita em JPEG/PNG. Isso descarta arquivos
    que apenas se parecem com imagem e remove metadados.
    """
    if not conteudo:
        raise ImagemInvalida("Arquivo vazio")
    if len(conteudo) > settings.max_upload_bytes:
        limite = settings.max_upload_bytes // (1024 * 1024)
        raise ImagemInvalida(f"Imagem maior que o limite de {limite} MB")

    try:
        with Image.open(io.BytesIO(conteudo)) as img:
            img.verify()
        with Image.open(io.BytesIO(conteudo)) as img:
            formato = (img.format or "").upper()
            if formato not in FORMATOS_ACEITOS:
                raise ImagemInvalida(f"Formato não suportado: {formato or 'desconhecido'}")
            img = img.convert("RGBA" if formato in {"PNG", "WEBP", "GIF"} else "RGB")
            img.thumbnail((MAX_LADO, MAX_LADO))
            buffer = io.BytesIO()
            if img.mode == "RGBA":
                img.save(buffer, format="PNG", optimize=True)
                extensao = "png"
            else:
                img.save(buffer, format="JPEG", quality=85, optimize=True)
                extensao = "jpg"
    except ImagemInvalida:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImagemInvalida("O arquivo enviado não é uma imagem válida") from exc

    nome = f"{secrets.token_hex(12)}.{extensao}"
    destino = settings.upload_dir / nome
    destino.write_bytes(buffer.getvalue())
    return f"/uploads/{nome}"
