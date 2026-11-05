import QtQuick
import QtQuick.Window
import "components"

// The Stage shell (brief section 4; concept-1-stage).  Owner: builder 4 (SHELL).
// Context property `app` is the AppFacade (project_opener/quick/facade.py); every fact comes from it.
// Skeleton: the 68 px rail and an empty page area routed by app.ui.route.
Window {
    id: root
    readonly property var tk: app.ui.tokens
    width: 1280
    height: 800
    minimumWidth: app.ui.minimumWidth
    minimumHeight: app.ui.minimumHeight
    visible: false            // app_v4 shows it (or leaves it hidden with --minimised)
    color: tk.bg
    title: "Project Opener"

    readonly property var pages: ({
        "home": "pages/HomePage.qml",
        "activity": "pages/ActivityPage.qml",
        "projects": "pages/ProjectsPage.qml",
        "project": "pages/ProjectPage.qml",
        "hub": "pages/HubPage.qml",
        "updates": "pages/UpdatesPage.qml",
        "settings": "pages/SettingsPage.qml"
    })

    Rail {
        id: rail
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        current: app.ui.route
        onNavigate: (route) => app.ui.go(route, ({}))
    }

    Loader {
        id: page
        anchors.left: rail.right
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        source: root.pages[app.ui.route] || root.pages["home"]
    }
}
