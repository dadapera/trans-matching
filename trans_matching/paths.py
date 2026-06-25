import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT))
CARTA_DIR = ROOT / "carta-credito"
GESTIONALE_DIR = ROOT / "gestionale"
REPORT_AMOUNT = ROOT / "report_matching.html"
REPORT_AGENT = ROOT / "report_agent_matching.html"
DB_PATH = Path(os.environ.get("DB_PATH", _DATA_DIR / "matching.db"))
AGENT_LOG_DIR = _DATA_DIR / "logs"
