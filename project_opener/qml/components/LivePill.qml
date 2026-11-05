import QtQuick

// The desktop pill, brought into the main window (juror C3): the running activity's live capture state in the
// centre card's header.  Reads app.capture exactly as the pill does (brief 3.8): the colour dot; an amber ring
// and "3 need a path"; a red ring and "Server offline"; a hollow dot and "Paused" / "Capture off"; "Saved ·
// 12 things · 14:32" for two seconds after a checkpoint; else "12 open".  No sound, no badge, one ring colour.
Rectangle {
    id: lp
    readonly property var tk: app.ui.tokens
    readonly property var cap: app.capture
    property string savedText: ""
    readonly property string st: cap.captureState
    readonly property bool hollow: st === "paused" || st === "off"
    readonly property string ring: cap.driveDown ? "bad" : cap.needsPathCount > 0 ? "warn" : ""
    readonly property color dotColor: cap.runningColor !== "" ? cap.runningColor : tk.accent
    readonly property string words: savedText !== "" ? "Saved · " + savedText
                                    : st === "off" ? "Capture off"
                                    : st === "paused" ? "Paused"
                                    : cap.driveDown ? "Server offline"
                                    : cap.needsPathCount > 0 ? (cap.needsPathCount === 1 ? "1 needs a path" : cap.needsPathCount + " need a path")
                                    : cap.openCount + " open"

    implicitWidth: row.implicitWidth + 20
    implicitHeight: 26
    radius: 13
    color: tk.surface
    border.width: 1
    border.color: savedText !== "" ? tk.success : tk.border_strong
    Accessible.role: Accessible.StaticText
    Accessible.name: "Capture: " + words

    Connections {
        target: lp.cap
        function onCheckpointSaved(id, count, time) {
            lp.savedText = count + (count === 1 ? " thing · " : " things · ") + time
            flash.restart()
        }
    }
    Timer { id: flash; interval: 2000; onTriggered: lp.savedText = "" }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 7
        Item {
            width: 16; height: 16
            anchors.verticalCenter: parent.verticalCenter
            Rectangle {
                anchors.centerIn: parent
                width: 16; height: 16; radius: 8
                visible: lp.ring !== ""
                color: "transparent"
                border.width: 2
                border.color: lp.ring === "bad" ? lp.tk.danger : lp.tk.warning
            }
            Rectangle {
                anchors.centerIn: parent
                width: 8; height: 8; radius: 4
                color: lp.hollow ? "transparent" : lp.dotColor
                border.width: lp.hollow ? 2 : 0
                border.color: lp.dotColor
            }
        }
        Txt {
            anchors.verticalCenter: parent.verticalCenter
            text: lp.words
            strong: true
            figures: true
            tone: lp.savedText !== "" ? "ok" : "ink"
        }
    }
}
