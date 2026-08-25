import subprocess

import chess
import pytest

from src.engine import Analysis, Candidate, Engine, EngineUnavailable

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
WHITE_MATE_IN_1_FEN = "6k1/5ppp/8/8/8/8/5PPP/4R1K1 w - - 0 1"
WHITE_MATED_IN_1_FEN = "K7/8/1k6/8/8/8/8/r6r w - - 0 1"


class _FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        return self._lines.pop(0) if self._lines else ""


class _FakeStdin:
    def __init__(self) -> None:
        self.fail_with: type[Exception] | None = None
        self.written: list[str] = []

    def write(self, data: str) -> None:
        if self.fail_with is not None:
            raise self.fail_with()
        self.written.append(data)

    def flush(self) -> None:
        pass


class _FakeProcess:
    def __init__(
        self,
        stdout_lines: list[str] = (),
        wait_side_effect: Exception | None = None,
    ) -> None:
        self.stdout = _FakeStdout(list(stdout_lines))
        self.stdin = _FakeStdin()
        self.returncode: int | None = None
        self.wait_side_effect = wait_side_effect
        self.wait_calls = 0
        self.kill_calls = 0

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.wait_side_effect is not None:
            raise self.wait_side_effect
        self.returncode = 0
        return self.returncode

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9


def _bare_engine(process: _FakeProcess) -> Engine:
    engine = Engine.__new__(Engine)
    engine._process = process
    return engine


# 1. readline() instead of stdout iteration, EngineUnavailable on a closed pipe.


def test_wait_for_raises_engine_unavailable_when_pipe_closes_before_token():
    engine = _bare_engine(_FakeProcess(stdout_lines=["info string mid-search\n"]))
    with pytest.raises(EngineUnavailable):
        engine._wait_for("uciok")


def test_read_until_raises_engine_unavailable_when_pipe_closes_before_token():
    engine = _bare_engine(_FakeProcess(stdout_lines=["info depth 1 seldepth 1\n"]))
    with pytest.raises(EngineUnavailable):
        engine._read_until("bestmove")


# 2. close() is idempotent and kills the process on a failed shutdown.


def test_close_is_idempotent():
    process = _FakeProcess()
    engine = _bare_engine(process)

    engine.close()
    assert process.wait_calls == 1

    engine.close()
    assert process.wait_calls == 1  # second call sees poll() != None, returns early


@pytest.mark.parametrize(
    "make_process",
    [
        lambda: _FakeProcess(wait_side_effect=subprocess.TimeoutExpired(cmd="stockfish", timeout=2)),
        lambda: _FakeProcess(),  # stdin.write fails below instead of wait()
    ],
    ids=["wait-timeout", "send-quit-fails"],
)
def test_close_kills_process_on_failed_shutdown(make_process):
    process = make_process()
    if process.wait_side_effect is None:
        process.stdin.fail_with = BrokenPipeError
    engine = _bare_engine(process)

    engine.close()

    assert process.kill_calls == 1


def test_close_kills_process_on_value_error():
    process = _FakeProcess()
    process.stdin.fail_with = ValueError
    engine = _bare_engine(process)

    engine.close()

    assert process.kill_calls == 1


# 3. Analysis.loss_cp


def test_loss_cp_from_white_to_move():
    candidates = [
        Candidate(move="e2e4", score_cp=50, mate_in=None, pv=["e2e4"]),
        Candidate(move="d2d4", score_cp=30, mate_in=None, pv=["d2d4"]),
        Candidate(move="a2a3", score_cp=-10, mate_in=None, pv=["a2a3"]),
    ]
    analysis = Analysis(fen="irrelevant", white_to_move=True, candidates=candidates)

    assert analysis.loss_cp(candidates[0]) == 0
    assert analysis.loss_cp(candidates[1]) == 20
    assert analysis.loss_cp(candidates[2]) == 60


def test_loss_cp_from_black_to_move():
    # Stored scores are normalized to White's perspective; candidates[0] is
    # still the best move for Black, so it holds the most negative value.
    candidates = [
        Candidate(move="e7e5", score_cp=-50, mate_in=None, pv=["e7e5"]),
        Candidate(move="c7c5", score_cp=-30, mate_in=None, pv=["c7c5"]),
        Candidate(move="a7a6", score_cp=10, mate_in=None, pv=["a7a6"]),
    ]
    analysis = Analysis(fen="irrelevant", white_to_move=False, candidates=candidates)

    assert analysis.loss_cp(candidates[0]) == 0
    assert analysis.loss_cp(candidates[1]) == 20
    assert analysis.loss_cp(candidates[2]) == 60


def test_loss_cp_treats_a_missed_mate_as_a_large_loss():
    candidates = [
        Candidate(move="d1h5", score_cp=None, mate_in=2, pv=["d1h5"]),
        Candidate(move="g1f3", score_cp=40, mate_in=None, pv=["g1f3"]),
    ]
    analysis = Analysis(fen="irrelevant", white_to_move=True, candidates=candidates)

    assert analysis.loss_cp(candidates[0]) == 0
    assert analysis.loss_cp(candidates[1]) > 90_000


# Integration tests: require a real Stockfish binary on PATH. Deselect with
# `pytest -m "not integration"` if it isn't installed.


@pytest.fixture
def real_engine():
    try:
        engine = Engine()
    except EngineUnavailable:
        pytest.skip("stockfish not installed")
    yield engine
    engine.close()


@pytest.mark.integration
def test_starting_position_returns_five_legal_candidates(real_engine):
    analysis = real_engine.analyse(START_FEN, movetime_ms=200)

    assert len(analysis.candidates) == 5
    board = chess.Board(START_FEN)
    for candidate in analysis.candidates:
        assert chess.Move.from_uci(candidate.move) in board.legal_moves


@pytest.mark.integration
def test_mate_in_one_is_found_on_the_first_candidate(real_engine):
    analysis = real_engine.analyse(WHITE_MATE_IN_1_FEN, movetime_ms=200)

    assert analysis.candidates[0].mate_in == 1
    assert analysis.candidates[0].score_cp is None


@pytest.mark.integration
def test_forced_mate_against_the_mover_is_negative(real_engine):
    analysis = real_engine.analyse(WHITE_MATED_IN_1_FEN, movetime_ms=200)

    assert analysis.candidates[0].mate_in == -1


@pytest.mark.integration
def test_perspective_is_consistent_between_white_and_black_to_move(real_engine):
    # Both are roughly balanced positions for the side to move. Normalized
    # to White's perspective, both should land near level rather than
    # showing an implausible extreme for either -- the classic unflipped-sign
    # bug would send one of these far outside a sane range.
    white_analysis = real_engine.analyse(START_FEN, movetime_ms=200)
    black_analysis = real_engine.analyse(AFTER_E4_FEN, movetime_ms=200)

    assert -100 < white_analysis.candidates[0].score_cp < 100
    assert -100 < black_analysis.candidates[0].score_cp < 100


@pytest.mark.integration
def test_close_terminates_the_real_process():
    try:
        engine = Engine()
    except EngineUnavailable:
        pytest.skip("stockfish not installed")

    engine.close()

    assert engine._process.poll() is not None
