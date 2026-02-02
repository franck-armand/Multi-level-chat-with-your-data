from pathlib import Path
from chatwithdocs.entities.vocab import load_vocab
from chatwithdocs.entities.resolve import resolve_entities

db = Path("data/edan.duckdb")
vocab = load_vocab(db)

tests = [
    "Tiapum",
    "R.H.D.P seats",
    "Cote d Ivoire",
    "KOUNFAO region",
    "P.D.C.I seats",
]

for t in tests:
    r = resolve_entities(t, vocab)
    print("Q:", t)
    print("Resolved:", r)
    print()
