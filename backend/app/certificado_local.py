"""Certificado HTTPS para a rede local do evento.

O navegador so libera a camera ao vivo (scanner de QR Code) em HTTPS. Na rede
local nao ha dominio publico, entao geramos:

* uma autoridade certificadora propria (CA), valida por 10 anos, em
  DATA_DIR/https/ca.crt - pode ser instalada nos aparelhos para tirar o aviso
  "conexao nao e particular";
* o certificado do servidor, assinado por essa CA, para localhost, 127.0.0.1,
  o nome deste computador e os IPs da rede local. Validade de 397 dias (limite
  aceito pelos navegadores). E refeito sozinho quando um IP novo aparece ou
  quando faltam menos de 30 dias para vencer; a CA e mantida, entao aparelhos
  que ja confiam nela continuam confiando.

Uso: python -m app.certificado_local [ip ...]
Imprime as linhas CERT=..., CHAVE=..., CA=... para o script de inicio.
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

NOME_CA = "Sorteios Mallory - CA local"
VALIDADE_CA = dt.timedelta(days=3650)
VALIDADE_SERVIDOR = dt.timedelta(days=397)
RENOVAR_ANTES = dt.timedelta(days=30)


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _salvar_chave(chave: ec.EllipticCurvePrivateKey, caminho: Path) -> None:
    caminho.write_bytes(
        chave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def _ler_chave(caminho: Path) -> ec.EllipticCurvePrivateKey:
    chave = serialization.load_pem_private_key(caminho.read_bytes(), password=None)
    assert isinstance(chave, ec.EllipticCurvePrivateKey)
    return chave


def _gerar_ca(pasta: Path) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    chave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, NOME_CA),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Mallory"),
    ])
    inicio = _agora() - dt.timedelta(minutes=5)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome)
        .issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(inicio)
        .not_valid_after(inicio + VALIDADE_CA)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(chave.public_key()), critical=False)
        .sign(chave, hashes.SHA256())
    )
    _salvar_chave(chave, pasta / "ca.key")
    (pasta / "ca.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    # Mesma CA em DER (.cer): formato que Windows e Android abrem com dois toques.
    (pasta / "ca.cer").write_bytes(cert.public_bytes(serialization.Encoding.DER))
    return cert, chave


def _carregar_ou_gerar_ca(pasta: Path) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey]:
    crt, key = pasta / "ca.crt", pasta / "ca.key"
    if crt.exists() and key.exists():
        cert = x509.load_pem_x509_certificate(crt.read_bytes())
        if cert.not_valid_after_utc - _agora() > RENOVAR_ANTES:
            return cert, _ler_chave(key)
    return _gerar_ca(pasta)


def ips_da_rede() -> list[str]:
    """IPv4 deste computador (sem loopback nem link-local)."""
    ips: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(str(info[4][0]))
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # nenhum pacote e enviado
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.")))


def _nomes_desejados(ips: list[str]) -> tuple[set[str], set[str]]:
    dns = {"localhost"}
    nome = socket.gethostname().strip()
    if nome:
        dns.add(nome.lower())
    return dns, {"127.0.0.1", *ips}


def _cobertura(cert: x509.Certificate) -> tuple[set[str], set[str]]:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return set(), set()
    return (
        {n.lower() for n in san.get_values_for_type(x509.DNSName)},
        {str(i) for i in san.get_values_for_type(x509.IPAddress)},
    )


def garantir_certificado(pasta: Path, ips: list[str] | None = None) -> tuple[Path, Path, Path]:
    """Devolve (certificado, chave, ca), criando ou renovando o que for preciso."""
    pasta.mkdir(parents=True, exist_ok=True)
    ips = ips_da_rede() if ips is None else ips
    ca_cert, ca_chave = _carregar_ou_gerar_ca(pasta)
    crt, key = pasta / "servidor.crt", pasta / "servidor.key"
    dns, ips_alvo = _nomes_desejados(ips)

    if crt.exists() and key.exists():
        atual = x509.load_pem_x509_certificate(crt.read_bytes())
        dns_ok, ips_ok = _cobertura(atual)
        if (
            atual.issuer == ca_cert.subject
            and atual.not_valid_after_utc - _agora() > RENOVAR_ANTES
            and dns <= dns_ok
            and ips_alvo <= ips_ok
        ):
            return crt, key, pasta / "ca.crt"

    chave = ec.generate_private_key(ec.SECP256R1())
    inicio = _agora() - dt.timedelta(minutes=5)
    nomes: list[x509.GeneralName] = [x509.DNSName(n) for n in sorted(dns)]
    nomes += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in sorted(ips_alvo)]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Sorteios Mallory (rede local)")]))
        .issuer_name(ca_cert.subject)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(inicio)
        .not_valid_after(min(inicio + VALIDADE_SERVIDOR, ca_cert.not_valid_after_utc))
        .add_extension(x509.SubjectAlternativeName(nomes), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=False, content_commitment=False,
                data_encipherment=False, key_agreement=True, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_chave.public_key()), critical=False
        )
        .sign(ca_chave, hashes.SHA256())
    )
    _salvar_chave(chave, key)
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return crt, key, pasta / "ca.crt"


def main(argv: list[str]) -> int:
    from .config import DATA_DIR

    ips = argv or None
    crt, key, ca = garantir_certificado(DATA_DIR / "https", ips)
    print(f"CERT={crt}")
    print(f"CHAVE={key}")
    print(f"CA={ca}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
