import QtQuick

// The footlights strip under the stage (concept-1-stage): the newest announcement as one line, then Drives on
// this PC, My tasks, and the Office (Control room's desks).  Each panel is as tall as its content, at most four
// rows; the row takes the tallest and the panels are top-aligned at that one height, so the three bottom edges
// stay level and no panel stretches past its content by more than the difference (no panel-void).  Each
// panel's action sits in its heading.  Below 1000 px of width the drive map takes the full width and the other
// two share the row under it.  `dimmed` while the dock is open.
Item {
    id: strip
    property bool dimmed: false
    readonly property int downCount: drives.downCount
    readonly property bool stack: width < 1000
    readonly property int colW: stack ? Math.floor((width - 16) / 2) : Math.floor((width - 32) / 3)
    readonly property int newsH: news.visible ? news.implicitHeight + 16 : 0
    readonly property int pairH: Math.max(tasks.implicitHeight, office.implicitHeight)
    readonly property int rowH: Math.max(drives.implicitHeight, pairH)
    height: newsH + (stack ? drives.implicitHeight + 16 + pairH : rowH)
    opacity: dimmed ? 0.4 : 1
    Behavior on opacity { NumberAnimation { duration: Math.round(240 * app.ui.k) } }

    AnnouncementLine {
        id: news
        objectName: "footNews"
        width: strip.width
        height: implicitHeight
    }
    DrivesPanel {
        id: drives
        objectName: "footDrives"
        y: strip.newsH
        width: strip.stack ? strip.width : strip.colW
        height: strip.stack ? implicitHeight : strip.rowH
    }
    TasksPanel {
        id: tasks
        objectName: "footTasks"
        x: strip.stack ? 0 : strip.colW + 16
        y: strip.stack ? drives.y + drives.height + 16 : strip.newsH
        width: strip.colW
        height: strip.stack ? strip.pairH : strip.rowH
    }
    OfficePanel {
        id: office
        objectName: "footOffice"
        x: strip.stack ? strip.colW + 16 : 2 * (strip.colW + 16)
        y: tasks.y
        width: strip.colW
        height: tasks.height
    }
}
