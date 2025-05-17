import re
import logging
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Tuple, Union

from html2text import html2text

from . import reference, aw
from .logging_utils import configure_logging, format_pandas_for_logging

__all__ = [
    "reference",
    "build_data_directory",
    "configure_logging",
    "strip_html_tags",
    "cleanup_string",
    "aw",
]


# helper for cleaning up HTML strings
# From - https://stackoverflow.com/questions/753052/strip-html-from-strings-in-python
class _MLStripper(HTMLParser):

    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self) -> str:
        return "".join(self.fed)


def strip_html_tags(html: str) -> str:
    """
    Remove HTML tags from a string.

    Args:
        html: HTML string to be cleaned.

    Returns:
        String with HTML tags removed.
    """
    s = _MLStripper()
    s.feed(html)
    return s.get_data()


def build_data_directory(dir_path: Union[str, Path]) -> Path:
    """
    Create a directory in the specified path.

    .. note::
        If the parents for the directory path do not exist, they will automatically be created.

    Args:
        dir_path: Path where directory shall be created.

    Returns:
        Path to directory location.
    """
    # make sure working with a Path
    if isinstance(dir_path, str):
        dir_path = Path(dir_path)

    # if already exists, leave it alone
    if dir_path.exists():
        logging.debug(f'Directory already exists, so not recreating, "{dir_path}"')

    # if does not exist, create it
    else:
        dir_path.mkdir(parents=True)
        logging.info(f'Created directory at "{dir_path}"')

    return dir_path


def build_data_resources(data_dir: Union[str, Path]) -> Path:
    """
    Build out standard data directory structure in location where data shall reside for the project.

    Args:
        data_dir: Path to where data directory resides.

    Returns:
        Path to data directory.
    """
    # make sure working with a Path
    if isinstance(data_dir, str):
        data_dir = Path(data_dir)

    # build the parent data directory
    build_data_directory(data_dir)

    # build the four directories for the different types of data
    build_data_directory(data_dir / "external")
    build_data_directory(data_dir / "raw")
    build_data_directory(data_dir / "interim")
    build_data_directory(data_dir / "processed")

    return data_dir


def cleanup_string(input_string: str) -> str:
    """Helper function to clean up description strings."""

    # ensure something to work with
    if len(input_string) == 0:
        return input_string

    # convert to markdown first, so any reasonable formatting is retained
    cleanup = html2text(input_string)

    # since people love to hit the space key multiple times in stupid places, get rid of multiple space, but leave
    # newlines in there since they actually do contribute to formatting
    cleanup = re.sub(r"\s{2,}", " ", cleanup)

    # apparently some people think it is a good idea to hit return more than twice...account for this foolishness
    cleanup = re.sub(r"\n{3,}", "\n\n", cleanup)
    cleanup = re.sub(r"(.)\n(.)", r"\g<1> \g<2>", cleanup)

    # get rid of any trailing newlines at end of entire text block
    cleanup = re.sub(r"\n+$", "", cleanup)

    # correct any leftover standalone links
    cleanup = cleanup.replace("<", "[").replace(">", "]")

    # get rid of any leading or trailing spaces
    cleanup = cleanup.strip()

    # finally call it good
    return cleanup


def remove_backslashes(input_str: str) -> str:
    """Helper function to remove backslashes from a string if there is a string to work with."""
    if isinstance(input_str, str) and len(input_str):
        return input_str.replace("\\", "")
    else:
        return input_str


def get_difficulty_parts(
    difficulty_combined: str,
) -> tuple[str | None, str | None, str | None]:
    match = re.match(
        r"^([I|IV|V|VI|5\.\d]{1,3}(?=-))?-?([I|IV|V|VI|5\.\d]{1,3}[+|-]?)\(?([I|IV|V|VI|5\.\d]{0,3}[+|-]?)",
        difficulty_combined,
    )

    # helper function to get difficulty parts
    get_if_match = lambda match_string: (
        match_string if match_string and len(match_string) else None
    )

    # get the match parts
    minimum = get_if_match(match.group(1))
    maximum = get_if_match(match.group(2))
    outlier = get_if_match(match.group(3))

    return minimum, maximum, outlier
