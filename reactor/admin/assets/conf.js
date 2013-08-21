function beginMakeConfig(container_id, name_map, spec_path, save_path) {
    var context = new Object();
    context["container_id"] = container_id;
    context["name_map"] = name_map;
    context["spec_path"] = spec_path;
    context["save_path"] = save_path;

    // Begin ajax request to fetch spec from backend and populate the config
    // form.
    fetchConfig(context);
}

function fetchConfig(context) {
    $.ajax({
        url: context["spec_path"],
        type: "GET",
        dataType: "json",
        error: function(req, error, htmlError) {
            $("div#" + context["container_id"] + " > div")
                .attr("class", "alert alert-error")
                .html("<strong>Error:</strong> Couldn't fetch configuration format.");
            $("#prompt-modal").find("#prompt-modal-label")
                .html("Configuration populate failed");
            $("#prompt-modal").find("#prompt-modal-body")
                .html("Couldn't fetch the configuration format from reactor.");
            $("#prompt-modal").modal("show");
        },
        success: function(result) {
            fetchValues(context, result);
        }
    });
}

function getConfigTemplate(config) {
    if ("endpoint" in config && "template" in config["endpoint"]) {
        return config.endpoint.template;
    }

    return null;
}

function fetchValues(context, spec) {
    $.ajax({
        url: context["save_path"],
        type: "GET",
        dataType: "json",
        error: function(req, error, htmlError) {
        },
        success: function(result) {
            template_name = getConfigTemplate(result);
            if (template_name &&
                template_name in ENDPOINT_TEMPLATES) {
                makeTemplateConfig(context, spec, result,
                    ENDPOINT_TEMPLATES[template_name]);
            } else {
                makeCustomConfig(context, spec, result);
            }
        }
    });
}

// Make a config without a template.
function makeCustomConfig(context, spec, values) {
    mergeConfig(context, spec, values);
    makeConfig(context);
}

// Make a config with a template.
function makeTemplateConfig(context, spec, values, template) {
    spec.template = template;
    $.each(template.components, function(index, section) {
        if (section.name && section.description) {
            context.name_map[section.name] = section.description;
        }
    });
    mergeConfig(context, spec, values);
    makeConfig(context);
}

function templateItemToConfig(item) {
    var secdiv = item.lastIndexOf(":");
    var section = item.slice(0, secdiv);
    var key = item.slice(secdiv + 1);
    return [ section, key ];
}

function mergeConfig(context, spec, values) {
    // First fill in from template, if present.
    if (spec.template != null) {
        $.each(spec.template.components, function(index, section) {
            $.each(section.items, function(index, item) {
                if (item.default != null) {
                    var path = templateItemToConfig(item.item);
                    var spec_section = path[0];
                    var key = path[1];
                    if (!(key in spec[spec_section]))
                        spec[spec_section][key] = Object();
                    spec[spec_section][key]["value"] = item.default;
                    if (section.name == null) {
                        spec[spec_section][key]["present"] = true;
                        spec[spec_section][key]["type"] = "hidden";
                    }
                }
            });
        });
    }

    // Then fill in from config values.
    $.each(values, function(section, params) {
        if (section in spec) {
            $.each(params, function(key, value) {
                if (key in spec[section])
                    spec[section][key]["value"] = value;
                else
                    console.error("Key '" + key + "' is present in the current config, but not in the spec.");
            });
        } else {
            // This is benign, some sections aren't configurable.
            console.debug("Section '" + section + "' is present in the current config, but not in the spec.");
        }
    });
    context["spec"] = spec;
}

