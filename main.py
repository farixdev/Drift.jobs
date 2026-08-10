import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_env

load_env()

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from app_paths import resource_path
from ui.app import DriftApp
from version import __version__


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Drift")
    app.setApplicationDisplayName("Drift")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("drift.jobs")
    app.setWindowIcon(QIcon(resource_path("assets/logo/drift.ico")))

    # Bring the DB up to date so theme/accent preferences load, then install the
    # design system (tokens + global stylesheet + base font) before any UI shows.
    from db import init_db
    init_db()
    from ui.theme import theme
    theme().apply(app)

    # No API key is required — Drift scores locally out of the box. Add a free
    # Groq key via the ⚙ Settings dialog for AI scoring and cover letters.
    window = DriftApp()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
