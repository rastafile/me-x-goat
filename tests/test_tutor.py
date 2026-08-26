from src.engine import Analysis, Candidate
from src.tutor import assess, classify, loss_cp


def _analysis(white_to_move: bool, score_cp: int | None, move: str = "m", mate_in: int | None = None, pv=None):
    return Analysis(
        fen="irrelevant",
        white_to_move=white_to_move,
        candidates=[Candidate(move=move, score_cp=score_cp, mate_in=mate_in, pv=pv or [move])],
    )


def test_loss_cp_is_zero_when_the_result_matches_the_best_available():
    before = _analysis(white_to_move=True, score_cp=50, move="e2e4")
    after = _analysis(white_to_move=False, score_cp=50, move="e7e5")

    assert loss_cp(before, after, "white") == 0


def test_loss_cp_is_positive_when_the_result_falls_short():
    before = _analysis(white_to_move=True, score_cp=100)
    after = _analysis(white_to_move=False, score_cp=80)

    assert loss_cp(before, after, "white") == 20


def test_loss_cp_matches_for_a_mirrored_black_mover():
    # Same underlying advantage (100 available, 80 achieved), mirrored to a
    # Black mover: stored scores are negated (White's convention), and the
    # mover color flips too. The recurring perspective bug, caught here.
    before = _analysis(white_to_move=False, score_cp=-100)
    after = _analysis(white_to_move=True, score_cp=-80)

    assert loss_cp(before, after, "black") == 20


def test_loss_cp_does_not_crash_on_a_missed_mate_and_lands_as_a_blunder():
    before = _analysis(white_to_move=True, score_cp=None, mate_in=2, move="mate_move")
    after = _analysis(white_to_move=False, score_cp=50)

    loss = loss_cp(before, after, "white")

    assert loss > 300
    assert classify(loss) == "blunder"


def test_classify_boundaries():
    assert classify(0) == "excellent"
    assert classify(10) == "excellent"
    assert classify(11) == "good"
    assert classify(50) == "good"
    assert classify(51) == "inaccuracy"
    assert classify(100) == "inaccuracy"
    assert classify(101) == "mistake"
    assert classify(300) == "mistake"
    assert classify(301) == "blunder"


def test_assess_leaves_best_move_and_continuation_empty_for_a_good_move():
    before = _analysis(white_to_move=True, score_cp=100, move="e2e4", pv=["e2e4", "e7e5", "g1f3"])
    after = _analysis(white_to_move=False, score_cp=70)

    result = assess(before, "e2e4", after, "white")

    assert result.classification == "good"
    assert result.loss_cp == 30
    assert result.best_move is None
    assert result.continuation == []
    assert result.offer_take_back is False


def test_assess_populates_best_move_and_continuation_for_a_mistake():
    before = _analysis(white_to_move=True, score_cp=100, move="d1h5", pv=["d1h5", "b8c6", "f1c4", "g8f6"])
    after = _analysis(white_to_move=False, score_cp=-100)

    result = assess(before, "a2a3", after, "white")

    assert result.classification == "mistake"
    assert result.loss_cp == 200
    assert result.best_move == "d1h5"
    assert result.continuation == ["d1h5", "b8c6", "f1c4", "g8f6"]
    assert result.offer_take_back is False


def test_assess_offers_take_back_only_for_a_blunder():
    before = _analysis(white_to_move=True, score_cp=300, move="d1h5", pv=["d1h5", "b8c6"])
    after = _analysis(white_to_move=False, score_cp=-100)

    result = assess(before, "a2a3", after, "white")

    assert result.classification == "blunder"
    assert result.offer_take_back is True
