import QtQuick

// Footlight 3: the Office (Control room's office panel).  Who is in and what they are in, online first; a
// colleague who comes online gets one ring that grows and fades over 2.4 s: the office breathes once, it does
// not pulse (rich motion, window active).  Data: app.hub.peers (builder 1).
Card {
    id: panel
    property int maxRows: 4
    implicitHeight: 64 + Math.max(1, Math.min(rep.count, maxRows)) * 48 + 40

    Item {
        id: head
        x: panel.pad; y: panel.pad - 4
        width: panel.width - 2 * panel.pad
        height: 34
        SectionHeading {
            anchors.verticalCenter: parent.verticalCenter
            title: "Office"
            facts: app.hub.configured ? app.hub.peersOnline + " online" : ""
        }
        ActionButton {
            visible: app.hub.configured
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "Team Hub"
            icon: "arrow-right"
            kind: "ghost"
            small: true
            onClicked: app.ui.go("hub", ({}))
        }
    }
    Column {
        id: list
        x: panel.pad
        anchors.top: head.bottom
        anchors.topMargin: 6
        width: panel.width - 2 * panel.pad
        Repeater {
            id: rep
            model: app.hub.peers
            delegate: Item {
                id: person
                width: list.width
                visible: index < panel.maxRows
                height: visible ? 48 : 0
                Rectangle { width: parent.width; height: 1; color: panel.tk.border; visible: index > 0 }
                Avatar {
                    id: av
                    anchors.verticalCenter: parent.verticalCenter
                    initials: model.initials
                    hue: model.hue
                    online: model.online
                    size: 28
                }
                Column {
                    anchors.left: av.right
                    anchors.leftMargin: 12
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    Txt { width: parent.width; text: model.displayName; strong: true; tone: model.online ? "ink" : "muted" }
                    Txt {
                        width: parent.width
                        text: [model.doing, model.role].filter(function (s) { return s && s !== "" }).join(" · ")
                        role: "small"
                        tone: "faint"
                    }
                }
                Tip { visible: hov.containsMouse; text: model.login + (model.host ? " · " + model.host : "") }
                MouseArea { id: hov; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                // breathe once when this person arrives (a change of the row, never when the panel first fills)
                readonly property bool online: model.online === true
                onOnlineChanged: if (online) av.breathe()
            }
        }
        EmptyBlock {
            visible: rep.count === 0
            width: list.width
            line: app.hub.configured ? "Nobody else has signed in to the Team Hub yet."
                                     : "Pick a shared folder for the Team Hub to see who is in."
            action: app.hub.configured ? "" : "Set up the Team Hub"
            onTriggered: app.ui.go("settings", { section: "hub" })
        }
    }
}
