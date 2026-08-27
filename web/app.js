import {Chessboard, COLOR, INPUT_EVENT_TYPE} from "./vendor/cm-chessboard/src/Chessboard.js"
import {PromotionDialog, PROMOTION_DIALOG_RESULT_TYPE} from "./vendor/cm-chessboard/src/extensions/promotion-dialog/PromotionDialog.js"
import {loadStoredLanguage, setLanguage, t} from "./i18n.js"

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

const statusEl = document.getElementById("status")
const tutorPanelEl = document.getElementById("tutor-panel")
const mistakePanelEl = document.getElementById("mistake-panel")
const summaryPanelEl = document.getElementById("summary-panel")
const takeBackButton = document.getElementById("take-back-button")
const exportPgnButton = document.getElementById("export-pgn-button")
const strengthInput = document.getElementById("strength-input")
const strengthValueEl = document.getElementById("strength-value")
const styleInput = document.getElementById("style-input")
const themeInput = document.getElementById("theme-input")
const languageInput = document.getElementById("language-input")

const DEFAULT_THEME = "wood"
const THEME_STORAGE_KEY = "theme"

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
// The last GameStateResponse applied, so a language switch can re-render the
// dynamic panels (tutor, mistake counts, summary) without a round trip --
// null until the first /new-game response arrives.
let lastState = null

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
strengthInput.addEventListener("input", () => {
    strengthValueEl.textContent = strengthInput.value
})
themeInput.addEventListener("change", () => applyTheme(themeInput.value))
languageInput.addEventListener("change", () => {
    setLanguage(languageInput.value)
    if (lastState) {
        renderDynamicPanels(lastState)
    }
})

applyTheme(loadStoredTheme())
const initialLanguage = loadStoredLanguage()
languageInput.value = initialLanguage
setLanguage(initialLanguage)

function loadStoredTheme() {
    try {
        return localStorage.getItem(THEME_STORAGE_KEY) || DEFAULT_THEME
    } catch {
        return DEFAULT_THEME
    }
}

function applyTheme(name) {
    const stale = Array.from(document.body.classList).filter((cls) => cls.startsWith("theme-"))
    document.body.classList.remove(...stale)
    document.body.classList.add(`theme-${name}`)
    themeInput.value = name
    try {
        localStorage.setItem(THEME_STORAGE_KEY, name)
    } catch {
        // Private browsing / storage disabled: theme still applies for
        // this page load, it just won't be remembered next time.
    }
}

async function startNewGame(color) {
    const response = await fetch("/new-game", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            color,
            strength: Number(strengthInput.value),
            style: styleInput.value,
        }),
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
    lastState = state
    currentFen = state.fen
    legalMoves = state.legal_moves
    gameOver = state.is_over
    takeBackButton.disabled = false
    exportPgnButton.disabled = false

    renderDynamicPanels(state)
}

// Everything server-driven that a language switch must be able to
// re-render on the spot, without a round trip -- as opposed to the static
// data-i18n labels, which setLanguage() (i18n.js) updates directly.
function renderDynamicPanels(state) {
    const strings = t()

    const lines = []
    if (state.goat_move) {
        lines.push(strings.goatPlays(state.goat_move.san))
    }
    if (state.is_over) {
        lines.push(strings.gameOver(strings.outcome[state.outcome] ?? state.outcome))
    } else if (typeof state.evaluation === "number") {
        lines.push(strings.evaluation(state.evaluation))
    }
    statusEl.textContent = lines.join("\n")

    renderTutor(state.tutor)
    renderMistakeCounts(state.mistake_counts)
    renderSummary(state.summary)
}

function renderTutor(tutor) {
    // tutor is only ever populated for the user's own move (never the
    // GOAT's, per docs/decisions.md ADR 4 and design.md §6), so this
    // naturally updates only on the user's moves with no extra guard here.
    tutorPanelEl.textContent = ""
    if (!tutor) {
        return
    }

    const strings = t()
    const classification = strings.classification[tutor.classification] ?? tutor.classification
    const lines = [strings.tutorLine(classification, tutor.loss_cp)]
    if (tutor.best_move) {
        lines.push(strings.betterWas(tutor.best_move))
    }
    if (tutor.continuation.length > 0) {
        lines.push(strings.likelyContinuation(tutor.continuation.join(" ")))
    }
    // Plain UCI for now, not narrated text -- narration is week 4
    // (docs/week-3.md session 5 contract).
    // A real element, not a bare text node: a node appended straight after
    // plain text doesn't reliably start its own line (the take-back button
    // was rendering squeezed onto the text's last line instead of below it).
    const text = document.createElement("p")
    text.textContent = lines.join("\n")
    tutorPanelEl.appendChild(text)

    // The take-back offer is appended last, after the rest of the analysis
    // text is already in place, per design.md §6's ordering rule ("always
    // after the explanation").
    if (tutor.offer_take_back) {
        const offer = document.createElement("button")
        offer.type = "button"
        offer.textContent = strings.takeThatBack
        offer.addEventListener("click", takeBack)
        tutorPanelEl.appendChild(offer)
    }
}

function renderMistakeCounts(counts) {
    const strings = t()
    const line = (label, side) => strings.mistakeCountsLine(label, side)
    mistakePanelEl.textContent = [line(strings.white, counts.white), line(strings.black, counts.black)].join("\n")
}

function renderSummary(summary) {
    if (!summary) {
        summaryPanelEl.textContent = ""
        return
    }
    const strings = t()
    const colorLabel = summary.decided_by === "white" ? strings.white : strings.black
    summaryPanelEl.textContent = strings.summaryLine(summary.decided_at_ply, colorLabel, summary.loss_cp)
}
