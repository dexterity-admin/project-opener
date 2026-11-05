import QtQuick

// A setting that is on or off: the label and one faint line saying what it does, the switch on the right.
Item {
    id: row
    property string label: ""
    property string help: ""
    property bool checked: false
    signal toggled(bool on)
    width: parent ? parent.width : 500
    implicitHeight: Math.max(34, txt.implicitHeight)
    height: implicitHeight
    Column {
        id: txt
        anchors.left: parent.left
        anchors.right: sw.left
        anchors.rightMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Txt { width: parent.width; text: row.label; strong: true }
        Txt { width: parent.width; visible: row.help !== ""; text: row.help; role: "small"; tone: "faint"; wrapMode: Text.Wrap; elide: Text.ElideNone }
    }
    Toggle {
        id: sw
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        checked: row.checked
        Accessible.name: row.label
        onToggled: (on) => row.toggled(on)
    }
}
