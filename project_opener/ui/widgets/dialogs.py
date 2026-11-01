"""Editing dialogs. Each returns data through ``result_*`` attributes after ``exec()``.

Every dialog follows one form grammar (docs/DESIGN.md "Dialogs"): a heading,
an optional grey line naming the object, labels *above* their fields, one
help line under a field where it earns its place, an inline error line above
the buttons (never a message box), and a button row whose confirming button
is the default: Enter accepts, Esc cancels.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from project_opener.core import models as M
from project_opener.ui import icons, theme
from project_opener.ui.widgets.common import Button, Chip, ElidedLabel, IconButton, IconCircle, SwitchRow, label
from project_opener.ui.widgets.flow import FlowLayout


class _FieldBlock(QWidget):
    """Label (above), the control, and an optional faint help line, as one block.

    A wrapped help line is given its real height for the block's width on every
    resize: box layouts otherwise size it as one line and it overlaps the field."""

    def __init__(self, text: str, widget: QWidget, help_text: str = ""):
        super().__init__()
        self.setObjectName("transparent_row")
        self.setStyleSheet("#transparent_row { background: transparent; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(label(text, "field_label"))
        lay.addWidget(widget)
        self.help = None
        if help_text:
            self.help = label(help_text, "faint", wrap=True)
            lay.addWidget(self.help)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if self.help is not None:
            h = self.help.heightForWidth(max(80, self.width()))
            if h > 0 and self.help.minimumHeight() != h:
                self.help.setMinimumHeight(h)
                self.updateGeometry()


def field_block(text: str, widget: QWidget, help_text: str = "") -> QWidget:
    return _FieldBlock(text, widget, help_text)


class _Scrim(QWidget):
    """A 40 % ink veil over the main window while one of our dialogs is open."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.hide()

    def paintEvent(self, e) -> None:  # noqa: N802
        from PySide6.QtGui import QColor, QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(16, 24, 20, 102))
        p.end()


