from core.handlers.level1_sql import run_level1
from core.handlers.level2_hybrid import run_level2

def run_app(mode: str, db_path: str, max_rows: int):
    if mode.startswith("Level 1"):
        run_level1(db_path=db_path, max_rows=max_rows)
    elif mode.startswith("Level 2"):
        run_level2(db_path=db_path, max_rows=max_rows)
    else:
        raise ValueError(f"Unsupported mode: {mode}")
