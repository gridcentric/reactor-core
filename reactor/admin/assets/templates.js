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
                        { "item" : "cloud:osvms:availability_zone" },
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
        }
}
