"""
An agent that runs on the same host as the load balancer (nginx) and will send data
from information gathered from the log files.
"""
import datetime
import hashlib
import httplib2
import json
import re
import threading
import time

from gridcentric.scalemanager.api import ScaleManagerApiClient

class HttpRequestThread(threading.Thread):
    
    def __init__(self, url, method, **kwargs):
        threading.Thread.__init__(self)
        self.url = url
        self.method = method
        self.kwargs = kwargs

    def run(self):
        kwargs = self.kwargs
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        if 'body' in kwargs:
            kwargs['headers']['Content-Type'] = 'application/json'
            kwargs['body'] = json.dumps(kwargs['body'])

        http = httplib2.Http()
        resp, body = http.request(self.url, self.method, **kwargs)


class NginxAgentUpdate(threading.Thread):
    
    def __init__(self, client, record):
        threading.Thread.__init__(self)
        self.client = client
        self.record = record
        
    def run(self):
        print "Updating agent record: %s" %(self.record)
        if self.record != {}:
            # There is no reason to send empty data
            self.client.update_agent_stats('NginxAgent', self.record)

class LogReader(object):
     
    def __init__(self, log_filename, filter=None):
        self.log_filename = log_filename
        self.filter = None
        if filter != None:
            self.filter = re.compile(filter)
        
    
    def connect(self):
        self.logfile = open(self.log_filename,'r')
    
    def nextline(self):
        line = self.logfile.readline()
        if self.filter != None and line != "":
            # Apply the filter to the line.
            m = self.filter.match(line)
            if m != None:
                return m.groups()
            else:
                return None
        return line

class NginxRequestAgent(object):
    """
    This will monitor the nginx access log and send information
    about the collected stats after the poll period.
    """
    
    def __init__(self, api_url, access_logfile, poll_period):
        log_filter = ".*\[(.*)\].*<(.*?)>.*?(/.*) HTTP.*"
        self.log = LogReader(access_logfile, log_filter)
        self.poll_period = poll_period
        self.execute = True
        self.api_url = api_url
        
    
    def reset_record(self):
        self.record = {}
    
    def start(self):
        self.reset_record()
        self.log.connect()
        last_push = datetime.datetime.now()
        client = ScaleManagerApiClient(self.api_url)
        while self.execute:
            line = self.log.nextline()
            if line == "":
                # The log file has not been updated since the last read.
                time.sleep(self.poll_period / 10.0)
            elif line != None:
                # We have some information
                (timeinfo, host, url_path) = line
                url = "%s%s" %(host, url_path)
                self.record[host] = self.record.get(host,0) + 1
            
            current_poll = datetime.datetime.now()
            delta = current_poll - last_push
            if delta.seconds >= self.poll_period:
                # Send up the latest results.
                request_rates = self.calculate_request_rate(delta)
                # Refresh our record
                self.reset_record()
                NginxAgentUpdate(client, request_rates).start()
                last_push = current_poll
    
    def calculate_request_rate(self, time_delta):
        request_rates = {}
        for url, count in self.record.iteritems():
            request_rates[hashlib.md5(url).hexdigest()] = (count + 0.0) / time_delta.seconds
        return request_rates

if __name__ == '__main__':
    agent = NginxRequestAgent("http://localhost:8080","/var/log/nginx/access.log",10)
    agent.start()

    