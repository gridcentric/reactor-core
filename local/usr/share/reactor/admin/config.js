//
// config.js
//

function enableConfig(edit, save, value) {
    if( value ) {
        $("#" + edit).val(value);
    }
    $("#" + save).removeAttr("disabled");
}
function disableConfig(edit, save) {
    $("#" + save).attr("disabled", "disabled");
}
function loadConfig(edit, save, path, field) {
    $.ajax({
        url: "/v1.0/" + path + "?auth_key=${auth_key}",
        type: 'GET',
        dataType: 'json',
        success: function(result) {
            enableConfig(edit, save, result[field]);
        },
    });
}

function setupConfig(form, edit, save, popup, path, disabled, callback, field) {
    if( !field ) {
        field = path;
    }

    $("#" + form).submit(function(e) {
        e.preventDefault();
        var value = document.forms[form].elements[0].value;
        var data = {};
        data[field] = value;
        $.ajax({
            url: "/v1.0/" + path + "?auth_key=${auth_key}",
            type: 'POST',
            dataType: 'json',
            data: JSON.stringify(data),
            processData: false,
            contentType: 'application/json',
            success: function() {
                $("#" + popup).show();
                $("#" + popup).fadeOut('slow');
                if( disabled ) {
                    disableConfig(edit, save);
                }
                if( callback ) {
                    callback();
                }
                loadConfig(edit, save, path, field);
            },
        });
    });

    if( disabled ) {
        disableConfig(edit, save);
    }
    loadConfig(edit, save, path, field);
    $("#" + popup).hide();
}
