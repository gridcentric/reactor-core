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

    } else if( elem.is(":visible") ) {
        elem.plot = $.plot(elem, data, options);
    }

    return isInDOM(elem);
}

function autoUpdateGraph(elem, path, data, metrics, callback, period) {
    function onData(result) {
        var timestamp = new Date().getTime();

        // Hit the callback.
        callback(result, timestamp, data, metrics);

        // Plot if the element is on screen.
        if (updateGraph(elem, data)) {
            setTimeout(function() {
                autoUpdateGraph(elem, path, data, metrics, callback, period);
            }, period);
        }
    }
    $.ajax({
        url: "/v1.1/" + path,
        type: 'GET',
        dataType: 'json',
        success: onData,
    });
}

function setupGraph(elem, path, callback, period) {
    var data = [];

    // Do an initial plot on screen.
    updateGraph(elem, data);

    // Replot when a resize occurs.
    elem.resize(function() { elem.plot = false; updateGraph(elem, data); });

    // Start the update cycle.
    if (path !== null)
        autoUpdateGraph(elem, path, data, {}, callback, period);
}
