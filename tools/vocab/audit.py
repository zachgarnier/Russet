#!/usr/bin/env python3
"""Audit (and optionally fix) vocabulary highlighting in data/levels/<id>.js.

Compares the [form|gloss] tags of a level against data/vocab/<id>.js and reports:
  MISSING   vocab words that appear in a text but are not highlighted  (errors)
  WRONG     tags whose word is not in the vocabulary, or a look-alike   (errors)
  STALE     tags whose French gloss disagrees with an override          (warnings)
  AMBIGUOUS one word fits several vocab lemmas, first one was picked    (review)
  BLOCKED   matches deliberately ignored via the overrides file         (info)
  UNUSED    vocab lemmas that appear in no text                         (info)

Judgement calls (irregular forms, look-alike words, specific glosses) are not
hard-coded here: they live in tools/vocab/overrides/<id>.json so a new set can
be tuned without touching this script. See tools/vocab/README.md.

Usage:
  python tools/vocab/audit.py a2-2                  # check, writes vocab-report.txt
  python tools/vocab/audit.py a2-2 --fix            # show what a rebuild would change
  python tools/vocab/audit.py a2-2 --fix --write    # rewrite the bodies in place
  python tools/vocab/audit.py a2-2 --all            # expect every occurrence, not just the first
  python tools/vocab/audit.py a2-2 --preview /tmp/a2-2.js   # dump the rebuilt file
  python tools/vocab/audit.py a2-2 --out report.txt

Exit code: 0 = clean, 1 = MISSING/WRONG found, 2 = bad invocation / missing file.
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OVERRIDES = ROOT / "tools" / "vocab" / "overrides"

# ---------- crude Russian stemmer (same rules used to build a2-2) ----------
ADJ_END = ("ый", "ий", "ой", "ая", "яя", "ое", "ее", "ые", "ие",
           "ых", "их", "ую", "юю", "ого", "ему", "ому", "ыми", "ими")
ENDINGS = ["ться", "тся", "ешься", "емся", "ишься", "ится", "ятся", "утся", "ются",
           "лся", "лась", "лось", "лись",
           "ями", "ами", "ов", "ев", "ей", "ой", "ый", "ий", "ая", "яя", "ое", "ее",
           "ые", "ие", "ых", "их", "ую", "юю",
           "ом", "ем", "ам", "ям", "ах", "ях", "ого", "ему", "ому", "ыми", "ими",
           "ешь", "ишь", "ет", "ит", "ут", "ют", "ат", "ят", "ем", "им", "ть",
           "а", "я", "о", "е", "у", "ю", "ы", "и", "ь", "й", "л", "м"]
ENDINGS.sort(key=len, reverse=True)

TAG_RE = re.compile(r"\[([^|\]\n]+)\|([^\]\n]+)\]")
TOKEN_RE = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")
BODY_RE = re.compile(r"body: `([\s\S]*?)`")


def stem(word):
    for end in ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[:-len(end)]
    return word


def expand_optional(text):
    """От(е)ц -> Отец, i.e. show both spellings in one entry."""
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"([А-Яа-яЁё])\(([А-Яа-яЁё]{1,2})\)", r"\1\2", text, count=1)
    return text


def clean_gloss(gloss):
    gloss = re.sub(r"\s*\([^)]*\)", "", gloss).strip(" ,;")
    return (gloss[:1].lower() + gloss[1:]) if gloss else "?"


def score(token, lemma):
    """0 = no match, 100 = exact, 75-85 = same stem / prefix."""
    if token == lemma:
        return 100
    if len(lemma) <= 3:
        return 0
    st, sl = stem(token), stem(lemma)
    if st == sl:
        return 85 if (token.endswith(ADJ_END) and lemma.endswith(ADJ_END)) else 80
    if len(st) >= 4 and len(sl) >= 4 and (st.startswith(sl) or sl.startswith(st)):
        gap = abs(len(st) - len(sl))
        if gap <= 2:
            return 75 - gap
    return 0


class Config:
    """tools/vocab/overrides/<id>.json — human decisions the stemmer cannot make."""

    def __init__(self, data):
        self.force = {k.lower(): v for k, v in data.get("force", {}).items()}
        self.block = {(t.lower(), l) for t, l in data.get("block", [])}
        self.canon = data.get("canon", {})
        self.gloss = data.get("gloss", {})
        self.form_gloss = {k.lower(): v for k, v in data.get("form_gloss", {}).items()}
        self.phrases = [(p["match"], p.get("lemma", p["match"].lower()), p["gloss"])
                        for p in data.get("phrases", [])]

    @property
    def stats(self):
        return (len(self.force), len(self.block), len(self.gloss) + len(self.form_gloss),
                len(self.phrases))


def load_vocab(path):
    raw = path.read_text(encoding="utf-8")
    body = raw.split("`", 1)[1].rsplit("`", 1)[0]
    order, gloss, lines = [], {}, 0
    for line in body.splitlines():
        if "|" not in line:
            continue
        lines += 1
        ru, fr = (part.strip() for part in line.split("|", 1))
        ru = re.sub(r"\([^)]*\)", " ", expand_optional(ru))
        meaning = clean_gloss(fr)
        for part in re.split(r"\s*/\s*|,\s*", ru):
            lemma = re.sub(r"\s+", " ", part.strip(" ?")).lower()
            if not lemma or "..." in lemma or lemma in gloss:
                continue
            gloss[lemma] = meaning
            order.append(lemma)
    return order, gloss, lines


def best_match(token, order, cfg):
    if token in cfg.force:
        lemma = cfg.force[token]
        return lemma, 100, [lemma], "force"
    top, winners = 0, []
    for lemma in order:
        s = score(token, lemma)
        if s > top:
            top, winners = s, [lemma]
        elif s and s == top:
            winners.append(lemma)
    if not winners:
        return None, 0, [], "none"
    return winners[0], top, winners, "stem"


def resolve(token, order, cfg):
    """-> (lemma or None, score, all candidates, how, blocked)"""
    lemma, s, winners, how = best_match(token, order, cfg)
    blocked = lemma is not None and (token, lemma) in cfg.block
    if blocked:
        return None, s, winners, how, True
    if lemma:
        lemma = cfg.canon.get(lemma, lemma)
    return lemma, s, winners, how, False


def strip_tags(body):
    return TAG_RE.sub(lambda m: m.group(1), body)


def tag_list(body):
    """Tags with offsets translated to the tag-free text: (surface, gloss, start, end)."""
    out, shift = [], 0
    for m in TAG_RE.finditer(body):
        start = m.start() - shift
        end = start + len(m.group(1))
        shift += (m.end() - m.start()) - len(m.group(1))
        out.append((m.group(1), m.group(2), start, end))
    return out


def is_phrase(surface, cfg):
    return any(re.fullmatch(pat, surface, flags=re.IGNORECASE) for pat, _, _ in cfg.phrases)


def phrase_gloss(surface, cfg):
    for pat, lemma, gl in cfg.phrases:
        if re.fullmatch(pat, surface, flags=re.IGNORECASE):
            return lemma, gl
    return None, None


PREFIXES = ("пере", "пред", "при", "про", "под", "над", "об", "от", "до", "из", "вы",
            "за", "на", "по", "с", "у", "в", "раз", "рос", "без", "бес", "не", "воз", "вос", "пре")


def _stem_variants(token):
    """The stem plus the stem with a typical verb/adjective prefix removed."""
    st = stem(token)
    variants = {st}
    for p in PREFIXES:
        if st.startswith(p) and len(st) - len(p) >= 4:
            variants.add(st[len(p):])
    return variants


def related_lemma(token, order, cfg):
    """Best vocab lemma that looks like the same word family but is rejected by `score`.

    Used for the report only (never for tagging): catches cases like 'внимательнее'
    when only the noun 'внимание' is listed, or 'позвонила' when only 'звонить' is.
    """
    if token in cfg.force:
        return None
    variants = _stem_variants(token)
    if max(len(v) for v in variants) < 4:
        return None
    best = None
    for lemma in order:
        if " " in lemma or score(token, lemma) or (token, lemma) in cfg.block:
            continue
        sl = stem(lemma)
        for cand in variants:
            cp = 0
            for a, b in zip(cand, sl):
                if a != b:
                    break
                cp += 1
            # 5 common chars either way: stripping a prefix makes look-alikes easy,
            # so a stripped variant gets no extra slack
            if cp < 5 or cp < min(len(cand), len(sl)) - 3:
                continue
            rank = (cp, -abs(len(cand) - len(sl)))
            if best is None or rank > best[0]:
                best = (rank, lemma)
    return best[1] if best else None


def context(plain, start, end, width=32):
    left = re.sub(r"\s+", " ", plain[max(0, start - width):start])
    right = re.sub(r"\s+", " ", plain[end:end + width])
    return f"…{left} [[{plain[start:end]}]] {right}…"


def plan(plain, cfg, order, gloss, existing, all_occurrences=False):
    """Choose the tags a rebuilt body should have. -> list of dicts sorted by offset."""
    tokens = [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(plain)]
    chosen, used, occupied = [], set(), []
    for pat, lemma, gl in cfg.phrases:
        for m in re.finditer(pat, plain, flags=re.IGNORECASE):
            chosen.append({"start": m.start(), "end": m.end(), "surface": m.group(0),
                           "lemma": lemma, "gloss": gl})
            used.add(lemma)
            occupied.append((m.start(), m.end()))
            if not all_occurrences:
                break
    for surface, start, end in tokens:
        low = surface.lower()
        lemma, _, _, _, blocked = resolve(low, order, cfg)
        if not lemma or (lemma in used and not all_occurrences):
            continue
        if any(a <= start < b for a, b in occupied):
            continue
        meaning = (cfg.form_gloss.get(low) or cfg.gloss.get(lemma)
                   or existing.get(low) or gloss.get(lemma) or "?")
        chosen.append({"start": start, "end": end, "surface": surface,
                       "lemma": lemma, "gloss": meaning})
        used.add(lemma)
        occupied.append((start, end))
    chosen.sort(key=lambda c: c["start"])
    return chosen


def build_body(plain, chosen):
    out, pos = [], 0
    for c in chosen:
        out.append(plain[pos:c["start"]])
        out.append(f"[{c['surface']}|{c['gloss']}]")
        pos = c["end"]
    out.append(plain[pos:])
    return "".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit vocabulary highlighting in a level file.")
    ap.add_argument("set_id", help="set id, e.g. a2-2 (data/levels/<id>.js + data/vocab/<id>.js)")
    ap.add_argument("--fix", action="store_true", help="compute the rebuilt bodies and list changes")
    ap.add_argument("--write", action="store_true", help="apply the rebuild to the level file (implies --fix)")
    ap.add_argument("--all", dest="all_occurrences", action="store_true",
                    help="target every occurrence of a vocab word, not just the first per text")
    ap.add_argument("--preview", metavar="PATH", help="write the rebuilt level file to PATH")
    ap.add_argument("--out", metavar="PATH", default="vocab-report.txt",
                    help="report file (default: vocab-report.txt)")
    args = ap.parse_args(argv)
    fix = args.fix or args.write

    level_path = ROOT / "data" / "levels" / f"{args.set_id}.js"
    vocab_path = ROOT / "data" / "vocab" / f"{args.set_id}.js"
    if not level_path.exists():
        print(f"ERROR: {level_path} not found")
        return 2
    if not vocab_path.exists():
        print(f"ERROR: {vocab_path} not found — this set has no vocabulary to check")
        return 2

    order, gloss, vocab_lines = load_vocab(vocab_path)
    cfg_path = OVERRIDES / f"{args.set_id}.json"
    cfg = Config(json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {})

    src = level_path.read_text(encoding="utf-8")
    spans = [(m.start(1), m.end(1)) for m in BODY_RE.finditer(src)]
    if not spans:
        print(f"ERROR: no `body:` blocks found in {level_path}")
        return 2
    existing = {}
    for m in TAG_RE.finditer(src):
        existing.setdefault(m.group(1).lower(), m.group(2))

    lines, counts = [], {"missing": 0, "wrong": 0, "stale": 0, "ambig": 0, "blocked": 0,
                         "related": 0, "tags": 0}
    ambiguous, blocked_pairs, per_text = [], set(), []
    missing_lines, wrong_lines, stale_lines = [], [], []
    fix_changes, seen_missing, related_map = [], set(), {}

    def note_related(low, surface, start, end, idx):
        rel = related_lemma(low, order, cfg)
        if not rel:
            return
        entry = related_map.get((low, rel))
        if entry is None:
            related_map[(low, rel)] = {"surface": surface, "texts": [idx],
                                       "context": context(plain, start, end)}
            counts["related"] += 1
        elif idx not in entry["texts"]:
            entry["texts"].append(idx)

    for idx, (bs, be) in enumerate(spans, 1):
        body = src[bs:be]
        plain = strip_tags(body)
        tokens = [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(plain)]
        tags = tag_list(body)
        counts["tags"] += len(tags)
        per_text.append(len(tags))

        tagged_lemmas, tagged_surfaces = set(), set()
        for surface, meaning, start, end in tags:
            low = surface.lower()
            if is_phrase(surface, cfg):
                lemma, _ = phrase_gloss(surface, cfg)
                tagged_lemmas.add(lemma)
                tagged_surfaces.add(low)
                continue
            lemma, sc, winners, how, blocked = resolve(low, order, cfg)
            if lemma:
                tagged_lemmas.add(lemma)
                tagged_surfaces.add(low)
            else:
                why = (f"look-alike of '{winners[0]}' (blocked)" if blocked
                       else "not in the vocabulary")
                wrong_lines.append(f"  [text {idx}] {why}: [{surface}|{meaning}]\n"
                                   f"           {context(plain, start, end)}")
                counts["wrong"] += 1
                continue
            opinion = cfg.form_gloss.get(low) or cfg.gloss.get(lemma)
            if opinion and meaning != opinion:
                stale_lines.append(f"  [text {idx}] [{surface}|{meaning}] -> \"{opinion}\" (override)")
                counts["stale"] += 1

        # MISSING: vocab words present but not highlighted
        if args.all_occurrences:
            token_count, tag_count = {}, {}
            for surface, _, _ in tokens:
                token_count[surface.lower()] = token_count.get(surface.lower(), 0) + 1
            for surface in tagged_surfaces:
                tag_count[surface] = tag_count.get(surface, 0) + 1
            for surface, start, end in tokens:
                low = surface.lower()
                lemma, sc, _, _, blocked = resolve(low, order, cfg)
                if not lemma:
                    note_related(low, surface, start, end, idx)
                    continue
                if lemma in tagged_lemmas:
                    continue
                if token_count[low] <= tag_count.get(low, 0):
                    continue
                if (idx, lemma) in seen_missing:
                    continue
                seen_missing.add((idx, lemma))
                missing_lines.append(
                    f"  [text {idx}] {surface} -> {lemma} ({gloss.get(lemma)})  match {sc}\n"
                    f"           {context(plain, start, end)}")
                counts["missing"] += 1
        else:
            for surface, start, end in tokens:
                low = surface.lower()
                lemma, sc, winners, how, blocked = resolve(low, order, cfg)
                if blocked:
                    blocked_pairs.add((low, winners[0]))
                    continue
                if not lemma:
                    note_related(low, surface, start, end, idx)
                    continue
                if lemma in tagged_lemmas:
                    continue
                if len(winners) > 1:
                    ambiguous.append((idx, surface, winners))
                if (idx, lemma) in seen_missing:
                    continue
                seen_missing.add((idx, lemma))
                missing_lines.append(
                    f"  [text {idx}] {surface} -> {lemma} ({gloss.get(lemma)})  match {sc}\n"
                    f"           {context(plain, start, end)}")
                counts["missing"] += 1

        # ambiguous tokens anywhere (info)
        for surface, start, end in tokens:
            low = surface.lower()
            _, _, winners, how, blocked = resolve(low, order, cfg)
            if how == "stem" and len(winners) > 1 and not blocked:
                ambiguous.append((idx, surface, winners))

        if fix:
            chosen = plan(plain, cfg, order, gloss, existing, args.all_occurrences)
            new_body = build_body(plain, chosen)
            old_map = {s.lower(): (s, g) for s, g, _, _ in tags}
            new_map = {c["surface"].lower(): (c["surface"], c["gloss"]) for c in chosen}
            for low, (surface, meaning) in old_map.items():
                if low not in new_map:
                    fix_changes.append(f"  [text {idx}] - [{surface}|{meaning}] (remove: not a vocab tag)")
                elif new_map[low][1] != meaning:
                    fix_changes.append(f"  [text {idx}] ~ [{surface}|{meaning}] -> \"{new_map[low][1]}\"")
            for low, (surface, meaning) in new_map.items():
                if low not in old_map:
                    fix_changes.append(f"  [text {idx}] + [{surface}|{meaning}] (add)")
            spans[idx - 1] = (bs, be, new_body)

    counts["ambig"] = len({(i, s, tuple(w)) for i, s, w in ambiguous})
    counts["blocked"] = len(blocked_pairs)

    # ---------- report ----------
    ovr = cfg.stats
    head = [f"set: {args.set_id}",
            f"level: {level_path.relative_to(ROOT)}",
            f"vocab: {vocab_path.relative_to(ROOT)} ({vocab_lines} lines -> {len(order)} lemmas)",
            f"overrides: {cfg_path.relative_to(ROOT) if cfg_path.exists() else 'none'}"
            f" (force {ovr[0]}, block {ovr[1]}, gloss {ovr[2]}, phrases {ovr[3]})",
            f"texts: {len(spans)}, tags: {counts['tags']}, mode: {'all occurrences' if args.all_occurrences else 'first per lemma per text'}",
            ""]
    lines += head
    lines += [f"MISSING ({counts['missing']})"] + (missing_lines or ["  none"]) + [""]
    lines += [f"WRONG ({counts['wrong']})"] + (wrong_lines or ["  none"]) + [""]
    lines += [f"STALE GLOSS ({counts['stale']})"] + (stale_lines or ["  none"]) + [""]
    uniq_ambig = sorted({(i, s, tuple(w)) for i, s, w in ambiguous})
    lines += [f"AMBIGUOUS ({len(uniq_ambig)}) — review, the first lemma was used"]
    lines += [f"  [text {i}] {s}: " + " / ".join(w) for i, s, w in uniq_ambig] or ["  none"]
    lines += [""]
    lines += [f"BLOCKED ({counts['blocked']}) — matches ignored on purpose"]
    lines += [f"  {t} -> {l}" for t, l in sorted(blocked_pairs)] or ["  none"]
    lines += [""]
    lines += [f"RELATED, NOT LISTED ({counts['related']}) — possible same-family words, never auto-tagged"]
    if related_map:
        for (low, rel), e in sorted(related_map.items(),
                                    key=lambda kv: (kv[1]["texts"][0], kv[1]["surface"].lower())):
            lines.append(f"  {e['surface']} ~ {rel} ({gloss.get(rel)})   texts: "
                         + ", ".join(str(t) for t in e["texts"]))
            lines.append(f"      {e['context']}")
    else:
        lines.append("  none")
    lines += [""]

    if fix:
        lines += [f"FIX PLAN ({len(fix_changes)} change(s))"] + (fix_changes or ["  nothing to change"]) + [""]
    else:
        lines += ["FIX PLAN (run with --fix to compute)", ""]

    lines += [f"PER-TEXT TAGS: {per_text}", ""]
    pathlib.Path(args.out).write_text("\n".join(lines), encoding="utf-8")

    if fix:
        pieces, pos = [], 0
        for entry in spans:
            bs, be, new_body = entry
            pieces.append(src[pos:bs])
            pieces.append(new_body)
            pos = be
        pieces.append(src[pos:])
        rebuilt = "".join(pieces)
        if args.preview:
            pathlib.Path(args.preview).write_text(rebuilt, encoding="utf-8")
        if args.write:
            if rebuilt == src:
                print(f"{args.set_id}: already up to date, file unchanged")
            else:
                level_path.write_text(rebuilt, encoding="utf-8")
                print(f"{args.set_id}: wrote {level_path.relative_to(ROOT)}"
                      f" ({len(fix_changes)} change(s), run python tools/validate.py)")
        else:
            print(f"{args.set_id}: dry run, {len(fix_changes)} change(s) - add --write to apply")

    print(f"{args.set_id}: {len(spans)} texts, {counts['tags']} tags, {len(order)} vocab lemmas")
    before = " (before fix)" if args.write and fix_changes else ""
    print(f"check{before}: missing {counts['missing']}, wrong {counts['wrong']},"
          f" stale-gloss {counts['stale']}, ambiguous {counts['ambig']},"
          f" blocked {counts['blocked']}, related {counts['related']}")
    print(f"report: {args.out}")
    if args.write and fix_changes:
        print("note: counts above describe the file before the fix - re-run to verify")
        return 0
    if counts["missing"] or counts["wrong"]:
        print("FAIL: vocabulary highlighting needs fixing (see report)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
