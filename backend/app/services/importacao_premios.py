"""Importacao de premios por planilha (CSV ou XLSX).

Colunas: nome (obrigatoria), descricao e quantidade (opcionais; quantidade
em branco vale 1). A imagem do premio continua sendo colocada na tela.

A previa nao grava nada: aponta erros por linha e premios que ja existem no
evento (mesmo nome, sem diferenca de maiusculas/acentos), que ficam de fora
para que importar a mesma planilha duas vezes nao duplique os premios.
"""

from __future__ import annotations

import csv
import io

from openpyxl import Workbook

from ..texto import normalizar_busca
from .importacao import ler_linhas, normalizar_cabecalho

QUANTIDADE_MAXIMA = 500

SINONIMOS = {
    "nome": {"nome", "premio", "nome_do_premio", "produto", "item", "descricao_do_premio"},
    "descricao": {"descricao", "detalhes", "observacao", "modelo", "marca"},
    "quantidade": {"quantidade", "qtd", "qtde", "quant", "unidades", "quantidade_de_unidades"},
}


def _mapear(cabecalho: list[str]) -> dict[str, int]:
    mapa: dict[str, int] = {}
    for indice, bruto in enumerate(cabecalho):
        chave = normalizar_cabecalho(str(bruto))
        for campo, nomes in SINONIMOS.items():
            if chave in nomes and campo not in mapa:
                mapa[campo] = indice
                break
    return mapa


def _celula(linha: list[str], indice: int | None) -> str:
    if indice is None or indice >= len(linha):
        return ""
    return str(linha[indice] or "").strip()


def previa(conteudo: bytes, nome_arquivo: str, nomes_existentes: set[str]) -> list[dict]:
    """Linhas lidas, cada uma com `erros` (impede importar) e `ja_existe`."""
    todas = ler_linhas(conteudo, nome_arquivo)
    if not todas:
        raise ValueError("A planilha está vazia.")
    mapa = _mapear([str(c) for c in todas[0]])
    if "nome" not in mapa:
        encontradas = ", ".join(f"'{str(c).strip()}'" for c in todas[0] if str(c).strip()) or "nenhuma"
        raise ValueError(
            "A planilha precisa da coluna 'nome' (o nome do prêmio). "
            f"Colunas encontradas: {encontradas}. Baixe o modelo para conferir."
        )

    vistos: dict[str, int] = {}
    saida: list[dict] = []
    for numero, linha in enumerate(todas[1:], start=2):
        nome = _celula(linha, mapa.get("nome"))
        descricao = _celula(linha, mapa.get("descricao")) or None
        bruto = _celula(linha, mapa.get("quantidade"))
        erros: list[str] = []
        if not nome:
            erros.append("Sem nome")
        elif len(nome) > 200:
            erros.append("Nome com mais de 200 caracteres")
        quantidade = 1
        if bruto:
            try:
                valor = float(bruto.replace(",", "."))
                if not valor.is_integer():
                    raise ValueError
                quantidade = int(valor)
            except ValueError:
                erros.append(f"Quantidade inválida: {bruto}")
                quantidade = 0
            else:
                if not 1 <= quantidade <= QUANTIDADE_MAXIMA:
                    erros.append(f"Quantidade deve ser de 1 a {QUANTIDADE_MAXIMA}")
        chave = normalizar_busca(nome)
        if nome and chave in vistos:
            erros.append(f"Repetido na planilha (linha {vistos[chave]}): some as quantidades numa linha só")
        elif nome:
            vistos[chave] = numero
        saida.append(
            {
                "linha": numero,
                "nome": nome,
                "descricao": descricao,
                "quantidade": quantidade,
                "erros": erros,
                "ja_existe": bool(nome) and chave in nomes_existentes,
            }
        )
    return saida


_CABECALHO = ["nome", "descricao", "quantidade"]
_EXEMPLOS = [["Air Fryer 5L", "Marca X, 110V", "10"], ["Bicicleta Aro 29", "", "2"]]


def modelo_csv() -> bytes:
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow(_CABECALHO)
    for linha in _EXEMPLOS:
        escritor.writerow(linha)
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def modelo_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "premios"
    ws.append(_CABECALHO)
    for nome, descricao, quantidade in _EXEMPLOS:
        ws.append([nome, descricao, int(quantidade)])
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["C"].width = 12
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
