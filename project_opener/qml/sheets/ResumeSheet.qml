import QtQuick
import "../components"

// Resume (owner decision, 5 November 2026: "A tick list, items pre-ticked").  What was open at the last
// snapshot, grouped: the activity's items (ticked), other files, folders and pages opened during the
// activity (ticked), everything else (unticked; a window with no path or an unsaved document says it cannot
// be reopened).  "Reopen 9" restores only the ticked ones, each put back where it was.  Never automatic.
// Data: app.capture.resumeCandidates (filled by prepareResume when the Resume band's button opens this).
Sheet {
    id: s
    readonly property var r: app.activities.resume
    property int ticked: 0
    title: r.title !== undefined ? r.title : "Resume"
    subtitle: (r.takenAt !== undefined && r.takenAt !== "" ? "What was open at " + r.takenAt : "What was open")
              + " · tick what to reopen"
    confirmText: "Reopen " + ticked
    confirmEnabled: ticked > 0
    sheetWidth: 640

    function recount() {
        var m = app.capture.resumeCandidates, n = 0
        for (var i = 0; i < m.count(); i++) if (m.get(i).ticked) n++
        ticked = n
    }
    Connections {
        target: app.capture.resumeCandidates
        function onDataChanged() { s.recount() }
        function onModelReset() { s.recount() }
    }
    Component.onCompleted: recount()
    onAccepted: {
        var ok = Window.window.safe(function () { app.activities.resumeNow() })
        if (ok) s.close()
    }

    TickList {
        id: list
        width: parent.width
        model: app.capture.resumeCandidates
        onToggled: (key, on) => Window.window.safe(function () { app.capture.setResumeTicked(key, on) })
    }
    EmptyBlock {
        visible: list.count === 0
        width: parent.width
        line: "Nothing was recorded for this activity."
    }
}
