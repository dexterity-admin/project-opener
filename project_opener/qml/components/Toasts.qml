import QtQuick

// Toasts: bottom right over the page, newest at the bottom, each with the floating shadow; an action toast
// carries one button that routes (app.toastAction).  They arrive with a 8 px rise and fade (180 ms), leave
// faster, and go by themselves after 4.5 s (actions 8 s) unless hovered.  "Show notifications" off hides
// them; feedback the page shows itself (the dock) never comes here.
Item {
    id: toastLayer
    readonly property var tk: app.ui.tokens
    property int seq: 0

    function push(title, body, level, button, route, payload) {
        if (app.settings.value("show_toasts") === false) return
        seq += 1
        list.append({ key: seq, ttitle: title, tbody: body || "", tlevel: level || "info",
                      tbutton: button || "", troute: route || "", tpayload: JSON.stringify(payload || ({})) })
        while (list.count > 4) list.remove(0)
    }

    function clear() { list.clear() }

    ListModel { id: list }

    Connections {
        target: app
        function onToast(title, body, level) { toastLayer.push(title, body, level, "", "", ({})) }
        function onToastAction(title, body, level, button, route, payload) { toastLayer.push(title, body, level, button, route, payload) }
    }

    Column {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 24
        spacing: 10
        width: 360

        Repeater {
            model: list
            delegate: Item {
                id: t
                width: 360
                height: card.height
                opacity: 0
                property bool hovered: hover.containsMouse
                Component.onCompleted: arrive.start()
                NumberAnimation on opacity { id: arrive; running: false; to: 1; duration: Math.round(180 * app.ui.k); easing.type: Easing.OutCubic }
                Timer {
                    interval: model.tbutton !== "" ? 8000 : 4500
                    running: !t.hovered
                    onTriggered: list.remove(index)
                }
                Rectangle {            // the floating shadow: two soft rings under the card
                    x: -2; y: 6; width: card.width + 4; height: card.height + 4
                    radius: 14; color: toastLayer.tk.shadow_soft
                }
                Rectangle {
                    x: 0; y: 3; width: card.width; height: card.height
                    radius: 12; color: toastLayer.tk.shadow_q
                }
                Rectangle {
                    id: card
                    width: parent.width
                    height: col.implicitHeight + 24
                    radius: 12
                    color: toastLayer.tk.surface_2
                    border.width: 1
                    border.color: toastLayer.tk.border_strong
                    Icon {
                        id: lvl
                        x: 14; y: 14
                        name: model.tlevel === "success" ? "check-circle" : model.tlevel === "warning" ? "warning"
                            : model.tlevel === "error" ? "warning-circle" : "info"
                        tone: model.tlevel === "success" ? "ok" : model.tlevel === "warning" ? "warn"
                            : model.tlevel === "error" ? "bad" : "muted"
                    }
                    Column {
                        id: col
                        anchors.left: lvl.right
                        anchors.leftMargin: 10
                        anchors.right: close.left
                        anchors.rightMargin: 8
                        y: 12
                        spacing: 2
                        Txt { width: parent.width; text: model.ttitle; strong: true; wrapMode: Text.Wrap; elide: Text.ElideNone; maximumLineCount: 2 }
                        Txt { width: parent.width; visible: model.tbody !== ""; text: model.tbody; role: "small"; tone: "muted"; wrapMode: Text.Wrap; maximumLineCount: 3 }
                        Item { width: 1; height: model.tbutton !== "" ? 6 : 0 }
                        ActionButton {
                            visible: model.tbutton !== ""
                            text: model.tbutton
                            small: true
                            onClicked: {
                                if (model.troute === "link") app.handle_command({ cmd: "open", link: JSON.parse(model.tpayload).link })
                                else if (model.troute !== "") app.ui.go(model.troute, JSON.parse(model.tpayload))
                                list.remove(index)
                            }
                        }
                    }
                    ActionButton {
                        id: close
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 8
                        kind: "ghost"
                        icon: "x"
                        small: true
                        tooltip: "Dismiss"
                        onClicked: list.remove(index)
                    }
                }
                MouseArea { id: hover; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
            }
        }
    }
}
