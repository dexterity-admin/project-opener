import QtQuick
import "../components"

// A confirmation in the one dialog grammar: the question names the object and its consequence; the confirming
// button names the action.  Destructive: outlined in the negative colour and Cancel takes the default, so
// Enter never deletes.  Main.confirm(title, body, confirmText, destructive, onOk) opens it.
Sheet {
    id: s
    property string body: ""
    property string confirm: "Continue"
    property var onCancel: null
    title: "Are you sure?"
    confirmText: confirm
    sheetWidth: 480

    onAccepted: {
        Window.window.closeSheet()
        Window.window.confirmed()
    }
    onCancelled: if (s.onCancel) s.onCancel()

    Txt {
        width: parent.width
        text: s.body
        tone: "muted"
        wrapMode: Text.Wrap
        elide: Text.ElideNone
    }
}
