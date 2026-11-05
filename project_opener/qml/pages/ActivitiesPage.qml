import QtQuick
import "../components"
import "../sheets"

// Activities: every activity as a row (the list fallback of the stage): identity dot and title, its line,
// the health pill, the capture state, Open.  New activity is the page's primary; Start from what's open
// sits beside it while nothing runs.
Page {
    id: page
    minimumWidth: 860

    PageHeader {
        title: "Activities"
        subtitle: rep.count === 0 ? "" : rep.count + (rep.count === 1 ? " activity" : " activities")
                  + (app.capture.runningId !== "" ? " · " + app.capture.runningName + " running" : "")
        ActionButton {
            visible: app.capture.runningId === ""
            text: "Start from what's open"
            icon: "browsers"
            onClicked: Window.window.startFromOpen()
        }
        ActionButton {
            text: "New activity"
            icon: "plus"
            kind: "primary"
            onClicked: Window.window.openSheet("ActivityEditor", { activityId: "" })
        }
    }

    LaunchDock { width: page.contentW }

    Card {
        width: page.contentW
        height: list.implicitHeight + 2 * pad
        Column {
            id: list
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            Repeater {
                id: rep
                model: app.activities.activities
                delegate: Item {
                    width: list.width
                    height: 64
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Rectangle {
                        anchors.fill: parent
                        anchors.topMargin: 1
                        radius: 10
                        color: rowMouse.containsMouse ? page.tk.surface_2 : "transparent"
                    }
                    IconTile { id: tile; x: 4; anchors.verticalCenter: parent.verticalCenter; icon: model.icon; tint: model.dotColor; size: 32 }
                    Column {
                        anchors.left: tile.right
                        anchors.leftMargin: 14
                        anchors.right: health.left
                        anchors.rightMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Row {
                            width: parent.width
                            spacing: 6
                            Txt { id: actTitle; width: Math.min(implicitWidth, parent.width - (pinMark.visible ? 20 : 0)); text: model.title; strong: true }
                            Icon { id: pinMark; visible: model.pinned; name: "push-pin"; size: 12; tone: "faint"; anchors.verticalCenter: actTitle.verticalCenter; Accessible.name: "Pinned" }
                        }
                        Txt {
                            width: parent.width
                            text: [model.subtitle, model.taskLine].filter(function (s) { return s && s !== "" }).join(" · ")
                            role: "small"
                            tone: "faint"
                            figures: true
                        }
                    }
                    Item {
                        id: health
                        width: 150
                        height: 20
                        anchors.right: cap.left
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        StatusPill {
                            anchors.right: parent.right
                            status: model.healthWorst === "" ? "neutral" : model.healthWorst === "ok" ? "ok"
                                  : model.healthWorst === "offline" ? "bad" : "warn"
                            label: model.healthWorst === "" ? "" : model.healthWorst === "ok" ? "Reachable"
                                 : model.healthWorst === "offline" ? "Server offline"
                                 : model.healthWorst === "variable" ? "Undefined variable" : "Not found"
                        }
                    }
                    Txt {
                        id: cap
                        width: 110
                        anchors.right: open.left
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        horizontalAlignment: Text.AlignRight
                        text: model.running ? "Running" : model.pausedText !== "" ? model.pausedText
                             : model.captureOn ? "Capture on" : "Capture off"
                        role: "small"
                        tone: model.running ? "ok" : "faint"
                    }
                    ActionButton {
                        id: open
                        anchors.right: parent.right
                        anchors.rightMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Open"
                        icon: "play"
                        small: true
                        onClicked: app.activities.open(model.activityId)
                    }
                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        z: -1
                        onClicked: app.ui.go("activity", { activityId: model.activityId })
                    }
                }
            }
            EmptyBlock {
                visible: rep.count === 0
                width: list.width
                line: "No activities yet. Open what a task needs, then start one from what's open."
                action: "Start from what's open"
                actionIcon: "browsers"
                onTriggered: Window.window.startFromOpen()
            }
        }
    }

    // a launch in progress stays visible here as on Home
}
