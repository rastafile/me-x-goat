# Me X GOAT

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

A local chess app for people who want to understand the game, not just win at it.

You play against an opponent built to feel like a grandmaster. After every move you
make, a separate tutor tells you what that move actually did — what you gave up,
where the position is heading, what you should have been looking at. The opponent
explains its own thinking too. The two never talk to each other.

Everything runs on your machine. Nothing connects to any online chess platform.

## How it works

Three layers, and the separation between them is the whole design:

| Layer | What it does | What it is |
|---|---|---|
| Engine | Picks and evaluates every move | Stockfish, running locally |
| Style | Chooses among the engine's top moves to give the opponent a recognizable character | Plain Python rules |
| Narration | Turns tags and numbers into readable explanations | A language model |

**The language model never chooses a move.** It receives intent tags and evaluations,
and writes prose. Every legal, tactical, and strategic decision comes from Stockfish.
This is what keeps the app from confidently suggesting nonsense — language models are
unreliable at chess calculation, so they are kept away from it entirely.

If the narration API is unavailable, games continue with text assembled from the tags.
Offline play is a requirement, not a fallback.

## Status

Under construction, built in the open over four weeks.

- [ ] Week 1 — engine, game state, style filter (playable in the terminal)
- [ ] Week 2 — HTTP server, draggable board, themes
- [ ] Week 3 — the tutor
- [ ] Week 4 — narration layer, mate badge, tests, v1

## Requirements

- Python 3.11+
- Stockfish 16+, installed separately
- macOS or Linux
- An Anthropic API key, optional — the app runs without one in degraded mode

## Install

Stockfish is **not** bundled with this project. It is GPL-3 licensed and is invoked as
a separate process over the UCI protocol, which is what allows this project to stay
MIT. Install it yourself:

```bash
# macOS
brew install stockfish

# Debian / Ubuntu
sudo apt install stockfish
```

Then:

```bash
git clone https://github.com/rastafile/me-x-goat.git
cd me-x-goat
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Verify Stockfish is reachable:

```bash
stockfish
# type: uci
# expect: uciok
# type: quit
```

## Run

```bash
python -m src.play_cli
```

You pick your color at the start. If you take black, the opponent opens.

## Configuration

| Setting | Default | Notes |
|---|---|---|
| `STOCKFISH_PATH` | `stockfish` | Absolute path if not on `PATH` |
| `ANTHROPIC_API_KEY` | unset | Without it, narration falls back to templates |
| `OUTPUT_LANGUAGE` | `en` | Language of tutor and opponent commentary |

## Design

The full specification lives in [`docs/design.md`](docs/design.md). It was written
before any code, and it explains the decisions that are not obvious from reading the
source — why the tutor is blind to the opponent's plan, why mate is announced but
never solved for you, why strength is regulated with two parameters instead of
Stockfish's built-in skill level.

## Contributing

Suggestions are welcome and are the reason this is public. Open an issue describing
what you would change and why. Good suggestions get implemented with credit.

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## What this is not

This project does not connect to Chess.com, Lichess, or any other platform, and it
never will. Receiving assistance during a live rated game is cheating. The point here
is the opposite: understanding what strong players see, on your own board, on your own
time.

## License

MIT. Use it, fork it, sell it — just keep the copyright notice.

Stockfish is a separate program under GPL-3 and is not distributed with this project.
