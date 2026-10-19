import pytest

from caixa_inteligente.evaluation import recognition_metrics


def row(expected, known, suggestion, accepted):
    return {
        "expected": expected,
        "is_known": known,
        "visual_prediction": suggestion,
        "text_prediction": suggestion,
        "hybrid_prediction": suggestion,
        "accepted": accepted,
    }


def test_unknown_false_acceptances_reduce_precision_and_are_not_known_errors():
    metrics = recognition_metrics(
        [
            row("a", True, "a", "a"),
            row("b", True, "a", None),
            row("unknown", False, "a", "a"),
            row("other", False, "a", None),
        ]
    )
    assert metrics["known_top1_accuracy"]["hybrid"] == 0.5
    gate = metrics["visual_baseline_gate"]
    assert gate["precision_on_accepted"] == 0.5
    assert gate["unknown_false_acceptance_rate"] == 0.5
    assert gate["known_rejected"] == 1
    assert not metrics["hybrid_rejection_discrimination_validated"]


def test_rejecting_everything_does_not_become_perfect_precision():
    metrics = recognition_metrics([row("a", True, "a", None), row("unknown", False, "a", None)])
    assert metrics["visual_baseline_gate"]["precision_on_accepted"] is None
    assert metrics["visual_baseline_gate"]["coverage"] == 0


def test_unknown_only_suite_has_no_known_accuracy():
    metrics = recognition_metrics([row("unknown", False, "a", None)])
    assert metrics["known_top1_accuracy"]["visual"] is None
    with pytest.raises(ValueError, match="sem consultas"):
        recognition_metrics([])
