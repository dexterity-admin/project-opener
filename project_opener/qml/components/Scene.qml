import QtQuick

// One activity on the stage (concept-1-stage, board A).  mode: centre (full size, the three questions in
// three columns: what was open, what is reachable on this PC, the task and watchers) | wing (smaller, dimmer,
// behind) | fold (a compact card under the centre below 1180 px).  `docked`: the centre has grown into the
// launch dock.  `m` is the delegate's model object (ACTIVITY_ROLES).
Card {
    id: scene
    property var m
    property string mode: "centre"
    property bool docked: false
    property bool primaryOpen: true          // the centre's Open is the screen's one filled control
    signal openClicked()
    signal editClicked()
    signal picked()
    signal closeDock()
    signal showActivity()

    readonly property bool centre: mode === "centre"
    color: centre ? tk.surface : (wingMouse.containsMouse ? tk.surface_2 : tk.surface)
    border.color: centre ? tk.border_strong : tk.border
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

    // ------------------------------------------------------------ heading (all modes but docked)
    Item {
        id: head
        visible: !scene.docked
        x: scene.pad
        y: scene.pad
        width: scene.width - 2 * scene.pad
        height: 40
        IconTile { id: tile; icon: scene.m ? scene.m.icon : "stack"; tint: scene.m ? scene.m.dotColor : ""; size: scene.centre ? 36 : 30 }
        Column {
            anchors.left: tile.right
            anchors.leftMargin: 12
            anchors.right: statePill.left
            anchors.rightMargin: 8
            anchors.verticalCenter: tile.verticalCenter
            spacing: 2
            Txt { width: parent.width; text: scene.m ? scene.m.title : ""; role: "heading" }
            Txt { width: parent.width; text: scene.m ? scene.m.subtitle : ""; role: "small"; tone: "muted"; figures: true }
        }
        StatusPill {
            id: statePill
            anchors.right: parent.right
            anchors.verticalCenter: tile.verticalCenter
            visible: scene.centre && label !== ""
            status: scene.m && scene.m.running ? "ok" : "neutral"
            label: !scene.m ? "" : scene.m.running ? "Running" : scene.m.pausedAt !== "" ? "Paused" : scene.m.pinned ? "Pinned" : ""
        }
    }

    // ------------------------------------------------------------ centre: the three questions
    Row {
        id: cols
        visible: scene.centre && !scene.docked
        x: scene.pad
        anchors.top: head.bottom
        anchors.topMargin: 18
        width: scene.width - 2 * scene.pad
        spacing: 24
        readonly property int colW: Math.floor((width - 2 * spacing) / 3)

        Column {                                    // what was open
            width: cols.colW
            spacing: 6
            Txt { text: "Open last time · " + (scene.m ? scene.m.itemCount : 0); role: "small"; tone: "faint"; figures: true }
            Repeater {
                model: scene.m ? scene.m.previewNames : []
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
                visible: scene.m && scene.m.previewMore > 0
                text: "+" + (scene.m ? scene.m.previewMore : 0) + " more, in launch order"
                tone: "faint"
                figures: true
            }
            Txt {
                visible: scene.m && scene.m.itemCount === 0
                width: cols.colW
                text: "No items yet. Add files, folders or links, or save what is open while it runs."
                tone: "muted"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
            }
        }
        Column {                                    // what is reachable on this PC
            width: cols.colW
            spacing: 6
            Txt { text: "Health on this PC"; role: "small"; tone: "faint" }
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
                tone: "faint"
                figures: true
            }
        }
        Column {                                    // the task and the watchers
            width: cols.colW
            spacing: 6
            Txt { text: "Task and watchers"; role: "small"; tone: "faint" }
            Row {
                visible: scene.m && scene.m.taskLine !== ""
                spacing: 8
                Icon { name: "check-square"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                Txt { text: scene.m ? scene.m.taskLine : ""; width: cols.colW - 22; anchors.verticalCenter: parent.verticalCenter }
            }
            Repeater {
                model: app.watchers.watchers
                delegate: Row {
                    visible: scene.m && model.activityId === scene.m.activityId && model.watcherEnabled
                    height: visible ? implicitHeight : 0
                    spacing: 8
                    Icon { name: model.kind === "health" ? "bell" : "eye"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                    Txt {
                        text: model.name + (model.lastHitText !== "" ? " · " + model.lastHitText : "")
                        width: cols.colW - 22
                        figures: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
            ActionButton {
                visible: scene.m && scene.m.taskLine === ""
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
        width: scene.width - 2 * scene.pad
        height: 34
        anchors.bottom: parent.bottom
        anchors.bottomMargin: scene.pad
        Row {
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
            width: Math.min(implicitWidth, parent.width - 260)
            text: scene.m ? scene.m.captureText : ""
            role: "small"
            tone: "faint"
            figures: true
        }
    }

    // ------------------------------------------------------------ wing / fold body
    Column {
        visible: !scene.centre
        x: scene.pad
        anchors.top: head.bottom
        anchors.topMargin: 14
        width: scene.width - 2 * scene.pad
        spacing: 6
        Repeater {
            model: scene.m && scene.mode === "wing" ? scene.m.previewNames.slice(0, 3) : []
            delegate: Row {
                required property var modelData
                required property int index
                spacing: 8
                Icon { name: scene.m.previewGlyphs[index] || "file"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                Txt { text: parent.modelData; width: scene.width - 2 * scene.pad - 22; tone: "muted"; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }
    Item {
        visible: !scene.centre
        x: scene.pad
        width: scene.width - 2 * scene.pad
        height: 28
        anchors.bottom: parent.bottom
        anchors.bottomMargin: scene.pad - 4
        ActionButton {
            id: wingOpen
            text: "Open activity"
            small: true
            onClicked: scene.openClicked()
        }
        Txt {
            anchors.left: wingOpen.right
            anchors.leftMargin: 10
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: scene.m ? (scene.m.taskLine !== "" ? scene.m.taskLine : scene.m.lastOpenedText) : ""
            role: "small"
            tone: "faint"
            figures: true
        }
    }

    // ------------------------------------------------------------ the dock (the centre grown)
    DockView {
        id: dockView
        visible: scene.docked
        opacity: scene.docked ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Math.round(180 * app.ui.k) } }
        x: scene.pad
        y: scene.pad
        width: scene.width - 2 * scene.pad
        onCloseRequested: scene.closeDock()
        onShowActivity: scene.showActivity()
    }
    readonly property int dockHeight: dockView.implicitHeight + 2 * pad
}
