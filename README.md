# Русский · Practice

A zero-dependency web app to reinforce Russian vocabulary through **reading and listening exercises** (emails, dialogues, articles…) followed by multiple-choice questions. Target words are highlighted in the text; tap one to see its meaning. Listening mode hides the text and reads it aloud with the browser's text-to-speech.

## Run it
No build step, no dependencies. Either:
- open `index.html` directly in a browser, or
- serve the folder: `python3 -m http.server 8000` → http://localhost:8000

Deploy as-is on GitHub Pages, Netlify, or any static host.
Audio uses the Web Speech API: you need a Russian (`ru-RU`) voice installed on your OS/browser (Chrome/Edge/Safari work best).

## Structure
```
index.html          page shell
css/style.css       design tokens + components (editorial look, light/dark automatic)
js/app.js           router, rendering, audio, progress (localStorage)
data/manifest.js    ordered list of set ids
data/levels/*.js    one file per vocabulary set  ← the content you edit
tools/validate.py   checks your data files
```

## Add a new vocabulary set ("level")
1. Copy `data/levels/a2-1.js` to `data/levels/<new-id>.js` (e.g. `b1-1.js`).
2. Edit its fields:
   | field | meaning |
   |---|---|
   | `id` | **must equal the file name** (without `.js`); also the key for saved progress |
   | `title`, `desc` | shown on the home card |
   | `target` | level badge, e.g. `"A2"`, `"B1"` |
   | `texts[]` | the exercises |
3. Register it in `data/manifest.js`: `window.LEVEL_FILES = ["a2-1", "b1-1"];` (order = display order).
4. Run `python3 tools/validate.py`, then refresh the page.

### Exercise schema
```js
{
  type: "Email",              // free label (Email, Dialogue, Article, Story…)
  title: "…",
  body: `Plain Russian text with [целевое слово|traduction] markup.`,
  qs: [ { q: "Question?", o: ["opt A", "opt B", "opt C"], a: 1 } ]   // a = index of the correct option (0-based)
}
```
- `[слово|translation]` highlights the word and shows the translation on tap. The audio reads only the Russian word.
- Put the *inflected form as it appears* in the text, e.g. `[деревьях|arbre]`.
- Newlines in `body` are preserved. Avoid `[` `]` and backticks for anything else. Use ’ not `'` inside translations if you use single-quoted strings.
- 2–5 options per question; 3–4 questions per text works well.

### Generate content with an LLM
Prompt template:
> I'm learning Russian (target A2). Here is my vocabulary list: `<paste words | translations>`. Write 6 texts (2 emails, 2 dialogues, 2 articles), 60–100 words each, using every word at least once, plus easy common words. Mark target words as `[form|French meaning]`. Add 4 multiple-choice questions per text in Russian. Output a JS file in this exact format: `<paste data/levels/a2-1.js>`. Set `id` to `<new-id>`.

## Notes
- Progress (best score per exercise) and preferences are in `localStorage` (keys prefixed `ru:`). Clear them from the browser dev tools to reset.
- Data files are plain `<script>` files (not JSON) so the app works from `file://` without a server.
- Ideas: fill-in-the-blank, spaced-repetition of missed words, per-word audio, vocabulary index page.

## Vocabulary list of a set (view + download)
Each set page shows its full word list in a scrollable panel (search, "Hide French" self-test mode, tap a row to hear it) with **CSV**, **Anki (TSV)** and **TXT** downloads.
During exercises the words are *not* shown by default: a flip card offers them as a hint on its back.

The list lives in `data/vocab/<set-id>.js`, matching the set's id. To create it from plain text files with one `russian | french` pair per line:
```
python3 tools/import_vocab.py <set-id> list1.txt list2.txt ...
```
(or edit the generated file by hand). If a set has no vocab file, the panel is simply hidden. `tools/validate.py` checks the lines.

## Audio player
Text is split into sentences and read one at a time. Pause/play resumes from the start of the sentence you stopped in; ⏮ restarts the text; « goes to the previous sentence (or restarts the current one if you are more than 2 s into it, like a music app); » skips to the next one. The sentence being read is highlighted.
