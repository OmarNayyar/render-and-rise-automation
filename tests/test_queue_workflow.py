from __future__ import annotations

import csv

import pytest

from render_and_rise.rr_gui import Row, TaskWorker, read_queue, write_queue
from render_and_rise.workflow import approve_qa2, require_ready_for_publish


def test_queue_round_trip_preserves_extra_columns(tmp_path) -> None:
    queue_path = tmp_path / "queue.csv"
    rows = [
        Row(
            product_id="RR-DEMO-001",
            title="Demo",
            status="READY",
            notes="reviewed",
            master_path="products/RR-DEMO-001/master/raw.png",
            extras={
                "dropbox_link": "https://www.dropbox.com/scl/fo/example?dl=0",
                "custom_metadata": "preserved",
            },
        )
    ]

    write_queue(queue_path, rows)
    loaded = read_queue(queue_path)

    assert loaded[0].extras["dropbox_link"].endswith("dl=0")
    assert loaded[0].extras["custom_metadata"] == "preserved"


def test_legacy_dropbox_key_is_migrated_on_read_and_write(tmp_path) -> None:
    queue_path = tmp_path / "queue.csv"
    queue_path.write_text(
        "product_id,title,status,notes,master_path,dropbox_share_link,custom_metadata\n"
        "RR-DEMO-001,Demo,BUILT,,,https://www.dropbox.com/scl/fo/example?dl=1,kept\n",
        encoding="utf-8",
    )

    rows = read_queue(queue_path)
    write_queue(queue_path, rows)

    with queue_path.open(newline="", encoding="utf-8") as handle:
        stored = list(csv.DictReader(handle))

    assert stored[0]["dropbox_link"].endswith("dl=1")
    assert "dropbox_share_link" not in stored[0]
    assert stored[0]["custom_metadata"] == "kept"


def test_qa2_only_approves_built_products() -> None:
    assert approve_qa2("BUILT") == "READY"
    with pytest.raises(ValueError, match="requires status BUILT"):
        approve_qa2("APPROVED")


def test_publication_requires_ready_status() -> None:
    require_ready_for_publish("READY")
    with pytest.raises(ValueError, match="requires status READY"):
        require_ready_for_publish("BUILT")


def test_task_worker_preserves_custom_success_message() -> None:
    messages: list[tuple[bool, str]] = []
    worker = TaskWorker(lambda _emit: None, success_message="Custom completion message")
    worker.done.connect(lambda success, message: messages.append((success, message)))

    worker.run()

    assert messages == [(True, "Custom completion message")]
