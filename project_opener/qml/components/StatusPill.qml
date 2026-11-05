import QtQuick

// The 3.2 status pill (docs/DESIGN.md): pale tint, dark ink of the same hue.
// status (level): ok | warn | bad | info | neutral | opening | checking | queued.
// Words are the pill words: Reachable / Not found / Server offline / Undefined variable / Opened.
// Settling (board D, "the live elements"): the fill cross-fades over 180 ms and the word swaps at the
// midpoint; the pill is right-anchored by its users so a width change never pushes a column.
Rectangle {
    id: pill
    readonly property var tk: app.ui.tokens
    property string status: "neutral"
    property string label: ""
    property string shown: label
    readonly property bool neutral: status === "neutral" || status === "opening" || status === "checking"
                                    || status === "queued" || status === ""

    height: 20
    radius: 10
    width: shown === "" ? 0 : pillText.implicitWidth + 16
    visible: shown !== ""
    color: neutral ? tk.pill_neutral_bg : status === "ok" ? tk.pill_ok_bg : status === "warn" ? tk.pill_warn_bg
         : status === "bad" ? tk.pill_bad_bg : tk.pill_info_bg
    Behavior on color { ColorAnimation { duration: Math.round(180 * app.ui.k); easing.type: Easing.OutCubic } }
    Accessible.role: Accessible.StaticText
    Accessible.name: shown

    onLabelChanged: {
        if (app.ui.k === 0 || shown === "" || label === "") { shown = label; return }
        swap.restart()
    }
    SequentialAnimation {
        id: swap
        NumberAnimation { target: pillText; property: "opacity"; to: 0; duration: Math.round(90 * app.ui.k) }
        ScriptAction { script: pill.shown = pill.label }
        NumberAnimation { target: pillText; property: "opacity"; to: 1; duration: Math.round(90 * app.ui.k) }
    }

    Text {
        id: pillText
        anchors.centerIn: parent
        text: pill.shown
        font.family: pill.tk.face
        font.pixelSize: 12
        font.weight: Font.Medium
        font.features: ({ "tnum": 1 })
        color: pill.neutral ? pill.tk.pill_neutral_ink : pill.status === "ok" ? pill.tk.pill_ok_ink
             : pill.status === "warn" ? pill.tk.pill_warn_ink : pill.status === "bad" ? pill.tk.pill_bad_ink
             : pill.tk.pill_info_ink
    }
}
