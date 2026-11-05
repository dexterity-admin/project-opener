import QtQuick

// Footlight 1: Drives on this PC (health by cause, then by symptom; DESIGN.md "the drive map").  The roots
// that are down, worst first, each with its pill and two lines: the root and its mapping ("\\nas01  Z: ->
// \\nas01\Project"), then the office-wide fact in full, "down since 09:40 · seen by 3 PCs · 14 jobs"
// (brief 3.4); that line wraps rather than elides.  An action only where the row needs doing.  Reachable
// roots fold behind one ghost line that expands on click.  At most four rows while folded, so the three
// footlights end level; the panel is as tall as its rows (no panel-void) and Re-check sits in the heading.
// Data: app.watchers.roots, the one source for "down since" (the office-wide merge of watch/<user>.json).
Card {
    id: panel
    property bool expanded: false
    property int maxRows: 4
    property int downCount: 0
    property int okCount: 0
    implicitHeight: list.y + list.implicitHeight + pad

    function recount() {
        var m = app.watchers.roots, n = 0
        for (var i = 0; i < m.count(); i++) if (m.get(i).status === "ok") n++
        okCount = n
        downCount = m.count() - n
    }
    function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s") }
    Connections { target: app.watchers; function onRootsChanged() { panel.recount() } }
    Connections { target: app.watchers.roots; function onCountChanged() { panel.recount() } }
    Component.onCompleted: recount()

    Item {
        id: head
        x: panel.pad; y: panel.pad - 4
        width: panel.width - 2 * panel.pad
        height: 34
        SectionHeading {
            anchors.verticalCenter: parent.verticalCenter
            title: "Drives on this PC"
            facts: panel.downCount > 0 ? panel.downCount + " down" : rep.count > 0 ? "all reachable" : ""
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
                app.watchers.recheckRoots()
            }
        }
    }
    Column {
        id: list
        x: panel.pad
        y: head.y + head.height + 6
        width: panel.width - 2 * panel.pad
        Repeater {
            id: rep
            model: app.watchers.roots
            delegate: Item {
                id: row
                readonly property bool down: model.status !== "ok"
                width: list.width
                // roots are sorted worst first, so the folded rows are the down ones, capped at maxRows
                visible: panel.expanded || (down && index < panel.maxRows)
                height: visible ? Math.max(48, lines.implicitHeight + 20) : 0
                readonly property string word: model.status === "ok" ? "Reachable" : model.status === "offline" ? "Server offline"
                                             : model.status === "variable" ? "Undefined variable" : "Not found"
                // the office-wide fact as fragments, so a narrow row wraps between them, not inside one
                readonly property var facts: (down
                    ? [model.sinceText !== "" ? model.sinceText : (model.statusLabel !== word ? model.statusLabel : ""),
                       model.jobsAffected > 0 ? panel.plural(model.jobsAffected, "job") : ""]
                    : [model.uses]).join(" · ").split(" · ").filter(function (s) { return s && s !== "" })
                readonly property real lineH: Math.max(20, act.visible ? act.height : pill.height)
                Rectangle { width: parent.width; height: 1; color: panel.tk.border; visible: index > 0 }
                // line 1 (root and mapping) shares its height with the pill and the action; line 2, the
                // office-wide fact, runs the full width under them
                Column {
                    id: lines
                    anchors.left: parent.left
                    anchors.right: parent.right
                    y: 10
                    spacing: 2
                    Flow {
                        id: first
                        width: pill.x - 10
                        spacing: 8
                        Txt {
                            id: nameText
                            text: model.rootName
                            strong: true
                            height: row.lineH
                            width: Math.min(implicitWidth, parent.width)
                        }
                        Txt {
                            visible: model.mapping !== ""
                            text: model.mapping
                            role: "small"
                            tone: "muted"
                            height: row.lineH
                            width: Math.min(implicitWidth, parent.width)
                        }
                    }
                    Txt {
                        objectName: "driveFacts"
                        // no-break spaces inside each fragment, so the line breaks only after a " · "
                        visible: row.facts.length > 0
                        width: parent.width
                        text: row.facts.map(function (f) { return f.replace(/ /g, "\u00a0") }).join("\u00a0· ")
                        role: "small"
                        tone: "faint"
                        figures: true
                        wrapMode: Text.WordWrap          // never inside a fact (no stray "·" line)
                        elide: Text.ElideNone
                    }
                }
                Tip { visible: rowHover.containsMouse && model.uses !== "" && row.down; text: model.uses }
                MouseArea { id: rowHover; anchors.fill: lines; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                StatusPill {
                    id: pill
                    anchors.right: act.visible ? act.left : parent.right
                    anchors.rightMargin: act.visible ? 8 : 0
                    y: lines.y + (row.lineH - height) / 2
                    status: model.status === "ok" ? "ok" : model.status === "offline" ? "bad" : "warn"
                    label: row.word
                }
                ActionButton {
                    id: act
                    width: 96
                    anchors.right: parent.right
                    y: lines.y + (row.lineH - height) / 2
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
            readonly property int hiddenDown: Math.max(0, panel.downCount - panel.maxRows)
            visible: panel.okCount > 0 || hiddenDown > 0
            width: list.width
            height: 34
            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                Icon { name: panel.expanded ? "caret-down" : "caret-right"; size: 12; anchors.verticalCenter: parent.verticalCenter }
                Txt {
                    text: [parent.parent.hiddenDown > 0 && !panel.expanded ? parent.parent.hiddenDown + " more down" : "",
                           panel.okCount > 0 ? panel.okCount + (panel.okCount === 1 ? " drive reachable" : " drives reachable") : ""]
                          .filter(function (s) { return s !== "" }).join(" · ")
                    tone: "muted"
                    figures: true
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: panel.expanded = !panel.expanded }
        }
    }
}
