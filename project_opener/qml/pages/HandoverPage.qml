import QtQuick
import "../components"

// Handover: give my activities and open tasks to a colleague while I am on leave, through the hub.  Nothing
// moves until they accept it (their inbox, or "Handed to you" here); the tasks come back when I say I am back,
// or on my PC's first start after the last day.  Form grammar of DESIGN.md "Dialogs": labels above fields,
// inline validation above the button, the confirming button named for its action.
Page {
    id: page
    minimumWidth: 860
    readonly property var mine: app.team.handover
    readonly property bool handedOver: mine.id !== undefined
    readonly property var ch: app.team.choices
    property string to: ""
    property string error: ""
    property var actPicked: ({})
    property var taskPicked: ({})
    property bool picksSeeded: false

    function iso(d) {
        function two(n) { return (n < 10 ? "0" : "") + n }
        return d.getFullYear() + "-" + two(d.getMonth() + 1) + "-" + two(d.getDate())
    }
    function seedPicks() {                         // recent activities and every open task, ticked
        if (page.picksSeeded || page.ch.activities === undefined) return
        var a = {}, t = {}
        for (var i = 0; i < page.ch.activities.length; i++) a[page.ch.activities[i].id] = page.ch.activities[i].recent
        for (var j = 0; j < page.ch.tasks.length; j++) t[page.ch.tasks[j].id] = true
        page.actPicked = a
        page.taskPicked = t
        page.picksSeeded = page.ch.activities.length > 0 || page.ch.tasks.length > 0
    }
    function picked(map) {
        var out = []
        for (var k in map) if (map[k]) out.push(k)
        return out
    }
    function toggle(which, id) {
        var m = Object.assign({}, which === "a" ? page.actPicked : page.taskPicked)
        m[id] = !m[id]
        if (which === "a") page.actPicked = m; else page.taskPicked = m
    }
    function colleagues() {
        var m = app.hub.peers, out = []
        for (var i = 0; i < m.count(); i++) {
            var p = m.get(i)
            out.push({ value: p.login, text: p.displayName + (p.online ? "" : " (away)") })
        }
        return out
    }
    function submit() {
        page.error = app.team.startHandover(page.to, firstDay.text, lastDay.text, page.picked(page.actPicked),
                                            page.picked(page.taskPicked))
    }

    Component.onCompleted: { app.team.refresh(); seedPicks() }
    Connections { target: app.team; function onHandoverChanged() { page.seedPicks() } }

    PageHeader {
        title: "Handover"
        subtitle: page.handedOver ? (page.mine.on ? "On leave · handed to " : "Handed to ") + page.mine.toName + " · " + page.mine.spanText
                : "Your activities and open tasks go to a colleague until you are back."
    }

    // ------------------------------------------------------------ mine, on
    Card {
        id: onCard
        visible: page.handedOver
        width: page.contentW
        height: onCol.implicitHeight + 2 * pad
        Rectangle { width: parent.width; height: 2; color: page.tk.teal }
        Column {
            id: onCol
            x: onCard.pad; y: onCard.pad
            width: onCard.width - 2 * onCard.pad
            spacing: 10
            Row {
                spacing: 10
                Icon { name: "airplane-tilt"; size: 18; tone: "accent"; anchors.verticalCenter: parent.verticalCenter }
                Txt { role: "heading"; text: (page.mine.toName || "") + (page.mine.accepted ? " has your work" : " has not accepted yet") }
            }
            Txt {
                width: parent.width
                tone: "muted"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
                text: [page.mine.activityCount === 1 ? "1 activity" : (page.mine.activityCount || 0) + " activities",
                       page.mine.taskCount === 1 ? "1 open task" : (page.mine.taskCount || 0) + " open tasks"].join(" · ")
                      + (page.mine.accepted ? " · " + (page.mine.movedCount === 1 ? "1 task is" : (page.mine.movedCount || 0) + " tasks are") + " theirs until you are back"
                                            : " · nothing moves until they accept it")
            }
            ActionButton {
                text: page.mine.on ? "I’m back" : "Cancel the handover"
                icon: page.mine.on ? "hand-waving" : "x"
                kind: page.mine.on ? "primary" : "outline"
                onClicked: app.team.endHandover("")
            }
        }
    }

    // ------------------------------------------------------------ the form
    Card {
        id: form
        visible: !page.handedOver
        width: page.contentW
        height: formCol.implicitHeight + 2 * pad
        Column {
            id: formCol
            x: form.pad; y: form.pad
            width: form.width - 2 * form.pad
            spacing: 16
            SectionHeading { title: "Going on leave"; facts: "" }
            Row {
                spacing: 16
                ChoiceField {
                    width: 260
                    label: "Colleague"
                    options: app.hub.peersOnline >= 0 ? page.colleagues() : []   // re-read when the peers change
                    value: page.to
                    onPicked: (v) => { page.to = v; page.error = "" }
                }
                Field {
                    id: firstDay
                    width: 160
                    label: "First day"
                    text: page.iso(new Date())
                    placeholder: "2026-11-24"
                    input.onTextChanged: page.error = ""
                }
                Field {
                    id: lastDay
                    width: 160
                    label: "Last day"
                    placeholder: "2026-11-28"
                    input.onTextChanged: page.error = ""
                }
            }
            Txt { text: "Activities"; strong: true }
            Flow {
                width: parent.width
                spacing: 8
                Repeater {
                    model: page.ch.activities || []
                    delegate: Chip {
                        text: modelData.name
                        interactive: true
                        checked: page.actPicked[modelData.id] === true
                        onClicked: page.toggle("a", modelData.id)
                    }
                }
                Txt { visible: (page.ch.activities || []).length === 0; text: "No activities yet."; tone: "faint" }
            }
            Txt { text: "Open tasks"; strong: true }
            Flow {
                width: parent.width
                spacing: 8
                Repeater {
                    model: page.ch.tasks || []
                    delegate: Chip {
                        text: modelData.title + (modelData.dueText !== "" ? " · " + modelData.dueText : "")
                        interactive: true
                        checked: page.taskPicked[modelData.id] === true
                        onClicked: page.toggle("t", modelData.id)
                    }
                }
                Txt { visible: (page.ch.tasks || []).length === 0; text: "No open tasks of yours."; tone: "faint" }
            }
            Txt {
                width: parent.width
                visible: page.error !== ""
                text: page.error
                tone: "bad"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
            }
            Row {
                spacing: 8
                ActionButton {
                    text: "Hand over"
                    icon: "airplane-tilt"
                    kind: "primary"
                    busy: app.team.busy
                    available: app.hub.configured
                    tooltip: app.hub.configured ? "" : "A handover goes through the Team Hub folder"
                    onClicked: page.submit()
                }
            }
        }
    }

    // ------------------------------------------------------------ handed to me
    Card {
        id: inCard
        width: page.contentW
        height: inCol.implicitHeight + 2 * pad
        Column {
            id: inCol
            x: inCard.pad; y: inCard.pad
            width: inCard.width - 2 * inCard.pad
            spacing: 8
            SectionHeading { title: "Handed to you"; facts: app.team.incomingCount > 0 ? String(app.team.incomingCount) : "" }
            Repeater {
                id: inRep
                model: app.team.incoming
                delegate: Item {
                    width: inCol.width
                    height: 64
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Column {
                        y: 10
                        width: parent.width - acc.width - 16
                        spacing: 2
                        Txt { width: parent.width; strong: true; text: model.fromName + " · " + model.spanText }
                        Txt {
                            width: parent.width
                            tone: "muted"
                            text: (model.activityCount === 1 ? "1 activity" : model.activityCount + " activities") + " · "
                                  + (model.taskCount === 1 ? "1 task" : model.taskCount + " tasks")
                                  + (model.taskTitles !== "" ? ": " + model.taskTitles : "")
                        }
                    }
                    Row {
                        id: acc
                        anchors.right: parent.right
                        y: 14
                        spacing: 8
                        Txt { text: model.stateText; role: "small"; tone: model.accepted ? "ok" : "warn"; anchors.verticalCenter: parent.verticalCenter }
                        ActionButton {
                            visible: !model.accepted
                            text: "Accept"
                            small: true
                            onClicked: app.team.acceptHandover(model.handoverId)
                        }
                    }
                }
            }
            EmptyBlock { visible: inRep.count === 0; width: inCol.width; line: "Nobody has handed work to you." }
        }
    }
}
