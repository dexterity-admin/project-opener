import QtQuick
import QtQuick.Controls.Basic as C

// The one dialog grammar (docs/DESIGN.md "Dialogs"), as a sheet over the 40 % ink scrim:
// heading 16/600, one optional grey line naming the object, content (labels above fields), the inline error
// above the buttons, and the buttons right-aligned: Cancel, then the confirming button named for its action.
// Enter accepts and Esc cancels; for a destructive action the confirming button is outlined in the negative
// colour and Cancel takes the default, so Enter never deletes.  At most 640 px tall (fits a 768 px laptop):
// the content scrolls.  Sheets are loaded by Main.openSheet and close with Main.closeSheet.
FocusScope {
    id: sheet
    readonly property var tk: app.ui.tokens
    property string title: ""
    property string subtitle: ""
    property string confirmText: "Save"
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
        height: Math.min(640, sheet.height - 48, head.height + flick.contentHeight + foot.height + 48)
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

        Rectangle { x: -4; y: 10; width: parent.width + 8; height: parent.height + 4; radius: 20; color: sheet.tk.shadow_soft }
        Rectangle { x: 0; y: 5; width: parent.width; height: parent.height; radius: 16; color: sheet.tk.shadow_q }
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
            x: 24
            anchors.top: head.bottom
            anchors.bottom: foot.top
            width: frame.width - 48
            contentHeight: body.implicitHeight + 4
            contentWidth: width
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            C.ScrollBar.vertical: C.ScrollBar { policy: flick.contentHeight > flick.height ? C.ScrollBar.AsNeeded : C.ScrollBar.AlwaysOff }
            Column {
                id: body
                width: flick.width
                spacing: 16
            }
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
                        available: sheet.confirmEnabled && !sheet.busy
                        onClicked: sheet.accept()
                    }
                }
            }
        }
    }
}
