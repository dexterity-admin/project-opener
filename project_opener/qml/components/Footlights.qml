import QtQuick

// The footlights strip under the stage (concept-1-stage): Drives on this PC, My tasks, and Control room's
// Office panel.  The three share a bottom edge (the tallest sets the row); below 1000 px of width the drive
// map takes the full width and the other two share the row under it.  `dimmed` while the dock is open.
Item {
    id: strip
    property bool dimmed: false
    readonly property int downCount: drives.downCount
    readonly property bool stack: width < 1000
    readonly property int colW: stack ? Math.floor((width - 16) / 2) : Math.floor((width - 32) / 3)
    readonly property int rowH: Math.max(drives.implicitHeight, tasks.implicitHeight, office.implicitHeight)
    height: stack ? drives.implicitHeight + 16 + Math.max(tasks.implicitHeight, office.implicitHeight) : rowH
    opacity: dimmed ? 0.4 : 1
    Behavior on opacity { NumberAnimation { duration: Math.round(240 * app.ui.k) } }

    DrivesPanel {
        id: drives
        width: strip.stack ? strip.width : strip.colW
        height: strip.stack ? implicitHeight : strip.rowH
    }
    TasksPanel {
        id: tasks
        x: strip.stack ? 0 : strip.colW + 16
        y: strip.stack ? drives.height + 16 : 0
        width: strip.colW
        height: strip.stack ? Math.max(tasks.implicitHeight, office.implicitHeight) : strip.rowH
    }
    OfficePanel {
        id: office
        x: strip.stack ? strip.colW + 16 : 2 * (strip.colW + 16)
        y: tasks.y
        width: strip.colW
        height: tasks.height
    }
}
