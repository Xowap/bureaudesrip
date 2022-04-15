#!/usr/bin/env python3
from argparse import ArgumentParser
from dataclasses import dataclass
from logging import DEBUG, getLogger
from pathlib import Path
from signal import SIGTERM, signal
from sys import stderr
from typing import Iterator, NamedTuple, Optional, Sequence

import coloredlogs
from rich.progress import Progress

from .errors import BureauDesRipError
from .handbrake import HandBrake

logger = getLogger(__name__)


@dataclass
class Output:
    """
    All the specs for one expected output file

    Other Parameters
    ----------------
    dir_path
        Path of the parent dir
    file_path
        Path to the file that will be written
    file_name
        Name of the file without the dir
    title
        ID of the DVD title to use as input
    subtitles
        Languages of the subtitles that we want
    """

    dir_path: Path
    file_path: Path
    file_name: str
    title: int
    subtitles: Sequence[str]


class Args(NamedTuple):
    """
    CLI Arguments

    Other Parameters
    ----------------
    input_file
        Path to the DVD device
    output_dir
        Directory in which files should be put
    title_map
        Episode name for each title
    series_name
        Overall series name
    episode_name_format
        Template for each file name ("{name}" will get replaced by the series
        name and "{episode}" by the episode name).
    no_eject
        Prevents from ejecting when the rip is done
    """

    input_file: Path
    output_dir: Path
    title_map: Sequence["TitleMapEntry"]
    series_name: str
    episode_name_format: str
    no_eject: bool

    def get_outputs(self, titles) -> Iterator[Output]:
        """
        Generates episode titles and such from the

        Parameters
        ----------
        titles
            That's the output of the DVD scan, that we use to get things like
            subtitle languages
        """

        for title in self.title_map:
            name = self.episode_name_format.format(
                name=self.series_name,
                episode=title.name,
            )
            file_name = f"{name}.mkv"

            title_info = None

            for candidate in titles["TitleList"]:
                if candidate["Index"] == title.title:
                    title_info = candidate

            yield Output(
                dir_path=self.output_dir,
                file_path=self.output_dir / file_name,
                file_name=file_name,
                title=title.title,
                subtitles=list(
                    set(x["LanguageCode"] for x in title_info["SubtitleList"])
                ),
            )

    def check_consistency(self, titles) -> None:
        """
        Checks that the titles the user wants to extract do actually exist in
        order to raise an error otherwise

        Parameters
        ----------
        titles
            Output of the scan
        """

        existing_titles = set(title["Index"] for title in titles["TitleList"])
        expected_titles = set(e.title for e in self.title_map)

        if not_found := expected_titles - existing_titles:
            raise BureauDesRipError(f"Titles not found: {not_found}")


@dataclass
class TitleMapEntry:
    """
    An entry of mapping between title ID and episode names, from CLI
    """

    title: int
    name: str

    @classmethod
    def parse(cls, val: str):
        """
        Called by argparse to parse the strings from CLI arguments

        Parameters
        ----------
        val
            Value to be parsed
        """

        try:
            title, name = val.split("=", maxsplit=1)
            return cls(int(title), name)
        except Exception:
            raise ValueError(
                "Title map should be of format '{title_id}={title_name}', by example '1=S02E04'"
            )


def parse_args(argv: Optional[Sequence[str]] = None) -> Args:
    """
    Configures and calls argparse

    Parameters
    ----------
    argv
        Optional array of arguments from CLI, using system argv otherwise
    """

    parser = ArgumentParser()
    parser.add_argument("-i", "--input-file", type=Path, default="/dev/dvd")
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument(
        "-t", "--title-map", type=TitleMapEntry.parse, nargs="+", required=True
    )
    parser.add_argument("-n", "--series-name", required=True)
    parser.add_argument(
        "-f", "--episode-name-format", default="{name} — DVDRip — {episode}"
    )
    parser.add_argument("--no-eject", default=False, action="store_true")

    return Args(**parser.parse_args(argv).__dict__)


def sigterm_handler(_, __):
    """
    Raises an exception on SIGTERM to leave a chance to all context managers
    and finally blocks to close their resources.
    """

    raise SystemExit(1)


def main(argv: Optional[Sequence[str]] = None):
    """
    Main logic, basically we parse the user input and DVD the we orchestrate
    the transcoding of all is fine.

    Parameters
    ----------
    argv
        Optional argv array, defaults to the system one (you can give your own
        stuff if you want to call this from another Python function)
    """

    args = parse_args(argv)

    hb = HandBrake()
    scan = None

    logger.info("Analyzing DVD")
    with Progress() as progress:
        task = progress.add_task("Scanning", total=100)

        for update in hb.scan_dvd(args.input_file):
            if update.name == "JSON Title Set":
                scan = update.content
            elif update.name == "Progress":
                progress.update(
                    task, completed=update.content["Scanning"]["Progress"] * 100
                )

    if scan is None:
        raise BureauDesRipError("Could not find scan output")

    logger.debug("Checking consistency")
    args.check_consistency(scan)

    for output in args.get_outputs(scan):
        logger.info("Ripping title %s into directory %s", output.title, output.dir_path)
        output.dir_path.mkdir(parents=True, exist_ok=True)
        process = hb.transcode_title(
            args.input_file, output.file_path, output.title, output.subtitles
        )

        with Progress() as progress:
            scanning = progress.add_task("Scanning", total=100)
            transcoding = progress.add_task("Transcoding", total=100)

            for update in process:
                state = update["State"]

                if state == "SCANNING":
                    progress.update(
                        scanning, completed=update["Scanning"]["Progress"] * 100
                    )
                elif state == "WORKING":
                    progress.update(scanning, completed=100)
                    progress.update(
                        transcoding, completed=update["Working"]["Progress"] * 100
                    )

    if not args.no_eject:
        logger.info("Ejecting")
        hb.eject(args.input_file)


def __main__():
    """
    A bit of sugar around the real main function, to configure logging and
    signal handlers.
    """

    signal(SIGTERM, sigterm_handler)

    try:
        coloredlogs.install(
            level=DEBUG,
            fmt="%(asctime)s %(name)s[%(process)d] %(levelname)s %(message)s",
        )

        main()
    except KeyboardInterrupt:
        stderr.write("ok, bye\n")
        exit(1)
    except BureauDesRipError as e:
        stderr.write(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    __main__()
