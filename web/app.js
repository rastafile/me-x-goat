import {Chessboard, COLOR, INPUT_EVENT_TYPE} from "./vendor/cm-chessboard/src/Chessboard.js"
import {PromotionDialog, PROMOTION_DIALOG_RESULT_TYPE} from "./vendor/cm-chessboard/src/extensions/promotion-dialog/PromotionDialog.js"

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

const statusEl = document.getElementById("status")
const takeBackButton = document.getElementById("take-back-button")
const exportPgnButton = document.getElementById("export-pgn-button")

// Server state mirrored client-side so the board's input handler can
// validate drags without asking the server on every hover.
let userColor = null
let legalMoves = []
let gameOver = false
let currentFen = START_FEN
// Guards against a single gesture (or an overlapping one) firing
// validateMoveInput more than once before the first submission resolves,
// which would otherwise submit the same drag as two or more real moves.
let isSubmitting = false

const board = new Chessboard(document.getElementById("board"), {
    position: START_FEN,
    assetsUrl: "/static/vendor/cm-chessboard/assets/",
    extensions: [{class: PromotionDialog}],
})

document.querySelectorAll("#new-game-panel button").forEach((button) => {
    button.addEventListener("click", () => startNewGame(button.dataset.color))
})
takeBackButton.addEventListener("click", takeBack)
exportPgnButton.addEventListener("click", exportPgn)

async function startNewGame(color) {
    const response = await fetch("/new-game", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({color}),
    })
    const state = await response.json()

    userColor = state.user_color
    gameOver = false
    await board.setPosition(state.fen, false)
    // Must be awaited: enableMoveInput's square hit-testing uses the
    // board's orientation, which this only updates once the (async)
    // turn animation queue actually finishes.
    await board.setOrientation(userColor === "white" ? COLOR.white : COLOR.black)
    applyState(state)
    enableUserInput()
}

async function takeBack() {
    const response = await fetch("/take-back", {method: "POST"})
    if (!response.ok) {
        return
    }
    const state = await response.json()
    gameOver = false
    await board.setPosition(state.fen, true)
    applyState(state)
    enableUserInput()
}

async function exportPgn() {
    const response = await fetch("/pgn")
    if (!response.ok) {
        return
    }
    const pgn = await response.text()
    // No download affordance yet -- just show it; a real export control
    // is a controls-session concern (docs/week-2.md session 5).
    window.alert(pgn)
}

function enableUserInput() {
    // enableMoveInput throws if input is already enabled (e.g. starting a
    // new game or taking back while a previous handler is still attached);
    // disableMoveInput is always safe to call, enabled or not.
    board.disableMoveInput()
    if (gameOver) {
        return
    }
    board.enableMoveInput(inputHandler, userColor === "white" ? COLOR.white : COLOR.black)
}

function inputHandler(event) {
    if (event.type === INPUT_EVENT_TYPE.moveInputStarted) {
        return legalMoves.some((uci) => uci.startsWith(event.squareFrom))
    }

    if (event.type === INPUT_EVENT_TYPE.validateMoveInput) {
        if (isSubmitting) {
            return false
        }
        const matches = legalMoves.filter(
            (uci) => uci.slice(0, 2) === event.squareFrom && uci.slice(2, 4) === event.squareTo,
        )
        if (matches.length === 0) {
            return false
        }
        if (matches.length === 1 && matches[0].length === 4) {
            isSubmitting = true
            submitMove(matches[0])
            return true
        }

        // Multiple matches only happens for promotion (one per piece choice).
        isSubmitting = true
        const color = userColor === "white" ? COLOR.white : COLOR.black
        board.showPromotionDialog(event.squareTo, color, (result) => {
            if (result.type === PROMOTION_DIALOG_RESULT_TYPE.pieceSelected) {
                submitMove(event.squareFrom + event.squareTo + result.piece.charAt(1))
            } else {
                isSubmitting = false
                board.setPosition(currentFen, true)
                enableUserInput()
            }
        })
        return true
    }

    if (event.type === INPUT_EVENT_TYPE.moveInputFinished && event.legalMove) {
        board.disableMoveInput()
    }
}

async function submitMove(uci) {
    const response = await fetch("/move", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({uci}),
    })
    if (!response.ok) {
        // Shouldn't happen: legalMoves came from the server moments ago.
        // Revert the optimistic UI move and let the user try again.
        isSubmitting = false
        await board.setPosition(currentFen, true)
        enableUserInput()
        return
    }
    const state = await response.json()
    isSubmitting = false
    await board.setPosition(state.fen, true)
    applyState(state)
    enableUserInput()
}

function applyState(state) {
    currentFen = state.fen
    legalMoves = state.legal_moves
    gameOver = state.is_over
    takeBackButton.disabled = false
    exportPgnButton.disabled = false

    const lines = []
    if (state.goat_move) {
        lines.push(`GOAT plays ${state.goat_move.san}`)
    }
    if (gameOver) {
        lines.push(`Game over: ${state.outcome}`)
    } else if (typeof state.evaluation === "number") {
        lines.push(`Evaluation: ${state.evaluation > 0 ? "+" : ""}${state.evaluation}`)
    }
    statusEl.textContent = lines.join("\n")
}
