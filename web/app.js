import {Chessboard, COLOR, INPUT_EVENT_TYPE} from "./vendor/cm-chessboard/src/Chessboard.js"
import {PromotionDialog, PROMOTION_DIALOG_RESULT_TYPE} from "./vendor/cm-chessboard/src/extensions/promotion-dialog/PromotionDialog.js"
import {loadStoredLanguage, setLanguage, t} from "./i18n.js"

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

const statusEl = document.getElementById("status")
const tutorPanelEl = document.getElementById("tutor-panel")
const mistakePanelEl = document.getElementById("mistake-panel")
const summaryPanelEl = document.getElementById("summary-panel")
const mateBadgeEl = document.getElementById("mate-badge")
const evalBarEl = document.getElementById("eval-bar")
const evalBarFillEl = document.getElementById("eval-bar-fill")
const takeBackButton = document.getElementById("take-back-button")
const exportPgnButton = document.getElementById("export-pgn-button")
const strengthInput = document.getElementById("strength-input")
const strengthValueEl = document.getElementById("strength-value")
const styleInput = document.getElementById("style-input")
const themeInput = document.getElementById("theme-input")
const languageInput = document.getElementById("language-input")
const mateBadgeToggle = document.getElementById("mate-badge-toggle")
const evalBarToggle = document.getElementById("eval-bar-toggle")

const DEFAULT_THEME = "wood"
const THEME_STORAGE_KEY = "theme"
// design.md §7: the badge has its own switch, default on, so a user can
// wean themselves off it once the skill of scanning for mate forms.
const MATE_BADGE_STORAGE_KEY = "mateBadgeEnabled"
const EVAL_BAR_STORAGE_KEY = "evalBarEnabled"
// design.md §6's "saturating past some bound" -- a plain clamp-then-scale
// is enough to guarantee no absurd sliver or overflow; no need for a
// fancier curve than that.
const EVAL_CAP_CP = 1000

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
mateBadgeToggle.addEventListener("change", () => {
    storeMateBadgeEnabled(mateBadgeToggle.checked)
    if (lastState) {
        renderMateBadge(lastState.mate_in)
    }
})
evalBarToggle.addEventListener("change", () => {
    storeEvalBarEnabled(evalBarToggle.checked)
    renderEvalBar(lastState ? lastState.evaluation : null, lastState ? lastState.mate_in : null)
})

applyTheme(loadStoredTheme())
const initialLanguage = loadStoredLanguage()
languageInput.value = initialLanguage
setLanguage(initialLanguage)
mateBadgeToggle.checked = loadStoredMateBadgeEnabled()
evalBarToggle.checked = loadStoredEvalBarEnabled()
renderEvalBar(null, null)

function loadStoredTheme() {
    try {
        return localStorage.getItem(THEME_STORAGE_KEY) || DEFAULT_THEME
    } catch {
        return DEFAULT_THEME
    }
}

function loadStoredMateBadgeEnabled() {
    try {
        const stored = localStorage.getItem(MATE_BADGE_STORAGE_KEY)
        return stored === null ? true : stored === "true"
    } catch {
        return true
    }
}

function storeMateBadgeEnabled(enabled) {
    try {
        localStorage.setItem(MATE_BADGE_STORAGE_KEY, String(enabled))
    } catch {
        // Private browsing / storage disabled: the switch still applies for
        // this page load, it just won't be remembered next time.
    }
}

function loadStoredEvalBarEnabled() {
    try {
        const stored = localStorage.getItem(EVAL_BAR_STORAGE_KEY)
        return stored === null ? true : stored === "true"
    } catch {
        return true
    }
}

