from __future__ import annotations

import threading

from prometheus.api.jobs import JobManager


def test_queue_position_comes_from_the_live_fifo_queue():
    manager = JobManager(max_workers=1)
    first_started = threading.Event()
    first_release = threading.Event()
    second_started = threading.Event()
    second_release = threading.Event()
    third_started = threading.Event()
    third_release = threading.Event()
    fourth_started = threading.Event()
    fourth_release = threading.Event()

    first = manager.create("first.mp4")
    second = manager.create("second.mp4")
    third = manager.create("third.mp4")
    fourth = manager.create("fourth.mp4")
    manager.submit(first.id, lambda: (first_started.set(), first_release.wait(5)))
    assert first_started.wait(1)
    manager.submit(second.id, lambda: (second_started.set(), second_release.wait(5)))
    manager.submit(third.id, lambda: (third_started.set(), third_release.wait(5)))
    manager.submit(fourth.id, lambda: (fourth_started.set(), fourth_release.wait(5)))

    assert "queue_position" not in manager.public_info(first)
    assert manager.public_info(second)["queue_position"] == 0
    assert manager.public_info(third)["queue_position"] == 1
    assert manager.public_info(fourth)["queue_position"] == 2
    assert set(manager.public_info(third)) == {
        "id", "video_name", "state", "stage", "error", "tier", "queue_position"
    }

    first_release.set()
    assert second_started.wait(1)
    assert "queue_position" not in manager.public_info(second)
    assert manager.public_info(third)["queue_position"] == 0
    assert manager.public_info(fourth)["queue_position"] == 1

    second_release.set()
    assert third_started.wait(1)
    assert "queue_position" not in manager.public_info(third)
    third_release.set()
    assert fourth_started.wait(1)
    assert "queue_position" not in manager.public_info(fourth)
    fourth_release.set()
