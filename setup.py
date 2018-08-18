from __future__ import absolute_import
import subprocess

from setuptools import setup


setup(
    name="notedown_presenter",
    version="0.1",
    description="Convert markdown to IPython notebook with presentation metadata.",
    packages=['notedown_presenter'],
    author="Joshua Milas",
    author_email='josh.milas@gmail.com',
    license='BSD 2-Clause',
    url='http://github.com/aaren/notedown',
    install_requires=['notedown'],
)
