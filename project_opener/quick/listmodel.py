"""``DictListModel``: a list of dicts as a QML model, one role per key.

The one architectural rule of the Qt Quick shell (spikes/quick/REPORT.md, hard
item 2): every list the UI shows is a ``QAbstractListModel`` with per-row
``dataChanged``, never a QVariantList property, so delegates stay in place and
their arrival animations do not replay when one row changes.

Role-name rules (hard item 3): never use ``root``, ``parent``, ``model``,
``index``, ``data``, ``id`` or a QML Item property name (``x``, ``y``,
``width``, ``height``, ``visible``, ``color``, ``text``, ``state``,
``enabled``, ``opacity``, ``scale``, ``z``) as a role.  Ids are ``fooId``.
``ROLE_BLOCKLIST`` is checked when the model is built.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, QPersistentModelIndex, Qt, Signal, Slot

ROLE_BLOCKLIST = frozenset({
    "root", "parent", "model", "index", "data", "id", "x", "y", "z", "width", "height", "visible", "color",
    "text", "state", "enabled", "opacity", "scale", "rotation", "children", "anchors", "focus", "clip",
})


class DictListModel(QAbstractListModel):
    """Rows are dicts; ``roles`` names the keys QML may read (``model.<role>`` or bare ``<role>``)."""

    countChanged = Signal()

    def __init__(self, roles: Sequence[str], key: str = "", rows: Iterable[dict[str, Any]] | None = None,
                 parent: Any = None):
        super().__init__(parent)
        bad = [r for r in roles if r in ROLE_BLOCKLIST]
        if bad:
            raise ValueError(f"reserved QML names used as roles: {bad}")
        self._roles = list(roles)
        self._key = key or (self._roles[0] if self._roles else "")
        self._rows: list[dict[str, Any]] = [dict(r) for r in rows or ()]

    # ---------------------------------------------------------- Qt contract
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._rows)

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return {Qt.ItemDataRole.UserRole + i: QByteArray(k.encode("utf-8")) for i, k in enumerate(self._roles)}

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            role = Qt.ItemDataRole.UserRole
        i = role - Qt.ItemDataRole.UserRole
        if not 0 <= i < len(self._roles):
            return None
        return self._rows[index.row()].get(self._roles[i])

    # ------------------------------------------------------------ QML side
    @Slot(result=int)
    def count(self) -> int:
        return len(self._rows)

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict[str, Any]:
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}

    @Slot(str, result=int)
    def indexOf(self, key_value: str) -> int:  # noqa: N802
        for i, r in enumerate(self._rows):
            if str(r.get(self._key)) == str(key_value):
                return i
        return -1

    # --------------------------------------------------------- Python side
    @property
    def roles(self) -> list[str]:
        return list(self._roles)

    @property
    def rows(self) -> list[dict[str, Any]]:
        return self._rows

    def reset(self, rows: Iterable[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = [dict(r) for r in rows]
        self.endResetModel()
        self.countChanged.emit()

    def update(self, row: int, **values: Any) -> None:
        if not 0 <= row < len(self._rows):
            return
        changed = [k for k, v in values.items() if self._rows[row].get(k) != v]
        if not changed:
            return
        self._rows[row].update(values)
        roles = [Qt.ItemDataRole.UserRole + self._roles.index(k) for k in changed if k in self._roles]
        self.dataChanged.emit(self.index(row), self.index(row), roles)

    def upsert(self, row_data: dict[str, Any]) -> int:
        """Update the row with the same key value, else append.  Returns the row index."""
        i = self.indexOf(str(row_data.get(self._key)))
        if i >= 0:
            self.update(i, **row_data)
            return i
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(dict(row_data))
        self.endInsertRows()
        self.countChanged.emit()
        return len(self._rows) - 1

    def remove(self, key_value: str) -> bool:
        i = self.indexOf(key_value)
        if i < 0:
            return False
        self.beginRemoveRows(QModelIndex(), i, i)
        del self._rows[i]
        self.endRemoveRows()
        self.countChanged.emit()
        return True

    def sync(self, rows: Iterable[dict[str, Any]]) -> None:
        """Make the model equal ``rows`` (matched by key) with row-level signals only:
        changed rows update in place, missing rows are removed, new rows inserted at their position.
        Use this for lists that refresh often (live snapshot, peers) so delegates survive."""
        new = [dict(r) for r in rows]
        keys = [str(r.get(self._key)) for r in new]
        for k in [str(r.get(self._key)) for r in self._rows if str(r.get(self._key)) not in keys]:
            self.remove(k)
        for pos, r in enumerate(new):
            i = self.indexOf(str(r.get(self._key)))
            if i < 0:
                self.beginInsertRows(QModelIndex(), pos, pos)
                self._rows.insert(pos, r)
                self.endInsertRows()
                self.countChanged.emit()
                continue
            if i != pos:
                self.beginMoveRows(QModelIndex(), i, i, QModelIndex(), pos if pos < i else pos + 1)
                self._rows.insert(pos, self._rows.pop(i))
                self.endMoveRows()
            self.update(pos, **r)
