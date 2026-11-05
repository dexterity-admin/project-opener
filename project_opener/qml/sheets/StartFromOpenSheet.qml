import QtQuick
import "../components"

// Start from what's open (brief 3.8): every window the watcher sees, each with its pill; non-file windows
// (chat, mail) unticked by default; a name and a job; "Start activity · 9 items".  Data:
// app.capture.startCandidates (builder 2, filled by prepareStartFromOpen).
Sheet {
    id: s
    property int ticked: 0
    title: "Start from what's open"
    subtitle: rep.count > 0 ? rep.count + " windows · tick what belongs to the activity" : ""
    confirmText: "Start activity · " + ticked + (ticked === 1 ? " item" : " items")
    confirmEnabled: nameField.text.trim() !== "" && ticked > 0
    sheetWidth: 640

    function recount() {
        var m = app.capture.startCandidates, n = 0
        for (var i = 0; i < m.count(); i++) if (m.get(i).ticked) n++
        ticked = n
    }
    Connections {
        target: app.capture
        function onStartCandidatesReady() { s.recount() }
    }
    Connections {
        target: app.capture.startCandidates
        function onDataChanged() { s.recount() }
        function onModelReset() { s.recount() }
    }
    Component.onCompleted: { recount(); nameField.focusInput() }
    onAccepted: {
        var ok = Window.window.safe(function () {
            var id = app.capture.startFromOpen(nameField.text, job.value)
            if (id) app.ui.go("activity", { activityId: id })
        }, "Starting from what's open arrives with the capture update.")
        if (ok) s.close()
    }

    Row {
        spacing: 16
        Field { id: nameField; width: 320; label: "Name"; placeholder: "Lot 8 check" }
        ChoiceField {
            id: job
            width: 260
            label: "Job"
            value: ""
            options: {
                var out = [{ value: "", text: "No project" }]
                var m = app.activities.projects
                for (var i = 0; i < m.count(); i++) out.push({ value: m.get(i).projectId, text: m.get(i).title })
                return out
            }
            onPicked: (v) => value = v
        }
    }
    Column {
        width: parent.width
        Repeater {
            id: rep
            model: app.capture.startCandidates
            delegate: Item {
                width: parent ? parent.width : 600
                height: 50
                Rectangle { width: parent.width; height: 1; color: s.tk.border; visible: index > 0 }
                Rectangle {
                    id: box
                    width: 16; height: 16; radius: 4
                    anchors.verticalCenter: parent.verticalCenter
                    color: model.ticked ? s.tk.text : "transparent"
                    border.width: model.ticked ? 0 : 1.5
                    border.color: s.tk.border_strong
                    Icon { anchors.centerIn: parent; visible: model.ticked; name: "check"; size: 12; color: s.tk.bg }
                    Accessible.role: Accessible.CheckBox
                    Accessible.name: model.name
                    Accessible.checked: model.ticked
                }
                Icon { id: g; anchors.left: box.right; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; name: model.kind === "folder" ? "folder" : model.kind === "url" ? "link" : model.status === "identified" ? "file" : "app-window" }
                Column {
                    anchors.left: g.right
                    anchors.leftMargin: 10
                    anchors.right: pill.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    Txt { width: parent.width; text: model.status === "identified" ? model.name : "A window titled ‘" + model.name + "’"; strong: model.ticked }
                    Txt { width: parent.width; text: [model.appName, model.path !== "" ? model.path : model.note].filter(function (x) { return x && x !== "" }).join(" · "); role: "small"; tone: "faint"; elide: Text.ElideMiddle }
                }
                StatusPill {
                    id: pill
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    status: model.status === "identified" ? "ok" : model.status === "unsaved" ? "neutral" : "warn"
                    label: model.status === "identified" ? "Identified" : model.status === "unsaved" ? "Unsaved" : model.status === "ambiguous" ? "Ambiguous" : "No path"
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: Window.window.safe(function () { app.capture.setCandidateTicked(model.entryKey, !model.ticked) })
                }
            }
        }
        EmptyBlock {
            visible: rep.count === 0
            width: parent.width
            line: "Looking at the open windows…"
        }
    }
}
