import QtQuick

// Footlight 2: My tasks (brief 3.3), due soonest first.  A row: the done box, the title over "lot 7 check ·
// from Yokesh", the due text on the right (a warn pill when due today or overdue).  Rows capped at 4 so the
// three footlights share a bottom edge.  Data: app.tasks.mine (builder 1).
Card {
    id: panel
    property int maxRows: 4
    implicitHeight: 64 + Math.max(1, Math.min(rep.count, maxRows)) * 48 + 40

    Item {
        id: head
        x: panel.pad; y: panel.pad - 4
        width: panel.width - 2 * panel.pad
        height: 34
        SectionHeading {
            anchors.verticalCenter: parent.verticalCenter
            title: "My tasks"
            facts: app.tasks.mineOpenCount > 0 ? String(app.tasks.mineOpenCount) : ""
        }
        ActionButton {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "Tasks"
            icon: "arrow-right"
            kind: "ghost"
            small: true
            onClicked: app.ui.go("hub", { tab: "tasks" })
        }
    }
    Column {
        id: list
        x: panel.pad
        anchors.top: head.bottom
        anchors.topMargin: 6
        width: panel.width - 2 * panel.pad
        Repeater {
            id: rep
            model: app.tasks.mine
            delegate: TaskRow {
                width: list.width
                visible: index < panel.maxRows
                height: visible ? 48 : 0
                first: index === 0
                compact: true
            }
        }
        EmptyBlock {
            visible: rep.count === 0
            width: list.width
            line: "Nothing assigned to you."
            action: "New task"
            actionIcon: "plus"
            onTriggered: Window.window.openSheet("TaskSheet", {})
        }
        ActionButton {
            visible: rep.count > panel.maxRows
            text: (rep.count - panel.maxRows) + " more"
            kind: "link"
            small: true
            onClicked: app.ui.go("hub", { tab: "tasks" })
        }
    }
}
