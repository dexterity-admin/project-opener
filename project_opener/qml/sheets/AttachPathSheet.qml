import QtQuick

// Attach a path to an unidentified or ambiguous window (candidates listed), or add the application.
// Owner: builder 4.  Placeholder from the architecture skeleton; reads only `app` (the facade).
Item {
    id: attachPathSheet
    readonly property var tk: app.ui.tokens
}
