import QtQuick
import QtQuick.Controls.Basic as C

// The command palette (Ctrl+K in the app, Ctrl+Alt+K from anywhere): one field and the hits grouped under
// grey headings (Activities, Projects, Items, Actions) as in 3.2.  Arrow keys skip headings; actions show
// their shortcut on the right; a miss says "Nothing matches ‘…’".  It floats over the 40 % scrim.
Item {
    id: pal
    readonly property var tk: app.ui.tokens
    property bool open: false
    property int current: -1
    visible: open || fade.running
    opacity: open ? 1 : 0
    Behavior on opacity { NumberAnimation { id: fade; duration: Math.round(150 * app.ui.k) } }

    function show(q) {
        open = true
        field.text = q
        app.ui.setPaletteQuery(q)
        current = firstHit(0, 1)
        field.forceActiveFocus()
    }
    function hide() { open = false; field.focus = false }
    function firstHit(from, step) {
        var m = app.ui.palette
        for (var i = from; i >= 0 && i < m.count(); i += step)
            if (m.get(i).rowKind === "hit") return i
        return -1
    }
    function run(i) {
        var row = app.ui.palette.get(i)
        if (!row || row.rowKind !== "hit") return
        hide()
        Window.window.runAction(row.action, row.target)
    }

    Rectangle { anchors.fill: parent; color: pal.tk.scrim }
    MouseArea { anchors.fill: parent; onClicked: pal.hide() }

    Item {
        id: box
        width: Math.min(640, parent.width - 96)
        height: Math.min(parent.height - 160, 72 + list.contentHeight + (list.count === 0 ? 48 : 16))
        x: (parent.width - width) / 2
        y: Math.max(48, parent.height * 0.14)
        Rectangle { x: -3; y: 8; width: parent.width + 6; height: parent.height + 4; radius: 18; color: pal.tk.shadow_soft }
        Rectangle { x: 0; y: 4; width: parent.width; height: parent.height; radius: 16; color: pal.tk.shadow_q }
        Rectangle {
            anchors.fill: parent
            radius: 16
            color: pal.tk.surface
            border.width: 1
            border.color: pal.tk.border_strong
            MouseArea { anchors.fill: parent }

            Icon { id: lens; x: 18; y: 18; name: "magnifying-glass"; size: 18 }
            C.TextField {
                id: field
                anchors.left: lens.right
                anchors.leftMargin: 10
                anchors.right: parent.right
                anchors.rightMargin: 16
                y: 10
                height: 36
                placeholderText: "Open an activity, a project, an item or an action"
                placeholderTextColor: pal.tk.text_faint
                color: pal.tk.text
                font.family: pal.tk.face
                font.pixelSize: 16
                background: Item {}
                Accessible.name: "Search"
                onTextEdited: { app.ui.setPaletteQuery(text); pal.current = pal.firstHit(0, 1) }
                Keys.onEscapePressed: pal.hide()
                Keys.onDownPressed: { var n = pal.firstHit(pal.current + 1, 1); if (n >= 0) pal.current = n }
                Keys.onUpPressed: { var n = pal.firstHit(pal.current - 1, -1); if (n >= 0) pal.current = n }
                Keys.onReturnPressed: pal.run(pal.current)
                Keys.onEnterPressed: pal.run(pal.current)
            }
            Rectangle { x: 0; y: 56; width: parent.width; height: 1; color: pal.tk.border }

            Txt {
                visible: list.count === 0
                x: 20; y: 72
                text: "Nothing matches ‘" + field.text + "’"
                tone: "muted"
            }
            ListView {
                id: list
                x: 8; y: 64
                width: parent.width - 16
                height: parent.height - 72
                clip: true
                model: app.ui.palette
                currentIndex: pal.current
                boundsBehavior: Flickable.StopAtBounds
                delegate: Item {
                    width: list.width
                    height: model.rowKind === "heading" ? 30 : 44
                    Txt {
                        visible: model.rowKind === "heading"
                        x: 12
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 4
                        text: model.title
                        role: "small"
                        tone: "faint"
                    }
                    Rectangle {
                        visible: model.rowKind === "hit"
                        anchors.fill: parent
                        radius: 10
                        color: index === pal.current ? pal.tk.surface_2 : rowMouse.containsMouse ? pal.tk.surface_2 : "transparent"
                        Icon { id: g; x: 12; anchors.verticalCenter: parent.verticalCenter; name: model.glyph }
                        Dot { visible: model.dotColor !== ""; tint: model.dotColor; x: 34; anchors.verticalCenter: parent.verticalCenter }
                        Column {
                            x: 48
                            width: parent.width - 48 - sc.width - 20
                            anchors.verticalCenter: parent.verticalCenter
                            Txt { width: parent.width; text: model.title; strong: index === pal.current }
                            Txt { width: parent.width; visible: model.subtitle !== ""; text: model.subtitle; role: "small"; tone: "faint"; elide: Text.ElideMiddle }
                        }
                        Txt {
                            id: sc
                            anchors.right: parent.right
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            text: model.shortcut
                            role: "small"
                            tone: "faint"
                            figures: true
                        }
                        MouseArea {
                            id: rowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: pal.run(index)
                        }
                    }
                }
            }
        }
    }
}
