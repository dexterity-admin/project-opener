import QtQuick
import QtQuick.Controls.Basic as C
import "../components"

// The revision diff (route "diff"; docs/V4-PLUS-BRIEF.md "Visual revision diff").  Two revisions of one
// drawing or document: dropped on the page, chosen here, or sent by "Compare with…" on an item (payload
// {a, b}).  PDF: the red/green overlay with a page strip and the changed regions; Excel: changed cells per
// sheet; Word: changed paragraphs with the words inside.  The page reports what differs, never whether a
// change is right.  Everything comes from app.diff (quick/diff_api.py).
Item {
    id: root
    readonly property var tk: app.ui.tokens
    readonly property var d: app.diff
    readonly property var res: d.result
    readonly property string kind: d.state === "done" ? (res.kind || "") : ""
    property int minimumWidth: 860
    property alias contentHeight: pg.contentHeight

    // PDF view state
    readonly property var pages: kind === "pdf" ? (res.pages || []) : []
    property int pageIdx: 0
    property int regionIdx: -1
    property real zoom: 1                  // 1 = the whole sheet in view; 2, 4 = closer
    readonly property var curPage: pageIdx < pages.length ? pages[pageIdx] : null
    readonly property var regions: curPage ? (curPage.regions || []) : []
    // Excel view state
    readonly property var sheets: kind === "xlsx" ? (res.sheets || []) : []
    property string sheetName: ""
    readonly property var curSheet: {
        for (var i = 0; i < sheets.length; i++) if (sheets[i].name === sheetName) return sheets[i]
        return sheets.length ? sheets[0] : null
    }
    property int shownRows: 200
    property bool dragging: false
    // the page's sheet image is on screen (the overlay loads asynchronously; the smoke waits for it)
    readonly property bool overlayReady: kind !== "pdf" || sheetImg.status === Image.Ready || sheetImg.status === Image.Error

    onResChanged: {
        pageIdx = 0
        regionIdx = -1
        zoom = 1
        shownRows = 200
        var first = ""
        var ps = res.pages || []
        for (var i = 0; i < ps.length; i++) if (ps[i].status !== "same") { pageIdx = i; break }
        var ss = res.sheets || []
        for (var j = 0; j < ss.length; j++) if (ss[j].status !== "same") { first = ss[j].name; break }
        sheetName = first !== "" ? first : (ss.length ? ss[0].name : "")
    }
    Component.onCompleted: {
        var p = app.ui.routePayload
        if (p && p.a && p.b) app.diff.compare(p.a, p.b)
        else root.resChanged()
    }

    function pickRegion(i) {
        regionIdx = i
        if (i < 0 || i >= regions.length) return
        if (zoom === 1) zoom = 2
        Qt.callLater(viewer.centreOn, regions[i])
    }
    function kindWord(k) { return k === "both" ? "Added and removed" : k === "added" ? "Added" : "Removed" }
    function kindLevel(k) { return k === "added" ? "ok" : k === "removed" ? "bad" : k === "changed" ? "info" : "neutral" }
    function changeWord(k) { return k === "added" ? "Added" : k === "removed" ? "Removed" : k === "formula" ? "Formula" : "Changed" }
    function esc(s) {
        return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
                        .replace(/\t/g, "&nbsp;&nbsp;&nbsp;&nbsp;").replace(/\n/g, "<br>")
    }
    function segmentsHtml(segs) {
        var out = ""
        for (var i = 0; i < segs.length; i++) {
            var s = segs[i]
            if (s.op === "eq") { out += esc(s.text); continue }
            if (s.op === "ins" && i > 0 && segs[i - 1].op === "del") out += "&#8201;"   // a thin space after the struck word
            if (s.op === "del")
                out += "<span style=\"background-color:" + tk.pill_bad_bg + ";color:" + tk.pill_bad_ink + ";text-decoration:line-through\">" + esc(s.text) + "</span>"
            else
                out += "<span style=\"background-color:" + tk.pill_ok_bg + ";color:" + tk.pill_ok_ink + "\">" + esc(s.text) + "</span>"
        }
        return out
    }
    function pageLine(p) {
        if (p.status === "same") return "No change"
        if (p.status === "added") return "New page"
        if (p.status === "removed") return "Page removed"
        var n = (p.regions || []).length
        return n === 1 ? "1 region" : n + " regions"
    }
    function wordsLine(added, removed) {
        var parts = []
        if (added.length) parts.push("+ " + added.slice(0, 8).join(" ") + (added.length > 8 ? " …" : ""))
        if (removed.length) parts.push("− " + removed.slice(0, 8).join(" ") + (removed.length > 8 ? " …" : ""))
        return parts.join("   ")
    }

    Page {
        id: pg
        anchors.fill: parent
        minimumWidth: root.minimumWidth

        PageHeader {
            title: "Revision diff"
            subtitle: d.state === "done" ? (res.summary || "") : d.state === "busy" ? d.progressText : ""
            ActionButton {
                visible: d.fileA !== "" && d.fileB !== ""
                text: "Swap"
                icon: "arrows-left-right"
                tooltip: "Compare the other way round"
                onClicked: app.diff.swap()
            }
            ActionButton {
                visible: d.fileA !== "" || d.fileB !== ""
                text: "New comparison"
                icon: "x"
                kind: "ghost"
                onClicked: app.diff.clear()
            }
        }

        // ------------------------------------------------------------------ the pair: older → newer
        Item {
            id: pair
            width: parent.width
            height: 72
            visible: d.fileA !== "" || d.fileB !== ""
            Repeater {
                model: [{ side: "a", label: "Older", name: d.nameA, folder: d.folderA, path: d.fileA },
                        { side: "b", label: "Newer", name: d.nameB, folder: d.folderB, path: d.fileB }]
                delegate: Card {
                    required property var modelData
                    required property int index
                    x: index === 0 ? 0 : (pair.width + 40) / 2
                    width: (pair.width - 40) / 2
                    height: 72
                    Rectangle {          // the side's colour in the overlay: removed (older), added (newer)
                        width: 3
                        radius: 1.5
                        x: 10
                        y: 14
                        height: parent.height - 28
                        color: index === 0 ? d.colours.removed : d.colours.added
                    }
                    Column {
                        anchors.left: parent.left
                        anchors.leftMargin: 24
                        anchors.right: sideActions.left
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Txt { text: modelData.label; role: "label" }
                        Txt {
                            width: parent.width
                            text: modelData.name !== "" ? modelData.name : "No file yet"
                            strong: modelData.name !== ""
                            tone: modelData.name !== "" ? "ink" : "muted"
                            elide: Text.ElideMiddle
                        }
                        Txt { width: parent.width; visible: modelData.folder !== ""; text: modelData.folder; role: "small"; tone: "faint"; elide: Text.ElideMiddle }
                    }
                    Row {
                        id: sideActions
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 4
                        ActionButton {
                            visible: modelData.path !== ""
                            icon: "arrow-square-out"; kind: "ghost"; small: true
                            tooltip: "Open " + modelData.name
                            onClicked: app.diff.openFile(modelData.path)
                        }
                        ActionButton {
                            text: modelData.path !== "" ? "Change…" : "Choose file…"
                            kind: modelData.path !== "" ? "ghost" : "outline"
                            small: true
                            onClicked: app.diff.browse(modelData.side)
                        }
                    }
                }
            }
            Icon { anchors.centerIn: parent; name: "arrow-right"; size: 18; tone: "faint" }
        }

        // ------------------------------------------------------------------ nothing chosen yet
        Card {
            width: parent.width
            height: emptyBlock.implicitHeight + 2 * pad
            visible: d.fileA === "" && d.fileB === ""
            EmptyBlock {
                id: emptyBlock
                anchors.fill: parent
                anchors.margins: parent.pad
                line: "Two revisions of one drawing or document: PDF, Excel .xlsx or Word .docx. Drop both here, or choose them."
                action: "Choose two files"
                actionIcon: "git-diff"
                actionKind: "primary"
                onTriggered: app.diff.browsePair()
            }
        }

        // ------------------------------------------------------------------ working / cannot compare
        Card {
            width: parent.width
            height: 76
            visible: d.state === "busy"
            Column {
                anchors.fill: parent
                anchors.margins: parent.pad
                spacing: 10
                Txt { width: parent.width; text: d.progressText; tone: "muted"; figures: true }
                Rectangle {
                    width: parent.width
                    height: 4
                    radius: 2
                    color: tk.surface_2
                    Rectangle {
                        height: 4
                        radius: 2
                        color: tk.teal
                        width: parent.width * Math.max(0.03, d.progress)
                        Behavior on width { NumberAnimation { duration: Math.round(240 * app.ui.k); easing.type: Easing.OutCubic } }
                    }
                }
            }
        }
        Card {
            width: parent.width
            height: errCol.implicitHeight + 2 * pad
            visible: d.state === "error"
            Column {
                id: errCol
                x: parent.pad
                y: parent.pad
                width: parent.width - 2 * parent.pad
                spacing: 12
                Txt { width: parent.width; text: d.error; tone: "bad"; wrapMode: Text.Wrap; elide: Text.ElideNone }
                ActionButton { text: "Choose other files"; small: true; onClicked: app.diff.browsePair() }
            }
        }

        // ------------------------------------------------------------------ PDF: strip · overlay · regions
        Item {
            id: pdfView
            visible: root.kind === "pdf"
            width: parent.width
            readonly property int stripW: 112
            readonly property int sideW: pg.narrow ? 0 : 288
            readonly property int viewH: Math.max(400, root.height - 250)
            height: visible ? (pg.narrow ? viewH + 16 + regionsCard.height : Math.max(viewH, regionsCard.height)) : 0

            // page strip
            ListView {
                id: strip
                width: pdfView.stripW
                height: pdfView.viewH
                clip: true
                spacing: 10
                model: root.pages
                boundsBehavior: Flickable.StopAtBounds
                C.ScrollBar.vertical: C.ScrollBar { policy: strip.contentHeight > strip.height ? C.ScrollBar.AsNeeded : C.ScrollBar.AlwaysOff }
                delegate: Item {
                    required property var modelData
                    required property int index
                    readonly property bool on: index === root.pageIdx
                    width: strip.width - 10
                    height: thumb.height + 40
                    Rectangle {
                        id: thumb
                        width: parent.width
                        height: Math.round(width * modelData.height / Math.max(1, modelData.width))
                        color: "#FFFFFF"
                        border.width: parent.on ? 2 : 1
                        border.color: parent.on ? root.tk.accent : root.tk.border
                        radius: 4
                        Image {
                            anchors.fill: parent
                            anchors.margins: 2
                            source: modelData.thumbUrl || ""
                            asynchronous: true
                            fillMode: Image.PreserveAspectFit
                            smooth: true
                        }
                    }
                    Txt { y: thumb.height + 4; text: "Page " + (index + 1); role: "small"; strong: parent.on; figures: true }
                    Txt {
                        y: thumb.height + 20
                        width: parent.width
                        text: root.pageLine(modelData)
                        role: "small"
                        tone: modelData.status === "same" ? "faint" : "muted"
                        figures: true
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: { root.pageIdx = index; root.regionIdx = -1; root.zoom = 1 }
                    }
                    Accessible.role: Accessible.Button
                    Accessible.name: "Page " + (index + 1) + ", " + root.pageLine(modelData)
                }
            }

            // the overlay
            Card {
                id: viewCard
                x: pdfView.stripW + 16
                width: parent.width - x - (pdfView.sideW > 0 ? pdfView.sideW + 16 : 0)
                height: pdfView.viewH
                clip: true
                Row {
                    id: legend
                    x: 14
                    y: 12
                    spacing: 14
                    Repeater {
                        model: [{ c: d.colours.removed, t: "Removed" }, { c: d.colours.added, t: "Added" },
                                { c: d.colours.unchanged, t: "Unchanged" }]
                        delegate: Row {
                            required property var modelData
                            spacing: 6
                            Rectangle { width: 10; height: 10; radius: 2; color: modelData.c; anchors.verticalCenter: parent.verticalCenter }
                            Txt { text: modelData.t; role: "small"; tone: "muted" }
                        }
                    }
                }
                Segmented {
                    id: zoomSeg
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    y: 6
                    label: "Zoom"
                    value: String(root.zoom)
                    options: [{ value: "1", text: "Whole sheet" }, { value: "2", text: "2×" }, { value: "4", text: "4×" }]
                    onPicked: (v) => { root.zoom = Number(v); if (root.regionIdx >= 0) Qt.callLater(viewer.centreOn, root.regions[root.regionIdx]) }
                }
                Rectangle { y: 46; width: parent.width; height: 1; color: root.tk.border }
                Flickable {
                    id: viewer
                    x: 1
                    y: 47
                    width: parent.width - 2
                    height: parent.height - 48
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    readonly property real pw: root.curPage ? root.curPage.width : 1
                    readonly property real ph: root.curPage ? root.curPage.height : 1
                    readonly property real fit: Math.min((width - 24) / pw, (height - 24) / ph)
                    readonly property real s: fit * root.zoom
                    contentWidth: Math.max(width, pw * s + 24)
                    contentHeight: Math.max(height, ph * s + 24)
                    C.ScrollBar.vertical: C.ScrollBar { policy: viewer.contentHeight > viewer.height ? C.ScrollBar.AsNeeded : C.ScrollBar.AlwaysOff }
                    C.ScrollBar.horizontal: C.ScrollBar { policy: viewer.contentWidth > viewer.width ? C.ScrollBar.AsNeeded : C.ScrollBar.AlwaysOff }

                    function centreOn(r) {
                        if (!r) return
                        var cx = sheet.x + (r.x + r.w / 2) * sheet.width
                        var cy = sheet.y + (r.y + r.h / 2) * sheet.height
                        contentX = Math.max(0, Math.min(contentWidth - width, cx - width / 2))
                        contentY = Math.max(0, Math.min(contentHeight - height, cy - height / 2))
                    }

                    Rectangle {
                        id: sheet
                        x: Math.max(12, (viewer.width - width) / 2)
                        y: Math.max(12, (viewer.height - height) / 2)
                        width: viewer.pw * viewer.s
                        height: viewer.ph * viewer.s
                        color: "#FFFFFF"
                        border.width: 1
                        border.color: root.tk.border_strong
                        Txt {
                            anchors.centerIn: parent
                            visible: sheetImg.status === Image.Loading
                            text: "Drawing the overlay…"
                            tone: "faint"
                        }
                        Image {
                            id: sheetImg
                            anchors.fill: parent
                            source: root.curPage ? (root.curPage.overlayUrl || "") : ""
                            asynchronous: true
                            cache: false
                            smooth: true
                            mipmap: true
                            fillMode: Image.Stretch
                        }
                        Repeater {
                            model: root.regions
                            delegate: Rectangle {
                                required property var modelData
                                required property int index
                                readonly property bool on: index === root.regionIdx
                                x: modelData.x * sheet.width - 3
                                y: modelData.y * sheet.height - 3
                                width: modelData.w * sheet.width + 6
                                height: modelData.h * sheet.height + 6
                                color: "transparent"
                                radius: 3
                                border.width: on ? 2 : 1
                                border.color: root.tk.accent
                                opacity: on || root.regionIdx < 0 ? 1 : 0.55
                                Rectangle {
                                    x: -1
                                    y: -height - 2
                                    width: Math.max(18, num.implicitWidth + 8)
                                    height: 16
                                    radius: 3
                                    color: root.tk.accent
                                    Txt { id: num; anchors.centerIn: parent; text: modelData.n; role: "small"; tone: "onAccent"; figures: true }
                                }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.pickRegion(index) }
                            }
                        }
                    }
                }
            }

            // the changed regions
            Card {
                id: regionsCard
                x: pg.narrow ? 0 : parent.width - pdfView.sideW
                y: pg.narrow ? pdfView.viewH + 16 : 0
                width: pg.narrow ? parent.width : pdfView.sideW
                height: pg.narrow ? regCol.implicitHeight + 2 * pad : Math.max(pdfView.viewH, regCol.implicitHeight + 2 * pad)
                Column {
                    id: regCol
                    x: parent.pad
                    y: parent.pad
                    width: parent.width - 2 * parent.pad
                    spacing: 0
                    SectionHeading {
                        width: parent.width
                        title: root.curPage ? "Page " + (root.pageIdx + 1) : ""
                        facts: root.curPage ? root.pageLine(root.curPage) + " · " + root.curPage.size : ""
                    }
                    Item { width: 1; height: 8 }
                    Repeater {
                        model: root.regions
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            readonly property bool on: index === root.regionIdx
                            width: regCol.width
                            height: Math.max(48, regText.implicitHeight + 16)
                            radius: 6
                            color: on ? root.tk.surface_2 : regMouse.containsMouse ? root.tk.surface_2 : "transparent"
                            Rectangle {
                                id: badge
                                x: 6
                                y: 12
                                width: 22
                                height: 18
                                radius: 3
                                color: parent.on ? root.tk.accent : root.tk.surface_3
                                Txt { anchors.centerIn: parent; text: modelData.n; role: "small"; tone: parent.parent.on ? "onAccent" : "ink"; figures: true }
                            }
                            Column {
                                id: regText
                                anchors.left: badge.right
                                anchors.leftMargin: 10
                                anchors.right: parent.right
                                anchors.rightMargin: 6
                                y: 8
                                spacing: 2
                                Row {
                                    spacing: 6
                                    Rectangle {
                                        visible: modelData.kind !== "added"
                                        width: 8; height: 8; radius: 2; color: d.colours.removed
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    Rectangle {
                                        visible: modelData.kind !== "removed"
                                        width: 8; height: 8; radius: 2; color: d.colours.added
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    Txt { text: root.kindWord(modelData.kind); strong: true }
                                }
                                Txt {
                                    width: parent.width
                                    visible: text !== ""
                                    text: root.wordsLine(modelData.wordsAdded || [], modelData.wordsRemoved || [])
                                    role: "small"
                                    wrapMode: Text.Wrap
                                    maximumLineCount: 3
                                    elide: Text.ElideRight
                                }
                                Txt {
                                    width: parent.width
                                    text: "at " + modelData.mm[0] + ", " + modelData.mm[1] + " mm · " + modelData.mm[2] + " × " + modelData.mm[3] + " mm"
                                    role: "small"
                                    tone: "faint"
                                    figures: true
                                }
                            }
                            MouseArea { id: regMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: root.pickRegion(index) }
                            Accessible.role: Accessible.Button
                            Accessible.name: "Region " + modelData.n + ", " + root.kindWord(modelData.kind)
                        }
                    }
                    Txt {
                        width: parent.width
                        visible: root.curPage !== null && root.regions.length === 0
                        topPadding: 4
                        text: !root.curPage ? "" : root.curPage.status === "same" ? "No difference on this page."
                            : root.curPage.status === "added" ? "This page is only in the newer revision."
                            : root.curPage.status === "removed" ? "This page is only in the older revision."
                            : "Only text moved or changed; see the words below."
                        tone: "muted"
                        wrapMode: Text.Wrap
                        elide: Text.ElideNone
                    }
                    Item { width: 1; height: 12 }
                    Repeater {
                        model: root.curPage ? (root.curPage.notes || []) : []
                        delegate: Txt {
                            required property var modelData
                            width: regCol.width
                            text: modelData
                            role: "small"
                            tone: "faint"
                            figures: true
                            wrapMode: Text.Wrap
                            elide: Text.ElideNone
                        }
                    }
                }
            }
        }

        // ------------------------------------------------------------------ Excel: cells per sheet
        Card {
            id: xlsxCard
            visible: root.kind === "xlsx"
            width: parent.width
            height: visible ? xlsxCol.implicitHeight + 2 * pad : 0
            Column {
                id: xlsxCol
                x: parent.pad
                y: parent.pad
                width: parent.width - 2 * parent.pad
                spacing: 12
                Tabs {
                    width: parent.width
                    current: root.curSheet ? root.curSheet.name : ""
                    tabs: root.sheets.map(function (s) { return { key: s.name, text: s.name, count: s.count } })
                    onPicked: (key) => { root.sheetName = key; root.shownRows = 200 }
                }
                Txt {
                    width: parent.width
                    visible: root.curSheet !== null
                    text: !root.curSheet ? "" : root.curSheet.status === "added" ? "Sheet only in the newer revision"
                        : root.curSheet.status === "removed" ? "Sheet only in the older revision"
                        : root.curSheet.status === "same" ? "No cell differs on this sheet"
                        : [root.curSheet.changed ? root.curSheet.changed + " changed" : "",
                           root.curSheet.added ? root.curSheet.added + " added" : "",
                           root.curSheet.removed ? root.curSheet.removed + " removed" : "",
                           root.curSheet.rowsInserted ? (root.curSheet.rowsInserted === 1 ? "1 row inserted" : root.curSheet.rowsInserted + " rows inserted") : "",
                           root.curSheet.rowsDeleted ? (root.curSheet.rowsDeleted === 1 ? "1 row deleted" : root.curSheet.rowsDeleted + " rows deleted") : ""]
                          .filter(function (s) { return s !== "" }).join(" · ")
                    tone: "muted"
                    figures: true
                }
                Column {
                    id: xTable
                    width: parent.width
                    visible: root.curSheet !== null && root.curSheet.rows.length > 0
                    readonly property int cellW: 84
                    readonly property int kindW: 104
                    readonly property int valW: (width - cellW - kindW) / 2
                    Item {
                        width: parent.width
                        height: 28
                        Txt { width: xTable.cellW; text: "Cell"; role: "label"; anchors.verticalCenter: parent.verticalCenter }
                        Txt { x: xTable.cellW; text: "Change"; role: "label"; anchors.verticalCenter: parent.verticalCenter }
                        Txt { x: xTable.cellW + xTable.kindW; width: xTable.valW - 12; text: d.nameA; role: "label"; elide: Text.ElideMiddle; anchors.verticalCenter: parent.verticalCenter }
                        Txt { x: xTable.cellW + xTable.kindW + xTable.valW; width: xTable.valW; text: d.nameB; role: "label"; elide: Text.ElideMiddle; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Repeater {
                        model: root.curSheet ? root.curSheet.rows.slice(0, root.shownRows) : []
                        delegate: Item {
                            id: cellRow
                            required property var modelData
                            width: xTable.width
                            height: Math.max(44, oldCol.implicitHeight + 16, newCol.implicitHeight + 16)
                            Rectangle { width: parent.width; height: 1; color: root.tk.border }
                            Txt {
                                width: xTable.cellW - 8
                                text: modelData.cell + (modelData.oldCell !== "" && modelData.oldCell !== modelData.cell ? " ← " + modelData.oldCell : "")
                                figures: true
                                strong: true
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            StatusPill { x: xTable.cellW; anchors.verticalCenter: parent.verticalCenter; status: root.kindLevel(modelData.kind); label: root.changeWord(modelData.kind) }
                            Column {
                                id: oldCol
                                x: xTable.cellW + xTable.kindW
                                width: xTable.valW - 12
                                anchors.verticalCenter: parent.verticalCenter
                                Txt { width: parent.width; text: modelData.old !== "" ? modelData.old : modelData.kind === "added" ? "" : "(empty)"; tone: modelData.old !== "" ? "muted" : "faint"; figures: true; wrapMode: Text.Wrap; maximumLineCount: 3 }
                                Txt { width: parent.width; visible: modelData.oldFormula !== ""; text: modelData.oldFormula; role: "small"; tone: "faint"; elide: Text.ElideRight }
                            }
                            Column {
                                id: newCol
                                x: xTable.cellW + xTable.kindW + xTable.valW
                                width: xTable.valW
                                anchors.verticalCenter: parent.verticalCenter
                                Txt { width: parent.width; text: modelData.new !== "" ? modelData.new : modelData.kind === "removed" ? "" : "(empty)"; tone: modelData.new !== "" ? "ink" : "faint"; figures: true; wrapMode: Text.Wrap; maximumLineCount: 3 }
                                Txt { width: parent.width; visible: modelData.newFormula !== ""; text: modelData.newFormula; role: "small"; tone: "faint"; elide: Text.ElideRight }
                            }
                        }
                    }
                }
                ActionButton {
                    visible: root.curSheet !== null && root.curSheet.rows.length > root.shownRows
                    text: root.curSheet ? "Show all " + root.curSheet.rows.length : ""
                    kind: "link"
                    small: true
                    onClicked: root.shownRows = 100000
                }
                Txt {
                    visible: root.curSheet !== null && root.curSheet.more > 0
                    text: root.curSheet ? root.curSheet.more + " more changes not listed" : ""
                    role: "small"
                    tone: "faint"
                    figures: true
                }
            }
        }

        // ------------------------------------------------------------------ Word: paragraphs
        Card {
            id: docxCard
            visible: root.kind === "docx"
            width: parent.width
            height: visible ? docxCol.implicitHeight + 2 * pad : 0
            readonly property var rows: root.kind === "docx" ? (res.paragraphs || []) : []
            Column {
                id: docxCol
                x: parent.pad
                y: parent.pad
                width: parent.width - 2 * parent.pad
                readonly property int whereW: 180
                readonly property int kindW: 104
                Txt { visible: docxCard.rows.length === 0; text: "The text of both revisions is the same."; tone: "muted" }
                Item {
                    width: parent.width
                    height: 28
                    visible: docxCard.rows.length > 0
                    Txt { text: "Where"; role: "label"; anchors.verticalCenter: parent.verticalCenter }
                    Txt { x: docxCol.whereW; text: "Change"; role: "label"; anchors.verticalCenter: parent.verticalCenter }
                    Txt { x: docxCol.whereW + docxCol.kindW; text: "Text"; role: "label"; anchors.verticalCenter: parent.verticalCenter }
                }
                Repeater {
                    model: docxCard.rows.slice(0, root.shownRows)
                    delegate: Item {
                        required property var modelData
                        width: docxCol.width
                        height: Math.max(44, body.implicitHeight + 20)
                        Rectangle { width: parent.width; height: 1; color: root.tk.border }
                        Txt {
                            y: 12
                            width: docxCol.whereW - 12
                            text: modelData.where
                            role: "small"
                            tone: "muted"
                            figures: true
                            wrapMode: Text.Wrap
                            maximumLineCount: 2
                        }
                        StatusPill { x: docxCol.whereW; y: 12; status: root.kindLevel(modelData.kind); label: root.changeWord(modelData.kind) }
                        Text {
                            id: body
                            x: docxCol.whereW + docxCol.kindW
                            y: 10
                            width: docxCol.width - x
                            text: root.segmentsHtml(modelData.segments || [])
                            textFormat: Text.RichText
                            wrapMode: Text.Wrap
                            color: root.tk.text
                            font.family: root.tk.face
                            font.pixelSize: 13
                            lineHeight: 1.15
                        }
                    }
                }
                ActionButton {
                    visible: docxCard.rows.length > root.shownRows
                    text: "Show all " + docxCard.rows.length
                    kind: "link"
                    small: true
                    onClicked: root.shownRows = 100000
                }
            }
        }
    }

    // ---------------------------------------------------------------------- drop two revisions
    DropArea {
        anchors.fill: parent
        keys: ["text/uri-list"]
        onEntered: (drag) => { root.dragging = drag.hasUrls; drag.accepted = drag.hasUrls }
        onExited: root.dragging = false
        onDropped: (drop) => {
            root.dragging = false
            var urls = []
            for (var i = 0; i < drop.urls.length; i++) urls.push(String(drop.urls[i]))
            app.diff.dropped(urls)
            drop.accept()
        }
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: 12
        visible: root.dragging
        color: Qt.rgba(0, 0, 0, 0)
        radius: 10
        border.width: 2
        border.color: tk.accent
        Rectangle {
            anchors.centerIn: parent
            width: dropText.implicitWidth + 40
            height: 44
            radius: 22
            color: tk.surface
            border.width: 1
            border.color: tk.border_strong
            Txt {
                id: dropText
                anchors.centerIn: parent
                text: d.fileA !== "" && d.fileB === "" ? "Release to compare with " + d.nameA : "Release to compare these revisions"
                strong: true
            }
        }
    }
}
