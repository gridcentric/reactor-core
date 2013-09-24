//
// graph.js
//

var options = {
    lines: { show: true, fill: 0.5 },
    points: { show: false },
    xaxis: { show: false },
    yaxis: { show: true, ticks: 10, min: 0 },
    grid: { backgroundColor: { colors: ["#fff", "#eee"] } }
};

function isInDOM(elem) {
    if( !elem.closest('html').length ) {
        return false;
    } else {
        return true;
    }
}

function updateGraph(elem, data) {
    if( elem.plot ) {
        elem.plot.setData(data);
        elem.plot.setupGrid();
        elem.plot.draw();
    } else if( isInDOM(elem) && elem.is(":visible") ) {
        elem.plot = $.plot(elem, data, options);
    }
}

function setupGraph(elem) {
    var data = [];

    // Do an initial plot on screen.
    updateGraph(elem, data);

    // Replot when a resize occurs.
    elem.resize(function() { elem.plot = false; updateGraph(elem, data); });
}
