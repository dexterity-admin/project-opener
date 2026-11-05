import QtQuick
import QtQuick.Controls.Basic as C

// A tooltip in the theme: ink on the raised surface, the floating shadow, 500 ms delay.
C.ToolTip {
    id: tip
    readonly property var tk: app.ui.tokens
    delay: 500
    padding: 8
    contentItem: Text {
        text: tip.text
        font.family: tip.tk.face
        font.pixelSize: 12
        color: tip.tk.text
        wrapMode: Text.Wrap
    }
    background: Rectangle {
        radius: 8
        color: tip.tk.surface_2
        border.width: 1
        border.color: tip.tk.border_strong
    }
}
