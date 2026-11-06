import QtQuick
import "../components"

// Team Hub (brief 3.2, 3.3; board C): the 3.2 tabs plus Tasks and Groups.  Published projects and activities
// (revision a figure in the corner), the inbox (sent items, mentions, assigned tasks), the Tasks tab by owner
// or by job, announcements, the Activity register (Event · Rev · By · When under each job), Groups.  The
// publish / announce / send sheets carry the @ picker and the "For" field.  Data: app.hub, app.tasks (builder 1).
Page {
    id: page
    minimumWidth: 860
    property string tab: app.ui.routePayload.tab || "published"
    readonly property bool configured: app.hub.configured

    // only what no tab says (the tabs carry the published, inbox, task and group counts)
    function subtitle() {
        if (!configured) return "Not connected"
        return String(app.settings.value("hub_path")) + " · " + app.hub.peersOnline
               + (app.hub.peersOnline === 1 ? " colleague online" : " colleagues online")
    }

    PageHeader {
        title: "Team Hub"
        subtitle: page.subtitle()
        StatusPill {
            visible: page.configured
            y: 7
            status: app.hub.reachable ? "ok" : "bad"
            label: app.hub.reachable ? "Connected" : "Not reachable"
        }
        ActionButton {
            visible: page.configured
            icon: "arrows-clockwise"
            kind: "ghost"
            tooltip: "Refresh"
            onClicked: Window.window.safe(function () { app.hub.refresh() })
        }
        ActionButton {
            visible: page.configured
            text: page.tab === "tasks" ? "New task" : page.tab === "announcements" ? "Post an announcement"
                : page.tab === "groups" ? "New group" : "Publish an activity"
            icon: page.tab === "tasks" ? "check-square" : page.tab === "announcements" ? "megaphone-simple"
                : page.tab === "groups" ? "users-three" : "share-network"
            kind: "primary"
            onClicked: {
                var w = Window.window
                if (page.tab === "tasks") w.openSheet("TaskSheet", {})
                else if (page.tab === "announcements") w.openSheet("PublishSheet", { mode: "announce" })
                else if (page.tab === "groups") w.openSheet("GroupSheet", {})
                else w.openSheet("PublishSheet", { mode: "activity", targetId: app.capture.runningId || "" })
            }
        }
    }

    // ------------------------------------------------------------ not configured
    Card {
        visible: !page.configured
        width: page.contentW
        height: 170
        Column {
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            spacing: 12
            Txt { text: "Connect a Team Hub"; role: "heading" }
            Txt {
                width: Math.min(560, parent.width)
                text: "Pick a shared folder, for example \\\\nas01\\Project\\_ProjectOpenerHub. Everyone in the office points at the same one."
                tone: "muted"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
            }
            ActionButton {
                text: "Choose the folder"
                icon: "folder-open"
                kind: "primary"
                onClicked: {
                    var p = app.settings.browseFolder("Team Hub folder", "")
                    if (p !== "") app.settings.setValue("hub_path", p)
                }
            }
        }
    }

    Tabs {
        visible: page.configured
        current: page.tab
        tabs: [
            { key: "published", text: "Published", count: pubRep.count },
            { key: "inbox", text: "Inbox", count: app.hub.inboxCount },
            { key: "tasks", text: "Tasks", count: app.tasks.openCount },
            { key: "announcements", text: "Announcements", count: annRep.count },
            { key: "activity", text: "Activity", count: 0 },
            { key: "groups", text: "Groups", count: grpRep.count }
        ]
        onPicked: (key) => page.tab = key
    }

    // ------------------------------------------------------------ published
    Card {
        visible: page.configured && page.tab === "published"
        width: page.contentW
        height: pubCol.implicitHeight + 2 * pad
        Column {
            id: pubCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            Repeater {
                id: pubRep
                model: app.hub.published
                delegate: Item {
                    width: pubCol.width
                    height: 70
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Icon { id: pi; y: 16; name: model.type === "activity" ? "stack" : "folder" }
                    Column {
                        anchors.left: pi.right
                        anchors.leftMargin: 12
                        anchors.right: rev.left
                        anchors.rightMargin: 16
                        y: 12
                        spacing: 2
                        Txt { width: parent.width; text: model.title; strong: true }
                        Txt { width: parent.width; text: model.description; tone: "muted" }
                        Txt {
                            width: parent.width
                            text: [(model.type === "activity" ? "Activity" : "Project") + " · " + model.itemCount + (model.itemCount === 1 ? " item" : " items"),
                                   "by " + model.authorName, model.publishedText, model.forText]
                                  .filter(function (s) { return s && s !== "" }).join(" · ")
                            role: "small"
                            tone: "faint"
                            figures: true
                            HoverHandler { id: pubHover }
                            Tip { visible: pubHover.hovered; text: "by @" + model.author + (model.forTip ? " · for " + model.forTip : "") }
                        }
                    }
                    Txt {
                        id: rev
                        anchors.right: act.left
                        anchors.rightMargin: 16
                        y: 14
                        text: "rev " + model.revision
                        tone: "muted"
                        figures: true
                    }
                    Item {
                        id: act
                        width: 110
                        height: 28
                        anchors.right: parent.right
                        y: 10
                        ActionButton {
                            anchors.right: parent.right
                            visible: !model.isMine && !model.cloned
                            text: "Clone"
                            small: true
                            onClicked: Window.window.safe(function () { app.hub.clonePublished(model.publishedId) })
                        }
                        Txt {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            visible: !model.isMine && model.cloned
                            text: "In your workspace"
                            role: "small"
                            tone: "faint"
                        }
                        ActionButton {
                            anchors.right: parent.right
                            visible: model.isMine
                            text: "Unpublish"
                            kind: "ghost"
                            small: true
                            onClicked: Window.window.confirm("Unpublish " + model.title + "?", "Colleagues keep their clones; it leaves the hub's list.",
                                                             "Unpublish", true, function () { Window.window.safe(function () { app.hub.unpublish(model.publishedId) }) })
                        }
                    }
                }
            }
            EmptyBlock {
                visible: pubRep.count === 0
                width: pubCol.width
                line: "No projects or activities published yet."
                action: "Publish an activity"
                onTriggered: Window.window.openSheet("PublishSheet", { mode: "activity", targetId: "" })
            }
        }
    }

    // ------------------------------------------------------------ inbox
    Card {
        visible: page.configured && page.tab === "inbox"
        width: page.contentW
        height: inCol.implicitHeight + 2 * pad
        Column {
            id: inCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            Repeater {
                id: inRep
                model: app.hub.inbox
                delegate: Item {
                    width: inCol.width
                    height: 68
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Avatar { id: ia; y: 14; size: 30; initials: String(model.senderName).charAt(0); online: false }
                    Column {
                        anchors.left: ia.right
                        anchors.leftMargin: 12
                        anchors.right: inAct.left
                        anchors.rightMargin: 16
                        y: 12
                        spacing: 2
                        Row {
                            spacing: 8
                            Icon { name: model.kind === "mention" ? "at" : model.kind === "task" ? "check-square" : model.kind === "activity" ? "stack" : "folder"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                            Txt {
                                // a task note is either an assignment or a "<name> finished <title>" (tasks_api)
                                text: model.senderName + (model.kind === "mention" ? " mentioned you"
                                      : model.kind === "task" ? (String(model.message).indexOf(" finished ") >= 0 ? " finished a task" : " gave you a task")
                                      : " sent you " + model.title)
                                strong: true
                                anchors.verticalCenter: parent.verticalCenter
                                HoverHandler { id: fromHover }
                                Tip { visible: fromHover.hovered && model.sender !== ""; text: "@" + model.sender }
                            }
                            Txt { text: model.sentText; tone: "faint"; figures: true; anchors.verticalCenter: parent.verticalCenter }
                        }
                        Txt {                // "@Vikram Revision C has…": people by name, the login in the tooltip (T2-3)
                            width: parent.width
                            text: model.messageText
                            tone: "muted"
                            HoverHandler { id: msgHover }
                            Tip { visible: msgHover.hovered && model.mentionLogins !== ""; text: model.mentionLogins }
                        }
                        Txt { width: parent.width; visible: model.kind === "mention" || model.kind === "task"; text: model.title; role: "small"; tone: "faint" }
                    }
                    Row {
                        id: inAct
                        anchors.right: parent.right
                        y: 12
                        spacing: 6
                        ActionButton {
                            visible: model.kind === "project" || model.kind === "activity"
                            text: "Add to workspace"
                            small: true
                            onClicked: Window.window.safe(function () { app.hub.acceptInbox(model.messageId) })
                        }
                        ActionButton {
                            visible: (model.kind === "mention" || model.kind === "task") && model.link !== ""
                            text: "Open"
                            small: true
                            onClicked: app.handle_command({ cmd: "open", link: model.link })
                        }
                        ActionButton {
                            text: "Dismiss"
                            kind: "ghost"
                            small: true
                            onClicked: Window.window.safe(function () { app.hub.dismissInbox(model.messageId) })
                        }
                    }
                }
            }
            EmptyBlock { visible: inRep.count === 0; width: inCol.width; line: "Nothing sent to you yet." }
        }
    }

    // ------------------------------------------------------------ tasks
    Card {
        visible: page.configured && page.tab === "tasks"
        width: page.contentW
        height: taskCol.implicitHeight + 2 * pad
        Column {
            id: taskCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            spacing: 8
            Item {
                width: parent.width
                height: 34
                SectionHeading {                    // the count is the tab's, the grouping the switch's
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - groupBy.width - 16
                    title: "Tasks"
                }
                Segmented {
                    id: groupBy
                    anchors.right: parent.right
                    options: [{ value: "owner", text: "By owner" }, { value: "job", text: "By job" }]
                    value: app.tasks.groupBy
                    onPicked: (v) => Window.window.safe(function () { app.tasks.setGroupBy(v) })
                }
            }
            Repeater {
                id: taskRep
                model: app.tasks.all
                delegate: Column {
                    width: taskCol.width
                    readonly property string groupKey: app.tasks.groupBy === "job" ? (model.jobNumber || model.attachTitle || "No job") : model.ownerName
                    readonly property bool firstOfGroup: index === 0 || (function () {
                        var p = app.tasks.all.get(index - 1)
                        return (app.tasks.groupBy === "job" ? (p.jobNumber || p.attachTitle || "No job") : p.ownerName) !== groupKey
                    })()
                    Txt { visible: parent.firstOfGroup; text: parent.groupKey; role: "small"; tone: "faint"; topPadding: index === 0 ? 0 : 10; bottomPadding: 4 }
                    // grouped by owner, the heading names the owner once: no owner column on the rows
                    TaskRow { width: taskCol.width; first: parent.firstOfGroup; compact: false; showOwner: app.tasks.groupBy !== "owner" }
                }
            }
            EmptyBlock {
                visible: taskRep.count === 0
                width: taskCol.width
                line: "No tasks yet."
                action: "New task"
                actionIcon: "plus"
                onTriggered: Window.window.openSheet("TaskSheet", {})
            }
        }
    }

    // ------------------------------------------------------------ announcements
    Card {
        visible: page.configured && page.tab === "announcements"
        width: page.contentW
        height: annCol.implicitHeight + 2 * pad
        Column {
            id: annCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            Repeater {
                id: annRep
                model: app.hub.announcements
                delegate: Item {
                    width: annCol.width
                    height: Math.max(64, annText.implicitHeight + 24)
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Icon { id: li; y: 14; name: model.level === "warning" ? "warning" : model.level === "error" ? "warning-circle" : "megaphone-simple"; tone: model.level === "warning" ? "warn" : model.level === "error" ? "bad" : "muted" }
                    Column {
                        id: annText
                        anchors.left: li.right
                        anchors.leftMargin: 12
                        anchors.right: rm.left
                        anchors.rightMargin: 16
                        y: 12
                        spacing: 2
                        Txt { width: parent.width; text: model.title; strong: true }
                        Txt { width: parent.width; text: model.body; tone: "muted"; wrapMode: Text.Wrap; elide: Text.ElideNone; maximumLineCount: 3 }
                        Txt { width: parent.width; text: model.authorName + " · " + model.tsText; role: "small"; tone: "faint"; figures: true }
                    }
                    ActionButton {
                        id: rm
                        anchors.right: parent.right
                        y: 12
                        visible: model.mine
                        text: "Remove"
                        kind: "ghost"
                        small: true
                        onClicked: Window.window.safe(function () { app.hub.removeAnnouncement(model.announcementId) })
                    }
                }
            }
            EmptyBlock { visible: annRep.count === 0; width: annCol.width; line: "No announcements." }
        }
    }

    // ------------------------------------------------------------ the Activity register
    Card {
        visible: page.configured && page.tab === "activity"
        width: page.contentW
        height: regCol.implicitHeight + 2 * pad
        Column {
            id: regCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            readonly property int byW: 120
            readonly property int revW: 56
            readonly property int whenW: 90
            Repeater {
                id: regRep
                model: app.hub.register
                delegate: Column {
                    width: regCol.width
                    readonly property bool firstOfJob: index === 0 || app.hub.register.get(index - 1).job !== model.job
                    Item {
                        visible: parent.firstOfJob
                        width: parent.width
                        height: visible ? (index === 0 ? 30 : 44) : 0
                        Txt { anchors.bottom: parent.bottom; anchors.bottomMargin: 6; text: model.job; role: "heading" }
                    }
                    Item {
                        visible: parent.firstOfJob
                        width: parent.width
                        height: visible ? 24 : 0
                        Txt { text: "Event"; role: "small"; tone: "faint" }
                        Txt { x: parent.width - regCol.whenW - regCol.byW - regCol.revW - 24; width: regCol.revW; horizontalAlignment: Text.AlignRight; text: "Rev"; role: "small"; tone: "faint" }
                        Txt { x: parent.width - regCol.whenW - regCol.byW - 12; width: regCol.byW; text: "By"; role: "small"; tone: "faint" }
                        Txt { x: parent.width - regCol.whenW; width: regCol.whenW; horizontalAlignment: Text.AlignRight; text: "When"; role: "small"; tone: "faint" }
                    }
                    Item {
                        width: parent.width
                        height: 36
                        Rectangle { width: parent.width; height: 1; color: page.tk.border }
                        Txt { y: 9; width: parent.width - regCol.whenW - regCol.byW - regCol.revW - 40; text: model.event }
                        Txt { x: parent.width - regCol.whenW - regCol.byW - regCol.revW - 24; y: 9; width: regCol.revW; horizontalAlignment: Text.AlignRight; text: model.revision; figures: true; tone: "muted" }
                        Txt { x: parent.width - regCol.whenW - regCol.byW - 12; y: 9; width: regCol.byW; text: model.by; tone: "muted" }
                        Txt { x: parent.width - regCol.whenW; y: 9; width: regCol.whenW; horizontalAlignment: Text.AlignRight; text: model.whenText; figures: true; tone: "muted" }
                    }
                }
            }
            EmptyBlock { visible: regRep.count === 0; width: regCol.width; line: "Nothing recorded yet today." }
        }
    }

    // ------------------------------------------------------------ groups
    Card {
        visible: page.configured && page.tab === "groups"
        width: page.contentW
        height: grpCol.implicitHeight + 2 * pad
        Column {
            id: grpCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            Repeater {
                id: grpRep
                model: app.hub.groups
                delegate: Item {
                    width: grpCol.width
                    height: 56
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Dot { id: gd; anchors.verticalCenter: parent.verticalCenter; tint: model.dotColor; width: 8; height: 8; radius: 4 }
                    Column {
                        anchors.left: gd.right
                        anchors.leftMargin: 14
                        anchors.right: gAct.left
                        anchors.rightMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        Txt { width: parent.width; text: "@" + model.groupName + " · " + model.memberCount + (model.memberCount === 1 ? " member" : " members"); strong: true; figures: true }
                        Txt {
                            width: parent.width
                            text: (model.memberNames || (model.members || []).join(", ")) + (model.updatedBy ? " · changed by " + model.updatedBy : "")
                            role: "small"
                            tone: "faint"
                            HoverHandler { id: memHover }
                            Tip { visible: memHover.hovered; text: (model.members || []).map(function (m) { return "@" + m }).join(", ") }
                        }
                    }
                    Row {
                        id: gAct
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 4
                        ActionButton { text: "Edit"; kind: "ghost"; small: true; onClicked: Window.window.openSheet("GroupSheet", { name: model.groupName, members: model.members, color: model.dotColor }) }
                        ActionButton {
                            icon: "trash"; kind: "ghost"; small: true; tooltip: "Delete @" + model.groupName
                            onClicked: Window.window.confirm("Delete @" + model.groupName + "?", "Mentions of it stop reaching its members; nobody is removed from anything else.",
                                                             "Delete group", true, function () { Window.window.safe(function () { app.hub.deleteGroup(model.groupName) }) })
                        }
                    }
                }
            }
            EmptyBlock {
                visible: grpRep.count === 0
                width: grpCol.width
                line: "No groups yet. A group is a name for several people: @checkers, @P12513-team."
                action: "New group"
                onTriggered: Window.window.openSheet("GroupSheet", {})
            }
        }
    }
}
