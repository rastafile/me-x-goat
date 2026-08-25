from src.engine import Analysis, Candidate
from src.game import Game
from src.narration import describe_move
from src.persona import Choice

WHITE_TO_MOVE_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
WHITE_MATE_IN_1_FEN = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"


def _analysis(candidates: list[Candidate], fen: str = WHITE_TO_MOVE_FEN) -> Analysis:
    return Analysis(fen=fen, white_to_move=fen.split()[1] == "w", candidates=candidates)


def test_leads_with_the_highest_weight_tag():
    candidate = Candidate(move="d4d5", score_cp=10, mate_in=None, pv=["d4d5"])
    analysis = _analysis([candidate])
    choice = Choice(move="d4d5", tags=["improve_worst_piece", "queen_trade"], reason_score=4.5)
    game = Game(user_color="white")

    text = describe_move(analysis, choice, game)

    assert text.startswith("I'm trading queens while I'm ahead.")


def test_forced_mate_always_leads_over_style_tags():
    candidate = Candidate(move="d4d5", score_cp=10, mate_in=None, pv=["d4d5"])
    analysis = _analysis([candidate])
    # Hand-built: forced_mate wouldn't really co-occur with style tags in
    # practice, but the lead-picking logic must still rank it highest.
    choice = Choice(move="d4d5", tags=["queen_trade", "forced_mate"], reason_score=float("inf"))
    game = Game(user_color="white")

    text = describe_move(analysis, choice, game)

    assert text.startswith("I found a forced mate.")


def test_no_tags_falls_back_to_a_generic_line():
    candidate = Candidate(move="e2e4", score_cp=10, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="white")

    text = describe_move(analysis, choice, game)

    assert text == "I'm just playing the strongest move I see."


def test_tags_never_appear_literally_in_the_output():
    candidate = Candidate(move="d4d5", score_cp=10, mate_in=None, pv=["d4d5"])
    analysis = _analysis([candidate])
    all_tags = ["queen_trade", "toward_endgame", "improve_worst_piece", "keep_tension", "avoid_chaos"]
    choice = Choice(move="d4d5", tags=all_tags, reason_score=8.5)
    game = Game(user_color="white")

    text = describe_move(analysis, choice, game)

    for tag in all_tags:
        assert tag not in text


def test_evaluation_line_appears_when_the_user_is_meaningfully_ahead():
    # user_color=white, White (the user) is ahead by 300 -- the opponent
    # concedes the user is doing well.
    candidate = Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="white")

    text = describe_move(analysis, choice, game)
    lines = text.splitlines()

    assert len(lines) == 2
    assert lines[1] == "You're doing well here, I have to admit."


def test_evaluation_line_flips_for_a_black_user():
    # Same White-ahead-by-300 position, but the user is Black this time --
    # the opponent (White) should sound pleased with its own position, not
    # concede the user is doing well.
    candidate = Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="black")

    text = describe_move(analysis, choice, game)

    assert text.splitlines()[1] == "I like where I stand right now."


def test_evaluation_line_omitted_when_roughly_balanced():
    candidate = Candidate(move="e2e4", score_cp=20, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="white")

    text = describe_move(analysis, choice, game)

    assert len(text.splitlines()) == 1


def test_evaluation_line_omitted_for_a_mate_typed_candidate():
    candidate = Candidate(move="e1e8", score_cp=None, mate_in=1, pv=["e1e8"])
    analysis = _analysis([candidate], fen=WHITE_MATE_IN_1_FEN)
    choice = Choice(move="e1e8", tags=["forced_mate"], reason_score=float("inf"))
    # Not actually pushed here, so the game isn't over -- isolates the
    # eval-line behavior from the outcome-line behavior tested below.
    game = Game(user_color="black", fen=WHITE_MATE_IN_1_FEN)

    text = describe_move(analysis, choice, game)

    assert text == "I found a forced mate."


def test_outcome_line_replaces_the_evaluation_line_when_the_game_is_over():
    candidate = Candidate(move="e1e8", score_cp=None, mate_in=1, pv=["e1e8"])
    analysis = _analysis([candidate], fen=WHITE_MATE_IN_1_FEN)
    choice = Choice(move="e1e8", tags=["forced_mate"], reason_score=float("inf"))
    game = Game(user_color="black", fen=WHITE_MATE_IN_1_FEN)
    game.push("e1e8")

    text = describe_move(analysis, choice, game)

    assert text == "I found a forced mate.\nCheckmate."


def test_at_most_two_lines():
    candidate = Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(
        move="e2e4",
        tags=["queen_trade", "toward_endgame", "improve_worst_piece"],
        reason_score=7.0,
    )
    game = Game(user_color="white")

    text = describe_move(analysis, choice, game)

    assert len(text.splitlines()) <= 2


def test_deterministic_same_input_same_output():
    candidate = Candidate(move="d4d5", score_cp=250, mate_in=None, pv=["d4d5"])
    analysis = _analysis([candidate])
    choice = Choice(move="d4d5", tags=["toward_endgame"], reason_score=2.5)
    game = Game(user_color="black")

    first = describe_move(analysis, choice, game)
    second = describe_move(analysis, choice, game)

    assert first == second
