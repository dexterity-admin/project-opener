import QtQuick
import "../components"

// Paths arrived from Explorer ("Add to running activity", Send to) with no activity running: add them to an
// activity, or start a new one from the selection.
Sheet {
    id: s
    property var paths: []
    property string chosen: ""
    title: paths.length === 1 ? "Add 1 item to an activity" : "Add " + paths.length + " items to an activity"
    subtitle: "No activity is running"
    confirmText: chosen === "__new" ? "Start activity" : "Add items"
    confirmEnabled: chosen !== "" && (chosen !== "__new" || newName.text.trim() !== "")
    sheetWidth: 600

    onAccepted: {
        if (chosen === "__new") {
            var id = app.activities.create(newName.text, "")
            if (id) app.activities.addPaths(id, paths)
        } else {
            app.activities.addPaths(chosen, paths)
            app.ui.go("activity", { activityId: chosen })
        }
        s.close()
    }

    Column {
        width: parent.width
        spacing: 2
        Repeater {
            model: s.paths
            delegate: Row {
                required property var modelData
                spacing: 8
                Icon { name: "file"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                Txt { text: parent.modelData; width: s.width - 120; tone: "muted"; elide: Text.ElideMiddle }
            }
        }
    }
    Column {
        width: parent.width
        Repeater {
            model: app.activities.activities
            delegate: Rectangle {
                width: parent ? parent.width : 500
                height: 46
                radius: 10
                color: s.chosen === model.activityId ? s.tk.accent_soft : am.containsMouse ? s.tk.surface_2 : "transparent"
                IconTile { id: t; x: 8; anchors.verticalCenter: parent.verticalCenter; icon: model.icon; tint: model.dotColor; size: 26 }
                Txt { anchors.left: t.right; anchors.leftMargin: 10; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: model.title; strong: s.chosen === model.activityId }
                MouseArea { id: am; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: s.chosen = model.activityId }
                Accessible.role: Accessible.RadioButton
                Accessible.name: model.title
                Accessible.checked: s.chosen === model.activityId
            }
        }
        Rectangle {
            width: parent.width
            height: 46
            radius: 10
            color: s.chosen === "__new" ? s.tk.accent_soft : nm.containsMouse ? s.tk.surface_2 : "transparent"
            Icon { id: ni; x: 14; anchors.verticalCenter: parent.verticalCenter; name: "plus" }
            Txt { anchors.left: ni.right; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter; text: "A new activity from these"; strong: s.chosen === "__new" }
            MouseArea { id: nm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { s.chosen = "__new"; newName.focusInput() } }
        }
    }
    Field { id: newName; visible: s.chosen === "__new"; width: 320; label: "Name"; placeholder: "Lot 8 check" }
}
