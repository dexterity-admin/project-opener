import QtQuick

// The title row: an optional back link, an optional icon tile on the title's line, the title (24/600, one
// per page, a noun; Home keeps its greeting), one grey finding line under it, and the page's actions on the
// right (its one primary among them).  The title elides before the actions are pushed off.
Item {
    id: hdr
    property string title: ""
    property string subtitle: ""
    property string back: ""            // "Home", "Projects" ...: shows "← <back>" above the title
    property string icon: ""
    property string tint: ""
    default property alias actions: actionRow.data
    signal backClicked()

    width: parent ? parent.width : 800
    implicitHeight: (back !== "" ? 28 : 0) + Math.max(titleCol.implicitHeight, actionRow.implicitHeight)

    ActionButton {
        id: backBtn
        visible: hdr.back !== ""
        text: hdr.back
        icon: "arrow-left"
        kind: "link"
        small: true
        x: -10
        onClicked: hdr.backClicked()
    }
    IconTile {
        id: tile
        visible: hdr.icon !== ""
        icon: hdr.icon
        tint: hdr.tint
        size: 40
        y: titleCol.y + 2
    }
    Column {
        id: titleCol
        y: hdr.back !== "" ? 28 : 0
        anchors.left: hdr.icon !== "" ? tile.right : parent.left
        anchors.leftMargin: hdr.icon !== "" ? 14 : 0
        anchors.right: actionRow.left
        anchors.rightMargin: 16
        spacing: 4
        Txt {
            width: parent.width
            text: hdr.title
            role: "title"
            Accessible.role: Accessible.Heading
        }
        Txt {
            width: parent.width
            visible: hdr.subtitle !== ""
            text: hdr.subtitle
            tone: "muted"
            figures: true
        }
    }
    Row {
        id: actionRow
        anchors.right: parent.right
        y: titleCol.y + 2
        spacing: 8
    }
}
