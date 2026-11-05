import QtQuick
import QtQuick.Controls.Basic as C

// "…": the rest of an object's actions in a floating menu.  entries: [{text, icon, action, danger, hidden}];
// a {text: "-"} entry is a divider.  Emits triggered(action).
Item {
    id: mb
    readonly property var tk: app.ui.tokens
    property var entries: []
    property string tooltip: "More"
    property bool small: false
    signal triggered(string action)
    width: btn.width
    height: btn.height

    ActionButton {
        id: btn
        icon: "dots-three"
        kind: "outline"
        small: mb.small
        tooltip: mb.tooltip
        onClicked: menu.open()
    }
    C.Popup {
        id: menu
        y: btn.height + 6
        x: btn.width - width
        width: 240
        padding: 6
        modal: false
        focus: true
        closePolicy: C.Popup.CloseOnEscape | C.Popup.CloseOnPressOutside
        background: Item {
            Rectangle { x: -2; y: 6; width: parent.width + 4; height: parent.height + 2; radius: 14; color: mb.tk.shadow_soft }
            Rectangle { anchors.fill: parent; radius: 12; color: mb.tk.surface; border.width: 1; border.color: mb.tk.border_strong }
        }
        contentItem: Column {
            Repeater {
                model: mb.entries
                delegate: Item {
                    required property var modelData
                    width: 228
                    visible: !modelData.hidden
                    height: !visible ? 0 : modelData.text === "-" ? 9 : 34
                    Rectangle {
                        visible: parent.modelData.text === "-"
                        width: parent.width; height: 1; y: 4
                        color: mb.tk.border
                    }
                    Rectangle {
                        visible: parent.modelData.text !== "-"
                        anchors.fill: parent
                        radius: 8
                        color: rowMouse.containsMouse ? mb.tk.surface_2 : "transparent"
                        Icon {
                            id: ic
                            x: 10
                            anchors.verticalCenter: parent.verticalCenter
                            name: parent.parent.modelData.icon || ""
                            size: 14
                            tone: parent.parent.modelData.danger ? "bad" : "muted"
                        }
                        Txt {
                            anchors.left: ic.right
                            anchors.leftMargin: 10
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: parent.parent.modelData.text
                            tone: parent.parent.modelData.danger ? "bad" : "ink"
                        }
                        MouseArea {
                            id: rowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { menu.close(); mb.triggered(parent.parent.modelData.action) }
                        }
                    }
                }
            }
        }
    }
}
