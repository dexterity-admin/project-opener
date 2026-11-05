import QtQuick

// Text in the one family (Onest) at one of the type roles of docs/DESIGN.md.
// role: title 24/600 · heading 16/600 · section 16/600 · body 13/400 · small 12/400 · kpi 24/400
// tone: ink | muted | faint | accent | ok | warn | bad | onAccent.  figures: tabular numbers (rows, pills, times).
Text {
    id: t
    readonly property var tk: app.ui.tokens
    property string role: "body"
    property string tone: "ink"
    property bool figures: false
    property bool strong: false

    font.family: tk.face
    font.pixelSize: role === "title" || role === "kpi" ? 24 : role === "heading" || role === "section" ? 16
                  : role === "small" ? 12 : 13
    font.weight: role === "title" || role === "heading" || role === "section" ? Font.DemiBold
               : strong ? Font.Medium : Font.Normal
    font.features: figures ? ({ "tnum": 1 }) : ({})
    color: tone === "muted" ? tk.text_muted : tone === "faint" ? tk.text_faint : tone === "accent" ? tk.accent
         : tone === "ok" ? tk.success : tone === "warn" ? tk.warning : tone === "bad" ? tk.danger
         : tone === "onAccent" ? tk.accent_fg : tone === "field" ? tk.field_ink : tk.text
    elide: Text.ElideRight
    textFormat: Text.PlainText
    verticalAlignment: Text.AlignVCenter
}
