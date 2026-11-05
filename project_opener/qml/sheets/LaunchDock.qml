import QtQuick

// The launch dock: the scene's opening act; rows arrive in launch order and pills settle (app.activities.dock).
// Owner: builder 4.  Placeholder from the architecture skeleton; reads only `app` (the facade).
Item {
    id: launchDock
    readonly property var tk: app.ui.tokens
}
