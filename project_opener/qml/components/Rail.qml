import QtQuick

// The 68 px rail (concept-1-stage, ".rail").  Owner: builder 4 (SHELL).
// Skeleton: one round slot per route with a letter in place of the Phosphor icon, the counts to come
// from app.tasks.mineOpenCount and app.hub.inboxCount.
Rectangle {
    id: rail
    readonly property var tk: app.ui.tokens
    property string current: "home"
    signal navigate(string route)

    width: 68
    color: tk.bg

    readonly property var routes: [
        { route: "home", glyph: "H", label: "Home" },
        { route: "projects", glyph: "P", label: "Projects" },
        { route: "hub", glyph: "T", label: "Team Hub" },
        { route: "updates", glyph: "U", label: "Updates" },
        { route: "settings", glyph: "S", label: "Settings" }
    ]

    Column {
        anchors.top: parent.top
        anchors.topMargin: 20
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 6

        Rectangle {          // the mark
            width: 28
            height: 28
            radius: 8
            anchors.horizontalCenter: parent.horizontalCenter
            color: rail.tk.accent
        }
        Item { width: 1; height: 16 }

        Repeater {
            model: rail.routes
            delegate: Rectangle {
                required property var modelData
                width: 40
                height: 40
                radius: 20
                color: rail.current === modelData.route ? rail.tk.surface_2 : "transparent"
                Accessible.role: Accessible.Button
                Accessible.name: modelData.label
                Text {
                    anchors.centerIn: parent
                    text: parent.modelData.glyph
                    color: rail.current === parent.modelData.route ? rail.tk.text : rail.tk.text_muted
                    font.family: "Onest"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: rail.navigate(parent.modelData.route)
                }
            }
        }
    }
}
