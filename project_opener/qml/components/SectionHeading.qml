import QtQuick

// A block heading: the noun (16/600) and, after it in grey, the facts that lead it ("3 · lot 7 check paused
// at 14:32").  A lone count leads in grey, tabular (DESIGN.md), never a KPI strip.  Set `width` to let the
// facts elide; otherwise the heading takes its natural width.
Item {
    id: h
    property string title: ""
    property string facts: ""
    implicitWidth: head.implicitWidth + (facts !== "" ? 8 + factsText.implicitWidth : 0)
    implicitHeight: 24
    Txt {
        id: head
        text: h.title
        role: "heading"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        elide: Text.ElideNone
    }
    Txt {
        id: factsText
        text: h.facts
        visible: h.facts !== ""
        tone: "muted"
        figures: true
        anchors.left: head.right
        anchors.leftMargin: 8
        width: Math.max(0, Math.min(implicitWidth, h.width - head.implicitWidth - 8))
        anchors.baseline: head.baseline
    }
}
