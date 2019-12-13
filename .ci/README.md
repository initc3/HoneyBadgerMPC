# Notes on working with Travis CI

## Encrypting Environment Variables
**Example**: Encrypting credentials for Docker Hub, for the `ic3bot`
machine user.

**Encrypting the username**:

```shell
$ travis encrypt --org --repo initc3/HoneyBadgerMPC DOCKER_USERNAME=ic3bot --add env.global
```

**Encrypting the password**:

```shell
$ travis encrypt --org --repo initc3/HoneyBadgerMPC DOCKER_PASSWORD="<access_token>" --add env.global
```

**SUPER DUPER IMPORTANT**: `--repo initc3/HoneyBadgerMPC` Without this
option the encrypted variables will or may not be avaiable to the
initc3/HoneyBadgerMPC repo.

**How to get a Docker Hub access token?**
Login with the `ic3bot` machine user at https://hub.docker.com/ and
go to https://hub.docker.com/settings/security to create a new access
token.


## Encrypting files
**Use case**: Publish docs to Github Pages from Travis CI.

Prerequisite: Generate an ssh key, named `deploy_key`.

```shell
$ travis login --org --github-token <token>
$ travis encrypt-file --org --repo initc3/HoneyBadgerMPC deploy_key
```

**How to get a Github token?**
Login with the `ic3bot` machine user at https://github.com/, and go to
https://github.com/settings/tokens, select "Personal access tokens" and
generate a new token.
