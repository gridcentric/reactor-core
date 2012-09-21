//
// config.js
//

function enableConfig(id, value) {
    if( value ) {
        $("#configValue-" + id).val(value);
    }
    $("#configSave-" + id).removeAttr("disabled");
}

function disableConfig(id) {
    $("#configSave-" + id).attr("disabled", "disabled");
}

function loadConfig(id, path, field) {
    $.ajax({
        url: "/v1.0/" + path + "?auth_key=${auth_key}",
        type: 'GET',
        dataType: 'json',
        success: function(result) {
            enableConfig(id, result[field]);
        },
    });
}

function generateConfig(elem, id, name) {
    if( !name ) {
        elem.append('                                                          \
<div class="wrapper">                                                          \
    <form class="config" id="config-' + id + '">                               \
        <textarea class="config"                                               \
                  id="configValue-' + id + '"                                  \
                  value=""/><br/>                                              \
        <div class="popupholder">                                              \
            <input id="configSave-' + id + '" type="submit" value="Save"/>     \
            <div id="configPopup-' + id + '" class="popup">Saved.</div>        \
        </div>                                                                 \
    </form>                                                                    \
</div>                                                                         \
');
    } else {
        elem.append('                                                          \
<form class="config" id="config-' + id + '">                                   \
    <label>' + name + '</label>                                                \
    <input id="configValue-' + id + '" value=""/>                              \
    <input id="configSave-' + id + '" type="submit" value="Save"/>             \
    <div id="configPopup-' + id + '" class="popup">Saved.</div>                \
</form>                                                                        \
');
    }
}

function setupConfig(elem, name, path, disabled, callback, field) {
    var id = randomId();
    generateConfig(elem, id, name);

    if( !field ) {
        field = path;
    }

    $("#config-" + id).submit(function(e) {
        e.preventDefault();
        var value = document.forms["config-" + id].elements[0].value;
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
                $("#configPopup-" + id).show();
                $("#configPopup-" + id).fadeOut('slow');
                if( disabled ) {
                    disableConfig(id);
                }
                if( callback ) {
                    callback();
                }
                loadConfig(id, path, field);
            },
        });
    });

    if( disabled ) {
        disableConfig(id);
    }

    loadConfig(id, path, field);
    $("#configPopup-" + id).hide();
}
