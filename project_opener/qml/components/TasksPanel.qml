import QtQuick

// Footlight 2: My tasks (brief 3.3), due soonest first.  A row: the done box, the title over "lot 7 check ·
// from Yokesh", the due text on the right (a warn pill when due today or overdue).  Rows capped at 4 so the
// three footlights end level; the panel is as tall as its rows (no panel-void) and its action, Tasks, sits in
// the heading with the count of the rest ("3 · 2 more"), never at the foot.  Data: app.tasks.mine.
Card {
    id: panel
    property int maxRows: 4
    implicitHeight: list.y + list.implicitHeight + pad

    Item {
        id: head
        x: panel.pad; y: panel.pad - 4
        width: panel.width - 2 * panel.pad
        height: 34
        SectionHeading {
            anchors.verticalCenter: parent.verticalCenter
            title: "My tasks"
            facts: (app.tasks.mineOpenCount > 0 ? String(app.tasks.mineOpenCount) : "")
                 + (rep.count > panel.maxRows ? " · " + (rep.count - panel.maxRows) + " more" : "")
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
        y: head.y + head.height + 6
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
    }
}
