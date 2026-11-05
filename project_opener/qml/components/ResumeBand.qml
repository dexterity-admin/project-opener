import QtQuick

// The Resume band (brief 3.1, 6): after an unclean shutdown, the first thing on Home, on the one flat colour
// field.  It is the same object as the paused scene in the centre of the stage.  Resume is the screen's
// one filled control; Dismiss keeps the snapshot (restorable from the activity's checkpoints).  Never automatic.
Rectangle {
    id: band
    readonly property var tk: app.ui.tokens
    readonly property var r: app.activities.resume
    readonly property bool shown: r.activityId !== undefined && r.activityId !== ""
    width: parent ? parent.width : 800
    height: shown ? 56 : 0
    visible: height > 0
    clip: true
    radius: 14
    color: tk.field_mint
    Behavior on height { NumberAnimation { duration: Math.round(240 * app.ui.k); easing.type: Easing.OutCubic } }
    Accessible.role: Accessible.AlertMessage
    Accessible.name: band.shown ? band.r.title + ". " + band.r.text : ""

    Icon { id: ic; x: 18; anchors.verticalCenter: parent.verticalCenter; name: "arrow-counter-clockwise"; tone: "ink" }
    Txt {
        id: ttl
        anchors.left: ic.right
        anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: band.shown ? band.r.title : ""
        strong: true
        tone: "field"
        elide: Text.ElideNone
    }
    Txt {
        anchors.left: ttl.right
        anchors.leftMargin: 12
        anchors.right: buttons.left
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        text: band.shown ? band.r.text : ""
        tone: "muted"
        figures: true
    }
    Row {
        id: buttons
        anchors.right: parent.right
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8
        ActionButton { text: "Dismiss"; kind: "ghost"; onClicked: app.activities.dismissResume() }
        ActionButton { text: "Resume"; icon: "play"; kind: "primary"; onClicked: app.activities.resumeNow() }
    }
}
