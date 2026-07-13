from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from trans_matching.models import Transaction
from trans_matching.parsers.amex import parse_amex_file
from trans_matching.parsers.gestionale import parse_gestionale_pdf


async def parse_upload_files(
    carta: UploadFile,
    gestionale: UploadFile,
) -> tuple[list[Transaction], list[Transaction], str, str]:
    carta_name = carta.filename or "carta.csv"
    gestionale_name = gestionale.filename or "gestionale.pdf"

    carta_suffix = Path(carta_name).suffix.lower()
    gestionale_suffix = Path(gestionale_name).suffix.lower()
    if carta_suffix not in {".csv", ".pdf"}:
        raise HTTPException(status_code=400, detail="Il file carta deve essere CSV o PDF")
    if gestionale_suffix != ".pdf":
        raise HTTPException(status_code=400, detail="Il file gestionale deve essere PDF")

    carta_bytes = await carta.read()
    gestionale_bytes = await gestionale.read()
    if not carta_bytes:
        raise HTTPException(status_code=400, detail="File carta vuoto")
    if not gestionale_bytes:
        raise HTTPException(status_code=400, detail="File gestionale vuoto")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        carta_path = tmp / f"carta{carta_suffix}"
        gestionale_path = tmp / "gestionale.pdf"
        carta_path.write_bytes(carta_bytes)
        gestionale_path.write_bytes(gestionale_bytes)

        try:
            card_txns = parse_amex_file(carta_path)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Errore parsing file carta: {exc}",
            ) from exc

        try:
            gestionale_txns = parse_gestionale_pdf(gestionale_path)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Errore parsing PDF gestionale: {exc}",
            ) from exc

    if not card_txns:
        raise HTTPException(status_code=400, detail="Nessuna transazione nel file carta")
    if not gestionale_txns:
        raise HTTPException(status_code=400, detail="Nessuna transazione nel PDF gestionale")

    return card_txns, gestionale_txns, carta_name, gestionale_name
