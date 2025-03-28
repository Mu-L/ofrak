import asyncio
import logging
import os
import tempfile312 as tempfile
from dataclasses import dataclass
from subprocess import CalledProcessError

from ofrak.component.packer import Packer
from ofrak.component.unpacker import Unpacker
from ofrak.resource import Resource
from ofrak.core.filesystem import File, Folder, FilesystemRoot, SpecialFileType
from ofrak.core.magic import MagicMimePattern, MagicDescriptionPattern
from ofrak.core.binary import GenericBinary

from ofrak.model.component_model import ComponentExternalTool
from ofrak_type.range import Range

LOGGER = logging.getLogger(__name__)

ZIP_TOOL = ComponentExternalTool(
    "zip",
    "https://linux.die.net/man/1/zip",
    install_check_arg="--help",
    apt_package="zip",
    brew_package="zip",
)
UNZIP_TOOL = ComponentExternalTool(
    "unzip",
    "https://linux.die.net/man/1/unzip",
    install_check_arg="--help",
    apt_package="unzip",
    brew_package="unzip",
)


@dataclass
class ZipArchive(GenericBinary, FilesystemRoot):
    """
    Filesystem stored in a zip archive.
    """


class ZipUnpacker(Unpacker[None]):
    """
    Unpack (decompress) a zip archive.
    """

    targets = (ZipArchive,)
    children = (File, Folder, SpecialFileType)
    external_dependencies = (UNZIP_TOOL,)

    async def unpack(self, resource: Resource, config=None):
        zip_view = await resource.view_as(ZipArchive)
        async with resource.temp_to_disk(suffix=".zip") as temp_path:
            with tempfile.TemporaryDirectory() as temp_dir:
                cmd = [
                    "unzip",
                    temp_path,
                    "-d",
                    temp_dir,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                )
                returncode = await proc.wait()
                if proc.returncode:
                    raise CalledProcessError(returncode=returncode, cmd=cmd)
                await zip_view.initialize_from_disk(temp_dir)


class ZipPacker(Packer[None]):
    """
    Pack files into a compressed zip archive.
    """

    targets = (ZipArchive,)
    external_dependencies = (ZIP_TOOL,)

    async def pack(self, resource: Resource, config=None):
        zip_view: ZipArchive = await resource.view_as(ZipArchive)
        flush_dir = await zip_view.flush_to_disk()
        temp_archive = f"{flush_dir}.zip"
        cwd = os.getcwd()
        os.chdir(flush_dir)
        cmd = [
            "zip",
            "-r",
            temp_archive,
            ".",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
        )
        returncode = await proc.wait()
        if proc.returncode:
            raise CalledProcessError(returncode=returncode, cmd=cmd)
        os.chdir(cwd)
        with open(temp_archive, "rb") as fh:
            resource.queue_patch(Range(0, await zip_view.resource.get_data_length()), fh.read())


MagicMimePattern.register(ZipArchive, "application/zip")
MagicDescriptionPattern.register(
    ZipArchive, lambda desc: any([("Zip archive data" in s) for s in desc.split(", ")])
)
