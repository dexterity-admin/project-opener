import QtQuick

// Text at one of the type roles of docs/DESIGN.md ("Type"): Instrument Sans for the body, Archivo light for
// titles and numerals, JetBrains Mono for section labels, Cormorant italic for a person's own note.
// role: title 30/Archivo 300 · heading 16/600 · section 16/600 · body 13/400 · small 12/400 · kpi 24/Archivo 300
//       · hero 32/Archivo 250 (Today's hero) · numeral 44/Archivo 250, tabular (Today's stats)
//       · label 10.5/mono 500 uppercase · note 19/Cormorant italic
// tone: ink | muted | faint | accent | ok | warn | bad | onAccent | onAction.  figures: tabular numbers.
Text {
    id: t
    readonly property var tk: app.ui.tokens
    property string role: "body"
    property string tone: "ink"
    property bool figures: false
    property bool strong: false
    readonly property bool display: role === "title" || role === "kpi" || role === "hero" || role === "numeral"

    font.family: display ? tk.face_display : role === "label" ? tk.face_mono : role === "note" ? tk.face_note : tk.face
    font.pixelSize: role === "numeral" ? 44 : role === "hero" ? 32 : role === "title" ? 30 : display ? 24 : role === "heading" || role === "section" ? 16
                  : role === "small" ? 12 : role === "label" ? 10.5 : role === "note" ? 19 : 13
    font.weight: role === "hero" || role === "numeral" ? 250 : display ? Font.Light
               : role === "heading" || role === "section" ? Font.DemiBold
               : role === "label" || role === "note" ? Font.Medium
               : strong ? Font.Medium : Font.Normal
    font.italic: role === "note"
    font.capitalization: role === "label" ? Font.AllUppercase : Font.MixedCase
    font.letterSpacing: role === "label" ? 1.5 : role === "numeral" ? -1.8 : role === "hero" ? -0.8 : display ? -0.5 : 0
    font.features: figures || role === "kpi" || role === "numeral" ? ({ "tnum": 1 }) : ({})   // never a title (DESIGN.md)
    color: tone === "muted" ? tk.text_muted : tone === "faint" || role === "label" && tone === "ink" ? tk.text_faint
         : tone === "accent" ? tk.accent
         : tone === "ok" ? tk.success : tone === "warn" ? tk.warning : tone === "bad" ? tk.danger
         : tone === "onAccent" ? tk.accent_fg : tone === "onAction" ? tk.action_fg
         : tone === "field" ? tk.field_ink : tk.text
    elide: Text.ElideRight
    textFormat: Text.PlainText
    verticalAlignment: Text.AlignVCenter
}
