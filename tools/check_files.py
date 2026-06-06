from pathlib import Path
files = [
    Path('pfe-ai-recruitment/test_cv_parser.py'),
    Path('pfe-ai-recruitment/app/agents/cv_parser.py'),
]
for f in files:
    if not f.exists():
        print(f"Missing: {f}")
        continue
    b = f.read_bytes()
    idx = b.find(b"\x00")
    print(f"{f}: null_index={idx}, size={len(b)}")
