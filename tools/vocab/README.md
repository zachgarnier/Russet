# Vocabulary highlighting audit

`tools/vocab/audit.py` checks that the `[form|gloss]` tags in `data/levels/<id>.js` match
`data/vocab/<id>.js`: every tag must be a vocabulary word, and every vocabulary word used in a
text must be highlighted. It can also rebuild the bodies so they match the vocabulary.

It exists because LLM-written readings look fine but tag words that are not in the list
(`центр`) and forget words that are (`недавно`).

## Quick start

```sh
python tools/vocab/audit.py a2-2                  # check only; writes vocab-report.txt
python tools/vocab/audit.py a2-2 --fix            # show the changes a rebuild would make
python tools/vocab/audit.py a2-2 --fix --write    # apply them to the level file
python tools/vocab/audit.py a2-2 --all            # expect every occurrence, not the first per text
python tools/vocab/audit.py a2-2 --preview /tmp/a2-2.js   # dump the rebuilt file without writing
python tools/vocab/audit.py a2-2 --out report.txt # choose the report file
```

* Exit code `0` = clean, `1` = MISSING/WRONG tags found, `2` = bad invocation or missing file.
* Progress in the app is keyed by text index, so a rebuild never resets scores.
* `--write` only rewrites the text inside each `body:` template literal; `qs`, `title`, `type`
  and everything else stay byte-identical. It always strips existing tags first and re-adds them.

## Report sections

| Section | Meaning | Fails the run? |
| --- | --- | --- |
| `MISSING` | A vocab word is in the text but not tagged. `match 100` = exact form, `80/85` = same stem, `<80` = weak guess. | yes |
| `WRONG` | A tag whose word is not in the vocabulary, or a look-alike rejected by `block`. | yes |
| `STALE GLOSS` | The tag's French gloss differs from `form_gloss`/`gloss` in the overrides. | no |
| `AMBIGUOUS` | One surface fits several lemmas (`многие` → `много` / `многий`); the first was used. | no |
| `BLOCKED` | Matches listed in `block` and ignored on purpose. | no |
| `RELATED, NOT LISTED` | A word that looks like the same family as a listed one but is a different word (`внимательнее` ~ `внимание`), or an aspectual/prefix pair. Never auto-tagged. | no |
| `FIX PLAN` | Added / removed / re-glossed tags a rebuild would produce. | no |

## Overrides: `tools/vocab/overrides/<id>.json`

The stemmer handles regular inflection. Everything else is a human decision stored per set:

```json
{
  "//": "comment keys are ignored",
  "force":      { "людей": "человек", "вошла": "войти", "конце": "конец" },
  "block":      [["почту", "почти"], ["сиденье", "сидеть"]],
  "canon":      { "должна": "должен", "должно": "должен", "должны": "должен" },
  "gloss":      { "стать": "devenir", "принимать": "prendre" },
  "form_gloss": { "сначала": "d'abord", "должны": "devoir" },
  "phrases":    [{ "match": "друг другу", "lemma": "друг друга", "gloss": "les uns les autres" }]
}
```

* `force` – surface → the lemma it really belongs to (irregular verbs, suppletive forms).
  Also use it to adopt an inflection the stemmer refuses (`готов` → `готовый`).
* `block` – `[surface, lemma]` pairs the stemmer links but that are different words
  (`почту` is mail, not *almost*; `сиденье` is a seat, not *to sit*). Blocked words stay untagged.
* `canon` – merge lemmas so one text tags a word only once across its forms.
* `gloss` – French wording per lemma, overrides the gloss in `data/vocab/<id>.js`.
* `form_gloss` – French wording for one exact surface (wins over everything else).
* `phrases` – multi-word expressions; `match` is a regex, first match per text is tagged.

Gloss precedence in a rebuild: `form_gloss` → `gloss` → the gloss already used for that surface
in the file → `data/vocab/<id>.js`. Keeping the existing gloss preserves the author's wording;
`STALE GLOSS` tells you when an override disagrees with it.

## Workflow for a new set

1. Add `data/levels/<id>.js` and `data/vocab/<id>.js` as usual (see `AGENTS.md`).
2. Run `python tools/vocab/audit.py <id>` — with no overrides expect many MISSING/WRONG hits.
3. `--fix` (or `--preview`) to see what the rebuild would tag. Glosses come from the vocab list.
4. Walk the report:
   * `WRONG` → add a `block` pair, or fix the vocabulary if the word really belongs to it.
   * `MISSING` → usually a real omission; if the lemma is wrong for the context, add `force`
     or a `block` pair. Watch weak matches (`match 7x`): adjectives vs nouns, active vs reflexive.
   * `AMBIGUOUS` → confirm the first lemma makes sense, otherwise `force` the surface.
   * `STALE GLOSS` → change the file gloss (rebuild does it) or relax the override.
