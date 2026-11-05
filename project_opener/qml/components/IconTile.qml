import QtQuick

// A project's or activity's icon on a pale tint of its own colour (identity, not chrome).
Rectangle {
    id: tile
    readonly property var tk: app.ui.tokens
    property string icon: "stack"
    property string tint: ""
    property int size: 32
    width: size
    height: size
    radius: size >= 32 ? 10 : 8
    readonly property color base: tint !== "" ? tint : tk.text_faint
    color: Qt.tint(tk.surface, Qt.rgba(base.r, base.g, base.b, tk.dark ? 0.22 : 0.14))
    border.width: 1
    border.color: Qt.tint(tk.surface, Qt.rgba(base.r, base.g, base.b, tk.dark ? 0.32 : 0.24))
    Icon {
        anchors.centerIn: parent
        name: tile.icon
        size: Math.round(tile.size * 0.5)
        color: Qt.tint(tile.tk.text, Qt.rgba(tile.base.r, tile.base.g, tile.base.b, 0.55))
    }
}
