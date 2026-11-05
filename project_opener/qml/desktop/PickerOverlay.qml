import QtQuick
import QtQuick.Window

// Window picker overlay, one per monitor: dims slightly, frames the window under the pointer green/amber with the label; click adds, Esc cancels.
// Owner: builder 3.  Placeholder from the architecture skeleton; created by Python, never by Main.qml.
Window {
    id: pickerOverlay
    readonly property var tk: app.ui.tokens
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    visible: false
    color: "transparent"
}
