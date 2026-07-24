from pathlib import Path

from trans_matching.storage.agent_repository import (
    create_agent_run,
    get_agent_run,
    mark_orphaned_running_runs,
    update_agent_run,
)


def test_mark_orphaned_running_runs(tmp_path: Path) -> None:
    db = tmp_path / "matching.db"
    running_id = create_agent_run(3, db_path=db)
    done_id = create_agent_run(1, db_path=db)
    update_agent_run(done_id, status="completed", db_path=db)

    assert mark_orphaned_running_runs(db_path=db) == 1
    assert get_agent_run(running_id, db_path=db).status == "error"
    assert get_agent_run(done_id, db_path=db).status == "completed"
    assert mark_orphaned_running_runs(db_path=db) == 0
