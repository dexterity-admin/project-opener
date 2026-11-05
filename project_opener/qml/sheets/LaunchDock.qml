import QtQuick
import "../components"

// The launch dock as a card of its own, for launches that start away from the stage (a project opened the
// 3.x way, an activity opened from the list or the palette).  On Home the dock is the centre scene grown
// (Scene.qml); everywhere else it is this card, shown while app.activities.dockOpen.  `forId` limits it to one
// activity or project ("" = any).
Card {
    id: card
    property string forId: ""
    readonly property bool shown: app.activities.dockOpen && (forId === "" || app.activities.dockId === forId)
    visible: shown
    height: shown ? dockView.implicitHeight + 2 * pad : 0
    DockView {
        id: dockView
        x: card.pad
        y: card.pad
        width: card.width - 2 * card.pad
        onCloseRequested: app.activities.closeDock()
        onShowActivity: {
            var id = app.activities.dockId
            app.activities.closeDock()
            if (app.activities.activities.indexOf(id) >= 0) app.ui.go("activity", { activityId: id })
            else app.ui.go("project", { projectId: id })
        }
    }
}
