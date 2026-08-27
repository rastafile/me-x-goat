// All user-facing text the page can show, in both directions -- per
// CLAUDE.md: "Text shown to the end user is controlled by the
// OUTPUT_LANGUAGE setting... Do not hardcode user-facing strings in any
// single language." Nothing here talks to the server: the server only ever
// returns structured data (classification words, cp numbers, UCI/SAN moves,
// an outcome enum) -- every sentence the user reads is assembled client-side,
// so translation lives entirely in this module. app.js never contains a
// hardcoded user-facing string; it always goes through t().
//
// Chess notation (UCI, SAN) is never translated -- it's already universal.
// The two <option> labels naming the languages themselves ("English",
// "Português (Brasil)") are not translated either, by the same convention
// every language switcher follows: a language names itself in its own
// tongue, not the currently active one.

export const DEFAULT_LANGUAGE = "en-US"
const STORAGE_KEY = "language"

const STRINGS = {
    "en-US": {
        playAs: "Play as:",
        white: "White",
        black: "Black",
        random: "Random",
        strength: "Strength:",
        style: "Style:",
        theme: "Theme:",
        language: "Language:",
        styleCarlsen: "Carlsen",
        styleRaw: "Raw engine",
        themeWood: "Wood",
        themeClassicGreen: "Classic green",
        themeBlue: "Blue",
        themeMarble: "Marble",
        themeHighContrast: "High contrast",
        takeBack: "Take back",
        exportPgn: "Export PGN",
        goatPlays: (san) => `GOAT plays ${san}`,
        gameOver: (outcome) => `Game over: ${outcome}`,
        evaluation: (value) => `Evaluation: ${value > 0 ? "+" : ""}${value}`,
        tutorLine: (classification, lossCp) => `Tutor: ${classification} (${lossCp} cp lost)`,
        betterWas: (move) => `Better was ${move}`,
        likelyContinuation: (moves) => `Likely continuation: ${moves}`,
        takeThatBack: "Take that back",
        mistakeCountsLine: (label, side) =>
            `${label}: ${side.inaccuracy} inaccuracies, ${side.mistake} mistakes, ${side.blunder} blunders`,
        summaryLine: (ply, colorLabel, lossCp) =>
            `Game decided at ply ${ply}, by ${colorLabel}'s move (${lossCp} cp lost).`,
        classification: {
            excellent: "excellent",
            good: "good",
            inaccuracy: "inaccuracy",
            mistake: "mistake",
            blunder: "blunder",
        },
        outcome: {
            checkmate: "checkmate",
            stalemate: "stalemate",
            insufficient_material: "insufficient material",
            seventyfive_moves: "75-move rule",
            fivefold_repetition: "fivefold repetition",
            fifty_moves: "fifty-move rule",
            threefold_repetition: "threefold repetition",
        },
    },
    "pt-BR": {
        playAs: "Jogar de:",
        white: "Brancas",
        black: "Pretas",
        random: "Aleatório",
        strength: "Força:",
        style: "Estilo:",
        theme: "Tema:",
        language: "Idioma:",
        styleCarlsen: "Carlsen",
        styleRaw: "Motor puro",
        themeWood: "Madeira",
        themeClassicGreen: "Verde clássico",
        themeBlue: "Azul",
        themeMarble: "Mármore",
        themeHighContrast: "Alto contraste",
        takeBack: "Desfazer",
        exportPgn: "Exportar PGN",
        goatPlays: (san) => `GOAT joga ${san}`,
        gameOver: (outcome) => `Fim de jogo: ${outcome}`,
        evaluation: (value) => `Avaliação: ${value > 0 ? "+" : ""}${value}`,
        tutorLine: (classification, lossCp) => `Tutor: ${classification} (${lossCp} cp perdidos)`,
        betterWas: (move) => `Melhor seria ${move}`,
        likelyContinuation: (moves) => `Continuação provável: ${moves}`,
        takeThatBack: "Desfazer esse lance",
        mistakeCountsLine: (label, side) =>
            `${label}: ${side.inaccuracy} imprecisões, ${side.mistake} erros, ${side.blunder} erros graves`,
        summaryLine: (ply, colorLabel, lossCp) =>
            `Partida decidida no lance ${ply}, pelo lance das ${colorLabel} (${lossCp} cp perdidos).`,
        classification: {
            excellent: "excelente",
            good: "bom",
            inaccuracy: "imprecisão",
            mistake: "erro",
            blunder: "erro grave",
        },
        outcome: {
            checkmate: "xeque-mate",
            stalemate: "afogamento",
            insufficient_material: "material insuficiente",
            seventyfive_moves: "regra dos 75 lances",
            fivefold_repetition: "repetição quíntupla",
            fifty_moves: "regra dos 50 lances",
            threefold_repetition: "repetição tripla",
        },
    },
}

let currentLanguage = DEFAULT_LANGUAGE

export function loadStoredLanguage() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY)
        return STRINGS[stored] ? stored : DEFAULT_LANGUAGE
    } catch {
        return DEFAULT_LANGUAGE
    }
}

// Sets the active language, persists it, and updates every static label in
// the page (anything tagged data-i18n) in place. Dynamic, server-driven
// panels (tutor, mistake counts, summary, status) are not this function's
// job -- app.js re-renders those from its own last-known state, since they
// need values (a move, a count) that no DOM attribute carries.
export function setLanguage(lang) {
    currentLanguage = STRINGS[lang] ? lang : DEFAULT_LANGUAGE
    try {
        localStorage.setItem(STORAGE_KEY, currentLanguage)
    } catch {
        // Private browsing / storage disabled: language still applies for
        // this page load, it just won't be remembered next time.
    }
    document.querySelectorAll("[data-i18n]").forEach((el) => {
        const key = el.dataset.i18n
        if (STRINGS[currentLanguage][key]) {
            el.textContent = STRINGS[currentLanguage][key]
        }
    })
}

export function t() {
    return STRINGS[currentLanguage]
}
