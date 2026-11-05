import QtQuick

// Page tabs (Team Hub, Settings, the activity editor): labels with their count in grey; the current tab is
// the raised pill.  tabs: [{key, text, count}].  They wrap to a second line when the width is short.
Flow {
    id: tabBar
    readonly property var tk: app.ui.tokens
    property var tabs: []
    property string current: ""
    signal picked(string key)
    width: parent ? parent.width : 600
    spacing: 4
    Accessible.role: Accessible.PageTabList

    Repeater {
        model: tabBar.tabs
        delegate: Rectangle {
            required property var modelData
            readonly property bool on: modelData.key === tabBar.current
            height: 32
            width: tabRow.implicitWidth + 28
            radius: 16
            color: on ? tabBar.tk.surface_2 : tabMouse.containsMouse ? tabBar.tk.surface : "transparent"
            Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k) } }
            activeFocusOnTab: true
            border.width: activeFocus ? 2 : 0
            border.color: tabBar.tk.accent
            Keys.onReturnPressed: tabBar.picked(modelData.key)
            Keys.onSpacePressed: tabBar.picked(modelData.key)
            Accessible.role: Accessible.PageTab
            Accessible.name: modelData.text
            Accessible.selected: on
            Row {
                id: tabRow
                anchors.centerIn: parent
                spacing: 6
                Txt { text: parent.parent.modelData.text; strong: parent.parent.on; elide: Text.ElideNone }
                Txt {
                    visible: (parent.parent.modelData.count || 0) > 0
                    text: parent.parent.modelData.count || ""
                    tone: "faint"
                    figures: true
                    elide: Text.ElideNone
                }
            }
            MouseArea {
                id: tabMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: tabBar.picked(parent.modelData.key)
            }
        }
    }
}
