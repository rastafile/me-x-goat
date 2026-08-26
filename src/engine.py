"""The only module that speaks UCI with Stockfish."""

import subprocess
from dataclasses import dataclass

_MATE_SCORE = 100_000  # bridges mate distance onto the cp scale, for mover_score only


class EngineUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    move: str
    score_cp: int | None
    mate_in: int | None
    pv: list[str]


def mover_score(candidate: Candidate, white_to_move: bool) -> int:
    """A candidate's evaluation from the mover's point of view, with mate
    bridged onto the cp scale so it can be compared/subtracted like a normal
    score. Only meaningful for comparison (Analysis.loss_cp, tutor.py) --
    never a real evaluation to show anyone (design.md's "mate is not cp")."""
    if candidate.score_cp is not None:
        white_value = candidate.score_cp
    else:
        assert candidate.mate_in is not None
        sign = 1 if candidate.mate_in > 0 else -1
        white_value = sign * (_MATE_SCORE - abs(candidate.mate_in))
    return white_value if white_to_move else -white_value


@dataclass(frozen=True)
class Analysis:
    fen: str
    white_to_move: bool
    candidates: list[Candidate]

    def loss_cp(self, candidate: Candidate) -> int:
        """Centipawns worse than the best candidate, from the mover's point
        of view. Zero for the best candidate itself."""
        best = self.candidates[0]
        return mover_score(best, self.white_to_move) - mover_score(candidate, self.white_to_move)


class Engine:
    def __init__(self, path: str = "stockfish", multipv: int = 5) -> None:
        self._multipv = multipv
        try:
            self._process = subprocess.Popen(
                [path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise EngineUnavailable(f"stockfish binary not found: {path!r}") from exc

        self._send("uci")
        self._wait_for("uciok")
        self._send(f"setoption name MultiPV value {multipv}")
        self._send("isready")
        self._wait_for("readyok")

    def analyse(self, fen: str, movetime_ms: int) -> Analysis:
        """Run a fixed-time search and return the candidates, best to worst.

        Terminal positions (checkmate, stalemate) have no legal moves, so
        `candidates` comes back empty.
        """
        white_to_move = fen.split()[1] == "w"
        self._send(f"position fen {fen}")
        self._send(f"go movetime {movetime_ms}")

        # Every depth re-emits all MultiPV lines; keep only the last one per
        # index, so whatever is on the board when bestmove arrives is final.
        by_index: dict[int, Candidate] = {}
        for line in self._read_until("bestmove"):
            parsed = self._parse_info(line, white_to_move)
            if parsed is not None:
                index, candidate = parsed
                by_index[index] = candidate

        candidates = [by_index[i] for i in sorted(by_index)]
        return Analysis(fen=fen, white_to_move=white_to_move, candidates=candidates)

    def close(self) -> None:
        if self._process.poll() is not None:
            return
        try:
            self._send("quit")
            self._process.wait(timeout=2)
        except (BrokenPipeError, ValueError, subprocess.TimeoutExpired):
            self._process.kill()

    def __enter__(self) -> "Engine":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _send(self, command: str) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(command + "\n")
        self._process.stdin.flush()

    def _wait_for(self, token: str) -> None:
        assert self._process.stdout is not None
        while True:
            line = self._process.stdout.readline()
            if line == "":
                raise EngineUnavailable("stockfish closed its output stream")
            if token in line:
                return

    def _read_until(self, token: str) -> list[str]:
        assert self._process.stdout is not None
        lines = []
        while True:
            line = self._process.stdout.readline()
            if line == "":
                raise EngineUnavailable("stockfish closed its output stream")
            if line.startswith(token):
                break
            lines.append(line.strip())
        return lines

    @staticmethod
    def _parse_info(line: str, white_to_move: bool) -> tuple[int, Candidate] | None:
        if not line.startswith("info") or " pv " not in line:
            return None
        parts = line.split()
        if "multipv" not in parts or "score" not in parts:
            return None
        # A bound-only score is a mid-search estimate, superseded later at the
        # same depth; skip it rather than let it overwrite a settled value.
        if "lowerbound" in parts or "upperbound" in parts:
            return None

        index = int(parts[parts.index("multipv") + 1])

        score_i = parts.index("score")
        kind, raw_value = parts[score_i + 1], int(parts[score_i + 2])
        value = raw_value if white_to_move else -raw_value
        score_cp = value if kind == "cp" else None
        mate_in = value if kind == "mate" else None

        pv = parts[parts.index("pv") + 1 :]
        if not pv:
            return None

        return index, Candidate(move=pv[0], score_cp=score_cp, mate_in=mate_in, pv=pv)
