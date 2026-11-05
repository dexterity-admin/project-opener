import QtQuick
import QtQuick.Window
import "components"

// The Stage shell (brief section 4; concept-1-stage).  Owner: builder 4 (SHELL).
// Context property `app` is the AppFacade (project_opener/quick/facade.py); every fact comes from it.
// The shell is a 68 px rail and one page routed by app.ui.route; sheets, the command palette and toasts
// float above it.  Pages and sheets reach the shell through `Window.window` (openSheet, openPalette, toast).
Window {
    id: root
    readonly property var tk: app.ui.tokens
    width: 1400
    height: 860
    minimumWidth: app.ui.minimumWidth
    minimumHeight: app.ui.minimumHeight
    visible: false            // app_v4 shows it (or leaves it hidden with --minimised)
    color: tk.bg
    title: "Project Opener"

    // Ambient loops (the office breathing) only in rich motion and only while the window is active.
    readonly property bool ambientOn: app.ui.ambient && root.active
    readonly property int pageMinimumWidth: pageLoader.item && pageLoader.item.minimumWidth !== undefined
                                            ? pageLoader.item.minimumWidth : 0
    readonly property var pageItem: pageLoader.item
    property string lastSheet: ""

    readonly property var pages: ({
        "home": "pages/HomePage.qml",
        "activity": "pages/ActivityPage.qml",
        "activities": "pages/ActivitiesPage.qml",
        "projects": "pages/ProjectsPage.qml",
        "project": "pages/ProjectPage.qml",
        "hub": "pages/HubPage.qml",
        "updates": "pages/UpdatesPage.qml",
        "settings": "pages/SettingsPage.qml"
    })

    // ---------------------------------------------------------------- shell API (for pages and sheets)
    function openSheet(name, props) {
        sheetLoader.setSource("sheets/" + name + ".qml", props || {})
        lastSheet = name
    }
    function closeSheet() {
        sheetLoader.source = ""
        lastSheet = ""
    }
    function confirm(title, body, confirmText, destructive, onOk) {
        root._confirmOk = onOk
        openSheet("ConfirmSheet", { title: title, body: body, confirm: confirmText, destructive: destructive === true })
    }
    property var _confirmOk: null
    function confirmed() {
        var fn = root._confirmOk
        root._confirmOk = null
        if (fn) fn()
    }
    function openPalette(query) { cmdPalette.show(query || "") }
    function closePalette() { cmdPalette.hide() }
    function clearToasts() { toasts.clear() }
    function toast(title, body, level) { toasts.push(title, body, level || "info", "", "", ({})) }
    function go(route, payload) { app.ui.go(route, payload || ({})) }
    function runAction(action, target) {
        switch (action) {
        case "openActivityPage": go("activity", { activityId: target }); break
        case "openProjectPage": go("project", { projectId: target }); break
        case "openItem": { var p = String(target).split("|"); app.activities.openProjectItem(p[0], p[1]); break }
        case "newActivity": openSheet("ActivityEditor", { activityId: "" }); break
        case "newProject": openSheet("ProjectEditor", { projectId: "" }); break
        case "newTask": openSheet("TaskSheet", {}); break
        case "startFromOpen": startFromOpen(); break
        case "snapshotNow": safe(function () { app.capture.snapshotNow() }); break
        case "addWindow": safe(function () { app.capture.addForegroundWindow() }); break
        case "goHome": go("home"); break
        case "goActivities": go("activities"); break
        case "goProjects": go("projects"); break
        case "goHub": go("hub"); break
        case "goUpdates": go("updates"); break
        case "goSettings": go("settings"); break
        case "toggleTheme": app.ui.setTheme(app.ui.dark ? "light" : "dark"); break
        }
    }
    // A call into a sub-API that fails (a share gone, a bad value) is said once, never left to the console.
    function safe(fn, message) {
        try { fn(); return true }
        catch (e) { toast("Could not do that", message || String(e), "warning"); return false }
    }
    function startFromOpen() {
        safe(function () { app.capture.prepareStartFromOpen() })
        openSheet("StartFromOpenSheet", {})
    }

    // ---------------------------------------------------------------- layout
    Rail {
        id: rail
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        current: app.ui.route
        onNavigate: (route) => app.ui.go(route, ({}))
        onSearch: cmdPalette.show("")
    }

    Item {
        id: stageArea
        anchors.left: rail.right
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        clip: true

        Loader {
            id: pageLoader
            width: parent.width
            height: parent.height
            // (re)loaded on every route change by the Connections below, so a page reads its payload once,
            // at creation, and never reacts to a route change while it is being torn down
            focus: true
            onLoaded: {
                if (app.ui.k > 0) enter.restart()
                var tint = item && item.tint !== undefined ? item.tint : ""
                if (tint !== "" && app.ui.k > 0) { sweep.color = tint; sweepIn.restart() }
            }
        }
        // Page transitions carry the job's colour: entering an activity or a project, a 3 px line in its own
        // colour draws across the top of the page and fades (identity colour, never chrome; not in off).
        Rectangle {
            id: sweep
            height: 3
            width: 0
            opacity: 0
            z: 5
        }
        SequentialAnimation {
            id: sweepIn
            PropertyAction { target: sweep; property: "opacity"; value: 1 }
            NumberAnimation { target: sweep; property: "width"; from: 0; to: stageArea.width; duration: Math.round(380 * app.ui.k); easing.type: Easing.OutCubic }
            NumberAnimation { target: sweep; property: "opacity"; to: 0; duration: Math.round(320 * app.ui.k); easing.type: Easing.OutCubic }
        }
        // Page change: the page settles in 8 px and fades in (purposeful scales it; off is a cut).
        ParallelAnimation {
            id: enter
            NumberAnimation { target: pageLoader; property: "opacity"; from: 0; to: 1; duration: Math.round(220 * app.ui.k); easing.type: Easing.OutCubic }
            NumberAnimation { target: pageLoader; property: "y"; from: 8; to: 0; duration: Math.round(260 * app.ui.k); easing.type: Easing.OutCubic }
        }
    }

    // ---------------------------------------------------------------- floating layers
    Loader {
        id: sheetLoader
        anchors.fill: parent
        z: 20
        focus: status === Loader.Ready
        onLoaded: item.forceActiveFocus()
    }
    Palette { id: cmdPalette; anchors.fill: parent; z: 30 }
    Toasts { id: toasts; anchors.fill: parent; z: 40 }

    Connections {
        target: app.activities
        function onConfirmNeeded(requestId, targetId, count) {
            root._confirmOk = function () { app.activities.answerConfirm(requestId, true) }
            root.openSheet("ConfirmSheet", {
                title: "Open " + count + " items at once?",
                body: "Windows opens them one after another; the dock shows each as it lands.",
                confirm: "Open " + count + " items", destructive: false,
                onCancel: function () { app.activities.answerConfirm(requestId, false) } })
        }
        function onCreated(kind, id) {
            if (kind === "activity") root.go("activity", { activityId: id })
            else root.go("project", { projectId: id })
        }
    }
    Connections {
        target: app
        function onPaletteRequested() { cmdPalette.show("") }
        function onChooserRequested(paths) { root.openSheet("AddChooserSheet", { paths: paths }) }
    }
    function loadPage() {
        pageLoader.source = ""
        pageLoader.source = root.pages[app.ui.route] || root.pages["home"]
    }
    Component.onCompleted: loadPage()
    Connections {
        target: app.ui
        function onRouteChanged() {
            root.loadPage()
            var p = app.ui.routePayload
            if (p.sheet === "start-from-open") root.startFromOpen()
        }
    }

    Shortcut { sequence: "Ctrl+K"; onActivated: cmdPalette.show("") }
    Shortcut { sequence: "Ctrl+N"; onActivated: root.openSheet("ActivityEditor", { activityId: "" }) }
    Shortcut { sequence: "Ctrl+,"; onActivated: app.ui.go("settings", ({})) }
    Shortcut { sequence: "Alt+Left"; onActivated: app.ui.back() }
}
