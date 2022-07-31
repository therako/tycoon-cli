#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import re
from setuptools import setup, find_packages


egg = re.compile("\#egg\=(.*?)$")
requirements = open("requirements.txt").read().splitlines()
REQUIREMENTS = [
    req
    for req in requirements
    if (not req.startswith("-e") and not req.startswith("#") and req != "")
]
DEPENDENCY_LINKS = [
    req.replace("-e ", "") for req in requirements if req.startswith("-e")
]
REQUIREMENTS.extend(
    [egg.findall(req)[0] for req in requirements if req.startswith("-e")]
)

setup(
    name="tycoon_cli",
    author="Arun Kumar",
    author_email="therealrako@gmail.com",
    license="GNU General Public License v3.0",
    url="https://github.com/therako/tycoon-cli",
    description="A CLI client to play airline manager tycoon https://tycoon.airlines-manager.com",
    version="0.0.1",
    packages=find_packages(exclude=("tests",)),
    scripts=("bin/tycoon-cli",),
    install_requires=REQUIREMENTS,
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
    ],
)
