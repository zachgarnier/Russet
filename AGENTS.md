# AGENTS.md

Static, zero-dependency Russian practice app: `index.html` + `js/app.js` + plain-script content in `data/`. No build, package manager, lint, typecheck, test suite, or CI. "Ship" = commit the files and serve the folder.

## Verify changes
- `python tools/validate.py` — run after any `data/` edit. Resolves the repo root itself (any cwd works) and exits non-zero on errors. It checks manifest/filename consistency, bracket balance, `[word|translation]` tags, and answer indexes.
- `python tools/vocab/audit.py <set-id>` — run after writing or importing a set. It reports vocab words used in a text but not highlighted (MISSING), tags for words that are not in `data/vocab/<id>.js` (WRONG), and gloss mismatches; exits non-zero on MISSING/WRONG. `--fix --write` rebuilds the `body` texts from the vocabulary. Human decisions (irregular forms, look-alike words, French wording) live in `tools/vocab/overrides/<id>.json`; read `tools/vocab/README.md` before using it.
- The validator does **not** parse JS, so syntax errors pass it. Check the page in a browser: open `index.html` directly, or `python -m http.server 8000`.
- A broken level/vocab file fails silently in the UI (set disappears); the only signal is a `Could not load …` console warning from `loadScript` in `js/app.js`.
- Audio needs a `ru-RU` `speechSynthesis` voice, so player behavior can't be verified headlessly.

## How content is wired
- `data/levels/<id>.js` is a classic script calling `registerLevel({...})`; `id` **must equal** the filename (validator enforces it).
- `data/vocab/<id>.js` calls `registerVocab("<id>", \`…\`)` with one `russian | french` line per word. Optional — the vocabulary panel is hidden when absent.
- To add a set: copy a level file, edit, then add its id to `window.LEVEL_FILES` in `data/manifest.js` (array order = display order). No `<script>` tag needed; at boot `js/app.js` injects every level, then every vocab file, silently ignoring missing vocab.
- Keep data as plain scripts: no ES modules, `fetch`, or JSON loading — the app must keep working from `file://`.

## Content conventions (differ from defaults)
- Markup is `[form|translation]`. Translations are **French**; questions/options are Russian; UI chrome is English. Mark the word in the exact inflected form used in the text.
- `target` must be one of `A1`, `A2`, `B1`, `B2` (the `CEFR` constant in `js/app.js`); any other value leaves no level pill active.
- Options are lettered from `"ABCDE"`, so at most 5 per question; `a` is the 0-based correct index.
- Do not use literal `[`, `]`, or backticks elsewhere in `body`: the validator counts brackets, and the reader/audio logic splits on bracket markup.

## Gotchas
- `tools/vocab/audit.py --write` replaces **all** tags inside each `body` (they are re-added from the vocabulary + overrides), so review its FIX PLAN/report first. Questions (`qs`) are never touched.
- `python tools/import_vocab.py <set-id> file1.txt …` rewrites `data/vocab/<set-id>.js` wholesale — hand edits to that file are lost.
- Progress is keyed by text **index**: `localStorage["ru:prog"]` → `<set-id>:<textIndex>`. Reordering or deleting `texts[]` reassigns old scores; clear `ru:*` keys to reset.
- Vocab entries are parsed by splitting on the first `|` and trimming; lines without `|` are dropped. Keep exactly one pipe per line.
