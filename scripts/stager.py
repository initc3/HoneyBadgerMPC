#!/usr/bin/env python3

from subprocess import call
import re
import argparse
import yaml
import logging

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class Stager(object):
    def __init__(self, docker_filename, dockerhub_base):
        self.dockerhub_base = dockerhub_base
        self.docker_filename = docker_filename
        self.targets, self.repositories = self._parse_docker_file(docker_filename)

    def _parse_docker_file(self, filename: str) -> tuple:
        """ Given the path to a dockerfile, parse the dockerfile
        and return a list of the targets contained in the dockerfile as well as
        a list of the repository names associated with each target.
        """
        logger.info(f"Parsing dockerfile: {filename}")

        with open(filename, "r") as docker_file:
            content = docker_file.readlines()

        regex = re.compile("FROM (.*) AS ([^#]*)(#.*)*\n")
        targets = [
            match.group(2).strip()
            for match in map(regex.match, content)
            if match is not None
        ]

        logger.info(f"Read targets: {targets}")

        repos = [f"{self.dockerhub_base}-{target}" for target in targets]

        return targets, repos

    def _get_prior_targets(self, target: str) -> list:
        """ Given the name of a target in the dockerfile, retrieve
        the names of all prior targets up to and including the specified
        target
        """
        target_idx = self.targets.index(target)
        return self.targets[: target_idx + 1]

    def _build_repo_name(self, target: str, tag: str = None):
        """ Given a target name from the dockerfile and an optional
        tag, build the string representing the full image name of the
        docker container.
        """
        repo = f"{self.dockerhub_base}-{target}"
        if tag is not None:
            repo = f"{repo}:{tag}"

        return repo

    def _run_command(self, command: str) -> int:
        """ Helper method to run a command and log it.
        Returns the status code from running the command.
        """
        logger.debug(command)
        return call(command, shell=True)

    def _push_image(self, target: str, tag: str) -> bool:
        """ Push the image with the given target and tag
        """
        repo_name = self._build_repo_name(target, tag)
        logger.info(f"Pushing image: {repo_name}")

        ret = self._run_command(f"docker push {repo_name}")
        return ret == 0

    def push(self, end_target: str, build_tags: list):
        """ Given a goal target, push that target and all intermediate stages
        beforehand with the given tags.
        """
        assert end_target in self.targets
        logger.info(f"Pushing up until target {end_target} with tags {build_tags}")
        for target in self._get_prior_targets(end_target):
            for tag in build_tags:
                if not self._push_image(target, tag):
                    exit(1)

    def _pull_image(self, target: str, tag: str) -> bool:
        """ Pull the image with the given target and tag from dockerhub
        """
        repo_name = self._build_repo_name(target, tag)
        logger.info(f"Pulling image: {repo_name}")

        ret = self._run_command(f"docker pull {repo_name}")
        return ret == 0

    def pull(self, end_target: str, build_tags: list):
        """ Given a goal target, pull all stages up to and including
        the end target with the given tags.
        """
        assert end_target in self.targets

        logger.info(
            f"Pulling all images until target {end_target} tagged with {build_tags}"
        )

        for tag in build_tags:
            for target in self._get_prior_targets(end_target):
                if not self._pull_image(target, tag):
                    exit(1)

    def _tag_image(self, target: str, from_tag: str, to_tag: str) -> bool:
        """ Tag the image with the given target and tag (from_tag)
        with the given tag name (to_tag).
        """
        from_repo = self._build_repo_name(target, from_tag)
        to_repo = self._build_repo_name(target, to_tag)

        logger.info(f"Tagging image {from_repo} as {to_repo}")
        tag_command = f"docker tag {from_repo} {to_repo}"

        ret = self._run_command(tag_command)
        return ret == 0

    def tag(self, end_target: str, build_tags: list, source_tag: str):
        """ Given a goal target, tag all images that have the given source_tag
        with the build_tags up until the target image.
        """
        assert end_target in self.targets

        logger.info(
            f"Tagging all images until given target {end_target} "
            f"and tag {source_tag} with tags {build_tags}"
        )

        for target in self._get_prior_targets(end_target):
            for tag in build_tags:
                if not self._tag_image(target, source_tag, tag):
                    exit(1)

    def _build_image(
        self,
        target: str,
        build_tag: str,
        cache: bool,
        cache_tags: list,
        cache_skip: list = [],
    ) -> bool:
        """ Build the image with the given target and build_tag.

        args:
            target (str): Target of the image to build
            build_tag (str): Tag to tag the build with
            cache (bool): Whether or not to utilize caching
            cache_tags (list): List of tags to use when caching.
                Attempts to cache using the first cache_tag, then second, etc.
            cache_skip (list): list of tuples of (target, tag) to skip when caching.

        TODO: Allow for CLI access for cache_skip
        """
        assert len(cache_tags) > 0

        repo_name = self._build_repo_name(target, build_tag)

        cache_images = []
        for prior_target in reversed(self._get_prior_targets(target)):
            for tag in cache_tags:
                if (prior_target, tag) not in cache_skip:
                    cache_images.append(self._build_repo_name(prior_target, tag))

        logger.info(
            f"Building image: {repo_name}. Cache: {cache}; cache_images: {cache_images}"
        )

        cache_flag = f"--cache-from {','.join(cache_images)}" if cache else "--no-cache"
        build_command = f"docker build -t {repo_name} --target {target} {cache_flag} ."

        ret = self._run_command(build_command)
        return ret == 0

    def build(
        self,
        end_target: str,
        build_tags: list,
        cache: bool,
        cache_tags: list,
        remote_cache: bool,
        exact: bool,
    ):
        """ Given a goal target, build all stages up until and including the specified target
        and tag the images using the provided build tags.

        args:
            end_target (str): Final target to build an image for
            build_tags (list): List of tags to tag the built images with
            cache (bool): Whether or not to utilize caching while building
            cache_tags (list): List of tags to try when caching
            remote_cache (bool): When true, download the most recent version of cache images
            exact (bool): When true, build only the specified target but
                with full caching as specified.
        """
        assert end_target in self.targets

        logger.info(
            f"Building all images until target {end_target} with tags {build_tags}. "
            f"\nCache: {cache}; remote_cache: {remote_cache}; exact: {exact}; cache_tags: {cache_tags}"
        )

        if len(build_tags) == 0:
            build_tags = ["latest"]

        if len(cache_tags) == 0:
            cache_tags = ["latest"]

        targets = [end_target] if exact else self._get_prior_targets(end_target)
        for target in targets:
            # skip failed tags
            failed_tags = []

            if cache and remote_cache:
                for tag in cache_tags:
                    if not self._pull_image(target, tag):
                        failed_tags.append((target, tag))

            if not self._build_image(
                target, build_tags[0], cache, cache_tags, cache_skip=failed_tags
            ):
                exit(1)

            # Tag built image with extra build tags too.
            for tag in build_tags[1:]:
                if not self._tag_image(target, build_tags[0], tag):
                    exit(1)


