import QtQuick

// The 68 px rail (concept-1-stage, ".rail"): the mark, Search, one round slot per route with its tooltip,
// and the person at the foot.  Counts only on queues that need action: the hub's inbox and mentions, my
// open tasks.  The rail names nothing the page title already says.
Rectangle {
    id: rail
    readonly property var tk: app.ui.tokens
    property string current: "home"
    signal navigate(string route)
    signal search()

    width: app.ui.railWidth
    color: tk.bg

    readonly property int hubCount: (app.hub.inboxCount || 0)
    readonly property var routes: [
        { route: "home", glyph: "house", label: "Home", count: 0 },
        { route: "activities", glyph: "stack", label: "Activities", count: 0 },
        { route: "projects", glyph: "squares-four", label: "Projects", count: 0 },
        { route: "hub", glyph: "users-three", label: "Team Hub", count: rail.hubCount + (app.tasks.mineOpenCount || 0) },
        { route: "updates", glyph: "arrow-circle-down", label: "Updates", count: 0 },
        { route: "settings", glyph: "sliders-horizontal", label: "Settings", count: 0 }
    ]

    Column {
        anchors.top: parent.top
        anchors.topMargin: 20
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 8

        Image {                       // the mark: the app icon (accent squircle, folder, arrow)
            width: 32
            height: 32
            source: app.ui.appIcon
            sourceSize.width: 64
            sourceSize.height: 64
            anchors.horizontalCenter: parent.horizontalCenter
            smooth: true
            Accessible.name: "Project Opener"
        }
        Item { width: 1; height: 14 }

        RailButton {
            glyph: "magnifying-glass"
            label: "Search (Ctrl+K)"
            onClicked: rail.search()
        }
        Item { width: 1; height: 4 }

        Repeater {
            model: rail.routes
            delegate: RailButton {
                required property var modelData
                glyph: modelData.glyph
                label: modelData.label
                count: modelData.count
                active: rail.current === modelData.route
                        || (modelData.route === "activities" && rail.current === "activity")
                        || (modelData.route === "projects" && rail.current === "project")
                onClicked: rail.navigate(modelData.route)
            }
        }
    }

    Avatar {
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 20
        anchors.horizontalCenter: parent.horizontalCenter
        initials: app.displayName.length > 0 ? app.displayName.charAt(0).toUpperCase() : "?"
        hue: rail.tk.accent
        online: app.hub.configured && app.hub.reachable
        size: 28
        Tip { visible: avatarMouse.containsMouse; text: app.displayName + " · " + app.login }
        MouseArea { id: avatarMouse; anchors.fill: parent; hoverEnabled: true; onClicked: rail.navigate("settings") }
    }
}
