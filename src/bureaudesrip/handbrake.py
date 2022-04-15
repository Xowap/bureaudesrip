import json
import re
import shlex
from dataclasses import dataclass
from logging import getLogger
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen
from typing import Any, Iterator, Sequence

from .errors import BureauDesRipError

logger = getLogger(__name__)

JSON_ENTRY = re.compile(r"^([\w\s]+): ({\n( .*\n)+})", re.MULTILINE)


@dataclass
class HandBrakeEntry:
    """
    During execution, HandBrakeCLI will emit several JSON objects to inform
    the calling program about progress or other things. This represents those
    messages once parsed.
    """

    name: str
    content: Any


class HandBrake:
    """
    Utility class to wrap around the HandBrakeCLI utility. Requires it to be
    installed of course.
    """

    def __init__(self, bin_name: str = "HandBrakeCLI"):
        self.bin_name = bin_name

    def make_args(self, *args):
        """
        Makes the args value to invoke HandBrakeCLI with the right binary
        and the JSON flag
        """

        return [self.bin_name, "--json", *args]

    def run(self, *args) -> Iterator[HandBrakeEntry]:
        """
        Runs HandBrake CLI and parses stdout as it goes to emit the
        HandBrakeEntry objects when they are found. They'll inform the caller
        about the progress or about the information that they're looking for.

        It's a bit twisted inside this function but it's mostly sugar and
        safeties to do what is described above.

        Parameters
        ----------
        args
            Args for HandBrakeCLI (on top of what make_args() adds)
        """

        run_args = self.make_args(*args)

        logger.debug("Running: %s", shlex.join(run_args))

        proc = Popen(
            args=run_args,
            stdout=PIPE,
            stderr=PIPE,
            stdin=PIPE,
            bufsize=1,
            encoding="utf-8",
            universal_newlines=True,
        )

        try:
            stdout = ""

            try:
                for data in proc.stdout:
                    stdout += data
                    truncate = 0

                    for match in JSON_ENTRY.finditer(stdout):
                        yield HandBrakeEntry(
                            name=match.group(1),
                            content=json.loads(match.group(2)),
                        )
                        truncate = match.endpos

                    if truncate:
                        stdout = stdout[truncate:]
            except json.decoder.JSONDecodeError:
                raise BureauDesRipError("Cannot decode JSON output")

            if proc.wait():
                raise BureauDesRipError("\n".join([*proc.stderr.readlines()][-5:]))
        finally:
            if proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

    def scan_dvd(self, path: Path):
        """
        Triggers a simple scan of all DVD titles (+ all kinds of meta info like
        subtitle languages).

        Parameters
        ----------
        path
            Path to the DVD device/file
        """

        yield from self.run("--scan", "-t", "0", "-i", f"{path}")

    def transcode_title(
        self,
        dvd_path: Path,
        output_path: Path,
        title_id: int,
        subtitle_langs: Sequence[str],
    ) -> Any:
        """
        This will transcode a title into a file. It will emit all the progress
        JSON objects as we move forward. Not gonna go in depth there, but have
        a look at __main__.py to see how to interpret those.

        Notes
        -----
        Those are the best default I could think of for a DVD RIP of identical
        quality and good compatibility with current players. Since I wrote this
        to RIP one particular series, maybe something should be changed for
        other series but I don't really care right now.

        Parameters
        ----------
        dvd_path
            Path to the DVD device/file
        output_path
            Path to the output file
        title_id
            ID of the title on the DVD
        subtitle_langs
            Languages of the subtitles that we want to keep. For the record,
            we want to keep all subtitles but it's just that HandBrake will not
            copy the subtitles unless you give it the list of languages, so
            we're getting that list from the scan that is done before and
            transfer it through this argument (but ideally I'd prefer not to
            have it).
        """

        for item in self.run(
            *["--title", f"{title_id}"],
            *["--format", "av_mkv"],
            *["--optimize"],
            *["--encoder", "x264"],
            *["--encoder-preset", "medium"],
            *["--encoder-tune", "film"],
            *["--quality", "18"],
            *["--two-pass"],
            *["--turbo"],
            *["--all-audio"],
            *["--aencoder", "copy:ac3"],
            *["--subtitle-lang-list", ",".join(subtitle_langs)],
            *["--all-subtitles"],
            *["-i", f"{dvd_path}"],
            *["-o", f"{output_path}"],
        ):
            if item.name == "Progress":
                yield item.content

    def eject(self, dvd_path: Path):
        """
        Technically not in HandBrake but well I was lazy to put this in any
        other file so there it is. It will eject the DVD to kindly signify to
        the user that the rip is complete.

        Since nothing is sure there (is the command there? is it even a DVD
        player and not an ISO image?) and that it's definitely not a critically
        important action, no hard fail will happen if the eject fails

        Parameters
        ----------
        dvd_path
            Path to the DVD device
        """

        p = Popen(
            args=["eject", f"{dvd_path}"],
            stdout=DEVNULL,
            stderr=DEVNULL,
            stdin=DEVNULL,
        )

        if p.wait():
            logger.warning("Could not eject DVD")
