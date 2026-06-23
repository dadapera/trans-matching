from __future__ import annotations

import os

import httpx
from openai import APIConnectionError, OpenAI

from trans_matching.config import get_openai_config


def get_openai_ssl_verify() -> bool | str:
    """Configura verifica SSL per httpx/OpenAI.

    Default True. Con proxy/antivirus che intercettano HTTPS su Windows spesso
    serve OPENAI_CA_BUNDLE (cert root aziendale) o OPENAI_VERIFY_SSL=false.
    """
    ca_bundle = os.getenv("OPENAI_CA_BUNDLE", "").strip()
    if ca_bundle:
        return ca_bundle
    raw = os.getenv("OPENAI_VERIFY_SSL", "true").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def build_openai_http_client(*, timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(verify=get_openai_ssl_verify(), timeout=timeout)


def build_openai_async_http_client(*, timeout: float = 60.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(verify=get_openai_ssl_verify(), timeout=timeout)


def verify_openai_connection() -> None:
    """Verifica connettività OpenAI all'avvio; errore chiaro se SSL/rete fallisce."""
    config = get_openai_config()
    try:
        with build_openai_http_client(timeout=20.0) as http_client:
            client = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                http_client=http_client,
            )
            client.models.list()
    except APIConnectionError as exc:
        verify = get_openai_ssl_verify()
        hint = (
            "Prova in .env: OPENAI_VERIFY_SSL=false "
            "(oppure OPENAI_CA_BUNDLE=percorso/certificato-root.pem)."
        )
        if verify is False:
            hint = "Connessione fallita anche con OPENAI_VERIFY_SSL=false: controlla rete/VPN/firewall."
        raise RuntimeError(
            f"OpenAI non raggiungibile: {exc}. {hint}"
        ) from exc
