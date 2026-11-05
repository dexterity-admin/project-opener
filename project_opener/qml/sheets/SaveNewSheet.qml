import QtQuick
import "../components"

// "Save N new as items" (owner decision, 5 November 2026: "Everything open, I untick").  Every new thing the
// watcher sees is offered, most likely first: files, folders and pages opened since the activity started
// are ticked; those already open when it started, app, chat and mail windows and windows with no path are
// not.  Nothing is added without this choice; what stays unticked is not offered again for this activity.
// Data: app.capture.newCandidates (filled by prepareSaveNew / saveNewAsItems).
Sheet {
    id: s
    property int ticked: 0
    readonly property int total: list.count
    title: "Save new things as items"
    subtitle: total > 0 ? app.capture.runningName + " · " + total + (total === 1 ? " new thing" : " new things")
                          + " open · tick what belongs" : app.capture.runningName
    confirmText: ticked > 0 ? "Save " + ticked + " as " + (ticked === 1 ? "item" : "items")
                            : total > 0 ? "Leave all out" : "Done"
    sheetWidth: 640

    function recount() {
        var m = app.capture.newCandidates, n = 0
        for (var i = 0; i < m.count(); i++) if (m.get(i).ticked) n++
        ticked = n
    }
    Connections {
        target: app.capture.newCandidates
        function onDataChanged() { s.recount() }
        function onModelReset() { s.recount() }
    }
    Component.onCompleted: recount()
    onAccepted: {
        var ok = Window.window.safe(function () { if (s.total > 0) app.capture.saveTicked() })
        if (ok) s.close()
    }

    Txt {
        width: parent.width
        visible: s.total > 0
        text: "Unticked things stay open and in the list; they are not offered again for this activity."
        tone: "muted"
        wrapMode: Text.Wrap
        elide: Text.ElideNone
    }
    TickList {
        id: list
        width: parent.width
        model: app.capture.newCandidates
        onToggled: (key, on) => Window.window.safe(function () { app.capture.setNewTicked(key, on) })
    }
    EmptyBlock {
        visible: s.total === 0
        width: parent.width
        line: "Nothing new: everything open is already an item, ignored or left out."
    }
}
