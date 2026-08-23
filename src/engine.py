"""The only module that speaks UCI with Stockfish."""

import subprocess
from dataclasses import dataclass


class EngineUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    move: str
    score_cp: int | None
    mate_in: int | None
    pv: list[str]


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

    def analyse(self, fen: str, movetime_ms: int) -> list[Candidate]:
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

        return [by_index[i] for i in sorted(by_index)]

    def close(self) -> None:
        self._send("quit")
        self._process.wait(timeout=2)

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
        for line in self._process.stdout:
            if token in line:
                return

    def _read_until(self, token: str) -> list[str]:
        assert self._process.stdout is not None
        lines = []
        for line in self._process.stdout:
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
