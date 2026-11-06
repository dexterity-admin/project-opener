import QtQuick
import "../components"

// Updates (3.2 flow over AppContext): check, download, install and restart, skip, mirror to the hub; the
// version appears here once (its subtitle).  One filled control: Download / Install while an update is
// offered, else Check for updates.  Update sources (as 3.2): the LAN mirror's reachability (probed off the GUI
// thread) and GitHub, with "Copy this version to the Team Hub" under the mirror so an admin can put the version
// the office runs on the share without a pending download (an installed build only; otherwise the reason
// shows; hidden once a newer installer is downloaded, whose own copy control is then the one).  Diagnostics:
// the data folder, the render backend and motion level.
Page {
    id: page
    minimumWidth: 860
    readonly property string st: app.settings.updateState
    readonly property var info: app.settings.update
    readonly property bool offered: info.version !== undefined && st !== "skipped"
    readonly property string busyVersion: app.settings.mirrorVersion !== "" ? app.settings.mirrorVersion : (page.info.version || "")

    Component.onCompleted: app.settings.refreshSources()

    PageHeader {
        title: "Updates"
        subtitle: app.settings.updateLine
        ActionButton {
            text: page.st === "checking" ? "Checking…" : "Check for updates"
            icon: "arrows-clockwise"
            kind: page.offered || page.st === "ready" ? "outline" : "primary"
            available: page.st !== "checking" && page.st !== "downloading"
            onClicked: app.settings.checkUpdates()
        }
    }

    Card {
        width: page.contentW
        height: stateCol.implicitHeight + 2 * pad
        Column {
            id: stateCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            spacing: 10

            Row {
                spacing: 10
                Icon {
                    name: page.st === "error" ? "warning-circle" : page.offered || page.st === "ready" ? "arrow-circle-up" : "check-circle"
                    tone: page.st === "error" ? "bad" : page.offered || page.st === "ready" ? "accent" : "muted"
                    size: 18
                    anchors.verticalCenter: parent.verticalCenter
                }
                Txt {
                    anchors.verticalCenter: parent.verticalCenter
                    role: "heading"
                    text: page.st === "error" ? "Could not check for updates"
                        : page.st === "ready" ? "Version " + page.info.version + " is downloaded and verified"
                        : page.st === "downloading" ? "Downloading version " + page.info.version
                        : page.st === "mirroring" ? "Copying version " + page.busyVersion + " to the Team Hub"
                        : page.st === "skipped" ? "Version " + page.info.version + " is skipped"
                        : page.offered ? "Version " + page.info.version + " is available"
                        : page.st === "checking" ? "Checking GitHub and the Team Hub mirror…"
                        : page.st === "none" ? "You are on the latest version"
                        : app.settings.checkLine
                }
            }
            Txt {
                width: parent.width
                visible: text !== ""
                // the version is the subtitle's; this line says only what it does not
                text: page.st === "error" ? app.settings.updateError
                    : page.st === "skipped" ? "It is not offered again until a newer one appears."
                    : page.offered || page.st === "ready" ? [ "From " + page.info.source, page.info.size, page.info.published ].filter(function (s) { return s && s !== "" }).join(" · ")
                    : page.st === "none" || page.st === "idle" ? "The channel is " + (app.settings.value("update_channel") === "all" ? "every release" : "stable releases")
                    : ""
                tone: page.st === "error" ? "bad" : "muted"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
            }
            Txt {
                width: Math.min(640, parent.width)
                visible: (page.offered || page.st === "ready") && page.info.notes !== ""
                text: page.info.notes || ""
                tone: "muted"
                wrapMode: Text.Wrap
                elide: Text.ElideNone
                maximumLineCount: 8
            }
            Rectangle {                     // determinate progress, 4 px, full width under its label
                visible: page.st === "downloading"
                width: parent.width
                height: 4
                radius: 2
                color: page.tk.surface_3
                Rectangle { height: 4; radius: 2; color: page.tk.accent; width: parent.width * app.settings.updateProgress }
            }
            Row {
                spacing: 8
                visible: page.offered || page.st === "ready" || page.st === "skipped"
                ActionButton {
                    visible: page.st === "available"
                    text: "Download"
                    icon: "download-simple"
                    kind: "primary"
                    onClicked: app.settings.downloadUpdate()
                }
                ActionButton {
                    visible: page.st === "ready"
                    text: "Install and restart"
                    icon: "arrow-circle-up"
                    kind: "primary"
                    onClicked: app.settings.installUpdate()
                }
                ActionButton {
                    visible: page.st === "ready" && app.hub.configured
                    text: "Copy " + (page.info.version || "it") + " to the Team Hub"
                    icon: "share-network"
                    onClicked: app.settings.mirrorUpdate()
                }
                ActionButton {
                    visible: page.st === "available"
                    text: "Skip this version"
                    kind: "ghost"
                    onClicked: app.settings.skipUpdate()
                }
                ActionButton {
                    visible: page.st === "skipped"
                    text: "Offer it again"
                    kind: "ghost"
                    onClicked: app.settings.unskipUpdate()
                }
            }
        }
    }

    // ------------------------------------------------------------ update sources (3.2)
    Card {
        width: page.contentW
        height: srcCol.implicitHeight + 2 * pad
        Column {
            id: srcCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            spacing: 4
            SectionHeading { width: parent.width; title: "Update sources" }
            Item { width: 1; height: 4 }
            Repeater {
                model: app.settings.updateSources
                delegate: Column {
                    required property var modelData
                    required property int index
                    width: srcCol.width
                    Item {
                        width: parent.width
                        height: 54
                        Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: index > 0 }
                        Icon { id: si; y: 14; name: modelData.key === "lan" ? "hard-drives" : "globe-simple" }
                        Column {
                            anchors.left: si.right
                            anchors.leftMargin: 12
                            anchors.right: sp.left
                            anchors.rightMargin: 16
                            y: 10
                            spacing: 2
                            Txt { width: parent.width; text: modelData.name; strong: true }
                            Txt { width: parent.width; text: modelData.detail; role: "small"; tone: "faint"; elide: Text.ElideMiddle }
                        }
                        Item {
                            id: sp
                            width: 130
                            height: 20
                            anchors.right: parent.right
                            y: 14
                            StatusPill { anchors.right: parent.right; status: modelData.status; label: modelData.label }
                        }
                    }
                    // under the mirror: copy the version this PC runs, for colleagues to install from the LAN
                    Row {
                        visible: modelData.key === "lan" && app.settings.mirrorCurrentShown
                        x: 28
                        spacing: 12
                        height: visible ? 44 : 0
                        ActionButton {
                            id: mirrorNow
                            anchors.verticalCenter: parent.verticalCenter
                            text: "Copy this version to the Team Hub"
                            icon: "share-network"
                            small: true
                            available: app.settings.mirrorCurrentReason === "" && page.st !== "mirroring"
                            tooltip: "Puts the installer of the version you run (from its GitHub release, verified) in the hub's updates folder, so colleagues install it over the LAN"
                            onClicked: app.settings.mirrorCurrent()
                        }
                        Txt {
                            anchors.verticalCenter: parent.verticalCenter
                            visible: app.settings.mirrorCurrentReason !== ""
                            width: srcCol.width - 28 - mirrorNow.width - 12
                            text: app.settings.mirrorCurrentReason
                            role: "small"
                            tone: "muted"
                        }
                    }
                }
            }
        }
    }

    Card {
        width: page.contentW
        height: diag.implicitHeight + 2 * pad
        Column {
            id: diag
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            spacing: 8
            SectionHeading { width: parent.width; title: "Diagnostics" }
            Repeater {
                // no version row: the subtitle carries it (DESIGN.md: a fact appears once per screen)
                model: [
                    { k: "Signed in as", v: app.displayName, tip: "@" + app.login },
                    { k: "Data folder", v: app.settings.dataFolder, tip: "" },
                    { k: "Rendering", v: app.ui.backend === "software" ? "Software (no graphics card in use)" : "Graphics card", tip: "" },
                    { k: "Motion", v: app.ui.motionReason, tip: "" },
                    { k: "Company", v: "Dexterity Design Services Pvt. Ltd.", tip: "" }
                ]
                delegate: Item {
                    required property var modelData
                    width: diag.width
                    height: 30
                    Txt { width: 160; text: parent.modelData.k; tone: "muted" }
                    Txt {
                        x: 170
                        width: parent.width - 170 - 90
                        text: parent.modelData.v
                        figures: true
                        elide: Text.ElideMiddle
                        HoverHandler { id: dh }
                        Tip { visible: dh.hovered && parent.parent.modelData.tip !== ""; text: parent.parent.modelData.tip }
                    }
                }
            }
            ActionButton {
                text: "Open the data folder"
                icon: "folder-open"
                small: true
                onClicked: app.settings.openFolder(app.settings.dataFolder)
            }
        }
    }
}
