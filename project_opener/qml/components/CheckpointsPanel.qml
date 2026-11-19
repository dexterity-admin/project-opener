import QtQuick

// Checkpoints (brief 3.8): the activity's newest ten snapshots, each restorable.  Snapshot now and Park add
// one; starting, every 15 minutes while windows change, and ending keep one by themselves (kept 14 days, then
// one a day for 60; Time travel shows the week).  Data: app.capture.checkpoints, selected by ActivitiesApi.select.
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
        facts: rep.count > 0 ? "newest " + rep.count + " · all on Time travel" : ""
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
                    name: model.kind === "manual" ? "camera" : model.kind === "close" ? "stop-circle"
                        : model.kind === "park" ? "moon" : model.kind === "start" ? "play-circle" : "clock-counter-clockwise"
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
                             : (model.kind === "manual" ? "Snapshot" : model.kind === "close" ? "When it ended"
                                : model.kind === "start" ? "When it started" : model.kind === "park" ? "Parked"
                                : "Kept while you worked")
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
            line: "No checkpoints yet. Snapshot now keeps one."
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