class _BaseDialog(QDialog):
    def __init__(self, title: str, parent=None, width: int = 560, subtitle: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setWindowIcon(icons.app_icon())
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 22, 24, 20)
        self.root.setSpacing(12)
        head = QVBoxLayout()
        head.setSpacing(2)
        self.heading = label(title, "h2")
        head.addWidget(self.heading)
        self.subheading = ElidedLabel(subtitle, mode=Qt.TextElideMode.ElideMiddle)
        self.subheading.setObjectName("muted")
        self.subheading.setVisible(bool(subtitle))
        head.addWidget(self.subheading)
        self.root.addLayout(head)
        self._invalid: QWidget | None = None
        self.error_label = label("", "error", wrap=True)
        self.error_label.hide()
        self._scrim: _Scrim | None = None

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        host = self.parentWidget().window() if self.parentWidget() is not None else None
        if host is not None and host is not self:
            if self._scrim is None:
                self._scrim = _Scrim(host)
            self._scrim.setGeometry(host.rect())
            self._scrim.show()
            self._scrim.raise_()

    def hideEvent(self, e) -> None:  # noqa: N802
        super().hideEvent(e)
        if self._scrim is not None:
            self._scrim.hide()

    # ------------------------------------------------------------- fields
    def field(self, text: str, widget: QWidget, help_text: str = "") -> QWidget:
        block = field_block(text, widget, help_text)
        self.root.addWidget(block)
        return block

    def add_buttons(self, ok_text: str = "Save", danger: bool = False) -> QHBoxLayout:
        self.root.addWidget(self.error_label)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        self.ok_btn = QPushButton(ok_text)
        self.ok_btn.setObjectName("danger" if danger else "primary")
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setDefault(True)
        self.ok_btn.setAutoDefault(True)
        self.cancel_btn.setAutoDefault(False)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.ok_btn)
        self.root.addSpacing(4)
        self.root.addLayout(row)
        return row

    # ------------------------------------------------------------- errors
    def show_error(self, text: str, widget: QWidget | None = None) -> None:
        """Inline validation: the message above the buttons, the field outlined, focus on it."""
        self.clear_error()
        self.error_label.setText(text)
        self.error_label.show()
        if widget is not None:
            self._invalid = widget
            widget.setProperty("invalid", "true")
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.setFocus()

    def clear_error(self) -> None:
        self.error_label.hide()
        w = self._invalid
        if w is not None:
            w.setProperty("invalid", "false")
            w.style().unpolish(w)
            w.style().polish(w)
            self._invalid = None


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
        self.flow = FlowLayout(self, 0, 6, 6, fit_height=True)
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
        lay.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Add a tag, for example FST or as-built")
        self.edit.installEventFilter(self)        # Enter adds the tag and does not submit the dialog
        row.addWidget(self.edit, 1)
        add = Button("Add", "fa5s.plus")
        add.setAutoDefault(False)
        add.clicked.connect(self._add_from_edit)
        row.addWidget(add)
        lay.addLayout(row)
        self.chips_host = QWidget()
        self.chips_host.setObjectName("transparent_row")
        self.chips_host.setStyleSheet("#transparent_row { background: transparent; }")
        self.flow = FlowLayout(self.chips_host, 0, 6, 6, fit_height=True)
        lay.addWidget(self.chips_host)
        self._suggestions = [x for x in suggestions if x.lower() not in [t.lower() for t in self.tags]][:8]
        self._render()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.edit and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._add_from_edit()
                return True
        return super().eventFilter(obj, event)

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
        """The project's tags as chips with a ✕, then tags used elsewhere as "+ tag" chips to add."""
        self.flow.clear()
        for tag in self.tags:
            c = Chip(f"{tag}  ✕", checkable=False)
            c.setAutoDefault(False)
            c.setToolTip(f"Remove {tag}")
            c.clicked.connect(lambda _=False, v=tag: self._remove(v))
            self.flow.addWidget(c)
        lower = [t.lower() for t in self.tags]
        for s in self._suggestions:
            if s.lower() in lower:
                continue
            c = Chip(f"+ {s}", checkable=False)
            c.setObjectName("chip")
            c.setAutoDefault(False)
            c.setToolTip(f"Add {s} (used by another project)")
            c.clicked.connect(lambda _=False, v=s: self._add(v))
            self.flow.addWidget(c)
        self.chips_host.setVisible(bool(self.flow.count()))
        self.chips_host.updateGeometry()
        self.updateGeometry()

    def _remove(self, tag: str) -> None:
        self.tags = [t for t in self.tags if t != tag]
        self._render()


