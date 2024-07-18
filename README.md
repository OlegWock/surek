# surek

* ToDo: I'll write docs for this later

How to use:

Create file `surek.yml` based on `surek.yml.example`.

```bash
# Start system containers
yarn surek system start
```

Create folder `stacks/service_name`, inside which create folder `surek.stack.yml` with content like this:

```yml
# Example for owncloud

name: owncloud
source:
  type: local
compose_file_path: ./docker-compose.yml
public:
  - domain: owncloud.<root>
    target: owncloud:8080
env:
  shared:
    - NODE_ENV=dev
  by_container:
    owncloud:
      - OWNCLOUD_ADMIN_USERNAME=<default_user>
      - OWNCLOUD_ADMIN_PASSWORD=<default_password>
      - OWNCLOUD_DOMAIN=owncloud.<root>
      - OWNCLOUD_TRUSTED_DOMAINS=owncloud.<root>
```

This stack expects to have `docker-compose.yml` in same folder.

<details>
<summary>Content of compose file</summary>

```yml
services:
  owncloud:
    image: owncloud/server:10
    restart: unless-stopped
    depends_on:
      - mariadb
      - redis
    environment:
      - OWNCLOUD_DB_TYPE=mysql
      - OWNCLOUD_DB_NAME=owncloud
      - OWNCLOUD_DB_USERNAME=owncloud
      - OWNCLOUD_DB_PASSWORD=owncloud
      - OWNCLOUD_DB_HOST=mariadb
      - OWNCLOUD_MYSQL_UTF8MB4=true
      - OWNCLOUD_REDIS_ENABLED=true
      - OWNCLOUD_REDIS_HOST=redis
    volumes:
      - files:/mnt/data

  mariadb:
    image: mariadb:10.11 # minimum required ownCloud version is 10.9
    restart: unless-stopped
    environment:
      - MYSQL_ROOT_PASSWORD=owncloud
      - MYSQL_USER=owncloud
      - MYSQL_PASSWORD=owncloud
      - MYSQL_DATABASE=owncloud
      - MARIADB_AUTO_UPGRADE=1
    command: ["--max-allowed-packet=128M", "--innodb-log-file-size=64M"]
    volumes:
      - mysql:/var/lib/mysql

  redis:
    image: redis:6
    restart: unless-stopped
    command: ["--databases", "1"]
    volumes:
      - redis:/data

volumes:
  files:
  mysql:
  redis:
```

</details>

And start stack using this command

```bash
# Deploy user services
yarn surek start owncloud
```