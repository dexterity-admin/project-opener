import QtQuick

// A surface one tone step above the ground: 1 px border, radius 16, no shadow (only floating things have one).
// `pad` follows the density token (20 comfortable / 14 compact).
Rectangle {
    readonly property var tk: app.ui.tokens
    readonly property int pad: tk.pad
    color: tk.surface
    border.width: 1
    border.color: tk.border
    radius: 16
}
