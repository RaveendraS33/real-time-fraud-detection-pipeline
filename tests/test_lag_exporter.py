from fraud_detection.lag_exporter import compute_lag


def test_compute_lag_behind() -> None:
    assert compute_lag(high_watermark=100, committed_offset=90) == 10


def test_compute_lag_caught_up() -> None:
    assert compute_lag(high_watermark=100, committed_offset=100) == 0


def test_compute_lag_no_committed_offset() -> None:
    assert compute_lag(high_watermark=100, committed_offset=-1) == 0
