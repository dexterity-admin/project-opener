import QtQuick

// Time travel this week (Today's first panel): a lane per day from Monday to today, a tick per checkpoint any
// activity kept (`app.today.week`), placed by its time of day; its height follows the windows it holds.  Click
// (or hover) a tick: the card at the foot says when, how many windows and which activity, with Restore.  The
// newest is shown first.  The card sits at the panel's foot, so a panel stretched to the row's height keeps
// its lanes at the top and the card at the bottom edge.  `arrive` grows the ticks in with the panel's rise.
Card {
    id: panel
    radius: 8
    property real arrive: 1
    readonly property var ticks: app.today.week
    readonly property var days: app.today.weekDays
    readonly property int laneH: 26
    readonly property int labelW: 40
    property int picked: -1                       // index in ticks; -1 = the newest
    readonly property int sel: ticks.length === 0 ? -1 : picked >= 0 && picked < ticks.length ? picked : ticks.length - 1
    readonly property var cur: sel >= 0 ? ticks[sel] : null
    onTicksChanged: picked = -1

    // the hours the lanes span: 07:00 to 19:00, widened to the earliest and latest checkpoint
    readonly property int lo: {
        var m = 7 * 60
        for (var i = 0; i < ticks.length; i++) m = Math.min(m, ticks[i].minute)
        return Math.floor(m / 60) * 60
    }
    readonly property int hi: {
        var m = 19 * 60
        for (var i = 0; i < ticks.length; i++) m = Math.max(m, ticks[i].minute)
        return Math.min(24 * 60, Math.ceil((m + 1) / 60) * 60)
    }
    readonly property int maxWin: {
        var m = 1
        for (var i = 0; i < ticks.length; i++) m = Math.max(m, ticks[i].windows)
        return m
    }
    function hh(m) { return (m < 600 ? "0" : "") + Math.floor(m / 60) + ":00" }

    implicitHeight: ticks.length === 0 ? body.y + empty.implicitHeight + pad
                  : body.y + lanes.height + 22 + 14 + foot.height + pad

    Item {
        id: head
        x: panel.pad; y: panel.pad - 4
        width: panel.width - 2 * panel.pad
        height: 34
        SectionHeading {
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - timelineBtn.width - 8
            title: "Time travel"
            facts: panel.ticks.length === 0 ? "this week"
                 : "this week · " + panel.ticks.length + (panel.ticks.length === 1 ? " checkpoint" : " checkpoints")
        }
        ActionButton {
            id: timelineBtn
            objectName: "openTimeline"
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "Open timeline"
            icon: "arrow-right"
            kind: "ghost"
            small: true
            onClicked: app.ui.go("timetravel", ({}))
        }
    }

    Item {
        id: body
        x: panel.pad
        y: head.y + head.height + 6
        width: panel.width - 2 * panel.pad

        EmptyBlock {
            id: empty
            visible: panel.ticks.length === 0
            width: parent.width
            line: "No checkpoints this week. An activity keeps one when you take a snapshot, while it runs and when it ends."
        }

        Column {
            id: lanes
            visible: panel.ticks.length > 0
            width: parent.width
            Repeater {
                model: panel.days
                delegate: Item {
                    required property string modelData
                    required property int index
                    width: lanes.width
                    height: panel.laneH
                    Txt { text: parent.modelData; role: "label"; width: panel.labelW; anchors.verticalCenter: parent.verticalCenter }
                    Rectangle {
                        x: panel.labelW; y: parent.height - 1
                        width: parent.width - panel.labelW; height: 1
                        color: panel.tk.border
                    }
                }
            }
        }
        Repeater {                                   // the ticks, over the lanes
            model: panel.ticks
            delegate: Item {
                id: tick
                required property var modelData
                required property int index
                readonly property bool on: index === panel.sel
                readonly property real laneW: lanes.width - panel.labelW - 8
                visible: panel.ticks.length > 0
                width: 12
                height: panel.laneH - 6
                x: panel.labelW + 4 + laneW * (modelData.minute - panel.lo) / Math.max(1, panel.hi - panel.lo) - width / 2
                y: modelData.day * panel.laneH + 2
                Accessible.role: Accessible.Button
                Accessible.name: modelData.whenText + ", " + modelData.windows + " windows, " + modelData.name
                Rectangle {
                    id: bar
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 3
                    width: 4
                    radius: 2
                    height: Math.round(8 + 10 * tick.modelData.windows / panel.maxWin)
                    color: tick.on || tickMouse.containsMouse ? panel.tk.action : panel.tk.teal
                    opacity: tick.on || tickMouse.containsMouse ? 1 : 0.75
                    transform: Scale { origin.y: bar.height; yScale: panel.arrive * (tick.on ? 1.25 : 1) }
                    Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k) } }
                }
                MouseArea {
                    id: tickMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: panel.picked = tick.index
                }
            }
        }
        Item {                                       // the hours under the lanes
            visible: panel.ticks.length > 0
            y: lanes.height + 4
            x: panel.labelW
            width: lanes.width - panel.labelW
            height: 18
            Txt { text: panel.hh(panel.lo); role: "label"; anchors.left: parent.left }
            Txt { text: panel.hh(panel.hi); role: "label"; anchors.right: parent.right }
        }
    }

    Rectangle {                                      // the picked checkpoint, at the panel's foot
        id: foot
        visible: panel.cur !== null
        x: panel.pad
        width: panel.width - 2 * panel.pad
        height: 44
        anchors.bottom: parent.bottom
        anchors.bottomMargin: panel.pad
        radius: 6
        color: panel.tk.surface_2
        Txt {
            id: when
            x: 12
            anchors.verticalCenter: parent.verticalCenter
            text: panel.cur ? panel.cur.whenText : ""
            strong: true
            figures: true
            elide: Text.ElideNone
        }
        Txt {
            anchors.left: when.right
            anchors.leftMargin: 10
            anchors.right: restore.left
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            text: panel.cur ? panel.cur.windows + (panel.cur.windows === 1 ? " window · " : " windows · ") + panel.cur.name : ""
            tone: "muted"
            figures: true
        }
        ActionButton {
            id: restore
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: "Restore"
            small: true
            available: panel.cur !== null && panel.cur.identified > 0
            tooltip: available ? "Reopen these windows in launch order and put them back where they were"
                               : "Nothing in this checkpoint can be reopened: no window has a known path"
            onClicked: {
                var c = panel.cur
                Window.window.confirm("Restore the " + c.whenText + " checkpoint of " + c.name + "?",
                                      "Its " + c.identified + " identified windows reopen in launch order; windows already open are left alone.",
                                      "Restore", false,
                                      function () { Window.window.safe(function () { app.capture.restoreCheckpoint(c.activityId, c.checkpointId) }) })
            }
        }
    }
}
