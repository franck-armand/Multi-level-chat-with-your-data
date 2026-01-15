from pathlib import Path
from edan.rag.index import build_rag_index
from edan.rag.retriever import retrieve

db = Path("data/edan.duckdb")
build_rag_index(db)

hits = retrieve(db, "RHDP", k=5)
for h in hits:
    print(h)
