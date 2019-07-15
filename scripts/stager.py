#!/usr/bin/env python3

from os import system
import re
import argparse
import yaml


class Stager(object):
    def __init__(self, docker_filename, dockerhub_base):
        self.dockerhub_base = dockerhub_base
        self.docker_filename = docker_filename
        self.targets, self.repositories = self._parse_docker_file(docker_filename)

    def _parse_docker_file(self, filename):
        with open(filename, "r") as docker_file:
            content = docker_file.readlines()

        regex = re.compile("FROM (.*) AS ([^#]*)(#.*)*\n")
        targets = [
            match.group(2).strip()
            for match in map(regex.match, content)
            if match is not None
        ]

        repos = [f"{self.dockerhub_base}-{target}" for target in targets]

        return targets, repos

    def _get_prior_targets(self, target):
        target_idx = self.targets.index(target)
        return self.targets[: target_idx + 1]

    def _run_command(self, command):
        print(f"Running command: {command}")
        system(command)

    def _build_repo(self, target, tag=None):
        repo = f"{self.dockerhub_base}-{target}"
        if tag is not None:
            repo = f"{repo}:{tag}"

        return repo

    def _pull_image(self, target: str, tag: str):
        pull_command = f"docker pull {self._build_repo(target, tag)}"
        self._run_command(pull_command)

    def _build_image(self, target: str, build_tag: str, cache: bool, cache_tags: list):
        assert len(cache_tags) > 0

        build_command = (
            f"docker build -t {self._build_repo(target, build_tag)} --target {target}"
        )

        if cache:
            cache_images = []
            for tag in cache_tags:
                cache_images += [
                    self._build_repo(target, tag)
                    for target in reversed(self._get_prior_targets(target))
                ]

            build_command = f"{build_command} --cache-from {','.join(cache_images)} ."
        else:
            build_command = f"{build_command} --no-cache ."

        self._run_command(build_command)

    def _push_image(self, target: str, tag: str):
        push_command = f"docker push {self._build_repo(target, tag)}"
        self._run_command(push_command)

    def _tag_image(self, target: str, from_tag: str, to_tag: str):
        tag_command = f"docker tag {self._build_repo(target, from_tag)} {self._build_repo(target, to_tag)}"
        self._run_command(tag_command)

    def pull(self, end_target: str, build_tags: list):
        assert end_target in self.targets
        for tag in build_tags:
            for target in self._get_prior_targets(end_target):
                self._pull_image(target, tag)

    def build(
        self,
        end_target: str,
        build_tags: list,
        cache: bool,
        cache_tags: list,
        remote_cache: bool,
        exact: bool,
    ):
        assert end_target in self.targets

        if len(build_tags) == 0:
            build_tags = ["latest"]

        if len(cache_tags) == 0:
            cache_tags = ["latest"]

        targets = [end_target] if exact else self._get_prior_targets(end_target)
        for target in targets:
            if cache and remote_cache:
                for tag in cache_tags:
                    self.pull(target, [tag])

            self._build_image(target, build_tags[0], cache, cache_tags)

            # Tag built image with extra build tags too.
            for tag in build_tags[1:]:
                self._tag_image(target, build_tags[0], tag)

    def push(self, end_target: str, build_tags: list):
        assert end_target in self.targets
        for target in self._get_prior_targets(end_target):
            for tag in build_tags:
                self._push_image(target, tag)

    def tag(self, end_target: str, build_tags: list, source_tag: str):
        assert end_target in self.targets
        for target in self._get_prior_targets(end_target):
            for tag in build_tags:
                self._tag_image(target, tag, source_tag)


