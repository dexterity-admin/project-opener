import QtQuick
import "../components"

// A watcher (brief 3.4): what to watch (a folder, a server's health, the hub, a date), the events, and who to
// tell (a toast, @mentions, a Cliq message, a Cliq channel).  Folders are polled (the share is SMB).
Sheet {
    id: s
    property string watcherId: ""
    property string activityId: ""
    property string kind: "folder"
    property var events: ["new", "changed"]
    title: watcherId === "" ? "New watcher" : "Edit watcher"
    subtitle: activityId !== "" ? "For " + (app.activities.current.title || "") : ""
    confirmText: watcherId === "" ? "Create watcher" : "Save watcher"
    confirmEnabled: kind === "hub" || kind === "time" || target.text.trim() !== ""
    sheetWidth: 600

    readonly property var eventsFor: ({
        folder: [{ v: "new", t: "A new file" }, { v: "changed", t: "A file changed" }, { v: "gone", t: "A file is gone" }],
        health: [{ v: "down", t: "It goes down" }, { v: "up", t: "It comes back" }],
        hub: [{ v: "published", t: "Something is published" }, { v: "task_assigned", t: "A task is given" }, { v: "task_done", t: "A task is done" }, { v: "mention", t: "A mention" }],
        time: [{ v: "due", t: "A due date" }, { v: "stale", t: "Not opened for 30 days" }, { v: "reminder", t: "A reminder" }]
    })
    function toggleEvent(v) {
        var e = events.slice()
        var i = e.indexOf(v)
        if (i >= 0) e.splice(i, 1); else e.push(v)
        events = e
    }
    onKindChanged: events = [eventsFor[kind][0].v]
    onAccepted: {
        var ok = Window.window.safe(function () {
            var notify = { toast: toast.checked, mentions: tell.targets, cliqDm: dm.checked, cliqChannel: channel.text }
            var params = { pattern: pattern.text || "*", activityId: s.activityId }
            if (s.watcherId === "") app.watchers.create(s.kind, target.text, s.events, params, notify)
            else app.watchers.edit(s.watcherId, { target: target.text, events: s.events, params: params, notify: notify })
        })
        if (ok) s.close()
    }

    Column {
        spacing: 6
        Txt { text: "Watch"; strong: true }
        Segmented {
            label: "Watch"
            options: [{ value: "folder", text: "A folder" }, { value: "health", text: "A server or drive" }, { value: "hub", text: "The hub" }, { value: "time", text: "A date" }]
            value: s.kind
            onPicked: (v) => s.kind = v
        }
    }
    Row {
        visible: s.kind === "folder" || s.kind === "health"
        width: parent.width
        spacing: 12
        Field {
            id: target
            width: parent.width - (browseBtn.visible ? browseBtn.width + 12 : 0)
            label: s.kind === "folder" ? "Folder" : "Server, share or drive"
            placeholder: s.kind === "folder" ? "\\\\nas01\\Project\\P12513\\ISO\\Revision C" : "\\\\nas01"
        }
        ActionButton {
            id: browseBtn
            visible: s.kind === "folder"
            y: 25
            text: "Browse"
            icon: "folder-open"
            onClicked: { var p = app.settings.browseFolder("Folder to watch", target.text); if (p !== "") target.text = p }
        }
    }
    Field { id: pattern; visible: s.kind === "folder"; width: (parent.width - 16) / 2; label: "Files"; placeholder: "*.pdf"; help: "Empty: every file." }
    Column {
        width: parent.width
        spacing: 6
        Txt { text: "When"; strong: true }
        Flow {
            width: parent.width
            spacing: 6
            Repeater {
                model: s.eventsFor[s.kind]
                delegate: Chip {
                    required property var modelData
                    interactive: true
                    text: modelData.t
                    checked: s.events.indexOf(modelData.v) >= 0
                    onClicked: s.toggleEvent(modelData.v)
                }
            }
        }
    }
    SwitchRow { id: toast; label: "Tell me with a toast"; checked: true; onToggled: (v) => checked = v }
    ForField { id: tell; width: parent.width; label: "Also tell"; help: "People and groups get it in their inbox." }
    SwitchRow { id: dm; label: "Message on Cliq"; help: "To me and the people above, when linked."; checked: app.settings.value("notify_cliq_default") === true; onToggled: (v) => checked = v }
    Field { id: channel; width: (parent.width - 16) / 2; label: "Cliq channel"; placeholder: "#p12513"; help: "Optional: post there too." }
}
