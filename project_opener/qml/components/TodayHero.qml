import QtQuick

// Today's hero (docs/DESIGN.md "Today"; data: app.today.hero).  A card with a 2 px accent rule on its top edge,
// glass in rich motion (surface at 94 %), and the mist glow breathing behind it (rich, window active).
// Left: a mono label (when and which activity), the Archivo heading, one grey line, then the screen's one amber
// control (Resume activity with the shine, or Open activity) and one quiet action.  Right: the restore plan:
// what will reopen (the latest snapshot's restorable windows, else the items in launch order) as chips, and the
// line of flow from when it stopped to Ready.  With no activity at all: one line and New activity.
//
// The hero grows into the launch dock (`docked`), as the Stage centre did: only the frame animates (420 ms,
// OutCubic on height); the plan fades out at once, the dock's header and rows come in from 100 ms over 140 ms,
// laid out at their final width, clipped to the growing frame.
Card {
    id: hero
    radius: 8
    property bool docked: false
    property real arrive: 1
    readonly property var h: app.today.hero
    readonly property bool has: h.activityId !== undefined && h.activityId !== ""
    readonly property bool resume: has && h.kind === "resume"
    readonly property int padX: 28
    readonly property int padY: 26
    readonly property int innerW: width - 2 * padX
    readonly property bool split: innerW >= 600
    readonly property int leftW: split ? Math.floor((innerW - 28) * 1.25 / 2.25) : innerW
    readonly property int rightW: split ? innerW - 28 - leftW : innerW
    readonly property bool rich: app.ui.motion === "rich"
    readonly property bool ambient: Window.window !== null && Window.window.ambientOn === true
    signal closeDock()
    signal showActivity()

    property color base: tk.surface
    color: rich && app.ui.backend !== "software" ? Qt.rgba(base.r, base.g, base.b, 0.94) : tk.surface
    clip: true

    readonly property int restHeight: padY + Math.max(left.implicitHeight, plan.visible && split ? plan.implicitHeight : 0)
                                      + (plan.visible && !split ? 20 + plan.implicitHeight : 0) + padY
    readonly property int dockHeight: padY - 8 + dockHead.height + 8 + dockView.implicitHeight + padY - 8
    height: docked ? dockHeight : restHeight
    Behavior on height { NumberAnimation { duration: Math.round(420 * app.ui.k); easing.type: Easing.OutCubic } }

    function play() { pipe.play() }

    // ------------------------------------------------------------ the mist glow
    Canvas {
        id: glow
        width: 520; height: 520
        x: hero.width - width + 120
        y: -260
        property color mist: hero.tk.mist
        onMistChanged: requestPaint()
        onPaint: {
            var c = getContext("2d")
            c.reset()
            var g = c.createRadialGradient(260, 260, 0, 260, 260, 260)
            g.addColorStop(0, Qt.rgba(mist.r, mist.g, mist.b, 1))
            g.addColorStop(0.55, Qt.rgba(mist.r, mist.g, mist.b, 0.55))
            g.addColorStop(1, Qt.rgba(mist.r, mist.g, mist.b, 0))
            c.fillStyle = g
            c.fillRect(0, 0, 520, 520)
        }
        opacity: hero.docked ? 0 : hero.arrive
        SequentialAnimation on scale {
            running: !hero.docked && hero.visible && hero.ambient
            loops: Animation.Infinite
            NumberAnimation { from: 0.96; to: 1.04; duration: 3000; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1.04; to: 0.96; duration: 3000; easing.type: Easing.InOutSine }
            onRunningChanged: if (!running) glow.scale = 1
        }
    }
    Rectangle {                                 // the title-block rule, between the corner arcs
        x: hero.radius; width: hero.width - 2 * hero.radius; height: 2
        color: hero.tk.accent
    }

    // ------------------------------------------------------------ at rest
    Item {
        id: rest
        anchors.fill: parent
        visible: opacity > 0
        opacity: hero.docked ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: Math.round(120 * app.ui.k) } }

        Column {
            id: left
            x: hero.padX; y: hero.padY
            width: hero.leftW
            spacing: 10
            Txt {
                width: parent.width
                text: hero.has ? hero.h.label : "Today"
                role: "label"
                figures: true
            }
            Txt {
                width: parent.width
                text: hero.has ? hero.h.heading : "Nothing to pick up yet"
                role: "hero"
                Accessible.role: Accessible.Heading
            }
            Txt {
                width: parent.width
                text: hero.has ? hero.h.line : "Your last activity waits here, with what it will reopen."
                tone: "muted"
                figures: true
                wrapMode: Text.Wrap
                maximumLineCount: 2
                visible: text !== ""
            }
            Item { width: 1; height: 6 }
            Row {
                spacing: 10
                ActionButton {                  // the screen's one amber control
                    text: !hero.has ? "Start from what's open" : hero.resume ? "Resume activity" : "Open activity"
                    icon: !hero.has ? "browsers" : "play"
                    kind: "primary"
                    shine: hero.has
                    tooltip: hero.resume ? "A tick list first: what reopens is yours to choose" : ""
                    onClicked: {
                        if (!hero.has) { Window.window.startFromOpen(); return }
                        if (hero.resume) {
                            var aid = hero.h.activityId
                            var ok = Window.window.safe(function () { app.capture.prepareResume(aid) })
                            if (ok) Window.window.openSheet("ResumeSheet", {})
                        } else {
                            app.activities.open(hero.h.activityId)
                        }
                    }
                }
                ActionButton {
                    text: !hero.has ? "New activity" : hero.resume ? "Dismiss" : "Activity page"
                    icon: !hero.has ? "plus" : ""
                    kind: hero.has ? "ghost" : "outline"
                    tooltip: hero.resume ? "The snapshot stays in the activity's checkpoints" : ""
                    onClicked: {
                        if (!hero.has) Window.window.openSheet("ActivityEditor", { activityId: "" })
                        else if (hero.resume) app.activities.dismissResume()
                        else app.ui.go("activity", { activityId: hero.h.activityId })
                    }
                }
            }
        }

        // the restore plan
        Column {
            id: plan
            visible: hero.has
            x: hero.split ? hero.padX + hero.leftW + 28 : hero.padX
            y: hero.split ? hero.padY + Math.max(0, (left.implicitHeight - implicitHeight) / 2) : left.y + left.implicitHeight + 20
            width: hero.rightW
            spacing: 14
            readonly property var chips: hero.has ? hero.h.chips : []
            readonly property int total: hero.has ? hero.h.planCount : 0
            readonly property int perRow: width >= 520 ? 3 : 2
            readonly property int chipMax: Math.floor((width - 6 * (perRow - 1)) / perRow)
            // two rows at most: the chips, then "+N" in the last slot when more will reopen
            readonly property int shownN: total <= 2 * perRow ? Math.min(total, chips.length) : 2 * perRow - 1

            Item {
                width: parent.width
                height: 14
                Txt { text: hero.has && hero.h.planKind === "items" ? "Opens" : "Restore plan"; role: "label" }
                Txt {
                    anchors.right: parent.right
                    text: hero.has ? hero.h.planText : ""
                    role: "label"
                    figures: true
                    horizontalAlignment: Text.AlignRight
                }
            }
            Flow {
                width: parent.width
                spacing: 6
                visible: plan.total > 0
                Repeater {
                    model: plan.chips.slice(0, plan.shownN)
                    delegate: Rectangle {
                        required property var modelData
                        height: 26
                        radius: 13
                        width: Math.min(plan.chipMax, chipRow.implicitWidth + 20)
                        color: hero.tk.surface_2
                        Row {
                            id: chipRow
                            x: 10
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 6
                            Icon { name: parent.parent.modelData.glyph; size: 13; anchors.verticalCenter: parent.verticalCenter }
                            Txt {
                                text: parent.parent.modelData.text
                                role: "small"
                                width: Math.min(implicitWidth, plan.chipMax - 39)
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                }
                Rectangle {
                    visible: plan.total > plan.shownN
                    height: 26
                    radius: 13
                    width: more.implicitWidth + 20
                    color: hero.tk.surface_2
                    Txt { id: more; anchors.centerIn: parent; text: "+" + (plan.total - plan.shownN); role: "small"; tone: "muted"; figures: true }
                }
            }
            Txt {
                visible: plan.total === 0
                text: "Nothing to reopen yet: add items to the activity."
                tone: "muted"
            }
            FlowPipe {
                id: pipe
                width: parent.width
                height: implicitHeight
                loop: !hero.docked
            }
            Item {
                width: parent.width
                height: 14
                Txt { text: hero.has ? hero.h.fromText : ""; role: "label"; figures: true }
                Txt { anchors.right: parent.right; text: hero.has ? hero.h.toText : ""; role: "label" }
            }
        }
    }

    // ------------------------------------------------------------ the dock (the hero grown)
    readonly property var dockRow: {
        var m = app.activities.activities
        var i = m.indexOf(app.activities.dockId)
        return docked && i >= 0 ? m.get(i) : null
    }
    Item {
        id: dockHead
        visible: hero.docked
        opacity: dockView.opacity
        x: hero.padX - 8; y: hero.padY - 8
        width: hero.width - 2 * (hero.padX - 8)
        height: 40
        IconTile { id: tile; icon: hero.dockRow ? hero.dockRow.icon : "stack"; tint: app.activities.dockColor; size: 36; anchors.verticalCenter: parent.verticalCenter }
        Column {
            anchors.left: tile.right
            anchors.leftMargin: 12
            anchors.right: closeBtn.left
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Txt { width: parent.width; text: app.activities.dockTitle; role: "heading" }
            Txt { width: parent.width; text: app.activities.dockLine; role: "small"; tone: "muted"; figures: true }
        }
        ActionButton {
            id: closeBtn
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            kind: "ghost"
            icon: "x"
            tooltip: "Close (Esc)"
            onClicked: hero.closeDock()
        }
    }
    DockView {
        id: dockView
        visible: hero.docked
        embedded: true
        opacity: 0
        x: dockHead.x
        y: dockHead.y + dockHead.height + 8
        width: dockHead.width
        onCloseRequested: hero.closeDock()
        onShowActivity: hero.showActivity()
    }
    property bool growing: false
    onDockedChanged: {
        if (docked && app.ui.k > 0) { dockView.opacity = 0; growing = true; dockIn.restart() }
        else { dockIn.stop(); growing = false; dockView.opacity = docked ? 1 : 0 }
    }
    SequentialAnimation {
        id: dockIn
        PauseAnimation { duration: Math.round(100 * app.ui.k) }
        NumberAnimation { target: dockView; property: "opacity"; to: 1; duration: Math.round(140 * app.ui.k); easing.type: Easing.OutCubic }
        PauseAnimation { duration: Math.max(0, Math.round(420 * app.ui.k) - Math.round(240 * app.ui.k)) }
        onFinished: hero.growing = false        // a handler, not a ScriptAction (see StatusPill)
    }
    Component.onCompleted: if (docked) dockView.opacity = 1
}
