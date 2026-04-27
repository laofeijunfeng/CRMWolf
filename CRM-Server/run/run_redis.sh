docker run \
    --restart always \
    --name=redis_crm \
    -p 6379:6379 \
    -d redis:6.0.5-alpine
