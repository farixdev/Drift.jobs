"""Drift component library (Phase 1). macOS/iOS system aesthetic, theme-reactive.

Every component reads the active palette from `ui.theme` and restyles on
`themeChanged`. Import from here:

    from ui.components import Button, Card, TextField, Toggle, Toast, ...
"""
from ui.components.controls import (
    Button,
    Checkbox,
    KeyboardHint,
    Radio,
    SegmentedControl,
    Stepper,
    Toggle,
)
from ui.components.display import (
    Avatar,
    Badge,
    Card,
    Chip,
    DisclosureGroup,
    Label,
    ProgressBar,
    Skeleton,
    Spinner,
)
from ui.components.feedback import (
    EmptyState,
    ErrorState,
    InlineBanner,
    Toast,
    ToastHost,
)
from ui.components.inputs import ChipInput, SearchField, Select, TextField
from ui.components.navigation import Sidebar, TabBar, Toolbar
from ui.components.overlays import (
    CommandPalette,
    ConfirmDialog,
    Modal,
    Popover,
    Sheet,
)
from ui.components.table import DataTable

__all__ = [
    "Button", "Checkbox", "KeyboardHint", "Radio", "SegmentedControl", "Stepper",
    "Toggle", "Avatar", "Badge", "Card", "Chip", "DisclosureGroup", "Label",
    "ProgressBar", "Skeleton", "Spinner", "EmptyState", "ErrorState",
    "InlineBanner", "Toast", "ToastHost", "ChipInput", "SearchField", "Select",
    "TextField", "Sidebar", "TabBar", "Toolbar", "CommandPalette",
    "ConfirmDialog", "Modal", "Popover", "Sheet", "DataTable",
]
