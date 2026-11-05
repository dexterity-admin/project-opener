import QtQuick

// A switch.  Toggles are chrome, so they carry no colour (DESIGN.md): the on track is ink with the knob in
// the ground colour; off is the strong border colour.  `label` (optional) sits left of the track.
Item {
    id: sw
    readonly property var tk: app.ui.tokens
    property bool checked: false
    property string label: ""
    signal toggled(bool on)

    activeFocusOnTab: true
    implicitWidth: (label !== "" ? lbl.implicitWidth + 10 : 0) + 36
    implicitHeight: 34
    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.checked: checked

    function flip() { sw.toggled(!sw.checked) }

    Txt {
        id: lbl
        visible: sw.label !== ""
        text: sw.label
        tone: "muted"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        elide: Text.ElideNone
    }
    Rectangle {
        id: track
        width: 36
        height: 20
        radius: 10
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        color: sw.checked ? tk.text : tk.border_strong
        Behavior on color { ColorAnimation { duration: Math.round(150 * app.ui.k) } }
        Rectangle {
            width: 14
            height: 14
            radius: 7
            y: 3
            x: sw.checked ? parent.width - width - 3 : 3
            color: tk.bg
            Behavior on x { NumberAnimation { duration: Math.round(160 * app.ui.k); easing.type: Easing.OutCubic } }
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: height / 2
            color: "transparent"
            border.width: 2
            border.color: tk.accent
            visible: sw.activeFocus
        }
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: sw.flip()
    }
    Keys.onSpacePressed: sw.flip()
}
