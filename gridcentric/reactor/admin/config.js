//
// config.js
//

function enableConfig(id, value, readonly) {
    if( value ) {
        $("#configValue-" + id).val(value);
    }
    if( !readonly ) {
        $("#configValue-" + id).removeAttr("disabled");
        $("#configSave-" + id).removeAttr("disabled");
    }
}

function disableConfig(id) {
    $("#configValue-" + id).attr("disabled", "disabled");
    $("#configSave-" + id).attr("disabled", "disabled");
}

function loadConfig(id, path, field, readonly) {
    $.ajax({
        url: "/v1.0/" + path + "?auth_key=${auth_key}",
        type: 'GET',
        dataType: 'json',
        success: function(result) {
            if( field ) {
                enableConfig(id, result[field], readonly);
            } else {
                enableConfig(id, JSON.stringify(result), readonly);
            }
        },
    });
}

function generateConfig(elem, id, name, textarea, readonly) {
    elem.html("");

    var saveButton = "";
    if( !readonly ) {
        saveButton = '                                                         \
            <input id="configSave-' + id + '" type="submit" value="Save"/>     \
            <div id="configPopup-' + id + '" class="popup">Saved.</div>';
    }

    if( textarea ) {
        elem.append('                                                          \
<div class="wrapper">                                                          \
    <form class="config" id="config-' + id + '">                               \
        <label>' + name + '</label>                                            \
        <textarea class="config"                                               \
                  id="configValue-' + id + '"                                  \
                  value=""/><br/>                                              \
        <div class="popupholder">' + saveButton + '</div>                      \
    </form>                                                                    \
</div>                                                                         \
');
    } else {
        elem.append('                                                          \
<form class="config" id="config-' + id + '">                                   \
    <label>' + name + '</label>                                                \
    <input id="configValue-' + id + '" value=""/>                              \
    ' + saveButton + '                                                         \
</form>                                                                        \
');
    }
}

function setupConfig(elem, name, textarea, path, field, readonly, noload, callback) {
    var id = randomId();
    generateConfig(elem, id, name, textarea, readonly);

    function reloadConfig() {
        if( !noload || readonly ) {
            disableConfig(id);
        }
        if( !noload ) {
            loadConfig(id, path, field, readonly);
        }
    }

    $("#config-" + id).submit(function(e) {
        e.preventDefault();
        var value = document.forms["config-" + id].elements[0].value;

        if( field ) {
            var data = {};
            data[field] = value;
            data = JSON.stringify(data);
        } else {
            var data = value;
        }

        $.ajax({
            url: "/v1.0/" + path + "?auth_key=${auth_key}",
            type: 'POST',
            dataType: 'json',
            data: data,
            processData: false,
            contentType: 'application/json',
            success: function() {
                $("#configPopup-" + id).show();
                $("#configPopup-" + id).fadeOut('slow');

                if( callback ) {
                    callback();
                }
                reloadConfig();
            },
        });
    });

    reloadConfig();
    $("#configPopup-" + id).hide();

    return reloadConfig;
}

function setupActions(elem, datamap, path, callback)
{
    elem.html("");

    $.each(datamap, function(name, value) {
        var id = randomId();
        elem.append('&nbsp;&nbsp;<a id="action-' + id + '" href="#">' + name + '</a>');

        $("#action-" + id).click(function(e) {
            e.preventDefault();

            $.ajax({
                url: "/v1.0/" + path + "?auth_key=${auth_key}",
                type: 'POST',
                dataType: 'json',
                data: JSON.stringify(value),
                processData: false,
                contentType: 'application/json',
                success: function() {
                    if( callback ) {
                        callback();
                    }
                },
            });
        });
    });
}
