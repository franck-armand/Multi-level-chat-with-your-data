from ui.layout import setup_page, sidebar_controls
from core.router import run_app
from dotenv import load_dotenv

load_dotenv(override=False)


def main():
    setup_page()
    mode, db_path, max_rows = sidebar_controls()
    run_app(mode=mode, db_path=db_path, max_rows=max_rows)


if __name__ == "__main__":
    main()
