import QtQuick

// A colleague: initials on a stable pale tint of their hue, the online dot.  `hue` is either the hub's 0-359
// hue for the login (app.hub.peers: the same pale tint as the Office's desk tiles, DeskTile.qml) or a colour.
// `breathe()` plays the office's one ring (Control room's desks): it grows 8 -> 20 px beyond the avatar and
// fades over 2.4 s (rich) or 1.44 s (purposeful, 0.6x), once, when someone arrives; none in off.
Item {
    id: av
    readonly property var tk: app.ui.tokens
    property string initials: "?"
    property var hue: ""
    property bool online: false
    property int size: 28
    width: size
    height: size

    // the desk tint (tests/test_v4_round2_footlights.py checks text on it at 4.5:1 for every hue, both themes)
    readonly property bool numeric: typeof hue === "number"
    readonly property real tintS: tk.dark ? 0.22 : 0.65
    readonly property real tintL: tk.dark ? 0.20 : 0.93
    readonly property color base: numeric ? Qt.hsla(hue / 360, 0.55, tk.dark ? 0.6 : 0.42, 1)
                                          : hue !== "" ? hue : tk.text_faint
    readonly property color fill: numeric ? Qt.hsla(hue / 360, tintS, tintL, 1)
                                          : Qt.tint(tk.surface, Qt.rgba(base.r, base.g, base.b, tk.dark ? 0.32 : 0.22))

    // one ring on arrival: a transition, so it plays in rich and purposeful (scaled by k), never in off
    function breathe() {
        if (app.ui.k > 0 && Window.window && Window.window.active)
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
        NumberAnimation { target: halo; property: "width"; from: av.size + 8; to: av.size + 20; duration: Math.round(2400 * app.ui.k); easing.type: Easing.OutCubic }
        NumberAnimation { target: halo; property: "height"; from: av.size + 8; to: av.size + 20; duration: Math.round(2400 * app.ui.k); easing.type: Easing.OutCubic }
        NumberAnimation { target: halo; property: "opacity"; from: 0.7; to: 0; duration: Math.round(2400 * app.ui.k); easing.type: Easing.OutCubic }
    }
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: av.fill
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
