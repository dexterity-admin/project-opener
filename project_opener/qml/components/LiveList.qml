import QtQuick

// Open now: what the watcher sees while the activity runs (app.capture.live, worst first; builder 2).
// The honesty rule: windows it could not identify are listed as seen, in Desk's dashed tile, with the
// title in quotes, the reason, and the two actions: Attach a path, Ignore.  Ambiguous rows name their
// candidates; nothing is guessed.  Identified rows carry the path's health pill and "New" when they are not
// items yet.  Rows are keyed by entryKey: a row never jumps under the pointer (the model syncs in place).
// Round 2: one capture-state line heads the list (juror U4); with capture off or paused the rows are the last
// snapshot's, greyed under "Capture off · last snapshot 14:32".  Two words for "no file" (T3): "Needs a path"
// (a document whose path is unknown) and "Not a file" (an application window or an unsaved document).
// Ignore leaves the window out of this activity (owner decision, 5 November 2026), as the pill's Ignore does.
Column {
    id: live
    readonly property var tk: app.ui.tokens
    property string activityId: ""
    // false while the (kept-alive) activity page is hidden: no delegate work on every capture pass
    property bool active: true
    spacing: 0

    // Rows arrive worst first (builder 2): ambiguous, unidentified, offline, unsaved, window, identified.
    function groupOf(st) {
        return st === "identified" ? "identified" : st === "offline" ? "offline"
             : st === "window" || st === "unsaved" ? "window" : "needs"
    }
    function heading(g) {
        if (g === "needs") return "Needs a path · " + app.capture.needsPathCount
        if (g === "offline") return "Server offline · reopens when the server answers"
        if (g === "window") return "Not a file · nothing to reopen"
        return "Identified · " + app.capture.identifiedCount + (app.capture.newToSave > 0 ? " · " + app.capture.newToSave + " new" : "")
    }

    Txt {                                   // the one capture-state line, when it is not simply watching
        visible: app.capture.liveStale
        width: live.width
        bottomPadding: 6
        text: app.capture.captureLine + (rep.count > 0 ? " · what was open then" : "")
        tone: "muted"
        strong: true
        figures: true
    }
    Repeater {
        id: rep
        model: live.active ? app.capture.live : null
        delegate: Column {
            id: entry
            width: live.width
            opacity: app.capture.liveStale ? 0.55 : 1
            readonly property string group: live.groupOf(model.status)
            readonly property bool firstOfGroup: index === 0 || live.groupOf(app.capture.live.get(index - 1).status) !== group
            readonly property bool needs: group === "needs"
            readonly property string st: model.status
            readonly property var cands: model.candidates || []
            readonly property bool seenOnly: needs || st === "unsaved" || st === "window"   // no path: show the title
            readonly property var health: st === "offline" ? ["bad", "Server offline"]
                                        : st === "identified" && app.activities.healthRev >= 0
                                          ? app.activities.pathHealth(model.path) : ["", ""]

            Txt {
                visible: entry.firstOfGroup
                width: parent.width
                topPadding: index === 0 ? 4 : 14
                bottomPadding: 6
                text: live.heading(entry.group)
                role: "small"
                tone: "faint"
                figures: true
            }
            Item {
                width: parent.width
                height: entry.needs ? (model.status === "ambiguous" ? 74 + 18 * Math.min(2, model.candidates.length) : 64) : 50
                // Desk's dashed tile for a window with no path
                Canvas {
                    id: dash
                    visible: entry.needs
                    anchors.fill: parent
                    anchors.topMargin: 3
                    anchors.bottomMargin: 3
                    property color line: live.tk.border_strong
                    onLineChanged: requestPaint()
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onPaint: {
                        var c = getContext("2d")
                        c.reset()
                        c.strokeStyle = line
                        c.lineWidth = 1
                        c.setLineDash([4, 3])
                        var r = 10, w = width - 1, h = height - 1
                        c.beginPath()
                        c.moveTo(r + 0.5, 0.5); c.lineTo(w - r, 0.5); c.arcTo(w, 0.5, w, r, r)
                        c.lineTo(w, h - r); c.arcTo(w, h, w - r, h, r)
                        c.lineTo(r + 0.5, h); c.arcTo(0.5, h, 0.5, h - r, r)
                        c.lineTo(0.5, r); c.arcTo(0.5, 0.5, r, 0.5, r)
                        c.stroke()
                    }
                }
                Rectangle {
                    visible: !entry.needs && !entry.firstOfGroup
                    width: parent.width; height: 1; color: live.tk.border
                }
                Icon {
                    id: glyph
                    x: entry.needs ? 12 : 2
                    y: entry.needs ? 14 : (parent.height - height) / 2
                    name: model.kind === "folder" ? "folder" : model.kind === "url" ? "link"
                        : model.status === "identified" ? "file" : "app-window"
                }
                Column {
                    anchors.left: glyph.right
                    anchors.leftMargin: 10
                    anchors.right: actions.left
                    anchors.rightMargin: 12
                    y: entry.needs ? 10 : (parent.height - height) / 2
                    spacing: 1
                    Txt {
                        width: parent.width
                        text: entry.seenOnly ? "A window titled ‘" + model.title + "’" : model.name
                        strong: true
                    }
                    Txt {
                        width: parent.width
                        text: entry.seenOnly
                              ? [model.appName, model.note].filter(function (s) { return s && s !== "" }).join(" · ")
                              : [model.path, model.monitor, model.note].filter(function (s) { return s && s !== "" }).join(" · ")
                        role: "small"
                        tone: "faint"
                        elide: Text.ElideMiddle
                    }
                    Repeater {
                        model: entry.needs && entry.st === "ambiguous" ? entry.cands.slice(0, 2) : []
                        delegate: Txt {
                            required property var modelData
                            width: parent.width
                            text: "could be " + modelData
                            role: "small"
                            tone: "muted"
                            elide: Text.ElideMiddle
                        }
                    }
                }
                Row {
                    id: actions
                    anchors.right: parent.right
                    anchors.rightMargin: entry.needs ? 10 : 0
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    StatusPill {
                        // "New" only on what "Save N new as items" saves, so the page has one count (U2-3)
                        visible: !entry.needs && model.toSave === true
                        anchors.verticalCenter: parent.verticalCenter
                        status: "info"
                        label: visible ? "New" : ""
                    }
                    StatusPill {
                        visible: !entry.needs && entry.health[1] !== ""
                        anchors.verticalCenter: parent.verticalCenter
                        status: entry.health[0]
                        label: entry.health[1]
                    }
                    ActionButton {
                        visible: entry.needs || entry.st === "window"
                        text: "Ignore"
                        kind: "ghost"
                        small: true
                        tooltip: "Leave this window out of this activity's list"
                        onClicked: Window.window.safe(function () { app.capture.ignoreForActivity(model.entryKey) })
                    }
                    ActionButton {
                        visible: entry.needs || model.status === "unsaved"
                        text: "Attach a path"
                        small: true
                        onClicked: Window.window.openSheet("AttachPathSheet", {
                            entryKey: model.entryKey, windowTitle: model.title, appName: model.appName,
                            candidates: model.candidates, unsaved: model.status === "unsaved" })
                    }
                }
            }
        }
    }
    EmptyBlock {
        visible: rep.count === 0
        width: live.width
        line: app.capture.captureState === "watching" ? "Watching. Nothing is open yet." : app.capture.captureLine
    }
}
