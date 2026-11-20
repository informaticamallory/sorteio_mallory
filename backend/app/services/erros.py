from __future__ import annotations


class RegraDeNegocio(Exception):
    """Violacao de regra do sorteio. As rotas a convertem em HTTP com `status_code`."""

    def __init__(self, mensagem: str, status_code: int = 409) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status_code = status_code
