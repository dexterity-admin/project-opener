import QtQuick
import QtQuick.Controls.Basic as C
import "../components"

// Space map (docs/V4-PLUS-BRIEF.md "Share hygiene", docs/DESIGN.md "Motion"): bubbles sized by the space each
// project card's folders use, drill-down with breadcrumbs, and beside them the duplicate groups and stale files
// of what is shown, each with Show in Explorer.  Report only: nothing here deletes, moves or renames a file.
// Physics by motion level: rich = drift and bump (and drag), purposeful = settle, then stop; off = packed, still.
// Amber inside a bubble is the share of its bytes that are a duplicate or stale.  One filled control: Scan.
Page {
    id: page
    minimumWidth: 860
    readonly property var sm: app.spacemap
    readonly property var st: sm.stats
    readonly property bool rich: app.ui.ambient && Window.active
    readonly property bool moving: app.ui.k > 0
    property string side: "duplicates"

    // the side card's two lists (one shown at a time); placed under the card's heading
    component SideList: ListView {
        id: lv
        x: sideCard.pad
        y: sideHead.y + sideHead.height + 10
        width: sideCard.width - 2 * sideCard.pad
        height: sideCard.height - y - 8
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        property string emptyText: ""
        C.ScrollBar.vertical: C.ScrollBar {
            policy: lv.contentHeight > lv.height ? C.ScrollBar.AsNeeded : C.ScrollBar.AlwaysOff
            contentItem: Rectangle { implicitWidth: 6; radius: 3; color: page.tk.border_strong }
        }
        Txt {
            width: parent.width
            visible: lv.count === 0 && page.sm.hasResult
            text: lv.emptyText
            tone: "muted"
            wrapMode: Text.Wrap
            elide: Text.ElideNone
        }
    }

    Component.onCompleted: sm.load()

    PageHeader {
        title: "Space map"
        subtitle: page.sm.scanning ? page.sm.progressText : page.sm.summary
        ActionButton {
            text: page.sm.state === "stopping" ? "Stopping…" : page.sm.scanning ? "Stop" : page.sm.hasResult ? "Scan again" : "Scan"
            icon: page.sm.scanning ? "stop-circle" : "arrows-clockwise"
            kind: page.sm.scanning ? "outline" : "primary"
            available: page.sm.state !== "loading" && page.sm.state !== "stopping"
            tooltip: page.sm.scanning ? "Stops the scan; what was listed so far is kept"
                                      : "Reads every folder named on the Team Hub's project cards. Nothing is changed."
            onClicked: page.sm.scanning ? page.sm.cancel() : page.sm.scan()
        }
    }

    Txt {
        width: page.contentW
        visible: page.sm.state === "error"
        text: page.sm.error
        tone: "bad"
        wrapMode: Text.Wrap
        elide: Text.ElideNone
    }

    // ------------------------------------------------------------ the four figures
    Row {
        id: figures
        width: page.contentW
        spacing: 16
        visible: page.sm.hasResult
        readonly property int cell: (width - 3 * spacing) / 4
        Repeater {
            model: [
                { label: "Space used", value: page.st.size, facts: page.st.files },
                { label: "In duplicates", value: page.st.dupWasted, facts: page.st.dupGroups },
                { label: "Stale · " + page.sm.scannedMonths + " months", value: page.st.stale, facts: page.st.staleCount },
                { label: "Skipped", value: String(page.st.skipped), facts: page.st.skipped === 1 ? "path" : "paths" }
            ]
            delegate: Card {
                required property var modelData
                width: figures.cell
                height: 92
                Rectangle { x: 0; y: 0; width: parent.width; height: 2; radius: 1; color: page.tk.border_strong }
                Column {
                    x: parent.pad; y: 14
                    width: parent.width - 2 * parent.pad
                    spacing: 4
                    Txt { width: parent.width; text: modelData.label; role: "label" }
                    Txt { width: parent.width; text: modelData.value; role: "kpi" }
                    Txt { width: parent.width; text: modelData.facts; role: "small"; tone: "faint"; figures: true }
                }
            }
        }
    }

    // ------------------------------------------------------------ bubbles | side lists
    Flow {
        id: body
        width: page.contentW
        spacing: 16
        readonly property int sideW: page.narrow ? width : 360
        readonly property int mapW: page.narrow ? width : width - sideW - spacing
        readonly property int blockH: page.narrow ? 400 : 470

        Card {
            id: mapCard
            width: body.mapW
            height: body.blockH
            clip: true

            Row {                                   // breadcrumbs
                id: crumbs
                x: parent.pad - 6; y: 12
                spacing: 2
                Repeater {
                    model: page.sm.crumbs
                    delegate: Row {
                        required property var modelData
                        required property int index
                        spacing: 2
                        Icon { visible: index > 0; name: "caret-right"; size: 12; tone: "faint"; anchors.verticalCenter: parent.verticalCenter }
                        ActionButton {
                            text: modelData.label
                            kind: "link"
                            small: true
                            available: index < page.sm.depth
                            onClicked: page.sm.goTo(modelData.depth)
                        }
                    }
                }
            }

            EmptyBlock {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: parent.pad
                anchors.verticalCenter: parent.verticalCenter
                visible: !page.sm.hasResult && !page.sm.scanning && page.sm.state !== "loading"
                line: "Not scanned yet. A scan reads every folder named on the Team Hub's project cards, finds files of the same content and files nobody has changed for "
                      + page.sm.staleMonths + " months. Nothing on the share is changed."
            }
            Txt {
                anchors.centerIn: field
                visible: page.sm.hasResult && bubbleRep.count === 0
                text: "No files here."
                tone: "muted"
            }

            Item {                                  // the bubble field
                id: field
                x: 8
                y: crumbs.y + 40
                width: parent.width - 16
                height: parent.height - y - 8
                property real energy: 0
                property real settleUntil: 0

                function radiusFor(b) {
                    var total = 0, i
                    for (i = 0; i < bubbleRep.count; i++) total += Math.max(1, bubbleRep.itemAt(i) ? bubbleRep.itemAt(i).bytes : 1)
                    var area = width * height * 0.5
                    var k = Math.sqrt(area / (Math.PI * Math.max(1, total)))
                    return Math.max(14, Math.min(Math.min(width, height) * 0.36, k * Math.sqrt(Math.max(1, b))))
                }
                // packed, largest first: each bubble touches one already placed, at the free spot nearest the
                // centre (36 directions round each); if one does not fit, every radius shrinks by a tenth and the
                // pack starts again.  The group is then centred.  Same input, same picture (no randomness).
                function layout(scale) {
                    var cx = width / 2, cy = height / 2, placed = [], gap = 4
                    for (var i = 0; i < bubbleRep.count; i++) {
                        var b = bubbleRep.itemAt(i)
                        if (!b) continue
                        var r = Math.max(10, radiusFor(b.bytes) * scale), best = null, bestD = 1e12
                        var cands = placed.length === 0 ? [{ x: cx, y: cy }] : []
                        for (var j = 0; j < placed.length; j++) {
                            var p = placed[j]
                            for (var t = 0; t < 36; t++) {
                                var ang = t * Math.PI / 18
                                cands.push({ x: p.x + Math.cos(ang) * (p.r + r + gap), y: p.y + Math.sin(ang) * (p.r + r + gap) })
                            }
                        }
                        for (var c = 0; c < cands.length; c++) {
                            var q = cands[c]
                            if (q.x < r || q.y < r || q.x > width - r || q.y > height - r) continue
                            var ok = true
                            for (var m = 0; m < placed.length && ok; m++)
                                if (Math.hypot(placed[m].x - q.x, placed[m].y - q.y) < placed[m].r + r + gap - 0.5) ok = false
                            var d = (q.x - cx) * (q.x - cx) * 0.6 + (q.y - cy) * (q.y - cy)
                            if (ok && d < bestD) { best = q; bestD = d }
                        }
                        if (best === null) return null
                        placed.push({ x: best.x, y: best.y, r: r, item: b })
                    }
                    return placed
                }
                function pack() {
                    if (width <= 0 || height <= 0) return
                    var placed = null, scale = 1
                    for (var tries = 0; tries < 12 && placed === null; tries++, scale *= 0.9) placed = layout(scale)
                    if (placed === null) return
                    var x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, i
                    for (i = 0; i < placed.length; i++) {
                        x0 = Math.min(x0, placed[i].x - placed[i].r); x1 = Math.max(x1, placed[i].x + placed[i].r)
                        y0 = Math.min(y0, placed[i].y - placed[i].r); y1 = Math.max(y1, placed[i].y + placed[i].r)
                    }
                    var sx = width / 2 - (x0 + x1) / 2, sy = height / 2 - (y0 + y1) / 2
                    for (i = 0; i < placed.length; i++) {
                        var b = placed[i].item
                        b.r = placed[i].r
                        if (!b.placed || !page.moving) { b.px = placed[i].x + sx; b.py = placed[i].y + sy; b.placed = true }
                        b.vx = 0; b.vy = 0
                    }
                    wake()
                }
                function step(dt) {
                    var n = bubbleRep.count, i, j, a, b
                    var f = Math.min(2, dt * 60)
                    var t = Date.now() / 1700
                    var e = 0
                    for (i = 0; i < n; i++) {
                        a = bubbleRep.itemAt(i)
                        if (!a || a.held) continue
                        a.vx += (width / 2 - a.px) * 0.0006 * f
                        a.vy += (height / 2 - a.py) * 0.0006 * f
                        if (page.rich) a.vx += Math.sin(t + a.r) * 0.004 * f
                        a.vx *= Math.pow(0.96, f); a.vy *= Math.pow(0.96, f)
                        a.px += a.vx * f; a.py += a.vy * f
                    }
                    for (i = 0; i < n; i++) {
                        a = bubbleRep.itemAt(i)
                        if (!a) continue
                        a.px = Math.min(width - a.r, Math.max(a.r, a.px)); a.py = Math.min(height - a.r, Math.max(a.r, a.py))
                        for (j = i + 1; j < n; j++) {
                            b = bubbleRep.itemAt(j)
                            if (!b) continue
                            var dx = b.px - a.px, dy = b.py - a.py, d = Math.hypot(dx, dy) || 1, m = a.r + b.r + 3
                            if (d < m) {
                                var p = (m - d) / 2, ux = dx / d, uy = dy / d
                                if (!a.held) { a.px -= ux * p; a.py -= uy * p; a.vx -= ux * 0.15; a.vy -= uy * 0.15 }
                                if (!b.held) { b.px += ux * p; b.py += uy * p; b.vx += ux * 0.15; b.vy += uy * 0.15 }
                            }
                        }
                        e += a.vx * a.vx + a.vy * a.vy
                    }
                    energy = e
                }

                onWidthChanged: packLater.restart()
                onHeightChanged: packLater.restart()
                Timer { id: packLater; interval: 30; onTriggered: field.pack() }

                // rich: runs while the window is active; purposeful: settles (2.5 s at most), then stops; off: never
                function wake() {
                    if (!page.moving || bubbleRep.count === 0) return
                    settleUntil = Math.max(settleUntil, Date.now() + 2500)
                    if (!sim.running) sim.start()
                }
                Connections { target: page; function onRichChanged() { field.wake() } }
                FrameAnimation {
                    id: sim
                    onTriggered: {
                        field.step(frameTime)
                        if (!page.rich && !field.anyHeld && (Date.now() > field.settleUntil || field.energy < 0.0004)) {
                            field.settleUntil = 0
                            stop()
                        }
                    }
                }
                property bool anyHeld: false

                Repeater {
                    id: bubbleRep
                    model: page.sm.bubbles
                    onCountChanged: packLater.restart()
                    delegate: Item {
                        id: bub
                        required property string bubbleKey
                        required property string label
                        required property var bytes
                        required property string sizeText
                        required property real share
                        required property bool drillable
                        required property string detail
                        property real r: 20
                        property real px: field.width / 2
                        property real py: field.height / 2
                        property real vx: 0
                        property real vy: 0
                        property bool placed: false
                        property bool held: false
                        onBytesChanged: packLater.restart()
                        x: px - r; y: py - r
                        width: 2 * r; height: 2 * r
                        Behavior on r { enabled: page.moving && bub.placed; NumberAnimation { duration: Math.round(420 * app.ui.k); easing.type: Easing.OutCubic } }

                        Rectangle {
                            anchors.fill: parent
                            radius: width / 2
                            color: page.tk.surface_2
                            border.width: 1
                            border.color: hit.containsMouse && bub.drillable ? page.tk.accent : page.tk.border_strong
                        }
                        Rectangle {                     // the duplicate-or-stale share, as area
                            readonly property real rr: bub.r * Math.sqrt(Math.max(0, Math.min(1, bub.share)))
                            visible: rr >= 2
                            anchors.centerIn: parent
                            width: 2 * rr; height: 2 * rr; radius: rr
                            color: page.tk.action
                            opacity: 0.55
                        }
                        Column {
                            anchors.centerIn: parent
                            width: 2 * bub.r * 0.78
                            visible: bub.r >= 26
                            Txt { width: parent.width; text: bub.label; role: "small"; strong: true; horizontalAlignment: Text.AlignHCenter }
                            Txt { width: parent.width; text: bub.sizeText; role: "label"; figures: true; horizontalAlignment: Text.AlignHCenter
                                  visible: bub.r >= 32 }
                        }
                        MouseArea {
                            id: hit
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: bub.held ? Qt.ClosedHandCursor : bub.drillable ? Qt.PointingHandCursor : Qt.OpenHandCursor
                            property real sx: 0
                            property real sy: 0
                            property bool dragged: false
                            onPressed: (m) => { sx = m.x; sy = m.y; dragged = false; bub.held = true; field.anyHeld = true; field.wake() }
                            onPositionChanged: (m) => {
                                if (!pressed) return
                                var dx = m.x - sx, dy = m.y - sy
                                if (!dragged && Math.hypot(dx, dy) < 4) return
                                dragged = true
                                var nx = Math.min(field.width - bub.r, Math.max(bub.r, bub.px + dx))
                                var ny = Math.min(field.height - bub.r, Math.max(bub.r, bub.py + dy))
                                bub.vx = (nx - bub.px) * 0.5; bub.vy = (ny - bub.py) * 0.5
                                bub.px = nx; bub.py = ny
                                if (!page.moving) bub.vx = bub.vy = 0
                            }
                            onReleased: {
                                bub.held = false; field.anyHeld = false
                                field.wake()
                                if (!dragged && bub.drillable) page.sm.drill(bub.bubbleKey)
                            }
                            onCanceled: { bub.held = false; field.anyHeld = false }
                        }
                        Tip { visible: hit.containsMouse && !bub.held; text: bub.label + " · " + bub.sizeText
                              + (bub.share > 0.005 ? " · " + Math.round(bub.share * 100) + "% duplicate or stale" : "")
                              + (bub.detail !== "" && bub.detail !== bub.label ? "\n" + bub.detail : "") }
                        Accessible.role: bub.drillable ? Accessible.Button : Accessible.StaticText
                        Accessible.name: bub.label + ", " + bub.sizeText
                    }
                }
            }
        }

        Card {
            id: sideCard
            width: body.sideW
            height: body.blockH
            Column {
                id: sideHead
                x: parent.pad; y: parent.pad
                width: parent.width - 2 * parent.pad
                spacing: 12
                Segmented {
                    label: "List"
                    value: page.side
                    options: [ { value: "duplicates", text: "Duplicates · " + page.sm.duplicateCount },
                               { value: "stale", text: "Stale · " + page.sm.staleCount } ]
                    onPicked: (v) => page.side = v
                }
                Row {
                    spacing: 8
                    visible: page.side === "stale"
                    Txt { text: "Stale after"; tone: "muted"; anchors.verticalCenter: parent.verticalCenter }
                    Segmented {
                        label: "Stale after (months)"
                        value: String(page.sm.staleMonths)
                        options: page.sm.staleChoices.map(function (m) { return { value: m, text: m } })
                        onPicked: (v) => page.sm.setStaleMonths(v)
                    }
                    Txt { text: "months"; tone: "muted"; anchors.verticalCenter: parent.verticalCenter }
                }
                Txt {
                    visible: page.side === "stale" && page.sm.hasResult && page.sm.staleMonths !== page.sm.scannedMonths
                    width: parent.width
                    text: "The list is from a scan at " + page.sm.scannedMonths + " months; scan again to use " + page.sm.staleMonths + "."
                    role: "small"; tone: "faint"; wrapMode: Text.Wrap; elide: Text.ElideNone
                }
            }
            SideList {                              // duplicate groups: each copy's folder with Show in Explorer
                id: dupList
                visible: page.side === "duplicates"
                model: page.sm.duplicates
                emptyText: "No duplicate files here."
                delegate: Column {
                    id: dupRow
                    required property string name
                    required property string countText
                    required property string sizeText
                    required property var paths
                    required property int index
                    width: dupList.width - 8
                    spacing: 2
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: dupRow.index > 0 }
                    Item { width: 1; height: 6 }
                    Txt { width: parent.width; text: dupRow.name; strong: true; elide: Text.ElideMiddle }
                    Txt { width: parent.width; role: "small"; tone: "faint"; figures: true
                          text: dupRow.countText + " · " + dupRow.sizeText }
                    Repeater {
                        model: dupRow.paths.slice(0, 4)
                        delegate: Item {
                            required property string modelData
                            width: dupRow.width
                            height: 28
                            Txt { anchors.left: parent.left; anchors.right: rev.left; anchors.rightMargin: 6
                                  anchors.verticalCenter: parent.verticalCenter
                                  text: modelData.substring(0, modelData.lastIndexOf("\\")) || modelData
                                  role: "small"; tone: "muted"; elide: Text.ElideMiddle }
                            ActionButton { id: rev; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                           icon: "folder-open"; kind: "ghost"; small: true
                                           tooltip: "Show in Explorer"; onClicked: page.sm.showInExplorer(modelData) }
                        }
                    }
                    Txt { visible: dupRow.paths.length > 4; role: "small"; tone: "faint"
                          text: "and " + (dupRow.paths.length - 4) + " more" }
                    Item { width: 1; height: 6 }
                }
            }
            SideList {                              // stale files, largest first
                id: staleList
                visible: page.side === "stale"
                model: page.sm.stale
                emptyText: "No file here is older than " + page.sm.scannedMonths + " months."
                delegate: Item {
                    id: staleRow
                    required property string path
                    required property string name
                    required property string folder
                    required property string sizeText
                    required property string ageText
                    required property int index
                    width: staleList.width - 8
                    height: 52
                    Rectangle { width: parent.width; height: 1; color: page.tk.border; visible: staleRow.index > 0 }
                    Column {
                        anchors.left: parent.left; anchors.right: srev.left; anchors.rightMargin: 6
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Txt { width: parent.width; text: staleRow.name; strong: true; elide: Text.ElideMiddle }
                        Txt { width: parent.width; role: "small"; tone: "faint"; figures: true; elide: Text.ElideMiddle
                              text: staleRow.ageText + " · " + staleRow.sizeText + " · " + staleRow.folder }
                    }
                    ActionButton { id: srev; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                   icon: "folder-open"; kind: "ghost"; small: true
                                   tooltip: "Show in Explorer"; onClicked: page.sm.showInExplorer(staleRow.path) }
                }
            }
        }
    }

    // ------------------------------------------------------------ what was skipped
    Card {
        width: page.contentW
        visible: page.st.skipped > 0
        height: visible ? skipCol.implicitHeight + 2 * pad : 0
        Column {
            id: skipCol
            x: parent.pad; y: parent.pad
            width: parent.width - 2 * parent.pad
            spacing: 4
            SectionHeading { width: parent.width; title: "Skipped"; facts: page.st.skipped + (page.st.skipped === 1 ? " path" : " paths") }
            Repeater {
                model: page.sm.skipped
                delegate: Item {
                    required property string path
                    required property string reason
                    required property int index
                    visible: index < 8
                    width: skipCol.width
                    height: visible ? 26 : 0
                    Txt { width: parent.width * 0.7; text: path !== "" ? path : "The scan"; role: "small"; elide: Text.ElideMiddle
                          anchors.verticalCenter: parent.verticalCenter }
                    Txt { x: parent.width * 0.7 + 12; width: parent.width * 0.3 - 12; text: reason; role: "small"; tone: "muted"
                          anchors.verticalCenter: parent.verticalCenter }
                }
            }
            Txt { visible: page.st.skipped > 8; role: "small"; tone: "faint"
                  text: "and " + (page.st.skipped - 8) + " more" }
        }
    }
}
