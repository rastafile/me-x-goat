from src.engine import Analysis, Candidate
from src.game import Game
from src.narration import DEFAULT_LANGUAGE, LANGUAGES, describe_assessment, describe_move, describe_transition
from src.persona import Choice
from src.tutor import Assessment

WHITE_TO_MOVE_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
WHITE_MATE_IN_1_FEN = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
# Fool's mate's final position -- an already-delivered checkmate, so
# Game(fen=...).is_over() is True with no moves needed to get there.
CHECKMATED_FEN = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"


def _analysis(candidates: list[Candidate], fen: str = WHITE_TO_MOVE_FEN) -> Analysis:
    return Analysis(fen=fen, white_to_move=fen.split()[1] == "w", candidates=candidates)


def test_leads_with_the_highest_weight_tag():
    candidate = Candidate(move="d4d5", score_cp=10, mate_in=None, pv=["d4d5"])
    analysis = _analysis([candidate])
    choice = Choice(move="d4d5", tags=["improve_worst_piece", "queen_trade"], reason_score=4.5)
    game = Game(user_color="white")

    assert describe_move(analysis, choice, game, "en-US").startswith("I'm trading queens while I'm ahead.")
    assert describe_move(analysis, choice, game, "pt-BR").startswith("Estou trocando as damas enquanto estou à frente.")


def test_forced_mate_always_leads_over_style_tags():
    candidate = Candidate(move="d4d5", score_cp=10, mate_in=None, pv=["d4d5"])
    analysis = _analysis([candidate])
    # Hand-built: forced_mate wouldn't really co-occur with style tags in
    # practice, but the lead-picking logic must still rank it highest.
    choice = Choice(move="d4d5", tags=["queen_trade", "forced_mate"], reason_score=float("inf"))
    game = Game(user_color="white")

    assert describe_move(analysis, choice, game, "en-US").startswith("I found a forced mate.")
    assert describe_move(analysis, choice, game, "pt-BR").startswith("Encontrei um mate forçado.")


def test_opening_book_always_leads_over_style_tags():
    candidate = Candidate(move="g1f3", score_cp=20, mate_in=None, pv=["g1f3"])
    analysis = _analysis([candidate])
    choice = Choice(move="g1f3", tags=["opening_book"], reason_score=float("inf"))
    game = Game(user_color="white")

    assert describe_move(analysis, choice, game, "en-US").startswith("This is a line I know well.")
    assert describe_move(analysis, choice, game, "pt-BR").startswith("Essa é uma linha que conheço bem.")


def test_no_tags_falls_back_to_a_generic_line():
    candidate = Candidate(move="e2e4", score_cp=10, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="white")

    assert describe_move(analysis, choice, game, "en-US") == "I'm just playing the strongest move I see."
    assert describe_move(analysis, choice, game, "pt-BR") == "Estou só jogando o lance mais forte que vejo."


def test_tags_never_appear_literally_in_the_output():
    candidate = Candidate(move="d4d5", score_cp=10, mate_in=None, pv=["d4d5"])
    analysis = _analysis([candidate])
    all_tags = ["queen_trade", "toward_endgame", "improve_worst_piece", "keep_tension", "avoid_chaos"]
    choice = Choice(move="d4d5", tags=all_tags, reason_score=8.5)
    game = Game(user_color="white")

    for language in LANGUAGES:
        text = describe_move(analysis, choice, game, language)
        for tag in all_tags:
            assert tag not in text


def test_evaluation_line_appears_when_the_user_is_meaningfully_ahead():
    # user_color=white, White (the user) is ahead by 300 -- the opponent
    # concedes the user is doing well.
    candidate = Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="white")

    en = describe_move(analysis, choice, game, "en-US").splitlines()
    pt = describe_move(analysis, choice, game, "pt-BR").splitlines()

    assert len(en) == len(pt) == 2
    assert en[1] == "You're doing well here, I have to admit."
    assert pt[1] == "Você está bem aqui, tenho que admitir."


def test_evaluation_line_flips_for_a_black_user():
    # Same White-ahead-by-300 position, but the user is Black this time --
    # the opponent (White) should sound pleased with its own position, not
    # concede the user is doing well.
    candidate = Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="black")

    assert describe_move(analysis, choice, game, "en-US").splitlines()[1] == "I like where I stand right now."
    assert describe_move(analysis, choice, game, "pt-BR").splitlines()[1] == "Gosto de como estou agora."


def test_evaluation_line_omitted_when_roughly_balanced():
    candidate = Candidate(move="e2e4", score_cp=20, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="white")

    assert len(describe_move(analysis, choice, game, "en-US").splitlines()) == 1


def test_evaluation_line_omitted_for_a_mate_typed_candidate():
    candidate = Candidate(move="e1e8", score_cp=None, mate_in=1, pv=["e1e8"])
    analysis = _analysis([candidate], fen=WHITE_MATE_IN_1_FEN)
    choice = Choice(move="e1e8", tags=["forced_mate"], reason_score=float("inf"))
    # Not actually pushed here, so the game isn't over -- isolates the
    # eval-line behavior from the outcome-line behavior tested below.
    game = Game(user_color="black", fen=WHITE_MATE_IN_1_FEN)

    assert describe_move(analysis, choice, game, "en-US") == "I found a forced mate."


