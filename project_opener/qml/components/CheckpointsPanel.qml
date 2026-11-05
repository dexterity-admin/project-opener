import QtQuick

// Checkpoints (brief 3.8): the activity's last ten snapshots, newest first, each restorable.  Snapshot now
// adds one; the watcher keeps one automatically; ending the activity keeps one.  Data: app.capture.checkpoints
// (builder 2), selected for this activity by ActivitiesApi.select.
Card {
    id: panel
    property string activityId: ""
    property int maxRows: 5
    implicitHeight: 64 + Math.max(1, Math.min(rep.count, maxRows)) * 46 + (rep.count > maxRows ? 30 : 0) + pad
    property bool all: false

    SectionHeading {
        x: panel.pad; y: panel.pad
        width: panel.width - 2 * panel.pad
        title: "Checkpoints"
        facts: rep.count > 0 ? rep.count + " · the last ten are kept" : ""
    }
    Column {
        id: list
        x: panel.pad
        y: 60
        width: panel.width - 2 * panel.pad
        Repeater {
            id: rep
            model: app.capture.checkpoints
            delegate: Item {
                width: list.width
                visible: panel.all || index < panel.maxRows
                height: visible ? 46 : 0
                Rectangle { width: parent.width; height: 1; color: panel.tk.border; visible: index > 0 }
                Icon {
                    id: ic
                    anchors.verticalCenter: parent.verticalCenter
                    name: model.kind === "manual" ? "camera" : model.kind === "close" ? "stop-circle" : "clock-counter-clockwise"
                }
                Column {
                    anchors.left: ic.right
                    anchors.leftMargin: 10
                    anchors.right: restore.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    Txt {
                        width: parent.width
                        text: model.label !== "" ? model.label
                             : (model.kind === "manual" ? "Snapshot" : model.kind === "close" ? "When it ended" : "Kept by the watcher")
                               + (model.isLatest ? " · latest" : "")
                        figures: true
                        strong: model.isLatest
                    }
                    Txt {
                        width: parent.width
                        text: model.takenText + " · " + model.identified + " of " + model.count + " identified"
                        role: "small"
                        tone: "faint"
                        figures: true
                    }
                }
                ActionButton {
                    id: restore
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Restore"
                    small: true
                    tooltip: "Reopen these windows in launch order and put them back where they were"
                    onClicked: Window.window.confirm("Restore the " + model.takenText + " checkpoint?",
                                                     "Its " + model.identified + " identified windows reopen in launch order; windows already open are left alone.",
                                                     "Restore", false,
                                                     function () { Window.window.safe(function () { app.capture.restoreCheckpoint(panel.activityId, model.checkpointId) }) })
                }
            }
        }
        EmptyBlock {
            visible: rep.count === 0
            width: list.width
            line: "No checkpoints yet. Snapshot now keeps one; the last ten stay."
        }
        ActionButton {
            visible: rep.count > panel.maxRows
            text: panel.all ? "Show fewer" : "Show all " + rep.count
            kind: "link"
            small: true
            onClicked: panel.all = !panel.all
        }
    }
}
