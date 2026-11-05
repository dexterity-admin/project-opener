import QtQuick
import "../components"
import "../sheets"

// A project (DESIGN.md "Project page"): the icon tile on the title's line, the title (job number first), its
// line, the tags and the meta line on one left edge; the items in order with their portable paths and the
// same health pills; beside them the activities that draw from the job and the notes (they stack under the
// items below 1000 px).  "Open project" is the primary (disabled with the reason when nothing is enabled).
Page {
    id: page
    minimumWidth: 860
    readonly property string tint: { var m = app.activities.projects; var i = m.indexOf(page.projectId); return i >= 0 ? m.get(i).dotColor : "" }
    readonly property string projectId: app.ui.routePayload.projectId || ""
    readonly property var proj: app.activities.currentProject
    readonly property bool known: proj.projectId !== undefined && proj.projectId === projectId
    readonly property bool stack: contentW < 1000

    Component.onCompleted: { var id = page.projectId; Qt.callLater(function () { app.activities.selectProject(id) }) }

    function menuAction(a) {
        var w = Window.window
        switch (a) {
        case "edit": w.openSheet("ProjectEditor", { projectId: page.projectId }); break
        case "pin": app.activities.toggleProjectPin(page.projectId); break
        case "activity": app.activities.newActivityFromProject(page.projectId); break
        case "publish": w.openSheet("PublishSheet", { mode: "project", targetId: page.projectId }); break
        case "send": w.openSheet("PublishSheet", { mode: "send-project", targetId: page.projectId }); break
        case "group": w.safe(function () {
            var name = app.hub.groupFromProject(page.projectId)
            if (name) w.toast("Group @" + name + " made", "Everyone holding this job is in it.", "success")
        }, "Groups arrive with the Team Hub update."); break
        case "task": w.openSheet("TaskSheet", { attachKind: "project", attachId: page.projectId }); break
        case "delete": w.confirm("Delete " + proj.title + "?",
                                 "Its " + proj.itemCount + " items go from this PC; activities keep their own copies.",
                                 "Delete project", true, function () { app.activities.removeProject(page.projectId); app.ui.go("projects", ({})) }); break
        }
    }

    PageHeader {
        back: "Back"
        onBackClicked: app.ui.back()
        title: page.known ? proj.title : "Project not found"
        subtitle: page.known ? proj.subtitle : "It may have been deleted on this PC."
        icon: page.known ? proj.icon : ""
        tint: page.known ? proj.dotColor : ""
        ActionButton {
            visible: page.known
            text: "Add items"
            icon: "plus"
            onClicked: {
                var paths = app.settings.browseFiles("Add items to " + proj.title, "")
                if (paths.length > 0) app.activities.addProjectPaths(page.projectId, paths)
            }
        }
        ActionButton {
            visible: page.known
            text: "Open project"
            icon: "play"
            kind: "primary"
            available: page.known && proj.itemCount > 0
            tooltip: page.known && proj.itemCount === 0 ? "Nothing to open: add items first" : ""
            onClicked: app.activities.openProject(page.projectId)
        }
        MenuButton {
            visible: page.known
            entries: [
                { text: "Edit project", icon: "pencil-simple", action: "edit" },
                { text: proj.pinned ? "Unpin" : "Pin", icon: "push-pin", action: "pin" },
                { text: "New activity from this job", icon: "stack", action: "activity" },
                { text: "-" },
                { text: "Publish to Team Hub", icon: "share-network", action: "publish" },
                { text: "Send to a colleague", icon: "paper-plane-tilt", action: "send" },
                { text: "Make a group of everyone on this job", icon: "users-three", action: "group" },
                { text: "New task", icon: "check-square", action: "task" },
                { text: "-" },
                { text: "Delete project", icon: "trash", action: "delete", danger: true }
            ]
            onTriggered: (a) => page.menuAction(a)
        }
    }

    LaunchDock { width: page.contentW; forId: page.projectId }

    // tags and the meta line share the title's left edge
    Row {
        visible: page.known
        spacing: 12
        Row {
            spacing: 6
            anchors.verticalCenter: parent.verticalCenter
            Repeater {
                model: page.known ? proj.tags : []
                delegate: Chip { required property var modelData; text: modelData }
            }
        }
        Txt {
            text: page.known ? proj.metaLine : ""
            tone: "faint"
            figures: true
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Item {
        id: cols
        visible: page.known
        width: page.contentW
        readonly property int sideW: page.stack ? width : 320
        readonly property int mainW: page.stack ? width : width - sideW - 16
        height: page.stack ? items.height + 16 + side.height : Math.max(items.height, side.height)

        Card {
            id: items
            width: cols.mainW
            height: itemsCol.implicitHeight + 2 * pad
            Column {
                id: itemsCol
                x: items.pad; y: items.pad
                width: items.width - 2 * items.pad
                spacing: 12
                SectionHeading {
                    width: parent.width
                    title: "Items"
                    facts: page.known ? proj.healthText : ""
                }
                ItemsList {
                    width: parent.width
                    items: app.activities.projectItems
                    onOpenItem: (id) => app.activities.openProjectItem(page.projectId, id)
                    onEditItem: (id) => Window.window.openSheet("ItemEditor", { projectId: page.projectId, itemId: id })
                }
            }
        }

        Column {
            id: side
            x: page.stack ? 0 : cols.mainW + 16
            y: page.stack ? items.height + 16 : 0
            width: cols.sideW
            spacing: 16

            Card {
                id: actsCard
                width: parent.width
                height: actsCol.implicitHeight + 2 * pad
                Column {
                    id: actsCol
                    x: actsCard.pad; y: actsCard.pad
                    width: actsCard.width - 2 * actsCard.pad
                    spacing: 8
                    SectionHeading {
                        width: parent.width
                        title: "Activities"
                        facts: page.known && proj.activityNames.length > 0 ? String(proj.activityNames.length) : ""
                    }
                    Repeater {
                        model: page.known ? proj.activityNames : []
                        delegate: Item {
                            required property var modelData
                            required property int index
                            width: actsCol.width
                            height: 36
                            Icon { id: ai; anchors.verticalCenter: parent.verticalCenter; name: "stack" }
                            Txt {
                                anchors.left: ai.right
                                anchors.leftMargin: 10
                                anchors.right: parent.right
                                anchors.verticalCenter: parent.verticalCenter
                                text: parent.modelData
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: app.ui.go("activity", { activityId: page.proj.activityIds[parent.index] })
                            }
                        }
                    }
                    Txt {
                        visible: page.known && proj.activityNames.length === 0
                        width: parent.width
                        text: "No activity draws from this job yet."
                        tone: "muted"
                        wrapMode: Text.Wrap
                        elide: Text.ElideNone
                    }
                    ActionButton {
                        text: "New activity from this job"
                        icon: "plus"
                        small: true
                        onClicked: app.activities.newActivityFromProject(page.projectId)
                    }
                }
            }
            Card {
                id: notes
                width: parent.width
                height: notesCol.implicitHeight + 2 * pad
                Column {
                    id: notesCol
                    x: notes.pad; y: notes.pad
                    width: notes.width - 2 * notes.pad
                    spacing: 8
                    SectionHeading { width: parent.width; title: "Notes" }
                    Txt {
                        width: parent.width
                        text: page.known && proj.notes !== "" ? proj.notes : "No notes. Rulings, contacts and the share's quirks belong here."
                        tone: page.known && proj.notes !== "" ? "ink" : "muted"
                        wrapMode: Text.Wrap
                        elide: Text.ElideNone
                    }
                    ActionButton {
                        text: "Edit notes"
                        icon: "pencil-simple"
                        kind: "ghost"
                        small: true
                        onClicked: Window.window.openSheet("ProjectEditor", { projectId: page.projectId, focusField: "notes" })
                    }
                }
            }
        }
    }

    EmptyBlock {
        visible: !page.known
        width: page.contentW
        line: "This project is not in your workspace."
        action: "All projects"
        onTriggered: app.ui.go("projects", ({}))
    }

}