class ComposeStager(Stager):
    """ Subclass of stager that utilizes docker-compose for building.
    Note: This has poor cache performance, so is not used in production.
    """

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
        """ Builds image by dynamically creating docker-compose file based on the
        existing file, but adds cache and target instructions.
        """
        assert len(cache_tags) > 0

        build_content = {**self.compose_content}  # shallow copy

        build_content["services"]["honeybadgermpc"][
            "image"
        ] = f"{self._build_repo_name(target, build_tag)}"
        build_content["services"]["honeybadgermpc"]["build"]["target"] = target

        cached_images = []
        for cache_tag in cache_tags:
            cached_images += [
                f"{self._build_repo_name(t, cache_tag)}"
                for t in self._get_prior_targets(target)
            ]

        build_content["services"]["honeybadgermpc"]["build"][
            "cache_from"
        ] = cached_images

        build_command = f'echo "{yaml.dump(build_content)}" | docker-compose -f - build honeybadgermpc'
        if not cache:
            build_command = f"{build_command} --no-cache"

        ret = self._run_command(build_command)
        return ret == 0


def main():
    base_parser = argparse.ArgumentParser(
        description="Intelligently pull, build, upload, and tag multi-stage docker "
        "images stage-by-stage for best cache performance.",
        prog="stager",
        epilog="Author: Drake Eidukas (@Drake-Eidukas)",
    )

    base_parser.add_argument(
        "-r",
        "--repo-base",
        type=str,
        default="dsluiuc/honeybadger",
        help="Base repo name to use for dockerhub (e.g. dsluiuc/honeybadger is the "
        "base name for dsluiuc/honeybadger-dev:latest).",
    )

    base_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Enable more verbose logging levels in script. "
        "Use -v for INFO, -vv for DEBUG, and -vvv for global DEBUG.",
    )

    file_parser = base_parser.add_mutually_exclusive_group()
    file_parser.add_argument(
        "-f",
        "--dockerfile",
        type=argparse.FileType("r"),
        metavar="file",
        default="Dockerfile",
        help="Filepath to Dockerfile to use",
    )

    file_parser.add_argument(
        "--compose-file",
        type=argparse.FileType("r"),
        metavar="file",
        help="Filepath to docker-compose file to use",
    )

    target_parser = argparse.ArgumentParser(add_help=False)
    target_parser.add_argument(
        "-t",
        "--target",
        type=str,
        default=None,
        help="Target stage in dockerfile to proceed until",
    )

    target_parser.add_argument(
        "-b",
        "--build-tags",
        type=str,
        nargs="+",
        default=["latest"],
        help="Tag to use when pushing, building, pulling, or tagging.",
    )

    subparsers = base_parser.add_subparsers(dest="type", title="Subcommands")
    subparsers.add_parser(
        "pull",
        parents=[target_parser],
        description="Pull a docker image and all preceeding images from dockerhub.",
        help="Pull a docker image and all preceeding images from dockerhub."
        "\ne.g. ./scripts/stager.py pull -t prod",
    )
    subparsers.add_parser(
        "push",
        parents=[target_parser],
        description="Push a docker image and all preceeding images to dockerhub.",
        help="Push a docker image and all preceeding images to dockerhub."
        "\ne.g. ./scripts/stager.py push -t prod",
    )

    tagger = subparsers.add_parser(
        "tag",
        parents=[target_parser],
        description="Tag a docker image and all preceeding images with a provided tag.",
        help="Tag a docker image and all preceeding images with a provided tag."
        "\ne.g. ./scripts/stager.py tag -b newest -s latest to tag repo:newest as repo:latest",
    )
    tagger.add_argument(
        "-s",
        "--source-tag",
        type=str,
        default="latest",
        help="Tag of images to have another tag added."
        "\ne.g. If you wanted to re-tag repo:A as repo:B, this flag should be 'A'",
    )

    # TODO: add argument for --exclude to exclude some target:tag combos from being used to cache to the build command.
    builder = subparsers.add_parser(
        "build",
        parents=[target_parser],
        description="Build specified and all preceeding docker images.",
        help="Build specified and all preceeding docker images."
        "\ne.g. docker build -t prod -c remote",
    )
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
        help="Level of caching to use when building docker images. "
        "'none' disables caching, 'local' uses whatever is currently cached on disk, and "
        "'remote' warms up the cache by fetching the remote version of the image before building.",
    )

    builder.add_argument(
        "--cache-tags",
        type=str,
        nargs="+",
        default=["latest"],
        help="Tags to use when fetching cache images. "
        "Use when you want to cache from images with multiple tags. "
        "Tags are tried in the order given.",
    )

    args = base_parser.parse_args()
    if args.type is None:
        exit(1)

    if args.verbose >= 3:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.verbose >= 2:
        logger.setLevel(logging.DEBUG)
    elif args.verbose >= 1:
        logger.setLevel(logging.INFO)

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
