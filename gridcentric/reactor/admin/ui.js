//
// ui.js
//

// This function is useful for generating unique identifiers
// for div and elements that are added to the page dynamically.
// (Generally once the divs are added, we track the elements
// in a javascript array -- so determinism is not so important).
function randomId() {
    var chars = 'abcdefghiklmnopqrstuvwxyz'.split('');
    var str = '';
    for( var i = 0; i < 8; i++ ) {
        str += chars[Math.floor(Math.random() * chars.length)];
    }
    return str;
}

// This object is used to store the global windows created
// as per above. It is initialized here so that it doesn't
// get reset over-and-over again.
var windows = {};

function windowOpen(object_type, name) {
    var key = object_type + "-" + name;
    if( !windows[key] ) {
        var objectDiv = object_type + "Window-" + randomId();
        $("#" + object_type + "Content").append("<div id='" + objectDiv + "' style='padding: 0;'/>");
        $("#" + objectDiv).kendoWindow({
            title: name,
            content: "/reactor/admin/" + object_type + ".html" +
                     "?auth_key=${auth_key}&" + object_type + "=" + name,
            actions: ["Minimize", "Close"],
            width: "500px",
            height: "339px",
            modal: false,
            resizable: false,
            draggable: true,
        });
        windows[key] = $("#" + objectDiv);
    } else {
        windows[key].data("kendoWindow").open();
    }
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

function setupTextSelect(object_type) {
    $("#" + object_type + "Text").submit(function(e) {
        e.preventDefault();
        var name = document.forms[object_type + "Text"].elements[0].value;
        windowOpen(object_type, name);
    });
}
function setupListSelect(object_type) {
    $("#" + object_type + "List").submit(function(e) {
        e.preventDefault();
        var name = document.forms[object_type + "List"].elements[0].value;
        windowOpen(object_type, name);
    });
}
function setupSelect(object_type) {
    $("#" + object_type + "AutoComplete").kendoAutoComplete({
        dataSource: dataSources[object_type],
    });
    $("#" + object_type + "DropDown").kendoDropDownList({
        dataSource: dataSources[object_type],
    });
    setupTextSelect(object_type);
    setupListSelect(object_type);
    $("#" + object_type + "ListButton").click(function() {
        toggleShowList(object_type);
    });
    $("#" + object_type + "TextButton").click(function () {
        toggleShowText(object_type);
    });
    toggleShowText(object_type);
}
