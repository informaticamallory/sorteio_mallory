from __future__ import annotations

import csv
import io
import re
import unicodedata

from openpyxl import Workbook, load_workbook

from ..texto import normalizar_matricula
from . import identificacao

COLUNAS = ("nome", "matricula", "setor", "nascimento", "cpf")
LIMITE_LINHAS_VAZIAS = 1000


def _normalizar(texto: str) -> str:
    """"CPF:" -> "cpf", "Data de Nascimento" -> "data_de_nascimento", "Nº CPF" -> "no_cpf"."""
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    # Pontuacao do cabecalho (":", ".", "*", "/", "-", "º"...) nao importa.
    chave = re.sub(r"[^a-z0-9]+", "_", sem_acento.strip().lower())
    return chave.strip("_")


SINONIMOS = {
    "nome": {"nome", "nome_completo", "participante", "funcionario", "colaborador",
             "nome_do_funcionario", "nome_funcionario", "nome_do_colaborador", "nome_colaborador"},
    "matricula": {"matricula", "registro", "cracha", "codigo", "cod", "chapa",
                  "codigo_do_funcionario", "codigo_funcionario", "matricula_do_funcionario"},
    "setor": {"setor", "area", "departamento", "equipe", "centro_de_custo"},
    "nascimento": {"nascimento", "data_de_nascimento", "data_nascimento", "dt_nascimento",
                   "data_nasc", "dt_nasc", "nasc", "dt_de_nascimento"},
    "cpf": {"cpf", "cpf_completo", "numero_cpf", "numero_do_cpf", "n_cpf", "no_cpf", "num_cpf"},
}


def _mapear_cabecalho(cabecalho: list[str]) -> dict[str, int]:
    mapa: dict[str, int] = {}
    for indice, bruto in enumerate(cabecalho):
        chave = _normalizar(str(bruto))
        for campo, nomes in SINONIMOS.items():
            if chave in nomes:
                mapa.setdefault(campo, indice)
                break
    return mapa


def _celula_para_texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def ler_planilha(conteudo: bytes, nome_arquivo: str) -> list[dict]:
    """Devolve as linhas brutas da planilha como dicionarios nome/matricula/setor."""
    todas = ler_linhas(conteudo, nome_arquivo)
    if not todas:
        return []
    return _montar(todas[0], todas[1:])


def ler_linhas(conteudo: bytes, nome_arquivo: str) -> list[list[str]]:
    """Linhas nao vazias da planilha (CSV ou XLSX), cabecalho incluido, como texto."""
    nome = (nome_arquivo or "").lower()
    if nome.endswith(".csv") or nome.endswith(".txt"):
        return _linhas_csv(conteudo)
    if nome.endswith(".xlsx") or nome.endswith(".xlsm"):
        return _linhas_xlsx(conteudo)
    raise ValueError("Formato não suportado. Envie um arquivo .csv ou .xlsx")


def normalizar_cabecalho(texto: str) -> str:
    return _normalizar(texto)


def _ler_csv(conteudo: bytes) -> list[dict]:
    todas = _linhas_csv(conteudo)
    if not todas:
        return []
    return _montar(todas[0], todas[1:])


def _linhas_csv(conteudo: bytes) -> list[list[str]]:
    texto = None
    for codificacao in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError("Não foi possível ler o arquivo CSV (codificação desconhecida)")

    amostra = texto[:4096]
    try:
        dialeto = csv.Sniffer().sniff(amostra, delimiters=";,\t")
        delimitador = dialeto.delimiter
    except csv.Error:
        delimitador = ";" if amostra.count(";") > amostra.count(",") else ","

    leitor = csv.reader(io.StringIO(texto), delimiter=delimitador)
    return [linha for linha in leitor if any((c or "").strip() for c in linha)]


def _ler_xlsx(conteudo: bytes) -> list[dict]:
    todas = _linhas_xlsx(conteudo)
    if not todas:
        return []
    return _montar(todas[0], todas[1:])


def _linhas_xlsx(conteudo: bytes) -> list[list[str]]:
    wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    ws = wb.active
    todas = []
    vazias_seguidas = 0
    for linha in ws.iter_rows(values_only=True):
        valores = [_celula_para_texto(v) for v in linha]
        if any(valores):
            todas.append(valores)
            vazias_seguidas = 0
        else:
            # Planilhas "formatadas" ate a linha 1.000.000: para depois de um
            # bloco longo de linhas vazias em vez de percorrer todas.
            vazias_seguidas += 1
            if todas and vazias_seguidas >= LIMITE_LINHAS_VAZIAS:
                break
    wb.close()
    return todas


