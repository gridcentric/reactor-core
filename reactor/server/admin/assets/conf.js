function beginMakeConfig(container_id, name_map, spec_path, save_path, template) {
    var context = new Object();
    context["container_id"] = container_id;
    context["name_map"] = name_map;
    context["spec_path"] = spec_path;
    context["save_path"] = save_path;

    // Setup the prompt modal first so we can immediately begin using it to
    // report errors during setup back to the user.
    constructPrompt(context, $("#" + container_id));

    // Begin ajax request to fetch template from backend and populate the config
    // form. If the backend fails to respond with a template, we'll try to fall
    // back to the template provided to us by the 'template' argument. If these
    // both fail, we throw up a generic error message and leave the form in a
    // reasonable state.
    fetchConfig(context, template);
}

function fetchConfig(context, template) {
    $.ajax({
        url: context["spec_path"],
        type: "GET",
        dataType: "json",
        error: function(req, error, htmlError) {
            $("div#" + context["container_id"] + " > div")
                .attr("class", "alert alert-error")
                .html("<strong>Error:</strong> Couldn't fetch configuration format.");

            if (typeof(template) !== "undefined") {
                // Create a deep copy of the template object given to us, just in case the
                // caller modifies it later. We store references and page stage in the
                // template and can't handle the template unexpectedly chaning from
                // underneath us.
                promptSetHeader(context, "Falling back to built-in format");
                promptSetBody(context, "Couldn't fetch the configuration format from reactor. " +
                             "Falling back to built-in format.");
                context["template"] = $.extend(true, {}, template);
                makeConfig(context);
            } else {
                promptSetHeader(context, "Configuration populate failed");
                promptSetBody(context, "Couldn't fetch the configuration format from reactor.");
            }

            promptDisplay(context);

        },
        success: function(result) {
            fetchValues(context, result);
        }
    });
}

function fetchValues(context, template) {
    $.ajax({
        url: context["save_path"],
        type: "GET",
        dataType: "json",
        error: function(req, error, htmlError) {
        },
        success: function(result) {
            mergeConfig(context, template, result);
            context["template"] = template;
            makeConfig(context);
        }
    });
}

function mergeConfig(context, template, values) {
    $.each(values, function(section, params) {
        if (section in template) {
            $.each(params, function(key, value) {
                if (key in template[section])
                    template[section][key]["value"] = value;
                else
                    console.error("Key '" + key + "' is present in the current config, but not in the spec.");
            });
        } else {
            // This is benign, some sections aren't configurable.
            console.debug("Section '" + section + "' is present in the current config, but not in the spec.");
        }
    });
    return template;
}

