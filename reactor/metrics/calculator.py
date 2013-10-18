"""
This module is used to calculate the ideal number of instances a endpoint
requires given all the gather metrics and the scaling spec of the endpoint.
"""

import logging
import re
import math
import sys

def calculate_weighted_averages(metrics):
    """ Calculates the weighted average for each metric. """
    totals = {}
    total_weights = {}
    for metric in metrics:
        for key, info in metric.iteritems():
            # Try to be generous with our parsing of metrics, but interpret
            # each element as a float. If the user does not provide a weight we
            # assign the element a weight of 1.0 as a default value.
            try:
                (weight, value) = info
                weight = float(weight)
                value = float(value)
            except TypeError:
                try:
                    (weight, value) = (1.0, float(info))
                except ValueError:
                    continue
            except:
                continue
            totals[key] = totals.get(key, 0) + weight * value
            total_weights[key] = total_weights.get(key, 0) + weight
    for key in totals:
        if total_weights[key] != 0:
            totals[key] = (float(totals[key]) / total_weights[key])
        else:
            totals[key] = 0.0
    return totals

def calculate_num_servers_uniform(total, bound, bump_up=False, bump_down=False):
    """
    Determines the number of servers required to spread the 'total' load uniformly
    across them all so that each one has at most 'bound' amount of load.
    """
    assert not(bump_up and bump_down)

    if bound <= 0:
        # A bound of 0 essentially indicates an inifinite number of servers.
        # Return the maximum value possible.
        return sys.maxint

    if total % bound == 0:
        if bump_up:
            total += 1
        if bump_down:
            total -= 1

    return int(math.ceil(total / bound))

def calculate_server_range(total, lower, upper, lower_exact=True, upper_exact=True):
    r = []
    if lower == None and upper == None:
        # Weird rule.
        return (0, sys.maxint)
    if lower == None and upper != None:
        # There was no lower bound specified so we only use the upper bound to
        # determine the ideal number of instances.
        value = calculate_num_servers_uniform(total, upper, bump_up=not upper_exact)
        r = (value, sys.maxint)
    elif lower != None and upper == None:
        # There was no upper bound specified so we only use the lower bound to
        # determine the ideal number of instances.
        value = calculate_num_servers_uniform(total, lower, bump_down=not lower_exact)
        r = (0, value)
    elif lower != None and upper != None:
        # The ideal number of instances is a range between what satisfies the
        # lower bound and the upper bound.
        r = (calculate_num_servers_uniform(total, upper, bump_up=not upper_exact),
             calculate_num_servers_uniform(total, lower, bump_down=not lower_exact))

    return r

def calculate_ideal_uniform(endpoint_spec, metric_averages, num_instances):
    """
    Returns the ideal number of instances these endpoint spec should have as a
    tuple that defines the range (min_servers, max_servers).

    endpoint_spec:
        A list of criteria that define that define the ideal range for a metric.
            e.g. ['20<=rate<=50','100<=response<800']
        (The hits per second should be between 20 - 50 for each instance and
        the response rate should be between 100ms - 800ms.)

    metrics_averages:
        A set of metrics computed with calculate_weighted_averages.

    num_instances:
        The number of instances that produced these metrics.
    """

    logging.debug("Metric totals: %s", metric_averages)
    ideal_instances = (-1, -1)
    for criteria in endpoint_spec:
        if criteria != '':
            c = EndpointCriteria(criteria)
            logging.debug("Endpoint criteria found: (%s, %s, %s)",
                          c.metric_key, c.lower_bound, c.upper_bound)

            if c.metric_key == 'instances':
                (metric_min, metric_max) = (c.lower_bound, c.upper_bound)
            else:
                avg = metric_averages.get(c.metric_key, 0)
                (metric_min, metric_max) = \
                    calculate_server_range(avg * num_instances,
                                           c.lower_bound,
                                           c.upper_bound,
                                           lower_exact=c.lower_exact,
                                           upper_exact=c.upper_exact)

            logging.debug("Ideal instances for metric %s: [%s,%s]",
                          c.metric_key, metric_min, metric_max)

            if ideal_instances == (-1, -1):
                # First time through the loop so we just set it to the first ideal values.
                ideal_instances = (metric_min, metric_max)

            else:
                # We find the intersection of ideal servers between the
                # existing metrics and this one. If the intersections are
                # completely disjoint, we disregard the later section.
                new_min = max(ideal_instances[0], metric_min)
                new_max = min(ideal_instances[1], metric_max)

                if new_min <= new_max:
                    ideal_instances = (new_min, new_max)
                elif metric_max < ideal_instances[0]:
                    ideal_instances = (ideal_instances[0], ideal_instances[0])
                elif metric_min > ideal_instances[1]:
                    ideal_instances = (ideal_instances[1], ideal_instances[1])

            logging.debug("Returning ideal instances: %s", ideal_instances)

    return ideal_instances

class EndpointCriteria(object):

    NUMBER_PATTERN = "\s*([0-9]+([.][0-9]+)?)\s*"
    OP_PATTERN = "\s*(<=?)\s*"
    METRIC_NAME_PATTERN = "\s*(\w+)\s*"

    PATTERN = "^(" + NUMBER_PATTERN + OP_PATTERN + ")?" + \
              METRIC_NAME_PATTERN + \
              "(" + OP_PATTERN + NUMBER_PATTERN + ")?$"

    def __init__(self, criteria_str):
        self._parse(criteria_str)

    @staticmethod
    def validate(criteria_str):
        m = re.match(EndpointCriteria.PATTERN, criteria_str)
        if not m:
            raise Exception("Rules must match: %s" % EndpointCriteria.PATTERN)

    def _parse(self, criteria_str):
        """
        The criteria string is of the form:
        x [<=?] metric_key [<=?] y
        """
        m = re.match(EndpointCriteria.PATTERN, criteria_str)
        if m != None:
            try:
                self.lower_bound = m.group(2) and float(m.group(2))
            except ValueError:
                self.lower_bound = None
            self.lower_exact = m.group(4) == "<="
            self.metric_key = m.group(5)
            self.upper_exact = m.group(7) == "<="
            try:
                self.upper_bound = m.group(8) and float(m.group(8))
            except ValueError:
                self.upper_bound = None
        else:
            self.lower_bound = None
            self.lower_exact = None
            self.metric_key = None
            self.upper_bound = None
            self.upper_exact = None

    def __str__(self):
        return "%s => %s%s,%s%s" % (
            self.metric_key,
            self.lower_exact and "[" or "(",
            self.lower_bound,
            self.upper_bound,
            self.upper_exact and "]" or ")")
