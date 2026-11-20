"""Certificado HTTPS da rede local (scanner de QR Code pela camera)."""
from __future__ import annotations

import datetime as dt
import ipaddress
import ssl

from cryptography import x509

from app import certificado_local as cl


def _san(caminho):
    cert = x509.load_pem_x509_certificate(caminho.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return cert, set(san.get_values_for_type(x509.DNSName)), {str(i) for i in san.get_values_for_type(x509.IPAddress)}


def test_gera_ca_e_certificado_com_ips_da_rede(tmp_path):
    crt, key, ca = cl.garantir_certificado(tmp_path, ["192.168.0.10"])
    cert, dns, ips = _san(crt)
    assert "localhost" in dns
    assert {"127.0.0.1", "192.168.0.10"} <= ips
    assert (tmp_path / "ca.cer").exists()

    ca_cert = x509.load_pem_x509_certificate(ca.read_bytes())
    assert cert.issuer == ca_cert.subject
    assert ca_cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    # Navegadores recusam certificados de servidor com mais de 398 dias.
    assert cert.not_valid_after_utc - cert.not_valid_before_utc <= dt.timedelta(days=398)
    cert.verify_directly_issued_by(ca_cert)


def test_cadeia_valida_para_o_ssl_do_python(tmp_path):
    crt, key, ca = cl.garantir_certificado(tmp_path, ["10.0.0.5"])
    servidor = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    servidor.load_cert_chain(crt, key)  # chave casa com o certificado
    cliente = ssl.create_default_context(cafile=str(ca))
    assert cliente.cert_store_stats()["x509_ca"] == 1


def test_reaproveita_quando_nada_mudou(tmp_path):
    crt, _, _ = cl.garantir_certificado(tmp_path, ["192.168.0.10"])
    antes = crt.read_bytes()
    cl.garantir_certificado(tmp_path, ["192.168.0.10"])
    assert crt.read_bytes() == antes


def test_ip_novo_refaz_o_servidor_e_mantem_a_ca(tmp_path):
    crt, _, ca = cl.garantir_certificado(tmp_path, ["192.168.0.10"])
    ca_antes, srv_antes = ca.read_bytes(), crt.read_bytes()
    cl.garantir_certificado(tmp_path, ["192.168.0.10", "172.17.80.102"])
    assert ca.read_bytes() == ca_antes  # aparelhos que confiam na CA continuam confiando
    assert crt.read_bytes() != srv_antes
    _, _, ips = _san(crt)
    assert ipaddress.ip_address("172.17.80.102") in {ipaddress.ip_address(i) for i in ips}


def test_vencendo_e_renovado(tmp_path, monkeypatch):
    crt, _, _ = cl.garantir_certificado(tmp_path, [])
    antes = crt.read_bytes()
    futuro = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=380)
    monkeypatch.setattr(cl, "_agora", lambda: futuro)
    cl.garantir_certificado(tmp_path, [])
    assert crt.read_bytes() != antes
