"""The design-system gallery — every component in every state, light + dark.

This is the Phase 1 `/design-system` deliverable, realised as a screen (Qt has no
URL routing) reachable via Ctrl+Shift+D. A header switches theme (Light/Dark/Auto)
and accent live; everything below restyles instantly, which is also the manual
proof that the token system is wired correctly.
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.components import (
    Avatar,
    Badge,
    Button,
    Card,
    Checkbox,
    Chip,
    ChipInput,
    CommandPalette,
    ConfirmDialog,
    DataTable,
    DisclosureGroup,
    EmptyState,
    ErrorState,
    InlineBanner,
    KeyboardHint,
    Label,
    Modal,
    ProgressBar,
    Radio,
    SearchField,
    SegmentedControl,
    Select,
    Sheet,
    Skeleton,
    Spinner,
    Stepper,
    TabBar,
    TextField,
    Toast,
    ToastHost,
    Toggle,
)
from ui.theme import theme, tokens
from ui.theme.tokens import ACCENTS


class _Swatch(QFrame):
    def __init__(self, color, label, text_color, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 56)
        self.setStyleSheet(f"background:{color}; border-radius:{tokens.RADIUS['control']}px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        name = QLabel(label)
        name.setFont(theme().font("caption1", weight=600))
        name.setStyleSheet(f"color:{text_color}; background:transparent;")
        val = QLabel(color)
        val.setFont(theme().font("caption2"))
        val.setStyleSheet(f"color:{text_color}; background:transparent;")
        lay.addWidget(name)
        lay.addStretch()
        lay.addWidget(val)


class DesignSystemScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._toasts = ToastHost(self)
        self._build()
        theme().themeChanged.connect(self._restyle_shell)
        self._restyle_shell()

    # -- section scaffold -------------------------------------------------- #
    def _section(self, title, subtitle=""):
        wrap = QVBoxLayout()
        wrap.setSpacing(12)
        head = Label(title, "title2", "primary")
        wrap.addWidget(head)
        if subtitle:
            wrap.addWidget(Label(subtitle, "subhead", "secondary"))
        self._body.addLayout(wrap)
        return wrap

    def _row(self, *widgets, spacing=12):
        row = QHBoxLayout()
        row.setSpacing(spacing)
        for w in widgets:
            row.addWidget(w)
        row.addStretch()
        self._body.addLayout(row)
        return row

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header with live theme + accent controls
        self._header = QFrame()
        self._header.setObjectName("DSHeader")
        hb = QHBoxLayout(self._header)
        hb.setContentsMargins(32, 18, 32, 18)
        title = Label("Design System", "title1", "primary")
        hb.addWidget(title)
        hb.addStretch()
        self._mode = SegmentedControl(["Light", "Dark", "Auto"],
                                      {"light": 0, "dark": 1, "auto": 2}[theme().mode])
        self._mode.changed.connect(self._on_mode)
        hb.addWidget(self._mode)
        self._accent_row = QHBoxLayout()
        self._accent_row.setSpacing(6)
        for acc in ACCENTS:
            sw = QPushButton()
            sw.setFixedSize(22, 22)
            sw.setCursor(Qt.PointingHandCursor)
            sw.setToolTip(acc)
            sw.clicked.connect(lambda _=False, a=acc: theme().set_accent(a))
            sw.setStyleSheet(
                f"QPushButton{{background:{ACCENTS[acc]['light']}; border-radius:11px;"
                f" border:2px solid rgba(255,255,255,0.5);}}")
            self._accent_row.addWidget(sw)
        hb.addLayout(self._accent_row)
        root.addWidget(self._header)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self._body = QVBoxLayout(host)
        self._body.setContentsMargins(32, 24, 32, 48)
        self._body.setSpacing(28)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        self._build_typography()
        self._build_colors()
        self._build_buttons()
        self._build_selection()
        self._build_inputs()
        self._build_chips()
        self._build_feedback()
        self._build_containers()
        self._build_table()
        self._build_overlays()

    # -- sections ---------------------------------------------------------- #
    def _build_typography(self):
        self._section("Typography", "SF Pro / Inter · semantic scale, tabular numerals on data")
        for role in tokens.TYPE_SCALE:
            size, lh, w, _ = tokens.TYPE_SCALE[role]
            lbl = Label(f"{role} · {size}/{lh} — The quick brown fox jumps 1,234,567", role, "primary")
            self._body.addWidget(lbl)

    def _build_colors(self):
        self._section("Color", "Layered backgrounds, four label levels, semantic + eight accents")
        p = theme().palette()
        grid = QGridLayout()
        grid.setSpacing(8)
        swatches = [
            (p.bg_base, "bg-base", p.label_primary), (p.bg_elevated, "bg-elevated", p.label_primary),
            (theme().accent(), "accent", theme().accent_on()),
            (p.success, "success", "#fff"), (p.warning, "warning", "#fff"),
            (p.danger, "danger", "#fff"), (p.info, "info", "#fff"),
        ]
        for i, (c, n, tc) in enumerate(swatches):
            grid.addWidget(_Swatch(c, n, tc), i // 4, i % 4)
        self._body.addLayout(grid)

    def _build_buttons(self):
        self._section("Buttons", "primary · secondary · tinted · plain · destructive")
        self._row(Button("Primary", "primary"), Button("Secondary", "secondary"),
                  Button("Tinted", "tinted"), Button("Plain", "plain"),
                  Button("Delete", "destructive"))
        disabled = Button("Disabled", "primary")
        disabled.setEnabled(False)
        self._row(Button("Small", "primary", "sm"), Button("Medium", "primary", "md"),
                  Button("Large", "primary", "lg"), disabled, KeyboardHint("⌘K"))

    def _build_selection(self):
        self._section("Selection controls")
        self._row(Toggle(True), Toggle(False),
                  Checkbox("Remote only", True), Checkbox("Hybrid", False),
                  Radio("Full-time", True), Radio("Contract", False))
        self._row(SegmentedControl(["Day", "3 days", "Week", "Month"], 2), Stepper(12, 0, 60))

    def _build_inputs(self):
        self._section("Text inputs", "with inline validation states")
        f_ok = TextField("Email", "you@example.com", "We never share it")
        f_err = TextField("Salary", "e.g. 120000")
        f_err.set_error("Enter a number")
        f_valid = TextField("Title", "Backend Engineer")
        f_valid.set_valid("Looks good")
        grid = QGridLayout()
        grid.setSpacing(16)
        grid.addWidget(f_ok, 0, 0)
        grid.addWidget(f_err, 0, 1)
        grid.addWidget(f_valid, 0, 2)
        self._body.addLayout(grid)
        self._row(SearchField("Search title, company, or skill…"),
                  Select(["Remote", "Hybrid", "Onsite"]))
        self._body.addWidget(ChipInput(tokens_=["Python", "Django", "AWS"]))

    def _build_chips(self):
        self._section("Chips, badges, avatars")
        self._row(Chip("Python", "accent"), Chip("Docker", "neutral"),
                  Chip("Strong match", "success"), Chip("− Kubernetes", "warning"),
                  Chip("Removable", "neutral", removable=True),
                  Badge("3", "accent"), Badge("12", "danger"), Badge("NEW", "success"),
                  Avatar("Jane Doe"), Avatar("Sam Okoro"))

    def _build_feedback(self):
        self._section("Feedback & status")
        self._body.addWidget(InlineBanner("Groq rate limit hit — retrying in 4s.", "warning"))
        self._body.addWidget(InlineBanner("Resume parsed — 14 skills found.", "success"))
        pb = ProgressBar(68)
        pb.setFixedWidth(280)
        self._row(pb, Spinner(24), Spinner(18))
        sk = QVBoxLayout()
        for w_ in (Skeleton(16), Skeleton(12), Skeleton(12)):
            sk.addWidget(w_)
        skwrap = QWidget()
        skwrap.setLayout(sk)
        skwrap.setFixedWidth(280)
        self._row(skwrap)
        states = QHBoxLayout()
        e = EmptyState("No jobs yet", "Run a scan to see matches", "✦")
        er = ErrorState("Source failed", "HTTP 500 · themuse · 20:14")
        states.addWidget(self._boxed(e))
        states.addWidget(self._boxed(er))
        self._body.addLayout(states)

    def _build_containers(self):
        self._section("Containers")
        row = QHBoxLayout()
        row.setSpacing(16)
        for title, body in [("Senior Python Engineer", "Acme · Remote · $120k–$150k"),
                            ("Data Engineer", "Globex · NYC · Full-time")]:
            card = Card()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 14, 16, 14)
            cl.addWidget(Label(title, "headline", "primary"))
            cl.addWidget(Label(body, "footnote", "secondary"))
            crow = QHBoxLayout()
            crow.addWidget(Chip("Python", "success"))
            crow.addWidget(Chip("AWS", "success"))
            crow.addWidget(Badge("91", "accent"))
            crow.addStretch()
            cl.addLayout(crow)
            row.addWidget(card)
        self._body.addLayout(row)
        disc = DisclosureGroup("Score breakdown")
        disc.add(Label("Lexical 0.82 · Semantic 0.74 · LLM 0.90", "subhead", "secondary"))
        self._body.addWidget(disc)
        self._body.addWidget(TabBar(["Jobs", "Saved", "Applied"], 0))

    def _build_table(self):
        self._section("Data table", "sortable · sticky header · tabular figures")
        rows = [["Senior Python Engineer", "Acme", "Remote", "91"],
                ["Backend Engineer", "Globex", "Berlin", "84"],
                ["Data Engineer", "Initech", "NYC", "72"],
                ["Platform Engineer", "Umbrella", "Remote", "68"]]
        table = DataTable(["Title", "Company", "Location", "Score"], rows, numeric_cols=[3])
        table.setMinimumHeight(200)
        self._body.addWidget(table)

    def _build_overlays(self):
        self._section("Overlays & transient", "modal · sheet · confirm · command palette · toast")
        self._row(
            self._opener("Open modal", self._show_modal),
            self._opener("Open sheet", self._show_sheet),
            self._opener("Destructive confirm", self._show_confirm),
            self._opener("Command palette (⌘K)", self._show_palette),
            self._opener("Show toast", lambda: self._toasts.show_toast("Saved to your list", "success")),
        )

    # -- helpers ----------------------------------------------------------- #
    def _boxed(self, w):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 24, 16, 24)
        lay.addWidget(w)
        return card

    def _opener(self, text, cb):
        b = Button(text, "secondary", "md")
        b.clicked.connect(cb)
        return b

    def _on_mode(self, idx):
        theme().set_mode(["light", "dark", "auto"][idx])

    def _show_modal(self):
        m = Modal("Tailor résumé for this job", self.window(), 460, 300)
        m.add(Label("Drift will rewrite bullets to surface matched keywords — "
                    "honestly, never inventing experience.", "subhead", "secondary"))
        m.content.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        cancel = Button("Cancel", "secondary", "md")
        cancel.clicked.connect(m.reject)
        go = Button("Generate", "primary", "md")
        go.clicked.connect(m.accept)
        row.addWidget(cancel)
        row.addWidget(go)
        m.content.addLayout(row)
        m.exec_()

    def _show_sheet(self):
        s = Sheet("Add API key", self.window(), 320)
        s.add(TextField("Provider key", "gsk_…", "Stored in your OS keychain, never logged"))
        s.content.addStretch()
        close = Button("Save", "primary", "md")
        close.clicked.connect(s.accept)
        s.content.addWidget(close)
        s.exec_()

    def _show_confirm(self):
        ConfirmDialog("Dismiss this job?", "It won't appear in future scans. "
                      "You can undo from the toast.", "Dismiss", self.window()).exec_()

    def _show_palette(self):
        CommandPalette([
            ("Toggle theme", theme().toggle),
            ("Accent: Blue", lambda: theme().set_accent("blue")),
            ("Accent: Purple", lambda: theme().set_accent("purple")),
            ("Run all searches", lambda: self._toasts.show_toast("Running…", "info")),
            ("Upload résumé", lambda: None),
            ("Open settings", lambda: None),
        ], self.window()).exec_()

    def _restyle_shell(self):
        p = theme().palette()
        self.setStyleSheet(f"background:{p.bg_base};")
        self._header.setStyleSheet(
            f"QFrame#DSHeader{{background:{p.bg_sidebar_solid};"
            f" border-bottom:1px solid {p.separator_nonopaque};}}")
        # keep accent swatch ring readable in both themes
        for i in range(self._accent_row.count()):
            w = self._accent_row.itemAt(i).widget()
            if w:
                acc = list(ACCENTS)[i]
                sel = "3px solid " + theme().accent() if acc == theme().accent_id else "2px solid rgba(128,128,128,0.4)"
                w.setStyleSheet(
                    f"QPushButton{{background:{ACCENTS[acc]['light']}; border-radius:11px; border:{sel};}}")
