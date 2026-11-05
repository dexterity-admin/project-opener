import QtQuick
import QtQuick.Window

// The pill (brief 3.8): capsule docked to a screen edge; states running/needs/paused/saved/idle; edge-tab rest style. Python adds WS_EX_NOACTIVATE.
// Owner: builder 3.  Placeholder from the architecture skeleton; created by Python, never by Main.qml.
Window {
    id: pill
    readonly property var tk: app.ui.tokens
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: false
    color: "transparent"
}
