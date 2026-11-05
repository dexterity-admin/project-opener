import QtQuick

// One Settings section: a card with its heading, one finding line, and its rows (labels above controls,
// one grammar: DESIGN.md "Settings rows").
Card {
    id: sec
    property string title: ""
    property string line: ""
    property string key: ""
    default property alias rows: body.data
    width: parent ? parent.width : 600
    height: col.implicitHeight + 2 * pad

    Column {
        id: col
        x: sec.pad; y: sec.pad
        width: sec.width - 2 * sec.pad
        spacing: 16
        Column {
            width: parent.width
            spacing: 4
            Txt { text: sec.title; role: "heading"; Accessible.role: Accessible.Heading }
            Txt { visible: sec.line !== ""; width: parent.width; text: sec.line; tone: "muted"; wrapMode: Text.Wrap; elide: Text.ElideNone }
        }
        Column {
            id: body
            width: parent.width
            spacing: 18
        }
    }
}
