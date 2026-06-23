from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARTA_DIR = ROOT / "carta-credito"
GESTIONALE_DIR = ROOT / "gestionale"
REPORT_AMOUNT = ROOT / "report_matching.html"
REPORT_AGENT = ROOT / "report_agent_matching.html"
DB_PATH = ROOT / "matching.db"
AGENT_LOG_DIR = ROOT / "logs"
