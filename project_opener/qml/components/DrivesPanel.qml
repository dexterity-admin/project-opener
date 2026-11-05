import QtQuick

// Footlight 1: Drives on this PC (health by cause, then by symptom; DESIGN.md "the drive map").  The roots
// that are down, worst first, each with its pill, the mapping or "down since 09:40 · seen by 3 PCs" faint
// under it, and an action only where the row needs doing.  Reachable roots fold behind one ghost line.
// Data: app.watchers.roots (the office-wide merge; builder 1).
Card {
    id: panel
    property bool expanded: false
    property int maxRows: 4
    property int downCount: 0
    implicitHeight: 64 + Math.max(1, Math.min(list.count, maxRows)) * 48 + 40

    property int okCount: 0
    function recount() {
        var m = app.watchers.roots, n = 0
        for (var i = 0; i < m.count(); i++) if (m.get(i).status === "ok") n++
        okCount = n
        downCount = m.count() - n
    }
    Connections { target: app.watchers; function onRootsChanged() { panel.recount() } }
    Component.onCompleted: recount()

    Item {
        id: head
        x: panel.pad; y: panel.pad - 4
        width: panel.width - 2 * panel.pad
        height: 34
        SectionHeading {
            anchors.verticalCenter: parent.verticalCenter
            title: "Drives on this PC"
            facts: panel.downCount > 0 ? panel.downCount + " down" : list.count > 0 ? "all reachable" : ""
        }
        ActionButton {
            visible: app.activities.activityCount > 0
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "Re-check"
            icon: "arrows-clockwise"
            kind: "ghost"
            small: true
            onClicked: {
                app.activities.recheck()
                try { app.watchers.recheckRoots() } catch (e) {}
            }
        }
    }
    Column {
        id: list
        property int count: rep.count
        x: panel.pad
        anchors.top: head.bottom
        anchors.topMargin: 6
        width: panel.width - 2 * panel.pad
        Repeater {
            id: rep
            model: app.watchers.roots
            delegate: Item {
                width: list.width
                visible: model.status !== "ok" || panel.expanded
                height: visible ? 48 : 0
                Rectangle { width: parent.width; height: 1; color: panel.tk.border; visible: index > 0 }
                readonly property string word: model.status === "ok" ? "Reachable" : model.status === "offline" ? "Server offline"
                                             : model.status === "variable" ? "Undefined variable" : "Not found"
                Column {
                    anchors.left: parent.left
                    anchors.right: pill.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    Txt { width: parent.width; text: model.rootName; strong: true }
                    Txt {
                        width: parent.width
                        text: [model.mapping,
                               model.sinceText !== "" ? model.sinceText : (model.statusLabel !== parent.parent.word ? model.statusLabel : ""),
                               model.uses].filter(function (s) { return s && s !== "" }).join(" · ")
                        role: "small"
                        tone: "faint"
                        figures: true
                    }
                }
                StatusPill {
                    id: pill
                    anchors.right: act.visible ? act.left : parent.right
                    anchors.rightMargin: act.visible ? 8 : 0
                    anchors.verticalCenter: parent.verticalCenter
                    status: model.status === "ok" ? "ok" : model.status === "offline" ? "bad" : "warn"
                    label: parent.word
                }
                ActionButton {
                    id: act
                    width: 96
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    small: true
                    visible: model.status === "variable"
                    text: "Set variable"
                    onClicked: app.ui.go("settings", { section: "paths" })
                }
            }
        }
        EmptyBlock {
            visible: rep.count === 0
            width: list.width
            line: app.activities.activityCount > 0 ? "Checking the paths your activities use…" : "No paths to check yet."
        }
        Item {
            visible: panel.okCount > 0
            width: list.width
            height: 34
            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                Icon { name: panel.expanded ? "caret-down" : "caret-right"; size: 12; anchors.verticalCenter: parent.verticalCenter }
                Txt {
                    text: panel.okCount + (panel.okCount === 1 ? " drive reachable" : " drives reachable")
                    tone: "muted"
                    figures: true
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: panel.expanded = !panel.expanded }
        }
    }
}
