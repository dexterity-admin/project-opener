import QtQuick

// A short set of exclusive choices drawn as one pill (theme, motion, view mode).  options: [{value, text}].
// The chosen segment is the raised surface, its label unchanged: chrome, not colour.
Rectangle {
    id: seg
    readonly property var tk: app.ui.tokens
    property var options: []
    property string value: ""
    property string label: ""
    signal picked(string value)

    implicitHeight: 34
    implicitWidth: row.implicitWidth + 6
    radius: 17
    color: tk.surface
    border.width: 1
    border.color: tk.border_strong
    Accessible.role: Accessible.PageTabList
    Accessible.name: label

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 2
        Repeater {
            model: seg.options
            delegate: Rectangle {
                required property var modelData
                readonly property bool on: String(modelData.value) === String(seg.value)
                height: 28
                width: segText.implicitWidth + 24
                radius: 14
                color: on ? seg.tk.surface_3 : segMouse.containsMouse ? seg.tk.surface_2 : "transparent"
                Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k) } }
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.text
                Accessible.selected: on
                Txt {
                    id: segText
                    anchors.centerIn: parent
                    text: parent.modelData.text
                    strong: parent.on
                    tone: parent.on ? "ink" : "muted"
                    elide: Text.ElideNone
                }
                MouseArea {
                    id: segMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: seg.picked(String(parent.modelData.value))
                }
            }
        }
    }
}
