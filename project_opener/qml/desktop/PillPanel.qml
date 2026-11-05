import QtQuick
import "../components"

// The pill's panel (board "snapshot-surfaces" C).  Owner: builder 3.
// Title; "12 open · 9 identified · last checkpoint 10:52, 2 new since"; the watcher's list worst
// first (app.capture.live is sorted that way); one filled button (Snapshot now), Add a window,
// Review; pause and open in Project Opener in the header.  Actions go through pill.act(...).
// Each row offers Ignore on hover (owner decision, 5 November 2026): the window leaves this activity's list
// and counts; the note under the list then offers "Always ignore <app>" (Settings.capture_ignore) and Undo.
// The surface is the main window's (tk.surface, opaque, tk.border_strong edge); every text is a token pair
// tools/check_contrast.py checks (text, text_muted on surface and surface_2, accent_fg on accent, pills).
Rectangle {
    id: panel
    readonly property var tk: app.ui.tokens
    readonly property var cap: app.capture
    readonly property int shownRows: 4
    readonly property bool paused: cap.state === "paused"
    // the last Ignore, for its note: {key, name, app, always}; {} when there is none
    property var ignored: ({})
    function ignoreRow(key, name, appName) {
        pill.ignore(key, false)
        panel.ignored = { key: key, name: name, app: appName, always: false }
        noteTimer.restart()
    }
    function ignoreAlways() {
        const n = pill.ignore(panel.ignored.key, true)
        panel.ignored = { key: panel.ignored.key, name: panel.ignored.name, app: n || panel.ignored.app, always: true }
        noteTimer.restart()
    }
    function undoIgnore() {
        pill.unignore(panel.ignored.key, panel.ignored.always === true)
        panel.ignored = ({})
    }
    onVisibleChanged: if (!visible) panel.ignored = ({})
    Timer { id: noteTimer; interval: 10000; onTriggered: panel.ignored = ({}) }
    readonly property var keys: (app.desktop && app.desktop.hotkeyStatus) ? app.desktop.hotkeyStatus : ({})

    function keyText(name) {
        const s = keys[name]
        return (s && s.ok) ? s.keys : ""
    }
    function statusOf(st) {
        if (st === "identified") return "ok"
        if (st === "offline") return "bad"
        if (st === "ambiguous" || st === "unidentified") return "warn"
        return "neutral"
    }
    function wordsOf(st) {
        return ({ identified: "Identified", offline: "Server offline", ambiguous: "Ambiguous",
                  unidentified: "Needs a path", unsaved: "Not a file", window: "Not a file" })[st] || st
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
                    id: rowItem
                    required property int index
                    required property string entryKey
                    required property string appName
                    required property string name
                    required property string status
                    readonly property bool hot: rowHover.hovered
                    visible: index < panel.shownRows
                    width: parent ? parent.width : 0
                    height: visible ? 26 : 0
                    Rectangle {                      // the hovered row, on the main window's raised surface
                        anchors.fill: parent
                        anchors.leftMargin: -6; anchors.rightMargin: -6
                        radius: 6
                        color: tk.surface_2
                        visible: rowItem.hot
                    }
                    HoverHandler { id: rowHover }
                    Text {
                        id: app_
                        width: 74
                        anchors.verticalCenter: parent.verticalCenter
                        text: rowItem.appName
                        elide: Text.ElideRight
                        font.family: "Onest"; font.pixelSize: 13
                        color: tk.text_muted
                    }
                    Text {
                        anchors.left: app_.right; anchors.leftMargin: 10
                        anchors.right: rowItem.hot ? ign.left : sp.left; anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        text: rowItem.name
                        elide: Text.ElideMiddle
                        font.family: "Onest"; font.pixelSize: 13
                        color: tk.text
                    }
                    StatusPill {
                        id: sp
                        visible: !rowItem.hot
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        status: panel.statusOf(rowItem.status)
                        label: panel.wordsOf(rowItem.status)
                    }
                    PanelButton {
                        id: ign
                        visible: rowItem.hot
                        height: 24
                        text: "Ignore"
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        Accessible.name: "Ignore " + rowItem.name + " for this activity"
                        onActivated: panel.ignoreRow(rowItem.entryKey, rowItem.name, rowItem.appName)
                    }
                }
            }
            Text {
                visible: rows.count === 0
                text: "Nothing open yet. The watcher looks every few seconds."
                font.family: "Onest"; font.pixelSize: 13
                color: tk.text_muted
            }
            Text {
                visible: rows.count > panel.shownRows
                leftPadding: 84
                text: "+" + (rows.count - panel.shownRows) + " more"
                font.family: "Onest"; font.pixelSize: 13
                font.features: ({ "tnum": 1 })
                color: tk.text_muted
            }
            // The last Ignore: what happened, the stronger option, and Undo.
            Item {
                visible: panel.ignored.key !== undefined
                width: parent.width
                height: visible ? 30 : 0
                Text {
                    anchors.left: parent.left
                    anchors.right: noteActs.left; anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: panel.ignored.always === true ? "Ignoring every " + panel.ignored.app + " window"
                                                        : "Ignored here: " + (panel.ignored.name || "")
                    elide: Text.ElideMiddle
                    font.family: "Onest"; font.pixelSize: 13
                    color: tk.text_muted
                }
                Row {
                    id: noteActs
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    PanelButton {
                        visible: panel.ignored.always !== true && (panel.ignored.app || "") !== ""
                        height: 26
                        kind: "ghost"
                        text: "Always ignore " + (panel.ignored.app || "")
                        onActivated: panel.ignoreAlways()
                    }
                    PanelButton {
                        height: 26
                        kind: "ghost"
                        text: "Undo"
                        onActivated: panel.undoIgnore()
                    }
                }
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
                font.features: ({ "tnum": 1 })
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
                color: pb.kind === "primary" ? tk.accent_fg : tk.text
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
                border.color: pb.kind === "primary" ? tk.accent_fg : tk.border_strong
                Text {
                    id: kbdText
                    anchors.centerIn: parent
                    text: pb.keys
                    font.family: "Onest"; font.pixelSize: 11; font.weight: Font.Medium
                    color: pb.kind === "primary" ? tk.accent_fg : tk.text_muted
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
