"""
This module uses DOT to build a simple service graph.
This is to be used primarily for debugging (or demo) purposes.
"""

import uuid
import subprocess
from StringIO import StringIO

def dot(client, extras={}):
    # Build our string.
    output = StringIO()
    nodemap = { "" : 0 }
    
    def start_graph(output):
        output.write("digraph G {\n")
        output.write("splines=true;\n")
        output.write("pack=false;\n")
        output.write("overlap=false;\n")
        output.write("sep=0.1\n")

    def end_graph(output):
        output.write("}\n")

    def node_name(name):
        if not(name in nodemap):
            nodemap[name] = "node%d" % nodemap[""]
            nodemap[""] = nodemap[""] + 1
        return nodemap[name]

    def node_declare(name):
        output.write("%s [label=\"%s\", shape=box];\n" % (node_name(name), name))

    def build_cluster(output, name, nodes, filled=False):
        output.write("subgraph cluster_%s {\n" % node_name(name))
        output.write("label = \"%s\";\n" % name)
        if filled:
            output.write("style = filled;\n")
        for node in nodes:
            node_declare(node)
        output.write("}\n")

    def connect(output, name, node, weight=1):
        output.write("%s -> %s [penwidth=0.5, arrowsize=0.5, weight=%d];\n" % \
            (node_name(name), node_name(node), weight))

    def connect_all(output, name, nodes):
        for node in nodes:
            connect(output, name, node)

    # Grab all the nodes in the cluster.
    services = client.list_managed_services()
    managers = client.get_managers_active()
    service_ips = {}

    start_graph(output)

    # Build our clusters.
    manager_cluster = build_cluster(output, "managers", managers, filled=True)
    for service in services:
        if not(service in extras):
            service_ips[service] = client.get_service_ip_addresses(service)
            build_cluster(output, service, service_ips[service])

    # Build special clusters.
    for service in extras:
        build_cluster(output, service, extras[service], filled=True)

    # Connect the management nodes.
    for ip in managers:

        # Connect to all extras.
        for service in extras:
            connect_all(output, ip, extras[service])

        # Connect service nodes.
        for service in services:
            if not(service in extras):
                nodes = client.get_service_connections(service) or []
                connect_all(output, ip, nodes)

    end_graph(output)

    # Run it through DOT.
    dot = subprocess.Popen(["fdp", "-Tpng"], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    (stdout, stderr) = dot.communicate(output.getvalue())

    return stdout
