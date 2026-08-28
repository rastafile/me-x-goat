"""Wall-clock time bookkeeping for the optional chess clock (docs/week-7.md).

Orchestration state, same category as server.py's mistake counts and
assessment history -- it never influences persona.py's move choice, and
persona.py never imports this module.

Stateful, not pure -- reading "now" is an inherent side effect, same
category as engine.py's subprocess I/O -- but every method that needs it
takes `now_ms` as an explicit parameter rather than calling time.time()
internally, so this stays deterministically testable without mocking the
clock. Callers should pass a monotonic clock reading (e.g.
int(time.monotonic() * 1000)), not wall time, so a system clock adjustment
mid-game can never shorten or lengthen anyone's remaining time.
"""


class Clock:
    def __init__(self, white_ms: int, black_ms: int, increment_ms: int) -> None:
        self._remaining_ms = {"white": white_ms, "black": black_ms}
        self._increment_ms = increment_ms
        self._running_color: str | None = None
        self._turn_started_at_ms: int | None = None

    def start_turn(self, color: str, now_ms: int) -> None:
        """Marks `color`'s turn as running as of `now_ms`. Does not stop
        whatever turn might already be running -- callers are expected to
        stop_turn() first; starting over an already-running turn would
        silently discard the elapsed time between the two start_turn calls."""
        self._running_color = color
        self._turn_started_at_ms = now_ms

    def stop_turn(self, now_ms: int) -> None:
        """Deducts elapsed time from whoever's turn was running, then
        applies the increment -- called once a move has actually been
        made, so the mover didn't flag (docs/week-7.md session 1 checks
        that before this ever runs). A no-op if no turn is running."""
        if self._running_color is None:
            return
        elapsed_ms = now_ms - self._turn_started_at_ms
        color = self._running_color
        # Floored at zero rather than going negative -- a defensive floor,
        # not the normal path: the caller is expected to have already
        # confirmed this mover didn't flag before calling stop_turn.
        self._remaining_ms[color] = max(0, self._remaining_ms[color] - elapsed_ms) + self._increment_ms
        self._running_color = None
        self._turn_started_at_ms = None

    def remaining_ms(self, color: str) -> int:
        return self._remaining_ms[color]

    def is_flagged(self, color: str, now_ms: int) -> bool:
        """True if `color`'s clock has hit zero, including whatever time
        has elapsed since its turn started, if it's currently running."""
        remaining = self._remaining_ms[color]
        if self._running_color == color:
            remaining -= now_ms - self._turn_started_at_ms
        return remaining <= 0
