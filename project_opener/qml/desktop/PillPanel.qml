import QtQuick
import "../components"

// The pill's panel (board "snapshot-surfaces" C).  Owner: builder 3.
// Title; "12 open · 9 identified · last checkpoint 10:52, 2 new since"; the watcher's list worst
// first (app.capture.live is sorted that way); one filled button (Snapshot now), Add a window,
// Review; pause and open in Project Opener in the header.  Actions go through pill.act(...).
Rectangle {
    id: panel
    readonly property var tk: app.ui.tokens
    readonly property var cap: app.capture
    readonly property int shownRows: 4
    readonly property bool paused: cap.state === "paused"
    readonly property var keys: (app.desktop && app.desktop.hotkeyStatus) ? app.desktop.hotkeyStatus : ({})

    function keyText(name) {
        const s = keys[name]
        return (s && s.ok) ? s.keys : ""
    }
    function statusOf(st) {
        if (st === "identified") return "ok"
        if (st === "offline") return "bad"
        if (st === "ambiguous" || st === "unidentified" || st === "unsaved") return "warn"
        return "neutral"
    }
    function wordsOf(st) {
        return ({ identified: "Identified", offline: "Server offline", ambiguous: "Ambiguous",
                  unidentified: "Needs a path", unsaved: "Unsaved", window: "Not a file" })[st] || st
    }

    implicitWidth: Math.max(400, buttons.implicitWidth + 32)
    implicitHeight: content.implicitHeight + 30
    radius: 18
    color: tk.surface
    border.width: 1
    border.color: tk.border_strong

    Column {
        id: content
        x: 16; y: 16
        width: parent.width - 32
        spacing: 0

        // ----------------------------------------------------- header
        Item {
            width: parent.width; height: 28
            Rectangle {
                id: hdot
                width: 10; height: 10; radius: 5
                anchors.verticalCenter: parent.verticalCenter
                color: panel.paused ? "transparent" : (cap.runningColor !== "" ? cap.runningColor : tk.accent)
                border.width: panel.paused ? 2 : 0
                border.color: cap.runningColor !== "" ? cap.runningColor : tk.accent
            }
            Text {
                anchors.left: hdot.right; anchors.leftMargin: 10
                anchors.right: tools.left; anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: cap.runningName || cap.runningLabel
                elide: Text.ElideRight
                font.family: "Onest"; font.pixelSize: 15; font.weight: Font.DemiBold
                color: tk.text
            }
            Row {
                id: tools
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6
                IconButton {       // pause / resume capture
                    tip: panel.paused ? "Resume capture" : "Pause capture"
                    onActivated: pill.act(panel.paused ? "resume" : "pause")
                    Row {
                        anchors.centerIn: parent
                        spacing: 3
                        visible: !panel.paused
                        Rectangle { width: 3; height: 11; radius: 1; color: tk.text_muted }
                        Rectangle { width: 3; height: 11; radius: 1; color: tk.text_muted }
                    }
                    Canvas {
                        anchors.centerIn: parent
                        width: 11; height: 12
                        visible: panel.paused
                        onPaint: {
                            const c = getContext("2d"); c.reset()
                            c.fillStyle = tk.text_muted
                            c.beginPath(); c.moveTo(1, 0); c.lineTo(11, 6); c.lineTo(1, 12); c.closePath(); c.fill()
                        }
                    }
                }
                IconButton {       // open in Project Opener
                    tip: "Open in Project Opener"
                    onActivated: pill.act("open")
                    Canvas {
                        anchors.centerIn: parent
                        width: 12; height: 12
                        onPaint: {
                            const c = getContext("2d"); c.reset()
                            c.strokeStyle = tk.text_muted; c.lineWidth = 1.6; c.lineCap = "round"
                            c.beginPath(); c.moveTo(2, 10); c.lineTo(10, 2); c.moveTo(4, 2); c.lineTo(10, 2); c.lineTo(10, 8)
                            c.stroke()
                        }
                    }
                }
            }
        }

        Text {
            width: parent.width - 20
            x: 20
            topPadding: 6; bottomPadding: 12
            text: pill.meta
            wrapMode: Text.WordWrap
            font.family: "Onest"; font.pixelSize: 13
            font.features: ({ "tnum": 1 })
            color: tk.text_muted
        }

        Rectangle { width: parent.width; height: 1; color: tk.border }

        // ------------------------------------------------- live list
        Column {
            width: parent.width
            topPadding: 10
            spacing: 6
            Repeater {
                id: rows
                model: cap.live
                delegate: Item {
                    required property int index
                    required property string appName
                    required property string name
                    required property string status
                    visible: index < panel.shownRows
                    width: parent ? parent.width : 0
                    height: visible ? 22 : 0
                    Text {
                        id: app_
                        width: 74
                        anchors.verticalCenter: parent.verticalCenter
                        text: appName
                        elide: Text.ElideRight
                        font.family: "Onest"; font.pixelSize: 13
                        color: tk.text_faint
                    }
                    Text {
                        anchors.left: app_.right; anchors.leftMargin: 10
                        anchors.right: sp.left; anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        text: name
                        elide: Text.ElideMiddle
                        font.family: "Onest"; font.pixelSize: 13
                        color: tk.text
                    }
                    StatusPill {
                        id: sp
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        status: panel.statusOf(parent.status)
                        label: panel.wordsOf(parent.status)
                    }
                }
            }
            Text {
                visible: rows.count === 0
                text: "Nothing open yet. The watcher looks every few seconds."
                font.family: "Onest"; font.pixelSize: 13
                color: tk.text_faint
            }
            Text {
                visible: rows.count > panel.shownRows
                leftPadding: 84
                text: "+" + (rows.count - panel.shownRows) + " more"
                font.family: "Onest"; font.pixelSize: 13
                font.features: ({ "tnum": 1 })
                color: tk.text_faint
            }
        }

        // "Save 2 new as items": the set grows by itself (brief 3.8).
        Item {
            visible: cap.newCount > 0
            width: parent.width
            height: visible ? 30 : 0
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: cap.newCount + " new, not yet in the activity"
                font.family: "Onest"; font.pixelSize: 13
                color: tk.text_muted
            }
            PanelButton {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                kind: "ghost"
                text: "Save " + cap.newCount + " new as items"
                onActivated: pill.act("save_new")
            }
        }

        Item { width: 1; height: 14 }

        Row {
            id: buttons
            spacing: 8
            PanelButton {
                kind: "primary"
                text: "Snapshot now"
                keys: panel.keyText("snapshot")
                onActivated: pill.act("snapshot")
            }
            PanelButton {
                text: "Add a window"
                onActivated: pill.act("add_window")
            }
            PanelButton {
                kind: "ghost"
                text: "Review"
                onActivated: pill.act("review")
            }
        }
    }

    component IconButton: Rectangle {
        id: ib
        property string tip: ""
        signal activated()
        width: 28; height: 28; radius: 14
        color: "transparent"
        border.width: 1
        border.color: ibMouse.containsMouse ? tk.border_strong : "transparent"
        MouseArea {
            id: ibMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: ib.activated()
        }
    }

    component PanelButton: Rectangle {
        id: pb
        property string text: ""
        property string keys: ""
        property string kind: "secondary"      // primary | secondary | ghost
        signal activated()
        height: 34
        width: label.implicitWidth + (kbd.visible ? kbd.width + 8 : 0) + 28
        radius: 17
        color: kind === "primary" ? tk.accent : (pbMouse.containsMouse && kind !== "primary" ? tk.surface_2 : "transparent")
        border.width: 1
        border.color: kind === "primary" ? tk.accent : kind === "ghost" ? "transparent" : tk.border_strong
        Row {
            anchors.centerIn: parent
            spacing: 8
            Text {
                id: label
                anchors.verticalCenter: parent.verticalCenter
                text: pb.text
                font.family: "Onest"; font.pixelSize: 13; font.weight: Font.Medium
                color: pb.kind === "primary" ? tk.accent_fg : pb.kind === "ghost" ? tk.text_muted : tk.text
            }
            Rectangle {
                id: kbd
                visible: pb.keys !== ""
                anchors.verticalCenter: parent.verticalCenter
                width: kbdText.implicitWidth + 10
                height: 18
                radius: 5
                color: "transparent"
                border.width: 1
                border.color: pb.kind === "primary" ? Qt.rgba(1, 1, 1, 0.45) : tk.border_strong
                Text {
                    id: kbdText
                    anchors.centerIn: parent
                    text: pb.keys
                    font.family: "Onest"; font.pixelSize: 11; font.weight: Font.Medium
                    color: pb.kind === "primary" ? Qt.rgba(1, 1, 1, 0.8) : tk.text_faint
                }
            }
        }
        MouseArea {
            id: pbMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: pb.activated()
        }
    }
}