5. Repeat 3-4 until the summary says `missing 0, wrong 0, stale-gloss 0`.
6. Apply with `--write`, then:
   ```sh
   python tools/validate.py
   node --check data/levels/<id>.js
   ```
7. Open the page and spot-check a few texts, glossary cards and audio. Audio needs a `ru-RU`
   `speechSynthesis` voice, so it cannot be verified headlessly.

Budget roughly 10-20 minutes per new set: the script finds the problems, the overrides hold the
handful of decisions.

## Policy used for a2-2 (and default)

* One tag per lemma per text (the first occurrence), not every repetition. `--all` switches to
  every occurrence; tag density triples, so use it only if you want that.
* Tags show the exact inflected form used in the text (`[заметил|remarquer]`), but glosses stay in
  dictionary form (infinitive, singular, masculine) unless `form_gloss` says otherwise.
* Translations are French. Questions/options and UI stay as they are.

## Precision and recall

* Ordinary inflection is matched by the stemmer: cases, plurals, verb endings, short forms of
  adjectives, comparatives in `-ее/-ей` and adverbs in `-о` all resolve to the listed lemma.
  If the list contains `внимательный`, then `внимательнее` / `внимательно` are tagged with
  `match 85/80` and need no override. Irregular forms (suppletive verbs, `людей`, `готов`) need a
  `force` entry.
* The checker never guesses a different word: a listed noun does **not** cover its adjective
  (`внимание` ≠ `внимательнее`), and a listed imperfective does **not** cover its perfective
  (`звонить` ≠ `позвонить`). Those pairs appear under `RELATED, NOT LISTED` with the text
  numbers and one context line, so a real gap in the vocabulary is visible instead of silent.
  Adding the word to `data/vocab/<id>.js` is a content decision — the tool never does it.
* `RELATED` is a heuristic (shared 5+ character stem, optional prefix stripping). Expect a few
  obvious false friends (`интернет` ~ `интерес`); read it as a shortlist of candidates to add,
  not as an error list. It never affects tagging, so it cannot hurt precision.

## Look-alike pairs already known (worth checking in a new set)

`почту/почти`, `часто/часть`, `часов/часа → часть`, `домом/дома/дом → домой`,
`вечер/вечера → вечером`, `сиденье/сидеть`, `встречаем/встреча`, `хотят/хотим → хотя`,
`возможно/возможность`, `остаться/оставить`, `ста/стать`, `правильное/правильно`,
`опытные/опыт`, `интересных/интерес`, `входом/входить`, `деревню/дерево`,
`образец/образ`, `карты/картина`, `пяти/пятый`, `просто/простой`, `правила/право`,
`скорой/скоро`, `плохой/плохо`, `точную/точно`, `сестра/сесть`, `закончил/закончиться`,
`начинает/начинаться`, `потом/потому`, `всего/всегда`, `большой/больше`,
`школу/школы → школьный`, `как/какой`, `ни/ни`, `то/то`, `чем/чем`.

They are all in `overrides/a2-2.json`; copy the file when starting a new set and prune what no
longer applies.

## Reference result

`a2-2`: 25 texts, 711 tags, `missing 0, wrong 0, stale-gloss 0, ambiguous 7, blocked 60,
related 49`. Re-running `--fix --write` on it is a no-op (idempotent). The 7 ambiguous ones are
expected (`много/многий`, `дорога/дорогой`, `приходить/приходиться`).

`a2-1` (the demo set) still fails on purpose: it has no overrides and several real misses
(`недавно`-style omissions, `[Зимой|hiver]` which is not in its vocabulary). Running the tool on
it is a good example of the work the overrides encode.

## Notes

* Generated reports (`vocab-report.txt`, `tools/vocab/*.txt`) are scratch files; delete them.
* On Windows the console codepage can mangle Cyrillic in stdout — the report file is UTF-8,
  so open it (or `chcp 65001` first). The script's stdout summary is ASCII on purpose.
* The script only touches `data/levels/<id>.js`. It never edits vocabulary files, the manifest or
  `js/app.js`.