def _two(a: QWidget, b: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(a, 1)
    row.addWidget(b, 1)
    return row


class ProjectEditor(_BaseDialog):
    def __init__(self, project: M.Project | None, tag_suggestions: list[str], parent=None, is_new: bool | None = None):
        """``is_new`` defaults to "no project given"; pass True for a prefilled
        template (dropped files, a clone) so the dialog still says Create."""
        self.is_new = (project is None) if is_new is None else bool(is_new)
        super().__init__("New project" if self.is_new else "Edit project", parent, 640)
        self.project = project or M.Project(name="")
        p = self.project
        name_row = QWidget()
        name_row.setObjectName("transparent_row")
        name_row.setStyleSheet("#transparent_row { background: transparent; }")
        nr = QHBoxLayout(name_row)
        nr.setContentsMargins(0, 0, 0, 0)
        nr.setSpacing(10)
        self.preview = IconCircle(p.icon, p.color, 34)
        nr.addWidget(self.preview)
        self.name = QLineEdit(p.name)
        self.name.setPlaceholderText("P12513 As-built isometrics")
        self.name.setFont(theme.ui_font(theme.current().font_size + 1, 500))
        self.name.textEdited.connect(lambda _t: self.clear_error())
        nr.addWidget(self.name, 1)
        self.field("Name", name_row)

        self.client = QLineEdit(p.client)
        self.client.setPlaceholderText("FST")
        self.job = QLineEdit(p.job_number)
        self.job.setPlaceholderText("P12513")
        self.root.addLayout(_two(field_block("Client", self.client), field_block("Job number", self.job)))
        self.description = QLineEdit(p.description)
        self.description.setPlaceholderText("RLM red-line cross-check lot 7")
        self.field("Description", self.description)
        self.swatches = ColorSwatches(p.color)
        self.swatches.changed.connect(self._color_changed)
        self.field("Colour", self.swatches)
        self.icon_picker = IconPicker(p.icon, p.color)
        self.icon_picker.changed.connect(lambda n: self.preview.set(icon_name=n))
        self.field("Icon", self.icon_picker)
        self.tags = TagEditor(p.tags, tag_suggestions)
        self.field("Tags", self.tags)
        self.auto = SwitchRow("Open at start-up", "Opens this project's enabled items when Project Opener starts.",
                              p.auto_launch)
        self.root.addWidget(self.auto)
        self.add_buttons("Create project" if self.is_new else "Save")
        self.name.setFocus()

    def _color_changed(self, c: str) -> None:
        self.preview.set(color=c)
        self.icon_picker.set_color(c)

    def accept(self) -> None:  # noqa: D102
        if not self.name.text().strip():
            self.show_error("Give the project a name.", self.name)
            return
        p = self.project
        p.name = self.name.text().strip()
        p.client = self.client.text().strip()
        p.job_number = self.job.text().strip()
        p.description = self.description.text().strip()
        p.color = self.swatches.color()
        p.icon = self.icon_picker.icon_name()
        p.tags = self.tags.tags
        p.auto_launch = self.auto.isChecked()
        super().accept()


class ItemEditor(_BaseDialog):
    KINDS = (("file", "File"), ("folder", "Folder"), ("url", "Link"), ("app", "Application"), ("command", "Command"))

    def __init__(self, item: M.Item | None, groups: list[str], parent=None):
        super().__init__("Add item" if item is None else "Edit item", parent, 600)
        self.item = item or M.Item(path="", kind="file")
        it = self.item
        prow_w = QWidget()
        prow_w.setObjectName("transparent_row")
        prow_w.setStyleSheet("#transparent_row { background: transparent; }")
        prow = QHBoxLayout(prow_w)
        prow.setContentsMargins(0, 0, 0, 0)
        prow.setSpacing(8)
        self.path = QLineEdit(it.path)
        self.path.setPlaceholderText(r"Z:\Project\P12513\ISO, https://…, or cmd: ipconfig")
        self.path.textChanged.connect(self._guess)
        self.path.textEdited.connect(lambda _t: self.clear_error())
        prow.addWidget(self.path, 1)
        bf = Button("File…", "fa5s.file")
        bf.setToolTip("Choose a file")
        bf.setAutoDefault(False)
        bf.clicked.connect(self._browse_file)
        bd = Button("Folder…", "fa5s.folder-open")
        bd.setToolTip("Choose a folder")
        bd.setAutoDefault(False)
        bd.clicked.connect(self._browse_folder)
        prow.addWidget(bf)
        prow.addWidget(bd)
        self.field("Path, link or command", prow_w,
                   "{VARIABLES} from Settings resolve on each PC. Drive letters become UNC paths when the project is published.")
        self.kind = QComboBox()
        for k, lbl in self.KINDS:
            self.kind.addItem(lbl, k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(it.kind)))
        self.group = QComboBox()
        self.group.setEditable(True)
        self.group.addItem("")
        for g in groups:
            if g:
                self.group.addItem(g)
        self.group.setCurrentText(it.group)
        self.group.lineEdit().setPlaceholderText("Drawings, References, Tools")
        self.root.addLayout(_two(field_block("Type", self.kind), field_block("Group", self.group)))
        self.label = QLineEdit(it.label)
        self.label.setPlaceholderText("Shown instead of the file name")
        self.args = QLineEdit(it.args)
        self.args.setPlaceholderText(r'"{SERVER_ROOT}\model.dgn"')
        self.root.addLayout(_two(field_block("Label", self.label), field_block("Arguments", self.args)))
        self.enabled = SwitchRow("Opens with the project", "Off: kept in the list, skipped by Open project.", it.enabled)
        self.root.addWidget(self.enabled)
        self.add_buttons("Add item" if item is None else "Save")
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
            self.show_error("Enter a path, folder, link, application or command.", self.path)
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
        super().__init__("New launch set" if launch_set is None else "Edit launch set", parent, 560, subtitle=project.name)
        self.set = launch_set or M.LaunchSet(name="")
        self.project = project
        name_row = QWidget()
        name_row.setObjectName("transparent_row")
        name_row.setStyleSheet("#transparent_row { background: transparent; }")
        nr = QHBoxLayout(name_row)
        nr.setContentsMargins(0, 0, 0, 0)
        nr.setSpacing(10)
        self.preview = IconCircle(self.set.icon, project.color, 28)
        nr.addWidget(self.preview)
        self.name = QLineEdit(self.set.name)
        self.name.setPlaceholderText("Checking, Submission pack, Morning start")
        self.name.textEdited.connect(lambda _t: self.clear_error())
        nr.addWidget(self.name, 1)
        self.field("Name", name_row)
        self.icon_picker = IconPicker(self.set.icon, project.color)   # same grid as ProjectEditor
        self.icon_picker.changed.connect(lambda n: self.preview.set(icon_name=n))
        self.field("Icon", self.icon_picker)
        self.list = QListWidget()
        self.list.setFixedHeight(232)
        chosen = set(self.set.item_ids)
        ordered = project.items_for_set(self.set) + [i for i in project.items if i.id not in chosen]
        for it in ordered:                                  # the list order is the launch order
            li = QListWidgetItem(icons.icon(icons.KIND_ICONS.get(it.kind, "fa5s.file")), it.display_name + ("" if not it.group else f"   ·   {it.group}"))
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            li.setCheckState(Qt.CheckState.Checked if (it.id in chosen or launch_set is None) else Qt.CheckState.Unchecked)
            li.setToolTip(it.path)
            self.list.addItem(li)
        self.list.itemChanged.connect(lambda _i: self._count())
        self.count_lbl = label("", "faint")
        block = self.field("Items in this set", self.list)
        block.layout().addWidget(self.count_lbl)
        row = QHBoxLayout()
        row.setSpacing(8)
        all_b = Button("Select all")
        all_b.setAutoDefault(False)
        all_b.clicked.connect(lambda: self._set_all(True))
        none_b = Button("Select none")
        none_b.setAutoDefault(False)
        none_b.clicked.connect(lambda: self._set_all(False))
        row.addWidget(all_b)
        row.addWidget(none_b)
        row.addStretch(1)
        up = Button("Move up", "fa5s.arrow-up")
        up.setAutoDefault(False)
        up.clicked.connect(lambda: self.move_current(-1))
        down = Button("Move down", "fa5s.arrow-down")
        down.setAutoDefault(False)
        down.clicked.connect(lambda: self.move_current(1))
        row.addWidget(up)
        row.addWidget(down)
        self.root.addLayout(row)
        self.add_buttons("Create launch set" if launch_set is None else "Save")
        self._count()
        self.name.setFocus()

    def move_current(self, delta: int) -> None:
        """Move the selected row one step up or down: the list order is the launch order."""
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or not (0 <= target < self.list.count()):
            return
        item = self.list.takeItem(row)
        self.list.insertItem(target, item)
        self.list.setCurrentRow(target)
        self._count()

    def _checked_ids(self) -> list[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]

    def _count(self) -> None:
        n, total = len(self._checked_ids()), self.list.count()
        self.count_lbl.setText(f"{n} of {total} item{'s' if total != 1 else ''} selected")

    def _set_all(self, on: bool) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def accept(self) -> None:  # noqa: D102
        if not self.name.text().strip():
            self.show_error("Give the launch set a name.", self.name)
            return
        ids = self._checked_ids()
        if not ids:
            self.show_error("Select at least one item.", self.list)
            return
        self.set.name = self.name.text().strip()
        self.set.icon = self.icon_picker.icon_name()
        self.set.item_ids = ids
        super().accept()


