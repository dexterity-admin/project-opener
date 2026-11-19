import QtQuick

// The Rise entrance (docs/DESIGN.md "Motion"), once per page arrival, never on a data refresh: the block's
// `arrive` goes 0 to 1 over 650 ms after `index` x 60 ms.  The block maps it to its opacity and to a 12 px rise
// (rich; purposeful fades only).  Off: arrives at once.  finish() completes it now (the dock opening).
SequentialAnimation {
    id: rise
    property QtObject target
    property int index: 0
    PauseAnimation { duration: Math.round(rise.index * 60 * app.ui.k) }
    NumberAnimation {
        target: rise.target
        property: "arrive"
        from: 0
        to: 1
        duration: Math.round(650 * app.ui.k)
        easing.type: Easing.Bezier
        easing.bezierCurve: [0.2, 0.7, 0.2, 1, 1, 1]
    }
    function begin() {
        if (app.ui.k <= 0) { target.arrive = 1; return }
        target.arrive = 0
        start()
    }
    function finish() { if (running) complete() }
}
