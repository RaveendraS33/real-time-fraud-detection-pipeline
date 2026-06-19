import pytest

from fraud_detection.simulator import TransactionSimulator


def test_simulator_can_force_normal_transaction() -> None:
    transaction = TransactionSimulator(seed=7).generate(fraud_rate=0)

    assert transaction.simulation is not None
    assert transaction.simulation.is_fraud is False
    assert transaction.device_id


def test_simulator_can_force_explainable_fraud() -> None:
    transaction = TransactionSimulator(seed=7).generate(fraud_rate=1)

    assert transaction.simulation is not None
    assert transaction.simulation.is_fraud is True
    assert transaction.simulation.scenario in {
        "high_amount",
        "foreign_device",
        "card_testing",
    }
    assert transaction.device_id.startswith("new-device-")


def test_simulator_rejects_invalid_fraud_rate() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        TransactionSimulator().generate(fraud_rate=1.1)
