var scales = [ ' (n)', ' (u)', ' (m)', '', ' (K)', ' (M)', ' (G)' ];

function normalize(data, timestamp, last) {
    var count       = data["count"];
    var scale       = data["scale"];
    var delta_scale = 1.0;
    var scale_idx   = data["scale_idx"];
    var avg         = data["average"];

    // Grab the old scales.
    if( !count || !scale || !scale_idx ) {
        count = 0.0;
        scale = 1.0;
        scale_idx = 3;
    }
    last = last * scale;

    // Compute the new average.
    if( !avg ) {
        avg = 0.0;
    }
    avg = ((avg * count) + last) / (count + 1.0);
    data["average"] = avg;

    // Figure out the up scale.
    while( avg < 1 && avg > 0 ) {
        delta_scale = delta_scale * 1000;
        avg = avg * 1000;
        scale_idx -= 1;
    }

    // Figure out the down scale.
    while( avg > 1000 ) {
        delta_scale = delta_scale / 1000;
        avg = avg / 1000;
        scale_idx += 1;
    }

    // Apply uniformly.
    var normalized_data = [];
    $.each(data["data"], function(index, value) {
        if (value[1] == null)
            normalized_data.push([value[0], null]);
        else
            normalized_data.push([value[0], value[1] * delta_scale]);
    });

    // Push the new value.
    normalized_data.push([timestamp, last * delta_scale])

    data["data"]      = normalized_data;
    data["count"]     = Math.min(count + 1.0, normalized_data.length);
    data["average"]   = delta_scale * data["average"];
    data["scale"]     = delta_scale * scale;
    data["scale_idx"] = scale_idx;
    data["label"]     = data["name"] + scales[scale_idx];
}

// Number of timeslices to graph.
var NUM_TIMESLICES = 60;

// Tracked metrics.
var METRICS = {};
var NUM_METRICS = 0;

function initMetricData(metric, init_timestamp, color) {
    metric_data = {
        "name"  : metric,
        "data"  : [],
        "color" : color
    };

    // Initialize data
    for ( var i = 0; i < NUM_TIMESLICES; i++ ) {
        var ts = init_timestamp - ((NUM_TIMESLICES - i) * UPDATE_PERIOD);
        metric_data.data.push([ts , null]);
    }

    return metric_data;
}

function updateMetricData(metric_data, timestamp, value) {
    // Push the data and normalize
    normalize(metric_data, timestamp, value);

    // Limit the size
    while( metric_data.data.length > NUM_TIMESLICES ) {
        metric_data.data.shift();
    }
}

function graphMetrics(result) {
    if (!result) {
        result = {};
    }

    // Generate a timestamp
    var timestamp = new Date().getTime();

    // Loop through point-in-time metrics
    $.each(result, function(metric, value) {

        // If we haven't seen this metric,
        if (!(metric in METRICS)) {

            // Create a div for the graph and append it
            var outerDiv = $('#graph-templates .metric-graph-template').clone();
            outerDiv.find(".metric-graph-inner").attr("id", "livemetrics_" + metric);
            $("#metrics").append(outerDiv);

            // Set up the graph for it
            setupGraph($("#livemetrics_" + metric));

            // Add to map
            METRICS[metric] = initMetricData(metric, timestamp, NUM_METRICS + 1);
            NUM_METRICS++;
        }

        // Update metric data
        updateMetricData(METRICS[metric], timestamp, value);
    });

    // For each tracked metric,
    $.each(METRICS, function(metric, metric_data) {

        // If we didn't receive an update,
        if (!(metric in result)) {
            // Push a null value
            updateMetricData(metric_data, timestamp, null);
        }

        // Update metric graph.
        updateGraph($("#livemetrics_" + metric), [ metric_data ]);
    });
}
