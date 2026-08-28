// All user-facing text the page assembles itself, in both directions -- per
// CLAUDE.md: "Text shown to the end user is controlled by the
// OUTPUT_LANGUAGE setting... Do not hardcode user-facing strings in any
// single language." app.js never contains a hardcoded user-facing string;
// it always goes through t() or a data-i18n label.
//
// As of docs/week-4.md session 4, the GOAT's and the tutor's own sentences
// are no longer built here -- coach.py/narration.py narrate those
// server-side now, in the requested language, and app.js just displays
// state.goat_move.commentary / state.tutor.commentary verbatim. What's left
// in this module is: static UI labels (buttons, dropdowns), the mistake
// counts and end-of-game summary (still server-structured numbers, no prose
// from coach.py this week), the mate badge's templated text (session 5 --
// a number plugged into a fixed phrase, not model prose, so it stays here
// rather than moving server-side), and the one status line the server
// can't narrate -- the outcome phrase for a game the user's own move
// ended, where there's no GOAT reply to carry it.
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
        mateBadgeToggle: "Mate badge",
        evalBarToggle: "Evaluation bar",
        gameOver: (outcome) => `Game over: ${outcome}`,
        evaluation: (value) => `Evaluation: ${value > 0 ? "+" : ""}${value}`,
        mateAvailable: (n) => `mate in ${n} available`,
        mateFacing: (n) => `you are facing mate in ${n}`,
        takeThatBack: "Take that back",
        mistakeCountsLine: (label, side) =>
            `${label}: ${side.inaccuracy} inaccuracies, ${side.mistake} mistakes, ${side.blunder} blunders`,
        summaryLine: (ply, colorLabel, lossCp) =>
            `Game decided at ply ${ply}, by ${colorLabel}'s move (${lossCp} cp lost).`,
        outcome: {
            checkmate: "checkmate",
            stalemate: "stalemate",
            insufficient_material: "insufficient material",
            seventyfive_moves: "75-move rule",
            fivefold_repetition: "fivefold repetition",
            fifty_moves: "fifty-move rule",
            threefold_repetition: "threefold repetition",
            timeout: "time forfeit",
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
        mateBadgeToggle: "Aviso de mate",
        evalBarToggle: "Barra de avaliação",
        gameOver: (outcome) => `Fim de jogo: ${outcome}`,
        evaluation: (value) => `Avaliação: ${value > 0 ? "+" : ""}${value}`,
        mateAvailable: (n) => `mate em ${n} disponível`,
        mateFacing: (n) => `você está enfrentando mate em ${n}`,
        takeThatBack: "Desfazer esse lance",
        mistakeCountsLine: (label, side) =>
            `${label}: ${side.inaccuracy} imprecisões, ${side.mistake} erros, ${side.blunder} erros graves`,
        summaryLine: (ply, colorLabel, lossCp) =>
            `Partida decidida no lance ${ply}, pelo lance das ${colorLabel} (${lossCp} cp perdidos).`,
        outcome: {
            checkmate: "xeque-mate",
            stalemate: "afogamento",
            insufficient_material: "material insuficiente",
            seventyfive_moves: "regra dos 75 lances",
            fivefold_repetition: "repetição quíntupla",
            fifty_moves: "regra dos 50 lances",
            threefold_repetition: "repetição tripla",
            timeout: "tempo esgotado",
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
