#!/usr/bin/env python3

from setuptools import setup, find_packages

setup(
    name="diskface",
    version="1.0.0",
    description="Interactive disk space analyzer and cleaner",
    author="Becky",
    python_requires=">=3.7",
    packages=find_packages(),
    py_modules=["diskface"],
    install_requires=[
        "rich>=12.0.0",
    ],
    entry_points={
        "console_scripts": [
            "diskface=diskface:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
    ],
) 