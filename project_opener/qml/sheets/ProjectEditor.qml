import QtQuick
import "../components"

// New or edit project (the 3.2 project dialog in the one grammar): name; client | job number on one row;
// description; tags; colour; icon; notes.  Under 640 px tall: it scrolls.
Sheet {
    id: s
    property string projectId: ""
    property string focusField: ""
    readonly property bool creating: projectId === ""
    readonly property var proj: app.activities.currentProject

    title: creating ? "New project" : "Edit project"
    subtitle: creating ? "" : (proj.title || "")
    confirmText: creating ? "Create project" : "Save"
    confirmEnabled: nameField.text.trim() !== ""
    sheetWidth: 600

    Component.onCompleted: {
        if (!creating) {
            app.activities.selectProject(projectId)
            nameField.text = proj.name || ""
            client.text = proj.client || ""
            jobNo.text = proj.jobNumber || ""
            desc.text = proj.description || ""
            tags.text = (proj.tags || []).join(", ")
            notes.text = proj.notes || ""
            colour.value = proj.dotColor || "#2F5BFF"
            iconPick.value = proj.icon || "folder"
        }
        if (s.focusField === "notes") notes.forceActiveFocus(); else nameField.focusInput()
    }
    onAccepted: {
        var f = { name: nameField.text, client: client.text, jobNumber: jobNo.text, description: desc.text,
                  tags: tags.text, notes: notes.text, color: colour.value, icon: iconPick.value }
        if (creating) app.activities.createProject(f)
        else app.activities.editProject(projectId, f)
        s.close()
    }

    Field { id: nameField; width: parent.width; label: "Name"; placeholder: "As-built isometrics"; onAccepted: s.accept() }
    Row {
        width: parent.width
        spacing: 16
        Field { id: client; width: (parent.width - 16) / 2; label: "Client"; placeholder: "FST" }
        Field { id: jobNo; width: (parent.width - 16) / 2; label: "Job number"; placeholder: "P12513"; help: "Leads every title: P12513 · As-built isometrics." }
    }
    Field { id: desc; width: parent.width; label: "Description"; placeholder: "RLM red-line cross-check" }
    Field { id: tags; width: parent.width; label: "Tags"; placeholder: "as-built, isometrics"; help: "Separate with commas." }
    Column {
        spacing: 6
        Txt { text: "Colour"; strong: true }
        Row {
            id: colour
            property string value: "#2F5BFF"
            spacing: 8
            Repeater {
                model: ["#2F5BFF", "#10B981", "#F97316", "#8B5CF6", "#14B8A6", "#E11D48", "#CA8A04", "#64748B"]
                delegate: Rectangle {
                    required property var modelData
                    width: 26; height: 26; radius: 13
                    color: modelData
                    border.width: colour.value.toUpperCase() === modelData ? 3 : 0
                    border.color: s.tk.text
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: colour.value = parent.modelData }
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: "Colour " + modelData
                }
            }
        }
    }
    Column {
        width: parent.width
        spacing: 6
        Txt { text: "Icon"; strong: true }
        Flow {
            id: iconPick
            property string value: "folder"
            width: parent.width
            spacing: 6
            Repeater {
                model: app.activities.projectIcons
                delegate: Rectangle {
                    required property var modelData
                    width: 34; height: 34; radius: 10
                    color: iconPick.value === modelData ? s.tk.surface_3 : ipm.containsMouse ? s.tk.surface_2 : "transparent"
                    Icon { anchors.centerIn: parent; name: parent.modelData; tone: iconPick.value === parent.modelData ? "ink" : "muted" }
                    MouseArea { id: ipm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: iconPick.value = parent.modelData }
                }
            }
        }
    }
    AreaField { id: notes; width: parent.width; label: "Notes"; placeholder: "Rulings, contacts, the share's quirks"; boxHeight: 72 }
}
