import QtQuick
import "../components"

// An activity (concept-1-stage, board B): the centre scene become the page.  Header: the capture switch,
// Snapshot now, Add a window, and the one filled button that follows what is waiting (Save N new as items
// when the watcher found new things, else Snapshot now while it runs, else Open activity).  Left: Open now
// (the live list, worst first) while it runs, else the items in launch order.  Right: the launch record
// ("Opened at 09:12"), the task and the watchers, the Monitors panel, the checkpoints.
Page {
    id: page
    minimumWidth: 860
    readonly property string tint: { var m = app.activities.activities; var i = m.indexOf(page.activityId); return i >= 0 ? m.get(i).dotColor : "" }
    readonly property string activityId: app.ui.routePayload.activityId || ""
    readonly property var act: app.activities.current
    readonly property bool known: act.activityId !== undefined && act.activityId === activityId
    readonly property bool running: known && app.capture.runningId === activityId
    readonly property int newCount: running ? app.capture.newCount : 0
    readonly property bool hasRecord: app.activities.dockId === activityId && app.activities.dock.count() > 0
                                     && app.activities.launchProgress >= 0
    readonly property bool stack: contentW < 1080

    Component.onCompleted: { var id = page.activityId; Qt.callLater(function () { app.activities.select(id) }) }

    function subtitle() {
        if (!known) return ""
        if (running) {
            var parts = [app.capture.openCount + (app.capture.openCount === 1 ? " thing open" : " things open"),
                         app.capture.identifiedCount + " identified"]
            if (app.capture.needsPathCount > 0) parts.push(app.capture.needsPathCount + " need a path")
            // as the pill's panel words it: "checkpoint 10:52, 2 new since" / "11 new since the start"
            var since = app.capture.sinceCheckpoint
            if (app.capture.lastCheckpointText !== "")
                parts.push("checkpoint " + app.capture.lastCheckpointText + (since > 0 ? ", " + since + " new since" : ""))
            else if (since > 0) parts.push(since + " new since the start")
            return "Running · " + parts.join(" · ")
        }
        return act.subtitle
    }
    function snapshot() { Window.window.safe(function () { app.capture.snapshotNow() }) }
    function addWindow() {
        if (app.desktop) Window.window.safe(function () { app.desktop.startPicker() })
        else Window.window.safe(function () { app.capture.addForegroundWindow() })
    }
    function menuAction(a) {
        var w = Window.window
        switch (a) {
        case "edit": w.openSheet("ActivityEditor", { activityId: page.activityId }); break
        case "pin": app.activities.togglePin(page.activityId); break
        case "duplicate": { var id = app.activities.duplicate(page.activityId); if (id) app.ui.go("activity", { activityId: id }); break }
        case "publish": w.openSheet("PublishSheet", { mode: "activity", targetId: page.activityId }); break
        case "send": w.openSheet("PublishSheet", { mode: "send-activity", targetId: page.activityId }); break
        case "task": w.openSheet("TaskSheet", { attachKind: "activity", attachId: page.activityId }); break
        case "watcher": w.openSheet("WatcherSheet", { activityId: page.activityId }); break
        case "mail": app.activities.mailBundle(page.activityId); break
        case "link": app.activities.copyLink(page.activityId); break
        case "pause": w.safe(function () { if (app.capture.state === "paused") app.capture.resume(); else app.capture.pause() }); break
        case "end": w.confirm("End " + act.name + "?", "A last checkpoint is kept and capture stops; nothing is closed.",
                              "End activity", false, function () { w.safe(function () { app.capture.endActivity() }) }); break
        case "delete": w.confirm("Delete " + act.name + "?",
                                 "Its " + act.itemCount + " items and its checkpoints go; the projects and their items stay.",
                                 "Delete activity", true, function () { app.activities.remove(page.activityId); app.ui.go("activities", ({})) }); break
        }
    }

    PageHeader {
        back: "Back"
        onBackClicked: app.ui.back()
        title: page.known ? act.title : "Activity not found"
        subtitle: page.known ? page.subtitle() : "It may have been deleted on this PC."
        icon: page.known ? act.icon : ""
        tint: page.known ? act.dotColor : ""

        Toggle {
            visible: page.known
            label: "Capture"
            checked: page.known && act.captureOn
            onToggled: (on) => {
                if (!app.settings.value("capture_enabled") && on) app.settings.setValue("capture_enabled", true)
                app.activities.edit(page.activityId, { captureOn: on })
            }
        }
        ActionButton {
            visible: page.running && page.newCount > 0
            text: "Snapshot now"
            icon: "camera"
            onClicked: page.snapshot()
        }
        ActionButton {
            visible: page.running
            text: "Add a window"
            icon: "selection-plus"
            onClicked: page.addWindow()
        }
        ActionButton {                               // the one filled control follows what is waiting
            visible: page.known
            kind: "primary"
            icon: page.running ? (page.newCount > 0 ? "download-simple" : "camera") : "play"
            text: !page.running ? "Open activity" : page.newCount > 0 ? "Save " + page.newCount + " new as items" : "Snapshot now"
            onClicked: {
                if (!page.running) app.activities.open(page.activityId)
                else if (page.newCount > 0) Window.window.saveNew()
                else page.snapshot()
            }
        }
        MenuButton {
            visible: page.known
            entries: [
                { text: "Edit activity", icon: "pencil-simple", action: "edit" },
                { text: act.pinned ? "Unpin from the stage" : "Pin to the stage", icon: "push-pin", action: "pin" },
                { text: "Duplicate", icon: "copy", action: "duplicate" },
                { text: "-" },
                { text: "Publish to Team Hub", icon: "share-network", action: "publish" },
                { text: "Send to a colleague", icon: "paper-plane-tilt", action: "send" },
                { text: "New task", icon: "check-square", action: "task" },
                { text: "Add a watcher", icon: "eye", action: "watcher" },
                { text: "Mail the items as links", icon: "envelope-simple", action: "mail" },
                { text: "Copy link", icon: "link", action: "link" },
                { text: "-" },
                { text: app.capture.state === "paused" ? "Resume capture" : "Pause capture", icon: "pause", action: "pause", hidden: !page.running },
                { text: "End activity", icon: "stop-circle", action: "end", hidden: !page.running },
                { text: "Delete activity", icon: "trash", action: "delete", danger: true }
            ]
            onTriggered: (a) => page.menuAction(a)
        }
    }

    Txt {
        visible: page.known && act.description !== ""
        width: Math.min(720, page.contentW)
        text: page.known ? act.description : ""
        tone: "muted"
        wrapMode: Text.Wrap
        elide: Text.ElideNone
    }

    // ------------------------------------------------------------ the two columns
    Item {
        id: cols
        visible: page.known
        width: page.contentW
        readonly property int rightW: page.stack ? width : Math.max(380, Math.round(width * 0.36))
        readonly property int leftW: page.stack ? width : width - rightW - 16
        height: page.stack ? left.height + 16 + right.height : Math.max(left.height, right.height)

        Card {
            id: left
            width: cols.leftW
            height: leftCol.implicitHeight + 2 * pad
            Column {
                id: leftCol
                x: left.pad; y: left.pad
                width: left.width - 2 * left.pad
                spacing: 12
                Item {
                    width: parent.width
                    height: 30
                    SectionHeading {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - editItems.width - 12
                        title: page.running ? "Open now" : "Items"
                        facts: page.running ? app.capture.openCount + " things · " + app.capture.identifiedCount + " identified"
                                            : act.itemCount + " · launch order"
                    }
                    ActionButton {
                        id: editItems
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: page.running ? "Items" : "Edit items"
                        icon: page.running ? "list-bullets" : "pencil-simple"
                        kind: "ghost"
                        small: true
                        onClicked: Window.window.openSheet("ActivityEditor", { activityId: page.activityId, tab: "items" })
                    }
                }
                LiveList {
                    visible: page.running
                    width: parent.width
                    activityId: page.activityId
                }
                ItemsList {
                    visible: !page.running
                    width: parent.width
                    items: app.activities.items
                    showProject: act.projectCount > 1
                    onOpenItem: (id) => app.activities.openItem(page.activityId, id)
                    onEditItem: (id) => Window.window.openSheet("ActivityEditor", { activityId: page.activityId, tab: "items", itemId: id })
                }
            }
        }

        Column {
            id: right
            x: page.stack ? 0 : cols.leftW + 16
            y: page.stack ? left.height + 16 : 0
            width: cols.rightW
            spacing: 16

            Card {
                visible: page.hasRecord
                width: parent.width
                height: visible ? record.implicitHeight + 2 * pad : 0
                DockView {
                    id: record
                    record: true
                    maxRows: 7
                    x: parent.pad; y: parent.pad
                    width: parent.width - 2 * parent.pad
                }
            }

            Card {
                id: taskCard
                width: parent.width
                height: taskCol.implicitHeight + 2 * pad
                Column {
                    id: taskCol
                    x: taskCard.pad; y: taskCard.pad
                    width: taskCard.width - 2 * taskCard.pad
                    spacing: 4
                    SectionHeading { width: parent.width; title: "Task and watchers" }
                    Item { width: 1; height: 4 }
                    Repeater {
                        id: taskRep
                        model: app.tasks.all
                        delegate: TaskRow {
                            width: taskCol.width
                            visible: model.attachId === page.activityId
                            height: visible ? 48 : 0
                            first: true
                            compact: true
                        }
                    }
                    Repeater {
                        id: watchRep
                        model: app.watchers.watchers
                        delegate: Item {
                            width: taskCol.width
                            visible: model.activityId === page.activityId
                            height: visible ? 46 : 0
                            Icon { id: wi; anchors.verticalCenter: parent.verticalCenter; name: model.kind === "health" ? "bell" : model.kind === "time" ? "clock" : "eye" }
                            Column {
                                anchors.left: wi.right
                                anchors.leftMargin: 10
                                anchors.right: wt.left
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                Txt { width: parent.width; text: model.name + (model.lastHitText !== "" ? " · " + model.lastHitText : ""); figures: true }
                                Txt { width: parent.width; text: model.notifyText; role: "small"; tone: "faint" }
                            }
                            Toggle {
                                id: wt
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                checked: model.watcherEnabled
                                onToggled: (on) => Window.window.safe(function () { app.watchers.setEnabled(model.watcherId, on) })
                            }
                        }
                    }
                    Row {
                        spacing: 8
                        topPadding: 6
                        ActionButton { text: "New task"; icon: "plus"; small: true; onClicked: Window.window.openSheet("TaskSheet", { attachKind: "activity", attachId: page.activityId }) }
                        ActionButton { text: "Add a watcher"; icon: "eye"; small: true; onClicked: Window.window.openSheet("WatcherSheet", { activityId: page.activityId }) }
                    }
                }
            }

            MonitorsPanel {
                width: parent.width
                height: implicitHeight
                running: page.running
            }
            CheckpointsPanel {
                width: parent.width
                height: implicitHeight
                activityId: page.activityId
            }
        }
    }

    EmptyBlock {
        visible: !page.known
        width: page.contentW
        line: "This activity is not in your workspace."
        action: "All activities"
        onTriggered: app.ui.go("activities", ({}))
    }
}
