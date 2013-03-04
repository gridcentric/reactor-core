//
// graph.js
//

var options = {
    lines: { show: true },
    points: { show: true },
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

function try_plot(elem, data) {

    if( elem.plot ) {
        elem.plot.setData(data);
        elem.plot.setupGrid();
        elem.plot.draw();

    } else if( elem.is(":visible") ) {
        elem.plot = $.plot(elem, data, options);
    }
}

function updateGraph(elem, path, data, metrics, callback) {
    function onData(result) {
        var timestamp = new Date();

        // Hit the callback.
        callback(result, timestamp, data, metrics);

        // Plot if the element is on screen.
        try_plot(elem, data);

        // Reschedule a callback if we're still open.
        if( isInDOM(elem) ) {
            setTimeout(function() {
                updateGraph(elem, path, data, metrics, callback);
            }, 5000);
        }
    }
    $.ajax({
        url: "/v1.0/" + path,
        type: 'GET',
        dataType: 'json',
        success: onData,
    });
}

function setupGraph(elem, path, callback) {
    var data = [];

    // Do an initial plot on screen.
    try_plot(elem, data);

    // Replot when a resize occurs.
    elem.resize(function() { elem.plot = false; try_plot(elem, data); });

    // Start the update cycle.
    updateGraph(elem, path, data, {}, callback);
}
