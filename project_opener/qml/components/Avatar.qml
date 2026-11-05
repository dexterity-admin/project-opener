import QtQuick

// A colleague: initials on a stable pale tint of their hue, the online dot.  `breathe()` plays the office's
// one ring (Control room's desks): it grows 8 -> 20 px beyond the avatar and fades over 2.4 s, once, when
// someone arrives.  Only in rich motion and while the window is active (ambient rule).
Item {
    id: av
    readonly property var tk: app.ui.tokens
    property string initials: "?"
    property string hue: ""
    property bool online: false
    property int size: 28
    width: size
    height: size

    readonly property color base: hue !== "" ? hue : tk.text_faint

    function breathe() {
        if (app.ui.ambient && Window.window && Window.window.active)
            ring.restart()
    }

    Rectangle {
        id: halo
        anchors.centerIn: parent
        width: av.size
        height: av.size
        radius: width / 2
        color: "transparent"
        border.width: 1.5
        border.color: av.base
        opacity: 0
    }
    ParallelAnimation {
        id: ring
        NumberAnimation { target: halo; property: "width"; from: av.size + 8; to: av.size + 20; duration: 2400; easing.type: Easing.OutCubic }
        NumberAnimation { target: halo; property: "height"; from: av.size + 8; to: av.size + 20; duration: 2400; easing.type: Easing.OutCubic }
        NumberAnimation { target: halo; property: "opacity"; from: 0.7; to: 0; duration: 2400; easing.type: Easing.OutCubic }
    }
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: Qt.tint(av.tk.surface, Qt.rgba(av.base.r, av.base.g, av.base.b, av.tk.dark ? 0.32 : 0.22))
        opacity: av.online ? 1 : 0.6
        Text {
            anchors.centerIn: parent
            text: av.initials
            font.family: av.tk.face
            font.pixelSize: Math.round(av.size * 0.42)
            font.weight: Font.DemiBold
            color: av.tk.text
        }
    }
    Rectangle {
        visible: av.online
        width: Math.max(8, Math.round(av.size * 0.3))
        height: width
        radius: width / 2
        color: av.tk.success
        border.width: 2
        border.color: av.tk.surface
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: -1
    }
}
