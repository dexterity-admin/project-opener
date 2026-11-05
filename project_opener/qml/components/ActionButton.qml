import QtQuick

// A pill button.  kind: primary (the one filled control on a screen) | outline | ghost | danger (outlined in
// the negative colour) | link (text only).  Hover steps the fill, press sinks 1 px and scales .985 (90 ms).
// A disabled button keeps its tooltip, which says why.
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
        color: btn.primary ? (btn.hovered ? tk.accent_hover : tk.accent)
             : btn.kind === "link" ? "transparent"
             : btn.hovered ? tk.surface_2 : (btn.kind === "ghost" ? "transparent" : tk.surface)
        border.width: btn.primary || btn.kind === "ghost" || btn.kind === "link" ? 0 : 1
        border.color: btn.kind === "danger" ? tk.danger : (btn.hovered ? tk.text_faint : tk.border_strong)
        Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k); easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: Math.round(90 * app.ui.k) } }
        Behavior on y { NumberAnimation { duration: Math.round(90 * app.ui.k) } }

        Row {
            id: row
            anchors.centerIn: parent
            spacing: 6
            Icon {
                visible: btn.icon !== ""
                name: btn.icon
                size: btn.small ? 14 : 16
                tone: btn.primary ? "onAccent" : btn.kind === "danger" ? "bad" : (btn.text === "" ? "muted" : "ink")
                anchors.verticalCenter: parent.verticalCenter
            }
            Txt {
                visible: btn.text !== ""
                text: btn.text
                role: btn.small ? "small" : "body"
                strong: true
                tone: btn.primary ? "onAccent" : btn.kind === "danger" ? "bad" : "ink"
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

    Tip {
        visible: btn.tooltip !== "" && mouse.containsMouse
        text: btn.tooltip
    }
}
