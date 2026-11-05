import QtQuick
import "../components"

// A group (brief 3.2): a name for several people, @checkers or @P12513-team.  Anyone may edit; last writer
// wins; the record shows who.
Sheet {
    id: s
    property string name: ""
    property var members: []
    property string color: "#4F46A3"
    readonly property bool creating: name === ""
    title: creating ? "New group" : "Edit @" + name
    confirmText: creating ? "Create group" : "Save group"
    confirmEnabled: nameField.text.trim() !== "" && who.targets.length > 0
    sheetWidth: 560

    Component.onCompleted: { nameField.text = s.name; who.targets = s.members || []; nameField.focusInput() }
    onAccepted: {
        var n = nameField.text.trim().replace(/^@/, "").replace(/\s+/g, "-")
        var ok = Window.window.safe(function () { app.hub.saveGroup(n, who.targets, s.color) }, "Groups arrive with the Team Hub update.")
        if (ok) s.close()
    }

    Field { id: nameField; width: 300; label: "Name"; placeholder: "checkers"; help: "Mentioned as @name; spaces become dashes." }
    ForField { id: who; width: parent.width; label: "Members" }
    Column {
        spacing: 6
        Txt { text: "Colour"; strong: true }
        Row {
            spacing: 8
            Repeater {
                model: ["#4F46A3", "#2F5BFF", "#0F766E", "#B4452E", "#8A5A00", "#A3285B"]
                delegate: Rectangle {
                    required property var modelData
                    width: 26; height: 26; radius: 13
                    color: modelData
                    border.width: s.color.toUpperCase() === modelData ? 3 : 0
                    border.color: s.tk.text
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: s.color = parent.modelData }
                }
            }
        }
    }
}
