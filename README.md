# Surek

Surek is an utility built on top of Docker Compose to make managing self-hosted services easier.

It manages Caddy reverse proxy for your containers, can backup Docker volumes, and comes with Portainer and Netdata to easily manage and monitor your server.

## Install

Surek requires that you have Docker and Node.js (tested with v22) installed. It also assumes you have a domain pointed to your server.

Run this command to install Surek. If your docker installation requires using `sudo`, install Surek with `sudo` too.

```
npm install -g surek
```

## Usage

Create a folder where you wish to keep your config and service definitions (stacks). If you intend to push this folder into git, add this line to `.gitignore`

```
surek-data
```

Create a file named `surek.yml`. This is main config.

```yaml
# Root domain 
root_domain: example.com
# Used for Netdata, also can be used in stack configs
default_auth: surek:test42
# Optional. Backup volumes into S3 compatible storage
backup:
  password: "test42"
  s3_endpoint: "s3.eu-central-003.backblazeb2.com"
  s3_bucket: "surek-backup"
  s3_access_key: "beep"
  s3_secret_key: "boop"
# Optional. GitHub personal access token. Enables pulling stacks from github (including private repositories)
github:
  pat: secret
```

With central config in place, you can start system containers. Those include Caddy, Portainer, Netdata and everything else Surek needs to work properly.

```
# Run with sudo if your Docker installation requires it
surek system start
```

After system containers started, you can verify their status with command:

```
surek status
```

Next are stacks. Stack is a collection of services that are related. In Surek, stacks are stored in `stacks` folder (create it!) and defined by `surek.stack.yml` file. This file defines location of compose file and other stack parameters. 

```yaml
name: any-name-you-want
# All files we need are already here. Convenient for services that have their Docker images in the registry
source:
  type: local
  # Or pull service from Github
  # type: github
  # #ref is git reference (commit, tag, branch, etc) and is optional, will use HEAD by default
  # slug: OlegWock/repo-name#ref

# Path to compose file relative to stack config in case of local source, or relative to repo root for github sources
compose_file_path: "./docker-compose.yml"
# Optional. Services to expose as subdomains
public:
  # You can use <root> and other variables in configs (about them later)
  - domain: owncloud.<root>
    target: owncloud:8080 # <service name>:<port inside container>
    auth: admin:password123 # Optional. Adds Basic HTTP auth to subdomain
# Optional. Environment variables to add to particular (or all) container
env:
  by_container:
    owncloud: # service name
      - OWNCLOUD_DOMAIN=owncloud.<root>
      - OWNCLOUD_TRUSTED_DOMAINS=owncloud.<root>
  shared:
    - EXAMPLE=1
# Optional. Exclude certain volumes from backup
backup:
  exclude_volumes:
    - volume-name
```

And last important piece is compose file itself. You write compose files as you would do normally, except a few specifics.

* You don't need to expose any ports from container
* You should use named volumes (not bind mounts) if you want them to be backuped. It's also important to not set any parameters for these volumes (like driver or driver parameters), as they will be overwritten by Surek.
* All services (from all stacks) will be placed in same internal network, so if you have any code depending on container hostname (e.g. connecting database to app), make sure you set hostname explicitly or use unique service name for them to avoid collisions with common services (like MySQL, Redis, etc.) from other stacks.

With that finished, you can start stack with this command:

```
surek deploy <stack name from config>
```

This will deploy stack. What happens under the hood is:

1. If using GitHub, Surek will pull latest version into temporary folder.
2. Surek will copy all files from stack folder (folder where `surek.stack.yml` is stored) into temporary folder (overwriting files and merging folders). If you need to overwrite or add any files to stack pulled from GitHub repo, this is the way.
3. Surek will read compose file (by path specified in stack config), transform it by adding containers to network, updating volume configuration, etc., and save as `docker-compose.surek.yml`.
4. Docker Compose will be used to deploy the stack.

To stop stack:

```
surek stop <stack name>
```

To start stack again without re-pulling and transforming compose file:

```
surek start <stack name>
```

## Examples

You can find example stacks in [example-stacks](example-stacks/) folder.

## Variables

In Stack config, it's possible to use variables in `public.domain`, `public.auth`, and `env` sections. List of available variables:

* `<root>` – root domain, as defined in `surek.yml`.
* `<default_auth>` – shortcut for `<default_user>:<default_password>`.
* `<default_user>` – default user, as defined in `surek.yml`.
* `<default_password>` – default password, as defined in `surek.yml`.

And those are available only if you have `backup` configured in `surek.yml`:

* `<backup_password>`
* `<backup_s3_endpoint>`
* `<backup_s3_bucket>`
* `<backup_s3_access_key>`
* `<backup_s3_secret_key>`