class SendToDialog(_BaseDialog):
    def __init__(self, project: M.Project, peers: list[str], parent=None):
        super().__init__("Send to a colleague", parent, 480, subtitle=project.name)
        self.to = QComboBox()
        self.to.setEditable(True)
        for p in peers:
            self.to.addItem(p)
        self.to.lineEdit().setPlaceholderText("Windows user name")
        self.to.lineEdit().textEdited.connect(lambda _t: self.clear_error())
        self.field("To", self.to, "Colleagues seen on the hub are listed; any Windows user name works.")
        self.message = QPlainTextEdit()
        self.message.setFixedHeight(80)
        self.message.setPlaceholderText("Here are the links for the P12513 check")
        self.field("Message (optional)", self.message, "Drive letters become UNC paths so the items open on their PC.")
        self.add_buttons("Send")

    @property
    def recipient(self) -> str:
        return self.to.currentText().strip()

    def accept(self) -> None:  # noqa: D102
        if not self.recipient:
            self.show_error("Enter the colleague's Windows user name.", self.to)
            return
        super().accept()


class AnnouncementDialog(_BaseDialog):
    """Compose a Team Hub announcement.

    After ``exec()`` returns true read ``title_edit.text()``, ``body.toPlainText()``,
    ``level.currentData()`` and ``expires`` - the last is exactly what
    ``Hub.announce(..., expires=)`` takes: an ISO-8601 UTC timestamp string
    (``M.now_iso()`` format) or ``""`` for never.
    """

    def __init__(self, parent=None):
        super().__init__("Post an announcement", parent, 520, subtitle="Shown as a banner on everyone's Home page")
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Z: drive moves to the new NAS on Friday")
        self.title_edit.textEdited.connect(lambda _t: self.clear_error())
        self.field("Title", self.title_edit)
        self.body = QPlainTextEdit()
        self.body.setPlaceholderText("The Project share moves at 18:00. Mapped drives reconnect automatically.")
        self.body.setFixedHeight(96)
        self.field("Details", self.body)
        self.level = QComboBox()
        for key, text in (("info", "Information"), ("warning", "Warning"), ("critical", "Critical")):
            self.level.addItem(text, key)
        self.expires_days = QSpinBox()
        self.expires_days.setRange(0, 365)
        self.expires_days.setValue(0)
        self.expires_days.setSuffix(" days")
        self.expires_days.setSpecialValueText("Never")
        self.expires_days.setToolTip("0 = never expires")
        self.root.addLayout(_two(field_block("Level", self.level), field_block("Expires after", self.expires_days)))
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
            self.show_error("Give the announcement a title.", self.title_edit)
            return
        super().accept()


