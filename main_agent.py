"""Matching agentico transazioni carta vs gestionale (LangChain)."""

import sys
import time

from trans_matching.llm_usage import format_llm_cost_line, reset_llm_usage
from trans_matching.openai_http import verify_openai_connection
from trans_matching.paths import DB_PATH, REPORT_AGENT
from trans_matching.agent.pipeline import run_agent_matching
from trans_matching.reports.html_agent import generate_agent_html_report
from trans_matching.timing import format_elapsed


def main() -> None:
    started_at = time.perf_counter()
    reset_llm_usage()

    try:
        verify_openai_connection()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    results, run_id, logger = run_agent_matching()
    elapsed = time.perf_counter() - started_at

    generate_agent_html_report(REPORT_AGENT, run_id=run_id)

    matched = sum(1 for result in results if result.matched)
    ambiguous = sum(1 for result in results if result.is_ambiguous)

    print(f"Transazioni carta:       {len(results)}")
    print(f"Match:                   {matched}/{len(results)}")
    print(f"Ambigui:                 {ambiguous}")
    print(f"Run agent salvata:       #{run_id} ({DB_PATH.name})")
    print(f"Log debug:               {logger.log_path}")
    llm_cost = format_llm_cost_line()
    if llm_cost is not None:
        print(f"Costo API LLM:           {llm_cost}")
    print(f"Report:                  {REPORT_AGENT.name}")
    print(f"Tempo totale:            {format_elapsed(elapsed)}")


if __name__ == "__main__":
    main()
