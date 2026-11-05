import QtQuick

// Items in launch order (an activity's, or a project's): the step number, the kind glyph, the name over the
// portable path (muted, elided in the middle), the group, the health pill, and a fixed action slot per row
// (Open; the editor holds the rest) so every pill ends on one line.  `model` rows: ITEM_ROLES.
Column {
    id: list
    readonly property var tk: app.ui.tokens
    property var items
    property bool showProject: false
    property bool numbered: true
    property int maxRows: 0                 // 0 = all
    signal openItem(string itemId)
    signal editItem(string itemId)
    spacing: 0

    Repeater {
        id: rep
        model: list.items
        delegate: Item {
            width: list.width
            visible: list.maxRows === 0 || index < list.maxRows
            height: visible ? (list.tk.pad < 20 ? 44 : 52) : 0
            opacity: model.itemEnabled ? 1 : 0.55
            Rectangle { width: parent.width; height: 1; color: list.tk.border; visible: index > 0 }
            Txt {
                id: num
                visible: list.numbered
                width: list.numbered ? 22 : 0
                anchors.verticalCenter: parent.verticalCenter
                text: model.order
                role: "small"
                tone: "faint"
                figures: true
            }
            Icon { id: glyph; anchors.left: num.right; anchors.verticalCenter: parent.verticalCenter; name: model.glyph }
            Column {
                anchors.left: glyph.right
                anchors.leftMargin: 10
                anchors.right: grp.left
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                Txt { width: parent.width; text: model.name + (model.itemEnabled ? "" : " · off"); strong: true }
                Txt {
                    width: parent.width
                    text: [model.path, list.showProject ? model.projectTitle : "", model.profileName !== "" ? "profile " + model.profileName : ""]
                          .filter(function (s) { return s && s !== "" }).join(" · ")
                    role: "small"
                    tone: "faint"
                    elide: Text.ElideMiddle
                }
            }
            Txt {
                id: grp
                width: 96
                anchors.right: pill.left
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: model.group
                role: "small"
                tone: "faint"
                horizontalAlignment: Text.AlignRight
            }
            Item {
                id: pill
                width: 130
                height: 20
                anchors.right: actions.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                StatusPill { anchors.right: parent.right; status: model.healthLevel; label: model.healthLabel }
            }
            Row {
                id: actions
                width: 72
                layoutDirection: Qt.RightToLeft
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 4
                ActionButton { icon: "pencil-simple"; kind: "ghost"; small: true; tooltip: "Edit"; onClicked: list.editItem(model.itemId) }
                ActionButton { icon: "arrow-square-out"; kind: "ghost"; small: true; tooltip: "Open " + model.name; onClicked: list.openItem(model.itemId) }
            }
            Tip { visible: hov.containsMouse && model.resolved !== "" && model.resolved !== model.path; text: "On this PC: " + model.resolved }
            MouseArea { id: hov; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton; z: -1 }
        }
    }
    EmptyBlock {
        visible: rep.count === 0
        width: list.width
        line: "No items yet."
    }
    property alias count: rep.count
}
