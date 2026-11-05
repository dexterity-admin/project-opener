import QtQuick
import "../components"

// A task (brief 3.3): title, owner (anyone; the @ picker), due date, attached activity or project, a note that
// may mention people.  Everyone is equal: anyone creates and assigns; the record shows who.  Editing (taskId
// set) fills the fields from app.tasks.all and offers "Mail this task" (an Outlook draft, else mailto:).
Sheet {
    id: s
    property string taskId: ""
    property string attachKind: ""
    property string attachId: ""
    property string existingDue: ""            // the task's own date when editing ("2026-11-07")
    property string existingDueText: ""
    title: taskId === "" ? "New task" : "Edit task"
    subtitle: attachId !== "" ? "For " + attachTitle() : ""
    confirmText: taskId === "" ? "Create task" : "Save task"
    confirmEnabled: titleField.text.trim() !== ""
    sheetWidth: 600
    footerExtra: [
        ActionButton {
            visible: s.taskId !== ""
            text: "Mail this task"
            icon: "envelope-simple"
            small: true
            tooltip: "An Outlook draft with the task and its link (the default mail app without Outlook)"
            onClicked: Window.window.safe(function () { app.tasks.mailTask(s.taskId) })
        }
    ]

    function attachTitle() {
        var m = attachKind === "project" ? app.activities.projects : app.activities.activities
        var i = m.indexOf(attachId)
        return i >= 0 ? m.get(i).title : ""
    }
    function dueDate() {
        var d = new Date()
        var add = { today: 0, tomorrow: 1, friday: (5 - d.getDay() + 7) % 7, week: 7, none: -1 }[due.value]
        if (add === undefined) return due.value
        if (add < 0) return ""
        d.setDate(d.getDate() + add)
        return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2)
    }
    function load() {
        var m = app.tasks.all
        var i = m.indexOf(s.taskId)
        if (i < 0) return
        var t = m.get(i)
        titleField.text = t.title
        note.text = t.note || ""
        who.targets = t.owner && t.owner !== app.login ? [t.owner] : []
        s.attachKind = t.attachKind || ""
        s.attachId = t.attachId || ""
        s.existingDue = t.due || ""
        s.existingDueText = t.dueText ? String(t.dueText).charAt(0).toUpperCase() + String(t.dueText).slice(1) : ""
        due.value = t.due ? t.due : "none"
    }
    Component.onCompleted: {
        if (s.taskId !== "") s.load()
        titleField.focusInput()
    }
    onAccepted: {
        var owner = who.targets.length > 0 ? who.targets[0] : app.login
        var ok = Window.window.safe(function () {
            if (s.taskId === "") {
                var id = app.tasks.create(titleField.text, owner, s.dueDate(), s.attachKind, s.attachId)
                if (note.text !== "" && id) app.tasks.edit(id, { note: note.text })
            } else {
                app.tasks.edit(s.taskId, { title: titleField.text, owner: owner, due: s.dueDate(), note: note.text,
                                           attachKind: s.attachKind || "activity", attachId: s.attachId })
            }
        })
        if (ok) s.close()
    }

    Field { id: titleField; width: parent.width; label: "Task"; placeholder: "Back-check lot 7"; onAccepted: s.accept() }
    Row {
        width: parent.width
        spacing: 16
        ForField { id: who; width: (parent.width - 16) / 2; label: "Owner"; help: "Empty: you." }
        ChoiceField {
            id: due
            width: (parent.width - 16) / 2
            label: "Due"
            value: "friday"
            options: (s.existingDue !== "" ? [{ value: s.existingDue, text: s.existingDueText || s.existingDue }] : [])
                     .concat([{ value: "today", text: "Today" }, { value: "tomorrow", text: "Tomorrow" }, { value: "friday", text: "Friday" },
                              { value: "week", text: "In a week" }, { value: "none", text: "No date" }])
            onPicked: (v) => value = v
        }
    }
    ChoiceField {
        width: parent.width
        label: "Attached to"
        value: s.attachKind === "" ? "" : s.attachKind + "|" + s.attachId
        options: {
            var out = [{ value: "", text: "Nothing" }]
            var a = app.activities.activities
            for (var i = 0; i < a.count(); i++) out.push({ value: "activity|" + a.get(i).activityId, text: a.get(i).title })
            var p = app.activities.projects
            for (var j = 0; j < p.count(); j++) out.push({ value: "project|" + p.get(j).projectId, text: p.get(j).title })
            return out
        }
        onPicked: (v) => { var parts = v.split("|"); s.attachKind = parts[0] || ""; s.attachId = parts[1] || "" }
    }
    MentionField { id: note; width: parent.width; label: "Note"; placeholder: "What done looks like; @ to mention someone"; boxHeight: 72 }
}