class ComposeStager(Stager):
    def __init__(self, compose_filename, dockerhub_base):
        self.compose_filename = compose_filename
        self.compose_content = self._parse_compose_file(compose_filename)

        docker_filename = self.compose_content["services"]["honeybadgermpc"]["build"][
            "dockerfile"
        ]
        super().__init__(docker_filename, dockerhub_base)

    def _parse_compose_file(self, filename):
        with open(filename, "r") as compose_file:
            return yaml.load(compose_file)

    def _build_image(self, target: str, build_tag: str, cache: bool, cache_tags: list):
        assert len(cache_tags) > 0

        build_content = {**self.compose_content}  # shallow copy

        build_content["services"]["honeybadgermpc"][
            "image"
        ] = f"{self._build_repo(target, build_tag)}"
        build_content["services"]["honeybadgermpc"]["build"]["target"] = target

        cached_images = []
        for cache_tag in cache_tags:
            cached_images += [
                f"{self._build_repo(t, cache_tag)}"
                for t in self._get_prior_targets(target)
            ]

        build_content["services"]["honeybadgermpc"]["build"][
            "cache_from"
        ] = cached_images

        build_command = f'echo "{yaml.dump(build_content)}" | docker-compose -f - build honeybadgermpc'
        if not cache:
            build_command = f"{build_command} --no-cache"

        self._run_command(build_command)


def main():
    base_parser = argparse.ArgumentParser()
    base_parser.add_argument(
        "-r",
        "--repo-base",
        type=str,
        default="dsluiuc/honeybadger",
        help="Base repo name to use for dockerhub (e.g. dsluiuc/honeybadger is the "
        "base name for dsluiuc/honeybadger-dev:latest).",
    )

    file_parser = base_parser.add_mutually_exclusive_group()
    file_parser.add_argument(
        "-f",
        "--dockerfile",
        type=argparse.FileType("r"),
        metavar="file",
        default="Dockerfile",
        help="Dockerfile to use",
    )

    file_parser.add_argument(
        "--compose-file",
        type=argparse.FileType("r"),
        metavar="file",
        help="docker-compose file to use",
    )

    target_parser = argparse.ArgumentParser(add_help=False)
    target_parser.add_argument(
        "-t",
        "--target",
        type=str,
        default=None,
        help="Target in dockerfile to proceed until",
    )

    target_parser.add_argument(
        "-b",
        "--build-tags",
        type=str,
        nargs="+",
        default=["latest"],
        help="Tag to use with dockerhub",
    )

    subparsers = base_parser.add_subparsers(dest="type")
    subparsers.add_parser("pull", parents=[target_parser])
    subparsers.add_parser("push", parents=[target_parser])

    tagger = subparsers.add_parser("tag", parents=[target_parser])
    tagger.add_argument(
        "-s",
        "--source-tag",
        type=str,
        default="latest",
        help="Tag of images to have another tag added",
    )

    builder = subparsers.add_parser("build", parents=[target_parser])
    builder.add_argument(
        "-e",
        "--exact",
        action="store_true",
        help="Only build the specified target and not preceeding targets.",
    )

    builder.add_argument(
        "-c",
        "--cache",
        type=str,
        default="local",
        choices=["none", "local", "remote"],
        help="Level of caching to use",
    )

    builder.add_argument(
        "--cache-tags",
        type=str,
        nargs="+",
        default=["latest"],
        help="Tags to use when fetching cache images",
    )

    args = base_parser.parse_args()
    if args.type is None:
        exit(1)

    dockerfile_name = args.dockerfile.name
    args.dockerfile.close()

    if args.compose_file is not None:
        filename = args.compose_file.name
        args.compose_filename.close()
        stager = ComposeStager(filename, args.repo_base)
    else:
        stager = Stager(dockerfile_name, args.repo_base)

    if args.target is None:
        args.target = stager.targets[-1]

    if args.type == "push":
        stager.push(args.target, args.build_tags)
    elif args.type == "pull":
        stager.pull(args.target, args.build_tags)
    elif args.type == "build":
        cache = args.cache in ("local", "remote")
        remote_cache = args.cache == "remote"
        stager.build(
            args.target,
            args.build_tags,
            cache,
            args.cache_tags,
            remote_cache,
            args.exact,
        )
    elif args.type == "tag":
        stager.tag(args.target, args.build_tags, args.source_tag)
    else:
        exit(1)


if __name__ == "__main__":
    main()