function storeEvalBarEnabled(enabled) {
    try {
        localStorage.setItem(EVAL_BAR_STORAGE_KEY, String(enabled))
    } catch {
        // Private browsing / storage disabled: the switch still applies for
        // this page load, it just won't be remembered next time.
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
            // The page's own switch (docs/decisions.md ADR 6) -- stored in
            // localStorage via i18n.js, always in sync with this select's
            // value.
            language: languageInput.value,
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
        // goat_move.commentary is already narrated server-side (coach.py),
        // in the requested language, and already covers the outcome phrase
        // too when the GOAT's own move ends the game (narration.py) -- the
        // move itself (SAN) stays visible alongside it, just not as the
        // whole message (docs/week-4.md session 4 contract).
        lines.push(state.goat_move.san)
        lines.push(state.goat_move.commentary)
    } else if (state.is_over) {
        // The user's own move ended the game -- no GOAT reply narrates it,
        // so this is the one status line still assembled client-side.
        lines.push(strings.gameOver(strings.outcome[state.outcome] ?? state.outcome))
    } else if (typeof state.evaluation === "number") {
        lines.push(strings.evaluation(state.evaluation))
    }
    statusEl.textContent = lines.join("\n")

    renderTutor(state.tutor)
    renderMistakeCounts(state.mistake_counts)
    renderSummary(state.summary)
    renderMateBadge(state.mate_in)
    renderEvalBar(state.evaluation, state.mate_in)
}

function renderMateBadge(mateIn) {
    // The server always computes mate_in; the switch is a pure display
    // choice (same pattern as the theme), never a reason to skip asking.
    if (!mateBadgeToggle.checked || typeof mateIn !== "number") {
        mateBadgeEl.textContent = ""
        return
    }
    const strings = t()
    // Never the piece, square, or move -- design.md §7's central rule.
    // mateAvailable/mateFacing only ever take the distance, nothing else.
    mateBadgeEl.textContent = mateIn > 0 ? strings.mateAvailable(mateIn) : strings.mateFacing(-mateIn)
}

function renderEvalBar(evaluation, mateIn) {
    // Same pure-display-choice pattern as the mate badge: the fill is still
    // computed even when hidden, purely so toggling back on shows the
    // right thing immediately without waiting on the next server response.
    evalBarEl.classList.toggle("hidden", !evalBarToggle.checked)

    let fraction = 0.5 // neutral: no evaluation yet (game start, game over)
    if (typeof mateIn === "number") {
        // A mate saturates the bar fully, in whichever direction it favors
        // -- there's no cp scale to speak of once mate is forced.
        fraction = mateIn > 0 ? 1 : 0
    } else if (typeof evaluation === "number") {
        const capped = Math.max(-EVAL_CAP_CP, Math.min(EVAL_CAP_CP, evaluation))
        fraction = 0.5 + (capped / EVAL_CAP_CP) * 0.5
    }
    evalBarFillEl.style.height = `${(fraction * 100).toFixed(1)}%`
}

function renderTutor(tutor) {
    // tutor is only ever populated for the user's own move (never the
    // GOAT's, per docs/decisions.md ADR 4 and design.md §6), so this
    // naturally updates only on the user's moves with no extra guard here.
    tutorPanelEl.textContent = ""
    if (!tutor) {
        return
    }

    // tutor.commentary is already narrated server-side (coach.py), in the
    // requested language -- classification, best_move, and continuation are
    // still on the response for anything that wants the raw numbers, but
    // the panel itself just shows the sentence now.
    // A real element, not a bare text node: a node appended straight after
    // plain text doesn't reliably start its own line (the take-back button
    // was rendering squeezed onto the text's last line instead of below it).
    const text = document.createElement("p")
    text.textContent = tutor.commentary
    tutorPanelEl.appendChild(text)

    // The take-back button is a UI control, not narrated prose -- it keys
    // off offer_take_back (a boolean), not off any text, and is appended
    // last, after the commentary is already in place, per design.md §6's
    // ordering rule ("always after the explanation").
    if (tutor.offer_take_back) {
        const offer = document.createElement("button")
        offer.type = "button"
        offer.textContent = t().takeThatBack
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