function makeConfig(context) {
    var template = context["template"];

    // We internally work with jquery objects instead of DOM elements.
    var container_elt = $("#" + context["container_id"]);

    // Start with a clean slate, unlink subtree from container_elt.
    container_elt.children().remove();

    // Walk through template and mark all fields as unmodified. This guards
    // against the edge case where we're passed in the same template object to
    // multiple calls to this function. Note that it's quite possible for the
    // modified attribute to be undefined, in which case we simply leave it
    // undefined.
    function markUnmodified(root_node) {
        $.each(root_node, function(key, value) {
            // Filter out nodes we don't want to recurse into. These include
            // arrays, pointers to the DOM elements we stash in the template and
            // leaf values.
            if (key === "ref" ||
                typeof(value) !== "object" ||
                value instanceof Array || value === null)
                return true;

            if ("modified" in value)
                value["modified"] = false;

            if ("skip-init" in value)
                value["skip-init"] = false;

            markUnmodified(value);
        });
    }

    markUnmodified(template);

    // Construct sub templates.
    var sub_template_set = new Object();
    $.each(template, function(section_name, section) {
        if (contains(section_name, ":")) {
            sub_template_set[section_name.split(":")[0]] =
                sub_template_set[section_name.split(":")[0]] + 1 || 1;
        }
    });
    var sub_template_list = Object.keys(sub_template_set);

    context["sub_templates"] = new Object();
    $.each(sub_template_list, function(idx, sub_template_name) {
        context["sub_templates"][sub_template_name] = new Object();
        $.each(template, function(section_name, section) {
            if (startsWith(section_name, sub_template_name + ":"))
                context["sub_templates"][sub_template_name][section_name.split(":")[1]] = section;
        });
    });

    // Build toplevel sections list.
    context["toplevel_sections"] = new Array();
    $.each(template, function(section_name, section) {
        if (!contains(section_name, ":"))
            context["toplevel_sections"].push(section_name);
    });

    // Add subconfig names as toplevel sections.
    context["toplevel_sections"].push.apply(context["toplevel_sections"],
                                            Object.keys(context["sub_templates"]));

    // Build toplevel scaffolding.
    context["toplevel_folds"] = constructScaffolding(context,
                                                     container_elt,
                                                     context["toplevel_sections"],
                                                     true,
                                                     false);

    // Build sub template scaffolding.
    context["nested_folds"] = new Object();
    $.each(context["sub_templates"], function(sub_template_name, sub_template) {
        context["nested_folds"][sub_template_name] =
            constructScaffolding(context,
                                 context["toplevel_folds"][sub_template_name],
                                 Object.keys(sub_template),
                                 true,
                                 true);
    });

    // Populate toplevel config.
    $.each(template, function(section_name, section) {
        if ($.inArray(section_name, context["toplevel_sections"]) !== -1)
            generateTemplate(context["toplevel_folds"][section_name],
                             section_name,
                             section);
    });

    // Populate sub template configs.
    $.each(context["sub_templates"], function(sub_template_name, sub_template) {
        $.each(sub_template, function(section_name, section) {
            generateTemplate(context["nested_folds"][sub_template_name][section_name],
                             section_name,
                             section);
        });
    });

    var button_grp = $("<div/>").attr("class", "btn-toolbar").appendTo(container_elt);

    // Construct config save button.
    $("<div/>").attr("class", "btn-group").append(
        $("<a>Save</a>")
            .attr({
                "id": "config-save",
                "class": "btn btn-primary",
                "role": "button"
            })
            .click(function() {
                postConfig(context, context["save_path"]);
            })).appendTo(button_grp);

    // Construct config reset button.
    $("<div/>").attr("class", "btn-group").append(
        $("<a>Reset</a>")
            .attr({
                "id": "config-reset",
                "class": "btn btn-primary",
                "role": "button"
            })
            .click(function() {
                makeConfig(context);
            })).appendTo(button_grp);

    return context;
}

function readConfig(context) {
    var template = context["template"];
    var sub_templates = context["sub_templates"];
    var toplevel_sections = context["toplevel_sections"];

    // If 'obj' does not have the property 'attr', initialize 'attr' with 'initval'.
    function touch(obj, attr, initval) {
        if (!(attr in obj))
            obj[attr] = initval;
        return obj[attr];
    }

    function intern_section(result, section_name, section) {
        $.each(section, function(config_name, config) {
            if (config["modified"]) {
                var val;
                switch (config["type"]) {
                case "boolean":
                    val = config["ref"].prop("checked");
                    break;
                case "list":
                    val = config["ref"].val().split("\n").filter(function(elt, idx, arr) {
                        return $.trim(elt).length > 0;
                    });
                    break;
                default:
                    val = config["ref"].val();
                }
                touch(result, section_name, {})[config_name] = val;
            }
        });
    }

    var repr = new Object();

    // Grab values from toplevel sections.
    $.each(template, function(section_name, section) {
        if ($.inArray(section_name, toplevel_sections) !== -1)
            intern_section(repr, section_name, section);
    });

    // Grab values from sub sections.
    $.each(sub_templates, function(template_name, sub_template) {
        $.each(sub_template, function(sub_section_name, sub_section) {
            intern_section(repr, template_name + ":" + sub_section_name, sub_section);
        });
    });

    console.debug(JSON.stringify(repr));
    return repr;
}

