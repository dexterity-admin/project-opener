import QtQuick
import QtQuick.Controls.Basic as C

// A page: a vertical scroller with the page margins and one column (gap 16).  `minimumWidth` is the page's
// explicit minimum (the spike's rule: QML has no sizeHint), asserted by tools/smoke_quick.py against the
// 1040 x 660 window beside the rail.  `narrow` tells blocks to stack.
Flickable {
    id: page
    readonly property var tk: app.ui.tokens
    property int minimumWidth: 860
    readonly property int margin: width >= 1200 ? 40 : 28
    readonly property int contentW: width - 2 * margin
    readonly property bool narrow: contentW < 1000
    default property alias content: col.data
    property alias column: col

    contentWidth: width
    contentHeight: col.implicitHeight + 28 + 40
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    C.ScrollBar.vertical: C.ScrollBar {
        policy: page.contentHeight > page.height ? C.ScrollBar.AsNeeded : C.ScrollBar.AlwaysOff
        contentItem: Rectangle { implicitWidth: 6; radius: 3; color: page.tk.border_strong }
    }

    function scrollTo(item) {
        var y = item.mapToItem(col, 0, 0).y + 28 - 16
        contentY = Math.max(0, Math.min(y, contentHeight - height))
    }

    Column {
        id: col
        x: page.margin
        y: 28
        width: page.contentW
        spacing: 16
    }
}
