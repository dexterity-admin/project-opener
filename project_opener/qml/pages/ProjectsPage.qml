import QtQuick
import QtQuick.Controls.Basic as C
import "../components"
import "../sheets"

// Projects: the jobs.  Search, tag filters (outlined chips: the only interactive chips), list or grid (the
// 3.2 view_mode), health pills.  Cards: the icon tile on its tint, the title (job number first), the second
// line never blank, pale tag pills, the health line, the pill, Open pinned to the foot so a row of cards has
// one bottom edge.  New project is the page's primary.
Page {
    id: page
    minimumWidth: 860
    property string mode: app.settings.value("view_mode") === "list" ? "list" : "grid"
    readonly property int cols: contentW >= 1180 ? 3 : 2
    readonly property int cardW: Math.floor((contentW - (cols - 1) * 16) / cols)

    // A line of facts drops whole facts from the right until it fits (DESIGN.md): a card's pill never runs
    // under its Open button ("1 server offline · 1 undefined variable · 5 reachable" -> "1 server offline").
    FontMetrics { id: pillMetrics; font.family: page.tk.face; font.pixelSize: 12; font.weight: Font.Medium }
    function fitFacts(text, maxW) {
        var parts = String(text).split(" · ")
        while (parts.length > 1 && pillMetrics.advanceWidth(parts.join(" · ")) + 16 > maxW) parts.pop()
        return parts.join(" · ")
    }

    PageHeader {
        title: "Projects"
        subtitle: app.activities.projectCount === 0 ? "" : app.activities.projectCount + (app.activities.projectCount === 1 ? " project" : " projects")
                  + (rep.count !== app.activities.projectCount ? " · " + rep.count + " shown" : "")
        Segmented {
            options: [{ value: "grid", text: "Grid" }, { value: "list", text: "List" }]
            value: page.mode
            label: "View"
            onPicked: (v) => { page.mode = v; app.settings.setValue("view_mode", v) }
        }
        ActionButton {
            text: "New project"
            icon: "plus"
            kind: "primary"
            onClicked: Window.window.openSheet("ProjectEditor", { projectId: "" })
        }
    }

    LaunchDock { width: page.contentW }

    // search and tag filters
    Item {
        width: page.contentW
        height: Math.max(34, chips.height)
        Field {
            id: search
            width: 280
            placeholder: "Search projects, items and paths"
            trailingIcon: text !== "" ? "x" : "magnifying-glass"
            text: app.activities.projectQuery
            input.onTextEdited: app.activities.setProjectFilter(search.text, app.activities.projectTag)
            onTrailingClicked: { search.text = ""; app.activities.setProjectFilter("", app.activities.projectTag) }
        }
        Flow {
            id: chips
            anchors.left: search.right
            anchors.leftMargin: 16
            anchors.right: parent.right
            y: 3
            spacing: 6
            Repeater {
                model: app.activities.allTags
                delegate: Chip {
                    required property var modelData
                    interactive: true
                    text: modelData
                    checked: app.activities.projectTag === modelData
                    onClicked: app.activities.setProjectFilter(search.text, checked ? "" : modelData)
                }
            }
        }
    }

    // grid
    Flow {
        id: grid
        visible: page.mode === "grid"
        width: page.contentW
        spacing: 16
        Repeater {
            id: rep
            model: app.activities.projects
            delegate: Card {
                id: card
                // the last row: two or more cards share its full width; a lone card keeps its column width
                // (DESIGN.md "Card grids", 3.2's justified last row)
                readonly property int lastRow: rep.count % page.cols
                readonly property bool inLastRow: lastRow >= 2 && index >= rep.count - lastRow
                width: inLastRow ? Math.floor((page.contentW - (lastRow - 1) * 16) / lastRow) : page.cardW
                height: 196
                color: cardMouse.containsMouse ? tk.surface_2 : tk.surface
                Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k) } }
                MouseArea {
                    id: cardMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: app.ui.go("project", { projectId: model.projectId })
                }
                IconTile { id: tile; x: card.pad; y: card.pad; icon: model.icon; tint: model.dotColor; size: 36 }
                Column {
                    anchors.left: tile.right
                    anchors.leftMargin: 12
                    anchors.right: parent.right
                    anchors.rightMargin: card.pad
                    y: card.pad - 2
                    spacing: 2
                    Txt { width: parent.width; text: model.title; role: "heading" }
                    Txt { width: parent.width; text: model.subtitle; tone: "muted" }
                }
                Flow {
                    x: card.pad
                    y: 78
                    width: card.width - 2 * card.pad
                    height: 22
                    clip: true
                    spacing: 6
                    Repeater {
                        model: tags
                        delegate: Chip { required property var modelData; text: modelData }
                    }
                }
                Txt {
                    x: card.pad
                    y: 112
                    width: card.width - 2 * card.pad
                    text: model.healthLine + (model.activityCount > 0 ? " · " + model.activityCount + (model.activityCount === 1 ? " activity" : " activities") : "")
                    role: "small"
                    tone: "faint"
                    figures: true
                }
                Item {
                    x: card.pad
                    width: card.width - 2 * card.pad
                    height: 34
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: card.pad - 4
                    ActionButton {
                        id: openBtn
                        text: "Open project"
                        small: true
                        onClicked: app.activities.openProject(model.projectId)
                    }
                    StatusPill {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        status: model.healthWorst === "ok" ? "ok" : model.healthWorst === "offline" ? "bad" : model.healthWorst === "" ? "neutral" : "warn"
                        label: model.healthWorst === "" ? "" : page.fitFacts(model.healthText, parent.width - openBtn.width - 12)
                    }
                }
                Icon {
                    visible: model.pinned
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 14
                    name: "push-pin"
                    size: 14
                    tone: "faint"
                }
            }
        }
    }

    // list
    Card {
        visible: page.mode === "list"
        width: page.contentW
        height: listCol.implicitHeight + 2 * pad
        Column {
            id: listCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            Repeater {
                model: page.mode === "list" ? app.activities.projects : null
                delegate: Item {
                    width: listCol.width
                    height: 60
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                    Rectangle { anchors.fill: parent; anchors.topMargin: 1; radius: 10; color: lm.containsMouse ? page.tk.surface_2 : "transparent" }
                    MouseArea { id: lm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: app.ui.go("project", { projectId: model.projectId }) }
                    IconTile { id: lt; x: 4; anchors.verticalCenter: parent.verticalCenter; icon: model.icon; tint: model.dotColor; size: 30 }
                    Column {
                        anchors.left: lt.right
                        anchors.leftMargin: 12
                        anchors.right: lpill.left
                        anchors.rightMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        Txt { width: parent.width; text: model.title; strong: true }
                        Txt { width: parent.width; text: model.subtitle + " · " + model.healthLine; role: "small"; tone: "faint"; figures: true }
                    }
                    Item {
                        id: lpill
                        width: 170
                        height: 20
                        anchors.right: lopen.left
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        StatusPill {
                            anchors.right: parent.right
                            status: model.healthWorst === "ok" ? "ok" : model.healthWorst === "offline" ? "bad" : model.healthWorst === "" ? "neutral" : "warn"
                            label: model.healthWorst === "" ? "" : model.healthText
                        }
                    }
                    ActionButton {
                        id: lopen
                        anchors.right: parent.right
                        anchors.rightMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Open"
                        small: true
                        onClicked: app.activities.openProject(model.projectId)
                    }
                }
            }
        }
    }

    EmptyBlock {
        visible: rep.count === 0
        width: page.contentW
        line: app.activities.projectCount === 0 ? "No projects yet. A project holds a job's files, folders and links."
                                                : "Nothing matches ‘" + search.text + "’."
        action: app.activities.projectCount === 0 ? "New project" : "Clear the filter"
        onTriggered: {
            if (app.activities.projectCount === 0) Window.window.openSheet("ProjectEditor", { projectId: "" })
            else { search.text = ""; app.activities.setProjectFilter("", "") }
        }
    }

}
