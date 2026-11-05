import QtQuick

// A tick list grouped under headings: the "Save N new as items" and Resume sheets (owner decisions of
// 5 November 2026).  Rows come from a DictListModel with entryKey, ticked, tickable, name, path, appName,
// status, note, kind, group, groupLabel and optionally action and monitor.  A row that cannot be added or
// reopened shows an empty, dimmed box and says why; nothing is ticked that the evidence does not support.
Column {
    id: list
    readonly property var tk: app.ui.tokens
    property var model
    readonly property int count: rep.count
    signal toggled(string entryKey, bool ticked)

    function statusOf(st) {
        if (st === "identified") return "ok"
        if (st === "offline") return "bad"
        if (st === "ambiguous" || st === "unidentified") return "warn"
        return "neutral"
    }
    function wordsOf(st) {
        return ({ identified: "Identified", offline: "Server offline", ambiguous: "Ambiguous",
                  unidentified: "Needs a path", unsaved: "Unsaved", window: "Not a file" })[st] || st
    }
    function glyphOf(kind, status) {
        if (kind === "folder") return "folder"
        if (kind === "url") return "link"
        if (kind === "app") return "app-window"
        return status === "identified" || status === "offline" ? "file" : "app-window"
    }

    width: parent ? parent.width : 560

    Repeater {
        id: rep
        model: list.model
        delegate: Column {
            id: row
            required property int index
            required property var model
            readonly property bool first: index === 0 || list.model.get(index - 1).group !== model.group
            width: list.width

            Item {                                    // the group's heading
                visible: row.first
                width: parent.width
                height: visible ? (row.index === 0 ? 26 : 40) : 0
                Txt {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 6
                    text: row.model.groupLabel
                    role: "small"
                    tone: "muted"
                    strong: true
                    Accessible.role: Accessible.Heading
                }
            }

            Item {
                width: parent.width
                height: 52
                Rectangle { width: parent.width; height: 1; color: list.tk.border }
                Rectangle {
                    id: box
                    width: 18; height: 18; radius: 5
                    anchors.verticalCenter: parent.verticalCenter
                    color: row.model.ticked ? list.tk.text : "transparent"
                    border.width: row.model.ticked ? 0 : 1.5
                    border.color: list.tk.border_strong
                    opacity: row.model.tickable ? 1 : 0.45
                    Icon { anchors.centerIn: parent; visible: row.model.ticked; name: "check"; size: 12; color: list.tk.bg }
                    Accessible.role: Accessible.CheckBox
                    Accessible.name: row.model.name
                    Accessible.checked: row.model.ticked
                }
                Icon {
                    id: glyph
                    anchors.left: box.right; anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    name: list.glyphOf(row.model.kind, row.model.status)
                    tone: row.model.tickable ? "ink" : "faint"
                }
                Column {
                    anchors.left: glyph.right; anchors.leftMargin: 10
                    anchors.right: right.left; anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1
                    Txt {
                        width: parent.width
                        text: row.model.status === "identified" || row.model.status === "offline"
                              || row.model.kind === "app" ? row.model.name : "A window titled ‘" + row.model.name + "’"
                        strong: row.model.ticked
                        tone: row.model.tickable ? "ink" : "muted"
                    }
                    Txt {
                        width: parent.width
                        role: "small"
                        tone: "muted"
                        elide: Text.ElideMiddle
                        text: {
                            var m = row.model
                            var detail = m.path !== "" ? m.path : (m.action !== undefined && m.action !== "" ? m.action : m.note)
                            return [m.appName, detail].filter(function (x) { return x && x !== "" }).join(" · ")
                        }
                    }
                }
                Row {
                    id: right
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    Txt {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: text !== ""
                        text: row.model.monitor !== undefined ? row.model.monitor : ""
                        role: "small"
                        tone: "muted"
                        figures: true
                    }
                    StatusPill {
                        anchors.verticalCenter: parent.verticalCenter
                        status: list.statusOf(row.model.status)
                        label: list.wordsOf(row.model.status)
                    }
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: row.model.tickable
                    cursorShape: row.model.tickable ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: list.toggled(row.model.entryKey, !row.model.ticked)
                }
            }
        }
    }
}
