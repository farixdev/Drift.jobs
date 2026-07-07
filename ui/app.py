from PyQt5.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui import styles
from ui.dialogs import SettingsDialog
from ui.screen_results import ResultsScreen
from ui.screen_scan import ScanScreen
from ui.screen_setup import SetupScreen
from ui.worker import ScanWorker


class DriftApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("drift.jobs")
        self.setMinimumSize(480, 660)
        self.resize(560, 760)
        self.setStyleSheet(styles.APP_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.setup_screen = SetupScreen()
        self.scan_screen = ScanScreen()
        self.results_screen = ResultsScreen()

        self.stack.addWidget(self.setup_screen)
        self.stack.addWidget(self.scan_screen)
        self.stack.addWidget(self.results_screen)

        self.setup_screen.start_scan.connect(self._begin_scan)
        self.results_screen.back_to_setup.connect(self._go_setup)
        self.scan_screen.stop_clicked.connect(self._stop_scan)

        # Settings reachable from every screen's top bar.
        for screen in (self.setup_screen, self.scan_screen, self.results_screen):
            screen.topbar.settings_clicked.connect(self._open_settings)

        self._worker: ScanWorker | None = None

    def _open_settings(self) -> None:
        SettingsDialog(self).exec_()

    def _go_setup(self) -> None:
        self.stack.setCurrentWidget(self.setup_screen)

    def _stop_scan(self) -> None:
        if self._worker:
            self._worker.stop()

    def _begin_scan(
        self,
        resume_path: str,
        sources: list,
        threshold: int,
        resume_text: str,
        custom_url: str = "",
    ) -> None:
        self.scan_screen.reset(threshold)
        self.stack.setCurrentWidget(self.scan_screen)

        self._worker = ScanWorker(resume_path, sources, threshold, resume_text, custom_url)
        self._worker.log_signal.connect(self.scan_screen.update_log)
        self._worker.progress_signal.connect(self.scan_screen.set_progress)
        self._worker.subtitle_signal.connect(self.scan_screen.set_subtitle)
        self._worker.done_signal.connect(lambda jobs: self._show_results(jobs, threshold))
        self._worker.error_signal.connect(self._show_error)
        self._worker.start()

    def _show_results(self, jobs: list, threshold: int) -> None:
        resume_text = self._worker.parsed_resume_text if self._worker else ""
        skills = self._worker.parsed_skills if self._worker else []
        self.results_screen.set_results(jobs, threshold, resume_text, skills)
        self.stack.setCurrentWidget(self.results_screen)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Scan failed", message)
        self.stack.setCurrentWidget(self.setup_screen)
