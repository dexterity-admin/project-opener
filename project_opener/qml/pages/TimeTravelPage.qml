import QtQuick
import "../components"

// Time travel (docs/V4-PLUS-BRIEF.md section 1, docs/DESIGN.md "Today" time-travel panel, grown to a page):
// the last seven days of checkpoints across every activity, a lane per day (today on top), a tick per
// checkpoint at its time of day.  Hover a tick for when, the activity and the window count; click it to
// select it, and the card below offers Restore (the activity page's checkpoint restore, behind the same
// confirmation).  Ticks are deep teal (graphics, never text); the selected one is ink.  Restore is the page's
// one amber control.  Data: app.capture.timeline / timelineInfo (refreshMemory recomputes them on arrival).
Page {
    id: page
    minimumWidth: 860

    readonly property var info: app.capture.timelineInfo
    readonly property int total: info.total || 0
    readonly property int startHour: info.startHour || 8
    readonly property int endHour: info.endHour || 18
    readonly property var days: info.days || []
    property string selectedId: ""
    property var selected: ({})
    property int hoverIndex: -1

    readonly property color tickColor: app.ui.dark ? tk.teal : tk.teal_deep

    function plural(n, one, many) { return n + " " + (n === 1 ? one : many) }
    function select(id) {
        var m = app.capture.timeline
        var i = id !== "" ? m.indexOf(id) : -1
        if (i < 0 && m.count() > 0) i = 0          // newest first: the latest moment is the default
        selected = i >= 0 ? m.get(i) : ({})
        selectedId = i >= 0 ? selected.checkpointId : ""
    }
    function hourText(h) { return (h < 10 ? "0" : "") + h + ":00" }

    Component.onCompleted: {
        Window.window.safe(function () { app.capture.refreshMemory() })
        select("")
    }
    Connections {
        target: app.capture
        function onMemoryChanged() { page.select(page.selectedId) }
    }

    PageHeader {
        title: "Time travel"
        subtitle: page.total === 0 ? ""
                  : page.plural(page.total, "checkpoint", "checkpoints") + " in 7 days"
                    + (app.capture.weekReopened > 0
                       ? " · " + page.plural(app.capture.weekReopened, "window", "windows") + " reopened this week" : "")
        ActionButton {
            visible: app.capture.runningId !== ""
            text: "Park"
            icon: "moon"
            tooltip: "Keep this moment with a note (Ctrl+Alt+P)"
            onClicked: Window.window.safe(function () { app.capture.requestPark() })
        }
    }

    Card {
        id: week
        width: page.contentW
        height: weekCol.implicitHeight + 2 * pad
        Column {
            id: weekCol
            x: week.pad; y: week.pad
            width: week.width - 2 * week.pad
            spacing: 12

            SectionHeading {
                width: parent.width
                title: "This week"
                facts: page.total > 0 ? "a tick per checkpoint · every activity" : ""
            }

            Item {
                id: lanes
                visible: page.total > 0
                width: parent.width
                readonly property int labelW: 118
                readonly property int laneH: 38
                readonly property int axisH: 22
                readonly property real trackW: Math.max(1, width - labelW - 8)
                height: visible ? axisH + page.days.length * laneH : 0

                // the hour axis: a mono label every two hours, kept inside the lane's ends
                Repeater {
                    model: Math.floor((page.endHour - page.startHour) / 2) + 1
                    delegate: Txt {
                        readonly property int hour: page.startHour + index * 2
                        readonly property real at: lanes.trackW * (hour - page.startHour) / Math.max(1, page.endHour - page.startHour)
                        role: "label"
                        figures: true
                        text: page.hourText(hour)
                        x: lanes.labelW + Math.max(0, Math.min(lanes.trackW - implicitWidth, at - implicitWidth / 2))
                        y: 0
                        height: lanes.axisH - 6
                    }
                }

                // a lane per day: its name and count on the left, a hairline track on the right
                Repeater {
                    model: page.days
                    delegate: Item {
                        x: 0
                        y: lanes.axisH + index * lanes.laneH
                        width: lanes.width
                        height: lanes.laneH
                        Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                        Txt {
                            x: 0
                            width: lanes.labelW - 44
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.label
                            strong: modelData.day === 0
                            tone: modelData.count > 0 ? "ink" : "faint"
                        }
                        Txt {
                            x: lanes.labelW - 40
                            width: 28
                            anchors.verticalCenter: parent.verticalCenter
                            horizontalAlignment: Text.AlignRight
                            role: "label"
                            figures: true
                            text: modelData.count > 0 ? String(modelData.count) : ""
                        }
                        Rectangle {
                            x: lanes.labelW
                            width: lanes.trackW
                            height: 1
                            anchors.verticalCenter: parent.verticalCenter
                            color: page.tk.border_strong
                        }
                    }
                }

                // the ticks
                Repeater {
                    id: ticks
                    model: app.capture.timeline
                    delegate: Item {
                        id: tick
                        readonly property bool chosen: model.checkpointId === page.selectedId
                        readonly property bool hot: tickMouse.containsMouse
                        x: lanes.labelW + model.pos * lanes.trackW - width / 2
                        y: lanes.axisH + model.day * lanes.laneH
                        width: 12
                        height: lanes.laneH
                        Rectangle {
                            anchors.centerIn: parent
                            width: tick.chosen ? 4 : 3
                            height: tick.chosen || tick.hot ? 24 : model.kind === "park" ? 20 : 14
                            radius: 1.5
                            color: tick.chosen ? page.tk.text : page.tickColor
                            Behavior on height { NumberAnimation { duration: Math.round(140 * app.ui.k); easing.type: Easing.OutCubic } }
                        }
                        Rectangle {                      // Park carries a small cap: the moment with a note
                            visible: model.kind === "park"
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: parent.height / 2 - (tick.chosen || tick.hot ? 12 : 10) - 3
                            width: 6; height: 6; radius: 3
                            color: tick.chosen ? page.tk.text : page.tickColor
                        }
                        MouseArea {
                            id: tickMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onContainsMouseChanged: page.hoverIndex = containsMouse ? index : (page.hoverIndex === index ? -1 : page.hoverIndex)
                            onClicked: page.select(model.checkpointId)
                        }
                        Accessible.role: Accessible.Button
                        Accessible.name: model.timeText + ", " + model.activityName + ", " + model.count + " windows"
                    }
                }

                // hover: when, the activity, the window count (kept inside the card)
                Rectangle {
                    id: tip
                    readonly property var row: page.hoverIndex >= 0 ? app.capture.timeline.get(page.hoverIndex) : ({})
                    visible: page.hoverIndex >= 0 && tip.row.checkpointId !== undefined
                    z: 5
                    width: Math.min(320, tipText.implicitWidth + 20)
                    height: 28
                    radius: 6
                    color: page.tk.surface
                    border.width: 1
                    border.color: page.tk.border_strong
                    x: visible ? Math.max(lanes.labelW, Math.min(lanes.width - width,
                                          lanes.labelW + tip.row.pos * lanes.trackW - width / 2)) : 0
                    y: visible ? Math.max(0, lanes.axisH + tip.row.day * lanes.laneH - height + 4) : 0
                    Txt {
                        id: tipText
                        x: 10
                        width: parent.width - 20
                        anchors.verticalCenter: parent.verticalCenter
                        figures: true
                        text: tip.visible ? tip.row.timeText + " · " + tip.row.activityName + " · "
                                            + page.plural(tip.row.count, "window", "windows") : ""
                    }
                }
            }

            EmptyBlock {
                visible: page.total === 0
                width: parent.width
                line: "No checkpoints in the last seven days. Starting an activity keeps one; Park keeps one with your note."
            }
        }
    }

    // the selected moment and its Restore
    Card {
        id: detail
        visible: page.selectedId !== ""
        width: page.contentW
        height: visible ? detailCol.implicitHeight + 2 * pad : 0
        Column {
            id: detailCol
            x: detail.pad; y: detail.pad
            width: detail.width - 2 * detail.pad - restoreBtn.width - 16
            spacing: 6
            Txt {
                width: parent.width
                role: "label"
                figures: true
                text: page.selectedId === "" ? ""
                      : (page.days[page.selected.day] ? page.days[page.selected.day].label : "") + " · "
                        + page.selected.timeText + " · " + page.selected.kindWord
            }
            Row {
                width: parent.width
                spacing: 8
                Dot { tint: page.selected.dotColor || ""; anchors.verticalCenter: parent.verticalCenter }
                Txt {
                    width: parent.width - 14
                    role: "heading"
                    text: page.selected.activityName || ""
                }
            }
            Txt {                                      // a Park note is the person's own words (DESIGN.md "Type")
                visible: (page.selected.note || "") !== ""
                width: parent.width
                role: page.selected.kind === "park" ? "note" : "body"
                text: page.selected.kind === "park" ? "‘" + page.selected.note + "’" : (page.selected.note || "")
                wrapMode: Text.Wrap
                maximumLineCount: 3
            }
            Txt {
                width: parent.width
                tone: "muted"
                figures: true
                text: page.selectedId === "" ? ""
                      : page.plural(page.selected.count || 0, "window", "windows") + " open · "
                        + (page.selected.restorable || 0) + " can be reopened"
            }
        }
        ActionButton {
            id: restoreBtn
            anchors.right: parent.right
            anchors.rightMargin: detail.pad
            anchors.verticalCenter: parent.verticalCenter
            text: "Restore"
            icon: "clock-counter-clockwise"
            kind: "primary"
            available: (page.selected.restorable || 0) > 0
            tooltip: available ? "Reopen these windows in launch order and put them back where they were"
                               : "Nothing in this checkpoint has a file to reopen"
            onClicked: {
                if (!available) return
                var row = page.selected
                Window.window.confirm("Restore the " + row.timeText + " checkpoint?",
                                      row.activityName + ": its " + row.restorable
                                      + " identified windows reopen in launch order; windows already open are left alone.",
                                      "Restore", false,
                                      function () { Window.window.safe(function () { app.capture.restoreCheckpoint(row.activityId, row.checkpointId) }) })
            }
        }
    }
}