def _montar(cabecalho: list, corpo: list[list]) -> list[dict]:
    mapa = _mapear_cabecalho([str(c) for c in cabecalho])
    encontradas = ", ".join(f"'{str(c).strip()}'" for c in cabecalho if str(c).strip()) or "nenhuma"
    if "nome" not in mapa or "matricula" not in mapa:
        raise ValueError(
            "A planilha precisa das colunas 'nome' e 'matricula' (ou 'código'). "
            f"Colunas encontradas: {encontradas}. Baixe o modelo para conferir."
        )
    if ("cpf" in mapa) != ("nascimento" in mapa):
        faltando = "CPF" if "cpf" not in mapa else "data de nascimento"
        raise ValueError(
            f"A planilha tem só uma das colunas de identificação: falta a coluna de {faltando}. "
            f"Colunas encontradas: {encontradas}."
        )
    resultado = []
    for numero, linha in enumerate(corpo, start=2):

        def pegar(chave: str) -> str:
            indice = mapa.get(chave)
            if indice is None or indice >= len(linha):
                return ""
            return _celula_para_texto(linha[indice])

        resultado.append(
            {
                "linha": numero,
                "nome": pegar("nome"),
                "matricula": pegar("matricula"),
                "setor": pegar("setor"),
                # Lidos so para calcular os codigos; nunca saem desta funcao
                # para o banco, para a resposta ou para logs.
                "nascimento": pegar("nascimento"),
                "cpf": pegar("cpf"),
            }
        )
    return resultado


def validar_linhas(
    linhas: list[dict],
    matriculas_existentes: set[str] | dict[str, str | None],
    cpfs_existentes: dict[str, str] | None = None,
) -> list[dict]:
    """Valida as linhas e calcula os codigos de identificacao.

    `matriculas_existentes`: matriculas NORMALIZADAS do evento (ou um dict
    normalizada -> cpf_hash). `cpfs_existentes`: cpf_hash -> matricula
    normalizada de quem ja tem aquele CPF no evento.

    A saida nunca contem CPF nem data de nascimento: so os codigos HMAC e a
    indicacao de que a identificacao esta completa.
    """
    existentes = {normalizar_matricula(m) for m in matriculas_existentes}
    cpfs_existentes = cpfs_existentes or {}
    vistas: dict[str, int] = {}
    cpfs_vistos: dict[str, int] = {}
    saida = []
    for bruta in linhas:
        erros: list[str] = []
        nome = (bruta["nome"] or "").strip()
        matricula = (bruta["matricula"] or "").strip()
        setor = (bruta["setor"] or "").strip()
        normalizada = normalizar_matricula(matricula)

        if not nome:
            erros.append("Nome em branco")
        if len(nome) > 200:
            erros.append("Nome com mais de 200 caracteres")
        if not matricula:
            erros.append("Matricula em branco")
        if len(matricula) > 60:
            erros.append("Matricula com mais de 60 caracteres")

        duplicada = normalizada != "" and normalizada in vistas
        if duplicada:
            erros.append(f"Matricula repetida na planilha (linha {vistas[normalizada]})")
        elif normalizada:
            vistas[normalizada] = bruta["linha"]

        ja_existe = normalizada in existentes

        # --- identificacao (CPF + nascimento), opcional por linha
        texto_cpf = (bruta.get("cpf") or "").strip()
        texto_nascimento = (bruta.get("nascimento") or "").strip()
        codigo_identificacao = codigo_cpf = None
        if texto_cpf or texto_nascimento:
            cpf = identificacao.normalizar_cpf(texto_cpf) if texto_cpf else None
            nascimento = identificacao.normalizar_nascimento(texto_nascimento) if texto_nascimento else None
            if not texto_cpf:
                erros.append("CPF em branco (informe CPF e nascimento juntos)")
            elif cpf is None:
                erros.append("CPF inválido")
            if not texto_nascimento:
                erros.append("Data de nascimento em branco (informe CPF e nascimento juntos)")
            elif nascimento is None:
                erros.append("Data de nascimento inválida (use dd/mm/aaaa)")
            if cpf is not None:
                codigo_cpf = identificacao.codigo_cpf(cpf)
                if codigo_cpf in cpfs_vistos:
                    erros.append(f"CPF repetido na planilha (linha {cpfs_vistos[codigo_cpf]})")
                else:
                    cpfs_vistos[codigo_cpf] = bruta["linha"]
                dono = cpfs_existentes.get(codigo_cpf)
                if dono is not None and dono != normalizada:
                    erros.append("CPF já cadastrado para outra matrícula neste evento")
            if cpf is not None and nascimento is not None:
                codigo_identificacao = identificacao.codigo_identificacao(nascimento, cpf[:5])

        saida.append(
            {
                "linha": bruta["linha"],
                "nome": nome,
                "matricula": matricula,
                "setor": setor,
                "erros": erros,
                "duplicada_na_planilha": duplicada,
                "ja_existe_no_evento": ja_existe,
                "tem_identificacao": codigo_identificacao is not None,
                "codigo_identificacao": codigo_identificacao if not erros else None,
                "codigo_cpf": codigo_cpf if not erros else None,
            }
        )
    return saida


# CPFs de exemplo com digitos verificadores validos, mas ficticios.
_EXEMPLOS = [
    ["Maria de Souza", "000123", "Financeiro", "15/03/1990", "529.982.247-25"],
    ["Joao Pereira", "000124", "Producao", "02/11/1985", "111.444.777-35"],
]
_CABECALHO = ["nome", "matricula", "setor", "data_nascimento", "cpf"]


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
    ws.title = "participantes"
    ws.append(_CABECALHO)
    for linha in _EXEMPLOS:
        ws.append(linha)
    # Matricula, nascimento e CPF como texto: preserva zeros a esquerda.
    for linha in ws.iter_rows(min_col=2, max_col=5):
        for celula in linha:
            if celula.column != 3:
                celula.number_format = "@"
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["D"].width = 18
    ws.column_dimensions["E"].width = 18
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
