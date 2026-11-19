import QtQuick
import "../components"

// Today (docs/DESIGN.md "Today"; the approved board B, "Drafted Glass"), route `home`.  Real data only
// (app.today; docs/V4-PLUS-BRIEF.md section 5): the hero (the resume after a shutdown, else the last-run
// activity, with its restore plan), four stats, then Time travel | Office pulse | Drives on this PC sharing a
// bottom edge.  One gap (14) on this screen.  The hero grows into the launch dock for any activity opened
// while Today shows (the guard and --bench measure that one grow); all opened, the dock settles into the
// activity page 1.2 s later; Esc or × closes it.  Blocks rise in once per arrival, 60 ms apart; the numerals
// count up after their rise.  Below 1000 px the panels go Time travel over Office | Drives.
Page {
    id: home
    minimumWidth: 860
    readonly property var win: Window.window
    readonly property int gap: 14
    readonly property var st: app.today.stats

    readonly property bool docked: app.activities.dockOpen && app.activities.dockId !== ""
                                   && app.activities.activities.indexOf(app.activities.dockId) >= 0
    readonly property bool projectDock: app.activities.dockOpen && app.activities.dockId !== ""
                                        && app.activities.activities.indexOf(app.activities.dockId) < 0

    // ------------------------------------------------------------ the dock (the hero grown)
    Connections {
        target: app.activities
        function onLaunchFinished(id, summary) {
            if (home.docked && id === app.activities.dockId && dockClean.allOpened()) settle.restart()
        }
    }
    // the dock opening is the one long animation: measure its frames for the runtime guard, over the grow
    // only (after it the dock idles between rows and no frame is due; juror U2-1).  The arrival finishes first.
    onDockedChanged: {
        if (docked) finishArrival()
        if (docked && app.ui.k > 0) { app.ui.beginDockMeasure(); measure.restart() }
    }
    Timer { id: measure; interval: Math.max(1, app.ui.dockMeasureMs); onTriggered: app.ui.endDockMeasure() }
    // all opened: the hero becomes the activity page (board D frame 6); otherwise the dock stays
    Timer {
        id: settle
        interval: 1200
        onTriggered: if (home.docked) { var id = app.activities.dockId; app.activities.closeDock(); app.ui.go("activity", { activityId: id }) }
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

    // ------------------------------------------------------------ arrival
    function finishArrival() {
        for (var i = 0; i < rises.length; i++) rises[i].finish()
        for (var j = 0; j < cards.length; j++) cards[j].finishCount()
        counted = true
        popDelay.stop()
        popTick.stop()
        streak.popped = 14
    }
    readonly property var rises: [riseHero, riseS0, riseS1, riseS2, riseS3, riseP0, riseP1, riseP2]
    readonly property var cards: [s0, s1, s2, s3]
    property bool counted: false
    function startCounts() {
        if (counted || !st.ready) return
        counted = true
        for (var i = 0; i < cards.length; i++) cards[i].countUp(Math.round((i + 1) * 60 * app.ui.k + 650 * app.ui.k))
        streak.start(Math.round(4 * 60 * app.ui.k + 650 * app.ui.k + 900 * app.ui.k))
    }
    onStChanged: startCounts()
    Component.onCompleted: {
        column.spacing = gap
        for (var i = 0; i < rises.length; i++) rises[i].begin()
        hero.play()
        startCounts()
    }

    // ------------------------------------------------------------ title
    Item {
        width: home.contentW
        height: 40
        Txt {
            id: title
            text: "Today"
            role: "title"
            anchors.verticalCenter: parent.verticalCenter
            Accessible.role: Accessible.Heading
        }
        Txt {
            anchors.left: title.right
            anchors.leftMargin: 12
            anchors.baseline: title.baseline
            text: Qt.formatDate(new Date(), "ddd d MMM")
            role: "label"
            figures: true
        }
        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            ActionButton {
                visible: app.capture.runningId === "" && app.activities.activityCount > 0
                text: "Start from what's open"
                icon: "browsers"
                onClicked: Window.window.startFromOpen()
            }
            ActionButton {
                visible: app.activities.activityCount > 0       // with none, the hero offers it
                text: "New activity"
                icon: "plus"
                onClicked: Window.window.openSheet("ActivityEditor", { activityId: "" })
            }
        }
    }

    // a project opened the 3.x way (palette, project page) docks here, above the hero
    Card {
        visible: home.projectDock
        radius: 8
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

    // ------------------------------------------------------------ hero
    TodayHero {
        id: hero
        objectName: "todayHero"
        width: home.contentW
        docked: home.docked
        opacity: arrive
        transform: Translate { y: (1 - hero.arrive) * (app.ui.motion === "rich" ? 12 : 0) }
        onCloseDock: { settle.stop(); app.activities.closeDock() }
        onShowActivity: { var id = app.activities.dockId; app.activities.closeDock(); app.ui.go("activity", { activityId: id }) }
    }
    Rise { id: riseHero; target: hero; index: 0 }

    // ------------------------------------------------------------ stats
    Item {
        id: stats
        objectName: "todayStats"
        width: home.contentW
        readonly property int cw: Math.floor((width - 3 * home.gap) / 4)
        height: Math.max(s0.implicitHeight, s1.implicitHeight, s2.implicitHeight, s3.implicitHeight)
        opacity: home.docked ? 0.4 : 1
        Behavior on opacity { NumberAnimation { duration: Math.round(240 * app.ui.k) } }

        StatCard {
            id: s0
            objectName: "statTasks"
            width: stats.cw; height: stats.height
            opacity: arrive
            transform: Translate { y: (1 - s0.arrive) * (app.ui.motion === "rich" ? 12 : 0) }
            label: "Tasks due today"
            value: home.st.ready ? home.st.dueToday : 0
            unit: home.st.ready ? "of " + home.st.open + " open" : ""
            line: !home.st.ready ? "" : home.st.tasksLine !== "" ? home.st.tasksLine
                : home.st.open === 0 ? "Nothing open for you" : "None overdue"
            tip: "Your open tasks due today; of all your open tasks"
        }
        StatCard {
            id: s1
            objectName: "statChanged"
            x: stats.cw + home.gap
            width: stats.cw; height: stats.height
            opacity: arrive
            transform: Translate { y: (1 - s1.arrive) * (app.ui.motion === "rich" ? 12 : 0) }
            label: "Changed overnight"
            empty: home.st.ready && home.st.changed < 0
            emptyLine: "No folder watcher yet."
            emptyAction: hero.has ? "Add a watcher" : ""
            emptyIcon: "eye"
            onEmptyTriggered: Window.window.openSheet("WatcherSheet", { activityId: hero.h.activityId, kind: "folder" })
            value: home.st.ready ? Math.max(0, home.st.changed) : 0
            unit: value === 1 ? "file" : "files"
            tip: "Files your folder watchers saw new, changed or gone since 18:00 yesterday"
            Canvas {                                     // per hour since 18:00 yesterday
                id: spark
                width: parent ? parent.width : 100
                height: 22
                readonly property var pts: home.st.ready && home.st.changedSpark ? home.st.changedSpark : []
                property color ink: home.tk.teal
                onPtsChanged: requestPaint()
                onInkChanged: requestPaint()
                onWidthChanged: requestPaint()
                onPaint: {
                    var c = getContext("2d")
                    c.reset()
                    var n = pts.length
                    if (n < 2) return
                    var mx = 1
                    for (var i = 0; i < n; i++) mx = Math.max(mx, pts[i])
                    c.strokeStyle = ink
                    c.lineWidth = 1.6
                    c.lineJoin = "round"
                    c.beginPath()
                    for (var j = 0; j < n; j++) {
                        var x = j * (width - 2) / (n - 1) + 1, y = height - 2 - pts[j] / mx * (height - 4)
                        if (j === 0) c.moveTo(x, y); else c.lineTo(x, y)
                    }
                    c.stroke()
                }
            }
        }
        StatCard {
            id: s2
            objectName: "statStreak"
            x: 2 * (stats.cw + home.gap)
            width: stats.cw; height: stats.height
            opacity: arrive
            transform: Translate { y: (1 - s2.arrive) * (app.ui.motion === "rich" ? 12 : 0) }
            label: "Day streak"
            value: home.st.ready ? home.st.streak : 0
            unit: value === 1 ? "day" : "days"
            tip: "Days in a row with something opened; a quiet Saturday or Sunday does not break it"
            Row {                                        // the last days that fit, oldest first
                id: streak
                spacing: 3
                property int popped: 14
                readonly property var days: home.st.ready && home.st.streakDays ? home.st.streakDays : []
                readonly property int fit: Math.min(days.length, Math.floor((stats.cw - 2 * (s2.pad - 2) + spacing) / (10 + spacing)))
                function start(delay) {
                    if (app.ui.k <= 0) { popped = 14; return }
                    popped = 0
                    popDelay.interval = Math.max(1, delay)
                    popDelay.restart()
                }
                Timer { id: popDelay; onTriggered: popTick.restart() }
                Timer { id: popTick; interval: 45; repeat: true; onTriggered: if (++streak.popped >= 14) stop() }
                Repeater {
                    model: streak.days.slice(streak.days.length - streak.fit)
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: 10; height: 10; radius: 2.5
                        color: modelData ? home.tk.teal : home.tk.border_strong
                        opacity: modelData ? 0.85 : 1
                        scale: index < streak.popped ? 1 : 0
                        Behavior on scale { NumberAnimation { duration: Math.round(400 * app.ui.k); easing.type: Easing.OutCubic } }
                    }
                }
            }
        }
        StatCard {
            id: s3
            objectName: "statWeek"
            x: 3 * (stats.cw + home.gap)
            width: stats.cw; height: stats.height
            opacity: arrive
            transform: Translate { y: (1 - s3.arrive) * (app.ui.motion === "rich" ? 12 : 0) }
            label: "Due this week"
            value: home.st.ready ? home.st.dueWeek : 0
            unit: value === 1 ? "task" : "tasks"
            line: !home.st.ready ? "" : "by " + home.st.weekEnd + (home.st.noDate > 0 ? " · " + home.st.noDate + " undated" : "")
            tip: "Your open tasks due from today to Sunday"
        }
        Rise { id: riseS0; target: s0; index: 1 }
        Rise { id: riseS1; target: s1; index: 2 }
        Rise { id: riseS2; target: s2; index: 3 }
        Rise { id: riseS3; target: s3; index: 4 }
    }

    // ------------------------------------------------------------ panels
    Item {
        id: panels
        objectName: "todayPanels"
        width: home.contentW
        readonly property bool stack: width < 1000
        readonly property int unit: stack ? 0 : Math.floor((width - 2 * home.gap) / 3.35)
        readonly property int ttW: stack ? width : width - 2 * home.gap - 2 * unit
        readonly property int sideW: stack ? Math.floor((width - home.gap) / 2) : unit
        readonly property int pairH: Math.max(office.implicitHeight, drives.implicitHeight)
        readonly property int rowH: Math.max(tt.implicitHeight, pairH)
        height: stack ? tt.implicitHeight + home.gap + pairH : rowH
        opacity: home.docked ? 0.4 : 1
        Behavior on opacity { NumberAnimation { duration: Math.round(240 * app.ui.k) } }

        TimeTravelPanel {
            id: tt
            objectName: "todayTimeTravel"
            width: panels.ttW
            height: panels.stack ? implicitHeight : panels.rowH
            opacity: arrive
            transform: Translate { y: (1 - tt.arrive) * (app.ui.motion === "rich" ? 12 : 0) }
        }
        OfficePanel {
            id: office
            objectName: "todayOffice"
            radius: 8
            property real arrive: 1
            x: panels.stack ? 0 : panels.ttW + home.gap
            y: panels.stack ? tt.height + home.gap : 0
            width: panels.sideW
            height: panels.stack ? panels.pairH : panels.rowH
            opacity: arrive
            transform: Translate { y: (1 - office.arrive) * (app.ui.motion === "rich" ? 12 : 0) }
        }
        DrivesPanel {
            id: drives
            objectName: "todayDrives"
            radius: 8
            property real arrive: 1
            x: panels.stack ? panels.sideW + home.gap : panels.ttW + panels.unit + 2 * home.gap
            y: office.y
            width: panels.stack ? panels.width - panels.sideW - home.gap : panels.unit
            height: office.height
            opacity: arrive
            transform: Translate { y: (1 - drives.arrive) * (app.ui.motion === "rich" ? 12 : 0) }
        }
        Rise { id: riseP0; target: tt; index: 5 }
        Rise { id: riseP1; target: office; index: 6 }
        Rise { id: riseP2; target: drives; index: 7 }
    }
}
