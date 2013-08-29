ENDPOINT_TEMPLATES = {
    "rdp" : {
            "description" : "Remote Desktop Protocol",
            "components" : [
                {
                    "name" : "loadbalancer", "description" : "RDP Settings", "items" : [
                        { "item" : "loadbalancer:rdp:username" },
                        { "item" : "loadbalancer:rdp:password" },
                        { "item" : "loadbalancer:rdp:domain" },
                        { "item" : "loadbalancer:rdp:host" },
                        { "item" : "loadbalancer:rdp:template" },
                        { "item" : "loadbalancer:rdp:reconnect" },
                        { "item" : "loadbalancer:rdp:client_subnets" }
                    ]
                },
                {
                    "name" : "cloud", "description" : "Cloud Settings", "items" : [
                        { "item" : "cloud:osvms:auth_url" },
                        { "item" : "cloud:osvms:region_name" },
                        { "item" : "cloud:osvms:username" },
                        { "item" : "cloud:osvms:tenant_name" },
                        { "item" : "cloud:osvms:password" },
                        { "item" : "cloud:osvms:instance_id" },
                        { "item" : "cloud:osvms:security_groups"},
                        { "item" : "cloud:osvms:availability_zone" }
                    ]
                },
                {
                    "name" : "scaling", "description" : "Auto-scaling", "items" : [
                        { "item" : "scaling:min_instances", "default" : "1" },
                        { "item" : "scaling:max_instances", "default" : "1" },
                        { "item" : "scaling:rules" }
                    ]
                },
                {
                    "items" : [
                        { "item" : "endpoint:url", "default" : "rdp://" },
                        { "item" : "endpoint:port", "default" : "3389" },
                        { "item" : "endpoint:cloud", "default" : "osvms" },
                        { "item" : "endpoint:loadbalancer", "default" : "rdp" },
                        { "item" : "endpoint:template", "default" : "rdp" }
                    ]
                }
            ]
        },
    "http" : {
            "description" : "HTTP-based Web Service",
            "components" : [
                {
                    "name" : "endpoint", "description" : "Endpoint", "items" : [
                        { "item" : "endpoint:url", "default" : "http://" },
                        { "item" : "endpoint:port", "default" : "80" }
                    ]
                },
                {
                    "name" : "cloud", "description" : "Cloud Settings", "items" : [
                        { "item" : "cloud:osvms:auth_url" },
                        { "item" : "cloud:osvms:region_name" },
                        { "item" : "cloud:osvms:username" },
                        { "item" : "cloud:osvms:tenant_name" },
                        { "item" : "cloud:osvms:password" },
                        { "item" : "cloud:osvms:instance_id" },
                        { "item" : "cloud:osvms:security_groups"},
                        { "item" : "cloud:osvms:availability_zone" }
                    ]
                },
                {
                    "name" : "scaling", "description" : "Auto-scaling", "items" : [
                        { "item" : "scaling:min_instances", "default" : "1" },
                        { "item" : "scaling:max_instances", "default" : "1" },
                        { "item" : "scaling:rules" }
                    ]
                },
                {
                    "items" : [
                        { "item" : "endpoint:cloud", "default" : "osvms" },
                        { "item" : "endpoint:loadbalancer", "default" : "nginx" },
                        { "item" : "loadbalancer:nginx:keepalive", "default" : 0 },
                        { "item" : "loadbalancer:nginx:ssl", "default" : false },
                        { "item" : "loadbalancer:nginx:redirect", "default" : null },
                        { "item" : "endpoint:template", "default" : "http" }
                    ]
                }
            ]
        },
    "https" : {
            "description" : "HTTPS-based Web Service",
            "components" : [
                {
                    "name" : "endpoint", "description" : "Endpoint", "items" : [
                        { "item" : "endpoint:url", "default" : "https://" },
                        { "item" : "endpoint:port", "default" : "443" }
                    ]
                },
                {
                    "name" : "loadbalancer", "description" : "SSL Settings", "items" : [
                        { "item" : "loadbalancer:nginx:ssl_certificate" },
                        { "item" : "loadbalancer:nginx:ssl_key" }
                    ]
                },
                {
                    "name" : "cloud", "description" : "Cloud Settings", "items" : [
                        { "item" : "cloud:osvms:auth_url" },
                        { "item" : "cloud:osvms:region_name" },
                        { "item" : "cloud:osvms:username" },
                        { "item" : "cloud:osvms:tenant_name" },
                        { "item" : "cloud:osvms:password" },
                        { "item" : "cloud:osvms:instance_id" },
                        { "item" : "cloud:osvms:security_groups"},
                        { "item" : "cloud:osvms:availability_zone" }
                    ]
                },
                {
                    "name" : "scaling", "description" : "Auto-scaling", "items" : [
                        { "item" : "scaling:min_instances", "default" : "1" },
                        { "item" : "scaling:max_instances", "default" : "1" },
                        { "item" : "scaling:rules" }
                    ]
                },
                {
                    "items" : [
                        { "item" : "endpoint:cloud", "default" : "osvms" },
                        { "item" : "endpoint:loadbalancer", "default" : "nginx" },
                        { "item" : "loadbalancer:nginx:keepalive", "default" : 1 },
                        { "item" : "loadbalancer:nginx:ssl", "default" : true },
                        { "item" : "loadbalancer:nginx:redirect", "default" : null },
                        { "item" : "endpoint:template", "default" : "https" }
                    ]
                }
            ]
        }
}
