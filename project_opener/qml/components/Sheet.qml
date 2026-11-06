import QtQuick
import QtQuick.Controls.Basic as C

// The one dialog grammar (docs/DESIGN.md "Dialogs"), as a sheet over the 40 % ink scrim:
// heading 16/600, one optional grey line naming the object, content (labels above fields), the inline error
// above the buttons, and the buttons right-aligned: Cancel, then the confirming button named for its action.
// Enter accepts and Esc cancels; for a destructive action the confirming button is outlined in the negative
// colour and Cancel takes the default, so Enter never deletes.  At most 640 px tall (fits a 768 px laptop):
// the content scrolls.  While it is taller than the body, the body ends between two rows (never through one),
// a 24 px fade sits at its foot and the scrollbar stays visible; Tab scrolls the focused field into view.
// Sheets are loaded by Main.openSheet and close with Main.closeSheet.
FocusScope {
    id: sheet
    readonly property var tk: app.ui.tokens
    property string title: ""
    property string subtitle: ""
    property string confirmText: "Save"
    property string confirmTooltip: ""         // a rule the sheet would otherwise say in a sentence (juror T2-4)
    property bool destructive: false
    property bool confirmEnabled: true
    property bool showCancel: true
    property string cancelText: "Cancel"
    property string error: ""
    property int sheetWidth: 560
    property bool busy: false
    default property alias content: body.data
    property alias footerExtra: extra.data
    signal accepted()
    signal cancelled()

    anchors.fill: parent
    focus: true

    function close() { Window.window.closeSheet() }
    function accept() {
        if (!confirmEnabled) return
        error = ""
        accepted()
    }
    function cancel() {
        cancelled()
        close()
    }
    function fail(message) { error = message }

    // Scroll the body so `item` (a control that took the focus, by Tab or by click) is whole and clear of the
    // fade, together with the largest block around it that fits (a field with its label, a switch row).
    function ensureVisible(item) {
        if (!item || !flick.scrolls) return
        var p = item, shown = item
        while (p && p !== body) {
            if (p.height <= flick.height - 32) shown = p
            p = p.parent
        }
        if (p !== body) return
        var r = shown.mapToItem(body, 0, 0)
        var y = flick.contentY
        if (r.y < y) y = r.y - 4
        else if (r.y + shown.height + 28 > y + flick.height) y = r.y + shown.height + 28 - flick.height
        flick.contentY = Math.max(0, Math.min(y, flick.contentHeight - flick.height))
    }
    Connections {
        target: sheet.Window.window
        function onActiveFocusItemChanged() { sheet.ensureVisible(sheet.Window.window.activeFocusItem) }
    }

    // The body's height when it scrolls: the bottom of the last whole row that fits, plus 24 px of the next
    // row under the fade (the cue that there is more), so no field is cut through.  A plain Column taller
    // than the room (a tab's page of rows) is looked into for its own rows; a field keeps its label.
    function snappedBody(room) {
        var best = rowEdge(body, 0, room, 0)
        return best > 0 ? best : room
    }
    function rowEdge(item, offset, room, best) {
        for (var i = 0; i < item.children.length; i++) {
            var c = item.children[i]
            if (!c.visible || c.height <= 0) continue
            var edge = offset + c.y + c.height + 24
            if (edge <= room) { if (edge > best) best = edge }
            else if (String(c).indexOf("QQuickColumn") === 0) best = rowEdge(c, offset + c.y, room, best)
        }
        return best
    }

    Keys.onEscapePressed: cancel()
    Keys.onReturnPressed: (event) => { if (destructive) cancel(); else accept() }
    Keys.onEnterPressed: (event) => { if (destructive) cancel(); else accept() }

    Rectangle {
        id: scrim
        anchors.fill: parent
        color: sheet.tk.scrim
        opacity: 0
        Component.onCompleted: opacity = 1
        Behavior on opacity { NumberAnimation { duration: Math.round(160 * app.ui.k) } }
        MouseArea { anchors.fill: parent; onClicked: sheet.cancel() }
    }

    Item {
        id: frame
        width: Math.min(sheet.sheetWidth, sheet.width - 64)
        readonly property real bodyRoom: Math.min(640, sheet.height - 48) - head.height - foot.height - 48
        readonly property real bodyHeight: flick.contentHeight <= bodyRoom ? flick.contentHeight : sheet.snappedBody(bodyRoom)
        height: head.height + bodyHeight + foot.height + 48
        x: (sheet.width - width) / 2
        y: (sheet.height - height) / 2 + rise
        property real rise: app.ui.k > 0 ? 12 : 0
        opacity: app.ui.k > 0 ? 0 : 1
        Component.onCompleted: if (app.ui.k > 0) arrive.start()
        ParallelAnimation {
            id: arrive
            NumberAnimation { target: frame; property: "rise"; to: 0; duration: Math.round(220 * app.ui.k); easing.type: Easing.OutCubic }
            NumberAnimation { target: frame; property: "opacity"; to: 1; duration: Math.round(180 * app.ui.k); easing.type: Easing.OutCubic }
        }

        // the floating shadow: offset rings on dark only (on light they read as a second, misregistered shape;
        // the surface's border_strong ring floats it there)
        Rectangle { visible: app.ui.dark; x: -4; y: 10; width: parent.width + 8; height: parent.height + 4; radius: 20; color: sheet.tk.shadow_soft }
        Rectangle { visible: app.ui.dark; x: 0; y: 5; width: parent.width; height: parent.height; radius: 16; color: sheet.tk.shadow_q }
        Rectangle {
            anchors.fill: parent
            radius: 16
            color: sheet.tk.surface
            border.width: 1
            border.color: sheet.tk.border_strong
            MouseArea { anchors.fill: parent }
        }

        Column {
            id: head
            x: 24
            y: 22
            width: frame.width - 48
            spacing: 4
            Text {
                width: parent.width
                text: sheet.title
                font.family: sheet.tk.face
                font.pixelSize: 21
                font.weight: Font.DemiBold
                color: sheet.tk.text
                wrapMode: Text.Wrap
                Accessible.role: Accessible.Heading
            }
            Txt { width: parent.width; visible: sheet.subtitle !== ""; text: sheet.subtitle; tone: "muted" }
            Item { width: 1; height: 12 }
        }

        Flickable {
            id: flick
            readonly property bool scrolls: contentHeight > height + 1
            x: 24
            anchors.top: head.bottom
            height: frame.bodyHeight
            width: frame.width - 48
            contentHeight: body.implicitHeight + 4
            contentWidth: width
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            flickableDirection: Flickable.VerticalFlick
            C.ScrollBar.vertical: bar
            Column {
                id: body
                width: flick.width
                spacing: 16
            }
        }
        // the scroll cue: a fade over the body's foot while more lies below, and the scrollbar in the
        // sheet's right margin (never over a field), shown whenever the body scrolls
        Rectangle {
            id: fade
            x: flick.x
            y: flick.y + flick.height - height
            width: flick.width
            height: 24
            visible: flick.scrolls && flick.contentY < flick.contentHeight - flick.height - 1
            property color surf: sheet.tk.surface
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(fade.surf.r, fade.surf.g, fade.surf.b, 0) }
                GradientStop { position: 1.0; color: fade.surf }
            }
        }
        C.ScrollBar {
            id: bar
            parent: frame
            x: frame.width - 18
            y: flick.y
            width: 10
            height: flick.height
            policy: flick.scrolls ? C.ScrollBar.AlwaysOn : C.ScrollBar.AlwaysOff
            padding: 2
            contentItem: Rectangle { implicitWidth: 6; radius: 3; color: sheet.tk.border_strong }
            background: Item {}
        }

        Column {
            id: foot
            x: 24
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 20
            width: frame.width - 48
            spacing: 12
            Item { width: 1; height: 4 }
            Txt {
                width: parent.width
                visible: sheet.error !== ""
                text: sheet.error
                tone: "bad"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
            }
            Item {
                width: parent.width
                height: 34
                Row { id: extra; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; spacing: 8 }
                Row {
                    anchors.right: parent.right
                    spacing: 8
                    ActionButton {
                        id: cancelBtn
                        visible: sheet.showCancel
                        text: sheet.cancelText
                        kind: "ghost"
                        onClicked: sheet.cancel()
                    }
                    ActionButton {
                        id: okBtn
                        text: sheet.confirmText
                        kind: sheet.destructive ? "danger" : "primary"
                        tooltip: sheet.confirmTooltip
                        available: sheet.confirmEnabled && !sheet.busy
                        onClicked: sheet.accept()
                    }
                }
            }
        }
    }
}
