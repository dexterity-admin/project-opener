import QtQuick

// A pill button.  kind: primary (the one filled control on a screen) | outline | ghost | danger (outlined in
// the negative colour) | link (text only).  Hover steps the fill, press sinks 1 px and scales .985 (90 ms).
// A disabled button keeps its tooltip, which says why.  `shine` (Today's Resume only, DESIGN.md "Motion"): a soft
// highlight sweeps across the amber face every 4.5 s, in rich motion while the window is active.
Item {
    id: btn
    readonly property var tk: app.ui.tokens
    property string text: ""
    property string icon: ""
    property string kind: "outline"
    property bool small: false
    property string tooltip: ""
    property bool busy: false
    property bool available: true          // false = shown disabled but still hoverable, so the tooltip says why
    property bool shine: false
    property real shineT: 0
    readonly property bool ambient: shine && Window.window !== null && Window.window.ambientOn === true
    signal clicked()

    activeFocusOnTab: enabled && visible
    implicitHeight: small ? 28 : 34
    implicitWidth: Math.max(implicitHeight, row.implicitWidth + (text === "" ? 0 : (small ? 22 : 30)))
    width: implicitWidth
    height: implicitHeight
    opacity: enabled && available ? 1 : 0.45
    Accessible.role: Accessible.Button
    Accessible.name: text !== "" ? text : tooltip
    Accessible.onPressAction: if (btn.available) btn.clicked()

    readonly property bool primary: kind === "primary"
    readonly property bool hovered: mouse.containsMouse && enabled && available

    Rectangle {
        id: face
        anchors.fill: parent
        radius: height / 2
        y: mouse.pressed ? 1 : 0
        scale: mouse.pressed ? 0.985 : 1
        color: btn.primary ? (btn.hovered ? tk.action_hover : tk.action)
             : btn.kind === "link" ? "transparent"
             : btn.hovered ? tk.surface_2 : (btn.kind === "ghost" ? "transparent" : tk.surface)
        border.width: btn.primary || btn.kind === "ghost" || btn.kind === "link" ? 0 : 1
        border.color: btn.kind === "danger" ? tk.danger : (btn.hovered ? tk.text_faint : tk.border_strong)
        Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k); easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: Math.round(90 * app.ui.k) } }
        Behavior on y { NumberAnimation { duration: Math.round(90 * app.ui.k) } }

        // the sweep is strongest mid-face and fades to nothing at the round ends, so the square clip never shows
        Item {
            anchors.fill: parent
            visible: btn.shine && btn.primary && btn.shineT > 0
            clip: true
            Rectangle {
                width: parent.width * 0.4
                height: parent.height
                x: -width + btn.shineT * (parent.width + width)
                opacity: Math.sin(Math.PI * btn.shineT) * 0.8
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "#00FFFFFF" }
                    GradientStop { position: 0.5; color: "#B3FFFFFF" }
                    GradientStop { position: 1; color: "#00FFFFFF" }
                }
            }
        }

        Row {
            id: row
            anchors.centerIn: parent
            spacing: 6
            Icon {
                visible: btn.icon !== ""
                name: btn.icon
                size: btn.small ? 14 : 16
                tone: btn.primary ? "onAction" : btn.kind === "danger" ? "bad" : (btn.text === "" ? "muted" : "ink")
                anchors.verticalCenter: parent.verticalCenter
            }
            Txt {
                visible: btn.text !== ""
                text: btn.text
                role: btn.small ? "small" : "body"
                strong: true
                tone: btn.primary ? "onAction" : btn.kind === "danger" ? "bad" : "ink"
                anchors.verticalCenter: parent.verticalCenter
                elide: Text.ElideNone
            }
        }
    }
    // focus ring: the accent, 2 px outside the face
    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: height / 2
        color: "transparent"
        border.width: 2
        border.color: tk.accent
        visible: btn.activeFocus
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: btn.available ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (btn.available) btn.clicked()
    }
    Keys.onSpacePressed: if (btn.available) btn.clicked()
    Keys.onReturnPressed: if (btn.available) btn.clicked()
    Keys.onEnterPressed: if (btn.available) btn.clicked()

    SequentialAnimation on shineT {
        running: btn.shine && btn.primary && btn.visible && btn.ambient
        loops: Animation.Infinite
        PauseAnimation { duration: 3300 }
        NumberAnimation { from: 0; to: 1; duration: 1200; easing.type: Easing.Bezier; easing.bezierCurve: [0.2, 0.7, 0.2, 1, 1, 1] }
        onRunningChanged: if (!running) btn.shineT = 0
    }

    Tip {
        visible: btn.tooltip !== "" && mouse.containsMouse
        text: btn.tooltip
    }
}
