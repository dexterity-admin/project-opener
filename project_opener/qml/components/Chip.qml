import QtQuick

// Two kinds: a tag on a card or row (pale neutral pill, 20 px, no border) and, with `interactive`, an
// outlined filter chip (only interactive filters are outlined; DESIGN.md).  `removable` adds an ×.
Rectangle {
    id: chip
    readonly property var tk: app.ui.tokens
    property string text: ""
    property bool interactive: false
    property bool checked: false
    property bool removable: false
    property string icon: ""
    signal clicked()
    signal removed()

    height: interactive ? 28 : 20
    radius: height / 2
    width: chipRow.implicitWidth + (interactive ? 22 : 14)
    color: checked ? tk.accent_soft : interactive ? (chipMouse.containsMouse ? tk.surface_2 : "transparent") : tk.surface_2
    border.width: interactive && !checked ? 1 : 0
    border.color: tk.border_strong
    Accessible.role: interactive ? Accessible.CheckBox : Accessible.StaticText
    Accessible.name: text
    Accessible.checked: checked

    Row {
        id: chipRow
        anchors.centerIn: parent
        spacing: 4
        Icon { visible: chip.icon !== ""; name: chip.icon; size: 12; anchors.verticalCenter: parent.verticalCenter }
        Txt {
            text: chip.text
            role: "small"
            strong: chip.checked
            tone: chip.interactive || chip.checked ? "ink" : "muted"
            elide: Text.ElideNone
            anchors.verticalCenter: parent.verticalCenter
        }
        Icon {
            visible: chip.removable
            name: "x"
            size: 12
            anchors.verticalCenter: parent.verticalCenter
            MouseArea { anchors.fill: parent; anchors.margins: -4; cursorShape: Qt.PointingHandCursor; onClicked: chip.removed() }
        }
    }
    MouseArea {
        id: chipMouse
        anchors.fill: parent
        enabled: chip.interactive
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: chip.clicked()
        z: -1
    }
}
