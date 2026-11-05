import QtQuick
import "../components"

// Updates (3.2 flow over AppContext): check, download, install and restart, skip, mirror to the hub; the
// version appears here only (its subtitle).  One filled control: Download / Install while an update is
// offered, else Check for updates.  Diagnostics: the data folder, the render backend and motion level.
Page {
    id: page
    minimumWidth: 860
    readonly property string st: app.settings.updateState
    readonly property var info: app.settings.update
    readonly property bool offered: info.version !== undefined && st !== "skipped"

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
                        : page.st === "mirroring" ? "Copying version " + page.info.version + " to the Team Hub"
                        : page.st === "skipped" ? "Version " + page.info.version + " is skipped"
                        : page.offered ? "Version " + page.info.version + " is available"
                        : page.st === "checking" ? "Checking GitHub and the Team Hub mirror…"
                        : page.st === "none" ? "You are on the latest version"
                        : "Updates are checked every few hours"
                }
            }
            Txt {
                width: parent.width
                visible: text !== ""
                text: page.st === "error" ? app.settings.updateError
                    : page.st === "skipped" ? "It is not offered again until a newer one appears."
                    : page.offered || page.st === "ready" ? [ "From " + page.info.source, page.info.size, page.info.published ].filter(function (s) { return s && s !== "" }).join(" · ")
                    : page.st === "none" || page.st === "idle" ? app.version + " · the channel is " + (app.settings.value("update_channel") === "all" ? "every release" : "stable releases")
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
                    text: "Copy to the Team Hub"
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
                model: [
                    { k: "Version", v: app.version },
                    { k: "Signed in as", v: app.displayName + " · " + app.login },
                    { k: "Data folder", v: app.settings.dataFolder },
                    { k: "Rendering", v: app.ui.backend === "software" ? "Software (no graphics card in use)" : "Graphics card" },
                    { k: "Motion", v: app.ui.motionReason },
                    { k: "Company", v: "Dexterity Design Services Pvt. Ltd." }
                ]
                delegate: Item {
                    required property var modelData
                    width: diag.width
                    height: 30
                    Txt { width: 160; text: parent.modelData.k; tone: "muted" }
                    Txt { x: 170; width: parent.width - 170 - 90; text: parent.modelData.v; figures: true; elide: Text.ElideMiddle }
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
