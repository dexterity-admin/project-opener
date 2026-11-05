import QtQuick
import "../components"

// Paths arrived from Explorer ("Add to running activity", Send to) with no activity running: add them to an
// activity, or start a new one from the selection.  One choice: each row carries a radio, the chosen row sits
// in accent_soft, and the running activity (else the most recently opened) is chosen when the sheet opens.
Sheet {
    id: s
    property var paths: []
    property string chosen: ""
    title: paths.length === 1 ? "Add 1 item to an activity" : "Add " + paths.length + " items to an activity"
    subtitle: "No activity is running"
    confirmText: chosen === "__new" ? "Start activity" : "Add items"
    confirmEnabled: chosen !== "" && (chosen !== "__new" || newName.text.trim() !== "")
    sheetWidth: 600

    // the running activity, else the one opened last, else the first
    function defaultChoice() {
        var m = app.activities.activities, best = "", bestWhen = ""
        for (var i = 0; i < m.count(); i++) {
            var r = m.get(i)
            if (r.running) return r.activityId
            var when = String(r.lastOpened || "")
            if (best === "" || when > bestWhen) { best = r.activityId; bestWhen = when }
        }
        return best
    }
    Component.onCompleted: {
        if (chosen === "") chosen = defaultChoice()
        if (chosen === "") { chosen = "__new"; newName.focusInput() }
    }

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

    component Radio: Rectangle {
        property bool on: false
        width: 18; height: 18; radius: 9
        color: "transparent"
        border.width: on ? 5 : 1.5
        border.color: on ? s.tk.text : s.tk.border_strong
    }

    Column {
        id: pathsCol
        width: parent.width
        spacing: 2
        Repeater {
            model: s.paths
            delegate: Row {
                required property var modelData
                spacing: 8
                Icon { name: "file"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                Txt { text: parent.modelData; width: pathsCol.width - 22; tone: "muted"; elide: Text.ElideMiddle }
            }
        }
    }
    Column {
        width: parent.width
        Repeater {
            model: app.activities.activities
            delegate: Rectangle {
                readonly property bool on: s.chosen === model.activityId
                width: parent ? parent.width : 500
                height: 46
                radius: 10
                color: on ? s.tk.accent_soft : am.containsMouse ? s.tk.surface_2 : "transparent"
                Radio { id: rb; x: 12; anchors.verticalCenter: parent.verticalCenter; on: parent.on }
                IconTile { id: t; anchors.left: rb.right; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; icon: model.icon; tint: model.dotColor; size: 26 }
                Txt { anchors.left: t.right; anchors.leftMargin: 10; anchors.right: when.left; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: model.title; strong: parent.on }
                Txt { id: when; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: model.running ? "Running" : (model.lastOpened ? model.lastOpenedText : ""); role: "small"; tone: "faint"; figures: true; elide: Text.ElideNone }
                MouseArea { id: am; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: s.chosen = model.activityId }
                Accessible.role: Accessible.RadioButton
                Accessible.name: model.title
                Accessible.checked: on
            }
        }
        Rectangle {
            readonly property bool on: s.chosen === "__new"
            width: parent.width
            height: 46
            radius: 10
            color: on ? s.tk.accent_soft : nm.containsMouse ? s.tk.surface_2 : "transparent"
            Radio { id: nr; x: 12; anchors.verticalCenter: parent.verticalCenter; on: parent.on }
            Icon { id: ni; anchors.left: nr.right; anchors.leftMargin: 17; anchors.verticalCenter: parent.verticalCenter; name: "plus" }
            Txt { anchors.left: ni.right; anchors.leftMargin: 15; anchors.verticalCenter: parent.verticalCenter; text: "A new activity from these"; strong: parent.on }
            MouseArea { id: nm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { s.chosen = "__new"; newName.focusInput() } }
            Accessible.role: Accessible.RadioButton
            Accessible.name: "A new activity from these"
            Accessible.checked: on
        }
    }
    Field { id: newName; visible: s.chosen === "__new"; width: (parent.width - 16) / 2; label: "Name"; placeholder: "Lot 8 check" }
}
