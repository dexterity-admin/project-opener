import QtQuick
import QtQuick.Controls.Basic as C

// One form field in the dialog grammar: the label above (500 weight), the input (34 px, radius 10), an
// optional faint help line, and the error outline (negative colour) that clears as the user types.
// Placeholders are examples, never labels.
Column {
    id: f
    readonly property var tk: app.ui.tokens
    property string label: ""
    property string help: ""
    property alias text: input.text
    property alias placeholder: input.placeholderText
    property alias input: input
    property alias echoMode: input.echoMode
    property bool invalid: false
    property string trailingIcon: ""
    signal accepted()
    signal trailingClicked()
    spacing: 6
    width: 280

    function focusInput() { input.forceActiveFocus() }

    Txt {
        visible: f.label !== ""
        text: f.label
        strong: true
        width: f.width
    }
    C.TextField {
        id: input
        width: f.width
        height: 34
        leftPadding: 12
        rightPadding: f.trailingIcon !== "" ? 36 : 12
        font.family: f.tk.face
        font.pixelSize: 13
        color: f.tk.text
        placeholderTextColor: f.tk.text_faint
        selectionColor: f.tk.accent_soft
        selectedTextColor: f.tk.text
        selectByMouse: true
        onTextEdited: f.invalid = false
        onAccepted: f.accepted()
        Accessible.name: f.label
        background: Rectangle {
            radius: 10
            color: f.tk.surface
            border.width: input.activeFocus || f.invalid ? 2 : 1
            border.color: f.invalid ? f.tk.danger : input.activeFocus ? f.tk.accent : f.tk.border_strong
        }
        Icon {
            visible: f.trailingIcon !== ""
            name: f.trailingIcon
            anchors.right: parent.right
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            MouseArea {
                anchors.fill: parent
                anchors.margins: -6
                cursorShape: Qt.PointingHandCursor
                onClicked: f.trailingClicked()
            }
        }
    }
    Txt {
        visible: f.help !== ""
        text: f.help
        role: "small"
        tone: "faint"
        width: f.width
        wrapMode: Text.Wrap
        elide: Text.ElideNone
    }
}
