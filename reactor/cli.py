# Copyright 2013 GridCentric Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import getopt
import textwrap
import sys
import traceback

from collections import namedtuple

OptionSpec = namedtuple("OptionSpec", [
    "name",
    "description",
    "interpret_fn",
    "default"
])

DEBUG = OptionSpec(
    "debug",
    "Enable full stack errors.",
    None,
    None,
)

HELP = OptionSpec(
    "help",
    "Display this message.",
    None,
    None,
)

class InvalidArguments(Exception):
    pass

def show_help(option_specs, help_msg):
    # NOTE: We assume that the help_msg is a tuple, and
    # it has a length of either 1 or 2 (depending on whether
    # or not there is both a header and a footer). This is
    # asserted below to ensure that all callers use it as
    # expected.
    sys.stdout.write(help_msg[0])

    # Print the options.
    if len(option_specs) > 0:
        print "Options:"
        for opt in option_specs:
            if opt.interpret_fn is not None:
                front = "% 19s=" % ("--" + opt.name)
            else:
                front = "% 20s" % ("--" + opt.name)

            desc = textwrap.wrap(opt.description, 60)
            for lineno in range(len(desc)):
                if lineno == 0:
                    # Print with the option name.
                    print " %21s    %s" % (front, desc[lineno])
                else:
                    # Print without the option name.
                    print " %21s    %s" % ("", desc[lineno])

    # Print the footer, if it's given.
    if len(help_msg) == 2:
        sys.stdout.write(help_msg[1])

def parse_options(option_specs, help_msg):
    parsed_options = {}

    # Set defaults.
    for opt in option_specs:
        if opt.name in parsed_options:
            raise TypeError("Conflicting options: %s" % opt.name)
        parsed_options[opt.name] = opt.default

    # Pull options from the environment.
    for opt in option_specs:
        env_value = os.getenv("REACTOR_%s" % opt.name.upper())
        if env_value is not None:
            if opt.interpret_fn is not None:
                parsed_options[opt.name] = opt.interpret_fn(env_value)
            else:
                parsed_options[opt.name] = True

    # Construct our available options.
    available_opts = []
    for opt in option_specs:
        if opt.interpret_fn is not None:
            available_opts.append("%s=" % opt.name)
        else:
            available_opts.append(opt.name)

    # Parse all given options.
    opts, args = getopt.getopt(sys.argv[1:], "", available_opts)
    for o, a in opts:
        found_match = False
        for opt in option_specs:

            if o == "--help":
                # Special case.
                show_help(option_specs, help_msg)
                sys.exit(0)

            elif o == ("--%s" % opt.name):
                if opt.interpret_fn is not None:
                    parsed_options[opt.name] = opt.interpret_fn(a)
                else:
                    parsed_options[opt.name] = True
                found_match = True
                break

        if not found_match:
            show_help(option_specs, help_msg)
            sys.exit(1)

    # Return our dictionary.
    return parsed_options, args

def main(real_main_fn, option_specs, help_msg):
    # Ensure the help_msg is reasonable.
    assert isinstance(help_msg, tuple)
    assert len(help_msg) in (1, 2)

    # Insert our specs.
    option_specs = option_specs[:]
    option_specs.insert(0, HELP)
    option_specs.insert(1, DEBUG)

    # Parse options.
    options, args = parse_options(option_specs, help_msg)

    # Run the real main function.
    debug = options.get("debug")
    try:
        real_main_fn(options, args)
        sys.exit(0)
    except InvalidArguments:
        show_help(option_specs, help_msg)
        sys.exit(1)
    except Exception, e:
        if debug:
            traceback.print_exc()
        else:
            sys.stderr.write("%s\n" %(e))
        sys.exit(1)
