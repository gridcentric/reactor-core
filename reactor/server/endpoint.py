# The API endpoint config blob.
APIEndpointConfig = '{              \n\
    "endpoint": {                   \n\
        "url": "http://",           \n\
        "static_instances": [       \n\
            "localhost"             \n\
        ],                          \n\
        "port": 8080,               \n\
        "loadbalancer": "nginx"     \n\
    },                              \n\
    "loadbalancer:nginx": {         \n\
        "ssl": true                 \n\
    }                               \n\
}'
