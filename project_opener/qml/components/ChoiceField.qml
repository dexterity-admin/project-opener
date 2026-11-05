import QtQuick
import QtQuick.Controls.Basic as C

// A choice with its label above.  options: [{value, text}].  A control that opens says so: the 12 px chevron.
Column {
    id: f
    readonly property var tk: app.ui.tokens
    property string label: ""
    property var options: []
    property string value: ""
    signal picked(string value)
    spacing: 6
    width: 220

    function indexOfValue(v) {
        for (var i = 0; i < options.length; i++) if (String(options[i].value) === String(v)) return i
        return -1
    }

    Txt { visible: f.label !== ""; text: f.label; strong: true; width: f.width }
    C.ComboBox {
        id: box
        width: f.width
        height: 34
        model: f.options
        textRole: "text"
        valueRole: "value"
        currentIndex: f.indexOfValue(f.value)
        onActivated: (i) => f.picked(String(f.options[i].value))
        font.family: f.tk.face
        font.pixelSize: 13
        Accessible.name: f.label
        contentItem: Text {
            leftPadding: 12
            rightPadding: 30
            text: box.displayText
            font: box.font
            color: f.tk.text
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Icon {
            name: "caret-down"
            size: 12
            x: box.width - width - 12
            y: (box.height - height) / 2
        }
        background: Rectangle {
            radius: 10
            color: box.hovered ? f.tk.surface_2 : f.tk.surface
            border.width: box.activeFocus ? 2 : 1
            border.color: box.activeFocus ? f.tk.accent : f.tk.border_strong
        }
        delegate: C.ItemDelegate {
            required property var modelData
            required property int index
            width: box.width
            height: 32
            highlighted: box.highlightedIndex === index
            contentItem: Text {
                text: modelData.text
                font.family: f.tk.face
                font.pixelSize: 13
                color: f.tk.text
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle {
                radius: 8
                color: parent.highlighted ? f.tk.surface_2 : "transparent"
            }
        }
        popup: C.Popup {
            y: box.height + 4
            width: box.width
            padding: 4
            implicitHeight: Math.min(contentItem.implicitHeight + 8, 320)
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: box.popup.visible ? box.delegateModel : null
                currentIndex: box.highlightedIndex
            }
            background: Rectangle {
                radius: 10
                color: f.tk.surface
                border.width: 1
                border.color: f.tk.border_strong
            }
        }
    }
}
