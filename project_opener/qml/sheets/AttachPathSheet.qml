import QtQuick
import "../components"

// Attach a path to a window the watcher could not identify (the honesty rule: the user says it once).
// An ambiguous window offers its candidates; an unsaved document can instead add its application as an item.
Sheet {
    id: s
    property string entryKey: ""
    property string appName: ""
    property var candidates: []
    property bool unsaved: false
    property string picked: ""
    title: "Attach a path"
    property string windowTitle: ""
    subtitle: "A window titled ‘" + windowTitle + "’" + (appName !== "" ? " · " + appName : "")
    Component.onCompleted: pathField.focusInput()
    confirmText: "Attach path"
    confirmEnabled: pathField.text.trim() !== ""
    sheetWidth: 600

    onAccepted: {
        var ok = Window.window.safe(function () { app.capture.attachPath(s.entryKey, pathField.text) })
        if (ok) s.close()
    }
    footerExtra: [
        ActionButton {
            visible: s.appName !== ""
            text: "Add " + s.appName + " itself"
            small: true
            tooltip: "Opens the application with the activity, without a document"
            onClicked: { if (Window.window.safe(function () { app.capture.addAsApplication(s.entryKey) })) s.close() }
        }
    ]

    Txt {
        width: parent.width
        text: s.unsaved ? "The document has no file yet. Save it, then attach where it was saved."
             : s.candidates.length > 0 ? "Its title matches more than one file; nothing was guessed. Pick the right one, or give the path."
             : "The application did not say which file it has open. Give the path once; from then on it is an item."
        tone: "muted"
        wrapMode: Text.Wrap
        elide: Text.ElideNone
    }
    Column {
        visible: s.candidates.length > 0
        width: parent.width
        Repeater {
            model: s.candidates
            delegate: Rectangle {
                required property var modelData
                width: parent ? parent.width : 500
                height: 40
                radius: 10
                color: pathField.text === modelData ? s.tk.accent_soft : cm.containsMouse ? s.tk.surface_2 : "transparent"
                Icon { id: ci; x: 12; anchors.verticalCenter: parent.verticalCenter; name: "file" }
                Txt { anchors.left: ci.right; anchors.leftMargin: 10; anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; text: parent.modelData; elide: Text.ElideMiddle }
                MouseArea { id: cm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: pathField.text = parent.modelData }
            }
        }
    }
    Row {
        spacing: 12
        Field { id: pathField; width: 440; label: "Path"; placeholder: "\\\\nas01\\Project\\P12513\\CAD\\Lot 7.dwg"; onAccepted: s.accept() }
        ActionButton {
            y: 25
            text: "Browse"
            icon: "folder-open"
            onClicked: { var p = app.settings.browseFile("The file this window has open", "", ""); if (p !== "") pathField.text = p }
        }
    }
}
