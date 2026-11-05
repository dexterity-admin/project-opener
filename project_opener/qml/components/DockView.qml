import QtQuick
import QtQuick.Controls.Basic as C

// The launch dock (brief 4; DESIGN.md "Launch sheet"): the run's rows in launch order, each with the pill
// the project page uses.  Rows arrive in launch order (60 ms apart, 8 px rise); a pill reads Opening… while
// its item is tried, then settles.  A 3 px progress line under the heading.  Footer: "9 opened · 2 not
// opened · 0 skipped · 3.4 s", "Open the 2 again" when something did not open, the task line on the right.
// `record`: the same rows as the activity page's "Opened at 09:12" column (static, no arrival).
Item {
    id: dock
    readonly property var tk: app.ui.tokens
    property bool record: false
    property int maxRows: 8
    readonly property int rowH: tk.pad < 20 ? 40 : 46
    property int failed: 0
    signal closeRequested()
    signal showActivity()

    Component.onCompleted: failed = countFailed()
    implicitHeight: head.height + 16 + Math.min(list.count, maxRows) * rowH + (list.count > maxRows ? 8 : 0) + foot.height + 12

    function countFailed() {
        var n = 0
        var m = app.activities.dock
        for (var i = 0; i < m.count(); i++) {
            var s = m.get(i).status
            if (s !== "opened" && s !== "skipped" && s !== "queued" && s !== "opening") n++
        }
        return n
    }
    Connections {
        target: app.activities
        function onLaunchChanged() { dock.failed = dock.countFailed() }
    }

    Item {
        id: head
        width: parent.width
        height: dock.record ? 30 : 56
        Row {
            id: titleRow
            spacing: 8
            Dot { tint: app.activities.dockColor; anchors.verticalCenter: parent.verticalCenter; visible: !dock.record }
            Txt {
                text: dock.record ? "Opened at " + app.activities.dockStartedText
                                  : (app.activities.launching ? "Opening " : "Opened ") + app.activities.dockTitle
                role: "heading"
                width: Math.min(implicitWidth, dock.width - 120)
                anchors.verticalCenter: parent.verticalCenter
            }
            Txt {
                visible: dock.record
                text: list.count + (list.count === 1 ? " item" : " items") + " · launch order"
                tone: "muted"
                figures: true
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        Txt {
            visible: !dock.record
            anchors.top: titleRow.bottom
            anchors.topMargin: 2
            width: parent.width - 60
            text: app.activities.dockLine
            tone: "muted"
            figures: true
        }
        ActionButton {
            visible: !dock.record
            anchors.right: parent.right
            anchors.top: parent.top
            kind: "ghost"
            icon: "x"
            tooltip: "Close (Esc)"
            onClicked: dock.closeRequested()
        }
        Rectangle {             // 3 px progress line
            anchors.bottom: parent.bottom
            width: parent.width
            height: 3
            radius: 1.5
            color: dock.tk.surface_3
            Rectangle {
                height: 3
                radius: 1.5
                color: dock.tk.accent
                width: parent.width * app.activities.launchProgress
                Behavior on width { NumberAnimation { duration: Math.round(260 * app.ui.k); easing.type: Easing.OutCubic } }
            }
        }
    }

    ListView {
        id: list
        anchors.top: head.bottom
        anchors.topMargin: 8
        width: parent.width
        height: Math.min(count, dock.maxRows) * dock.rowH + (count > dock.maxRows ? 8 : 0)
        clip: true
        interactive: count > dock.maxRows
        boundsBehavior: Flickable.StopAtBounds
        model: app.activities.dock
        C.ScrollBar.vertical: C.ScrollBar { policy: list.count > dock.maxRows ? C.ScrollBar.AsNeeded : C.ScrollBar.AlwaysOff }
        delegate: Item {
            id: row
            width: list.width
            height: dock.rowH
            opacity: dock.record || app.ui.k === 0 ? 1 : 0
            property real rise: dock.record || app.ui.k === 0 ? 0 : 8
            Component.onCompleted: if (!dock.record && app.ui.k > 0) arrive.start()
            SequentialAnimation {
                id: arrive
                PauseAnimation { duration: Math.round(60 * Math.min(Math.max(0, index), 10) * app.ui.k) }
                ParallelAnimation {
                    NumberAnimation { target: row; property: "opacity"; to: 1; duration: Math.round(200 * app.ui.k); easing.type: Easing.OutCubic }
                    NumberAnimation { target: row; property: "rise"; to: 0; duration: Math.round(240 * app.ui.k); easing.type: Easing.OutCubic }
                }
            }
            Item {
                width: parent.width
                height: parent.height
                y: row.rise
                Rectangle { width: parent.width; height: 1; color: dock.tk.border; visible: index > 0 }
                Icon { id: glyph; x: 2; anchors.verticalCenter: parent.verticalCenter; name: model.glyph }
                Column {
                    anchors.left: glyph.right
                    anchors.leftMargin: 10
                    anchors.right: pill.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1
                    Txt { width: parent.width; text: model.name; strong: true }
                    Txt {
                        width: parent.width
                        text: (model.group !== "" ? model.group + " · " : "") + model.order
                              + (model.status !== "opened" && model.status !== "queued" && model.status !== "opening" && model.message !== ""
                                 ? " · " + model.message : "")
                        role: "small"
                        tone: "faint"
                        figures: true
                    }
                }
                StatusPill {
                    id: pill
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    status: model.level
                    label: model.statusLabel
                }
                Tip { visible: rowHover.containsMouse && model.path !== ""; text: model.path }
                MouseArea { id: rowHover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
            }
        }
    }

    Item {
        id: foot
        anchors.top: list.bottom
        anchors.topMargin: 12
        width: parent.width
        height: 34
        Rectangle { width: parent.width; height: 1; color: dock.tk.border; y: -6 }
        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 12
            Txt {
                text: app.activities.launchSummary !== "" ? app.activities.launchSummary
                     : app.activities.launching ? "Opening in launch order…" : ""
                strong: app.activities.launchSummary !== ""
                figures: true
                anchors.verticalCenter: parent.verticalCenter
                opacity: text === "" ? 0 : 1
                Behavior on opacity { NumberAnimation { duration: Math.round(200 * app.ui.k) } }
            }
            ActionButton {
                visible: !app.activities.launching && dock.failed > 0
                text: "Open the " + dock.failed + " again"
                kind: "link"
                small: true
                anchors.verticalCenter: parent.verticalCenter
                onClicked: app.activities.openFailedAgain()
            }
        }
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Txt {
                text: app.activities.dockTaskLine
                tone: "muted"
                width: Math.min(implicitWidth, dock.width * 0.4)
                anchors.verticalCenter: parent.verticalCenter
            }
            ActionButton {
                visible: !dock.record && !app.activities.launching
                text: "Go to activity"
                icon: "arrow-right"
                small: true
                anchors.verticalCenter: parent.verticalCenter
                onClicked: dock.showActivity()
            }
        }
    }
}
