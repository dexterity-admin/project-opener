import QtQuick
import QtQuick.Controls.Basic as C

// A text field that knows @mentions (brief 3.2): typing @ opens the picker under the caret, narrowing as you
// type (app.hub.mentionAt finds the mention being typed; setMentionQuery narrows the candidates); Up/Down move,
// Enter or a click inserts "@login " (app.hub.insertMention), Esc closes the picker.  Label above.
Column {
    id: f
    readonly property var tk: app.ui.tokens
    property string label: ""
    property alias text: area.text
    property alias placeholder: area.placeholderText
    property int boxHeight: 96
    property bool forceOpen: false            // screenshots: show the picker as if "@pr" were being typed
    spacing: 6
    width: 400

    function update() {
        var found = {}
        try { found = app.hub.mentionAt(area.text, area.cursorPosition) } catch (e) { found = {} }
        if (found && found.query !== undefined) {
            try { app.hub.setMentionQuery(found.query) } catch (e2) {}
            picker.current = 0
            picker.shown = true
        } else {
            picker.shown = f.forceOpen
        }
    }
    function insert(login) {
        var r = app.hub.insertMention(area.text, area.cursorPosition, login)
        area.text = r.text
        area.cursorPosition = r.cursor
        picker.shown = false
        area.forceActiveFocus()
    }
    Component.onCompleted: if (forceOpen) picker.shown = true

    Txt { visible: f.label !== ""; text: f.label; strong: true; width: f.width }
    Item {
        width: f.width
        height: f.boxHeight
        z: 10
        C.ScrollView {
            anchors.fill: parent
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
                onTextChanged: f.update()
                onCursorPositionChanged: f.update()
                Keys.priority: Keys.BeforeItem
                Keys.onPressed: (event) => {
                    if (!picker.shown) return
                    if (event.key === Qt.Key_Down) { picker.move(1); event.accepted = true }
                    else if (event.key === Qt.Key_Up) { picker.move(-1); event.accepted = true }
                    else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { if (picker.choose()) event.accepted = true }
                    else if (event.key === Qt.Key_Escape) { picker.shown = false; event.accepted = true }
                }
            }
        }
        MentionPicker {
            id: picker
            x: Math.min(Math.max(0, area.cursorRectangle.x), f.width - width)
            y: area.cursorRectangle.y + area.cursorRectangle.height + 12
            onChosen: (login) => f.insert(login)
        }
    }
}
