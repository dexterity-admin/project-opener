import QtQuick
import "../components"

// Home as a stage (concept-1-stage, board A): the Resume band; the current activity in the centre at full
// size with the others in the wings (they fold under the centre below 1180 px); opening it grows the centre
// into the launch dock while the wings recede (board D); the footlights strip: Drives on this PC, My tasks,
// the Office.  One filled control: Resume while a resume waits, else the centre's Open activity, else (no
// activities) Start from what's open.
Page {
    id: home
    minimumWidth: 860
    readonly property var win: Window.window

    // "Lot 7 check" -> "lot 7 check" mid-sentence; an acronym or job number stays ("PO4 test", "P12513") (ui/text.first_lower)
    function firstLower(t) {
        if (t.length > 1 && t[0] !== t[0].toLowerCase() && t[1] === t[1].toLowerCase() && !/[0-9]/.test(t[1]))
            return t[0].toLowerCase() + t.slice(1)
        return t
    }

    readonly property bool resumeWaiting: app.activities.resume.activityId !== undefined && app.activities.resume.activityId !== ""
    readonly property bool wide: home.width >= 1180
    readonly property int n: rep.count
    property string centreId: ""
    property int centreIndex: 0
    property int rev: 0                      // bumps on every activities refresh (bindings that read rows by get())
    readonly property bool docked: app.activities.dockOpen && centreId !== "" && app.activities.dockId === centreId
    readonly property bool projectDock: app.activities.dockOpen && app.activities.dockId !== ""
                                        && app.activities.activities.indexOf(app.activities.dockId) < 0
    readonly property int sceneH: 330
    readonly property int foldH: 150

    function relocate() {
        var m = app.activities.activities
        var i = centreId === "" ? -1 : m.indexOf(centreId)
        if (i < 0) {
            i = 0
            var rid = app.activities.resume.activityId
            if (rid !== undefined && rid !== "" && m.indexOf(rid) >= 0) i = m.indexOf(rid)
            centreId = m.count() > 0 ? m.get(i).activityId : ""
        }
        centreIndex = Math.max(0, i)
    }
    Connections {
        target: app.activities.activities
        function onModelReset() { home.relocate() }
        function onRowsInserted() { home.relocate() }
        function onRowsRemoved() { home.relocate() }
        function onRowsMoved() { home.relocate() }
    }
    Connections {
        target: app.activities
        function onActivitiesChanged() { home.rev++ }
        function onLaunchStarted(id) {
            if (app.activities.activities.indexOf(id) >= 0) { home.centreId = id; home.relocate() }
        }
        function onLaunchFinished(id, summary) {
            if (id === home.centreId && dockClean.allOpened()) settle.restart()
        }
    }
    Component.onCompleted: relocate()

    // the dock opening is the one long animation: measure its frames for the runtime guard
    onDockedChanged: {
        if (docked && app.ui.k > 0) { app.ui.beginDockMeasure(); measure.restart() }
    }
    Timer { id: measure; interval: 1400; onTriggered: app.ui.endDockMeasure() }
    // all opened: the scene becomes the activity page (board D frame 6); otherwise the dock stays
    Timer {
        id: settle
        interval: 1200
        onTriggered: if (home.docked) { var id = home.centreId; app.activities.closeDock(); app.ui.go("activity", { activityId: id }) }
    }
    QtObject {
        id: dockClean
        function allOpened() {
            var m = app.activities.dock
            for (var i = 0; i < m.count(); i++) if (m.get(i).status !== "opened") return false
            return m.count() > 0
        }
    }
    Shortcut {
        sequence: "Esc"
        enabled: (home.docked || home.projectDock) && home.win !== null && home.win.lastSheet === ""
        onActivated: { settle.stop(); app.activities.closeDock() }
    }

    function roleOf(i) {
        if (n === 0) return "hidden"
        if (i === centreIndex) return "centre"
        if (n === 2) return "right"
        if (i === (centreIndex + 1) % n) return "right"
        if (i === (centreIndex - 1 + n) % n) return "left"
        return "hidden"
    }
    function openScene(id) {
        settle.stop()
        centreId = id
        relocate()
        app.activities.open(id)
    }

    // ------------------------------------------------------------ title
    PageHeader {
        title: greeting() + ", " + app.displayName
        subtitle: home.finding()
        ActionButton {
            visible: app.capture.runningId === "" && home.n > 0
            text: "Start from what's open"
            icon: "browsers"
            onClicked: Window.window.startFromOpen()
        }
        ActionButton {
            text: "New activity"
            icon: "plus"
            onClicked: Window.window.openSheet("ActivityEditor", { activityId: "" })
        }
    }
    function greeting() {
        var h = new Date().getHours()
        return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"
    }
    function finding() {
        var parts = []
        if (home.resumeWaiting) parts.push("1 activity to resume")
        if (app.capture.runningId !== "") parts.push(app.capture.runningName + " running")
        if (footlights.downCount > 0) parts.push(footlights.downCount + (footlights.downCount === 1 ? " drive down" : " drives down") + " on this PC")
        if (app.hub.configured) parts.push(app.hub.peersOnline + (app.hub.peersOnline === 1 ? " colleague online" : " colleagues online"))
        if (app.tasks.mineOpenCount > 0) parts.push(app.tasks.mineOpenCount + (app.tasks.mineOpenCount === 1 ? " task open" : " tasks open"))
        if (parts.length === 0) parts.push(home.n === 0 ? "Nothing open yet" : home.n + (home.n === 1 ? " activity" : " activities"))
        return parts.join(" · ")
    }

    ResumeBand { width: home.contentW }

    // a project opened the 3.x way (palette, project page) docks here, above the stage
    Card {
        visible: home.projectDock
        width: home.contentW
        height: visible ? projectDockView.implicitHeight + 2 * pad : 0
        DockView {
            id: projectDockView
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            onCloseRequested: app.activities.closeDock()
            onShowActivity: { app.activities.closeDock(); app.ui.go("project", { projectId: app.activities.dockId }) }
        }
    }

    // ------------------------------------------------------------ the stage
    Item {
        width: home.contentW
        height: 30
        visible: home.n > 0
        SectionHeading {
            anchors.left: parent.left
            anchors.right: allLink.left
            anchors.rightMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            title: "Activities"
            facts: {
                var m = app.activities.activities
                var f = String(home.n) + (home.rev < 0 ? "" : "")
                if (home.centreIndex < m.count()) {
                    var r = m.get(home.centreIndex)
                    if (r.running) f += " · " + home.firstLower(r.name) + " running"
                    else if (r.pausedText !== "") f += " · " + home.firstLower(r.name) + " " + r.pausedText
                }
                return f
            }
        }
        ActionButton {
            id: allLink
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "All activities"
            icon: "arrow-right"
            kind: "ghost"
            small: true
            onClicked: app.ui.go("activities", ({}))
        }
    }

    Item {
        id: stage
        visible: home.n > 0
        width: home.contentW
        readonly property int dockH: centreScene ? centreScene.dockHeight : 400
        property var centreScene: null
        height: home.docked ? Math.max(home.sceneH, dockH)
              : home.wide || home.n === 1 ? home.sceneH : home.sceneH + 16 + home.foldH
        Behavior on height { NumberAnimation { duration: Math.round(420 * app.ui.k); easing.type: Easing.OutCubic } }

        Repeater {
            id: rep
            model: app.activities.activities
            delegate: Scene {
                id: sc
                m: model
                readonly property string slot: home.roleOf(index)
                readonly property real sw: stage.width
                readonly property int wingW: Math.round(sw * 0.28)
                readonly property int centreW: home.n === 1 ? sw : home.n === 2 && home.wide ? Math.round(sw * 0.64) : Math.round(sw * 0.48)
                mode: slot === "centre" ? "centre" : (home.wide ? "wing" : "fold")
                docked: slot === "centre" && home.docked
                primaryOpen: !home.resumeWaiting
                visible: slot !== "hidden" && opacity > 0.01
                z: slot === "centre" ? 2 : 1
                transformOrigin: Item.Center

                x: docked || !home.wide && slot === "centre" ? 0
                 : slot === "centre" ? (home.n === 2 ? 0 : (sw - centreW) / 2)
                 : home.wide ? (slot === "left" ? 0 : sw - wingW)
                 : (slot === "left" ? 0 : (home.n === 2 ? 0 : (sw + 16) / 2))
                y: slot === "centre" ? 0 : home.wide ? 26 : home.sceneH + 16
                width: docked || slot === "centre" && !home.wide ? sw
                     : slot === "centre" ? centreW
                     : home.wide ? wingW : (home.n === 2 ? sw : (sw - 16) / 2)
                height: docked ? stage.dockH : slot === "centre" ? home.sceneH : home.wide ? home.sceneH - 52 : home.foldH
                opacity: slot === "hidden" ? 0 : home.docked && slot !== "centre" ? 0 : slot === "centre" ? 1 : home.wide ? 0.62 : 0.9
                scale: home.docked && slot !== "centre" ? 0.84 : slot === "centre" || !home.wide ? 1 : 0.94

                Behavior on x { NumberAnimation { duration: Math.round(420 * app.ui.k); easing.type: Easing.OutCubic } }
                Behavior on y { NumberAnimation { duration: Math.round(420 * app.ui.k); easing.type: Easing.OutCubic } }
                Behavior on width { NumberAnimation { duration: Math.round(420 * app.ui.k); easing.type: Easing.OutCubic } }
                Behavior on height { NumberAnimation { duration: Math.round(420 * app.ui.k); easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: Math.round(240 * app.ui.k); easing.type: Easing.OutCubic } }
                Behavior on scale { NumberAnimation { duration: Math.round(300 * app.ui.k); easing.type: Easing.OutCubic } }

                onSlotChanged: if (slot === "centre") stage.centreScene = sc
                Component.onCompleted: if (slot === "centre") stage.centreScene = sc
                onPicked: { home.centreId = model.activityId; home.relocate() }
                onOpenClicked: home.openScene(model.activityId)
                onEditClicked: Window.window.openSheet("ActivityEditor", { activityId: model.activityId })
                onCloseDock: { settle.stop(); app.activities.closeDock() }
                onShowActivity: { var id = model.activityId; app.activities.closeDock(); app.ui.go("activity", { activityId: id }) }
            }
        }
    }

    Card {
        visible: home.n === 0
        width: home.contentW
        height: 200
        Column {
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            spacing: 12
            Txt { text: "No activities yet"; role: "heading" }
            Txt {
                width: Math.min(520, parent.width)
                text: "Open what a task needs the usual way, then turn the open windows into an activity in one step."
                tone: "muted"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
            }
            Row {
                spacing: 8
                ActionButton { text: "Start from what's open"; icon: "browsers"; kind: "primary"; onClicked: Window.window.startFromOpen() }
                ActionButton { text: "New activity"; icon: "plus"; onClicked: Window.window.openSheet("ActivityEditor", { activityId: "" }) }
            }
        }
    }

    // ------------------------------------------------------------ footlights
    Footlights {
        id: footlights
        width: home.contentW
        dimmed: home.docked
    }
}
