"""Matching transazioni carta di credito vs gestionale."""

import time

from trans_matching.llm_usage import format_llm_cost_line
from trans_matching.paths import DB_PATH, REPORT_AMOUNT
from trans_matching.pipeline import run_matching
from trans_matching.reports.html import generate_html_report
from trans_matching.storage import save_run
from trans_matching.timing import format_elapsed


def main() -> None:
    started_at = time.perf_counter()

    results = run_matching()
    elapsed = time.perf_counter() - started_at

    run_id = save_run(results, elapsed_seconds=elapsed)
    generate_html_report(REPORT_AMOUNT, run_id=run_id)

    matched = sum(1 for r in results if r.is_matched)

    print(f"Transazioni carta:       {len(results)}")
    print(f"Match:                   {matched}/{len(results)}")
    print(f"Run salvata:             #{run_id} ({DB_PATH.name})")
    llm_cost = format_llm_cost_line()
    if llm_cost is not None:
        print(f"Costo API LLM:           {llm_cost}")
    print(f"Tempo totale:            {format_elapsed(elapsed)}")


if __name__ == "__main__":
    main()
