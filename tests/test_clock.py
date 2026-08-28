from src.clock import Clock


def test_stop_turn_deducts_elapsed_time_from_the_running_color():
    clock = Clock(white_ms=60_000, black_ms=60_000, increment_ms=0)
    clock.start_turn("white", now_ms=0)

    clock.stop_turn(now_ms=5_000)

    assert clock.remaining_ms("white") == 55_000
    assert clock.remaining_ms("black") == 60_000  # untouched


def test_increment_applied_only_to_the_side_that_just_moved():
    clock = Clock(white_ms=60_000, black_ms=60_000, increment_ms=2_000)
    clock.start_turn("white", now_ms=0)

    clock.stop_turn(now_ms=5_000)

    assert clock.remaining_ms("white") == 60_000 - 5_000 + 2_000
    assert clock.remaining_ms("black") == 60_000


def test_stop_turn_is_a_no_op_when_nothing_is_running():
    clock = Clock(white_ms=60_000, black_ms=60_000, increment_ms=1_000)

    clock.stop_turn(now_ms=99_999)  # no start_turn call at all

    assert clock.remaining_ms("white") == 60_000
    assert clock.remaining_ms("black") == 60_000


def test_remaining_ms_is_floored_at_zero_before_the_increment():
    # Defensive floor: the caller is expected to check is_flagged before
    # ever calling stop_turn, but this must never go negative regardless.
    clock = Clock(white_ms=1_000, black_ms=60_000, increment_ms=500)
    clock.start_turn("white", now_ms=0)

    clock.stop_turn(now_ms=10_000)  # far more elapsed than white had

    assert clock.remaining_ms("white") == 0 + 500


def test_start_turn_switches_which_color_is_running():
    clock = Clock(white_ms=60_000, black_ms=60_000, increment_ms=0)
    clock.start_turn("white", now_ms=0)
    clock.stop_turn(now_ms=3_000)

    clock.start_turn("black", now_ms=3_000)
    clock.stop_turn(now_ms=10_000)

    assert clock.remaining_ms("white") == 57_000
    assert clock.remaining_ms("black") == 53_000


def test_is_flagged_true_once_remaining_time_reaches_zero():
    clock = Clock(white_ms=5_000, black_ms=60_000, increment_ms=0)
    clock.start_turn("white", now_ms=0)
    clock.stop_turn(now_ms=5_000)

    assert clock.is_flagged("white", now_ms=5_001) is True


def test_is_flagged_false_with_time_still_on_the_clock():
    clock = Clock(white_ms=5_000, black_ms=60_000, increment_ms=0)

    assert clock.is_flagged("white", now_ms=0) is False


def test_is_flagged_accounts_for_a_currently_running_turn_without_stopping_it():
    # The whole point of taking now_ms as a parameter here rather than
    # only via stop_turn: a client can ask "has this side flagged yet?"
    # mid-turn, before any move has actually been made (docs/week-7.md
    # session 1's /timeout endpoint).
    clock = Clock(white_ms=5_000, black_ms=60_000, increment_ms=0)
    clock.start_turn("white", now_ms=0)

    assert clock.is_flagged("white", now_ms=4_000) is False
    assert clock.is_flagged("white", now_ms=5_000) is True
    # Confirms it's non-destructive -- the clock is unaffected by an
    # is_flagged query, only by an actual stop_turn call.
    assert clock.remaining_ms("white") == 5_000


def test_is_flagged_for_a_color_whose_turn_is_not_running_ignores_the_clock():
    clock = Clock(white_ms=5_000, black_ms=0, increment_ms=0)
    clock.start_turn("white", now_ms=0)

    # black's turn isn't running, so its own zero balance is what decides
    # this -- and it's already at zero, so it's flagged regardless of `now_ms`.
    assert clock.is_flagged("black", now_ms=0) is True
