import QtQuick
import "../components"

// A task (brief 3.3): title, owner (anyone; the @ picker), due date, attached activity or project, a note that
// may mention people.  Everyone is equal: anyone creates and assigns; the record shows who.
Sheet {
    id: s
    property string taskId: ""
    property string attachKind: ""
    property string attachId: ""
    title: taskId === "" ? "New task" : "Edit task"
    subtitle: attachId !== "" ? "For " + attachTitle() : ""
    confirmText: taskId === "" ? "Create task" : "Save task"
    confirmEnabled: titleField.text.trim() !== ""
    sheetWidth: 600

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
    Component.onCompleted: titleField.focusInput()
    onAccepted: {
        var owner = who.targets.length > 0 ? who.targets[0] : app.login
        var ok = Window.window.safe(function () {
            if (s.taskId === "") {
                var id = app.tasks.create(titleField.text, owner, s.dueDate(), s.attachKind, s.attachId)
                if (note.text !== "" && id) app.tasks.edit(id, { note: note.text })
            } else {
                app.tasks.edit(s.taskId, { title: titleField.text, owner: owner, due: s.dueDate(), note: note.text })
            }
        }, "Tasks arrive with the Team Hub update.")
        if (ok) s.close()
    }

    Field { id: titleField; width: parent.width; label: "Task"; placeholder: "Back-check lot 7"; onAccepted: s.accept() }
    Row {
        spacing: 16
        ForField { id: who; width: 300; label: "Owner"; help: "Empty: you." }
        ChoiceField {
            id: due
            width: 220
            label: "Due"
            value: "friday"
            options: [{ value: "today", text: "Today" }, { value: "tomorrow", text: "Tomorrow" }, { value: "friday", text: "Friday" },
                      { value: "week", text: "In a week" }, { value: "none", text: "No date" }]
            onPicked: (v) => value = v
        }
    }
    ChoiceField {
        width: 380
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
