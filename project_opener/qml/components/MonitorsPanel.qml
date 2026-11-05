import QtQuick

// Control room's Monitors panel on the running activity's page: this PC's screens drawn to scale, each with
// the windows the watcher saw on it, so it is plain that restore puts windows back and that an unidentified
// window was seen.  Window rectangles are drawn when the live rows carry their placement (placeX/Y/W/H, 0..1
// of the monitor); otherwise each screen shows its count and names.
Card {
    id: panel
    property bool running: false
    readonly property var screens: Qt.application.screens
    readonly property real minX: bounds().x
    readonly property real minY: bounds().y
    readonly property real spanW: bounds().w
    readonly property real spanH: bounds().h
    readonly property real s: Math.min((width - 2 * pad) / Math.max(1, spanW), 120 / Math.max(1, spanH))
    property int rev: 0
    implicitHeight: 64 + Math.ceil(spanH * s) + 16 + names.implicitHeight + pad

    function bounds() {
        var x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9
        for (var i = 0; i < screens.length; i++) {
            var sc = screens[i]
            x0 = Math.min(x0, sc.virtualX); y0 = Math.min(y0, sc.virtualY)
            x1 = Math.max(x1, sc.virtualX + sc.width); y1 = Math.max(y1, sc.virtualY + sc.height)
        }
        if (screens.length === 0) return { x: 0, y: 0, w: 1920, h: 1080 }
        return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
    }
    function windowsOn(n) {
        var m = app.capture.live, out = []
        for (var i = 0; i < m.count(); i++) {
            var r = m.get(i)
            if (r.monitor === "monitor " + n) out.push(r)
        }
        return out
    }
    Connections { target: app.capture; function onLiveChanged() { panel.rev++ } }

    SectionHeading {
        x: panel.pad; y: panel.pad
        width: panel.width - 2 * panel.pad
        title: "Monitors"
        facts: panel.screens.length + (panel.screens.length === 1 ? " screen" : " screens")
               + (panel.running ? " · windows go back where they were" : "")
    }
    Item {
        id: map
        x: panel.pad + ((panel.width - 2 * panel.pad) - panel.spanW * panel.s) / 2
        y: 64
        width: panel.spanW * panel.s
        height: panel.spanH * panel.s
        Repeater {
            model: panel.screens
            delegate: Rectangle {
                required property var modelData
                required property int index
                readonly property var wins: panel.rev >= 0 ? panel.windowsOn(index + 1) : []
                x: (modelData.virtualX - panel.minX) * panel.s + 2
                y: (modelData.virtualY - panel.minY) * panel.s + 2
                width: modelData.width * panel.s - 4
                height: modelData.height * panel.s - 4
                radius: 6
                color: panel.tk.surface_2
                border.width: 1
                border.color: panel.tk.border_strong
                Repeater {
                    model: parent.wins
                    delegate: Rectangle {
                        required property var modelData
                        visible: modelData.placeW !== undefined && modelData.placeW > 0
                        x: (modelData.placeX || 0) * parent.width
                        y: (modelData.placeY || 0) * parent.height
                        width: (modelData.placeW || 0) * parent.width
                        height: (modelData.placeH || 0) * parent.height
                        radius: 3
                        color: "transparent"
                        border.width: 1
                        border.color: modelData.status === "identified" ? panel.tk.text_muted : panel.tk.warning
                    }
                }
                Txt {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 6
                    text: (index + 1) + (parent.wins.length > 0 ? " · " + parent.wins.length + (parent.wins.length === 1 ? " window" : " windows") : "")
                    role: "small"
                    tone: "muted"
                    figures: true
                }
            }
        }
    }
    Column {
        id: names
        x: panel.pad
        anchors.top: map.bottom
        anchors.topMargin: 12
        width: panel.width - 2 * panel.pad
        spacing: 2
        Repeater {
            model: panel.screens
            delegate: Txt {
                required property var modelData
                required property int index
                width: names.width
                text: (index + 1) + "  " + modelData.width + " × " + modelData.height
                      + (modelData.name !== "" ? " · " + modelData.name : "")
                role: "small"
                tone: "faint"
                figures: true
            }
        }
    }
}
