import QtQuick

// Toast stack fed by app.toast / app.toastAction.
// Owner: builder 4.  Placeholder from the architecture skeleton; reads only `app` (the facade).
Item {
    id: toasts
    readonly property var tk: app.ui.tokens
}