class PublishDialog(_BaseDialog):
    """Ask for the description shown on the Team Hub when publishing ``project``.

    After ``exec()`` returns true read ``description`` (stripped; prefilled with
    the project's own description).
    """

    def __init__(self, project: M.Project, parent=None):
        super().__init__("Publish to Team Hub", parent, 520, subtitle=project.name)
        self.description_edit = QPlainTextEdit(project.description)
        self.description_edit.setPlaceholderText("What this project is for and who should clone it")
        self.description_edit.setFixedHeight(90)
        self.field("Description shown to the team", self.description_edit,
                   "Drive letters become UNC paths so the project opens on every PC.")
        self.add_buttons("Publish")
        self.description_edit.setFocus()

    @property
    def description(self) -> str:
        return self.description_edit.toPlainText().strip()


class ConfirmDialog(_BaseDialog):
    """A confirmation in the app's own grammar: the question, its consequence, the action named.

    For a destructive action the confirming button is outlined in the negative
    colour and Cancel takes the default, so Enter never deletes.
    """

    def __init__(self, parent, title: str, text: str, ok_text: str, danger: bool = False):
        super().__init__(title, parent, 440)
        self.root.addWidget(label(text, "muted", wrap=True))
        self.add_buttons(ok_text, danger=danger)
        if danger:
            self.ok_btn.setDefault(False)
            self.cancel_btn.setDefault(True)
            self.cancel_btn.setAutoDefault(True)
            self.cancel_btn.setFocus()
        else:
            self.ok_btn.setFocus()


def confirm_box(parent, title: str, text: str, danger: bool = False, ok_text: str = "") -> tuple[ConfirmDialog, QPushButton]:
    """The confirmation dialog and its confirming button, not yet shown (``confirm`` execs it)."""
    dlg = ConfirmDialog(parent, title, text, ok_text or title, danger)
    return dlg, dlg.ok_btn


def confirm(parent, title: str, text: str, danger: bool = False, ok_text: str = "") -> bool:
    dlg, _ = confirm_box(parent, title, text, danger, ok_text)
    return dlg.exec() == QDialog.DialogCode.Accepted
