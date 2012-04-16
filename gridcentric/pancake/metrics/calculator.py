"""
This module is used to calculate the ideal number of instances a service requires given
all the gather metrics and the scaling spec of the service.
"""
import logging
import re


def calculate_totals(metrics):
    """
    Calculates the totals for each metric across all the individual instances.
    """
    totals = {}
    total_weights = {}
    for metric in metrics:
        for key, info in metric.iteritems():
            (weight, value) = info
            totals[key] = totals.get(key, 0) + weight * value
            total_weights[key] = total_weights.get(key, 0) + weight
    for key in totals:
        totals[key] = (float(totals[key]) / total_weights[key])
    return totals

def calculate_num_servers_uniform(total, bound):
    return int(total / bound + (total % bound > 0))

def calculate_server_range(total, lower, upper):
    r = []
    if lower == None and upper != None:
        # There was no lower bound specified so we only use the upper bound to
        # determine the ideal number of instances.
        value = calculate_num_servers_uniform(total, upper)
        r = (value, value) 
    elif lower != None and upper == None:
        # There was no upper bound specified so we only use the lower bound to
        # determine the ideal number of instances.
        value = calculate_num_servers_uniform(total, lower)
        r = (value, value)
    elif lower != None and upper != None:
        # The ideal number of instances is a range between what satisfies the lower bound and
        # the upper bound.
        r = (calculate_num_servers_uniform(total, upper), 
                  calculate_num_servers_uniform(total, lower))

    return r

def caluculate_ideal_uniform(service_spec, metrics):
    """
    Returns the ideal number of instances these service spec should have as a tuple that
    defines the range (min_servers, max_servers).
    
    service_spec: A list of criteria that define that define the ideal range for a metric.
                e.g. ['20<=rate<=50','100<=response<800']
                (The hits per second should be between 20 - 50 for each instance
                 and the response rate should be between 100ms - 800ms.)
    
    metrics: A list of gather metrics that will be evaluated against the service_spec
    """
    
    metric_totals = calculate_totals(metrics)
    logging.debug("Metric totals: %s" %(metric_totals))
    ideal_instances = None
    for criteria in service_spec:
        c = ServiceCriteria(criteria)
        logging.debug("Service criteria found: (%s, %s, %s)" % (c.metric_key(), c.lower_bound(), c.upper_bound()))
        total = metric_totals.get(c.metric_key(), 0)
        (metric_min, metric_max) = calculate_server_range(total, c.lower_bound(), c.upper_bound())
        logging.debug("Ideal instances for metric %s: %s" %(c.metric_key(), (metric_min, metric_max)))
        if ideal_instances == None:
            # First time through the loop so we just set it to the first ideal values.
            ideal_instances = (metric_min, metric_max)
        else:
            # We find the intersection of ideal servers between the existing metrics
            # and this one.
            ideal_instances = (max(ideal_instances(0), metric_min),  min(idea_instances(1), metric_max))
        logging.debug("Returning ideal instances [%s,%s]" %(ideal_instances))
    
    return ideal_instances
    
    
class ServiceCriteria(object):
    
    def __init__(self, criteria_str):
        self.values = []
        self.operators = []
        self.key = None
        self._parse(criteria_str)

    def upper_bound(self):
        
        if len(self.values) < 2:
            # No upper bound has been defined, so we just define it as None
            self.values += [None]
        return self.values[1]

    def lower_bound(self):
        if len(self.values) < 1:
            # No lower bound has been defined, so we just define it as None
            self.values += [None]
        return self.values[0]

    def metric_key(self):
        return self.key

    def _parse(self, criteria_str):
        """
        The criteria string is of the form:
        x [<=] metric_key [<=] y
        """
        
        pattern = "((.+)(<=?))?(.+)(<=?)(.+)"
        
        m = re.match(pattern, criteria_str)
        if m != None:
            for group in list(m.groups())[1:]:
                if group != None:
                    if group.startswith("<"):
                        # This is an operator
                        self._add_operator(group)
                    else:
                        try:
                            value = float(group)
                            # This is a value because it can be casts to a float.
                            self._add_value(value)
                        except:
                            # This is the metric key
                            self._add_metric_key(group)

    def _add_value(self, value):
            self.values += [value]
        
    def _add_operator(self, operator):
        self.operators += [operator]
    
    def _add_metric_key(self, metric_key):
        self.key = metric_key
        if len(self.values) == 0:
            self.values += [None]
            self.operators += [None]     
