import QtQuick

// The footlights strip: drives (app.watchers.roots), my tasks (app.tasks.mine), the office (app.hub.peers).
// Owner: builder 4.  Placeholder from the architecture skeleton; reads only `app` (the facade).
Item {
    id: footlights
    readonly property var tk: app.ui.tokens
}
