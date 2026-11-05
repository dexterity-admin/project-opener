import QtQuick
import QtQuick.Controls.Basic as C
import "../components"

// The activity editor.  Details: name, the pill's short name, the job (the first project: its spine in every
// title), description, icon, capture and resume switches.  Items: the launch order (Move up / Move down),
// each item's on switch, a CAD launch profile for application items, and items drawn from ANY project
// (cross-project) or added as files and folders.  Item changes apply at once; Details on Save.
Sheet {
    id: s
    property string activityId: ""
    property string projectId: ""
    property string tab: "details"
    property string itemId: ""
    readonly property bool creating: activityId === ""
    readonly property var act: app.activities.current
    property string query: ""

    title: creating ? "New activity" : "Edit activity"
    subtitle: creating ? "Open what it needs later, or save what is open while it runs." : (act.title || "")
    confirmText: creating ? "Create activity" : "Save"
    sheetWidth: 680
    confirmEnabled: nameField.text.trim() !== ""

    Component.onCompleted: {
        if (!creating) {
            app.activities.select(activityId)
            nameField.text = act.name || ""
            shortField.text = act.shortName || ""
            descField.text = act.description || ""
            capture.checked = act.captureOn !== false
            resume.checked = act.resumeOnStart !== false
            job.value = (act.projectIds && act.projectIds.length > 0) ? act.projectIds[0] : ""
            iconPick.value = act.icon || "stack"
        } else {
            job.value = s.projectId
            iconPick.value = "stack"
            capture.checked = true
            resume.checked = true
        }
        nameField.focusInput()
    }

    onAccepted: {
        var fields = { name: nameField.text, shortName: shortField.text, description: descField.text,
                       captureOn: capture.checked, resumeOnStart: resume.checked, icon: iconPick.value,
                       projectIds: job.value !== "" ? [job.value].concat((act.projectIds || []).filter(function (p) { return p !== job.value })) : [] }
        if (creating) {
            var id = app.activities.create(nameField.text, job.value)
            if (id === "") { s.fail("The activity could not be created."); return }
            app.activities.edit(id, fields)
        } else {
            app.activities.edit(activityId, fields)
        }
        s.close()
    }

    Tabs {
        visible: !s.creating
        current: s.tab
        tabs: [{ key: "details", text: "Details", count: 0 }, { key: "items", text: "Items", count: s.creating ? 0 : (act.itemCount || 0) }]
        onPicked: (k) => s.tab = k
    }

    // ------------------------------------------------------------ details
    Column {
        visible: s.tab === "details" || s.creating
        width: parent.width
        spacing: 16
        Row {
            spacing: 16
            Field { id: nameField; width: 360; label: "Name"; placeholder: "Lot 7 check"; onAccepted: s.accept() }
            Field { id: shortField; width: 236; label: "Short name"; help: "On the pill and the tray; up to 18 characters."; placeholder: nameField.text.slice(0, 18); input.maximumLength: 18 }
        }
        ChoiceField {
            id: job
            width: 360
            label: "Job"
            options: {
                var out = [{ value: "", text: "No project" }]
                var m = app.activities.projects
                for (var i = 0; i < m.count(); i++) out.push({ value: m.get(i).projectId, text: m.get(i).title })
                return out
            }
            onPicked: (v) => value = v
        }
        AreaField { id: descField; width: parent.width; label: "Description"; placeholder: "Back-check of lot 7 against the RLM mark-ups"; boxHeight: 64 }
        Column {
            spacing: 6
            Txt { text: "Icon"; strong: true }
            Flow {
                id: iconPick
                property string value: "stack"
                width: s.width
                spacing: 6
                Repeater {
                    model: ["stack", "checks", "compass", "ruler", "cube", "factory", "anchor", "buildings", "clipboard-text", "calendar", "magnifying-glass", "users-three", "wrench", "lightning", "flag", "star"]
                    delegate: Rectangle {
                        required property var modelData
                        width: 34; height: 34; radius: 10
                        color: iconPick.value === modelData ? s.tk.surface_3 : im.containsMouse ? s.tk.surface_2 : "transparent"
                        border.width: iconPick.value === modelData ? 1 : 0
                        border.color: s.tk.border_strong
                        Icon { anchors.centerIn: parent; name: parent.modelData; tone: iconPick.value === parent.modelData ? "ink" : "muted" }
                        MouseArea { id: im; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: iconPick.value = parent.modelData }
                        Accessible.role: Accessible.RadioButton
                        Accessible.name: modelData
                    }
                }
            }
        }
        SwitchRow { id: capture; label: "Capture while it runs"; help: "Keeps a snapshot of what is open so it comes back after a restart."; onToggled: (on) => checked = on }
        SwitchRow { id: resume; label: "Offer to resume after a restart"; help: "A band on Home; never automatic."; onToggled: (on) => checked = on }
    }

    // ------------------------------------------------------------ items
    Column {
        visible: s.tab === "items" && !s.creating
        width: parent.width
        spacing: 8
        Repeater {
            id: itemsRep
            model: app.activities.items
            delegate: Item {
                width: parent ? parent.width : 600
                height: model.kind === "app" ? 92 : 52
                Rectangle { width: parent.width; height: 1; color: s.tk.border; visible: index > 0 }
                Rectangle { anchors.fill: parent; radius: 8; color: model.itemId === s.itemId ? s.tk.accent_soft : "transparent"; opacity: 0.6 }
                Txt { id: num; y: 16; width: 22; text: model.order; role: "small"; tone: "faint"; figures: true }
                Icon { id: g; anchors.left: num.right; y: 16; name: model.glyph }
                Column {
                    anchors.left: g.right
                    anchors.leftMargin: 10
                    anchors.right: ctl.left
                    anchors.rightMargin: 10
                    y: 8
                    Txt { width: parent.width; text: model.name; strong: true }
                    Txt { width: parent.width; text: model.path + (model.projectTitle !== "" ? " · " + model.projectTitle : ""); role: "small"; tone: "faint"; elide: Text.ElideMiddle }
                }
                Row {
                    id: ctl
                    anchors.right: parent.right
                    y: 9
                    spacing: 2
                    Toggle { checked: model.itemEnabled; onToggled: (on) => app.activities.editItem(s.activityId, model.itemId, { itemEnabled: on }) }
                    ActionButton { icon: "arrow-up"; kind: "ghost"; small: true; tooltip: "Move up"; available: index > 0; onClicked: app.activities.moveItem(s.activityId, model.itemId, index - 1) }
                    ActionButton { icon: "arrow-down"; kind: "ghost"; small: true; tooltip: "Move down"; available: index < itemsRep.count - 1; onClicked: app.activities.moveItem(s.activityId, model.itemId, index + 1) }
                    ActionButton { icon: "x"; kind: "ghost"; small: true; tooltip: "Remove from this activity"; onClicked: app.activities.removeItem(s.activityId, model.itemId) }
                }
                ChoiceField {
                    visible: model.kind === "app"
                    x: 32
                    y: 48
                    width: 300
                    label: ""
                    options: {
                        var out = [{ value: "", text: "No launch profile" }]
                        var m = app.activities.profiles
                        for (var i = 0; i < m.count(); i++) out.push({ value: m.get(i).profileId, text: m.get(i).name + " · " + m.get(i).appName })
                        return out
                    }
                    value: model.profileId
                    onPicked: (v) => app.activities.editItem(s.activityId, model.itemId, { profileId: v })
                }
            }
        }
        Txt { visible: itemsRep.count === 0; text: "No items yet."; tone: "muted" }
        Row {
            spacing: 8
            ActionButton {
                text: "Add files"
                icon: "file-plus"
                small: true
                onClicked: { var p = app.settings.browseFiles("Add files to " + (s.act.name || ""), ""); if (p.length > 0) app.activities.addPaths(s.activityId, p) }
            }
            ActionButton {
                text: "Add a folder"
                icon: "folder-plus"
                small: true
                onClicked: { var p = app.settings.browseFolder("Add a folder to " + (s.act.name || ""), ""); if (p !== "") app.activities.addPaths(s.activityId, [p]) }
            }
        }
        Item { width: 1; height: 8 }
        Txt { text: "From any project"; role: "heading" }
        Field { id: find; width: 320; placeholder: "Search items and paths"; trailingIcon: "magnifying-glass"; input.onTextEdited: s.query = text.toLowerCase() }
        Column {
            width: parent.width
            Repeater {
                model: app.activities.allItems
                delegate: Item {
                    readonly property bool hit: s.query === "" || (model.name + " " + model.path + " " + model.projectTitle).toLowerCase().indexOf(s.query) >= 0
                    width: parent ? parent.width : 600
                    visible: hit
                    height: hit ? 44 : 0
                    Rectangle { width: parent.width; height: 1; color: s.tk.border }
                    Icon { id: pg; y: 14; name: model.glyph }
                    Column {
                        anchors.left: pg.right
                        anchors.leftMargin: 10
                        anchors.right: addBtn.left
                        anchors.rightMargin: 10
                        y: 5
                        Txt { width: parent.width; text: model.name }
                        Txt { width: parent.width; text: model.projectTitle + " · " + model.path; role: "small"; tone: "faint"; elide: Text.ElideMiddle }
                    }
                    ActionButton {
                        id: addBtn
                        anchors.right: parent.right
                        y: 8
                        text: model.inCurrent ? "Added" : "Add"
                        small: true
                        available: !model.inCurrent
                        onClicked: app.activities.addProjectItem(s.activityId, model.projectId, model.itemKey.split("|")[1])
                    }
                }
            }
        }
    }
}
