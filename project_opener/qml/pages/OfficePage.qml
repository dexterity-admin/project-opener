import QtQuick
import "../components"

// Office pulse: who is on which project now, from the hub's heartbeats (app.hub.peers) and handovers.
// active (green) = signed in and in an activity or project; idle (amber) = signed in, nothing open;
// away (faint) = no heartbeat for three minutes; on leave = a handover is on ("on leave · handed to X").
// Colleagues only, active first; each desk in the person's own pale hue (DeskTile's rule).  The office
// breathes once when someone arrives (DeskTile.breathe, rich/purposeful only).
Page {
    id: page
    minimumWidth: 860
    readonly property var c: app.team.officeCounts
    readonly property int cols: page.contentW >= 1100 ? 3 : 2

    Component.onCompleted: app.team.refresh()

    function countLine() {
        var parts = []
        if (c.active) parts.push(c.active + " active")
        if (c.idle) parts.push(c.idle + " idle")
        if (c.leave) parts.push(c.leave + " on leave")
        if (c.away) parts.push(c.away + " away")
        return parts.join(" · ")
    }
    function dotColor(p) {
        return p === "active" ? page.tk.success : p === "idle" ? page.tk.action : p === "leave" ? page.tk.accent : page.tk.border_strong
    }

    PageHeader {
        title: "Office"
        subtitle: !app.hub.configured ? "" : app.team.officeCount === 0 ? "" : page.countLine()
        ActionButton {
            visible: app.hub.configured
            text: app.team.handover.id !== undefined ? "Your handover" : "Hand over my work"
            icon: "airplane-tilt"
            onClicked: app.ui.go("handover", ({}))
        }
    }

    Row {                                          // the legend: the four states in their dots
        visible: app.team.officeCount > 0
        spacing: 18
        Repeater {
            model: [{ k: "active", t: "active" }, { k: "idle", t: "idle" }, { k: "leave", t: "on leave" }, { k: "away", t: "away" }]
            delegate: Row {
                spacing: 6
                Rectangle { width: 8; height: 8; radius: 4; color: page.dotColor(modelData.k); anchors.verticalCenter: parent.verticalCenter }
                Txt { text: modelData.t; role: "small"; tone: "muted" }
            }
        }
    }

    Grid {
        id: grid
        width: page.contentW
        columns: page.cols
        columnSpacing: 12
        rowSpacing: 12
        readonly property real cell: (width - (columns - 1) * columnSpacing) / columns
        Repeater {
            id: rep
            model: app.team.office
            delegate: Card {
                id: desk
                width: grid.cell
                height: 92
                readonly property bool away: model.presence === "away"
                opacity: away ? 0.72 : 1
                Rectangle {                         // the person's pale hue band on the left (identity, not chrome)
                    x: 0; y: 0; width: 4; height: parent.height; radius: 2
                    color: Qt.hsla((Number(model.hue) % 360) / 360, 0.5, page.tk.dark ? 0.55 : 0.45, desk.away ? 0.35 : 1)
                }
                Avatar {
                    id: av
                    x: desk.pad; y: 16
                    size: 36
                    initials: model.initials
                    hue: Number(model.hue)
                    online: model.presence === "active" || model.presence === "idle"
                }
                Column {
                    anchors.left: av.right
                    anchors.leftMargin: 12
                    anchors.right: parent.right
                    anchors.rightMargin: desk.pad
                    y: 14
                    spacing: 3
                    Row {
                        width: parent.width
                        spacing: 8
                        Txt { id: nm; text: model.displayName; strong: true; width: Math.min(implicitWidth, parent.width - pres.width - 8) }
                        Row {
                            id: pres
                            spacing: 5
                            anchors.verticalCenter: nm.verticalCenter
                            Rectangle { width: 8; height: 8; radius: 4; color: page.dotColor(model.presence); anchors.verticalCenter: parent.verticalCenter }
                            Txt { text: model.presenceText; role: "small"; tone: model.presence === "away" ? "faint" : "muted" }
                        }
                    }
                    Txt {
                        width: parent.width
                        text: model.presence === "leave" ? model.leaveText
                            : model.doing !== "" ? model.doing
                            : model.presence === "idle" ? "nothing open"
                            : model.seenText
                        tone: model.presence === "active" ? "ink" : "muted"
                        visible: text !== ""
                    }
                    Txt {
                        width: parent.width
                        text: [model.role, model.presence === "leave" ? model.seenText : ""].filter(function (s) { return s && s !== "" }).join(" · ")
                        role: "small"
                        tone: "faint"
                        visible: text !== ""
                    }
                }
            }
        }
    }

    EmptyBlock {
        visible: rep.count === 0
        width: page.contentW
        line: app.hub.configured ? "Nobody else has signed in to the Team Hub yet."
                                 : "Pick a shared folder for the Team Hub to see who is in."
        action: app.hub.configured ? "" : "Set up the Team Hub"
        onTriggered: app.ui.go("settings", { tab: "hub", section: "hub" })
    }
}
