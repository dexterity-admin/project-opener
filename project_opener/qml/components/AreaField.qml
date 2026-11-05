import QtQuick
import QtQuick.Controls.Basic as C

// A multi-line field with its label above (notes, descriptions).  For text that may mention people, use
// MentionField instead.
Column {
    id: f
    readonly property var tk: app.ui.tokens
    property string label: ""
    property alias text: area.text
    property alias placeholder: area.placeholderText
    property int boxHeight: 84
    spacing: 6
    width: 280

    Txt { visible: f.label !== ""; text: f.label; strong: true; width: f.width }
    C.ScrollView {
        width: f.width
        height: f.boxHeight
        C.TextArea {
            id: area
            wrapMode: TextEdit.Wrap
            font.family: f.tk.face
            font.pixelSize: 13
            color: f.tk.text
            placeholderTextColor: f.tk.text_faint
            selectionColor: f.tk.accent_soft
            selectedTextColor: f.tk.text
            selectByMouse: true
            padding: 10
            Accessible.name: f.label
            background: Rectangle {
                radius: 10
                color: f.tk.surface
                border.width: area.activeFocus ? 2 : 1
                border.color: area.activeFocus ? f.tk.accent : f.tk.border_strong
            }
        }
    }
}
