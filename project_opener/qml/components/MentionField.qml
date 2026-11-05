import QtQuick

// Text field with the @ picker (app.hub.mentionAt / mentionCandidates / insertMention).
// Owner: builder 4.  Placeholder from the architecture skeleton; reads only `app` (the facade).
Item {
    id: mentionField
    readonly property var tk: app.ui.tokens
}
