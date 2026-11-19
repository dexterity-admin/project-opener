import QtQuick

// The 4.0 sidebar (docs/DESIGN.md "Shape and space", concept B "Drafted Glass"): 236 px on the page ground with
// a hairline on its right edge; the Dexterity mark and the product name; Search; mono group labels over the
// routes; the active route is a surface_2 fill with a 2 px teal bar on its left; counts only on queues.
// Below a 1100 px window it folds to the 68 px rail (labels become tooltips) so pages keep their 860 px
// minimum.  It lists only routes that exist: Time travel, Space map, Wrapped and Handover join when built.
Item {
    id: side
    readonly property var tk: app.ui.tokens
    property bool expanded: true
    property string current: "home"
    signal navigate(string route, var payload)
    signal search()

    readonly property int fullWidth: 236
    width: expanded ? fullWidth : app.ui.railWidth
    Behavior on width { NumberAnimation { duration: Math.round(240 * app.ui.k); easing.type: Easing.OutCubic } }

    readonly property int hubCount: (app.hub.inboxCount || 0)
    readonly property int tasksOpen: (app.tasks.mineOpenCount || 0)
    readonly property string hubTab: side.current === "hub" ? (app.ui.routePayload.tab || "") : ""

    Rail {                                   // the folded form: the 3.x/Stage rail, unchanged
        anchors.fill: parent
        visible: !side.expanded
        current: side.current
        onNavigate: (route) => side.navigate(route, ({}))
        onSearch: side.search()
    }

    Rectangle {                              // the hairline on the right edge
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 1
        color: side.tk.border
        visible: side.expanded
    }

    component NavRow: Rectangle {
        id: row
        property string glyph: ""
        property string label: ""
        property int count: 0
        property bool active: false
        signal clicked()
        width: parent ? parent.width : 0
        height: 36
        radius: 5
        color: active ? side.tk.surface_2 : hover.containsMouse ? side.tk.surface_2 : "transparent"
        Behavior on color { ColorAnimation { duration: Math.round(140 * app.ui.k) } }
        Accessible.role: Accessible.Button
        Accessible.name: label + (count > 0 ? ", " + count : "")
        Rectangle {                          // the teal bar of the active route
            visible: row.active
            x: 0; y: 6; width: 2; height: row.height - 12; radius: 1
            color: side.tk.teal
        }
        Icon {
            x: 12
            anchors.verticalCenter: parent.verticalCenter
            name: row.glyph
            size: 18
            tone: row.active ? "ink" : "muted"
        }
        Txt {
            x: 40
            anchors.verticalCenter: parent.verticalCenter
            width: row.width - 40 - (cnt.visible ? cnt.width + 12 : 12)
            text: row.label
            strong: true
            tone: row.active ? "ink" : "muted"
        }
        Txt {
            id: cnt
            visible: row.count > 0
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            role: "label"
            figures: true
            text: String(row.count)
        }
        MouseArea {
            id: hover
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: row.clicked()
        }
        transform: Translate { x: hover.containsMouse && !row.active ? 2 : 0
            Behavior on x { NumberAnimation { duration: Math.round(250 * app.ui.k); easing.type: Easing.OutCubic } } }
    }

    Item {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 15
        visible: side.expanded
        opacity: side.expanded ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Math.round(180 * app.ui.k) } }

        Column {
            id: top
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.topMargin: 20
            spacing: 2

            Row {                            // the mark and the product
                spacing: 10
                leftPadding: 8
                bottomPadding: 14
                Image {
                    width: 28; height: 28
                    source: "../../resources/brand/dexterity-mark-64.png"
                    sourceSize.width: 64; sourceSize.height: 64
                    smooth: true
                    Accessible.name: "Dexterity"
                }
                Txt { text: "Project Opener"; strong: true; anchors.verticalCenter: parent.verticalCenter }
            }

            Rectangle {                      // Search: reads as a field, opens the palette
                width: parent.width
                height: 36
                radius: 5
                color: searchHover.containsMouse ? side.tk.surface_2 : "transparent"
                border.width: 1
                border.color: side.tk.border
                Accessible.role: Accessible.Button
                Accessible.name: "Search (Ctrl+K)"
                Icon { x: 12; anchors.verticalCenter: parent.verticalCenter; name: "magnifying-glass"; size: 16 }
                Txt { x: 40; anchors.verticalCenter: parent.verticalCenter; text: "Search"; tone: "faint" }
                Txt { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                      text: "Ctrl K"; role: "label" }
                MouseArea { id: searchHover; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: side.search() }
            }

            Txt { text: "Workspace"; role: "label"; leftPadding: 12; topPadding: 18; bottomPadding: 8 }
            NavRow { glyph: "house"; label: "Today"; active: side.current === "home"; onClicked: side.navigate("home", ({})) }
            NavRow { glyph: "stack"; label: "Activities"; active: side.current === "activities" || side.current === "activity"
                     onClicked: side.navigate("activities", ({})) }
            NavRow { glyph: "squares-four"; label: "Projects"; active: side.current === "projects" || side.current === "project"
                     onClicked: side.navigate("projects", ({})) }
            NavRow { glyph: "checks"; label: "Tasks"; count: side.tasksOpen; active: side.hubTab === "tasks"
                     onClicked: side.navigate("hub", ({ tab: "tasks" })) }
            NavRow { glyph: "clock-counter-clockwise"; label: "Time travel"; active: side.current === "timetravel"; onClicked: side.navigate("timetravel", ({})) }

            Txt { text: "Office"; role: "label"; leftPadding: 12; topPadding: 18; bottomPadding: 8 }
            NavRow { glyph: "users-three"; label: "Team Hub"; count: side.hubCount
                     active: side.current === "hub" && side.hubTab !== "tasks"; onClicked: side.navigate("hub", ({})) }
        }

        Column {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 16
            spacing: 2
            NavRow { glyph: "arrow-circle-down"; label: "Updates"; active: side.current === "updates"
                     onClicked: side.navigate("updates", ({})) }
            NavRow { glyph: "sliders-horizontal"; label: "Settings"; active: side.current === "settings"
                     onClicked: side.navigate("settings", ({})) }
            Item { width: 1; height: 10 }
            Row {                            // the person
                spacing: 10
                leftPadding: 8
                Avatar {
                    initials: app.displayName.length > 0 ? app.displayName.charAt(0).toUpperCase() : "?"
                    hue: side.tk.accent
                    online: app.hub.configured && app.hub.reachable
                    size: 28
                }
                Txt { anchors.verticalCenter: parent.verticalCenter; text: app.displayName; width: 150 }
            }
        }
    }
}