function postConfig(context, post_url) {
    var posting = constructPromptLabel(context, "begin-saving-label",
                                       "Saving", "Pushing configuration to reactor.",
                                       "info").show(200).delay(1500);
    $.ajax({
        url: post_url,
        type: "POST",
        data: JSON.stringify(readConfig(context)),
        contentType: "application/json",
        success: function() {
            constructPromptLabel(context, "done-saving-label",
                                 "Success", "New configuration saved.",
                                 "success").show(200).delay(2300).hide(400);
        },
        error: function(req, error, htmlError) {
            promptSetHeader(context, "Config update failed");
            promptSetBody(context, "The request to update the config " +
                          "terminated due to a(n) " + error + ":" + htmlError + ".");
            promptDisplay(context);
        },
        complete: function() {
            posting.hide(400);
        }
    });
}

function constructPromptLabel(context, id, topic, message, type) {
    root = $("#" + context["container_id"]);

    // Remove old prompts for this class.
    root.find("#" + id).remove();

    var label = $("<div/>").attr({
        "class": "alert alert-" + type,
        "id": id,
        "style": "display:none"
    }).appendTo(root);

    label.html("<strong>" + topic + ":</strong> " + message);

    $("<button/>").attr({
        "type": "button",
        "class": "close",
        "data-dismiss": "alert"
    }).html("&times;").appendTo(label);

    return label;
}

function constructPrompt(context, root) {
    if (context["prompt_modal"])
        return;

    var modal_div = $("<div/>").attr({
        "id": "prompt-modal",
        "class": "modal hide fade",
        "tabindex": -1,
        "role": "dialog",
        "aria-labelledby": "prompt-modal-label",
        "aria-hidden": true
    }).appendTo(root.parent());

    var modal_header = $("<div/>").attr("class", "modal-header").appendTo(modal_div)
        .append($("<button>×</button>")
                .attr({
                    "type": "button",
                    "class": "close",
                    "data-dismiss": "modal",
                    "aria-hidden": true
                }))
        .append($("<h3>Prompt header</h3>")
                .attr("id", "prompt-modal-label"));

    var modal_body = $("<div/>").attr({
        "class": "modal-body",
        "id": "prompt-modal-body"
    }).appendTo(modal_div)
        .append("<p>Prompt message</p>");

    var modal_footer = $("<div/>").attr("class", "modal-footer").appendTo(modal_div)
        .append($("<button>Close</button>").attr({
            "class": "btn",
            "data-dismiss": "modal",
            "aria-hidden": true
        }));

    context["prompt_modal"] = modal_div;
}

function promptDisplay(context) {
    context["prompt_modal"].modal('show');
}

function promptSetHeader(context, content) {
    context["prompt_modal"].find("#prompt-modal-label").html(content);
}

function promptSetBody(context, content) {
    context["prompt_modal"].find("#prompt-modal-body > p").html(content);
}

function constructScaffolding(context, root, sections, exclusive, open) {
    var folds = new Object();

    var top = $("<div/>").attr({
        "class": "accordion",
        "id": "fold-toplevel-" + root.attr("id")
    }).appendTo(root);

    $.each(sections, function(idx, section) {
        var group = $("<div/>").attr("class", "accordion-group").appendTo(top);
        var acd_heading = $("<div/>").attr("class", "accordion-heading").appendTo(group);
        var acd_toggle = $("<a/>").attr({
            "class": "accordion-toggle",
            "data-toggle": "collapse",
            "href": "#fold-" + section
        }).html(capitalize(context["name_map"][section] || section)).appendTo(acd_heading);

        if (exclusive)
            acd_toggle.attr("data-parent", "#fold-toplevel-" + root.attr("id"));

        var acd_body = $("<div/>").attr("id", "fold-" + section).appendTo(group);
        if (open) {
            acd_body.attr("class", "accordion-body collapse in");
            open = false;
        } else {
            acd_body.attr("class", "accordion-body collapse");
        }

        var acd_inner = $("<div/>").attr({
            "class": "accordion-inner",
            "id": "fold-nested-" + section
        }).appendTo(acd_body);

        folds[section] = acd_inner;
    });

    return folds;
}

