import QtQuick

// The newest current announcement on Home, one line above the footlights (DESIGN.md: "Announcements: the
// newest only, as one band with the body on one line and +N more to the right"; brief 3.7 keeps it from 3.2).
// The level is only the 6 px dot (info, warning, error); the title and its age always read whole, the body
// elides.  A click opens the Team Hub's Announcements tab.  Hidden when there is none (expired ones never
// reach app.hub.announcements).
Rectangle {
    id: band
    readonly property var tk: app.ui.tokens
    property var newest: null
    property int total: 0
    visible: newest !== null
    implicitHeight: visible ? 40 : 0
    radius: 12
    color: hov.containsMouse ? tk.surface_2 : tk.surface
    border.width: 1
    border.color: tk.border

    function pick() {
        var m = app.hub.announcements, best = null
        for (var i = 0; i < m.count(); i++) {
            var a = m.get(i)
            if (best === null || String(a.ts) > String(best.ts)) best = a
        }
        newest = best
        total = m.count()
    }
    Connections {
        target: app.hub.announcements
        function onCountChanged() { band.pick() }
        function onDataChanged() { band.pick() }
        function onModelReset() { band.pick() }
    }
    Component.onCompleted: pick()

    readonly property string level: newest ? String(newest.level) : ""
    Accessible.role: Accessible.Button
    Accessible.name: newest ? "Announcement: " + newest.title + ", " + newest.tsText + ". Open the announcements" : ""

    Icon {
        id: mega
        x: 14
        anchors.verticalCenter: parent.verticalCenter
        name: "megaphone-simple"
        size: 16
    }
    Rectangle {
        id: dot
        anchors.left: mega.right
        anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        width: 6
        height: 6
        radius: 3
        color: band.level === "error" ? band.tk.danger : band.level === "warning" ? band.tk.warning : band.tk.info
    }
    Txt {
        id: title
        objectName: "newsTitle"
        anchors.left: dot.right
        anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(implicitWidth, tail.x - x - 12)
        text: band.newest ? band.newest.title : ""
        strong: true
    }
    Txt {
        id: body
        anchors.left: title.right
        anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, tail.x - x - 12)
        visible: width > 40 && text !== ""
        text: band.newest ? String(band.newest.body).replace(/\s+/g, " ") : ""
        tone: "muted"
    }
    Row {
        id: tail
        anchors.right: parent.right
        anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10
        Txt {
            anchors.verticalCenter: parent.verticalCenter
            text: band.newest ? [band.newest.authorName, band.newest.tsText].filter(function (s) { return s && s !== "" }).join(" · ") : ""
            role: "small"
            tone: "faint"
            figures: true
            elide: Text.ElideNone
        }
        Txt {
            visible: band.total > 1
            anchors.verticalCenter: parent.verticalCenter
            text: "+" + (band.total - 1) + " more"
            role: "small"
            tone: "muted"
            figures: true
            elide: Text.ElideNone
        }
        Icon { name: "arrow-right"; size: 14; anchors.verticalCenter: parent.verticalCenter }
    }
    MouseArea {
        id: hov
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: app.ui.go("hub", { tab: "announcements" })
    }
}
