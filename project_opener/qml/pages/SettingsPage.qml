import QtQuick
import QtQuick.Controls.Basic as C
import "../components"

// Settings: every 3.2 setting plus Motion, Snapshot (capture), the pill and keys (its rest style and place,
// the four keys with their conflict status, the Explorer entries), Cliq (the office bot's token kept with
// DPAPI, my link), and the watchers.  One area at a time: real tabs, each showing one section only (app-screens
// §8.2), the last tab remembered (app.settings.settingsTab); a route payload {section} opens that tab.  Labels
// above controls; a switch row says what it does.  Values are read through app.settings.value(key) and
// written with setValue (side effects routed in Python).
Page {
    id: page
    minimumWidth: 860
    property int rev: 0
    readonly property bool wideNav: contentW >= 1000
    Connections { target: app.settings; function onChanged(key) { page.rev++ } }
    function v(key) { return page.rev >= 0 ? app.settings.value(key) : null }
    function set(key, value) { app.settings.setValue(key, value) }
    // app.desktop.hotkeyStatus[name] = {keys, ok, error}; error is Windows' own text or the desktop's
    // ("Already used here for snapshot", "No shortcut set", "Turned off", a parse error).
    function keyLevel(st) {
        if (st === null) return "neutral"
        if (st.ok) return "ok"
        var e = String(st.error || "")
        return e === "Turned off" || e === "No shortcut set" ? "neutral" : "bad"
    }
    function keyWord(st) {
        if (st === null) return "Not registered yet"
        if (st.ok) return "Registered"
        var e = String(st.error || "")
        if (e === "Turned off") return "Off"
        if (e === "No shortcut set") return "Not set"
        if (e.toLowerCase().indexOf("already registered") >= 0) return "Taken by another app"
        if (e.indexOf("Already used here") === 0) return "Used twice"
        return "Not a valid key"
    }

    readonly property var sections: [
        { key: "profile", text: "Profile" }, { key: "appearance", text: "Appearance" },
        { key: "launching", text: "Opening" }, { key: "paths", text: "Paths" },
        { key: "hub", text: "Team Hub" }, { key: "snapshot", text: "Snapshot" },
        { key: "pill", text: "Pill and keys" }, { key: "cliq", text: "Cliq and mail" },
        { key: "watchers", text: "Watchers" }, { key: "updates", text: "Updates" }
    ]
    function tabFor(key) {
        for (var i = 0; i < sections.length; i++) if (sections[i].key === key) return key
        return "profile"
    }
    // the tab the page opens on: a route's {section}, else the last one used
    property string tab: app.ui.routePayload.section ? tabFor(app.ui.routePayload.section) : app.settings.settingsTab
    function pick(key) {
        page.tab = page.tabFor(key)
        app.settings.setSettingsTab(page.tab)
        page.contentY = 0
    }
    Component.onCompleted: if (app.ui.routePayload.section) app.settings.setSettingsTab(page.tab)

    PageHeader {
        title: "Settings"
    }

    Tabs {
        width: page.contentW
        tabs: page.sections
        current: page.tab
        onPicked: (key) => page.pick(key)
    }

    // ------------------------------------------------------------ profile
    SettingsSection {
        id: secProfile
        visible: page.tab === "profile"
        width: page.contentW
        line: "How colleagues see you on the Team Hub and in mentions."
        Row {
            spacing: 16
            Field {
                width: 260
                label: "Display name"
                text: page.v("display_name") || ""
                placeholder: app.login
                input.onEditingFinished: page.set("display_name", text)
            }
            Field {
                width: 220
                label: "Role"
                text: page.v("role") || ""
                placeholder: "Checker"
                input.onEditingFinished: page.set("role", text)
            }
            Field {
                width: 280
                label: "E-mail"
                help: "The Cliq bot finds you by it."
                text: page.v("email") || ""
                placeholder: "name@dexterity.in"
                input.onEditingFinished: page.set("email", text)
            }
        }
    }

    // ------------------------------------------------------------ appearance
    SettingsSection {
        id: secAppearance
        visible: page.tab === "appearance"
        width: page.contentW
        Row {
            spacing: 24
            Column {
                spacing: 6
                Txt { text: "Theme"; strong: true }
                Segmented {
                    label: "Theme"
                    options: [{ value: "dark", text: "Dark" }, { value: "light", text: "Light" }, { value: "system", text: "As Windows" }]
                    value: app.ui.themeMode
                    onPicked: (val) => app.ui.setTheme(val)
                }
            }
            Column {
                spacing: 6
                Txt { text: "Density"; strong: true }
                Segmented {
                    label: "Density"
                    options: [{ value: "comfortable", text: "Comfortable" }, { value: "compact", text: "Compact" }]
                    value: page.v("density") || "comfortable"
                    onPicked: (val) => page.set("density", val)
                }
            }
        }
        Column {
            spacing: 6
            Txt { text: "Accent"; strong: true }
            Row {
                spacing: 8
                Repeater {
                    model: ["#0E7C5B", "#0F766E", "#1D5FB8", "#4F46A3", "#A3285B", "#B4452E", "#8A5A00", "#3B6A1F", "#5C5F66", "#1A201D"]
                    delegate: Rectangle {
                        required property var modelData
                        readonly property bool on: String(page.v("accent")).toUpperCase() === modelData
                        width: 28; height: 28; radius: 14
                        color: modelData
                        border.width: on ? 3 : 1
                        border.color: on ? page.tk.text : page.tk.border_strong
                        Accessible.role: Accessible.RadioButton
                        Accessible.name: "Accent " + modelData
                        Accessible.checked: on
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.set("accent", parent.modelData) }
                    }
                }
            }
            Txt { text: "The accent marks the one main action, focus and selection; colour on data stays the projects' own."; role: "small"; tone: "faint" }
        }
        Column {
            spacing: 6
            Txt { text: "Motion"; strong: true }
            Segmented {
                label: "Motion"
                options: [{ value: "auto", text: "Automatic" }, { value: "rich", text: "Rich" }, { value: "purposeful", text: "Purposeful" }, { value: "off", text: "Off" }]
                value: app.ui.motionSetting
                onPicked: (val) => app.ui.setMotion(val)
            }
            Txt { text: app.ui.motionReason; tone: "muted" }
            Txt {
                width: Math.min(640, secAppearance.width - 2 * secAppearance.pad)
                text: "Rich moves the stage and lets the office breathe; purposeful keeps every transition shorter and nothing loops; off shows every screen complete and still."
                role: "small"
                tone: "faint"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
            }
        }
    }

    // ------------------------------------------------------------ launching
    SettingsSection {
        id: secLaunching
        visible: page.tab === "launching"
        width: page.contentW
        Row {
            spacing: 16
            ChoiceField {
                width: 220
                label: "Pause between items"
                options: [{ value: 0, text: "None" }, { value: 150, text: "0.15 s" }, { value: 350, text: "0.35 s" }, { value: 600, text: "0.6 s" }, { value: 1000, text: "1 s" }]
                value: String(page.v("launch_delay_ms"))
                onPicked: (val) => page.set("launch_delay_ms", parseInt(val))
            }
            ChoiceField {
                width: 260
                label: "Ask before opening more than"
                options: [{ value: 4, text: "4 items" }, { value: 8, text: "8 items" }, { value: 12, text: "12 items" }, { value: 20, text: "20 items" }, { value: 0, text: "Never ask" }]
                value: String(page.v("confirm_launch_over"))
                onPicked: (val) => page.set("confirm_launch_over", parseInt(val))
            }
        }
        SwitchRow { label: "Show notifications"; help: "Toasts for results the page does not show itself."; checked: page.v("show_toasts") === true; onToggled: (on) => page.set("show_toasts", on) }
        SwitchRow { label: "Start with Windows"; help: "Starts minimised to the tray when you sign in."; checked: page.v("run_at_startup") === true; onToggled: (on) => page.set("run_at_startup", on) }
        SwitchRow { label: "Start minimised"; checked: page.v("start_minimised") === true; onToggled: (on) => page.set("start_minimised", on) }
        SwitchRow { label: "Closing the window keeps it in the tray"; checked: page.v("minimise_to_tray") === true; onToggled: (on) => page.set("minimise_to_tray", on) }
        SwitchRow { label: "Open projects marked to open at start"; checked: page.v("auto_launch_on_start") === true; onToggled: (on) => page.set("auto_launch_on_start", on) }
    }

    // ------------------------------------------------------------ paths and variables
    SettingsSection {
        id: secPaths
        visible: page.tab === "paths"
        width: page.contentW
        line: "A variable stands for a folder that differs between PCs: {SERVER_ROOT} → \\\\nas01\\Project.  Items keep the variable; each PC fills it in."
        Column {
            width: parent.width
            Repeater {
                id: varRep
                model: page.rev >= 0 ? Object.keys(app.settings.variables()) : []
                delegate: Item {
                    required property var modelData
                    required property int index
                    width: parent ? parent.width : 600
                    height: 44
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Txt { y: 12; width: 200; text: modelData; strong: true; figures: true }
                    Txt { x: 210; y: 12; width: parent.width - 210 - 60; text: app.settings.variables()[modelData]; tone: "muted"; elide: Text.ElideMiddle }
                    ActionButton {
                        anchors.right: parent.right
                        y: 6
                        icon: "trash"; kind: "ghost"; small: true; tooltip: "Remove " + modelData
                        onClicked: app.settings.setVariable(modelData, "")
                    }
                }
            }
            Txt { visible: varRep.count === 0; text: "No variables yet."; tone: "muted" }
        }
        Row {
            spacing: 12
            Field { id: varName; width: 200; label: "Variable"; placeholder: "{SERVER_ROOT}" }
            Field { id: varValue; width: 340; label: "On this PC"; placeholder: "\\\\nas01\\Project"; onAccepted: addVar.clicked() }
            ActionButton {
                id: addVar
                y: 25
                text: "Add variable"
                available: varName.text.trim() !== "" && varValue.text.trim() !== ""
                onClicked: { app.settings.setVariable(varName.text, varValue.text); varName.text = ""; varValue.text = "" }
            }
        }
    }

    // ------------------------------------------------------------ hub
    SettingsSection {
        id: secHub
        visible: page.tab === "hub"
        width: page.contentW
        line: app.hub.configured ? app.hub.statusText : "Not connected. Every PC in the office points at the same shared folder."
        Row {
            spacing: 12
            Field {
                id: hubField
                width: Math.min(520, secHub.width - 200)
                label: "Hub folder"
                text: page.v("hub_path") || ""
                placeholder: "\\\\nas01\\Project\\_ProjectOpenerHub"
                input.onEditingFinished: page.set("hub_path", text)
            }
            ActionButton {
                y: 25
                text: "Browse"
                icon: "folder-open"
                onClicked: { var p = app.settings.browseFolder("Team Hub folder", hubField.text); if (p !== "") page.set("hub_path", p) }
            }
        }
        SwitchRow { label: "Share what I open"; help: "Colleagues see the activity or project you are in, and the register records openings."; checked: page.v("hub_share_pulse") === true; onToggled: (on) => page.set("hub_share_pulse", on) }
        SwitchRow { label: "Find colleagues on this network"; help: "A small broadcast so the office shows who is in before the hub folder is read."; checked: page.v("presence_udp") === true; onToggled: (on) => page.set("presence_udp", on) }
    }

    // ------------------------------------------------------------ snapshot: capture and its surfaces
    SettingsSection {
        id: secSnapshot
        visible: page.tab === "snapshot"
        width: page.contentW
        line: "10 checkpoints kept per activity, in this PC's data folder."      // a fact, not a description (T2-4)
        SwitchRow { label: "Capture while an activity runs"; help: "The switch on each activity's page turns it off for that activity only."; checked: page.v("capture_enabled") === true; onToggled: (on) => page.set("capture_enabled", on) }
        Row {
            spacing: 16
            ChoiceField {
                width: 220
                label: "Look every"
                options: [{ value: 3, text: "3 s" }, { value: 5, text: "5 s" }, { value: 10, text: "10 s" }]
                value: String(page.v("capture_interval_s"))
                onPicked: (val) => page.set("capture_interval_s", parseInt(val))
            }
        }
        SwitchRow { label: "Read browser addresses"; help: "The active tab of Edge and Chrome windows."; checked: page.v("capture_browser_urls") === true; onToggled: (on) => page.set("capture_browser_urls", on) }
        SwitchRow { label: "Open Office files through Office"; help: "Files on the share open without stalling in Protected View."; checked: page.v("open_office_via_com") === true; onToggled: (on) => page.set("open_office_via_com", on) }
        Column {
            width: parent.width
            spacing: 6
            Txt { text: "Never captured"; strong: true }
            Flow {
                width: parent.width
                spacing: 6
                Repeater {
                    model: page.rev >= 0 ? (page.v("capture_ignore") || []) : []
                    delegate: Chip {
                        required property var modelData
                        text: modelData.process + (modelData.title ? " · " + modelData.title : "")
                        removable: true
                        onRemoved: app.settings.removeIgnoreRule(modelData.process)
                    }
                }
            }
            Txt { text: "Ignore on a window in Open now adds it here."; role: "small"; tone: "faint" }
        }
    }

    // ------------------------------------------------------------ the pill, the keys, the Explorer entries
    SettingsSection {
        id: secPill
        visible: page.tab === "pill"
        width: page.contentW
        Txt { text: "The pill"; role: "heading" }
        SwitchRow { label: "Show the pill while an activity runs"; help: "A small capsule on a screen edge: the activity, how many things are open, what needs you."; checked: page.v("pill_enabled") === true; onToggled: (on) => page.set("pill_enabled", on) }
        Row {
            spacing: 24
            Column {
                spacing: 6
                Txt { text: "At rest"; strong: true }
                Segmented {
                    label: "Rest style"
                    options: [{ value: "pill", text: "Pill" }, { value: "edge", text: "Edge tab" }]
                    value: page.v("pill_rest_style") || "pill"
                    onPicked: (val) => page.set("pill_rest_style", val)
                }
            }
            Column {
                spacing: 6
                Txt { text: "Place"; strong: true }
                Row {
                    spacing: 8
                    Txt {
                        anchors.verticalCenter: parent.verticalCenter
                        text: Object.keys(page.v("pill_positions") || {}).length > 0 ? "Where you left it, per monitor layout" : "Bottom right, above the notification area"
                        tone: "muted"
                    }
                    ActionButton { text: "Put it back"; small: true; visible: Object.keys(page.v("pill_positions") || {}).length > 0; onClicked: app.settings.resetPillPosition() }
                }
            }
        }
        SwitchRow { label: "Keep the pill when no activity runs"; help: "It then offers Start from what's open."; checked: page.v("pill_pinned") === true; onToggled: (on) => page.set("pill_pinned", on) }
        SwitchRow { label: "Hide during full screen, presentations and Do not disturb"; checked: page.v("hide_when_fullscreen") === true; onToggled: (on) => page.set("hide_when_fullscreen", on) }

        Rectangle { width: parent.width; height: 1; color: page.tk.border }
        Txt { text: "Keys from anywhere"; role: "heading" }
        SwitchRow { label: "Use the keys"; checked: page.v("hotkeys_enabled") === true; onToggled: (on) => page.set("hotkeys_enabled", on) }
        Column {
            width: parent.width
            Repeater {
                model: [
                    { key: "snapshot", text: "Snapshot now" },
                    { key: "add_window", text: "Add the window in front (twice: pick a window)" },
                    { key: "panel", text: "Show or hide the pill's panel" },
                    { key: "palette", text: "Command palette over any window" }
                ]
                delegate: Item {
                    required property var modelData
                    required property int index
                    readonly property var status: app.desktop && app.desktop.hotkeyStatus ? (app.desktop.hotkeyStatus[modelData.key] || null) : null
                    width: parent ? parent.width : 600
                    height: 50
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Txt { y: 15; width: parent.width - 420; text: modelData.text }
                    Field {
                        x: parent.width - 400
                        y: 8
                        width: 180
                        text: parent.status && parent.status.keys ? parent.status.keys : ((page.v("hotkeys") || {})[modelData.key] || "")
                        input.onEditingFinished: app.settings.setHotkey(parent.modelData.key, text)
                    }
                    Item {
                        x: parent.width - 210
                        y: 15
                        width: 210
                        height: 20
                        StatusPill {
                            anchors.right: parent.right
                            status: page.keyLevel(parent.parent.status)
                            label: page.keyWord(parent.parent.status)
                        }
                    }
                    Tip { visible: hm.containsMouse && parent.status !== null && !parent.status.ok && (parent.status.error || "") !== ""; text: parent.status ? (parent.status.error || "") : "" }
                    MouseArea { id: hm; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                }
            }
        }

        Rectangle { width: parent.width; height: 1; color: page.tk.border }
        // the switch shows what is installed (the desktop's state), so its words and its position agree
        SwitchRow {
            readonly property bool installed: app.desktop ? app.desktop.explorerVerbInstalled : page.v("explorer_verb") === true
            label: "Explorer entries"
            help: "“Add to running activity” on any file or folder, and Send to › Project Opener. "
                  + (app.desktop ? (installed ? "Installed for you." : "Not installed.") : "")
            checked: installed
            onToggled: (on) => page.set("explorer_verb", on)
        }
    }

    // ------------------------------------------------------------ Cliq and mail
    SettingsSection {
        id: secCliq
        visible: page.tab === "cliq"
        width: page.contentW
        line: "The office bot sends you mentions, tasks and watcher hits as Cliq messages with a link back here."
        property string testText: ""
        property bool testOk: false
        Connections { target: app.settings; function onCliqTested(ok, message) { secCliq.testOk = ok; secCliq.testText = message } }
        Row {
            spacing: 16
            Field { width: 220; label: "Bot"; placeholder: "projectopener"; text: page.v("cliq_bot") || ""; input.onEditingFinished: page.set("cliq_bot", text) }
            Field { width: 320; label: "Cliq address"; text: page.v("cliq_api_base") || ""; input.onEditingFinished: page.set("cliq_api_base", text) }
        }
        Row {
            spacing: 12
            Field {
                id: tokenField
                width: 320
                label: "Bot token"
                help: app.settings.hasCliqToken ? "A token is stored for this Windows account (DPAPI). Enter a new one to replace it." : "Stored for this Windows account only (DPAPI); never shown again."
                echoMode: TextInput.Password
                placeholder: app.settings.hasCliqToken ? "••••••••" : "Paste the office bot's token"
            }
            ActionButton {
                y: 25
                text: "Save token"
                available: tokenField.text !== ""
                onClicked: { app.settings.setCliqToken(tokenField.text); tokenField.text = "" }
            }
            ActionButton {
                y: 25
                visible: app.settings.hasCliqToken
                text: "Remove"
                kind: "ghost"
                onClicked: app.settings.setCliqToken("")
            }
        }
        Item {
            width: parent.width
            height: 34
            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12
                StatusPill {
                    anchors.verticalCenter: parent.verticalCenter
                    status: (page.v("cliq_user_id") || "") !== "" ? "ok" : "neutral"
                    label: (page.v("cliq_user_id") || "") !== "" ? "Linked" : "Not linked"
                }
                ActionButton { text: "Link and send me a test"; small: true; onClicked: { secCliq.testText = "Asking Cliq…"; app.settings.testCliq() } }
                ActionButton { visible: (page.v("cliq_user_id") || "") !== ""; text: "Unlink"; kind: "ghost"; small: true; onClicked: app.settings.unlinkCliq() }
                Txt { anchors.verticalCenter: parent.verticalCenter; text: secCliq.testText; tone: secCliq.testText === "" ? "muted" : secCliq.testOk ? "ok" : "bad" }
            }
        }
        SwitchRow { label: "Message me on Cliq by default"; help: "Mentions, tasks given to you and watcher hits. Each watcher can say otherwise."; checked: page.v("notify_cliq_default") === true; onToggled: (on) => page.set("notify_cliq_default", on) }
        Column {
            spacing: 6
            Txt { text: "Mail"; strong: true }
            Segmented {
                label: "Mail"
                options: [{ value: "outlook", text: "Outlook" }, { value: "mailto", text: "Default mail app" }]
                value: page.v("mail_client") || "outlook"
                onPicked: (val) => page.set("mail_client", val)
            }
        }
    }

    // ------------------------------------------------------------ watchers
    SettingsSection {
        id: secWatchers
        visible: page.tab === "watchers"
        width: page.contentW
        line: "Rules that tell you when a file lands, a server goes down, a colleague finishes, or a date comes."
        Column {
            width: parent.width
            Repeater {
                id: wRep
                model: app.watchers.watchers
                delegate: Item {
                    width: parent ? parent.width : 600
                    height: 56
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Icon { id: wi; y: 18; name: model.kind === "health" ? "bell" : model.kind === "time" ? "clock" : model.kind === "hub" ? "users-three" : "eye" }
                    Column {
                        anchors.left: wi.right
                        anchors.leftMargin: 12
                        anchors.right: wAct.left
                        anchors.rightMargin: 16
                        y: 9
                        Txt { width: parent.width; text: model.name + (model.lastHitText !== "" ? " · " + model.lastHitText : ""); strong: true; figures: true }
                        Txt { width: parent.width; text: model.target + " · " + model.notifyText; role: "small"; tone: "faint"; elide: Text.ElideMiddle }
                    }
                    Row {
                        id: wAct
                        anchors.right: parent.right
                        y: 11
                        spacing: 6
                        Toggle { checked: model.watcherEnabled; onToggled: (on) => Window.window.safe(function () { app.watchers.setEnabled(model.watcherId, on) }) }
                        ActionButton { icon: "pencil-simple"; kind: "ghost"; small: true; tooltip: "Edit"; onClicked: Window.window.openSheet("WatcherSheet", { watcherId: model.watcherId }) }
                        ActionButton {
                            icon: "trash"; kind: "ghost"; small: true; tooltip: "Delete"
                            onClicked: Window.window.confirm("Delete the watcher " + model.name + "?", "It stops telling anyone; past alerts stay.", "Delete watcher", true,
                                                             function () { Window.window.safe(function () { app.watchers.remove(model.watcherId) }) })
                        }
                    }
                }
            }
            Txt { visible: wRep.count === 0; text: "No watchers yet."; tone: "muted" }
        }
        ActionButton { text: "New watcher"; icon: "plus"; onClicked: Window.window.openSheet("WatcherSheet", {}) }
    }

    // ------------------------------------------------------------ updates
    SettingsSection {
        id: secUpdates
        visible: page.tab === "updates"
        width: page.contentW
        Column {
            spacing: 6
            Txt { text: "Offer"; strong: true }
            Segmented {
                label: "Update channel"
                options: [{ value: "stable", text: "Stable releases" }, { value: "all", text: "Every release" }]
                value: page.v("update_channel") || "stable"
                onPicked: (val) => page.set("update_channel", val)
            }
        }
        SwitchRow { label: "Check for updates by itself"; help: "GitHub and the Team Hub's mirror, every few hours."; checked: page.v("update_check") === true; onToggled: (on) => page.set("update_check", on) }
    }
}
