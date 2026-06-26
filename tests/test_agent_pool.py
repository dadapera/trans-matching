from decimal import Decimal

from trans_matching.agent.pool import GestionalePool
from trans_matching.models import Transaction


def test_find_by_identificativi_accepts_row_signature_without_identifier() -> None:
    txn = Transaction(
        date="25/05/2026",
        amount=Decimal("193.37"),
        description="RYA RYANAIR         ROSSI/MARIO",
        source="gestionale",
    )
    pool = GestionalePool([txn])

    assert pool.find_by_identificativi(["25/05/2026|193.37|RYA RYANAIR ROSSI/MARIO"]) == [txn]


def test_find_by_identificativi_accepts_formatted_row_with_empty_identifier() -> None:
    txn = Transaction(
        date="25/05/2026",
        amount=Decimal("66.00"),
        description="TRE TRENITALIA      BIANCHI/LUCA",
        source="gestionale",
    )
    pool = GestionalePool([txn])

    assert pool.find_by_identificativi(["|25/05/2026|66.00|TRE TRENITALIA BIANCHI/LUCA"]) == [txn]


def test_find_by_identificativi_still_accepts_explicit_identifier() -> None:
    txn = Transaction(
        identificativo="ABC 123",
        date="25/05/2026",
        amount=Decimal("414.00"),
        description="WY OMAN AIR WEB     CAVALLARO/DANILO",
        source="gestionale",
    )
    pool = GestionalePool([txn])

    assert pool.find_by_identificativi(["abc 123"]) == [txn]
