import QtQuick

// Control room's Monitors panel on an activity's page: this PC's screens drawn to scale, each with the windows
// the watcher saw on it, so it is plain that restore puts windows back.  Running: the live rows.  Not running:
// the last snapshot's windows at 50 % (juror D2-1 / C2-1), so the page always shows where things go back.
// Frames are drawn in border_strong; only a window that needs a path (warning) or whose server is offline
// (danger) is coloured.  Each screen's label sits in a 16 px strip under it, never on the frame lines.
Card {
    id: panel
    property bool running: false
    property string activityId: ""
    readonly property var screens: Qt.application.screens
    readonly property real minX: bounds().x
    readonly property real minY: bounds().y
    readonly property real spanW: bounds().w
    readonly property real spanH: bounds().h
    readonly property int stripH: 16
    readonly property int rows: screenRows()
    readonly property real s: Math.min((width - 2 * pad) / Math.max(1, spanW), 120 / Math.max(1, spanH))
    property int rev: 0
    property var last: ({ takenText: "", rows: [] })
    implicitHeight: 64 + Math.ceil(spanH * s) + rows * (stripH + 4) + pad

    function reloadLast() {
        last = (!running && activityId !== "") ? app.capture.lastWindows(activityId) : { takenText: "", rows: [] }
        rev++
    }
    onRunningChanged: reloadLast()
    onActivityIdChanged: reloadLast()
    onVisibleChanged: if (visible) reloadLast()
    Component.onCompleted: reloadLast()

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
    // screens stacked vertically each get their own label strip: the row a screen sits in, top to bottom
    function rowOf(vy) {
        var tops = []
        for (var i = 0; i < screens.length; i++)
            if (tops.indexOf(screens[i].virtualY) < 0) tops.push(screens[i].virtualY)
        tops.sort(function (a, b) { return a - b })
        var n = 0
        for (var j = 0; j < tops.length; j++) if (tops[j] < vy) n++
        return n
    }
    function screenRows() {
        var tops = []
        for (var i = 0; i < screens.length; i++)
            if (tops.indexOf(screens[i].virtualY) < 0) tops.push(screens[i].virtualY)
        return Math.max(1, tops.length)
    }
    function windowsOn(n) {
        var out = []
        if (panel.running) {                    // the live rows are the running activity's
            var m = app.capture.live
            for (var i = 0; i < m.count(); i++) {
                var r = m.get(i)
                if (r.monitor === "monitor " + n) out.push(r)
            }
        } else {
            var rs = panel.last.rows || []
            for (var k = 0; k < rs.length; k++) if (rs[k].monitor === "monitor " + n) out.push(rs[k])
        }
        return out
    }
    function frameColor(status) {
        if (status === "unidentified" || status === "ambiguous") return panel.tk.warning
        if (status === "offline") return panel.tk.danger
        return panel.tk.border_strong
    }
    Connections { target: app.capture; function onLiveChanged() { if (panel.running) panel.rev++ } }

    SectionHeading {
        x: panel.pad; y: panel.pad
        width: panel.width - 2 * panel.pad
        title: "Monitors"
        facts: panel.screens.length + (panel.screens.length === 1 ? " screen" : " screens")
               + (panel.running ? " · windows go back where they were"
                  : panel.last.takenText !== "" ? " · as at " + panel.last.takenText : "")
    }
    Item {
        id: map
        x: panel.pad + ((panel.width - 2 * panel.pad) - panel.spanW * panel.s) / 2
        y: 64
        width: panel.spanW * panel.s
        height: panel.spanH * panel.s + panel.rows * (panel.stripH + 4)
        Repeater {
            model: panel.screens
            delegate: Item {
                id: scr
                required property var modelData
                required property int index
                readonly property var wins: panel.rev >= 0 ? panel.windowsOn(index + 1) : []
                x: (modelData.virtualX - panel.minX) * panel.s + 2
                y: (modelData.virtualY - panel.minY) * panel.s + panel.rowOf(modelData.virtualY) * (panel.stripH + 4)
                width: modelData.width * panel.s - 4
                height: modelData.height * panel.s + panel.stripH
                Rectangle {
                    id: face
                    objectName: "monitorFace"
                    width: parent.width
                    height: parent.height - panel.stripH - 4
                    radius: 6
                    color: panel.tk.surface_2
                    border.width: 1
                    border.color: panel.tk.border_strong
                    clip: true
                    Item {
                        objectName: "monitorWindows"
                        anchors.fill: parent
                        anchors.margins: 1
                        opacity: panel.running ? 1 : 0.5
                        Repeater {
                            model: scr.wins
                            delegate: Rectangle {
                                objectName: "monitorFrame"
                                required property var modelData
                                readonly property bool flagged: modelData.status === "unidentified" || modelData.status === "ambiguous"
                                                                || modelData.status === "offline"
                                visible: modelData.placeW !== undefined && modelData.placeW > 0
                                x: (modelData.placeX || 0) * parent.width
                                y: (modelData.placeY || 0) * parent.height
                                width: (modelData.placeW || 0) * parent.width
                                height: (modelData.placeH || 0) * parent.height
                                radius: 3
                                color: "transparent"
                                border.width: flagged ? 1.5 : 1
                                readonly property color edge: panel.frameColor(modelData.status)
                                border.color: edge
                                z: flagged ? 1 : 0
                            }
                        }
                    }
                }
                Txt {
                    objectName: "monitorLabel"
                    anchors.top: face.bottom
                    anchors.topMargin: 4
                    width: parent.width
                    height: panel.stripH
                    text: (scr.index + 1) + " · " + scr.modelData.width + " × " + scr.modelData.height
                          + (scr.wins.length > 0 ? " · " + scr.wins.length + (scr.wins.length === 1 ? " window" : " windows") : "")
                    role: "small"
                    tone: "muted"
                    figures: true
                    elide: Text.ElideRight
                }
            }
        }
    }
}
