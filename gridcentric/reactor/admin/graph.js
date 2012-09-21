//
// graph.js
//

var options = {
    lines: { show: true },
    points: { show: true },
    xaxis: { show: false },
    yaxis: { show: true },
};

function updateGraph(elem, path, data, metrics, callback) {
    function onData(result) {
        var timestamp = new Date();
        callback(result, timestamp, data, metrics);
        if( elem.is(":visible") ) {
            $.plot(elem, data, options);
        }
        setTimeout(function() {
            updateGraph(elem, path, data, metrics, callback);
        }, 5000);
    }
    $.ajax({
        url: "/v1.0/" + path + "?auth_key=${auth_key}",
        type: 'GET',
        dataType: 'json',
        success: onData,
    });
}

function setupGraph(elem, path, callback) {
    var data = [];
    if( elem.is(":visible") ) {
        $.plot(elem, data, options);
    }
    updateGraph(elem, path, data, {}, callback);
}
