#Check out my other projects! https://justagwas.com/projects
#The OFFICIAL Repo - https://github.com/Justagwas/openpiano
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from openpiano.app_controller import PianoAppController
from openpiano.core.config import APP_NAME


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    controller = PianoAppController(app)
    controller.run()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())