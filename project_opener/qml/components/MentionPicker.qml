import QtQuick
import QtQuick.Controls.Basic as C

// The @ picker (brief 3.2): people and groups from app.hub.mentionCandidates (users/*.json and groups.json;
// builder 1 narrows it with setMentionQuery; never the user themself), each with display name, role and the
// online dot (the login in a tooltip: DESIGN.md "People"); a group shows its members.  A popup in the window's overlay (never clipped by a sheet) placed under the caret by its
// host; it never takes the focus: Up/Down/Enter arrive from the host's field.  Hosts: MentionField, ForField.
C.Popup {
    id: pk
    readonly property var tk: app.ui.tokens
    property int current: 0
    property bool shown: false
    readonly property int count: rep.count
    signal chosen(string login)

    visible: shown
    width: 340
    padding: 6
    focus: false
    modal: false
    closePolicy: C.Popup.NoAutoClose

    function move(step) { if (count > 0) current = (current + step + count) % count }
    function choose() {
        if (count === 0) return false
        pk.chosen(app.hub.mentionCandidates.get(current).login)
        return true
    }

    background: Item {
        Rectangle { visible: app.ui.dark; x: -2; y: 6; width: parent.width + 4; height: parent.height + 2; radius: 14; color: pk.tk.shadow_soft }
        Rectangle { anchors.fill: parent; radius: 12; color: pk.tk.surface; border.width: 1; border.color: pk.tk.border_strong }
    }
    contentItem: Column {
        id: col
        Repeater {
            id: rep
            model: app.hub.mentionCandidates
            delegate: Rectangle {
                width: pk.width - 12
                height: 40
                radius: 8
                color: index === pk.current || m.containsMouse ? pk.tk.surface_2 : "transparent"
                Avatar {
                    id: av
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    size: 24
                    initials: model.isGroup ? "@" : String(model.displayName).charAt(0)
                    online: !model.isGroup && model.online
                }
                Txt {
                    id: nm
                    anchors.left: av.right
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.isGroup ? "@" + model.login : model.displayName
                    strong: true
                    elide: Text.ElideNone
                }
                Txt {
                    anchors.left: nm.right
                    anchors.leftMargin: 8
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.isGroup ? "group · " + model.memberCount + " · " + model.role
                                        : [model.role, model.online ? "online" : "offline"].filter(function (x) { return x && x !== "" }).join(" · ")
                    role: "small"
                    tone: "faint"
                }
                MouseArea { id: m; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: pk.chosen(model.login) }
                Tip { visible: m.containsMouse && !model.isGroup; text: "@" + model.login }
            }
        }
        Txt { visible: rep.count === 0; x: 8; height: 32; text: "Nobody by that name"; tone: "muted" }
        Txt {
            x: 8
            height: 26
            text: "Enter inserts · people and groups on the Team Hub"
            role: "small"
            tone: "faint"
        }
    }
}
