import QtQuick
import QtQuick.Window

// Window picker overlay, one per monitor (board "snapshot-surfaces" D).  Owner: builder 3.
// Created by desktop/picker.py with `picker` (WindowPicker) and `screenRef` (its QScreen).
// Transparent for input: the click and Esc are read by low-level hooks in picker.py, so the window
// under the pointer is found with WindowFromPoint straight through this overlay.
// Dims slightly, frames the window under the pointer green (identifiable) or amber, with a label
// saying exactly what will be added.
Window {
    id: overlay
    required property var picker
    required property var screenRef
    readonly property var tk: app.ui.tokens
    property var f: ({ visible: false, x: 0, y: 0, w: 0, h: 0, ok: false, known: false, label: "" })
    readonly property color frameColor: f.ok ? tk.success : tk.warning
    readonly property real dim: 0.28

    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
           | Qt.WindowDoesNotAcceptFocus
    visible: false
    color: "transparent"
    title: "Project Opener picker"

    function update() {
        f = picker.frameFor(screenRef.geometry.x, screenRef.geometry.y, screenRef.devicePixelRatio)
    }
    onVisibleChanged: if (visible) { hint.text = picker.hint(); update() }
    Connections {
        target: overlay.picker
        function onFrameChanged() { overlay.update() }
    }

    // The dim around the framed window (four bands), the whole screen when nothing is framed.
    Rectangle { color: "black"; opacity: overlay.dim; visible: !overlay.f.visible; anchors.fill: parent }
    Item {
        anchors.fill: parent
        visible: overlay.f.visible
        Rectangle { color: "black"; opacity: overlay.dim; x: 0; y: 0; width: parent.width; height: Math.max(0, overlay.f.y) }
        Rectangle { color: "black"; opacity: overlay.dim; x: 0; y: overlay.f.y + overlay.f.h; width: parent.width
                    height: Math.max(0, parent.height - overlay.f.y - overlay.f.h) }
        Rectangle { color: "black"; opacity: overlay.dim; x: 0; y: Math.max(0, overlay.f.y)
                    width: Math.max(0, overlay.f.x); height: Math.max(0, Math.min(overlay.f.h, parent.height - overlay.f.y)) }
        Rectangle { color: "black"; opacity: overlay.dim; x: overlay.f.x + overlay.f.w; y: Math.max(0, overlay.f.y)
                    width: Math.max(0, parent.width - overlay.f.x - overlay.f.w)
                    height: Math.max(0, Math.min(overlay.f.h, parent.height - overlay.f.y)) }
    }

    Rectangle {
        id: frame
        visible: overlay.f.visible
        x: overlay.f.x - 3; y: overlay.f.y - 3
        width: overlay.f.w + 6; height: overlay.f.h + 6
        radius: 8
        color: "transparent"
        border.width: 3
        border.color: overlay.frameColor
    }

    Rectangle {
        id: label
        visible: overlay.f.visible && labelText.text !== ""
        readonly property var lines: String(overlay.f.label || "").split("\n")
        x: Math.max(8, Math.min(overlay.width - width - 8, overlay.f.x + 30))
        y: Math.max(8, Math.min(overlay.height - height - 8, overlay.f.y + overlay.f.h - height - 30))
        width: Math.min(460, Math.max(labelText.implicitWidth, subText.implicitWidth) + 24)
        height: col.implicitHeight + 16
        radius: 10
        color: overlay.tk.surface
        border.width: 1
        border.color: overlay.tk.border_strong
        Column {
            id: col
            x: 12; y: 8
            width: parent.width - 24
            Text {
                id: labelText
                width: parent.width
                elide: Text.ElideRight
                text: overlay.f.known ? label.lines[0] : (overlay.f.title || "Reading this window…")
                font.family: "Onest"; font.pixelSize: 13; font.weight: Font.DemiBold
                color: overlay.tk.text
            }
            Text {
                id: subText
                width: parent.width
                visible: text !== ""
                wrapMode: Text.WordWrap
                text: overlay.f.known ? label.lines.slice(1).join(" ") : ""
                font.family: "Onest"; font.pixelSize: 13
                color: overlay.tk.text_muted
            }
        }
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 12
        width: hint.implicitWidth + 28
        height: 30
        radius: 15
        color: overlay.tk.surface
        border.width: 1
        border.color: overlay.tk.border_strong
        Text {
            id: hint
            anchors.centerIn: parent
            font.family: "Onest"; font.pixelSize: 13
            color: overlay.tk.text_muted
        }
    }
}
