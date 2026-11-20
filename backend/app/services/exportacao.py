from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openpyxl import Workbook

CABECALHO = [
    "rodada",
    "premio",
    "unidade",
    "ganhador",
    "matricula",
    "setor",
    "situacao",
    "entregue",
    "data_hora_sorteio",
    "organizador",
    "entrega_confirmada_por",
    "data_hora_entrega",
    "motivo_anulacao",
    "tipo_anulacao",
    "estorno_entrega",
    "sorteio_anterior",
    "elegiveis_na_rodada",
    # Colunas acrescentadas no fim para nao deslocar as posicoes anteriores.
    "pulseira",
    "bloco",
    "evento",
]


def para_fuso(valor: datetime | None, fuso: str) -> str:
    """Converte um instante UTC (naive) para o fuso do evento, formato BR."""
    if valor is None:
        return ""
    try:
        zona = ZoneInfo(fuso)
    except (ZoneInfoNotFoundError, ValueError):
        zona = ZoneInfo("UTC")
    return valor.replace(tzinfo=timezone.utc).astimezone(zona).strftime("%d/%m/%Y %H:%M:%S")


def _linha(item: dict, fuso_padrao: str) -> list:
    # Exportacoes de varios eventos: cada linha no fuso do proprio evento.
    fuso = item.get("evento_fuso") or fuso_padrao
    bloco = f"{item['bloco_numero']:02d} - {item['bloco_nome']}" if item.get("bloco_numero") else ""
    return [
        item["rodada"],
        item["premio_nome"],
        item["unidade_numero"],
        item["ganhador_nome"],
        item["ganhador_matricula"],
        item["ganhador_setor"],
        "Valido" if item["status"] == "valido" else "Anulado",
        "Sim" if item["entregue"] else "Não",
        para_fuso(item["criado_em"], fuso),
        item["criado_por"],
        item["entregue_por"] or "",
        para_fuso(item["entregue_em"], fuso),
        item["motivo_anulacao"] or "",
        item["tipo_anulacao"] or "",
        "Sim" if item["estorno_entrega"] else "Não",
        item["draw_anterior_id"] or "",
        item["elegiveis_total"],
        item.get("ganhador_pulseira") or "",
        bloco,
        item.get("evento_nome") or "",
    ]


def resultados_csv(itens: list[dict], fuso: str) -> bytes:
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow(CABECALHO)
    for item in itens:
        escritor.writerow(_linha(item, fuso))
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def resultados_xlsx(itens: list[dict], fuso: str, nome_evento: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "resultados"
    ws.append(CABECALHO)
    for item in itens:
        ws.append(_linha(item, fuso))
    larguras = [8, 30, 9, 30, 14, 22, 10, 10, 20, 20, 20, 20, 40, 18, 16, 16, 18, 12, 24, 30]
    for indice, largura in enumerate(larguras, start=1):
        ws.column_dimensions[ws.cell(row=1, column=indice).column_letter].width = largura
    ws.freeze_panes = "A2"

    info = wb.create_sheet("evento")
    info.append(["evento", nome_evento])
    info.append(["fuso_horario", fuso])
    info.append(["gerado_em", para_fuso(datetime.now(timezone.utc).replace(tzinfo=None), fuso)])

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
