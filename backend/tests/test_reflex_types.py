# AI-assisted: written with Claude Code (Anthropic). See docs/AI_USAGE.md.
"""Reflex interface and output contract (Parity Scale L0/L1), without loading the network."""
import pytest

from trace_backend.reflex.types import (
    Choice,
    ChoiceAnswer,
    Noul,
    NoulCriteria,
    Score,
    ScoreAnswer,
    confidence,
    from_dict,
    make_answer,
    option_hypotheses,
    render,
)


@pytest.mark.parametrize("probs,expected", [([0.0, 0.57, 0.43], 0.355), ([0.04, 0.35, 0.61], 0.415),
                                            ([0.34, 0.4, 0.02, 0.24], 0.2), ([0.0, 0.89, 0.11], 0.835),
                                            ([1.0, 0.0, 0.0], 1.0), ([0.25] * 4, 0.0)])
def test_confidence_matches_typesafe_documented_examples(probs, expected):
    assert confidence(probs) == pytest.approx(expected, abs=0.005)


def test_score_answer_is_expected_level():
    a = make_answer(Score("How severe?", ["a", "b", "c"]), ["0", "1", "2"], [0.0, 0.57, 0.43])
    assert isinstance(a, ScoreAnswer) and a.score == pytest.approx(1.43, abs=1e-3)
    assert a.legend[2] == "c"


def test_choice_answer_is_argmax_and_constrained():
    q = Choice("Which team?", {"billing": None, "returns": "Exchanges", "shipping": None})
    a = make_answer(q, list(q.criteria), [0.35, 0.61, 0.04])
    assert isinstance(a, ChoiceAnswer) and a.choice == "returns" and set(a.probabilities) == set(q.criteria)


def test_levels_judged_without_numbers_or_neighbours():
    _, hyps = option_hypotheses(Score("How severe?", ["Cosmetic", "Broken with workaround", "Blocking"]))
    assert all("0" not in h and "Broken" not in h for h in [hyps[0], hyps[2]])


def test_structured_entries_render_deterministically():
    s = render({"what": "Blocking", "examples": ["cannot log in", "data loss"]})
    assert "what: Blocking" in s and "- cannot log in" in s


def test_noul_criteria_and_dict_form():
    q = from_dict({"type": "noul", "instructions": "Refund?", "criteria": {"true": "asks for money back"}})
    keys, hyps = option_hypotheses(q)
    assert keys == ["yes", "no"] and "asks for money back" in hyps[0]
    assert isinstance(q.crit(), NoulCriteria) and isinstance(q, Noul)


def test_limits():
    with pytest.raises(ValueError):
        Score("x", [f"l{i}" for i in range(11)])
    Choice("x", {f"o{i}": None for i in range(255)})
    with pytest.raises(ValueError):
        Choice("x", {f"o{i}": None for i in range(256)})
