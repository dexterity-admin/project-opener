import QtQuick

// The 3.2 status pill in QML (spikes/quick/qml/Main.qml "Pill").  Owner: builder 4 (SHELL).
// status: ok | warn | bad | info | neutral | opening | checking.  Words: Reachable / Not found /
// Server offline / Undefined variable / Opened (docs/DESIGN.md).  Motion scales with app.ui.k.
Rectangle {
    id: pill
    readonly property var tk: app.ui.tokens
    property string status: "neutral"
    property string label: ""
    readonly property bool neutral: status === "neutral" || status === "opening" || status === "checking"

    height: 20
    radius: 10
    width: label === "" ? 0 : pillText.implicitWidth + 16
    visible: label !== ""
    color: neutral ? tk.pill_neutral_bg : status === "ok" ? tk.pill_ok_bg : status === "warn" ? tk.pill_warn_bg
         : status === "bad" ? tk.pill_bad_bg : tk.pill_info_bg
    Behavior on color { ColorAnimation { duration: Math.round(220 * app.ui.k) } }

    Text {
        id: pillText
        anchors.centerIn: parent
        text: pill.label
        font.family: "Onest"
        font.pixelSize: 12
        font.weight: Font.Medium
        font.features: ({ "tnum": 1 })
        color: pill.neutral ? pill.tk.pill_neutral_ink : pill.status === "ok" ? pill.tk.pill_ok_ink
             : pill.status === "warn" ? pill.tk.pill_warn_ink : pill.status === "bad" ? pill.tk.pill_bad_ink
             : pill.tk.pill_info_ink
    }
}
