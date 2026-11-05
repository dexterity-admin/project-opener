import QtQuick

// One Phosphor glyph (the icon font qtawesome ships; app.ui.glyph maps names, including migrated
// 3.x "fa5s.*" names).  Plain grey by default: colour belongs to identity and health only.
Text {
    id: icon
    readonly property var tk: app.ui.tokens
    property string name: ""
    property int size: 16
    property string tone: "muted"

    text: name === "" ? "" : app.ui.glyph(name)
    font.family: app.ui.iconFamily
    font.pixelSize: size
    width: size
    height: size
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    color: tone === "ink" ? tk.text : tone === "faint" ? tk.text_faint : tone === "accent" ? tk.accent
         : tone === "onAccent" ? tk.accent_fg : tone === "ok" ? tk.success : tone === "warn" ? tk.warning
         : tone === "bad" ? tk.danger : tk.text_muted
    Accessible.ignored: true
}
