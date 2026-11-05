import QtQuick

// The 6 px identity dot in a project's or activity's own colour (colour is data, never chrome).
Rectangle {
    property string tint: ""
    readonly property var tk: app.ui.tokens
    width: 6
    height: 6
    radius: 3
    color: tint !== "" ? tint : tk.text_faint
}
