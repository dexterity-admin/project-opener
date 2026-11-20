import QtQuick
import QtQuick.Effects

// The surface of a floating sheet or the palette (docs/DESIGN.md "Glass"): in rich motion on the graphics card,
// `surface` at 94 % over a 14 px blur (saturation 1.3) of the window's ground behind it; below rich, or on the
// software renderer (no blur), opaque `surface`.  The ground (Main.qml `ground`: sidebar and pages) never holds
// a floating surface, so glass never blurs glass.  `track` takes the floating frame's moving y (its rise) so the
// blurred patch follows it.
Item {
    id: g
    readonly property var tk: app.ui.tokens
    property real radius: 10
    property real track: 0
    property color borderColor: tk.border_strong
    property color base: tk.surface
    readonly property Item ground: Window.window ? Window.window.ground || null : null
    readonly property bool on: visible && app.ui.ambient && app.ui.backend !== "software" && ground !== null

    ShaderEffectSource {
        id: src
        visible: false
        width: g.width
        height: g.height
        sourceItem: g.on ? g.ground : null
        live: g.on
        recursive: false
        sourceRect: {
            var t = g.track + g.width + g.height          // re-evaluate as the frame moves or resizes
            if (!g.on || t !== t) return Qt.rect(0, 0, 0, 0)
            var p = g.mapToItem(g.ground, 0, 0)
            return Qt.rect(p.x, p.y, g.width, g.height)
        }
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: g.radius
        visible: false
        layer.enabled: g.on
    }
    MultiEffect {
        anchors.fill: parent
        visible: g.on
        source: src
        blurEnabled: true
        blur: 0.9
        blurMax: 32
        saturation: 0.3
        maskEnabled: true
        maskSource: mask
    }
    Rectangle {
        anchors.fill: parent
        radius: g.radius
        color: g.on ? Qt.rgba(g.base.r, g.base.g, g.base.b, 0.94) : g.base
        border.width: 1
        border.color: g.borderColor
    }
}
