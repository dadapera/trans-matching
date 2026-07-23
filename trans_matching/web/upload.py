from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException, UploadFile

from trans_matching.models import Transaction
from trans_matching.parsers.amex import parse_amex_file
from trans_matching.parsers.gestionale import parse_gestionale_pdf
from trans_matching.parsers.pdf_text import pdf_has_text_layer, pdf_page_count

ProgressCallback = Callable[[int, int, str], None]


def validate_upload_names(carta_name: str, gestionale_name: str) -> tuple[str, str]:
    carta_suffix = Path(carta_name).suffix.lower()
    gestionale_suffix = Path(gestionale_name).suffix.lower()
    if carta_suffix not in {".csv", ".pdf"}:
        raise HTTPException(status_code=400, detail="Il file carta deve essere CSV o PDF")
    if gestionale_suffix != ".pdf":
        raise HTTPException(status_code=400, detail="Il file gestionale deve essere PDF")
    return carta_suffix, gestionale_suffix


def parse_carta_and_gestionale(
    carta_path: Path,
    gestionale_path: Path,
    *,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[Transaction], list[Transaction]]:
    carta_suffix = carta_path.suffix.lower()
    needs_ocr = (
        carta_suffix == ".pdf"
        and not pdf_has_text_layer(carta_path)
    )
    carta_steps = pdf_page_count(carta_path) if needs_ocr else 1
    total_steps = max(1, carta_steps) + 1

    def report(done: int, message: str) -> None:
        if on_progress is not None:
            on_progress(done, total_steps, message)

    def carta_progress(current: int, total: int, message: str) -> None:
        # Map carta-local progress onto the overall job (leave last step for gestionale).
        if total <= 0:
            report(0, message)
            return
        mapped = int(round((current / total) * carta_steps))
        report(min(mapped, carta_steps), message)

    report(0, "Avvio parsing carta…")
    try:
        card_txns = parse_amex_file(carta_path, on_progress=carta_progress)
    except Exception as exc:
        raise ValueError(f"Errore parsing file carta: {exc}") from exc

    report(carta_steps, "Parsing gestionale…")
    try:
        gestionale_txns = parse_gestionale_pdf(gestionale_path)
    except Exception as exc:
        raise ValueError(f"Errore parsing PDF gestionale: {exc}") from exc

    if not card_txns:
        raise ValueError("Nessuna transazione nel file carta")
    if not gestionale_txns:
        raise ValueError("Nessuna transazione nel PDF gestionale")

    report(total_steps, "Completato")
    return card_txns, gestionale_txns


async def read_upload_bytes(
    carta: UploadFile,
    gestionale: UploadFile,
) -> tuple[bytes, bytes, str, str]:
    carta_name = carta.filename or "carta.csv"
    gestionale_name = gestionale.filename or "gestionale.pdf"
    validate_upload_names(carta_name, gestionale_name)

    carta_bytes = await carta.read()
    gestionale_bytes = await gestionale.read()
    if not carta_bytes:
        raise HTTPException(status_code=400, detail="File carta vuoto")
    if not gestionale_bytes:
        raise HTTPException(status_code=400, detail="File gestionale vuoto")

    return carta_bytes, gestionale_bytes, carta_name, gestionale_name