def test_outcome_line_replaces_the_evaluation_line_when_the_game_is_over():
    candidate = Candidate(move="d8h4", score_cp=None, mate_in=None, pv=["d8h4"])
    analysis = _analysis([candidate], fen=CHECKMATED_FEN)
    choice = Choice(move="d8h4", tags=[], reason_score=0.0)
    game = Game(user_color="white", fen=CHECKMATED_FEN)

    assert describe_move(analysis, choice, game, "en-US") == "I'm just playing the strongest move I see.\nCheckmate."
    assert describe_move(analysis, choice, game, "pt-BR") == "Estou só jogando o lance mais forte que vejo.\nXeque-mate."


def test_at_most_two_lines():
    candidate = Candidate(move="e2e4", score_cp=300, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(
        move="e2e4",
        tags=["queen_trade", "toward_endgame", "improve_worst_piece"],
        reason_score=7.0,
    )
    game = Game(user_color="white")

    for language in LANGUAGES:
        assert len(describe_move(analysis, choice, game, language).splitlines()) <= 2


def test_deterministic_same_input_same_output():
    candidate = Candidate(move="d4d5", score_cp=250, mate_in=None, pv=["d4d5"])
    analysis = _analysis([candidate])
    choice = Choice(move="d4d5", tags=["toward_endgame"], reason_score=2.5)
    game = Game(user_color="black")

    first = describe_move(analysis, choice, game, "en-US")
    second = describe_move(analysis, choice, game, "en-US")

    assert first == second


def test_unknown_language_falls_back_to_the_default():
    candidate = Candidate(move="e2e4", score_cp=10, mate_in=None, pv=["e2e4"])
    analysis = _analysis([candidate])
    choice = Choice(move="e2e4", tags=[], reason_score=0.0)
    game = Game(user_color="white")

    assert describe_move(analysis, choice, game, "fr-FR") == describe_move(analysis, choice, game, DEFAULT_LANGUAGE)


def test_languages_constant_includes_the_default():
    assert DEFAULT_LANGUAGE in LANGUAGES


def test_excellent_and_good_get_one_line_in_both_languages():
    excellent = Assessment(classification="excellent", loss_cp=0, best_move=None, continuation=[], offer_take_back=False)
    good = Assessment(classification="good", loss_cp=20, best_move=None, continuation=[], offer_take_back=False)

    assert describe_assessment(excellent, "en-US") == "Excellent move."
    assert describe_assessment(excellent, "pt-BR") == "Lance excelente."
    assert describe_assessment(good, "en-US") == "Good move."
    assert describe_assessment(good, "pt-BR") == "Bom lance."


def test_mistake_states_the_loss_and_the_stronger_alternative():
    assessment = Assessment(
        classification="mistake", loss_cp=150, best_move="e2e4", continuation=["e2e4", "e7e5"], offer_take_back=False
    )

    en = describe_assessment(assessment, "en-US")
    pt = describe_assessment(assessment, "pt-BR")

    assert en == (
        "That's a mistake -- you gave up about 150 centipawns.\n"
        "The stronger try was e2e4.\n"
        "From there, it likely continues e2e4 e7e5."
    )
    assert pt == (
        "Isso é um erro -- você perdeu cerca de 150 centipeões.\n"
        "A tentativa mais forte era e2e4.\n"
        "A partir daí, provavelmente segue e2e4 e7e5."
    )


def test_blunder_offers_the_take_back_last():
    assessment = Assessment(
        classification="blunder", loss_cp=650, best_move="e2e4", continuation=["e2e4"], offer_take_back=True
    )

    en = describe_assessment(assessment, "en-US")
    pt = describe_assessment(assessment, "pt-BR")

    assert en.endswith("Want to take that back?")
    assert pt.endswith("Quer desfazer esse lance?")


def test_inaccuracy_never_offers_a_take_back():
    assessment = Assessment(
        classification="inaccuracy", loss_cp=60, best_move="e2e4", continuation=["e2e4"], offer_take_back=False
    )

    assert "?" not in describe_assessment(assessment, "en-US")


def test_describe_assessment_falls_back_to_the_default_language():
    assessment = Assessment(classification="good", loss_cp=10, best_move=None, continuation=[], offer_take_back=False)

    assert describe_assessment(assessment, "fr-FR") == describe_assessment(assessment, DEFAULT_LANGUAGE)


def test_describe_transition_has_a_phrase_for_each_transition_in_both_languages():
    for transition in ("queens_off", "file_opens", "pawn_endgame_begins"):
        en = describe_transition(transition, "en-US")
        pt = describe_transition(transition, "pt-BR")

        assert en and isinstance(en, str)
        assert pt and isinstance(pt, str)
        assert en != pt


def test_describe_transition_falls_back_to_the_default_language():
    assert describe_transition("queens_off", "fr-FR") == describe_transition("queens_off", DEFAULT_LANGUAGE)
