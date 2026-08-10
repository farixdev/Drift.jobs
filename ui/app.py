from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QShortcut,
    QStackedWidget,
    QWidget,
)

from ui import styles
from ui.components import Sidebar
from ui.dialogs import SettingsDialog
from ui.screen_dashboard import DashboardScreen
from ui.screen_design_system import DesignSystemScreen
from ui.screen_resume import ResumeScreen
from ui.screen_results import ResultsScreen
from ui.screen_run import RunScreen
from ui.screen_runs import RunsScreen
from ui.screen_search_builder import SearchBuilderScreen
from ui.screen_setup import SetupScreen
from ui.screen_sources import SourcesScreen
from ui.screen_tracker import TrackerScreen
from ui.theme import theme
from ui.worker import ScanWorker


class DriftApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("drift.jobs")
        self.setMinimumSize(900, 640)
        self.resize(1120, 780)
        self.setStyleSheet(styles.APP_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        # Left: sidebar navigation. Right: content stack.
        self.sidebar = Sidebar()
        self.sidebar.selected.connect(self._navigate)
        shell.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        shell.addWidget(self.stack, 1)

        # Screens
        self.dashboard_screen = DashboardScreen()
        self.setup_screen = SetupScreen()
        self.scan_screen = RunScreen()
        self.results_screen = ResultsScreen()
        self.design_screen = DesignSystemScreen()
        self.builder_screen = SearchBuilderScreen()
        self.resume_screen = ResumeScreen()
        self.tracker_screen = TrackerScreen()
        self.sources_screen = SourcesScreen()
        self.runs_screen = RunsScreen()

        for s in (self.dashboard_screen, self.setup_screen, self.scan_screen,
                  self.results_screen, self.design_screen, self.builder_screen,
                  self.resume_screen, self.tracker_screen, self.sources_screen,
                  self.runs_screen):
            self.stack.addWidget(s)

        # Route map for sidebar keys → (screen, reload?)
        self._routes = {
            "dashboard": (self.dashboard_screen, True),
            "search": (self.setup_screen, False),
            "jobs": (self.results_screen, False),
            "applications": (self.tracker_screen, True),
            "resumes": (self.resume_screen, False),
            "sources": (self.sources_screen, True),
            "runs": (self.runs_screen, True),
        }

        # Wire signals
        self.dashboard_screen.navigate.connect(self._nav_key)
        self.dashboard_screen.run_all.connect(self._go_search)
        self.setup_screen.start_scan.connect(self._begin_scan)
        self.setup_screen.open_builder.connect(self._open_search_builder)
        self.builder_screen.back.connect(self._go_search)
        self.builder_screen.run_search.connect(self._run_from_builder)
        self.results_screen.back_to_setup.connect(self._go_search)
        self.scan_screen.stop_clicked.connect(self._stop_scan)
        for scr in (self.resume_screen, self.tracker_screen, self.sources_screen,
                    self.runs_screen):
            scr.back.connect(lambda: self.sidebar.select("dashboard"))
        # Settings gear on every screen that has a topbar
        for scr in (self.setup_screen, self.scan_screen, self.results_screen,
                    self.builder_screen, self.resume_screen, self.tracker_screen,
                    self.sources_screen, self.runs_screen):
            if hasattr(scr, "topbar"):
                scr.topbar.settings_clicked.connect(self._open_settings)

        # Build the nav (auto-selects the first item → shows Dashboard).
        self.sidebar.add_item("dashboard", "Dashboard", "◫")
        self.sidebar.add_item("search", "Search", "⌕")
        self.sidebar.add_item("jobs", "Jobs", "≣")
        self.sidebar.add_item("applications", "Applications", "▤")
        self.sidebar.add_section("Library")
        self.sidebar.add_item("resumes", "Résumés", "▢")
        self.sidebar.add_item("sources", "Sources", "◆")
        self.sidebar.add_item("runs", "Runs", "↻")
        self.sidebar.add_stretch()
        self.sidebar.add_item("settings", "Settings", "⚙")

        QShortcut(QKeySequence("Ctrl+Shift+D"), self,
                  activated=lambda: self.stack.setCurrentWidget(self.design_screen))
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self._open_command_palette)

        self._worker: ScanWorker | None = None

    # -- navigation -------------------------------------------------------- #
    def _navigate(self, key: str) -> None:
        if key == "settings":
            self._open_settings()
            return
        route = self._routes.get(key)
        if not route:
            return
        screen, needs_reload = route
        if needs_reload and hasattr(screen, "reload"):
            screen.reload()
        self.stack.setCurrentWidget(screen)

    def _nav_key(self, key: str) -> None:
        self.sidebar.select(key)

    def _go_search(self) -> None:
        self.sidebar.select("search")

    # -- actions ----------------------------------------------------------- #
    def _open_settings(self) -> None:
        SettingsDialog(self).exec_()

    def _open_command_palette(self) -> None:
        from ui.components import CommandPalette
        CommandPalette([
            ("Dashboard", lambda: self.sidebar.select("dashboard")),
            ("Search / new scan", self._go_search),
            ("Search builder", self._open_search_builder),
            ("Jobs", lambda: self.sidebar.select("jobs")),
            ("Applications", lambda: self.sidebar.select("applications")),
            ("Résumé editor", lambda: self.sidebar.select("resumes")),
            ("Sources", lambda: self.sidebar.select("sources")),
            ("Runs", lambda: self.sidebar.select("runs")),
            ("Design system", lambda: self.stack.setCurrentWidget(self.design_screen)),
            ("Toggle light / dark theme", theme().toggle),
            ("Settings", self._open_settings),
        ], self).exec_()

    def _open_search_builder(self) -> None:
        self.stack.setCurrentWidget(self.builder_screen)

    def _run_from_builder(self, criteria) -> None:
        s = self.setup_screen
        if not getattr(s, "_resume_path", "") or not getattr(s, "_parsed", False):
            self.sidebar.select("search")
            QMessageBox.information(self, "Upload a résumé",
                                   "Upload a résumé on the Search screen first, then run your search.")
            return
        selected = [k for k, w in s.sources.items() if w.is_on()] or list(s.sources.keys())
        self._begin_scan(s._resume_path, selected, s.slider.value(),
                         s._resume_text, "", criteria=criteria)

    def _stop_scan(self) -> None:
        if self._worker:
            self._worker.stop()

    def _begin_scan(self, resume_path, sources, threshold, resume_text,
                    custom_url="", criteria=None) -> None:
        self.scan_screen.reset([] if custom_url else sources, threshold)
        self.stack.setCurrentWidget(self.scan_screen)
        self._worker = ScanWorker(resume_path, sources, threshold, resume_text,
                                 custom_url, criteria=criteria)
        self._worker.log_signal.connect(self.scan_screen.update_log)
        self._worker.progress_signal.connect(self.scan_screen.set_progress)
        self._worker.subtitle_signal.connect(self.scan_screen.set_subtitle)
        self._worker.source_event.connect(self.scan_screen.update_source)
        self._worker.stats_signal.connect(self.scan_screen.update_stats)
        self._worker.done_signal.connect(lambda jobs: self._show_results(jobs, threshold))
        self._worker.error_signal.connect(self._show_error)
        self._worker.start()

    def _show_results(self, jobs, threshold) -> None:
        resume_text = self._worker.parsed_resume_text if self._worker else ""
        skills = self._worker.parsed_skills if self._worker else []
        self.results_screen.set_results(jobs, threshold, resume_text, skills)
        self.stack.setCurrentWidget(self.results_screen)
        self.sidebar.select("jobs")

    def _show_error(self, message) -> None:
        QMessageBox.critical(self, "Scan failed", message)
        self.sidebar.select("search")
