"""Editing dialogs. Each returns data through ``result_*`` attributes after ``exec()``."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from project_opener.core import models as M
from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import Button, Chip, IconButton, IconCircle, SwitchRow, label
from project_opener.ui.widgets.flow import FlowLayout


class _BaseDialog(QDialog):
    def __init__(self, title: str, parent=None, width: int = 560):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setWindowIcon(icons.app_icon())
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 20, 22, 18)
        self.root.setSpacing(12)
        self.heading = label(title, "h2")
        self.root.addWidget(self.heading)

    def add_buttons(self, ok_text: str = "Save") -> QDialogButtonBox:
        box = QDialogButtonBox()
        self.ok_btn = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok_btn.setObjectName("primary")
        box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)   # default (outlined) pill
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        self.root.addSpacing(6)
        self.root.addWidget(box)
        return box


class ColorSwatches(QWidget):
    """22 px colour circles; the selected one gets a 2 px ring in the text colour."""

    changed = Signal(str)

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._color = color
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._buttons: list[QPushButton] = []
        for c in M.PALETTE:
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(22, 22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(c)
            b.setProperty("color", c)
            b.setStyleSheet(self._style(c))
            b.clicked.connect(lambda _=False, cc=c: self._pick(cc))
            self.group.addButton(b)
            self._buttons.append(b)
            lay.addWidget(b)
        custom = IconButton("fa5s.eye-dropper", "Custom colour", size=16)
        custom.clicked.connect(self._custom)
        lay.addWidget(custom)
        lay.addStretch(1)
        self.set_color(color)

    @staticmethod
    def _style(c: str) -> str:
        t = theme.current()
        return (f"QPushButton {{ background-color: {c}; border: 2px solid {c}; border-radius: 11px; padding: 0; min-height: 0; max-height: 22px; }}"
                f"QPushButton:hover {{ border: 2px solid {t.border_strong}; }}"
                f"QPushButton:focus {{ border: 2px solid {t.accent}; }}"
                f"QPushButton:checked {{ border: 2px solid {t.text}; }}")

    def _pick(self, c: str) -> None:
        self._color = c
        self.changed.emit(c)

    def _custom(self) -> None:
        col = QColorDialog.getColor(QColor(self._color), self, "Project colour")
        if col.isValid():
            self.set_color(col.name())
            self.changed.emit(col.name())

    def set_color(self, c: str) -> None:
        self._color = c
        for b in self._buttons:
            b.setChecked(b.property("color").lower() == c.lower())

    def color(self) -> str:
        return self._color


class IconPicker(QWidget):
    """Grid of outline icons in the text colour; the selected one sits on an
    accent_soft fill with a 2 px accent border.  Saved fa5 names still select
    their Phosphor equivalent."""

    changed = Signal(str)

    def __init__(self, current: str, color: str, parent=None):
        super().__init__(parent)
        self._icon = current
        self._color = color
        t = theme.current()
        self.flow = FlowLayout(self, 0, 6, 6)
        self._buttons: dict[str, QPushButton] = {}
        for name, tip in icons.PROJECT_ICONS:
            b = QPushButton()
            b.setObjectName("iconpick")
            b.setCheckable(True)
            b.setFixedSize(34, 34)
            b.setToolTip(tip)
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton#iconpick {{ background: transparent; border: 1px solid transparent; border-radius: {t.radius_sm}px; padding: 0; min-height: 0; max-height: 34px; }}"
                f"QPushButton#iconpick:hover {{ background-color: {t.surface_2}; }}"
                f"QPushButton#iconpick:pressed {{ background-color: {t.surface_3}; }}"
                f"QPushButton#iconpick:focus {{ border: 2px solid {t.accent}; }}"
                f"QPushButton#iconpick:checked {{ background-color: {t.accent_soft}; border: 2px solid {t.accent}; }}")
            b.clicked.connect(lambda _=False, n=name: self._pick(n))
            self._buttons[name] = b
            self.flow.addWidget(b)
        self.set_color(color)
        self._pick(current, emit=False)

    def _pick(self, name: str, emit: bool = True) -> None:
        self._icon = name
        target = icons.resolve(name)
        for n, b in self._buttons.items():
            b.setChecked(icons.resolve(n) == target)
        if emit:
            self.changed.emit(name)

    def set_color(self, color: str) -> None:
        """Kept for callers; icons are drawn in the text colour, the preview carries the colour."""
        self._color = color
        t = theme.current()
        for n, b in self._buttons.items():
            b.setIcon(icons.icon(n, t.text))

    def icon_name(self) -> str:
        return self._icon


class TagEditor(QWidget):
    def __init__(self, tags: list[str], suggestions: list[str], parent=None):
        super().__init__(parent)
        self.tags: list[str] = list(tags)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Add a tag and press Enter (e.g. FST, as-built, P12513)")
        self.edit.returnPressed.connect(self._add_from_edit)
        row.addWidget(self.edit, 1)
        add = Button("Add", "fa5s.plus")
        add.clicked.connect(self._add_from_edit)
        row.addWidget(add)
        lay.addLayout(row)
        self.chips_host = QWidget()
        self.flow = FlowLayout(self.chips_host, 0, 6, 6)
        lay.addWidget(self.chips_host)
        if suggestions:
            sug = QHBoxLayout()
            sug.setSpacing(6)
            sug.addWidget(label("Suggestions:", "faint"))
            for s in [x for x in suggestions if x not in self.tags][:8]:
                c = Chip(s, checkable=False)
                c.clicked.connect(lambda _=False, v=s: self._add(v))
                sug.addWidget(c)
            sug.addStretch(1)
            lay.addLayout(sug)
        self._render()

    def _add_from_edit(self) -> None:
        for part in self.edit.text().split(","):
            self._add(part)
        self.edit.clear()

    def _add(self, tag: str) -> None:
        tag = tag.strip()
        if tag and tag.lower() not in [t.lower() for t in self.tags]:
            self.tags.append(tag)
            self._render()

    def _render(self) -> None:
        self.flow.clear()
        for tag in self.tags:
            c = Chip(f"{tag}  ✕", checkable=False)
            c.setToolTip("Remove")
            c.clicked.connect(lambda _=False, v=tag: self._remove(v))
            self.flow.addWidget(c)
        self.chips_host.updateGeometry()

    def _remove(self, tag: str) -> None:
        self.tags = [t for t in self.tags if t != tag]
        self._render()


class ProjectEditor(_BaseDialog):
    def __init__(self, project: M.Project | None, tag_suggestions: list[str], parent=None):
        super().__init__("New project" if project is None else "Edit project", parent, 620)
        self.project = project or M.Project(name="")
        p = self.project
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        head = QHBoxLayout()
        head.setSpacing(12)
        self.preview = IconCircle(p.icon, p.color, 34)
        head.addWidget(self.preview)
        self.name = QLineEdit(p.name)
        self.name.setPlaceholderText("Project name, e.g. P12513 As-built isometrics")
        self.name.setFont(theme.ui_font(theme.current().font_size + 1, 500))
        head.addWidget(self.name, 1)
        self.root.addLayout(head)

        self.client = QLineEdit(p.client)
        self.client.setPlaceholderText("Client (optional)")
        self.job = QLineEdit(p.job_number)
        self.job.setPlaceholderText("Job / project number (optional)")
        cj = QHBoxLayout()
        cj.addWidget(self.client, 1)
        cj.addWidget(self.job, 1)
        form.addRow("Client / job", cj)
        self.description = QLineEdit(p.description)
        self.description.setPlaceholderText("One line about this project")
        form.addRow("Description", self.description)
        self.swatches = ColorSwatches(p.color)
        self.swatches.changed.connect(self._color_changed)
        form.addRow("Colour", self.swatches)
        self.icon_picker = IconPicker(p.icon, p.color)
        self.icon_picker.changed.connect(lambda n: self.preview.set(icon_name=n))
        form.addRow("Icon", self.icon_picker)
        self.tags = TagEditor(p.tags, tag_suggestions)
        form.addRow("Tags", self.tags)
        self.notes = QPlainTextEdit(p.notes)
        self.notes.setPlaceholderText("Notes: contacts, drive mappings, conventions, reminders…")
        self.notes.setFixedHeight(80)
        form.addRow("Notes", self.notes)
        self.root.addLayout(form)
        self.auto = SwitchRow("Auto-launch at start-up", "Open this project's enabled items when Project Opener starts.",
                              p.auto_launch)
        self.root.addWidget(self.auto)
        self.add_buttons("Create" if project is None else "Save")
        self.name.setFocus()

    def _color_changed(self, c: str) -> None:
        self.preview.set(color=c)
        self.icon_picker.set_color(c)

    def accept(self) -> None:  # noqa: D102
        if not self.name.text().strip():
            QMessageBox.warning(self, "Name required", "Give the project a name.")
            self.name.setFocus()
            return
        p = self.project
        p.name = self.name.text().strip()
        p.client = self.client.text().strip()
        p.job_number = self.job.text().strip()
        p.description = self.description.text().strip()
        p.color = self.swatches.color()
        p.icon = self.icon_picker.icon_name()
        p.tags = self.tags.tags
        p.notes = self.notes.toPlainText()
        p.auto_launch = self.auto.isChecked()
        super().accept()


class ItemEditor(_BaseDialog):
    def __init__(self, item: M.Item | None, groups: list[str], parent=None):
        super().__init__("Add item" if item is None else "Edit item", parent, 600)
        self.item = item or M.Item(path="", kind="file")
        it = self.item
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        prow = QHBoxLayout()
        self.path = QLineEdit(it.path)
        self.path.setPlaceholderText(r"Z:\Project\P12513\ISO  ·  https://…  ·  {SERVER_ROOT}\…  ·  cmd: dir")
        self.path.textChanged.connect(self._guess)
        prow.addWidget(self.path, 1)
        bf = Button("", "fa5s.file")
        bf.setToolTip("Browse for a file")
        bf.clicked.connect(self._browse_file)
        bd = Button("", "fa5s.folder-open")
        bd.setToolTip("Browse for a folder")
        bd.clicked.connect(self._browse_folder)
        prow.addWidget(bf)
        prow.addWidget(bd)
        form.addRow("Path / URL", prow)
        self.kind = QComboBox()
        for k, lbl in (("file", "File"), ("folder", "Folder"), ("url", "Link"), ("app", "Application"), ("command", "Command")):
            self.kind.addItem(lbl, k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(it.kind)))
        form.addRow("Type", self.kind)
        self.label = QLineEdit(it.label)
        self.label.setPlaceholderText("Friendly name (optional)")
        form.addRow("Label", self.label)
        self.args = QLineEdit(it.args)
        self.args.setPlaceholderText('Arguments for applications, e.g. "{SERVER_ROOT}\\model.dgn"')
        form.addRow("Arguments", self.args)
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItem("")
        for g in groups:
            if g:
                self.group.addItem(g)
        self.group.setCurrentText(it.group)
        self.group.lineEdit().setPlaceholderText("Group, e.g. Drawings / References / Tools")
        form.addRow("Group", self.group)
        self.enabled = QCheckBox("Enabled (opens with the project)")
        self.enabled.setChecked(it.enabled)
        form.addRow("", self.enabled)
        self.root.addLayout(form)
        self.hint = label("Tip: paths starting with a drive letter are made portable automatically when you publish "
                          "to the Team Hub. Use {VARIABLES} from Settings for paths that differ per machine.", "faint", wrap=True)
        self.root.addWidget(self.hint)
        self.add_buttons("Add" if item is None else "Save")
        self.path.setFocus()

    def _guess(self, text: str) -> None:
        if not self.item.path:  # only auto-guess for new items
            self.kind.setCurrentIndex(max(0, self.kind.findData(M.guess_kind(text))))

    def _browse_file(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Choose a file", os.path.dirname(self.path.text()) or "")
        if f:
            self.path.setText(os.path.normpath(f))
            self.kind.setCurrentIndex(max(0, self.kind.findData(M.guess_kind(f))))

    def _browse_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose a folder", self.path.text() or "")
        if d:
            self.path.setText(os.path.normpath(d))
            self.kind.setCurrentIndex(max(0, self.kind.findData("folder")))

    def accept(self) -> None:  # noqa: D102
        if not self.path.text().strip():
            QMessageBox.warning(self, "Path required", "Enter a path, folder, link, application or command.")
            return
        it = self.item
        it.path = self.path.text().strip()
        it.kind = self.kind.currentData()
        it.label = self.label.text().strip()
        it.args = self.args.text().strip()
        it.group = self.group.currentText().strip()
        it.enabled = self.enabled.isChecked()
        super().accept()


class LaunchSetEditor(_BaseDialog):
    def __init__(self, project: M.Project, launch_set: M.LaunchSet | None, parent=None):
        super().__init__("New launch set" if launch_set is None else "Edit launch set", parent, 560)
        self.set = launch_set or M.LaunchSet(name="")
        self.project = project
        head = QHBoxLayout()
        head.setSpacing(12)
        self.preview = IconCircle(self.set.icon, project.color, 28)
        head.addWidget(self.preview)
        self.name = QLineEdit(self.set.name)
        self.name.setPlaceholderText("e.g. Morning start, Checking, Submission pack")
        head.addWidget(self.name, 1)
        self.root.addLayout(head)
        self.root.addWidget(label("Icon", "muted"))
        self.icon_picker = IconPicker(self.set.icon, project.color)   # same grid as ProjectEditor
        self.icon_picker.changed.connect(lambda n: self.preview.set(icon_name=n))
        self.root.addWidget(self.icon_picker)
        self.root.addWidget(label("Items in this set", "muted"))
        self.list = QListWidget()
        self.list.setMinimumHeight(240)
        chosen = set(self.set.item_ids)
        for it in project.items:
            li = QListWidgetItem(icons.icon(icons.KIND_ICONS.get(it.kind, "fa5s.file")), it.display_name + ("" if not it.group else f"   ·   {it.group}"))
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            li.setCheckState(Qt.CheckState.Checked if (it.id in chosen or launch_set is None) else Qt.CheckState.Unchecked)
            li.setToolTip(it.path)
            self.list.addItem(li)
        self.root.addWidget(self.list)
        row = QHBoxLayout()
        all_b = Button("Select all")
        all_b.clicked.connect(lambda: self._set_all(True))
        none_b = Button("Select none")
        none_b.clicked.connect(lambda: self._set_all(False))
        row.addWidget(all_b)
        row.addWidget(none_b)
        row.addStretch(1)
        self.root.addLayout(row)
        self.add_buttons("Create" if launch_set is None else "Save")

    def _set_all(self, on: bool) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def accept(self) -> None:  # noqa: D102
        if not self.name.text().strip():
            QMessageBox.warning(self, "Name required", "Give the launch set a name.")
            return
        self.set.name = self.name.text().strip()
        self.set.icon = self.icon_picker.icon_name()
        self.set.item_ids = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                             if self.list.item(i).checkState() == Qt.CheckState.Checked]
        super().accept()


class SendToDialog(_BaseDialog):
    def __init__(self, project: M.Project, peers: list[str], parent=None):
        super().__init__(f"Send '{project.name}' to a colleague", parent, 480)
        self.to = QComboBox()
        self.to.setEditable(True)
        for p in peers:
            self.to.addItem(p)
        self.to.lineEdit().setPlaceholderText("Windows user name of the colleague")
        self.root.addWidget(label("To", "muted"))
        self.root.addWidget(self.to)
        self.root.addWidget(label("Message (optional)", "muted"))
        self.message = QPlainTextEdit()
        self.message.setFixedHeight(80)
        self.message.setPlaceholderText("Here are the links for the P12513 check …")
        self.root.addWidget(self.message)
        self.root.addWidget(label("Drive letters in paths are converted to UNC so they open on their machine.", "faint", wrap=True))
        self.add_buttons("Send")

    @property
    def recipient(self) -> str:
        return self.to.currentText().strip()


class AnnouncementDialog(_BaseDialog):
    """Compose a Team Hub announcement.

    After ``exec()`` returns true read ``title_edit.text()``, ``body.toPlainText()``,
    ``level.currentData()`` and ``expires`` - the last is exactly what
    ``Hub.announce(..., expires=)`` takes: an ISO-8601 UTC timestamp string
    (``M.now_iso()`` format) or ``""`` for never.
    """

    def __init__(self, parent=None):
        super().__init__("Post an announcement", parent, 520)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Title, e.g. Z: drive moves to the new NAS on Friday")
        self.root.addWidget(self.title_edit)
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText("Details everyone should see on their Home page…")
        self.body.setFixedHeight(110)
        self.root.addWidget(self.body)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.level = QComboBox()
        for key, text in (("info", "Information"), ("warning", "Warning"), ("critical", "Critical")):
            self.level.addItem(text, key)
        row.addWidget(self.level, 1)
        row.addWidget(label("Expires after", "muted"))
        self.expires_days = QSpinBox()
        self.expires_days.setRange(0, 365)
        self.expires_days.setValue(0)
        self.expires_days.setSuffix(" days")
        self.expires_days.setSpecialValueText("Never")
        self.expires_days.setToolTip("0 = never expires")
        row.addWidget(self.expires_days)
        self.root.addLayout(row)
        self.add_buttons("Post")

    @property
    def expires(self) -> str:
        """ISO UTC timestamp N days from now, or ``""`` when the announcement never expires."""
        days = self.expires_days.value()
        if days <= 0:
            return ""
        return (datetime.now(UTC) + timedelta(days=days)).isoformat(timespec="seconds")

    def accept(self) -> None:  # noqa: D102
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "Title required", "Give the announcement a title.")
            return
        super().accept()


class PublishDialog(_BaseDialog):
    """Ask for the description shown on the Team Hub when publishing ``project``.

    After ``exec()`` returns true read ``description`` (stripped; prefilled with
    the project's own description).
    """

    def __init__(self, project: M.Project, parent=None):
        super().__init__(f"Publish '{project.name}' to Team Hub", parent, 520)
        self.root.addWidget(label("Description shown to the team", "muted"))
        self.description_edit = QPlainTextEdit(project.description)
        self.description_edit.setPlaceholderText("What this project is for and who should clone it…")
        self.description_edit.setFixedHeight(90)
        self.root.addWidget(self.description_edit)
        self.root.addWidget(label("Drive letters become UNC paths so the project opens on every PC.", "faint", wrap=True))
        self.add_buttons("Publish")
        self.description_edit.setFocus()

    @property
    def description(self) -> str:
        return self.description_edit.toPlainText().strip()


def confirm(parent, title: str, text: str, danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    yes = box.addButton("Yes", QMessageBox.ButtonRole.AcceptRole)
    yes.setObjectName("danger" if danger else "primary")
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is yes
