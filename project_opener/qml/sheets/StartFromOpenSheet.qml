import QtQuick

// Start from what's open: every window with its pill, non-file windows unticked, name + project, Start activity N items (app.capture.startCandidates).
// Owner: builder 4.  Placeholder from the architecture skeleton; reads only `app` (the facade).
Item {
    id: startFromOpenSheet
    readonly property var tk: app.ui.tokens
}
