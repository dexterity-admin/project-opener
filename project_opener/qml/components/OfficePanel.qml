import QtQuick

// Footlight 3: the Office, drawn as Control room's desks (board A).  Each colleague is a 44 px desk tile in
// their own stable pale hue with their initials, name and the activity they are in; online first, at most
// four desks so the three footlights end level.  A colleague who comes online gets the office's one ring
// (rich 2.4 s, purposeful 0.6x, once; none in off): the office breathes once, it does not pulse.  The panel
// is as tall as its desks (no panel-void); its action, Team Hub, sits in the heading.  Data: app.hub.peers.
Card {
    id: panel
    property int maxRows: 4
    implicitHeight: list.y + list.implicitHeight + pad

    // online first, in the hub's order otherwise; rebuilt whenever the peers change
    property var desks: []
    property var lastOnline: ({})
    property bool filled: false
    property var arrivals: ({})
    function rebuild() {
        var m = app.hub.peers, on = [], off = [], now = ({}), arr = ({})
        for (var i = 0; i < m.count(); i++) {
            var p = m.get(i)
            if (p.online) {
                on.push(p)
                now[p.login] = true
                if (panel.filled && !panel.lastOnline[p.login]) arr[p.login] = true
            } else {
                off.push(p)
            }
        }
        panel.arrivals = arr
        panel.lastOnline = now
        if (m.count() > 0) panel.filled = true      // the first fill rings nobody
        panel.desks = on.concat(off)
    }
    Connections { target: app.hub; function onPeersChanged() { panel.rebuild() } }
    Component.onCompleted: rebuild()

    Item {
        id: head
        x: panel.pad; y: panel.pad - 4
        width: panel.width - 2 * panel.pad
        height: 34
        SectionHeading {
            anchors.verticalCenter: parent.verticalCenter
            title: "Office"
            facts: !app.hub.configured ? ""
                 : app.hub.peersOnline + " online" + (panel.desks.length > panel.maxRows
                                                      ? " · " + (panel.desks.length - panel.maxRows) + " more" : "")
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
        y: head.y + head.height + 8
        width: panel.width - 2 * panel.pad
        spacing: 6
        Repeater {
            id: rep
            model: panel.desks.slice(0, panel.maxRows)
            delegate: DeskTile {
                id: desk
                width: list.width
                login: modelData.login
                displayName: modelData.displayName
                initials: modelData.initials
                hue: Number(modelData.hue)
                online: modelData.online === true
                doing: modelData.doing || ""
                role: modelData.role || ""
                host: modelData.host || ""
                Component.onCompleted: if (panel.arrivals[modelData.login]) desk.breathe()
            }
        }
        EmptyBlock {
            visible: panel.desks.length === 0
            width: list.width
            line: app.hub.configured ? "Nobody else has signed in to the Team Hub yet."
                                     : "Pick a shared folder for the Team Hub to see who is in."
            action: app.hub.configured ? "" : "Set up the Team Hub"
            onTriggered: app.ui.go("settings", { section: "hub" })
        }
    }
}
