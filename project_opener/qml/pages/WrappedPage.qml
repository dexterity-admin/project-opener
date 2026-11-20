import QtQuick
import "../components"

// Weekly Wrapped (docs/V4-PLUS-BRIEF.md sections 1 and 4): my week counted from what the app records (activities
// run, tasks closed, on time, day streak, windows reopened once the restore log exists), then the office board
// every PC publishes through the hub folder.  No hours, no window titles.  Motion (DESIGN.md "Motion"): the
// blocks rise once on arrival (60 ms apart; a fade in purposeful), then the numerals count up (900 ms, ease-out
// cubic) and the streak squares pop 45 ms apart; at motion off everything is still and shows its value.  A data
// refresh never replays it.  The one amber control is Post in Connect.
Page {
    id: page
    minimumWidth: 860
    readonly property var w: app.team.wrapped
    readonly property bool ready: w.week !== undefined
    readonly property bool still: app.ui.k === 0
    property bool arrived: false           // the rise and count-up ran (once per page arrival)
    property string channel: app.settings.value("wrapped_space") || ""

    Component.onCompleted: { app.team.refresh(); if (ready) page.arrive() }
    onReadyChanged: if (ready) page.arrive()
    function arrive() { if (!page.arrived) page.arrived = true }

    // ---- one block that rises into place on arrival
    component Rise: Item {
        id: riser
        property int order: 0
        default property alias body: holder.data
        implicitHeight: holder.childrenRect.height
        width: parent ? parent.width : 0
        height: implicitHeight
        Item {
            id: holder
            width: parent.width
            height: childrenRect.height
            opacity: page.still || page.arrived && riseDone ? 1 : 0
            property bool riseDone: page.still
            property real dy: page.still || app.ui.k < 1 ? 0 : 12
            transform: Translate { y: holder.riseDone ? 0 : holder.dy }
            Behavior on opacity { enabled: !page.still; NumberAnimation { duration: Math.round(650 * app.ui.k); easing.type: Easing.Bezier; easing.bezierCurve: [0.2, 0.7, 0.2, 1, 1, 1] } }
            Timer {
                interval: Math.round(60 * riser.order * app.ui.k) + 1
                running: page.arrived && !holder.riseDone
                onTriggered: holder.riseDone = true
            }
        }
    }

    // ---- a stat: mono label, Archivo numeral that counts up once, a muted line
    component Stat: Item {
        id: stat
        property string label: ""
        property int value: 0
        property bool known: true          // false = not counted (no number is shown)
        property string unit: ""
        property string line: ""
        property int order: 0
        property real shown: page.still ? value : 0
        property bool counted: page.still
        implicitHeight: col.implicitHeight
        height: implicitHeight
        onValueChanged: if (stat.counted) stat.shown = stat.value
        NumberAnimation {
            id: count
            target: stat; property: "shown"; from: 0; to: stat.value
            duration: Math.round(900 * app.ui.k); easing.type: Easing.OutCubic
            onFinished: { stat.counted = true; stat.shown = stat.value }
        }
        Timer {                           // after the rise of its block
            interval: Math.round((600 + 60 * stat.order) * app.ui.k) + 1
            running: page.arrived && !stat.counted
            onTriggered: { if (app.ui.k === 0) { stat.counted = true; stat.shown = stat.value } else count.start() }
        }
        Column {
            id: col
            width: parent.width
            spacing: 4
            Txt { text: stat.label; role: "label"; width: parent.width }
            Row {
                spacing: 6
                Text {
                    id: numeral
                    text: stat.known ? String(Math.round(stat.shown)) : "–"
                    font.family: page.tk.face_display
                    font.pixelSize: 44
                    font.weight: Font.Light
                    font.letterSpacing: -1.5
                    font.features: ({ "tnum": 1 })
                    color: stat.known ? page.tk.text : page.tk.text_faint
                    Accessible.name: stat.label + " " + (stat.known ? stat.value + (stat.unit ? " " + stat.unit : "") : "not counted")
                }
                Txt { visible: stat.known && stat.unit !== ""; text: stat.unit; tone: "muted"; anchors.baseline: numeral.baseline }
            }
            Txt { width: parent.width; text: stat.line; role: "small"; tone: "muted"; visible: text !== "" }
        }
    }

    PageHeader {
        title: "Wrapped"
        subtitle: page.ready ? page.w.title + " · " + page.w.rangeText : ""
        Segmented {
            options: [{ value: "0", text: "This week" }, { value: "-1", text: "Last week" }]
            value: String(app.team.weekOffset)
            onPicked: (v) => app.team.setWeekOffset(Number(v))
        }
    }

    // ------------------------------------------------------------ my week
    Rise {
        order: 0
        Card {
            id: hero
            width: page.contentW
            height: heroCol.implicitHeight + 2 * pad
            Rectangle { width: parent.width; height: 2; color: page.tk.teal }      // the teal rule on the hero
            Column {
                id: heroCol
                x: hero.pad; y: hero.pad
                width: hero.width - 2 * hero.pad
                spacing: 18
                Item {
                    width: parent.width
                    height: 36
                    Txt {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - spaceRow.width - 16
                        text: page.ready ? page.w.name + "’s week" : "Your week"
                        font.family: page.tk.face_display
                        font.pixelSize: 26
                        font.weight: Font.Light
                    }
                    Row {
                        id: spaceRow
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8
                        visible: app.team.connectReady
                        Field {
                            width: 170
                            text: page.channel
                            placeholder: "Piping team"
                            input.onEditingFinished: page.channel = text
                            Accessible.name: "Connect Space"
                        }
                        ActionButton {
                            text: "Post in Connect"
                            icon: "paper-plane-tilt"
                            kind: "primary"
                            available: page.ready && page.channel.replace("#", "").trim() !== ""
                            tooltip: available ? "Posts these numbers in the Space " + page.channel.replace("#", "") : "Name a Connect Space first"
                            onClicked: app.team.postToSpace(page.channel)
                        }
                    }
                }
                Grid {
                    id: stats
                    width: parent.width
                    columns: page.contentW >= 900 ? 5 : 3
                    columnSpacing: 24
                    rowSpacing: 18
                    readonly property real cell: (width - (columns - 1) * columnSpacing) / columns
                    Stat {
                        width: stats.cell; order: 1
                        label: "Activities run"; value: page.w.activitiesRun || 0
                        line: (page.w.activitiesRun || 0) === 1 ? "one opening this week" : "openings of your activities"
                    }
                    Stat {
                        width: stats.cell; order: 2
                        label: "Tasks closed"; value: page.w.tasksClosed || 0
                        line: "marked done by you"
                    }
                    Stat {
                        width: stats.cell; order: 3
                        label: "On time"; value: Math.max(0, page.w.onTimeRate === undefined ? 0 : page.w.onTimeRate)
                        known: page.ready && page.w.onTimeRate >= 0; unit: "%"
                        line: page.w.onTimeLine || ""
                    }
                    Column {
                        width: stats.cell
                        spacing: 8
                        Stat {
                            width: parent.width; order: 4
                            label: "Day streak"; value: page.w.dayStreak || 0
                            unit: (page.w.dayStreak || 0) === 1 ? "day" : "days"
                        }
                        Row {                                   // Mon..Sun, popping 45 ms apart after the count
                            spacing: 5
                            Repeater {
                                model: page.ready ? page.w.squares : []
                                delegate: Rectangle {
                                    id: sq
                                    width: 14; height: 14; radius: 3
                                    color: modelData ? page.tk.teal : "transparent"
                                    border.width: modelData ? 0 : 1
                                    border.color: index === page.w.squaresToday ? page.tk.text_muted : page.tk.border_strong
                                    property bool popped: page.still
                                    scale: popped ? 1 : 0.4
                                    opacity: popped ? 1 : 0
                                    Behavior on scale { enabled: !page.still; NumberAnimation { duration: Math.round(220 * app.ui.k); easing.type: Easing.OutCubic } }
                                    Behavior on opacity { enabled: !page.still; NumberAnimation { duration: Math.round(160 * app.ui.k) } }
                                    Timer {
                                        interval: Math.round((1500 + 45 * index) * app.ui.k) + 1
                                        running: page.arrived && !sq.popped
                                        onTriggered: sq.popped = true
                                    }
                                    Accessible.name: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][index] + (modelData ? ", launched" : ", nothing launched")
                                }
                            }
                        }
                    }
                    Stat {
                        width: stats.cell; order: 5
                        label: "Windows reopened"; value: Math.max(0, page.w.windowsReopened === undefined ? 0 : page.w.windowsReopened)
                        known: page.ready && page.w.windowsReopened >= 0
                        line: known ? "put back by restores" : "not counted yet"
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------ the board
    Rise {
        order: 2
        Card {
            id: boardCard
            width: page.contentW
            height: boardCol.implicitHeight + 2 * pad
            Column {
                id: boardCol
                x: boardCard.pad; y: boardCard.pad
                width: boardCard.width - 2 * boardCard.pad
                spacing: 12
                Item {
                    width: parent.width
                    height: 34
                    SectionHeading {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width - sortSeg.width - 16
                        title: "Office board"
                        facts: !page.w.hub ? "" : app.team.boardCount + (app.team.boardCount === 1 ? " person" : " people")
                               + (page.w.place > 0 ? " · you are " + page.w.place + " of " + page.w.of : "")
                    }
                    Segmented {
                        id: sortSeg
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: app.team.boardCount > 1
                        options: [{ value: "tasks", text: "Tasks" }, { value: "activities", text: "Activities" }, { value: "streak", text: "Streak" }]
                        value: app.team.boardSort
                        onPicked: (v) => app.team.setBoardSort(v)
                    }
                }
                Row {                                         // column labels
                    visible: app.team.boardCount > 0
                    width: parent.width
                    Txt { width: 40; text: "#"; role: "label" }
                    Txt { width: parent.width - 40 - 4 * boardCol.numW; text: "Person"; role: "label" }
                    Txt { width: boardCol.numW; horizontalAlignment: Text.AlignRight; text: "Activities"; role: "label" }
                    Txt { width: boardCol.numW; horizontalAlignment: Text.AlignRight; text: "Tasks"; role: "label" }
                    Txt { width: boardCol.numW; horizontalAlignment: Text.AlignRight; text: "On time"; role: "label" }
                    Txt { width: boardCol.numW; horizontalAlignment: Text.AlignRight; text: "Streak"; role: "label" }
                }
                readonly property int numW: page.narrow ? 92 : 120
                Repeater {
                    id: boardRep
                    model: app.team.board
                    delegate: Rectangle {
                        width: boardCol.width
                        height: 46
                        radius: 5
                        color: model.isMe ? page.tk.surface_2 : "transparent"
                        Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 && !model.isMe }
                        Row {
                            width: parent.width
                            height: parent.height
                            Txt { height: parent.height; width: 40; leftPadding: 8; text: String(model.place); figures: true; tone: model.place <= 3 ? "ink" : "muted"; strong: model.place === 1 }
                            Row {
                                width: parent.width - 40 - 4 * boardCol.numW
                                height: parent.height
                                spacing: 10
                                Avatar { size: 26; initials: model.initials; hue: Number(model.hue); anchors.verticalCenter: parent.verticalCenter }
                                Txt { width: parent.width - 40; text: model.name + (model.isMe ? " (you)" : ""); strong: model.isMe; anchors.verticalCenter: parent.verticalCenter }
                            }
                            Txt { height: parent.height; width: boardCol.numW; horizontalAlignment: Text.AlignRight; text: String(model.activitiesRun); figures: true }
                            Txt { height: parent.height; width: boardCol.numW; horizontalAlignment: Text.AlignRight; text: String(model.tasksClosed); figures: true }
                            Txt { height: parent.height; width: boardCol.numW; horizontalAlignment: Text.AlignRight; text: model.onTimeText; figures: true; tone: model.onTimeText === "–" ? "faint" : "ink" }
                            Txt { height: parent.height; width: boardCol.numW; horizontalAlignment: Text.AlignRight; rightPadding: 8; text: String(model.dayStreak); figures: true }
                        }
                    }
                }
                Txt {
                    width: parent.width
                    visible: page.w.hub === true && !app.team.showOnBoard
                    text: "You are off the board: colleagues do not see your numbers. Your own week stays here."
                    tone: "muted"
                    wrapMode: Text.Wrap
                    elide: Text.ElideNone
                }
                EmptyBlock {
                    visible: boardRep.count === 0
                    width: parent.width
                    line: !page.w.hub ? "Pick a shared folder for the Team Hub to see the office board."
                        : !page.w.reachable ? "The hub folder is not reachable just now."
                        : "Nobody has numbers for this week yet."
                    action: !page.w.hub ? "Set up the Team Hub" : ""
                    onTriggered: app.ui.go("settings", { tab: "hub", section: "hub" })
                }
                ActionButton {
                    visible: page.w.hub === true
                    text: app.team.showOnBoard ? "Board settings" : "Show me on the board"
                    kind: "link"
                    small: true
                    onClicked: app.ui.go("settings", { tab: "hub", section: "hub" })
                }
            }
        }
    }
}
