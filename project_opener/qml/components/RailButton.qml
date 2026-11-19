import QtQuick

// One rail slot: a 40 px round button with a Phosphor glyph; the current route is the raised pill.
// A count is an accent badge (queues that need action only); the label is the tooltip and the
// accessible name.
Item {
    id: rb
    readonly property var tk: app.ui.tokens
    property string glyph: ""
    property string label: ""
    property int count: 0
    property bool dot: false          // a quieter second queue (open tasks beside the inbox count)
    property string detail: ""        // what the badge and dot count, for the tooltip
    property bool active: false
    signal clicked()

    width: 40
    height: 40
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: label + (detail !== "" ? ", " + detail : count > 0 ? ", " + count : "")
    Accessible.onPressAction: rb.clicked()
    Keys.onReturnPressed: rb.clicked()
    Keys.onSpacePressed: rb.clicked()

    Rectangle {
        anchors.fill: parent
        radius: 20
        color: rb.active ? rb.tk.surface_2 : mouse.containsMouse ? rb.tk.surface : "transparent"
        border.width: rb.activeFocus ? 2 : 0
        border.color: rb.tk.accent
        Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k) } }
        Icon {
            anchors.centerIn: parent
            name: rb.glyph
            size: 18
            tone: rb.active ? "ink" : "muted"
        }
    }
    Rectangle {
        visible: rb.count > 0
        width: Math.max(16, badge.implicitWidth + 8)
        height: 16
        radius: 8
        color: rb.tk.accent
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: -2
        anchors.topMargin: -2
        Text {
            id: badge
            anchors.centerIn: parent
            text: rb.count > 99 ? "99+" : rb.count
            font.family: rb.tk.face
            font.pixelSize: 10
            font.weight: Font.DemiBold
            font.features: ({ "tnum": 1 })
            color: rb.tk.accent_fg
        }
    }
    Rectangle {                       // open tasks: a dot, bottom right, so it never reads as part of the count
        visible: rb.dot
        width: 8
        height: 8
        radius: 4
        color: rb.tk.accent
        border.width: 2
        border.color: rb.tk.bg
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 1
        anchors.bottomMargin: 1
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: rb.clicked()
    }
    Tip { visible: mouse.containsMouse; text: rb.label + (rb.detail !== "" ? " · " + rb.detail : "") }
}
