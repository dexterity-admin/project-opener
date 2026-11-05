import QtQuick

// One task (Home strip, the hub's Tasks tab, an activity page): the done box, title over its line, the owner
// (wide rows), the due text on the right.  Marking done goes through app.tasks.setDone (tells the creator).
// Reads the delegate's `model` (TASK_ROLES).
Item {
    id: row
    readonly property var tk: app.ui.tokens
    property bool first: false
    property bool compact: false
    readonly property bool done: model.done === true
    readonly property bool urgent: !done && (model.overdue === true || String(model.dueText).indexOf("today") >= 0
                                             || String(model.dueText).indexOf("Overdue") === 0)
    height: 48

    Rectangle { width: parent.width; height: 1; color: row.tk.border; visible: !row.first }
    Rectangle {
        id: box
        width: 16; height: 16; radius: 4
        anchors.verticalCenter: parent.verticalCenter
        color: row.done ? row.tk.text : "transparent"
        border.width: row.done ? 0 : 1.5
        border.color: row.tk.border_strong
        Icon { anchors.centerIn: parent; visible: row.done; name: "check"; size: 12; color: row.tk.bg }
        MouseArea {
            anchors.fill: parent
            anchors.margins: -6
            cursorShape: Qt.PointingHandCursor
            onClicked: { try { app.tasks.setDone(model.taskId, !row.done) } catch (e) { Window.window.toast("Not available yet", "Tasks arrive with the Team Hub update.", "info") } }
        }
        Accessible.role: Accessible.CheckBox
        Accessible.name: "Done: " + model.title
        Accessible.checked: row.done
    }
    Column {
        anchors.left: box.right
        anchors.leftMargin: 12
        anchors.right: owner.visible ? owner.left : due.left
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 1
        Txt {
            width: parent.width
            text: model.title
            strong: !row.done
            tone: row.done ? "faint" : "ink"
            font.strikeout: row.done
        }
        Txt {
            width: parent.width
            text: row.done ? "done " + model.doneAt + " by " + model.doneBy
                 : [model.attachTitle, model.createdByName !== "" ? "from " + model.createdByName : ""]
                   .filter(function (s) { return s && s !== "" }).join(" · ")
            role: "small"
            tone: "faint"
        }
    }
    Row {
        id: owner
        visible: !row.compact
        width: 140
        anchors.right: due.left
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8
        Avatar { size: 22; initials: String(model.ownerName).charAt(0); online: false; anchors.verticalCenter: parent.verticalCenter }
        Txt { text: model.ownerName; tone: "muted"; width: 110; anchors.verticalCenter: parent.verticalCenter }
    }
    Item {
        id: due
        width: row.compact ? 96 : 110
        height: 20
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        StatusPill {
            anchors.right: parent.right
            visible: row.urgent
            status: "warn"
            label: row.urgent ? model.dueText : ""
        }
        Txt {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            visible: !row.urgent
            text: row.done ? "done" : model.dueText
            tone: "muted"
            figures: true
        }
    }
}
