import QtQuick
import "../components"

// Publish to the Team Hub, post an announcement, or send to colleagues (board C).  mode: activity | project |
// announce | send-activity | send-project.  Every text field knows @mentions (the picker under the caret); the
// "For" field takes people and groups, each of whom gets it in their inbox (and a Cliq message when linked).
Sheet {
    id: s
    property string mode: "activity"
    property string targetId: ""
    property bool demoMention: false
    readonly property bool isPublish: mode === "activity" || mode === "project"
    readonly property bool isSend: mode === "send-activity" || mode === "send-project"
    readonly property bool forActivity: mode === "activity" || mode === "send-activity"
    property string picked: targetId

    function rowFor(id) {
        var m = forActivity ? app.activities.activities : app.activities.projects
        var i = m.indexOf(id)
        return i >= 0 ? m.get(i) : null
    }
    readonly property var target: picked !== "" ? rowFor(picked) : null

    title: mode === "announce" ? "Post an announcement" : isSend ? "Send to colleagues" : "Publish to Team Hub"
    subtitle: target ? target.title + " · " + target.itemCount + (target.itemCount === 1 ? " item" : " items")
                       + (forActivity ? " · capture and checkpoints stay on this PC" : "") : ""
    confirmText: mode === "announce" ? "Post" : isSend ? "Send" : "Publish"
    confirmEnabled: (mode === "announce" ? annTitle.text.trim() !== "" : s.picked !== "") && (!isSend || forField.targets.length > 0)
    sheetWidth: 600

    function until(days) {
        if (days === "") return ""
        var d = new Date(Date.now() + parseInt(days) * 86400000)
        return d.toISOString().slice(0, 10)
    }
    onAccepted: {
        var ok = Window.window.safe(function () {
            if (s.mode === "activity") app.hub.publishActivity(s.picked, desc.text, forField.targets)
            else if (s.mode === "project") app.hub.publishProject(s.picked, desc.text, forField.targets)
            else if (s.mode === "announce") app.hub.announce(annTitle.text, desc.text, level.value, s.until(expires.value))
            else app.hub.send(s.forActivity ? "activity" : "project", s.picked, forField.targets, desc.text)
        }, "Publishing arrives with the Team Hub update.")
        if (ok) s.close()
    }

    ChoiceField {
        visible: s.mode !== "announce" && s.targetId === ""
        width: parent.width
        label: s.forActivity ? "Activity" : "Project"
        options: {
            var m = s.forActivity ? app.activities.activities : app.activities.projects
            var out = []
            for (var i = 0; i < m.count(); i++) {
                var r = m.get(i)
                out.push({ value: s.forActivity ? r.activityId : r.projectId, text: r.title })
            }
            return out
        }
        value: s.picked
        onPicked: (v) => s.picked = v
    }
    Field {
        id: annTitle
        visible: s.mode === "announce"
        width: parent.width
        label: "Title"
        placeholder: "Z: drive moves on Friday"
    }
    MentionField {
        id: desc
        width: parent.width
        label: s.mode === "announce" ? "Message" : s.isSend ? "Note" : "Description"
        placeholder: s.mode === "announce" ? "What everyone should know; @ to mention someone"
                   : "What it is for and what to watch; @ to mention someone"
        forceOpen: s.demoMention
        Component.onCompleted: if (s.demoMention) text = "Lot 7 back-check set. Watch Revision C for the modeller's sheets, @pr"
    }
    Row {
        visible: s.mode === "announce"
        spacing: 16
        Column {
            spacing: 6
            Txt { text: "Kind"; strong: true }
            Segmented { id: level; label: "Kind"; options: [{ value: "info", text: "Notice" }, { value: "warning", text: "Warning" }]; value: "info"; onPicked: (v) => value = v }
        }
        ChoiceField {
            id: expires
            width: 200
            label: "Shown until"
            options: [{ value: "1", text: "Tomorrow" }, { value: "3", text: "3 days" }, { value: "7", text: "A week" }, { value: "", text: "Removed by hand" }]
            value: "7"
            onPicked: (v) => value = v
        }
    }
    ForField {
        id: forField
        width: parent.width
        label: s.isSend ? "To" : "For"
        help: s.isSend ? "Each person gets it in their inbox." : "Optional. They get it in their inbox and a mention; everyone else still sees it on the hub."
        Component.onCompleted: if (s.demoMention) targets = ["yokesh", "checkers"]
    }
}