function makeConfig(context) {
    var spec = context["spec"];

    // We internally work with jquery objects instead of DOM elements.
    var container_elt = $("#" + context["container_id"]);

    // Start with a clean slate, unlink subtree from container_elt.
    container_elt.children().remove();

    // Walk through spec and mark all fields as unmodified. This guards
    // against the edge case where we're passed in the same spec object to
    // multiple calls to this function. Note that it's quite possible for the
    // modified attribute to be undefined, in which case we simply leave it
    // undefined.
    function markUnmodified(root_node) {
        $.each(root_node, function(key, value) {
            // Filter out nodes we don't want to recurse into. These include
            // arrays, pointers to the DOM elements we stash in the spec and
            // leaf values.
            if (key === "ref" ||
                key === "header" ||
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

    markUnmodified(spec);

    // Construct sub specs.
    var sub_spec_set = new Object();
    $.each(spec, function(section_name, section) {
        if (contains(section_name, ":")) {
            sub_spec_set[section_name.split(":")[0]] =
                sub_spec_set[section_name.split(":")[0]] + 1 || 1;
        }
    });
    var sub_spec_list = Object.keys(sub_spec_set);

    context["sub_specs"] = new Object();
    $.each(sub_spec_list, function(idx, sub_spec_name) {
        context["sub_specs"][sub_spec_name] = new Object();
        $.each(spec, function(section_name, section) {
            if (startsWith(section_name, sub_spec_name + ":"))
                context["sub_specs"][sub_spec_name][section_name.split(":")[1]] = section;
        });
    });

    // Build toplevel sections list.
    context["toplevel_sections"] = new Array();
    $.each(spec, function(section_name, section) {
        if (!contains(section_name, ":"))
            context["toplevel_sections"].push(section_name);
    });

    // Add subconfig names as toplevel sections.
    context["toplevel_sections"].push.apply(context["toplevel_sections"],
                                            Object.keys(context["sub_specs"]));

    if (spec.template != null) {
        // Construct the scaffolding for the form.
        sections = $.map(spec.template.components, function(section, index) {
            return section.name;
        });
        context["toplevel_folds"] = constructScaffolding(context,
                                        container_elt, sections, false, false);
        $.each(spec.template.components, function(index, section) {
            if (section.name != null) {
                // Construct the section.
                generateSection(context["toplevel_folds"][section.name],
                                section.name, spec, section);

                // Generate backlinks to section headers.
                $.each(section.items, function(index, item) {
                    path = templateItemToConfig(item.item);
                    section_name = path[0];
                    config = path[1];
                    spec[section_name][config].header = section.name;
                });
            }
        });
    } else {
        // Build toplevel scaffolding.
        context["toplevel_folds"] = constructScaffolding(context,
                                                         container_elt,
                                                         context["toplevel_sections"],
                                                         false,
                                                         false);

        // Build sub spec scaffolding.
        context["nested_folds"] = new Object();
        $.each(context["sub_specs"], function(sub_spec_name, sub_spec) {
            context["nested_folds"][sub_spec_name] =
                constructScaffolding(context,
                                     context["toplevel_folds"][sub_spec_name],
                                     Object.keys(sub_spec),
                                     false,
                                     true);
        });

        // Populate toplevel config.
        $.each(spec, function(section_name, section) {
            if ($.inArray(section_name, context["toplevel_sections"]) !== -1)
                generateSection(context["toplevel_folds"][section_name],
                                 section_name,
                                 section);
        });

        // Populate sub spec configs.
        $.each(context["sub_specs"], function(sub_spec_name, sub_spec) {
            $.each(sub_spec, function(section_name, section) {
                generateSection(context["nested_folds"][sub_spec_name][section_name],
                                 section_name,
                                 section);
            });
        });
    }

    context["save_task"] = function() {
        disableButtons(context);
        postConfig(context, context["save_path"]);
    }
    context["reset_task"] = function() {
        disableButtons(context);
        $("#prompt-label").clearQueue().fadeTo(400, 0);
        makeConfig(context);
    }

    enableButtons(context);

    // Enable custom CSS that needs to be run post-construction
    enableChosen();

    return context;
}

function readConfig(context) {
    var spec = context["spec"];
    var sub_specs = context["sub_specs"];
    var toplevel_sections = context["toplevel_sections"];

    // If 'obj' does not have the property 'attr', initialize 'attr' with 'initval'.
    function touch(obj, attr, initval) {
        if (!(attr in obj))
            obj[attr] = initval;
        return obj[attr];
    }

    function intern_section(result, section_name, section) {
        $.each(section, function(config_name, config) {
            var val;
            var include = true;

            if (!(config["present"] || config["modified"])) {
                return true;
            }

            switch (config["type"]) {
            case "boolean":
                val = config["ref"].prop("checked");
                break;
            case "list":
                val = config["ref"].val().split("\n").filter(
                    function(elt, idx, arr) {
                        return $.trim(elt).length > 0;
                    });
                include = (val.length !== 0);
                break;
            case "hidden":
                val = config["value"];
                break;
            default:
                val = config["ref"].val();
                include = (val.length !== 0);
            }
            if (include)
                touch(result, section_name, {})[config_name] = val;
        });
    }

    var repr = new Object();

    // Grab values from toplevel sections.
    $.each(spec, function(section_name, section) {
        if ($.inArray(section_name, toplevel_sections) !== -1)
            intern_section(repr, section_name, section);
    });

    // Grab values from sub sections.
    $.each(sub_specs, function(spec_name, sub_spec) {
        $.each(sub_spec, function(sub_section_name, sub_section) {
            intern_section(repr, spec_name + ":" + sub_section_name, sub_section);
        });
    });

    console.debug("POSTING: " + JSON.stringify(repr));
    return repr;
}

function stripAnnotations(context) {
    function removeAnnotation(section) {
        $.each(section, function(key, field) {
            if (field.hasOwnProperty("ref")) {
                field["ref"].closest(".control-group").attr("class", "control-group")
                    .find("span.help-block").slideUp(150, function() { this.remove() });
            }
        });
    }

    $.each(context["spec"], function(section_name, section) {
        removeAnnotation(section);
    });

    $.each(context["sub_specs"], function(sub_spec_name, sub_spec) {
        $.each(sub_spec, function(section_name, section) {
            removeAnnotation(section);
        });
    });

    $("#" + context["container_id"]).find(".fold-error-count").remove();
}

function annotateFields(context, messages) {
    // Transform messages object a bit so we can stick some metadata in it.
    messages_spec = Object();
    $.each(messages, function(section_name, section) {
        messages_spec[section_name] = { "count": 0, "section" : {} };
        $.each(section, function(key, value) {
            messages_spec[section_name]["section"][key] = value;
            messages_spec[section_name]["count"]++;
        });
    });

    var spec = context["spec"];
    var sub_specs = context["sub_specs"];

    // The meta_sections object is used to keep track of the number of
    // annotations under a nested folds header.
    var meta_sections = new Object();

    function annotateFoldHeader(fold) {
        var count = fold["count"];
        var header = fold["header"];
        header.find('.fold-error-count').remove();
        if (count > 1) {
            $("#conf-header-error-count-template").clone().appendTo(header)
                .find("font").html("(" + count + " problems)");
        } else if (count === 1) {
            $("#conf-header-error-count-template").clone().appendTo(header)
                .find("font").html("(" + count + " problem)");
        }
    }

    function addAnnotation(elements, annotations) {
        $.each(annotations["section"], function(field, message) {
            var elt = elements[field]["ref"]
            var container = elt.closest(".control-group")
            container.attr("class", "control-group error")
            var controls = container.find(".controls")
            $("#conf-error-label-template").clone().attr("id", "")
                .html(message).appendTo(controls);
            elt.focus(function() {
                if (container.attr("class") === "control-group error")
                    container.attr("class", "control-group warning");
            });
            elt.change(function() {
                if (container.attr("class") === "control-group warning") {
                    container.attr("class", "control-group info");
                }
            });
            context["errors"]++;
        });
    }

    stripAnnotations(context);

    // Reinitialize the error count.
    context["errors"] = 0;

    // Add in new annotations and update the fold headers for sections with messages.
    $.each(messages_spec, function(section_name, section) {
        if (spec.template != null) {
            // Annotate elements in section.
            addAnnotation(spec[section_name], section);

            // Collate fold errors.
            $.each(section["section"], function(field, message) {
                header = spec[section_name][field].header;
                if (!(header in meta_sections)) {
                    meta_sections[header] = Object();
                    meta_sections[header].header =
                        context["toplevel_folds"][header]
                            .closest(".accordion-group")
                            .find(".accordion-toggle");
                }

                if (meta_sections[header].count) {
                    meta_sections[header].count += 1;
                } else {
                    meta_sections[header].count = 1;
                }
            });
        }
        else {
            if (contains(section_name, ":")) {
                var components = section_name.split(":")
                var sub_spec = sub_specs[components[0]]
                var section_name = components[1];

                section["header"] = context["nested_folds"][components[0]][section_name]
                    .closest(".accordion-group").find(".accordion-toggle");

                if (typeof(meta_sections[components[0]]) === "undefined") {
                    meta_sections[components[0]] = {
                        "header": context["toplevel_folds"][components[0]]
                            .closest(".accordion-group")
                            .children()
                            .children(".accordion-toggle"),
                        "count": 0
                    };
                }
                meta_sections[components[0]]["count"] += section["count"];
                section["meta"] = meta_sections[components[0]];

                annotateFoldHeader(section);
                annotateFoldHeader(meta_sections[components[0]]);

                addAnnotation(sub_spec[section_name], section);
            } else {
                section["header"] = context["toplevel_folds"][section_name]
                    .closest(".accordion-group")
                    .find(".accordion-toggle");

                annotateFoldHeader(section);

                addAnnotation(spec[section_name], section);
            }
        }
    });

    if (spec.template != null) {
        $.each(meta_sections, function(ref, section) {
            annotateFoldHeader(section);
        });
    }

    // Display the overall error count.
    updateErrorCount(context).clearQueue().fadeIn(200);
}

function updateErrorCount(context) {
    var errors = context["errors"];
    if (errors > 1) {
        return updatePromptLabel(context,
                                 "Error", "The new configuration has "
                                 + context["errors"] + " problems.", "error");
    } else if (errors === 1) {
        return updatePromptLabel(context,
                                 "Error", "The new configuration has "
                                 + context["errors"] + " problem.", "error");
    } else {
        return updatePromptLabel(context,
                                 "Retry", "All problems appear to have been " +
                                 "addressed. Please save again.", "info");
    }
}

function postConfig(context, post_url) {
    $.ajax({
        url: post_url,
        type: "POST",
        data: JSON.stringify(readConfig(context)),
        contentType: "application/json",
        success: function() {
            updatePromptLabel(context,
                              "Success", "New configuration saved.",
                              "success")
                .clearQueue()
                .fadeIn(200)
                .delay(2000)
                .fadeTo(400, 0);
            stripAnnotations(context);
        },
        error: function(req, error, htmlError) {
            var annotations = JSON.parse(req.responseText);
            console.debug("ERRORS: " + req.responseText);
            context["errors"] = Object.keys(annotations).length;
            annotateFields(context, annotations);
        },
        complete: function() {
            enableButtons(context);
        }
    });
}

function enableButtons(context) {
    $("#conf-buttons").find("a").attr("class", "btn btn-primary");
    $("#conf-buttons").find("#conf-save-button").on("click", context["save_task"]);
    $("#conf-buttons").find("#conf-reset-button").on("click", context["reset_task"]);
}

function disableButtons(context) {
    $("#conf-buttons").find("a").attr("class", "btn btn-primary disabled");
    $("#conf-buttons").find("#conf-save-button").off("click");
    $("#conf-buttons").find("#conf-reset-button").off("click");
}

function updatePromptLabel(context, topic, message, type) {
    var label = $("#prompt-label")
    label.attr("class", "alert alert-" + type);

    label.children().remove()
    label.html($("<strong>" + topic + ": </strong>"))
    label.append(document.createTextNode(message));
    label.attr("style", "visibility:shown");
    return label;
}

function constructScaffolding(context, root, sections, exclusive, open) {
    var folds = new Object();
    var top = $("#conf-fold-template").clone()
        .attr("id", "fold-toplevel-" + root.attr("id")).appendTo(root);

    $.each(sections, function(idx, section) {
        var group = $("#conf-fold-group-template").clone()
            .attr("id", "fold-group-" + root.attr("id")).appendTo(top);

        var link = group.find("#fold-toggle")

        link.attr("href", "#fold-" + section)
            .html(capitalize(context["name_map"][section] || section));

        var body = group.find("#fold-body").attr("id", "fold-" + section);
        if (exclusive) {
            body.collapse({
                toggle: false,
                parent: "#fold-toplevel-" + root.attr("id")
            });
        } else {
            body.collapse({
                toggle: false
            });
        }

        if (open) {
            body.collapse("show");
            open = false;
        }

        folds[section] = group.find("#fold-inner").attr("id", "fold-nested-" + section);
    });

    return folds;
}

// Generates a config section based on the description provided by the
// 'spec' object, rooted at the div 'root'.
function generateSection(root, name, spec, template) {
    // Get rid of any old elements to prevent duplicates.
    root.find("form#form-" + name).remove();
    var fs = $("<fieldset/>")
        .appendTo(
            $("<form/>").attr("class", "form-inline").appendTo(root));

    var configs = new Array();
    if (typeof(template) === "undefined") {
        // Sort using the 'order' key so that all the config params show
        // up in a consistent order.
        $.each(spec, function(config_name, config) {
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
    } else {
        // Pop config items into list in order that they exist in the
        // template.
        $.each(template.items, function(idx, item) {
            // First dig out the config spec.
            path = templateItemToConfig(item.item);
            section = path[0];
            config_name = path[1];
            config = spec[section][config_name];

            // Pop it into the list.
            configs.push([ config_name, config ]);
        });
    }

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
        var cgroup = $("#conf-slot-template").clone().appendTo(root);
        cgroup.find("#conf-label").html(name);

        return cgroup.find("#conf-box")
    }

    config["skip-init"] = new Object();
    var input_elt = null;

    // Setup the generic scaffolding for a config variable.
    var slot = buildConfigSlot(root,
            config["label"] || config_name.replace("_", " "));

    config["present"] = ("value" in config);

    // Perform any type-specific setup for the variable.
    switch (config["type"]) {
    case "list":
        input_elt = $("#conf-input-list").clone().appendTo(slot);
        if (config["present"]) {
            if (typeof config["value"] == "string") {
                config["value"] = config["value"].split(",")
            }
            input_elt.html(config["value"].join("\n"));
        }
        config["skip-init"]["value"] = true;
        break;
    case "string":
        input_elt = $("#conf-input-text").clone().appendTo(slot);
        if (contains(config_name.toLowerCase(), "password"))
            input_elt.attr("type", "password");
        break;
    case "select":
        span_elt = $("#conf-input-select").clone().appendTo(slot);
        input_elt = span_elt.find("select");
        $.each(config["options"], function(i, item) {
            $('<option>', {
                text: item[0], value: item[1]
            }).appendTo(input_elt);
        });
        if (config["present"])
            input_elt.val(config["value"]);
        config["skip-init"]["value"] = true;
        attachTooltip(span_elt, config, "hover", 250);
        config["skip-init"]["tooltip"] = true;
        break;
    case "multiselect":
        span_elt = $("#conf-input-multiselect").clone().appendTo(slot);
        input_elt = span_elt.find("select");
        if (typeof config["value"] == "string") {
            config["value"] = config["value"].split(",")
        }
        $.each(config["options"], function(i, item) {
            label = item[0];
            value = item[1];
            selected = config["present"] && $.inArray(value, config["value"]) >= 0;
            opt = $('<option>', {
                text: label, value: value
            });
            if (selected)
                opt.attr('selected', true);
            opt.appendTo(input_elt);
        });
        config["skip-init"]["value"] = true;
        attachTooltip(span_elt, config, "hover", 250);
        config["skip-init"]["tooltip"] = true;
        break;
    case "integer":
        input_elt = $("#conf-input-number").clone().appendTo(slot);
        break;
    case "boolean":
        input_elt = $("#conf-input-boolean").clone().appendTo(slot);
        input_elt.attr("checked", config["value"]);
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

            if (config["present"])
                input_elt.attr("value", config["value"]);

            config["skip-init"]["value"] = true;
        }

        // Attach tooltip.
        if (!config["skip-init"]["tooltip"])
            attachTooltip(input_elt, config);

        // Register an onchange callback to mark field as modified on change.
        input_elt.change(function() { config["modified"] = true; });

        // Save reference to HTML element in config spec.
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
