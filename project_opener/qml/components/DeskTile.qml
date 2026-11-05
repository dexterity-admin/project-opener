import QtQuick

// One colleague's desk in the Office footlight (Control room's office panel, board A): a 44 px tile in their
// own stable pale hue (DESIGN.md "a stable pale tint of their hue"; the hub gives every login a 0-359 hue),
// the initials on a surface disc, the name, and what they are in ("doing") as the subline.  Someone not in
// sits on the neutral surface_2 tile, muted.  `breathe()` is the office's one ring on arrival: it grows 8 to
// 20 px beyond the tile and fades, 2.4 s in rich, 0.6x in purposeful, once; none in off.
// Text on the tint passes 4.5:1 for every hue in both themes (tests/test_v4_round2_footlights.py reads tintS
// and tintL from this file).
Item {
    id: desk
    objectName: "deskTile"
    readonly property bool ringing: ring.running
    readonly property int ringMs: ring.ms
    readonly property var tk: app.ui.tokens
    property string login: ""
    property string displayName: ""
    property string initials: "?"
    property var hue: 0
    property bool online: false
    property string doing: ""
    property string role: ""
    property string host: ""
    height: 44

    readonly property real tintS: tk.dark ? 0.22 : 0.65
    readonly property real tintL: tk.dark ? 0.20 : 0.93
    readonly property color tint: Qt.hsla((Number(hue) % 360) / 360, tintS, tintL, 1)
    readonly property color edge: Qt.hsla((Number(hue) % 360) / 360, 0.5, tk.dark ? 0.55 : 0.45, 1)
    readonly property string subline: doing !== "" ? doing : role

    function breathe() {
        if (app.ui.k > 0 && Window.window && Window.window.active)
            ring.restart()
    }

    Rectangle {
        id: halo
        anchors.centerIn: parent
        width: desk.width
        height: desk.height
        radius: 10
        color: "transparent"
        border.width: 1.5
        border.color: desk.edge
        opacity: 0
    }
    ParallelAnimation {
        id: ring
        readonly property int ms: Math.round(2400 * app.ui.k)
        NumberAnimation { target: halo; property: "width"; from: desk.width + 8; to: desk.width + 20; duration: ring.ms; easing.type: Easing.OutCubic }
        NumberAnimation { target: halo; property: "height"; from: desk.height + 8; to: desk.height + 20; duration: ring.ms; easing.type: Easing.OutCubic }
        NumberAnimation { target: halo; property: "opacity"; from: 0.7; to: 0; duration: ring.ms; easing.type: Easing.OutCubic }
    }

    Rectangle {
        id: tile
        anchors.fill: parent
        radius: 10
        color: desk.online ? desk.tint : desk.tk.surface_2

        Rectangle {
            id: disc
            x: 8
            anchors.verticalCenter: parent.verticalCenter
            width: 28
            height: 28
            radius: 14
            color: desk.tk.surface
            Text {
                anchors.centerIn: parent
                text: desk.initials
                font.family: desk.tk.face
                font.pixelSize: 12
                font.weight: Font.DemiBold
                color: desk.online ? desk.tk.text : desk.tk.text_muted
            }
        }
        Rectangle {
            visible: desk.online
            width: 9
            height: 9
            radius: 4.5
            color: desk.tk.success
            border.width: 2
            border.color: desk.tint
            x: disc.x + disc.width - 8
            y: disc.y + disc.height - 8
        }
        Column {
            anchors.left: disc.right
            anchors.leftMargin: 10
            anchors.right: parent.right
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            Txt {
                width: parent.width
                text: desk.displayName
                strong: true
                tone: desk.online ? "ink" : "muted"
            }
            Txt {
                visible: desk.subline !== ""
                width: parent.width
                text: desk.subline
                role: "small"
                tone: "muted"
            }
        }
    }
    Tip {
        visible: hov.containsMouse
        text: [desk.displayName, desk.login, desk.host, desk.role, desk.online ? "in" : "not in"]
              .filter(function (s) { return s && s !== "" }).join(" · ")
    }
    MouseArea { id: hov; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
}
