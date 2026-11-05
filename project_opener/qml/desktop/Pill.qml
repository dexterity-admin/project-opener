import QtQuick
import QtQuick.Window

// The pill (brief 3.8, board "snapshot-surfaces" B and C).  Owner: builder 3.
// Created by desktop/pill.py (PillController) with the context properties `app` (the facade) and
// `pill` (the controller).  The window is only as big as what it shows: the capsule or the 6 px
// edge tab at rest, the panel's rectangle while the panel is open.  Python adds WS_EX_NOACTIVATE.
// States: running (colour dot) / needs (amber or red ring) / paused (hollow dot) / saved (2 s) /
// start (pinned, nothing running).  Motion: rich grows the panel from the pill in 180 ms,
// purposeful fades, off appears.
Window {
    id: win
    readonly property var tk: app.ui.tokens
    readonly property var v: pill.view
    readonly property string motion: app.ui.motion
    readonly property bool edgeStyle: v.edge === true
    readonly property color dotColor: v.dot === "muted" ? tk.text_faint : (v.color !== "" ? v.color : tk.accent)

    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: false
    color: "transparent"
    title: "Project Opener pill"

    // Hover anywhere in the window (capsule or panel): 500 ms opens, leaving closes (pill.py timers).
    Item {
        anchors.fill: parent
        HoverHandler { onHoveredChanged: pill.hoverChanged(hovered) }
    }

    // ----------------------------------------------------------- capsule
    Rectangle {
        id: capsule
        visible: !win.edgeStyle && !pill.panelOpen && win.v.visible === true
        width: row.implicitWidth + 22
        height: 30
        radius: 15
        anchors.centerIn: parent
        color: win.tk.surface
        border.width: 1
        border.color: win.v.tone === "ok" ? win.tk.success : win.tk.border_strong
        onWidthChanged: pill.setContentSize(width, height)
        Component.onCompleted: pill.setContentSize(width, height)

        Row {
            id: row
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 10
            spacing: 8

            Item {      // the dot, with its ring when something needs the user
                width: 18; height: 18
                anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    anchors.centerIn: parent
                    width: 18; height: 18; radius: 9
                    visible: win.v.ring === "warn" || win.v.ring === "bad"
                    color: "transparent"
                    border.width: 2
                    border.color: win.v.ring === "bad" ? win.tk.danger : win.tk.warning
                }
                Rectangle {
                    anchors.centerIn: parent
                    width: 10; height: 10; radius: 5
                    color: win.v.dot === "hollow" ? "transparent" : win.dotColor
                    border.width: win.v.dot === "hollow" ? 2 : 0
                    border.color: win.dotColor
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: win.v.text || ""
                font.family: "Onest"; font.pixelSize: 13; font.weight: Font.Medium
                color: win.tk.text
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: text !== ""
                text: win.v.detail || ""
                font.family: "Onest"; font.pixelSize: 13; font.weight: Font.Medium
                font.features: ({ "tnum": 1 })
                color: win.v.tone === "ok" ? win.tk.success : win.tk.text_muted
            }
        }
    }

    // ------------------------------------------------------------ edge tab
    Rectangle {
        id: tab
        visible: win.edgeStyle && !pill.panelOpen && win.v.visible === true
        anchors.fill: parent
        radius: 3
        color: win.v.tone === "ok" ? win.tk.success
             : win.v.ring === "bad" ? win.tk.danger
             : win.v.ring === "warn" ? win.tk.warning
             : win.dotColor
        border.width: 1
        border.color: win.tk.border_strong
    }

    // Press, drag to any edge (snaps on release), or click.
    MouseArea {
        anchors.fill: parent
        enabled: !pill.panelOpen
        acceptedButtons: Qt.LeftButton
        cursorShape: Qt.PointingHandCursor
        property point pressGlobal
        property point pressWin
        property bool dragging: false
        onPressed: (mouse) => {
            pressGlobal = mapToGlobal(mouse.x, mouse.y)
            pressWin = Qt.point(win.x, win.y)
            dragging = false
        }
        onPositionChanged: (mouse) => {
            if (!pressed) return
            const g = mapToGlobal(mouse.x, mouse.y)
            const dx = g.x - pressGlobal.x, dy = g.y - pressGlobal.y
            if (!dragging && Math.abs(dx) + Math.abs(dy) < 5) return
            dragging = true
            pill.dragTo(pressWin.x + dx, pressWin.y + dy)
        }
        onReleased: {
            if (dragging) pill.dropped(win.x, win.y)
            else pill.clicked()
            dragging = false
        }
    }

    // --------------------------------------------------------------- panel
    PillPanel {
        id: panel
        anchors.fill: parent
        readonly property bool shown: pill.panelOpen
        visible: opacity > 0
        opacity: shown ? 1 : 0
        scale: (win.motion === "rich" && !shown) ? 0.6 : 1
        transformOrigin: pill.growFrom === "bottomright" ? Item.BottomRight
                       : pill.growFrom === "bottomleft" ? Item.BottomLeft
                       : pill.growFrom === "topright" ? Item.TopRight : Item.TopLeft
        Behavior on opacity {
            enabled: win.motion !== "off"
            NumberAnimation { duration: Math.round(180 * app.ui.k); easing.type: Easing.OutCubic }
        }
        Behavior on scale {
            enabled: win.motion === "rich"
            NumberAnimation { duration: Math.round(180 * app.ui.k); easing.type: Easing.OutCubic }
        }
        onImplicitHeightChanged: pill.setPanelSize(implicitWidth, implicitHeight)
        onImplicitWidthChanged: pill.setPanelSize(implicitWidth, implicitHeight)
        Component.onCompleted: pill.setPanelSize(implicitWidth, implicitHeight)
    }
}
