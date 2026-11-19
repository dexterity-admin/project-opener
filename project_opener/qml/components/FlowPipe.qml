import QtQuick

// The line of flow (brand motion, docs/DESIGN.md "Motion"): a hairline track between two nodes; the teal fill
// draws to the far node (1.6 s), the far node fills amber, then in rich motion an amber slug travels the pipe
// every few seconds while the window is active.  Purposeful: one pass, then still.  Off: drawn, still.
// `play()` starts it (the page's arrival); `loop` gates the slug (the page sets it false while the dock is open).
Item {
    id: pipe
    readonly property var tk: app.ui.tokens
    property bool loop: true
    property real drawn: 1                  // 0..1: the fill's reach
    property real slug: -1                  // 0..1 while the slug travels; -1 = none
    readonly property real span: width - 2 * node
    readonly property int node: 5
    readonly property bool ambient: Window.window !== null && Window.window.ambientOn === true
    implicitHeight: 14

    function play() {
        if (app.ui.k <= 0) { drawn = 1; return }
        drawn = 0
        draw.restart()
    }

    Rectangle {                             // track
        x: pipe.node; width: pipe.span; height: 1.5
        anchors.verticalCenter: parent.verticalCenter
        color: pipe.tk.border_strong
    }
    Rectangle {                             // fill
        x: pipe.node; width: pipe.span * pipe.drawn; height: 3; radius: 1.5
        anchors.verticalCenter: parent.verticalCenter
        color: pipe.tk.teal
    }
    Rectangle {                             // slug
        visible: pipe.slug >= 0
        width: 14; height: 3; radius: 1.5
        x: pipe.node + (pipe.span - width) * Math.max(0, pipe.slug)
        anchors.verticalCenter: parent.verticalCenter
        color: pipe.tk.action
    }
    Rectangle {                             // near node
        width: 2 * pipe.node; height: width; radius: pipe.node
        anchors.verticalCenter: parent.verticalCenter
        color: pipe.tk.surface
        border.width: 1.5
        border.color: pipe.tk.teal
    }
    Rectangle {                             // far node: amber once the fill arrives
        x: pipe.width - width
        width: 2 * pipe.node; height: width; radius: pipe.node
        anchors.verticalCenter: parent.verticalCenter
        color: pipe.drawn >= 1 ? pipe.tk.action : pipe.tk.surface
        border.width: 1.5
        border.color: pipe.drawn >= 1 ? pipe.tk.action : pipe.tk.teal
        Behavior on color { ColorAnimation { duration: Math.round(400 * app.ui.k) } }
    }

    SequentialAnimation {
        id: draw
        PauseAnimation { duration: Math.round(500 * app.ui.k) }
        NumberAnimation {
            target: pipe; property: "drawn"; from: 0; to: 1
            duration: Math.round(1600 * app.ui.k)
            easing.type: Easing.Bezier; easing.bezierCurve: [0.65, 0, 0.35, 1, 1, 1]
        }
    }
    SequentialAnimation {
        running: pipe.loop && pipe.visible && pipe.drawn >= 1 && pipe.ambient
        loops: Animation.Infinite
        PauseAnimation { duration: 2000 }
        NumberAnimation {
            target: pipe; property: "slug"; from: 0; to: 1; duration: 1200
            easing.type: Easing.Bezier; easing.bezierCurve: [0.65, 0, 0.35, 1, 1, 1]
        }
        PropertyAction { target: pipe; property: "slug"; value: -1 }
        onRunningChanged: if (!running) pipe.slug = -1
    }
}
