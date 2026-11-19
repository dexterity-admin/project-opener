import QtQuick

// One of Today's four stats (docs/DESIGN.md "Shape and space"): a 2 px `border_strong` rule on the top edge that
// turns `accent` on hover, a mono label, an Archivo numeral with its unit, then one line or one small graphic
// (the default children).  The numeral counts up from 0 once, after the card's rise (countUp(delay)); a later
// change of `value` shows at once.  `empty`: the source does not exist yet, so no numeral: the empty-state line
// and its one action instead.
Card {
    id: stat
    radius: 8
    property string label: ""
    property int value: 0
    property string unit: ""
    property string line: ""
    property string tip: ""
    property bool empty: false
    property string emptyLine: ""
    property string emptyAction: ""
    property string emptyIcon: ""
    signal emptyTriggered()
    property real arrive: 1
    property real shown: value
    default property alias graphic: slot.data
    readonly property bool hovered: hover.containsMouse

    Accessible.role: Accessible.Grouping
    Accessible.name: label + ": " + (empty ? emptyLine : value + " " + unit + (line !== "" ? ". " + line : ""))
    implicitHeight: col.y + col.implicitHeight + pad - 2

    function countUp(delay) {
        if (app.ui.k <= 0 || empty) { shown = Qt.binding(function () { return stat.value }); return }
        count.delay = delay
        shown = 0
        count.restart()
    }
    function finishCount() {               // the dock opening: the numeral shows its value now
        count.stop()
        shown = Qt.binding(function () { return stat.value })
    }
    SequentialAnimation {
        id: count
        property int delay: 0
        PauseAnimation { duration: count.delay }
        NumberAnimation {
            target: stat; property: "shown"; from: 0; to: stat.value
            duration: Math.round(900 * app.ui.k)
            easing.type: Easing.OutCubic
        }
        onFinished: stat.shown = Qt.binding(function () { return stat.value })
    }

    Rectangle {                             // the title-block rule, between the corner arcs
        x: stat.radius; y: 0
        width: stat.width - 2 * stat.radius; height: 2
        color: stat.hovered ? stat.tk.accent : stat.tk.border_strong
        Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k) } }
    }
    MouseArea { id: hover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
    Tip { visible: stat.tip !== "" && hover.containsMouse; text: stat.tip }

    Column {
        id: col
        x: stat.pad - 2; y: stat.pad - 2
        width: stat.width - 2 * (stat.pad - 2)
        spacing: 8
        Txt { width: parent.width; text: stat.label; role: "label" }
        Row {
            visible: !stat.empty
            spacing: 6
            height: 46
            Txt { id: num; text: String(Math.round(stat.shown)); role: "numeral"; height: parent.height; elide: Text.ElideNone }
            Txt {
                text: stat.unit
                tone: "muted"
                anchors.baseline: num.baseline
                elide: Text.ElideNone
                figures: true
            }
        }
        Item {
            id: slot
            visible: !stat.empty && children.length > 0
            width: parent.width
            height: childrenRect.height
        }
        Txt {
            visible: !stat.empty && stat.line !== ""
            width: parent.width
            text: stat.line
            role: "small"
            tone: "muted"
            figures: true
        }
        EmptyBlock {
            visible: stat.empty
            width: parent.width
            line: stat.emptyLine
            action: stat.emptyAction
            actionIcon: stat.emptyIcon
            onTriggered: stat.emptyTriggered()
        }
    }
}
