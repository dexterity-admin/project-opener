import QtQuick

// One activity on the stage (concept-1-stage, board A).  mode: centre (full size, the three questions in
// three columns: what was open, what is reachable on this PC, the task and watchers) | wing (smaller, dimmer,
// behind) | fold (a compact card under the centre below 1180 px).  `docked`: the centre has grown into the
// launch dock.  `m` is the delegate's model object (ACTIVITY_ROLES).
//
// The grow (juror U2, D8): only the card's frame animates.  Its content is laid out once, at `layoutWidth` (the
// size it grows to), so no frame re-lays the dock; the title row is the shared element and stays put; the
// three columns fade out at once and the dock's rows (queued ones at 35 %) are there from the first frame of
// the grow, clipped to the growing frame (juror D2-2).
// Round 2 (juror C2, C3, C4, brief 3.3): the card's edge lights in the danger colour when a drive the activity
// uses is down, with that fact as the health column's first line; the running activity's live pill sits in
// the header; a folder watcher's new files are a figure with "Save N as items"; open tasks are listed.
Card {
    id: scene
    property var m
    property string mode: "centre"
    property bool docked: false
    property bool primaryOpen: true          // the centre's Open is the screen's one filled control
    property real layoutWidth: width         // the content's width: the final width while the frame animates
    property int growMs: 0
    signal openClicked()
    signal editClicked()
    signal picked()
    signal closeDock()
    signal showActivity()

    readonly property bool centre: mode === "centre"
    readonly property bool driveDown: m ? m.driveDown === true : false
    readonly property var newFiles: m && m.newFiles ? m.newFiles : ({})
    readonly property int newCount: newFiles.count !== undefined ? newFiles.count : 0
    readonly property var openTasks: m && m.openTasks ? m.openTasks : []
    readonly property int innerW: layoutWidth - 2 * pad
    color: centre ? tk.surface : (wingMouse.containsMouse ? tk.surface_2 : tk.surface)
    border.color: driveDown && centre ? tk.danger : centre ? tk.border_strong : tk.border
    border.width: driveDown && centre ? 2 : 1
    Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k) } }
    Accessible.role: Accessible.Grouping
    Accessible.name: m ? m.title : ""

    MouseArea {
        id: wingMouse
        anchors.fill: parent
        enabled: !scene.centre
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: scene.picked()
    }

    // ------------------------------------------------------------ heading (every mode; the dock keeps it)
    Item {
        id: head
        x: scene.pad
        y: scene.pad
        width: scene.innerW
        height: scene.centre ? 40 : Math.max(40, titleCol.implicitHeight)
        IconTile { id: tile; icon: scene.m ? scene.m.icon : "stack"; tint: scene.m ? scene.m.dotColor : ""; size: scene.centre ? 36 : 30 }
        Column {
            id: titleCol
            anchors.left: tile.right
            anchors.leftMargin: 12
            anchors.right: stateBox.left
            anchors.rightMargin: 8
            anchors.verticalCenter: tile.verticalCenter
            spacing: 2
            Txt {                                // a wing's title wraps rather than reading as clipped (D2)
                id: titleText
                width: parent.width
                text: scene.m ? scene.m.title : ""
                role: "heading"
                wrapMode: scene.centre ? Text.NoWrap : Text.Wrap
                maximumLineCount: scene.centre ? 1 : 2
            }
            Txt {                                // a wing's line wraps too: its facts are never cut (juror D2-3)
                width: parent.width
                text: scene.docked ? app.activities.dockLine : scene.m ? scene.m.subtitle : ""
                role: "small"; tone: "muted"; figures: true
                wrapMode: scene.centre ? Text.NoWrap : Text.Wrap
                maximumLineCount: scene.centre ? 1 : 2
            }
        }
        Item {
            id: stateBox
            anchors.right: parent.right
            anchors.verticalCenter: tile.verticalCenter
            width: !scene.centre ? 0 : scene.docked ? closeBtn.width : livePill.visible ? livePill.width : statePill.width
            height: 28
            LivePill {
                id: livePill
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                visible: scene.centre && !scene.docked && scene.m && scene.m.running
            }
            StatusPill {
                id: statePill
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                visible: scene.centre && !scene.docked && !(scene.m && scene.m.running) && label !== ""
                status: "neutral"
                label: !scene.m ? "" : scene.m.pausedAt !== "" ? "Paused" : scene.m.pinned ? "Pinned" : ""
            }
            ActionButton {
                id: closeBtn
                visible: scene.docked
                opacity: dockView.opacity             // arrives with the dock, at the grown frame's edge
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                kind: "ghost"
                icon: "x"
                tooltip: "Close (Esc)"
                onClicked: scene.closeDock()
            }
        }
    }

    // ------------------------------------------------------------ centre: the three questions
    Row {
        id: cols
        visible: opacity > 0
        opacity: scene.centre && !scene.docked ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Math.round(120 * app.ui.k) } }
        x: scene.pad
        anchors.top: head.bottom
        anchors.topMargin: 18
        width: scene.innerW
        spacing: 24
        readonly property real unit: (width - 2 * spacing) / 3.2       // the third column takes 1.2 (juror D2)
        readonly property int colW: Math.floor(unit)
        readonly property int col3W: Math.floor(unit * 1.2)

        Column {                                    // what was open
            width: cols.colW
            spacing: 6
            Txt { text: "Open last time · " + (scene.m ? scene.m.itemCount : 0); role: "small"; tone: "muted"; figures: true }
            Repeater {
                model: scene.m ? scene.m.previewNames.slice(0, 4) : []
                delegate: Row {
                    required property var modelData
                    required property int index
                    spacing: 8
                    width: cols.colW
                    Icon { name: scene.m.previewGlyphs[index] || "file"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                    Txt { text: parent.modelData; width: cols.colW - 22; anchors.verticalCenter: parent.verticalCenter }
                }
            }
            Txt {
                readonly property int more: scene.m ? scene.m.itemCount - Math.min(4, scene.m.previewNames.length) : 0
                visible: more > 0
                text: "+" + more + " more, in launch order"
                tone: "muted"
                figures: true
            }
            Txt {
                visible: scene.m && scene.m.itemCount === 0
                width: cols.colW
                text: "No items yet."
                tone: "muted"
            }
        }
        Column {                                    // what is reachable on this PC
            width: cols.colW
            spacing: 6
            Txt { text: "Health on this PC"; role: "small"; tone: "muted" }
            Row {                                    // the drive that is down: the one fact only this app knows
                visible: scene.driveDown
                spacing: 8
                width: cols.colW
                Rectangle { width: 8; height: 8; radius: 4; color: scene.tk.danger; anchors.verticalCenter: parent.verticalCenter }
                Txt {
                    width: cols.colW - 16
                    text: scene.m ? scene.m.driveText : ""
                    tone: "bad"
                    strong: true
                    figures: true
                    wrapMode: Text.Wrap
                    elide: Text.ElideNone
                    maximumLineCount: 2
                }
            }
            Repeater {
                model: scene.m ? scene.m.problems : []
                delegate: Item {
                    required property var modelData
                    width: cols.colW
                    height: 22
                    Txt { text: parent.modelData.name; width: parent.width - p.width - 8; anchors.verticalCenter: parent.verticalCenter }
                    StatusPill { id: p; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; status: parent.modelData.level; label: parent.modelData.label }
                }
            }
            Txt {
                text: !scene.m ? "" : scene.m.okCount > 0 ? scene.m.okCount + " reachable"
                     : scene.m.healthWorst === "" ? (scene.m.itemCount > 0 ? "Checking the paths…" : "No paths to check yet.") : ""
                visible: text !== ""
                tone: "muted"
                figures: true
            }
        }
        Column {                                    // the task and the watchers
            width: cols.col3W
            spacing: 6
            Txt { text: "Tasks and watchers"; role: "small"; tone: "muted" }
            Item {                                  // a folder watcher's new files, as a figure (juror C4, brief 3.8)
                visible: scene.newCount > 0
                width: cols.col3W
                height: visible ? 52 : 0
                Txt {
                    id: fig
                    text: String(scene.newCount)
                    role: "kpi"
                    figures: true
                    anchors.left: parent.left
                    anchors.top: parent.top
                }
                Column {
                    anchors.left: fig.right
                    anchors.leftMargin: 10
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.topMargin: 2
                    spacing: 4
                    Txt {
                        width: parent.width
                        text: (scene.newFiles.text || "").replace(/^\d+\s*/, "") + (scene.newFiles.timeText ? " · " + scene.newFiles.timeText : "")
                        figures: true
                    }
                    ActionButton {
                        text: "Save " + scene.newCount + " as items"
                        kind: "link"
                        small: true
                        x: -10
                        onClicked: Window.window.safe(function () {
                            app.activities.addPaths(scene.m.activityId, scene.newFiles.paths)
                            var keys = scene.newFiles.keys || []
                            for (var i = 0; i < keys.length; i++) app.watchers.markRead(keys[i])
                        })
                    }
                }
            }
            Repeater {                              // the open tasks on this activity (brief 3.3)
                model: scene.openTasks.slice(0, scene.newCount > 0 ? 1 : 2)
                // the due date in its own right-aligned column: the title elides, never the date (juror D2-3)
                delegate: Item {
                    required property var modelData
                    width: cols.col3W
                    height: Math.max(20, taskTitle.implicitHeight)
                    Icon { id: taskGlyph; name: "check-square"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                    Txt {
                        id: taskDue
                        objectName: "taskDue"
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        text: parent.modelData.dueText || ""
                        tone: parent.modelData.overdue ? "warn" : "muted"
                        figures: true
                        elide: Text.ElideNone
                    }
                    Txt {
                        id: taskTitle
                        objectName: "taskTitle"
                        anchors.left: taskGlyph.right
                        anchors.leftMargin: 8
                        anchors.right: taskDue.left
                        anchors.rightMargin: taskDue.text !== "" ? 10 : 0
                        anchors.verticalCenter: parent.verticalCenter
                        text: parent.modelData.title
                        tone: parent.modelData.overdue ? "warn" : "ink"
                    }
                }
            }
            Repeater {
                model: app.watchers.watchers
                delegate: Row {
                    visible: scene.m && model.activityId === scene.m.activityId && model.watcherEnabled
                             && !(model.kind === "folder" && scene.newCount > 0)
                    height: visible ? implicitHeight : 0
                    spacing: 8
                    Icon { name: model.kind === "health" ? "bell" : "eye"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                    Txt {
                        text: model.name + (model.lastHitText !== "" ? " · " + model.lastHitText : "")
                        width: cols.col3W - 22
                        figures: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
            ActionButton {
                visible: scene.openTasks.length === 0
                text: "Add a task"
                icon: "plus"
                kind: "link"
                small: true
                x: -10
                onClicked: Window.window.openSheet("TaskSheet", { attachKind: "activity", attachId: scene.m.activityId })
            }
        }
    }

    Item {                                          // centre footer
        visible: scene.centre && !scene.docked
        x: scene.pad
        width: scene.innerW
        height: 34
        anchors.bottom: parent.bottom
        anchors.bottomMargin: scene.pad
        Row {
            id: footBtns
            spacing: 8
            ActionButton {
                text: "Open activity"
                icon: "play"
                kind: scene.primaryOpen ? "primary" : "outline"
                onClicked: scene.openClicked()
            }
            ActionButton { text: "Edit"; kind: "ghost"; onClicked: scene.editClicked() }
        }
        Txt {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: Math.min(implicitWidth, parent.width - footBtns.width - 16)
            horizontalAlignment: Text.AlignRight
            text: scene.m ? scene.m.captureText : ""
            role: "small"
            tone: "muted"
            figures: true
        }
    }

    // ------------------------------------------------------------ wing / fold body
    Column {
        id: wingBody
        visible: !scene.centre
        x: scene.pad
        anchors.top: head.bottom
        anchors.topMargin: 14
        width: scene.innerW
        spacing: 6
        Repeater {
            model: scene.m && scene.mode === "wing" ? scene.m.previewNames.slice(0, 2) : []
            delegate: Row {
                required property var modelData
                required property int index
                spacing: 8
                Icon { name: scene.m.previewGlyphs[index] || "file"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                Txt { text: parent.modelData; width: scene.innerW - 22; tone: "muted"; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
    Item {
        id: wingFoot
        visible: !scene.centre
        x: scene.pad
        width: scene.innerW
        height: 28
        anchors.bottom: parent.bottom
        anchors.bottomMargin: scene.pad - 4
        // Open only: the task line lives on the centre card and the Activities list, and the wing's own line
        // already says how many items and when it was last opened (juror D2-3)
        ActionButton {
            id: wingOpen
            text: "Open activity"
            small: true
            onClicked: scene.openClicked()
        }
    }
    // a wing is as tall as what it shows (juror D1): heading, two lines, the Open button
    readonly property int wingHeight: pad + head.height + 14 + wingBody.implicitHeight + 16 + 28 + pad - 4

    // ------------------------------------------------------------ the dock (the centre grown)
    DockView {
        id: dockView
        visible: scene.docked
        embedded: true
        opacity: 0
        x: scene.pad
        anchors.top: head.bottom
        anchors.topMargin: 8
        width: scene.innerW
        onCloseRequested: scene.closeDock()
        onShowActivity: scene.showActivity()
    }
    // the rows are laid out at their final width (no per-frame layout) and come in as the columns' 120 ms
    // fade-out ends (from 100 ms, over 140 ms), so the growing frame is never empty and the two never read on
    // top of each other (round 3: a crossfade showed both layers of text mid-grow); the frame clips them until
    // it has reached its size
    property bool growing: false
    clip: growing
    onDockedChanged: {
        if (docked && app.ui.k > 0) { dockView.opacity = 0; growing = true; dockIn.restart() }
        else { dockIn.stop(); growing = false; dockView.opacity = docked ? 1 : 0 }
    }
    SequentialAnimation {
        id: dockIn
        PauseAnimation { duration: Math.round(100 * app.ui.k) }
        NumberAnimation { target: dockView; property: "opacity"; to: 1; duration: Math.round(140 * app.ui.k); easing.type: Easing.OutCubic }
        PauseAnimation { duration: Math.max(0, scene.growMs - Math.round(240 * app.ui.k)) }
        ScriptAction { script: scene.growing = false }
    }
    Component.onCompleted: if (docked) dockView.opacity = 1
    readonly property int dockHeight: pad + head.height + 8 + dockView.implicitHeight + pad
}
