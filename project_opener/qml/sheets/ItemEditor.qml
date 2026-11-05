import QtQuick
import "../components"

// Edit a project item: label, path (stored portable: a drive letter becomes its share or variable), kind |
// group on one row, arguments and a CAD launch profile for applications, the on switch.
Sheet {
    id: s
    property string projectId: ""
    property string itemId: ""
    readonly property var row: {
        var m = app.activities.projectItems
        var i = m.indexOf(itemId)
        return i >= 0 ? m.get(i) : ({})
    }
    title: "Edit item"
    subtitle: row.name || ""
    confirmText: "Save item"
    confirmEnabled: pathField.text.trim() !== ""
    sheetWidth: 600

    Component.onCompleted: {
        label.text = row.label || ""
        pathField.text = row.path || ""
        kind.value = row.kind || "file"
        group.text = row.group || ""
        args.text = row.args || ""
        profile.value = row.profileId || ""
        on.checked = row.itemEnabled !== false
        pathField.focusInput()
    }
    onAccepted: {
        app.activities.editProjectItem(projectId, itemId, {
            label: label.text, path: app.activities.portable(pathField.text), kind: kind.value, group: group.text,
            args: args.text, profileId: profile.value, itemEnabled: on.checked })
        s.close()
    }
    footerExtra: [
        ActionButton {
            text: "Remove item"
            kind: "danger"
            small: true
            onClicked: Window.window.confirm("Remove " + (s.row.name || "this item") + "?",
                                             "Activities drawn from it keep their own copy.", "Remove item", true,
                                             function () { app.activities.removeProjectItem(s.projectId, s.itemId) })
        }
    ]

    Field { id: label; width: parent.width; label: "Label"; placeholder: "Leave empty to show the file name" }
    Row {
        spacing: 12
        Field { id: pathField; width: 440; label: "Path or address"; placeholder: "\\\\nas01\\Project\\P12513\\ISO" }
        ActionButton {
            y: 25
            text: "Browse"
            icon: "folder-open"
            onClicked: { var p = app.settings.browseFile("Choose the file", pathField.text, ""); if (p !== "") pathField.text = p }
        }
    }
    Row {
        spacing: 16
        ChoiceField {
            id: kind
            width: 220
            label: "Kind"
            options: [{ value: "file", text: "File" }, { value: "folder", text: "Folder" }, { value: "url", text: "Link" },
                      { value: "app", text: "Application" }, { value: "command", text: "Command" }]
            onPicked: (v) => value = v
        }
        Field { id: group; width: 300; label: "Group"; placeholder: "Checking" }
    }
    Field { id: args; visible: kind.value === "app" || kind.value === "command"; width: parent.width; label: "Arguments"; placeholder: "{ITEM} -viewpoint \"Lot 7\"" }
    ChoiceField {
        id: profile
        visible: kind.value === "app"
        width: 360
        label: "Launch profile"
        options: {
            var out = [{ value: "", text: "No launch profile" }]
            var m = app.activities.profiles
            for (var i = 0; i < m.count(); i++) out.push({ value: m.get(i).profileId, text: m.get(i).name + " · " + m.get(i).appName })
            return out
        }
        onPicked: (v) => value = v
    }
    SwitchRow { id: on; label: "Open with the project"; onToggled: (v) => checked = v }
}
