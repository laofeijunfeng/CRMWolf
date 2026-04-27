docker run \
    --restart always \
    --name=mysql_crm \
    -e MYSQL_ROOT_PASSWORD=N0k2x4gzjnbbH3zEmDPW \
    -v ~/data/var/data/mysql_crm/db:/var/lib/mysql \
    -p 3306:3306 \
    -d mysql:8.0 --default-authentication-plugin=mysql_native_password --character-set-server=UTF8MB4
