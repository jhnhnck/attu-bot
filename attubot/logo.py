"""
AttuBot - Logo Rendering
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
from io import BufferedIOBase, BytesIO

from attubot.config import NovaConfig
from attubot.logging import get_logger

logger = get_logger(__name__)

async def svg_to_png(svg_data: str, height: int, width: int) -> BufferedIOBase:
    arguments = [
        '--height', str(height),
        '--width', str(width),
        '--resources-dir', str(NovaConfig.path.parent),
        '-',
        '-c']

    logger.info('Executing: $ resvg', ' '.join(arguments))

    process = await asyncio.create_subprocess_exec(
        'resvg', *arguments,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate(input=svg_data.encode('utf-8'))

    if process.returncode != 0:
        error_message = stderr.decode()
        raise RuntimeError(f'resvg failed with error:\n{error_message}')

    return BytesIO(stdout)


def generate_svg(rotation: float, foreground: str, background: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
    <svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" x="0px" y="0px"
        viewBox="0 0 1682 1682" style="enable-background:new 0 0 1682 1682;" xml:space="preserve">
    <style type="text/css">
        .back {{ fill: {background}; }}
        .fore {{ fill: {foreground}; transform-origin: center; }}
    </style>
    <g id="Layer_0" class="back">
        <circle r="841" cx="841" cy="841"/>
    </g>
    <g id="Layer_1" class="fore" transform="scale(0.925) rotate({rotation % 360})">
        <path d="M1110.2,1463c-83.1,35.1-171.3,53-262.3,53s-179.2-17.8-262.3-53c-80.2-33.9-152.3-82.5-214.2-144.4
            c-61.9-61.9-110.4-133.9-144.4-214.2c-35.1-83.1-53-171.3-53-262.3c0-90.9,17.8-179.2,53-262.3c24.8-58.6,57.4-112.8,97.3-161.9
            c-37.9-45.3-74.6-89.1-109.6-130.9C84.3,434.9,5,629,5,841.6c0,462.5,375,837.5,837.5,837.5c160.9,0,311.1-45.4,438.7-124
            c-33.7-39.7-68.9-81.2-105.3-124.2C1154.7,1442.8,1132.7,1453.5,1110.2,1463z"/>
        <path d="M585.6,221.5c83.1-35.1,171.3-53,262.3-53s179.2,17.8,262.3,53c80.2,33.9,152.3,82.5,214.2,144.4
            c61.9,61.9,110.4,133.9,144.4,214.2c35.1,83.1,53,171.3,53,262.3c0,90.9-17.8,179.2-53,262.3c-9.3,22-19.7,43.4-31.2,64.1
            c43.4,35.1,85.3,68.8,125.2,100.8c74.5-125.2,117.3-271.5,117.3-427.7c0-462.5-375-837.5-837.5-837.5C629,4.1,434.2,84,286.3,215.5
            c41.6,34.9,85.2,71.4,130.2,109.2C467.5,282.1,524.1,247.5,585.6,221.5z"/>
        <path d="M847.9,216c-149.2,0-286.4,52.5-394.1,139.9c69.1,57.9,141.4,118.3,215.4,179.9c-27.4,15.5-52.9,34.9-75.8,57.8
            c-23,23-42.4,48.7-58,76.2c-61.7-73.6-122-145.5-179.6-214.3C271.8,562,221.6,696.4,221.6,842.2c0,345.3,280.9,626.2,626.3,626.2
            c107.2,0,208.2-27.1,296.6-74.8c-59.2-70-121.2-143.4-184.5-218.6c49-17.3,93.9-45.4,131.7-83.2c39-39,67.7-85.5,84.8-136.2
            c77,63.2,152,124.5,223.4,182.4c47.4-88.1,74.4-188.9,74.4-295.8C1474.1,496.9,1193.2,216,847.9,216z M1104.5,896.5
            c-10.3,50.9-35.3,97.7-72.9,135.3c-22.1,22.1-47.3,39.8-74.7,52.7c-1.2,0.6-2.5,1.2-3.7,1.7c-2.5,1.1-5,2.2-7.6,3.3
            c-1.3,0.5-2.5,1.1-3.8,1.6c-5.1,2-10.3,3.9-15.5,5.6c-2.6,0.9-5.2,1.7-7.9,2.5c-6,1.8-12.2,3.3-18.4,4.7
            c-18.7,4.1-37.9,6.2-57.5,6.2c-71.4,0-138.5-27.8-189-78.3c-14.2-14.2-26.6-29.7-37.1-46.3c-3.5-5.5-6.8-11.2-9.9-16.9
            c-20.5-38.3-31.3-81.2-31.3-125.9c0-35.4,6.9-69.8,19.9-101.7c0.1-0.2,0.2-0.5,0.3-0.7c0.6-1.5,1.3-3,1.9-4.5
            c1.3-3,2.7-5.9,4.1-8.9c1.4-2.9,2.9-5.8,4.4-8.7c1.5-2.9,3.1-5.7,4.7-8.6c0.8-1.4,1.6-2.8,2.5-4.2c1.1-1.9,2.3-3.7,3.4-5.6
            c2.3-3.7,4.8-7.3,7.3-10.9s5.1-7.1,7.8-10.6c6.8-8.7,14.1-17,22-24.8c25.4-25.4,55-45.1,87.3-58.3c31.9-13.1,66.3-20,101.8-20
            c71.4,0,138.5,27.8,189,78.3s78.3,117.6,78.3,189C1109.8,861,1108,879,1104.5,896.5z"/>
        <path d="M974.4,717c-33.2-34.9-80.1-56.6-131.9-56.6c-100.5,0-182.3,81.8-182.3,182.3c0,100.5,81.8,182.3,182.3,182.3
            c50.3,0,95.9-20.4,128.9-53.5c1-1,2.1-2.1,3.1-3.1c2-2.1,4-4.3,5.9-6.5c1.9-2.2,3.8-4.5,5.6-6.8c24.4-31,38.9-70.1,38.9-112.5
            c0-47.1-18-90.1-47.4-122.5C976.4,719.1,975.4,718,974.4,717z"/>
    </g>
    </svg>""".strip()


async def generate_png(rotation: float, foreground: str, background: str, height: int = 500, width: int = 500) -> BufferedIOBase:
    svg = generate_svg(rotation, foreground, background)
    return await svg_to_png(svg, height, width)
