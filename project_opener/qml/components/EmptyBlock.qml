import QtQuick

// An empty state: one trade-word line and, where the data will appear, one action.  It spans the block it
// stands in (never a narrow island); the text measure stays under 420 px.
Item {
    id: e
    property string line: ""
    property string action: ""
    property string actionIcon: ""
    property string actionKind: "outline"
    signal triggered()
    implicitHeight: col.implicitHeight          // sized to its content: the card around it pads it (juror D2-4)
    implicitWidth: 300
    Column {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: 12
        Txt {
            width: Math.min(420, parent.width)
            text: e.line
            tone: "muted"
            wrapMode: Text.Wrap
            elide: Text.ElideNone
        }
        ActionButton {
            visible: e.action !== ""
            text: e.action
            icon: e.actionIcon
            kind: e.actionKind
            small: true
            onClicked: e.triggered()
        }
    }
}