// Generates a config section based on the description provided by the
// 'template' object, rooted at the div 'root'.
function generateTemplate(root, name, template) {
    // Get rid of any old elements to prevent duplicates.
    root.find("form#form-" + name).remove();
    var fs = $("<fieldset/>")
        .appendTo(
            $("<form/>").attr("class", "form-inline").appendTo(root));

    // Sort using the 'order' key so that all the config params show
    // up in a consistent order.
    var configs = new Array();
    $.each(template, function(config_name, config) {
        configs.push([ config_name, config ]);
    });

    configs.sort(function(a, b) {
        order_a = a[1]["order"] || 0;
        order_b = b[1]["order"] || 0;
        name_a = a[0];
        name_b = b[0];

        if (order_a === order_b)
            return name_a > name_b ? 1 : -1;
        else
            return order_a > order_b ? 1 : -1;
    });

    $.each(configs, function(idx, config) {
        generateSingleConfig(fs, config[0], config[1]);
    });
}

function generateSingleConfig(root, config_name, config)
{
    function attachTooltip(elt, config, trigger, hide_delay) {
        if (typeof(trigger) === "undefined") trigger = "hover click";
        if (typeof(hide_delay) === "undefined") hide_delay = 50;

        elt.tooltip({ "title": config["description"]
                                   .replace("<", "&lt;")
                                   .replace(">", "&gt;"),
                      "placement": "right",
                      "trigger": trigger,
                      "delay": { "show" : 0, "hide": hide_delay }
                    });

        config["skip-init"]["tooltip"] = true;
    }

    function buildConfigSlot(root, name) {
        var cgroup = $("<div/>").attr("class", "control-group").appendTo(root)
            .append($("<label/>").attr("class", "control-label")
                    .html(name.replace("_", " ")));

        return $("<div/>").attr("class", "controls").appendTo(cgroup);
    }

    config["skip-init"] = new Object();
    var input_elt = null;

    // Setup the generic scaffolding for a config variable.
    var slot = buildConfigSlot(root, config_name);

    // Perform any type-specific setup for the variable.
    switch (config["type"]) {
    case "list":
        input_elt = $("<textarea/>").attr("rows", 5).appendTo(slot);
        if ("value" in config)
            input_elt.html(config["value"]);
        config["skip-init"]["value"] = true;
        break;
    case "choice":
    case "multichoice":
        input_elt = $("<select/>").appendTo(slot);
        $.each(config["options"], function(idx, choice) {
            input_elt.append($("<option/>").html(choice));
        });
        if (config["type"] === "multichoice")
            input_elt.attr("multiple", "multiple");
        config["skip-init"]["value"] = true;
        break;
    case "string":
        input_elt = $("<input/>")
            .attr({
                "class": "input-large",
                "type": "text"
            })
            .appendTo(slot);
        if (contains(config_name.toLowerCase(), "password"))
            input_elt.attr("type", "password");
        break;
    case "integer":
        input_elt = $("<input/>")
            .attr({
                "class": "input-large",
                "type": "number",
                "min": 0
            })
            .appendTo(slot);
        break;
    case "boolean":
        input_elt = $("<input/>")
            .attr("type", "checkbox")
            .prop("checked", config["value"])
            .appendTo(
                $("<label/>").attr("class", "checkbox").appendTo(slot));

        attachTooltip(input_elt, config, "hover", 750);
        break;
    default:
        // Error.
        input_elt = null;
    }

    // Perform any remaining init common to all variables.
    if (input_elt) {
        // Set the initialize value for the input field if it's not already set.
        if (!config["skip-init"]["value"]) {
            if ("default" in config)
                input_elt.attr("placeholder", config["default"]);

            if ("value" in config)
                input_elt.attr("value", config["value"]);

            config["skip-init"]["value"] = true;
        }

        // Attach tooltip.
        if (!config["skip-init"]["tooltip"])
            attachTooltip(input_elt, config);

        // Register an onchange callback to mark field as modified on change.
        input_elt.change(function() { config["modified"] = true; });

        // Save reference to HTML element in config template.
        config["ref"] = input_elt;
    }
}

function contains(str, search_str) {
    return (str.search(search_str) !== -1);
}

function startsWith(str, prefix) {
    return str.indexOf(prefix) === 0;
}

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}
