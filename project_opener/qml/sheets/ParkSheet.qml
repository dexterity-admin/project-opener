import QtQuick
import "../components"

// Park (docs/V4-PLUS-BRIEF.md "Daily rhythm"): Ctrl+Alt+P, the pill or the tray keeps the running workspace as a
// checkpoint of kind "park" with a short "where I left off" note; Today's hero shows it the next morning and
// Time travel marks it.  The activity keeps running.  Data: app.capture (runningName, openCount, park(note)).
Sheet {
    id: s
    readonly property bool running: app.capture.runningId !== ""
    title: "Park"
    subtitle: running ? app.capture.runningName + " · " + app.capture.openCount
                        + (app.capture.openCount === 1 ? " thing" : " things") + " open"
                      : "No activity is running"
    confirmText: running ? "Park" : "Close"
    showCancel: running
    confirmTooltip: running ? "Keeps what is open now with your note; nothing is closed" : ""

    onAccepted: {
        if (!s.running) { s.close(); return }
        var ok = Window.window.safe(function () { app.capture.park(note.text) })
        if (ok) s.close()
    }

    AreaField {
        id: note
        visible: s.running
        width: parent.width
        label: "Where I left off"
        placeholder: "Sheets 12 to 18 back-checked; 19 next, waiting on the line list"
        boxHeight: 96
    }
}
