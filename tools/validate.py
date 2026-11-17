#!/usr/bin/env python3
"""Sanity-check data/levels/*.js: manifest coverage, markup, answer indexes. Usage: python3 tools/validate.py"""
import re, json, pathlib, sys
root = pathlib.Path(__file__).resolve().parent.parent
manifest = re.findall(r'"([^"]+)"', (root / "data/manifest.js").read_text(encoding="utf-8").split("=", 1)[1])
errors = 0
def err(m):
    global errors; errors += 1; print("ERROR:", m)
files = {p.stem for p in (root / "data/levels").glob("*.js")}
for i in manifest:
    if i not in files: err(f"manifest lists '{i}' but data/levels/{i}.js is missing")
for i in files - set(manifest): print(f"WARN: {i}.js is not in manifest.js (will not load)")
for p in sorted((root / "data/levels").glob("*.js")):
    s = p.read_text(encoding="utf-8")
    if f'id: "{p.stem}"' not in s: err(f"{p.name}: id must equal file name")
    if s.count("[") != s.count("]"): err(f"{p.name}: unbalanced [ ] in the file")
    for m in re.finditer(r"\[([^\]|]*)\]", s):
        if "|" not in m.group(0) and "qs" not in m.group(0) and '"' not in m.group(0): err(f"{p.name}: tag without translation: {m.group(0)}")
    for m in re.finditer(r"o:\s*(\[[^\]]*\]),\s*a:\s*(\d+)", s):
        n, a = len(json.loads(m.group(1))), int(m.group(2))
        if a >= n: err(f"{p.name}: answer index {a} out of range for {n} options")
for p in sorted((root / "data/vocab").glob("*.js")):
    for n, ln in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if ln and not ln.startswith(("//", "registerVocab", "`")) and "|" not in ln: err(f"{p.name}:{n}: vocab line without '|': {ln}")
    if p.stem not in manifest: print(f"WARN: vocab/{p.name} has no matching set in manifest.js")
print("OK" if not errors else f"{errors} error(s)"); sys.exit(1 if errors else 0)
