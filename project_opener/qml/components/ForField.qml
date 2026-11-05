import QtQuick
import QtQuick.Controls.Basic as C

// "For": the people and groups a publish, an announcement or a send is for (brief 3.2).  Chips for the
// targets, then an input that opens the same picker as @ (typing narrows it; Enter adds the highlighted one;
// Backspace on an empty input removes the last chip).  `targets` holds logins and group names, no "@".
Column {
    id: f
    readonly property var tk: app.ui.tokens
    property string label: "For"
    property var targets: []
    property string help: ""
    spacing: 6
    width: 400

    function add(login) {
        if (targets.indexOf(login) < 0) targets = targets.concat([login])
        input.text = ""
        picker.shown = false
        input.forceActiveFocus()
    }
    function removeAt(i) {
        var t = targets.slice()
        t.splice(i, 1)
        targets = t
    }
    function nameFor(login) {
        var m = app.hub.mentionCandidates
        for (var i = 0; i < m.count(); i++) { var r = m.get(i); if (r.login === login) return r.isGroup ? "@" + login : r.displayName }
        return login
    }

    Txt { text: f.label; strong: true; width: f.width }
    Item {
        width: f.width
        height: Math.max(34, flow.implicitHeight + 8)
        z: 10
        Rectangle {
            anchors.fill: parent
            radius: 10
            color: f.tk.surface
            border.width: input.activeFocus ? 2 : 1
            border.color: input.activeFocus ? f.tk.accent : f.tk.border_strong
        }
        Flow {
            id: flow
            x: 6; y: 4
            width: parent.width - 12
            spacing: 6
            Repeater {
                model: f.targets
                delegate: Chip {
                    required property var modelData
                    required property int index
                    y: 3
                    text: f.nameFor(modelData)
                    removable: true
                    onRemoved: f.removeAt(index)
                }
            }
            C.TextField {
                id: input
                width: Math.max(160, flow.width - 20 - (f.targets.length > 0 ? 0 : 0))
                height: 26
                padding: 4
                placeholderText: f.targets.length === 0 ? "add a person or a group…" : ""
                placeholderTextColor: f.tk.text_faint
                color: f.tk.text
                font.family: f.tk.face
                font.pixelSize: 13
                background: Item {}
                Accessible.name: f.label
                onTextEdited: {
                    try { app.hub.setMentionQuery(text.replace(/^@/, "")) } catch (e) {}
                    picker.current = 0
                    picker.shown = text.length > 0 || activeFocus
                }
                onActiveFocusChanged: if (!activeFocus) picker.shown = false
                Keys.onDownPressed: picker.move(1)
                Keys.onUpPressed: picker.move(-1)
                Keys.onReturnPressed: (event) => { if (picker.shown && picker.choose()) event.accepted = true; else event.accepted = false }
                Keys.onEscapePressed: (event) => { if (picker.shown) { picker.shown = false; event.accepted = true } else event.accepted = false }
                Keys.onPressed: (event) => { if (event.key === Qt.Key_Backspace && text === "" && f.targets.length > 0) { f.removeAt(f.targets.length - 1); event.accepted = true } }
            }
        }
        MentionPicker {
            id: picker
            y: parent.height + 6
            onChosen: (login) => f.add(login)
        }
    }
    Txt { visible: f.help !== ""; text: f.help; role: "small"; tone: "faint"; width: f.width; wrapMode: Text.Wrap; elide: Text.ElideNone }
}
