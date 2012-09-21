//
// ui.js
//

// This function is useful for generating unique identifiers
// for div and elements that are added to the page dynamically.
function randomId() {
    var chars = 'abcdefghiklmnopqrstuvwxyz'.split('');
    var str = '';
    for( var i = 0; i < 8; i++ ) {
        str += chars[Math.floor(Math.random() * chars.length)];
    }
    return str;
}

function windowOpen(object_type, name, cleanup) {
    var objectDiv = object_type + "Window-" + randomId();
    $("#" + object_type + "Content").append(
        "<div id='" + objectDiv + "' style='padding: 0;'/>");

    // Setup the cleanup functions.
    function on_close() {
        var elem = $("#" + objectDiv);
        elem.data("kendoWindow").destroy();
        elem.remove();
    }

    // Create and open the window.
    $("#" + objectDiv).kendoWindow({
         title: name,
         content: "/reactor/admin/" + object_type + ".html" +
                  "?auth_key=${auth_key}&" + object_type + "=" + name,
         actions: ["Maximize", "Close"],
         minWidth:  540,
         minHeight: 100,
         width:     540,
         height:    270,
         resizable: true,
         draggable: true,
         close: on_close,
    });
}

//
// DataSources.
// Used for managers and endpoints.
//

var dataSources = {};

function setupDataSource(name, path, field)
{
    if( dataSources[name] ) {
        return dataSources[name];
    }

    var source = new kendo.data.DataSource({
        transport: {
            read: {
                url: "/v1.0/" + path + "?auth_key=${auth_key}",
                dataType: "json",
            }
        },
        schema: {
            data: function(data) {
                return data[field]
            }
        }
    });

    dataSources[name] = source;
    return dataSources[name];
}

//
// List / Text search buttons.
// Used for managers and endpoints.
//

function toggleShowList(object_type) {
    $("#" + object_type + "ListButton").addClass('disabled');
    $("#" + object_type + "TextButton").removeClass('disabled');
    $("#" + object_type + "Text").hide();
    $("#" + object_type + "List").show();
}
function toggleShowText(object_type) {
    $("#" + object_type + "ListButton").removeClass('disabled');
    $("#" + object_type + "TextButton").addClass('disabled');
    $("#" + object_type + "Text").show();
    $("#" + object_type + "List").hide();
}

function setupTextSelect(object_type, cleanup) {
    $("#" + object_type + "Text").submit(function(e) {
        e.preventDefault();
        var name = document.forms[object_type + "Text"].elements[0].value;
        windowOpen(object_type, name, cleanup);
    });
}

function setupListSelect(object_type, cleanup) {
    $("#" + object_type + "List").submit(function(e) {
        e.preventDefault();
        var name = document.forms[object_type + "List"].elements[0].value;
        windowOpen(object_type, name, cleanup);
    });
}

function generateSelect(object_type, elem) {
    elem.append('                                                           \
<div class="wrapper">                                                       \
    <form id="' + object_type + 'Text">                                     \
        <input id="' + object_type + 'managerAutoComplete"/>                \
        <input type="submit" value="Open">                                  \
    </form>                                                                 \
    <form id="' + object_type + 'List">                                     \
        <select id="' + object_type + 'DropDown"/>                          \
        <input type="submit" value="Open">                                  \
    </form>                                                                 \
    <center>                                                                \
        <a href="#" id="' + object_type + 'ListButton">List</a>             \
        &nbsp;|&nbsp;                                                       \
        <a href="#" id="' + object_type + 'TextButton">Find or Create</a>   \
    </center>                                                               \
</div>                                                                      \
<div id="' + object_type + 'Content"></div>                                 \
');
}

function setupSelect(object_type, elem, cleanup) {
    generateSelect(object_type, elem);

    $("#" + object_type + "AutoComplete").kendoAutoComplete({
        dataSource: dataSources[object_type],
    });
    $("#" + object_type + "DropDown").kendoDropDownList({
        dataSource: dataSources[object_type],
    });

    setupTextSelect(object_type, cleanup);
    setupListSelect(object_type, cleanup);

    $("#" + object_type + "ListButton").click(function() {
        toggleShowList(object_type);
    });
    $("#" + object_type + "TextButton").click(function () {
        toggleShowText(object_type);
    });

    toggleShowList(object_type);
}
