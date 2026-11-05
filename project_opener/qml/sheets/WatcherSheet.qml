import QtQuick

// New/edit watcher: kind, target, events, who to tell (toast, @mentions, Cliq).
// Owner: builder 4.  Placeholder from the architecture skeleton; reads only `app` (the facade).
Item {
    id: watcherSheet
    readonly property var tk: app.ui.tokens
}
