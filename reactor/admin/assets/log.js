function addLogRow(table, ent) {
    var ts = new Date(ent[0] * 1000).toUTCString();
    switch (ent[1]) {
        case 'INFO':
            var sev = "<span class=\"label label-info\">Info</span>";
            break;
        case 'WARN':
            var sev = "<span class=\"label label-warning\">Warning</span>";
            break;
        case 'ERROR':
            var sev = "<span class=\"label label-error\">Error</span>";
            break;
        default:
            var sev = "<span class=\"label\">" + ent[1] + "</span>";
    }
    var tr = "<tr><td>" + ts + "</td><td>" + sev + "</td><td>" + ent[2] + "</td></tr>";
    $('#' + table + ' tr:first').after(tr);
}

function loadLog(url, div, table, since) {
    if (since == null)
        since = 0.0;

    $.ajax({
        url: url + "?since="+since,
        type: 'GET',
        dataType: 'json',
        success: function(log) {
            if (log.length > 0) {
                $.each(log, function(index, ent) {
                    addLogRow(table, ent);
                });
                since = log[log.length-1][0];
            }
            setTimeout(function() {
                loadLog(url, div, table, since);
            }, UPDATE_PERIOD);
        },
    });
}
